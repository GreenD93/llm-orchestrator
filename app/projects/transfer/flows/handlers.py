# app/projects/transfer/flows/handlers.py
from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler, update_memory_and_save
from app.core.agents.agent_runner import RetryableError, FatalExecutionError
from app.projects.transfer.state.models import Stage, TERMINAL_STAGES, TransferState

UI_POLICY: Dict[str, Dict[str, Any]] = {
    "ASK_CONTINUE": {"buttons": ["계속 진행", "취소"]},
    "CONFIRM": {"buttons": ["확인", "취소"]},
    "ASK": {},
    "DONE": {},
}


def _apply_ui_policy(payload: dict) -> dict:
    action = payload.get("action") or payload.get("next_action", "DONE")
    payload["next_action"] = action
    payload["ui_hint"] = UI_POLICY.get(action, {})
    return payload


class DefaultFlowHandler(BaseFlowHandler):
    """TRANSFER가 아닌 경우: Interaction만 실행 후 메모리 갱신, DONE 반환."""

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        payload = None
        for ev in self.runner.run_stream("interaction", ctx):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")
        if payload:
            update_memory_and_save(
                self.memory_manager,
                self.sessions,
                ctx.session_id,
                ctx.state,
                ctx.memory,
                ctx.user_message,
                payload.get("message", ""),
            )
        yield {"event": EventType.DONE, "payload": _apply_ui_policy(payload or {})}


UNSUPPORTED_MESSAGE = "입력이 반복되어 더 이상 진행할 수 없어요. 처음부터 다시 시도해 주세요."


class TransferFlowHandler(BaseFlowHandler):
    """Slot → State 적용 → (CONFIRMED면 Execute) → Interaction → terminal이면 completed, DONE."""

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        delta = self.runner.run("slot", ctx)
        ctx.state = self.state_manager_factory(ctx.state).apply(delta)

        if getattr(ctx.state, "stage", None) == Stage.UNSUPPORTED:
            payload = {"message": UNSUPPORTED_MESSAGE, "action": "DONE"}
            update_memory_and_save(
                self.memory_manager, self.sessions, ctx.session_id, ctx.state, ctx.memory,
                ctx.user_message, payload["message"],
            )
            if self.completed:
                self.completed.add(ctx.session_id, ctx.state, ctx.memory)
            ctx.state = TransferState()
            self.sessions.save_state(ctx.session_id, ctx.state)
            yield {"event": EventType.DONE, "payload": _apply_ui_policy(payload)}
            return

        if getattr(ctx.state, "stage", None) and ctx.state.stage == Stage.CONFIRMED:
            try:
                self.runner.run("execute", ctx)
                ctx.state.stage = Stage.EXECUTED
            except RetryableError:
                ctx.state.stage = Stage.FAILED
                ctx.state.meta.setdefault("execution", {})["retryable"] = True
            except FatalExecutionError:
                ctx.state.stage = Stage.FAILED
            self.sessions.save_state(ctx.session_id, ctx.state)

        payload = None
        for ev in self.runner.run_stream("interaction", ctx):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")

        if payload:
            update_memory_and_save(
                self.memory_manager,
                self.sessions,
                ctx.session_id,
                ctx.state,
                ctx.memory,
                ctx.user_message,
                payload.get("message", ""),
            )

        if getattr(ctx.state, "stage", None) and ctx.state.stage in TERMINAL_STAGES:
            if self.completed:
                self.completed.add(ctx.session_id, ctx.state, ctx.memory)
            ctx.state = TransferState()
            self.sessions.save_state(ctx.session_id, ctx.state)

        yield {"event": EventType.DONE, "payload": _apply_ui_policy(payload or {})}
