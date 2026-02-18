# app/projects/transfer/agents/schemas.py
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel


class IntentResult(BaseModel):
    """
    사용자가 원하는 시나리오 이름.
    새 서비스 추가 = scenario 값 + SCENARIO_TO_FLOW 한 줄.
    """
    scenario: str                   # "TRANSFER" | "GENERAL" | 미래: "BALANCE_CHECK" | ...
    reason: Optional[str] = None


class SlotOperation(BaseModel):
    op: Literal["set", "clear", "confirm", "continue_flow", "cancel_flow"]
    slot: Optional[str] = None
    value: Optional[object] = None


class SlotResult(BaseModel):
    operations: List[SlotOperation] = []
    tasks: Optional[List[Dict[str, Any]]] = None  # 멀티 이체: [{target, amount, ...}, ...]


class InteractionResult(BaseModel):
    """InteractionAgent 출력: 다음 행동 + 사용자 메시지만. UI 정책은 FlowHandler에서 매핑."""
    action: Literal["ASK", "CONFIRM", "DONE", "ASK_CONTINUE"]
    message: str
