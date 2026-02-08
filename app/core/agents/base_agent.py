# app/core/agents/base_agent.py
from typing import Any, Callable, Dict, Optional

from app.core.logging import setup_logger

from app.core.llm.openai_client import OpenAIClient

DEFAULT_LLM_CONFIG = {"model": "gpt-4o-mini", "temperature": 0}


class BaseAgent:
    """
    Agent는 계산만 담당.
    상태 관측, 훅, 이벤트는 Executor/Orchestrator 책임.
    tools = Python 함수 dict, retriever = search(query) 호출 가능 객체.
    """
    output_schema: Optional[str] = None
    supports_stream: bool = False

    def __init__(
        self,
        *,
        system_prompt: str,
        llm_config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        tools: Optional[Dict[str, Callable]] = None,
        retriever: Optional[Any] = None,
    ):
        cfg = llm_config or DEFAULT_LLM_CONFIG
        self.system_prompt = system_prompt
        self.model = cfg.get("model", "gpt-4o-mini")
        self.temperature = cfg.get("temperature", 0.0)
        self.timeout = cfg.get("timeout_sec")
        self.tools = tools or {}
        self.retriever = retriever
        self.llm = OpenAIClient()
        self.logger = setup_logger(self.__class__.__name__)

    def chat(self, messages: list) -> str:
        if not self.llm:
            raise RuntimeError("LLM client not configured")
        resp = self.llm.chat(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            timeout=self.timeout,
        )
        return resp.choices[0].message.content.strip()

    def chat_stream(self, messages: list):
        if not self.llm:
            raise RuntimeError("LLM client not configured")
        return self.llm.chat_stream(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            timeout=self.timeout,
        )

    def run(self, *args, **kwargs) -> dict:
        raise NotImplementedError

    def run_stream(self, *args, **kwargs):
        raise NotImplementedError
