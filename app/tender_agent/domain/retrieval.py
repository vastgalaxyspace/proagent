from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievalSourcePage:
    source_plan_id: UUID
    logical_document_id: UUID
    document_id: UUID
    page_id: UUID

    source_role: str
    binding_status: str
    precedence_order: int

    logical_document_title: str
    source_name: str

    page_number: int
    source_page_number: int
    text: str


@dataclass(frozen=True)
class RetrievalChunkDraft:
    logical_document_id: UUID
    document_id: UUID
    page_id: UUID

    sequence_number: int

    source_role: str
    binding_status: str
    precedence_order: int

    logical_document_title: str
    heading: str | None
    source_name: str

    page_number: int
    source_page_number: int

    text: str
    token_count: int
    chunk_hash: str
    embedding: list[float]


@dataclass(frozen=True)
class RetrievalBuildResult:
    chunks: list[RetrievalChunkDraft]
    indexed_page_count: int
    skipped_page_count: int


@dataclass(frozen=True)
class StoredRetrievalChunk:
    chunk_id: UUID
    logical_document_id: UUID
    document_id: UUID
    page_id: UUID

    source_role: str
    binding_status: str
    precedence_order: int

    logical_document_title: str
    heading: str | None
    source_name: str

    page_number: int
    source_page_number: int

    text: str
    embedding: list[float]


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: UUID
    logical_document_id: UUID
    document_id: UUID
    page_id: UUID

    text: str
    heading: str | None
    source_name: str

    page_number: int
    source_page_number: int

    source_role: str
    binding_status: str
    precedence_order: int

    vector_score: float
    keyword_score: float
    authority_score: float
    reranker_score: float | None
    final_score: float


@dataclass(frozen=True)
class RetrievalSearchResult:
    query: str
    hits: list[RetrievalHit]
    retrieval_mode: str
    reranker_degraded: bool
    warnings: list[str]