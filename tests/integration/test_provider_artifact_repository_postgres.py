from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderArtifactRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.domain.providers.artifacts import (
    ProviderDataQualityIssueWrite,
    ProviderDeadLetterWrite,
    ProviderIngestionManifestWrite,
    ProviderIssueSeverity,
    ProviderRawArtifactReservation,
    ProviderRawArtifactWrite,
)
from stock_research_agent.domain.providers.enums import (
    ProviderSyncSliceStatus,
    ProviderSyntheticStatus,
)
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderRequestAttemptWrite,
    ProviderSyncPlanWrite,
    ProviderSyncRequestWrite,
    ProviderSyncRunWrite,
)
from tests.integration.test_provider_sync_repository_postgres import _governance

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Provider artifact tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    value = create_engine(TEST_DATABASE_URL)
    yield value
    value.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    value = Session(bind=connection)
    try:
        yield value
    finally:
        value.close()
        transaction.rollback()
        connection.close()


def _lineage(session: Session) -> tuple[object, object, object, object, object]:
    definition, capability, policy, license_policy = _governance(session)
    sync = SqlAlchemyProviderSyncRepository(session)
    request = sync.create_request(
        ProviderSyncRequestWrite(
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
            policy_id=policy.id,
            license_policy_id=license_policy.id,
            credential_reference_id=None,
            security_id=None,
            universe_code="ARTIFACT_TEST",
            research_as_of_time=datetime(2026, 7, 29, tzinfo=UTC),
            range_start=date(2026, 7, 29),
            range_end=date(2026, 7, 29),
            execution_mode=ProviderExecutionMode.OFFLINE,
            scope={"universe_code": "ARTIFACT_TEST"},
            budget={
                "max_requests": 1,
                "max_bytes": 1_000_000,
                "max_attempts": 1,
                "max_duration_seconds": 60,
            },
            request_checksum="4" * 64,
            idempotency_key="5" * 64,
        )
    )
    plan = sync.add_plan(
        ProviderSyncPlanWrite(
            sync_request_id=request.id,
            adapter_version="1.0.0",
            slices=({"slice_id": "ONE"},),
            plan_checksum="6" * 64,
        )
    )
    run = sync.create_run(
        ProviderSyncRunWrite(
            sync_request_id=request.id,
            sync_plan_id=plan.id,
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
        )
    )
    attempt = sync.append_attempt(
        ProviderRequestAttemptWrite(
            sync_run_id=run.id,
            slice_id="ONE",
            attempt_number=1,
            status=ProviderSyncSliceStatus.COMPLETED,
            endpoint_id="OFFLINE_FIXTURE",
            response_status_code=200,
            response_bytes=16,
            started_at=datetime(2026, 7, 29, tzinfo=UTC),
            completed_at=datetime(2026, 7, 29, tzinfo=UTC),
        )
    )
    return definition, capability, license_policy, run, attempt


def test_artifact_repository_is_idempotent_and_preserves_lineage(
    session: Session,
) -> None:
    definition, capability, license_policy, run, attempt = _lineage(session)
    repository = SqlAlchemyProviderArtifactRepository(session)
    artifact_value = ProviderRawArtifactWrite(
        provider_definition_id=definition.id,
        provider_capability_id=capability.id,
        sync_run_id=run.id,
        request_attempt_id=attempt.id,
        license_policy_id=license_policy.id,
        source_identity="fixture/test.json",
        source_checksum="7" * 64,
        byte_count=16,
        content_type="application/json",
        blob_key="provider/test/7.json",
        acquired_at=datetime(2026, 7, 29, tzinfo=UTC),
        source_published_at=None,
        synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
    )
    artifact = repository.add_artifact(artifact_value)
    assert repository.add_artifact(artifact_value).id == artifact.id
    manifest = repository.add_manifest(
        ProviderIngestionManifestWrite(
            raw_artifact_id=artifact.id,
            sync_run_id=run.id,
            adapter_version="1.0.0",
            parser_version="1.0.0",
            schema_version="1.0.0",
            batch_checksum="8" * 64,
            record_count=1,
            warning_codes=("SYNTHETIC_TEST_ONLY",),
            synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
            manifest_checksum="9" * 64,
        )
    )
    issue = repository.add_quality_issue(
        ProviderDataQualityIssueWrite(
            sync_run_id=run.id,
            manifest_id=manifest.id,
            rule_code="SYNTHETIC_ONLY",
            severity=ProviderIssueSeverity.LOW,
            safe_detail="Synthetic fixture lineage only",
        )
    )
    dead_letter = repository.add_dead_letter(
        ProviderDeadLetterWrite(
            sync_run_id=run.id,
            manifest_id=manifest.id,
            source_identity="fixture/test.json",
            safe_error_code="TEST_REJECTION",
            safe_detail="Synthetic rejection example",
        )
    )
    assert issue.manifest_id == manifest.id
    assert dead_letter.manifest_id == manifest.id
    assert session.in_transaction()


def test_artifact_repository_accepts_preallocated_identity_and_conflicts_closed(
    session: Session,
) -> None:
    definition, capability, license_policy, run, attempt = _lineage(session)
    repository = SqlAlchemyProviderArtifactRepository(session)
    artifact_id = UUID("82000000-0000-0000-0000-000000000099")
    value = ProviderRawArtifactWrite(
        provider_definition_id=definition.id,
        provider_capability_id=capability.id,
        sync_run_id=run.id,
        request_attempt_id=attempt.id,
        license_policy_id=license_policy.id,
        source_identity="fixture/preallocated.json",
        source_checksum="a" * 64,
        byte_count=16,
        content_type="application/json",
        blob_key="provider/preallocated/a.json",
        acquired_at=datetime(2026, 7, 29, tzinfo=UTC),
        source_published_at=None,
        synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
    )
    reservation = ProviderRawArtifactReservation(id=artifact_id, value=value)

    assert repository.add_artifact_with_id(reservation).id == artifact_id
    assert repository.add_artifact_with_id(reservation).id == artifact_id
    with pytest.raises(ValueError, match="PROVIDER_ARTIFACT_CONFLICT"):
        repository.add_artifact_with_id(
            reservation.model_copy(
                update={"value": value.model_copy(update={"source_checksum": "b" * 64})}
            )
        )
