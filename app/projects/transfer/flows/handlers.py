# app/projects/transfer/flows/handlers.py
from typing import Any, Dict, Generator

from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler, get_history, update_and_save
from app.core.agents import RetryableError, FatalExecutionError
from app.projects.transfer.state.models import Stage, TERMINAL_STAGES, TransferState

# UI 정책: InteractionAgent는 결정+메시지만. 버튼/화면 구성은 여기서 매핑.
UI_POLICY: Dict[str, Dict[str, Any]] = {
    "ASK_CONTINUE": {"buttons": ["계속 진행", "취소"]},
    "CONFIRM": {"buttons": ["확인", "취소"]},
    "ASK": {},
    "DONE": {},
}


def _apply_ui_policy(payload: dict) -> dict:
    action = payload.get("action") or payload.get("next_action", "DONE")
    payload["next_action"] = action
    payload["ui_hint"] = UI_POLICY.get(action, {})
    return payload


class DefaultFlowHandler(BaseFlowHandler):
    """TRANSFER가 아닌 경우: Interaction만 호출 후 메모리 갱신, DONE 반환."""

    def run(
        self,
        *,
        session_id: str,
        state: Any,
        memory: dict,
        user_message: str,
    ) -> Generator[Dict[str, Any], None, None]:
        history = get_history(memory)
        interaction = self.get("interaction")
        payload = None
        for ev in self._run_interaction_stream(
            state, history, memory.get("summary_text", ""), memory.get("summary_struct")
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")
        if payload:
            update_and_save(
                self.memory,
                self.sessions,
                session_id,
                state,
                memory,
                user_message,
                payload.get("message", ""),
            )
        yield {"event": EventType.DONE, "payload": _apply_ui_policy(payload or {})}

    def _run_interaction_stream(self, state, history, summary_text, summary_struct):
        interaction = self.get("interaction")
        payload = None
        for ev in interaction.call(
            state, history, summary_text, summary_struct, state=state, stream=True
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload") or {}
        return payload


# UNSUPPORTED(멀티턴 초과 등): InteractionAgent 호출 없이 고정 메시지로 종료.
UNSUPPORTED_MESSAGE = "입력이 반복되어 더 이상 진행할 수 없어요. 처음부터 다시 시도해 주세요."


class TransferFlowHandler(BaseFlowHandler):
    """1. slot 2. apply 3. CONFIRMED이면 ExecuteExecutor.call 4. UNSUPPORTED면 고정 메시지 5. 그 외 interaction 6. terminal이면 completed."""

    def run(
        self,
        *,
        session_id: str,
        state: Any,
        memory: dict,
        user_message: str,
    ) -> Generator[Dict[str, Any], None, None]:
        history = self._get_history(memory)
        slot = self.get("slot")
        interaction = self.get("interaction")

        delta = slot.call(user_message, state=state)
        state = self.state_manager_factory(state).apply(delta)

        if getattr(state, "stage", None) == Stage.UNSUPPORTED:
            payload = {"message": UNSUPPORTED_MESSAGE, "action": "DONE"}
            update_and_save(
                self.memory, self.sessions, session_id, state, memory, user_message, payload["message"]
            )
            if self.completed:
                self.completed.add(session_id, state, memory)
            state = TransferState()
            self.sessions.save_state(session_id, state)
            yield {"event": EventType.DONE, "payload": _apply_ui_policy(payload)}
            return

        if getattr(state, "stage", None) and state.stage == Stage.CONFIRMED:
            execute_executor = self.get("execute")
            try:
                execute_executor.call(state=state)
                state.stage = Stage.EXECUTED
            except RetryableError:
                state.stage = Stage.FAILED
                state.meta.setdefault("execution", {})["retryable"] = True
            except FatalExecutionError:
                state.stage = Stage.FAILED
            self.sessions.save_state(session_id, state)

        if getattr(state, "stage", None) and str(state.stage) == "READY":
            self.memory._compress(memory)

        payload = None
        for ev in self._run_interaction_stream(
            state, history, memory.get("summary_text", ""), memory.get("summary_struct")
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload")

        if payload:
            update_and_save(
                self.memory,
                self.sessions,
                session_id,
                state,
                memory,
                user_message,
                payload.get("message", ""),
            )

        if getattr(state, "stage", None) and state.stage in TERMINAL_STAGES:
            if self.completed:
                self.completed.add(session_id, state, memory)
            state = TransferState()
            self.sessions.save_state(session_id, state)

        yield {"event": EventType.DONE, "payload": _apply_ui_policy(payload or {})}

    def _run_interaction_stream(self, state, history, summary_text, summary_struct):
        interaction = self.get("interaction")
        payload = None
        for ev in interaction.call(
            state, history, summary_text, summary_struct, state=state, stream=True
        ):
            yield ev
            if ev.get("event") == EventType.LLM_DONE:
                payload = ev.get("payload") or {}
        return payload
