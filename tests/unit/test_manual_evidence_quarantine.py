from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.infrastructure.blob_storage import LocalBlobStorage
from stock_research_agent.infrastructure.manual_evidence_storage import (
    AtomicManualEvidenceQuarantine,
    QuarantineFileRequest,
)


def _request(content: bytes) -> QuarantineFileRequest:
    return QuarantineFileRequest(
        import_request_id=uuid4(),
        content=content,
        content_type="text/html",
        expected_byte_size=len(content),
        expected_checksum=hashlib.sha256(content).hexdigest(),
    )


def test_quarantine_preserves_exact_synthetic_bytes_atomically(tmp_path: Path) -> None:
    content = b"<html>SYNTHETIC_TEST_ONLY OFFLINE NOT_LIVE</html>\n"
    storage = LocalBlobStorage(tmp_path / "quarantine", max_blob_bytes=26_214_400)

    quarantined = AtomicManualEvidenceQuarantine(storage).quarantine(_request(content))

    assert quarantined.checksum == hashlib.sha256(content).hexdigest()
    assert quarantined.byte_size == len(content)
    assert quarantined.blob_key
    assert not Path(quarantined.blob_key).is_absolute()
    assert ".." not in quarantined.blob_key
    assert storage.get(quarantined.storage_uri) == content


@pytest.mark.parametrize(
    "change",
    [
        {"expected_byte_size": 1},
        {"expected_checksum": "f" * 64},
    ],
)
def test_identity_mismatch_writes_nothing(
    tmp_path: Path,
    change: dict[str, object],
) -> None:
    root = tmp_path / "quarantine"
    request = _request(b"synthetic\n")
    request = QuarantineFileRequest(**{**request.__dict__, **change})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        AtomicManualEvidenceQuarantine(
            LocalBlobStorage(root, max_blob_bytes=26_214_400)
        ).quarantine(request)

    assert exc_info.value.code == "QUARANTINE_CHECKSUM_MISMATCH"
    assert not root.exists() or not tuple(path for path in root.rglob("*") if path.is_file())


class _CorruptingStorage(LocalBlobStorage):
    def checksum(self, uri: str) -> str:
        return "0" * 64


def test_durability_failure_cleans_only_uncommitted_blob(tmp_path: Path) -> None:
    root = tmp_path / "quarantine"
    service = AtomicManualEvidenceQuarantine(_CorruptingStorage(root, max_blob_bytes=26_214_400))

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        service.quarantine(_request(b"synthetic\n"))

    assert exc_info.value.code == "QUARANTINE_WRITE_FAILED"
    assert not tuple(path for path in root.rglob("*") if path.is_file())
