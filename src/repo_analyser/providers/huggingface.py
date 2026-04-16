from __future__ import annotations

import httpx

from repo_analyser.config import Settings
from repo_analyser.logging_utils import get_logger
from repo_analyser.providers.base import LlmRequest, LlmResponse, ModelProvider


class HuggingFaceProvider(ModelProvider):
    name = "huggingface"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger(__name__, "huggingface")
        self.client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.huggingface_api_key}"},
        )

    async def generate(self, request: LlmRequest) -> LlmResponse:
        if not self.settings.huggingface_api_key:
            raise RuntimeError("HUGGINGFACE_API_KEY is not configured.")
        self.logger.info("Sending generation request to HuggingFace model %s.", self.settings.huggingface_model)
        response = await self.client.post(
            f"{self.settings.huggingface_base_url}/{self.settings.huggingface_model}",
            json={
                "inputs": f"{request.system_prompt}\n\n{request.user_prompt}",
                "parameters": {"temperature": request.temperature, "return_full_text": False},
            },
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload:
            text = payload[0].get("generated_text", "")
        else:
            text = str(payload)
        self.logger.info("HuggingFace generation completed successfully.")
        return LlmResponse(provider=self.name, model=self.settings.huggingface_model, text=text)
