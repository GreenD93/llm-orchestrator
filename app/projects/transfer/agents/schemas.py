# app/projects/transfer/agents/schemas.py
"""
이체 서비스 에이전트 출력 스키마 (Pydantic 모델).

─── 용도 ────────────────────────────────────────────────────────────────────
  AgentRunner의 schema_registry에 등록되어 에이전트 출력 검증에 사용된다.
  card.json "policy.schema" 필드에 스키마 이름을 지정하면 자동 적용된다.

─── 새 시나리오 추가 ─────────────────────────────────────────────────────────
  1. IntentResult.scenario에 가능한 값 추석 추가
  2. transfer/flows/router.py SCENARIO_TO_FLOW dict에 한 줄 추가
  3. transfer/flows/handlers.py에 FlowHandler 구현 (필요 시)
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel


class IntentResult(BaseModel):
    """
    IntentAgent 출력. 사용자 발화에서 분류된 시나리오 이름.

    scenario: "TRANSFER" | "GENERAL"
              미래 확장: "BALANCE_CHECK" | "CARD_APPLY" | ...
    reason:   디버깅용. LLM이 분류 근거를 설명하는 텍스트 (선택).
    """
    scenario: str
    reason: Optional[str] = None


class SlotOperation(BaseModel):
    """
    SlotFillerAgent가 반환하는 단일 슬롯 조작 명령.

    op:    조작 종류
      - "set":           slot=슬롯명, value=값 → slots에 값 저장
      - "clear":         slot=슬롯명 → slots에서 값 제거
      - "confirm":       READY → CONFIRMED 단계 전환 요청
      - "continue_flow": 이어서 진행 (예: 취소 후 재시도)
      - "cancel_flow":   현재 이체 취소 → CANCELLED 단계 전환
    slot:  조작 대상 슬롯명 ("target", "amount", "transfer_date", "memo")
    value: "set" 조작 시 저장할 값 (None이면 skip)
    """
    op: Literal["set", "clear", "confirm", "continue_flow", "cancel_flow"]
    slot: Optional[str] = None
    value: Optional[object] = None


class SlotResult(BaseModel):
    """
    SlotFillerAgent 전체 출력.

    operations: 슬롯 조작 명령 목록. 순서대로 StateManager.apply()가 처리.
    tasks:      다건 이체 감지 시 각 이체 정보 목록.
                [{"target": "홍길동", "amount": 50000}, {"target": "박철수", "amount": 30000}]
                탐지 시 첫 번째 태스크가 즉시 처리되고 나머지는 task_queue에 저장.
    """
    operations: List[SlotOperation] = []
    tasks: Optional[List[Dict[str, Any]]] = None


class InteractionResult(BaseModel):
    """
    InteractionAgent 출력.

    action:  다음 UI 동작:
      - "ASK":          추가 정보 수집 (빈 버튼)
      - "CONFIRM":      이체 내용 확인 요청 (확인/취소 버튼)
      - "DONE":         대화 종료 (빈 버튼)
      - "ASK_CONTINUE": 계속 진행 여부 확인 (계속 진행/취소 버튼)
    message: 사용자에게 보여줄 텍스트.

    Note:
      UI 버튼 목록은 handlers.py UI_POLICY에서 action별로 매핑된다.
      InteractionAgent는 action·message만 반환하고 버튼 결정은 FlowHandler의 책임.
    """
    action: Literal["ASK", "CONFIRM", "DONE", "ASK_CONTINUE"]
    message: str
