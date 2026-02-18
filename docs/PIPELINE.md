# LLM Orchestrator — Pipeline & Flow Diagrams

> 이 문서는 이체 서비스(transfer)를 예제로, 단일·다건 처리 / 부족 정보 보완 흐름을
> 파이프라인 다이어그램으로 상세히 설명합니다.
> transfer 프로젝트는 **템플릿 확장 예시**이며, 같은 구조로 어떤 서비스든 구현 가능합니다.

---

## 1. 전체 파이프라인 (단일 턴)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          한 번의 사용자 메시지 처리                            │
└─────────────────────────────────────────────────────────────────────────────┘

 사용자 메시지
      │
      ▼
 ┌──────────────────────────────────────────────────────────┐
 │  CoreOrchestrator.run_one_turn()                          │
 │                                                           │
 │  ① SessionStore.get_or_create()                           │
 │     └─ (state, memory) ← raw_history + summary_text      │
 │                                                           │
 │  ② [IntentAgent] ← state.stage + history + user_message  │
 │     └─ "TRANSFER" or "GENERAL"                           │
 │                                                           │
 │  ③ FlowRouter.route(intent, state) → flow_key            │
 │     ├─ TRANSFER → TransferFlowHandler                     │
 │     └─ GENERAL  → DefaultFlowHandler                      │
 │                                                           │
 │  ④ FlowHandler.run(ctx) → [이벤트 스트림]                │
 │                                                           │
 │  ⑤ SessionStore.save_state()  ← finally 블록 (항상 저장) │
 └──────────────────────────────────────────────────────────┘
      │
      ▼
 SSE 이벤트 스트림 → 프론트엔드
```

---

## 2. 단일 이체 파이프라인 (완전 정보)

```
사용자: "엄마한테 1만원 보내줘"

      │
      ▼
 [IntentAgent]
  └─ TRANSFER
      │
      ▼
 [SlotFillerAgent]
  └─ operations: [
       {op:"set", slot:"target", value:"엄마"},
       {op:"set", slot:"amount", value:10000}
     ]
      │
      ▼
 [TransferStateManager.apply()]
  ├─ slots.target = "엄마"   ✓ 검증 통과
  ├─ slots.amount = 10000    ✓ 검증 통과 (≥1원)
  ├─ missing_required = []   ← 필수 슬롯 모두 채워짐
  └─ stage: INIT → READY     ← 코드 전이
      │
      ▼
 [READY 단계 — LLM 없음, 코드 생성]
  └─ message: "엄마에게 1만원을(를) 이체할까요?
               메모나 이체 날짜를 추가하시겠어요?"
  └─ next_action: CONFIRM, buttons: ["확인", "취소"]
      │
      ├─ "확인" ─────────────────────────┐
      │                                  ▼
      │                          [TransferStateManager]
      │                           stage: CONFIRMED
      │                                  │
      │                                  ▼
      │                          [TransferExecuteAgent]
      │                           └─ 실행 성공 → EXECUTED
      │                                  │
      │                                  ▼
      │                          message: "이체가 완료됐어요."
      │                          MemoryManager.update() → 요약 저장
      │                          state 초기화 (메모리 유지)
      │
      └─ "취소" ─────────────────────────▶ CANCELLED
                                          message: "이체가 취소됐어요."
```

---

## 3. 부족 정보 보완 파이프라인 (FILLING 루프)

```
사용자: "엄마한테 보내줘"  ← amount 없음

      │
      ▼
 [SlotFillerAgent]
  └─ operations: [{op:"set", slot:"target", value:"엄마"}]
      │
      ▼
 [TransferStateManager.apply()]
  ├─ slots.target = "엄마"
  ├─ missing_required = ["amount"]   ← 필수 슬롯 미충족
  └─ stage: INIT → FILLING
      │
      ▼
 [InteractionAgent — FILLING]
  입력: state.missing_required=["amount"], state.slots.target="엄마"
       + summary_text (과거 요약) + raw_history (최근 대화)
  └─ message: "엄마에게 얼마를 보내드릴까요?"
      │
 ─────────────── 다음 턴 ───────────────

 사용자: "3만원"
      │
      ▼
 [SlotFillerAgent]
  └─ operations: [{op:"set", slot:"amount", value:30000}]
      │
      ▼
 [TransferStateManager.apply()]
  ├─ slots.amount = 30000    ✓ 검증 통과
  ├─ missing_required = []
  └─ stage: FILLING → READY
      │
      ▼
 [READY — 코드 생성]
  └─ message: "엄마에게 3만원을(를) 이체할까요?"
              next_action: CONFIRM

─────────────────────────────────────────
검증 실패 케이스:
─────────────────────────────────────────

 사용자: "마이너스 천원"
      │
      ▼
 [SlotFillerAgent]
  └─ operations: [{op:"set", slot:"amount", value:-1000}]
      │
      ▼
 [TransferStateManager.apply()]
  ├─ validator(_validate_amount): -1000 < 1 → 실패
  ├─ state.meta["slot_errors"]["amount"] = "이체 금액은 1원 이상..."
  └─ slots.amount = None (변경 없음), stage = FILLING 유지
      │
      ▼
 [InteractionAgent — FILLING]
  입력: state.meta.slot_errors.amount = "이체 금액은 1원 이상..."
  └─ message: "이체 금액은 1원 이상이어야 해요. 다시 말씀해 주세요."

* 검증은 StateManager 코드에서 처리 — 프롬프트 의존 없음 *
```

---

## 4. 다건(Multi-task) 큐 파이프라인

```
사용자: "엄마한테 만원, 용걸이한테 5만원 보내줘"

      │
      ▼
 [IntentAgent] → TRANSFER
      │
      ▼
 [SlotFillerAgent]
  └─ tasks: [
       {target:"엄마",   amount:10000},   ← tasks[0]
       {target:"용걸이", amount:50000}    ← tasks[1]
     ]
      │
      ▼
 [Handler: 다건 분리]
  ├─ meta.batch_total = 2
  ├─ meta.batch_progress = 0
  ├─ tasks[0] → 현재 슬롯 적용
  └─ task_queue = [{target:"용걸이", amount:50000}]  ← 대기
      │
      ▼
 [StateManager] → READY (두 슬롯 모두 완전)
      │
      ▼
 [코드 생성 메시지]
  └─ "총 2건이 요청됐어요. 먼저 엄마에게 1만원 보낼까요? (1/2)"
     next_action: CONFIRM
      │
      ├─ "확인" ─────────────────────────────────────┐
      │                                               │
      │ [Execute: 엄마 1만원]                         │
      │  └─ EXECUTED, batch_executed = 1              │
      │                                               │
      │ [_load_next_task()]                           │
      │  ├─ task_queue.pop(0) → {용걸이, 50000}       │
      │  ├─ slots 적용, missing_required = []         │
      │  └─ stage → READY (완전한 태스크)             │
      │                                               │
      │ meta.batch_progress = 1                       │
      │                                               ▼
      │                           [코드 생성 메시지]
      │                            └─ "완료! 다음으로 용걸이에게 5만원 보낼까요? (2/2)"
      │                               next_action: CONFIRM
      │                                               │
      │                               "확인" ─────────┘
      │                                               │
      │                               [Execute: 용걸이 5만원]
      │                                └─ EXECUTED, batch_executed = 2
      │                                               │
      │                               [_load_next_task()]
      │                                └─ task_queue 비어있음 → None
      │                                               │
      │                               [Terminal]
      │                                └─ "2건 이체가 모두 완료됐어요."
      │
      └─ "취소" (1번 취소, 큐 있음)
           │
           ▼
      [task_queue 있음 → 다음 태스크로 스킵]
       ├─ _load_next_task() → 용걸이 태스크
       ├─ meta.last_cancelled = True
       └─ stage → READY
           │
           ▼
      [코드 생성]
       └─ "취소됐어요. 용걸이에게 5만원 보낼까요? (2/2)"
```

---

## 5. 부족한 정보가 있는 다건 태스크

```
사용자: "엄마한테 만원, 용걸이한테 보내줘"  ← 용걸이 금액 없음

      │
      ▼
 [SlotFillerAgent]
  └─ tasks: [
       {target:"엄마",   amount:10000},   ← 완전
       {target:"용걸이", amount:null}     ← 불완전 (amount 없음)
     ]
      │
      ▼
 [Handler: 다건 분리]
  ├─ tasks[0] {엄마, 10000} → 현재 슬롯
  └─ task_queue = [{용걸이, null}]
      │
      ▼
 [StateManager] → READY (엄마 태스크 완전)
  └─ "엄마에게 1만원 보낼까요? (1/2)"

 사용자: "확인"

 [Execute: 엄마 1만원]
 [_load_next_task()]
  ├─ slots = {target:"용걸이", amount:null}
  ├─ missing_required = ["amount"]  ← 불완전!
  └─ stage → FILLING (불완전 태스크)
      │
      ▼
 [InteractionAgent — FILLING]
  입력: missing_required=["amount"], slots.target="용걸이"
  └─ "용걸이에게 얼마를 보내드릴까요? (2/2)"

 사용자: "3만원"
      │
      ▼
 [SlotFillerAgent] → amount: 30000
 [StateManager] → READY
  └─ "용걸이에게 3만원 보낼까요? (2/2)"
```

---

## 6. 메모리가 대화에 기여하는 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                  Memory 구조 (MemoryManager)                 │
│                                                             │
│  summary_text                   raw_history                 │
│  ┌─────────────────────────┐   ┌──────────────────────────┐ │
│  │ "지난 대화에서 엄마에게  │   │ turn N-3: user/assistant │ │
│  │  만원, 용걸이에게 5만원  │   │ turn N-2: user/assistant │ │
│  │  이체 완료. 사용자가 종종│   │ turn N-1: user/assistant │ │
│  │  가족에게 소액 송금..."  │   │ turn N:   user (현재)    │ │
│  └─────────────────────────┘   └──────────────────────────┘ │
│          ↑ LLM 요약 (8턴 초과 시)      ↑ 최근 4턴 원문       │
└─────────────────────────────────────────────────────────────┘
                    │
                    │ build_messages() 호출 시
                    ▼
        [system: agent 지침]
        [system: state 정보 + summary_text]
        [user: "안녕"  ]  ← raw_history
        [assistant: "..."]
        [user: "총 얼마 보냈어?"]  ← 현재 user_message

                    │
                    ▼
           [InteractionAgent]
        summary_text 참조 → "지난번에 엄마 1만원, 용걸이 5만원
                              총 6만원을 보내셨어요."

────────────── 자연스러운 응대 예시 ──────────────

  상황: 이체 완료 후 사용자가 "총 얼마 보냈어?" 질문

  IntentAgent → GENERAL (이체 이력 질문)
  DefaultFlowHandler → InteractionAgent

  InteractionAgent 입력:
    summary: "엄마 10,000원, 용걸이 50,000원 이체 완료"
    user_message: "총 얼마 보냈어?"

  출력: "이번에 총 6만원을 보내셨어요.
         엄마에게 1만원, 용걸이에게 5만원이었어요."

  ↑ 프롬프트 제어가 아닌 실제 메모리 데이터 기반 응답
```

---

## 7. 코드 제어 vs LLM 제어 경계

```
┌────────────────────────────────────────────────────────────────────┐
│             코드(결정론적)                  LLM(확률적)              │
│─────────────────────────────────────────────────────────────────── │
│  Stage 전이 (INIT→FILLING→READY→...)    Intent 분류                │
│  슬롯 타입 검증 (int, str)               슬롯 값 추출               │
│  슬롯 비즈니스 검증 (amount ≥ 1원)       자연어 → 슬롯 변환         │
│  날짜 포맷 검증 (YYYY-MM-DD)             날짜 표현 → ISO 변환       │
│  READY 확인 메시지 생성                  FILLING 안내 메시지 생성   │
│  Terminal 메시지 생성                    일반 대화 응답              │
│  배치 큐 관리 (pop, count)               다건 의도 감지              │
│  MAX_FILL_TURNS 초과 → UNSUPPORTED      오류 안내 문구              │
│  메모리 요약 트리거                       대화 요약 내용 생성         │
│─────────────────────────────────────────────────────────────────── │
│  안전 기준: 금전/상태 변경은 모두 코드 검증 → LLM 출력을 신뢰하지 않음│
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. 템플릿 확장 가이드 (신규 서비스)

```
minimal/ 템플릿을 복사해서 시작:

  [단순 대화 서비스]         [슬롯 기반 서비스]        [멀티 시나리오]
  minimal/ 그대로 사용  →  transfer/ 구조 참고   →  Intent 분기 추가
  ChatAgent만 구현          SlotFiller + State         다수 FlowHandler
  메모리 자동 적용           검증 로직 코드화           SuperOrchestrator

  공통 Core (수정 금지):
  ├─ ExecutionContext.build_messages()  ← 모든 Agent 공통 메시지 빌더
  ├─ AgentRunner (재시도, 검증, 타임아웃)
  ├─ MemoryManager (자동 요약)
  ├─ InMemorySessionStore (프로덕션: Redis로 교체)
  └─ SSE 이벤트 스트림

  서비스 구현 포인트:
  ├─ agents/*/prompt.py  ← 역할·지침 정의
  ├─ agents/*/card.json  ← 모델·정책·툴 설정
  ├─ state/models.py     ← 상태값, 슬롯, 단계 정의
  ├─ state/state_manager.py ← 전이 규칙 (코드)
  ├─ flows/handlers.py   ← 실행 순서 결정
  └─ manifest.py         ← 전체 조립
```

---

## 9. 이벤트 스트림 예시 (다건 처리)

```
# 턴 1: "엄마한테 만원 용걸이한테 5만원"
→ AGENT_START  {agent:"intent",       label:"의도 파악 중"}
→ AGENT_DONE   {agent:"intent",       result:"TRANSFER",  success:true}
→ AGENT_START  {agent:"slot",         label:"정보 추출 중"}
→ AGENT_DONE   {agent:"slot",         label:"정보 추출 완료", stage:"READY"}
→ DONE         {message:"총 2건... 엄마 1만원 (1/2)?",
                next_action:"CONFIRM", ui_hint:{buttons:["확인","취소"]},
                state_snapshot:{stage:"READY", slots:{...}, meta:{batch_total:2,...}}}

# 턴 2: "확인"
→ AGENT_START  {agent:"intent",   result:"TRANSFER"}
→ AGENT_DONE   ...
→ AGENT_START  {agent:"slot",     label:"정보 추출 중"}
→ AGENT_DONE   {stage:"CONFIRMED"}
→ TASK_PROGRESS {index:1, total:2, slots:{target:"엄마", amount:10000}}
→ AGENT_START  {agent:"execute",  label:"이체 실행 중"}
→ AGENT_DONE   {agent:"execute",  success:true}
→ DONE         {message:"완료! 다음으로 용걸이 5만원 (2/2)?",
                next_action:"CONFIRM",
                state_snapshot:{stage:"READY", batch_progress:1}}

# 턴 3: "확인"
→ ...TASK_PROGRESS {index:2, total:2}
→ AGENT_DONE   {agent:"execute", success:true}
→ DONE         {message:"2건 이체가 모두 완료됐어요.", next_action:"DONE"}
```
