# app/projects/transfer/state/models.py
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.core.state import BaseState


# 멀티턴 초과 시 "처리 불가" 명시용. InteractionAgent 호출 없이 고정 메시지로 종료.
MAX_FILL_TURNS = 10


class Stage(str, Enum):
    INIT = "INIT"
    FILLING = "FILLING"
    READY = "READY"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    AWAITING_CONTINUE_DECISION = "AWAITING_CONTINUE_DECISION"
    UNSUPPORTED = "UNSUPPORTED"


TERMINAL_STAGES = {
    Stage.EXECUTED,
    Stage.FAILED,
    Stage.CANCELLED,
    Stage.UNSUPPORTED,
}


class Slots(BaseModel):
    target: Optional[str] = None
    amount: Optional[int] = None
    memo: Optional[str] = None
    alias: Optional[str] = None
    transfer_date: Optional[str] = None


class TransferState(BaseState):
    scenario: str = "TRANSFER"
    stage: Stage = Stage.INIT
    slots: Slots = Slots()
    missing_required: List[str] = Field(default_factory=list)
    filling_turns: int = 0

    def has_any_slot(self) -> bool:
        return any(v is not None for v in self.slots.model_dump().values())


REQUIRED_SLOTS = ("target", "amount")
SLOT_SCHEMA: Dict[str, Dict[str, Any]] = {
    "target": {"type": str, "required": True},
    "amount": {"type": int, "required": True},
    "memo": {"type": str, "required": False},
    "alias": {"type": str, "required": False},
    "transfer_date": {"type": str, "required": False, "format": "YYYY-MM-DD"},
}
