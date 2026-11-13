from __future__ import annotations

import hashlib
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
    RequirementBuildResult,
    RequirementDraft,
    RequirementEvidenceDraft,
)
from app.tender_agent.schemas.requirements import (
    LLMRequirementBatch,
    RequirementCatalog,
    RequirementCategoryDefinition,
)
from app.tender_agent.services.retrieval_service import (
    RetrievalService,
)


class RequirementService:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        retrieval_service: RetrievalService,
        catalog_path: Path,
        prompt_path: Path,
        retrieval_limit: int = 12,
        minimum_confidence: float = 0.65,
        max_chunk_characters: int = 3500,
    ) -> None:
        if retrieval_limit <= 0:
            raise ValueError(
                "Requirement retrieval limit must be "
                "positive."
            )

        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "Requirement confidence must be between "
                "0 and 1."
            )

        if max_chunk_characters <= 0:
            raise ValueError(
                "Maximum chunk characters must be positive."
            )

        self.llm = llm
        self.retrieval_service = retrieval_service
        self.retrieval_limit = retrieval_limit
        self.minimum_confidence = minimum_confidence
        self.max_chunk_characters = (
            max_chunk_characters
        )

        self.catalog = self._load_catalog(catalog_path)
        self.system_prompt = self._load_prompt(
            prompt_path
        )

    def build(
        self,
        *,
        chunks: list[StoredRetrievalChunk],
    ) -> RequirementBuildResult:
        if not chunks:
            raise ValueError(
                "No retrieval chunks were available for "
                "requirement extraction."
            )

        requirements: list[RequirementDraft] = []
        warnings: list[str] = []

        for category in self.catalog.categories:
            try:
                category_requirements, category_warnings = (
                    self._extract_category(
                        category=category,
                        chunks=chunks,
                    )
                )
            except Exception as exc:
                warnings.append(
                    f"{category.key}: requirement "
                    f"extraction failed: {exc}"
                )
                continue

            requirements.extend(category_requirements)
            warnings.extend(category_warnings)

        requirements = self._deduplicate(requirements)

        if not requirements:
            raise RuntimeError(
                "No grounded tender requirements could "
                "be extracted."
            )

        return RequirementBuildResult(
            requirements=requirements,
            requirement_count=len(requirements),
            mandatory_count=sum(
                item.obligation_level == "mandatory"
                for item in requirements
            ),
            conditional_count=sum(
                item.obligation_level == "conditional"
                for item in requirements
            ),
            informational_count=sum(
                item.obligation_level == "informational"
                for item in requirements
            ),
            review_requirement_codes=[
                item.requirement_code
                for item in requirements
                if item.needs_review
            ],
            warnings=warnings,
        )

    def _extract_category(
        self,
        *,
        category: RequirementCategoryDefinition,
        chunks: list[StoredRetrievalChunk],
    ) -> tuple[list[RequirementDraft], list[str]]:
        search_result = self.retrieval_service.search(
            query=category.retrieval_query,
            chunks=chunks,
            limit=self.retrieval_limit,
        )

        context_items = [
            self._context_from_hit(hit)
            for hit in search_result.hits
        ]

        if not context_items:
            return [], [
                f"{category.key}: no relevant chunks "
                "were retrieved."
            ]

        request_payload = {
            "category": category.model_dump(),
            "retrieved_context": context_items,
        }

        payload = self.llm.generate_json(
            system_prompt=self.system_prompt,
            user_prompt=(
                "Extract tender requirements for this "
                "category:\n"
                + json.dumps(
                    request_payload,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            ),
            deep=False,
        )

        llm_batch = LLMRequirementBatch.model_validate(
            payload
        )

        context_by_id = {
            item["chunk_id"]: item
            for item in context_items
        }

        requirements: list[RequirementDraft] = []
        warnings = list(search_result.warnings)

        for item in llm_batch.requirements:
            evidence, grounding_warnings = (
                self._ground_evidence(
                    references=item.evidence,
                    context_by_id=context_by_id,
                )
            )

            requirement_code = (
                self._requirement_code(
                    category_key=category.key,
                    requirement_text=(
                        item.requirement_text
                    ),
                )
            )

            needs_review = bool(
                item.confidence
                < self.minimum_confidence
                or grounding_warnings
                or not evidence
                or any(
                    evidence_item.binding_status
                    != "binding"
                    for evidence_item in evidence
                )
            )

            requirements.append(
                RequirementDraft(
                    requirement_code=(
                        requirement_code
                    ),
                    category_key=category.key,
                    category_label=category.label,
                    title=self._clean_text(
                        item.title
                    ),
                    requirement_text=(
                        self._clean_text(
                            item.requirement_text
                        )
                    ),
                    obligation_level=(
                        item.obligation_level
                    ),
                    condition_text=(
                        self._clean_optional_text(
                            item.condition_text
                        )
                    ),
                    bidder_proof=list(
                        dict.fromkeys(
                            self._clean_text(proof)
                            for proof in item.bidder_proof
                            if proof.strip()
                        )
                    ),
                    confidence=item.confidence,
                    needs_review=needs_review,
                    evidence=evidence,
                    warnings=grounding_warnings,
                )
            )

        return requirements, warnings

    def _ground_evidence(
        self,
        *,
        references: list[Any],
        context_by_id: dict[str, dict[str, Any]],
    ) -> tuple[
        list[RequirementEvidenceDraft],
        list[str],
    ]:
        evidence: list[RequirementEvidenceDraft] = []
        warnings: list[str] = []
        seen: set[tuple[str, str]] = set()

        for reference in references:
            chunk_id = str(reference.chunk_id)
            context = context_by_id.get(chunk_id)

            if context is None:
                warnings.append(
                    f"Unknown evidence chunk {chunk_id}."
                )
                continue

            quote = self._clean_text(reference.quote)

            if not self._quote_is_supported(
                quote=quote,
                text=context["text"],
            ):
                warnings.append(
                    "Evidence quote was not found in "
                    f"chunk {chunk_id}."
                )
                continue

            evidence_key = (
                chunk_id,
                quote.casefold(),
            )

            if evidence_key in seen:
                continue

            seen.add(evidence_key)

            evidence.append(
                RequirementEvidenceDraft(
                    chunk_id=reference.chunk_id,
                    logical_document_id=(
                        context["logical_document_id"]
                    ),
                    page_id=context["page_id"],
                    source_name=context["source_name"],
                    page_number=context["page_number"],
                    source_role=context["source_role"],
                    binding_status=(
                        context["binding_status"]
                    ),
                    precedence_order=(
                        context["precedence_order"]
                    ),
                    quote=quote,
                    retrieval_score=(
                        context["retrieval_score"]
                    ),
                )
            )

        return evidence, warnings

    def _context_from_hit(
        self,
        hit: Any,
    ) -> dict[str, Any]:
        return {
            "chunk_id": str(hit.chunk_id),
            "logical_document_id": (
                hit.logical_document_id
            ),
            "page_id": hit.page_id,
            "source_name": hit.source_name,
            "page_number": hit.page_number,
            "source_role": hit.source_role,
            "binding_status": hit.binding_status,
            "precedence_order": hit.precedence_order,
            "retrieval_score": float(
                hit.final_score
            ),
            "text": hit.text[
                : self.max_chunk_characters
            ],
        }

    def _deduplicate(
        self,
        requirements: list[RequirementDraft],
    ) -> list[RequirementDraft]:
        selected: dict[
            tuple[str, str],
            RequirementDraft,
        ] = {}

        for requirement in requirements:
            key = (
                requirement.category_key,
                self._comparison_text(
                    requirement.requirement_text
                ),
            )

            current = selected.get(key)

            if (
                current is None
                or requirement.confidence
                > current.confidence
            ):
                selected[key] = requirement

        return list(selected.values())

    @staticmethod
    def _requirement_code(
        *,
        category_key: str,
        requirement_text: str,
    ) -> str:
        digest = hashlib.sha256(
            (
                category_key
                + "\n"
                + RequirementService._comparison_text(
                    requirement_text
                )
            ).encode("utf-8")
        ).hexdigest()[:16].upper()

        return f"REQ-{digest}"

    @staticmethod
    def _quote_is_supported(
        *,
        quote: str,
        text: str,
    ) -> bool:
        normalized_quote = (
            RequirementService._comparison_text(
                quote
            )
        )
        normalized_text = (
            RequirementService._comparison_text(
                text
            )
        )

        return bool(
            normalized_quote
            and normalized_quote in normalized_text
        )

    @staticmethod
    def _comparison_text(value: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            value.casefold(),
        ).strip()

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

    @staticmethod
    def _clean_optional_text(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        cleaned = RequirementService._clean_text(
            value
        )

        return cleaned or None

    @staticmethod
    def _load_catalog(
        path: Path,
    ) -> RequirementCatalog:
        if not path.is_file():
            raise RuntimeError(
                "Requirement dictionary was not found: "
                f"{path}"
            )

        payload = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )

        return RequirementCatalog.model_validate(
            payload
        )

    @staticmethod
    def _load_prompt(path: Path) -> str:
        if not path.is_file():
            raise RuntimeError(
                "Requirement prompt was not found: "
                f"{path}"
            )

        payload = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )

        if not isinstance(payload, dict):
            raise RuntimeError(
                "Requirement prompt must be an object."
            )

        prompt = payload.get("system_prompt")

        if not isinstance(prompt, str) or not prompt.strip():
            raise RuntimeError(
                "Requirement system_prompt is missing."
            )

        return prompt.strip()
