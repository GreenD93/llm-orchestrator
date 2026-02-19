# LLM Orchestrator — 통합 가이드

> **"GUIDE.md 읽고 XXX 서비스 만들어줘"** 한 마디로 바이브 코딩할 수 있는 종합 문서.

---

## 1. 한눈에 보기

**LLM 에이전트들을 조합해 대화형 AI 서비스를 만드는 백엔드 엔진.**

- 사용자 메시지 1개 → 에이전트 파이프라인 실행 → SSE 이벤트 스트림 반환
- 각 서비스는 `app/projects/<name>/`에 독립적으로 구현
- `app/core/`는 공통 엔진이며 서비스별 로직을 포함하지 않는다
- 여러 서비스를 `SuperOrchestrator`로 묶어 하나의 앱으로 확장 가능

### 요청 1개의 전체 흐름

```
POST /v1/agent/chat/stream
         |
         v
+---------------------------------------------------------+
|                    CoreOrchestrator                      |
|                                                         |
|  1. SessionStore.get_or_create()  -> state, memory      |
|  2. is_mid_flow 판별              -> IntentAgent 스킵?  |
|  3. IntentAgent (optional)        -> scenario 분류      |
|  4. FlowRouter.route()            -> flow_key 결정      |
|  5. FlowHandler.run(ctx)          -> 이벤트 스트리밍     |
|  6. (finally) SessionStore.save() + _fire_hooks()       |
+--------------------------+------------------------------+
                           |  SSE 이벤트 스트림
                           v
         AGENT_START -> LLM_TOKEN* -> LLM_DONE
         -> AGENT_DONE -> TASK_PROGRESS? -> DONE
```

### 클래스 책임 분리표

| 구성요소 | 역할 | 위치 |
|----------|------|------|
| `CoreOrchestrator` | 요청 수신, 세션 관리, 에러 핸들링, 훅 실행 | `core/orchestration/orchestrator.py` |
| `ExecutionContext` | Agent가 읽는 유일한 입력 (state, memory, user_message) | `core/context.py` |
| `BaseAgent` | LLM 호출 단위. `run()` 또는 `run_stream()` 구현 | 각 프로젝트 `agents/` |
| `ConversationalAgent` | JSON 출력, 파싱, fallback, 스트리밍 기본 구현 | `core/agents/conversational_agent.py` |
| `AgentRunner` | Agent를 이름으로 실행. retry, timeout, 스키마 검증 | `core/agents/agent_runner.py` |
| `BaseFlowHandler` | **에이전트 실행 순서, 분기 로직의 유일한 위치** | 각 프로젝트 `flows/handlers.py` |
| `BaseFlowRouter` | scenario -> flow_key 매핑 | 각 프로젝트 `flows/router.py` |
| `BaseState` | 서비스 상태. Pydantic 모델 | 각 프로젝트 `state/models.py` |
| `StateManager` | state 전이 로직 (코드). LLM delta를 받아 state 업데이트 | 각 프로젝트 `state/state_manager.py` |
| `MemoryManager` | summary_text 자동 요약 + raw_history 관리 | `core/memory/memory_manager.py` |
| `TurnTracer` | 턴 단위 에이전트 실행 추적. AgentRunner가 자동 기록 | `core/tracing.py` |
| `AgentResult` | 에이전트 표준 응답 (success/need_info/cannot_handle/partial) | `core/agents/agent_result.py` |
| `ManifestBuilder` | manifest.py 보일러플레이트를 빌더 패턴으로 간소화 | `core/orchestration/manifest_loader.py` |
| `BaseLLMClient` | LLM 프로바이더 인터페이스. OpenAI/Anthropic 교체 가능 | `core/llm/base_client.py` |
| `SuperOrchestrator` | 여러 CoreOrchestrator / A2AServiceProxy를 하나로 묶음 | `core/orchestration/super_orchestrator.py` |

---

## 2. 프로젝트 구조

```
app/
+-- core/                              <- 도메인 무관 프레임워크 (수정 금지)
|   +-- config.py                      <- 환경변수 -> Settings 싱글톤
|   +-- context.py                     <- ExecutionContext + build_messages()
|   +-- events.py                      <- EventType enum
|   +-- tracing.py                     <- TurnTracer (에이전트 실행 추적)
|   +-- agents/
|   |   +-- base_agent.py              <- BaseAgent (LLM 호출, tool-call 루프)
|   |   +-- conversational_agent.py    <- JSON 파싱, 검증, fallback, char 스트리밍
|   |   +-- agent_runner.py            <- AgentRunner (재시도, 검증, 타임아웃)
|   |   +-- agent_result.py            <- AgentResult 표준 응답
|   |   +-- registry.py                <- build_runner() (card.json -> 인스턴스 생성)
|   +-- orchestration/
|   |   +-- orchestrator.py            <- CoreOrchestrator (단일 턴 실행기)
|   |   +-- super_orchestrator.py      <- SuperOrchestrator, A2AServiceProxy
|   |   +-- flow_handler.py            <- BaseFlowHandler 인터페이스
|   |   +-- flow_router.py             <- BaseFlowRouter 인터페이스
|   |   +-- manifest_loader.py         <- ManifestBuilder, resolve_class, load_yaml
|   |   +-- defaults.py                <- make_error_event() 공통 에러 응답
|   +-- state/
|   |   +-- base_state.py              <- BaseState (scenario, stage, meta, task_queue)
|   |   +-- base_state_manager.py      <- BaseStateManager.apply(delta)
|   |   +-- stores.py                  <- InMemorySessionStore, InMemoryCompletedStore
|   +-- memory/
|   |   +-- memory_manager.py          <- 자동 요약, raw_history 관리
|   +-- llm/
|   |   +-- base_client.py             <- BaseLLMClient 인터페이스 + LLMResponse/ToolCall
|   |   +-- openai_client.py           <- OpenAI 프로바이더
|   |   +-- anthropic_client.py        <- Anthropic 프로바이더
|   +-- tools/
|   |   +-- base_tool.py               <- BaseTool 인터페이스
|   |   +-- calculator.py              <- Calculator (예시 Tool)
|   |   +-- registry.py                <- TOOL_REGISTRY, build_tools()
|   +-- api/
|       +-- schemas.py                 <- OrchestrateRequest / OrchestrateResponse
|       +-- router_factory.py          <- create_agent_router() -> FastAPI 라우터
+-- projects/
|   +-- minimal/                       <- 새 서비스 시작점 (복사해서 사용)
|   +-- transfer/                      <- 이체 서비스 (레퍼런스 구현)
+-- main.py                            <- FastAPI 앱 진입점
```

---

## 3. 새 서비스 만들기 — 3가지 경로

### 경로 A: 단순 대화 (minimal 복사)

ChatAgent 1개로 자유 대화. 상태 머신 없음.

**1단계: 복사**

```bash
cp -r app/projects/minimal app/projects/my_service
```

**2단계: 수정 체크리스트**

| 파일 | 수정 내용 |
|------|-----------|
| `project.yaml` | `name: my_service` |
| `agents/chat_agent/prompt.py` | 서비스 역할, 성격, 지침 |
| `agents/chat_agent/card.json` | LLM 모델, 온도, 정책 |
| `manifest.py` | `PROJECT_MODULE = "app.projects.my_service"` |

**3단계: main.py 등록**

```python
# app/main.py
from app.projects.my_service.manifest import load_manifest

manifest = load_manifest()
orchestrator = CoreOrchestrator(manifest)
```

**project.yaml 예시 (minimal 그대로)**

```yaml
name: my_service

agents:
  chat:
    class: ChatAgent
    card: agents/chat_agent/card.json
    stream: true

flows:
  router: flows.router.MinimalFlowRouter
  handlers:
    DEFAULT_FLOW: flows.handlers.ChatFlowHandler

state:
  model: state.models.MinimalState
  manager: state.models.MinimalStateManager
```

**manifest.py 예시**

```python
from pathlib import Path
from app.core.orchestration.manifest_loader import ManifestBuilder

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_MODULE = "app.projects.my_service"

def load_manifest():
    return (
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
        .class_name_map({
            "ChatAgent": "agents.chat_agent.agent.ChatAgent",
        })
        .build()
    )
```

**ChatAgent 예시**

```python
from app.core.agents.base_agent import BaseAgent
from app.core.context import ExecutionContext
from app.core.events import EventType

class ChatAgent(BaseAgent):
    supports_stream = True

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        messages = context.build_messages()
        message = self.chat(messages)
        return {"action": "ASK", "message": message}

    def run_stream(self, context: ExecutionContext, **kwargs):
        messages = context.build_messages()
        buffer = ""
        for token in self.chat_stream(messages):
            buffer += token
            yield {"event": EventType.LLM_TOKEN, "payload": token}
        yield {"event": EventType.LLM_DONE, "payload": {"action": "ASK", "message": buffer}}
```

**FlowHandler (1줄)**

```python
from app.core.orchestration.flow_handler import BaseFlowHandler

class ChatFlowHandler(BaseFlowHandler):
    def run(self, ctx):
        yield from self._stream_agent_turn(ctx, "chat", "응답 생성 중")
```

---

### 경로 B: 인텐트 분기 (IntentAgent + Router 추가)

경로 A에 IntentAgent와 FlowRouter를 추가해 시나리오별 핸들러 분기.

**추가 파일**

```
agents/
  intent_agent/
    agent.py      <- IntentAgent (비스트리밍, dict 반환)
    prompt.py     <- 시나리오 분류 프롬프트
    card.json     <- 빠른 모델 + 낮은 온도
flows/
  router.py       <- scenario -> flow_key 매핑
  handlers.py     <- FlowHandler 추가
```

**IntentAgent 예시**

```python
from app.core.agents.base_agent import BaseAgent
from app.core.agents.agent_runner import RetryableError

class IntentAgent(BaseAgent):
    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context, **kwargs) -> dict:
        messages = context.build_messages()
        raw = self.chat(messages).strip().upper()
        if raw not in ("FAQ", "GENERAL"):
            raise RetryableError(f"invalid_intent: {raw}")
        return {"scenario": raw, "supported": raw == "FAQ"}
```

**FlowRouter 예시**

```python
from app.core.orchestration.flow_router import BaseFlowRouter

SCENARIO_TO_FLOW = {
    "FAQ": "FAQ_FLOW",
}

class MyFlowRouter(BaseFlowRouter):
    def route(self, intent_result, state) -> str:
        scenario = intent_result.get("scenario", "GENERAL")
        return SCENARIO_TO_FLOW.get(scenario, "DEFAULT_FLOW")
```

**project.yaml 추가 항목**

```yaml
agents:
  intent:
    class: IntentAgent
    card: agents/intent_agent/card.json
  chat:
    class: ChatAgent
    card: agents/chat_agent/card.json
    stream: true

flows:
  router: flows.router.MyFlowRouter
  handlers:
    DEFAULT_FLOW: flows.handlers.ChatFlowHandler
    FAQ_FLOW: flows.handlers.FAQFlowHandler
```

---

### 경로 C: 슬롯 수집 + 실행 (transfer 수준)

상태 머신, 슬롯 검증, 에러 전파, 배치 처리까지 필요한 복잡한 서비스.

**전체 파일 목록**

```
app/projects/<name>/
+-- project.yaml           <- 서비스 이름, 에이전트 목록, router/handler, state.model
+-- manifest.py            <- ManifestBuilder로 CoreOrchestrator 조립
+-- messages.py            <- 사용자 노출 문구 상수
+-- logic.py               <- is_confirm() / is_cancel() 등 결정론적 로직
+-- agents/
|   +-- intent_agent/      <- 시나리오 분류
|   +-- slot_filler_agent/ <- JSON delta 추출
|   +-- interaction_agent/ <- 자연어 응답 생성
|   +-- execute_agent/     <- 실행 (API 호출)
+-- state/
|   +-- models.py          <- Stage enum + Slots + State + SLOT_SCHEMA
|   +-- state_manager.py   <- apply(delta): 슬롯 검증, 단계 전이
|   +-- stores.py          <- SessionStore 팩토리
+-- flows/
    +-- router.py          <- scenario -> flow_key
    +-- handlers.py        <- DefaultFlowHandler + 메인FlowHandler
```

**구현 순서**

1. `project.yaml` — 이름, 에이전트 목록
2. `state/models.py` — Stage enum, Slots, State, SLOT_SCHEMA
3. `state/state_manager.py` — apply(delta) 구현
4. `state/stores.py` — SessionStore 팩토리
5. `agents/` — 에이전트 구현 (`context.build_messages()` 사용)
6. `flows/router.py` — scenario -> flow_key
7. `flows/handlers.py` — 에이전트 파이프라인 + 분기
8. `messages.py` — 사용자 메시지 상수
9. `logic.py` — 결정론적 분기 (confirm/cancel 등)
10. `manifest.py` — 조립
11. `app/main.py` — 라우터 등록

**에러 전파 패턴 (SlotFiller -> StateManager -> InteractionAgent)**

```
SlotFillerAgent
  +-- JSON 파싱 실패 -> {"operations": [], "_meta": {"parse_error": True}}
       |
TransferStateManager.apply()
  +-- parse_error 감지 -> state.meta.slot_errors["_unclear"] = "이해하지 못했어요."
       |
InteractionAgent
  +-- state.meta.slot_errors._unclear 인지 -> "다시 알려주세요."

StateManager 검증 실패 (amount=0 등)
  +-- state.meta.slot_errors["amount"] = SLOT_SCHEMA error_msg
       |
InteractionAgent
  +-- slot_errors.amount 인지 -> 에러 메시지 전달
```

---

## 4. 파일별 작성 가이드

### project.yaml 스펙

```yaml
name: my_service                        # 서비스 이름

agents:
  <agent_key>:                          # runner.run("agent_key", ctx)로 호출
    class: ClassName                    # manifest class_name_map 키와 매칭
    card: agents/<dir>/card.json        # LLM/정책 설정 (상대 경로)
    stream: true                        # run_stream() 사용 시 (기본 false)

flows:
  router: flows.router.MyFlowRouter     # 프로젝트 내 상대 경로
  handlers:
    DEFAULT_FLOW: flows.handlers.ChatFlowHandler
    MY_FLOW: flows.handlers.MyFlowHandler

state:
  model: state.models.MyState           # BaseState 상속 모델
  manager: state.state_manager.MyStateManager  # BaseStateManager 상속
```

### manifest.py (ManifestBuilder)

```python
from pathlib import Path
from app.core.orchestration.manifest_loader import ManifestBuilder

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_MODULE = "app.projects.my_service"

def load_manifest():
    return (
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
        .class_name_map({
            "IntentAgent":  "agents.intent_agent.agent.IntentAgent",
            "SlotAgent":    "agents.slot_agent.agent.SlotAgent",
            "ChatAgent":    "agents.chat_agent.agent.ChatAgent",
        })
        .schema_registry({                      # 선택: Pydantic 검증 모델
            "IntentResult": IntentResult,
        })
        .validator_map({                         # 선택: 커스텀 검증 함수
            "intent_enum": validate_intent,
        })
        .sessions_factory(SessionStore)          # 미지정 시 project.yaml state.model로 자동 구성
        .completed_factory(CompletedStore)       # 선택: 완료 이력 저장
        .memory(                                 # 선택: 커스텀 요약 프롬프트
            summary_system_prompt="요약 지침...",
            summary_user_template="요약 형식... {memory_block} ... {dialog}",
        )
        .build()
    )
```

### card.json (provider / model / policy / tools)

```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "temperature": 0
  },
  "policy": {
    "max_retry": 2,
    "backoff_sec": 1,
    "timeout_sec": 10,
    "validate": "intent_enum",
    "schema": "IntentResult"
  },
  "tools": ["calculator"]
}
```

- `provider`: `"openai"` (기본) 또는 `"anthropic"`
- `policy.validate`: manifest `validator_map` 키와 매칭
- `policy.schema`: manifest `schema_registry` 키와 매칭 (Pydantic 검증)
- `tools`: `TOOL_REGISTRY`에 등록된 tool 이름 목록

### Agent 선택 기준

| | `BaseAgent` 직접 | `ConversationalAgent` | `ChatAgent` (BaseAgent) |
|---|---|---|---|
| 출력 형식 | 자유 (dict) | JSON `{action, message}` | 평문 텍스트 |
| 스키마 검증 | 직접 구현 | 선택적 (`response_schema`) | 없음 |
| fallback | 직접 구현 | 파싱 실패 시 기본 메시지 | 직접 구현 |
| 스트리밍 | 직접 구현 | 버퍼 수집 후 char 단위 emit | 토큰 실시간 emit |
| 첫 글자 응답 속도 | 구현에 따라 | 느림 (버퍼 완성 후) | 빠름 (즉시) |
| 적합한 경우 | IntentAgent 등 | 상태 기반 흐름, UI action | 빠른 대화, 스키마 불필요 |

**ConversationalAgent 상속 방법**

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

### state/models.py + state_manager.py

**State 모델**

```python
from enum import Enum
from pydantic import BaseModel, Field
from app.core.state.base_state import BaseState

class Stage(str, Enum):
    INIT      = "INIT"
    FILLING   = "FILLING"
    READY     = "READY"
    CONFIRMED = "CONFIRMED"
    EXECUTED  = "EXECUTED"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"

class Slots(BaseModel):
    target: str | None = None
    amount: int | None = None

class MyState(BaseState):
    scenario: str = "MY_SCENARIO"
    stage: Stage = Stage.INIT
    slots: Slots = Field(default_factory=Slots)
    missing_required: list[str] = Field(default_factory=list)
    filling_turns: int = 0

SLOT_SCHEMA = {
    "target": {
        "type": str, "required": True,
        "validate": lambda v: bool(v and v.strip()),
        "error_msg": "대상이 올바르지 않아요.",
    },
    "amount": {
        "type": int, "required": True,
        "validate": lambda v: v > 0,
        "error_msg": "금액은 1 이상이어야 해요.",
    },
}
```

**StateManager**

```python
from app.core.state.base_state_manager import BaseStateManager

class MyStateManager(BaseStateManager):
    def apply(self, delta: dict) -> MyState:
        # 1. _meta 처리 (parse_error 등)
        if delta.get("_meta", {}).get("parse_error"):
            self.state.meta.setdefault("slot_errors", {})["_unclear"] = "이해하지 못했어요."

        # 2. operations 적용
        for op in delta.get("operations", []):
            self._apply_op(op)

        # 3. 슬롯 검증 + 단계 전이
        self._validate_required()
        self._transition()
        return self.state
```

### flows/router.py + handlers.py

**Router**

```python
from app.core.orchestration.flow_router import BaseFlowRouter

class MyFlowRouter(BaseFlowRouter):
    def route(self, intent_result, state) -> str:
        scenario = intent_result.get("scenario", "GENERAL")
        if scenario == "MY_SCENARIO":
            return "MY_FLOW"
        return "DEFAULT_FLOW"
```

**Handler**

```python
from app.core.orchestration.flow_handler import BaseFlowHandler
from app.core.events import EventType

class MyFlowHandler(BaseFlowHandler):
    def run(self, ctx):
        # 1. SlotFiller -> StateManager
        yield {"event": EventType.AGENT_START, "payload": {"agent": "slot", "label": "정보 추출 중"}}
        delta = self.runner.run("slot", ctx)
        ctx.state = self.state_manager_factory(ctx.state).apply(delta)
        yield {"event": EventType.AGENT_DONE, "payload": {"agent": "slot", "success": True, "stage": ctx.state.stage}}

        # 2. 단계별 분기
        if ctx.state.stage == Stage.CONFIRMED:
            self.runner.run("execute", ctx)
            ctx.state.stage = Stage.EXECUTED

        # 3. InteractionAgent (스트리밍)
        yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                           done_transform=_apply_ui_policy)
```

### messages.py

```python
TERMINAL_MESSAGES = {
    Stage.EXECUTED:  "완료됐어요. 다른 도움이 필요하신가요?",
    Stage.FAILED:    "실패했어요. 잠시 후 다시 시도해 주세요.",
    Stage.CANCELLED: "취소됐어요. 다른 도움이 필요하신가요?",
}
UNSUPPORTED_MESSAGE = "입력이 반복되어 더 이상 진행할 수 없어요."
```

---

## 5. 코드 패턴 카탈로그

### build_messages() 표준

```python
# Agent.run() 내부 — 모든 Agent에서 동일하게 사용
context_block = f"현재 stage: {ctx.state.stage}\n슬롯: {ctx.state.slots}"
messages = ctx.build_messages(context_block, last_n_turns=6)
raw = self.chat(messages)  # self.system_prompt 자동 prepend
```

`build_messages()`가 반환하는 메시지 구조:
```
[system] context_block + summary_text (장기 기억)
[user/asst] raw_history 최근 N턴 (단기 기억)
[user] user_message   <- 자동으로 마지막에 추가됨 (수동 추가 금지!)
```

### _stream_agent_turn() 헬퍼 (1줄 완성)

단일 에이전트 호출로 대화 턴을 마무리할 때 사용.
`AGENT_START -> 스트리밍 -> AGENT_DONE -> 메모리 저장 -> DONE`을 한 줄로 처리.

```python
# 단순 (minimal 등)
yield from self._stream_agent_turn(ctx, "chat", "응답 생성 중")

# UI 정책 적용 (transfer 등)
yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                   done_transform=_apply_ui_policy)
```

`done_transform`이 없으면 LLM 원본 payload에 `state_snapshot`만 추가.

### _update_memory() 수동 호출 (복잡 분기)

`_stream_agent_turn()` 헬퍼를 쓰지 않고 직접 분기할 때:

```python
# READY 단계: LLM 호출 없이 코드로 메시지 생성
message = build_ready_message(ctx.state)
self._update_memory(ctx, message)  # DONE yield 직전 필수
yield {
    "event": EventType.DONE,
    "payload": {
        "message": message,
        "next_action": "CONFIRM",
        "ui_hint": {"buttons": ["확인", "취소"]},
        "state_snapshot": ctx.state.model_dump(),
    },
}
```

### AgentResult 표준 응답

```python
from app.core.agents.agent_result import AgentResult

# 성공
return AgentResult.success({"action": "ASK", "message": "안녕하세요"})

# 파라미터 부족
return AgentResult.need_info(["amount"], "금액을 알려주세요.")

# 처리 불가
return AgentResult.cannot_handle("지원하지 않습니다.")

# 부분 성공 (파싱 에러 등)
return AgentResult.partial({"operations": []}, reason="parse_error")
```

AgentRunner가 `to_dict()`로 변환. FlowHandler는 dict 형태로 받으며 `_result_status` 필드로 상태 인지.

### 에러 전파 (slot_errors)

**원칙: 오류 신호는 `state.meta.slot_errors`를 통해 전달. `context.metadata`는 agent 간 공유되지 않는다.**

```python
# StateManager에서 에러 기록
self.state.meta.setdefault("slot_errors", {})[slot] = error_msg

# InteractionAgent 프롬프트에서 확인
if ctx.state.meta.get("slot_errors"):
    block += f"\n오류: {ctx.state.meta['slot_errors']}"
```

### 배치 처리 (task_queue)

```python
# SlotFillerAgent가 다건 감지 시:
{"tasks": [{"target": "A", "amount": 10000}, {"target": "B", "amount": None}]}

# Handler에서 분리:
ctx.state.task_queue = tasks[1:]  # 나머지는 큐에
# 현재 턴에서 tasks[0] 처리 -> 완료 후 task_queue에서 하나씩 꺼내 진행

# 진행 상황 이벤트
yield {
    "event": EventType.TASK_PROGRESS,
    "payload": {"index": 1, "total": 3, "slots": ctx.state.slots.model_dump()},
}
```

### Hooks (프론트 + 서버)

```python
# 1. FlowHandler에서 DONE payload에 hooks 추가
payload = {
    "message": "완료됐어요.",
    "action": "DONE",
    "hooks": [{"type": "task_completed", "data": ctx.state.slots.model_dump()}],
}

# 2. manifest.py에 서버 사이드 핸들러 등록
"hook_handlers": {
    "task_completed": lambda ctx, data: send_notification(data),
}

# 흐름: FlowHandler -> DONE payload(hooks) -> 프론트 수신 + 서버 hook_handlers 자동 실행
```

---

## 6. LLM 프로바이더 설정

### card.json provider 필드

```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "temperature": 0
  }
}
```

### OpenAI 예시

```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "temperature": 0.3
  }
}
```

### Anthropic 예시

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
card.json -> provider + model 지정
BaseAgent -> BaseLLMClient 인터페이스만 사용
각 프로바이더 -> 메시지 포맷, tool 포맷, 응답 파싱 내부 처리
```

- **system_prompt 분리**: `chat(system_prompt=..., messages=...)`
  - OpenAI: messages 앞에 `{"role": "system", ...}` prepend
  - Anthropic: `system` 파라미터로 전달
- **tool 스키마 중립 포맷**: `{"name", "description", "parameters"}`
  - OpenAI: `{"type": "function", "function": schema}` 래핑
  - Anthropic: `{"name", "input_schema": schema["parameters"]}` 변환
- **tool-call 루프**: `LLMResponse.tool_calls` -> `build_assistant_message()` -> `build_tool_result_message()`

### 새 프로바이더 추가 방법

1. `core/llm/<provider>_client.py` — `BaseLLMClient` 구현
2. `core/llm/__init__.py` — `create_llm_client()`에 분기 추가
3. `core/config.py` — API 키 설정 추가

---

## 7. API & SSE 이벤트 스펙

### 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/v1/agent/chat` | 비스트리밍. `{session_id, message}` -> `{interaction, hooks}` |
| POST/GET | `/v1/agent/chat/stream` | SSE 스트리밍. 이벤트 스펙 참고 |
| GET | `/v1/agent/completed` | `session_id` 쿼리 -> 세션별 완료 이력 |
| GET | `/v1/agent/debug/{session_id}` | state, memory, completed 스냅샷 (DEV_MODE=true) |

**요청 body**

```json
{
  "session_id": "user-001",
  "message": "안녕하세요"
}
```

### 이벤트 타입별 payload

| EventType | payload | 설명 |
|-----------|---------|------|
| `AGENT_START` | `{agent, label}` | 에이전트 시작 알림 |
| `LLM_TOKEN` | `"토큰 문자열"` | 스트리밍 텍스트 조각 |
| `LLM_DONE` | `{action, message, ...}` | LLM 응답 완료 |
| `AGENT_DONE` | `{agent, label, success, stage?, result?}` | 에이전트 완료 |
| `TASK_PROGRESS` | `{index, total, slots}` | 배치 작업 진행 |
| `DONE` | 아래 참조 | **턴 종료. 반드시 마지막 이벤트** |

### DONE 필수 필드

```json
{
  "message":        "사용자에게 보여줄 텍스트",
  "next_action":    "ASK | CONFIRM | DONE | ASK_CONTINUE",
  "ui_hint":        {"buttons": ["확인", "취소"]},
  "state_snapshot": { "stage": "FILLING", "slots": {...}, ... },
  "hooks":          [{"type": "...", "data": {...}}],
  "_trace":         {"turn_id": "a1b2c3d4", "total_elapsed_ms": 1234.5, "agents": [...]}
}
```

| next_action | UI 의미 | 버튼 예시 |
|-------------|---------|-----------|
| `ASK` | 자유 텍스트 입력 대기 | 없음 |
| `CONFIRM` | 예/아니오 확인 | `["확인", "취소"]` |
| `ASK_CONTINUE` | 계속/중단 선택 | `["계속 진행", "취소"]` |
| `DONE` | 플로우 종료 | 없음 |

### 한 턴의 전형적 이벤트 흐름

```
AGENT_START  {agent:"intent", label:"의도 파악 중"}
AGENT_DONE   {agent:"intent", result:"TRANSFER", success:true}
AGENT_START  {agent:"slot",   label:"정보 추출 중"}
AGENT_DONE   {agent:"slot",   success:true, stage:"FILLING"}
AGENT_START  {agent:"interaction", label:"응답 생성 중"}
LLM_TOKEN    "누"
LLM_TOKEN    "구"
LLM_TOKEN    "에게"
...
LLM_DONE     {action:"ASK", message:"누구에게 얼마를 보내드릴까요?"}
AGENT_DONE   {agent:"interaction", success:true}
DONE         {message:"...", next_action:"ASK", state_snapshot:{stage:"FILLING",...}}
```

### 프론트 통합 예시 (React EventSource)

```javascript
const source = new EventSource(
  `/v1/agent/chat/stream?session_id=${sessionId}&message=${encodeURIComponent(text)}`
);

source.addEventListener("AGENT_START", (e) => {
  const { agent, label } = JSON.parse(e.data);
  setAgentStatus({ agent, label, running: true });
});

source.addEventListener("LLM_TOKEN", (e) => {
  setStreamingText(prev => prev + JSON.parse(e.data));
});

source.addEventListener("DONE", (e) => {
  const { message, next_action, ui_hint, state_snapshot } = JSON.parse(e.data);
  setMessages(prev => [...prev, { role: "assistant", content: message }]);
  setButtons(ui_hint.buttons || []);
  setCurrentState(state_snapshot);
  source.close();
});
```

**POST + fetch 스트리밍**

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
  parseSSEChunk(decoder.decode(value));
}
```

**next_action으로 UI 동작 결정**

```javascript
switch (next_action) {
  case "CONFIRM":   showConfirmDialog(message, ui_hint.buttons); break;
  case "ASK_CONTINUE": showContinueDialog(message, ui_hint.buttons); break;
  case "DONE":      showCompletionMessage(message); resetSession(); break;
  default:          enableTextInput(); // ASK
}
```

---

## 8. 메모리 시스템

### raw_history + summary_text

```
memory (dict):
  raw_history:   [{role, content}, ...]   # 최근 대화 원문
  summary_text:  "..."                    # LLM이 생성한 이전 대화 요약
```

### 자동 요약 설정

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `MEMORY_ENABLE_SUMMARY` | `true` | LLM 자동 요약 활성화 |
| `MEMORY_SUMMARIZE_THRESHOLD` | `6` | 요약 트리거 턴 수 |
| `MEMORY_KEEP_RECENT_TURNS` | `4` | 요약 후 유지할 최근 턴 수 |
| `MEMORY_SUMMARY_MODEL` | `gpt-4o-mini` | 요약 전용 LLM (저렴한 모델 권장) |

요약 흐름:
```
raw_history 턴 수 >= MEMORY_SUMMARIZE_THRESHOLD
  -> 오래된 턴 -> LLM 요약 -> summary_text 누적
  -> raw_history = 최근 MEMORY_KEEP_RECENT_TURNS 턴만 유지
```

### 세션 리셋과 메모리 관계

- `summary_text`는 세션/플로우 리셋 후에도 유지 -> 장기 맥락 보존
- `_reset_session()`에서 state만 초기화. memory(summary_text, raw_history)는 건드리지 않는다

커스텀 요약 프롬프트는 manifest에서 주입:
```python
ManifestBuilder(...).memory(
    summary_system_prompt="도메인 특화 요약 지침...",
    summary_user_template="요약 형식... {memory_block} ... {dialog} ...",
)
```

---

## 9. 운영 & 디버깅

### TurnTracer (_trace)

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

Orchestrator가 턴 시작 시 `TurnTracer`를 생성해 `ExecutionContext.tracer`에 주입.
AgentRunner가 매 에이전트 실행마다 자동으로 `tracer.record()`를 호출.

### CompletedStore (완료 이력)

```python
# Handler 터미널 처리에서 저장
if self.completed:
    self.completed.add(ctx.session_id, ctx.state, ctx.memory)

# API로 조회
# GET /v1/agent/completed?session_id=user-001
```

### Debug API

```
GET /v1/agent/debug/{session_id}
```

DEV_MODE=true일 때만 활성화. state, memory, completed 스냅샷 반환.

### 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_API_KEY` | - | OpenAI API 키 |
| `ANTHROPIC_API_KEY` | - | Anthropic API 키 |
| `DEV_MODE` | `true` | Debug 엔드포인트 활성화 |
| `MEMORY_ENABLE_SUMMARY` | `true` | LLM 자동 요약 활성화 |
| `MEMORY_SUMMARIZE_THRESHOLD` | `6` | 요약 트리거 턴 수 |
| `MEMORY_KEEP_RECENT_TURNS` | `4` | 요약 후 유지할 최근 턴 수 |
| `MEMORY_SUMMARY_MODEL` | `gpt-4o-mini` | 요약 전용 LLM |
| `MAX_FILL_TURNS` | `5` | 슬롯 채우기 최대 시도 횟수 |

---

## 10. 절대 규칙 & 흔한 실수

### 8가지 절대 규칙

1. **`app/core/`에 프로젝트 로직 금지.** 공통 패턴만.
2. **Agent는 `context.build_messages()`를 사용한다.** `user_message`를 수동으로 붙이지 않는다 (이미 자동 추가됨).
3. **DONE 이벤트에는 반드시 `state_snapshot`을 포함한다.**
4. **`_update_memory(ctx, message)`는 DONE yield 직전에 호출한다.**
5. **`on_error`는 `lambda e: make_error_event(e)` 패턴.** 예외를 반드시 전달.
6. **세션 리셋 시 `memory`는 건드리지 않는다.** `state`만 초기화.
7. **사용자 노출 문구는 `messages.py`에 분리한다.** handler에 문자열 하드코딩 금지.
8. **`EventType` enum을 사용한다.** `"LLM_DONE"` 같은 문자열 리터럴 사용 금지.

### 10가지 흔한 실수

| # | 실수 | 올바른 방법 |
|---|------|------------|
| 1 | `build_messages()` 후 `user_message`를 또 추가 | `build_messages()`가 자동으로 마지막에 추가. 수동 추가하면 중복 |
| 2 | `on_error`에서 `make_error_event()` (인자 없음) | `make_error_event(e)` — 예외 `e`를 전달해야 에러 분류 동작 |
| 3 | `_reset_session()`에서 memory 초기화 | state만 초기화. memory는 세션 리셋 후에도 유지 |
| 4 | DONE 이벤트에 `state_snapshot` 누락 | `_yield_done()` 헬퍼 또는 `ctx.state.model_dump()` 패턴 |
| 5 | confirm 연산을 INIT/FILLING에서 허용 | `state_manager._apply_op()`: READY 단계에서만 CONFIRMED 전환 (코드 강제) |
| 6 | 배치 처리 중 다건 재감지 | `if delta.get("tasks") and stage in (INIT, FILLING)` 조건 필수 |
| 7 | `"LLM_DONE"` 문자열 리터럴 사용 | `EventType.LLM_DONE` enum 사용 |
| 8 | Agent에서 state 직접 수정 | Agent는 context를 읽기만. 상태 변경은 Handler에서 StateManager.apply()로 |
| 9 | handler에 사용자 메시지 하드코딩 | `messages.py`에 상수로 분리 |
| 10 | IntentAgent가 FILLING/READY 단계에서도 실행 | `is_mid_flow` 조건으로 스킵. 오탐 방지 |

---

## 11. 멀티 서비스 확장

### SuperOrchestrator

`main.py`에서 CoreOrchestrator를 SuperOrchestrator로 교체하면 된다. 기존 API 라우터 코드 변경 없음.

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
            "card":     ["카드", "신청", "발급"],
        },
        default="transfer",
    ),
)
agent_router = create_agent_router(orchestrator)  # 기존 코드 그대로
```

### A2AServiceProxy

서비스를 별도 프로세스/서버로 분리하고 SSE로 프록시:

```python
# 외부 서비스가 동일한 /v1/agent/chat/stream 인터페이스를 제공하면
A2AServiceProxy("http://card-svc/v1/agent")
```

`CoreOrchestrator`, `A2AServiceProxy`, `SuperOrchestrator` 모두 동일한 `handle_stream()` 인터페이스.
`create_agent_router`에 어떤 것을 넣어도 동일하게 동작 (교체 투명).

### KeywordServiceRouter

```python
KeywordServiceRouter(
    rules={"transfer": ["이체", "송금"]},
    default="transfer",
)
```

키워드 기반으로 서비스 라우팅. 커스텀 라우터는 `BaseServiceRouter`를 상속해서 구현.

---

## 12. 참고: transfer 서비스 상세

### 전체 파이프라인 다이어그램

```
사용자 메시지
      |
      v
+-------------------+
|  READY 단계?      |--- YES --> is_confirm() / is_cancel()  <- LLM 없음
+--------+----------+                    |
         | NO                            v
         v                    delta = confirm / cancel / []
+-------------------+
| SlotFillerAgent   |  <- 오늘 날짜 주입
|  (LLM 호출)       |
+--------+----------+
         | delta = {operations, tasks?, _meta?}
         v
+-----------------------------------------------+
|  TransferStateManager.apply(delta)            |
|  - 슬롯 set/clear/confirm/cancel 처리         |
|  - 슬롯 검증 -> slot_errors 기록              |
|  - parse_error -> slot_errors._unclear        |
|  - FILLING 횟수 초과 -> UNSUPPORTED           |
|  - 단계 전이: INIT->FILLING->READY->CONFIRMED |
+--------+--------------------------------------+
         | stage?
    +----+-------+----------+-----------+
    v            v          v           v
UNSUPPORTED  CONFIRMED   READY     FILLING/INIT
안내 + 리셋  Execute    확인 메시지  InteractionAgent
             실행       (코드 생성)  (slot_errors 인지)
```

### 상태 전이 (Stage)

```
INIT --> FILLING --> READY --> CONFIRMED --> EXECUTED
  |         |                     |            |
  |         +--> CANCELLED        +--> FAILED  |
  |         +--> UNSUPPORTED                   |
  +--------------------------------------------+
                 (세션 리셋 후 INIT으로)
```

| Stage | 설명 |
|-------|------|
| `INIT` | 초기 상태. 슬롯이 하나도 채워지지 않음 |
| `FILLING` | 슬롯 수집 중 |
| `READY` | 필수 슬롯 모두 채움. 확인/취소 대기 |
| `CONFIRMED` | 사용자 확인 완료. 실행 대기 |
| `EXECUTED` | 실행 성공 (터미널) |
| `FAILED` | 실행 실패 (터미널) |
| `CANCELLED` | 사용자 취소 (터미널) |
| `UNSUPPORTED` | FILLING 턴 수 초과 (터미널) |

터미널 스테이지(EXECUTED/FAILED/CANCELLED/UNSUPPORTED)에서 `ctx.state = TransferState()`로 슬롯 초기화.

### 에러 처리 분기

**READY 단계 (LLM 호출 없음)**:
- `is_confirm()` -> `{"operations": [{"op": "confirm"}]}` -> CONFIRMED
- `is_cancel()` -> `{"operations": [{"op": "cancel_flow"}]}` -> CANCELLED
- 불명확 입력 -> `{"operations": []}` -> READY 유지 (안전 기본값)

**UNSUPPORTED (턴 수 초과)**:
- `filling_turns > MAX_FILL_TURNS` -> 고정 메시지 반환 -> 슬롯 초기화

**Execute 실패**:
- Execute Agent 예외 -> `stage = FAILED` -> 터미널 처리 -> 슬롯 초기화

### 배치 다건 처리 흐름

```
턴1: "홍길동에게 5만원, 엄마에게 3만원"
     SlotFiller -> tasks: [{target:"홍길동", amount:50000}, {target:"엄마", amount:30000}]
     Handler -> tasks[0] = 현재 슬롯, tasks[1:] = task_queue
     -> READY: "홍길동에게 5만원 보낼까요? (1/2)"

턴2: "확인"
     -> CONFIRMED -> Execute -> EXECUTED
     -> task_queue에서 다음 꺼냄 -> state 리셋 + 새 슬롯
     -> READY: "완료! 다음으로 엄마에게 3만원 보낼까요? (2/2)"

턴3: "확인"
     -> CONFIRMED -> Execute -> EXECUTED
     -> task_queue 비어있음 -> 최종 완료
```

### 실제 시나리오 요약

| 시나리오 | Flow | 턴 수 | 터미널 | 슬롯 초기화 |
|----------|------|-------|--------|-------------|
| 일반 대화 | DEFAULT_FLOW | 1 | - | 해당 없음 |
| 이체 성공 | TRANSFER_FLOW | 멀티 (4턴 예시) | EXECUTED | O |
| 이체 취소 | TRANSFER_FLOW | 2턴 예시 | CANCELLED | O |
| 실행 실패 | TRANSFER_FLOW | 멀티 | FAILED | O |
| 입력 반복 초과 | TRANSFER_FLOW | 11+ | UNSUPPORTED | O |

### LLM vs 코드 제어 경계

| LLM이 결정 | 코드가 결정 |
|------------|-------------|
| 인텐트 분류 (TRANSFER/GENERAL) | 상태 전이 조건 |
| 슬롯 추출 (자연어 -> 구조화) | 슬롯 유효성 검증 (StateManager) |
| 자연어 응답 생성 (FILLING/INIT) | READY 단계 확인/취소 (`logic.py`) |
| 대화 요약 | 명시적 취소 키워드 감지 (`logic.py`) |
| - | confirm 유효성 (READY -> CONFIRMED만 허용) |
| - | 터미널 메시지, 세션 리셋 (`messages.py`) |

> **LLM으로 해결하려는 것 중 명확한 분기 조건이 있으면 코드로 먼저 처리한다.**

---

## 확장 포인트 한눈에 보기

| 확장 목표 | 수정 위치 |
|----------|-----------|
| 새 Agent 추가 | `agents/<name>/` + `project.yaml` + `manifest._AGENT_CLASS_MAP` |
| 새 Tool 추가 | `core/tools/` 구현 + `TOOL_REGISTRY` 등록 + `card.json tools` 배열 |
| 새 Flow 시나리오 | IntentAgent prompt + router SCENARIO_TO_FLOW + 새 FlowHandler |
| 새 서비스 | `projects/minimal` 복사 + `main.py` 등록 |
| 멀티 서비스 | `main.py` -> `SuperOrchestrator` 전환 |
| 외부 서비스 연동 | `A2AServiceProxy` 사용 |
| 세션 영속화 | `InMemorySessionStore` -> Redis/DB 기반으로 교체 |
| RAG/검색 | `BaseAgent(retriever=...)` 주입 -> `retriever.search(query)` -> LLM 컨텍스트 추가 |
| 커스텀 요약 프롬프트 | `ManifestBuilder.memory(summary_system_prompt=..., summary_user_template=...)` |
| 프로젝트 전환 | `main.py`에서 `load_manifest` import 대상만 변경 |
