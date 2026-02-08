# app/core/agents/agent_executor.py
"""Executor: 얇은 어댑터. stream/non-stream 분기, ExecutionAgent 호출, hooks·state 전달만 담당."""

from typing import Any, Callable, Generator, Optional

from app.core.agents.execution_agent import ExecutionAgent, FatalExecutionError, RetryableError


class AgentExecutor:
    """
    - 실행 정책(schema/validator/retry)은 ExecutionAgent와 registry에서 결정.
    - Executor는 stream 여부에 따라 run / run_stream 호출, on_success/on_failure, state 전달만 수행.
    """

    def __init__(
        self,
        *,
        agent: Any,
        execution_agent: ExecutionAgent,
        name: str,
        schema: Optional[str] = None,
        validator: Optional[Callable[[Any], bool]] = None,
        max_retry: int = 1,
        backoff_sec: int = 1,
        timeout_sec: Optional[int] = None,
        on_success: Optional[Callable[[Any], None]] = None,
        on_failure: Optional[Callable[[Exception], None]] = None,
    ):
        self.agent = agent
        self.exec = execution_agent
        self.name = name
        self.schema = schema
        self.validator = validator
        self.max_retry = max_retry
        self.backoff_sec = backoff_sec
        self.timeout_sec = timeout_sec
        self.on_success = on_success
        self.on_failure = on_failure

    def call(self, *args, stream: bool = False, state: Any = None, **kwargs):
        if stream and getattr(self.agent, "supports_stream", False):
            for ev in self.exec.run_stream(
                agent_name=self.name,
                call=lambda: self.agent.run_stream(*args, **kwargs),
                timeout_sec=self.timeout_sec,
                state=state,
            ):
                yield ev
            return
        try:
            result = self.exec.run(
                agent_name=self.name,
                call=lambda: self.agent.run(*args, **kwargs),
                schema=self.schema,
                validator=self.validator,
                max_retry=self.max_retry,
                backoff_sec=self.backoff_sec,
                timeout_sec=self.timeout_sec,
                state=state,
            )
            if self.on_success:
                self.on_success(result)
            return result
        except (RetryableError, FatalExecutionError) as e:
            if self.on_failure:
                self.on_failure(e)
            raise
