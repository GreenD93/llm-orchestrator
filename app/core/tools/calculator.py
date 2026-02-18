# app/core/tools/calculator.py
from app.core.tools.base_tool import BaseTool


class Calculator(BaseTool):
    """
    사칙연산 Tool.

    사용 예시:
        "10000원을 5번 보내려 해" → calculator(a=10000, b=5, op="mul") → "50000"
        → SlotFillerAgent가 amount=50000으로 설정

    파라미터 부족 시: LLM이 필요한 값을 사용자에게 되물음
        "5번 보내려 해" (금액 미제공) → LLM: "얼마씩 보내시겠어요?"
        → 사용자 답변 후 다음 턴에 calculator 호출
    """

    name = "calculator"
    description = "두 수의 사칙연산(덧셈/뺄셈/곱셈/나눗셈). 금액 계산 등에 사용."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "첫 번째 피연산자"},
                        "b": {"type": "number", "description": "두 번째 피연산자"},
                        "op": {
                            "type": "string",
                            "enum": ["add", "sub", "mul", "div"],
                            "description": "연산자: add(덧셈), sub(뺄셈), mul(곱셈), div(나눗셈)",
                        },
                    },
                    "required": ["a", "b", "op"],
                },
            },
        }

    def run(self, a: float, b: float, op: str) -> str:
        results = {
            "add": a + b,
            "sub": a - b,
            "mul": a * b,
            "div": a / b if b != 0 else None,
        }
        result = results.get(op)
        if result is None:
            return f"[error: op='{op}']" if op not in results else "[error: division by zero]"
        # 정수이면 int로 반환 (50000.0 → 50000)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
