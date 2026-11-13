from __future__ import annotations

import math
from typing import Protocol

from app.infrastructure.providers.client import build_ai_client
from app.infrastructure.providers.settings import AIProviderSettings


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...

    @property
    def dimensions(self) -> int:
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, query: str) -> list[float]:
        ...


class APIEmbeddingProvider:
    def __init__(
        self,
        *,
        settings: AIProviderSettings,
    ) -> None:
        self.settings = settings
        self.client = build_ai_client(
            settings=settings,
            capability="embedding",
        )

    @property
    def name(self) -> str:
        return self.settings.provider

    @property
    def model(self) -> str:
        return self.settings.model_for("embedding")

    @property
    def dimensions(self) -> int:
        return self.settings.embedding_dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        batch_size = self.settings.embedding_batch_size

        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            ordered_items = sorted(
                response.data,
                key=lambda item: item.index,
            )
            received = [
                self._validate_vector(item.embedding)
                for item in ordered_items
            ]

            if len(received) != len(batch):
                raise RuntimeError(
                    "Embedding provider returned an incomplete batch."
                )

            vectors.extend(received)

        if len(vectors) != len(texts):
            raise RuntimeError(
                "Embedding provider did not return one vector "
                "for every input."
            )

        return vectors

    def embed_query(self, query: str) -> list[float]:
        vectors = self.embed_texts([query])

        if len(vectors) != 1:
            raise RuntimeError(
                "Embedding provider did not return a query vector."
            )

        return vectors[0]

    def _validate_vector(self, vector: list[float]) -> list[float]:
        normalized = [float(value) for value in vector]

        if not normalized:
            raise RuntimeError(
                "Embedding provider returned an empty vector."
            )
        if any(not math.isfinite(value) for value in normalized):
            raise RuntimeError(
                "Embedding provider returned a non-finite vector."
            )
        if len(normalized) != self.dimensions:
            raise RuntimeError(
                "Embedding vector dimensions do not match "
                "AI_EMBEDDING_DIMENSIONS."
            )

        return normalized


def cosine_similarity(
    first: list[float],
    second: list[float],
) -> float:
    if len(first) != len(second):
        raise ValueError("Embedding dimensions do not match.")

    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    denominator = first_norm * second_norm

    if denominator == 0:
        return 0.0

    return sum(
        left * right
        for left, right in zip(first, second)
    ) / denominator
