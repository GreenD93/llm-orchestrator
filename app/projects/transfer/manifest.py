# app/projects/transfer/manifest.py
"""
project.yaml 로드 → class path를 실제 클래스로 resolve → CoreOrchestrator에 전달할 dict 반환.
manifest는 조립용 데이터만 생성, 로직 없음.
"""

import importlib
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from app.core.agents import ExecutionAgent, build_executors
from app.core.memory import MemoryManager, SummarizerAgent
from app.core.events import EventType

# 프로젝트 루트 (이 파일 기준)
PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_class(module_path: str, project_module: str = "app.projects.transfer"):
    """'flows.router.TransferFlowRouter' → (module, 'TransferFlowRouter') → class."""
    parts = module_path.rsplit(".", 1)
    if len(parts) == 1:
        raise ValueError(f"Expected 'module.ClassName', got {module_path}")
    mod_path, class_name = parts
    full_mod = f"{project_module}.{mod_path}"
    mod = importlib.import_module(full_mod)
    return getattr(mod, class_name)


def _load_card(rel_path: str) -> Dict[str, Any]:
    path = PROJECT_ROOT / rel_path
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_manifest(project_module: str = "app.projects.transfer") -> Dict[str, Any]:
    """
    - project.yaml 로드
    - class path를 실제 클래스 객체로 resolve
    - CoreOrchestrator에 전달할 dict 반환
    """
    with open(PROJECT_ROOT / "project.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # State manager
    state_manager_class = _resolve_class(data["state"]["manager"], project_module)

    # Session / Completed store (transfer 전용)
    from app.projects.transfer.state.stores import SessionStore, CompletedStore

    # Memory
    summarizer = SummarizerAgent()
    def memory_manager_factory():
        return MemoryManager(summarizer=summarizer)

    # Execution: schema_registry, validator_map 은 transfer 스키마 사용
    from app.projects.transfer.agents import schemas as agent_schemas

    schema_registry = {
        "IntentResult": agent_schemas.IntentResult,
        "SlotResult": agent_schemas.SlotResult,
        "InteractionResult": agent_schemas.InteractionResult,
    }
    validator_map = {
        "intent_enum": lambda v: (
            isinstance(v, dict)
            and v.get("intent") in ("TRANSFER", "OTHER")
            and "supported" in v
        ),
        "slot_ops": lambda v: isinstance(v, dict) and "operations" in v,
    }

    def execution_agent_factory():
        return ExecutionAgent(schema_registry=schema_registry, validator_map=validator_map)

    # Agents: class path → class, card 로드
    agents_config = data.get("agents", {})
    agent_specs = {}
    for key, spec in agents_config.items():
        class_path = spec["class"]
        # project.yaml 에서 class가 "IntentAgent" 단일 이름이면 agents에서 매핑
        if "." not in class_path:
            agent_module_map = {
                "IntentAgent": "agents.intent_agent.agent.IntentAgent",
                "SlotFillerAgent": "agents.slot_filler_agent.agent.SlotFillerAgent",
                "InteractionAgent": "agents.interaction_agent.agent.InteractionAgent",
                "TransferExecuteAgent": "agents.transfer_execute_agent.agent.TransferExecuteAgent",
            }
            class_path = agent_module_map.get(class_path, f"agents.{key}.agent.{class_path}")
        cls = _resolve_class(class_path, project_module)
        card = _load_card(spec["card"])
        agent_specs[key] = {
            "class": cls,
            "card": card,
            "stream": spec.get("stream", False),
        }

    # Flows
    router_class = _resolve_class(data["flows"]["router"], project_module)
    handlers_config = data["flows"]["handlers"]
    handlers = {}
    for flow_key, handler_path in handlers_config.items():
        handlers[flow_key] = _resolve_class(handler_path, project_module)

    def executors_factory(execution_agent, agent_specs):
        return build_executors(execution_agent, agent_specs)

    def on_error(e: Exception):
        return {
            "event": EventType.DONE,
            "payload": {
                "message": "처리 중 오류가 발생했어요. 다시 시도해주세요.",
                "next_action": "DONE",
                "ui_hint": {"type": "text", "fields": [], "buttons": []},
            },
        }

    return {
        "sessions_factory": lambda: SessionStore(),
        "completed_factory": lambda: CompletedStore(),
        "memory_manager_factory": memory_manager_factory,
        "execution_agent_factory": execution_agent_factory,
        "executors_factory": executors_factory,
        "agents": agent_specs,
        "state": {"manager": state_manager_class},
        "flows": {"router": router_class, "handlers": handlers},
        "default_flow": "DEFAULT_FLOW",
        "on_error": on_error,
    }
