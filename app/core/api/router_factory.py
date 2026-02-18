# app/core/api/router_factory.py
"""단일 orchestrate API 진입점. Request/Response 스키마 기준."""

import json
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.api.schemas import OrchestrateRequest, OrchestrateResponse


def create_agent_router(orchestrator: Any) -> APIRouter:
    """
    오케스트레이션 진입점:
    - POST /v1/agent/chat         : 비스트리밍
    - POST /v1/agent/chat/stream  : 스트리밍 SSE
    - GET  /v1/agent/chat/stream  : 스트리밍 SSE (GET)
    - GET  /v1/agent/health       : 헬스 체크
    - GET  /v1/agent/agents       : A2A 호환 Agent Card 목록
    - GET  /v1/agent/completed    : 세션별 완료 이력
    - DELETE /v1/agent/session/{session_id} : 세션 리셋
    """
    router = APIRouter(prefix="/v1/agent", tags=["agent"])

    def _stream_events(session_id: str, message: str):
        for event in orchestrator.handle_stream(session_id, message):
            yield {
                "event": event.get("event", ""),
                "data": json.dumps(event.get("payload", {}), ensure_ascii=False),
            }

    @router.get("/health")
    async def health():
        agents = list(orchestrator._runner._agents.keys())
        flows = list(orchestrator._flow_handlers.keys())
        return {"status": "ok", "agents": agents, "flows": flows}

    @router.get("/agents")
    async def list_agents():
        cards = []
        for agent in orchestrator._runner._agents.values():
            if hasattr(agent, "to_agent_card"):
                cards.append(agent.to_agent_card())
            else:
                cards.append({"name": agent.__class__.__name__})
        return {"agents": cards}

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

    @router.delete("/session/{session_id}")
    async def reset_session(session_id: str):
        if hasattr(orchestrator.sessions, "reset_full"):
            orchestrator.sessions.reset_full(session_id)
        else:
            # Fallback: get_or_create로 새 상태 생성 후 저장
            state, memory = orchestrator.sessions.get_or_create(session_id)
            orchestrator.sessions.save_state(session_id, state.__class__())
        return {"status": "ok", "session_id": session_id}

    return router
