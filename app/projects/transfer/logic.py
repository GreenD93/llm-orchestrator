# app/projects/transfer/logic.py
"""
LLM에 의존하지 않는 코드 레벨 분류 로직.

원칙: 명확한 사용자 의사(확인/취소)는 LLM 없이 결정론적으로 처리한다.
     모호하거나 자연어 해석이 필요한 경우에만 LLM(SlotFiller)을 호출한다.
"""

import re

# ── 확인 의사 ─────────────────────────────────────────────────────────────────
# READY 단계에서 사용자가 확인 버튼을 누르거나 유사 표현을 사용하는 경우.
# 전체 발화가 확인 표현인 경우만 매칭 (부분 포함 X → 오탐 방지).
_CONFIRM_RE = re.compile(
    r"^(확인|네|응|맞아요?|예|그래요?|그럼요?|진행|진행해?|진행할게요?|진행하겠습니다|"
    r"ok|okay|좋아요?|좋습니다|"
    r"보내줘?|보낼게요?|보내겠습니다|"
    r"이체해?|이체할게요?|이체하겠습니다|"
    r"해줘?|할게요?|하겠습니다|맞습니다|됩니다|그러세요?|당연|ㅇㅇ|ㅇㅋ|네네|예예)$",
    re.IGNORECASE,
)

# ── 취소 의사 ─────────────────────────────────────────────────────────────────
# 부분 포함으로 매칭 (문장 내 어디든 취소 신호가 있으면 취소).
# 단, 짧은 단어 오탐을 줄이기 위해 단어 경계(\b) 또는 어미 조합으로 제한.
_CANCEL_RE = re.compile(
    r"취소|그만|안\s*할게|안\s*보낼게|됐어|안\s*해(?:도)?(?:요)?|"
    r"필요\s*없|그냥\s*둬|그냥\s*됐|보내지\s*마|이체\s*하지\s*마|"
    r"^아니(?:요|오)?$|^싫어요?$",
    re.IGNORECASE,
)


def is_confirm(message: str) -> bool:
    """
    READY 단계: 사용자 확인 의사를 키워드로 판별.
    전체 발화가 확인 표현인 경우만 True (부분 포함 오탐 방지).
    """
    return bool(_CONFIRM_RE.match(message.strip()))


def is_cancel(message: str) -> bool:
    """
    임의 단계: 명시적 취소 의사를 키워드로 판별.
    문장 내 취소 신호가 하나라도 있으면 True.
    """
    return bool(_CANCEL_RE.search(message.strip()))


# ── 슬롯 편집 + 확인 (프론트엔드 생성 패턴) ─────────────────────────────────────
# 프론트에서 슬롯을 편집하고 "확인"을 누르면 아래 형식의 메시지가 전송된다:
#   "받는 분 용걸이으로 하고 확인"
#   "금액 50,000원, 메모 생일으로 하고 확인"
# 결정론적 패턴이므로 LLM 없이 코드로 처리한다.

_SLOT_EDIT_CONFIRM_RE = re.compile(r'^(.+)으로 하고 확인$')

_LABEL_TO_SLOT = {
    "받는 분": "target",
    "금액": "amount",
    "메모": "memo",
    "이체일": "transfer_date",
}


def parse_slot_edit_confirm(message: str) -> dict | None:
    """
    프론트엔드 슬롯 편집 + 확인 메시지를 코드 레벨로 파싱.

    Returns:
        delta dict ({"operations": [...]}) 또는 None (패턴 불일치 시 SlotFiller에 위임).
    """
    m = _SLOT_EDIT_CONFIRM_RE.match(message.strip())
    if not m:
        return None

    parts = [p.strip() for p in m.group(1).split(",")]
    ops = []

    for part in parts:
        matched = False
        for label, slot in _LABEL_TO_SLOT.items():
            if part.startswith(label + " "):
                raw_value = part[len(label):].strip()
                if slot == "amount":
                    parsed = _parse_amount_from_display(raw_value)
                    if parsed is None:
                        return None
                    ops.append({"op": "set", "slot": slot, "value": parsed})
                else:
                    ops.append({"op": "set", "slot": slot, "value": raw_value})
                matched = True
                break
        if not matched:
            return None

    if not ops:
        return None

    ops.append({"op": "confirm"})
    return {"operations": ops}


def _parse_amount_from_display(text: str) -> int | None:
    """프론트 표시 금액 → 정수. "50,000원" → 50000"""
    text = text.strip().replace(",", "").replace("원", "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None
