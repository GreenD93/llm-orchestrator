# app/projects/transfer/agents/transfer_execute_agent/prompt.py
"""실행 Agent는 LLM 미사용 시에도 registry 호환용."""

SYSTEM_PROMPT = "Execution agent (no LLM)."


def get_system_prompt() -> str:
    return SYSTEM_PROMPT
