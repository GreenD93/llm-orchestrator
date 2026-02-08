# app/core/api/router_factory.py
"""단일 orchestrate API 진입점. Request/Response 스키마 기준."""

import json
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.api.schemas import OrchestrateRequest, OrchestrateResponse


def create_agent_router(orchestrator: Any) -> APIRouter:
    """
    단일 오케스트레이션 진입점:
    - POST /v1/agent/chat      : 비스트리밍, OrchestrateRequest → OrchestrateResponse
    - POST /v1/agent/chat/stream: 스트리밍 SSE
    - GET  /v1/agent/completed  : 세션별 완료 이력 (선택)
    """
    router = APIRouter(prefix="/v1/agent", tags=["agent"])

    def _stream_events(session_id: str, message: str):
        for event in orchestrator.handle_stream(session_id, message):
            yield {
                "event": event.get("event", ""),
                "data": json.dumps(event.get("payload", {}), ensure_ascii=False),
            }

    @router.post("/chat", response_model=OrchestrateResponse)
    async def orchestrate(req: OrchestrateRequest) -> OrchestrateResponse:
        result = orchestrator.handle(req.session_id, req.message)
        return OrchestrateResponse(**result)

    @router.post("/chat/stream")
    async def orchestrate_stream(req: OrchestrateRequest):
        return EventSourceResponse(_stream_events(req.session_id, req.message))

    @router.get("/chat/stream")
    async def orchestrate_stream_get(session_id: str, message: str):
        return EventSourceResponse(_stream_events(session_id, message))

    @router.get("/completed")
    async def list_completed(session_id: str):
        return {
            "session_id": session_id,
            "completed": orchestrator.completed.list_for_session(session_id),
        }

    return router
