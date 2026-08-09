from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from stock_research_agent.db.models.data_access import DataSnapshot
from stock_research_agent.db.models.reports import ResearchReport
from stock_research_agent.db.models.research_agent import ResearchAgentRun
from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
    SqlAlchemyProviderQueryRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderConfigurationStatus,
    ProviderCredentialStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderLiveValidationStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.health import (
    ProviderHealthSnapshotWrite,
    ProviderReadinessStatus,
)
from stock_research_agent.domain.providers.licenses import (
    LicensePermission,
    SourceLicensePolicyWrite,
)
from stock_research_agent.domain.providers.policies import ProviderPolicyWrite
from stock_research_agent.domain.providers.queries import ProviderQueryService
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderSyncRequestWrite,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
    SecurityMasterSeedService,
)
from stock_research_agent.providers.blocked import get_blocked_provider_descriptor
from stock_research_agent.providers.tushare.adapter import TushareAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 29, tzinfo=UTC)


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 9 company acceptance")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    value = create_engine(TEST_DATABASE_URL)
    try:
        yield value
    finally:
        value.dispose()
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


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


def _persist_offline_boundary(
    session: Session,
    *,
    provider_code: str,
    capability_code: str,
    security_id: UUID,
    market_code: str,
    production_status: ProviderProductionStatus,
    include_health: bool = True,
) -> None:
    definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
        ProviderDefinitionWrite(
            code=provider_code,
            definition_version="1.0.0",
            adapter_version="1.0.0",
            display_name=f"{provider_code} Stage 9 acceptance",
            data_domain="DOCUMENT_DISCLOSURES",
            definition_status=ProviderDefinitionStatus.ACTIVE,
            production_status=production_status,
            official_domains=(
                "data.sec.gov" if provider_code == "SEC_EDGAR_PUBLIC_V1" else "api.tushare.pro",
            ),
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
            code=capability_code,
            capability_version="1.0.0",
            status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
            data_domain="DOCUMENT_DISCLOSURES",
            market_codes=(market_code,),
            security_types=("COMMON_STOCK",),
            operations=("READ_OFFLINE_FIXTURE",),
        )
    )
    policy = governance.add_policy(
        ProviderPolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            endpoint_policy_version="1.0.0",
            network_enabled=False,
            max_requests=2,
            max_response_bytes=4096,
            max_total_bytes=8192,
            max_duration_seconds=30,
            max_attempts=1,
            max_redirects=0,
            rate_limit_per_second=Decimal("1"),
            retry_base_delay_seconds=Decimal("1"),
            cache_enabled=False,
            cache_ttl_seconds=None,
            retention_days=30,
        )
    )
    license_policy = governance.add_license_policy(
        SourceLicensePolicyWrite(
            provider_definition_id=definition.id,
            policy_version="1.0.0",
            status=ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
            acquisition=LicensePermission.UNKNOWN_REQUIRES_REVIEW,
            raw_storage=LicensePermission.UNKNOWN_REQUIRES_REVIEW,
            cache=LicensePermission.PROHIBITED,
            derived_use=LicensePermission.UNKNOWN_REQUIRES_REVIEW,
            redistribution=LicensePermission.PROHIBITED,
            retention_days=30,
            deletion_required=False,
            attribution_required=True,
            terms_source_ids=(f"{provider_code}_STAGE1_EVIDENCE",),
            reviewed_at=AS_OF,
            expires_at=None,
        )
    )
    identity = {
        "provider_definition_id": str(definition.id),
        "provider_capability_id": str(capability.id),
        "security_id": str(security_id),
        "research_as_of_time": AS_OF,
    }
    SqlAlchemyProviderSyncRepository(session).create_request(
        ProviderSyncRequestWrite(
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
            policy_id=policy.id,
            license_policy_id=license_policy.id,
            credential_reference_id=None,
            security_id=security_id,
            universe_code=None,
            research_as_of_time=AS_OF,
            range_start=date(2025, 1, 1),
            range_end=date(2026, 7, 29),
            execution_mode=ProviderExecutionMode.OFFLINE,
            scope={"scope_type": "SECURITY", "scope_value": str(security_id)},
            budget={
                "max_requests": 2,
                "max_bytes": 8192,
                "max_attempts": 1,
                "max_duration_seconds": 30,
            },
            request_checksum=provider_checksum(identity),
            idempotency_key=provider_checksum({"stage9_acceptance": identity}),
        )
    )
    if not include_health:
        return
    reasons = (
        ("LIVE_VALIDATION_NOT_PASSED", "PRODUCTION_STATUS_BLOCKED")
        if production_status is ProviderProductionStatus.BLOCKED
        else ("LICENSE_NOT_APPROVED", "LIVE_VALIDATION_NOT_PASSED")
    )
    health_values = {
        "provider_definition_id": definition.id,
        "status": ProviderReadinessStatus.BLOCKED,
        "configuration_status": (
            ProviderConfigurationStatus.BLOCKED
            if production_status is ProviderProductionStatus.BLOCKED
            else ProviderConfigurationStatus.VALID
        ),
        "credential_status": ProviderCredentialStatus.NOT_READ,
        "license_status": ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED,
        "live_validation_status": ProviderLiveValidationStatus.NOT_ATTEMPTED,
        "limiting_reasons": reasons,
        "observed_at": AS_OF,
    }
    governance.add_health_snapshot(
        ProviderHealthSnapshotWrite(
            **health_values,
            checksum=provider_checksum(health_values),
        )
    )


def test_real_company_acceptance_documents_state_current_offline_boundaries() -> None:
    industrial_fii = (PROJECT_ROOT / "docs/sample-data-validation/601138.SH.md").read_text(
        encoding="utf-8"
    )
    micron = (PROJECT_ROOT / "docs/sample-data-validation/MU.md").read_text(encoding="utf-8")

    assert "## Stage 9 offline production-provider acceptance" in industrial_fii
    assert "Stage 9 company evidence status: `BLOCKED`" in industrial_fii
    assert "TUSHARE_PRO_V1: `BLOCKED`" in industrial_fii
    assert "SSE_DISCLOSURE_BODIES_V1: `BLOCKED`" in industrial_fii
    assert "Live validation: `NOT_ATTEMPTED`" in industrial_fii
    assert "Synthetic fixtures accepted as company evidence: `0`" in industrial_fii

    assert "## Stage 9 offline production-provider acceptance" in micron
    assert "SEC offline adapter and metadata contract: `PASS`" in micron
    assert "Verified company filing body: `BLOCKED`" in micron
    assert "Verified financial completion: `BLOCKED`" in micron
    assert "Live validation: `NOT_ATTEMPTED`" in micron
    assert "Synthetic fixtures accepted as company evidence: `0`" in micron


def test_public_synthetic_fixtures_do_not_fill_missing_evidence() -> None:
    sec_root = PROJECT_ROOT / "tests/fixtures/providers/sec_synthetic"
    tushare_root = PROJECT_ROOT / "tests/fixtures/providers/tushare"
    sec_manifest = json.loads((sec_root / "tstx_sec_public.manifest.json").read_text("utf-8"))
    sec_payload = json.loads((sec_root / "tstx_sec_public.json").read_text("utf-8"))
    tushare_manifest = json.loads(
        (tushare_root / "synthetic_protocol_response.manifest.json").read_text("utf-8")
    )
    tushare_payload = json.loads(
        (tushare_root / "synthetic_protocol_response.json").read_text("utf-8")
    )

    assert (
        sec_manifest["data_origin"],
        sec_manifest["access_mode"],
        sec_manifest["live_status"],
    ) == (
        "FIXTURE",
        "OFFLINE",
        "NOT_LIVE",
    )
    assert "body" not in sec_payload
    assert sec_payload["financial_facts"] == []
    assert sec_manifest["synthetic"] is True
    assert sec_manifest["company_evidence"] is False
    assert tushare_manifest["security"] == "SYNTHETIC_SECURITY"
    assert tushare_manifest["company_evidence_status"] == "NOT_COMPANY_EVIDENCE"
    assert tushare_manifest["data_origin"] == "SYNTHETIC_TEST_ONLY"
    assert tushare_payload["data"]["items"] == []


def test_industrial_fii_live_providers_remain_fail_closed() -> None:
    tushare = TushareAdapter.descriptor
    disclosure = get_blocked_provider_descriptor("SSE_DISCLOSURE_BODIES_V1")

    assert tushare.production_status is ProviderProductionStatus.BLOCKED
    assert tushare.capability_status is ProviderCapabilityStatus.IMPLEMENTED_OFFLINE
    assert tushare.license_status is ProviderLicenseStatus.RESTRICTED_REVIEW_REQUIRED
    assert tushare.credential_status.value == "NOT_READ"
    assert tushare.live_status.value == "NOT_ATTEMPTED"
    assert disclosure is not None
    assert disclosure.production_status is ProviderProductionStatus.BLOCKED
    assert disclosure.live_status.value == "NOT_ATTEMPTED"
    assert disclosure.network_status == "HARD_BLOCKED"


def test_postgresql_queries_preserve_real_company_readiness_without_downstream_writes(
    session: Session,
) -> None:
    SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
    before = tuple(
        session.scalar(select(func.count()).select_from(model))
        for model in (DataSnapshot, ResearchAgentRun, ResearchReport)
    )
    _persist_offline_boundary(
        session,
        provider_code="TUSHARE_PRO_V1",
        capability_code="FETCH_EOD_PRICES",
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        market_code="CN_A",
        production_status=ProviderProductionStatus.BLOCKED,
    )
    _persist_offline_boundary(
        session,
        provider_code="SEC_EDGAR_PUBLIC_V1",
        capability_code="FETCH_SEC_SUBMISSIONS",
        security_id=MICRON_SECURITY_ID,
        market_code="US_EQUITY",
        production_status=ProviderProductionStatus.CONDITIONAL,
    )
    service = ProviderQueryService(SqlAlchemyProviderQueryRepository(session))

    industrial_fii = service.get_readiness(INDUSTRIAL_FII_SECURITY_ID)
    micron = service.get_readiness(MICRON_SECURITY_ID)

    assert industrial_fii is not None
    assert industrial_fii.values == {
        "security_id": str(INDUSTRIAL_FII_SECURITY_ID),
        "status": "BLOCKED",
        "provider_count": 1,
        "providers": [
            {
                "provider_code": "TUSHARE_PRO_V1",
                "definition_status": "ACTIVE",
                "production_status": "BLOCKED",
                "capability_code": "FETCH_EOD_PRICES",
                "capability_status": "IMPLEMENTED_OFFLINE",
                "readiness_status": "BLOCKED",
                "limiting_reasons": [
                    "LIVE_VALIDATION_NOT_PASSED",
                    "PRODUCTION_STATUS_BLOCKED",
                ],
                "health_observed_at": "2026-07-29T00:00:00Z",
            }
        ],
        "limiting_reasons": [
            "TUSHARE_PRO_V1:FETCH_EOD_PRICES:LIVE_VALIDATION_NOT_PASSED",
            "TUSHARE_PRO_V1:FETCH_EOD_PRICES:PRODUCTION_STATUS_BLOCKED",
        ],
    }
    assert micron is not None
    assert micron.values == {
        "security_id": str(MICRON_SECURITY_ID),
        "status": "BLOCKED",
        "provider_count": 1,
        "providers": [
            {
                "provider_code": "SEC_EDGAR_PUBLIC_V1",
                "definition_status": "ACTIVE",
                "production_status": "CONDITIONAL",
                "capability_code": "FETCH_SEC_SUBMISSIONS",
                "capability_status": "IMPLEMENTED_OFFLINE",
                "readiness_status": "BLOCKED",
                "limiting_reasons": [
                    "LICENSE_NOT_APPROVED",
                    "LIVE_VALIDATION_NOT_PASSED",
                ],
                "health_observed_at": "2026-07-29T00:00:00Z",
            }
        ],
        "limiting_reasons": [
            "SEC_EDGAR_PUBLIC_V1:FETCH_SEC_SUBMISSIONS:LICENSE_NOT_APPROVED",
            "SEC_EDGAR_PUBLIC_V1:FETCH_SEC_SUBMISSIONS:LIVE_VALIDATION_NOT_PASSED",
        ],
    }
    after = tuple(
        session.scalar(select(func.count()).select_from(model))
        for model in (DataSnapshot, ResearchAgentRun, ResearchReport)
    )
    assert after == before


def test_readiness_without_health_snapshot_fails_closed_with_stable_reason(
    session: Session,
) -> None:
    SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
    _persist_offline_boundary(
        session,
        provider_code="TUSHARE_PRO_V1",
        capability_code="FETCH_EOD_PRICES",
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        market_code="CN_A",
        production_status=ProviderProductionStatus.BLOCKED,
        include_health=False,
    )

    result = ProviderQueryService(SqlAlchemyProviderQueryRepository(session)).get_readiness(
        INDUSTRIAL_FII_SECURITY_ID
    )

    assert result is not None
    assert result.values["status"] == "BLOCKED"
    assert result.values["limiting_reasons"] == [
        "TUSHARE_PRO_V1:FETCH_EOD_PRICES:HEALTH_SNAPSHOT_NOT_FOUND"
    ]
    providers = result.values["providers"]
    assert isinstance(providers, list)
    assert providers[0]["readiness_status"] == "BLOCKED"
    assert providers[0]["limiting_reasons"] == ["HEALTH_SNAPSHOT_NOT_FOUND"]
    assert providers[0]["health_observed_at"] is None
