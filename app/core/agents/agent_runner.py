# app/core/agents/agent_runner.py
"""Agent 실행 단일화: 재시도/검증/타임아웃 + run(context) 호출을 하나의 Runner에서 수행."""

import time
import traceback
from typing import Any, Dict, Generator, Optional

from pydantic import ValidationError

from app.core.context import ExecutionContext
from app.core.logging import setup_logger


class RetryableError(Exception):
    pass


class FatalExecutionError(Exception):
    pass


class AgentRunner:
    """
    Registry(name -> Agent 인스턴스) + 실행 정책(재시도, 스키마, 타임아웃).
    정책은 agent.policy, 스키마는 agent.output_type에서 직접 읽음.
    """

    def __init__(self, agents: Dict[str, Any]):
        self._agents = agents
        self.logger = setup_logger("AgentRunner")

    def run(self, agent_name: str, context: ExecutionContext, **kwargs) -> Any:
        agent = self._agents.get(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")

        policy = getattr(agent, "policy", None)
        max_retry = getattr(policy, "max_retry", 1) if policy else 1
        backoff_sec = getattr(policy, "backoff_sec", 1) if policy else 1
        timeout_sec = getattr(policy, "timeout_sec", None) if policy else None
        validator = getattr(policy, "validator", None) if policy else None
        output_type = getattr(agent, "output_type", None)

        for attempt in range(1, max_retry + 1):
            started = time.monotonic()
            try:
                result = agent.run(context, **kwargs)
                elapsed = time.monotonic() - started
                if timeout_sec and elapsed > timeout_sec:
                    raise RetryableError(f"timeout_exceeded: {elapsed:.2f}s > {timeout_sec}s")
                if validator and not validator(result):
                    raise RetryableError("validation_failed")
                if output_type is not None:
                    parsed = output_type.model_validate(result)
                    return parsed.model_dump()
                return result
            except (RetryableError, ValidationError) as e:
                self.logger.warning(f"[{agent_name}] retry {attempt}/{max_retry}: {e}")
                if attempt >= max_retry:
                    context.metadata.setdefault("execution", {"agent": agent_name, "error": str(e), "attempt": attempt})
                    raise
                time.sleep(backoff_sec * attempt)
            except Exception as e:
                self.logger.error(f"[{agent_name}] fatal: {e}")
                context.metadata.setdefault("execution", {
                    "agent": agent_name,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })
                raise FatalExecutionError(str(e))

    def run_stream(
        self,
        agent_name: str,
        context: ExecutionContext,
        timeout_sec: Optional[int] = None,
        **kwargs,
    ) -> Generator[Dict[str, Any], None, None]:
        agent = self._agents.get(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")
        if not getattr(agent, "supports_stream", False):
            result = self.run(agent_name, context, **kwargs)
            yield {"event": "LLM_DONE", "payload": result}
            return

        policy = getattr(agent, "policy", None)
        if timeout_sec is None:
            timeout_sec = getattr(policy, "timeout_sec", None) if policy else None
        started = time.monotonic()
        try:
            for event in agent.run_stream(context, **kwargs):
                if timeout_sec and (time.monotonic() - started) > timeout_sec:
                    raise RetryableError("stream_timeout_exceeded")
                yield event
        except Exception as e:
            self.logger.error(f"[{agent_name}] stream failed: {e}")
            context.metadata.setdefault("execution", {
                "agent": agent_name,
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            raise
