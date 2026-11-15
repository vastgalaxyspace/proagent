from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

from app.infrastructure.providers.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
)
from app.infrastructure.providers.reranker import (
    RerankerProvider,
)
from app.tender_agent.domain.retrieval import (
    RetrievalBuildResult,
    RetrievalChunkDraft,
    RetrievalHit,
    RetrievalSearchResult,
    RetrievalSourcePage,
    StoredRetrievalChunk,
)


@dataclass(frozen=True)
class RetrievalLimits:
    chunk_characters: int = 1200
    chunk_overlap_characters: int = 200
    search_candidate_pool: int = 24


class RetrievalService:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        reranker_provider: RerankerProvider,
        limits: RetrievalLimits,
    ) -> None:
        if limits.chunk_characters <= 0:
            raise ValueError(
                "Chunk size must be positive."
            )

        if limits.chunk_overlap_characters < 0:
            raise ValueError(
                "Chunk overlap cannot be negative."
            )

        if (
            limits.chunk_overlap_characters
            >= limits.chunk_characters
        ):
            raise ValueError(
                "Chunk overlap must be smaller than "
                "the chunk size."
            )

        if limits.search_candidate_pool <= 0:
            raise ValueError(
                "Search candidate pool must be positive."
            )

        self.embedding_provider = (
            embedding_provider
        )
        self.reranker_provider = (
            reranker_provider
        )
        self.limits = limits

    @property
    def embedding_provider_name(self) -> str:
        return self.embedding_provider.name

    @property
    def embedding_model(self) -> str:
        return self.embedding_provider.model

    @property
    def embedding_dimensions(self) -> int:
        return self.embedding_provider.dimensions

    @property
    def reranker_provider_name(self) -> str:
        return self.reranker_provider.name

    @property
    def reranker_model(self) -> str:
        return self.reranker_provider.model

    def build_index(
        self,
        pages: list[RetrievalSourcePage],
    ) -> RetrievalBuildResult:
        ordered_pages = sorted(
            pages,
            key=lambda page: (
                page.precedence_order,
                str(page.logical_document_id),
                page.page_number,
            ),
        )

        pending_chunks: list[
            tuple[
                RetrievalSourcePage,
                int,
                str | None,
                str,
            ]
        ] = []

        sequence_by_document: dict = {}
        indexed_page_count = 0
        skipped_page_count = 0

        for page in ordered_pages:
            normalized_text = self._normalize_text(
                page.text
            )

            if not normalized_text:
                skipped_page_count += 1
                continue

            indexed_page_count += 1

            heading = self._extract_heading(
                normalized_text
            )

            pieces = self._split_text(
                normalized_text
            )

            for piece in pieces:
                sequence_number = (
                    sequence_by_document.get(
                        page.logical_document_id,
                        0,
                    )
                    + 1
                )

                sequence_by_document[
                    page.logical_document_id
                ] = sequence_number

                pending_chunks.append(
                    (
                        page,
                        sequence_number,
                        heading,
                        piece,
                    )
                )

        if not pending_chunks:
            return RetrievalBuildResult(
                chunks=[],
                indexed_page_count=0,
                skipped_page_count=(
                    skipped_page_count
                ),
            )

        embeddings = (
            self.embedding_provider.embed_texts(
                [
                    piece
                    for _, _, _, piece
                    in pending_chunks
                ]
            )
        )

        if len(embeddings) != len(
            pending_chunks
        ):
            raise RuntimeError(
                "Embedding provider did not return "
                "one vector for every chunk."
            )

        chunks: list[RetrievalChunkDraft] = []

        for (
            page,
            sequence_number,
            heading,
            piece,
        ), embedding in zip(
            pending_chunks,
            embeddings,
            strict=True,
        ):
            chunks.append(
                RetrievalChunkDraft(
                    logical_document_id=(
                        page.logical_document_id
                    ),
                    document_id=page.document_id,
                    page_id=page.page_id,
                    sequence_number=sequence_number,
                    source_role=page.source_role,
                    binding_status=(
                        page.binding_status
                    ),
                    precedence_order=(
                        page.precedence_order
                    ),
                    logical_document_title=(
                        page.logical_document_title
                    ),
                    heading=heading,
                    source_name=page.source_name,
                    page_number=page.page_number,
                    source_page_number=(
                        page.source_page_number
                    ),
                    text=piece,
                    token_count=len(
                        self._tokenize(piece)
                    ),
                    chunk_hash=hashlib.sha256(
                        piece.encode("utf-8")
                    ).hexdigest(),
                    embedding=embedding,
                )
            )

        return RetrievalBuildResult(
            chunks=chunks,
            indexed_page_count=(
                indexed_page_count
            ),
            skipped_page_count=(
                skipped_page_count
            ),
        )

    def search(
        self,
        *,
        query: str,
        chunks: list[StoredRetrievalChunk],
        limit: int = 8,
        minimum_score: float = 0.05,
    ) -> RetrievalSearchResult:
        normalized_query = self._normalize_text(
            query
        )

        if not normalized_query or not chunks:
            return RetrievalSearchResult(
                query=normalized_query,
                hits=[],
                retrieval_mode="empty",
                reranker_degraded=False,
                warnings=[],
            )

        query_embedding = (
            self.embedding_provider.embed_query(
                normalized_query
            )
        )

        query_tokens = set(
            self._tokenize(normalized_query)
        )

        maximum_precedence = max(
            chunk.precedence_order
            for chunk in chunks
        )

        initial_hits: list[RetrievalHit] = []

        for chunk in chunks:
            vector_score = max(
                0.0,
                cosine_similarity(
                    query_embedding,
                    chunk.embedding,
                ),
            )

            chunk_tokens = set(
                self._tokenize(chunk.text)
            )

            keyword_score = (
                len(query_tokens & chunk_tokens)
                / len(query_tokens)
                if query_tokens
                else 0.0
            )

            if (
                normalized_query.casefold()
                in chunk.text.casefold()
            ):
                keyword_score = min(
                    1.0,
                    keyword_score + 0.20,
                )

            authority_score = (
                self._authority_score(
                    binding_status=(
                        chunk.binding_status
                    ),
                    source_role=chunk.source_role,
                    precedence_order=(
                        chunk.precedence_order
                    ),
                    maximum_precedence=(
                        maximum_precedence
                    ),
                )
            )

            initial_score = (
                vector_score * 0.55
                + keyword_score * 0.30
                + authority_score * 0.15
            )

            if initial_score < minimum_score:
                continue

            initial_hits.append(
                RetrievalHit(
                    chunk_id=chunk.chunk_id,
                    logical_document_id=(
                        chunk.logical_document_id
                    ),
                    document_id=chunk.document_id,
                    page_id=chunk.page_id,
                    text=chunk.text,
                    heading=chunk.heading,
                    source_name=chunk.source_name,
                    page_number=chunk.page_number,
                    source_page_number=(
                        chunk.source_page_number
                    ),
                    source_role=chunk.source_role,
                    binding_status=(
                        chunk.binding_status
                    ),
                    precedence_order=(
                        chunk.precedence_order
                    ),
                    vector_score=round(
                        vector_score,
                        6,
                    ),
                    keyword_score=round(
                        keyword_score,
                        6,
                    ),
                    authority_score=round(
                        authority_score,
                        6,
                    ),
                    reranker_score=None,
                    final_score=round(
                        initial_score,
                        6,
                    ),
                )
            )

        initial_hits.sort(
            key=lambda hit: (
                -hit.final_score,
                -hit.precedence_order,
                hit.page_number,
                str(hit.chunk_id),
            )
        )

        candidate_count = max(
            limit,
            self.limits.search_candidate_pool,
        )

        candidate_pool = initial_hits[
            :candidate_count
        ]

        if not candidate_pool:
            return RetrievalSearchResult(
                query=normalized_query,
                hits=[],
                retrieval_mode="hybrid",
                reranker_degraded=False,
                warnings=[],
            )

        try:
            reranked = (
                self.reranker_provider.rerank(
                    query=normalized_query,
                    documents=[
                        hit.text
                        for hit in candidate_pool
                    ],
                    top_n=min(
                        limit,
                        len(candidate_pool),
                    ),
                )
            )

            final_hits = [
                replace(
                    candidate_pool[result.index],
                    reranker_score=round(
                        result.score,
                        6,
                    ),
                    final_score=round(
                        result.score * 0.70
                        + candidate_pool[
                            result.index
                        ].final_score
                        * 0.30,
                        6,
                    ),
                )
                for result in reranked
            ]

            final_hits.sort(
                key=lambda hit: (
                    -hit.final_score,
                    -hit.precedence_order,
                    hit.page_number,
                )
            )

            return RetrievalSearchResult(
                query=normalized_query,
                hits=final_hits[:limit],
                retrieval_mode=(
                    "embedding_keyword_authority_"
                    "reranker"
                ),
                reranker_degraded=False,
                warnings=[],
            )

        except Exception as exc:
            return RetrievalSearchResult(
                query=normalized_query,
                hits=candidate_pool[:limit],
                retrieval_mode=(
                    "embedding_keyword_authority"
                ),
                reranker_degraded=True,
                warnings=[
                    "Reranker was unavailable; hybrid "
                    f"ranking was used: {str(exc)[:200]}"
                ],
            )

    def _split_text(
        self,
        text: str,
    ) -> list[str]:
        maximum = self.limits.chunk_characters
        overlap = (
            self.limits.chunk_overlap_characters
        )

        if len(text) <= maximum:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < len(text):
            proposed_end = min(
                start + maximum,
                len(text),
            )
            end = proposed_end

            if proposed_end < len(text):
                minimum_break = (
                    start + maximum // 2
                )

                break_candidates = [
                    text.rfind(
                        "\n\n",
                        minimum_break,
                        proposed_end,
                    ),
                    text.rfind(
                        ". ",
                        minimum_break,
                        proposed_end,
                    ),
                    text.rfind(
                        " ",
                        minimum_break,
                        proposed_end,
                    ),
                ]

                valid_breaks = [
                    position
                    for position in break_candidates
                    if position > start
                ]

                if valid_breaks:
                    end = max(valid_breaks)

                    if text[end:end + 2] == ". ":
                        end += 1

            piece = text[start:end].strip()

            if piece:
                chunks.append(piece)

            if end >= len(text):
                break

            next_start = max(
                end - overlap,
                start + 1,
            )

            while (
                next_start < len(text)
                and text[next_start].isspace()
            ):
                next_start += 1

            start = next_start

        return chunks

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:
        lines = [
            re.sub(
                r"[ \t]+",
                " ",
                line,
            ).strip()
            for line in text.replace(
                "\r\n",
                "\n",
            ).replace(
                "\r",
                "\n",
            ).splitlines()
        ]

        normalized_lines: list[str] = []
        previous_empty = False

        for line in lines:
            is_empty = not line

            if is_empty and previous_empty:
                continue

            normalized_lines.append(line)
            previous_empty = is_empty

        return "\n".join(
            normalized_lines
        ).strip()

    @staticmethod
    def _extract_heading(
        text: str,
    ) -> str | None:
        for line in text.splitlines():
            normalized = line.strip()

            if normalized:
                return normalized[:500]

        return None

    @staticmethod
    def _tokenize(
        text: str,
    ) -> list[str]:
        return re.findall(
            r"[a-z0-9]+",
            text.casefold(),
        )

    @staticmethod
    def _authority_score(
        *,
        binding_status: str,
        source_role: str,
        precedence_order: int,
        maximum_precedence: int,
    ) -> float:
        binding_scores = {
            "binding": 1.0,
            "review_required": 0.5,
            "non_binding": 0.0,
        }

        binding_score = binding_scores.get(
            binding_status,
            0.0,
        )

        precedence_score = (
            precedence_order
            / maximum_precedence
            if maximum_precedence > 0
            else 0.0
        )

        amendment_bonus = (
            0.15
            if (
                binding_status == "binding"
                and source_role
                in {"corrigendum", "prebid_clarification"}
            )
            else 0.0
        )

        return min(
            1.0,
            binding_score * 0.70
            + precedence_score * 0.30
            + amendment_bonus,
        )
