# app/core/orchestration/orchestrator.py
from typing import Any, Dict, Generator

from app.core.events import EventType


class CoreOrchestrator:
    """
    Session / Memory / Execution / Agents 조립.
    FlowRouter → FlowHandler 연결.
    프로젝트 도메인을 모름. manifest만으로 동작.
    """

    def __init__(self, manifest: Dict[str, Any]):
        self._manifest = manifest

        self.sessions = manifest["sessions_factory"]()
        self.completed = manifest["completed_factory"]()
        self.memory_manager = manifest["memory_manager_factory"]()

        execution_agent = manifest["execution_agent_factory"]()
        self._executors = manifest["executors_factory"](
            execution_agent=execution_agent,
            agent_specs=manifest["agents"],
        )

        self._state_manager_factory = manifest["state"]["manager"]
        self.flow_router = manifest["flows"]["router"]()

        handlers_config = manifest["flows"]["handlers"]
        self.flow_handlers = {}
        for flow_key, handler_cls in handlers_config.items():
            self.flow_handlers[flow_key] = handler_cls(
                executors=self._executors,
                memory=self.memory_manager,
                sessions=self.sessions,
                state_manager_factory=self._state_manager_factory,
                completed=self.completed,
            )

    def _core_stream(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        state, memory = self.sessions.get_or_create(session_id)

        intent_executor = self._executors.get("intent")
        if intent_executor is None:
            flow = list(self.flow_handlers.keys())[0]
        else:
            intent_result = intent_executor.call(user_message, state=state)
            if not isinstance(intent_result, dict):
                intent_result = {"intent": "OTHER", "supported": False}
            intent = intent_result.get("intent", "OTHER")
            supported = intent_result.get("supported", intent == "TRANSFER")
            if not supported:
                flow = self._manifest.get("default_flow") or "DEFAULT_FLOW"
                if flow not in self.flow_handlers:
                    flow = list(self.flow_handlers.keys())[0]
            else:
                flow = self.flow_router.route(intent=intent, state=state)

        handler = self.flow_handlers[flow]
        yield from handler.run(
            session_id=session_id,
            state=state,
            memory=memory,
            user_message=user_message,
        )

    def handle_stream(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        try:
            yield from self._core_stream(session_id, user_message)
        except Exception as e:
            if "on_error" in self._manifest:
                yield self._manifest["on_error"](e)
            else:
                yield {
                    "event": EventType.DONE,
                    "payload": {
                        "message": "처리 중 오류가 발생했어요. 다시 시도해주세요.",
                        "next_action": "DONE",
                        "ui_hint": {"type": "text", "fields": [], "buttons": []},
                    },
                }
            raise
        finally:
            state, _ = self.sessions.get_or_create(session_id)
            self.sessions.save_state(session_id, state)

    def handle(self, session_id: str, user_message: str) -> Dict[str, Any]:
        final = None
        for event in self._core_stream(session_id, user_message):
            if event.get("event") == EventType.DONE:
                final = event.get("payload")
        return {
            "interaction": final if final is not None else {},
            "hooks": [],
        }
