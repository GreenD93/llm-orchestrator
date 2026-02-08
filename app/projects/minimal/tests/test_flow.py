"""LLM 없이 MinimalFlowHandler 단위 테스트 + manifest 조립 검증."""

import pytest
from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.state import BaseState
from app.core.orchestration import CoreOrchestrator
from app.projects.minimal.flows.handlers import MinimalFlowHandler
from app.projects.minimal.manifest import load_manifest


def _mock_runner():
    class MockRunner:
        def run_stream(self, agent_name, ctx, **kwargs):
            yield {"event": EventType.LLM_TOKEN, "payload": "x"}
            yield {"event": EventType.LLM_DONE, "payload": {"message": "ok", "action": "DONE", "ui_hint": {}}}
    return MockRunner()


def _mock_memory_manager():
    return type("MM", (), {"update": lambda *a, **k: None})()


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
    handler = MinimalFlowHandler(
        runner=_mock_runner(),
        sessions=_mock_sessions(),
        memory_manager=_mock_memory_manager(),
        state_manager_factory=None,
        completed=None,
    )
    ctx = ExecutionContext(
        session_id="test-session",
        user_message="안녕",
        state=BaseState(),
        memory={"raw_history": []},
    )
    events = list(handler.run(ctx))
    assert any(e.get("event") == EventType.DONE for e in events)
    done_ev = next(e for e in events if e.get("event") == EventType.DONE)
    assert "payload" in done_ev
    assert "message" in done_ev["payload"]


def test_minimal_manifest_builds_orchestrator():
    """manifest + 최소 agent + 최소 flow만으로 오케스트레이터 조립 가능."""
    manifest = load_manifest()
    orch = CoreOrchestrator(manifest)
    assert orch._flow_handlers.get("DEFAULT_FLOW") is not None
    assert "interaction" in orch._runner._agents
