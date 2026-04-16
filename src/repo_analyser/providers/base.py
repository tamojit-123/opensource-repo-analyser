from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LlmRequest:
    system_prompt: str
    user_prompt: str
    temperature: float = 0.2


@dataclass(slots=True)
class LlmResponse:
    provider: str
    model: str
    text: str


class ModelProvider:
    name: str

    async def generate(self, request: LlmRequest) -> LlmResponse:
        raise NotImplementedError
