# app/core/tools/base_tool.py
"""
BaseTool: 재사용 가능한 Tool 기반 클래스.

─── 등록 흐름 ────────────────────────────────────────────────────────────────
  1. BaseTool 상속 → name·description 정의 → schema()·run() 구현
  2. app/core/tools/registry.py TOOL_REGISTRY에 한 줄 추가
  3. 사용할 Agent의 card.json "tools": ["tool_name"] 에 추가
  4. AgentRunner 빌드 시 build_tools()가 자동 주입

─── OpenAI function-calling 연동 ────────────────────────────────────────────
  schema() 반환값이 OpenAI function-calling 형식이어야 한다:
  {
      "type": "function",
      "function": {
          "name": "calculator",
          "description": "수식을 계산합니다.",
          "parameters": {
              "type": "object",
              "properties": {
                  "expression": {"type": "string", "description": "계산할 수식"}
              },
              "required": ["expression"],
          },
      },
  }

  BaseAgent.chat()이 tool-call 루프에서 schema()를 읽어 LLM에 전달하고,
  LLM이 tool_call을 반환하면 run(**args)을 호출한다.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """모든 Tool의 기반 클래스. name·description·schema·run 을 정의한다."""

    name: str           # tool 등록 키 (TOOL_REGISTRY + card.json "tools" 목록에서 사용)
    description: str    # 사람이 읽는 설명 (개발자용, LLM 프롬프트는 schema()에 포함)

    @abstractmethod
    def schema(self) -> dict:
        """
        OpenAI function-calling 형식의 tool 정의를 반환한다.
        LLM이 이 스키마를 읽고 언제·어떻게 tool을 호출할지 결정한다.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self, **kwargs) -> Any:
        """
        Tool을 실행하고 결과를 반환한다.

        Returns:
            str 또는 JSON-serializable 값.
            BaseAgent._execute_tool()이 str이 아니면 json.dumps()로 직렬화한다.
        """
        raise NotImplementedError
