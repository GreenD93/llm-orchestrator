# app/services/memory/prompts.py
def SUMMARIZER_SYSTEM_PROMPT() -> str:
    return (
        "너는 대화 메모리 요약기다.\n"
        "입력으로 주어진 최근 대화(raw_history)를 요약해서 아래 JSON만 출력해라.\n"
        "반드시 JSON으로만 출력.\n\n"
        "출력 형식:\n"
        "{\n"
        '  "summary_text": "간결한 텍스트 요약",\n'
        '  "summary_struct": {\n'
        '    "intent": "TRANSFER|OTHER",\n'
        '    "entities": {"target": null|str, "amount": null|int},\n'
        '    "status": "COLLECTING|WAITING_CONFIRMATION|EXECUTING|COMPLETED|ERROR|IDLE",\n'
        '    "notes": ["..."]\n'
        "  }\n"
        "}\n"
    )
