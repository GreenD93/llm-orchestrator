# app/core/llm/openai_client.py
"""
OpenAI API 클라이언트 — BaseLLMClient 구현.

system_prompt를 messages 앞에 prepend하고, tool 스키마를 OpenAI 포맷으로 변환한다.
"""

import json
from typing import Generator

from openai import OpenAI

from app.core.config import settings
from app.core.llm.base_client import BaseLLMClient, LLMResponse, ToolCall


class OpenAIClient(BaseLLMClient):
    """OpenAI API 래퍼. BaseLLMClient 인터페이스 구현."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

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
        msgs = [{"role": "system", "content": system_prompt}, *messages]
        kwargs = dict(model=model, messages=msgs, temperature=temperature, timeout=timeout)
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0]

        tool_calls = []
        if getattr(choice.message, "tool_calls", None):
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return LLMResponse(
            content=(choice.message.content or "").strip() or None,
            tool_calls=tool_calls,
            _raw=choice.message,
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
        msgs = [{"role": "system", "content": system_prompt}, *messages]
        stream = self.client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            stream=True,
            timeout=timeout,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def build_assistant_message(self, response: LLMResponse) -> dict:
        """OpenAI message 객체를 그대로 반환 (SDK가 dict-like 처리)."""
        return response._raw

    def build_tool_result_message(self, tool_call_id: str, content: str) -> dict:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}
