# app/core/tools/calculator.py
from app.core.tools.base_tool import BaseTool


class Calculator(BaseTool):
    """두 수의 사칙연산 Tool. LLM이 피연산자와 연산자를 추출해 호출."""

    name = "calculator"
    description = "두 수의 사칙연산을 수행합니다."

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": (
                "두 수의 사칙연산(덧셈, 뺄셈, 곱셈, 나눗셈)을 수행합니다. "
                "금액 계산이 필요할 때 사용합니다. "
                "예: '10000원씩 5번' → a=10000, b=5, op='multiply'. "
                "'3만원과 2만원 합쳐서' → a=30000, b=20000, op='add'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "첫 번째 피연산자"},
                    "b": {"type": "number", "description": "두 번째 피연산자"},
                    "op": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "연산 종류: add(덧셈), subtract(뺄셈), multiply(곱셈), divide(나눗셈)",
                    },
                },
                "required": ["a", "b", "op"],
            },
        }

    def run(self, a: float, b: float, op: str) -> str:
        ops = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else None,
        }
        result = ops.get(op)
        if result is None:
            return f"[error: op='{op}']" if op not in ops else "[error: division by zero]"
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
