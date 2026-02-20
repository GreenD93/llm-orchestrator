# app/projects/transfer/flows/handlers.py
"""
이체 서비스 FlowHandler 구현.

─── 역할 ─────────────────────────────────────────────────────────────────────
  FlowHandler는 에이전트 파이프라인과 분기 로직만 담당한다.
  상태 전이 로직은 StateManager, 슬롯 추출은 SlotFillerAgent가 처리한다.

─── Handler 목록 ─────────────────────────────────────────────────────────────
  DefaultFlowHandler:  TRANSFER 외 시나리오 (GENERAL 등) — InteractionAgent만 실행
  TransferFlowHandler: 이체 플로우 전체 파이프라인

─── TransferFlowHandler 실행 순서 ────────────────────────────────────────────
  1. SlotFillerAgent (또는 코드 레벨 분류)
     READY + 확인/취소 키워드 → 코드로 직접 delta 생성 (LLM 불필요)
     그 외                    → SlotFillerAgent LLM 호출
  2. StateManager.apply(delta) → 슬롯 검증·단계 전이
  3. 단계별 분기:
     UNSUPPORTED → 안내 메시지 + 세션 리셋
     CANCELLED + 대기 큐 → 다음 태스크 로드 (배치 스킵)
     CONFIRMED   → TransferExecuteAgent 실행
     EXECUTED/FAILED/CANCELLED → 완료 메시지 + 세션 리셋
     READY       → 결정론적 확인 메시지 (LLM 없음)
     FILLING/INIT → InteractionAgent 호출
"""

from typing import Any, Dict, Generator

from app.core.context import ExecutionContext
from app.core.events import EventType
from app.core.orchestration import BaseFlowHandler
from app.core.agents.agent_runner import RetryableError, FatalExecutionError
from app.projects.transfer.state.models import Stage, TransferState, Slots, REQUIRED_SLOTS
from app.projects.transfer.logic import is_confirm, is_cancel, parse_slot_edit_confirm
from app.projects.transfer.messages import (
    UNSUPPORTED_MESSAGE,
    TERMINAL_MESSAGES,
    build_ready_message,
    build_slots_card,
    batch_partial_complete,
    batch_all_complete,
)

# ── UI 정책 ─────────────────────────────────────────────────────────────────────
# action → 프론트엔드에 표시할 버튼 목록. 버튼 문구 변경 시 여기만 수정.
# InteractionAgent는 action만 반환하고, 버튼 결정은 이 dict에서 일괄 관리.
UI_POLICY: Dict[str, Dict[str, Any]] = {
    "ASK_CONTINUE": {"buttons": ["계속 진행", "취소"]},
    "CONFIRM":      {"buttons": ["확인", "취소"]},
    "ASK":          {},   # 버튼 없음 — 자유 텍스트 입력
    "DONE":         {},   # 버튼 없음 — 대화 종료
}


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _apply_ui_policy(payload: dict) -> dict:
    """
    DONE payload에 UI 정책(버튼 목록)을 적용한다.

    _stream_agent_turn()의 done_transform 콜백으로 전달되거나,
    비-LLM DONE payload 생성 시 직접 호출한다.
    """
    action = payload.get("action") or payload.get("next_action", "DONE")
    payload["next_action"] = action
    payload["ui_hint"] = UI_POLICY.get(action, {})
    return payload


def _load_next_task(state: TransferState) -> bool | None:
    """
    task_queue에서 다음 배치 태스크를 꺼내 state에 적용한다.

    Returns:
        True:  슬롯이 완전히 채워진 태스크 (READY로 전환 가능)
        False: 슬롯이 불완전한 태스크 (FILLING 단계 필요)
        None:  대기 큐가 비어있음 (더 처리할 태스크 없음)
    """
    if not state.task_queue:
        return None
    next_task = state.task_queue.pop(0)
    state.slots = Slots(**{k: v for k, v in next_task.items() if k in Slots.model_fields})
    state.missing_required = [s for s in REQUIRED_SLOTS if getattr(state.slots, s) is None]
    state.filling_turns = 0
    return len(state.missing_required) == 0


# ── Flow Handlers ─────────────────────────────────────────────────────────────

class DefaultFlowHandler(BaseFlowHandler):
    """
    TRANSFER 외 시나리오 핸들러 (GENERAL, 잔액 조회 등).

    InteractionAgent만 호출한다.
    summary + raw_history를 활용해 이전 이체 이력, 일반 질문에 자연스럽게 응대한다.
    """

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:
        yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                           done_transform=_apply_ui_policy)


class TransferFlowHandler(BaseFlowHandler):
    """
    이체 플로우 핸들러. 이 서비스의 핵심 파이프라인.

    INIT → FILLING → READY → CONFIRMED → EXECUTED / FAILED / CANCELLED
    """

    def _yield_done(self, ctx: ExecutionContext, payload: dict) -> dict:
        """DONE payload에 UI 정책과 state_snapshot을 추가한다."""
        payload = _apply_ui_policy(payload)
        return self._build_done_payload(ctx, payload)

    def run(self, ctx: ExecutionContext) -> Generator[Dict[str, Any], None, None]:

        # ── 1. Slot 추출 ─────────────────────────────────────────────────────
        #
        # READY 단계: 확인/취소는 코드로 직접 처리, 그 외(메모·날짜 등)는 SlotFiller 호출.
        # StateManager 안전 장치가 confirm을 READY→CONFIRMED 전환만 허용하므로 위험 없음.
        yield {"event": EventType.AGENT_START, "payload": {"agent": "slot", "label": "정보 추출 중"}}

        if ctx.state.stage == Stage.READY:
            if is_confirm(ctx.user_message):
                delta = {"operations": [{"op": "confirm"}]}
            elif is_cancel(ctx.user_message):
                delta = {"operations": [{"op": "cancel_flow"}]}
            else:
                # 프론트엔드 슬롯 편집 + 확인 패턴 → 코드 레벨 파싱 (LLM 불필요)
                delta = parse_slot_edit_confirm(ctx.user_message)
                if delta is None:
                    # 코드 파싱 실패 → SlotFiller LLM 호출 (메모·날짜 자유 입력 등)
                    delta = self.runner.run("slot", ctx)
                    # READY의 confirm/cancel은 is_confirm()/is_cancel() 코드 전용.
                    # SlotFiller가 슬롯 편집과 함께 반환해도 제거한다.
                    ops = delta.get("operations", [])
                    delta["operations"] = [
                        o for o in ops if o.get("op") not in ("confirm", "cancel_flow")
                    ]
        elif is_cancel(ctx.user_message) and ctx.state.stage == Stage.FILLING:
            # FILLING 단계에서 명시적 취소 → LLM 없이 바로 취소 처리
            # INIT 단계는 진행 중인 이체가 없으므로 shortcut 미적용:
            # InteractionAgent가 "취소할 이체가 없어요"로 자연스럽게 응대
            delta = {"operations": [{"op": "cancel_flow"}]}
        else:
            # 일반 슬롯 추출 — LLM 호출
            delta = self.runner.run("slot", ctx)

        # 다건 이체 감지: INIT·FILLING 단계에서만 처리.
        # READY 이후에는 이미 배치가 진행 중이므로 새 감지를 무시 → 배치 리셋 방지.
        if delta.get("tasks") and ctx.state.stage in (Stage.INIT, Stage.FILLING):
            tasks = delta["tasks"]
            ctx.state.meta["batch_total"]    = len(tasks)
            ctx.state.meta["batch_progress"] = 0
            # 첫 번째 태스크를 현재 슬롯에 적용, 나머지는 task_queue에 저장
            delta = {
                "operations": [
                    {"op": "set", "slot": k, "value": v}
                    for k, v in tasks[0].items() if v is not None
                ]
            }
            ctx.state.task_queue = tasks[1:]

        # READY + 빈 delta → off-topic 플래그 (3e에서 InteractionAgent 폴백에 사용)
        ready_empty_delta = (
            ctx.state.stage == Stage.READY
            and not delta.get("operations")
        )

        # ── 2. StateManager — 슬롯 검증·단계 전이 ───────────────────────────
        ctx.state = self.state_manager_factory(ctx.state).apply(delta)
        yield {"event": EventType.AGENT_DONE, "payload": {
            "agent": "slot",
            "label": "정보 추출 완료",
            "success": True,
            "stage": ctx.state.stage,
        }}

        # ── 3a. UNSUPPORTED — 반복 실패 횟수 초과 ────────────────────────────
        if ctx.state.stage == Stage.UNSUPPORTED:
            payload = {"message": UNSUPPORTED_MESSAGE, "action": "DONE"}
            self._update_memory(ctx, payload["message"])
            if self.completed:
                self.completed.add(ctx.session_id, ctx.state, ctx.memory)
            self._reset_state(ctx, TransferState())
            yield {"event": EventType.DONE, "payload": self._yield_done(ctx, payload)}
            return

        # ── 3b. CANCELLED + 대기 큐 → 다음 배치 태스크 로드 ─────────────────
        # 단건 취소 후 남은 태스크가 있으면 바로 다음 이체로 이동 (배치 플로우 계속)
        if ctx.state.stage == Stage.CANCELLED and ctx.state.task_queue:
            batch_progress = ctx.state.meta.get("batch_progress", 0)
            is_complete = _load_next_task(ctx.state)
            ctx.state.meta["batch_progress"] = batch_progress + 1
            ctx.state.meta["last_cancelled"] = True   # 확인 메시지에 "취소됐어요. 다음으로..." 접두 표시용
            ctx.state.stage = Stage.READY if is_complete else Stage.FILLING
            self.sessions.save_state(ctx.session_id, ctx.state)

        # ── 3c. CONFIRMED — 이체 실행 ─────────────────────────────────────────
        if ctx.state.stage == Stage.CONFIRMED:
            batch_total    = ctx.state.meta.get("batch_total",    1)
            batch_progress = ctx.state.meta.get("batch_progress", 0)

            # 배치 진행 상황을 프론트에 알림 (진행바 표시 등에 활용)
            yield {"event": EventType.TASK_PROGRESS, "payload": {
                "index": batch_progress + 1,
                "total": batch_total,
                "slots": ctx.state.slots.model_dump(),
            }}
            yield {"event": EventType.AGENT_START, "payload": {"agent": "execute", "label": "이체 실행 중"}}
            try:
                self.runner.run("execute", ctx)
                ctx.state.stage = Stage.EXECUTED
                ctx.state.meta["batch_executed"] = ctx.state.meta.get("batch_executed", 0) + 1
                ctx.state.meta.setdefault("batch_receipts", []).append(
                    build_slots_card(ctx.state.slots)
                )
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "execute", "label": "이체 실행 완료", "success": True,
                }}
                if self.completed:
                    self.completed.add(ctx.session_id, ctx.state, ctx.memory)

            except (RetryableError, FatalExecutionError):
                ctx.state.stage = Stage.FAILED
                yield {"event": EventType.AGENT_DONE, "payload": {
                    "agent": "execute", "label": "이체 실행 실패", "success": False,
                }}

            # 이체 성공 시 다음 배치 태스크 로드
            if ctx.state.stage == Stage.EXECUTED:
                is_complete = _load_next_task(ctx.state)
                new_progress = batch_progress + 1
                if is_complete is None:
                    pass  # 마지막 태스크 — terminal 분기로 넘어감
                elif is_complete:
                    ctx.state.stage = Stage.READY
                    ctx.state.meta["batch_progress"] = new_progress
                else:
                    ctx.state.stage = Stage.FILLING
                    ctx.state.meta["batch_progress"] = new_progress

            self.sessions.save_state(ctx.session_id, ctx.state)

        # ── 3d. Terminal — 완료·실패·취소 메시지 후 세션 리셋 ─────────────────
        if ctx.state.stage in TERMINAL_MESSAGES:
            total_executed = ctx.state.meta.get("batch_executed", 0)
            # 배치 일부만 완료하고 취소한 경우 특수 메시지
            if ctx.state.stage == Stage.CANCELLED and total_executed > 0:
                message = batch_partial_complete(total_executed)
            elif total_executed > 1:
                message = batch_all_complete(total_executed)
            else:
                message = TERMINAL_MESSAGES[ctx.state.stage]

            payload = {"message": message, "action": "DONE"}
            # 영수증: 배치일 때 전체 영수증, 단건일 때 기존 호환
            if ctx.state.stage in (Stage.EXECUTED, Stage.FAILED):
                batch_receipts = ctx.state.meta.get("batch_receipts", [])
                if len(batch_receipts) > 1:
                    payload["receipts"] = batch_receipts
                elif batch_receipts:
                    payload["receipt"] = batch_receipts[0]
                else:
                    payload["receipt"] = build_slots_card(ctx.state.slots)
            self._update_memory(ctx, message)
            if self.completed and ctx.state.stage in (Stage.FAILED, Stage.CANCELLED):
                self.completed.add(ctx.session_id, ctx.state, ctx.memory)
            self._reset_state(ctx, TransferState())
            yield {"event": EventType.DONE, "payload": self._yield_done(ctx, payload)}
            return

        # ── 3e. READY — 확인 메시지 또는 InteractionAgent 폴백 ──────────────
        if ctx.state.stage == Stage.READY:
            if ready_empty_delta:
                # Off-topic 또는 인식 불가 → InteractionAgent가 자연스럽게 응대 후 확인 유도
                yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                                   done_transform=_apply_ui_policy)
                return
            # 슬롯 변경 반영 → 결정론적 확인 메시지 + 카드
            message = build_ready_message(ctx.state)
            ctx.state.meta.pop("last_cancelled", None)
            payload = {
                "action": "CONFIRM",
                "message": message,
                "slots_card": build_slots_card(ctx.state.slots),
            }
            self._update_memory(ctx, message)
            yield {"event": EventType.DONE, "payload": self._yield_done(ctx, payload)}
            return

        # ── 3f. FILLING / INIT — InteractionAgent ────────────────────────────
        # 필요 슬롯을 물어보거나 오류(slot_errors)를 사용자에게 안내한다.
        yield from self._stream_agent_turn(ctx, "interaction", "응답 생성 중",
                                           done_transform=_apply_ui_policy)
