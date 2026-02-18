# LLM Orchestrator — Claude 작업 가이드

세션 시작 시 자동으로 읽힌다. 신규 서비스 개발·버그 수정·리팩토링 모두 이 문서를 먼저 참조.
상세 스펙은 `ARCHITECTURE.md`, 파이프라인 다이어그램은 `docs/PIPELINE.md`.

---

## 이 프레임워크가 하는 일

**"LLM 에이전트들을 조합해 대화형 AI 서비스를 만드는 백엔드 엔진"**

- 사용자 메시지 1개 → 에이전트 파이프라인 실행 → SSE 이벤트 스트림 반환
- 각 서비스는 `app/projects/<name>/`에 독립적으로 구현
- `app/core/`는 공통 엔진이며 서비스별 로직을 포함하지 않는다
- 여러 서비스를 SuperOrchestrator로 묶어 하나의 앱으로 확장 가능

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
```

### 구성 요소 역할

| 구성요소 | 역할 | 위치 |
|----------|------|------|
| `CoreOrchestrator` | 요청 수신·세션 관리·에러 핸들링 | `core/orchestration/orchestrator.py` |
| `ExecutionContext` | 에이전트가 읽는 유일한 입력 (state, memory, user_message) | `core/context.py` |
| `BaseAgent` | LLM 호출 단위. `run()` 또는 `run_stream()` 구현 | 각 프로젝트 `agents/` |
| `ConversationalAgent` | JSON 출력·파싱·fallback·스트리밍 기본 구현 | `core/agents/conversational_agent.py` |
| `AgentRunner` | Agent를 이름으로 실행. retry·timeout·스키마 검증 | `core/agents/agent_runner.py` |
| `BaseFlowHandler` | **에이전트 실행 순서·분기 로직의 유일한 위치** | 각 프로젝트 `flows/handlers.py` |
| `BaseFlowRouter` | scenario → flow_key 매핑 | 각 프로젝트 `flows/router.py` |
| `BaseState` | 서비스 상태. Pydantic 모델 | 각 프로젝트 `state/models.py` |
| `StateManager` | state 전이 로직 (코드). LLM delta를 받아 state 업데이트 | 각 프로젝트 `state/models.py` |
| `MemoryManager` | summary_text 자동 요약 + raw_history 관리 | `core/memory/manager.py` |

### 메모리 구조

```python
memory = {
    "summary_text": str,  # LLM 자동 요약. 세션 리셋 후에도 유지된다.
    "raw_history":  list, # 최근 N턴 메시지 [{role, content}, ...]
}
```

Agent에서 메모리를 활용하는 방법 → `context.build_messages(context_block)`:

```python
# system: context_block + summary_text
# + raw_history (최근 N턴)
# + user: user_message   ← 항상 자동으로 마지막에 추가
messages = context.build_messages("현재 상태: ...")
```

### LLM vs 코드 제어 경계

| LLM이 결정 | 코드가 결정 |
|------------|-------------|
| 인텐트 분류 (TRANSFER/GENERAL) | 상태 전이 조건 |
| 슬롯 추출 (자연어 → 구조화) | 슬롯 유효성 검증 (StateManager) |
| 자연어 응답 생성 (FILLING/INIT) | READY 단계 확인/취소 분류 (`logic.py`) |
| 대화 요약 | 명시적 취소 키워드 감지 (`logic.py`) |
| - | confirm 유효성 (READY → CONFIRMED만 허용) |
| - | 터미널 메시지, 세션 리셋 (`messages.py`) |

> **LLM으로 해결하려는 것 중 명확한 분기 조건이 있으면 코드로 먼저 처리한다.**
>
> - READY 단계 confirm/cancel → `logic.is_confirm()` / `logic.is_cancel()` (LLM 호출 없음)
> - 명시적 취소 키워드 → `logic.is_cancel()` 로 SlotFiller 전 차단
> - confirm 안전 제약 → `state_manager._apply_op()`: stage==READY일 때만 CONFIRMED 전환
> - READY + 불명확 입력 → operations:[] → READY 유지 (안전 기본값, LLM 없음)

---

## 절대 규칙

1. **`app/core/`에 프로젝트 로직 금지.** 공통 패턴만.

2. **Agent는 `context.build_messages()`를 사용한다.**
   `user_message`를 수동으로 붙이지 않는다. 이미 자동으로 추가된다.

3. **DONE 이벤트에는 반드시 `state_snapshot`을 포함한다.**

4. **`update_memory_and_save()`는 DONE yield 직전에 호출한다.**

5. **`on_error`는 `lambda e: make_error_event(e)` 패턴.** 예외를 반드시 전달한다. (`core/orchestration/defaults.py`)

6. **세션 리셋 시 `memory`는 건드리지 않는다.** `state`만 초기화.

7. **사용자 노출 문구는 `messages.py`에 분리한다.** handler에 문자열 하드코딩 금지.

---

## 에이전트 계층 구조

```
BaseAgent                    ← LLM 호출 단위 (chat/chat_stream 제공)
├── ConversationalAgent      ← JSON {action, message} + 파싱·검증·fallback·스트리밍
│   └── InteractionAgent     ← transfer 전용: state 컨텍스트 주입
└── ChatAgent                ← minimal 전용: 평문 텍스트, 단순 구조
```

### ConversationalAgent vs ChatAgent 선택 기준

| | `ConversationalAgent` | `ChatAgent` (BaseAgent 직접) |
|---|---|---|
| 출력 형식 | JSON `{action, message}` | 평문 텍스트 |
| 스키마 검증 | 선택적 (`response_schema`) | 없음 |
| fallback | 파싱 실패 시 기본 메시지 반환 | 직접 구현 |
| 스트리밍 | 전체 버퍼 후 char 단위 emit | 토큰 실시간 emit |
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

### `_stream_agent_turn()` 헬퍼 (공통 패턴)

단일 에이전트 호출로 대화 턴을 마무리하는 경우 이 헬퍼를 사용한다.
`AGENT_START → 스트리밍 → AGENT_DONE → 메모리 저장 → DONE` 흐름을 한 줄로 처리.

```python
# 단순 (minimal 등)
yield from self._stream_agent_turn(ctx, "chat", "응답 생성 중")

# UI 정책 적용 (transfer 등) — done_transform으로 프로젝트별 payload 변환
yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                   done_transform=_apply_ui_policy)
```

`done_transform`이 없으면 LLM 원본 payload에 `state_snapshot`만 추가.
**중간 단계에서 직접 메모리·DONE을 처리할 때는 헬퍼 사용하지 않는다** — `update_memory_and_save()`를 직접 호출한다 (READY/TERMINAL/UNSUPPORTED 분기 등).

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
yield {"event": EventType.DONE, "payload": _yield_done(ctx, payload)}
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
Handler      →  DONE payload에 hooks: [{type, data}]
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

## 신규 서비스 추가 — 체크리스트

`app/projects/minimal/`을 복사해서 시작한다.

```
app/projects/<name>/
├── project.yaml       ← 서비스 이름, 버전, 에이전트 목록, router/handler 클래스
├── manifest.py        ← CoreOrchestrator 조립 (minimal/manifest.py 참고)
├── messages.py        ← 사용자 노출 문구 상수 (코드 결정론적)
├── agents/
│   └── <agent>/
│       ├── agent.py   ← BaseAgent 상속. run() 또는 run_stream() 구현
│       ├── prompt.py  ← SYSTEM_PROMPT 상수
│       └── card.json  ← 에이전트 메타데이터
├── state/
│   ├── models.py      ← BaseState + Stage enum + Slots + StateManager
│   └── stores.py      ← InMemorySessionStore(state_factory=<State>) 팩토리
└── flows/
    ├── router.py      ← BaseFlowRouter. route(scenario) → flow_key
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

**원칙: 오류 신호는 state.meta.slot_errors를 통해 전달한다. context.metadata는 agent 간 공유되지 않는다.**

---

## 새 서비스 agent 구현 시 주의사항

### SlotFiller 패턴 (JSON 전용 agent)
- 파싱 실패 시 반드시 `{"operations": [], "_meta": {"parse_error": True}}` 반환
- StateManager.apply()에서 `_meta.parse_error`를 처리해 InteractionAgent가 인지할 수 있도록
- context_block에 **오늘 날짜**를 주입해 날짜 계산이 정확하게 (transfer 참고)

### InteractionAgent 프롬프트 패턴
- `state.meta.slot_errors` 를 최우선으로 확인해 오류 상황 먼저 안내
- 배치/다건 처리 시 `meta.batch_total`, `meta.batch_progress`로 몇 번째인지 안내
- 같은 질문 반복 금지 — 오류 발생 시 원인 설명 후 재질문

### is_confirm / is_cancel (policy 경계)
- READY 단계 확인/취소는 반드시 `logic.py`의 regex로 처리 (LLM 없음)
- 누락된 패턴 발견 시 `logic.py`에만 추가 (handler 코드 수정 불필요)

---

## 버전 이력

| 버전 | 내용 |
|------|------|
| v1.3.0 | 오류 인지 전파 (parse_error→slot_errors), InteractionAgent 프롬프트 강화, SlotFiller 날짜 주입, is_confirm 패턴 보강, hooks 인프라 구현 |
| v1.2.0 | `ConversationalAgent` 추출, `_stream_agent_turn()` 헬퍼, mid-flow Intent 스킵, retry UX (`on_retry` 콜백) |
| v1.1.0 | `build_messages()` 표준화, core 공통화, minimal 템플릿, 문서 정비 |
| v1.0.0 | 초기 구조: CoreOrchestrator, Agent/Runner/Handler, 배치 큐, 자동 요약 |
