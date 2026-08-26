"""Deterministic admission gates for governed evidence citations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from stock_research_agent.domain.documents.enums import CitationStatus
from stock_research_agent.domain.documents.schemas import (
    CitationVerification,
    DocumentVersionRecord,
)
from stock_research_agent.domain.live_evidence.enums import ManualEvidenceState
from stock_research_agent.domain.live_evidence.manifests import (
    EvidenceIngestionManifestRecord,
    EvidenceManifestRegistry,
)
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
)
from stock_research_agent.domain.research_agent.enums import ClaimType, EvidenceRole


class CitationEligibilityDecision(FrozenProviderContract):
    status: Literal["ELIGIBLE", "BLOCKED"]
    warning_codes: tuple[str, ...]


class EvidenceUseTarget(StrEnum):
    CLAIM_SUPPORT = "CLAIM_SUPPORT"
    CITATION = "CITATION"
    REPORT = "REPORT"


class ClaimEligibilityDecision(FrozenProviderContract):
    status: Literal["ELIGIBLE", "LIMITATION_ONLY", "BLOCKED"]
    warning_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCitationRequest:
    manifest: EvidenceIngestionManifestRecord
    manifest_registry: EvidenceManifestRegistry
    document_version: DocumentVersionRecord
    citation_id: UUID
    citation_document_version_id: UUID
    verification: CitationVerification
    research_as_of_time: AwareUtcDateTime


@dataclass(frozen=True, slots=True)
class EvidenceClaimRequest:
    evidence_state: ManualEvidenceState
    manifest: EvidenceIngestionManifestRecord | None
    manifest_registry: EvidenceManifestRegistry | None
    claim_type: ClaimType
    evidence_role: EvidenceRole
    intended_use: EvidenceUseTarget


def evaluate_citation_eligibility(
    request: EvidenceCitationRequest,
) -> CitationEligibilityDecision:
    manifest = request.manifest
    if not request.manifest_registry.verify(manifest):
        return _blocked("CITATION_SOURCE_BLOCKED")

    document = request.document_version
    if document.published_at is not None and document.published_at > request.research_as_of_time:
        return _blocked("CITATION_FUTURE_DATA")

    exact_document = (
        document.id == request.citation_document_version_id
        and request.verification.citation_id == request.citation_id
        and request.verification.status is CitationStatus.VALID
        and document.published_at is not None
        and document.security_id == manifest.security_id
        and document.source_payload_id == manifest.raw_payload_id
        and document.checksum == manifest.raw_payload_checksum
        and document.published_at == manifest.source_published_at
        and document.retrieved_at == manifest.retrieved_at
    )
    if not exact_document:
        return _blocked("CITATION_DOCUMENT_UNVERIFIED")
    return CitationEligibilityDecision(status="ELIGIBLE", warning_codes=())


def evaluate_claim_eligibility(
    request: EvidenceClaimRequest,
) -> ClaimEligibilityDecision:
    admitted_state = request.evidence_state in {
        ManualEvidenceState.APPROVED,
        ManualEvidenceState.PARTIAL,
        ManualEvidenceState.INGESTED,
    }
    manifest_verified = (
        request.manifest is not None
        and request.manifest_registry is not None
        and request.manifest_registry.verify(request.manifest)
    )
    if admitted_state and manifest_verified:
        return ClaimEligibilityDecision(status="ELIGIBLE", warning_codes=())

    limitation_only = (
        request.intended_use is not EvidenceUseTarget.CITATION
        and request.claim_type in {ClaimType.DATA_QUALITY, ClaimType.LIMITATION}
        and request.evidence_role is EvidenceRole.LIMITATION
    )
    if limitation_only:
        return ClaimEligibilityDecision(
            status="LIMITATION_ONLY",
            warning_codes=("UNVERIFIED_LIMITATION_ONLY",),
        )

    failure_by_target = {
        EvidenceUseTarget.CLAIM_SUPPORT: "UNVERIFIED_EVIDENCE_FORBIDDEN",
        EvidenceUseTarget.CITATION: "UNVERIFIED_CITATION_FORBIDDEN",
        EvidenceUseTarget.REPORT: "UNVERIFIED_REPORT_FORBIDDEN",
    }
    return ClaimEligibilityDecision(
        status="BLOCKED",
        warning_codes=(failure_by_target[request.intended_use],),
    )


def _blocked(code: str) -> CitationEligibilityDecision:
    return CitationEligibilityDecision(status="BLOCKED", warning_codes=(code,))
