from __future__ import annotations

from groq import Groq

from src.config import settings
from src.llm.base import LLMConfigurationError, LLMResponseError

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_COMPLETION_TOKENS = 500


class GroqClient:
    """Groq chat-completions client using the configured model id."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        resolved_key = (api_key if api_key is not None else settings.llm.api_key) or ""
        resolved_model = (
            model if model is not None else settings.llm.model
        ).strip()

        if not resolved_key.strip():
            raise LLMConfigurationError(
                "GROQ_API_KEY is not set. Add it to .env locally or to "
                "Streamlit secrets when deployed, then restart the app."
            )
        if not resolved_model:
            raise LLMConfigurationError(
                "LLM_MODEL is not set. Add a Groq model id to .env locally or "
                "to Streamlit secrets when deployed, then restart the app."
            )

        self.model = resolved_model
        self._client = Groq(
            api_key=resolved_key.strip(),
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=1,
        )

    def complete(self, system: str, user: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001 - provider/network errors vary
            raise LLMResponseError(
                f"Groq request failed ({type(exc).__name__}). "
                "Check GROQ_API_KEY, LLM_MODEL, and network access."
            ) from exc

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise LLMResponseError("Groq returned an empty response.")
        return content
