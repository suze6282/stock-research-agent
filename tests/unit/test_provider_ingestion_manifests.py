from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from stock_research_agent.domain.providers import artifacts
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _artifact(published_at: datetime | None = NOW) -> artifacts.ProviderRawArtifactRecord:
    return artifacts.ProviderRawArtifactRecord(
        id=uuid4(),
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        sync_run_id=uuid4(),
        request_attempt_id=uuid4(),
        license_policy_id=uuid4(),
        source_identity="fixture:exact",
        source_checksum="a" * 64,
        byte_count=10,
        content_type="application/json",
        blob_key="b" * 32,
        acquired_at=NOW,
        source_published_at=published_at,
        synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
        created_at=NOW,
    )


def _context(
    artifact: artifacts.ProviderRawArtifactRecord,
) -> artifacts.ProviderIngestionContext:
    return artifacts.ProviderIngestionContext(
        provider_definition_id=artifact.provider_definition_id,
        provider_capability_id=artifact.provider_capability_id,
        sync_run_id=artifact.sync_run_id,
        request_attempt_id=artifact.request_attempt_id,
        research_as_of_time=NOW,
        adapter_version="1.0.0",
        parser_version="1.0.0",
        schema_version="provider-v1",
        synthetic_status=artifact.synthetic_status,
    )


def test_manifest_is_deterministic_and_binds_complete_lineage() -> None:
    artifact = _artifact()
    batch = artifacts.ProviderManifestBatch(record_identities=("A", "B"), batch_checksum="c" * 64)
    first = artifacts.build_ingestion_manifest(artifact, batch, _context(artifact))
    second = artifacts.build_ingestion_manifest(artifact, batch, _context(artifact))
    assert first == second
    assert first.record_count == 2
    assert first.manifest_checksum == second.manifest_checksum


def test_unknown_published_at_requires_warning() -> None:
    artifact = _artifact(None)
    manifest = artifacts.build_ingestion_manifest(
        artifact,
        artifacts.ProviderManifestBatch(record_identities=("A",), batch_checksum="c" * 64),
        _context(artifact),
    )
    assert "UNKNOWN_PUBLISHED_AT" in manifest.warning_codes


def test_future_or_cross_run_artifact_is_rejected() -> None:
    artifact = _artifact(NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="FUTURE"):
        artifacts.build_ingestion_manifest(
            artifact,
            artifacts.ProviderManifestBatch(record_identities=("A",), batch_checksum="c" * 64),
            _context(artifact),
        )
    artifact = _artifact()
    with pytest.raises(ValueError, match="LINEAGE"):
        artifacts.build_ingestion_manifest(
            artifact,
            artifacts.ProviderManifestBatch(record_identities=("A",), batch_checksum="c" * 64),
            _context(artifact).model_copy(update={"sync_run_id": uuid4()}),
        )
