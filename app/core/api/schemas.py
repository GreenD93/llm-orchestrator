# app/core/api/schemas.py
"""서비스 진입점: 단일 orchestrate API용 Request/Response 스키마."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class OrchestrateRequest(BaseModel):
    """단일 턴 오케스트레이션 요청."""
    session_id: str = Field(..., description="세션 식별자")
    message: str = Field(..., description="사용자 메시지")


class OrchestrateResponse(BaseModel):
    """비스트리밍 응답: 턴 종료 시 interaction 한 건."""
    interaction: Dict[str, Any] = Field(default_factory=dict, description="DONE payload (메시지, next_action, ui_hint 등)")
    hooks: List[Any] = Field(default_factory=list, description="추가 훅 결과")
