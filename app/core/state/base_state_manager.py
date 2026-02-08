# app/core/state/base_state_manager.py
from typing import Any, Dict


class BaseStateManager:
    """프로젝트별 State 적용 로직. Core는 인터페이스만 정의."""

    def __init__(self, state: Any):
        self.state = state

    def apply(self, delta: Dict[str, Any]) -> Any:
        """delta를 state에 반영한 뒤 state 반환."""
        raise NotImplementedError
