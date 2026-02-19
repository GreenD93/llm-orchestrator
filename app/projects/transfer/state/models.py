# app/projects/transfer/state/models.py
"""
이체 서비스 State 모델.

─── 상태 머신 흐름 ──────────────────────────────────────────────────────────
  INIT → FILLING → READY → CONFIRMED → EXECUTED
                                    ↘ FAILED
               ↘ CANCELLED
               ↘ UNSUPPORTED (반복 실패 초과)

  INIT:        세션 시작. 슬롯이 하나도 없는 초기 상태.
  FILLING:     슬롯 일부 채워짐. missing_required가 남아있어 InteractionAgent가 추가 정보 요청.
  READY:       필수 슬롯(target, amount)이 모두 채워짐. 사용자 최종 확인 대기.
  CONFIRMED:   사용자가 이체 확인. TransferExecuteAgent 실행 대기.
  EXECUTED:    이체 성공. 세션 리셋 후 다음 이체를 받을 준비.
  FAILED:      이체 API 오류. 실패 안내 후 세션 리셋.
  CANCELLED:   사용자 취소. 세션 리셋.
  UNSUPPORTED: filling_turns >= MAX_FILL_TURNS. 반복 실패로 처리 불가 안내.

─── 배치 이체 흐름 ──────────────────────────────────────────────────────────
  SlotFillerAgent가 "홍길동에게 5만원, 박철수에게 3만원 이체해줘" 같은 발화를
  tasks 목록으로 반환하면:

  1. tasks[0] → 현재 슬롯에 적용 (INIT → FILLING or READY)
  2. tasks[1:] → state.task_queue에 저장
  3. 첫 번째 이체 완료 후 _load_next_task() → 두 번째 이체 처리 (handlers.py)

  meta 추적:
    batch_total:    전체 이체 건수
    batch_progress: 지금까지 처리한 건수 (완료+취소)
    batch_executed: 성공한 건수
    last_cancelled: 직전 태스크가 취소됐는지 (확인 메시지 접두 제어용)
"""

from datetime import date as _date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.state import BaseState


# 이 횟수 이상 슬롯을 채우지 못하면 UNSUPPORTED로 전환
MAX_FILL_TURNS = 10


class Stage(str, Enum):
    """이체 플로우의 단계."""
    INIT        = "INIT"
    FILLING     = "FILLING"
    READY       = "READY"
    CONFIRMED   = "CONFIRMED"
    EXECUTED    = "EXECUTED"
    FAILED      = "FAILED"
    CANCELLED   = "CANCELLED"
    UNSUPPORTED = "UNSUPPORTED"


# TERMINAL_MESSAGES dict의 키로 사용. 이 단계에 진입하면 세션이 리셋된다.
TERMINAL_STAGES = {
    Stage.EXECUTED,
    Stage.FAILED,
    Stage.CANCELLED,
    Stage.UNSUPPORTED,
}


class Slots(BaseModel):
    """
    이체에 필요한 슬롯 값.

    target:        수신자 이름 (필수)
    amount:        이체 금액, 원 단위 정수 (필수)
    memo:          이체 메모 (선택)
    alias:         수신자 별칭/계좌 별칭 (선택)
    transfer_date: 이체 날짜, "YYYY-MM-DD" 형식 (선택, 없으면 즉시 이체)
    """
    target:        Optional[str] = None
    amount:        Optional[int] = None
    memo:          Optional[str] = None
    alias:         Optional[str] = None
    transfer_date: Optional[str] = None


class TransferState(BaseState):
    """
    이체 서비스 State.

    Attributes:
        scenario:         항상 "TRANSFER" (IntentAgent 시나리오 매핑용)
        stage:            현재 단계 (Stage enum)
        slots:            채워진 슬롯 값
        missing_required: 아직 채워지지 않은 필수 슬롯 이름 목록 ["target", "amount"]
        filling_turns:    FILLING 단계에서 사용자에게 물어본 횟수 (MAX_FILL_TURNS 초과 시 UNSUPPORTED)
        task_queue:       배치 이체 대기 태스크 목록 (BaseState에서 상속)
    """
    scenario:         str        = "TRANSFER"
    stage:            Stage      = Stage.INIT
    slots:            Slots      = Field(default_factory=Slots)
    missing_required: List[str]  = Field(default_factory=list)
    filling_turns:    int        = 0
    # task_queue는 BaseState에서 상속: List[Dict[str, Any]] = []

    def has_any_slot(self) -> bool:
        """슬롯이 하나라도 채워졌는지 확인. INIT → FILLING 전환 판단에 사용."""
        return any(v is not None for v in self.slots.model_dump().values())


# SlotFillerAgent가 채워야 하는 필수 슬롯 목록
REQUIRED_SLOTS = ("target", "amount")


# ── 슬롯별 검증 함수 ────────────────────────────────────────────────────────────

def _validate_target(v: Any) -> bool:
    return isinstance(v, str) and len(v.strip()) > 0


def _validate_amount(v: Any) -> bool:
    return isinstance(v, int) and v >= 1


def _validate_transfer_date(v: Any) -> bool:
    if v is None:
        return True   # 선택 슬롯 — None은 유효
    try:
        _date.fromisoformat(str(v))
        return True
    except ValueError:
        return False


# ── 슬롯 스키마 ─────────────────────────────────────────────────────────────────
# StateManager가 이 스키마를 참조해 슬롯 값을 검증하고 오류 메시지를 설정한다.
#
# 각 슬롯의 필드:
#   type:      Python 타입 (값 캐스팅에 사용)
#   required:  True면 missing_required에 포함 (채워지지 않으면 FILLING 유지)
#   format:    형식 설명 (선택, 사람이 읽는 용도)
#   validate:  (value) → bool. 실패 시 error_msg가 meta["slot_errors"]에 저장
#   error_msg: 검증 실패 시 InteractionAgent에 전달할 오류 메시지
SLOT_SCHEMA: Dict[str, Dict[str, Any]] = {
    "target": {
        "type":      str,
        "required":  True,
        "validate":  _validate_target,
        "error_msg": "수신자 이름이 비어있거나 올바르지 않아요. 누구에게 보낼지 다시 알려주세요.",
    },
    "amount": {
        "type":      int,
        "required":  True,
        "validate":  _validate_amount,
        "error_msg": "이체 금액은 1원 이상의 정수여야 해요. 금액을 다시 알려주세요.",
    },
    "memo": {
        "type":     str,
        "required": False,
    },
    "alias": {
        "type":     str,
        "required": False,
    },
    "transfer_date": {
        "type":      str,
        "required":  False,
        "format":    "YYYY-MM-DD",
        "validate":  _validate_transfer_date,
        "error_msg": "이체 날짜를 인식하지 못했어요. '6월 19일', '2026-06-19' 형식으로 다시 알려주세요.",
    },
}
