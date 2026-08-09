from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.models.data_access import (
    DataProvider,
    DataSnapshot,
    SnapshotItem,
)
from stock_research_agent.db.models.research_agent import (
    ResearchAgentRun,
    ResearchPackage,
    ResearchPolicy,
    ResearchRequest,
)
from stock_research_agent.db.repositories.reports import (
    SqlAlchemyReportGenerationRepository,
    SqlAlchemyReportRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.reports.application import GenerateReportCommand
from stock_research_agent.domain.reports.checksums import (
    ReportChecksumContext,
    combined_report_checksum,
    markdown_checksum,
    structured_report_checksum,
)
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.generation import (
    ReportGenerationRunWrite,
    ReportGenerationStatus,
    ReportGenerationTransition,
)
from stock_research_agent.domain.reports.input_verification import (
    ReportInputValidationError,
)
from stock_research_agent.domain.reports.markdown import (
    MARKDOWN_RENDERER_VERSION,
    DeterministicMarkdownRenderer,
)
from stock_research_agent.domain.reports.policies import (
    REPORT_POLICY_VERSION,
    ReportPolicySeedService,
)
from stock_research_agent.domain.reports.queries import ReportQueryService
from stock_research_agent.domain.reports.references import ReportReferenceAllocator
from stock_research_agent.domain.reports.reflection_policy import (
    RUNTIME_REFLECTION_POLICY_VERSION,
    RuntimeReflectionPolicySeedService,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ReportSectionStatus,
    ResearchReportAggregateWrite,
    ResearchReportRecord,
    ResearchReportStatus,
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)
from stock_research_agent.domain.reports.schemas import (
    ReportInputManifest,
    ReportInputSectionState,
    ReportRequestRecord,
    ReportRequestWrite,
)
from stock_research_agent.domain.reports.templates import (
    ReportTemplateSeedService,
)
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    PackageSectionStatus,
    ResearchMode,
    ResearchPackageStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.packages import ResearchPackageAssembler
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    PageRequest,
    RequestedBudgets,
    ResearchRequestRecord,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_ISSUER_ID,
    INDUSTRIAL_FII_SECURITY_ID,
    SecurityMasterSeedService,
)
from stock_research_agent.report_cli_application import (
    SqlAlchemyReportCliApplication,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 13, tzinfo=UTC)
PROVIDER_ID = UUID("81000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("81000000-0000-4000-8000-000000000002")
SNAPSHOT_ITEM_ID = UUID("81000000-0000-4000-8000-00000000000a")
SOURCE_RECORD_ID = UUID("81000000-0000-4000-8000-00000000000b")
RESEARCH_REQUEST_ID = UUID("81000000-0000-4000-8000-000000000003")
RESEARCH_RUN_ID = UUID("81000000-0000-4000-8000-000000000004")
PACKAGE_ID = UUID("81000000-0000-4000-8000-000000000005")
REPORT_REQUEST_ID = UUID("81000000-0000-4000-8000-000000000006")
GENERATION_RUN_ID = UUID("81000000-0000-4000-8000-000000000007")
REPORT_ID = UUID("81000000-0000-4000-8000-000000000008")
CATALOG_VERSION = "tool-catalog-v1:" + "a" * 64


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").casefold() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments)


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 8 repository tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def report_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    _reset(engine)
    with Session(engine) as session:
        _seed_stage7_lineage(session)
        session.commit()
        yield session
        session.rollback()
    _reset(engine)
    engine.dispose()


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "TRUNCATE TABLE report_policies, research_policies, "
            "data_providers, data_snapshots CASCADE"
        )


def _seed_stage7_lineage(session: Session) -> None:
    SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
    session.add(
        DataProvider(
            id=PROVIDER_ID,
            code="STAGE8_TEST_FIXTURE",
            name="Stage 8 repository test fixture",
            provider_type="FIXTURE",
            status="APPROVED",
            base_url=None,
            documentation_url=None,
            terms_status="VERIFIED",
            capabilities=["SNAPSHOT"],
        )
    )
    snapshot = DataSnapshot(
        id=SNAPSHOT_ID,
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        research_as_of_time=AS_OF,
        snapshot_version=8101,
        status="BUILDING",
        completed_at=None,
        checksum=None,
        formula_version="raw-data-v1",
        notes="Stage 8 repository fixture",
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
            checksum_input="stage8-report-snapshot-item",
            checksum="7" * 64,
        )
    )
    session.flush()
    snapshot.status = "COMPLETE"
    snapshot.completed_at = AS_OF
    snapshot.checksum = "8" * 64
    session.flush()
    policy = build_controlled_offline_policy()
    session.add(
        ResearchPolicy(
            id=UUID("81000000-0000-4000-8000-000000000009"),
            version=policy.version,
            checksum=policy.checksum,
            definition=policy.model_dump(
                mode="json",
                exclude={"version", "checksum"},
            ),
            created_at=AS_OF,
        )
    )
    session.flush()
    request_values = {
        "security_query": "601138.SH",
        "resolved_security_id": INDUSTRIAL_FII_SECURITY_ID,
        "normalized_security_query": "601138.SH",
        "research_type": ResearchType.COMPANY_OVERVIEW,
        "research_mode": ResearchMode.REAL_RESEARCH,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": AS_OF,
        "requested_sections": (ResearchSection.DATA_QUALITY,),
        "requested_budgets": RequestedBudgets(),
        "policy_version": policy.version,
        "planner_version": "deterministic-template-v1",
        "tool_catalog_version": CATALOG_VERSION,
        "tool_catalog_checksum": "a" * 64,
    }
    request_record = ResearchRequestRecord.model_validate(
        {
            "id": RESEARCH_REQUEST_ID,
            **request_values,
            "request_checksum": stable_checksum(request_values),
            "created_at": AS_OF,
        }
    )
    session.add(
        ResearchRequest(
            id=request_record.id,
            security_id=request_record.resolved_security_id,
            snapshot_id=request_record.snapshot_id,
            security_query=request_record.security_query,
            normalized_security_query=request_record.normalized_security_query,
            research_type=request_record.research_type.value,
            research_mode=request_record.research_mode.value,
            research_as_of_time=request_record.research_as_of_time,
            requested_sections=[item.value for item in request_record.requested_sections],
            requested_budgets=request_record.requested_budgets.model_dump(mode="json"),
            policy_version=request_record.policy_version,
            planner_version=request_record.planner_version,
            tool_catalog_version=request_record.tool_catalog_version,
            tool_catalog_checksum=request_record.tool_catalog_checksum,
            request_checksum=request_record.request_checksum,
            created_at=request_record.created_at,
        )
    )
    session.flush()
    session.add(
        ResearchAgentRun(
            id=RESEARCH_RUN_ID,
            research_request_id=RESEARCH_REQUEST_ID,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            snapshot_id=SNAPSHOT_ID,
            research_as_of_time=AS_OF,
            research_type="COMPANY_OVERVIEW",
            status="PARTIAL",
            policy_version=policy.version,
            planner_version="deterministic-template-v1",
            tool_catalog_version=CATALOG_VERSION,
            tool_catalog_checksum="a" * 64,
            idempotency_key="c" * 64,
            budget={
                "max_steps": 12,
                "max_tool_calls": 24,
                "max_calls_per_tool": 5,
                "max_retries_per_step": 1,
                "max_duration_seconds": 120,
                "model_token_budget": 0,
                "consumed_steps": 0,
                "consumed_tool_calls": 0,
                "consumed_model_tokens": 0,
                "elapsed_seconds": "0",
            },
            warning_codes=["REAL_COMPANY_RESEARCH_INCOMPLETE"],
            terminal_reason_code="VERIFIED_EVIDENCE_INCOMPLETE",
            updated_at=AS_OF,
            terminal_at=AS_OF,
            created_at=AS_OF,
        )
    )
    session.flush()
    package = ResearchPackageAssembler().assemble(
        package_id=PACKAGE_ID,
        run_id=RESEARCH_RUN_ID,
        request_id=RESEARCH_REQUEST_ID,
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        research_type=ResearchType.COMPANY_OVERVIEW,
        policy_version=policy.version,
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        requested_sections=(ResearchSection.DATA_QUALITY,),
        claims=(),
        evidence=(),
        blocked_capabilities=("VERIFIED_COMPANY_BODY_UNAVAILABLE",),
        warnings=("REAL_COMPANY_RESEARCH_INCOMPLETE",),
        run_failed=False,
        created_at=AS_OF,
    )
    session.add(
        ResearchPackage(
            id=package.id,
            research_agent_run_id=package.run_id,
            request_id=package.request_id,
            security_id=package.security_id,
            snapshot_id=package.snapshot_id,
            research_as_of_time=package.research_as_of_time,
            research_type=package.research_type.value,
            policy_version=package.policy_version,
            planner_version=package.planner_version,
            tool_catalog_version=package.tool_catalog_version,
            evidence_version=package.evidence_version,
            claim_version=package.claim_version,
            package_version=package.package_version,
            status=package.status.value,
            sections=[item.model_dump(mode="json") for item in package.sections],
            evidence_ids=[],
            unsupported_claim_ids=[],
            conflicting_claim_ids=[],
            blocked_capabilities=list(package.blocked_capabilities),
            warnings=list(package.warnings),
            checksum=package.checksum,
            created_at=package.created_at,
        )
    )
    session.flush()


def _seed_report_references(repository: SqlAlchemyReportRepository) -> None:
    ReportPolicySeedService(repository).seed_v1()
    RuntimeReflectionPolicySeedService(repository).seed_v1()
    ReportTemplateSeedService(repository).seed_v1()


def _create_report_request(
    repository: SqlAlchemyReportRepository,
) -> ReportRequestRecord:
    manifest = ReportInputManifest(
        research_package_id=PACKAGE_ID,
        research_agent_run_id=RESEARCH_RUN_ID,
        research_request_id=RESEARCH_REQUEST_ID,
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        issuer_id=INDUSTRIAL_FII_ISSUER_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        research_type=ResearchType.COMPANY_OVERVIEW,
        research_mode=ResearchMode.REAL_RESEARCH,
        package_status=ResearchPackageStatus.BLOCKED,
        package_checksum="d" * 64,
        policy_version=build_controlled_offline_policy().version,
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        evidence_version="evidence-v1",
        claim_version="claim-v1",
        package_version="research-package-v1",
        claim_ids=(),
        evidence_ids=(),
        link_ids=(),
        citation_ids=(),
        lineage_ids=(),
        claims_checksum="1" * 64,
        evidence_checksum="2" * 64,
        links_checksum="3" * 64,
        citations_checksum="4" * 64,
        lineage_checksum="5" * 64,
        section_states=(
            ReportInputSectionState(
                section=ResearchSection.DATA_QUALITY,
                status=PackageSectionStatus.NO_EVIDENCE,
                claim_ids=(),
                warning_codes=(),
            ),
        ),
        blocked_capabilities=("VERIFIED_COMPANY_BODY_UNAVAILABLE",),
        warnings=("REAL_COMPANY_RESEARCH_INCOMPLETE",),
        data_quality_items=(),
        limitation_items=(),
        synthetic_status=SyntheticStatus.REAL_VERIFIED,
        manifest_schema_version="report-input-manifest-v1",
        canonical_payload_checksum="f" * 64,
        created_at=AS_OF,
    )
    return repository.add_request(
        ReportRequestWrite(
            id=REPORT_REQUEST_ID,
            manifest=manifest,
            report_type=ReportType.DATA_QUALITY_REPORT,
            report_locale=ReportLocale.ZH_CN,
            template_name="data_quality_report",
            template_version="1.0.0",
            report_policy_version=REPORT_POLICY_VERSION,
            reflection_policy_version=RUNTIME_REFLECTION_POLICY_VERSION,
            requested_sections=(
                ReportSection.DATA_QUALITY,
                ReportSection.LIMITATIONS,
            ),
            include_evidence_appendix=True,
            include_claim_index=True,
            max_excerpt_length=500,
            idempotency_key="9" * 64,
            created_at=AS_OF,
        )
    )


def _content() -> StructuredReportContent:
    return StructuredReportContent(
        schema_version="research-report-v1",
        locale=ReportLocale.ZH_CN,
        sections=(
            StructuredReportSection(
                section=ReportSection.DATA_QUALITY,
                section_index=0,
                title="数据质量",
                status=ReportSectionStatus.PARTIAL,
                blocks=(
                    StructuredReportBlock(
                        block_key="data_quality.limitation",
                        block_index=0,
                        block_type=ReportBlockType.LIMITATION,
                        status=ReportBlockStatus.PARTIAL,
                        text="真实公司证据不完整。",
                    ),
                ),
            ),
        ),
    )


def _report_record(request: ReportRequestRecord) -> ResearchReportRecord:
    manifest = request.manifest
    content = _content()
    rendered = DeterministicMarkdownRenderer().render(content)
    structured = structured_report_checksum(content)
    markdown = markdown_checksum(rendered.markdown_content)
    context = ReportChecksumContext(
        schema_version=content.schema_version,
        template_name="data_quality_report",
        template_version="1.0.0",
        renderer_version="deterministic-report-renderer-v1",
        markdown_renderer_version=MARKDOWN_RENDERER_VERSION,
        locale=ReportLocale.ZH_CN,
        input_manifest_checksum=manifest.canonical_payload_checksum,
        visible_references=ReportReferenceAllocator().allocate(content).references,
    )
    return ResearchReportRecord(
        id=REPORT_ID,
        report_generation_run_id=GENERATION_RUN_ID,
        report_version=1,
        report_type=ReportType.DATA_QUALITY_REPORT,
        report_locale=ReportLocale.ZH_CN,
        status=ResearchReportStatus.PARTIAL,
        title="可验证研究报告",
        security_id=manifest.security_id,
        snapshot_id=manifest.snapshot_id,
        research_as_of_time=manifest.research_as_of_time,
        research_package_id=manifest.research_package_id,
        input_manifest_checksum=manifest.canonical_payload_checksum,
        package_checksum=manifest.package_checksum,
        structured_content=content,
        markdown_content=rendered.markdown_content,
        structured_checksum=structured,
        markdown_checksum=markdown,
        content_checksum=combined_report_checksum(structured, markdown, context),
        claim_set_checksum=manifest.claims_checksum,
        evidence_set_checksum=manifest.evidence_checksum,
        link_set_checksum=manifest.links_checksum,
        citation_set_checksum=manifest.citations_checksum,
        renderer_version="deterministic-report-renderer-v1",
        template_name="data_quality_report",
        template_version="1.0.0",
        created_at=AS_OF,
    )


def _create_generation_run(
    repository: SqlAlchemyReportGenerationRepository,
    request: ReportRequestRecord,
) -> None:
    repository.create_run(
        ReportGenerationRunWrite(
            id=GENERATION_RUN_ID,
            report_request_id=request.id,
            research_package_id=PACKAGE_ID,
            research_agent_run_id=RESEARCH_RUN_ID,
            security_id=request.manifest.security_id,
            snapshot_id=request.manifest.snapshot_id,
            research_as_of_time=request.manifest.research_as_of_time,
            report_type=request.report_type,
            report_locale=request.report_locale,
            report_policy_version=request.report_policy_version,
            template_name=request.template_name,
            template_version=request.template_version,
            renderer_version="deterministic-report-renderer-v1",
            manifest_schema_version=request.manifest.manifest_schema_version,
            manifest_checksum=request.manifest.canonical_payload_checksum,
            package_checksum=request.manifest.package_checksum,
            claims_checksum=request.manifest.claims_checksum,
            evidence_checksum=request.manifest.evidence_checksum,
            links_checksum=request.manifest.links_checksum,
            citations_checksum=request.manifest.citations_checksum,
            lineage_checksum=request.manifest.lineage_checksum,
            idempotency_key="e" * 64,
            status=ReportGenerationStatus.CREATED,
            warning_count=0,
            created_at=AS_OF,
            updated_at=AS_OF,
        )
    )


def test_repository_rejects_factual_report_without_atomic_lineage_bindings(
    report_session: Session,
) -> None:
    repository = SqlAlchemyReportRepository(report_session)
    _seed_report_references(repository)
    request = _create_report_request(repository)
    _create_generation_run(
        SqlAlchemyReportGenerationRepository(report_session),
        request,
    )
    record = _report_record(request)
    section = record.structured_content.sections[0]
    factual = section.blocks[0].model_copy(
        update={
            "block_type": ReportBlockType.PARAGRAPH,
            "payload": {
                "claim_id": str(UUID("81000000-0000-4000-8000-00000000000c")),
                "support_status": "SUPPORTED",
            },
        }
    )
    record = record.model_copy(
        update={
            "structured_content": record.structured_content.model_copy(
                update={"sections": (section.model_copy(update={"blocks": (factual,)}),)}
            )
        }
    )

    with pytest.raises(ValueError, match="REPORT_FACTUAL_BINDINGS_REQUIRED"):
        repository.add_report(ResearchReportAggregateWrite(report=record))


def test_production_cli_application_runs_seed_and_domain_validated_transactions(
    report_session: Session,
) -> None:
    del report_session
    application = SqlAlchemyReportCliApplication()
    assert application.invoke("policy-seed-v1") is not None
    assert application.invoke("reflection-policy-seed-v1") is not None
    assert application.invoke("template-seed-v1") is not None

    policies = application.invoke("policy-list")
    assert isinstance(policies, tuple)
    assert policies

    with pytest.raises(ReportInputValidationError, match="ISSUER_IDENTITY_MISMATCH"):
        application.invoke(
            "generate",
            GenerateReportCommand(
                research_package_id=PACKAGE_ID,
                report_type=ReportType.DATA_QUALITY_REPORT,
                report_locale=ReportLocale.ZH_CN,
            ),
        )


def test_report_repository_persists_lifecycle_and_bounded_queries(
    report_session: Session,
) -> None:
    repository = SqlAlchemyReportRepository(report_session)
    _seed_report_references(repository)
    request = _create_report_request(repository)
    generation = SqlAlchemyReportGenerationRepository(report_session)
    _create_generation_run(generation, request)
    created = generation.get_run(GENERATION_RUN_ID)
    assert created is not None
    assert generation.find_reusable_run("e" * 64) == created
    running = generation.transition(
        created.id,
        ReportGenerationTransition(
            expected_status=ReportGenerationStatus.CREATED,
            target_status=ReportGenerationStatus.RUNNING,
            warning_count=0,
            changed_at=AS_OF,
        ),
    )
    report = repository.add_report(ResearchReportAggregateWrite(report=_report_record(request)))
    terminal = generation.transition(
        running.id,
        ReportGenerationTransition(
            expected_status=ReportGenerationStatus.RUNNING,
            target_status=ReportGenerationStatus.PARTIAL,
            warning_count=1,
            blocked_reason_code="VERIFIED_EVIDENCE_INCOMPLETE",
            changed_at=AS_OF,
        ),
    )
    assert terminal.status is ReportGenerationStatus.PARTIAL
    assert repository.get_report(REPORT_ID) == report
    assert repository.list_versions(GENERATION_RUN_ID) == (report.report,)

    query = ReportQueryService(repository)
    report_view = cast(dict[str, object], query.get_report(REPORT_ID))
    assert str(report_view["markdown_content"]).endswith("\n")
    sections = query.list_sections(REPORT_ID, PageRequest(limit=50, offset=0))
    blocks = query.list_blocks(REPORT_ID, PageRequest(limit=50, offset=0))
    assert sections.total == 1
    assert blocks.total == 1
    assert (
        query.list_claim_bindings(
            REPORT_ID,
            PageRequest(limit=50, offset=0),
        ).total
        == 0
    )
    report_session.commit()
