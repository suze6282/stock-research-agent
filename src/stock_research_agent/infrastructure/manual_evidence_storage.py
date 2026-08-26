"""Atomic local quarantine over the hardened immutable blob port."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.providers.schemas import Checksum, FrozenProviderContract
from stock_research_agent.infrastructure.blob_storage import BlobStorage, BlobStorageError


@dataclass(frozen=True)
class QuarantineFileRequest:
    import_request_id: UUID
    content: bytes
    content_type: str
    expected_byte_size: int
    expected_checksum: str


class QuarantinedFile(FrozenProviderContract):
    import_request_id: UUID
    blob_key: str = Field(min_length=1, max_length=512)
    storage_uri: str = Field(min_length=1, max_length=1024)
    checksum: Checksum
    byte_size: int = Field(ge=1, le=26_214_400)
    content_type: str = Field(min_length=3, max_length=128)


class AtomicManualEvidenceQuarantine:
    def __init__(self, storage: BlobStorage) -> None:
        self._storage = storage

    def quarantine(self, request: QuarantineFileRequest) -> QuarantinedFile:
        checksum = hashlib.sha256(request.content).hexdigest()
        if (
            len(request.content) != request.expected_byte_size
            or checksum != request.expected_checksum
        ):
            raise LiveEvidenceValidationError("QUARANTINE_CHECKSUM_MISMATCH")
        try:
            metadata = self._storage.put(
                request.content,
                content_type=request.content_type,
                metadata={
                    "acquisition_kind": "MANUAL_IMPORT",
                    "execution_mode": "OFFLINE",
                    "live_status": "NOT_LIVE",
                },
            )
        except BlobStorageError as error:
            raise LiveEvidenceValidationError("QUARANTINE_WRITE_FAILED") from error

        durable = (
            metadata.checksum_sha256 == checksum
            and metadata.size_bytes == len(request.content)
            and self._storage.checksum(metadata.uri) == checksum
        )
        if not durable:
            try:
                self._storage.delete(metadata.uri)
            except BlobStorageError as error:
                raise LiveEvidenceValidationError("QUARANTINE_WRITE_FAILED") from error
            raise LiveEvidenceValidationError("QUARANTINE_WRITE_FAILED")
        blob_key = urlsplit(metadata.uri).path.removeprefix("/")
        return QuarantinedFile(
            import_request_id=request.import_request_id,
            blob_key=blob_key,
            storage_uri=metadata.uri,
            checksum=checksum,
            byte_size=len(request.content),
            content_type=request.content_type,
        )
