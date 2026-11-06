from __future__ import annotations

from typing import Protocol


class LLMError(RuntimeError):
    """Base error for LLM configuration or response failures."""


class LLMConfigurationError(LLMError):
    """Raised when the provider or credentials are not configured."""


class LLMResponseError(LLMError):
    """Raised when the provider returns an unusable response."""


class LLMClient(Protocol):
    """Provider interface: one system prompt plus one user prompt."""

    def complete(self, system: str, user: str) -> str:
        ...
