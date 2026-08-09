from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.models.data_access import (
    DataProvider,
    DataSnapshot,
    SnapshotItem,
)
from stock_research_agent.db.models.research_agent import (
    ResearchAgentRun,
)
from stock_research_agent.db.repositories.research_agent import (
    SqlAlchemyResearchAgentRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchRunStatus,
    ResearchSection,
    ResearchType,
)
from stock_research_agent.domain.research_agent.policies import (
    ResearchPolicyError,
    ResearchPolicySeedService,
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    RequestedBudgets,
    ResearchPolicyWrite,
    ResearchRequestWrite,
    ResearchRunWrite,
    RunBudget,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    SecurityMasterSeedService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 10, 12, tzinfo=UTC)
SNAPSHOT_ID = UUID("73000000-0000-4000-8000-000000000001")
PROVIDER_ID = UUID("73000000-0000-4000-8000-000000000002")
SNAPSHOT_ITEM_ID = UUID("73000000-0000-4000-8000-000000000003")
SOURCE_RECORD_ID = UUID("73000000-0000-4000-8000-000000000004")
CATALOG_VERSION = "tool-catalog-v1:" + "a" * 64


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 7 policy tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def policy_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
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
    _ensure_snapshot(engine)
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


def _ensure_snapshot(engine: Engine) -> None:
    with Session(engine) as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        if session.get(DataProvider, PROVIDER_ID) is None:
            session.add(
                DataProvider(
                    id=PROVIDER_ID,
                    code="STAGE7_POLICY_FIXTURE",
                    name="Stage 7 policy test fixture",
                    provider_type="FIXTURE",
                    status="APPROVED",
                    base_url=None,
                    documentation_url=None,
                    terms_status="VERIFIED",
                    capabilities=["DAILY_PRICES"],
                )
            )
        if session.get(DataSnapshot, SNAPSHOT_ID) is None:
            snapshot = DataSnapshot(
                id=SNAPSHOT_ID,
                security_id=INDUSTRIAL_FII_SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=7002,
                status="BUILDING",
                completed_at=None,
                checksum=None,
                formula_version="raw-data-v1",
                notes="Stage 7 policy integration fixture",
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
                    checksum_input="stage7-policy-snapshot-item",
                    checksum="8" * 64,
                )
            )
            session.flush()
            snapshot.status = "COMPLETE"
            snapshot.completed_at = AS_OF
            snapshot.checksum = "7" * 64
        session.commit()


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


def _request(request_id: UUID) -> ResearchRequestWrite:
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
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        tool_catalog_checksum="a" * 64,
        request_checksum="b" * 64,
        created_at=AS_OF,
    )


def _run(
    request_id: UUID,
    run_id: UUID,
    *,
    status: ResearchRunStatus = ResearchRunStatus.CREATED,
    key: str = "c",
) -> ResearchRunWrite:
    return ResearchRunWrite(
        id=run_id,
        request_id=request_id,
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        status=status,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        tool_catalog_checksum="a" * 64,
        idempotency_key=key * 64,
        budget=_budget(),
        terminal_reason_code=("TEST_TERMINAL" if status is not ResearchRunStatus.CREATED else None),
        created_at=AS_OF,
        updated_at=AS_OF,
        terminal_at=(AS_OF if status is not ResearchRunStatus.CREATED else None),
    )


def test_policy_seed_is_idempotent_conflict_safe_and_immutable(
    policy_engine: Engine,
) -> None:
    with Session(policy_engine) as session:
        service = ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session))
        first = service.seed_v1()
        second = service.seed_v1()
        assert first.created is True
        assert second.created is False
        assert first.policy == second.policy
        session.commit()

    with Session(policy_engine) as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE research_policies SET checksum = :checksum WHERE version = :version"),
                {"checksum": "f" * 64, "version": first.policy.version},
            )
            session.commit()
        session.rollback()

    with Session(policy_engine) as session:
        session.execute(text("TRUNCATE TABLE research_policies CASCADE"))
        incompatible = build_controlled_offline_policy().model_copy(update={"checksum": "e" * 64})
        SqlAlchemyResearchAgentRepository(session).add_policy(
            ResearchPolicyWrite.model_validate(incompatible.model_dump(mode="python"))
        )
        session.commit()
    with Session(policy_engine) as session:
        with pytest.raises(ResearchPolicyError, match="POLICY_VERSION_CONFLICT"):
            ResearchPolicySeedService(SqlAlchemyResearchAgentRepository(session)).seed_v1()


def test_concurrent_identical_active_run_creation_converges_without_retry_sleep(
    policy_engine: Engine,
) -> None:
    request_id = uuid4()
    with Session(policy_engine) as session:
        repository = SqlAlchemyResearchAgentRepository(session)
        ResearchPolicySeedService(repository).seed_v1()
        repository.add_request(_request(request_id))
        session.commit()

    first = _run(request_id, uuid4())
    second = first.model_copy(update={"id": uuid4()})

    def create(value: ResearchRunWrite) -> UUID:
        with Session(policy_engine) as session:
            record = SqlAlchemyResearchAgentRepository(session).create_run(value)
            session.commit()
            return record.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = tuple(executor.map(create, (first, second)))

    assert ids[0] == ids[1]
    with Session(policy_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchAgentRun)
                .where(ResearchAgentRun.idempotency_key == first.idempotency_key)
            )
            == 1
        )


@pytest.mark.parametrize(
    "terminal_status",
    [ResearchRunStatus.FAILED, ResearchRunStatus.CANCELLED],
)
def test_failed_and_cancelled_history_do_not_block_a_new_active_run(
    policy_engine: Engine,
    terminal_status: ResearchRunStatus,
) -> None:
    request_id = uuid4()
    with Session(policy_engine) as session:
        repository = SqlAlchemyResearchAgentRepository(session)
        ResearchPolicySeedService(repository).seed_v1()
        repository.add_request(_request(request_id))
        repository.create_run(_run(request_id, uuid4(), status=terminal_status, key="9"))
        active = repository.create_run(_run(request_id, uuid4(), key="9"))
        session.commit()
        assert active.status is ResearchRunStatus.CREATED
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchAgentRun)
                .where(ResearchAgentRun.idempotency_key == "9" * 64)
            )
            == 2
        )
