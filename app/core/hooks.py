# app/core/hooks.py
"""훅 타입 정의. 실제 사용하는 on_error / after_turn만 유지."""

from typing import Any, Callable, Optional

# on_error: (exception) -> dict (DONE payload)
# after_turn: (context, payload) -> None  # 메모리 갱신·요약 등

HookOnError = Optional[Callable[[Exception], dict]]
HookAfterTurn = Optional[Callable[[Any, dict], None]]
