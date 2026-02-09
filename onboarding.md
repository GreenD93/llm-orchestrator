# AI 오케스트레이터 개발자 온보딩 가이드

이 문서는 **LLM 오케스트레이터** 템플릿을 바탕으로 코드를 팔로업하고 수정할 수 있도록 안내합니다.  
새 Agent 추가, 오케스트레이터/Executor 활용, 시나리오 이해, MCP·Tools·외부 지식 확장, API 사용법까지 한 번에 따라 할 수 있습니다.

---

## 1. 프로젝트를 어떻게 따라가면 되나요?

### 1.1 한 턴이 돌아가는 순서 (진입점 → 흐름)

1. **API**  
   `POST /v1/agent/chat` 또는 `POST /v1/agent/chat/stream` 요청이 들어옵니다.

2. **main.py**  
   `load_manifest()`로 프로젝트 설정을 읽고, `CoreOrchestrator(manifest)`로 오케스트레이터를 만든 뒤, `create_agent_router(orchestrator)`로 라우터를 붙입니다.  
   → **프로젝트를 바꿀 때는 여기서 import만 바꾸면 됩니다.**

   ```python
   # app/main.py
   from app.projects.transfer.manifest import load_manifest
   # from app.projects.minimal.manifest import load_manifest
   manifest = load_manifest()
   orchestrator = CoreOrchestrator(manifest)
   ```

3. **CoreOrchestrator** (`app/core/orchestration/orchestrator.py`)  
   - `run_one_turn(session_id, user_message)`가 **한 턴**을 책임집니다.
   - 세션 로드 → (선택) Intent Agent 실행 → **FlowRouter**로 flow 키 결정 → **FlowHandler.run(ctx)** 실행 → 세션 저장 및 **after_turn** 훅 호출.

4. **FlowRouter** (`app/core/orchestration/flow_router.py` + 프로젝트 `flows/router.py`)  
   - `route(intent=..., state=...)` → `"DEFAULT_FLOW"`, `"TRANSFER_FLOW"` 같은 **문자열**을 반환합니다.
   - 조건문만 사용하며, 별도 Flow 클래스/라이프사이클은 없습니다.

5. **FlowHandler** (`app/core/orchestration/flow_handler.py` + 프로젝트 `flows/handlers.py`)  
   - 선택된 flow에 맞는 Handler가 **Agent 실행 순서**를 정의합니다.
   - 실제 LLM 호출은 **AgentRunner**를 통해 `runner.run(agent_name, ctx)` 또는 `runner.run_stream(agent_name, ctx)`로만 수행합니다.

6. **AgentRunner** (`app/core/agents/agent_runner.py`)  
   - 이름 → Agent 인스턴스 매핑, 재시도/검증/타임아웃 정책을 적용한 뒤  
   - `agent.run(context)` 또는 `agent.run_stream(context)`를 호출합니다.

7. **Agent** (`app/core/agents/base_agent.py` + `projects/<프로젝트>/agents/...`)  
   - `run(context)` / `run_stream(context)`에서 **계산만** 담당합니다.  
   - 상태 관측, 훅, 이벤트는 Orchestrator/Handler 쪽 책임입니다.

**정리**:  
`main.py` → `CoreOrchestrator.run_one_turn` → `FlowRouter.route` → `FlowHandler.run` → `AgentRunner.run` / `run_stream` → 각 **Agent.run** / **Agent.run_stream**.  
이 순서대로 파일을 열어보면 한 턴의 코드 경로를 끝까지 따라갈 수 있습니다.

---

## 2. 새 Agent를 만들 때 어디를 수정하면 되나요?

새 Agent를 추가하려면 **아래 4곳**을 맞추면 됩니다.

### 2.1 Agent 클래스 + 프롬프트 (필수)

- **위치**: `app/projects/<프로젝트>/agents/<에이전트_이름>/`
- **파일**:
  - `agent.py`: `BaseAgent` 상속, `run(context)` (필요 시 `run_stream`) 구현.
  - `prompt.py`: `get_system_prompt()` 등 시스템 프롬프트 제공 (card에서 참조 가능).

**예: IntentAgent (비스트리밍, dict 반환)**

`run(context)`에서 사용자 메시지만으로 LLM을 호출하고, 의도 분류 결과를 `dict`로 반환합니다. 상태는 건드리지 않습니다.

```python
# app/projects/transfer/agents/intent_agent/agent.py
from app.core.agents.base_agent import BaseAgent
from app.core.agents.agent_runner import RetryableError
from app.core.context import ExecutionContext
from app.projects.transfer.agents.intent_agent.prompt import get_system_prompt

class IntentAgent(BaseAgent):
    output_schema = "IntentResult"   # Runner가 schema_registry로 검증할 때 사용

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        raw = self.chat([{"role": "user", "content": context.user_message}])
        value = raw.strip().upper()
        if value not in ("TRANSFER", "OTHER"):
            raise RetryableError(f"invalid_intent_output: {raw}")
        supported = value == "TRANSFER"
        return {"intent": value, "supported": supported, "reason": None}
```

**예: SlotFillerAgent (연산만 반환, 상태 적용은 Handler/StateManager)**

사용자 발화에서 슬롯 연산(operations)만 추출해 JSON으로 반환합니다. `ctx.state`를 수정하지 않고, Handler에서 `state_manager.apply(delta)`로 반영합니다.

```python
# app/projects/transfer/agents/slot_filler_agent/agent.py (요지)
def run(self, context: ExecutionContext, **kwargs) -> dict:
    raw = self.chat([{"role": "user", "content": context.user_message}]).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"operations": [], "_meta": {"parse_error": True}}
```

**예: 스트리밍 Agent (InteractionAgent)**

`supports_stream = True`를 두고, `run_stream(context)`에서 토큰 단위로 이벤트를 보낸 뒤 마지막에 `LLM_DONE`으로 전체 파싱 결과를 넘깁니다.

```python
# app/projects/transfer/agents/interaction_agent/agent.py (요지)
class InteractionAgent(BaseAgent):
    supports_stream = True

    def run_stream(self, context: ExecutionContext, **kwargs):
        history = context.get_history()
        summary_text = context.memory.get("summary_text", "")
        buffer = ""
        for token in self.chat_stream(self._messages(context.state, history, summary_text)):
            buffer += token
            yield {"event": EventType.LLM_TOKEN, "payload": token}
        yield {"event": EventType.LLM_DONE, "payload": self._parse(buffer)}
```

Agent는 **상태를 직접 바꾸지 말고**, `context`(state, memory, metadata)를 읽기만 하고, **반환값**으로만 결과를 전달하는 것이 원칙입니다. 상태 적용은 Handler에서 합니다.

### 2.2 Card (선택, 권장)

- **위치**: `app/projects/<프로젝트>/agents/<에이전트_이름>/card.json`
- **역할**: LLM 설정(`model`, `temperature`, `timeout_sec`), 재시도/검증 정책(`max_retry`, `validate`, `schema` 등)을 정의합니다.
- **manifest**에서 이 card를 읽어 `build_runner()`에 넘기므로, 새 Agent를 추가할 때 card도 함께 두면 Runner 정책을 카드만으로 조정하기 쉽습니다.

**예: Intent Agent 카드**

```json
{
  "name": "IntentAgent",
  "role": "intent_classifier",
  "description": "사용자 발화의 의도 분류",
  "llm": {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "temperature": 0
  },
  "policy": {
    "max_retry": 2,
    "backoff_sec": 1,
    "timeout_sec": 6,
    "validate": "intent_enum",
    "schema": "IntentResult"
  }
}
```

- `policy.validate`: manifest의 `validator_map` 키와 매칭되어 Runner가 검증 시 사용합니다.
- `policy.schema`: manifest의 `schema_registry` 키와 매칭되어 Pydantic으로 파싱 후 반환할 수 있습니다.

### 2.3 project.yaml + manifest

- **project.yaml**  
  - `agents` 아래에 새 키(예: `my_agent`)와 `class`, `card`, `stream`(스트리밍 시 true)를 추가합니다.

**예: project.yaml (transfer)**

```yaml
name: transfer

agents:
  intent:
    class: IntentAgent
    card: agents/intent_agent/card.json

  slot:
    class: SlotFillerAgent
    card: agents/slot_filler_agent/card.json

  interaction:
    class: InteractionAgent
    card: agents/interaction_agent/card.json
    stream: true

  execute:
    class: TransferExecuteAgent
    card: agents/transfer_execute_agent/card.json

flows:
  router: flows.router.TransferFlowRouter
  handlers:
    DEFAULT_FLOW: flows.handlers.DefaultFlowHandler
    TRANSFER_FLOW: flows.handlers.TransferFlowHandler

state:
  manager: state.state_manager.TransferStateManager
```

- **manifest.py**  
  - `agents_config`를 돌면서 새 Agent의 **클래스 경로**와 **card 경로**를 해석합니다.  
  - transfer는 `agent_module_map`으로 짧은 이름(`IntentAgent` 등)을 풀 경로로 매핑합니다. 새 Agent 추가 시 이 맵에 한 줄 추가하면 됩니다.  
  - 스키마 검증을 쓰려면 `schema_registry`(Pydantic 모델), `validator_map`(함수)에 해당 Agent용 항목을 등록합니다.

**예: manifest에서 Agent 한 개 등록 + Runner 빌드**

```python
# manifest.py 요지
agent_specs[key] = {"class": cls, "card": card, "stream": spec.get("stream", False)}
runner = build_runner(agent_specs, schema_registry=schema_registry, validator_map=validator_map)
```

### 2.4 FlowHandler에서 호출

- **위치**: `app/projects/<프로젝트>/flows/handlers.py`
- **수정**: 해당 flow에서 “이 턴에 이 Agent를 실행한다”는 **순서**에 맞게  
  `self.runner.run("agent_name", ctx)` 또는 `self.runner.run_stream("agent_name", ctx)`를 넣습니다.
- Agent 이름은 **project.yaml의 `agents` 키**와 동일해야 합니다 (예: `intent`, `slot`, `interaction`, `execute`).

**예: TransferFlowHandler에서 Slot → State 적용 → (CONFIRMED면 Execute) → Interaction**

```python
# flows/handlers.py (TransferFlowHandler.run 요지)
def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
    delta = self.runner.run("slot", ctx)
    ctx.state = self.state_manager_factory(ctx.state).apply(delta)

    if ctx.state.stage == Stage.CONFIRMED:
        try:
            self.runner.run("execute", ctx)
            ctx.state.stage = Stage.EXECUTED
        except FatalExecutionError:
            ctx.state.stage = Stage.FAILED
        self.sessions.save_state(ctx.session_id, ctx.state)

    payload = None
    for ev in self.runner.run_stream("interaction", ctx):
        yield ev
        if ev.get("event") == EventType.LLM_DONE:
            payload = ev.get("payload")

    if ctx.state.stage in TERMINAL_STAGES:
        ctx.state = TransferState()   # 슬롯 초기화
        self.sessions.save_state(ctx.session_id, ctx.state)
    yield {"event": EventType.DONE, "payload": _apply_ui_policy(payload or {})}
```

**체크리스트**

| 단계 | 위치 | 내용 |
|------|------|------|
| 1 | `agents/<이름>/agent.py`, `prompt.py` | Agent 클래스 + `run` / `run_stream`, 프롬프트 |
| 2 | `agents/<이름>/card.json` | LLM/정책 설정 (선택) |
| 3 | `project.yaml` | agents에 새 항목 추가 |
| 4 | `manifest.py` | 클래스/카드 해석, 필요 시 schema_registry·validator_map |
| 5 | `flows/handlers.py` | 적절한 flow에서 `runner.run("이름", ctx)` 호출 |

---

## 3. 오케스트레이터와 Executor(AgentRunner)는 어떻게 다루나요?

### 3.1 CoreOrchestrator (오케스트레이터)

- **역할**: “한 턴”만 담당합니다. 멀티턴은 여러 번 `run_one_turn`이 호출되는 것으로 이뤄집니다.
- **하는 일**  
  - 세션/메모리 로드, Context 구성  
  - (manifest에 intent Agent가 있으면) Intent 실행 후 **FlowRouter**로 flow 결정  
  - 해당 **FlowHandler** 한 번 실행  
  - 세션 저장 + **after_turn** 훅 호출
- **수정 포인트**  
  - 턴 단위로 “그 전/그 후”에 하고 싶은 일이 있으면 **manifest**의 `on_error`, `after_turn` 훅을 사용합니다.  
  - 오케스트레이터 코드 자체를 바꿀 필요는 거의 없고, **Router·Handler·Agent**를 바꾸는 것이 일반적입니다.

### 3.2 AgentRunner (Executor 역할)

- **역할**: “이름으로 Agent를 찾아서, 정책(재시도/검증/타임아웃)을 적용한 뒤 run/run_stream 호출”만 합니다.
- **수정 포인트**  
  - **어떤 Agent를 등록할지**: manifest에서 `build_runner(agent_specs, ...)`에 넘기는 `agent_specs` (project.yaml + manifest 해석 결과).  
  - **재시도/검증/타임아웃**: 각 Agent의 **card** `policy`와 manifest의 `validator_map` / `schema_registry`.  
  - 새 Agent를 “실제로 실행”하려면 반드시 **FlowHandler**에서 `runner.run("agent_name", ctx)`를 호출해야 합니다. Runner는 등록만 하고, “언제 누가 부를지”는 Handler가 결정합니다.

정리하면:  
- **오케스트레이터**: 턴 흐름·라우팅·저장·훅.  
- **Runner**: Agent 인스턴스 + 실행 정책 + run/run_stream 호출.  
- **Handler**: “이 flow에서는 이 순서로 이 Agent들을 실행한다”를 코딩하는 곳입니다.

---

## 4. 지금 템플릿으로 가능한 시나리오(멀티턴) — 케이스 개수

템플릿에는 **프로젝트 단위**로 시나리오가 나뉘고, 각 프로젝트는 **flow** 단위로 “케이스”가 나뉩니다.

### 4.1 minimal 프로젝트

- **flow**: 1개 — `DEFAULT_FLOW`만 존재.
- **시나리오**: “매 턴 interaction 한 번 실행 후 DONE” 한 가지.
- **멀티턴**: 가능. 매 요청마다 한 턴씩 실행되고, 세션/메모리는 유지됩니다.

→ **1가지 시나리오(케이스)**.

### 4.2 transfer 프로젝트

- **flow**: 2개 — `DEFAULT_FLOW`, `TRANSFER_FLOW`.
- **시나리오**  
  1. **DEFAULT_FLOW**: 이체가 아니거나 지원하지 않는 경우. Interaction만 실행 후 DONE.  
  2. **TRANSFER_FLOW**: 이체 시나리오. Intent → Slot Filling → State 적용 → (CONFIRMED면 Execute) → Interaction. 터미널 스테이지(EXECUTED, FAILED, CANCELLED, UNSUPPORTED)에서 완료 처리.
- **멀티턴**: 가능. state(stage, slots 등)가 턴마다 갱신되며, READY → CONFIRM → CONFIRMED → Execute 같은 흐름이 여러 턴에 걸쳐 진행됩니다.

→ **2가지 시나리오(케이스)** (DEFAULT_FLOW 1개 + TRANSFER_FLOW 1개).

#### 슬롯 초기화 (반영 여부)

**네, 반영되어 있습니다.** 슬롯필링 테스크가 **완전히 끝난 경우**(터미널 스테이지)에 슬롯과 상태가 초기화됩니다.

- **터미널 스테이지**: `EXECUTED`, `FAILED`, `CANCELLED`, `UNSUPPORTED`
- **처리 위치**: `app/projects/transfer/flows/handlers.py` 의 `TransferFlowHandler.run()` 끝부분

```python
# TransferFlowHandler.run() 중 터미널 처리
if getattr(ctx.state, "stage", None) and ctx.state.stage in TERMINAL_STAGES:
    if self.completed:
        self.completed.add(ctx.session_id, ctx.state, ctx.memory)
    ctx.state = TransferState()   # ← 새 상태로 교체 → slots=Slots() 등 초기값
    self.sessions.save_state(ctx.session_id, ctx.state)
```

`TransferState()`는 `stage=INIT`, `slots=Slots()`(전부 None)로 생성되므로, **다음 대화부터는 빈 슬롯으로 새 이체 플로우**가 시작됩니다.  
`UNSUPPORTED`(멀티턴 초과) 분기에서도 동일하게 `ctx.state = TransferState()` 후 저장합니다.

### 4.3 전체 정리

| 프로젝트 | flow 개수 | 시나리오(케이스) | 멀티턴 |
|----------|-----------|-------------------|--------|
| minimal  | 1         | 1 (일반 대화 1-step) | O |
| transfer | 2         | 2 (일반 대화 / 이체 슬롯필링~실행) | O |

“지금 템플릿으로 가능한 시나리오”는 **minimal 1개 + transfer 2개**로 보면 되고,  
새 flow를 추가하면(새 Handler + Router에서 새 키 반환) **새 시나리오(케이스)**를 계속 늘릴 수 있습니다.

---

## 5. MCP / Tools / Agent 외부 지식은 나중에 어떻게 넣나요?

### 5.1 Tools (Python 함수)

- **위치**: `app/plugins/experimental/tool_registry.py`  
  - 현재는 `TOOL_REGISTRY: Dict[str, Callable]`만 있고, core에서는 참조하지 않습니다.
- **연결 방법**  
  1. `TOOL_REGISTRY`에 이름 → 함수를 등록합니다.  
  2. **BaseAgent**는 `__init__(..., tools=...)`로 `dict[str, Callable]`를 받을 수 있습니다.  
  3. manifest에서 Agent **인스턴스를 만들 때** (또는 Agent 서브클래스에서) 해당 Agent용 tools를 넣어주면 됩니다.  
  - 현재 `build_runner()`는 card만 보고 인스턴스를 만들므로, **tools를 넘기려면** manifest의 Agent 생성 부분을 확장해, 예를 들어 `agents[key] = cls(..., tools=project_tools.get(key, {}))`처럼 주입할 수 있습니다.
- **사용**: Agent의 `run`/`run_stream` 안에서 `self.tools["tool_name"](...)`처럼 호출하면 됩니다.

### 5.2 MCP (Model Context Protocol)

- core에는 MCP 전용 코드가 없습니다.  
- **추가 방식**:  
  - **plugins/experimental**에 MCP 클라이언트/어댅터를 두고,  
  - Agent에 “도구처럼” 주입하거나,  
  - Handler/Context에서 MCP로부터 받은 결과를 `context.metadata` 또는 별도 필드로 넣어서 Agent에 전달하는 방식으로 확장할 수 있습니다.  
  - 즉, “외부 도구/리소스”를 **함수 또는 context 데이터**로 Agent에게 넘기는 형태로 통합하면 됩니다.

### 5.3 외부 지식 (RAG / Retriever)

- **BaseAgent**는 `__init__(..., retriever=...)`로 `search(query)` 호출 가능한 객체를 받을 수 있습니다.
- **프로젝트 예시**: `app/projects/transfer/knowledge/retriever.py`  
  - `Retriever` 클래스에 `search(query) -> List`를 구현해 두었고, 현재는 빈 리스트를 반환합니다.  
  - 여기에 실제 검색(파일, 벡터 DB 등)을 구현한 뒤, manifest에서 해당 Agent를 만들 때 `retriever=retriever_instance`를 넘기면 됩니다.
- **사용**: Agent의 `run` 안에서 `self.retriever.search(context.user_message)` 등으로 문서를 가져와, 프롬프트에 넣어 LLM에 전달하면 됩니다.
- **연결**: `build_runner()`를 확장해, 특정 Agent 이름에 대해 `retriever` 인스턴스를 만들어 `cls(..., retriever=...)`로 넘기면 됩니다.

**요약**

| 확장 | 위치 | 연결 방법 |
|------|------|-----------|
| Tools | `plugins/experimental/tool_registry.py` + Agent `tools` | manifest/runner 빌드 시 Agent에 `tools=...` 주입 |
| MCP | plugins에 구현 후 | Agent 또는 Context를 통해 “도구/데이터”로 주입 |
| 외부 지식 (RAG) | `projects/.../knowledge/retriever.py` 등 | `Retriever` 구현 후 manifest/runner에서 Agent에 `retriever=...` 주입 |

---

## 6. 사용법 요약

### 6.1 실행

```bash
pip install -r requirements.txt
# OPENAI_API_KEY 등 환경 변수 설정
uvicorn app.main:app --reload
```

### 6.2 API

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/v1/agent/chat` | 비스트리밍. `session_id`, `message` → 턴 1회 실행 후 `OrchestrateResponse` (interaction, hooks). |
| POST / GET | `/v1/agent/chat/stream` | 스트리밍 SSE. 동일 입력으로 턴 1회 실행, 이벤트: `LLM_TOKEN`, `LLM_DONE`, `DONE`. |
| GET | `/v1/agent/completed` | `session_id` 쿼리. 해당 세션의 완료 이력 (transfer에서 완료 저장 시). |

**요청 body (POST /chat, POST /chat/stream 공통)**

```json
{
  "session_id": "user-001",
  "message": "김철수한테 5만원 이체해줘"
}
```

**비스트리밍 응답 (POST /chat)**  
한 턴이 끝난 뒤 `OrchestrateResponse` 한 번 반환됩니다.

```json
{
  "interaction": {
    "message": "김철수에게 50,000원 이체할까요? 확인해 주세요.",
    "next_action": "CONFIRM",
    "action": "CONFIRM",
    "ui_hint": { "buttons": ["확인", "취소"] }
  },
  "hooks": []
}
```

**스트리밍 응답 (POST /chat/stream, SSE)**  
이벤트 스트림으로 `LLM_TOKEN`(토큰 문자열) → `LLM_DONE`(전체 payload) → `DONE`(최종 payload) 순서로 옵니다.

```
event: LLM_TOKEN
data: {"payload": "김"}

event: LLM_TOKEN
data: {"payload": "철수"}

event: LLM_DONE
data: {"message": "김철수에게 50,000원 이체할까요?", "action": "CONFIRM", ...}

event: DONE
data: {"message": "...", "next_action": "CONFIRM", "ui_hint": {"buttons": ["확인", "취소"]}}
```

**완료 이력 (GET /completed)**  
transfer에서 터미널 스테이지일 때 `completed.add(...)`로 저장한 이력을 조회합니다.

```
GET /v1/agent/completed?session_id=user-001
→ { "session_id": "user-001", "completed": [ ... ] }
```

### 6.3 테스트

```bash
# Flow 단위 테스트 (mock runner)
pytest app/projects/transfer/tests/test_flow.py app/projects/minimal/tests/test_flow.py -v

# API 스키마·엔드포인트 검증
pytest app/projects/transfer/tests/test_api.py -v
```

---

## 7. 빠른 참조: 수정 포인트 맵

| 하고 싶은 일 | 수정할 곳 |
|--------------|-----------|
| 새 Agent 추가 | `agents/<이름>/agent.py`, `prompt.py`, `agents/<이름>/card.json`, `project.yaml`, `manifest.py`, `flows/handlers.py` |
| flow 추가 (새 시나리오) | `flows/router.py` (route 반환값), `flows/handlers.py` (새 Handler 클래스), `project.yaml` (flows.handlers에 등록), `manifest.py` (이미 handlers 로딩하면 추가만) |
| 턴 끝 처리 (메모리/요약 등) | manifest의 `after_turn` 훅 |
| 에러 시 공통 응답 | manifest의 `on_error` 훅 |
| Agent 재시도/검증/타임아웃 | 해당 Agent의 card `policy` + manifest의 `validator_map` / `schema_registry` |
| Tools 사용 | `plugins/experimental/tool_registry.py` + manifest/runner에서 Agent에 `tools` 주입 |
| 외부 지식 (RAG) | `knowledge/retriever.py` 구현 + manifest/runner에서 Agent에 `retriever` 주입 |
| 프로젝트 전환 | `main.py`에서 `load_manifest` import 대상만 변경 |

---

## 8. 실제 시나리오 예시 (사용자 요청 → 실행 액션 → 응답)

아래는 **transfer** 프로젝트 기준으로, API에 `session_id` + `message`를 보냈을 때 턴마다 어떤 flow/Agent가 돌고 어떤 응답이 나오는지 요청·실행·응답 형태로 정리한 예시입니다.

---

### 시나리오 1: 일반 대화 (DEFAULT_FLOW, 1턴)

**의도**: 이체가 아닌 말 → Intent `OTHER` → Router가 `DEFAULT_FLOW` 선택 → Interaction만 실행 후 종료.

| 구분 | 내용 |
|------|------|
| **사용자 요청** | `POST /v1/agent/chat` body: `{"session_id": "s1", "message": "오늘 날씨 어때?"}` |
| **실행 액션** | 1) Intent Agent → `intent: "OTHER"` 2) Router → `DEFAULT_FLOW` 3) DefaultFlowHandler: `run_stream("interaction", ctx)` → 메모리 갱신 4) DONE |
| **응답** | `interaction.message`에 날씨 관련 안내 문구, `next_action: "DONE"`, `ui_hint: {}` |

```
요청: "오늘 날씨 어때?"
→ [Intent: OTHER] → [DEFAULT_FLOW] → [Interaction] → 응답: "날씨 정보는 ..." / DONE
```

---

### 시나리오 2: 이체 성공 (TRANSFER_FLOW, 멀티턴)

**의도**: 이체 의도로 시작 → 슬롯 채우기(멀티턴) → 확인 → 실행 → 터미널(EXECUTED) → **슬롯 초기화** 후 다음 턴부터 새 이체 가능.

- **턴1**: 이체 의도 + 수신인/금액 없음 → “누구에게?” 등으로 슬롯 요청  
- **턴2**: 수신인만 채움 → “얼마를?”  
- **턴3**: 금액 채움 → READY → “확인해주세요” (CONFIRM)  
- **턴4**: 사용자 “확인” → CONFIRMED → Execute Agent 실행 → EXECUTED → 완료 메시지 + **state = TransferState()** 로 초기화

| 턴 | 사용자 요청 | 실행 액션 (요지) | 응답 (요지) |
|----|-------------|------------------|-------------|
| 1 | "이체해줘" | Intent→TRANSFER, Router→TRANSFER_FLOW, Slot(빈 operations 가능), State(FILLING), Interaction | "누구에게 이체할까요?" / ASK |
| 2 | "김철수한테" | Slot→target set, State 적용, Interaction | "얼마를 이체할까요?" / ASK |
| 3 | "5만원" | Slot→amount set, State→READY, Interaction | "김철수에게 50,000원 이체할까요?" / CONFIRM, 버튼 [확인][취소] |
| 4 | "확인" | Slot→confirm, State→CONFIRMED, Execute 실행, State→EXECUTED, Interaction, **TERMINAL → ctx.state=TransferState()** | "이체가 완료되었습니다." / DONE |

```
턴1: "이체해줘"           → [Intent: TRANSFER] → [TRANSFER_FLOW] → Slot → Interaction → "누구에게?"
턴2: "김철수한테"         → [TRANSFER_FLOW] → Slot(target) → Interaction → "얼마를?"
턴3: "5만원"              → Slot(amount) → READY → Interaction → "확인할까요?" [확인][취소]
턴4: "확인"               → confirm → Execute → EXECUTED → Interaction → "이체 완료" → 슬롯 초기화
```

---

### 시나리오 3: 이체 취소 (TRANSFER_FLOW → CANCELLED → 슬롯 초기화)

**의도**: 이체 진행 중 사용자가 취소 → Slot Agent가 `cancel_flow` op 반환 → StateManager가 stage를 CANCELLED로 변경 → Handler에서 터미널 처리 후 **슬롯 초기화**.

| 턴 | 사용자 요청 | 실행 액션 (요지) | 응답 (요지) |
|----|-------------|------------------|-------------|
| 1 | "이체할게" | TRANSFER_FLOW, Slot, Interaction | "누구에게 이체할까요?" / ASK |
| 2 | "취소할게" / "그만" | Slot → operations: `[{ "op": "cancel_flow" }]`, State → CANCELLED, Interaction | 취소 안내 메시지 / DONE |
| (Handler) | - | `stage in TERMINAL_STAGES` → `ctx.state = TransferState()` | 다음 턴부터 빈 슬롯으로 새 이체 가능 |

```
턴1: "이체할게"     → TRANSFER_FLOW → "누구에게?"
턴2: "취소할게"     → Slot(cancel_flow) → CANCELLED → "취소되었습니다." → 슬롯 초기화
```

---

### 시나리오 4: 이체 실행 실패 또는 UNSUPPORTED

**케이스 A – Execute 실패 (FAILED)**  
확인 후 Execute Agent가 예외를 던지면 Handler에서 `ctx.state.stage = Stage.FAILED`로 설정. 터미널이므로 Handler 끝에서 `ctx.state = TransferState()`로 **슬롯 초기화** 후 저장.

| 턴 | 사용자 요청 | 실행 액션 | 응답 |
|----|-------------|-----------|------|
| N | "확인" | CONFIRMED → Execute 실행 → 예외 → stage=FAILED, TERMINAL → state 초기화 | 실패 안내 메시지 / DONE |

**케이스 B – UNSUPPORTED (슬롯 채우기 턴 수 초과)**  
`filling_turns > MAX_FILL_TURNS`(예: 10)가 되면 StateManager가 `stage = UNSUPPORTED`로 설정. Handler의 UNSUPPORTED 분기에서 고정 메시지 반환 후 `ctx.state = TransferState()`로 **슬롯 초기화**하고 완료 처리.

| 턴 | 사용자 요청 | 실행 액션 | 응답 |
|----|-------------|-----------|------|
| 11+ | (계속 빈말/혼란 입력) | Slot 적용 후 _transition에서 UNSUPPORTED, Handler에서 고정 메시지 + state 초기화 | "입력이 반복되어 더 이상 진행할 수 없어요. 처음부터 다시 시도해 주세요." / DONE |

---

### 시나리오 요약 표

| 시나리오 | Flow | 턴 수 | 터미널 스테이지 | 슬롯 초기화 |
|----------|------|-------|-----------------|-------------|
| 1. 일반 대화 | DEFAULT_FLOW | 1 | - | (해당 없음) |
| 2. 이체 성공 | TRANSFER_FLOW | 멀티(4턴 예시) | EXECUTED | O (TransferState()로 리셋) |
| 3. 이체 취소 | TRANSFER_FLOW | 2턴 예시 | CANCELLED | O |
| 4a. 이체 실행 실패 | TRANSFER_FLOW | 멀티 | FAILED | O |
| 4b. 입력 반복 초과 | TRANSFER_FLOW | 11+ | UNSUPPORTED | O |

이 가이드만 따라가도 코드 경로를 추적하고, Agent 추가·오케스트레이터/Executor 활용·시나리오 확장·MCP·Tools·외부 지식 추가·API 사용까지 일관되게 할 수 있습니다.
