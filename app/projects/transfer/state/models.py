# app/projects/transfer/state/models.py
from datetime import date as _date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.state import BaseState


# 멀티턴 초과 시 "처리 불가" 명시용.
MAX_FILL_TURNS = 10


class Stage(str, Enum):
    INIT = "INIT"
    FILLING = "FILLING"
    READY = "READY"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
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
    # task_queue는 BaseState에서 상속

    def has_any_slot(self) -> bool:
        return any(v is not None for v in self.slots.model_dump().values())


REQUIRED_SLOTS = ("target", "amount")


# ── 슬롯별 검증 함수 ────────────────────────────────────────────────────────────

def _validate_target(v: Any) -> bool:
    return isinstance(v, str) and len(v.strip()) > 0


def _validate_amount(v: Any) -> bool:
    return isinstance(v, int) and v >= 1


def _validate_transfer_date(v: Any) -> bool:
    if v is None:
        return True
    try:
        _date.fromisoformat(str(v))
        return True
    except ValueError:
        return False


# ── 슬롯 스키마 ─────────────────────────────────────────────────────────────────
# 각 슬롯의 type, required, format, validate, error_msg 정의.
# validate(value) → bool. 실패 시 error_msg가 state.meta["slot_errors"]에 저장됨.
SLOT_SCHEMA: Dict[str, Dict[str, Any]] = {
    "target": {
        "type": str,
        "required": True,
        "validate": _validate_target,
        "error_msg": "수신자 이름이 비어있거나 올바르지 않아요. 누구에게 보낼지 다시 알려주세요.",
    },
    "amount": {
        "type": int,
        "required": True,
        "validate": _validate_amount,
        "error_msg": "이체 금액은 1원 이상의 정수여야 해요. 금액을 다시 알려주세요.",
    },
    "memo": {
        "type": str,
        "required": False,
    },
    "alias": {
        "type": str,
        "required": False,
    },
    "transfer_date": {
        "type": str,
        "required": False,
        "format": "YYYY-MM-DD",
        "validate": _validate_transfer_date,
        "error_msg": "이체 날짜를 인식하지 못했어요. '6월 19일', '2026-06-19' 형식으로 다시 알려주세요.",
    },
}
