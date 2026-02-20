# app/core/orchestration/manifest_loader.py
"""
새 프로젝트 manifest.py 작성 시 boilerplate를 줄여주는 공통 유틸리티.

─── 사용법 1: 유틸리티 함수 (기존) ────────────────────────────────────────────
    from app.core.orchestration.manifest_loader import (
        load_yaml, resolve_class, load_card, build_agents_from_yaml
    )

─── 사용법 2: ManifestBuilder (권장) ──────────────────────────────────────────
    from app.core.orchestration.manifest_loader import ManifestBuilder

    def load_manifest():
        return (
            ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
            .class_name_map({"ChatAgent": "agents.chat_agent.agent.ChatAgent"})
            .build()
        )
"""

import importlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.core.agents.registry import build_runner


def resolve_class(module_path: str, project_module: str):
    """
    'module.ClassName' 형태의 경로를 파이썬 클래스로 변환.

    Args:
        module_path: 'flows.router.MyRouter' 형태 (project_module 기준 상대 경로)
        project_module: 'app.projects.myproject' 같은 패키지 루트

    Example:
        cls = resolve_class("flows.router.TransferFlowRouter", "app.projects.transfer")
    """
    parts = module_path.rsplit(".", 1)
    if len(parts) == 1:
        raise ValueError(f"Expected 'module.ClassName', got '{module_path}'")
    mod_path, class_name = parts
    full_mod = f"{project_module}.{mod_path}"
    mod = importlib.import_module(full_mod)
    return getattr(mod, class_name)


def load_card(rel_path: str, project_root: Path) -> Dict[str, Any]:
    """card.json 파일을 dict로 로드."""
    with open(project_root / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(project_root: Path) -> Dict[str, Any]:
    """project.yaml 파일을 dict로 로드."""
    with open(project_root / "project.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_agents_from_yaml(
    agents_config: Dict[str, Any],
    project_module: str,
    project_root: Path,
    schema_registry: Optional[Dict[str, Any]] = None,
    validator_map: Optional[Dict[str, Any]] = None,
    class_name_map: Optional[Dict[str, str]] = None,
) -> Any:  # AgentRunner
    """
    project.yaml의 agents 섹션을 파싱하여 AgentRunner를 빌드.

    class_name_map: 단순 클래스명 → 전체 점-경로 매핑.
                    project.yaml에 짧은 이름('ChatAgent')만 쓰고 싶을 때 사용.

    project.yaml 예시:
        agents:
          chat:
            class: ChatAgent                         # 단순 이름 → class_name_map 필요
            card: agents/chat_agent/card.json
          intent:
            class: agents.intent_agent.agent.IntentAgent  # 전체 경로도 OK
            card: agents/intent_agent/card.json
    """
    agent_specs = {}
    for key, spec in agents_config.items():
        class_path = spec["class"]
        if "." not in class_path:
            if class_name_map and class_path in class_name_map:
                class_path = class_name_map[class_path]
            else:
                raise ValueError(
                    f"Agent class '{class_path}' (key='{key}') has no module path. "
                    f"Use full path like 'agents.my_agent.agent.MyAgent' "
                    f"or provide it in class_name_map."
                )
        cls = resolve_class(class_path, project_module)
        card = load_card(spec["card"], project_root)
        agent_specs[key] = {"class": cls, "card": card}

    return build_runner(
        agent_specs,
        schema_registry=schema_registry or {},
        validator_map=validator_map or {},
    )


# ── ManifestBuilder ──────────────────────────────────────────────────────────


class ManifestBuilder:
    """
    project.yaml 기반 manifest dict 자동 조립. 기본값으로 동작, 필요한 부분만 override.

    최소 사용:
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
            .class_name_map({"ChatAgent": "agents.chat_agent.agent.ChatAgent"})
            .build()

    복잡 사용:
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
            .class_name_map(_MAP)
            .schema_registry(_SCHEMAS)
            .validator_map(_VALIDATORS)
            .memory(summary_system_prompt="...", summary_user_template="...")
            .sessions_factory(SessionStore)
            .completed_factory(CompletedStore)
            .hook_handlers({"transfer_completed": handler})
            .build()
    """

    def __init__(self, project_root: Path, project_module: str):
        self._project_root = project_root
        self._project_module = project_module
        self._class_name_map: Dict[str, str] = {}
        self._schema_registry: Dict[str, Any] = {}
        self._validator_map: Dict[str, Any] = {}
        self._memory_kwargs: Dict[str, Any] = {}
        self._sessions_factory = None
        self._completed_factory = None
        self._hook_handlers: Dict[str, Any] = {}
        self._on_error = None
        self._after_turn = None

    def class_name_map(self, m: Dict[str, str]) -> "ManifestBuilder":
        self._class_name_map = m
        return self

    def schema_registry(self, r: Dict[str, Any]) -> "ManifestBuilder":
        self._schema_registry = r
        return self

    def validator_map(self, m: Dict[str, Any]) -> "ManifestBuilder":
        self._validator_map = m
        return self

    def memory(self, **kwargs) -> "ManifestBuilder":
        """MemoryManager 생성자에 전달할 kwargs. (summary_system_prompt, summary_user_template 등)"""
        self._memory_kwargs = kwargs
        return self

    def sessions_factory(self, factory) -> "ManifestBuilder":
        self._sessions_factory = factory
        return self

    def completed_factory(self, factory) -> "ManifestBuilder":
        self._completed_factory = factory
        return self

    def hook_handlers(self, h: Dict[str, Any]) -> "ManifestBuilder":
        self._hook_handlers = h
        return self

    def on_error(self, handler) -> "ManifestBuilder":
        self._on_error = handler
        return self

    def after_turn(self, handler) -> "ManifestBuilder":
        self._after_turn = handler
        return self

    def build(self) -> Dict[str, Any]:
        """CoreOrchestrator가 기대하는 manifest dict 반환."""
        from app.core.memory import MemoryManager
        from app.core.orchestration.defaults import make_error_event
        from app.core.state.stores import InMemorySessionStore, InMemoryCompletedStore

        data = load_yaml(self._project_root)

        # State Manager
        state_manager_class = resolve_class(data["state"]["manager"], self._project_module)

        # Memory Manager
        memory_manager = MemoryManager(enable_memory=True, **self._memory_kwargs)

        # Agent Runner
        runner = build_agents_from_yaml(
            data["agents"],
            self._project_module,
            self._project_root,
            schema_registry=self._schema_registry,
            validator_map=self._validator_map,
            class_name_map=self._class_name_map,
        )

        # Flow Router + Handlers
        router_class = resolve_class(data["flows"]["router"], self._project_module)
        handlers = {
            flow_key: resolve_class(handler_path, self._project_module)
            for flow_key, handler_path in data["flows"]["handlers"].items()
        }

        # Sessions factory — 미지정이면 project.yaml의 state.model로 자동 구성
        sessions_factory = self._sessions_factory
        if sessions_factory is None:
            state_model_path = data.get("state", {}).get("model")
            if state_model_path:
                state_class = resolve_class(state_model_path, self._project_module)
            else:
                raise ValueError(
                    "sessions_factory가 미지정이고 project.yaml에 state.model도 없습니다. "
                    "둘 중 하나를 제공해주세요."
                )
            sessions_factory = lambda: InMemorySessionStore(state_factory=state_class)

        # Completed factory
        completed_factory = self._completed_factory
        if completed_factory is None:
            completed_factory = lambda: InMemoryCompletedStore()

        # Default flow
        default_flow = list(data["flows"]["handlers"].keys())[0]

        return {
            "sessions_factory":       sessions_factory,
            "completed_factory":      completed_factory,
            "memory_manager_factory": lambda: memory_manager,
            "runner":                 runner,
            "state":                  {"manager": state_manager_class},
            "flows":                  {"router": router_class, "handlers": handlers},
            "default_flow":           default_flow,
            "on_error":               self._on_error or (lambda e: make_error_event(e)),
            "after_turn":             self._after_turn,
            "hook_handlers":          self._hook_handlers,
        }
