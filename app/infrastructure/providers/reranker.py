from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from app.infrastructure.providers.client import build_ai_client
from app.infrastructure.providers.json_protocol import (
    parse_json_object,
)
from app.infrastructure.providers.settings import AIProviderSettings


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


class RerankerProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...

    def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[RerankResult]:
        ...


class APIRerankerProvider:
    def __init__(
        self,
        *,
        settings: AIProviderSettings,
    ) -> None:
        self.settings = settings
        self.client = build_ai_client(
            settings=settings,
            capability="reranker",
        )

    @property
    def name(self) -> str:
        return self.settings.provider

    @property
    def model(self) -> str:
        return self.settings.model_for("reranker")

    def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[RerankResult]:
        if not documents:
            return []

        requested = max(1, min(top_n, len(documents)))
        excerpts = [
            document[:self.settings.reranker_candidate_characters]
            for document in documents
        ]

        if self.settings.reranker_api_style == "rerank":
            data = self._call_rerank_endpoint(
                query=query,
                documents=excerpts,
                top_n=requested,
            )
        else:
            data = self._call_chat_reranker(
                query=query,
                documents=excerpts,
                top_n=requested,
            )

        return self._normalize_results(
            data=data,
            document_count=len(documents),
            top_n=requested,
        )

    def _call_rerank_endpoint(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> dict[str, Any]:
        response = self.client.post(
            "/rerank",
            cast_to=object,
            body={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": False,
            },
        )

        if not isinstance(response, dict):
            raise RuntimeError(
                "Reranker returned an invalid response."
            )

        return response

    def _call_chat_reranker(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "top_n": top_n,
            "candidates": [
                {"index": index, "text": text}
                for index, text in enumerate(documents)
            ],
            "required_output": {
                "results": [{"index": 0, "score": 0.0}]
            },
        }
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rank candidate texts by relevance. Return "
                        "JSON only with unique indices and scores "
                        "between 0 and 1."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=True),
                },
            ],
        )
        content = response.choices[0].message.content

        if not content:
            raise RuntimeError("Reranker returned empty content.")

        return parse_json_object(content)

    @staticmethod
    def _normalize_results(
        *,
        data: dict[str, Any],
        document_count: int,
        top_n: int,
    ) -> list[RerankResult]:
        results = data.get("results")

        if not isinstance(results, list):
            indices = data.get("indices")
            if isinstance(indices, list):
                results = [
                    {"index": index, "score": 1.0}
                    for index in indices
                ]

        if not isinstance(results, list):
            raise RuntimeError("Reranker response has no results.")

        normalized: list[RerankResult] = []
        seen: set[int] = set()

        for result in results:
            if not isinstance(result, dict):
                continue

            index = int(result.get("index", -1))
            score = float(
                result.get(
                    "relevance_score",
                    result.get("score", 0.0),
                )
            )

            if (
                index < 0
                or index >= document_count
                or index in seen
                or not 0 <= score <= 1
            ):
                raise RuntimeError(
                    "Reranker returned an invalid index or score."
                )

            seen.add(index)
            normalized.append(RerankResult(index=index, score=score))

        if len(normalized) < top_n:
            raise RuntimeError("Reranker returned too few results.")

        return normalized[:top_n]
