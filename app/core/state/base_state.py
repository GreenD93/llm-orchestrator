# app/core/state/base_state.py
from typing import Any, Dict
from pydantic import BaseModel, Field


class BaseState(BaseModel):
    """모든 시나리오 공통 State (도메인 무관)."""
    scenario: str = "DEFAULT"
    stage: str = "INIT"
    meta: Dict[str, Any] = Field(default_factory=dict)
