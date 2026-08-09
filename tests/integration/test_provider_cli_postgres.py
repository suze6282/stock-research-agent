from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from stock_research_agent.cli_providers import (
    ProviderControlCommand,
    execute_provider_control,
)
from stock_research_agent.db.models.providers import (
    ProviderAuditEvent,
    ProviderLiveValidationRun,
    ProviderSyncRun,
)
from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
)
from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.licenses import (
    LicensePermission,
    SourceLicensePolicyWrite,
)
from stock_research_agent.domain.providers.policies import ProviderPolicyWrite
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Provider CLI tests")

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


def _governance(session: Session) -> tuple[object, object]:
    definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
        ProviderDefinitionWrite(
            code="CLI_OFFLINE_TEST",
            definition_version="1.0.0",
            adapter_version="1.0.0",
            display_name="CLI Offline Test",
            data_domain="MARKET_DATA",
            definition_status=ProviderDefinitionStatus.ACTIVE,
            production_status=ProviderProductionStatus.TEST_ONLY,
            official_domains=("example.com",),
            policy_version="1.0.0",
            license_policy_version="1.0.0",
            credential_reference_id=None,
            source_register_version="1.0.0",
        )
    )
    governance = SqlAlchemyProviderGovernanceRepository(session)
    capability = governance.add_capability(
        ProviderCapabilityWrite(
            provider_definition_id=definition.id,
            code="OFFLINE_SAMPLE",
            capability_version="1.0.0",
            status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
            data_domain="MARKET_DATA",
            market_codes=("US_EQUITY",),
            security_types=("COMMON_STOCK",),
            operations=("READ_OFFLINE_FIXTURE",),
        )
    )
    governance.add_policy(
        ProviderPolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            endpoint_policy_version="1.0.0",
            network_enabled=False,
            max_requests=10,
            max_response_bytes=4096,
            max_total_bytes=8192,
            max_duration_seconds=60,
            max_attempts=1,
            max_redirects=0,
            rate_limit_per_second=Decimal("1"),
            retry_base_delay_seconds=Decimal("1"),
            cache_enabled=False,
            cache_ttl_seconds=None,
            retention_days=30,
        )
    )
    governance.add_license_policy(
        SourceLicensePolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            status=ProviderLicenseStatus.APPROVED,
            acquisition=LicensePermission.ALLOWED,
            raw_storage=LicensePermission.ALLOWED,
            cache=LicensePermission.PROHIBITED,
            derived_use=LicensePermission.ALLOWED,
            redistribution=LicensePermission.PROHIBITED,
            retention_days=30,
            deletion_required=False,
            attribution_required=True,
            terms_source_ids=("TEST_TERMS",),
            reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
            expires_at=None,
        )
    )
    return definition, capability


def _sync_command(operation: str) -> ProviderControlCommand:
    return ProviderControlCommand(
        operation=operation,
        provider_code="CLI_OFFLINE_TEST",
        capability_code="OFFLINE_SAMPLE",
        provider_version="1.0.0",
        capability_version="1.0.0",
        policy_version="1.0.0",
        license_version="1.0.0",
        universe_code="BOUNDED_TEST",
        research_as_of_time=datetime(2026, 7, 29, tzinfo=UTC),
        range_start=date(2026, 7, 1),
        range_end=date(2026, 7, 29),
        max_requests=2,
        max_bytes=4096,
        max_attempts=1,
        max_duration_seconds=30,
        confirmed=True,
    )


def test_control_cli_persists_finite_plan_and_append_only_audit_without_committing(
    session: Session,
) -> None:
    definition, _ = _governance(session)
    result = execute_provider_control(session, _sync_command("sync-plan"))

    assert result["status"] == "PLANNED"
    assert result["execution_mode"] == "OFFLINE"
    assert session.in_transaction()
    events = session.scalars(
        select(ProviderAuditEvent).where(ProviderAuditEvent.provider_definition_id == definition.id)
    ).all()
    assert [(event.action_code, event.decision_code) for event in events] == [
        ("SYNC_PLAN", "PLANNED")
    ]
    assert all(len(event.event_checksum) == 64 for event in events)


def test_sync_run_and_live_check_fail_closed_without_network_or_live_state(
    session: Session,
) -> None:
    definition, _ = _governance(session)
    run = execute_provider_control(session, _sync_command("sync-run"))
    live = execute_provider_control(
        session,
        ProviderControlCommand(
            operation="live-check",
            provider_code="CLI_OFFLINE_TEST",
            capability_code="OFFLINE_SAMPLE",
            provider_version="1.0.0",
            capability_version="1.0.0",
            max_requests=1,
            max_bytes=1024,
            confirmed=True,
        ),
    )

    assert run["status"] == "BLOCKED"
    assert run["warning"] == "OFFLINE_FIXTURE_EXECUTOR_NOT_SELECTED"
    assert live == {
        "status": "BLOCKED",
        "live_status": "NOT_ATTEMPTED",
        "warning": "LIVE_AUTHORIZATION_REQUIRED",
    }
    assert (
        session.scalar(
            select(func.count())
            .select_from(ProviderSyncRun)
            .where(ProviderSyncRun.provider_definition_id == definition.id)
        )
        == 1
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(ProviderLiveValidationRun)
            .where(ProviderLiveValidationRun.provider_definition_id == definition.id)
        )
        == 0
    )
    events = session.scalars(
        select(ProviderAuditEvent)
        .where(ProviderAuditEvent.provider_definition_id == definition.id)
        .order_by(ProviderAuditEvent.created_at, ProviderAuditEvent.id)
    ).all()
    assert {event.action_code for event in events} == {"SYNC_RUN", "LIVE_CHECK_REFUSED"}
    assert all("secret" not in event.safe_summary.casefold() for event in events)
