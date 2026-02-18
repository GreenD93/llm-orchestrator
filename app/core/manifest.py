# app/core/manifest.py
"""공통 manifest 로더: project.yaml 기반으로 CoreOrchestrator에 전달할 dict 조립."""

import importlib
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml

from app.core.agents.registry import build_runner
from app.core.memory import MemoryManager
from app.core.events import EventType


def _resolve_class(module_path: str, project_module: str):
    """'module.sub.ClassName' → 실제 클래스 반환."""
    parts = module_path.rsplit(".", 1)
    if len(parts) == 1:
        raise ValueError(f"Expected 'module.ClassName', got {module_path}")
    mod_path, class_name = parts
    full_mod = f"{project_module}.{mod_path}"
    mod = importlib.import_module(full_mod)
    return getattr(mod, class_name)


def load_manifest_from_yaml(
    project_root: Path,
    project_module: str,
    *,
    sessions_factory: Callable,
    completed_factory: Optional[Callable] = None,
    default_flow: str = "DEFAULT_FLOW",
    intent_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """project.yaml 로드 → 클래스 resolve → manifest dict 반환.

    Args:
        project_root: project.yaml이 위치한 디렉토리 경로.
        project_module: 프로젝트 Python 모듈 경로 (e.g. "app.projects.transfer").
        sessions_factory: SessionStore 생성 팩토리.
        completed_factory: CompletedStore 생성 팩토리 (선택).
        default_flow: 기본 flow 이름.
        intent_agent: intent 에이전트 이름 (없으면 intent 라우팅 건너뜀).
    """
    with open(project_root / "project.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # State manager
    state_manager_class = _resolve_class(data["state"]["manager"], project_module)

    # Memory
    memory_manager = MemoryManager(enable_memory=True)

    # Agents: class 경로에서 직접 resolve (card 불필요)
    agents_config = data.get("agents", {})
    agent_specs = {}
    for key, spec in agents_config.items():
        class_path = spec["class"]
        cls = _resolve_class(class_path, project_module)
        agent_specs[key] = {"class": cls, "stream": spec.get("stream", False)}

    runner = build_runner(agent_specs)

    # Flows
    router_class = _resolve_class(data["flows"]["router"], project_module)
    handlers = {
        flow_key: _resolve_class(handler_path, project_module)
        for flow_key, handler_path in data["flows"]["handlers"].items()
    }

    # Hooks
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
        "sessions_factory": sessions_factory,
        "completed_factory": completed_factory or (lambda: None),
        "memory_manager_factory": lambda: memory_manager,
        "runner": runner,
        "state": {"manager": state_manager_class},
        "flows": {"router": router_class, "handlers": handlers},
        "default_flow": default_flow,
        "intent_agent": intent_agent,
        "on_error": on_error,
        "after_turn": after_turn,
    }
