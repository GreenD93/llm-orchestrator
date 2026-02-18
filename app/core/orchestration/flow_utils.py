# app/core/orchestration/flow_utils.py
"""Handler 공통: 메모리 갱신·세션 저장은 Orchestrator/after_turn에서 처리. 여기서는 헬퍼만."""

from typing import Any


def update_memory_and_save(
    memory_manager: Any,
    sessions: Any,
    session_id: str,
    state: Any,
    memory: dict,
    user_message: str,
    assistant_message: str,
) -> None:
    """메모리 갱신 후 세션 상태 저장. after_turn 훅에서 호출 가능."""
    memory_manager.update(memory, user_message, assistant_message)
    sessions.save_state(session_id, state)
