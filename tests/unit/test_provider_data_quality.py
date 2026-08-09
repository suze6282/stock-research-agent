from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from stock_research_agent.domain.providers import artifacts
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _quality() -> object:
    return importlib.import_module("stock_research_agent.domain.providers.quality")


def _record(key: str = "A") -> artifacts.ProviderRecord:
    return artifacts.ProviderRecord(
        identity=artifacts.ProviderRecordIdentity(
            provider_definition_id=uuid4(),
            provider_capability_id=uuid4(),
            source_identity="fixture:quality",
            record_key=key,
            revision=1,
        ),
        raw_artifact_id=uuid4(),
        source_checksum="a" * 64,
        source_published_at=NOW,
        status=artifacts.ProviderRecordStatus.COMPLETE,
        numeric_values={"close": "12.34"},
        text_values={"currency": "USD", "unit": "USD"},
        synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
    )


def _context(record: artifacts.ProviderRecord) -> object:
    quality = _quality()
    return quality.ProviderQualityContext(
        research_as_of_time=NOW,
        provider_definition_id=record.identity.provider_definition_id,
        provider_capability_id=record.identity.provider_capability_id,
        raw_artifact_id=record.raw_artifact_id,
        source_checksum=record.source_checksum,
        synthetic_status=record.synthetic_status,
        allowed_currencies=("USD",),
        allowed_units=("USD", "SHARES"),
    )


def test_valid_batch_passes_all_deterministic_rules() -> None:
    quality = _quality()
    record = _record()
    batch = artifacts.ProviderBatch(manifest_checksum="b" * 64, records=(record,))
    result = quality.ProviderDataQualityValidator().validate(batch, _context(record))
    assert result.passed is True
    assert result.issues == ()


def test_future_checksum_and_synthetic_mixing_are_reported_without_mutation() -> None:
    quality = _quality()
    record = _record()
    future = record.model_copy(
        update={
            "source_published_at": NOW + timedelta(seconds=1),
            "source_checksum": "c" * 64,
            "synthetic_status": ProviderSyntheticStatus.REAL_VERIFIED,
        }
    )
    batch = artifacts.ProviderBatch.model_construct(
        manifest_checksum="b" * 64,
        records=(future,),
    )
    result = quality.ProviderDataQualityValidator().validate(batch, _context(record))
    assert result.passed is False
    assert {issue.rule for issue in result.issues} >= {
        quality.ProviderQualityRule.TEMPORAL,
        quality.ProviderQualityRule.SOURCE_CHECKSUM,
        quality.ProviderQualityRule.SYNTHETIC_ISOLATION,
    }
    assert future.source_published_at == NOW + timedelta(seconds=1)


def test_corrupted_duplicate_decimal_currency_and_identity_are_all_detected() -> None:
    quality = _quality()
    record = _record()
    corrupt = record.model_copy(
        update={
            "identity": record.identity.model_copy(update={"provider_definition_id": uuid4()}),
            "numeric_values": {"close": "not-decimal"},
            "text_values": {"currency": "EUR", "unit": "UNKNOWN"},
        }
    )
    batch = artifacts.ProviderBatch.model_construct(
        manifest_checksum="b" * 64,
        records=(corrupt, corrupt),
    )
    result = quality.ProviderDataQualityValidator().validate(batch, _context(record))
    rules = {issue.rule for issue in result.issues}
    assert {
        quality.ProviderQualityRule.IDENTITY,
        quality.ProviderQualityRule.DUPLICATE,
        quality.ProviderQualityRule.DECIMAL,
        quality.ProviderQualityRule.CURRENCY_UNIT,
    } <= rules
