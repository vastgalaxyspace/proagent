from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMAmendmentOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "replace",
        "add",
        "delete",
        "clarify",
    ]
    target: str = Field(min_length=1, max_length=500)
    previous_value: Any | None = None
    revised_value: Any | None = None
    page_id: UUID
    evidence_quote: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_values(self) -> "LLMAmendmentOperation":
        if (
            self.operation in {"replace", "add", "clarify"}
            and self.revised_value is None
        ):
            raise ValueError(
                "This amendment operation requires a revised value."
            )
        return self


class LLMAmendmentBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[LLMAmendmentOperation] = Field(
        default_factory=list,
        max_length=100,
    )
