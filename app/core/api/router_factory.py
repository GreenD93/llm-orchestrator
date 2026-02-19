# app/core/api/router_factory.py
"""단일 orchestrate API 진입점. Request/Response 스키마 기준."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.api.schemas import OrchestrateRequest, OrchestrateResponse
from app.core.config import settings
from sse_starlette.sse import EventSourceResponse


def create_agent_router(orchestrator: Any) -> APIRouter:
    """
    단일 오케스트레이션 진입점:
    - POST /v1/agent/chat         : 비스트리밍
    - POST /v1/agent/chat/stream  : 스트리밍 SSE
    - GET  /v1/agent/completed    : 세션별 완료 이력
    - GET  /v1/agent/debug/{id}   : 개발용 내부 상태 스냅샷 (DEV_MODE=true 시만)
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

    if settings.DEV_MODE:
        @router.get("/debug/{session_id}")
        async def debug_session(session_id: str):
            """
            개발용 세션 내부 상태 스냅샷.
            DEV_MODE=true 일 때만 등록됨 (.env에서 DEV_MODE=false로 비활성화).

            반환:
              state      - 현재 stage, slots, task_queue, meta 등 전체 state
              memory     - raw_history(대화 이력), summary_text(요약)
              completed  - 이 세션에서 완료된 이체 목록
            """
            sessions = getattr(orchestrator, "sessions", None)
            if sessions is None:
                raise HTTPException(status_code=501, detail="sessions not available on this orchestrator")

            state, memory = sessions.get_or_create(session_id)
            completed = orchestrator.completed.list_for_session(session_id)

            raw_history = memory.get("raw_history", [])
            return {
                "session_id": session_id,
                "state": state.model_dump() if hasattr(state, "model_dump") else state,
                "memory": {
                    "summary_text": memory.get("summary_text", ""),
                    "raw_history": raw_history,
                    "raw_history_turns": len(raw_history) // 2,
                    "summarize_threshold": settings.MEMORY_SUMMARIZE_THRESHOLD,
                },
                "completed": completed,
            }

    return router
