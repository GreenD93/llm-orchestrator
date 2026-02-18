# app/core/orchestration/flow_utils.py
"""Handler 공통: 메모리 갱신 헬퍼. 세션 저장은 Orchestrator finally에서 한 번만 수행."""

from typing import Any


def update_memory(
    memory_manager: Any,
    memory: dict,
    user_message: str,
    assistant_message: str,
) -> None:
    """메모리만 갱신. 세션 저장은 Orchestrator에서 수행."""
    memory_manager.update(memory, user_message, assistant_message)
