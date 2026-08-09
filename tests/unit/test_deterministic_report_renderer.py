from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.policies import build_default_report_policy
from stock_research_agent.domain.reports.references import ReportReferenceAllocator
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
)
from stock_research_agent.domain.reports.schemas import (
    PersistedReportInput,
    ReportInputManifest,
    ReportInputSectionState,
    ReportRequestRecord,
    VerifiedReportInput,
)
from stock_research_agent.domain.reports.templates import (
    ReportTemplateVersionRecord,
    build_default_template_writes,
)
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    PackageSectionStatus,
    ResearchMode,
    ResearchPackageStatus,
    ResearchSection,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
SECURITY_ID = UUID("10000000-0000-0000-0000-000000000002")
SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000003")
SUPPORTED_ID = UUID("20000000-0000-0000-0000-000000000001")
CONFLICTING_ID = UUID("20000000-0000-0000-0000-000000000002")
BLOCKED_ID = UUID("20000000-0000-0000-0000-000000000003")
SUPPORTED_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000001")
CONFLICTING_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000002")


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.rendering")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 deterministic report renderer is missing")


def _claim(
    claim_id: UUID,
    support: ClaimSupportStatus,
    statement_code: str,
    value: str,
) -> ResearchClaimRecord:
    return ResearchClaimRecord.model_construct(
        id=claim_id,
        run_id=RUN_ID,
        claim_type=ClaimType.FINANCIAL_METRIC,
        lifecycle_status=ClaimLifecycleStatus.VALIDATED,
        support_status=support,
        statement_code=statement_code,
        value=Decimal(value),
        unit="RATIO",
        period="FY2025",
        as_of_time=NOW,
        metric_basis="CANONICAL_V1",
        builder_version="deterministic-claim-builder-v1",
        validator_version="claim-support-validator-v1",
        created_at=NOW,
        completed_at=NOW,
    )


def _evidence(evidence_id: UUID, *, status: EvidenceStatus) -> ResearchEvidenceRecord:
    return ResearchEvidenceRecord.model_construct(
        id=evidence_id,
        run_id=RUN_ID,
        evidence_type=EvidenceType.DERIVED_METRIC_EVIDENCE,
        status=status,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        source_checksum="a" * 64,
        synthetic_status=SyntheticStatus.REAL_VERIFIED,
    )


def _link(
    link_id: int,
    claim_id: UUID,
    evidence_id: UUID,
    role: EvidenceRole,
) -> ClaimEvidenceLinkRecord:
    return ClaimEvidenceLinkRecord.model_construct(
        id=UUID(int=link_id),
        run_id=RUN_ID,
        claim_id=claim_id,
        evidence_id=evidence_id,
        role=role,
        created_at=NOW,
    )


def _verified(*, reverse: bool = False) -> VerifiedReportInput:
    claims = (
        _claim(SUPPORTED_ID, ClaimSupportStatus.SUPPORTED, "RETURN_ON_EQUITY", "0.125"),
        _claim(
            CONFLICTING_ID,
            ClaimSupportStatus.CONFLICTING,
            "OPERATING_MARGIN",
            "0.080",
        ),
        _claim(BLOCKED_ID, ClaimSupportStatus.BLOCKED, "PRICE_TO_EARNINGS", "0"),
    )
    evidence = (
        _evidence(SUPPORTED_EVIDENCE_ID, status=EvidenceStatus.VALID),
        _evidence(CONFLICTING_EVIDENCE_ID, status=EvidenceStatus.CONFLICTING),
    )
    links = (
        _link(1, SUPPORTED_ID, SUPPORTED_EVIDENCE_ID, EvidenceRole.PRIMARY),
        _link(
            2,
            CONFLICTING_ID,
            CONFLICTING_EVIDENCE_ID,
            EvidenceRole.CONTRADICTING,
        ),
    )
    if reverse:
        claims = tuple(reversed(claims))
        evidence = tuple(reversed(evidence))
        links = tuple(reversed(links))
    manifest = ReportInputManifest.model_construct(
        research_agent_run_id=RUN_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        research_mode=ResearchMode.REAL_RESEARCH,
        package_status=ResearchPackageStatus.PARTIAL,
        claim_ids=tuple(sorted((SUPPORTED_ID, CONFLICTING_ID, BLOCKED_ID), key=str)),
        evidence_ids=tuple(sorted((SUPPORTED_EVIDENCE_ID, CONFLICTING_EVIDENCE_ID), key=str)),
        link_ids=(UUID(int=1), UUID(int=2)),
        citation_ids=(),
        canonical_payload_checksum="f" * 64,
        section_states=(
            ReportInputSectionState(
                section=ResearchSection.FINANCIAL_HEALTH,
                status=PackageSectionStatus.PARTIAL,
                claim_ids=(SUPPORTED_ID,),
                warning_codes=(),
            ),
            ReportInputSectionState(
                section=ResearchSection.LIMITATIONS,
                status=PackageSectionStatus.BLOCKED,
                claim_ids=(BLOCKED_ID,),
                warning_codes=("BLOCKED_CLAIMS_PRESENT",),
            ),
        ),
        blocked_capabilities=("FINANCIAL_FACTS_MISSING",),
        warnings=("PARTIAL_RESEARCH_PACKAGE",),
    )
    persisted = PersistedReportInput.model_construct(
        claims=claims,
        evidence=evidence,
        links=links,
        citations=(),
        citation_verifications=(),
    )
    return VerifiedReportInput(manifest=manifest, input=persisted)


def _request() -> ReportRequestRecord:
    return ReportRequestRecord.model_construct(
        id=UUID("40000000-0000-0000-0000-000000000001"),
        manifest=_verified().manifest,
        report_type=ReportType.EVIDENCE_SUMMARY,
        report_locale=ReportLocale.EN_US,
        template_name="evidence_summary",
        template_version="1.0.0",
        report_policy_version="verifiable-report-policy-v1",
        reflection_policy_version="runtime-report-reflection-v1",
        requested_sections=tuple(ReportSection),
        include_evidence_appendix=True,
        include_claim_index=True,
        max_excerpt_length=1000,
        idempotency_key="e" * 64,
        created_at=NOW,
    )


def _template() -> ReportTemplateVersionRecord:
    write = next(
        item
        for item in build_default_template_writes()
        if item.report_type is ReportType.EVIDENCE_SUMMARY and item.locale is ReportLocale.EN_US
    )
    return ReportTemplateVersionRecord.model_construct(
        **write.__dict__,
        id=UUID("50000000-0000-0000-0000-000000000001"),
        created_at=NOW,
    )


def test_identical_semantic_input_produces_identical_structured_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setattr(
        module,
        "validate_report_input_manifest",
        lambda manifest, persisted: VerifiedReportInput(
            manifest=manifest,
            input=persisted,
        ),
    )
    renderer = module.DeterministicReportRenderer()

    first = renderer.render(
        _verified(),
        _request(),
        build_default_report_policy(),
        _template(),
    )
    reordered = renderer.render(
        _verified(reverse=True),
        _request(),
        build_default_report_policy(),
        _template(),
    )

    assert first == reordered
    assert first.structured_checksum == module.report_checksum(first.structured_content)
    assert first.renderer_version == "deterministic-report-renderer-v1"


def test_sections_and_claims_use_closed_stable_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setattr(
        module,
        "validate_report_input_manifest",
        lambda manifest, persisted: VerifiedReportInput(
            manifest=manifest,
            input=persisted,
        ),
    )
    draft = module.DeterministicReportRenderer().render(
        _verified(),
        _request(),
        build_default_report_policy(),
        _template(),
    )

    assert tuple(section.section for section in draft.structured_content.sections) == tuple(
        ReportSection
    )
    sections = {section.section: section for section in draft.structured_content.sections}
    assert sections[ReportSection.FINANCIAL_HEALTH].blocks[0].status is ReportBlockStatus.COMPLETE
    assert sections[ReportSection.CONFLICTS].blocks[0].block_type is ReportBlockType.CONFLICT
    assert sections[ReportSection.LIMITATIONS].blocks[0].block_type is ReportBlockType.LIMITATION
    assert draft.claim_ids == (CONFLICTING_ID, BLOCKED_ID, SUPPORTED_ID)


def test_renderer_uses_only_allowlisted_template_statements_and_exact_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    calls = 0

    def verify(
        manifest: ReportInputManifest,
        persisted: PersistedReportInput,
    ) -> VerifiedReportInput:
        nonlocal calls
        calls += 1
        return VerifiedReportInput(manifest=manifest, input=persisted)

    monkeypatch.setattr(module, "validate_report_input_manifest", verify)
    draft = module.DeterministicReportRenderer().render(
        _verified(),
        _request(),
        build_default_report_policy(),
        _template(),
    )

    assert calls == 1
    factual_blocks = tuple(
        block
        for section in draft.structured_content.sections
        for block in section.blocks
        if block.block_type is not ReportBlockType.HEADING
    )
    assert all(
        set(block.payload)
        <= {
            "claim_id",
            "evidence_ids",
            "link_ids",
            "metric_basis",
            "period",
            "reference",
            "reference_targets",
            "statement_code",
            "support_status",
            "unit",
            "value",
        }
        for block in factual_blocks
    )
    assert all("recommend" not in (block.text or "").casefold() for block in factual_blocks)
    assert all("target price" not in (block.text or "").casefold() for block in factual_blocks)
    allocation = ReportReferenceAllocator().allocate(draft.structured_content)
    assert tuple(item.label for item in allocation.references) == tuple(
        item.label for item in draft.visible_references
    )


def test_renderer_has_no_injected_tool_model_network_or_latest_data_dependency() -> None:
    module = _module()
    renderer = module.DeterministicReportRenderer()

    assert vars(renderer) == {}
    assert not hasattr(renderer, "tool_registry")
    assert not hasattr(renderer, "model_provider")
    assert not hasattr(renderer, "repository")
    assert not hasattr(renderer, "latest_snapshot")
