# app/services/execution/execution_agent.py

import time
import traceback
from typing import Any, Callable, Generator
from pydantic import ValidationError

from app.core.logging import setup_logger
from app.services.events import EventType
from app.services.agents.schemas import IntentResult, SlotResult, InteractionResult


SCHEMA_REGISTRY = {
    "IntentResult": IntentResult,
    "SlotResult": SlotResult,
    "InteractionResult": InteractionResult,
}


class RetryableError(Exception):
    pass


class FatalExecutionError(Exception):
    pass


VALIDATOR_MAP = {
    "intent_enum": lambda v: isinstance(v, dict) and v.get("intent") in ("TRANSFER", "OTHER"),
    "slot_ops": lambda v: isinstance(v, dict) and "operations" in v,
}


class ExecutionAgent:
    def __init__(self):
        self.logger = setup_logger("ExecutionAgent")

    def run(
        self,
        *,
        agent_name: str,
        call: Callable[[], Any],
        schema: str | None,
        validator,
        max_retry: int,
        backoff_sec: int,
        state=None,
    ):
        for attempt in range(1, max_retry + 1):
            try:
                result = call()

                if validator and not validator(result):
                    raise RetryableError("validation_failed")

                if schema:
                    model = SCHEMA_REGISTRY[schema]
                    parsed = model.model_validate(result)
                    return parsed.model_dump()

                return result

            except (RetryableError, ValidationError) as e:
                self.logger.warning(
                    f"[{agent_name}] retry {attempt}/{max_retry}: {e}"
                )
                if attempt >= max_retry:
                    if state:
                        state.meta["execution"] = {
                            "agent": agent_name,
                            "error": str(e),
                        }
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
        state=None,
    ):
        try:
            for event in call():
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


class AgentExecutor:
    """
    - 실행
    - retry / schema / validation
    - FLOW hook 생성
    """

    def __init__(self, *, agent, execution_agent, name, policy):
        self.agent = agent
        self.exec = execution_agent
        self.name = name

        self.schema = policy.get("schema")
        self.validator = VALIDATOR_MAP.get(policy.get("validate"))
        self.max_retry = policy.get("max_retry", 1)
        self.backoff_sec = policy.get("backoff_sec", 1)

    def flow(self, *, step: str, state, extra=None):
        payload = {
            "stage": state.stage,
            "missing_required": state.missing_required,
        }
        if extra:
            payload.update(extra)

        return {
            "event": EventType.FLOW,
            "agent": self.name,
            "step": step,
            "payload": payload,
        }

    def call(self, *args, stream: bool = False, state=None, **kwargs):
        if stream and self.agent.supports_stream:
            yield self.flow(step="start", state=state)

            for ev in self.exec.run_stream(
                agent_name=self.name,
                call=lambda: self.agent.run_stream(*args, **kwargs),
                state=state,
            ):
                yield ev

            yield self.flow(step="done", state=state)
            return

        result = self.exec.run(
            agent_name=self.name,
            call=lambda: self.agent.run(*args, **kwargs),
            schema=self.schema,
            validator=self.validator,
            max_retry=self.max_retry,
            backoff_sec=self.backoff_sec,
            state=state,
        )

        return result
