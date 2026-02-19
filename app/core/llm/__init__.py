# app/core/llm/__init__.py
from app.core.llm.base_client import BaseLLMClient, LLMResponse, ToolCall


def create_llm_client(provider: str = "openai") -> BaseLLMClient:
    """프로바이더 이름으로 LLM 클라이언트 인스턴스를 생성한다."""
    if provider == "openai":
        from app.core.llm.openai_client import OpenAIClient
        return OpenAIClient()
    if provider == "anthropic":
        from app.core.llm.anthropic_client import AnthropicClient
        return AnthropicClient()
    raise ValueError(f"Unknown LLM provider: {provider}")


__all__ = ["BaseLLMClient", "LLMResponse", "ToolCall", "create_llm_client"]
