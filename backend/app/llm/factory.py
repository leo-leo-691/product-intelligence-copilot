"""Provider factory — selects Gemini or Claude from configuration."""
from __future__ import annotations

from backend.app.config import settings
from backend.app.llm.base import LLMProvider
from backend.app.llm.claude_provider import ClaudeProvider
from backend.app.llm.gemini_provider import GeminiProvider

SUPPORTED = ("gemini", "anthropic")


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    name = (provider_name or settings.llm_provider or "gemini").strip().lower()
    if name == "gemini":
        return GeminiProvider()
    if name == "anthropic":
        return ClaudeProvider()
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {name}. Supported providers are gemini and anthropic."
    )


def require_configured_provider(provider_name: str | None = None) -> LLMProvider:
    """Return provider; raise clear errors for anthropic-without-key."""
    provider = get_llm_provider(provider_name)
    if provider.is_configured():
        return provider
    if provider.name == "anthropic":
        raise RuntimeError(
            "Anthropic provider selected but ANTHROPIC_API_KEY is not configured."
        )
    if provider.name == "gemini":
        raise RuntimeError(
            "Gemini provider selected but GEMINI_API_KEY is not configured."
        )
    raise RuntimeError(f"LLM provider '{provider.name}' is not configured.")
