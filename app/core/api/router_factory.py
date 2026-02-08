# app/core/api/router_factory.py
"""오케스트레이터로 FastAPI 라우터 자동 생성. 프로젝트 추가 시 라우터 코드 작성 불필요."""

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.events import EventType


class AgentChatRequest(BaseModel):
    session_id: str
    message: str


def create_agent_router(orchestrator: Any) -> APIRouter:
    """
    POST /v1/agent/chat
    POST /v1/agent/chat/stream
    GET  /v1/agent/completed
    """
    router = APIRouter(prefix="/v1/agent", tags=["agent"])

    def _stream_events(session_id: str, message: str):
        for event in orchestrator.handle_stream(session_id, message):
            yield {
                "event": event.get("event", ""),
                "data": json.dumps(event.get("payload", {}), ensure_ascii=False),
            }

    @router.post("/chat")
    async def chat(req: AgentChatRequest):
        return orchestrator.handle(req.session_id, req.message)

    @router.post("/chat/stream")
    async def chat_stream_post(req: AgentChatRequest):
        return EventSourceResponse(_stream_events(req.session_id, req.message))

    @router.get("/chat/stream")
    async def chat_stream(session_id: str, message: str):
        return EventSourceResponse(_stream_events(session_id, message))

    @router.get("/completed")
    async def list_completed(session_id: str):
        return {
            "session_id": session_id,
            "completed": orchestrator.completed.list_for_session(session_id),
        }

    return router
