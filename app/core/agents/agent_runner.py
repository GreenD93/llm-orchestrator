# app/core/agents/agent_runner.py
"""Agent 실행 단일화: 재시도/검증/타임아웃 + run(context) 호출을 하나의 Runner에서 수행."""

import time
import traceback
from typing import Any, Callable, Dict, Generator, Optional

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
    Agent는 run(context) -> dict 또는 run_stream(context) -> Generator만 제공.
    """

    def __init__(
        self,
        agents: Dict[str, Any],  # name -> agent instance
        schema_registry: Optional[Dict[str, Any]] = None,
        validator_map: Optional[Dict[str, Callable]] = None,
        policy_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self._agents = agents
        self._schema_registry = schema_registry or {}
        self._validator_map = validator_map or {}
        self._policy = policy_by_name or {}  # name -> { schema, validate, max_retry, backoff_sec, timeout_sec }
        self.logger = setup_logger("AgentRunner")

    def has_agent(self, name: str) -> bool:
        return name in self._agents

    def run(
        self,
        agent_name: str,
        context: ExecutionContext,
        *,
        on_retry: Optional[Callable[[str, int, int, str], None]] = None,
        **kwargs,
    ) -> Any:
        """
        on_retry: retry 발생 시 호출되는 콜백 (agent_name, attempt, max_retry, error_msg).
                  orchestrator가 이 콜백을 통해 "재시도 중" 이벤트를 수집할 수 있다.
        """
        agent = self._agents.get(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")
        policy = self._policy.get(agent_name, {})
        schema = policy.get("schema")
        validate_key = policy.get("validate")
        validator = self._validator_map.get(validate_key) if validate_key else None
        max_retry = policy.get("max_retry", 1)
        backoff_sec = policy.get("backoff_sec", 1)
        timeout_sec = policy.get("timeout_sec")

        for attempt in range(1, max_retry + 1):
            started = time.monotonic()
            try:
                result = agent.run(context, **kwargs)
                elapsed = time.monotonic() - started

                if timeout_sec and elapsed > timeout_sec:
                    raise RetryableError(f"timeout_exceeded: {elapsed:.2f}s > {timeout_sec}s")
                if validator and not validator(result):
                    raise RetryableError("validation_failed")

                # 스키마 등록된 경우 Pydantic 검증 후 dict 반환
                if schema and schema in self._schema_registry:
                    model = self._schema_registry[schema]
                    return model.model_validate(result).model_dump()
                return result

            except (RetryableError, ValidationError) as e:
                # 재시도 가능한 오류 — max_retry 소진 시 그대로 raise
                self.logger.warning(f"[{agent_name}] retry {attempt}/{max_retry}: {e}")
                if attempt >= max_retry:
                    context.metadata["execution"] = {"agent": agent_name, "error": str(e), "attempt": attempt}
                    raise
                if on_retry:
                    on_retry(agent_name, attempt, max_retry, str(e))
                time.sleep(backoff_sec * attempt)

            except Exception as e:
                # 예상치 못한 오류 — 재시도 없이 FatalExecutionError로 래핑
                self.logger.error(f"[{agent_name}] fatal: {e}")
                context.metadata["execution"] = {
                    "agent": agent_name,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
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

        # supports_stream=False인 경우 run()으로 폴백 후 단일 LLM_DONE 이벤트 emit
        if not getattr(agent, "supports_stream", False):
            result = self.run(agent_name, context, **kwargs)
            yield {"event": "LLM_DONE", "payload": result}
            return

        policy = self._policy.get(agent_name, {})
        timeout_sec = timeout_sec or policy.get("timeout_sec")
        started = time.monotonic()
        try:
            for event in agent.run_stream(context, **kwargs):
                if timeout_sec and (time.monotonic() - started) > timeout_sec:
                    raise RetryableError("stream_timeout_exceeded")
                yield event
        except Exception as e:
            self.logger.error(f"[{agent_name}] stream failed: {e}")
            context.metadata["execution"] = {
                "agent": agent_name,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            raise
