# app/projects/transfer/manifest.py
"""이체 서비스 manifest: project.yaml → CoreOrchestrator에 전달할 dict 조립."""

from pathlib import Path
from typing import Any, Dict

from app.core.memory import MemoryManager
from app.core.orchestration.defaults import make_error_event
from app.core.orchestration.manifest_loader import (
    load_yaml,
    resolve_class,
    build_agents_from_yaml,
)
from app.projects.transfer.agents import schemas as agent_schemas
from app.projects.transfer.state.stores import SessionStore, CompletedStore

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_MODULE = "app.projects.transfer"

# project.yaml의 짧은 class 이름 → 전체 경로 매핑
_AGENT_CLASS_MAP = {
    "IntentAgent":          "agents.intent_agent.agent.IntentAgent",
    "SlotFillerAgent":      "agents.slot_filler_agent.agent.SlotFillerAgent",
    "InteractionAgent":     "agents.interaction_agent.agent.InteractionAgent",
    "TransferExecuteAgent": "agents.transfer_execute_agent.agent.TransferExecuteAgent",
}

_SCHEMA_REGISTRY = {
    "IntentResult":      agent_schemas.IntentResult,
    "SlotResult":        agent_schemas.SlotResult,
    "InteractionResult": agent_schemas.InteractionResult,
}

_VALIDATOR_MAP = {
    "intent_scenario": lambda v: isinstance(v, dict) and isinstance(v.get("scenario"), str),
    "slot_ops":        lambda v: isinstance(v, dict) and "operations" in v,
}


def load_manifest() -> Dict[str, Any]:
    data = load_yaml(PROJECT_ROOT)

    # State Manager
    state_manager_class = resolve_class(data["state"]["manager"], PROJECT_MODULE)

    # Memory Manager (이체 도메인 특화 요약 프롬프트)
    memory_manager = MemoryManager(
        enable_memory=True,
        summary_system_prompt=(
            "You are a banking assistant conversation summarizer. "
            "Accurately preserve all transfer-related facts."
        ),
        summary_user_template=(
            "Summarize this bank transfer service conversation into 3-5 sentences.\n"
            "Must preserve: recipient names, amounts, transfer dates, "
            "completed/cancelled transfers, and any pending requests.\n"
            "Drop: greetings, repeated confirmations, filler phrases.\n\n"
            "{memory_block}"
            "Additional dialogue:\n"
            "{dialog}\n\n"
            "Summary:"
        ),
    )

    # Agent Runner
    runner = build_agents_from_yaml(
        data["agents"],
        PROJECT_MODULE,
        PROJECT_ROOT,
        schema_registry=_SCHEMA_REGISTRY,
        validator_map=_VALIDATOR_MAP,
        class_name_map=_AGENT_CLASS_MAP,
    )

    # Flow Router + Handlers
    router_class = resolve_class(data["flows"]["router"], PROJECT_MODULE)
    handlers = {
        flow_key: resolve_class(handler_path, PROJECT_MODULE)
        for flow_key, handler_path in data["flows"]["handlers"].items()
    }

    return {
        "sessions_factory":      SessionStore,
        "completed_factory":     CompletedStore,
        "memory_manager_factory": lambda: memory_manager,
        "runner":                runner,
        "state":                 {"manager": state_manager_class},
        "flows":                 {"router": router_class, "handlers": handlers},
        "default_flow":          "DEFAULT_FLOW",
        "on_error":              lambda e: make_error_event(),
        "after_turn":            None,
    }
