# app/core/agents/registry.py
"""문자열 → Agent 클래스 매핑. Runner 빌드는 build_runner에서 수행."""

from typing import Any, Dict, Optional, Type

from app.core.agents.agent_runner import AgentRunner
from app.core.agents.base_agent import BaseAgent


def get_registry(agent_specs: Dict[str, Dict[str, Any]]) -> Dict[str, Type[BaseAgent]]:
    """agent_specs에서 name -> Agent 클래스만 추출."""
    return {key: spec["class"] for key, spec in agent_specs.items()}


def build_runner(
    agent_specs: Dict[str, Dict[str, Any]],
    schema_registry: Optional[Dict[str, Any]] = None,
    validator_map: Optional[Dict[str, Any]] = None,
) -> AgentRunner:
    """spec으로 Agent 인스턴스 + 정책 생성 후 AgentRunner 반환."""
    agents = {}
    policy_by_name = {}
    for key, spec in agent_specs.items():
        cls = spec["class"]
        card = spec.get("card", {})
        llm = card.get("llm", {})
        policy = card.get("policy", {})

        schema = policy.get("schema")
        max_retry = policy.get("max_retry", 1)
        backoff_sec = policy.get("backoff_sec", 1)
        timeout_sec = policy.get("timeout_sec")
        policy_by_name[key] = {
            "schema": schema,
            "validate": policy.get("validate"),
            "max_retry": max_retry,
            "backoff_sec": backoff_sec,
            "timeout_sec": timeout_sec,
        }

        system_prompt = getattr(cls, "get_system_prompt", None)
        if callable(system_prompt):
            system_prompt = system_prompt()
        else:
            system_prompt = "You are a helpful assistant."
        stream = spec.get("stream", False)
        agents[key] = cls(
            system_prompt=system_prompt,
            llm_config=llm,
            stream=stream,
        )
    return AgentRunner(
        agents=agents,
        schema_registry=schema_registry or {},
        validator_map=validator_map or {},
        policy_by_name=policy_by_name,
    )
