from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from stock_research_agent import cli
from stock_research_agent.cli_research_pipeline import research_application_factory
from stock_research_agent.db.models.data_access import (
    DataProvider,
    DataSnapshot,
    SnapshotItem,
)
from stock_research_agent.db.models.research_agent import ResearchPolicy
from stock_research_agent.db.repositories.research_agent import (
    SqlAlchemyResearchAgentRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.reports.application import (
    GenerateReportCommand,
    ReflectReportCommand,
    ReleaseCheckCommand,
    ReviseReportCommand,
)
from stock_research_agent.domain.reports.enums import ReportLocale, ReportType
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    ObservationStatus,
    ObservationType,
    PackageSectionStatus,
    ResearchMode,
    ResearchPackageStatus,
    ResearchRunEventType,
    ResearchRunStatus,
    ResearchSection,
    ResearchStepStatus,
    ResearchStepType,
    ResearchType,
    SyntheticStatus,
    ToolInvocationStatus,
)
from stock_research_agent.domain.research_agent.policies import (
    ResearchPolicySeedService,
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkWrite,
    RequestedBudgets,
    ResearchClaimCompletion,
    ResearchClaimWrite,
    ResearchEvidenceWrite,
    ResearchObservationWrite,
    ResearchPackageSection,
    ResearchPackageWrite,
    ResearchPlanWrite,
    ResearchPolicyWrite,
    ResearchRequestWrite,
    ResearchRunEventWrite,
    ResearchRunUpdate,
    ResearchRunWrite,
    ResearchStepDefinition,
    ResearchStepWrite,
    ResearchToolInvocationCompletion,
    ResearchToolInvocationWrite,
    RunBudget,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_ISSUER_ID,
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
    SecurityMasterSeedService,
)
from stock_research_agent.report_cli_application import create_report_cli_application

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 10, 12, tzinfo=UTC)
SNAPSHOT_ID = UUID("72000000-0000-4000-8000-000000000001")
PARTIAL_SNAPSHOT_ID = UUID("72000000-0000-4000-8000-000000000006")
PROVIDER_ID = UUID("72000000-0000-4000-8000-000000000002")
SNAPSHOT_ITEM_ID = UUID("72000000-0000-4000-8000-000000000003")
SOURCE_RECORD_ID = UUID("72000000-0000-4000-8000-000000000004")
CATALOG_VERSION = "tool-catalog-v1:" + "a" * 64
COMPONENT_LINEAGE_REVISION = "0011_component_observation_lineage"
COMPONENT_LINEAGE_INTEGRITY_REVISION = "0012_component_observation_lineage_integrity"
runner = CliRunner()


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 7 repository tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def migrated_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL)
    command.downgrade(
        Config(str(PROJECT_ROOT / "alembic.ini")),
        "0005_rag_citations",
    )
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    with Session(engine) as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        provider = session.get(DataProvider, PROVIDER_ID)
        if provider is None:
            session.add(
                DataProvider(
                    id=PROVIDER_ID,
                    code="STAGE7_TEST_FIXTURE",
                    name="Stage 7 repository test fixture",
                    provider_type="FIXTURE",
                    status="APPROVED",
                    base_url=None,
                    documentation_url=None,
                    terms_status="VERIFIED",
                    capabilities=["DAILY_PRICES"],
                )
            )
        snapshot = session.get(DataSnapshot, SNAPSHOT_ID)
        if snapshot is None:
            snapshot = DataSnapshot(
                id=SNAPSHOT_ID,
                security_id=INDUSTRIAL_FII_SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=7001,
                status="BUILDING",
                completed_at=None,
                checksum=None,
                formula_version="raw-data-v1",
                notes="Stage 7 repository integration fixture",
            )
            session.add(snapshot)
            session.flush()
            session.add(
                SnapshotItem(
                    id=SNAPSHOT_ITEM_ID,
                    snapshot_id=SNAPSHOT_ID,
                    provider_id=PROVIDER_ID,
                    category="DAILY_PRICES",
                    source_record_type="daily_price_bars",
                    source_record_id=SOURCE_RECORD_ID,
                    source_published_at=AS_OF,
                    retrieved_at=AS_OF,
                    checksum_input="stage7-repository-snapshot-item",
                    checksum="8" * 64,
                )
            )
            session.flush()
            snapshot.status = "COMPLETE"
            snapshot.completed_at = AS_OF
            snapshot.checksum = "7" * 64
        partial_snapshot = session.get(DataSnapshot, PARTIAL_SNAPSHOT_ID)
        if partial_snapshot is None:
            partial_snapshot = DataSnapshot(
                id=PARTIAL_SNAPSHOT_ID,
                security_id=INDUSTRIAL_FII_SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=7003,
                status="BUILDING",
                completed_at=None,
                checksum=None,
                formula_version="raw-data-v1",
                notes="Stage 10 E2E UTC contract fixture",
            )
            session.add(partial_snapshot)
            session.flush()
            partial_snapshot.status = "PARTIAL"
            partial_snapshot.completed_at = AS_OF
            partial_snapshot.checksum = "6" * 64
        session.commit()
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            for table in (
                "research_run_events",
                "research_packages",
                "claim_evidence_links",
                "research_claims",
                "research_evidence",
                "research_observations",
                "research_tool_invocations",
                "research_steps",
                "research_plans",
                "research_agent_runs",
                "research_requests",
                "research_policies",
            ):
                connection.exec_driver_sql(f"TRUNCATE TABLE {table} CASCADE")
        engine.dispose()


def _budget() -> RunBudget:
    return RunBudget(
        max_steps=12,
        max_tool_calls=24,
        max_calls_per_tool=5,
        max_retries_per_step=1,
        max_duration_seconds=120,
        model_token_budget=0,
        consumed_steps=0,
        consumed_tool_calls=0,
        consumed_model_tokens=0,
        elapsed_seconds=Decimal("0"),
    )


def _request(policy_version: str, request_id: UUID) -> ResearchRequestWrite:
    return ResearchRequestWrite(
        id=request_id,
        security_query="601138.SH",
        resolved_security_id=INDUSTRIAL_FII_SECURITY_ID,
        normalized_security_query="601138.SH",
        research_type=ResearchType.COMPANY_OVERVIEW,
        research_mode=ResearchMode.REAL_RESEARCH,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        requested_sections=(ResearchSection.SECURITY_IDENTITY,),
        requested_budgets=RequestedBudgets(),
        policy_version=policy_version,
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        tool_catalog_checksum="a" * 64,
        request_checksum="b" * 64,
        created_at=AS_OF,
    )


def test_production_research_pipeline_composes_and_persists_a_real_plan(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    application = research_application_factory()
    result = application.run(
        SNAPSHOT_ID,
        ResearchType.COMPANY_OVERVIEW.value,
        "controlled-offline-v1",
        AS_OF,
    )

    assert result["plan_id"] is not None
    assert result["run_id"] is not None
    assert result["package_id"] is not None
    assert result["status"] in {"COMPLETED", "PARTIAL", "BLOCKED"}
    assert result["tool_invocation_count"] == 4
    with migrated_engine.connect() as connection:
        request_count = connection.exec_driver_sql(
            "SELECT count(*) FROM research_requests"
        ).scalar_one()
        run_count = connection.exec_driver_sql(
            "SELECT count(*) FROM research_agent_runs"
        ).scalar_one()
        assert request_count == 1
        assert run_count == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM research_plans").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM research_steps").scalar_one() > 0
        run_warnings = connection.scalar(text("SELECT warning_codes FROM research_agent_runs"))
        package_warnings = connection.scalar(text("SELECT warnings FROM research_packages"))
    assert "AGENT_SNAPSHOT_PARTIAL" not in run_warnings
    assert "AGENT_SNAPSHOT_PARTIAL" not in package_warnings


@pytest.mark.parametrize(
    "as_of",
    (
        "2026-07-18T23:59:00Z",
        "2026-07-18T23:59:00+00:00",
        "2026-07-19T07:59:00+08:00",
    ),
)
def test_agent_cli_normalizes_aware_iso_as_of_before_research_request(
    migrated_engine: Engine,
    as_of: str,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = runner.invoke(
        cli.app,
        [
            "agent",
            "plan",
            "601138.SH",
            "--type",
            "COMPANY_OVERVIEW",
            "--snapshot",
            str(SNAPSHOT_ID),
            "--as-of",
            as_of,
            "--policy",
            "controlled-offline-v1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    with migrated_engine.connect() as connection:
        stored = connection.scalar(text("SELECT research_as_of_time FROM research_requests"))
    assert stored == datetime(2026, 7, 18, 23, 59, tzinfo=UTC)


def test_agent_cli_rejects_naive_as_of_without_assuming_timezone(
    migrated_engine: Engine,
) -> None:
    result = runner.invoke(
        cli.app,
        [
            "agent",
            "plan",
            "601138.SH",
            "--type",
            "COMPANY_OVERVIEW",
            "--snapshot",
            str(SNAPSHOT_ID),
            "--as-of",
            "2026-07-18T23:59:00",
            "--policy",
            "controlled-offline-v1",
        ],
    )

    assert result.exit_code == 2
    assert "AS_OF_MUST_BE_AWARE_ISO_8601" in result.output
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM research_requests")) == 0


def test_research_pipeline_accepts_aware_cli_as_of_for_complete_snapshot(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = runner.invoke(
        cli.app,
        [
            "research-pipeline",
            "run-from-snapshot",
            str(SNAPSHOT_ID),
            "FULL_RESEARCH_PACKAGE",
            "controlled-offline-v1",
            "2026-07-18T23:59:00Z",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "SNAPSHOT_NOT_COMPLETE" not in result.stdout
    assert "AGENT_PLAN_REQUIRED" not in result.stdout


def test_production_composition_admits_partial_snapshot_and_persists_request_plan_run(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )

    assert result["request_id"] is not None
    assert result["plan_id"] is not None
    assert result["run_id"] is not None
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM research_requests")) == 1
        assert connection.scalar(text("SELECT count(*) FROM research_plans")) == 1
        assert connection.scalar(text("SELECT count(*) FROM research_agent_runs")) == 1


@pytest.mark.parametrize(
    ("status", "completed_at", "checksum"),
    (
        ("BUILDING", None, None),
        ("FAILED", AS_OF, None),
        ("SUPERSEDED", AS_OF, "5" * 64),
    ),
)
def test_postgres_request_trigger_rejects_non_admissible_snapshot_statuses(
    migrated_engine: Engine,
    status: str,
    completed_at: datetime | None,
    checksum: str | None,
) -> None:
    snapshot_id = uuid4()
    snapshot_version = uuid4().int % 2_000_000_000 + 1
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()
        snapshot = DataSnapshot(
            id=snapshot_id,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            research_as_of_time=AS_OF,
            snapshot_version=snapshot_version,
            status="BUILDING",
            completed_at=None,
            checksum=None,
            formula_version="raw-data-v1",
            notes=f"Stage 10 E2E rejected {status} Snapshot fixture",
        )
        session.add(snapshot)
        session.flush()
        if status != "BUILDING":
            snapshot.status = status
            snapshot.completed_at = completed_at
            snapshot.checksum = checksum
            session.flush()

        write = _request("controlled-offline-v1", uuid4()).model_copy(
            update={"snapshot_id": snapshot_id}
        )
        with pytest.raises(IntegrityError, match="research request snapshot context"):
            SqlAlchemyResearchAgentRepository(session).add_request(write)
        session.rollback()


def test_partial_snapshot_degraded_context_is_auditable_and_never_complete(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )

    assert result["status"] in {"PARTIAL", "BLOCKED"}
    with migrated_engine.connect() as connection:
        run = connection.execute(
            text("SELECT status, warning_codes FROM research_agent_runs")
        ).one()
        package = connection.execute(text("SELECT status, warnings FROM research_packages")).one()
    assert run.status in {"PARTIAL", "BLOCKED"}
    assert package.status in {"PARTIAL", "BLOCKED"}
    assert "AGENT_SNAPSHOT_PARTIAL" in run.warning_codes
    assert "AGENT_SNAPSHOT_PARTIAL" in package.warnings
    assert run.warning_codes.count("AGENT_SNAPSHOT_PARTIAL") == 1
    assert package.warnings.count("AGENT_SNAPSHOT_PARTIAL") == 1
    with migrated_engine.connect() as connection:
        invocation_statuses = tuple(
            connection.scalars(
                text("SELECT status FROM research_tool_invocations ORDER BY started_at")
            )
        )
    assert invocation_statuses
    assert "FAIL" not in invocation_statuses
    assert set(invocation_statuses) <= {"PASS", "PARTIAL", "BLOCKED"}


def test_production_observations_are_admitted_and_persisted_as_audit_evidence(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )

    with migrated_engine.connect() as connection:
        observation_rows = connection.execute(
            text(
                "SELECT o.id, o.research_step_id, o.invocation_id, "
                "i.research_step_id AS invocation_step_id "
                "FROM research_observations o "
                "JOIN research_tool_invocations i ON i.id = o.invocation_id "
                "ORDER BY o.id"
            )
        ).all()
        evidence_rows = connection.execute(
            text(
                "SELECT e.observation_id, e.status, e.source_record_type, "
                "e.source_record_id, e.source_checksum FROM research_evidence e "
                "JOIN research_observations o ON o.id = e.observation_id "
                "WHERE o.invocation_id IS NOT NULL ORDER BY e.observation_id"
            )
        ).all()

    observation_ids = tuple(row.id for row in observation_rows)
    assert observation_rows
    assert all(row.invocation_id is not None for row in observation_rows)
    assert all(row.research_step_id == row.invocation_step_id for row in observation_rows)
    assert len(evidence_rows) == len(observation_ids)
    assert tuple(row.observation_id for row in evidence_rows) == observation_ids
    assert all(
        row.status in {"VALID", "BLOCKED", "SOURCE_MISSING", "INVALID"} for row in evidence_rows
    )
    assert all(row.source_record_type for row in evidence_rows)
    assert all(row.source_record_id for row in evidence_rows)
    assert all(row.source_checksum for row in evidence_rows)


def test_production_evidence_adapter_never_promotes_unsafe_observations(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )

    with migrated_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT i.tool_name, i.status AS invocation_status, "
                "o.status AS observation_status, e.evidence_type, "
                "e.status AS evidence_status "
                "FROM research_tool_invocations i "
                "LEFT JOIN research_observations o ON o.invocation_id = i.id "
                "LEFT JOIN research_evidence e ON e.observation_id = o.id "
                "ORDER BY i.started_at, i.id"
            )
        ).all()

    evidence_rows = tuple(row for row in rows if row.evidence_type is not None)
    assert evidence_rows
    assert all(
        row.evidence_type == "BLOCKED_CAPABILITY_EVIDENCE" and row.evidence_status == "BLOCKED"
        for row in evidence_rows
        if row.observation_status == "BLOCKED"
    )
    assert all(
        row.evidence_type in {"SNAPSHOT_EVIDENCE", "DATA_QUALITY_EVIDENCE"}
        for row in evidence_rows
        if row.evidence_status == "VALID"
    )
    assert not any(
        row.evidence_status == "VALID"
        and row.evidence_type
        in {
            "STRUCTURED_FACT_EVIDENCE",
            "DERIVED_METRIC_EVIDENCE",
            "METRIC_LINEAGE_EVIDENCE",
            "DOCUMENT_CITATION_EVIDENCE",
            "CORPORATE_ACTION_EVIDENCE",
        }
        for row in evidence_rows
    )
    lineage = next(row for row in rows if row.tool_name == "get_metric_lineage")
    assert lineage.invocation_status == "BLOCKED"
    assert lineage.observation_status is None
    assert lineage.evidence_type is None


def test_production_validated_evidence_builds_links_and_terminal_claims(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )

    with migrated_engine.connect() as connection:
        evidence_count = connection.scalar(text("SELECT count(*) FROM research_evidence"))
        claims = connection.execute(
            text(
                "SELECT id, claim_type, lifecycle_status, support_status, "
                "builder_version, validator_version, completed_at "
                "FROM research_claims ORDER BY created_at, id"
            )
        ).all()
        links = connection.execute(
            text(
                "SELECT l.claim_id, l.evidence_id, l.role, e.status AS evidence_status "
                "FROM claim_evidence_links l "
                "JOIN research_evidence e ON e.id = l.evidence_id "
                "ORDER BY l.claim_id, l.evidence_id"
            )
        ).all()

    assert evidence_count and evidence_count > 0
    assert claims
    assert len(links) == len(claims)
    assert {row.claim_id for row in links} == {row.id for row in claims}
    assert all(row.lifecycle_status == "VALIDATED" for row in claims)
    assert all(row.builder_version == "deterministic-claim-builder-v1" for row in claims)
    assert all(row.validator_version == "claim-support-validator-v1" for row in claims)
    assert all(row.completed_at is not None for row in claims)


def test_production_claim_wiring_never_supports_facts_without_factual_evidence(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )

    factual_types = (
        "IDENTITY",
        "FINANCIAL_FACT",
        "FINANCIAL_METRIC",
        "VALUATION_METRIC",
        "DOCUMENT_DISCLOSURE",
        "CORPORATE_ACTION",
    )
    with migrated_engine.connect() as connection:
        supported_factual = connection.execute(
            text(
                "SELECT c.claim_type, e.evidence_type FROM research_claims c "
                "JOIN claim_evidence_links l ON l.claim_id = c.id "
                "JOIN research_evidence e ON e.id = l.evidence_id "
                "WHERE c.support_status = 'SUPPORTED' AND c.claim_type = ANY(:types)"
            ),
            {"types": list(factual_types)},
        ).all()
        unsafe_links = connection.scalar(
            text(
                "SELECT count(*) FROM claim_evidence_links l "
                "JOIN research_claims c ON c.id = l.claim_id "
                "JOIN research_evidence e ON e.id = l.evidence_id "
                "WHERE c.support_status = 'SUPPORTED' "
                "AND (e.status <> 'VALID' OR e.synthetic_status IN "
                "('SYNTHETIC_TEST_ONLY', 'UNKNOWN'))"
            )
        )
        claims = connection.execute(
            text(
                "SELECT claim_type, support_status FROM research_claims "
                "ORDER BY claim_type, support_status"
            )
        ).all()

    assert claims
    assert [(row.claim_type, row.evidence_type) for row in supported_factual] == [
        ("IDENTITY", "SECURITY_MASTER_EVIDENCE")
    ]
    assert unsafe_links == 0
    assert {row.claim_type for row in claims} <= {"IDENTITY", "DATA_QUALITY", "LIMITATION"}
    assert all(row.support_status == "BLOCKED" for row in claims if row.claim_type == "LIMITATION")


def test_production_package_consumes_persisted_run_scoped_evidence_and_claims(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )
    package_id = UUID(str(result["package_id"]))

    with migrated_engine.connect() as connection:
        package = connection.execute(
            text(
                "SELECT research_agent_run_id, security_id, snapshot_id, sections, "
                "evidence_ids, warnings FROM research_packages WHERE id = :id"
            ),
            {"id": package_id},
        ).one()
        evidence = connection.execute(
            text(
                "SELECT id, research_agent_run_id, security_id, snapshot_id "
                "FROM research_evidence ORDER BY id"
            )
        ).all()
        claims = connection.execute(
            text(
                "SELECT id, research_agent_run_id, lifecycle_status "
                "FROM research_claims ORDER BY id"
            )
        ).all()
        links = connection.execute(
            text(
                "SELECT claim_id, evidence_id, research_agent_run_id "
                "FROM claim_evidence_links ORDER BY id"
            )
        ).all()

    packaged_claim_ids = {
        UUID(claim_id) for section in package.sections for claim_id in section["claim_ids"]
    }
    packaged_evidence_ids = {UUID(evidence_id) for evidence_id in package.evidence_ids}
    persisted_claim_ids = {row.id for row in claims}
    persisted_evidence_ids = {row.id for row in evidence}

    assert evidence and claims and links
    assert packaged_evidence_ids == persisted_evidence_ids
    assert packaged_claim_ids == persisted_claim_ids
    assert all(row.lifecycle_status == "VALIDATED" for row in claims)
    assert all(row.research_agent_run_id == package.research_agent_run_id for row in evidence)
    assert all(row.security_id == package.security_id for row in evidence)
    assert all(row.snapshot_id == package.snapshot_id for row in evidence)
    assert all(row.research_agent_run_id == package.research_agent_run_id for row in claims)
    assert all(row.research_agent_run_id == package.research_agent_run_id for row in links)
    assert {row.claim_id for row in links} <= packaged_claim_ids
    assert {row.evidence_id for row in links} <= packaged_evidence_ids
    assert "NO_VALIDATED_CLAIMS" not in package.warnings


def test_production_package_never_promotes_partial_snapshot_research(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )
    package_id = UUID(str(result["package_id"]))

    with migrated_engine.connect() as connection:
        package = connection.execute(
            text("SELECT status, warnings FROM research_packages WHERE id = :id"),
            {"id": package_id},
        ).one()
        supported_factual = (
            connection.execute(
                text(
                    "SELECT claim_type FROM research_claims WHERE support_status = 'SUPPORTED' "
                    "AND claim_type IN ('IDENTITY', 'FINANCIAL_FACT', 'FINANCIAL_METRIC', "
                    "'VALUATION_METRIC', 'DOCUMENT_DISCLOSURE', 'CORPORATE_ACTION') "
                    "ORDER BY claim_type"
                )
            )
            .scalars()
            .all()
        )

    assert package.status in {"PARTIAL", "BLOCKED"}
    assert package.status != "COMPLETE"
    assert "AGENT_SNAPSHOT_PARTIAL" in package.warnings
    assert supported_factual == ["IDENTITY"]


def test_production_resolve_security_persists_canonical_identity_artifacts(
    migrated_engine: Engine,
) -> None:
    """RED-013: production resolve_security freezes one Ledger-admitted identity."""
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )
    run_id = UUID(str(result["run_id"]))
    package_id = UUID(str(result["package_id"]))

    with migrated_engine.connect() as connection:
        observations = connection.execute(
            text(
                "SELECT o.id, o.research_step_id, o.invocation_id, o.payload, "
                "o.output_checksum FROM research_observations o "
                "WHERE o.research_agent_run_id = :run_id "
                "AND o.observation_type = 'SECURITY_IDENTITY'"
            ),
            {"run_id": run_id},
        ).all()
        evidence = connection.execute(
            text(
                "SELECT e.id, e.observation_id, e.status, e.security_id, e.payload, "
                "e.source_record_type, e.source_record_id, e.source_checksum "
                "FROM research_evidence e WHERE e.research_agent_run_id = :run_id "
                "AND e.evidence_type = 'SECURITY_MASTER_EVIDENCE'"
            ),
            {"run_id": run_id},
        ).all()
        package = connection.execute(
            text("SELECT security_id, evidence_ids FROM research_packages WHERE id = :id"),
            {"id": package_id},
        ).one()

    assert len(observations) == 1
    assert len(evidence) == 1
    observation = observations[0]
    identity = evidence[0]
    expected_payload = {
        "security_id": str(INDUSTRIAL_FII_SECURITY_ID),
        "issuer_id": str(INDUSTRIAL_FII_ISSUER_ID),
        "issuer": "富士康工业互联网股份有限公司",
        "symbol": "601138",
        "exchange_mic": "XSHG",
        "exchange": "XSHG",
    }
    expected_source_checksum = stable_checksum(
        {
            "source_record_type": "SECURITY_MASTER_IDENTITY_V1",
            "projection": expected_payload,
        }
    )

    assert observation.invocation_id is None
    assert observation.payload == expected_payload
    assert observation.output_checksum == stable_checksum(expected_payload)
    assert identity.observation_id == observation.id
    assert identity.status == "VALID"
    assert identity.security_id == package.security_id == INDUSTRIAL_FII_SECURITY_ID
    assert identity.payload == expected_payload
    assert identity.source_record_type == "SECURITY_MASTER_IDENTITY_V1"
    assert identity.source_record_id == INDUSTRIAL_FII_SECURITY_ID
    assert identity.source_checksum == expected_source_checksum
    assert str(identity.id) in package.evidence_ids


def test_identity_evidence_flows_through_existing_claim_and_package_pipeline(
    migrated_engine: Engine,
) -> None:
    """RED-015: generic Claim and Package wiring consume valid identity Evidence."""
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    result = research_application_factory().run(
        SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )
    run_id = UUID(str(result["run_id"]))
    package_id = UUID(str(result["package_id"]))
    with migrated_engine.connect() as connection:
        claims = connection.execute(
            text(
                "SELECT id, lifecycle_status, support_status FROM research_claims "
                "WHERE research_agent_run_id = :run_id AND claim_type = 'IDENTITY'"
            ),
            {"run_id": run_id},
        ).all()
        identity_links = connection.execute(
            text(
                "SELECT l.claim_id, l.evidence_id FROM claim_evidence_links l "
                "JOIN research_claims c ON c.id = l.claim_id "
                "JOIN research_evidence e ON e.id = l.evidence_id "
                "WHERE c.research_agent_run_id = :run_id AND c.claim_type = 'IDENTITY' "
                "AND e.evidence_type = 'SECURITY_MASTER_EVIDENCE'"
            ),
            {"run_id": run_id},
        ).all()
        package = connection.execute(
            text("SELECT evidence_ids, sections FROM research_packages WHERE id = :id"),
            {"id": package_id},
        ).one()

    assert len(claims) == 1
    assert claims[0].lifecycle_status == "VALIDATED"
    assert claims[0].support_status == "SUPPORTED"
    assert len(identity_links) == 1
    assert str(identity_links[0].evidence_id) in package.evidence_ids
    packaged_claim_ids = {
        claim_id for section in package.sections for claim_id in section["claim_ids"]
    }
    assert str(claims[0].id) in packaged_claim_ids


def test_replaying_production_run_does_not_duplicate_identity_artifacts(
    migrated_engine: Engine,
) -> None:
    """RED-027: retry/reuse preserves one canonical component identity artifact."""
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    first = research_application_factory().run(
        SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )
    second = research_application_factory().run(
        SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )
    run_ids = (UUID(str(first["run_id"])), UUID(str(second["run_id"])))

    with migrated_engine.connect() as connection:
        observation_counts = connection.execute(
            text(
                "SELECT research_agent_run_id, count(*) FROM research_observations "
                "WHERE research_agent_run_id = ANY(:run_ids) "
                "AND observation_type = 'SECURITY_IDENTITY' "
                "GROUP BY research_agent_run_id"
            ),
            {"run_ids": list(run_ids)},
        ).all()
        evidence_counts = connection.execute(
            text(
                "SELECT research_agent_run_id, count(*) FROM research_evidence "
                "WHERE research_agent_run_id = ANY(:run_ids) "
                "AND evidence_type = 'SECURITY_MASTER_EVIDENCE' "
                "GROUP BY research_agent_run_id"
            ),
            {"run_ids": list(run_ids)},
        ).all()
        identity_payloads = connection.execute(
            text(
                "SELECT payload, output_checksum FROM research_observations "
                "WHERE research_agent_run_id = ANY(:run_ids) "
                "AND observation_type = 'SECURITY_IDENTITY' "
                "ORDER BY research_agent_run_id"
            ),
            {"run_ids": list(run_ids)},
        ).all()
        source_checksums = connection.scalars(
            text(
                "SELECT source_checksum FROM research_evidence "
                "WHERE research_agent_run_id = ANY(:run_ids) "
                "AND evidence_type = 'SECURITY_MASTER_EVIDENCE' "
                "ORDER BY research_agent_run_id"
            ),
            {"run_ids": list(run_ids)},
        ).all()

    assert {row.research_agent_run_id: row.count for row in observation_counts} == {
        run_id: 1 for run_id in run_ids
    }
    assert {row.research_agent_run_id: row.count for row in evidence_counts} == {
        run_id: 1 for run_id in run_ids
    }
    assert identity_payloads[0] == identity_payloads[1]
    assert len(set(source_checksums)) == 1


def test_partial_snapshot_production_offline_e2e_is_auditable_and_nonpublishable(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()
        session.commit()

    research = research_application_factory().run(
        PARTIAL_SNAPSHOT_ID,
        ResearchType.FULL_RESEARCH_PACKAGE.value,
        "controlled-offline-v1",
        AS_OF,
    )

    assert research["tool_invocation_count"] > 0
    package_id = UUID(str(research["package_id"]))
    with migrated_engine.connect() as connection:
        package_status = connection.scalar(
            text("SELECT status FROM research_packages WHERE id = :id"),
            {"id": package_id},
        )
        evidence_count = connection.scalar(text("SELECT count(*) FROM research_evidence"))
        unsupported_supported_claims = connection.scalar(
            text(
                "SELECT count(*) FROM research_claims c "
                "WHERE c.support_status = 'SUPPORTED' "
                "AND NOT EXISTS (SELECT 1 FROM claim_evidence_links l WHERE l.claim_id = c.id)"
            )
        )
    assert package_status in {"PARTIAL", "BLOCKED"}
    assert evidence_count > 0
    assert unsupported_supported_claims == 0

    reports = create_report_cli_application()
    reports.invoke("policy-seed-v1")
    reports.invoke("reflection-policy-seed-v1")
    reports.invoke("template-seed-v1")
    generated = reports.invoke(
        "generate",
        GenerateReportCommand(
            research_package_id=package_id,
            report_type=ReportType.DATA_QUALITY_REPORT,
            report_locale=ReportLocale.ZH_CN,
        ),
    )
    assert isinstance(generated, dict)
    assert generated["status"] in {"PARTIAL", "BLOCKED"}
    report_id = UUID(str(generated["report_id"]))

    round_one = reports.invoke(
        "reflect",
        ReflectReportCommand(report_id=report_id, round_number=1),
    )
    assert isinstance(round_one, dict)
    round_one_run = round_one["run"]
    assert isinstance(round_one_run, dict)
    round_one_id = UUID(str(round_one_run["id"]))
    revision_run_id = None
    target_report_id = report_id
    if int(round_one_run["total_finding_count"]) > 0:
        revision = reports.invoke(
            "revise",
            ReviseReportCommand(
                report_id=report_id,
                reflection_run_id=round_one_id,
            ),
        )
        assert isinstance(revision, dict)
        revision_run = revision["run"]
        assert isinstance(revision_run, dict)
        revision_run_id = UUID(str(revision_run["id"]))
        if revision_run["target_report_id"] is not None:
            target_report_id = UUID(str(revision_run["target_report_id"]))

    round_two = reports.invoke(
        "reflect",
        ReflectReportCommand(
            report_id=target_report_id,
            round_number=2,
            prior_reflection_run_id=round_one_id,
            revision_run_id=revision_run_id,
        ),
    )
    assert isinstance(round_two, dict)
    round_two_run = round_two["run"]
    assert isinstance(round_two_run, dict)
    gate = reports.invoke(
        "release-check",
        ReleaseCheckCommand(
            report_id=target_report_id,
            reflection_run_id=UUID(str(round_two_run["id"])),
        ),
    )
    assert isinstance(gate, dict)
    decision = gate["decision"]
    assert isinstance(decision, dict)
    assert decision["internal_release_status"] in {"PARTIAL", "BLOCKED"}


def _run(request_id: UUID, run_id: UUID, key: str = "c") -> ResearchRunWrite:
    return ResearchRunWrite(
        id=run_id,
        request_id=request_id,
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        status=ResearchRunStatus.CREATED,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        tool_catalog_checksum="a" * 64,
        idempotency_key=key * 64,
        budget=_budget(),
        created_at=AS_OF,
        updated_at=AS_OF,
    )


def _assert_component_observation_schema(engine: Engine, contract: str) -> None:
    columns = {
        column["name"]: column for column in inspect(engine).get_columns("research_observations")
    }
    assert columns["invocation_id"]["nullable"] is True, (
        f"{contract}: component Observation is blocked by invocation_id NOT NULL"
    )
    assert "research_step_id" in columns, (
        f"{contract}: research_observations.research_step_id is missing"
    )
    assert columns["research_step_id"]["nullable"] is False


def _lineage_definitions() -> tuple[ResearchStepDefinition, ...]:
    return (
        ResearchStepDefinition(
            step_index=0,
            step_key="resolve_security",
            step_type=ResearchStepType.RESOLVE_SECURITY,
            title="Resolve security",
            required=True,
            component_name="security-resolution-v1",
        ),
        ResearchStepDefinition(
            step_index=1,
            step_key="get_data_snapshot",
            step_type=ResearchStepType.LOAD_SNAPSHOT,
            title="Get data snapshot",
            required=True,
            dependency_keys=("resolve_security",),
            tool_name="get_data_snapshot",
            tool_version="1.0.0",
        ),
        ResearchStepDefinition(
            step_index=2,
            step_key="list_snapshot_items",
            step_type=ResearchStepType.QUERY_STRUCTURED_DATA,
            title="List snapshot items",
            required=True,
            dependency_keys=("get_data_snapshot",),
            tool_name="list_snapshot_items",
            tool_version="1.0.0",
        ),
    )


def _persist_lineage_graphs(
    session: Session,
    *,
    snapshot_id: UUID = SNAPSHOT_ID,
    count: int = 1,
) -> tuple[dict[str, UUID], ...]:
    repository = SqlAlchemyResearchAgentRepository(session)
    policy = build_controlled_offline_policy()
    repository.add_policy(ResearchPolicyWrite.model_validate(policy.model_dump(mode="python")))
    definitions = _lineage_definitions()
    graphs: list[dict[str, UUID]] = []
    for index in range(count):
        request_id, run_id, plan_id = (uuid4() for _ in range(3))
        component_step_id, first_tool_step_id, second_tool_step_id = (uuid4() for _ in range(3))
        first_invocation_id, second_invocation_id = (uuid4() for _ in range(2))
        request = _request(policy.version, request_id).model_copy(
            update={
                "snapshot_id": snapshot_id,
                "request_checksum": f"{index + 3:x}" * 64,
            }
        )
        repository.add_request(request)
        run = _run(request_id, run_id, f"{index + 5:x}").model_copy(
            update={"snapshot_id": snapshot_id}
        )
        repository.create_run(run)
        repository.add_plan(
            ResearchPlanWrite(
                id=plan_id,
                run_id=run_id,
                planner_version="deterministic-template-v1",
                plan_version="research-plan-v1",
                tool_catalog_version=CATALOG_VERSION,
                steps=definitions,
                plan_checksum=f"{index + 7:x}" * 64,
                created_at=AS_OF,
            )
        )
        repository.add_steps(
            tuple(
                ResearchStepWrite(
                    id=step_id,
                    run_id=run_id,
                    plan_id=plan_id,
                    definition=definition,
                    status=ResearchStepStatus.RUNNING,
                    created_at=AS_OF,
                )
                for step_id, definition in zip(
                    (component_step_id, first_tool_step_id, second_tool_step_id),
                    definitions,
                    strict=True,
                )
            )
        )
        for invocation_id, step_id, tool_name in (
            (first_invocation_id, first_tool_step_id, "get_data_snapshot"),
            (second_invocation_id, second_tool_step_id, "list_snapshot_items"),
        ):
            repository.add_invocation(
                ResearchToolInvocationWrite(
                    id=invocation_id,
                    run_id=run_id,
                    step_id=step_id,
                    attempt_number=1,
                    tool_name=tool_name,
                    tool_version="1.0.0",
                    status=ToolInvocationStatus.RUNNING,
                    redacted_input={},
                    input_checksum="e" * 64,
                    started_at=AS_OF,
                )
            )
        graphs.append(
            {
                "request_id": request_id,
                "run_id": run_id,
                "component_step_id": component_step_id,
                "first_tool_step_id": first_tool_step_id,
                "second_tool_step_id": second_tool_step_id,
                "first_invocation_id": first_invocation_id,
                "second_invocation_id": second_invocation_id,
            }
        )
    return tuple(graphs)


def _insert_lineage_observation(
    session: Session,
    *,
    run_id: UUID,
    step_id: UUID,
    invocation_id: UUID | None,
    security_id: UUID = INDUSTRIAL_FII_SECURITY_ID,
    snapshot_id: UUID = SNAPSHOT_ID,
    observation_id: UUID | None = None,
) -> UUID:
    resolved_id = observation_id or uuid4()
    session.execute(
        text(
            "INSERT INTO research_observations "
            "(id, research_agent_run_id, research_step_id, invocation_id, observation_type, "
            "status, schema_version, payload, output_checksum, security_id, snapshot_id, "
            "research_as_of_time, synthetic_status, warnings, created_at) VALUES "
            "(:id, :run_id, :step_id, :invocation_id, 'SECURITY_IDENTITY', 'PASS', "
            "'research-observation-v1', CAST(:payload AS jsonb), :checksum, :security_id, "
            ":snapshot_id, :as_of, 'REAL_VERIFIED', CAST('[]' AS jsonb), :created_at)"
        ),
        {
            "id": resolved_id,
            "run_id": run_id,
            "step_id": step_id,
            "invocation_id": invocation_id,
            "payload": '{"security_id":"40000000-0000-0000-0000-000000000001"}',
            "checksum": "f" * 64,
            "security_id": security_id,
            "snapshot_id": snapshot_id,
            "as_of": AS_OF,
            "created_at": AS_OF,
        },
    )
    session.flush()
    return resolved_id


def _insert_0010_tool_observation(
    session: Session,
    *,
    run_id: UUID,
    invocation_id: UUID,
    observation_id: UUID,
) -> None:
    session.execute(
        text(
            "INSERT INTO research_observations "
            "(id, research_agent_run_id, invocation_id, observation_type, status, "
            "schema_version, payload, output_checksum, security_id, snapshot_id, "
            "research_as_of_time, synthetic_status, warnings, created_at) VALUES "
            "(:id, :run_id, :invocation_id, 'SECURITY_IDENTITY', 'PASS', "
            "'research-observation-v1', CAST(:payload AS jsonb), :checksum, :security_id, "
            ":snapshot_id, :as_of, 'REAL_VERIFIED', CAST('[]' AS jsonb), :created_at)"
        ),
        {
            "id": observation_id,
            "run_id": run_id,
            "invocation_id": invocation_id,
            "payload": '{"security_id":"40000000-0000-0000-0000-000000000001"}',
            "checksum": "f" * 64,
            "security_id": INDUSTRIAL_FII_SECURITY_ID,
            "snapshot_id": SNAPSHOT_ID,
            "as_of": AS_OF,
            "created_at": AS_OF,
        },
    )


def test_postgres_persists_component_observation_without_fake_invocation(
    migrated_engine: Engine,
) -> None:
    """RED-017: a persisted component Step is the Observation execution parent."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "RED-017")

        observation = ResearchObservationWrite(
            id=uuid4(),
            run_id=graph["run_id"],
            research_step_id=graph["component_step_id"],
            invocation_id=None,
            observation_type=ObservationType.SECURITY_IDENTITY,
            status=ObservationStatus.PASS,
            schema_version="research-observation-v1",
            payload={"security_id": str(INDUSTRIAL_FII_SECURITY_ID)},
            output_checksum="f" * 64,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            snapshot_id=SNAPSHOT_ID,
            research_as_of_time=AS_OF,
            synthetic_status=SyntheticStatus.REAL_VERIFIED,
            created_at=AS_OF,
        )
        stored = SqlAlchemyResearchAgentRepository(session).add_observation(observation)
        row = session.execute(
            text(
                "SELECT research_step_id, invocation_id FROM research_observations WHERE id = :id"
            ),
            {"id": observation.id},
        ).one()

        assert stored.research_step_id == graph["component_step_id"]
        assert stored.invocation_id is None
        assert row.research_step_id == graph["component_step_id"]
        assert row.invocation_id is None


def test_component_observation_rejects_nonexistent_step(
    migrated_engine: Engine,
) -> None:
    """RED-018A: the mandatory Step FK rejects an orphan Observation."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "RED-018A")

        with pytest.raises(IntegrityError, match="OBSERVATION_STEP_NOT_FOUND"):
            _insert_lineage_observation(
                session,
                run_id=graph["run_id"],
                step_id=uuid4(),
                invocation_id=None,
            )


def test_component_observation_rejects_tool_step_without_invocation(
    migrated_engine: Engine,
) -> None:
    """RED-018B: Tool Step plus NULL Invocation needs the Route A lineage trigger."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "RED-018B")

        with pytest.raises(IntegrityError, match="OBSERVATION_TOOL_INVOCATION_REQUIRED"):
            _insert_lineage_observation(
                session,
                run_id=graph["run_id"],
                step_id=graph["first_tool_step_id"],
                invocation_id=None,
            )


def test_observation_rejects_cross_run_step_and_invocation_lineage(
    migrated_engine: Engine,
) -> None:
    """RED-019: Step and Invocation lineage cannot cross Research Runs."""
    with Session(migrated_engine) as session:
        first, second = _persist_lineage_graphs(session, count=2)
        _assert_component_observation_schema(migrated_engine, "RED-019")

        with pytest.raises(IntegrityError, match="OBSERVATION_STEP_RUN_MISMATCH"):
            with session.begin_nested():
                _insert_lineage_observation(
                    session,
                    run_id=first["run_id"],
                    step_id=second["component_step_id"],
                    invocation_id=None,
                )
        with pytest.raises(IntegrityError, match="OBSERVATION_INVOCATION_RUN_MISMATCH"):
            with session.begin_nested():
                _insert_lineage_observation(
                    session,
                    run_id=first["run_id"],
                    step_id=first["first_tool_step_id"],
                    invocation_id=second["first_invocation_id"],
                )


def test_tool_observation_requires_matching_step_invocation_and_run(
    migrated_engine: Engine,
) -> None:
    """RED-020: Route A preserves and strengthens real Tool Observation lineage."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "RED-020")

        observation_id = _insert_lineage_observation(
            session,
            run_id=graph["run_id"],
            step_id=graph["first_tool_step_id"],
            invocation_id=graph["first_invocation_id"],
        )
        assert (
            session.scalar(
                text("SELECT invocation_id FROM research_observations WHERE id = :id"),
                {"id": observation_id},
            )
            == graph["first_invocation_id"]
        )

        with pytest.raises(IntegrityError, match="OBSERVATION_INVOCATION_STEP_MISMATCH"):
            with session.begin_nested():
                _insert_lineage_observation(
                    session,
                    run_id=graph["run_id"],
                    step_id=graph["second_tool_step_id"],
                    invocation_id=graph["first_invocation_id"],
                )
        with pytest.raises(IntegrityError, match="OBSERVATION_TOOL_INVOCATION_REQUIRED"):
            with session.begin_nested():
                _insert_lineage_observation(
                    session,
                    run_id=graph["run_id"],
                    step_id=graph["second_tool_step_id"],
                    invocation_id=None,
                )


def test_component_observation_cannot_bind_tool_invocation(
    migrated_engine: Engine,
) -> None:
    """RED-021: a component Step cannot fake Tool lineage."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "RED-021")

        with pytest.raises(IntegrityError, match="OBSERVATION_COMPONENT_INVOCATION_FORBIDDEN"):
            with session.begin_nested():
                _insert_lineage_observation(
                    session,
                    run_id=graph["run_id"],
                    step_id=graph["component_step_id"],
                    invocation_id=graph["first_invocation_id"],
                )


def test_observation_rejects_security_different_from_frozen_run(
    migrated_engine: Engine,
) -> None:
    """RED-024: Observation security must equal the Run frozen security."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]

        with pytest.raises(IntegrityError, match="OBSERVATION_SECURITY_MISMATCH"):
            _insert_lineage_observation(
                session,
                run_id=graph["run_id"],
                step_id=graph["component_step_id"],
                invocation_id=None,
                security_id=MICRON_SECURITY_ID,
            )


def test_observation_rejects_snapshot_different_from_frozen_run(
    migrated_engine: Engine,
) -> None:
    """RED-025: Observation snapshot must equal the Run frozen snapshot."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]

        with pytest.raises(IntegrityError, match="OBSERVATION_SNAPSHOT_MISMATCH"):
            _insert_lineage_observation(
                session,
                run_id=graph["run_id"],
                step_id=graph["component_step_id"],
                invocation_id=None,
                snapshot_id=PARTIAL_SNAPSHOT_ID,
            )


def test_tool_and_component_observation_origins_are_independently_unique(
    migrated_engine: Engine,
) -> None:
    """RED-022: one Observation per Invocation and per component Step."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "RED-022")

        _insert_lineage_observation(
            session,
            run_id=graph["run_id"],
            step_id=graph["first_tool_step_id"],
            invocation_id=graph["first_invocation_id"],
        )
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                _insert_lineage_observation(
                    session,
                    run_id=graph["run_id"],
                    step_id=graph["first_tool_step_id"],
                    invocation_id=graph["first_invocation_id"],
                )

        _insert_lineage_observation(
            session,
            run_id=graph["run_id"],
            step_id=graph["component_step_id"],
            invocation_id=None,
        )
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                _insert_lineage_observation(
                    session,
                    run_id=graph["run_id"],
                    step_id=graph["component_step_id"],
                    invocation_id=None,
                )


def test_evidence_fk_accepts_component_originated_observation(
    migrated_engine: Engine,
) -> None:
    """RED-023: Evidence continues to reference the unified Observation table."""
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "RED-023")
        observation_id = _insert_lineage_observation(
            session,
            run_id=graph["run_id"],
            step_id=graph["component_step_id"],
            invocation_id=None,
        )

        evidence = ResearchEvidenceWrite(
            id=uuid4(),
            run_id=graph["run_id"],
            observation_id=observation_id,
            evidence_type=EvidenceType.SECURITY_MASTER_EVIDENCE,
            status=EvidenceStatus.BLOCKED,
            schema_version="research-evidence-v1",
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            snapshot_id=SNAPSHOT_ID,
            research_as_of_time=AS_OF,
            synthetic_status=SyntheticStatus.REAL_VERIFIED,
            payload={},
            warning_codes=("IDENTITY_SOURCE_NOT_ADMITTED",),
            created_at=AS_OF,
        )
        stored = SqlAlchemyResearchAgentRepository(session).add_evidence((evidence,))[0]

        assert stored.observation_id == observation_id


def test_tool_and_component_observations_remain_database_immutable(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _assert_component_observation_schema(migrated_engine, "IMMUTABLE-CONTRACT")
        observation_ids = (
            _insert_lineage_observation(
                session,
                run_id=graph["run_id"],
                step_id=graph["first_tool_step_id"],
                invocation_id=graph["first_invocation_id"],
            ),
            _insert_lineage_observation(
                session,
                run_id=graph["run_id"],
                step_id=graph["component_step_id"],
                invocation_id=None,
            ),
        )
        for observation_id in observation_ids:
            with pytest.raises(DatabaseError, match="immutable"):
                with session.begin_nested():
                    session.execute(
                        text(
                            "UPDATE research_observations SET payload = CAST('{}' AS jsonb) "
                            "WHERE id = :id"
                        ),
                        {"id": observation_id},
                    )
            with pytest.raises(DatabaseError, match="immutable"):
                with session.begin_nested():
                    session.execute(
                        text("DELETE FROM research_observations WHERE id = :id"),
                        {"id": observation_id},
                    )


@pytest.mark.parametrize(
    ("snapshot_id", "expected_snapshot_status"),
    (
        (SNAPSHOT_ID, "COMPLETE"),
        (PARTIAL_SNAPSHOT_ID, "PARTIAL"),
    ),
)
def test_component_observation_lineage_is_independent_of_snapshot_status(
    migrated_engine: Engine,
    snapshot_id: UUID,
    expected_snapshot_status: str,
) -> None:
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session, snapshot_id=snapshot_id)[0]
        _assert_component_observation_schema(migrated_engine, "SNAPSHOT-STATUS-INDEPENDENCE")
        _insert_lineage_observation(
            session,
            run_id=graph["run_id"],
            step_id=graph["component_step_id"],
            invocation_id=None,
            snapshot_id=snapshot_id,
        )

        assert (
            session.scalar(
                text("SELECT status FROM data_snapshots WHERE id = :id"),
                {"id": snapshot_id},
            )
            == expected_snapshot_status
        )
        assert (
            session.scalar(
                text("SELECT status FROM research_agent_runs WHERE id = :id"),
                {"id": graph["run_id"]},
            )
            == ResearchRunStatus.CREATED.value
        )


def test_0011_backfills_tool_observation_step_and_preserves_evidence_fk(
    migrated_engine: Engine,
) -> None:
    """Historical RED: 0010 Tool lineage and Evidence identity survive the upgrade."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.downgrade(config, "0010_partial_request")
    observation_id, evidence_id = uuid4(), uuid4()
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        _insert_0010_tool_observation(
            session,
            run_id=graph["run_id"],
            invocation_id=graph["first_invocation_id"],
            observation_id=observation_id,
        )
        SqlAlchemyResearchAgentRepository(session).add_evidence(
            (
                ResearchEvidenceWrite(
                    id=evidence_id,
                    run_id=graph["run_id"],
                    observation_id=observation_id,
                    evidence_type=EvidenceType.SECURITY_MASTER_EVIDENCE,
                    status=EvidenceStatus.BLOCKED,
                    schema_version="research-evidence-v1",
                    security_id=INDUSTRIAL_FII_SECURITY_ID,
                    snapshot_id=SNAPSHOT_ID,
                    research_as_of_time=AS_OF,
                    synthetic_status=SyntheticStatus.REAL_VERIFIED,
                    payload={},
                    warning_codes=("HISTORICAL_LINEAGE_FIXTURE",),
                    created_at=AS_OF,
                ),
            )
        )
        session.commit()

    with migrated_engine.connect() as connection:
        observation_before = connection.execute(
            text(
                "SELECT id, invocation_id, payload, output_checksum "
                "FROM research_observations WHERE id = :id"
            ),
            {"id": observation_id},
        ).one()
        evidence_before = connection.execute(
            text(
                "SELECT id, observation_id, payload, source_checksum "
                "FROM research_evidence WHERE id = :id"
            ),
            {"id": evidence_id},
        ).one()

    command.upgrade(config, COMPONENT_LINEAGE_REVISION)
    with migrated_engine.connect() as connection:
        observation = connection.execute(
            text(
                "SELECT id, research_step_id, invocation_id, payload, output_checksum "
                "FROM research_observations WHERE id = :id"
            ),
            {"id": observation_id},
        ).one()
        evidence_after = connection.execute(
            text(
                "SELECT id, observation_id, payload, source_checksum "
                "FROM research_evidence WHERE id = :id"
            ),
            {"id": evidence_id},
        ).one()

    assert observation.research_step_id == graph["first_tool_step_id"]
    assert (
        observation.id,
        observation.invocation_id,
        observation.payload,
        observation.output_checksum,
    ) == observation_before
    assert evidence_after == evidence_before

    command.upgrade(config, COMPONENT_LINEAGE_INTEGRITY_REVISION)
    with migrated_engine.connect() as connection:
        observation_after_integrity = connection.execute(
            text(
                "SELECT id, research_step_id, invocation_id, payload, output_checksum "
                "FROM research_observations WHERE id = :id"
            ),
            {"id": observation_id},
        ).one()
        evidence_after_integrity = connection.execute(
            text(
                "SELECT id, observation_id, payload, source_checksum "
                "FROM research_evidence WHERE id = :id"
            ),
            {"id": evidence_id},
        ).one()
        observation_count = connection.scalar(
            text("SELECT count(*) FROM research_observations WHERE id = :id"),
            {"id": observation_id},
        )
        evidence_count = connection.scalar(
            text("SELECT count(*) FROM research_evidence WHERE id = :id"),
            {"id": evidence_id},
        )

    assert observation_after_integrity == observation
    assert evidence_after_integrity == evidence_before
    assert observation_count == 1
    assert evidence_count == 1


def test_0011_downgrade_rejects_existing_component_observation_without_data_loss(
    migrated_engine: Engine,
) -> None:
    """Downgrade RED: component audit history cannot be deleted or assigned a fake Invocation."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, COMPONENT_LINEAGE_REVISION)
    with Session(migrated_engine) as session:
        graph = _persist_lineage_graphs(session)[0]
        observation_id = _insert_lineage_observation(
            session,
            run_id=graph["run_id"],
            step_id=graph["component_step_id"],
            invocation_id=None,
        )
        session.commit()

    with migrated_engine.connect() as connection:
        version_before_downgrade = connection.scalar(
            text("SELECT version_num FROM alembic_version")
        )

    with pytest.raises(RuntimeError, match="COMPONENT_OBSERVATIONS_PREVENT_DOWNGRADE"):
        command.downgrade(config, "0010_partial_request")

    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            version_before_downgrade
        )
        retained = connection.execute(
            text(
                "SELECT research_step_id, invocation_id FROM research_observations WHERE id = :id"
            ),
            {"id": observation_id},
        ).one()
    assert retained.research_step_id == graph["component_step_id"]
    assert retained.invocation_id is None


def test_repository_persists_full_audit_graph_without_committing(
    migrated_engine: Engine,
) -> None:
    request_id, run_id, plan_id, step_id, invocation_id = (uuid4() for _ in range(5))
    observation_id, evidence_id, claim_id, link_id, event_id = (uuid4() for _ in range(5))
    policy = build_controlled_offline_policy()

    with Session(migrated_engine) as session:
        repository = SqlAlchemyResearchAgentRepository(session)
        added_policy = repository.add_policy(
            ResearchPolicyWrite.model_validate(policy.model_dump(mode="python"))
        )
        assert added_policy == policy
        assert repository.get_policy(policy.version) == policy
        assert repository.add_request(_request(policy.version, request_id)).security_query == (
            "601138.SH"
        )
        created = repository.create_run(_run(request_id, run_id))
        assert created.status is ResearchRunStatus.CREATED
        assert repository.get_run(run_id, for_update=True) == created
        assert repository.find_reusable_run("c" * 64) == created

        plan = ResearchPlanWrite(
            id=plan_id,
            run_id=run_id,
            planner_version="deterministic-template-v1",
            plan_version="research-plan-v1",
            tool_catalog_version=CATALOG_VERSION,
            steps=(
                ResearchStepDefinition(
                    step_index=0,
                    step_key="get_data_snapshot",
                    step_type=ResearchStepType.LOAD_SNAPSHOT,
                    title="Get data snapshot",
                    required=True,
                    tool_name="get_data_snapshot",
                    tool_version="1.0.0",
                ),
            ),
            plan_checksum="d" * 64,
            created_at=AS_OF,
        )
        assert repository.add_plan(plan).model_dump() == plan.model_dump()
        step = ResearchStepWrite(
            id=step_id,
            run_id=run_id,
            plan_id=plan_id,
            definition=plan.steps[0],
            status=ResearchStepStatus.RUNNING,
            created_at=AS_OF,
        )
        assert repository.add_steps((step,))[0].definition == step.definition
        stored_plan = repository.get_plan(run_id)
        assert stored_plan is not None
        assert stored_plan.model_dump() == plan.model_dump()
        assert repository.list_steps(plan_id)[0].id == step_id

        invocation = ResearchToolInvocationWrite(
            id=invocation_id,
            run_id=run_id,
            step_id=step_id,
            attempt_number=1,
            tool_name="get_data_snapshot",
            tool_version="1.0.0",
            status=ToolInvocationStatus.RUNNING,
            redacted_input={"snapshot_id": str(SNAPSHOT_ID)},
            input_checksum="e" * 64,
            started_at=AS_OF,
        )
        assert repository.add_invocation(invocation).status is ToolInvocationStatus.RUNNING
        completed = repository.complete_invocation(
            invocation_id,
            ResearchToolInvocationCompletion(
                status=ToolInvocationStatus.PASS,
                output_checksum="f" * 64,
                completed_at=AS_OF,
            ),
        )
        assert completed.status is ToolInvocationStatus.PASS

        observation = ResearchObservationWrite(
            id=observation_id,
            run_id=run_id,
            research_step_id=step_id,
            invocation_id=invocation_id,
            observation_type=ObservationType.SECURITY_IDENTITY,
            status=ObservationStatus.PASS,
            schema_version="observation-v1",
            payload={"security_id": str(INDUSTRIAL_FII_SECURITY_ID)},
            output_checksum="f" * 64,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            snapshot_id=SNAPSHOT_ID,
            research_as_of_time=AS_OF,
            synthetic_status=SyntheticStatus.REAL_VERIFIED,
            created_at=AS_OF,
        )
        assert repository.add_observation(observation).model_dump() == observation.model_dump()
        evidence = ResearchEvidenceWrite(
            id=evidence_id,
            run_id=run_id,
            observation_id=observation_id,
            evidence_type=EvidenceType.SECURITY_MASTER_EVIDENCE,
            status=EvidenceStatus.VALID,
            schema_version="evidence-v1",
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            snapshot_id=SNAPSHOT_ID,
            research_as_of_time=AS_OF,
            source_record_type="securities",
            source_record_id=INDUSTRIAL_FII_SECURITY_ID,
            source_checksum="1" * 64,
            published_at=AS_OF,
            synthetic_status=SyntheticStatus.REAL_VERIFIED,
            payload={
                "security_id": str(INDUSTRIAL_FII_SECURITY_ID),
                "issuer": "富士康工业互联网股份有限公司",
                "symbol": "601138",
                "exchange": "XSHG",
            },
            created_at=AS_OF,
        )
        assert repository.add_evidence((evidence,))[0].model_dump() == evidence.model_dump()
        assert repository.list_evidence(run_id)[0].model_dump() == evidence.model_dump()

        claim = ResearchClaimWrite(
            id=claim_id,
            run_id=run_id,
            claim_type=ClaimType.IDENTITY,
            lifecycle_status=ClaimLifecycleStatus.CANDIDATE,
            support_status=None,
            statement_code="SECURITY_IDENTITY",
            builder_version="deterministic-claim-builder-v1",
            created_at=AS_OF,
        )
        assert repository.add_claim(claim).model_dump() == claim.model_dump()
        validated = repository.complete_claim(
            claim_id,
            ResearchClaimCompletion(
                lifecycle_status=ClaimLifecycleStatus.VALIDATED,
                support_status=ClaimSupportStatus.SUPPORTED,
                validator_version="claim-support-validator-v1",
                completed_at=AS_OF,
            ),
        )
        assert validated.support_status is ClaimSupportStatus.SUPPORTED
        link = ClaimEvidenceLinkWrite(
            id=link_id,
            run_id=run_id,
            claim_id=claim_id,
            evidence_id=evidence_id,
            role=EvidenceRole.PRIMARY,
            created_at=AS_OF,
        )
        assert repository.add_links((link,))[0].model_dump() == link.model_dump()

        package = repository.add_package(
            ResearchPackageWrite(
                run_id=run_id,
                request_id=request_id,
                security_id=INDUSTRIAL_FII_SECURITY_ID,
                snapshot_id=SNAPSHOT_ID,
                research_as_of_time=AS_OF,
                research_type=ResearchType.COMPANY_OVERVIEW,
                policy_version=policy.version,
                planner_version="deterministic-template-v1",
                tool_catalog_version=CATALOG_VERSION,
                evidence_version="evidence-v1",
                claim_version="claim-v1",
                package_version="package-v1",
                status=ResearchPackageStatus.PARTIAL,
                sections=(
                    ResearchPackageSection(
                        section=ResearchSection.SECURITY_IDENTITY,
                        status=PackageSectionStatus.PASS,
                        claim_ids=(claim_id,),
                    ),
                ),
                evidence_ids=(evidence_id,),
                unsupported_claim_ids=(),
                conflicting_claim_ids=(),
                blocked_capabilities=("DOCUMENT_EVIDENCE_BLOCKED",),
                warnings=("REAL_DISCLOSURE_BODY_UNAVAILABLE",),
                checksum="2" * 64,
            )
        )
        assert package.run_id == run_id
        event = ResearchRunEventWrite(
            id=event_id,
            run_id=run_id,
            sequence_number=1,
            event_type=ResearchRunEventType.RUN_CREATED,
            safe_detail={"source": "integration-test"},
            created_at=AS_OF,
        )
        assert repository.append_event(event).model_dump() == event.model_dump()

        repository.update_run(
            run_id,
            ResearchRunUpdate(
                expected_status=ResearchRunStatus.CREATED,
                target_status=ResearchRunStatus.PLANNING,
                budget=_budget(),
                changed_at=AS_OF,
            ),
        )
        assert session.in_transaction()
        session.rollback()

    with Session(migrated_engine) as verification:
        assert (
            verification.scalar(
                select(ResearchPolicy).where(ResearchPolicy.version == policy.version)
            )
            is None
        )


def test_database_rejects_duplicate_and_cross_run_children(
    migrated_engine: Engine,
) -> None:
    policy = build_controlled_offline_policy()
    request_id, first_run_id, second_run_id, plan_id, step_id = (uuid4() for _ in range(5))
    with Session(migrated_engine) as session:
        repository = SqlAlchemyResearchAgentRepository(session)
        repository.add_policy(ResearchPolicyWrite.model_validate(policy.model_dump(mode="python")))
        repository.add_request(_request(policy.version, request_id))
        repository.create_run(_run(request_id, first_run_id, "3"))
        repository.create_run(_run(request_id, second_run_id, "4"))
        definition = ResearchStepDefinition(
            step_index=0,
            step_key="identity",
            step_type=ResearchStepType.RESOLVE_SECURITY,
            title="Resolve security",
            required=True,
            component_name="deterministic-resolver",
        )
        repository.add_plan(
            ResearchPlanWrite(
                id=plan_id,
                run_id=first_run_id,
                planner_version="deterministic-template-v1",
                plan_version="research-plan-v1",
                tool_catalog_version=CATALOG_VERSION,
                steps=(definition,),
                plan_checksum="5" * 64,
                created_at=AS_OF,
            )
        )
        repository.add_steps(
            (
                ResearchStepWrite(
                    id=step_id,
                    run_id=first_run_id,
                    plan_id=plan_id,
                    definition=definition,
                    status=ResearchStepStatus.PENDING,
                    created_at=AS_OF,
                ),
            )
        )
        session.flush()

        with pytest.raises(IntegrityError):
            with session.begin_nested():
                repository.add_steps(
                    (
                        ResearchStepWrite(
                            id=uuid4(),
                            run_id=first_run_id,
                            plan_id=plan_id,
                            definition=definition,
                            status=ResearchStepStatus.PENDING,
                            created_at=AS_OF,
                        ),
                    )
                )

        with pytest.raises(IntegrityError):
            with session.begin_nested():
                repository.add_invocation(
                    ResearchToolInvocationWrite(
                        id=uuid4(),
                        run_id=second_run_id,
                        step_id=step_id,
                        attempt_number=1,
                        tool_name="get_data_snapshot",
                        tool_version="1.0.0",
                        status=ToolInvocationStatus.RUNNING,
                        redacted_input={},
                        input_checksum="6" * 64,
                        started_at=AS_OF,
                    )
                )

        assert session.scalar(
            select(ResearchPolicy).where(ResearchPolicy.version == policy.version)
        )
        session.rollback()
