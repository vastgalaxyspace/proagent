from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.tender_agent.schemas.evidence import (
    LLMFieldEvidence,
)


FieldExtractionStatus = Literal[
    "found",
    "not_found",
    "ambiguous",
]


class LLMFieldUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FieldExtractionStatus

    raw_value: Any | None = None
    display_value: str | None = None

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    explanation: str = Field(
        min_length=1,
        max_length=4000,
    )

    evidence: list[LLMFieldEvidence] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_status_and_value(
        self,
    ) -> "LLMFieldUnderstanding":
        if self.status == "not_found":
            self.raw_value = None
            self.display_value = None
            self.evidence = []

        if (
            self.status == "found"
            and self.raw_value is None
        ):
            raise ValueError(
                "A found field must contain raw_value."
            )

        return self