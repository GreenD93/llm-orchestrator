# app/projects/transfer/flows/handlers.py
from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler, update_memory_and_save
from app.core.agents.agent_runner import RetryableError, FatalExecutionError
from app.projects.transfer.state.models import Stage, TransferState, Slots, REQUIRED_SLOTS
from app.projects.transfer.logic import is_confirm, is_cancel
from app.projects.transfer.messages import (
    UNSUPPORTED_MESSAGE,
    TERMINAL_MESSAGES,
    build_ready_message,
    batch_partial_complete,
    batch_all_complete,
)

# UI 힌트: next_action → 버튼 목록. 문구 변경 시 여기만 수정.
UI_POLICY: Dict[str, Dict[str, Any]] = {
    "ASK_CONTINUE": {"buttons": ["계속 진행", "취소"]},
    "CONFIRM":      {"buttons": ["확인", "취소"]},
    "ASK":          {},
    "DONE":         {},
}


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _apply_ui_policy(payload: dict) -> dict:
    action = payload.get("action") or payload.get("next_action", "DONE")
    payload["next_action"] = action
    payload["ui_hint"] = UI_POLICY.get(action, {})
    return payload


def _state_snapshot(ctx: ExecutionContext) -> dict:
    return ctx.state.model_dump() if hasattr(ctx.state, "model_dump") else {}


def _reset_session(ctx: ExecutionContext, sessions: Any) -> None:
    """이체 종료 후 state 초기화. 대화 메모리는 MemoryManager가 관리 (raw_history 유지)."""
    ctx.state = TransferState()
    sessions.save_state(ctx.session_id, ctx.state)


def _load_next_task(state: TransferState) -> bool | None:
    """
    task_queue에서 다음 작업을 꺼내 state에 적용.
    반환: True=완전한 태스크, False=불완전(FILLING 필요), None=큐 없음
    """
    if not state.task_queue:
        return None
    next_task = state.task_queue.pop(0)
    state.slots = Slots(**{k: v for k, v in next_task.items() if k in Slots.model_fields})
    state.missing_required = [s for s in REQUIRED_SLOTS if getattr(state.slots, s) is None]
    state.filling_turns = 0
    return len(state.missing_required) == 0


def _yield_done(ctx: ExecutionContext, payload: dict) -> dict:
    """DONE 이벤트 payload에 state_snapshot 추가."""
    payload = _apply_ui_policy(payload)
    payload["state_snapshot"] = _state_snapshot(ctx)
    return payload


# ── Flow Handlers ─────────────────────────────────────────────────────────────

class DefaultFlowHandler(BaseFlowHandler):
    """
    TRANSFER 외 시나리오(GENERAL 등): InteractionAgent만 실행.
    메모리(summary + history)를 활용해 이전 이체 이력, 일반 질문에 자연스럽게 응대.
    """

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                           done_transform=_apply_ui_policy)


class TransferFlowHandler(BaseFlowHandler):
    """
    이체 플로우 핸들러.

    실행 순서:
      1. SlotFillerAgent  → 슬롯 추출 (다건 감지 포함)
      2. StateManager     → 슬롯 적용·검증·단계 전이 (코드)
      3. 단계별 분기:
         - UNSUPPORTED   → 안내 후 세션 리셋
         - CANCELLED + 대기 큐 → 다음 태스크로 스킵
         - CONFIRMED     → ExecuteAgent 실행, 다음 태스크 로드
         - TERMINAL      → 완료/실패/취소 메시지 후 세션 리셋
         - READY         → 코드 생성 확인 메시지 (LLM 없음)
         - FILLING/INIT  → InteractionAgent 호출
    """

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        # ── 1. Slot Filler (또는 코드 레벨 분류) ─────────────────────────────
        #
        # LLM 호출 없이 처리하는 경우:
        #   a) READY + 확인 키워드  → confirm delta
        #   b) READY + 취소 키워드  → cancel_flow delta
        #   c) READY + 불명확       → operations:[] → READY 유지 → 재확인 (안전 기본값)
        #   d) FILLING/INIT + 명시적 취소 키워드 → cancel_flow delta
        #
        yield {"event": EventType.AGENT_START, "payload": {"agent": "slot", "label": "정보 추출 중"}}

        if ctx.state.stage == Stage.READY:
            if is_confirm(ctx.user_message):
                delta = {"operations": [{"op": "confirm"}]}
            elif is_cancel(ctx.user_message):
                delta = {"operations": [{"op": "cancel_flow"}]}
            else:
                # 불명확 입력 → READY 유지 후 확인 메시지 재표시 (안전 기본값)
                delta = {"operations": []}
        elif is_cancel(ctx.user_message) and ctx.state.stage == Stage.FILLING:
            # INIT 단계에서는 shortcut 미적용 — 진행 중인 이체가 없으므로
            # InteractionAgent가 "취소할 이체가 없어요"로 자연스럽게 응대하도록 위임
            delta = {"operations": [{"op": "cancel_flow"}]}
        else:
            delta = self.runner.run("slot", ctx)

        # 다건 감지: INIT·FILLING 단계에서만 허용.
        # READY 이후에는 히스토리 재감지를 무시 → 진행 중 배치 리셋 방지.
        if delta.get("tasks") and ctx.state.stage in (Stage.INIT, Stage.FILLING):
            tasks = delta["tasks"]
            ctx.state.meta["batch_total"] = len(tasks)
            ctx.state.meta["batch_progress"] = 0
            delta = {
                "operations": [
                    {"op": "set", "slot": k, "value": v}
                    for k, v in tasks[0].items() if v is not None
                ]
            }
            ctx.state.task_queue = tasks[1:]

        # ── 2. StateManager — 검증·전이 (코드) ───────────────────────────────
        ctx.state = self.state_manager_factory(ctx.state).apply(delta)
        yield {"event": EventType.AGENT_DONE, "payload": {
            "agent": "slot",
            "label": "정보 추출 완료",
            "success": True,
            "stage": ctx.state.stage,
        }}

        # ── 3a. UNSUPPORTED — 반복 실패 초과 ─────────────────────────────────
        if ctx.state.stage == Stage.UNSUPPORTED:
            payload = {"message": UNSUPPORTED_MESSAGE, "action": "DONE"}
            update_memory_and_save(
                self.memory_manager, self.sessions, ctx.session_id,
                ctx.state, ctx.memory, ctx.user_message, payload["message"],
            )
            if self.completed:
                self.completed.add(ctx.session_id, ctx.state, ctx.memory)
            _reset_session(ctx, self.sessions)
            yield {"event": EventType.DONE, "payload": _yield_done(ctx, payload)}
            return

        # ── 3b. 단건 취소 + 대기 큐 → 다음 태스크로 스킵 ────────────────────
        if ctx.state.stage == Stage.CANCELLED and ctx.state.task_queue:
            batch_progress = ctx.state.meta.get("batch_progress", 0)
            is_complete = _load_next_task(ctx.state)
            ctx.state.meta["batch_progress"] = batch_progress + 1
            ctx.state.meta["last_cancelled"] = True
            ctx.state.stage = Stage.READY if is_complete else Stage.FILLING
            self.sessions.save_state(ctx.session_id, ctx.state)

        # ── 3c. Execute (CONFIRMED) ───────────────────────────────────────────
        if ctx.state.stage == Stage.CONFIRMED:
            batch_total    = ctx.state.meta.get("batch_total", 1)
            batch_progress = ctx.state.meta.get("batch_progress", 0)

            yield {"event": EventType.TASK_PROGRESS, "payload": {
                "index": batch_progress + 1,
                "total": batch_total,
                "slots": ctx.state.slots.model_dump(),
            }}
            yield {"event": EventType.AGENT_START, "payload": {"agent": "execute", "label": "이체 실행 중"}}
            try:
                self.runner.run("execute", ctx)
                ctx.state.stage = Stage.EXECUTED
                ctx.state.meta["batch_executed"] = ctx.state.meta.get("batch_executed", 0) + 1
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "execute", "label": "이체 실행 완료", "success": True,
                }}
                if self.completed:
                    self.completed.add(ctx.session_id, ctx.state, ctx.memory)

            except (RetryableError, FatalExecutionError):
                ctx.state.stage = Stage.FAILED
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "execute", "label": "이체 실행 실패", "success": False,
                }}

            # 다음 태스크 로드
            if ctx.state.stage == Stage.EXECUTED:
                is_complete = _load_next_task(ctx.state)
                new_progress = batch_progress + 1
                if is_complete is None:
                    pass  # 마지막 태스크 → terminal로
                elif is_complete:
                    ctx.state.stage = Stage.READY
                    ctx.state.meta["batch_progress"] = new_progress
                else:
                    ctx.state.stage = Stage.FILLING
                    ctx.state.meta["batch_progress"] = new_progress

            self.sessions.save_state(ctx.session_id, ctx.state)

        # ── 3d. Terminal (EXECUTED / FAILED / CANCELLED) ──────────────────────
        if ctx.state.stage in TERMINAL_MESSAGES:
            total_executed = ctx.state.meta.get("batch_executed", 0)
            if ctx.state.stage == Stage.CANCELLED and total_executed > 0:
                message = batch_partial_complete(total_executed)
            elif total_executed > 1:
                message = batch_all_complete(total_executed)
            else:
                message = TERMINAL_MESSAGES[ctx.state.stage]

            payload = {"message": message, "action": "DONE"}
            update_memory_and_save(
                self.memory_manager, self.sessions, ctx.session_id,
                ctx.state, ctx.memory, ctx.user_message, message,
            )
            if self.completed and ctx.state.stage in (Stage.FAILED, Stage.CANCELLED):
                self.completed.add(ctx.session_id, ctx.state, ctx.memory)
            _reset_session(ctx, self.sessions)
            yield {"event": EventType.DONE, "payload": _yield_done(ctx, payload)}
            return

        # ── 3e. READY — 결정론적 확인 메시지 (LLM 없음) ──────────────────────
        if ctx.state.stage == Stage.READY:
            message = build_ready_message(ctx.state)
            ctx.state.meta.pop("last_cancelled", None)
            payload = {"action": "CONFIRM", "message": message}
            update_memory_and_save(
                self.memory_manager, self.sessions, ctx.session_id,
                ctx.state, ctx.memory, ctx.user_message, message,
            )
            yield {"event": EventType.DONE, "payload": _yield_done(ctx, payload)}
            return

        # ── 3f. FILLING / INIT — InteractionAgent ────────────────────────────
        yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                           done_transform=_apply_ui_policy)
