# app/projects/transfer/state/stores.py
"""
이체 서비스 세션/이력 스토어.
범용 구현은 app.core.state.stores에 있으며, 이체 State 팩토리만 주입한다.
"""
from app.core.state.stores import InMemorySessionStore, InMemoryCompletedStore
from app.projects.transfer.state.models import TransferState


def SessionStore() -> InMemorySessionStore:
    """TransferState를 기본값으로 사용하는 세션 스토어."""
    return InMemorySessionStore(state_factory=TransferState)


def CompletedStore() -> InMemoryCompletedStore:
    """완료된 이체 이력 스토어."""
    return InMemoryCompletedStore()
