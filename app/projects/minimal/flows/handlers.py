"""1-step: interaction 실행 → 메모리 갱신 → DONE."""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler, update_memory_and_save


class MinimalFlowHandler(BaseFlowHandler):
    """최소 플로우: interaction 한 번 실행 후 DONE."""

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        payload = None
        for ev in self.runner.run_stream("interaction", ctx):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload") or {}
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
        yield {
            "event": EventType.DONE,
            "payload": {
                "message": payload.get("message", "") if payload else "",
                "next_action": payload.get("action", "DONE") if payload else "DONE",
                "ui_hint": {},
            },
        }
