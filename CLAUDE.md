# LLM Orchestrator — Claude 작업 가이드

세션 시작 시 자동으로 읽힌다. 신규 서비스 개발·버그 수정·리팩토링 모두 이 문서를 먼저 참조.

> **상세 구현 가이드**: [GUIDE.md](GUIDE.md) — 파일별 작성법, 코드 패턴, API 스펙, 디버깅 종합 문서.

---

## 이 프레임워크가 하는 일

**"LLM 에이전트들을 조합해 대화형 AI 서비스를 만드는 백엔드 엔진"**

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI (main.py)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─── app/core/ ─────────────────────────────────────────────┐  │
│  │  CoreOrchestrator    AgentRunner     MemoryManager        │  │
│  │  SessionStore        BaseFlowHandler TurnTracer           │  │
│  │  BaseAgent           StateManager    EventType            │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │  LLM Providers: OpenAI · Anthropic  (BaseLLMClient)      │  │
│  └───────────────────────────────────────────────────────────┘  │
│       ▲ 상속·사용                                               │
│  ┌─── app/projects/ ────────────────────────────────────────┐   │
│  │  transfer/    ← AI 이체 (레퍼런스)                        │   │
│  │  minimal/     ← 신규 서비스 템플릿                        │   │
│  │  <new>/       ← 여기에 새 서비스 추가                     │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

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
  사용자 메시지
       │
       ▼
┌──────────────── CoreOrchestrator ────────────────┐
│                                                   │
│  1. SessionStore ──→ state, memory 로드           │
│       │                                           │
│  2. is_mid_flow? ──YES──→ IntentAgent 스킵        │
│       │ NO                                        │
│       ▼                                           │
│  3. IntentAgent ──→ scenario 분류                 │
│       │                                           │
│  4. FlowRouter ──→ scenario → flow_key            │
│       │                                           │
│  5. FlowHandler.run(ctx) ──→ SSE 이벤트 yield     │
│       │                                           │
│  6. (finally) SessionStore.save()                 │
│              + hook_handlers 실행                  │
│              + after_turn 콜백                     │
└───────────────────┬───────────────────────────────┘
                    │
                    ▼
    SSE: AGENT_START → LLM_TOKEN* → LLM_DONE
         → AGENT_DONE → DONE (state_snapshot 포함)
```

### 컴포넌트 역할 경계

```
┌─────────────────────────────────────────────────────────┐
│                     FlowHandler                         │
│          (에이전트 실행 순서 · 분기의 유일한 위치)          │
│                                                         │
│    ┌──────────┐    delta    ┌──────────────┐            │
│    │  Agent   │───────────→│ StateManager │            │
│    │ (읽기만) │            │ (state 변경) │            │
│    └────┬─────┘            └──────┬───────┘            │
│         │                         │                     │
│     reads only              mutates state               │
│         │                         │                     │
│         ▼                         ▼                     │
│  ┌─────────────────────────────────────┐                │
│  │         ExecutionContext             │                │
│  │  state · memory · user_message      │                │
│  └─────────────────────────────────────┘                │
│                                                         │
│    _update_memory() → DONE yield → _build_done_payload  │
└─────────────────────────────────────────────────────────┘
```

### 에이전트 계층

```
BaseAgent                     ← LLM 호출 (chat / chat_stream + tool-call 루프)
├── ConversationalAgent       ← JSON {action, message} + 파싱·검증·fallback
│   ├── InteractionAgent      ← 자연어 응답. slot_errors 인지
│   └── SlotFillerAgent       ← JSON delta 추출. parse_error 신호
└── ChatAgent                 ← 평문 텍스트. 토큰 즉시 스트리밍
```

### 핵심 원칙

- **Agent는 `context.build_messages()`로 메시지를 구성한다.** `user_message`는 자동으로 마지막에 추가됨.
- **Agent는 context를 읽기만 한다.** 상태 변경은 FlowHandler에서 `StateManager.apply(delta)`로.
- **FlowHandler가 에이전트 실행 순서·분기 로직의 유일한 위치다.**
- **오류 신호는 `state.meta.slot_errors`를 통해 전달한다.** `context.metadata`는 agent 간 공유되지 않는다.
- **LLM으로 해결하려는 것 중 명확한 분기 조건이 있으면 코드로 먼저 처리한다.**
- **사용자 노출 문구는 `messages.py`에 분리한다.** handler에 문자열 하드코딩 금지.

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

## 신규 서비스 추가

`app/projects/minimal/`을 복사해서 시작한다. 상세 가이드: [GUIDE.md 섹션 3](GUIDE.md#3-새-서비스-만들기--3가지-경로).

```
app/projects/<name>/
├── project.yaml       ← 서비스 이름·버전·에이전트 목록·router/handler 클래스·state.model
├── manifest.py        ← ManifestBuilder로 CoreOrchestrator 조립
├── messages.py        ← 사용자 노출 문구 상수
├── agents/
│   └── <agent>/
│       ├── agent.py   ← BaseAgent 상속. run() 또는 run_stream() 구현
│       ├── prompt.py  ← get_system_prompt() 함수
│       └── card.json  ← LLM provider·model·temperature·policy·tools 설정
├── knowledge/         ← (선택) RAG·외부 지식 저장소
├── state/
│   ├── models.py      ← BaseState + Stage enum + Slots + SLOT_SCHEMA
│   ├── state_manager.py ← BaseStateManager 상속. apply(delta) 구현
│   └── stores.py      ← InMemorySessionStore 팩토리
└── flows/
    ├── router.py      ← BaseFlowRouter. route(intent_result, state) → flow_key
    └── handlers.py    ← BaseFlowHandler. run(ctx) → Generator[events]
```

### 구현 순서
1. `project.yaml` — 이름·버전·에이전트 목록
2. `state/models.py` — Stage, State, StateManager
3. `state/stores.py` — SessionStore 팩토리
4. `agents/` — 에이전트 구현 (`context.build_messages()` 사용)
5. `flows/router.py` — scenario → flow_key
6. `flows/handlers.py` — 실행 순서·분기
7. `messages.py` — 사용자 메시지 상수
8. `manifest.py` — 조립
9. `app/main.py` — 라우터 등록 + 이 문서 서비스 테이블 업데이트

---

## 흔한 실수

| # | 실수 | 올바른 방법 |
|---|------|------------|
| 1 | `build_messages()` 후 `user_message`를 또 추가 | `build_messages()`가 자동으로 마지막에 추가. 수동 추가하면 중복 |
| 2 | `on_error`에서 `make_error_event()` (인자 없음) | `make_error_event(e)` — 예외 `e`를 전달해야 에러 분류 동작 |
| 3 | state 리셋 시 memory 초기화 | `self._reset_state(ctx, NewState())` 사용. memory는 보존 |
| 4 | DONE 이벤트에 `state_snapshot` 누락 | `self._build_done_payload(ctx, payload)` 헬퍼 사용 |
| 5 | confirm 연산을 INIT/FILLING에서 허용 | `state_manager._apply_op()`: READY 단계에서만 CONFIRMED 전환 (코드 강제) |
| 6 | 배치 처리 중 다건 재감지 | `if delta.get("tasks") and stage in (INIT, FILLING)` 조건 필수 |
| 7 | `"LLM_DONE"` 문자열 리터럴 사용 | `EventType.LLM_DONE` enum 사용 |
| 8 | Agent에서 state 직접 수정 | Agent는 context를 읽기만. 상태 변경은 Handler에서 StateManager.apply()로 |
| 9 | handler에 사용자 메시지 하드코딩 | `messages.py`에 상수로 분리 |
| 10 | IntentAgent가 FILLING/READY 단계에서도 실행 | `is_mid_flow` 조건으로 스킵. 오탐 방지 |
