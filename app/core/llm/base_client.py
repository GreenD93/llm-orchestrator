# app/core/llm/base_client.py
"""
LLM 프로바이더 추상화 인터페이스.

모든 프로바이더(OpenAI, Anthropic 등)는 이 인터페이스를 구현한다.
BaseAgent는 BaseLLMClient만 사용하므로 프로바이더 교체가 투명하다.

─── 설계 원칙 ────────────────────────────────────────────────────────────────
  - system_prompt를 messages와 분리 전달. 프로바이더가 내부에서 적절히 처리.
    · OpenAI: messages 앞에 system 메시지로 prepend
    · Anthropic: system 파라미터로 전달 (messages에는 user/assistant만)
  - tool 스키마는 중립 포맷으로 전달. 프로바이더가 내부에서 자체 포맷으로 변환.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass
class ToolCall:
    """프로바이더 독립적 tool call 표현."""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """프로바이더 독립적 LLM 응답."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    _raw: Any = None  # 프로바이더별 원본 (tool-call 루프에서 assistant message 구성에 사용)


class BaseLLMClient(ABC):
    """LLM 프로바이더 인터페이스. OpenAI/Anthropic 등 구현."""

    @abstractmethod
    def chat(
        self,
        *,
        model: str,
        temperature: float,
        system_prompt: str,
        messages: list,
        timeout: int | None = None,
        tools: list | None = None,
    ) -> LLMResponse:
        """
        동기 LLM 호출.

        Args:
            model:         모델명 (예: "gpt-4o-mini", "claude-sonnet-4-20250514")
            temperature:   0=결정론적
            system_prompt: 시스템 프롬프트 (messages와 별도)
            messages:      [{"role": "user"|"assistant", "content": "..."}]
            timeout:       초 단위 타임아웃
            tools:         중립 포맷 tool 스키마 리스트
        """
        ...

    @abstractmethod
    def chat_stream(
        self,
        *,
        model: str,
        temperature: float,
        system_prompt: str,
        messages: list,
        timeout: int | None = None,
    ) -> Generator[str, None, None]:
        """스트리밍 LLM 호출. 토큰 문자열을 yield한다."""
        ...

    @abstractmethod
    def build_assistant_message(self, response: LLMResponse) -> dict:
        """tool-call 루프에서 assistant 메시지를 messages에 추가할 때 사용."""
        ...

    @abstractmethod
    def build_tool_result_message(self, tool_call_id: str, content: str) -> dict:
        """tool 실행 결과를 messages에 추가할 때 사용."""
        ...
