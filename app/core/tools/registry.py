# app/core/tools/registry.py
"""Tool 이름 → 클래스 매핑. 새 Tool 추가 = 이 dict에 한 줄."""

from typing import Dict, List, Type

from app.core.tools.base_tool import BaseTool
from app.core.tools.calculator import Calculator

TOOL_REGISTRY: Dict[str, Type[BaseTool]] = {
    "calculator": Calculator,
    # 새 Tool 추가 예시:
    # "exchange_rate": ExchangeRateTool,
    # "account_lookup": AccountLookupTool,
}


def build_tools(names: List[str]) -> List[BaseTool]:
    """card.json "tools" 목록을 BaseTool 인스턴스 리스트로 변환."""
    tools = []
    for name in names:
        cls = TOOL_REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"Unknown tool: '{name}'. TOOL_REGISTRY에 등록하세요.")
        tools.append(cls())
    return tools
