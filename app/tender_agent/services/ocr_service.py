from __future__ import annotations

import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from collections.abc import Iterator

from app.infrastructure.database.models import (
    Document,
    DocumentPage,
)
from app.infrastructure.providers.ocr import (
    OCRProvider,
    OCRResult,
)
from app.infrastructure.storage.interface import ObjectStorage
from app.tender_agent.services.quality_service import (
    QualityService,
)


class OCRRecoveryService:
    def __init__(
        self,
        *,
        storage: ObjectStorage,
        provider: OCRProvider,
        quality_service: QualityService,
    ) -> None:
        self.storage = storage
        self.provider = provider
        self.quality_service = quality_service

    def recover_page(
        self,
        *,
        document: Document,
        page: DocumentPage,
    ) -> tuple[OCRResult, dict]:
        with self._materialize_pdf_source(
            document=document,
            page=page,
        ) as pdf_path:
            result = self.provider.extract_pdf_page(
                path=pdf_path,
                page_number=page.source_page_number,
            )

        text, metrics = (
            self.quality_service.validate_ocr_text(
                result.text
            )
        )

        validated_result = OCRResult(
            text=text,
            provider=result.provider,
            confidence=result.confidence,
            layout=result.layout,
        )

        return validated_result, metrics

    @contextmanager
    def _materialize_pdf_source(
        self,
        *,
        document: Document,
        page: DocumentPage,
    ) -> Iterator[Path]:
        if not document.object_key:
            raise ValueError(
                "Document has no object-storage key."
            )

        with tempfile.TemporaryDirectory(
            prefix="ocr-source-"
        ) as temporary_directory:
            root = Path(temporary_directory).resolve()
            upload_suffix = Path(document.file_name).suffix.lower()
            upload_path = root / f"upload{upload_suffix}"

            with self.storage.open_read(
                document.object_key
            ) as source:
                with upload_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

            if upload_suffix == ".pdf":
                yield upload_path
                return

            if upload_suffix != ".zip":
                raise ValueError(
                    "OCR currently supports PDF pages only."
                )

            member_path = PurePosixPath(
                page.source_name.replace("\\", "/")
            )

            if (
                member_path.is_absolute()
                or ".." in member_path.parts
                or member_path.suffix.lower() != ".pdf"
            ):
                raise ValueError(
                    "Archive OCR source is unsafe or not a PDF."
                )

            target_path = root.joinpath(
                *member_path.parts
            ).resolve()

            if not target_path.is_relative_to(root):
                raise ValueError(
                    "Archive member escaped the OCR directory."
                )

            target_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with zipfile.ZipFile(upload_path) as archive:
                member = archive.getinfo(
                    member_path.as_posix()
                )

                if member.flag_bits & 0x1:
                    raise ValueError(
                        "Encrypted OCR sources are unsupported."
                    )

                with archive.open(member) as source:
                    with target_path.open("wb") as destination:
                        shutil.copyfileobj(
                            source,
                            destination,
                        )

            yield target_path