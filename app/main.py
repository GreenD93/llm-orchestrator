# app/main.py

from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.routes_agent import router as agent_router

app = FastAPI(title=settings.APP_NAME)
app.include_router(agent_router)
