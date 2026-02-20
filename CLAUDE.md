# LLM Orchestrator — Claude 작업 가이드

세션 시작 시 자동으로 읽힌다. 신규 서비스 개발·버그 수정·리팩토링 모두 이 문서를 먼저 참조.

> **상세 가이드**: [GUIDE.md](GUIDE.md) — 아키텍처, 새 서비스 만들기, 코드 패턴, API 스펙, 디버깅 종합 문서.

---

## 이 프레임워크가 하는 일

**"LLM 에이전트들을 조합해 대화형 AI 서비스를 만드는 백엔드 엔진"**

- 사용자 메시지 1개 → 에이전트 파이프라인 실행 → SSE 이벤트 스트림 반환
- 각 서비스는 `app/projects/<name>/`에 독립적으로 구현
- `app/core/`는 공통 엔진이며 서비스별 로직을 포함하지 않는다
- 여러 서비스를 `SuperOrchestrator`로 묶어 하나의 앱으로 확장 가능

---

## 등록된 서비스

| 서비스 | 경로 | 상태 | 설명 |
|--------|------|------|------|
| `transfer` | `app/projects/transfer/` | ✅ 운영 | AI 이체 서비스 (레퍼런스 구현) |
| `minimal` | `app/projects/minimal/` | ✅ 템플릿 | 신규 서비스 시작점 |

> **새 서비스 추가 시 이 테이블을 업데이트한다.**

---

## 핵심 개념

### 요청 한 번의 흐름

```
POST /v1/agent/chat/stream
    │
    ├─ SessionStore  → state, memory 로드
    ├─ IntentAgent   → scenario 분류 (is_mid_flow이면 스킵)
    ├─ FlowRouter    → flow_key 결정
    └─ FlowHandler   → 에이전트들 실행 → SSE 이벤트 yield
         └─ (finally) 세션 저장 + hook_handlers 실행 + after_turn
```

### 구성 요소 역할

| 구성요소 | 역할 | 위치 |
|----------|------|------|
| `CoreOrchestrator` | 요청 수신·세션 관리·에러 핸들링·훅 실행 | `core/orchestration/orchestrator.py` |
| `ExecutionContext` | 에이전트가 읽는 유일한 입력 (state, memory, user_message) | `core/context.py` |
| `BaseAgent` | LLM 호출 단위. `run()` 또는 `run_stream()` 구현 | 각 프로젝트 `agents/` |
| `ConversationalAgent` | JSON 출력·파싱·fallback·스트리밍 기본 구현 | `core/agents/conversational_agent.py` |
| `AgentRunner` | Agent를 이름으로 실행. retry·timeout·스키마 검증 | `core/agents/agent_runner.py` |
| `BaseFlowHandler` | **에이전트 실행 순서·분기 로직의 유일한 위치** | 각 프로젝트 `flows/handlers.py` |
| `BaseFlowRouter` | scenario → flow_key 매핑 | 각 프로젝트 `flows/router.py` |
| `BaseState` | 서비스 상태. Pydantic 모델 | 각 프로젝트 `state/models.py` |
| `StateManager` | state 전이 로직 (코드). LLM delta를 받아 state 업데이트 | 각 프로젝트 `state/state_manager.py` |
| `MemoryManager` | summary_text 자동 요약 + raw_history 관리 | `core/memory/memory_manager.py` |
| `TurnTracer` | 턴 단위 에이전트 실행 추적. AgentRunner가 자동 기록 | `core/tracing.py` |
| `AgentResult` | 에이전트 표준 응답 (success/need_info/cannot_handle/partial) | `core/agents/agent_result.py` |
| `ManifestBuilder` | manifest.py 보일러플레이트를 빌더 패턴으로 간소화 | `core/orchestration/manifest_loader.py` |
| `BaseLLMClient` | LLM 프로바이더 인터페이스. OpenAI/Anthropic 교체 가능 | `core/llm/base_client.py` |
| `SuperOrchestrator` | 여러 CoreOrchestrator / A2AServiceProxy를 하나로 묶음 | `core/orchestration/super_orchestrator.py` |

### 메모리 구조

```python
memory = {
    "summary_text": str,  # LLM 자동 요약. 세션 리셋 후에도 유지된다.
    "raw_history":  list, # 최근 N턴 메시지 [{role, content}, ...]
}
```

Agent에서 메모리를 활용하는 방법 → `context.build_messages(context_block)`:

```python
# [system] context_block + summary_text
# [user/asst] raw_history 최근 N턴
# [user] user_message   ← 자동으로 마지막에 추가됨
messages = context.build_messages("현재 상태: ...")
```

메모리 설정 (config.py):

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `MEMORY_SUMMARIZE_THRESHOLD` | 6 | 요약 트리거 턴 수 |
| `MEMORY_KEEP_RECENT_TURNS` | 3 | 요약 후 유지할 최근 턴 수 |
| `MEMORY_SUMMARY_MODEL` | `gpt-4o-mini` | 요약 LLM 모델 |

서버 설정 (`.env` → `config.py`):

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `BACKEND_HOST` | `0.0.0.0` | 백엔드 바인드 호스트 |
| `BACKEND_PORT` | `8010` | 백엔드 포트 |
| `FRONTEND_PORT` | `8501` | 프론트엔드 포트 |

> 모든 서버 설정은 `.env` 파일에서 일괄 관리. `.env.example`을 참고해 생성.
> 스크립트(`scripts/*.sh`, `run.sh`), 프론트엔드(`app.py`, `api_client.py`) 모두 `.env`를 읽는다.

### SSE 이벤트 흐름

```
AGENT_START  → agent 시작 알림 (label: "의도 파악 중")
LLM_TOKEN    → LLM 글자 단위 스트리밍
LLM_DONE     → LLM 전체 응답 완료 (parsed dict)
AGENT_DONE   → agent 완료 알림 (success, retry_count, elapsed_ms)
TASK_PROGRESS → 배치 이체 진행 상황 (index/total)
DONE         → 턴 완료. payload에 message, state_snapshot, hooks, _trace 포함
               + slots_card (READY 확인 카드), receipt (EXECUTED/FAILED 영수증)
```

### LLM vs 코드 제어 경계

| LLM이 결정 | 코드가 결정 |
|------------|-------------|
| 인텐트 분류 (TRANSFER/GENERAL) | 상태 전이 조건 |
| 슬롯 추출 (자연어 → 구조화) | 슬롯 유효성 검증 (StateManager) |
| 자연어 응답 생성 (FILLING/INIT) | READY 단계 확인/취소 분류 (`logic.py`) |
| READY off-topic 폴백 (InteractionAgent) | 명시적 취소 키워드 감지 (`logic.py`) |
| 대화 요약 | confirm 유효성 (READY → CONFIRMED만 허용) |
| - | 터미널 메시지, 세션 리셋 (`messages.py`) |
| - | READY 확인 메시지 + 슬롯 카드 (`messages.py`) |

> **LLM으로 해결하려는 것 중 명확한 분기 조건이 있으면 코드로 먼저 처리한다.**
>
> - READY 단계 confirm/cancel → `logic.is_confirm()` / `logic.is_cancel()` (LLM 호출 없음)
> - READY 단계 그 외 입력 → SlotFiller LLM 호출 (메모·날짜·금액 변경 지원)
> - READY + SlotFiller 빈 결과 → InteractionAgent 폴백 (off-topic 자연어 응대)
> - 명시적 취소 키워드 → `logic.is_cancel()` 로 SlotFiller 전 차단
> - confirm 안전 제약 → `state_manager._apply_op()`: stage==READY일 때만 CONFIRMED 전환

---

## 절대 규칙

1. **`app/core/`에 프로젝트 로직 금지.** 공통 패턴만.

2. **Agent는 `context.build_messages()`를 사용한다.**
   `user_message`를 수동으로 붙이지 않는다. 이미 자동으로 추가된다.

3. **DONE 이벤트에는 반드시 `state_snapshot`을 포함한다.** `self._build_done_payload(ctx, payload)` 헬퍼 사용 권장.

4. **`_update_memory(ctx, message)`는 DONE yield 직전에 호출한다.** (`BaseFlowHandler` 메서드)

5. **`on_error`는 `lambda e: make_error_event(e)` 패턴.** 예외를 반드시 전달한다. (`core/orchestration/defaults.py`)

6. **세션 리셋 시 `memory`는 건드리지 않는다.** `self._reset_state(ctx, NewState())` 사용.

7. **사용자 노출 문구는 `messages.py`에 분리한다.** handler에 문자열 하드코딩 금지.

8. **`EventType` enum을 사용한다.** `"LLM_DONE"` 같은 문자열 리터럴 사용 금지.

---

## 에이전트 계층 구조

```
BaseAgent                    ← LLM 호출 단위 (chat / chat_stream + tool-call 루프)
├── ConversationalAgent      ← JSON {action, message} + 파싱·검증·fallback·스트리밍
│   ├── InteractionAgent     ← transfer: state 컨텍스트 주입, slot_errors 인지
│   └── SlotFillerAgent      ← transfer: JSON delta 추출, 날짜 주입, parse_error 신호
└── ChatAgent                ← minimal: 평문 텍스트, 토큰 즉시 스트리밍
```

### ConversationalAgent vs ChatAgent 선택 기준

| | `ConversationalAgent` | `ChatAgent` (BaseAgent 직접) |
|---|---|---|
| 출력 형식 | JSON `{action, message}` | 평문 텍스트 |
| 스키마 검증 | 선택적 (`response_schema`) | 없음 |
| fallback | 파싱 실패 시 기본 메시지 반환 | 직접 구현 |
| 스트리밍 | 전체 버퍼 수집 후 char 단위 emit | 토큰 실시간 emit |
| 첫 글자 응답 속도 | 느림 (버퍼 완성 후) | 빠름 (즉시) |
| 적합한 경우 | 상태 기반 흐름·UI action 필요 | 빠른 프로토타이핑·스키마 불필요 |

### ConversationalAgent 상속 방법

```python
class MyAgent(ConversationalAgent):
    response_schema = MyOutputSchema  # Pydantic 모델 (선택)
    fallback_message = "오류가 발생했어요."

    def run(self, context, **kwargs) -> dict:
        block = f"현재 state: {context.state.stage}"
        return super().run(context, context_block=block)

    def run_stream(self, context, **kwargs):
        block = f"현재 state: {context.state.stage}"
        yield from super().run_stream(context, context_block=block)
```

---

## FlowHandler 패턴

### BaseFlowHandler 공통 메서드

| 메서드 | 용도 |
|--------|------|
| `_stream_agent_turn(ctx, agent, label, done_transform=)` | 단일 에이전트로 턴 마무리 (AGENT_START→스트리밍→DONE) |
| `_build_done_payload(ctx, payload)` | 수동 DONE 빌드 시 `state_snapshot` 자동 추가 |
| `_reset_state(ctx, new_state)` | 터미널 후 state 초기화. memory 보존 |
| `_update_memory(ctx, message)` | DONE yield 직전 메모리 갱신 |

```python
# 단순 (minimal 등)
yield from self._stream_agent_turn(ctx, "chat", "응답 생성 중")

# UI 정책 적용 (transfer 등) — done_transform으로 프로젝트별 payload 변환
yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                   done_transform=_apply_ui_policy)

# 수동 DONE 빌드 (READY/TERMINAL 등 LLM 없이 코드로 응답 생성)
payload = {"message": msg, "action": "DONE"}
yield {"event": EventType.DONE, "payload": self._build_done_payload(ctx, payload)}

# 터미널 후 state 리셋
self._reset_state(ctx, TransferState())
```

**중간 단계에서 직접 메모리·DONE을 처리할 때는 `_stream_agent_turn()` 사용하지 않는다** — `self._update_memory(ctx, message)`를 직접 호출한다 (READY/TERMINAL/UNSUPPORTED 분기 등).

---

## IntentAgent 스킵 — mid-flow 감지

`FILLING`·`READY`·`CONFIRMED` 단계에서는 IntentAgent를 호출하지 않는다.

**이유**: LLM이 이전 봇 응답(예: "다음으로 엄마에게 1000원 보내시겠어요?")을 컨텍스트로 받아
시나리오 대신 대화 내용을 그대로 반환하는 오탐이 발생한다.
특히 배치 이체에서 첫 번째 실행 후 두 번째 확인 단계에서 재현된다.

```python
is_mid_flow = (
    current_scenario
    and current_scenario != "DEFAULT"
    and state.stage not in ("INIT", "EXECUTED", "FAILED", "CANCELLED", "UNSUPPORTED")
)
# is_mid_flow=True → IntentAgent 스킵, current_scenario 그대로 유지
```

Intent 실패 시에도 GENERAL로 폴백하지 않고 `current_scenario`를 유지한다.

---

## AgentRunner retry UX

AgentRunner가 retry할 때 프론트에 알리는 패턴:

```python
retry_events: list = []
def _on_intent_retry(agent_name, attempt, max_retry, err):
    retry_events.append({"event": EventType.AGENT_START, "payload": {
        "agent": agent_name,
        "label": f"의도 재파악 중... ({attempt + 1}/{max_retry})",
    }})

intent_result = self._runner.run("intent", ctx, on_retry=_on_intent_retry)
for ev in retry_events:
    yield ev  # retry 이벤트를 run() 완료 후 순서대로 yield
```

`on_retry` 콜백은 AgentRunner.run()이 동기 블로킹이므로 retry 중에는 쌓아뒀다가 완료 후 emit.

---

## Hooks — 프론트 전달 + 서버 사이드 실행

DONE 이벤트 payload에 `hooks` 리스트를 추가하면:
1. **프론트**가 SSE(DONE 이벤트) 또는 REST(`"hooks"` 필드)로 수신
2. **서버**에서 manifest `hook_handlers`에 등록된 함수가 자동 실행

### Handler에서 hooks 추가

```python
# 예: 이체 완료 후 훅 발행
payload = {
    "message": message,
    "action": "DONE",
    "hooks": [
        {"type": "transfer_completed", "data": ctx.state.slots.model_dump()},
    ],
}
yield {"event": EventType.DONE, "payload": self._yield_done(ctx, payload)}
```

### manifest에 서버 사이드 핸들러 등록

```python
# manifest.py
"hook_handlers": {
    "transfer_completed": lambda ctx, data: send_push_notification(data),
    "session_reset":      lambda ctx, data: log_analytics(ctx.session_id),
},
```

### 전체 흐름

```
FlowHandler  →  DONE payload에 hooks: [{type, data}]
Orchestrator →  프론트로 DONE 이벤트 yield (hooks 포함)
             →  hook_handlers[type](ctx, data) 서버 사이드 실행
프론트       →  DONE.hooks 수신 → 필요한 UI 동작 수행
```

| | 설명 |
|---|---|
| `hook_handlers` | manifest에 등록. `{type: fn(ctx, data)}`. 실패 시 warning 로그만 (턴 결과 영향 없음) |
| `after_turn` | 모든 턴 후 실행되는 generic 콜백 `fn(ctx, final_payload)`. 훅 타입 구분 없음 |
| `hooks` (payload) | Handler가 직접 추가. `_stream_agent_turn()` 헬퍼 사용 시 `done_transform`으로 추가 가능 |

> **hooks는 모든 서비스(minimal 포함)에서 공통으로 사용 가능.** manifest `hook_handlers`를 채우고 handler에서 payload에 추가하면 된다.

---

## TurnTracer — 에이전트 실행 추적

Orchestrator가 턴 시작 시 `TurnTracer`를 생성해 `ExecutionContext.tracer`에 주입한다.
AgentRunner가 매 에이전트 실행마다 자동으로 `tracer.record()`를 호출한다.

DONE payload의 `_trace` 필드에 턴 전체 실행 히스토리가 포함된다:

```json
{
  "_trace": {
    "turn_id": "a1b2c3d4",
    "total_elapsed_ms": 1234.5,
    "agents": [
      {"agent": "intent", "elapsed_ms": 200.1, "success": true, "retries": 0, "error": null},
      {"agent": "slot",   "elapsed_ms": 150.3, "success": true, "retries": 0, "error": null}
    ]
  }
}
```

`tracer=None`이면 기록을 건너뛴다 (하위 호환).

---

## AgentResult — 에이전트 표준 응답

에이전트가 성공/실패/정보부족을 표현하는 표준 방법. 기존 dict 반환과 100% 호환.

```python
from app.core.agents.agent_result import AgentResult

# 성공
return AgentResult.success({"action": "ASK", "message": "안녕하세요"})

# 파라미터 부족
return AgentResult.need_info(["amount"], "이체 금액을 알려주세요.")

# 처리 불가
return AgentResult.cannot_handle("해외 이체는 지원하지 않습니다.")

# 부분 성공 (파싱 에러 등)
return AgentResult.partial({"operations": []}, reason="parse_error")
```

AgentRunner가 `isinstance(result, AgentResult)`를 확인해 자동으로 `to_dict()` 변환한다.
FlowHandler는 항상 dict을 받으며 `_result_status` 필드로 상태를 인지할 수 있다.

---

## ManifestBuilder — manifest 간소화

`ManifestBuilder`로 manifest.py 보일러플레이트를 빌더 패턴으로 줄인다.

```python
from app.core.orchestration.manifest_loader import ManifestBuilder

# 최소 사용 (minimal 등)
def load_manifest():
    return (
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
        .class_name_map({"ChatAgent": "agents.chat_agent.agent.ChatAgent"})
        .build()
    )

# 복잡 사용 (transfer 등)
def load_manifest():
    return (
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
        .class_name_map(_MAP)
        .schema_registry(_SCHEMAS)
        .validator_map(_VALIDATORS)
        .sessions_factory(SessionStore)
        .memory(summary_system_prompt="...", summary_user_template="...")
        .build()
    )
```

`sessions_factory`가 미지정이면 `project.yaml`의 `state.model` 필드로 State 클래스를 찾아 `InMemorySessionStore`를 자동 구성한다.

기존 유틸 함수(`load_yaml`, `resolve_class`, `build_agents_from_yaml`)도 계속 사용 가능.

---

## LLM 프로바이더 추상화

card.json의 `provider` 필드로 LLM 프로바이더를 교체할 수 있다 (기본값 `"openai"`).

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "temperature": 0
  }
}
```

### 아키텍처

```
card.json → provider + model 지정
BaseAgent → BaseLLMClient 인터페이스만 사용
각 프로바이더 → 메시지 포맷·tool 포맷·응답 파싱 내부 처리
```

| 파일 | 역할 |
|------|------|
| `core/llm/base_client.py` | `BaseLLMClient` 인터페이스, `LLMResponse`, `ToolCall` |
| `core/llm/openai_client.py` | OpenAI 구현 |
| `core/llm/anthropic_client.py` | Anthropic 구현 |
| `core/llm/__init__.py` | `create_llm_client(provider)` 팩토리 |

### 핵심 설계

- **system_prompt 분리**: `chat(system_prompt=..., messages=...)`로 전달. 프로바이더가 내부 처리.
  - OpenAI: messages 앞에 `{"role": "system", ...}` prepend
  - Anthropic: `system` 파라미터로 전달
- **tool 스키마 중립 포맷**: `{"name": ..., "description": ..., "parameters": {...}}`
  - OpenAI: `{"type": "function", "function": schema}` 래핑
  - Anthropic: `{"name": ..., "input_schema": schema["parameters"]}` 변환
- **tool-call 루프**: `LLMResponse.tool_calls` → `build_assistant_message()` → `build_tool_result_message()` 로 프로바이더 독립적 처리

### 새 프로바이더 추가 방법

1. `core/llm/<provider>_client.py` — `BaseLLMClient` 구현
2. `core/llm/__init__.py` — `create_llm_client()`에 분기 추가
3. `core/config.py` — API 키 설정 추가

---

## 오류 인지 — Agent 간 에러 전파 패턴

SlotFiller 같은 upstream agent가 실패할 때 downstream InteractionAgent가 이를 인지하는 구조:

```
SlotFillerAgent
  └─ JSON 파싱 실패 → {"operations": [], "_meta": {"parse_error": True}}
       ↓
TransferStateManager.apply()
  └─ parse_error 감지 → state.meta.slot_errors["_unclear"] = "이해하지 못했어요."
       ↓
InteractionAgent
  └─ state.meta.slot_errors._unclear 인지 → "말씀하신 내용을 이해하지 못했어요. 다시 알려주세요."

StateManager 검증 실패 (amount=0 등)
  └─ state.meta.slot_errors["amount"] = SLOT_SCHEMA error_msg
       ↓
InteractionAgent
  └─ slot_errors.amount 인지 → "이체 금액은 1원 이상이어야 해요. 다시 알려주세요."
```

**원칙: 오류 신호는 `state.meta.slot_errors`를 통해 전달한다. `context.metadata`는 agent 간 공유되지 않는다.**

---

## 신규 서비스 추가 — 체크리스트

`app/projects/minimal/`을 복사해서 시작한다.

```
app/projects/<name>/
├── project.yaml       ← 서비스 이름·버전·에이전트 목록·router/handler 클래스·state.model
├── manifest.py        ← ManifestBuilder로 CoreOrchestrator 조립 (minimal/manifest.py 참고)
├── messages.py        ← 사용자 노출 문구 상수 (코드 결정론적)
├── agents/
│   └── <agent>/
│       ├── agent.py   ← BaseAgent 상속. run() 또는 run_stream() 구현
│       ├── prompt.py  ← get_system_prompt() 함수
│       └── card.json  ← LLM provider·model·temperature·policy(timeout_sec)·tools 설정
├── knowledge/             ← (선택) RAG·외부 지식 저장소. retriever.search() 구현
├── state/
│   ├── models.py      ← BaseState + Stage enum + Slots + SLOT_SCHEMA
│   ├── state_manager.py ← BaseStateManager 상속. apply(delta) 구현
│   └── stores.py      ← InMemorySessionStore(state_factory=<State>) 팩토리
└── flows/
    ├── router.py      ← BaseFlowRouter. route(intent_result, state) → flow_key
    └── handlers.py    ← BaseFlowHandler. run(ctx) → Generator[events]
```

### 구현 순서
1. `project.yaml` — 이름·버전·에이전트 목록
2. `state/models.py` — Stage, State, StateManager (서비스 복잡도에 따라)
3. `state/stores.py` — SessionStore 팩토리
4. `agents/` — 에이전트 구현 (`context.build_messages()` 사용)
5. `flows/router.py` — scenario → flow_key
6. `flows/handlers.py` — 실행 순서·분기
7. `messages.py` — 사용자 메시지 상수
8. `manifest.py` — 조립
9. `app/main.py` — 라우터 등록 + 이 문서 서비스 테이블 업데이트

### 복잡도별 가이드

| 서비스 유형 | 에이전트 구성 | 상태 기계 | 참고 |
|-------------|---------------|-----------|------|
| 단순 대화 | ChatAgent 1개 | Stage 없음 | `minimal` 그대로 |
| 인텐트 분기 | IntentAgent + N개 핸들러 | scenario만 | router 확장 |
| 슬롯 수집 + 실행 | SlotAgent + InteractionAgent + ExecuteAgent | FILLING→READY→DONE | `transfer` 참고 |
| 다건 처리 | 위 + task_queue 패턴 | 위 + BATCH meta | `transfer` 참고 |

### 멀티 서비스 확장 (SuperOrchestrator)

`app/main.py`에서 CoreOrchestrator를 SuperOrchestrator로 교체하면 된다. 기존 API 라우터 코드 변경 없음.

```python
from app.core.orchestration import SuperOrchestrator, KeywordServiceRouter, A2AServiceProxy

orchestrator = SuperOrchestrator(
    services={
        "transfer": CoreOrchestrator(transfer_manifest),
        "balance":  CoreOrchestrator(balance_manifest),         # 새 서비스: 한 줄
        "card":     A2AServiceProxy("http://card-svc/v1/agent"), # A2A 원격: 한 줄
    },
    router=KeywordServiceRouter(
        rules={
            "transfer": ["이체", "송금", "보내"],
            "balance":  ["잔액", "얼마", "조회"],
        },
        default="transfer",
    ),
)
```

---

## 새 서비스 agent 구현 시 주의사항

### SlotFiller 패턴 (JSON 전용 agent)
- 파싱 실패 시 반드시 `{"operations": [], "_meta": {"parse_error": True}}` 반환
- StateManager.apply()에서 `_meta.parse_error`를 처리해 InteractionAgent가 인지할 수 있도록
- context_block에 **오늘 날짜**를 주입해 날짜 계산이 정확하게 (transfer 참고)

### InteractionAgent 프롬프트 패턴
- `state.meta.slot_errors`를 최우선으로 확인해 오류 상황 먼저 안내
- 배치/다건 처리 시 `meta.batch_total`, `meta.batch_progress`로 몇 번째인지 안내
- 같은 질문 반복 금지 — 오류 발생 시 원인 설명 후 재질문

### is_confirm / is_cancel (policy 경계)
- READY 단계 확인/취소는 반드시 `logic.py`의 regex로 처리 (LLM 없음)
- 누락된 패턴 발견 시 `logic.py`에만 추가 (handler 코드 수정 불필요)

### Tool 추가
- `BaseTool` 상속 → `schema()` + `run()` 구현
- `core/tools/registry.py` `TOOL_REGISTRY`에 한 줄 추가
- Agent `card.json` `"tools": ["tool_name"]` 등록

---

## 버전 이력

| 버전 | 내용 |
|------|------|
| v1.8.0 | 코어 패턴 추출 (`_build_done_payload`, `_reset_state`), handlers.py 정리 (`_yield_done` 메서드화, 모듈 함수 제거), InteractionAgent context_block 구조화, card.json timeout_sec 일관성, minimal provider 명시 |
| v1.7.0 | READY 슬롯 편집 (메모·날짜·금액 변경), off-topic 폴백 (READY/FILLING), 재이체 기능 (메모리 기반), 슬롯 카드 UI + 영수증, `.env` 서버 설정 통합, 프론트엔드 슬롯 편집 + 금액 자동 포맷 |
| v1.6.0 | LLM 프로바이더 추상화 (BaseLLMClient + OpenAI/Anthropic), 데드코드 제거 (hooks.py, flow_utils.py, output_schema, stream 파라미터), `_update_memory()` 메서드로 통합, tool 스키마 중립 포맷 |
| v1.5.0 | TurnTracer (에이전트 실행 추적), AgentResult (표준 응답), ManifestBuilder (manifest 간소화) |
| v1.4.0 | 전체 core·project 파일 종합 주석 정비. `agent_runner.py` `"LLM_DONE"` 문자열 리터럴 → `EventType.LLM_DONE` 버그 수정 |
| v1.3.0 | 오류 인지 전파 (parse_error→slot_errors), InteractionAgent 프롬프트 강화, SlotFiller 날짜 주입, is_confirm 패턴 보강, hooks 인프라 구현, 프론트엔드 메모리 탭 (요약+히스토리) |
| v1.2.0 | `ConversationalAgent` 추출, `_stream_agent_turn()` 헬퍼, mid-flow Intent 스킵, retry UX (`on_retry` 콜백) |
| v1.1.0 | `build_messages()` 표준화, core 공통화, minimal 템플릿, 문서 정비 |
| v1.0.0 | 초기 구조: CoreOrchestrator, Agent/Runner/Handler, 배치 큐, 자동 요약 |
