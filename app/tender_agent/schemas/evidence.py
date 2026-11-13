from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LLMFieldEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    quote: str = Field(min_length=1, max_length=2000)


class GroundedFieldEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    logical_document_id: UUID
    page_id: UUID

    source_name: str
    page_number: int

    source_role: str
    binding_status: str
    precedence_order: int

    quote: str
    retrieval_score: float