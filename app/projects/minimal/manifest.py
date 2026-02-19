# app/projects/minimal/manifest.py
"""최소 서비스 manifest. 새 프로젝트를 만들 때 이 파일을 복사·수정하는 것이 출발점이다."""

from pathlib import Path
from typing import Any, Dict

from app.core.orchestration.manifest_loader import ManifestBuilder

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_MODULE = "app.projects.minimal"


def load_manifest() -> Dict[str, Any]:
    return (
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
        .class_name_map({
            "ChatAgent": "agents.chat_agent.agent.ChatAgent",
        })
        .build()
    )
