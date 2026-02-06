# app/services/events.py
from enum import Enum


class EventType(str, Enum):
    LLM_TOKEN = "LLM_TOKEN"
    LLM_DONE = "LLM_DONE"
    FLOW = "FLOW"
    DONE = "DONE"
