from __future__ import annotations

from collections import Counter

from app.tender_agent.domain.classification import (
    ContentRole,
    TenderDocumentType,
)
from app.tender_agent.domain.structure import (
    ClassifiedPage,
    LogicalDocumentDraft,
)


class StructureService:
    def __init__(
        self,
        *,
        minimum_confidence: float = 0.60,
    ) -> None:
        self.minimum_confidence = minimum_confidence

    def reconstruct(
        self,
        pages: list[ClassifiedPage],
    ) -> list[LogicalDocumentDraft]:
        if not pages:
            return []

        ordered_pages = sorted(
            pages,
            key=lambda page: (
                page.document_id,
                page.page_number,
                page.page_id,
            ),
        )

        self._validate_pages(ordered_pages)

        drafts: list[LogicalDocumentDraft] = []
        current_pages: list[ClassifiedPage] = []
        current_boundary_reason = "first_page"

        for page in ordered_pages:
            if not current_pages:
                current_pages = [page]
                current_boundary_reason = "first_page"
                continue

            previous_page = current_pages[-1]

            boundary_reason = self._boundary_reason(
                previous_page=previous_page,
                current_page=page,
            )

            if boundary_reason is not None:
                drafts.append(
                    self._build_draft(
                        pages=current_pages,
                        sequence_number=len(drafts) + 1,
                        boundary_reason=(
                            current_boundary_reason
                        ),
                    )
                )

                current_pages = [page]
                current_boundary_reason = boundary_reason

            else:
                current_pages.append(page)

        if current_pages:
            drafts.append(
                self._build_draft(
                    pages=current_pages,
                    sequence_number=len(drafts) + 1,
                    boundary_reason=current_boundary_reason,
                )
            )

        self._validate_drafts(
            pages=ordered_pages,
            drafts=drafts,
        )

        return drafts

    def _boundary_reason(
        self,
        *,
        previous_page: ClassifiedPage,
        current_page: ClassifiedPage,
    ) -> str | None:
        if (
            previous_page.document_id
            != current_page.document_id
        ):
            return "uploaded_document_changed"

        if (
            previous_page.source_name
            != current_page.source_name
        ):
            return "source_file_changed"

        if (
            current_page.page_number
            != previous_page.page_number + 1
        ):
            return "non_consecutive_page"

        if (
            previous_page.content_role
            != current_page.content_role
        ):
            return "content_role_changed"

        if (
            previous_page.document_type
            in {"corrigendum", "prebid_clarification"}
            and current_page.document_type
            == previous_page.document_type
            and current_page.title
            != previous_page.title
        ):
            return "amendment_title_changed"

        if (
            current_page.classification_method
            == "deterministic_heading"
        ):
            return "strong_document_heading"

        previous_type = previous_page.document_type
        current_type = current_page.document_type

        if (
            previous_type != "unknown"
            and current_type != "unknown"
            and previous_type != current_type
        ):
            return "document_type_changed"

        return None

    def _build_draft(
        self,
        *,
        pages: list[ClassifiedPage],
        sequence_number: int,
        boundary_reason: str,
    ) -> LogicalDocumentDraft:
        known_types = [
            page.document_type
            for page in pages
            if page.document_type != "unknown"
        ]

        if known_types:
            document_type = Counter(
                known_types
            ).most_common(1)[0][0]
        else:
            document_type = "unknown"

        content_roles = [
            page.content_role
            for page in pages
            if page.content_role != "unknown"
        ]

        if content_roles:
            content_role = Counter(
                content_roles
            ).most_common(1)[0][0]
        else:
            content_role = "unknown"

        title_page = next(
            (
                page
                for page in pages
                if page.classification_method
                == "deterministic_heading"
            ),
            None,
        )

        if title_page is None:
            title_page = next(
                (
                    page
                    for page in pages
                    if page.document_type != "unknown"
                ),
                pages[0],
            )

        confidence = sum(
            page.confidence
            for page in pages
        ) / len(pages)

        needs_review = any(
            page.document_type == "unknown"
            or page.confidence < self.minimum_confidence
            for page in pages
        )

        return LogicalDocumentDraft(
            document_id=pages[0].document_id,
            sequence_number=sequence_number,
            document_type=document_type,
            content_role=content_role,
            title=title_page.title[:500],
            source_name=pages[0].source_name,
            start_page_number=pages[0].page_number,
            end_page_number=pages[-1].page_number,
            start_source_page_number=(
                pages[0].source_page_number
            ),
            end_source_page_number=(
                pages[-1].source_page_number
            ),
            page_count=len(pages),
            confidence=round(confidence, 4),
            needs_review=needs_review,
            boundary_reason=boundary_reason,
            page_ids=[
                page.page_id
                for page in pages
            ],
        )

    @staticmethod
    def _validate_pages(
        pages: list[ClassifiedPage],
    ) -> None:
        page_ids = [
            page.page_id
            for page in pages
        ]

        if len(page_ids) != len(set(page_ids)):
            raise ValueError(
                "Duplicate pages were provided to the "
                "structure service."
            )

        if any(page.page_number <= 0 for page in pages):
            raise ValueError(
                "Page numbers must be positive."
            )

        if any(
            page.source_page_number <= 0
            for page in pages
        ):
            raise ValueError(
                "Source page numbers must be positive."
            )

    @staticmethod
    def _validate_drafts(
        *,
        pages: list[ClassifiedPage],
        drafts: list[LogicalDocumentDraft],
    ) -> None:
        input_page_ids = {
            page.page_id
            for page in pages
        }

        structured_page_ids = [
            page_id
            for draft in drafts
            for page_id in draft.page_ids
        ]

        if len(structured_page_ids) != len(
            set(structured_page_ids)
        ):
            raise ValueError(
                "A page was assigned to multiple "
                "logical documents."
            )

        if set(structured_page_ids) != input_page_ids:
            raise ValueError(
                "Some classified pages were not assigned "
                "to a logical document."
            )
