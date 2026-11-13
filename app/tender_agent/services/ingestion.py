from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Document,
    Tender,
    TenderVersion,
)
from app.infrastructure.storage.interface import (
    ObjectStorage,
    StorageLimitExceeded,
)
from app.tender_agent.domain.exceptions import (
    InvalidUploadError,
    UploadTooLargeError,
)
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.repositories.tender_repository import TenderRepository


_ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".xml",
        ".html",
        ".htm",
        ".zip",
    }
)

_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    }
)


@dataclass(frozen=True)
class IngestionLimits:
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    chunk_bytes: int


@dataclass(frozen=True)
class IngestionResult:
    tender: Tender
    tender_version: TenderVersion
    documents: list[Document]
    stored_object_keys: list[str]


class IngestionService:
    def __init__(
        self,
        *,
        session: Session,
        storage: ObjectStorage,
        limits: IngestionLimits,
    ) -> None:
        self.session = session
        self.storage = storage
        self.limits = limits

    def ingest_tender(
        self,
        *,
        tenant_id: str,
        title: str,
        external_reference: str | None,
        uploads: list[UploadFile],
    ) -> IngestionResult:
        if not uploads:
            raise InvalidUploadError(
                "At least one tender file is required."
            )

        if len(uploads) > self.limits.max_files:
            raise InvalidUploadError(
                f"A maximum of {self.limits.max_files} files is allowed."
            )

        prepared_uploads = [
            (
                upload,
                self._sanitize_file_name(upload.filename),
                self._normalize_content_type(upload.content_type),
            )
            for upload in uploads
        ]

        tender_repository = TenderRepository(self.session)
        document_repository = DocumentRepository(self.session)

        tender, version, documents = tender_repository.create_tender(
            tenant_id=tenant_id,
            title=title.strip(),
            external_reference=(
                external_reference.strip()
                if external_reference
                else None
            ),
            document_names=[
                (file_name, content_type)
                for _, file_name, content_type in prepared_uploads
            ],
        )

        stored_object_keys: list[str] = []
        total_size = 0

        try:
            for prepared, document in zip(
                prepared_uploads,
                documents,
                strict=True,
            ):
                upload, file_name, content_type = prepared

                object_key = self._build_object_key(
                    tenant_id=tenant_id,
                    tender_id=tender.id,
                    tender_version_id=version.id,
                    document_id=document.id,
                    file_name=file_name,
                )

                stored_object_keys.append(object_key)

                upload.file.seek(0)

                try:
                    stored_object = self.storage.put_stream(
                        object_key=object_key,
                        stream=upload.file,
                        max_bytes=self.limits.max_file_bytes,
                        chunk_bytes=self.limits.chunk_bytes,
                    )
                except StorageLimitExceeded as exc:
                    raise UploadTooLargeError(
                        f"{file_name} exceeded the per-file size limit."
                    ) from exc

                if stored_object.size_bytes == 0:
                    raise InvalidUploadError(
                        f"{file_name} is empty."
                    )

                if not self._matches_basic_signature(
                    file_name=file_name,
                    header=stored_object.header,
                ):
                    raise InvalidUploadError(
                        f"{file_name} does not match its file extension."
                    )

                total_size += stored_object.size_bytes

                if total_size > self.limits.max_total_bytes:
                    raise UploadTooLargeError(
                        "The combined upload exceeded the total size limit."
                    )

                document_repository.mark_stored(
                    document,
                    object_key=stored_object.object_key,
                    size_bytes=stored_object.size_bytes,
                    sha256=stored_object.sha256,
                    content_type=content_type,
                )

        except Exception:
            self.cleanup_objects(stored_object_keys)
            raise

        return IngestionResult(
            tender=tender,
            tender_version=version,
            documents=documents,
            stored_object_keys=stored_object_keys,
        )

    def cleanup_objects(self, object_keys: list[str]) -> None:
        for object_key in object_keys:
            try:
                self.storage.delete(object_key)
            except Exception:
                pass

    @staticmethod
    def _sanitize_file_name(raw_name: str | None) -> str:
        if not raw_name:
            raise InvalidUploadError(
                "Every uploaded file must have a filename."
            )

        leaf_name = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
        normalized = unicodedata.normalize("NFKC", leaf_name).strip()

        if not normalized:
            raise InvalidUploadError("A filename is invalid.")

        suffix = Path(normalized).suffix.lower()

        if suffix not in _ALLOWED_EXTENSIONS:
            raise InvalidUploadError(
                f"Files with the {suffix or 'missing'} extension "
                "are not supported."
            )

        stem = Path(normalized).stem
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
        safe_stem = safe_stem.strip("._-")

        if not safe_stem:
            raise InvalidUploadError("A filename is invalid.")

        if safe_stem.lower() in _WINDOWS_RESERVED_NAMES:
            safe_stem = f"_{safe_stem}"

        maximum_stem_length = 180 - len(suffix)
        safe_stem = safe_stem[:maximum_stem_length]

        return f"{safe_stem}{suffix}"

    @staticmethod
    def _normalize_content_type(
        content_type: str | None,
    ) -> str:
        normalized = (
            content_type or "application/octet-stream"
        ).strip()

        if len(normalized) > 255:
            raise InvalidUploadError(
                "A file content type is too long."
            )

        return normalized

    @staticmethod
    def _build_object_key(
        *,
        tenant_id: str,
        tender_id: UUID,
        tender_version_id: UUID,
        document_id: UUID,
        file_name: str,
    ) -> str:
        tenant_key = hashlib.sha256(
            tenant_id.encode("utf-8")
        ).hexdigest()[:24]

        return (
            f"tenants/{tenant_key}/"
            f"tenders/{tender_id}/"
            f"versions/{tender_version_id}/"
            f"documents/{document_id}/"
            f"{file_name}"
        )

    @staticmethod
    def _matches_basic_signature(
        *,
        file_name: str,
        header: bytes,
    ) -> bool:
        suffix = Path(file_name).suffix.lower()

        if suffix == ".pdf":
            return header.startswith(b"%PDF-")

        if suffix in {".docx", ".xlsx", ".zip"}:
            return header.startswith(
                (
                    b"PK\x03\x04",
                    b"PK\x05\x06",
                    b"PK\x07\x08",
                )
            )

        if suffix in {".doc", ".xls"}:
            return header.startswith(
                b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
            )

        if suffix in {
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".htm",
        }:
            return b"\x00" not in header

        return False
