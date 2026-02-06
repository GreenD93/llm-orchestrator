# app/services/state/state_manager.py

import re
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.state.models import Stage
from app.services.state.models import TransferState, TERMINAL_STAGES, SLOT_SCHEMA, REQUIRED_SLOTS


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


class StateManager:
    def __init__(self, state: TransferState):
        self.state = state

    def apply(self, delta: Dict[str, Any]) -> TransferState:
        for op in delta.get("operations", []):
            self._apply_op(op)

        self._validate_required()
        self._transition()
        return self.state

    def _apply_op(self, op: Dict[str, Any]) -> None:
        op_type = op.get("op")

        # =========================
        # 흐름 제어 op
        # =========================
        if op_type == "cancel_flow":
            self.state.stage = Stage.CANCELLED
            return

        if op_type == "continue_flow":
            if self.state.has_any_slot():
                self.state.stage = Stage.FILLING
            else:
                self.state.stage = Stage.INIT
            return

        if op_type == "confirm":
            self.state.stage = Stage.CONFIRMED
            return

        # =========================
        # 슬롯 op
        # =========================
        slot = op.get("slot")
        if slot not in SLOT_SCHEMA:
            self.state.meta.setdefault("invalid_ops", []).append(op)
            return

        meta = SLOT_SCHEMA[slot]
        slot_type = meta["type"]
        format_spec = meta.get("format")

        if op_type == "set":
            raw_value = op.get("value")

            # 1️⃣ type cast
            casted = self._cast(raw_value, slot_type)
            if casted is None:
                self.state.meta.setdefault("cast_fail_ops", []).append(op)
                return

            # 2️⃣ format normalize (있으면)
            normalized = _normalize_format(casted, format_spec)
            if normalized is None:
                self.state.meta.setdefault("format_fail_ops", []).append(op)
                return

            setattr(self.state.slots, slot, normalized)

        elif op_type == "clear":
            setattr(self.state.slots, slot, None)

        else:
            self.state.meta.setdefault("unknown_ops", []).append(op)

    def _validate_required(self) -> None:
        self.state.missing_required = [
            s for s in REQUIRED_SLOTS
            if getattr(self.state.slots, s, None) is None
        ]

    def _transition(self) -> None:
        if self.state.stage in TERMINAL_STAGES:
            return

        if self.state.stage == Stage.INIT and self.state.has_any_slot():
            self.state.stage = Stage.FILLING

        if self.state.stage == Stage.AWAITING_CONTINUE_DECISION:
            return

        if self.state.stage != Stage.CONFIRMED and not self.state.missing_required:
            self.state.stage = Stage.READY

    @staticmethod
    def _cast(value: Any, t: type) -> Any:
        try:
            if value is None:
                return None
            return t(value)
        except Exception:
            return None
