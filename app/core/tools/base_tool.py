# app/core/tools/base_tool.py
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    재사용 가능한 Tool 베이스 클래스.
    Agent card.json의 "tools" 필드에 이름을 등록하면 자동으로 주입됨.

    확장:
        1. BaseTool 상속 후 name·description 정의
        2. schema()와 run() 구현
        3. app/core/tools/registry.py TOOL_REGISTRY에 한 줄 추가
        4. 사용할 agent의 card.json "tools": ["tool_name"] 에 추가
    """

    name: str
    description: str

    @abstractmethod
    def schema(self) -> dict:
        """OpenAI function-calling 형식의 tool 정의."""
        raise NotImplementedError

    @abstractmethod
    def run(self, **kwargs) -> Any:
        """Tool 실행. str 또는 JSON-serializable 값 반환."""
        raise NotImplementedError
