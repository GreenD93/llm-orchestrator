# app/api/v1/routes_agent.py

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import json

from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.orchestrator.agent_orchestrator import get_orchestrator

router = APIRouter(prefix="/v1/agent", tags=["agent"])
orchestrator = get_orchestrator()


@router.post("/chat", response_model=AgentChatResponse)
async def chat(req: AgentChatRequest):
    return orchestrator.handle(req.session_id, req.message)


def _stream_events(session_id: str, message: str):
    for event in orchestrator.handle_stream(session_id, message):
        yield {
            "event": event["event"],
            "data": json.dumps(event.get("payload", {}), ensure_ascii=False),
        }


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
