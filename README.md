# LLM 오케스트레이터 (멀티턴 슬롯필링 / 시나리오 기반)

**멀티턴 슬롯필링·시나리오 기반 AI 오케스트레이션** 공통 템플릿입니다.  
FastAPI + SSE 스트리밍을 사용하며, **프로젝트별로 Agent + Flow만 정의**하면 동작합니다.

- **core**: 도메인 무관 공통 레이어 (오케스트레이터, 플로우, 에이전트 실행, 메모리, 상태, 도구)
- **projects**: 프로젝트 단위 정의 (project.yaml, manifest, agents, state, flows)

첫 샘플 프로젝트는 **이체(transfer)** 입니다. Intent 분류 후 FlowRouter로 플로우를 나누고, **일반 대화(DEFAULT_FLOW)** 또는 **이체 플로우(TRANSFER_FLOW)**에서 Slot Filling → State 적용 → Interaction 순으로 진행됩니다.

---

## 프로젝트 구조

```
app/
├── main.py                    # FastAPI 앱, manifest → CoreOrchestrator → 단일 orchestrate API
├── core/                      # 공통 (도메인 무관)
│   ├── config.py
│   ├── context.py             # ExecutionContext (state, memory, metadata 통합)
│   ├── hooks.py               # before_agent, after_agent, on_error, after_turn
│   ├── events.py              # EventType 상수 (DONE, LLM_TOKEN, LLM_DONE)
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── agent_runner.py    # Agent 실행 단일화 (재시도/검증/타임아웃)
│   │   └── registry.py        # get_registry, build_runner
│   ├── orchestration/
│   │   ├── orchestrator.py    # 단일 턴 실행만 담당
│   │   ├── flow_router.py     # 모든 flow 결정 로직 (조건문)
│   │   ├── flow_handler.py    # Agent 실행만 (Runner 호출)
│   │   └── flow_utils.py      # update_memory_and_save
│   ├── memory/
│   │   └── memory_manager.py  # enable_memory, raw_history (요약은 after_turn 훅)
│   ├── state/
│   │   ├── base_state.py
│   │   └── base_state_manager.py
│   ├── llm/
│   │   └── openai_client.py
│   └── api/
│       ├── schemas.py         # OrchestrateRequest, OrchestrateResponse
│       └── router_factory.py  # create_agent_router → POST/chat, POST/chat/stream, GET/completed
├── plugins/
│   └── experimental/          # Tool/MCP 등 (선택, core에서 미참조)
│       └── tool_registry.py
└── projects/
    ├── minimal/                # 최소 템플릿 (복붙 후 이름만 바꿔 새 프로젝트 시작)
    │   ├── project.yaml        # interaction 단일 agent, 1-step flow, BaseState만 사용
    │   ├── manifest.py
    │   ├── agents/ (interaction만), state/, flows/, tests/
    │   └── ...
    └── transfer/               # 이체 프로젝트 (샘플)
        ├── project.yaml        # 프로젝트 정의 (agents, flows, state.manager)
        ├── manifest.py         # YAML → runtime 객체 (CoreOrchestrator에 전달할 dict)
        ├── agents/
        │   ├── intent_agent/      # agent.py, prompt.py, card는 cards/intent.json
        │   ├── slot_filler_agent/
        │   ├── interaction_agent/
        │   ├── transfer_execute_agent/
        │   ├── schemas.py
        │   └── cards/*.json
        ├── state/
        │   ├── models.py
        │   ├── state_manager.py
        │   └── stores.py
        ├── flows/
        │   ├── router.py       # TransferFlowRouter
        │   └── handlers.py     # DefaultFlowHandler, TransferFlowHandler
        ├── knowledge/
        │   ├── docs/
        │   └── retriever.py
        └── tests/
            ├── mock_llm.py
            └── test_flow.py
```

---

## 파이프라인 다이어그램

### 전체 흐름 (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              API Layer (FastAPI)                                          │
│   POST /v1/agent/chat   │   POST·GET /v1/agent/chat/stream   │   GET /v1/agent/completed  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         CoreOrchestrator (단일 턴 실행)                                    │
│  SessionStore  ·  MemoryManager  ·  AgentRunner  ·  FlowRouter  ·  FlowHandlers           │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │  Intent (Runner.run)  │
                              │  TRANSFER / 기타      │
                              └───────────┬───────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │     FlowRouter        │
                              │  intent + state 조건문  │
                              └───────────┬───────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
        ┌───────────────────────┐                   ┌───────────────────────┐
        │   DEFAULT_FLOW        │                   │   TRANSFER_FLOW       │
        │   (DefaultFlowHandler)│                   │ (TransferFlowHandler)│
        └───────────┬───────────┘                   └───────────┬───────────┘
                    │  Handler: interaction만 실행                  │  Handler: slot → apply → interaction
                    │  after_turn 훅에서 메모리 갱신                 │  terminal 시 Completed, after_turn
                    └─────────────────────┬───────────────────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │  SessionStore.save    │
                              └───────────────────────┘
```

### TRANSFER_FLOW 상세

```
  사용자 메시지
        │
        ▼
┌───────────────┐     operations      ┌─────────────────┐
│ Slot Executor │ ──────────────────► │  StateManager   │
│ (SlotFiller)  │                     │  apply(delta)   │
└───────────────┘                     └────────┬────────┘
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ Interaction     │
                                      │ (state, history,│
                                      │  memory 요약)   │
                                      └────────┬────────┘
                          stage ∈ {EXECUTED, FAILED, CANCELLED}
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ CompletedStore  │
                                      └─────────────────┘
```

---

## 주요 컴포넌트

| 컴포넌트 | 역할 |
|----------|------|
| **CoreOrchestrator** | 단일 턴만 담당. Session 로드 → Router로 flow 결정 → Handler.run(ctx) → 저장/after_turn. |
| **manifest** | project.yaml 로드, runner·router·handlers·훅 조립. |
| **BaseFlowRouter** | intent·state로 flow 키 반환. 프로젝트별 상속, 명시적 조건문만 사용. |
| **BaseFlowHandler** | runner, sessions, memory_manager, state_manager_factory 주입. run(ctx)에서 Runner로 에이전트만 실행. |
| **AgentRunner** | Agent 실행 단일화. run(name, context) / run_stream(name, context). 재시도·검증·타임아웃 포함. |
| **ExecutionContext** | session_id, user_message, state, memory, metadata. Agent는 Context로만 상태 접근. |
| **Registry** | 문자열 → Agent 클래스 매핑. build_runner(specs, schema_registry, validator_map)으로 Runner 생성. |

---

## 상태(Stage) 흐름 (transfer)

```
INIT → FILLING → READY → CONFIRMED
                ↑
                └── AWAITING_CONTINUE_DECISION
                └── CANCELLED (cancel_flow op)
                └── UNSUPPORTED (filling_turns > MAX_FILL_TURNS, 고정 메시지로 종료)

터미널: EXECUTED, FAILED, CANCELLED, UNSUPPORTED  → (CompletedStore는 옵션)
```

- **필수 슬롯**: `target`, `amount`
- **READY**: 필수 슬롯이 모두 채워진 상태. 확인 후 `confirm` op로 CONFIRMED.

---

## API 요약 (단일 orchestrate 진입점)

| 메서드 | 경로 | 스키마 | 설명 |
|--------|------|--------|------|
| POST | `/v1/agent/chat` | OrchestrateRequest → OrchestrateResponse | 비스트리밍. session_id, message → interaction, hooks |
| POST / GET | `/v1/agent/chat/stream` | OrchestrateRequest / query | 스트리밍 SSE. 이벤트: LLM_TOKEN, LLM_DONE, DONE |
| GET | `/v1/agent/completed` | session_id 쿼리 | 세션별 완료 이력 |

---

## 실행 방법

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경 변수 (OPENAI_API_KEY 등) 설정 후 서버 실행
uvicorn app.main:app --reload
```

---

## 새 프로젝트 추가 방법

1. **app/projects/<프로젝트명>/** 생성
2. **project.yaml** 작성: name, agents(class, card, stream), flows(router, handlers), state.manager
3. **manifest.py** 작성: `load_manifest()`에서 YAML 로드, class resolve, sessions_factory, completed_factory, memory_manager_factory, **runner** (build_runner), state, flows, on_error, after_turn 반환
4. **agents/** 에 에이전트 클래스 + cards, **state/** 에 models·state_manager·stores, **flows/** 에 router·handlers 구현
5. **app/main.py** 에서 해당 프로젝트의 `load_manifest()` 사용

```python
# main.py 예시 (프로젝트 전환 시)
from app.projects.transfer.manifest import load_manifest
# from app.projects.other_project.manifest import load_manifest
manifest = load_manifest()
```

---

## 테스트

```bash
# Flow 단위 테스트 (mock runner)
pytest app/projects/transfer/tests/test_flow.py app/projects/minimal/tests/test_flow.py -v

# API 스키마·엔드포인트 검증 (orchestrator mock)
pytest app/projects/transfer/tests/test_api.py -v
```

---

## 확장 (유지 범위)

| 항목 | 설명 |
|------|------|
| **새 Agent 추가** | Agent 클래스 run(context) 구현, manifest agents에 등록, Handler에서 runner.run(name, ctx) 호출. |
| **Router 조건 추가** | BaseFlowRouter 상속, route(intent, state) 안에 조건문 추가. |
| **after_turn** | 메모리 갱신·요약 등 턴 종료 시 처리. manifest에서 after_turn 훅으로 등록. |
| **CompletedStore** | 완료 이력 필요 시 manifest에서 completed_factory 제공. |
| **plugins/experimental** | Tool/MCP 등 실험 기능은 plugins에 두고 core에서 참조하지 않음. |

---

## 정리

- **단일 턴**: Orchestrator → Router(flow 결정) → Handler(Agent 실행만). Flow는 별도 클래스 없이 Router 조건문으로 분기.
- **Context**: state, memory, metadata는 ExecutionContext로 통합. Agent는 run(context)만 사용.
- **API**: OrchestrateRequest/OrchestrateResponse 기준 단일 진입점. `create_agent_router(orchestrator)`로 엔드포인트 생성.
- **확장**: 새 Agent 추가·Router 조건 추가 수준만 유지. 범용 플러그인/동적 로딩은 없음.
