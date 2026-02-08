"""Agent가 사용할 Tool / MCP. Python 함수만 등록. 필요 시 나중에 갈아끼우기. (experimental)"""

from typing import Any, Callable, Dict

TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {
    # "get_account_balance": get_account_balance,
    # "search_docs": search_docs,
}
