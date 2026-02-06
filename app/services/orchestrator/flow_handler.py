# app/services/orchestrator/flow_handler.py
from app.services.events import EventType
from app.services.state.models import TERMINAL_STAGES

class BaseFlowHandler:
    def run(self, **kwargs):
        raise NotImplementedError


class DefaultFlowHandler(BaseFlowHandler):
    """
    TRANSFER 아닌 모든 경우
    """

    def __init__(self, interaction_executor, memory_manager, sessions):
        self.interaction = interaction_executor
        self.memory = memory_manager
        self.sessions = sessions

    def run(self, *, session_id, state, memory, user_message):
        history = memory["raw_history"][-6:]

        interaction = None
        for ev in self.interaction.call(
            state,
            history,
            memory["summary_text"],
            memory["summary_struct"],
            stream=True,
            state=state,
        ):
            if ev["event"] == EventType.LLM_DONE:
                interaction = ev["payload"]
            yield ev

        self.memory.update(memory, user_message, interaction["message"])
        self.sessions.save_state(session_id, state)

        yield {"event": EventType.DONE, "payload": interaction}


class TransferFlowHandler(BaseFlowHandler):
    """
    이체 플로우
    """

    def __init__(self, slot_executor, interaction_executor, memory_manager, sessions, state_manager_factory, completed_store):
        self.slot = slot_executor
        self.interaction = interaction_executor
        self.memory = memory_manager
        self.sessions = sessions
        self.state_manager_factory = state_manager_factory
        self.completed = completed_store

    def run(self, *, session_id, state, memory, user_message):
        history = memory["raw_history"][-6:]

        delta = self.slot.call(user_message, state=state)
        state = self.state_manager_factory(state).apply(delta)

        interaction = self.interaction.call(
            state,
            history,
            memory["summary_text"],
            memory["summary_struct"],
            state=state,
        )

        self.memory.update(memory, user_message, interaction["message"])
        self.sessions.save_state(session_id, state)

        # ✅ terminal stage면 완료 기록
        if state.stage in TERMINAL_STAGES:
            self.completed.add(session_id, state, memory)

        yield {"event": EventType.DONE, "payload": interaction}