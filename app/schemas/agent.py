# app/schemas/agent.py

from pydantic import BaseModel
from typing import Dict, Any, List

class AgentChatRequest(BaseModel):
    session_id: str
    message: str

class AgentChatResponse(BaseModel):
    interaction: Dict[str, Any]
    hooks: List[Dict[str, Any]]
