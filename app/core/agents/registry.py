# app/core/agents/registry.py
"""
Agent 스펙(클래스 + card.json) → AgentRunner 빌드.

일반적으로 직접 호출하지 않고 manifest_loader.build_agents_from_yaml()을 통해 사용한다.

─── card.json 구조 ─────────────────────────────────────────────────────────
{
  "name": "MyAgent",
  "llm": {
    "model": "gpt-4o-mini",    // 사용할 OpenAI 모델
    "temperature": 0           // 0=결정론적, 높을수록 창의적
  },
  "policy": {
    "max_retry":   2,          // 최대 재시도 횟수 (기본 1)
    "backoff_sec": 1,          // 재시도 간격 (attempt * backoff_sec 초)
    "timeout_sec": 10,         // 실행 타임아웃 (초). 없으면 무제한.
    "validate":    "slot_ops", // validator_map 키. 결과 검증 함수 지정.
    "schema":      "SlotResult"// schema_registry 키. Pydantic 검증 후 dict 반환.
  },
  "tools": ["calculator"]      // 사용할 Tool 이름 목록. TOOL_REGISTRY에 등록된 것만.
}
"""

from typing import Any, Dict, Optional

from app.core.agents.agent_runner import AgentRunner
from app.core.tools.registry import build_tools


def build_runner(
    agent_specs: Dict[str, Dict[str, Any]],
    schema_registry: Optional[Dict[str, Any]] = None,
    validator_map: Optional[Dict[str, Any]] = None,
) -> AgentRunner:
    """
    Agent 스펙 딕셔너리로 AgentRunner를 빌드한다.

    Args:
        agent_specs: {
            "intent":  {"class": IntentAgentClass, "card": {...}, "stream": False},
            "slot":    {"class": SlotAgentClass,   "card": {...}, "stream": False},
        }
        schema_registry: 스키마 이름 → Pydantic 모델. AgentRunner에 전달.
        validator_map:   검증 키 → 검증 함수. AgentRunner에 전달.

    Returns:
        구성된 AgentRunner 인스턴스.
    """
    agents = {}
    policy_by_name = {}

    for key, spec in agent_specs.items():
        cls = spec["class"]
        card = spec.get("card", {})
        llm = card.get("llm", {})
        policy = card.get("policy", {})
        tool_names = card.get("tools", [])

        # card.json policy → AgentRunner 정책 변환
        policy_by_name[key] = {
            "schema":      policy.get("schema"),       # Pydantic 검증 스키마 이름
            "validate":    policy.get("validate"),     # 커스텀 검증 함수 키
            "max_retry":   policy.get("max_retry", 1),
            "backoff_sec": policy.get("backoff_sec", 1),
            "timeout_sec": policy.get("timeout_sec"),  # None이면 타임아웃 없음
        }

        # 시스템 프롬프트: get_system_prompt() classmethod 우선, 없으면 기본값
        system_prompt = getattr(cls, "get_system_prompt", None)
        if callable(system_prompt):
            system_prompt = system_prompt()
        else:
            system_prompt = "You are a helpful assistant."

        # 에이전트 인스턴스 생성 (card.json 설정 주입)
        agents[key] = cls(
            system_prompt=system_prompt,
            llm_config=llm,
            stream=spec.get("stream", False),
            tools=build_tools(tool_names) if tool_names else [],
        )

    return AgentRunner(
        agents=agents,
        schema_registry=schema_registry or {},
        validator_map=validator_map or {},
        policy_by_name=policy_by_name,
    )
