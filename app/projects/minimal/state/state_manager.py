"""최소 템플릿: BaseState만 사용. delta는 meta에만 반영 (선택)."""

from typing import Any, Dict

from app.core.state import BaseState, BaseStateManager


class MinimalStateManager(BaseStateManager):
    """stage/slot 없음. meta 갱신만 적용."""

    def __init__(self, state: BaseState):
        super().__init__(state)
        self.state: BaseState = state

    def apply(self, delta: Dict[str, Any]) -> BaseState:
        if isinstance(delta, dict) and "meta" in delta:
            self.state.meta.update(delta["meta"])
        return self.state
