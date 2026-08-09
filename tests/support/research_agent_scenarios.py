from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

from stock_research_agent.domain.research_agent.claims import (
    ClaimSupportValidator,
    DeterministicClaimBuilder,
)
from stock_research_agent.domain.research_agent.enums import (
    EvidenceStatus,
    EvidenceType,
    ResearchMode,
    ResearchPackageStatus,
    ResearchRunStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.idempotency import (
    research_run_idempotency_key,
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
    ResearchPackageRecord,
    ResearchRequestRecord,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

NOW = datetime(2026, 7, 13, tzinfo=UTC)
_NAMESPACE = UUID("77777777-7777-4777-8777-777777777777")


@dataclass(frozen=True, slots=True)
class HonestDegradationScenario:
    request: ResearchRequestRecord
    plan_checksum: str
    tool_names: tuple[str, ...]
    evidence: tuple[ResearchEvidenceRecord, ...]
    claims: tuple[ResearchClaimRecord, ...]
    package: ResearchPackageRecord
    idempotency_key: str
    run_status: ResearchRunStatus


def _id(label: str) -> UUID:
    return uuid5(_NAMESPACE, label)


def build_honest_degradation(
    *,
    label: str,
    security_id: UUID,
    security_query: str,
    symbol: str,
    issuer: str,
    exchange: str,
) -> HonestDegradationScenario:
    policy = build_controlled_offline_policy()
    catalog = build_tool_catalog_snapshot(create_tool_metadata_registry())
    snapshot_id = _id(f"{label}:snapshot")
    run_id = _id(f"{label}:run")
    request_id = _id(f"{label}:request")
    request = ResearchRequestRecord(
        id=request_id,
        security_query=security_query,
        resolved_security_id=security_id,
        normalized_security_query=security_query.upper(),
        research_type=ResearchType.FULL_RESEARCH_PACKAGE,
        research_mode=ResearchMode.REAL_RESEARCH,
        snapshot_id=snapshot_id,
        research_as_of_time=NOW,
        requested_sections=(
            ResearchSection.SECURITY_IDENTITY,
            ResearchSection.FINANCIAL_HEALTH,
            ResearchSection.DOCUMENT_EVIDENCE,
            ResearchSection.DATA_QUALITY,
            ResearchSection.LIMITATIONS,
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
    identity = _evidence(
        label=label,
        suffix="identity",
        run_id=run_id,
        security_id=security_id,
        snapshot_id=snapshot_id,
        evidence_type=EvidenceType.SECURITY_MASTER_EVIDENCE,
        status=EvidenceStatus.VALID,
        payload={
            "security_id": str(security_id),
            "issuer": issuer,
            "symbol": symbol,
            "exchange": exchange,
        },
    )
    quality = _evidence(
        label=label,
        suffix="quality",
        run_id=run_id,
        security_id=security_id,
        snapshot_id=snapshot_id,
        evidence_type=EvidenceType.DATA_QUALITY_EVIDENCE,
        status=EvidenceStatus.VALID,
        payload={"quality_code": "REAL_EVIDENCE_INCOMPLETE"},
    )
    blocked_document = _evidence(
        label=label,
        suffix="document",
        run_id=run_id,
        security_id=security_id,
        snapshot_id=snapshot_id,
        evidence_type=EvidenceType.BLOCKED_CAPABILITY_EVIDENCE,
        status=EvidenceStatus.BLOCKED,
        payload={"capability_code": "VERIFIED_COMPANY_BODY_UNAVAILABLE"},
    )
    blocked_financials = _evidence(
        label=label,
        suffix="financials",
        run_id=run_id,
        security_id=security_id,
        snapshot_id=snapshot_id,
        evidence_type=EvidenceType.BLOCKED_CAPABILITY_EVIDENCE,
        status=EvidenceStatus.BLOCKED,
        payload={"capability_code": "VERIFIED_FINANCIAL_FACTS_UNAVAILABLE"},
    )
    evidence = (identity, quality, blocked_document, blocked_financials)
    counter = iter(range(100))
    builder = DeterministicClaimBuilder(id_factory=lambda: _id(f"{label}:claim:{next(counter)}"))
    proposals = builder.propose_claims(run_id=run_id, evidence=evidence, created_at=NOW)
    validator = ClaimSupportValidator(id_factory=lambda: _id(f"{label}:link:{next(counter)}"))
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
                    real_research=True,
                ).completion.model_dump(mode="python"),
            }
        )
        for proposal in proposals
    )
    package = ResearchPackageAssembler().assemble(
        package_id=_id(f"{label}:package"),
        run_id=run_id,
        request_id=request_id,
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=NOW,
        research_type=request.research_type,
        policy_version=policy.version,
        planner_version=PLANNER_VERSION,
        tool_catalog_version=catalog.catalog_version,
        requested_sections=request.requested_sections,
        claims=claims,
        evidence=evidence,
        blocked_capabilities=(
            "VERIFIED_COMPANY_BODY_UNAVAILABLE",
            "VERIFIED_FINANCIAL_FACTS_UNAVAILABLE",
        ),
        warnings=("REAL_COMPANY_RESEARCH_INCOMPLETE",),
        run_failed=False,
        created_at=NOW,
    )
    key = research_run_idempotency_key(
        normalized_request=request.normalized_security_query,
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=NOW,
        research_type=request.research_type,
        requested_sections=request.requested_sections,
        policy_version=policy.version,
        planner_version=PLANNER_VERSION,
        tool_catalog_checksum=catalog.catalog_checksum,
    )
    assert package.status in {ResearchPackageStatus.PARTIAL, ResearchPackageStatus.BLOCKED}
    return HonestDegradationScenario(
        request=request,
        plan_checksum=plan.plan_checksum,
        tool_names=tuple(step.tool_name for step in plan.steps if step.tool_name is not None),
        evidence=evidence,
        claims=claims,
        package=package,
        idempotency_key=key,
        run_status=(
            ResearchRunStatus.PARTIAL
            if package.status is ResearchPackageStatus.PARTIAL
            else ResearchRunStatus.BLOCKED
        ),
    )


def _evidence(
    *,
    label: str,
    suffix: str,
    run_id: UUID,
    security_id: UUID,
    snapshot_id: UUID,
    evidence_type: EvidenceType,
    status: EvidenceStatus,
    payload: dict[str, str],
) -> ResearchEvidenceRecord:
    return ResearchEvidenceRecord(
        id=_id(f"{label}:evidence:{suffix}"),
        run_id=run_id,
        observation_id=_id(f"{label}:observation:{suffix}"),
        evidence_type=evidence_type,
        status=status,
        schema_version="evidence-v1",
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=NOW,
        source_record_type="persisted_stage_state",
        source_record_id=_id(f"{label}:source:{suffix}"),
        source_checksum="b" * 64,
        published_at=NOW,
        synthetic_status=SyntheticStatus.REAL_VERIFIED,
        payload=payload,
        warning_codes=("BLOCKED_CAPABILITY",) if status is EvidenceStatus.BLOCKED else (),
        created_at=NOW,
    )
