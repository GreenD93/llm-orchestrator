# app/core/orchestration/manifest_loader.py
"""
새 프로젝트 manifest.py 작성 시 boilerplate를 줄여주는 공통 유틸리티.

사용법 (새 프로젝트 manifest.py):
    from app.core.orchestration.manifest_loader import (
        load_yaml, resolve_class, load_card, build_agents_from_yaml
    )

    PROJECT_ROOT = Path(__file__).resolve().parent
    PROJECT_MODULE = "app.projects.myproject"

    def load_manifest():
        data = load_yaml(PROJECT_ROOT)
        runner = build_agents_from_yaml(
            data["agents"], PROJECT_MODULE, PROJECT_ROOT,
            class_name_map={"ChatAgent": "agents.chat_agent.agent.ChatAgent"},
        )
        ...
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
            stream: true
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
        agent_specs[key] = {"class": cls, "card": card, "stream": spec.get("stream", False)}

    return build_runner(
        agent_specs,
        schema_registry=schema_registry or {},
        validator_map=validator_map or {},
    )
