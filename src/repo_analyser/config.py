from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Open Source Repo Analyser"
    host: str = "127.0.0.1"
    port: int = 8000
    github_api_base: str = "https://api.github.com"
    github_token: str | None = None
    github_cache_ttl_seconds: int = 600
    cache_dir: Path = Field(default_factory=lambda: Path(".cache/repo-analyser"))
    output_dir: Path = Field(default_factory=lambda: Path("generated_issues"))
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "deepseek/deepseek-r1-distill-llama-70b"
    huggingface_api_key: str | None = None
    huggingface_base_url: str = "https://api-inference.huggingface.co/models"
    huggingface_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    reasoning_temperature: float = 0.2
    lightweight_temperature: float = 0.1
    request_timeout_seconds: float = 45.0
    max_markdown_issues: int = 25
    log_level: str = "INFO"
    log_to_file: bool = True
    log_dir: Path = Field(default_factory=lambda: Path("logs"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    return settings
