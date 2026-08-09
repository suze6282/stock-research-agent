from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from stock_research_agent.domain.reports.composition import (
    DeterministicReportCompositionService,
)
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.input_verification import (
    build_report_input_manifest,
    validate_report_input_manifest,
)
from stock_research_agent.domain.reports.policies import build_default_report_policy
from stock_research_agent.domain.reports.reflection import (
    DeterministicReportReflectionEngine,
    ReportReflectionFindingRecord,
    ReportReflectionResult,
    ReportReflectionRunRecord,
)
from stock_research_agent.domain.reports.reflection_policy import (
    build_default_runtime_reflection_policy,
)
from stock_research_agent.domain.reports.release_gate import (
    ReportReleaseDecisionResult,
    ReportReleaseGate,
)
from stock_research_agent.domain.reports.reporting import ResearchReportAggregate
from stock_research_agent.domain.reports.schemas import (
    PersistedReportInput,
    ReportInputManifest,
    ReportRequestRecord,
    VerifiedReportInput,
)
from stock_research_agent.domain.reports.templates import (
    ReportTemplateVersionRecord,
    build_default_template_writes,
)
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    ResearchMode,
    ResearchRunStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.packages import ResearchPackageAssembler
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ResearchAgentRunRecord,
    ResearchClaimRecord,
    ResearchEvidenceRecord,
    ResearchRequestCreate,
    ResearchRequestRecord,
    RunBudget,
)

AS_OF = datetime(2026, 7, 13, tzinfo=UTC)
CATALOG_VERSION = "tool-catalog-v1:" + "a" * 64


@dataclass(frozen=True, slots=True)
class RealCompanyScenario:
    report_input: VerifiedReportInput
    request: ReportRequestRecord
    template: ReportTemplateVersionRecord


@dataclass(frozen=True, slots=True)
class CompletedReportScenario:
    report: ResearchReportAggregate
    reflection: ReportReflectionResult
    gate: ReportReleaseDecisionResult


SYNTHETIC_MARKERS = (
    "SYNTHETIC_TEST_ONLY",
    "NOT_COMPANY_EVIDENCE",
    "OFFLINE",
    "NOT_LIVE",
)


def build_honest_real_company_scenario(
    *,
    namespace: str,
    security_id: UUID,
    issuer_id: UUID,
    security_query: str,
    issuer_name: str,
    symbol: str,
    exchange: str,
    locale: ReportLocale,
) -> RealCompanyScenario:
    request_id = uuid5(NAMESPACE_URL, f"{namespace}:request")
    run_id = uuid5(NAMESPACE_URL, f"{namespace}:run")
    package_id = uuid5(NAMESPACE_URL, f"{namespace}:package")
    snapshot_id = uuid5(NAMESPACE_URL, f"{namespace}:snapshot")
    claim_id = uuid5(NAMESPACE_URL, f"{namespace}:identity-claim")
    evidence_id = uuid5(NAMESPACE_URL, f"{namespace}:identity-evidence")
    link_id = uuid5(NAMESPACE_URL, f"{namespace}:identity-link")
    requested_sections = (
        ResearchSection.SECURITY_IDENTITY,
        ResearchSection.FINANCIAL_HEALTH,
        ResearchSection.DOCUMENT_EVIDENCE,
        ResearchSection.DATA_QUALITY,
        ResearchSection.LIMITATIONS,
    )
    command = ResearchRequestCreate(
        security_query=security_query,
        research_type=ResearchType.FULL_RESEARCH_PACKAGE,
        snapshot_id=snapshot_id,
        research_as_of_time=AS_OF,
        requested_sections=requested_sections,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
    )
    request_basis = {
        **command.model_dump(mode="python"),
        "normalized_security_query": security_query,
        "resolved_security_id": security_id,
        "tool_catalog_version": CATALOG_VERSION,
        "tool_catalog_checksum": "a" * 64,
    }
    research_request = ResearchRequestRecord.model_validate(
        {
            **request_basis,
            "id": request_id,
            "request_checksum": stable_checksum(request_basis),
            "created_at": AS_OF,
        }
    )
    run = ResearchAgentRunRecord(
        id=run_id,
        request_id=request_id,
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=AS_OF,
        status=ResearchRunStatus.PARTIAL,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        tool_catalog_checksum="a" * 64,
        idempotency_key="b" * 64,
        budget=RunBudget(
            max_steps=20,
            max_tool_calls=50,
            max_calls_per_tool=5,
            max_retries_per_step=1,
            max_duration_seconds=300,
            model_token_budget=0,
            consumed_steps=5,
            consumed_tool_calls=5,
            consumed_model_tokens=0,
            elapsed_seconds=Decimal("1"),
        ),
        warning_codes=("REAL_COMPANY_EVIDENCE_INCOMPLETE",),
        terminal_reason_code="VERIFIED_EVIDENCE_INCOMPLETE",
        created_at=AS_OF,
        updated_at=AS_OF,
        terminal_at=AS_OF,
    )
    claim = ResearchClaimRecord(
        id=claim_id,
        run_id=run_id,
        claim_type=ClaimType.IDENTITY,
        lifecycle_status=ClaimLifecycleStatus.VALIDATED,
        support_status=ClaimSupportStatus.SUPPORTED,
        statement_code="SECURITY_IDENTITY",
        builder_version="deterministic-claim-builder-v1",
        validator_version="claim-support-validator-v1",
        created_at=AS_OF,
        completed_at=AS_OF,
    )
    evidence = ResearchEvidenceRecord(
        id=evidence_id,
        run_id=run_id,
        observation_id=uuid5(NAMESPACE_URL, f"{namespace}:identity-observation"),
        evidence_type=EvidenceType.SECURITY_MASTER_EVIDENCE,
        status=EvidenceStatus.VALID,
        schema_version="evidence-v1",
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=AS_OF,
        source_record_type="security",
        source_record_id=security_id,
        source_checksum="c" * 64,
        published_at=AS_OF - timedelta(days=1),
        synthetic_status=SyntheticStatus.REAL_VERIFIED,
        payload={
            "security_id": str(security_id),
            "issuer_id": str(issuer_id),
            "issuer": issuer_name,
            "symbol": symbol,
            "exchange": exchange,
        },
        created_at=AS_OF,
    )
    link = ClaimEvidenceLinkRecord(
        id=link_id,
        run_id=run_id,
        claim_id=claim_id,
        evidence_id=evidence_id,
        role=EvidenceRole.PRIMARY,
        created_at=AS_OF,
    )
    package = ResearchPackageAssembler().assemble(
        package_id=package_id,
        run_id=run_id,
        request_id=request_id,
        security_id=security_id,
        snapshot_id=snapshot_id,
        research_as_of_time=AS_OF,
        research_type=ResearchType.FULL_RESEARCH_PACKAGE,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        requested_sections=requested_sections,
        claims=(claim,),
        evidence=(evidence,),
        blocked_capabilities=(
            "FINANCIAL_FACTS_UNAVAILABLE",
            "VERIFIED_COMPANY_BODY_UNAVAILABLE",
        ),
        warnings=("REAL_COMPANY_EVIDENCE_INCOMPLETE",),
        run_failed=False,
        created_at=AS_OF,
    )
    persisted = PersistedReportInput(
        package=package,
        run=run,
        request=research_request,
        issuer_id=issuer_id,
        claims=(claim,),
        evidence=(evidence,),
        links=(link,),
        citations=(),
        citation_verifications=(),
    )
    manifest = build_report_input_manifest(persisted)
    verified = validate_report_input_manifest(manifest, persisted)
    report_type = ReportType.FULL_RESEARCH_DRAFT
    template_write = next(
        value
        for value in build_default_template_writes()
        if value.report_type is report_type and value.locale is locale
    )
    template = ReportTemplateVersionRecord(
        **template_write.model_dump(mode="python"),
        id=uuid5(NAMESPACE_URL, f"{namespace}:template:{locale.value}"),
        created_at=AS_OF,
    )
    request = ReportRequestRecord(
        id=uuid5(NAMESPACE_URL, f"{namespace}:report-request:{locale.value}"),
        manifest=manifest,
        report_type=report_type,
        report_locale=locale,
        template_name=template.name,
        template_version=template.version,
        report_policy_version=build_default_report_policy().version,
        reflection_policy_version="runtime-report-reflection-v1",
        requested_sections=tuple(ReportSection),
        include_evidence_appendix=True,
        include_claim_index=True,
        max_excerpt_length=1000,
        idempotency_key="d" * 64,
        created_at=AS_OF,
    )
    return RealCompanyScenario(
        report_input=verified,
        request=request,
        template=template,
    )


def build_neutral_synthetic_scenario(
    *,
    namespace: str,
    locale: ReportLocale,
) -> RealCompanyScenario:
    security_id = uuid5(NAMESPACE_URL, f"{namespace}:security")
    issuer_id = uuid5(NAMESPACE_URL, f"{namespace}:issuer")
    base = build_honest_real_company_scenario(
        namespace=namespace,
        security_id=security_id,
        issuer_id=issuer_id,
        security_query="SYNTH-001",
        issuer_name="Neutral Synthetic Issuer",
        symbol="SYNTH-001",
        exchange="XTEST",
        locale=locale,
    )
    persisted = base.report_input.input
    request_values = persisted.request.model_dump(
        mode="python",
        exclude={"id", "request_checksum", "created_at"},
    )
    request_values.update(
        {
            "research_mode": ResearchMode.SYNTHETIC_TEST_ONLY,
            "requested_sections": (ResearchSection.SECURITY_IDENTITY,),
        }
    )
    research_request = persisted.request.model_copy(
        update={
            "research_mode": ResearchMode.SYNTHETIC_TEST_ONLY,
            "requested_sections": (ResearchSection.SECURITY_IDENTITY,),
            "request_checksum": stable_checksum(request_values),
        }
    )
    evidence = tuple(
        item.model_copy(
            update={
                "synthetic_status": SyntheticStatus.SYNTHETIC_TEST_ONLY,
                "payload": {
                    **item.payload,
                    "fixture_status": list(SYNTHETIC_MARKERS),
                },
            }
        )
        for item in persisted.evidence
    )
    run = persisted.run.model_copy(
        update={
            "status": ResearchRunStatus.COMPLETED,
            "warning_codes": SYNTHETIC_MARKERS,
            "terminal_reason_code": "SYNTHETIC_TEST_COMPLETE",
        }
    )
    package = ResearchPackageAssembler().assemble(
        package_id=persisted.package.id,
        run_id=run.id,
        request_id=research_request.id,
        security_id=security_id,
        snapshot_id=run.snapshot_id,
        research_as_of_time=run.research_as_of_time,
        research_type=ResearchType.FULL_RESEARCH_PACKAGE,
        policy_version=run.policy_version,
        planner_version=run.planner_version,
        tool_catalog_version=run.tool_catalog_version,
        requested_sections=(ResearchSection.SECURITY_IDENTITY,),
        claims=persisted.claims,
        evidence=evidence,
        blocked_capabilities=(),
        warnings=SYNTHETIC_MARKERS,
        run_failed=False,
        created_at=AS_OF,
    )
    synthetic = PersistedReportInput(
        package=package,
        run=run,
        request=research_request,
        issuer_id=issuer_id,
        claims=persisted.claims,
        evidence=evidence,
        links=persisted.links,
        citations=(),
        citation_verifications=(),
    )
    manifest = build_report_input_manifest(synthetic)
    verified = validate_report_input_manifest(manifest, synthetic)
    return RealCompanyScenario(
        report_input=verified,
        request=base.request.model_copy(update={"manifest": manifest}),
        template=base.template,
    )


def run_honest_report_flow(
    scenario: RealCompanyScenario,
    *,
    namespace: str,
) -> CompletedReportScenario:
    report = DeterministicReportCompositionService().compose(
        scenario.report_input,
        scenario.request,
        build_default_report_policy(),
        scenario.template,
        report_id=uuid5(NAMESPACE_URL, f"{namespace}:report"),
        generation_run_id=uuid5(NAMESPACE_URL, f"{namespace}:generation-run"),
        created_at=AS_OF,
    )
    reflection = materialize_reflection(
        report,
        scenario.report_input.manifest,
        round_number=2,
        namespace=namespace,
    )
    gate = ReportReleaseGate().evaluate(
        report,
        scenario.report_input.manifest,
        reflection,
        build_default_report_policy(),
    )
    return CompletedReportScenario(
        report=report,
        reflection=reflection,
        gate=gate,
    )


def materialize_reflection(
    report: ResearchReportAggregate,
    manifest: ReportInputManifest,
    *,
    round_number: int,
    namespace: str,
) -> ReportReflectionResult:
    reflection_draft = DeterministicReportReflectionEngine().reflect(
        report,
        manifest,
        build_default_runtime_reflection_policy(),
        round_number,
    )
    reflection_id = uuid5(
        NAMESPACE_URL,
        f"{namespace}:reflection-round-{round_number}",
    )
    findings = tuple(
        ReportReflectionFindingRecord(
            id=uuid5(
                NAMESPACE_URL,
                f"{namespace}:finding:{index}:{finding.finding_code.value}",
            ),
            reflection_run_id=reflection_id,
            research_report_id=report.report.id,
            finding_code=finding.finding_code.value,
            category=finding.category,
            severity=finding.severity,
            description=finding.description,
            remediation_code=finding.remediation_code,
            blocking=finding.blocking,
            report_section=finding.report_section,
            block_key=finding.block_key,
            claim_id=finding.claim_id,
            evidence_id=finding.evidence_id,
            citation_id=finding.citation_id,
            created_at=AS_OF,
        )
        for index, finding in enumerate(reflection_draft.findings)
    )
    counts = reflection_draft.severity_counts
    reflection = ReportReflectionResult(
        run=ReportReflectionRunRecord(
            id=reflection_id,
            research_report_id=report.report.id,
            reflection_policy_version="runtime-report-reflection-v1",
            engine_name=reflection_draft.engine_name,
            engine_version=reflection_draft.engine_version,
            round_number=round_number,
            input_report_checksum=report.report.content_checksum,
            status=reflection_draft.status,
            started_at=AS_OF,
            total_finding_count=counts.total,
            critical_count=counts.critical,
            high_count=counts.high,
            medium_count=counts.medium,
            low_count=counts.low,
            completed_at=AS_OF,
        ),
        finding_ids=tuple(item.id for item in findings),
        findings=findings,
    )
    return reflection
