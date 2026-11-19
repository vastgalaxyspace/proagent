from __future__ import annotations

import logging
import math
from typing import Any, Protocol, Sequence

from app.infrastructure.providers.client import build_ai_client
from app.infrastructure.providers.settings import AIProviderSettings
from app.infrastructure.providers.usage import record_ai_usage


logger = logging.getLogger(__name__)


def _order_embedding_items(
    items: Sequence[Any],
    *,
    expected_count: int,
) -> list[Any]:
    """Return provider embeddings in input order.

    OpenAI-compatible providers do not consistently populate the optional
    response ``index``. Use it only when the complete batch contains a valid
    permutation; otherwise retain the provider's response order, matching the
    compatibility behavior used by the previous procurement service.
    """

    ordered_items = list(items)

    if len(ordered_items) != expected_count:
        raise RuntimeError(
            "Embedding provider returned an incomplete batch."
        )

    indices = [
        getattr(item, "index", None)
        for item in ordered_items
    ]
    has_complete_integer_indices = all(
        isinstance(index, int)
        and not isinstance(index, bool)
        for index in indices
    )

    if not has_complete_integer_indices:
        logger.warning(
            "Embedding provider returned missing or non-integer "
            "response indexes; preserving provider response order."
        )
        return ordered_items

    if set(indices) != set(range(expected_count)):
        raise RuntimeError(
            "Embedding provider returned invalid response indexes."
        )

    return sorted(
        ordered_items,
        key=lambda item: item.index,
    )


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
            record_ai_usage(
                response=response,
                provider=self.name,
                model=self.model,
                capability="embedding",
            )
            ordered_items = _order_embedding_items(
                response.data,
                expected_count=len(batch),
            )
            received = [
                self._validate_vector(item.embedding)
                for item in ordered_items
            ]

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
