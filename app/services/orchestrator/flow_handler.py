from app.services.events import EventType
from app.services.state.models import TERMINAL_STAGES, Stage, TransferState


class BaseFlowHandler:
    def run(self, **kwargs):
        raise NotImplementedError

    def _get_history(self, memory):
        return memory["raw_history"][-6:]

    def _update_and_save(self, session_id, state, memory, user_message, assistant_message):
        self.memory.update(memory, user_message, assistant_message)
        self.sessions.save_state(session_id, state)

    def _run_interaction_stream(self, state, history, summary_text, summary_struct):
        """Interaction 스트림을 소비하면서 이벤트를 yield하고, 마지막 payload를 반환."""
        payload = None
        for ev in self.interaction.call(
            state,
            history,
            summary_text,
            summary_struct,
            state=state,
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload") or {}
        return payload


class DefaultFlowHandler(BaseFlowHandler):
    """TRANSFER가 아닌 경우: Interaction만 호출 후 메모리 갱신, DONE 반환."""

    def __init__(self, interaction_executor, memory_manager, sessions):
        self.interaction = interaction_executor
        self.memory = memory_manager
        self.sessions = sessions

    def run(self, *, session_id, state, memory, user_message):
        history = self._get_history(memory)
        payload = None
        for ev in self._run_interaction_stream(
            state, history, memory["summary_text"], memory["summary_struct"]
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")
        if payload:
            self._update_and_save(session_id, state, memory, user_message, payload.get("message", ""))
        yield {"event": EventType.DONE, "payload": payload or {}}


class TransferFlowHandler(BaseFlowHandler):
    def __init__(self, slot_executor, interaction_executor, memory_manager, sessions, state_manager_factory, completed_store):
        self.slot = slot_executor
        self.interaction = interaction_executor
        self.memory = memory_manager
        self.sessions = sessions
        self.state_manager_factory = state_manager_factory
        self.completed = completed_store

    def run(self, *, session_id, state, memory, user_message):
        history = self._get_history(memory)

        delta = self.slot.call(user_message, state=state)
        state = self.state_manager_factory(state).apply(delta)

        if state.stage == Stage.READY:
            self.memory._compress(memory)

        payload = None
        for ev in self._run_interaction_stream(
            state, history, memory["summary_text"], memory["summary_struct"]
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")

        if payload:
            self._update_and_save(session_id, state, memory, user_message, payload.get("message", ""))

        if state.stage in TERMINAL_STAGES:
            self.completed.add(session_id, state, memory)
            state = TransferState()
            self.sessions.save_state(session_id, state)

        yield {"event": EventType.DONE, "payload": payload or {}}
