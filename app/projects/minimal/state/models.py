# app/projects/minimal/state/models.py
"""
Minimal 서비스 State.
단순 대화 서비스는 BaseState의 기본값(stage="INIT")만으로 충분하다.
복잡한 슬롯·단계 관리가 필요하면 transfer/state/models.py를 참고한다.
"""
from app.core.state import BaseState, BaseStateManager


class MinimalState(BaseState):
    """stage: INIT (고정) — 상태 전이 없음."""
    scenario: str = "GENERAL"


class MinimalStateManager(BaseStateManager):
    """delta를 적용하지 않고 state를 그대로 반환 (상태 머신 없음)."""

    def __init__(self, state: MinimalState):
        super().__init__(state)

    def apply(self, delta: dict) -> MinimalState:
        return self.state
