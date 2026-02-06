# app/services/agents/registry.py

import json
from pathlib import Path
from typing import Any, Dict, Type

from app.services.agents.base_agent import BaseAgent
from app.services.agents.intent.agent import IntentAgent
from app.services.agents.slot_filler.agent import SlotFillerAgent
from app.services.agents.interaction.agent import InteractionAgent

_AGENTS_DIR = Path(__file__).resolve().parent

_AGENT_SPECS = [
    ("intent", IntentAgent, "intent/card.json"),
    ("slot", SlotFillerAgent, "slot_filler/card.json"),
    ("interaction", InteractionAgent, "interaction/card.json"),
]


def _load_card(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_registry() -> Dict[str, Dict[str, Any]]:
    registry = {}

    for key, cls, card_rel in _AGENT_SPECS:
        card = _load_card(_AGENTS_DIR / card_rel)

        registry[key] = {
            "class": cls,
            "llm": card.get("llm", {}),
            "policy": card.get("policy", {}),
        }

    return registry


AGENT_REGISTRY = _build_registry()
