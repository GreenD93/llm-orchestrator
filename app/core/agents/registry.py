# app/core/agents/registry.py
"""spec 기반 agent registry: manifest의 agents spec으로 AgentExecutor dict 생성. schema/validator 선택은 여기서 수행."""

from typing import Any, Dict

from app.core.agents.agent_executor import AgentExecutor
from app.core.agents.execution_agent import ExecutionAgent


def build_executors(
    execution_agent: ExecutionAgent,
    agent_specs: Dict[str, Dict[str, Any]],
) -> Dict[str, AgentExecutor]:
    """
    agent_specs: { "intent": { "class": IntentAgent, "card": { "llm": {}, "policy": {} } }, ... }
    card의 policy에서 schema/validate 키로 정책 결정 후, ExecutionAgent에 넘길 값만 Executor에 전달.
    """
    executors = {}
    for key, spec in agent_specs.items():
        cls = spec["class"]
        card = spec.get("card", {})
        llm = card.get("llm", {})
        policy = card.get("policy", {})

        schema = policy.get("schema")
        validate_key = policy.get("validate")
        validator = (
            execution_agent.validator_map.get(validate_key) if validate_key else None
        )
        max_retry = policy.get("max_retry", 1)
        backoff_sec = policy.get("backoff_sec", 1)
        timeout_sec = policy.get("timeout_sec")

        system_prompt = getattr(cls, "get_system_prompt", None)
        if callable(system_prompt):
            system_prompt = system_prompt()
        else:
            system_prompt = "You are a helpful assistant."

        stream = spec.get("stream", False)
        agent = cls(
            system_prompt=system_prompt,
            llm_config=llm,
            stream=stream,
        )
        executors[key] = AgentExecutor(
            agent=agent,
            execution_agent=execution_agent,
            name=key,
            schema=schema,
            validator=validator,
            max_retry=max_retry,
            backoff_sec=backoff_sec,
            timeout_sec=timeout_sec,
        )
    return executors
