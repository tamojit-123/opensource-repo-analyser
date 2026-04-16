from __future__ import annotations

from repo_analyser.config import Settings
from repo_analyser.logging_utils import get_logger
from repo_analyser.providers.base import LlmRequest, LlmResponse, ModelProvider
from repo_analyser.providers.huggingface import HuggingFaceProvider
from repo_analyser.providers.openrouter import OpenRouterProvider


class AutoFallbackProvider(ModelProvider):
    name = "auto-fallback"

    def __init__(self, settings: Settings) -> None:
        self.logger = get_logger(__name__, "llm-provider")
        self.providers: list[ModelProvider] = [
            OpenRouterProvider(settings),
            HuggingFaceProvider(settings),
        ]

    async def generate(self, request: LlmRequest) -> LlmResponse:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                self.logger.info("Attempting LLM generation with provider %s.", provider.name)
                return await provider.generate(request)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Provider %s failed: %s", provider.name, exc)
                last_error = exc
        self.logger.error("All LLM providers failed.")
        raise RuntimeError(f"All providers failed. Last error: {last_error}") from last_error
