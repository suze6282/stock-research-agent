from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers import artifacts
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _identity(key: str) -> object:
    return artifacts.ProviderRecordIdentity(
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        source_identity="fixture:batch",
        record_key=key,
        revision=1,
    )


def _record(key: str, **changes: object) -> object:
    values: dict[str, object] = {
        "identity": _identity(key),
        "raw_artifact_id": uuid4(),
        "source_checksum": "a" * 64,
        "source_published_at": NOW,
        "status": artifacts.ProviderRecordStatus.COMPLETE,
        "numeric_values": {"close": "12.3400"},
        "text_values": {"currency": "USD"},
        "warning_codes": (),
        "synthetic_status": ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
    }
    values.update(changes)
    return artifacts.ProviderRecord.model_validate(values)


def test_batch_is_frozen_bounded_and_stably_ordered() -> None:
    first = _record("A")
    second = _record("B")
    batch = artifacts.ProviderBatch(
        manifest_checksum="b" * 64,
        records=(first, second),
    )
    assert batch.record_count == 2
    assert batch.batch_checksum == artifacts.build_provider_batch_checksum(batch.records)
    with pytest.raises(ValidationError):
        batch.records = ()


@pytest.mark.parametrize(
    "changes",
    (
        {"numeric_values": {"close": 1.5}},
        {
            "status": "MISSING",
            "numeric_values": {"close": "0"},
            "warning_codes": ("MISSING_VALUE",),
        },
        {"raw_payload": {"secret": "forbidden"}},
        {"status": "PARTIAL", "warning_codes": ()},
    ),
)
def test_record_rejects_float_zero_for_missing_raw_overwrite_or_silent_partial(
    changes: dict[str, object],
) -> None:
    with pytest.raises((ValidationError, AttributeError)):
        _record("A", **changes)


def test_batch_rejects_duplicate_or_unstable_identity_order() -> None:
    first = _record("A")
    second = _record("B")
    with pytest.raises(ValidationError):
        artifacts.ProviderBatch(manifest_checksum="b" * 64, records=(second, first))
    with pytest.raises(ValidationError):
        artifacts.ProviderBatch(manifest_checksum="b" * 64, records=(first, first))
