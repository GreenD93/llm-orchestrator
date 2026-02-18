# app/core/tools/decorator.py
"""@tool 데코레이터: Python 함수를 OpenAI function calling 호환 Tool로 변환."""

import inspect
import json
from typing import Any, Callable, Dict, Optional, get_type_hints


# Python type → JSON Schema type 매핑
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _python_type_to_json_schema(t: type) -> str:
    return _TYPE_MAP.get(t, "string")


class ToolDefinition:
    """함수를 래핑하여 OpenAI function calling schema를 자동 생성."""

    def __init__(self, func: Callable, *, name: Optional[str] = None, description: Optional[str] = None):
        self._func = func
        self.name = name or func.__name__
        self.description = description or (func.__doc__ or "").strip()
        self._hints = get_type_hints(func)
        self._sig = inspect.signature(func)

    def __call__(self, **kwargs) -> Any:
        return self._func(**kwargs)

    def to_openai_schema(self) -> Dict[str, Any]:
        """OpenAI function calling 호환 schema 생성."""
        properties = {}
        required = []
        for param_name, param in self._sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            param_type = self._hints.get(param_name, str)
            properties[param_name] = {
                "type": _python_type_to_json_schema(param_type),
                "description": "",
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


def tool(func: Optional[Callable] = None, *, name: Optional[str] = None, description: Optional[str] = None):
    """@tool 데코레이터. 함수를 ToolDefinition으로 래핑.

    사용법:
        @tool
        def get_balance(account_id: str) -> dict:
            '''계좌 잔액 조회'''
            return {"balance": 1000000}

        @tool(name="custom_name", description="커스텀 설명")
        def my_func(x: int) -> int:
            return x * 2
    """
    if func is not None:
        return ToolDefinition(func)

    def wrapper(fn: Callable) -> ToolDefinition:
        return ToolDefinition(fn, name=name, description=description)
    return wrapper
