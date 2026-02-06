# app/services/orchestrator/agent_orchestrator.py

from app.services.state.stores import SessionStore, CompletedStore
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.summarizer_agent import SummarizerAgent

from app.services.execution.execution_agent import ExecutionAgent, AgentExecutor
from app.services.agents.registry import AGENT_REGISTRY

from app.services.state.state_manager import StateManager

from app.services.events import EventType

from app.services.orchestrator.flow_router import FlowRouter
from app.services.orchestrator.flow_handler import (
    DefaultFlowHandler,
    TransferFlowHandler,
)


def _make_executor(key: str, execution_agent: ExecutionAgent, *, stream: bool):
    entry = AGENT_REGISTRY[key]
    cls = entry["class"]

    agent = cls(
        system_prompt=cls.get_system_prompt(),
        llm_config=entry["llm"],
        stream=stream,
    )

    return AgentExecutor(
        agent=agent,
        execution_agent=execution_agent,
        name=key,
        policy=entry.get("policy", {}),
    )


class AgentOrchestratorService:
    def __init__(self):
        self.sessions = SessionStore()
        self.completed = CompletedStore()

        self.memory_manager = MemoryManager(summarizer=SummarizerAgent())
        self.execution_agent = ExecutionAgent()

        self.intent = _make_executor("intent", self.execution_agent, stream=False)
        self.slot = _make_executor("slot", self.execution_agent, stream=False)
        self.interaction = _make_executor("interaction", self.execution_agent, stream=True)

        self._state_manager_factory = StateManager
        self.flow_router = FlowRouter()

        self.flow_handlers = {
            "DEFAULT_FLOW": DefaultFlowHandler(
                self.interaction,
                self.memory_manager,
                self.sessions,
            ),
            "TRANSFER_FLOW": TransferFlowHandler(
                self.slot,
                self.interaction,
                self.memory_manager,
                self.sessions,
                self._state_manager_factory,
                self.completed
            ),
        }

    def _core_stream(self, session_id: str, user_message: str):
        state, memory = self.sessions.get_or_create(session_id)

        intent = self.intent.call(user_message, state=state)["intent"]

        flow = self.flow_router.route(intent=intent, state=state)
        handler = self.flow_handlers[flow]

        yield from handler.run(
            session_id=session_id,
            state=state,
            memory=memory,
            user_message=user_message,
        )

    # ======================================================
    # Public interfaces
    # ======================================================
    def handle_stream(self, session_id: str, user_message: str):
        try:
            yield from self._core_stream(session_id, user_message)
        except Exception as e:
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

    def handle(self, session_id: str, user_message: str):
        final = None
        for event in self._core_stream(session_id, user_message):
            if event["event"] == EventType.DONE:
                final = event["payload"]

        return {
            "interaction": final if final is not None else {},
            "hooks": [],
        }


_orchestrator = None


def get_orchestrator() -> AgentOrchestratorService:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestratorService()
    return _orchestrator
