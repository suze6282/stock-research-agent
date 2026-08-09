"""Assembly of bounded structural Research Packages."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ClaimSupportStatus,
    ClaimType,
    PackageSectionStatus,
    ResearchPackageStatus,
    ResearchSection,
    ResearchType,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchClaimRecord,
    ResearchEvidenceRecord,
    ResearchPackageRecord,
    ResearchPackageSection,
)


class ResearchPackageAssembler:
    """Organize validated IDs and states without generating narrative research."""

    def assemble(
        self,
        *,
        package_id: UUID,
        run_id: UUID,
        request_id: UUID,
        security_id: UUID,
        snapshot_id: UUID,
        research_as_of_time: datetime,
        research_type: ResearchType,
        policy_version: str,
        planner_version: str,
        tool_catalog_version: str,
        requested_sections: Sequence[ResearchSection],
        claims: Sequence[ResearchClaimRecord],
        evidence: Sequence[ResearchEvidenceRecord],
        blocked_capabilities: Sequence[str],
        warnings: Sequence[str],
        run_failed: bool,
        created_at: datetime,
    ) -> ResearchPackageRecord:
        requested = set(requested_sections)
        sections = tuple(_section(section, requested, claims) for section in ResearchSection)
        status = _package_status(sections, requested, run_failed)
        unsupported = tuple(
            sorted(
                (
                    claim.id
                    for claim in claims
                    if claim.support_status is ClaimSupportStatus.UNSUPPORTED
                ),
                key=str,
            )
        )
        conflicting = tuple(
            sorted(
                (
                    claim.id
                    for claim in claims
                    if claim.support_status is ClaimSupportStatus.CONFLICTING
                ),
                key=str,
            )
        )
        evidence_ids = tuple(sorted({item.id for item in evidence}, key=str))
        values = {
            "run_id": run_id,
            "request_id": request_id,
            "security_id": security_id,
            "snapshot_id": snapshot_id,
            "research_as_of_time": research_as_of_time,
            "research_type": research_type,
            "policy_version": policy_version,
            "planner_version": planner_version,
            "tool_catalog_version": tool_catalog_version,
            "evidence_version": "evidence-v1",
            "claim_version": "claim-v1",
            "package_version": "research-package-v1",
            "status": status,
            "sections": sections,
            "evidence_ids": evidence_ids,
            "unsupported_claim_ids": unsupported,
            "conflicting_claim_ids": conflicting,
            "blocked_capabilities": tuple(blocked_capabilities),
            "warnings": tuple(warnings),
        }
        return ResearchPackageRecord.model_validate(
            {
                "id": package_id,
                **values,
                "checksum": stable_checksum(values),
                "created_at": created_at,
            }
        )


def _section(
    section: ResearchSection,
    requested: set[ResearchSection],
    claims: Sequence[ResearchClaimRecord],
) -> ResearchPackageSection:
    if section not in requested:
        return ResearchPackageSection(
            section=section,
            status=PackageSectionStatus.NOT_REQUESTED,
            claim_ids=(),
        )
    selected = tuple(
        sorted(
            (claim for claim in claims if _claim_section(claim) is section),
            key=lambda claim: str(claim.id),
        )
    )
    if not selected:
        return ResearchPackageSection(
            section=section,
            status=PackageSectionStatus.NO_EVIDENCE,
            claim_ids=(),
        )
    support = {claim.support_status for claim in selected}
    warnings: tuple[str, ...] = ()
    if support == {ClaimSupportStatus.SUPPORTED}:
        status = PackageSectionStatus.PASS
    elif support.issubset({ClaimSupportStatus.BLOCKED}):
        status = PackageSectionStatus.BLOCKED
        warnings = ("BLOCKED_CLAIMS",)
    else:
        status = PackageSectionStatus.PARTIAL
        if ClaimSupportStatus.CONFLICTING in support:
            warnings = ("CONFLICTING_CLAIMS",)
        elif ClaimSupportStatus.UNSUPPORTED in support:
            warnings = ("UNSUPPORTED_CLAIMS",)
        elif ClaimSupportStatus.BLOCKED in support:
            warnings = ("BLOCKED_CLAIMS",)
        else:
            warnings = ("PARTIALLY_SUPPORTED_CLAIMS",)
    return ResearchPackageSection(
        section=section,
        status=status,
        claim_ids=tuple(claim.id for claim in selected),
        warning_codes=warnings,
    )


def _claim_section(claim: ResearchClaimRecord) -> ResearchSection:
    if claim.claim_type is ClaimType.IDENTITY:
        return ResearchSection.SECURITY_IDENTITY
    if claim.claim_type in {ClaimType.FINANCIAL_FACT, ClaimType.FINANCIAL_METRIC}:
        return ResearchSection.FINANCIAL_HEALTH
    if claim.claim_type is ClaimType.VALUATION_METRIC:
        return ResearchSection.VALUATION_SNAPSHOT
    if claim.claim_type is ClaimType.DOCUMENT_DISCLOSURE:
        if claim.statement_code.startswith("CATALYST_"):
            return ResearchSection.CATALYST_EVIDENCE
        if claim.statement_code.startswith("RISK_"):
            return ResearchSection.RISK_EVIDENCE
        return ResearchSection.DOCUMENT_EVIDENCE
    if claim.claim_type is ClaimType.CORPORATE_ACTION:
        return ResearchSection.CORPORATE_ACTIONS
    if claim.claim_type is ClaimType.DATA_QUALITY:
        return ResearchSection.DATA_QUALITY
    return ResearchSection.LIMITATIONS


def _package_status(
    sections: Sequence[ResearchPackageSection],
    requested: set[ResearchSection],
    run_failed: bool,
) -> ResearchPackageStatus:
    if run_failed:
        return ResearchPackageStatus.FAILED
    active = tuple(item.status for item in sections if item.section in requested)
    if active and all(status is PackageSectionStatus.PASS for status in active):
        return ResearchPackageStatus.COMPLETE
    if active and all(
        status in {PackageSectionStatus.BLOCKED, PackageSectionStatus.NO_EVIDENCE}
        for status in active
    ):
        return ResearchPackageStatus.BLOCKED
    return ResearchPackageStatus.PARTIAL
