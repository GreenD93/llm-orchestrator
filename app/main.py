# app/main.py
from fastapi import FastAPI

from app.core.config import settings
from app.core.orchestration import CoreOrchestrator
from app.core.api import create_agent_router
from app.projects.transfer.manifest import load_manifest

manifest = load_manifest()
orchestrator = CoreOrchestrator(manifest)
agent_router = create_agent_router(orchestrator)

app = FastAPI(title=settings.APP_NAME)
app.include_router(agent_router)
