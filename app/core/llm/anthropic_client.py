# app/core/llm/anthropic_client.py
"""
Anthropic API 클라이언트 — BaseLLMClient 구현.

system_prompt를 Anthropic의 system 파라미터로 전달하고,
messages에는 user/assistant만 포함한다.
tool 스키마는 Anthropic input_schema 포맷으로 변환한다.
"""

import json
from typing import Generator

from app.core.config import settings
from app.core.llm.base_client import BaseLLMClient, LLMResponse, ToolCall


class AnthropicClient(BaseLLMClient):
    """Anthropic API 래퍼. BaseLLMClient 인터페이스 구현."""

    def __init__(self):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

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
        kwargs = dict(
            model=model,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
        )
        if timeout:
            kwargs["timeout"] = timeout
        if tools:
            kwargs["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t["parameters"],
                }
                for t in tools
            ]

        resp = self.client.messages.create(**kwargs)

        content_text = ""
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else json.loads(block.input),
                ))

        return LLMResponse(
            content=content_text.strip() or None,
            tool_calls=tool_calls,
            _raw=resp,
        )

    def chat_stream(
        self,
        *,
        model: str,
        temperature: float,
        system_prompt: str,
        messages: list,
        timeout: int | None = None,
    ) -> Generator[str, None, None]:
        kwargs = dict(
            model=model,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
        )
        if timeout:
            kwargs["timeout"] = timeout

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    def build_assistant_message(self, response: LLMResponse) -> dict:
        """Anthropic 응답을 assistant 메시지로 변환."""
        raw = response._raw
        return {"role": "assistant", "content": raw.content}

    def build_tool_result_message(self, tool_call_id: str, content: str) -> dict:
        """Anthropic tool_result 포맷."""
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_call_id, "content": content}
            ],
        }
