# app/projects/transfer/tests/mock_llm.py
"""실제 LLM 호출 없이 FlowHandler 단위 테스트용 Mock."""


class MockAgent:
    def run(self, *args, **kwargs):
        return {"intent": "OTHER"}

    def run_stream(self, *args, **kwargs):
        yield {"event": "LLM_TOKEN", "payload": "테스트"}
        yield {"event": "LLM_DONE", "payload": {"message": "테스트 응답", "next_action": "DONE", "ui_hint": {}}}
