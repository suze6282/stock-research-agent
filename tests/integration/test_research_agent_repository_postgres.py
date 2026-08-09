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
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    INDUSTRIAL_FII_SECURITY_ID,
    SecurityMasterSeedService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 10, 12, tzinfo=UTC)
SNAPSHOT_ID = UUID("72000000-0000-4000-8000-000000000001")
PROVIDER_ID = UUID("72000000-0000-4000-8000-000000000002")
SNAPSHOT_ITEM_ID = UUID("72000000-0000-4000-8000-000000000003")
SOURCE_RECORD_ID = UUID("72000000-0000-4000-8000-000000000004")
CATALOG_VERSION = "tool-catalog-v1:" + "a" * 64


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
                    step_key="identity",
                    step_type=ResearchStepType.RESOLVE_SECURITY,
                    title="Resolve security",
                    required=True,
                    component_name="deterministic-resolver",
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
