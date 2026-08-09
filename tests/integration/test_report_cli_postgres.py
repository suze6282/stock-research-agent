from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from stock_research_agent.domain.reports.application import (
    GenerateReportCommand,
    ReportGenerationService,
)
from stock_research_agent.domain.reports.enums import ReportLocale, ReportType
from tests.integration.test_report_repository_postgres import (
    PACKAGE_ID,
    PROJECT_ROOT,
    _reset,
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


@dataclass
class _SqlWorkflow:
    session: Session
    fail: bool = False

    def execute(self, command: GenerateReportCommand) -> object:
        self.session.execute(
            text(
                "INSERT INTO report_policies "
                "(id, version, checksum, definition) "
                "VALUES (gen_random_uuid(), :version, :checksum, '{}'::jsonb)"
            ),
            {
                "version": "transaction-proof-v1",
                "checksum": "a" * 64,
            },
        )
        if self.fail:
            raise RuntimeError("SAFE_TRANSACTION_TEST_FAILURE")
        return {"status": "COMPLETED"}


def _command() -> GenerateReportCommand:
    return GenerateReportCommand(
        research_package_id=PACKAGE_ID,
        report_type=ReportType.DATA_QUALITY_REPORT,
        report_locale=ReportLocale.ZH_CN,
    )


def test_explicit_report_service_commits_one_postgres_transaction(
    stage8_session: Session,
) -> None:
    result = ReportGenerationService(
        _SqlWorkflow(stage8_session),
        stage8_session,
    ).generate(_command())

    assert result == {"status": "COMPLETED"}
    assert (
        stage8_session.scalar(
            text("SELECT count(*) FROM report_policies WHERE version = 'transaction-proof-v1'")
        )
        == 1
    )


def test_explicit_report_service_rolls_back_failed_postgres_transaction(
    stage8_session: Session,
) -> None:
    with pytest.raises(RuntimeError, match="SAFE_TRANSACTION_TEST_FAILURE"):
        ReportGenerationService(
            _SqlWorkflow(stage8_session, fail=True),
            stage8_session,
        ).generate(_command())

    assert (
        stage8_session.scalar(
            text("SELECT count(*) FROM report_policies WHERE version = 'transaction-proof-v1'")
        )
        == 0
    )
