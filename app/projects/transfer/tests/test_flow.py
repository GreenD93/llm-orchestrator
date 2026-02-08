# app/projects/transfer/tests/test_flow.py
"""실제 LLM 호출 없이 FlowHandler 단위 테스트."""

import pytest
from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler
from app.projects.transfer.flows.handlers import DefaultFlowHandler, TransferFlowHandler
from app.projects.transfer.state.models import TransferState
from app.projects.transfer.tests.mock_llm import MockAgent


def _mock_executors():
    """Mock executor: call() 시 고정 응답 반환."""
    class MockExecutor:
        def __init__(self, result):
            self._result = result
        def call(self, *args, stream=False, state=None, **kwargs):
            if stream:
                yield {"event": EventType.LLM_TOKEN, "payload": "x"}
                yield {"event": EventType.LLM_DONE, "payload": {"message": "ok", "next_action": "DONE", "ui_hint": {}}}
            else:
                return self._result
    return {
        "intent": MockExecutor({"intent": "OTHER"}),
        "slot": MockExecutor({"operations": []}),
        "interaction": MockExecutor(None),
    }


def _mock_memory():
    return type("Memory", (), {"update": lambda *a, **k: None, "_compress": lambda *a, **k: None})()


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
    executors = _mock_executors()
    executors["interaction"] = _mock_executors()["interaction"]
    handler = DefaultFlowHandler(
        executors=executors,
        memory=_mock_memory(),
        sessions=_mock_sessions(),
        state_manager_factory=None,
        completed=None,
    )
    events = list(handler.run(
        session_id="test-session",
        state=TransferState(),
        memory={"raw_history": [], "summary_text": "", "summary_struct": {}},
        user_message="안녕",
    ))
    assert any(e.get("event") == EventType.DONE for e in events)
