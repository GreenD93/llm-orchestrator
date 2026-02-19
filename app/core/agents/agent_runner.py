# app/core/agents/agent_runner.py
"""
Agent 실행의 단일 진입점.

AgentRunner는 에이전트를 이름으로 조회하고, 재시도·검증·타임아웃 정책을 적용해 실행한다.
FlowHandler는 직접 Agent를 호출하지 않고 항상 Runner를 통한다.

─── 오류 분류 ──────────────────────────────────────────────────────────────
  RetryableError      — 재시도할 수 있는 오류 (검증 실패, 타임아웃, 알 수 없는 시나리오 등).
                        max_retry 소진 시 raise. FlowHandler가 catch해서 stage=FAILED 처리.

  FatalExecutionError — 재시도해도 해결 안 되는 오류 (예상치 못한 예외).
                        즉시 raise. Orchestrator의 handle_stream()이 catch해 error event emit.

─── 재시도 흐름 ────────────────────────────────────────────────────────────
  attempt 1: agent.run() → 성공 → return
             agent.run() → RetryableError → on_retry 콜백 → sleep → attempt 2
  attempt N(=max_retry): 실패 → context.metadata["execution"] 기록 → raise RetryableError
"""

import time
import traceback
from typing import Any, Callable, Dict, Generator, Optional

from pydantic import ValidationError

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.logging import setup_logger


class RetryableError(Exception):
    """재시도 가능한 오류. AgentRunner가 max_retry 안에서 자동 재시도한다."""


class FatalExecutionError(Exception):
    """재시도 불가 오류. 즉시 실패 처리되어 Orchestrator까지 전파된다."""


class AgentRunner:
    """
    Agent 이름 → Agent 인스턴스 레지스트리 + 실행 정책(재시도, 스키마 검증, 타임아웃).

    FlowHandler에서 사용 예시:
        result = self.runner.run("slot", ctx)         # 단건 실행
        yield from self.runner.run_stream("interaction", ctx)  # 스트리밍

    Attributes:
        _agents:          name → Agent 인스턴스
        _schema_registry: 스키마 이름 → Pydantic 모델 (결과 검증용)
        _validator_map:   검증 키 → 검증 함수 (lambda result: bool)
        _policy:          name → {schema, validate, max_retry, backoff_sec, timeout_sec}
    """

    def __init__(
        self,
        agents: Dict[str, Any],
        schema_registry: Optional[Dict[str, Any]] = None,
        validator_map: Optional[Dict[str, Callable]] = None,
        policy_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self._agents = agents
        self._schema_registry = schema_registry or {}
        self._validator_map = validator_map or {}
        self._policy = policy_by_name or {}
        self.logger = setup_logger("AgentRunner")

    def has_agent(self, name: str) -> bool:
        """에이전트 등록 여부 확인. Orchestrator가 IntentAgent 존재 여부를 체크할 때 사용."""
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
        에이전트를 동기 실행한다. 재시도·검증·타임아웃 정책을 적용한다.

        Args:
            agent_name: 실행할 에이전트 키 ("intent", "slot", ...)
            context:    실행 컨텍스트
            on_retry:   재시도 시 호출되는 콜백 (agent_name, attempt, max_retry, error_msg).
                        Orchestrator가 "재시도 중" 이벤트를 수집할 때 사용.
                        run()이 동기 블로킹이므로, 재시도 이벤트는 완료 후 순서대로 yield됨.

        Returns:
            에이전트 결과 dict. schema가 등록된 경우 Pydantic 모델로 검증 후 dict 반환.

        Raises:
            RetryableError:    max_retry 소진 시
            FatalExecutionError: 예상치 못한 예외 발생 시
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

                # 타임아웃 체크 (실행 후 검사)
                if timeout_sec and elapsed > timeout_sec:
                    raise RetryableError(f"timeout_exceeded: {elapsed:.2f}s > {timeout_sec}s")

                # 커스텀 검증 함수 (예: slot_ops, intent_scenario)
                if validator and not validator(result):
                    raise RetryableError("validation_failed")

                # Pydantic 스키마 검증 — dict 그대로 반환
                if schema and schema in self._schema_registry:
                    model = self._schema_registry[schema]
                    return model.model_validate(result).model_dump()
                return result

            except (RetryableError, ValidationError) as e:
                self.logger.warning(f"[{agent_name}] retry {attempt}/{max_retry}: {e}")

                if attempt >= max_retry:
                    # 재시도 소진 → 실행 오류를 context.metadata에 기록하고 raise
                    context.metadata["execution"] = {
                        "agent": agent_name, "error": str(e), "attempt": attempt,
                    }
                    raise

                # 다음 시도 전: on_retry 콜백 호출 → 슬립
                if on_retry:
                    on_retry(agent_name, attempt, max_retry, str(e))
                time.sleep(backoff_sec * attempt)

            except Exception as e:
                # 예상치 못한 오류 → 재시도 없이 FatalExecutionError로 래핑
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
        """
        에이전트를 스트리밍 실행한다.

        supports_stream=False 에이전트는 run()으로 폴백하여 단일 LLM_DONE 이벤트를 emit한다.
        스트리밍은 retry 로직 없이 1회 실행한다 (재시도가 필요하면 run()을 사용).
        """
        agent = self._agents.get(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")

        # supports_stream=False → run()으로 폴백 후 LLM_DONE 단일 이벤트 emit
        if not getattr(agent, "supports_stream", False):
            result = self.run(agent_name, context, **kwargs)
            yield {"event": EventType.LLM_DONE, "payload": result}
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
