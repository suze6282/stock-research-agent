from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from stock_research_agent.db.models.reports import ResearchReport
from stock_research_agent.db.repositories.reports import (
    SqlAlchemyReportGenerationRepository,
    SqlAlchemyReportRepository,
)
from stock_research_agent.domain.reports.generation import (
    ReportGenerationRunWrite,
    ReportGenerationStatus,
    ReportGenerationTransition,
)
from stock_research_agent.domain.reports.reporting import ResearchReportAggregateWrite
from tests.integration.test_report_repository_postgres import (
    AS_OF,
    GENERATION_RUN_ID,
    PACKAGE_ID,
    PROJECT_ROOT,
    REPORT_ID,
    RESEARCH_RUN_ID,
    _create_report_request,
    _report_record,
    _reset,
    _seed_report_references,
    _seed_stage7_lineage,
)


@pytest.fixture
def stage8_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    url = os.environ["TEST_DATABASE_URL"]
    assert url.rsplit("/", maxsplit=1)[-1].endswith("_test")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    _reset(engine)
    with Session(engine) as session:
        _seed_stage7_lineage(session)
        session.commit()
        yield session
        session.rollback()
    _reset(engine)
    engine.dispose()


def _persist_terminal_report(session: Session) -> None:
    repository = SqlAlchemyReportRepository(session)
    _seed_report_references(repository)
    request = _create_report_request(repository)
    runs = SqlAlchemyReportGenerationRepository(session)
    runs.create_run(
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
    runs.transition(
        GENERATION_RUN_ID,
        ReportGenerationTransition(
            expected_status=ReportGenerationStatus.CREATED,
            target_status=ReportGenerationStatus.RUNNING,
            warning_count=0,
            changed_at=AS_OF,
        ),
    )
    repository.add_report(ResearchReportAggregateWrite(report=_report_record(request)))
    runs.transition(
        GENERATION_RUN_ID,
        ReportGenerationTransition(
            expected_status=ReportGenerationStatus.RUNNING,
            target_status=ReportGenerationStatus.PARTIAL,
            warning_count=1,
            blocked_reason_code="VERIFIED_EVIDENCE_INCOMPLETE",
            changed_at=AS_OF,
        ),
    )
    session.commit()


def test_terminal_report_and_generation_run_are_database_immutable(
    stage8_session: Session,
) -> None:
    _persist_terminal_report(stage8_session)

    with pytest.raises(DBAPIError):
        stage8_session.execute(
            text("UPDATE research_reports SET title = :title WHERE id = :id"),
            {"title": "mutated", "id": REPORT_ID},
        )
        stage8_session.commit()
    stage8_session.rollback()

    with pytest.raises(DBAPIError):
        stage8_session.execute(
            text("UPDATE report_generation_runs SET status = 'RUNNING' WHERE id = :id"),
            {"id": GENERATION_RUN_ID},
        )
        stage8_session.commit()
    stage8_session.rollback()

    stored = stage8_session.scalar(select(ResearchReport).where(ResearchReport.id == REPORT_ID))
    assert stored is not None
    assert stored.title == "可验证研究报告"


def test_invalid_report_insert_rolls_back_without_partial_rows(
    stage8_session: Session,
) -> None:
    _persist_terminal_report(stage8_session)
    before = stage8_session.scalar(text("SELECT count(*) FROM research_reports"))

    with pytest.raises(DBAPIError):
        stage8_session.execute(
            text(
                "INSERT INTO research_reports "
                "(id, report_generation_run_id, report_version, report_type, "
                "report_locale, status, title, security_id, snapshot_id, "
                "research_as_of_time, research_package_id, input_manifest_checksum, "
                "package_checksum, structured_content, markdown_content, "
                "structured_checksum, markdown_checksum, content_checksum, "
                "claim_set_checksum, evidence_set_checksum, link_set_checksum, "
                "citation_set_checksum, renderer_version, template_name, "
                "template_version) "
                "SELECT :id, report_generation_run_id, 2, report_type, "
                "report_locale, status, title, security_id, snapshot_id, "
                "research_as_of_time, research_package_id, input_manifest_checksum, "
                "package_checksum, structured_content, markdown_content, "
                "structured_checksum, markdown_checksum, content_checksum, "
                "claim_set_checksum, evidence_set_checksum, link_set_checksum, "
                "citation_set_checksum, renderer_version, template_name, "
                "template_version FROM research_reports WHERE id = :source"
            ),
            {
                "id": UUID("82000000-0000-4000-8000-000000000001"),
                "source": REPORT_ID,
            },
        )
        stage8_session.commit()
    stage8_session.rollback()

    after = stage8_session.scalar(text("SELECT count(*) FROM research_reports"))
    assert after == before
