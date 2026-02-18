# LLM Orchestrator — Architecture Reference

**Version**: 1.1.0
**Last updated**: 2026-02
**Status**: Production-ready (single service), SuperOrchestrator available for multi-service

---

## Changelog

| Version | Date    | Changes |
|---------|---------|---------|
| 1.1.0   | 2026-02 | `build_messages()` 표준화, 범용 InMemoryStore, manifest_loader 도입, `make_error_event` 통일, minimal 템플릿 생성, ARCHITECTURE.md 개정 |
| 1.0.0   | 2026-01 | 초기 아키텍처: CoreOrchestrator, Agent/Runner/Handler 패턴, 배치 task_queue, 자동 요약 메모리 |

---

## 1. 전체 아키텍처

```
HTTP Request (POST /v1/agent/chat/stream)
        │
        ▼
  FastAPI Router  ─── create_agent_router(orchestrator)
        │
        ▼
  CoreOrchestrator.handle_stream(session_id, user_message)
        │
        ├─ 1. SessionStore.get_or_create()    → state, memory
        ├─ 2. [IntentAgent.run()]             → scenario  (등록된 경우만)
        ├─ 3. FlowRouter.route()              → flow_key
        └─ 4. FlowHandler.run(ctx)            → Generator[events]
                   │
                   ├─ Agent 실행 (slot / interaction / execute …)
                   ├─ StateManager.apply(delta) → state 전이
                   └─ yield events → SSE stream
        │
        ▼
  SessionStore.save_state()   (finally 블록 — 예외 발생해도 저장)
        │
        ▼
  SSE 이벤트 스트림 → 클라이언트
```

### 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **단일 턴** | 1 HTTP 요청 = 1 `run_one_turn()`. 멀티턴은 반복 API 호출로 구현 |
| **Handler 중심** | Agent 실행 순서·분기 로직은 FlowHandler 안에만 존재 |
| **Context-first** | Agent는 `ExecutionContext`만 읽음. 저장소 직접 접근 없음 |
| **이벤트 스트리밍** | SSE로 실시간 진행 상황·토큰을 클라이언트에 전달 |
| **Manifest 조립** | YAML + manifest.py → CoreOrchestrator. 코드 변경 없이 서비스 교체 |

---

## 2. 디렉터리 구조

```
app/
├── core/                              ← 도메인 무관 프레임워크 (수정 금지)
│   ├── config.py                      ← 환경변수 → Settings 싱글톤
│   ├── context.py                     ← ExecutionContext + build_messages()
│   ├── events.py                      ← EventType enum
│   ├── agents/
│   │   ├── base_agent.py              ← BaseAgent (LLM 호출, tool-call 루프)
│   │   ├── agent_runner.py            ← AgentRunner (재시도, 검증, 타임아웃)
│   │   └── registry.py                ← build_runner() — card.json으로 인스턴스 생성
│   ├── orchestration/
│   │   ├── orchestrator.py            ← CoreOrchestrator (단일 턴 실행기)
│   │   ├── flow_handler.py            ← BaseFlowHandler 인터페이스
│   │   ├── flow_router.py             ← BaseFlowRouter 인터페이스
│   │   ├── flow_utils.py              ← update_memory_and_save()
│   │   ├── defaults.py                ← make_error_event() 공통 에러 응답
│   │   ├── manifest_loader.py         ← resolve_class, load_yaml, build_agents_from_yaml
│   │   └── super_orchestrator.py      ← SuperOrchestrator, KeywordServiceRouter, A2AServiceProxy
│   ├── state/
│   │   ├── base_state.py              ← BaseState (scenario, stage, meta, task_queue)
│   │   ├── base_state_manager.py      ← BaseStateManager.apply(delta) → state
│   │   └── stores.py                  ← InMemorySessionStore, InMemoryCompletedStore
│   ├── memory/
│   │   └── memory_manager.py          ← 자동 요약, raw_history 관리
│   ├── llm/
│   │   └── openai_client.py           ← OpenAI SDK 래퍼
│   ├── tools/
│   │   ├── base_tool.py               ← BaseTool 인터페이스
│   │   ├── calculator.py              ← Calculator 구현체 (예시)
│   │   └── registry.py                ← TOOL_REGISTRY, build_tools()
│   └── api/
│       ├── schemas.py                 ← OrchestrateRequest / OrchestrateResponse
│       └── router_factory.py          ← create_agent_router(orchestrator) → APIRouter
│
├── projects/
│   ├── minimal/                       ← 새 프로젝트 시작점 (복사해서 사용)
│   └── transfer/                      ← 이체 서비스 참조 구현 (복잡한 케이스)
│
└── main.py                            ← FastAPI 앱 진입점
```

---

## 3. 이벤트 스펙 (SSE 스트림)

모든 이벤트는 `{"event": "<EventType>", "payload": {...}}` 구조다.
SSE 전송 시 `event:` 필드와 `data:` 필드로 분리된다.

### 이벤트 목록

| EventType | 방향 | payload 구조 | 설명 |
|-----------|------|--------------|------|
| `AGENT_START` | server→client | `{agent, label}` | 에이전트 실행 시작 |
| `AGENT_DONE` | server→client | `{agent, label, success, [stage], [result]}` | 에이전트 실행 완료 |
| `LLM_TOKEN` | server→client | `"토큰 문자열"` | 스트리밍 텍스트 조각 |
| `LLM_DONE` | server→client | `{action, message, ...}` | 스트리밍 완료, 파싱된 결과 |
| `TASK_PROGRESS` | server→client | `{index, total, slots}` | 배치 작업 진행 상황 |
| `DONE` | server→client | 아래 참조 | **턴 종료. 반드시 마지막 이벤트** |

### DONE 이벤트 payload (필수 필드)

```json
{
  "message":        "사용자에게 보여줄 텍스트",
  "next_action":    "ASK | CONFIRM | DONE | ASK_CONTINUE",
  "ui_hint":        {"buttons": ["확인", "취소"]},
  "state_snapshot": { ...현재 state.model_dump()... }
}
```

| next_action | UI 의미 | 버튼 예시 |
|-------------|---------|-----------|
| `ASK` | 자유 텍스트 입력 대기 | 없음 |
| `CONFIRM` | 예/아니오 확인 | `["확인", "취소"]` |
| `ASK_CONTINUE` | 계속/중단 선택 | `["계속 진행", "취소"]` |
| `DONE` | 플로우 종료 | 없음 |

### 한 턴의 전형적인 이벤트 흐름 (이체 서비스)

```
AGENT_START  {agent:"intent", label:"의도 파악 중"}
AGENT_DONE   {agent:"intent", result:"TRANSFER", success:true}
AGENT_START  {agent:"slot",   label:"정보 추출 중"}
AGENT_DONE   {agent:"slot",   label:"정보 추출 완료", success:true, stage:"FILLING"}
AGENT_START  {agent:"interaction", label:"응답 생성 중"}
LLM_TOKEN    "누"
LLM_TOKEN    "구"
LLM_TOKEN    "에게"
...
LLM_DONE     {action:"ASK", message:"누구에게 얼마를 보내드릴까요?"}
AGENT_DONE   {agent:"interaction", success:true}
DONE         {message:"...", next_action:"ASK", ui_hint:{}, state_snapshot:{stage:"FILLING",...}}
```

---

## 4. API 엔드포인트

```
POST /v1/agent/chat               비스트리밍. 최종 DONE payload만 반환
POST /v1/agent/chat/stream        SSE 스트리밍. 위 이벤트 흐름 그대로 전송
GET  /v1/agent/chat/stream        브라우저 EventSource용 (GET 방식 SSE)
GET  /v1/agent/completed          세션별 완료 이력 조회
GET  /v1/agent/debug/{session_id} 세션 내부 상태 스냅샷 (DEV_MODE=true 시만)
```

---

## 5. 프론트엔드 통합 가이드

### 이 백엔드로 어떤 프론트든 붙일 수 있다

- **Streamlit**: `api_client.py`의 `stream_chat()` 참조
- **React / Vue / Next.js**: 브라우저 네이티브 `EventSource` 또는 `fetch` + ReadableStream
- **React Native / Flutter**: SSE 라이브러리 + JSON 파싱
- **서버 사이드**: Python `sseclient`, Go `eventsource` 등

### React 예시 (EventSource)

```javascript
const source = new EventSource(
  `/v1/agent/chat/stream?session_id=${sessionId}&message=${encodeURIComponent(text)}`
);

source.addEventListener("AGENT_START", (e) => {
  const { agent, label } = JSON.parse(e.data);
  setAgentStatus({ agent, label, running: true });
});

source.addEventListener("AGENT_DONE", (e) => {
  const { agent, success, stage } = JSON.parse(e.data);
  setAgentStatus({ agent, running: false, success, stage });
});

source.addEventListener("LLM_TOKEN", (e) => {
  setStreamingText(prev => prev + JSON.parse(e.data));
});

source.addEventListener("DONE", (e) => {
  const { message, next_action, ui_hint, state_snapshot } = JSON.parse(e.data);
  setMessages(prev => [...prev, { role: "assistant", content: message }]);
  setButtons(ui_hint.buttons || []);
  setCurrentState(state_snapshot);   // 슬롯 채움 현황, stage 등 UI에 표시 가능
  source.close();
});
```

### POST + fetch (스트리밍)

```javascript
const res = await fetch("/v1/agent/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ session_id: sessionId, message: text }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  // SSE 라인 파싱: "event: TYPE\ndata: {...}\n\n"
  parseSSEChunk(decoder.decode(value));
}
```

### state_snapshot 활용

```javascript
// DONE 이벤트의 state_snapshot으로 UI 상태 동기화
if (state_snapshot.stage === "FILLING") {
  showSlotProgress(state_snapshot.slots, state_snapshot.missing_required);
}
if (state_snapshot.stage === "READY") {
  highlightConfirmButton();
}
```

### 웹훅 / 서버 사이드 연동

```javascript
// next_action으로 다음 UI 동작 결정
switch (next_action) {
  case "CONFIRM":
    showConfirmDialog(message, ui_hint.buttons);
    break;
  case "ASK_CONTINUE":
    showContinueDialog(message, ui_hint.buttons);
    break;
  case "DONE":
    showCompletionMessage(message);
    resetSession();
    break;
  default: // ASK
    enableTextInput();
}
```

---

## 6. 핵심 컴포넌트 상세

### 6-1. ExecutionContext

```python
@dataclass
class ExecutionContext:
    session_id: str
    user_message: str
    state: Any           # BaseState 상속 객체
    memory: dict         # {"raw_history": [...], "summary_text": "..."}
    metadata: dict       # 실행 중 임시 데이터 (에러 정보, prior_scenario 등)

    def get_history(self, last_n=12) -> list:
        """raw_history에서 최근 last_n 개 메시지 반환."""

    def build_messages(self, context_block="", last_n_turns=6) -> list:
        """
        표준 Context Engineering 메시지 빌더.
        반환: [system: context_block+summary] + [history] + [current user message]
        """
```

**`build_messages()` 사용 원칙**:
- `context_block`: 동적 상태 정보 (stage, slots 등). 정적 지침은 포함하지 않음
- `BaseAgent.chat(messages)` 가 `self.system_prompt` (정적 지침) 을 자동으로 첫 번째에 추가
- 따라서 최종 LLM 입력 = `[system: agent instructions] + build_messages() 결과`

```python
# Agent.run() 패턴
context_block = f"현재 stage: {ctx.state.stage}"
messages = ctx.build_messages(context_block)   # summary + history + user_message 포함
raw = self.chat(messages)                       # self.system_prompt 자동 prepend
```

---

### 6-2. BaseAgent

```python
class BaseAgent:
    output_schema: str = None       # AgentRunner 출력 검증용 Pydantic 모델명
    supports_stream: bool = False   # True면 run_stream() 구현 필요

    def chat(self, messages: list) -> str:
        """[system: self.system_prompt] + messages 로 LLM 호출. tool-call 루프 내장."""

    def chat_stream(self, messages: list) -> Generator[str, None, None]:
        """스트리밍 토큰 생성. tools 미지원."""

    # 반드시 구현:
    def run(self, context: ExecutionContext, **kwargs) -> dict: ...
    def run_stream(self, context: ExecutionContext, **kwargs) -> Generator: ...  # supports_stream=True 시
```

**새 Agent 체크리스트**:

```
agents/my_agent/
├── __init__.py
├── agent.py    ← MyAgent(BaseAgent), get_system_prompt() classmethod, run() 구현
├── prompt.py   ← SYSTEM_PROMPT 상수 + get_system_prompt() 함수
└── card.json   ← LLM 설정 + 실행 정책
```

```json
// card.json
{
  "llm": { "model": "gpt-4.1-mini", "temperature": 0 },
  "policy": {
    "max_retry": 3,
    "backoff_sec": 1,
    "timeout_sec": 10,
    "schema": "MyResult"     // 선택: Pydantic 검증 모델명
  },
  "tools": ["calculator"]    // 선택: TOOL_REGISTRY에 등록된 툴
}
```

---

### 6-3. AgentRunner

`card.json` → Agent 인스턴스 + 정책으로 자동 생성. 직접 다룰 일 거의 없음.

```python
runner.run("slot", ctx)              # 동기 실행, dict 반환
runner.run_stream("interaction", ctx) # 스트리밍, Generator[event] 반환
runner.has_agent("intent")           # 에이전트 등록 여부 확인
```

---

### 6-4. Memory 구조

```
memory (dict):
  raw_history:   [{role, content}, ...]   # 최근 대화 원문
  summary_text:  "..."                    # LLM이 생성한 이전 대화 요약

자동 요약 트리거:
  raw_history 턴 수 ≥ MEMORY_SUMMARIZE_THRESHOLD (기본 8)
       ↓
  오래된 턴 → LLM 요약 → summary_text 누적
       ↓
  raw_history = 최근 MEMORY_KEEP_RECENT_TURNS (기본 4) 턴만 유지

중요: summary_text는 세션/플로우 리셋 후에도 유지 → 장기 맥락 보존
```

`MemoryManager`는 서비스별 요약 프롬프트를 주입받는다:

```python
MemoryManager(
    summary_system_prompt="도메인 특화 요약 지침...",
    summary_user_template="요약 형식... {memory_block} ... {dialog} ...",
)
```

---

### 6-5. BaseFlowHandler

```python
class BaseFlowHandler:
    def __init__(self, runner, sessions, memory_manager, state_manager_factory, completed=None):
        ...

    def run(self, ctx: ExecutionContext) -> Generator[dict, None, None]:
        # 반드시 구현. 내부에서 이벤트를 yield한다.
```

**Handler 작성 패턴**:

```python
class MyFlowHandler(BaseFlowHandler):
    def run(self, ctx):
        # 1. Agent 실행
        yield {"event": EventType.AGENT_START, "payload": {"agent": "chat", "label": "생성 중"}}
        payload = None
        for ev in self.runner.run_stream("chat", ctx):
            yield ev
            if ev["event"] == EventType.LLM_DONE:
                payload = ev["payload"]
        yield {"event": EventType.AGENT_DONE, "payload": {"agent": "chat", "success": True}}

        # 2. 메모리 업데이트 (턴 종료 전 필수)
        if payload:
            update_memory_and_save(
                self.memory_manager, self.sessions,
                ctx.session_id, ctx.state, ctx.memory,
                ctx.user_message, payload.get("message", ""),
            )

        # 3. DONE 이벤트 (반드시 마지막, 반드시 포함)
        yield {
            "event": EventType.DONE,
            "payload": {
                "message": payload.get("message", ""),
                "next_action": "ASK",
                "ui_hint": {},
                "state_snapshot": ctx.state.model_dump(),
            },
        }
```

---

## 7. 새 프로젝트 만들기

### Step 1: minimal 복사

```bash
cp -r app/projects/minimal app/projects/my_service
```

### Step 2: 서비스 정의

| 파일 | 수정 내용 |
|------|-----------|
| `agents/chat_agent/prompt.py` | 서비스 역할, 성격, 지침 작성 |
| `agents/chat_agent/card.json` | LLM 모델, 온도, 정책 설정 |
| `project.yaml` | name 변경 |
| `manifest.py` | `PROJECT_MODULE`, `_AGENT_CLASS_MAP` 변경 |

### Step 3: main.py에 등록

```python
from app.projects.my_service.manifest import load_manifest
manifest = load_manifest()
orchestrator = CoreOrchestrator(manifest)
```

### Step 4 (선택): 복잡한 서비스로 확장

transfer 프로젝트를 참고해서 추가:
- `IntentAgent` → 시나리오 분류
- `SlotFillerAgent` → 정보 추출
- `StateManager` + Stage enum → 상태 머신
- 다수 FlowHandler → 시나리오별 플로우

---

## 8. 복잡한 패턴 (transfer 참조)

### 8-1. 슬롯 기반 상태 머신

```
INIT → (슬롯 제공) → FILLING → (모두 채움) → READY
READY → (확인) → CONFIRMED → EXECUTED | FAILED
READY → (취소) → CANCELLED
FILLING → (횟수 초과) → UNSUPPORTED
```

- `SlotFillerAgent`: 사용자 발화 → `{"operations": [...]}` 반환
- `StateManager.apply(delta)`: operations 실행 → 슬롯 채움 → 단계 전이
- `READY` 단계: 결정론적 코드 응답 (LLM 호출 없이 토큰 절약)

### 8-2. 다건(Multi-task) 처리

```python
# SlotFillerAgent가 다건 감지 시:
{"tasks": [{"target": "A", "amount": 10000}, {"target": "B", "amount": null}]}

# Handler에서 분리:
ctx.state.task_queue = tasks[1:]  # 나머지는 큐에
# 현재 턴에서 tasks[0] 처리 → 완료 후 task_queue에서 하나씩 꺼내 진행
```

### 8-3. LLM 호출 절약 (결정론적 응답)

```python
if ctx.state.stage == Stage.READY:
    message = _build_ready_message(ctx.state)  # 코드로 생성
    update_memory_and_save(...)
    yield {"event": EventType.DONE, "payload": {"message": message, "next_action": "CONFIRM", ...}}
    return  # InteractionAgent 호출 없이 종료 → 1 LLM call 절약
```

### 8-4. 배치 진행 상황 이벤트

```python
yield {
    "event": EventType.TASK_PROGRESS,
    "payload": {"index": 1, "total": 3, "slots": ctx.state.slots.model_dump()},
}
```

---

## 9. SuperOrchestrator (N개 서비스)

```python
# app/main.py — 단일 서비스에서 멀티 서비스로 전환 시
from app.core.orchestration import SuperOrchestrator, KeywordServiceRouter, A2AServiceProxy

orchestrator = SuperOrchestrator(
    services={
        "transfer": CoreOrchestrator(load_transfer_manifest()),
        "balance":  CoreOrchestrator(load_balance_manifest()),  # 한 줄 추가
        "card":     A2AServiceProxy("http://card-svc/v1/agent"),  # 외부 A2A 서비스
    },
    router=KeywordServiceRouter(
        rules={
            "transfer": ["이체", "송금", "보내"],
            "balance":  ["잔액", "얼마", "조회"],
            "card":     ["카드", "신청", "발급"],
        },
        default="transfer",
    ),
)
agent_router = create_agent_router(orchestrator)  # 기존 코드 그대로
```

- `CoreOrchestrator`·`A2AServiceProxy`·`SuperOrchestrator` 모두 동일한 `handle_stream()` 인터페이스
- `create_agent_router`에 어떤 것을 넣어도 동일하게 동작 (교체 투명)
- A2A 패턴: 서비스를 별도 프로세스/서버로 분리하고 SSE로 프록시

---

## 10. 확장 포인트 요약

| 확장 목표 | 수정 위치 |
|----------|-----------|
| 새 Agent 추가 | `agents/<name>/` + `project.yaml` + `manifest._AGENT_CLASS_MAP` |
| 새 Tool 추가 | `core/tools/` 구현 + `TOOL_REGISTRY` 등록 + `card.json tools` 배열 |
| 새 Flow 시나리오 | `IntentAgent.KNOWN_SCENARIOS` + `intent prompt` + `router.SCENARIO_TO_FLOW` + 새 FlowHandler |
| 새 서비스 | `projects/minimal` 복사 + `main.py` 등록 |
| 멀티 서비스 | `main.py` → `SuperOrchestrator` 전환 |
| 외부 서비스 연동 | `A2AServiceProxy` 사용 |
| 세션 영속화 | `InMemorySessionStore` → Redis/DB 기반 구현으로 교체 |
| RAG/검색 | `BaseAgent(retriever=...)` 주입, `retriever.search(query)` → LLM 컨텍스트 추가 |
| 커스텀 요약 프롬프트 | `MemoryManager(summary_system_prompt=..., summary_user_template=...)` |

---

## 11. 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_API_KEY` | — | OpenAI API 키 (필수) |
| `DEV_MODE` | `true` | `GET /debug/{id}` 엔드포인트 활성화 |
| `MEMORY_ENABLE_SUMMARY` | `true` | LLM 자동 요약 활성화 |
| `MEMORY_SUMMARIZE_THRESHOLD` | `8` | 요약 트리거 턴 수 |
| `MEMORY_KEEP_RECENT_TURNS` | `4` | 요약 후 유지할 최근 턴 수 |
| `MEMORY_SUMMARY_MODEL` | `gpt-4o-mini` | 요약 전용 LLM (저렴한 모델 권장) |
| `MAX_FILL_TURNS` | `5` | 슬롯 채우기 최대 시도 횟수 |

---

## 12. 주의사항 / 알려진 패턴

1. **`build_messages()` 는 `user_message` 자동 포함** → messages 리스트에 직접 추가하면 중복
2. **DONE 이벤트는 반드시 마지막** → 클라이언트가 이를 기준으로 턴 종료 판단
3. **`update_memory_and_save()`는 DONE 전에 호출** → 다음 턴부터 히스토리 반영
4. **`summary_text`는 세션 리셋 후에도 유지** → `_reset_session()`에서 raw_history만 초기화
5. **StateManager.apply()는 반드시 state 반환** → in-place 수정해도 OK지만 return 필수
6. **`on_error`는 `lambda e: make_error_event()` 패턴** → 예외 객체를 받지만 기본 구현은 무시
7. **card.json `stream: true`와 `supports_stream`은 별개** → card는 빌더에서 스트리밍 여부 결정용, Agent 클래스는 `supports_stream = True`로 선언
8. **IntentAgent 없이도 동작** → `runner.has_agent("intent") == False`면 기본 `{"scenario": "GENERAL"}` 사용
