"""LLM 없이 MinimalFlowHandler 단위 테스트 + manifest 조립 검증."""

import pytest
from app.core.events import EventType
from app.core.state import BaseState
from app.core.orchestration import CoreOrchestrator
from app.projects.minimal.flows.handlers import MinimalFlowHandler
from app.projects.minimal.manifest import load_manifest
from app.projects.minimal.tests.mock_llm import MockExecutor


def _mock_memory():
    return type("Memory", (), {"update": lambda *a, **k: None})()


def _mock_sessions():
    memory = {"raw_history": []}
    store = {}

    class S:
        def get_or_create(self, sid):
            if sid not in store:
                store[sid] = {"state": BaseState(), "memory": dict(memory)}
            s = store[sid]
            return s["state"], s["memory"]

        def save_state(self, sid, state):
            if sid not in store:
                store[sid] = {"state": state, "memory": dict(memory)}
            else:
                store[sid]["state"] = state

    return S()


def test_minimal_flow_handler_yields_done():
    executors = {"interaction": MockExecutor()}
    handler = MinimalFlowHandler(
        executors=executors,
        memory=_mock_memory(),
        sessions=_mock_sessions(),
        state_manager_factory=None,
        completed=None,
    )
    events = list(
        handler.run(
            session_id="test-session",
            state=BaseState(),
            memory={"raw_history": []},
            user_message="안녕",
        )
    )
    assert any(e.get("event") == EventType.DONE for e in events)
    done_ev = next(e for e in events if e.get("event") == EventType.DONE)
    assert "payload" in done_ev
    assert "message" in done_ev["payload"]


def test_minimal_manifest_builds_orchestrator():
    """manifest + 최소 agent + 최소 flow만으로 오케스트레이터 조립 가능."""
    manifest = load_manifest()
    orch = CoreOrchestrator(manifest)
    assert orch.flow_handlers.get("DEFAULT_FLOW") is not None
    assert orch._executors.get("interaction") is not None
