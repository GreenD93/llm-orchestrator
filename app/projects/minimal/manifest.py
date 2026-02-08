"""
최소 manifest: raw_history-only 메모리, BaseState, schema/validator 없음.
"""

import importlib
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from app.core.agents.registry import build_runner
from app.core.memory import MemoryManager
from app.core.events import EventType

PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_class(module_path: str, project_module: str = "app.projects.minimal"):
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


def load_manifest(project_module: str = "app.projects.minimal") -> Dict[str, Any]:
    with open(PROJECT_ROOT / "project.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    state_manager_class = _resolve_class(data["state"]["manager"], project_module)
    from app.projects.minimal.state.stores import SessionStore, CompletedStore

    memory_manager = MemoryManager(enable_memory=True)

    agents_config = data.get("agents", {})
    agent_specs = {}
    for key, spec in agents_config.items():
        class_path = spec["class"]
        if "." not in class_path:
            class_path = f"agents.interaction_agent.agent.{class_path}"
        cls = _resolve_class(class_path, project_module)
        card = _load_card(spec["card"])
        agent_specs[key] = {"class": cls, "card": card, "stream": spec.get("stream", False)}

    runner = build_runner(agent_specs)

    router_class = _resolve_class(data["flows"]["router"], project_module)
    handlers_config = data["flows"]["handlers"]
    handlers = {
        flow_key: _resolve_class(handler_path, project_module)
        for flow_key, handler_path in handlers_config.items()
    }

    def on_error(e: Exception):
        return {
            "event": EventType.DONE,
            "payload": {
                "message": "처리 중 오류가 발생했어요. 다시 시도해주세요.",
                "next_action": "DONE",
                "ui_hint": {"type": "text", "fields": [], "buttons": []},
            },
        }

    def after_turn(ctx, payload: dict):
        memory_manager.update(ctx.memory, ctx.user_message, payload.get("message", ""))

    return {
        "sessions_factory": lambda: SessionStore(),
        "completed_factory": lambda: CompletedStore(),
        "memory_manager_factory": lambda: memory_manager,
        "runner": runner,
        "state": {"manager": state_manager_class},
        "flows": {"router": router_class, "handlers": handlers},
        "default_flow": "DEFAULT_FLOW",
        "on_error": on_error,
        "after_turn": after_turn,
    }
