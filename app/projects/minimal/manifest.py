# app/projects/minimal/manifest.py
"""
최소 서비스 manifest.
새 프로젝트를 만들 때 이 파일을 복사·수정하는 것이 출발점이다.
"""

from pathlib import Path
from typing import Any, Dict

from app.core.memory import MemoryManager
from app.core.orchestration.defaults import make_error_event
from app.core.orchestration.manifest_loader import (
    load_yaml,
    resolve_class,
    build_agents_from_yaml,
)
from app.core.state.stores import InMemorySessionStore, InMemoryCompletedStore
from app.projects.minimal.state.models import MinimalState

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_MODULE = "app.projects.minimal"

_AGENT_CLASS_MAP = {
    "ChatAgent": "agents.chat_agent.agent.ChatAgent",
}


def load_manifest() -> Dict[str, Any]:
    data = load_yaml(PROJECT_ROOT)

    state_manager_class = resolve_class(data["state"]["manager"], PROJECT_MODULE)

    memory_manager = MemoryManager(enable_memory=True)

    runner = build_agents_from_yaml(
        data["agents"],
        PROJECT_MODULE,
        PROJECT_ROOT,
        class_name_map=_AGENT_CLASS_MAP,
    )

    router_class = resolve_class(data["flows"]["router"], PROJECT_MODULE)
    handlers = {
        flow_key: resolve_class(handler_path, PROJECT_MODULE)
        for flow_key, handler_path in data["flows"]["handlers"].items()
    }

    return {
        "sessions_factory":       lambda: InMemorySessionStore(state_factory=MinimalState),
        "completed_factory":      lambda: InMemoryCompletedStore(),
        "memory_manager_factory": lambda: memory_manager,
        "runner":                 runner,
        "state":                  {"manager": state_manager_class},
        "flows":                  {"router": router_class, "handlers": handlers},
        "default_flow":           "DEFAULT_FLOW",
        "on_error":               lambda e: make_error_event(),
        "after_turn":             None,
    }
