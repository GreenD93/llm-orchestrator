# app/projects/transfer/messages.py
"""
이체 서비스 사용자 메시지 상수.

서비스 문구 변경은 이 파일만 수정하면 된다.
handlers.py / state 로직은 건드리지 않아도 됨.
"""

from typing import Dict
from app.projects.transfer.state.models import Stage


# ── 시스템 메시지 ─────────────────────────────────────────────────────────────

UNSUPPORTED_MESSAGE = (
    "입력이 반복되어 더 이상 진행할 수 없어요. 처음부터 다시 시도해 주세요."
)

# ── 단건 완료/실패/취소 ────────────────────────────────────────────────────────

TERMINAL_MESSAGES: Dict[Stage, str] = {
    Stage.EXECUTED:  "이체가 완료됐어요. 다른 도움이 필요하신가요?",
    Stage.FAILED:    "이체에 실패했어요. 잠시 후 다시 시도해 주세요.",
    Stage.CANCELLED: "이체가 취소됐어요. 다른 도움이 필요하신가요?",
}

# ── 다건 완료 메시지 ──────────────────────────────────────────────────────────

def batch_partial_complete(executed_count: int) -> str:
    """일부 이체 완료 후 나머지 취소 시."""
    return f"{executed_count}건을 이체하고 나머지를 취소했어요. 다른 도움이 필요하신가요?"


def batch_all_complete(executed_count: int) -> str:
    """모든 이체 완료 시."""
    return f"{executed_count}건 이체가 모두 완료됐어요. 다른 도움이 필요하신가요?"


# ── READY 단계 확인 메시지 빌더 ───────────────────────────────────────────────

def format_amount(amount: int | None) -> str:
    """숫자 → 한국식 금액 표기. 예: 10000 → '1만원', 150000 → '15만원'"""
    if amount is None:
        return "?"
    if amount >= 100_000_000:
        v = amount // 100_000_000
        return f"{v}억원" if amount % 100_000_000 == 0 else f"{amount:,}원"
    if amount >= 10_000:
        v = amount // 10_000
        return f"{v}만원" if amount % 10_000 == 0 else f"{amount:,}원"
    return f"{amount:,}원"


def build_ready_message(state) -> str:
    """
    READY 단계 확인 메시지를 코드로 결정론적 생성 (LLM 호출 없음).
    배치 진행 상황, 취소 여부에 따라 자동으로 문구 선택.
    """
    slots = state.slots
    target = slots.target or "?"
    amount_str = format_amount(slots.amount)

    batch_total    = state.meta.get("batch_total", 1)
    batch_progress = state.meta.get("batch_progress", 0)
    last_cancelled = state.meta.get("last_cancelled", False)

    if batch_total > 1:
        index = batch_progress + 1
        if last_cancelled:
            prefix = "취소됐어요. "
        elif batch_progress > 0:
            prefix = "완료! 다음으로 "
        else:
            prefix = f"총 {batch_total}건이 요청됐어요. 먼저 "
        line = f"{prefix}{target}에게 {amount_str} 보낼까요? ({index}/{batch_total})"
    else:
        line = f"{target}에게 {amount_str}을(를) 이체할까요?"

    # 선택적 슬롯 안내 (메모·날짜 미입력 시, 단건일 때만 — 배치는 첫 발화에 이미 지정)
    if not slots.memo and not slots.transfer_date and batch_total == 1:
        line += "\n메모나 이체 날짜를 추가하시겠어요? 없으시면 바로 진행할게요."

    return line
