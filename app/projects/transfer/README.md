# Transfer 서비스 — AI 이체 서비스

이 문서는 `transfer` 프로젝트의 설계·구현 맥락을 기록한다.
프레임워크 공통 개념은 루트의 `CLAUDE.md`, 종합 가이드는 `GUIDE.md` 참조.

---

## 서비스 개요

사용자가 자연어로 이체를 요청하면:
1. **SlotFillerAgent**가 수신인·금액 등 필수 정보를 추출
2. **StateManager**가 정보 완성 여부를 검증하고 단계를 전이
3. 정보가 충분하면 **코드가 확인 메시지**를 생성 (LLM 없음)
4. 사용자 확인 후 **ExecuteAgent**가 실제 이체 실행
5. 여러 건이 요청되면 `task_queue`로 순차 처리

---

## 상태 기계

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
 사용자 발화 → INIT ─┼─ 슬롯 완전 ──────────────────────────▶ READY
                    │                                         │
                    ├─ 슬롯 부족 ──────────────▶ FILLING ─────┘
                    │                              │
                    │                    반복 실패 │
                    │                              ▼
                    │                        UNSUPPORTED (세션 리셋)
                    │
             READY ─┼─ "확인" ──────────────▶ CONFIRMED ─▶ EXECUTED (세션 리셋)
                    │                                      ▶ FAILED   (세션 리셋)
                    │
                    ├─ "취소" ──────────────▶ CANCELLED
                    │    └─ task_queue 있음 ─▶ 다음 태스크로 스킵
                    │    └─ task_queue 없음 ─▶ 세션 리셋
```

### Stage별 처리 주체

| Stage | 처리 주체 | 설명 |
|-------|-----------|------|
| `INIT` | InteractionAgent (LLM) | 첫 인사·이체 의향 응대 |
| `FILLING` | InteractionAgent (LLM) | 빠진 슬롯 하나씩 질문 |
| `READY` | 코드 (`build_ready_message`) | LLM 없음. 결정론적 확인 메시지 |
| `CONFIRMED` | ExecuteAgent (코드) | 실제 이체 실행 |
| `EXECUTED` | 코드 (`messages.py`) | 완료 메시지 + 세션 리셋 |
| `FAILED` | 코드 (`messages.py`) | 실패 메시지 + 세션 리셋 |
| `CANCELLED` | 코드 (`messages.py`) | 취소 메시지 + 세션 리셋 |
| `UNSUPPORTED` | 코드 (`messages.py`) | 반복 실패 안내 + 세션 리셋 |

---

## 에이전트 구성

### IntentAgent
- **역할**: 사용자 발화를 `TRANSFER` / `GENERAL` 중 하나로 분류
- **GENERAL 포함**: 이체 이력·결과 질문, 일반 대화 → InteractionAgent가 메모리로 응대
- **TRANSFER만 제외**: 이체 의향이 명확한 경우

### SlotFillerAgent
- **역할**: 발화에서 `target`(수신인), `amount`(금액), `memo`, `transfer_date` 추출
- **다건 감지**: "홍길동 1만원, 김철수 5만원" → `tasks` 리스트 반환
- **제약**: `READY` 이후 단계에서는 다건 재감지 무시 (배치 리셋 방지)

### InteractionAgent (스트리밍)
- **역할**: INIT·FILLING 단계 자연어 응대
- **메모리 활용**: `summary_text`·`raw_history`에서 이체 이력 인용해 답변
- **READY 단계에서는 호출되지 않음**

### ExecuteAgent
- **역할**: 실제 이체 API 호출 (현재 목업)
- **실패 시**: `RetryableError` 또는 `FatalExecutionError` raise → stage = FAILED

---

## 슬롯 구조

```python
class Slots(BaseModel):
    target: str | None        # 수신인 (필수)
    amount: int | None        # 금액, 원 단위 (필수)
    memo: str | None          # 메모 (선택)
    transfer_date: str | None # 이체 날짜 (선택)

REQUIRED_SLOTS = ["target", "amount"]
```

### 슬롯 검증 (`StateManager`)
- `amount < 1000` → `slot_errors["amount"] = "amount_too_small"`
- `amount > 100_000_000` → `slot_errors["amount"] = "amount_too_large"`
- `target`이 숫자만 → `slot_errors["target"] = "target_invalid"`
- 오류 있으면 FILLING 유지, InteractionAgent가 자연어로 안내

---

## 다건(배치) 처리

```
사용자: "홍길동 1만원, 김철수 5만원 보내줘"
    │
    ▼ SlotFillerAgent
tasks = [
    {"target": "홍길동", "amount": 10000},
    {"target": "김철수", "amount": 50000},
]
    │
    ▼ handlers.py (INIT·FILLING 단계에서만 처리)
state.slots     = tasks[0]        # 첫 번째 태스크 즉시 적용
state.task_queue = tasks[1:]      # 나머지 큐에 보관
meta["batch_total"]    = 2
meta["batch_progress"] = 0
    │
    ▼ 첫 번째 READY → 확인 → CONFIRMED → EXECUTED
    │
    ▼ _load_next_task(state)  ← 다음 태스크 꺼내기
        True  → READY  (슬롯 완전)
        False → FILLING (슬롯 부족)
        None  → terminal (큐 끝)
```

### 배치 메타 키

| 키 | 설명 |
|----|------|
| `batch_total` | 요청된 총 이체 건수 |
| `batch_progress` | 지금까지 처리(확인·취소) 건수 |
| `batch_executed` | 실제 성공 이체 건수 |
| `last_cancelled` | 직전 태스크가 취소됐는지 (FILLING 안내에 사용) |

---

## 파일 구조 및 역할

```
app/projects/transfer/
├── project.yaml          # 서비스 메타, 에이전트 설정
├── manifest.py           # CoreOrchestrator 조립
├── messages.py           # 사용자 노출 문구 상수 (여기만 수정하면 문구 변경 완료)
├── agents/
│   ├── intent_agent/     # TRANSFER vs GENERAL 분류
│   ├── slot_filler_agent/ # 슬롯 추출 + 다건 감지
│   ├── interaction_agent/ # INIT·FILLING 자연어 응대 (스트리밍)
│   └── execute_agent/    # 이체 실행 (목업 → 실제 API로 교체)
├── state/
│   ├── models.py         # Stage, TransferState, Slots, StateManager
│   └── stores.py         # SessionStore, CompletedStore 팩토리
└── flows/
    ├── router.py         # TRANSFER→TransferFlow, GENERAL→DefaultFlow
    └── handlers.py       # 이체 플로우 전체 실행 로직
```

---

## 문구 변경 가이드

모든 사용자 노출 문구는 `messages.py`에 있다:

```python
# 단건 완료/실패/취소
TERMINAL_MESSAGES: Dict[Stage, str] = { ... }

# 다건 완료
def batch_all_complete(executed_count: int) -> str: ...
def batch_partial_complete(executed_count: int) -> str: ...

# READY 단계 확인 메시지 (코드 결정론적)
def build_ready_message(state) -> str: ...

# 반복 실패
UNSUPPORTED_MESSAGE = "..."
```

`handlers.py`와 `state/` 코드는 건드리지 않아도 된다.

---

## 확장 포인트

| 항목 | 방법 |
|------|------|
| 실제 이체 API 연결 | `execute_agent/agent.py`의 `run()` 구현 교체 |
| 새로운 슬롯 추가 | `Slots` 모델 + `REQUIRED_SLOTS` + SlotFiller 프롬프트 |
| 슬롯 검증 규칙 추가 | `StateManager.apply()` 내 검증 로직 |
| 문구 수정 | `messages.py`만 수정 |
| 새 플로우 추가 | `flows/router.py` + `flows/handlers.py`에 핸들러 추가 |

---

## 버전 이력

| 버전 | 내용 |
|------|------|
| v1.1.0 | messages.py 분리, 다건 재감지 버그 수정, 메모리 유지 수정, build_messages() 표준화 |
| v1.0.0 | 초기 구현: SlotFiller + StateManager + 배치 큐 + 자동 요약 |
