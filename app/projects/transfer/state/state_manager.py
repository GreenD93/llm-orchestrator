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
            meta = delta["_meta"]
            self.state.meta.setdefault("slot_meta", []).append(meta)
            if meta.get("parse_error") and self.state.stage in (Stage.INIT, Stage.FILLING):
                # SlotFiller가 LLM 응답을 JSON으로 파싱하지 못함.
                # → InteractionAgent가 "이해하지 못했어요" 안내를 하도록 slot_errors에 신호.
                self.state.meta.setdefault("slot_errors", {})["_unclear"] = (
                    "입력 내용을 이해하지 못했어요."
                )
        else:
            # 정상 파싱 성공 시 이전 불명확 오류 제거
            self.state.meta.get("slot_errors", {}).pop("_unclear", None)

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
            # 안전 제약: CONFIRMED는 반드시 READY → CONFIRMED 경로만 허용.
            # INIT·FILLING 단계에서 LLM이 confirm을 반환해도 무시한다.
            # (예: "보내줘" 발화에서 LLM이 confirm을 포함하더라도 READY 확인 단계를 건너뛸 수 없음)
            if self.state.stage == Stage.READY:
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
        """슬롯 상태와 현재 stage를 보고 다음 stage를 결정한다.

        흐름:
          TERMINAL/CONFIRMED → 전이 없음 (ops에서 이미 결정됨)
          filling_turns 초과  → UNSUPPORTED
          INIT + 슬롯 입력됨  → FILLING
          필수 슬롯 완전      → READY  (CONFIRMED는 _apply_op에서만 설정되므로 여기선 건드리지 않음)
        """
        if self.state.stage in TERMINAL_STAGES:
            return
        if self.state.filling_turns > MAX_FILL_TURNS:
            self.state.stage = Stage.UNSUPPORTED
            return
        if self.state.stage == Stage.INIT and self.state.has_any_slot():
            self.state.stage = Stage.FILLING
        # CONFIRMED는 반드시 READY 단계에서만 _apply_op("confirm")으로 진입.
        # 여기서 override하면 READY 단계를 건너뛰는 버그 발생.
        if self.state.stage != Stage.CONFIRMED and not self.state.missing_required:
            self.state.stage = Stage.READY

    @staticmethod
    def _cast(value: Any, t: type) -> Any:
        try:
            return t(value) if value is not None else None
        except Exception:
            return None
