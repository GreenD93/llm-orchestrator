# app/core/hooks.py
"""이벤트 시스템 제거. before_agent / after_agent / on_error 훅만 유지."""

from typing import Any, Callable, Optional

# 훅 시그니처 (선택)
# before_agent: (context, agent_name) -> None
# after_agent: (context, agent_name, result) -> None
# on_error: (exception) -> dict (DONE payload)
# after_turn: (context, payload) -> None  # 메모리 갱신·요약 등

HookBeforeAgent = Optional[Callable[[Any, str], None]]
HookAfterAgent = Optional[Callable[[Any, str, Any], None]]
HookOnError = Optional[Callable[[Exception], dict]]
HookAfterTurn = Optional[Callable[[Any, dict], None]]
