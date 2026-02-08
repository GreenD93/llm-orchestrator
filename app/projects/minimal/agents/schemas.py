from typing import Literal
from pydantic import BaseModel


class InteractionResult(BaseModel):
    """최소 템플릿: 다음 행동 + 메시지만."""
    action: Literal["ASK", "CONFIRM", "DONE", "ASK_CONTINUE"]
    message: str
