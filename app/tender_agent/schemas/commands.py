from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterDocumentRequest(BaseModel):
    file_name: str = Field(
        min_length=1,
        max_length=512,
    )

    content_type: str | None = Field(
        default=None,
        max_length=255,
    )


class CreateTenderRequest(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=500,
    )

    external_reference: str | None = Field(
        default=None,
        max_length=255,
    )

    documents: list[RegisterDocumentRequest] = Field(
        min_length=1,
        max_length=100,
    )