# app/core/orchestration/flow_utils.py
"""FlowHandler 공통 헬퍼: history 조회, 메모리·상태 저장. Handler는 업무 순서만 정의."""

from typing import Any


def get_history(memory: dict, last_n: int = 6) -> list:
    """memory["raw_history"]에서 최근 last_n 턴 반환."""
    return memory.get("raw_history", [])[-last_n:]


def update_and_save(
    memory_manager: Any,
    sessions: Any,
    session_id: str,
    state: Any,
    memory: dict,
    user_message: str,
    assistant_message: str,
) -> None:
    """메모리 갱신 후 세션 상태 저장."""
    memory_manager.update(memory, user_message, assistant_message)
    sessions.save_state(session_id, state)
