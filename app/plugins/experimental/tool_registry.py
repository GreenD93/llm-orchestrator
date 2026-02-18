# app/plugins/experimental/tool_registry.py
"""Agent가 사용할 Tool / MCP. Python 함수만 등록. (experimental)"""

from typing import Any, Callable, Dict

TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {}
