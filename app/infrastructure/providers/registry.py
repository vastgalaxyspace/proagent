from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.providers.embeddings import (
    APIEmbeddingProvider,
    EmbeddingProvider,
)
from app.infrastructure.providers.llm import APILLMProvider, LLMProvider
from app.infrastructure.providers.reranker import (
    APIRerankerProvider,
    RerankerProvider,
)
from app.infrastructure.providers.settings import (
    AIProviderSettings,
    get_ai_provider_settings,
)


@dataclass(frozen=True)
class AIProviderRegistry:
    settings: AIProviderSettings
    llm: LLMProvider
    verifier: LLMProvider
    embeddings: EmbeddingProvider
    reranker: RerankerProvider


def build_ai_provider_registry() -> AIProviderRegistry:
    settings = get_ai_provider_settings()

    for capability in (
        "primary",
        "embedding",
        "reranker",
        "verifier",
    ):
        settings.validate_capability(capability)

    return AIProviderRegistry(
        settings=settings,
        llm=APILLMProvider(
            settings=settings,
            capability="primary",
        ),
        verifier=APILLMProvider(
            settings=settings,
            capability="verifier",
        ),
        embeddings=APIEmbeddingProvider(settings=settings),
        reranker=APIRerankerProvider(settings=settings),
    )
