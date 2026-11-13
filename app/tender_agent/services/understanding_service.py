from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.infrastructure.providers.llm import (
    LLMProvider,
)
from app.tender_agent.domain.retrieval import (
    StoredRetrievalChunk,
)
from app.tender_agent.domain.values import (
    FieldEvidenceDraft,
    FieldUnderstandingBuildResult,
    FieldUnderstandingDraft,
)
from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
    TenderFieldDefinition,
    TenderFieldSection,
)
from app.tender_agent.schemas.understanding import (
    LLMFieldUnderstanding,
)
from app.tender_agent.services.retrieval_service import (
    RetrievalService,
)


class UnderstandingService:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        retrieval_service: RetrievalService,
        prompt_path: Path,
        retrieval_limit: int = 8,
        minimum_confidence: float = 0.65,
        max_chunk_characters: int = 3500,
    ) -> None:
        if retrieval_limit <= 0:
            raise ValueError(
                "Field retrieval limit must be positive."
            )
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "Field confidence threshold must be "
                "between 0 and 1."
            )
        if max_chunk_characters <= 0:
            raise ValueError(
                "Maximum chunk characters must be positive."
            )

        self.llm = llm
        self.retrieval_service = retrieval_service
        self.prompt_path = prompt_path
        self.retrieval_limit = retrieval_limit
        self.minimum_confidence = minimum_confidence
        self.max_chunk_characters = (
            max_chunk_characters
        )
        self.system_prompt = self._load_prompt()

    def understand(
        self,
        *,
        catalog: TenderFieldCatalog,
        chunks: list[StoredRetrievalChunk],
    ) -> FieldUnderstandingBuildResult:
        if not chunks:
            raise ValueError(
                "No retrieval chunks were available for "
                "field understanding."
            )

        results: list[FieldUnderstandingDraft] = []
        warnings: list[str] = []

        for section, field in catalog.all_fields():
            try:
                field_result = self._understand_field(
                    catalog=catalog,
                    section=section,
                    field=field,
                    chunks=chunks,
                )
            except Exception as exc:
                warnings.append(
                    f"{field.key}: extraction failed: {exc}"
                )

                field_result = FieldUnderstandingDraft(
                    field_key=field.key,
                    section_key=section.key,
                    label=field.label,
                    value_type=field.value_type,
                    status="error",
                    raw_value=None,
                    display_value=None,
                    confidence=0.0,
                    explanation=(
                        "Field extraction failed before a "
                        "grounded result could be produced."
                    ),
                    search_query=self._build_search_query(
                        section=section,
                        field=field,
                    ),
                    needs_review=True,
                    evidence=[],
                )

            results.append(field_result)

        error_count = sum(
            result.status == "error"
            for result in results
        )

        if error_count == len(results):
            raise RuntimeError(
                "Every configured field failed extraction."
            )

        return FieldUnderstandingBuildResult(
            fields=results,
            configured_count=len(results),
            found_count=sum(
                result.status == "found"
                for result in results
            ),
            not_found_count=sum(
                result.status == "not_found"
                for result in results
            ),
            ambiguous_count=sum(
                result.status == "ambiguous"
                for result in results
            ),
            error_count=error_count,
            review_field_keys=[
                result.field_key
                for result in results
                if result.needs_review
            ],
            warnings=warnings,
        )

    def _understand_field(
        self,
        *,
        catalog: TenderFieldCatalog,
        section: TenderFieldSection,
        field: TenderFieldDefinition,
        chunks: list[StoredRetrievalChunk],
    ) -> FieldUnderstandingDraft:
        search_query = self._build_search_query(
            section=section,
            field=field,
        )

        search_result = self.retrieval_service.search(
            query=search_query,
            chunks=chunks,
            limit=self.retrieval_limit,
        )

        context_items = [
            self._context_from_hit(hit)
            for hit in search_result.hits
        ]

        user_prompt = self._build_user_prompt(
            catalog=catalog,
            section=section,
            field=field,
            context_items=context_items,
        )

        payload = self.llm.generate_json(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            deep=False,
        )

        llm_result = (
            LLMFieldUnderstanding.model_validate(
                payload
            )
        )

        evidence, grounding_warnings = (
            self._ground_evidence(
                llm_result=llm_result,
                context_items=context_items,
            )
        )
        grounding_warnings.extend(
            search_result.warnings
        )

        status = llm_result.status
        needs_review = bool(
            status == "ambiguous"
            or llm_result.confidence
            < self.minimum_confidence
            or grounding_warnings
        )

        if status == "found" and not evidence:
            status = "ambiguous"
            needs_review = True
            grounding_warnings.append(
                "Found value had no valid evidence."
            )

        explanation = llm_result.explanation

        if grounding_warnings:
            explanation = (
                f"{explanation} Grounding warnings: "
                + "; ".join(grounding_warnings)
            )

        return FieldUnderstandingDraft(
            field_key=field.key,
            section_key=section.key,
            label=field.label,
            value_type=field.value_type,
            status=status,
            raw_value=llm_result.raw_value,
            display_value=llm_result.display_value,
            confidence=llm_result.confidence,
            explanation=explanation,
            search_query=search_query,
            needs_review=needs_review,
            evidence=evidence,
        )

    def _build_search_query(
        self,
        *,
        section: TenderFieldSection,
        field: TenderFieldDefinition,
    ) -> str:
        guidance = field.retrieval_guidance

        parts = [
            field.label,
            field.description,
            field.prompt,
            section.prompt,
            *guidance.aliases,
            *guidance.anchor_phrases,
            *guidance.likely_sections,
        ]

        return "\n".join(
            part.strip()
            for part in parts
            if part and part.strip()
        )

    def _context_from_hit(
        self,
        hit: Any,
    ) -> dict[str, Any]:
        score = hit.final_score

        return {
            "chunk_id": str(hit.chunk_id),
            "logical_document_id": str(
                hit.logical_document_id
            ),
            "page_id": str(hit.page_id),
            "source_name": hit.source_name,
            "page_number": hit.page_number,
            "source_role": hit.source_role,
            "binding_status": (
                hit.binding_status
            ),
            "precedence_order": (
                hit.precedence_order
            ),
            "retrieval_score": float(score),
            "text": hit.text[
                : self.max_chunk_characters
            ],
        }

    def _build_user_prompt(
        self,
        *,
        catalog: TenderFieldCatalog,
        section: TenderFieldSection,
        field: TenderFieldDefinition,
        context_items: list[dict[str, Any]],
    ) -> str:
        request = {
            "catalog_instruction": catalog.prompt,
            "section": {
                "key": section.key,
                "label": section.label,
                "instruction": section.prompt,
            },
            "field": {
                "key": field.key,
                "label": field.label,
                "description": field.description,
                "value_type": field.value_type,
                "instruction": field.prompt,
            },
            "retrieved_context": context_items,
        }

        return (
            "Extract the configured field from this input:\n"
            + json.dumps(
                request,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

    def _ground_evidence(
        self,
        *,
        llm_result: LLMFieldUnderstanding,
        context_items: list[dict[str, Any]],
    ) -> tuple[
        list[FieldEvidenceDraft],
        list[str],
    ]:
        context_by_id = {
            item["chunk_id"]: item
            for item in context_items
        }

        grounded: list[FieldEvidenceDraft] = []
        warnings: list[str] = []

        for reference in llm_result.evidence:
            chunk_id = str(reference.chunk_id)
            context = context_by_id.get(chunk_id)

            if context is None:
                warnings.append(
                    f"Unknown evidence chunk {chunk_id}."
                )
                continue

            if not self._quote_is_supported(
                quote=reference.quote,
                text=context["text"],
            ):
                warnings.append(
                    f"Evidence quote was not found in "
                    f"chunk {chunk_id}."
                )
                continue

            grounded.append(
                FieldEvidenceDraft(
                    chunk_id=reference.chunk_id,
                    logical_document_id=(
                        self._to_uuid(
                            context[
                                "logical_document_id"
                            ]
                        )
                    ),
                    page_id=self._to_uuid(
                        context["page_id"]
                    ),
                    source_name=context["source_name"],
                    page_number=context["page_number"],
                    source_role=context["source_role"],
                    binding_status=(
                        context["binding_status"]
                    ),
                    precedence_order=(
                        context["precedence_order"]
                    ),
                    quote=reference.quote,
                    retrieval_score=(
                        context["retrieval_score"]
                    ),
                )
            )

        return grounded, warnings

    @staticmethod
    def _quote_is_supported(
        *,
        quote: str,
        text: str,
    ) -> bool:
        normalize = lambda value: re.sub(
            r"\s+",
            " ",
            value.casefold(),
        ).strip()

        normalized_quote = normalize(quote)
        normalized_text = normalize(text)

        return bool(
            normalized_quote
            and normalized_quote in normalized_text
        )

    @staticmethod
    def _to_uuid(value: str):
        from uuid import UUID

        return UUID(value)

    def _load_prompt(self) -> str:
        if not self.prompt_path.is_file():
            raise RuntimeError(
                "Field-understanding prompt was not "
                f"found: {self.prompt_path}"
            )

        parsed = yaml.safe_load(
            self.prompt_path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(parsed, dict):
            raise RuntimeError(
                "Field-understanding prompt must be "
                "an object."
            )

        prompt = parsed.get("system_prompt")

        if not isinstance(prompt, str) or not prompt.strip():
            raise RuntimeError(
                "Field-understanding system_prompt is "
                "missing."
            )

        return prompt.strip()
