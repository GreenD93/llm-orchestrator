# app/core/agents/registry.py
"""Agent 인스턴스 생성 + Runner 빌드. 정책/스키마는 agent 클래스 속성에서 읽음."""

from typing import Any, Dict

from app.core.agents.agent_runner import AgentRunner


def build_runner(agent_specs: Dict[str, Dict[str, Any]]) -> AgentRunner:
    """spec으로 Agent 인스턴스 생성 후 AgentRunner 반환.
    정책/스키마는 agent 인스턴스의 policy, output_type 속성에서 직접 읽으므로
    schema_registry, validator_map 파라미터 불필요.
    """
    agents = {}
    for key, spec in agent_specs.items():
        cls = spec["class"]

        system_prompt = getattr(cls, "get_system_prompt", None)
        if callable(system_prompt):
            system_prompt = system_prompt()
        else:
            system_prompt = "You are a helpful assistant."

        stream = spec.get("stream", False)
        agents[key] = cls(
            system_prompt=system_prompt,
            stream=stream,
        )
    return AgentRunner(agents=agents)
