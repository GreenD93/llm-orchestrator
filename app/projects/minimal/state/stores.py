from typing import Any, Dict, Tuple

from app.core.state import BaseState


def _empty_memory() -> dict:
    return {"raw_history": []}


class SessionStore:
    def __init__(self):
        self._store: dict = {}

    def get_or_create(self, session_id: str) -> Tuple[BaseState, Dict[str, Any]]:
        if session_id not in self._store:
            self._store[session_id] = {
                "state": BaseState(),
                "memory": _empty_memory(),
            }
        s = self._store[session_id]
        return s["state"], s["memory"]

    def save_state(self, session_id: str, state: BaseState) -> None:
        self._store[session_id]["state"] = state


class CompletedStore:
    """최소 템플릿: 완료 이력 미사용 시 빈 구현."""

    def add(self, session_id: str, state: Any, memory_snapshot: Dict[str, Any]) -> None:
        pass
