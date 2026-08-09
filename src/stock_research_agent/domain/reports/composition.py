"""Deterministic composition of one sealed Stage 7 package into a report."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from stock_research_agent.domain.documents.enums import CitationStatus
from stock_research_agent.domain.reports.appendices import (
    EvidenceAppendixBindingView,
    build_claim_index,
    build_evidence_appendix,
)
from stock_research_agent.domain.reports.binding_schemas import (
    ReportCitationBindingWrite,
    ReportClaimBindingRole,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
    VisibleReferenceKind,
)
from stock_research_agent.domain.reports.bindings import citation_locator_summary
from stock_research_agent.domain.reports.blocks import ReportBlockDraft
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
from stock_research_agent.domain.reports.markdown import (
    MARKDOWN_RENDERER_VERSION,
    DeterministicMarkdownRenderer,
)
from stock_research_agent.domain.reports.references import ReportReferenceAllocator
from stock_research_agent.domain.reports.rendering import DeterministicReportRenderer
from stock_research_agent.domain.reports.reporting import (
    ReportSectionStatus,
    ResearchReportAggregate,
    ResearchReportRecord,
    ResearchReportStatus,
    StructuredReportBlock,
    StructuredReportContent,
)
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    ReportPolicyRecord,
    ReportRequestRecord,
    VerifiedReportInput,
)
from stock_research_agent.domain.reports.templates import ReportTemplateVersionRecord
from stock_research_agent.domain.research_agent.enums import (
    ClaimSupportStatus,
    EvidenceType,
    ResearchPackageStatus,
)


class DeterministicReportCompositionService:
    """Create the immutable JSON source and exact Markdown projection."""

    def compose(
        self,
        report_input: VerifiedReportInput,
        request: ReportRequestRecord,
        policy: ReportPolicyRecord,
        template: ReportTemplateVersionRecord,
        *,
        report_id: UUID,
        generation_run_id: UUID,
        created_at: AwareUtcDateTime,
        report_version: int = 1,
        previous_report_id: UUID | None = None,
    ) -> ResearchReportAggregate:
        draft = DeterministicReportRenderer().render(
            report_input,
            request,
            policy,
            template,
        )
        rendered = DeterministicMarkdownRenderer().render(draft.structured_content)
        references = ReportReferenceAllocator().allocate(draft.structured_content).references
        markdown_digest = markdown_checksum(rendered.markdown_content)
        checksum_context = ReportChecksumContext(
            schema_version=draft.structured_content.schema_version,
            template_name=template.name,
            template_version=template.version,
            renderer_version=draft.renderer_version,
            markdown_renderer_version=MARKDOWN_RENDERER_VERSION,
            locale=request.report_locale,
            input_manifest_checksum=report_input.manifest.canonical_payload_checksum,
            visible_references=references,
        )
        report = ResearchReportRecord(
            id=report_id,
            report_generation_run_id=generation_run_id,
            report_version=report_version,
            previous_report_id=previous_report_id,
            report_type=request.report_type,
            report_locale=request.report_locale,
            status=_status(report_input.manifest.package_status),
            title=_title(request.report_type, request.report_locale),
            security_id=report_input.manifest.security_id,
            snapshot_id=report_input.manifest.snapshot_id,
            research_as_of_time=report_input.manifest.research_as_of_time,
            research_package_id=report_input.manifest.research_package_id,
            input_manifest_checksum=report_input.manifest.canonical_payload_checksum,
            package_checksum=report_input.manifest.package_checksum,
            structured_content=draft.structured_content,
            markdown_content=rendered.markdown_content,
            structured_checksum=draft.structured_checksum,
            markdown_checksum=markdown_digest,
            content_checksum=combined_report_checksum(
                draft.structured_checksum,
                markdown_digest,
                checksum_context,
            ),
            claim_set_checksum=report_input.manifest.claims_checksum,
            evidence_set_checksum=report_input.manifest.evidence_checksum,
            link_set_checksum=report_input.manifest.links_checksum,
            citation_set_checksum=report_input.manifest.citations_checksum,
            renderer_version=draft.renderer_version,
            template_name=template.name,
            template_version=template.version,
            created_at=created_at,
        )
        claim_bindings, evidence_bindings, citation_bindings = _bindings(
            report,
            report_input,
            created_at,
        )
        content = _with_appendices(
            report.structured_content,
            report_input,
            request,
            claim_bindings,
            evidence_bindings,
        )
        if content != report.structured_content:
            rendered = DeterministicMarkdownRenderer().render(content)
            references = ReportReferenceAllocator().allocate(content).references
            structured_digest = structured_report_checksum(content)
            markdown_digest = markdown_checksum(rendered.markdown_content)
            checksum_context = ReportChecksumContext(
                schema_version=content.schema_version,
                template_name=template.name,
                template_version=template.version,
                renderer_version=draft.renderer_version,
                markdown_renderer_version=MARKDOWN_RENDERER_VERSION,
                locale=request.report_locale,
                input_manifest_checksum=(report_input.manifest.canonical_payload_checksum),
                visible_references=references,
            )
            report = report.model_copy(
                update={
                    "structured_content": content,
                    "markdown_content": rendered.markdown_content,
                    "structured_checksum": structured_digest,
                    "markdown_checksum": markdown_digest,
                    "content_checksum": combined_report_checksum(
                        structured_digest,
                        markdown_digest,
                        checksum_context,
                    ),
                }
            )
            claim_bindings, evidence_bindings, citation_bindings = _bindings(
                report,
                report_input,
                created_at,
            )
        return ResearchReportAggregate(
            report=report,
            claim_bindings=claim_bindings,
            evidence_bindings=evidence_bindings,
            citation_bindings=citation_bindings,
        )


def _status(package_status: ResearchPackageStatus) -> ResearchReportStatus:
    if package_status is ResearchPackageStatus.COMPLETE:
        return ResearchReportStatus.DRAFT
    if package_status is ResearchPackageStatus.PARTIAL:
        return ResearchReportStatus.PARTIAL
    if package_status is ResearchPackageStatus.BLOCKED:
        return ResearchReportStatus.BLOCKED
    return ResearchReportStatus.FAILED


def _title(report_type: ReportType, locale: ReportLocale) -> str:
    labels = {
        ReportLocale.ZH_CN: {
            ReportType.DATA_QUALITY_REPORT: "可验证数据质量报告",
            ReportType.EVIDENCE_SUMMARY: "可验证证据摘要",
            ReportType.FINANCIAL_RESEARCH_DRAFT: "可验证财务研究草稿",
            ReportType.FULL_RESEARCH_DRAFT: "可验证研究草稿",
        },
        ReportLocale.EN_US: {
            ReportType.DATA_QUALITY_REPORT: "Verifiable Data Quality Report",
            ReportType.EVIDENCE_SUMMARY: "Verifiable Evidence Summary",
            ReportType.FINANCIAL_RESEARCH_DRAFT: "Verifiable Financial Research Draft",
            ReportType.FULL_RESEARCH_DRAFT: "Verifiable Research Draft",
        },
    }
    return labels[locale][report_type]


def _bindings(
    report: ResearchReportRecord,
    report_input: VerifiedReportInput,
    created_at: AwareUtcDateTime,
) -> tuple[
    tuple[ReportClaimBindingWrite, ...],
    tuple[ReportEvidenceBindingWrite, ...],
    tuple[ReportCitationBindingWrite, ...],
]:
    claims = {value.id: value for value in report_input.input.claims}
    evidence = {value.id: value for value in report_input.input.evidence}
    links = {value.id: value for value in report_input.input.links}
    citations = {value.id: value for value in report_input.input.citations}
    citation_labels = {
        citation_id: f"CIT-{index:03d}"
        for index, citation_id in enumerate(
            sorted(citations, key=str),
            start=1,
        )
    }
    claim_writes: list[ReportClaimBindingWrite] = []
    evidence_writes: list[ReportEvidenceBindingWrite] = []
    citation_writes: list[ReportCitationBindingWrite] = []
    for section in report.structured_content.sections:
        for block in section.blocks:
            raw_claim_id = block.payload.get("claim_id")
            if not isinstance(raw_claim_id, str):
                continue
            claim_id = UUID(raw_claim_id)
            claim = claims.get(claim_id)
            if claim is None or claim.support_status is None:
                raise ValueError("REPORT_BLOCK_CLAIM_NOT_IN_MANIFEST")
            block_id = uuid5(
                NAMESPACE_URL,
                f"{report.id}:block:{block.block_key}",
            )
            claim_binding_id = uuid5(
                NAMESPACE_URL,
                f"{report.id}:claim-binding:{block.block_key}:{claim_id}",
            )
            claim_binding = ReportClaimBindingWrite(
                id=claim_binding_id,
                report_block_id=block_id,
                claim_id=claim_id,
                role=_claim_role(claim.support_status),
                item_or_row_key=block.block_key,
                created_at=created_at,
            )
            claim_writes.append(claim_binding)
            if claim_binding.role is ReportClaimBindingRole.LIMITATION:
                continue
            link_ids = block.payload.get("link_ids")
            if not isinstance(link_ids, list) or not link_ids:
                raise ValueError("REPORT_BLOCK_LINK_NOT_IN_MANIFEST")
            link = links.get(UUID(str(link_ids[0])))
            if link is None or link.claim_id != claim_id:
                raise ValueError("REPORT_BLOCK_LINK_NOT_IN_MANIFEST")
            evidence_record = evidence.get(link.evidence_id)
            if evidence_record is None:
                raise ValueError("REPORT_BLOCK_EVIDENCE_NOT_IN_MANIFEST")
            visible_reference = str(block.payload.get("reference", "")).strip("[]")
            reference_kind = (
                VisibleReferenceKind.METRIC
                if evidence_record.evidence_type
                in {
                    EvidenceType.DERIVED_METRIC_EVIDENCE,
                    EvidenceType.METRIC_LINEAGE_EVIDENCE,
                }
                else VisibleReferenceKind.EVIDENCE
            )
            evidence_binding_id = uuid5(
                NAMESPACE_URL,
                f"{report.id}:evidence-binding:{block.block_key}:{link.id}",
            )
            evidence_writes.append(
                ReportEvidenceBindingWrite(
                    id=evidence_binding_id,
                    report_block_id=block_id,
                    report_claim_binding_id=claim_binding_id,
                    claim_evidence_link_id=link.id,
                    evidence_id=evidence_record.id,
                    role=link.role,
                    visible_reference_kind=reference_kind,
                    visible_reference=visible_reference,
                    item_or_row_key=block.block_key,
                    citation_id=evidence_record.citation_id,
                    source_record_id=evidence_record.source_record_id,
                    source_checksum=evidence_record.source_checksum,
                    created_at=created_at,
                )
            )
            if evidence_record.citation_id is None:
                continue
            citation = citations.get(evidence_record.citation_id)
            if citation is None:
                raise ValueError("REPORT_BLOCK_CITATION_NOT_IN_MANIFEST")
            citation_writes.append(
                ReportCitationBindingWrite(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"{report.id}:citation-binding:{citation.id}",
                    ),
                    report_evidence_binding_id=evidence_binding_id,
                    citation_id=citation.id,
                    document_version_id=citation.document_version_id,
                    visible_reference=citation_labels[citation.id],
                    locator_summary=citation_locator_summary(citation),
                    rendered_excerpt=citation.excerpt,
                    rendered_excerpt_checksum=citation.excerpt_checksum,
                    citation_status=CitationStatus.VALID,
                    created_at=created_at,
                )
            )
    return tuple(claim_writes), tuple(evidence_writes), tuple(citation_writes)


def _claim_role(status: ClaimSupportStatus) -> ReportClaimBindingRole:
    if status is ClaimSupportStatus.CONFLICTING:
        return ReportClaimBindingRole.CONTRADICTING
    if status in {ClaimSupportStatus.UNSUPPORTED, ClaimSupportStatus.BLOCKED}:
        return ReportClaimBindingRole.LIMITATION
    return ReportClaimBindingRole.PRIMARY


def _with_appendices(
    content: StructuredReportContent,
    report_input: VerifiedReportInput,
    request: ReportRequestRecord,
    claim_bindings: tuple[ReportClaimBindingWrite, ...],
    evidence_bindings: tuple[ReportEvidenceBindingWrite, ...],
) -> StructuredReportContent:
    replacements: dict[ReportSection, StructuredReportBlock] = {}
    claims = {value.id: value for value in report_input.input.claims}
    evidence = {value.id: value for value in report_input.input.evidence}
    if request.include_claim_index and claim_bindings:
        replacements[ReportSection.CLAIM_INDEX] = _appendix_block(
            build_claim_index(
                content,
                report_input.input.claims,
                claim_bindings,
            )
        )
    if request.include_evidence_appendix and claim_bindings:
        evidence_by_claim_binding = {
            value.report_claim_binding_id: value for value in evidence_bindings
        }
        reference_by_record = {
            value.record_id: value.label
            for value in ReportReferenceAllocator().allocate(content).references
        }
        views: list[EvidenceAppendixBindingView] = []
        for claim_binding in claim_bindings:
            claim = claims[claim_binding.claim_id]
            evidence_binding = evidence_by_claim_binding.get(claim_binding.id)
            evidence_record = (
                None if evidence_binding is None else evidence[evidence_binding.evidence_id]
            )
            visible_reference = (
                reference_by_record[claim.id]
                if evidence_binding is None
                else evidence_binding.visible_reference
            )
            views.append(
                EvidenceAppendixBindingView(
                    visible_reference=visible_reference,
                    claim=claim,
                    claim_binding=claim_binding,
                    evidence=evidence_record,
                    evidence_binding=evidence_binding,
                )
            )
        replacements[ReportSection.EVIDENCE_APPENDIX] = _appendix_block(
            build_evidence_appendix(
                report_input.manifest,
                tuple(views),
            )
        )
    if not replacements:
        return content
    sections = tuple(
        section.model_copy(
            update={
                "status": ReportSectionStatus(replacements[section.section].status.value),
                "blocks": (replacements[section.section],),
            }
        )
        if section.section in replacements
        else section
        for section in content.sections
    )
    return content.model_copy(update={"sections": sections})


def _appendix_block(value: ReportBlockDraft) -> StructuredReportBlock:
    return StructuredReportBlock.model_validate(
        value.model_dump(
            mode="python",
            exclude={"checksum", "factual_location_key"},
        )
    )


__all__ = ["DeterministicReportCompositionService"]
