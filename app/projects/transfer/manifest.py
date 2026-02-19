# app/projects/transfer/manifest.py
"""이체 서비스 manifest: project.yaml → CoreOrchestrator에 전달할 dict 조립."""

from pathlib import Path
from typing import Any, Dict

from app.core.orchestration.manifest_loader import ManifestBuilder
from app.projects.transfer.agents import schemas as agent_schemas
from app.projects.transfer.state.stores import SessionStore, CompletedStore

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_MODULE = "app.projects.transfer"

_AGENT_CLASS_MAP = {
    "IntentAgent":          "agents.intent_agent.agent.IntentAgent",
    "SlotFillerAgent":      "agents.slot_filler_agent.agent.SlotFillerAgent",
    "InteractionAgent":     "agents.interaction_agent.agent.InteractionAgent",
    "TransferExecuteAgent": "agents.transfer_execute_agent.agent.TransferExecuteAgent",
}

_SCHEMA_REGISTRY = {
    "IntentResult":      agent_schemas.IntentResult,
    "SlotResult":        agent_schemas.SlotResult,
    "InteractionResult": agent_schemas.InteractionResult,
}

_VALIDATOR_MAP = {
    "intent_scenario": lambda v: isinstance(v, dict) and isinstance(v.get("scenario"), str),
    "slot_ops":        lambda v: isinstance(v, dict) and "operations" in v,
}


def load_manifest() -> Dict[str, Any]:
    return (
        ManifestBuilder(PROJECT_ROOT, PROJECT_MODULE)
        .class_name_map(_AGENT_CLASS_MAP)
        .schema_registry(_SCHEMA_REGISTRY)
        .validator_map(_VALIDATOR_MAP)
        .sessions_factory(SessionStore)
        .completed_factory(CompletedStore)
        .memory(
            summary_system_prompt=(
                "You are a banking assistant conversation summarizer. "
                "Accurately preserve all transfer-related facts."
            ),
            summary_user_template=(
                "Summarize this bank transfer service conversation into 3-5 sentences.\n"
                "Must preserve: recipient names, amounts, transfer dates, "
                "completed/cancelled transfers, and any pending requests.\n"
                "Drop: greetings, repeated confirmations, filler phrases.\n\n"
                "{memory_block}"
                "Additional dialogue:\n"
                "{dialog}\n\n"
                "Summary:"
            ),
        )
        .build()
    )
