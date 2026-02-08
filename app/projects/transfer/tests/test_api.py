# app/projects/transfer/tests/test_api.py
"""단일 orchestrate API 기준 시나리오: Request/Response 스키마 검증."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_orchestrate_chat_accepts_request_schema(client: TestClient):
    """POST /v1/agent/chat 이 OrchestrateRequest를 받고 OrchestrateResponse 형태로 응답."""
    from app.main import orchestrator
    with patch.object(orchestrator, "handle", return_value={
        "interaction": {"message": "ok", "next_action": "DONE", "ui_hint": {}},
        "hooks": [],
    }):
        resp = client.post(
            "/v1/agent/chat",
            json={"session_id": "test-api-session", "message": "안녕"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "interaction" in data
    assert "hooks" in data
    assert isinstance(data["interaction"], dict)
    assert isinstance(data["hooks"], list)
    assert data["interaction"].get("message") == "ok"


def test_orchestrate_chat_stream_endpoint_exists(client: TestClient):
    """POST /v1/agent/chat/stream 엔드포인트 존재 및 SSE 형식."""
    from app.main import orchestrator
    def fake_stream(sid, msg):
        yield {"event": "DONE", "payload": {"message": "ok"}}
    with patch.object(orchestrator, "handle_stream", side_effect=fake_stream):
        resp = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": "test-stream", "message": "hi"},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
