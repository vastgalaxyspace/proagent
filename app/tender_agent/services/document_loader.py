from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.infrastructure.storage.interface import ObjectStorage
from app.tender_agent.services.native_parser import (
    NativeDocumentParser,
    NativeExtractionResult,
)


class DocumentLoader:
    def __init__(
        self,
        *,
        storage: ObjectStorage,
        parser: NativeDocumentParser,
    ) -> None:
        self.storage = storage
        self.parser = parser

    def extract(
        self,
        *,
        document_id: str,
        file_name: str,
        object_key: str,
    ) -> NativeExtractionResult:
        suffix = Path(file_name).suffix.lower()

        with tempfile.TemporaryDirectory(
            prefix="native-extraction-"
        ) as temporary_directory:
            local_path = (
                Path(temporary_directory)
                / f"source{suffix}"
            )

            with self.storage.open_read(object_key) as source:
                with local_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

            return self.parser.extract(
                path=local_path,
                document_id=document_id,
            )