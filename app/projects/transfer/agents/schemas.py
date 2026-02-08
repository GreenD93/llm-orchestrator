# app/projects/transfer/agents/schemas.py
from typing import List, Literal, Optional
from pydantic import BaseModel


class IntentResult(BaseModel):
    """의도 + 이 서비스에서 지원 가능 여부. supported=false면 DEFAULT_FLOW로 분기."""

    intent: Literal["TRANSFER", "OTHER"]
    supported: bool = True
    reason: Optional[str] = None


class SlotOperation(BaseModel):
    op: Literal["set", "clear", "confirm", "continue_flow", "cancel_flow"]
    slot: Optional[str] = None
    value: Optional[object] = None


class SlotResult(BaseModel):
    operations: List[SlotOperation]


class InteractionResult(BaseModel):
    """InteractionAgent 출력: 다음 행동 + 사용자 메시지만. UI 정책은 FlowHandler에서 매핑."""
    action: Literal["ASK", "CONFIRM", "DONE", "ASK_CONTINUE"]
    message: str
