# app/services/llm/openai_client.py
from openai import OpenAI
from app.core.config import settings

class OpenAIClient:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def chat(self, *, model, temperature, messages):
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

    def chat_stream(self, *, model, temperature, messages):
        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
