# app/projects/transfer/tests/test_flow.py
"""실제 LLM 호출 없이 FlowHandler 단위 테스트."""

import pytest
from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler
from app.projects.transfer.flows.handlers import DefaultFlowHandler, TransferFlowHandler
from app.projects.transfer.state.models import TransferState


def _mock_runner():
    """Mock runner: run / run_stream 시 고정 응답 반환."""
    class MockRunner:
        def run(self, agent_name: str, ctx: ExecutionContext, **kwargs):
            if agent_name == "intent":
                return {"intent": "OTHER", "supported": False}
            if agent_name == "slot":
                return {"operations": []}
            if agent_name == "execute":
                return {"success": True}
            return {}

        def run_stream(self, agent_name: str, ctx: ExecutionContext, **kwargs):
            yield {"event": EventType.LLM_TOKEN, "payload": "x"}
            yield {"event": EventType.LLM_DONE, "payload": {"message": "ok", "next_action": "DONE", "ui_hint": {}}}
    return MockRunner()


def _mock_memory_manager():
    return type("MM", (), {"update": lambda *a, **k: None})()


def _mock_sessions():
    memory = {"raw_history": [], "summary_text": "", "summary_struct": {}}
    store = {}

    class S:
        def get_or_create(self, sid):
            if sid not in store:
                store[sid] = {"state": TransferState(), "memory": dict(memory)}
            s = store[sid]
            return s["state"], s["memory"]

        def save_state(self, sid, state):
            if sid not in store:
                store[sid] = {"state": state, "memory": dict(memory)}
            else:
                store[sid]["state"] = state
    return S()


def test_default_flow_handler_yields_done():
    handler = DefaultFlowHandler(
        runner=_mock_runner(),
        sessions=_mock_sessions(),
        memory_manager=_mock_memory_manager(),
        state_manager_factory=None,
        completed=None,
    )
    ctx = ExecutionContext(
        session_id="test-session",
        user_message="안녕",
        state=TransferState(),
        memory={"raw_history": [], "summary_text": "", "summary_struct": {}},
    )
    events = list(handler.run(ctx))
    assert any(e.get("event") == EventType.DONE for e in events)
