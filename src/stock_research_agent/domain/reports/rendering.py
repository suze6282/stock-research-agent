"""Pure deterministic renderer for canonical structured research reports."""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from uuid import UUID

from pydantic import Field, JsonValue

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import ReportSection
from stock_research_agent.domain.reports.input_verification import (
    validate_report_input_manifest,
)
from stock_research_agent.domain.reports.references import ReportReferenceAllocator
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)
from stock_research_agent.domain.reports.schemas import (
    Checksum,
    FrozenReportContract,
    ReportPolicyRecord,
    ReportRequestRecord,
    VerifiedReportInput,
    Version,
)
from stock_research_agent.domain.reports.sections import build_sections
from stock_research_agent.domain.reports.templates import (
    ReportTemplateVersionRecord,
    StatementPattern,
    TemplatePlaceholder,
    TemplateStatus,
)
from stock_research_agent.domain.research_agent.enums import (
    ClaimSupportStatus,
    ClaimType,
    EvidenceType,
    ResearchMode,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)

RENDERER_VERSION = "deterministic-report-renderer-v1"


class ReportRenderError(RuntimeError):
    """Safe fixed-code deterministic render failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SeedReferenceKind(StrEnum):
    CITATION = "CITATION"
    EVIDENCE = "EVIDENCE"
    METRIC = "METRIC"
    LIMITATION = "LIMITATION"
    CONFLICT = "CONFLICT"


class SeedVisibleReference(FrozenReportContract):
    kind: SeedReferenceKind
    record_id: UUID
    label: str = Field(pattern=r"^(CIT|EV|MET|LIM|CON)-[0-9]{3}$")


class RenderedReportDraft(FrozenReportContract):
    """Canonical structured output before Markdown and persistence composition."""

    renderer_version: Version
    input_manifest_checksum: Checksum
    structured_content: StructuredReportContent
    structured_checksum: Checksum
    claim_ids: tuple[UUID, ...] = Field(max_length=500)
    evidence_ids: tuple[UUID, ...] = Field(max_length=1000)
    link_ids: tuple[UUID, ...] = Field(max_length=5000)
    citation_ids: tuple[UUID, ...] = Field(max_length=1000)
    visible_references: tuple[SeedVisibleReference, ...] = Field(max_length=5000)


class DeterministicReportRenderer:
    """Render sealed report input without external capabilities or mutable state."""

    def render(
        self,
        report_input: VerifiedReportInput,
        request: ReportRequestRecord,
        policy: ReportPolicyRecord,
        template: ReportTemplateVersionRecord,
    ) -> RenderedReportDraft:
        verified = validate_report_input_manifest(
            report_input.manifest,
            report_input.input,
        )
        self._validate_configuration(verified, request, policy, template)
        claims = tuple(
            sorted(
                verified.input.claims,
                key=lambda item: (item.statement_code, str(item.id)),
            )
        )
        links = tuple(
            sorted(
                verified.input.links,
                key=lambda item: (
                    str(item.claim_id),
                    str(item.evidence_id),
                    str(item.id),
                ),
            )
        )
        evidence = {
            item.id: item
            for item in sorted(
                verified.input.evidence,
                key=lambda item: str(item.id),
            )
        }
        references = _seed_references(claims, links, evidence)
        content = _render_content(
            claims,
            links,
            evidence,
            references,
            verified,
            template,
        )
        allocation = ReportReferenceAllocator().allocate(content)
        content = allocation.content
        references = tuple(
            SeedVisibleReference(
                kind=SeedReferenceKind(item.kind.value),
                record_id=item.record_id,
                label=item.label,
            )
            for item in allocation.references
        )
        return RenderedReportDraft(
            renderer_version=RENDERER_VERSION,
            input_manifest_checksum=verified.manifest.canonical_payload_checksum,
            structured_content=content,
            structured_checksum=report_checksum(content),
            claim_ids=tuple(item.id for item in claims),
            evidence_ids=tuple(sorted(evidence, key=str)),
            link_ids=tuple(sorted((item.id for item in links), key=str)),
            citation_ids=tuple(sorted(verified.manifest.citation_ids, key=str)),
            visible_references=references,
        )

    @staticmethod
    def _validate_configuration(
        report_input: VerifiedReportInput,
        request: ReportRequestRecord,
        policy: ReportPolicyRecord,
        template: ReportTemplateVersionRecord,
    ) -> None:
        if request.manifest != report_input.manifest:
            raise ReportRenderError("REPORT_REQUEST_MANIFEST_MISMATCH")
        if request.report_type not in policy.allowed_report_types:
            raise ReportRenderError("REPORT_TYPE_NOT_ALLOWED")
        if request.report_locale not in policy.allowed_locales:
            raise ReportRenderError("REPORT_LOCALE_NOT_ALLOWED")
        if any(section not in policy.allowed_sections for section in request.requested_sections):
            raise ReportRenderError("REPORT_SECTION_NOT_ALLOWED")
        if policy.allow_model_narrative or policy.allow_model_reflection:
            raise ReportRenderError("MODEL_RENDERING_FORBIDDEN")
        if (
            template.status is not TemplateStatus.ACTIVE
            or template.report_type is not request.report_type
            or template.locale is not request.report_locale
            or template.name != request.template_name
            or template.version != request.template_version
        ):
            raise ReportRenderError("REPORT_TEMPLATE_MISMATCH")


def _render_content(
    claims: tuple[ResearchClaimRecord, ...],
    links: tuple[ClaimEvidenceLinkRecord, ...],
    evidence: dict[UUID, ResearchEvidenceRecord],
    references: tuple[SeedVisibleReference, ...],
    verified: VerifiedReportInput,
    template: ReportTemplateVersionRecord,
) -> StructuredReportContent:
    claims_by_section: dict[ReportSection, list[ResearchClaimRecord]] = defaultdict(list)
    for claim in claims:
        claims_by_section[_claim_section(claim)].append(claim)
    links_by_claim: dict[UUID, list[ClaimEvidenceLinkRecord]] = defaultdict(list)
    for link in links:
        links_by_claim[link.claim_id].append(link)
    reference_by_id = {item.record_id: item.label for item in references}
    patterns = {item.statement_code: item for item in template.statement_patterns}
    section_drafts = build_sections(template, verified.manifest)
    sections: list[StructuredReportSection] = []
    for section in section_drafts:
        section_claims = tuple(claims_by_section.get(section.section, ()))
        blocks = (
            tuple(
                _claim_block(
                    claim,
                    index,
                    tuple(links_by_claim.get(claim.id, ())),
                    evidence,
                    reference_by_id,
                    patterns,
                )
                for index, claim in enumerate(section_claims)
            )
            if section_claims
            else (
                _empty_state_block(
                    ReportBlockStatus(section.status.value),
                    section.section,
                ),
            )
        )
        sections.append(
            StructuredReportSection(
                section=section.section,
                section_index=section.section_index,
                title=section.title,
                status=section.status,
                blocks=blocks,
            )
        )
    content = StructuredReportContent(
        schema_version="research-report-v1",
        locale=template.locale,
        sections=tuple(sections),
    )
    return _mark_synthetic_content(content, verified)


def _mark_synthetic_content(
    content: StructuredReportContent,
    verified: VerifiedReportInput,
) -> StructuredReportContent:
    manifest = verified.manifest
    if (
        manifest.research_mode is not ResearchMode.SYNTHETIC_TEST_ONLY
        or manifest.synthetic_status is not SyntheticStatus.SYNTHETIC_TEST_ONLY
    ):
        return content
    marker_text = "SYNTHETIC_TEST_ONLY NOT_COMPANY_EVIDENCE OFFLINE NOT_LIVE"
    sections = tuple(
        section.model_copy(
            update={
                "blocks": tuple(
                    block.model_copy(update={"text": f"{block.text or ''} {marker_text}".strip()})
                    for block in section.blocks
                )
            }
        )
        if section.section is ReportSection.RESEARCH_SCOPE
        else section
        for section in content.sections
    )
    return content.model_copy(update={"sections": sections})


def _claim_block(
    claim: ResearchClaimRecord,
    block_index: int,
    links: tuple[ClaimEvidenceLinkRecord, ...],
    evidence: dict[UUID, ResearchEvidenceRecord],
    reference_by_id: dict[UUID, str],
    patterns: dict[str, StatementPattern],
) -> StructuredReportBlock:
    if claim.support_status is None:
        raise ReportRenderError("CLAIM_SUPPORT_STATUS_MISSING")
    reference = _claim_reference(claim, links, reference_by_id)
    reference_targets = _claim_reference_targets(
        claim,
        links,
        evidence,
        reference_by_id,
    )
    pattern = patterns.get("NUMERIC_CLAIM")
    if pattern is None:
        raise ReportRenderError("REPORT_STATEMENT_PATTERN_MISSING")
    text = _render_pattern(pattern, claim, reference)
    linked_evidence_ids = tuple(
        sorted(
            (link.evidence_id for link in links if link.evidence_id in evidence),
            key=str,
        )
    )
    linked_link_ids = tuple(
        sorted(
            (link.id for link in links if link.evidence_id in evidence),
            key=str,
        )
    )
    if (
        claim.support_status
        in {
            ClaimSupportStatus.SUPPORTED,
            ClaimSupportStatus.PARTIALLY_SUPPORTED,
            ClaimSupportStatus.CONFLICTING,
        }
        and not linked_evidence_ids
    ):
        raise ReportRenderError("REPORT_CLAIM_EVIDENCE_BINDING_MISSING")
    return StructuredReportBlock(
        block_key=f"claim.{claim.statement_code.casefold()}.{block_index}",
        block_index=block_index,
        block_type=_block_type(claim.support_status),
        status=_block_status(claim.support_status),
        text=text,
        payload={
            "claim_id": str(claim.id),
            "evidence_ids": [str(item) for item in linked_evidence_ids],
            "link_ids": [str(item) for item in linked_link_ids],
            "metric_basis": claim.metric_basis,
            "period": claim.period,
            "reference": reference,
            "reference_targets": reference_targets,
            "statement_code": claim.statement_code,
            "support_status": claim.support_status.value,
            "unit": claim.unit,
            "value": None if claim.value is None else str(claim.value),
        },
    )


def _empty_state_block(
    status: ReportBlockStatus,
    section: ReportSection,
) -> StructuredReportBlock:
    return StructuredReportBlock(
        block_key=f"empty.{section.value.casefold()}",
        block_index=0,
        block_type=ReportBlockType.HEADING,
        status=status,
        text=status.value,
        payload={},
    )


def _claim_section(claim: ResearchClaimRecord) -> ReportSection:
    if claim.support_status is ClaimSupportStatus.CONFLICTING:
        return ReportSection.CONFLICTS
    if claim.support_status is ClaimSupportStatus.UNSUPPORTED:
        return ReportSection.UNSUPPORTED_CLAIMS
    if claim.support_status is ClaimSupportStatus.BLOCKED:
        return ReportSection.LIMITATIONS
    return {
        ClaimType.IDENTITY: ReportSection.SECURITY_IDENTITY,
        ClaimType.FINANCIAL_FACT: ReportSection.FINANCIAL_HEALTH,
        ClaimType.FINANCIAL_METRIC: ReportSection.FINANCIAL_HEALTH,
        ClaimType.VALUATION_METRIC: ReportSection.VALUATION_SNAPSHOT,
        ClaimType.DOCUMENT_DISCLOSURE: ReportSection.DOCUMENT_EVIDENCE,
        ClaimType.CORPORATE_ACTION: ReportSection.CORPORATE_ACTIONS,
        ClaimType.DATA_QUALITY: ReportSection.DATA_QUALITY,
        ClaimType.LIMITATION: ReportSection.LIMITATIONS,
    }[claim.claim_type]


def _block_type(support: ClaimSupportStatus) -> ReportBlockType:
    if support is ClaimSupportStatus.CONFLICTING:
        return ReportBlockType.CONFLICT
    if support in {ClaimSupportStatus.UNSUPPORTED, ClaimSupportStatus.BLOCKED}:
        return ReportBlockType.LIMITATION
    return ReportBlockType.METRIC_TABLE


def _block_status(support: ClaimSupportStatus) -> ReportBlockStatus:
    return {
        ClaimSupportStatus.SUPPORTED: ReportBlockStatus.COMPLETE,
        ClaimSupportStatus.PARTIALLY_SUPPORTED: ReportBlockStatus.PARTIAL,
        ClaimSupportStatus.CONFLICTING: ReportBlockStatus.PARTIAL,
        ClaimSupportStatus.UNSUPPORTED: ReportBlockStatus.NO_EVIDENCE,
        ClaimSupportStatus.BLOCKED: ReportBlockStatus.BLOCKED,
    }[support]


def _seed_references(
    claims: tuple[ResearchClaimRecord, ...],
    links: tuple[ClaimEvidenceLinkRecord, ...],
    evidence: dict[UUID, ResearchEvidenceRecord],
) -> tuple[SeedVisibleReference, ...]:
    links_by_claim: dict[UUID, list[ClaimEvidenceLinkRecord]] = defaultdict(list)
    for link in links:
        links_by_claim[link.claim_id].append(link)
    counters: dict[SeedReferenceKind, int] = defaultdict(int)
    allocated: list[SeedVisibleReference] = []
    seen: set[tuple[SeedReferenceKind, UUID]] = set()
    for claim in claims:
        if claim.support_status in {
            ClaimSupportStatus.CONFLICTING,
            ClaimSupportStatus.UNSUPPORTED,
            ClaimSupportStatus.BLOCKED,
        }:
            kind = (
                SeedReferenceKind.CONFLICT
                if claim.support_status is ClaimSupportStatus.CONFLICTING
                else SeedReferenceKind.LIMITATION
            )
            _allocate_reference(kind, claim.id, counters, seen, allocated)
            continue
        for link in sorted(
            links_by_claim.get(claim.id, ()),
            key=lambda item: (str(item.evidence_id), str(item.id)),
        ):
            item = evidence.get(link.evidence_id)
            if item is None:
                continue
            kind = (
                SeedReferenceKind.METRIC
                if item.evidence_type
                in {
                    EvidenceType.DERIVED_METRIC_EVIDENCE,
                    EvidenceType.METRIC_LINEAGE_EVIDENCE,
                }
                else SeedReferenceKind.EVIDENCE
            )
            _allocate_reference(kind, item.id, counters, seen, allocated)
    return tuple(allocated)


def _allocate_reference(
    kind: SeedReferenceKind,
    record_id: UUID,
    counters: dict[SeedReferenceKind, int],
    seen: set[tuple[SeedReferenceKind, UUID]],
    allocated: list[SeedVisibleReference],
) -> None:
    key = (kind, record_id)
    if key in seen:
        return
    seen.add(key)
    counters[kind] += 1
    prefix = {
        SeedReferenceKind.EVIDENCE: "EV",
        SeedReferenceKind.METRIC: "MET",
        SeedReferenceKind.LIMITATION: "LIM",
        SeedReferenceKind.CONFLICT: "CON",
    }[kind]
    allocated.append(
        SeedVisibleReference(
            kind=kind,
            record_id=record_id,
            label=f"{prefix}-{counters[kind]:03d}",
        )
    )


def _claim_reference(
    claim: ResearchClaimRecord,
    links: tuple[ClaimEvidenceLinkRecord, ...],
    reference_by_id: dict[UUID, str],
) -> str:
    if claim.support_status in {
        ClaimSupportStatus.CONFLICTING,
        ClaimSupportStatus.UNSUPPORTED,
        ClaimSupportStatus.BLOCKED,
    }:
        label = reference_by_id.get(claim.id)
    else:
        label = next(
            (
                reference_by_id[link.evidence_id]
                for link in sorted(
                    links,
                    key=lambda item: (str(item.evidence_id), str(item.id)),
                )
                if link.evidence_id in reference_by_id
            ),
            None,
        )
    return "" if label is None else f"[{label}]"


def _claim_reference_targets(
    claim: ResearchClaimRecord,
    links: tuple[ClaimEvidenceLinkRecord, ...],
    evidence: dict[UUID, ResearchEvidenceRecord],
    reference_by_id: dict[UUID, str],
) -> JsonValue:
    if claim.support_status in {
        ClaimSupportStatus.CONFLICTING,
        ClaimSupportStatus.UNSUPPORTED,
        ClaimSupportStatus.BLOCKED,
    }:
        label = reference_by_id.get(claim.id)
        if label is None:
            return []
        kind = (
            "CONFLICT" if claim.support_status is ClaimSupportStatus.CONFLICTING else "LIMITATION"
        )
        return [{"kind": kind, "record_id": str(claim.id), "label": label}]
    for link in sorted(
        links,
        key=lambda item: (str(item.evidence_id), str(item.id)),
    ):
        item = evidence.get(link.evidence_id)
        label = reference_by_id.get(link.evidence_id)
        if item is None or label is None:
            continue
        kind = (
            "METRIC"
            if item.evidence_type
            in {
                EvidenceType.DERIVED_METRIC_EVIDENCE,
                EvidenceType.METRIC_LINEAGE_EVIDENCE,
            }
            else "EVIDENCE"
        )
        return [{"kind": kind, "record_id": str(item.id), "label": label}]
    return []


def _render_pattern(
    pattern: StatementPattern,
    claim: ResearchClaimRecord,
    reference: str,
) -> str:
    values = {
        TemplatePlaceholder.CLAIM_VALUE: ("" if claim.value is None else str(claim.value)),
        TemplatePlaceholder.CLAIM_UNIT: claim.unit or "",
        TemplatePlaceholder.CLAIM_PERIOD: claim.period or "",
        TemplatePlaceholder.CLAIM_AS_OF: (
            "" if claim.as_of_time is None else claim.as_of_time.isoformat().replace("+00:00", "Z")
        ),
        TemplatePlaceholder.VISIBLE_REFERENCE: reference,
    }
    parts: list[str] = []
    for token in pattern.tokens:
        if token.literal is not None:
            parts.append(token.literal)
            continue
        if token.placeholder not in values:
            raise ReportRenderError("REPORT_TEMPLATE_PLACEHOLDER_UNAVAILABLE")
        parts.append(values[token.placeholder])
    return "".join(parts)
