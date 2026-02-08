# app/core/agents/execution_agent.py
"""재시도, 스키마 검증, 타임아웃. schema_registry/validator_map은 manifest에서 주입."""

import time
import traceback
from typing import Any, Callable, Dict, Generator, Optional

from pydantic import ValidationError

from app.core.logging import setup_logger


class RetryableError(Exception):
    pass


class FatalExecutionError(Exception):
    pass


class ExecutionAgent:
    def __init__(
        self,
        schema_registry: Optional[Dict[str, Any]] = None,
        validator_map: Optional[Dict[str, Callable]] = None,
    ):
        self.schema_registry = schema_registry or {}
        self.validator_map = validator_map or {}
        self.logger = setup_logger("ExecutionAgent")

    def run(
        self,
        *,
        agent_name: str,
        call: Callable[[], Any],
        schema: Optional[str],
        validator: Optional[Callable],
        max_retry: int,
        backoff_sec: int,
        timeout_sec: Optional[int],
        state: Any = None,
    ):
        for attempt in range(1, max_retry + 1):
            started = time.monotonic()
            try:
                result = call()
                elapsed = time.monotonic() - started
                if timeout_sec and elapsed > timeout_sec:
                    raise RetryableError(f"timeout_exceeded: {elapsed:.2f}s > {timeout_sec}s")
                if validator and not validator(result):
                    raise RetryableError("validation_failed")
                if schema and schema in self.schema_registry:
                    model = self.schema_registry[schema]
                    parsed = model.model_validate(result)
                    return parsed.model_dump()
                return result
            except (RetryableError, ValidationError) as e:
                self.logger.warning(f"[{agent_name}] retry {attempt}/{max_retry}: {e}")
                if attempt >= max_retry:
                    if state:
                        state.meta["execution"] = {"agent": agent_name, "error": str(e), "attempt": attempt}
                    raise
                time.sleep(backoff_sec * attempt)
            except Exception as e:
                self.logger.error(f"[{agent_name}] fatal: {e}")
                if state:
                    state.meta["execution"] = {
                        "agent": agent_name,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    }
                raise FatalExecutionError(str(e))

    def run_stream(
        self,
        *,
        agent_name: str,
        call: Callable[[], Generator],
        timeout_sec: Optional[int],
        state: Any = None,
    ):
        started = time.monotonic()
        try:
            for event in call():
                if timeout_sec:
                    elapsed = time.monotonic() - started
                    if elapsed > timeout_sec:
                        raise RetryableError(f"stream_timeout_exceeded: {elapsed:.2f}s > {timeout_sec}s")
                yield event
        except Exception as e:
            self.logger.error(f"[{agent_name}] stream failed: {e}")
            if state:
                state.meta["execution"] = {
                    "agent": agent_name,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            raise
