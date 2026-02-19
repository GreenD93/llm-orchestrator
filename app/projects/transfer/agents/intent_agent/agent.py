# app/projects/transfer/agents/intent_agent/agent.py
from app.core.agents.base_agent import BaseAgent
from app.core.agents.agent_runner import RetryableError
from app.core.context import ExecutionContext
from app.projects.transfer.agents.intent_agent.prompt import get_system_prompt


class IntentAgent(BaseAgent):
    # 이 프로젝트에서 분류 가능한 시나리오 목록
    # 새 서비스 추가 시: 여기에 값 추가 + prompt.py 분류 기준 추가 + SCENARIO_TO_FLOW 등록
    KNOWN_SCENARIOS = {"TRANSFER", "GENERAL"}

    @classmethod
    def get_system_prompt(cls) -> str:
        return get_system_prompt()

    def run(self, context: ExecutionContext, **kwargs) -> dict:
        context_block = f"현재 이체 stage: {context.state.stage}"
        messages = context.build_messages(context_block)
        raw = self.chat(messages).strip().upper()
        if raw not in self.KNOWN_SCENARIOS:
            raise RetryableError(f"unknown_scenario: {raw}")
        return {"scenario": raw, "reason": None}
