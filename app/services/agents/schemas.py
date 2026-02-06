# app/services/agents/schemas.py

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# ---------- Intent ----------
class IntentResult(BaseModel):
    intent: Literal["TRANSFER", "OTHER"]


# ---------- SlotFiller ----------
class SlotOperation(BaseModel):
    op: Literal[
        "set",
        "clear",
        "confirm",
        "continue_flow",
        "cancel_flow",
    ]
    slot: Optional[str] = None
    value: Optional[object] = None


class SlotResult(BaseModel):
    operations: List[SlotOperation]


# ---------- Interaction ----------
class InteractionResult(BaseModel):
    message: str
    next_action: Literal[
        "ASK",
        "CONFIRM",
        "DONE",
        "ASK_CONTINUE",
    ]
    ui_hint: dict
