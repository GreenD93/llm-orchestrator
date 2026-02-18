# app/projects/transfer/state/state_manager.py
import re
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.state import BaseStateManager
from app.projects.transfer.state.models import (
    Stage,
    TransferState,
    TERMINAL_STAGES,
    SLOT_SCHEMA,
    REQUIRED_SLOTS,
    MAX_FILL_TURNS,
)


def _normalize_format(value: Any, format_spec: Optional[str]) -> Any:
    if format_spec is None:
        return value
    if format_spec == "YYYY-MM-DD":
        if value is None:
            return None
        s = str(value).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            try:
                datetime.strptime(s, "%Y-%m-%d")
                return s
            except ValueError:
                pass
        return None
    return value


class TransferStateManager(BaseStateManager):
    def __init__(self, state: TransferState):
        super().__init__(state)
        self.state: TransferState = state

    def apply(self, delta: Dict[str, Any]) -> TransferState:
        if "_meta" in delta:
            self.state.meta.setdefault("slot_meta", []).append(delta["_meta"])
        if self.state.stage == Stage.FILLING:
            self.state.filling_turns += 1
        for op in delta.get("operations", []):
            self._apply_op(op)
        self._validate_required()
        self._transition()
        return self.state

    def _apply_op(self, op: Dict[str, Any]) -> None:
        op_type = op.get("op")
        if op_type == "cancel_flow":
            self.state.stage = Stage.CANCELLED
            return
        if op_type == "continue_flow":
            self.state.stage = Stage.FILLING if self.state.has_any_slot() else Stage.INIT
            return
        if op_type == "confirm":
            self.state.stage = Stage.CONFIRMED
            return

        slot = op.get("slot")
        if slot not in SLOT_SCHEMA:
            self.state.meta.setdefault("invalid_ops", []).append(op)
            return

        schema = SLOT_SCHEMA[slot]
        slot_type = schema["type"]
        format_spec = schema.get("format")
        validator = schema.get("validate")
        error_msg = schema.get("error_msg", f"{slot} 값이 올바르지 않아요.")

        if op_type == "set":
            # 1. 타입 캐스팅
            casted = self._cast(op.get("value"), slot_type)
            if casted is None:
                self.state.meta.setdefault("cast_fail_ops", []).append(op)
                self._set_slot_error(slot, error_msg)
                return

            # 2. 포맷 정규화 (날짜 등)
            normalized = _normalize_format(casted, format_spec)
            if normalized is None:
                self.state.meta.setdefault("format_fail_ops", []).append(op)
                self._set_slot_error(slot, error_msg)
                return

            # 3. 비즈니스 룰 검증
            if validator and not validator(normalized):
                self.state.meta.setdefault("validation_fail_ops", []).append(op)
                self._set_slot_error(slot, error_msg)
                return

            # 검증 통과 → 슬롯 저장 및 이전 오류 제거
            setattr(self.state.slots, slot, normalized)
            self.state.meta.get("slot_errors", {}).pop(slot, None)

        elif op_type == "clear":
            setattr(self.state.slots, slot, None)
            self.state.meta.get("slot_errors", {}).pop(slot, None)

    def _set_slot_error(self, slot: str, msg: str) -> None:
        self.state.meta.setdefault("slot_errors", {})[slot] = msg

    def _validate_required(self) -> None:
        self.state.missing_required = [
            s for s in REQUIRED_SLOTS if getattr(self.state.slots, s, None) is None
        ]

    def _transition(self) -> None:
        if self.state.stage in TERMINAL_STAGES:
            return
        if self.state.filling_turns > MAX_FILL_TURNS:
            self.state.stage = Stage.UNSUPPORTED
            return
        if self.state.stage == Stage.INIT and self.state.has_any_slot():
            self.state.stage = Stage.FILLING
        if self.state.stage != Stage.CONFIRMED and not self.state.missing_required:
            self.state.stage = Stage.READY

    @staticmethod
    def _cast(value: Any, t: type) -> Any:
        try:
            return t(value) if value is not None else None
        except Exception:
            return None
