from __future__ import annotations


class TenderAgentError(Exception):
    """Base exception for expected Tender Agent failures."""


class IngestionError(TenderAgentError):
    """Base exception for file-ingestion failures."""


class InvalidUploadError(IngestionError):
    """The uploaded file name or content is invalid."""


class UploadTooLargeError(IngestionError):
    """An upload exceeded a configured size limit."""