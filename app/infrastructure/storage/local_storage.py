from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.infrastructure.storage.interface import (
    ObjectStorageError,
    StorageLimitExceeded,
    StoredObject,
)


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def open_read(
        self,
        object_key: str,
    ) -> Iterator[BinaryIO]:
        path = self._resolve_key(object_key)

        try:
            with path.open("rb") as stream:
                yield stream
        except OSError as exc:
            raise ObjectStorageError(
                "The stored object could not be opened."
            ) from exc

    def put_stream(
        self,
        *,
        object_key: str,
        stream: BinaryIO,
        max_bytes: int,
        chunk_bytes: int,
    ) -> StoredObject:
        target_path = self._resolve_key(object_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path: Path | None = None
        digest = hashlib.sha256()
        size_bytes = 0
        header = bytearray()

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target_path.parent,
                prefix=".upload-",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

                while True:
                    chunk = stream.read(chunk_bytes)

                    if not chunk:
                        break

                    if not isinstance(chunk, bytes):
                        raise ObjectStorageError(
                            "The upload stream did not return bytes."
                        )

                    size_bytes += len(chunk)

                    if size_bytes > max_bytes:
                        raise StorageLimitExceeded(
                            "The uploaded file exceeded its size limit."
                        )

                    if len(header) < 16:
                        remaining = 16 - len(header)
                        header.extend(chunk[:remaining])

                    digest.update(chunk)
                    temporary_file.write(chunk)

                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, target_path)

        except StorageLimitExceeded:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

        except Exception as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

            raise ObjectStorageError(
                "The uploaded file could not be stored."
            ) from exc

        return StoredObject(
            object_key=object_key,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            header=bytes(header),
        )

    def exists(self, object_key: str) -> bool:
        return self._resolve_key(object_key).is_file()

    def delete(self, object_key: str) -> None:
        self._resolve_key(object_key).unlink(missing_ok=True)

    def _resolve_key(self, object_key: str) -> Path:
        normalized_key = object_key.replace("\\", "/")
        key_path = PurePosixPath(normalized_key)

        if key_path.is_absolute():
            raise ObjectStorageError(
                "Absolute object keys are not allowed."
            )

        if not key_path.parts:
            raise ObjectStorageError("The object key is empty.")

        if any(part in {"", ".", ".."} for part in key_path.parts):
            raise ObjectStorageError(
                "The object key contains an unsafe path."
            )

        resolved_path = self.root.joinpath(*key_path.parts).resolve()

        if not resolved_path.is_relative_to(self.root):
            raise ObjectStorageError(
                "The object key escaped the storage root."
            )

        return resolved_path
