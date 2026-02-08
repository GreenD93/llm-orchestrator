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
├── main.py                    # FastAPI 앱, manifest 로드 → CoreOrchestrator → create_agent_router
├── core/                      # 공통 (도메인 무관)
│   ├── config.py
│   ├── logging.py
│   ├── events.py
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── execution_agent.py # 재시도/검증/타임아웃, RetryableError·FatalExecutionError
│   │   ├── agent_executor.py
│   │   └── registry.py        # spec 기반 AgentExecutor 생성
│   ├── orchestration/
│   │   ├── orchestrator.py     # CoreOrchestrator
│   │   ├── flow_router.py     # BaseFlowRouter
│   │   └── flow_handler.py    # BaseFlowHandler
│   ├── memory/
│   │   ├── memory_manager.py
│   │   └── summarizer_agent.py
│   ├── state/
│   │   ├── base_state.py
│   │   └── base_state_manager.py
│   ├── experimental/
│   │   └── tool_registry.py   # 선택 사항 (Tool/MCP 등록)
│   ├── llm/
│   │   └── openai_client.py
│   └── api/
│       └── router_factory.py   # create_agent_router(orchestrator) → POST/GET 라우트 자동 생성
│
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
│                         CoreOrchestrator (manifest 기반 조립)                              │
│  SessionStore  ·  CompletedStore  ·  MemoryManager + Summarizer  ·  Executors  ·  Handlers │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │   Intent (Executor)   │
                              │   TRANSFER / 기타     │
                              └───────────┬───────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │     FlowRouter        │
                              │  intent + state 기준   │
                              └───────────┬───────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
        ┌───────────────────────┐                   ┌───────────────────────┐
        │   DEFAULT_FLOW        │                   │   TRANSFER_FLOW       │
        │   (DefaultFlowHandler)│                   │ (TransferFlowHandler)│
        └───────────┬───────────┘                   └───────────┬───────────┘
                    │  Interaction만 수행                         │  Slot → State 적용
                    │  메모리 갱신 → DONE                          │  → Interaction → terminal 시 Completed
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
| **CoreOrchestrator** | manifest로 Session/Memory/Execution/Agents 조립, FlowRouter → FlowHandler 연결. 도메인 무관. |
| **manifest** | project.yaml 로드, class path → 실제 클래스 resolve, CoreOrchestrator에 전달할 dict 생성. |
| **BaseFlowRouter** | intent·state로 플로우 키 결정. 프로젝트별 상속 (예: TransferFlowRouter). |
| **BaseFlowHandler** | executors, memory, sessions, state_manager_factory, completed 주입. `get(agent_name)`으로 executor 조회. run()은 프로젝트별 구현 (코드 DSL). |
| **DefaultFlowHandler** | Interaction만 호출 후 메모리 갱신, DONE. |
| **TransferFlowHandler** | Slot 호출 → StateManager.apply → Interaction → terminal이면 Completed 저장 → DONE. |
| **AgentExecutor** | 실행 정책 단일 책임. retry, schema 검증, hooks. Agent는 실행 정책을 모름. |

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

## API 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/v1/agent/chat` | 비스트리밍. `session_id`, `message` → `{ interaction, hooks }` |
| POST / GET | `/v1/agent/chat/stream` | 스트리밍 (SSE). 이벤트: LLM_TOKEN, LLM_DONE, DONE |
| GET | `/v1/agent/completed` | 세션별 완료 이력 (`session_id` 쿼리) |

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
3. **manifest.py** 작성: `load_manifest()`에서 YAML 로드, class resolve, sessions_factory, completed_factory, memory_manager_factory, execution_agent_factory, executors_factory, agents, state, flows, on_error 반환
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
# transfer 프로젝트 FlowHandler 단위 테스트 (실제 LLM 호출 없이 mock)
pytest app/projects/transfer/tests/test_flow.py -v
```

---

## 확장 포인트 (템플릿 옵션)

| 항목 | 설명 |
|------|------|
| **EventType.FLOW** | core/events.py에서 미사용. 필요 시 enum에 추가 후 executor에서 yield. |
| **summary_struct** | memory에 optional. summarizer가 반환할 때만 설정. |
| **CompletedStore** | BaseFlowHandler 생성자에서 `completed=None` 허용. 완료 이력이 필요할 때만 manifest에서 전달. |
| **knowledge/retriever** | stub 유지. RAG 연동 시 retriever 구현 후 Agent에 주입. |

---

## 정리

- **템플릿**: core(공통) + projects(프로젝트별). project.yaml + manifest로 CoreOrchestrator 조립.
- **라우터**: `create_agent_router(orchestrator)`로 POST/GET 엔드포인트 자동 생성. 프로젝트 추가 시 라우터 코드 작성 불필요.
- **Flow**: 그래프 엔진 없이 Python 코드로 명시적 순서만 표현 (BaseFlowHandler 상속, get(agent_name), run() 구현).
