# app/core/state/base_state.py
"""
모든 서비스 State의 베이스 클래스.

새 서비스를 만들 때 BaseState를 상속해 서비스별 필드를 추가한다.

    class MyState(BaseState):
        scenario: str = "MY_SERVICE"
        stage: str = "INIT"
        slots: MySlots = MySlots()
        # ... 서비스별 필드

상속 시 주의:
  - scenario: 변경하지 않으면 "DEFAULT". IntentAgent가 반환하는 값과 일치해야 한다.
  - stage: 상태 머신의 현재 단계. 단순 서비스면 "INIT" 하나만 써도 된다.
  - meta: 런타임 중간 데이터 (오류 정보, 배치 진행 상황 등). 직렬화 가능한 값만 넣는다.
  - task_queue: 순차 처리할 작업 목록 (배치/다건 처리용).
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class BaseState(BaseModel):
    """
    서비스 공통 State 베이스.

    ─── 필드 설명 ───────────────────────────────────────────────────
    scenario   현재 활성 시나리오. IntentAgent가 설정하며 FlowRouter가 읽는다.
               예: "TRANSFER", "GENERAL", "DEFAULT"

    stage      서비스 상태 머신의 현재 단계.
               단순 서비스: "INIT" 하나로 충분.
               복잡 서비스: "INIT" → "FILLING" → "READY" → "CONFIRMED" → ... 정의.

    meta       런타임 중간 데이터 (dict). 타입 정의 없이 자유롭게 사용.
               주요 사용처:
                 - slot_errors:   {"슬롯명": "오류 메시지"}  ← StateManager가 기록
                 - slot_meta:     [{"parse_error": True}]   ← SlotFiller 파싱 실패 신호
                 - batch_total:   int  배치 전체 건수
                 - batch_progress: int 배치 완료 건수
                 - execution:     {"agent": ..., "error": ...}  ← 실행 오류 기록
               세션 리셋(이체 완료 등) 시 state 전체가 초기화되므로 meta도 함께 초기화됨.

    task_queue 순차 처리할 작업 목록. 배치/다건 처리에 사용.
               각 항목은 slot dict (부분 입력 허용).
                 [{"target": "홍길동", "amount": 50000},
                  {"target": "엄마",   "amount": None}]   ← amount는 FILLING 단계에서 수집
               FlowHandler가 pop()으로 꺼내 slots에 적용한다.
               단건 서비스면 사용할 필요 없다.
    """

    scenario:   str = "DEFAULT"
    stage:      str = "INIT"
    meta:       Dict[str, Any] = Field(default_factory=dict)
    task_queue: List[Dict[str, Any]] = Field(default_factory=list)
