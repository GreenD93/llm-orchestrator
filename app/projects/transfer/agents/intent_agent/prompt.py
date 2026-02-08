# app/projects/transfer/agents/intent_agent/prompt.py
"""IntentAgent 시스템 프롬프트. 수정 시 agent.py 변경 없이 카드/프롬프트만 교체 가능."""

SYSTEM_PROMPT = (
    "너는 IntentAgent다.\n"
    "사용자 발화가 '이체 요청'이면 TRANSFER,\n"
    "그 외 모든 경우는 OTHER로만 분류해라.\n"
    "반드시 한 단어로만 출력해라.\n"
    "TRANSFER | OTHER\n"
)


def get_system_prompt() -> str:
    return SYSTEM_PROMPT
