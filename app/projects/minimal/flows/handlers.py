"""1-step: interaction 호출 → 메모리 갱신 → DONE."""

from typing import Any, Dict, Generator

from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler, get_history, update_and_save


class MinimalFlowHandler(BaseFlowHandler):
    """최소 플로우: interaction 한 번 실행 후 DONE."""

    def run(
        self,
        *,
        session_id: str,
        state: Any,
        memory: dict,
        user_message: str,
    ) -> Generator[Dict[str, Any], None, None]:
        history = get_history(memory)
        summary_text = memory.get("summary_text", "")
        summary_struct = memory.get("summary_struct")
        interaction = self.get("interaction")
        payload = None
        for ev in interaction.call(
            state, history, summary_text, summary_struct, state=state, stream=True
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload") or {}
        if payload:
            update_and_save(
                self.memory,
                self.sessions,
                session_id,
                state,
                memory,
                user_message,
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
