"""Deterministic Claim, Evidence, and Citation bindings for report facts."""

from __future__ import annotations

import hashlib

from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    LocatorType,
)
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    CitationVerification,
    DocumentVersionRecord,
)
from stock_research_agent.domain.reports.binding_schemas import (
    ReportCitationBindingWrite as ReportCitationBindingWrite,
)
from stock_research_agent.domain.reports.binding_schemas import (
    ReportClaimBindingRole as ReportClaimBindingRole,
)
from stock_research_agent.domain.reports.binding_schemas import (
    ReportClaimBindingWrite as ReportClaimBindingWrite,
)
from stock_research_agent.domain.reports.binding_schemas import (
    ReportEvidenceBindingWrite as ReportEvidenceBindingWrite,
)
from stock_research_agent.domain.reports.binding_schemas import (
    VisibleReferenceKind as VisibleReferenceKind,
)
from stock_research_agent.domain.reports.blocks import ReportBlockDraft
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    EvidenceRole,
    EvidenceStatus,
    ResearchMode,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)


class ReportBindingError(ValueError):
    """Stable deterministic rejection for an invalid lineage binding."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_claim_binding(
    block: ReportBlockDraft,
    claim: ResearchClaimRecord,
    binding: ReportClaimBindingWrite,
    manifest: ReportInputManifest,
) -> None:
    """Validate an exact immutable Claim binding against sealed report inputs."""

    _validate_claim_reachability(claim, binding, manifest)
    _validate_claim_location(block, binding)
    _validate_claim_support_matrix(block, claim, binding)
    if manifest.research_mode is ResearchMode.REAL_RESEARCH and manifest.synthetic_status not in {
        SyntheticStatus.REAL_VERIFIED,
        SyntheticStatus.FIXTURE_REAL_EXCERPT,
    }:
        raise ReportBindingError("REAL_REPORT_SYNTHETIC_CLAIM_FORBIDDEN")


def validate_claim_binding_set(
    bindings: tuple[ReportClaimBindingWrite, ...],
) -> None:
    """Reject duplicate Claim/location edges before persistence."""

    keys = [
        (
            binding.report_block_id,
            binding.claim_id,
            binding.sentence_index,
            binding.item_or_row_key,
        )
        for binding in bindings
    ]
    if len(keys) != len(set(keys)):
        raise ReportBindingError("DUPLICATE_CLAIM_BINDING")


def validate_evidence_binding(
    claim_binding: ReportClaimBindingWrite,
    link: ClaimEvidenceLinkRecord,
    evidence: ResearchEvidenceRecord,
    binding: ReportEvidenceBindingWrite,
    manifest: ReportInputManifest,
) -> None:
    """Validate one exact Stage 7 Link and Evidence projection."""

    if binding.report_claim_binding_id != claim_binding.id:
        raise ReportBindingError("EVIDENCE_BINDING_CLAIM_BINDING_ID_MISMATCH")
    if binding.report_block_id != claim_binding.report_block_id:
        raise ReportBindingError("EVIDENCE_BINDING_BLOCK_ID_MISMATCH")
    if binding.claim_evidence_link_id != link.id:
        raise ReportBindingError("EVIDENCE_BINDING_LINK_ID_MISMATCH")
    if binding.evidence_id != evidence.id:
        raise ReportBindingError("EVIDENCE_BINDING_EVIDENCE_ID_MISMATCH")
    if link.claim_id != claim_binding.claim_id:
        raise ReportBindingError("CLAIM_EVIDENCE_LINK_CLAIM_MISMATCH")
    if link.evidence_id != evidence.id:
        raise ReportBindingError("CLAIM_EVIDENCE_LINK_EVIDENCE_MISMATCH")
    if binding.role is not link.role:
        raise ReportBindingError("EVIDENCE_BINDING_ROLE_MISMATCH")
    if binding.item_or_row_key != claim_binding.item_or_row_key:
        raise ReportBindingError("EVIDENCE_BINDING_LOCATION_MISMATCH")
    if evidence.citation_id is not None and binding.citation_id != evidence.citation_id:
        raise ReportBindingError("EVIDENCE_BINDING_CITATION_ID_MISMATCH")
    if (
        evidence.source_record_id is not None
        and binding.source_record_id != evidence.source_record_id
    ):
        raise ReportBindingError("EVIDENCE_BINDING_SOURCE_RECORD_ID_MISMATCH")
    if evidence.source_checksum is not None and binding.source_checksum != evidence.source_checksum:
        raise ReportBindingError("EVIDENCE_BINDING_SOURCE_CHECKSUM_MISMATCH")
    _validate_evidence_context(link, evidence, manifest)
    if binding.role is EvidenceRole.PRIMARY:
        if evidence.status is not EvidenceStatus.VALID:
            raise ReportBindingError("PRIMARY_EVIDENCE_NOT_VALID")
        if evidence.source_checksum is None:
            raise ReportBindingError("PRIMARY_EVIDENCE_CHECKSUM_REQUIRED")
    if manifest.research_mode is ResearchMode.REAL_RESEARCH and evidence.synthetic_status not in {
        SyntheticStatus.REAL_VERIFIED,
        SyntheticStatus.FIXTURE_REAL_EXCERPT,
    }:
        raise ReportBindingError("REAL_REPORT_SYNTHETIC_EVIDENCE_FORBIDDEN")


def validate_evidence_binding_set(
    bindings: tuple[ReportEvidenceBindingWrite, ...],
) -> None:
    """Reject duplicate lineage edges or duplicate visible references."""

    link_ids = [binding.claim_evidence_link_id for binding in bindings]
    if len(link_ids) != len(set(link_ids)):
        raise ReportBindingError("DUPLICATE_EVIDENCE_LINK_BINDING")
    references = [binding.visible_reference for binding in bindings]
    if len(references) != len(set(references)):
        raise ReportBindingError("DUPLICATE_VISIBLE_EVIDENCE_REFERENCE")


def validate_citation_binding(
    evidence_binding: ReportEvidenceBindingWrite,
    citation: CitationAnchorRecord,
    document: DocumentVersionRecord,
    verification: CitationVerification,
    binding: ReportCitationBindingWrite,
    manifest: ReportInputManifest,
) -> None:
    """Validate one unchanged visible projection of a verified Citation."""

    if binding.report_evidence_binding_id != evidence_binding.id:
        raise ReportBindingError("CITATION_EVIDENCE_BINDING_ID_MISMATCH")
    if binding.citation_id != citation.id:
        raise ReportBindingError("CITATION_BINDING_CITATION_ID_MISMATCH")
    if evidence_binding.citation_id != citation.id:
        raise ReportBindingError("EVIDENCE_CITATION_ID_MISMATCH")
    if citation.document_version_id != document.id or binding.document_version_id != document.id:
        raise ReportBindingError("CITATION_DOCUMENT_VERSION_MISMATCH")
    if evidence_binding.source_record_id != document.id:
        raise ReportBindingError("EVIDENCE_DOCUMENT_VERSION_MISMATCH")
    if verification.citation_id != citation.id:
        raise ReportBindingError("CITATION_VERIFICATION_ID_MISMATCH")
    if (
        verification.status is not CitationStatus.VALID
        or binding.citation_status is not CitationStatus.VALID
    ):
        raise ReportBindingError("CITATION_VERIFICATION_NOT_VALID")
    if citation.id not in manifest.citation_ids:
        raise ReportBindingError("CITATION_NOT_IN_REPORT_MANIFEST")
    if document.security_id != manifest.security_id:
        raise ReportBindingError("CITATION_DOCUMENT_SECURITY_MISMATCH")
    if document.published_at is None:
        raise ReportBindingError("CITATION_DOCUMENT_PUBLISHED_AT_UNKNOWN")
    if document.published_at > manifest.research_as_of_time:
        raise ReportBindingError("FUTURE_CITATION_DOCUMENT")
    if (
        document.checksum != citation.document_checksum
        or evidence_binding.source_checksum != document.checksum
    ):
        raise ReportBindingError("CITATION_DOCUMENT_CHECKSUM_MISMATCH")
    if binding.locator_summary != citation_locator_summary(citation):
        raise ReportBindingError("CITATION_LOCATOR_SUMMARY_MISMATCH")
    if _unsafe_excerpt(binding.rendered_excerpt):
        raise ReportBindingError("UNSAFE_CITATION_EXCERPT")
    if binding.rendered_excerpt != citation.excerpt:
        raise ReportBindingError("CITATION_EXCERPT_REWRITE_FORBIDDEN")
    excerpt_checksum = hashlib.sha256(binding.rendered_excerpt.encode("utf-8")).hexdigest()
    if (
        excerpt_checksum != citation.excerpt_checksum
        or binding.rendered_excerpt_checksum != excerpt_checksum
    ):
        raise ReportBindingError("CITATION_EXCERPT_CHECKSUM_MISMATCH")


def validate_citation_binding_set(
    bindings: tuple[ReportCitationBindingWrite, ...],
) -> None:
    """Enforce bounded one-to-one Citation references."""

    if len(bindings) > 1000:
        raise ReportBindingError("CITATION_BINDING_LIMIT_EXCEEDED")
    references = [binding.visible_reference for binding in bindings]
    if len(references) != len(set(references)):
        raise ReportBindingError("DUPLICATE_VISIBLE_CITATION_REFERENCE")
    citation_ids = [binding.citation_id for binding in bindings]
    if len(citation_ids) != len(set(citation_ids)):
        raise ReportBindingError("DUPLICATE_CITATION_BINDING")


def citation_locator_summary(citation: CitationAnchorRecord) -> str:
    """Return a stable, non-path Citation locator projection."""

    if citation.locator_type is LocatorType.PDF_PAGE_RANGE:
        return f"pages:{citation.start_page}-{citation.end_page}"
    if citation.locator_type is LocatorType.HTML_ANCHOR_RANGE:
        return f"html:{citation.html_anchor}"
    if citation.locator_type is LocatorType.JSON_POINTER:
        return f"json:{citation.json_pointer}"
    if citation.locator_type is LocatorType.SECTION_RANGE:
        return f"section:{citation.section_id}:{citation.start_offset}-{citation.end_offset}"
    return f"text:{citation.start_offset}-{citation.end_offset}"


def _validate_claim_reachability(
    claim: ResearchClaimRecord,
    binding: ReportClaimBindingWrite,
    manifest: ReportInputManifest,
) -> None:
    if binding.claim_id != claim.id:
        raise ReportBindingError("CLAIM_BINDING_ID_MISMATCH")
    if claim.id not in manifest.claim_ids:
        raise ReportBindingError("CLAIM_NOT_IN_REPORT_MANIFEST")
    if claim.run_id != manifest.research_agent_run_id:
        raise ReportBindingError("CLAIM_RUN_MISMATCH")
    if claim.lifecycle_status is not ClaimLifecycleStatus.VALIDATED or claim.support_status is None:
        raise ReportBindingError("CLAIM_NOT_VALIDATED")


def _validate_claim_location(
    block: ReportBlockDraft,
    binding: ReportClaimBindingWrite,
) -> None:
    locations = (
        binding.sentence_index is not None,
        binding.item_or_row_key is not None,
    )
    if not any(locations):
        raise ReportBindingError("CLAIM_BINDING_LOCATION_REQUIRED")
    if all(locations):
        raise ReportBindingError("CLAIM_BINDING_LOCATION_AMBIGUOUS")
    if binding.item_or_row_key is not None:
        expected = block.factual_location_key
        if expected != binding.item_or_row_key:
            raise ReportBindingError("CLAIM_BINDING_LOCATION_MISMATCH")
    elif block.factual_location_key != f"sentence.{binding.sentence_index}":
        raise ReportBindingError("CLAIM_BINDING_LOCATION_MISMATCH")


def _validate_claim_support_matrix(
    block: ReportBlockDraft,
    claim: ResearchClaimRecord,
    binding: ReportClaimBindingWrite,
) -> None:
    support = claim.support_status
    if support is ClaimSupportStatus.SUPPORTED:
        if binding.role is not ReportClaimBindingRole.PRIMARY:
            raise ReportBindingError("SUPPORTED_CLAIM_REQUIRES_PRIMARY_ROLE")
        return
    if support is ClaimSupportStatus.PARTIALLY_SUPPORTED:
        if block.status is not ReportBlockStatus.PARTIAL:
            raise ReportBindingError("PARTIAL_CLAIM_REQUIRES_PARTIAL_BLOCK")
        if binding.role is not ReportClaimBindingRole.PRIMARY:
            raise ReportBindingError("PARTIAL_CLAIM_REQUIRES_PRIMARY_ROLE")
        return
    if support is ClaimSupportStatus.CONFLICTING:
        if block.block_type is not ReportBlockType.CONFLICT:
            raise ReportBindingError("CONFLICTING_CLAIM_REQUIRES_CONFLICT_BLOCK")
        if binding.role is not ReportClaimBindingRole.CONTRADICTING:
            raise ReportBindingError("CONFLICTING_CLAIM_REQUIRES_CONTRADICTING_ROLE")
        return
    if support is ClaimSupportStatus.UNSUPPORTED:
        if block.block_type is not ReportBlockType.LIMITATION:
            raise ReportBindingError("UNSUPPORTED_CLAIM_REQUIRES_DISCLOSURE_BLOCK")
        if binding.role is not ReportClaimBindingRole.LIMITATION:
            raise ReportBindingError("UNSUPPORTED_CLAIM_REQUIRES_LIMITATION_ROLE")
        return
    if support is ClaimSupportStatus.BLOCKED:
        if binding.role is not ReportClaimBindingRole.LIMITATION:
            raise ReportBindingError("BLOCKED_CLAIM_REQUIRES_LIMITATION_ROLE")
        if (
            block.block_type not in {ReportBlockType.LIMITATION, ReportBlockType.WARNING}
            or block.status is not ReportBlockStatus.BLOCKED
        ):
            raise ReportBindingError("BLOCKED_CLAIM_REQUIRES_BLOCKED_DISCLOSURE")


def _validate_evidence_context(
    link: ClaimEvidenceLinkRecord,
    evidence: ResearchEvidenceRecord,
    manifest: ReportInputManifest,
) -> None:
    if link.id not in manifest.link_ids:
        raise ReportBindingError("LINK_NOT_IN_REPORT_MANIFEST")
    if evidence.id not in manifest.evidence_ids:
        raise ReportBindingError("EVIDENCE_NOT_IN_REPORT_MANIFEST")
    if link.run_id != manifest.research_agent_run_id:
        raise ReportBindingError("LINK_RUN_MISMATCH")
    if evidence.run_id != manifest.research_agent_run_id:
        raise ReportBindingError("EVIDENCE_RUN_MISMATCH")
    if evidence.security_id != manifest.security_id:
        raise ReportBindingError("EVIDENCE_SECURITY_MISMATCH")
    if evidence.snapshot_id != manifest.snapshot_id:
        raise ReportBindingError("EVIDENCE_SNAPSHOT_MISMATCH")
    if evidence.research_as_of_time != manifest.research_as_of_time:
        raise ReportBindingError("EVIDENCE_AS_OF_MISMATCH")
    if evidence.published_at is not None and evidence.published_at > manifest.research_as_of_time:
        raise ReportBindingError("FUTURE_REPORT_EVIDENCE")


def _unsafe_excerpt(excerpt: str) -> bool:
    normalized = excerpt.casefold()
    forbidden_tokens = (
        "<script",
        "</",
        "password=",
        "secret=",
        "token=",
        "api_key",
        "file://",
        "blob://",
        "\u200b",
        "\ufeff",
    )
    if any(token in normalized for token in forbidden_tokens):
        return True
    return len(excerpt) >= 3 and excerpt[1:3] == ":\\"
