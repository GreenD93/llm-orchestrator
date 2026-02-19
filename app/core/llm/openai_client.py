# app/core/llm/openai_client.py
"""
OpenAI API 클라이언트 래퍼.

BaseAgent가 직접 사용하는 유일한 LLM 호출 레이어.
모델 교체(Anthropic, Gemini 등)가 필요하면 이 파일만 수정하거나
같은 인터페이스(chat / chat_stream)를 가진 클래스로 교체한다.

─── 인터페이스 ──────────────────────────────────────────────────────────────
  chat()        → OpenAI ChatCompletion 응답 객체 (동기)
  chat_stream() → 토큰 문자열 generator (스트리밍)
"""

from openai import OpenAI
from app.core.config import settings


class OpenAIClient:
    """OpenAI API 단순 래퍼. 인증·설정은 settings에서 주입."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def chat(
        self,
        *,
        model: str,
        temperature: float,
        messages: list,
        timeout: int | None = None,
        tools: list | None = None,
    ):
        """
        동기 ChatCompletion 호출.

        Args:
            model:       OpenAI 모델명 (예: "gpt-4o-mini", "gpt-4o")
            temperature: 0=결정론적, 높을수록 창의적
            messages:    [{"role": "system"|"user"|"assistant", "content": "..."}]
            timeout:     초 단위 타임아웃. None이면 OpenAI SDK 기본값 사용
            tools:       OpenAI function-calling 스키마 목록. None이면 tool 미사용

        Returns:
            openai.types.chat.ChatCompletion — choices[0].message.content로 접근
        """
        kwargs = dict(model=model, messages=messages, temperature=temperature, timeout=timeout)
        if tools:
            kwargs["tools"] = tools
        return self.client.chat.completions.create(**kwargs)

    def chat_stream(
        self,
        *,
        model: str,
        temperature: float,
        messages: list,
        timeout: int | None = None,
    ):
        """
        스트리밍 ChatCompletion 호출. 토큰 문자열을 yield한다.

        Notes:
            - stream=True로 고정. tools를 지원하지 않는다.
            - delta.content가 None인 청크(첫 번째·마지막 등)는 자동으로 건너뜀.

        Yields:
            str: LLM이 생성한 토큰 (delta.content)
        """
        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
            timeout=timeout,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
