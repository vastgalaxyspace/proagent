from __future__ import annotations

from openai import OpenAI

from app.infrastructure.providers.settings import (
    AIProviderSettings,
    Capability,
)


def build_ai_client(
    *,
    settings: AIProviderSettings,
    capability: Capability,
) -> OpenAI:
    settings.validate_capability(capability)

    return OpenAI(
        api_key=settings.api_key_for(capability),
        base_url=settings.base_url_for(capability),
        timeout=settings.timeout_for(capability),
        max_retries=settings.max_retries,
    )
