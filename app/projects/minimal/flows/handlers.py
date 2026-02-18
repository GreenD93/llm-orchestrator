# app/projects/minimal/flows/handlers.py
from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler, update_memory_and_save


class ChatFlowHandler(BaseFlowHandler):
    """
    단일 에이전트 대화 플로우.
    ChatAgent 실행 → 메모리 업데이트 → DONE 이벤트 반환.
    """

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        yield {"event": EventType.AGENT_START, "payload": {"agent": "chat", "label": "응답 생성 중"}}

        payload = None
        for ev in self.runner.run_stream("chat", ctx):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")

        yield {"event": EventType.AGENT_DONE, "payload": {"agent": "chat", "label": "응답 완료", "success": True}}

        if payload:
            update_memory_and_save(
                self.memory_manager, self.sessions,
                ctx.session_id, ctx.state, ctx.memory,
                ctx.user_message, payload.get("message", ""),
            )

        state_snapshot = ctx.state.model_dump() if hasattr(ctx.state, "model_dump") else {}
        yield {
            "event": EventType.DONE,
            "payload": {
                "message": (payload or {}).get("message", ""),
                "next_action": "ASK",
                "ui_hint": {},
                "state_snapshot": state_snapshot,
            },
        }
