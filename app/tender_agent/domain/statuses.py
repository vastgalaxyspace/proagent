from __future__ import annotations

from enum import StrEnum


class TenderStatus(StrEnum):
    DRAFT = "draft"
    REVIEW_READY = "review_ready"
    APPROVED = "approved"
    ARCHIVED = "archived"


class TenderVersionStatus(StrEnum):
    DRAFT = "draft"
    PROCESSING = "processing"
    REVIEW_READY = "review_ready"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class DocumentStorageStatus(StrEnum):
    PENDING = "pending"
    STORED = "stored"
    FAILED = "failed"


class DocumentExtractionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    NEEDS_OCR = "needs_ocr"
    EMPTY = "empty"
    FAILED = "failed"


class OperationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
