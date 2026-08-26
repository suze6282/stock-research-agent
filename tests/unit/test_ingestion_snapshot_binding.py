from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.snapshot import (
    IngestionSnapshotBindingWrite,
    bind_manifest_to_snapshot,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")


def _write(**changes: object) -> IngestionSnapshotBindingWrite:
    values: dict[str, object] = {
        "manifest_id": uuid4(),
        "manifest_checksum": "a" * 64,
        "manifest_security_id": SECURITY_ID,
        "snapshot_id": uuid4(),
        "snapshot_checksum": "b" * 64,
        "snapshot_security_id": SECURITY_ID,
        "security_id": SECURITY_ID,
        "research_as_of_time": NOW,
        "source_published_at": NOW,
        "bound_at": NOW,
    }
    values.update(changes)
    return IngestionSnapshotBindingWrite.model_validate(values)


def test_exact_manifest_and_snapshot_scope_creates_immutable_binding() -> None:
    record = bind_manifest_to_snapshot(_write())

    assert len(record.binding_checksum) == 64
    with pytest.raises(ValidationError):
        record.__setattr__("snapshot_checksum", "c" * 64)


@pytest.mark.parametrize(
    "write",
    [
        _write(manifest_security_id=uuid4()),
        _write(snapshot_security_id=uuid4()),
        _write(source_published_at=datetime(2026, 7, 13, 12, 0, 1, tzinfo=UTC)),
    ],
)
def test_scope_mismatch_is_rejected(write: IngestionSnapshotBindingWrite) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        bind_manifest_to_snapshot(write)

    assert exc_info.value.code == "SNAPSHOT_BINDING_SCOPE_MISMATCH"


def test_duplicate_binding_is_rejected() -> None:
    write = _write()
    existing = bind_manifest_to_snapshot(write)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        bind_manifest_to_snapshot(write, existing=existing)

    assert exc_info.value.code == "SNAPSHOT_BINDING_DUPLICATE"
