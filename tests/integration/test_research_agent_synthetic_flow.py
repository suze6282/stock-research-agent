from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from stock_research_agent.domain.research_agent.budgets import RunBudgetTracker
from stock_research_agent.domain.research_agent.claims import (
    ClaimSupportValidator,
    DeterministicClaimBuilder,
)
from stock_research_agent.domain.research_agent.conflicts import EvidenceConflictDetector
from stock_research_agent.domain.research_agent.enums import (
    ClaimSupportStatus,
    EvidenceStatus,
    EvidenceType,
    ResearchMode,
    ResearchPackageStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.packages import ResearchPackageAssembler
from stock_research_agent.domain.research_agent.plan_validation import ResearchPlanValidator
from stock_research_agent.domain.research_agent.planning import (
    PLANNER_VERSION,
    DeterministicTemplatePlanner,
)
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchClaimRecord,
    ResearchEvidenceRecord,
    ResearchRequestRecord,
    RunBudget,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

FIXTURE = Path(__file__).parents[1] / "fixtures" / "research_agent" / "synthetic_research.json"
MANIFEST = (
    Path(__file__).parents[1] / "fixtures" / "research_agent" / "synthetic_research.manifest.json"
)
NOW = datetime(2026, 7, 24, tzinfo=UTC)
SECURITY_ID = UUID("70000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("70000000-0000-4000-8000-000000000002")
RUN_ID = UUID("70000000-0000-4000-8000-000000000003")
REQUEST_ID = UUID("70000000-0000-4000-8000-000000000004")


def _evidence(
    suffix: int,
    evidence_type: EvidenceType,
    payload: dict[str, str],
    *,
    status: EvidenceStatus = EvidenceStatus.VALID,
) -> ResearchEvidenceRecord:
    return ResearchEvidenceRecord(
        id=UUID(f"70000000-0000-4000-8000-{suffix:012d}"),
        run_id=RUN_ID,
        observation_id=UUID(f"71000000-0000-4000-8000-{suffix:012d}"),
        evidence_type=evidence_type,
        status=status,
        schema_version="evidence-v1",
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        source_record_type="synthetic_test_fixture",
        source_record_id=UUID(f"72000000-0000-4000-8000-{suffix:012d}"),
        source_checksum=f"{suffix:064x}",
        published_at=NOW,
        citation_id=(
            UUID(f"73000000-0000-4000-8000-{suffix:012d}")
            if evidence_type is EvidenceType.DOCUMENT_CITATION_EVIDENCE
            else None
        ),
        calculation_run_id=(
            UUID(f"74000000-0000-4000-8000-{suffix:012d}")
            if evidence_type is EvidenceType.DERIVED_METRIC_EVIDENCE
            else None
        ),
        calculation_input_ids=(
            (UUID(f"75000000-0000-4000-8000-{suffix:012d}"),)
            if evidence_type is EvidenceType.DERIVED_METRIC_EVIDENCE
            else ()
        ),
        formula_version=(
            "synthetic-formula-v1"
            if evidence_type is EvidenceType.DERIVED_METRIC_EVIDENCE
            else None
        ),
        synthetic_status=SyntheticStatus.SYNTHETIC_TEST_ONLY,
        payload=payload,
        created_at=NOW,
    )


def test_synthetic_fixture_is_neutral_marked_and_checksum_verified() -> None:
    payload = FIXTURE.read_bytes()
    fixture = json.loads(payload)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert fixture["security_id"] == str(SECURITY_ID)
    assert SECURITY_ID not in {INDUSTRIAL_FII_SECURITY_ID, MICRON_SECURITY_ID}
    assert fixture["markers"] == [
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "OFFLINE",
        "NOT_LIVE",
    ]
    assert manifest["checksum"] == hashlib.sha256(payload).hexdigest()
    assert manifest["test_only"] is True


def test_synthetic_complete_flow_is_finite_supported_and_isolated() -> None:
    policy = build_controlled_offline_policy().model_copy(update={"allow_synthetic_evidence": True})
    catalog = build_tool_catalog_snapshot(create_tool_metadata_registry())
    request = ResearchRequestRecord(
        id=REQUEST_ID,
        security_query="SYNTHETIC-NEUTRAL",
        resolved_security_id=SECURITY_ID,
        normalized_security_query="SYNTHETIC-NEUTRAL",
        research_type=ResearchType.COMPANY_OVERVIEW,
        research_mode=ResearchMode.SYNTHETIC_TEST_ONLY,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        requested_sections=(
            ResearchSection.SECURITY_IDENTITY,
            ResearchSection.DOCUMENT_EVIDENCE,
            ResearchSection.DATA_QUALITY,
        ),
        policy_version=policy.version,
        planner_version=PLANNER_VERSION,
        tool_catalog_version=catalog.catalog_version,
        tool_catalog_checksum=catalog.catalog_checksum,
        request_checksum="a" * 64,
        created_at=NOW,
    )
    plan = ResearchPlanValidator().validate(
        DeterministicTemplatePlanner().create_plan(request, policy, catalog),
        policy,
        catalog,
    )
    assert len(plan.steps) <= policy.max_steps
    assert len({step.step_key for step in plan.steps}) == len(plan.steps)

    evidence = (
        _evidence(
            11,
            EvidenceType.SECURITY_MASTER_EVIDENCE,
            {
                "security_id": str(SECURITY_ID),
                "issuer": "Synthetic Neutral Issuer",
                "symbol": "SYN",
                "exchange": "TEST",
            },
        ),
        _evidence(
            12,
            EvidenceType.DOCUMENT_CITATION_EVIDENCE,
            {"disclosure_code": "SYNTHETIC_DISCLOSURE"},
        ),
        _evidence(
            13,
            EvidenceType.DATA_QUALITY_EVIDENCE,
            {"quality_code": "SYNTHETIC_FIXTURE_COMPLETE"},
        ),
    )
    ids = iter(UUID(f"76000000-0000-4000-8000-{value:012d}") for value in range(1, 100))
    proposals = DeterministicClaimBuilder(id_factory=lambda: next(ids)).propose_claims(
        run_id=RUN_ID,
        evidence=evidence,
        created_at=NOW,
        research_mode=ResearchMode.SYNTHETIC_TEST_ONLY,
    )
    validator = ClaimSupportValidator(id_factory=lambda: next(ids))
    claims = tuple(
        ResearchClaimRecord.model_validate(
            {
                **proposal.model_dump(
                    mode="python",
                    exclude={"proposed_evidence_ids"},
                ),
                **validator.validate(
                    claim=proposal,
                    evidence=evidence,
                    completed_at=NOW,
                    real_research=False,
                ).completion.model_dump(mode="python"),
            }
        )
        for proposal in proposals
    )
    assert {claim.support_status for claim in claims} == {ClaimSupportStatus.SUPPORTED}
    package = ResearchPackageAssembler().assemble(
        package_id=UUID("70000000-0000-4000-8000-000000000005"),
        run_id=RUN_ID,
        request_id=REQUEST_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        research_type=request.research_type,
        policy_version=policy.version,
        planner_version=PLANNER_VERSION,
        tool_catalog_version=catalog.catalog_version,
        requested_sections=request.requested_sections,
        claims=claims,
        evidence=evidence,
        blocked_capabilities=(),
        warnings=("SYNTHETIC_TEST_ONLY", "NOT_COMPANY_EVIDENCE", "OFFLINE", "NOT_LIVE"),
        run_failed=False,
        created_at=NOW,
    )
    assert package.status is ResearchPackageStatus.COMPLETE
    assert package.security_id not in {INDUSTRIAL_FII_SECURITY_ID, MICRON_SECURITY_ID}


def test_synthetic_conflict_and_budget_degradation_remain_explicit() -> None:
    left = _evidence(
        21,
        EvidenceType.DERIVED_METRIC_EVIDENCE,
        {
            "metric_code": "SYNTHETIC_MARGIN",
            "period": "FY",
            "value": "1",
            "unit": "ratio",
            "as_of_time": "2026-07-24T00:00:00Z",
            "metric_basis": "SYNTHETIC_ONLY",
        },
    )
    right = _evidence(
        22,
        EvidenceType.DERIVED_METRIC_EVIDENCE,
        {
            "metric_code": "SYNTHETIC_MARGIN",
            "period": "FY",
            "value": "2",
            "unit": "ratio",
            "as_of_time": "2026-07-24T00:00:00Z",
            "metric_basis": "SYNTHETIC_ONLY",
        },
    )
    conflict = EvidenceConflictDetector().detect((left, right))
    assert conflict.conflicting is True
    assert "VALUE_CONFLICT" in conflict.reason_codes

    budget = RunBudget(
        max_steps=1,
        max_tool_calls=1,
        max_calls_per_tool=1,
        max_retries_per_step=0,
        max_duration_seconds=1,
        model_token_budget=0,
        consumed_steps=0,
        consumed_tool_calls=0,
        consumed_model_tokens=0,
        elapsed_seconds=Decimal("0"),
    )
    consumed = RunBudgetTracker().consume_step(budget)
    assert consumed.consumed_steps == consumed.max_steps
    assert consumed.consumed_model_tokens == 0
