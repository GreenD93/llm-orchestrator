# app/core/tools/base_tool.py
"""
BaseTool: 재사용 가능한 Tool 기반 클래스.

─── 등록 흐름 ────────────────────────────────────────────────────────────────
  1. BaseTool 상속 → name·description 정의 → schema()·run() 구현
  2. app/core/tools/registry.py TOOL_REGISTRY에 한 줄 추가
  3. 사용할 Agent의 card.json "tools": ["tool_name"] 에 추가
  4. AgentRunner 빌드 시 build_tools()가 자동 주입

─── 프로바이더 중립 스키마 ─────────────────────────────────────────────────
  schema() 반환값은 프로바이더 독립적 포맷이다:
  {
      "name": "calculator",
      "description": "수식을 계산합니다.",
      "parameters": {
          "type": "object",
          "properties": {
              "expression": {"type": "string", "description": "계산할 수식"}
          },
          "required": ["expression"],
      },
  }

  각 LLM 클라이언트(OpenAI/Anthropic)가 chat() 내부에서 자체 포맷으로 변환한다:
  - OpenAI: {"type": "function", "function": schema}
  - Anthropic: {"name": ..., "description": ..., "input_schema": schema["parameters"]}
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
        프로바이더 중립 포맷의 tool 정의를 반환한다.
        {"name": ..., "description": ..., "parameters": {...}}
        LLM 클라이언트가 프로바이더별 포맷으로 변환한다.

        schema["description"]이 LLM이 읽는 유일한 설명이다.
        이 설명만으로 LLM이 "언제 사용할지, 어떤 파라미터를 넘길지" 판단할 수 있어야 한다.
        사용 예시를 포함하면 효과적이다.
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
