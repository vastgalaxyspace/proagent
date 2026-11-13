from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    size_bytes: int
    sha256: str
    header: bytes


class ObjectStorageError(Exception):
    """Base exception raised by object-storage implementations."""


class StorageLimitExceeded(ObjectStorageError):
    """The incoming object exceeded its maximum size."""


class ObjectStorage(Protocol):
    def put_stream(
        self,
        *,
        object_key: str,
        stream: BinaryIO,
        max_bytes: int,
        chunk_bytes: int,
    ) -> StoredObject:
        ...

    def exists(self, object_key: str) -> bool:
        ...

    def delete(self, object_key: str) -> None:
        ...
    
    def open_read(
        self,
        object_key: str,
    ) -> AbstractContextManager[BinaryIO]:
        ...
