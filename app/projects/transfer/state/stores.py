# app/projects/transfer/state/stores.py
from datetime import datetime
from typing import Any, Dict, List, Tuple

from app.projects.transfer.state.models import TransferState


def _empty_memory() -> dict:
    return {"raw_history": [], "summary_text": "", "summary_struct": {}}


class SessionStore:
    def __init__(self):
        self._store: dict = {}

    def get_or_create(self, session_id: str) -> Tuple[TransferState, Dict[str, Any]]:
        if session_id not in self._store:
            self._store[session_id] = {
                "state": TransferState(),
                "memory": _empty_memory(),
            }
        s = self._store[session_id]
        return s["state"], s["memory"]

    def save_state(self, session_id: str, state: TransferState) -> None:
        self._store[session_id]["state"] = state

    def reset_full(self, session_id: str) -> None:
        self._store[session_id] = {"state": TransferState(), "memory": _empty_memory()}


class CompletedStore:
    def __init__(self, max_per_session: int = 50):
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self._max = max_per_session

    def add(
        self,
        session_id: str,
        state: TransferState,
        memory_snapshot: Dict[str, Any],
    ) -> None:
        self._store.setdefault(session_id, [])
        row = {
            "at": datetime.utcnow().isoformat() + "Z",
            "state": state.model_dump(),
            "summary_text": memory_snapshot.get("summary_text", ""),
            "summary_struct": memory_snapshot.get("summary_struct", {}),
        }
        self._store[session_id].append(row)
        if len(self._store[session_id]) > self._max:
            self._store[session_id] = self._store[session_id][-self._max :]

    def list_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(reversed(self._store.get(session_id, [])))
