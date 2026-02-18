# app/core/state/stores.py
"""
범용 인메모리 세션/이력 스토어.

프로덕션 환경에서는 Redis·RDB 기반 구현으로 교체 가능.
CoreOrchestrator가 기대하는 인터페이스:
  - SessionStore: get_or_create(session_id) → (state, memory)
                  save_state(session_id, state)
  - CompletedStore: add(session_id, state, memory_snapshot)
                    list_for_session(session_id) → list
"""

from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple


def _empty_memory() -> dict:
    return {"raw_history": [], "summary_text": ""}


class InMemorySessionStore:
    """
    세션별 (state, memory) 인메모리 저장소.

    사용법 (manifest.py):
        from app.core.state.stores import InMemorySessionStore
        "sessions_factory": lambda: InMemorySessionStore(state_factory=MyState),
    """

    def __init__(self, state_factory: Callable):
        self._store: dict = {}
        self._state_factory = state_factory

    def get_or_create(self, session_id: str) -> Tuple[Any, Dict[str, Any]]:
        if session_id not in self._store:
            self._store[session_id] = {
                "state": self._state_factory(),
                "memory": _empty_memory(),
            }
        s = self._store[session_id]
        return s["state"], s["memory"]

    def save_state(self, session_id: str, state: Any) -> None:
        if session_id in self._store:
            self._store[session_id]["state"] = state

    def reset(self, session_id: str) -> None:
        """세션 완전 초기화 (state + memory)."""
        self._store[session_id] = {
            "state": self._state_factory(),
            "memory": _empty_memory(),
        }


class InMemoryCompletedStore:
    """
    완료된 작업 이력 인메모리 저장소. 분석·디버그·히스토리 조회용.

    사용법 (manifest.py):
        from app.core.state.stores import InMemoryCompletedStore
        "completed_factory": lambda: InMemoryCompletedStore(),
    """

    def __init__(self, max_per_session: int = 50):
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self._max = max_per_session

    def add(
        self,
        session_id: str,
        state: Any,
        memory_snapshot: Dict[str, Any],
    ) -> None:
        self._store.setdefault(session_id, [])
        row = {
            "at": datetime.utcnow().isoformat() + "Z",
            "state": state.model_dump() if hasattr(state, "model_dump") else str(state),
            "summary_text": memory_snapshot.get("summary_text", ""),
        }
        self._store[session_id].append(row)
        if len(self._store[session_id]) > self._max:
            self._store[session_id] = self._store[session_id][-self._max:]

    def list_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(reversed(self._store.get(session_id, [])))
