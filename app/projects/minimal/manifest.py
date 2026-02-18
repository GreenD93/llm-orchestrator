# app/projects/minimal/manifest.py
"""Minimal 프로젝트 manifest: 공통 로더 + 프로젝트별 팩토리만 선언."""

from pathlib import Path

from app.core.manifest import load_manifest_from_yaml
from app.projects.minimal.state.stores import SessionStore, CompletedStore

PROJECT_ROOT = Path(__file__).resolve().parent


def load_manifest(project_module: str = "app.projects.minimal"):
    return load_manifest_from_yaml(
        project_root=PROJECT_ROOT,
        project_module=project_module,
        sessions_factory=SessionStore,
        completed_factory=CompletedStore,
        default_flow="DEFAULT_FLOW",
    )
