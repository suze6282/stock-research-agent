"""Fail-closed verification for exact Stage 7 report inputs."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from stock_research_agent.domain.documents.citations import create_citation
from stock_research_agent.domain.documents.enums import CitationStatus
from stock_research_agent.domain.documents.schemas import CreateCitationRequest
from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.schemas import (
    PersistedReportInput,
    ReportInputIssue,
    ReportInputManifest,
    ReportInputSectionState,
    VerifiedReportInput,
)
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    EvidenceStatus,
    EvidenceType,
    ResearchMode,
    ResearchRunStatus,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchPackageRecord,
    ResearchRequestRecord,
)


class ReportInputValidationError(RuntimeError):
    """Safe, stable-code report input verification failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_report_input_manifest(
    report_input: PersistedReportInput,
) -> ReportInputManifest:
    """Validate and freeze the exact ordered input records for a report."""

    _validate_input(report_input)
    claim_ids = _sorted_ids(item.id for item in report_input.claims)
    evidence_ids = _sorted_ids(item.id for item in report_input.evidence)
    link_ids = _sorted_ids(item.id for item in report_input.links)
    citation_ids = _sorted_ids(item.id for item in report_input.citations)
    lineage_ids = _lineage_ids(report_input)
    package = report_input.package
    return ReportInputManifest(
        research_package_id=package.id,
        research_agent_run_id=package.run_id,
        research_request_id=package.request_id,
        security_id=package.security_id,
        issuer_id=report_input.issuer_id,
        snapshot_id=package.snapshot_id,
        research_as_of_time=package.research_as_of_time,
        research_type=package.research_type,
        research_mode=report_input.request.research_mode,
        package_status=package.status,
        package_checksum=package.checksum,
        policy_version=package.policy_version,
        planner_version=package.planner_version,
        tool_catalog_version=package.tool_catalog_version,
        evidence_version=package.evidence_version,
        claim_version=package.claim_version,
        package_version=package.package_version,
        claim_ids=claim_ids,
        evidence_ids=evidence_ids,
        link_ids=link_ids,
        citation_ids=citation_ids,
        lineage_ids=lineage_ids,
        claims_checksum=report_checksum(report_input.claims),
        evidence_checksum=report_checksum(report_input.evidence),
        links_checksum=report_checksum(report_input.links),
        citations_checksum=report_checksum(
            {
                "citations": report_input.citations,
                "verifications": report_input.citation_verifications,
            }
        ),
        lineage_checksum=report_checksum(_lineage_basis(report_input)),
        section_states=tuple(
            ReportInputSectionState(
                section=item.section,
                status=item.status,
                claim_ids=item.claim_ids,
                warning_codes=item.warning_codes,
            )
            for item in package.sections
        ),
        blocked_capabilities=tuple(sorted(set(package.blocked_capabilities))),
        warnings=tuple(sorted(set(package.warnings))),
        data_quality_items=tuple(
            ReportInputIssue(code=code) for code in sorted(set(package.warnings))
        ),
        limitation_items=tuple(
            ReportInputIssue(code=code) for code in sorted(set(package.blocked_capabilities))
        ),
        synthetic_status=_aggregate_synthetic_status(report_input),
        manifest_schema_version="report-input-manifest-v1",
        canonical_payload_checksum=_input_checksum(report_input),
        created_at=package.created_at,
    )


def validate_report_input_manifest(
    manifest: ReportInputManifest,
    report_input: PersistedReportInput,
) -> VerifiedReportInput:
    """Rebuild an input manifest and reject any persisted or manifest drift."""

    rebuilt = build_report_input_manifest(report_input)
    if (
        manifest.claim_ids != rebuilt.claim_ids
        or manifest.evidence_ids != rebuilt.evidence_ids
        or manifest.link_ids != rebuilt.link_ids
        or manifest.citation_ids != rebuilt.citation_ids
        or manifest.lineage_ids != rebuilt.lineage_ids
    ):
        _fail("MANIFEST_RECORD_SET_MISMATCH")
    if manifest.canonical_payload_checksum != rebuilt.canonical_payload_checksum:
        _fail("MANIFEST_CHECKSUM_MISMATCH")
    if manifest != rebuilt:
        _fail("MANIFEST_METADATA_MISMATCH")
    return VerifiedReportInput(manifest=manifest, input=report_input)


def _validate_input(report_input: PersistedReportInput) -> None:
    package = report_input.package
    run = report_input.run
    request = report_input.request
    if package.run_id != run.id:
        _fail("PACKAGE_RUN_MISMATCH")
    if package.request_id != request.id or run.request_id != request.id:
        _fail("REQUEST_RUN_MISMATCH")
    if run.security_id != package.security_id:
        _fail("RUN_SECURITY_MISMATCH")
    if request.resolved_security_id != package.security_id:
        _fail("REQUEST_SECURITY_MISMATCH")
    if run.snapshot_id != package.snapshot_id or request.snapshot_id != package.snapshot_id:
        _fail("RUN_SNAPSHOT_MISMATCH")
    if (
        run.research_as_of_time != package.research_as_of_time
        or request.research_as_of_time != package.research_as_of_time
    ):
        _fail("RUN_AS_OF_MISMATCH")
    if request.research_type is not package.research_type:
        _fail("RESEARCH_TYPE_MISMATCH")
    if package.status.value == "FAILED":
        _fail("RESEARCH_PACKAGE_FAILED")
    if (
        run.policy_version != package.policy_version
        or request.policy_version != package.policy_version
    ):
        _fail("POLICY_VERSION_MISMATCH")
    if (
        run.planner_version != package.planner_version
        or request.planner_version != package.planner_version
    ):
        _fail("PLANNER_VERSION_MISMATCH")
    if (
        run.tool_catalog_version != package.tool_catalog_version
        or request.tool_catalog_version != package.tool_catalog_version
    ):
        _fail("TOOL_CATALOG_VERSION_MISMATCH")
    if run.status not in {
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.BLOCKED,
    }:
        _fail("RESEARCH_RUN_NOT_SEALED")
    _validate_package_checksum(package)
    _validate_request_checksum(request)
    _validate_claims(report_input)
    _validate_evidence(report_input)
    _validate_links(report_input)
    _validate_citations(report_input)
    _validate_issuer_identity(report_input)


def _validate_package_checksum(package: ResearchPackageRecord) -> None:
    values = package.model_dump(
        mode="python",
        exclude={"id", "checksum", "created_at"},
    )
    if stable_checksum(values) != package.checksum:
        _fail("PACKAGE_CHECKSUM_MISMATCH")


def _validate_request_checksum(request: ResearchRequestRecord) -> None:
    values = request.model_dump(
        mode="python",
        exclude={"id", "request_checksum", "created_at"},
    )
    if stable_checksum(values) != request.request_checksum:
        _fail("REQUEST_CHECKSUM_MISMATCH")


def _validate_claims(report_input: PersistedReportInput) -> None:
    claims = report_input.claims
    if _ids_in_input_order(item.id for item in claims) != _sorted_ids(item.id for item in claims):
        _fail("UNSTABLE_CLAIM_ORDER")
    expected = {
        claim_id for section in report_input.package.sections for claim_id in section.claim_ids
    }
    actual = {item.id for item in claims}
    if any(item.lifecycle_status is not ClaimLifecycleStatus.VALIDATED for item in claims):
        _fail("CLAIM_NOT_VALIDATED")
    if actual - expected:
        _fail("UNUSED_CLAIM")
    if expected - actual:
        _fail("CLAIM_RECORD_MISSING")
    for claim in claims:
        if claim.run_id != report_input.run.id:
            _fail("CLAIM_RUN_MISMATCH")
        if (
            claim.as_of_time is not None
            and claim.as_of_time > report_input.package.research_as_of_time
        ):
            _fail("FUTURE_DATA")
    unsupported = {
        item.id for item in claims if item.support_status is ClaimSupportStatus.UNSUPPORTED
    }
    conflicting = {
        item.id for item in claims if item.support_status is ClaimSupportStatus.CONFLICTING
    }
    if set(report_input.package.unsupported_claim_ids) != unsupported:
        _fail("UNSUPPORTED_CLAIM_SET_MISMATCH")
    if set(report_input.package.conflicting_claim_ids) != conflicting:
        _fail("CONFLICTING_CLAIM_SET_MISMATCH")


def _validate_evidence(report_input: PersistedReportInput) -> None:
    evidence = report_input.evidence
    if _ids_in_input_order(item.id for item in evidence) != _sorted_ids(
        item.id for item in evidence
    ):
        _fail("UNSTABLE_EVIDENCE_ORDER")
    expected = set(report_input.package.evidence_ids)
    actual = {item.id for item in evidence}
    if actual - expected:
        _fail("UNUSED_EVIDENCE")
    if expected - actual:
        _fail("EVIDENCE_RECORD_MISSING")
    for item in evidence:
        if item.run_id != report_input.run.id:
            _fail("EVIDENCE_RUN_MISMATCH")
        if item.security_id != report_input.package.security_id:
            _fail("EVIDENCE_SECURITY_MISMATCH")
        if item.snapshot_id != report_input.package.snapshot_id:
            _fail("EVIDENCE_SNAPSHOT_MISMATCH")
        if item.research_as_of_time != report_input.package.research_as_of_time:
            _fail("EVIDENCE_AS_OF_MISMATCH")
        if (
            item.published_at is not None
            and item.published_at > report_input.package.research_as_of_time
        ):
            _fail("FUTURE_DATA")
        if (
            report_input.request.research_mode is ResearchMode.REAL_RESEARCH
            and item.synthetic_status
            in {SyntheticStatus.SYNTHETIC_TEST_ONLY, SyntheticStatus.UNKNOWN}
        ):
            _fail("SYNTHETIC_EVIDENCE_FOR_REAL_RUN")


def _validate_links(report_input: PersistedReportInput) -> None:
    claim_ids = {item.id for item in report_input.claims}
    evidence_ids = {item.id for item in report_input.evidence}
    linked_claim_ids: set[UUID] = set()
    seen_pairs: set[tuple[UUID, UUID]] = set()
    for link in report_input.links:
        if link.run_id != report_input.run.id:
            _fail("CLAIM_EVIDENCE_LINK_RUN_MISMATCH")
        if link.claim_id not in claim_ids or link.evidence_id not in evidence_ids:
            _fail("CLAIM_EVIDENCE_LINK_UNREACHABLE")
        pair = (link.claim_id, link.evidence_id)
        if pair in seen_pairs:
            _fail("DUPLICATE_CLAIM_EVIDENCE_LINK")
        seen_pairs.add(pair)
        linked_claim_ids.add(link.claim_id)
    requires_evidence = {
        item.id
        for item in report_input.claims
        if item.support_status
        in {
            ClaimSupportStatus.SUPPORTED,
            ClaimSupportStatus.PARTIALLY_SUPPORTED,
            ClaimSupportStatus.CONFLICTING,
        }
    }
    if requires_evidence - linked_claim_ids:
        _fail("CLAIM_EVIDENCE_LINK_MISSING")


def _validate_citations(report_input: PersistedReportInput) -> None:
    citation_by_id = {item.id: item for item in report_input.citations}
    verification_by_id = {item.citation_id: item for item in report_input.citation_verifications}
    if len(citation_by_id) != len(report_input.citations):
        _fail("DUPLICATE_CITATION")
    if len(verification_by_id) != len(report_input.citation_verifications):
        _fail("DUPLICATE_CITATION_VERIFICATION")
    required = {item.citation_id for item in report_input.evidence if item.citation_id is not None}
    if set(citation_by_id) - required:
        _fail("UNUSED_CITATION")
    if required - set(citation_by_id):
        _fail("CITATION_RECORD_MISSING")
    if set(verification_by_id) != required:
        _fail("CITATION_VERIFICATION_SET_MISMATCH")
    for evidence in report_input.evidence:
        if evidence.citation_id is None:
            continue
        citation = citation_by_id[evidence.citation_id]
        verification = verification_by_id[evidence.citation_id]
        if verification.status is not CitationStatus.VALID:
            _fail("INVALID_CITATION")
        request = CreateCitationRequest.model_validate(
            citation.model_dump(
                mode="python",
                exclude={"id", "created_at", "locator_checksum"},
            )
        )
        if create_citation(request).locator_checksum != citation.locator_checksum:
            _fail("CITATION_CHECKSUM_MISMATCH")
        if evidence.evidence_type is EvidenceType.DOCUMENT_CITATION_EVIDENCE and (
            evidence.status is not EvidenceStatus.VALID
            or evidence.source_checksum != citation.document_checksum
        ):
            _fail("CITATION_EVIDENCE_MISMATCH")


def _validate_issuer_identity(report_input: PersistedReportInput) -> None:
    matching = tuple(
        item
        for item in report_input.evidence
        if item.evidence_type is EvidenceType.SECURITY_MASTER_EVIDENCE
        and item.status is EvidenceStatus.VALID
        and item.security_id == report_input.package.security_id
        and item.payload.get("security_id") == str(report_input.package.security_id)
        and item.payload.get("issuer_id") == str(report_input.issuer_id)
    )
    if len(matching) != 1:
        _fail("ISSUER_IDENTITY_MISMATCH")


def _input_checksum(report_input: PersistedReportInput) -> str:
    return report_checksum(report_input)


def _lineage_ids(report_input: PersistedReportInput) -> tuple[UUID, ...]:
    values: set[UUID] = set()
    for item in report_input.evidence:
        if item.calculation_run_id is not None:
            values.add(item.calculation_run_id)
        values.update(item.calculation_input_ids)
    return tuple(sorted(values, key=str))


def _lineage_basis(report_input: PersistedReportInput) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "evidence_id": item.id,
            "source_record_type": item.source_record_type,
            "source_record_id": item.source_record_id,
            "source_checksum": item.source_checksum,
            "published_at": item.published_at,
            "citation_id": item.citation_id,
            "calculation_run_id": item.calculation_run_id,
            "calculation_input_ids": item.calculation_input_ids,
            "formula_version": item.formula_version,
        }
        for item in report_input.evidence
    )


def _aggregate_synthetic_status(
    report_input: PersistedReportInput,
) -> SyntheticStatus:
    statuses = {item.synthetic_status for item in report_input.evidence}
    if not statuses or statuses == {SyntheticStatus.REAL_VERIFIED}:
        return SyntheticStatus.REAL_VERIFIED
    if SyntheticStatus.SYNTHETIC_TEST_ONLY in statuses:
        return SyntheticStatus.SYNTHETIC_TEST_ONLY
    if SyntheticStatus.UNKNOWN in statuses:
        return SyntheticStatus.UNKNOWN
    return SyntheticStatus.FIXTURE_REAL_EXCERPT


def _sorted_ids(values: Iterable[UUID]) -> tuple[UUID, ...]:
    return tuple(sorted(set(values), key=str))


def _ids_in_input_order(values: Iterable[UUID]) -> tuple[UUID, ...]:
    return tuple(values)


def _fail(code: str) -> None:
    raise ReportInputValidationError(code)
