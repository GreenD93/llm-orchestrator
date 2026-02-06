from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Stage(str, Enum):
    INIT = "INIT"
    FILLING = "FILLING"
    READY = "READY"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    AWAITING_CONTINUE_DECISION = "AWAITING_CONTINUE_DECISION"


TERMINAL_STAGES = {
    Stage.EXECUTED,
    Stage.FAILED,
    Stage.CANCELLED,
}


class BaseState(BaseModel):
    """
    모든 시나리오 공통 State
    """
    scenario: str = "DEFAULT"
    stage: Stage = Stage.INIT
    meta: Dict[str, Any] = Field(default_factory=dict)


class Slots(BaseModel):
    target: Optional[str] = None
    amount: Optional[int] = None
    memo: Optional[str] = None
    alias: Optional[str] = None
    transfer_date: Optional[str] = None


class TransferState(BaseState):
    """
    이체 시나리오 전용 State
    """
    scenario: str = "TRANSFER"
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
    "transfer_date": {
        "type": str,
        "required": False,
        "format": "YYYY-MM-DD",
    },
}
