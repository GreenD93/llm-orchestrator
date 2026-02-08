"""LLM 없이 Flow 테스트용 Mock."""


class MockExecutor:
    def __init__(self, payload=None):
        self._payload = payload or {"message": "ok", "action": "DONE", "ui_hint": {}}

    def call(self, *args, stream=False, state=None, **kwargs):
        if stream:
            from app.core.events import EventType
            yield {"event": EventType.LLM_TOKEN, "payload": "x"}
            yield {"event": EventType.LLM_DONE, "payload": self._payload}
        else:
            return self._payload
