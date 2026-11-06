from __future__ import annotations

from src.config import settings
from src.llm.base import (
    LLMClient,
    LLMConfigurationError,
    LLMError,
    LLMResponseError,
)
from src.llm.groq_client import GroqClient

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMConfigurationError",
    "LLMResponseError",
    "GroqClient",
    "get_llm_client",
]


def get_llm_client() -> LLMClient:
    provider = (settings.llm.provider or "").strip().lower()
    if provider == "groq":
        return GroqClient()
    raise LLMConfigurationError(
        f"Unsupported LLM provider {provider!r}. Configure llm.provider: groq."
    )
