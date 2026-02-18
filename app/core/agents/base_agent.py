# app/core/agents/base_agent.py
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Dict, List, Optional, Type

from pydantic import BaseModel

from app.core.logging import setup_logger
from app.core.llm.openai_client import OpenAIClient


@dataclass
class AgentPolicy:
    """에이전트 실행 정책: 재시도, 타임아웃, 검증."""
    max_retry: int = 1
    backoff_sec: int = 1
    timeout_sec: Optional[int] = None
    validator: Optional[Callable[[dict], bool]] = None


class BaseAgent:
    """
    Agent는 계산만 담당.
    상태 관측, 훅, 이벤트는 Executor/Orchestrator 책임.

    설정은 클래스 속성으로 선언하고, __init__에서 llm_config가 없으면 기본값 사용.
    """
    # --- Agent identity ---
    name: str = ""
    description: str = ""

    # --- Output type: Pydantic 모델 클래스 직접 참조 ---
    output_type: Optional[Type[BaseModel]] = None

    # --- LLM defaults ---
    default_model: str = "gpt-4o-mini"
    default_temperature: float = 0.0
    default_timeout_sec: Optional[int] = None

    # --- Execution policy ---
    policy: ClassVar[AgentPolicy] = AgentPolicy()

    # --- Tool support ---
    tools: List[Any] = []

    # --- Streaming ---
    supports_stream: bool = False

    def __init__(
        self,
        *,
        system_prompt: str = "",
        llm_config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        retriever: Optional[Any] = None,
    ):
        cfg = llm_config or {}
        self.system_prompt = system_prompt or ""
        self.model = cfg.get("model", self.default_model)
        self.temperature = cfg.get("temperature", self.default_temperature)
        self.timeout = cfg.get("timeout_sec", self.default_timeout_sec)
        self.retriever = retriever
        self.llm = OpenAIClient()
        self.logger = setup_logger(self.__class__.__name__)
        if stream:
            self.supports_stream = True

    def chat(self, messages: list) -> str:
        if not self.llm:
            raise RuntimeError("LLM client not configured")
        tools = self._get_openai_tools() if self.tools else None
        resp = self.llm.chat(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": self.system_prompt}, *messages],
            timeout=self.timeout,
            tools=tools,
        )
        choice = resp.choices[0]
        if choice.message.tool_calls:
            return self._handle_tool_calls(choice.message, messages)
        return choice.message.content.strip()

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

    def to_agent_card(self) -> dict:
        """A2A 호환 Agent Card 자동 생성."""
        return {
            "name": self.name or self.__class__.__name__,
            "description": self.description,
            "capabilities": {
                "streaming": self.supports_stream,
                "tools": [t.name for t in self.tools if hasattr(t, 'name')],
            },
        }

    # --- Tool support methods ---

    def _get_openai_tools(self) -> Optional[list]:
        """ToolDefinition 목록 → OpenAI function calling schema 변환."""
        if not self.tools:
            return None
        return [t.to_openai_schema() for t in self.tools if hasattr(t, 'to_openai_schema')]

    def _resolve_tool_call(self, name: str, args: dict) -> Any:
        """이름으로 tool 함수 실행."""
        for t in self.tools:
            if hasattr(t, 'name') and t.name == name:
                return t(**args)
        raise ValueError(f"Unknown tool: {name}")

    def _handle_tool_calls(self, message: Any, messages: list) -> str:
        """tool call 결과를 대화에 추가하고 재호출하는 루프."""
        import json
        current_messages = [{"role": "system", "content": self.system_prompt}, *messages]
        current_messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ],
        })
        for tc in message.tool_calls:
            args = json.loads(tc.function.arguments)
            result = self._resolve_tool_call(tc.function.name, args)
            current_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result,
            })
        tools = self._get_openai_tools()
        resp = self.llm.chat(
            model=self.model,
            temperature=self.temperature,
            messages=current_messages,
            timeout=self.timeout,
            tools=tools,
        )
        choice = resp.choices[0]
        if choice.message.tool_calls:
            return self._handle_tool_calls(choice.message, current_messages[1:])
        return choice.message.content.strip()
