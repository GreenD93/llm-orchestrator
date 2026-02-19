# LLM Orchestrator

**멀티턴 슬롯필링·시나리오 기반 AI 오케스트레이션 템플릿**

FastAPI + SSE 스트리밍 백엔드, Streamlit 프론트엔드.
`app/core/`는 도메인 무관 공통 엔진이고, 새 AI 서비스는 `app/projects/<name>/`에 독립적으로 구현한다.

---

## 특징

| | |
|---|---|
| **서비스 독립성** | 프로젝트별로 Agent + Flow만 정의하면 동작 |
| **SSE 스트리밍** | LLM 토큰을 실시간으로 프론트에 전달 |
| **멀티턴 메모리** | raw_history + LLM 자동 요약(summary_text) |
| **상태 머신** | INIT → FILLING → READY → CONFIRMED → EXECUTED 단계별 제어 |
| **배치 처리** | "홍길동에게 5만원, 엄마에게 3만원 이체해줘" 한 번에 처리 |
| **Hooks** | 이체 완료 등 이벤트를 프론트·서버 양쪽에 전달 |
| **멀티 서비스** | SuperOrchestrator로 여러 서비스를 하나의 API로 통합 |
| **A2A 지원** | 별도 프로세스 서비스를 HTTP로 연결 (A2AServiceProxy) |

---

## 프로젝트 구조

```
app/
├── main.py                         # FastAPI 앱 진입점 (단일→멀티 서비스 확장 예시 포함)
├── core/                           # 공통 엔진 — 도메인 로직 없음
│   ├── config.py                   # 환경 변수 설정 (OPENAI_API_KEY, 메모리 임계값 등)
│   ├── context.py                  # ExecutionContext: state·memory·metadata 통합 컨테이너
│   ├── events.py                   # EventType enum (DONE, LLM_TOKEN, LLM_DONE, AGENT_START …)
│   ├── hooks.py                    # 훅 타입 정의 (HookAfterTurn, HookOnError …)
│   ├── agents/
│   │   ├── base_agent.py           # LLM 호출 + tool-call 루프 기반 클래스
│   │   ├── conversational_agent.py # JSON 파싱·검증·fallback·char 단위 스트리밍
│   │   ├── agent_runner.py         # Agent 실행 단일화 (재시도·검증·타임아웃)
│   │   └── registry.py             # card.json → AgentRunner 빌드
│   ├── orchestration/
│   │   ├── orchestrator.py         # 단일 턴 실행 파이프라인
│   │   ├── super_orchestrator.py   # 멀티 서비스 통합 + A2AServiceProxy
│   │   ├── flow_handler.py         # BaseFlowHandler + _stream_agent_turn() 헬퍼
│   │   ├── flow_utils.py           # update_memory_and_save() 공통 유틸
│   │   ├── manifest_loader.py      # YAML 로드·클래스 resolve·AgentRunner 빌드 유틸
│   │   └── defaults.py             # make_error_event() — 예외 → 사용자 메시지 변환
│   ├── memory/
│   │   └── memory_manager.py       # raw_history 추가 + LLM 자동 요약
│   ├── state/
│   │   ├── base_state.py           # BaseState (scenario, stage, meta, task_queue)
│   │   └── base_state_manager.py   # apply(delta) → state 인터페이스
│   ├── tools/
│   │   ├── base_tool.py            # BaseTool: schema() + run()
│   │   ├── calculator.py           # 사칙연산 Tool (function-calling 예시)
│   │   └── registry.py             # TOOL_REGISTRY: 이름 → Tool 클래스
│   ├── llm/
│   │   └── openai_client.py        # OpenAI chat / chat_stream 래퍼
│   └── api/
│       ├── schemas.py              # OrchestrateRequest / OrchestrateResponse
│       └── router_factory.py       # create_agent_router() → FastAPI 라우터 생성
├── projects/
│   ├── minimal/                    # 신규 서비스 템플릿 (복사 후 시작)
│   │   ├── project.yaml
│   │   ├── manifest.py
│   │   ├── agents/chat_agent/      # ChatAgent: 평문 스트리밍, JSON 파싱 없음
│   │   ├── state/                  # MinimalState (stage=INIT 고정, 상태 머신 없음)
│   │   └── flows/                  # DefaultFlowHandler만
│   └── transfer/                   # 이체 서비스 (레퍼런스 구현)
│       ├── project.yaml
│       ├── manifest.py
│       ├── logic.py                # is_confirm() / is_cancel() — regex 기반 policy
│       ├── messages.py             # 사용자 노출 문구 상수
│       ├── agents/
│       │   ├── intent_agent/       # 시나리오 분류 (TRANSFER / GENERAL)
│       │   ├── slot_filler_agent/  # 슬롯 추출 + 오늘 날짜 주입 + parse_error 신호
│       │   ├── interaction_agent/  # slot_errors 인지·배치 안내·자연어 응답
│       │   ├── transfer_execute_agent/  # 이체 실행 (현재 Mock, API 교체 지점)
│       │   └── schemas.py          # IntentResult / SlotResult / InteractionResult
│       ├── state/
│       │   ├── models.py           # TransferState·Stage·Slots·SLOT_SCHEMA
│       │   ├── state_manager.py    # delta 적용·슬롯 검증·단계 전이·slot_errors 설정
│       │   └── stores.py           # InMemorySessionStore 팩토리
│       ├── flows/
│       │   ├── router.py           # TransferFlowRouter: scenario → flow_key
│       │   └── handlers.py         # DefaultFlowHandler · TransferFlowHandler
│       └── tests/
│           ├── test_flow.py        # FlowHandler 단위 테스트 (mock runner)
│           └── test_api.py         # API 스키마 검증
└── frontend/
    └── app.py                      # Streamlit 데모 UI (대화창 + 메모리 탭 + 디버그)
```

---

## 파이프라인 다이어그램

### 전체 흐름

```
POST /v1/agent/chat/stream
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                  CoreOrchestrator                    │
│                                                     │
│  1. SessionStore.get_or_create()  → state, memory   │
│  2. is_mid_flow 판별              → IntentAgent 스킵? │
│  3. IntentAgent (optional)        → scenario 분류    │
│  4. FlowRouter.route()            → flow_key 결정   │
│  5. FlowHandler.run(ctx)          → 이벤트 스트리밍  │
│  6. (finally) SessionStore.save() + _fire_hooks()   │
└──────────────────────────┬──────────────────────────┘
                           │  SSE 이벤트 스트림
                           ▼
         AGENT_START → LLM_TOKEN* → LLM_DONE
         → AGENT_DONE → TASK_PROGRESS? → DONE
```

### Transfer 플로우 상세

```
사용자 메시지
      │
      ▼
┌─────────────────┐
│  READY 단계?    │─── YES ──► is_confirm() / is_cancel()  ← LLM 없음
└────────┬────────┘                    │
         │ NO                          ▼
         ▼                    delta = confirm / cancel / []
┌─────────────────┐
│ SlotFillerAgent │  ← 오늘 날짜 주입
│  (LLM 호출)     │
└────────┬────────┘
         │ delta = {operations, tasks?, _meta?}
         ▼
┌─────────────────────────────────────────────┐
│  TransferStateManager.apply(delta)          │
│  · 슬롯 set/clear/confirm/cancel 처리       │
│  · 슬롯 검증 → slot_errors 기록             │
│  · parse_error → slot_errors._unclear       │
│  · FILLING 횟수 초과 → UNSUPPORTED          │
│  · 단계 전이: INIT→FILLING→READY→CONFIRMED  │
└─────────────────┬───────────────────────────┘
                  │ stage?
      ┌───────────┼───────────────┬──────────────┐
      ▼           ▼               ▼              ▼
 UNSUPPORTED   CONFIRMED      READY          FILLING/INIT
 안내 + 리셋  Execute 실행   확인 메시지     InteractionAgent
                              (코드 생성)    (slot_errors 인지)
```

### 상태(Stage) 전이

```
INIT ──► FILLING ──► READY ──► CONFIRMED ──► EXECUTED
  │          │                      │             │
  │          └──► CANCELLED         └──► FAILED   │
  │          └──► UNSUPPORTED                     │
  └──────────────────────────────────────────────►┘
                  (세션 리셋 후 INIT으로)
```

---

## 주요 컴포넌트

| 컴포넌트 | 역할 | 파일 |
|----------|------|------|
| `CoreOrchestrator` | 단일 턴 파이프라인 실행·세션 관리·훅 처리 | `core/orchestration/orchestrator.py` |
| `SuperOrchestrator` | 여러 서비스 통합. CoreOrchestrator와 동일한 인터페이스 | `core/orchestration/super_orchestrator.py` |
| `A2AServiceProxy` | 별도 프로세스 서비스를 HTTP로 호출. SuperOrchestrator에 끼워 사용 | `core/orchestration/super_orchestrator.py` |
| `ExecutionContext` | state·memory·metadata 컨테이너. Agent는 Context로만 접근 | `core/context.py` |
| `BaseFlowHandler` | 에이전트 실행 순서·분기의 유일한 위치 | `core/orchestration/flow_handler.py` |
| `AgentRunner` | 이름으로 Agent 실행. 재시도·타임아웃·스키마 검증 | `core/agents/agent_runner.py` |
| `ConversationalAgent` | JSON 파싱·검증·fallback·char 단위 스트리밍 공통 구현 | `core/agents/conversational_agent.py` |
| `MemoryManager` | raw_history 추가 + LLM 자동 요약 (threshold 도달 시) | `core/memory/memory_manager.py` |
| `BaseTool` | function-calling Tool 기반 클래스 | `core/tools/base_tool.py` |

---

## SSE 이벤트 스펙

| 이벤트 | payload | 설명 |
|--------|---------|------|
| `AGENT_START` | `{agent, label}` | 에이전트 시작 알림 |
| `LLM_TOKEN` | `str` | LLM 글자 단위 (스트리밍) |
| `LLM_DONE` | `{action, message, ...}` | LLM 응답 완료 |
| `AGENT_DONE` | `{agent, label, success, retry_count?}` | 에이전트 완료 |
| `TASK_PROGRESS` | `{index, total, slots}` | 배치 이체 진행 상황 |
| `DONE` | `{message, action, ui_hint, state_snapshot, hooks?}` | 턴 완료 |

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/v1/agent/chat` | 비스트리밍. `{session_id, message}` → `{interaction, hooks}` |
| POST/GET | `/v1/agent/chat/stream` | SSE 스트리밍. 위 이벤트 스펙 참고 |
| GET | `/v1/agent/completed` | `session_id` 쿼리 → 세션별 완료 이력 |
| GET | `/v1/agent/debug` | `session_id` 쿼리 → state·memory·summarize_threshold (개발용) |

---

## Hooks

이체 완료 등 이벤트를 **프론트와 서버 양쪽**에 전달하는 메커니즘.

```python
# FlowHandler에서 DONE payload에 hooks 추가
payload = {
    "message": "이체가 완료됐어요.",
    "action": "DONE",
    "hooks": [{"type": "transfer_completed", "data": slots.model_dump()}],
}

# manifest.py에서 서버 사이드 핸들러 등록
"hook_handlers": {
    "transfer_completed": lambda ctx, data: send_push(data["target"]),
}
```

프론트는 DONE 이벤트의 `hooks` 배열을 읽어 필요한 UI 동작을 수행한다.
서버는 `hook_handlers`에 등록된 함수를 자동 실행한다.

---

## 메모리 — Context Engineering

```
┌─────────────────────────────────────────────┐
│  [System Prompt]    ← agent 시스템 프롬프트  │
│  [Memory Block]     ← summary_text (장기)   │
│  [Recent Turns]     ← raw_history (최근 N턴) │
│  [Current Turn]     ← user_message          │
└─────────────────────────────────────────────┘
```

- `summary_text`: 6턴(설정 가능) 이후 자동 LLM 요약. 세션 리셋 후에도 유지.
- `raw_history`: 최근 N턴 원본. 요약 후 최근 3턴(설정 가능)만 유지.
- 프론트에서 "📝 요약 / 💬 히스토리" 탭으로 실시간 확인 가능.

---

## 실행 방법

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env에 OPENAI_API_KEY 등 설정

# 3. 서버 실행
uvicorn app.main:app --reload

# 4. 프론트엔드 (선택)
streamlit run frontend/app.py
```

---

## 새 서비스 추가

`app/projects/minimal/`을 복사해서 시작한다.

### 구현 순서

```
1. project.yaml          → 서비스 이름·에이전트 목록
2. state/models.py       → Stage enum + State + SLOT_SCHEMA
3. state/state_manager.py → apply(delta) 구현
4. state/stores.py       → SessionStore 팩토리
5. agents/               → run() / run_stream() 구현
6. flows/router.py       → scenario → flow_key 매핑
7. flows/handlers.py     → 에이전트 파이프라인 + 분기
8. messages.py           → 사용자 노출 문구 상수
9. manifest.py           → CoreOrchestrator 조립
10. app/main.py          → 서비스 등록
```

### 복잡도별 가이드

| 서비스 유형 | 에이전트 구성 | 참고 |
|-------------|---------------|------|
| 단순 대화 | ChatAgent 1개 | `minimal` 그대로 복사 |
| 인텐트 분기 | IntentAgent + N 핸들러 | router만 확장 |
| 슬롯 수집 + 실행 | SlotAgent + InteractionAgent + ExecuteAgent | `transfer` 참고 |
| 다건 처리 | 위 + task_queue | `transfer` 배치 로직 참고 |

### 멀티 서비스 확장

```python
# app/main.py 교체만으로 기존 API 라우터 변경 없이 확장
from app.core.orchestration import SuperOrchestrator, KeywordServiceRouter

orchestrator = SuperOrchestrator(
    services={
        "transfer": CoreOrchestrator(transfer_manifest),
        "balance":  CoreOrchestrator(balance_manifest),          # 새 서비스: 한 줄
        "card":     A2AServiceProxy("http://card-svc/v1/agent"), # A2A 원격: 한 줄
    },
    router=KeywordServiceRouter(rules={"transfer": ["이체", "송금"]}, default="transfer"),
)
agent_router = create_agent_router(orchestrator)  # 기존 코드 그대로
```

---

## 테스트

```bash
# FlowHandler 단위 테스트 (mock runner — LLM 호출 없음)
pytest app/projects/transfer/tests/test_flow.py -v

# API 스키마·엔드포인트 검증
pytest app/projects/transfer/tests/test_api.py -v
```

---

## 확장 포인트 요약

| 항목 | 방법 |
|------|------|
| 새 Agent | `BaseAgent` 또는 `ConversationalAgent` 상속, `card.json` 등록 |
| 새 Tool | `BaseTool` 상속 → `TOOL_REGISTRY` 등록 → `card.json "tools"` 추가 |
| 새 시나리오 | `SCENARIO_TO_FLOW` 한 줄 + FlowHandler 구현 |
| 새 서비스 | `minimal/` 복사 → 위 구현 순서 따라 진행 |
| 서버 사이드 훅 | `manifest["hook_handlers"]`에 `{type: fn}` 등록 |
| 멀티 서비스 | `SuperOrchestrator` + `KeywordServiceRouter` 사용 |
| 원격 서비스 연결 | `A2AServiceProxy(endpoint)` 사용 |
| 메모리 튜닝 | `MemoryManager(summarize_threshold=N, keep_recent_turns=M)` |
