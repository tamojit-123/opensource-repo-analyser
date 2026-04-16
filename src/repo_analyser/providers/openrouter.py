from __future__ import annotations

import httpx

from repo_analyser.config import Settings
from repo_analyser.logging_utils import get_logger
from repo_analyser.providers.base import LlmRequest, LlmResponse, ModelProvider


class OpenRouterProvider(ModelProvider):
    name = "openrouter"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger(__name__, "openrouter")
        self.client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost/repo-analyser",
                "X-Title": "Open Source Repo Analyser",
            },
            timeout=settings.request_timeout_seconds,
        )

    async def generate(self, request: LlmRequest) -> LlmResponse:
        if not self.settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured.")
        self.logger.info("Sending generation request to OpenRouter model %s.", self.settings.openrouter_model)
        response = await self.client.post(
            "/chat/completions",
            json={
                "model": self.settings.openrouter_model,
                "temperature": request.temperature,
                "messages": [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["choices"][0]["message"]["content"]
        self.logger.info("OpenRouter generation completed successfully.")
        return LlmResponse(provider=self.name, model=self.settings.openrouter_model, text=text)
