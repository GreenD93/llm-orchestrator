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
    ├─ IntentAgent   → scenario 분류 (선택)
    ├─ FlowRouter    → flow_key 결정
    └─ FlowHandler   → 에이전트들 실행 → SSE 이벤트 yield
```

### 구성 요소 역할

| 구성요소 | 역할 | 위치 |
|----------|------|------|
| `CoreOrchestrator` | 요청 수신·세션 관리·에러 핸들링 | `core/orchestration/orchestrator.py` |
| `ExecutionContext` | 에이전트가 읽는 유일한 입력 (state, memory, user_message) | `core/context.py` |
| `BaseAgent` | LLM 호출 단위. `run()` 또는 `run_stream()` 구현 | 각 프로젝트 `agents/` |
| `AgentRunner` | Agent를 이름으로 실행. FlowHandler에서 `self.runner.run("slot", ctx)` | `core/orchestration/` |
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
| 인텐트 분류 | 상태 전이 조건 |
| 슬롯 추출 | 입력값 유효성 검증 |
| 자연어 응답 (FILLING/INIT) | 터미널·확인 메시지 (`messages.py`) |
| 대화 요약 | 세션 리셋·메모리 유지 |

---

## 절대 규칙

1. **`app/core/`에 프로젝트 로직 금지.** 공통 패턴만.

2. **Agent는 `context.build_messages()`를 사용한다.**
   `user_message`를 수동으로 붙이지 않는다. 이미 자동으로 추가된다.

3. **DONE 이벤트에는 반드시 `state_snapshot`을 포함한다.**

4. **`update_memory_and_save()`는 DONE yield 직전에 호출한다.**

5. **`on_error`는 `lambda e: make_error_event()` 패턴.** (`core/orchestration/defaults.py`)

6. **세션 리셋 시 `memory`는 건드리지 않는다.** `state`만 초기화.

7. **사용자 노출 문구는 `messages.py`에 분리한다.** handler에 문자열 하드코딩 금지.

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

## 에이전트 구현 패턴

### 단순 호출 (run)
```python
def run(self, context: ExecutionContext, **kwargs) -> dict:
    messages = context.build_messages(f"현재 상태: {context.state.model_dump()}")
    raw = self.chat(messages)
    return self._parse(raw)
```

### 스트리밍 (run_stream)
```python
def run_stream(self, context: ExecutionContext, **kwargs):
    messages = context.build_messages()
    buffer = ""
    for token in self.chat_stream(messages):
        buffer += token
        yield {"event": EventType.LLM_TOKEN, "payload": token}
    yield {"event": EventType.LLM_DONE, "payload": self._parse(buffer)}
```

---

## 버전 이력

| 버전 | 내용 |
|------|------|
| v1.1.0 | `build_messages()` 표준화, core 공통화, minimal 템플릿, 문서 정비 |
| v1.0.0 | 초기 구조: CoreOrchestrator, Agent/Runner/Handler, 배치 큐, 자동 요약 |
