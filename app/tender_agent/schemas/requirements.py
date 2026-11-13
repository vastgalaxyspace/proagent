from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


RequirementObligation = Literal[
    "mandatory",
    "conditional",
    "informational",
]


class RequirementCategoryDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    label: str = Field(
        min_length=1,
        max_length=255,
    )
    description: str = Field(
        min_length=1,
        max_length=4000,
    )
    retrieval_query: str = Field(
        min_length=1,
        max_length=4000,
    )


class RequirementCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: str = Field(
        min_length=1,
        max_length=255,
    )
    schema_version: str = Field(
        min_length=1,
        max_length=100,
    )
    categories: list[
        RequirementCategoryDefinition
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_categories(
        self,
    ) -> "RequirementCatalog":
        keys = [
            category.key
            for category in self.categories
        ]

        if len(keys) != len(set(keys)):
            raise ValueError(
                "Requirement category keys must be unique."
            )

        return self


class LLMRequirementEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    quote: str = Field(
        min_length=1,
        max_length=5000,
    )


class LLMRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=3,
        max_length=255,
    )
    requirement_text: str = Field(
        min_length=5,
        max_length=10000,
    )
    obligation_level: RequirementObligation

    condition_text: str | None = Field(
        default=None,
        max_length=5000,
    )

    bidder_proof: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    evidence: list[LLMRequirementEvidence] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_condition(
        self,
    ) -> "LLMRequirement":
        if (
            self.obligation_level == "conditional"
            and not self.condition_text
        ):
            raise ValueError(
                "A conditional requirement must describe "
                "its condition."
            )

        return self


class LLMRequirementBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[LLMRequirement] = Field(
        default_factory=list,
        max_length=200,
    )