from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrievalGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = Field(default_factory=list)
    anchor_phrases: list[str] = Field(default_factory=list)
    likely_sections: list[str] = Field(default_factory=list)


class TenderFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    value_type: str = Field(min_length=1, max_length=50)
    prompt: str = Field(min_length=1)

    retrieval_guidance: RetrievalGuidance = Field(
        default_factory=RetrievalGuidance
    )


class TenderFieldSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1)
    fields: list[TenderFieldDefinition] = Field(
        min_length=1
    )


class TenderFieldCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    schema_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    sections: list[TenderFieldSection] = Field(
        min_length=1
    )

    def all_fields(
        self,
    ) -> list[
        tuple[TenderFieldSection, TenderFieldDefinition]
    ]:
        return [
            (section, field)
            for section in self.sections
            for field in section.fields
        ]