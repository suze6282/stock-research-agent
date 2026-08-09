from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.artifacts import ProviderRawArtifactDraft
from stock_research_agent.infrastructure.blob_storage import LocalBlobStorage
from stock_research_agent.infrastructure.provider_artifact_storage import (
    AtomicProviderArtifactStorage,
)


def test_atomic_storage_preserves_exact_bytes_and_stable_checksum(tmp_path: Path) -> None:
    content = b"line-one\r\nline-two\n"
    service = AtomicProviderArtifactStorage(
        LocalBlobStorage(tmp_path / "blobs", max_blob_bytes=100)
    )
    stored = service.write(
        ProviderRawArtifactDraft(
            content_type="application/json",
            expected_checksum=None,
            store_raw_permitted=True,
        ),
        content,
    )
    assert stored.byte_count == len(content)
    assert service.read(stored) == content
    assert service.read(stored).endswith(b"\n")
    assert "\\" not in stored.blob_key
    assert not Path(stored.blob_key).is_absolute()


def test_license_prohibition_and_checksum_mismatch_leave_no_artifact(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    service = AtomicProviderArtifactStorage(LocalBlobStorage(root, max_blob_bytes=100))
    with pytest.raises(PermissionError, match="RAW_STORAGE_PROHIBITED"):
        service.write(
            ProviderRawArtifactDraft(
                content_type="text/plain",
                store_raw_permitted=False,
            ),
            b"data",
        )
    with pytest.raises(ValueError, match="CHECKSUM"):
        service.write(
            ProviderRawArtifactDraft(
                content_type="text/plain",
                expected_checksum="0" * 64,
                store_raw_permitted=True,
            ),
            b"data",
        )
    assert not any(path.is_file() for path in root.rglob("*"))


@pytest.mark.parametrize("content_type", ("../text", "text/plain\nX-Test: yes"))
def test_draft_rejects_traversal_or_control_content_type(content_type: str) -> None:
    with pytest.raises(ValidationError):
        ProviderRawArtifactDraft(
            content_type=content_type,
            store_raw_permitted=True,
        )
