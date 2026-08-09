from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from uuid import UUID

import pytest

from stock_research_agent.domain.documents.citations import create_citation
from stock_research_agent.domain.documents.enums import CitationStatus, LocatorType
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    CitationVerification,
    CreateCitationRequest,
)
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    ResearchRunStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.packages import (
    ResearchPackageAssembler,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ResearchAgentRunRecord,
    ResearchClaimRecord,
    ResearchEvidenceRecord,
    ResearchRequestCreate,
    ResearchRequestRecord,
    RunBudget,
)

NOW = datetime(2026, 7, 26, 8, tzinfo=UTC)
PACKAGE_ID = UUID("10000000-0000-0000-0000-000000000001")
RUN_ID = UUID("10000000-0000-0000-0000-000000000002")
REQUEST_ID = UUID("10000000-0000-0000-0000-000000000003")
SECURITY_ID = UUID("10000000-0000-0000-0000-000000000004")
ISSUER_ID = UUID("10000000-0000-0000-0000-000000000005")
SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000006")
CLAIM_ID = UUID("20000000-0000-0000-0000-000000000001")
EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000001")
IDENTITY_CLAIM_ID = UUID("20000000-0000-0000-0000-000000000002")
IDENTITY_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000002")
CITATION_ID = UUID("40000000-0000-0000-0000-000000000001")
LINK_ID = UUID("50000000-0000-0000-0000-000000000001")
IDENTITY_LINK_ID = UUID("50000000-0000-0000-0000-000000000002")
CHECKSUM = "a" * 64
CATALOG_VERSION = "tool-catalog-v1:" + "b" * 64


def _report_types() -> SimpleNamespace:
    schemas = import_module("stock_research_agent.domain.reports.schemas")
    try:
        verification = import_module("stock_research_agent.domain.reports.input_verification")
        persisted = schemas.PersistedReportInput
        verified = schemas.VerifiedReportInput
    except (AttributeError, ModuleNotFoundError):
        pytest.fail("Stage 8 report input verification is missing")
    return SimpleNamespace(
        PersistedReportInput=persisted,
        VerifiedReportInput=verified,
        ReportInputValidationError=verification.ReportInputValidationError,
        build=verification.build_report_input_manifest,
        validate=verification.validate_report_input_manifest,
    )


def _request() -> ResearchRequestRecord:
    command = ResearchRequestCreate(
        security_query="NASDAQ:MU",
        research_type=ResearchType.FULL_RESEARCH_PACKAGE,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        requested_sections=(
            ResearchSection.SECURITY_IDENTITY,
            ResearchSection.DOCUMENT_EVIDENCE,
        ),
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
    )
    basis = {
        **command.model_dump(mode="python"),
        "normalized_security_query": "NASDAQ:MU",
        "resolved_security_id": SECURITY_ID,
        "tool_catalog_version": CATALOG_VERSION,
        "tool_catalog_checksum": "b" * 64,
    }
    return ResearchRequestRecord.model_validate(
        {
            **basis,
            "id": REQUEST_ID,
            "request_checksum": stable_checksum(basis),
            "created_at": NOW,
        }
    )


def _run() -> ResearchAgentRunRecord:
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=REQUEST_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        status=ResearchRunStatus.COMPLETED,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        tool_catalog_checksum="b" * 64,
        idempotency_key="c" * 64,
        budget=RunBudget(
            max_steps=20,
            max_tool_calls=50,
            max_calls_per_tool=5,
            max_retries_per_step=1,
            max_duration_seconds=300,
            model_token_budget=0,
            consumed_steps=8,
            consumed_tool_calls=10,
            consumed_model_tokens=0,
            elapsed_seconds=Decimal("1.25"),
        ),
        created_at=NOW,
        updated_at=NOW,
        terminal_at=NOW,
    )


def _citation() -> CitationAnchorRecord:
    excerpt = "Verified synthetic-neutral disclosure."
    request = CreateCitationRequest(
        document_version_id=UUID("60000000-0000-0000-0000-000000000001"),
        parse_run_id=UUID("60000000-0000-0000-0000-000000000002"),
        chunk_id=UUID("60000000-0000-0000-0000-000000000003"),
        locator_type=LocatorType.TEXT_OFFSET_RANGE,
        start_offset=0,
        end_offset=len(excerpt),
        excerpt=excerpt,
        excerpt_checksum=hashlib.sha256(excerpt.encode()).hexdigest(),
        canonical_text_checksum="d" * 64,
        document_checksum="e" * 64,
        parser_version="text-parser-v1",
        sanitizer_version="document-sanitizer-v1",
    )
    draft = create_citation(request)
    return CitationAnchorRecord.model_validate(
        {**draft.model_dump(mode="python"), "id": CITATION_ID, "created_at": NOW}
    )


def _evidence(**updates: object) -> ResearchEvidenceRecord:
    values: dict[str, object] = {
        "id": EVIDENCE_ID,
        "run_id": RUN_ID,
        "observation_id": UUID("30000000-0000-0000-0000-000000000002"),
        "evidence_type": EvidenceType.DOCUMENT_CITATION_EVIDENCE,
        "status": EvidenceStatus.VALID,
        "schema_version": "evidence-v1",
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "source_record_type": "document_version",
        "source_record_id": UUID("60000000-0000-0000-0000-000000000001"),
        "source_checksum": "e" * 64,
        "published_at": NOW - timedelta(days=1),
        "citation_id": CITATION_ID,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "payload": {"disclosure_code": "VERIFIED_DISCLOSURE"},
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchEvidenceRecord.model_validate(values)


def _claim(**updates: object) -> ResearchClaimRecord:
    values: dict[str, object] = {
        "id": CLAIM_ID,
        "run_id": RUN_ID,
        "claim_type": ClaimType.DOCUMENT_DISCLOSURE,
        "lifecycle_status": ClaimLifecycleStatus.VALIDATED,
        "support_status": ClaimSupportStatus.SUPPORTED,
        "statement_code": "VERIFIED_DISCLOSURE",
        "builder_version": "deterministic-claim-builder-v1",
        "validator_version": "claim-support-validator-v1",
        "created_at": NOW,
        "completed_at": NOW,
    }
    values.update(updates)
    return ResearchClaimRecord.model_validate(values)


def _identity_claim() -> ResearchClaimRecord:
    return ResearchClaimRecord(
        id=IDENTITY_CLAIM_ID,
        run_id=RUN_ID,
        claim_type=ClaimType.IDENTITY,
        lifecycle_status=ClaimLifecycleStatus.VALIDATED,
        support_status=ClaimSupportStatus.SUPPORTED,
        statement_code="SECURITY_IDENTITY",
        builder_version="deterministic-claim-builder-v1",
        validator_version="claim-support-validator-v1",
        created_at=NOW,
        completed_at=NOW,
    )


def _identity_evidence(**updates: object) -> ResearchEvidenceRecord:
    values: dict[str, object] = {
        "id": IDENTITY_EVIDENCE_ID,
        "run_id": RUN_ID,
        "observation_id": UUID("30000000-0000-0000-0000-000000000003"),
        "evidence_type": EvidenceType.SECURITY_MASTER_EVIDENCE,
        "status": EvidenceStatus.VALID,
        "schema_version": "evidence-v1",
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "source_record_type": "security",
        "source_record_id": SECURITY_ID,
        "source_checksum": "f" * 64,
        "published_at": NOW - timedelta(days=2),
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "payload": {
            "security_id": str(SECURITY_ID),
            "issuer_id": str(ISSUER_ID),
            "issuer": "Micron Technology, Inc.",
            "symbol": "MU",
            "exchange": "XNAS",
        },
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchEvidenceRecord.model_validate(values)


def _link(**updates: object) -> ClaimEvidenceLinkRecord:
    values: dict[str, object] = {
        "id": LINK_ID,
        "run_id": RUN_ID,
        "claim_id": CLAIM_ID,
        "evidence_id": EVIDENCE_ID,
        "role": EvidenceRole.PRIMARY,
        "created_at": NOW,
    }
    values.update(updates)
    return ClaimEvidenceLinkRecord.model_validate(values)


def _identity_link() -> ClaimEvidenceLinkRecord:
    return ClaimEvidenceLinkRecord(
        id=IDENTITY_LINK_ID,
        run_id=RUN_ID,
        claim_id=IDENTITY_CLAIM_ID,
        evidence_id=IDENTITY_EVIDENCE_ID,
        role=EvidenceRole.PRIMARY,
        created_at=NOW,
    )


def _bundle(report_types: SimpleNamespace, **updates: object) -> object:
    request = _request()
    run = _run()
    claim = _claim()
    identity_claim = _identity_claim()
    evidence = _evidence()
    identity_evidence = _identity_evidence()
    package = ResearchPackageAssembler().assemble(
        package_id=PACKAGE_ID,
        run_id=RUN_ID,
        request_id=REQUEST_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        research_type=ResearchType.FULL_RESEARCH_PACKAGE,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version=CATALOG_VERSION,
        requested_sections=(
            ResearchSection.SECURITY_IDENTITY,
            ResearchSection.DOCUMENT_EVIDENCE,
        ),
        claims=(claim, identity_claim),
        evidence=(evidence, identity_evidence),
        blocked_capabilities=(),
        warnings=(),
        run_failed=False,
        created_at=NOW,
    )
    values: dict[str, object] = {
        "package": package,
        "run": run,
        "request": request,
        "issuer_id": ISSUER_ID,
        "claims": (claim, identity_claim),
        "evidence": (evidence, identity_evidence),
        "links": (_link(), _identity_link()),
        "citations": (_citation(),),
        "citation_verifications": (
            CitationVerification(
                status=CitationStatus.VALID,
                citation_id=CITATION_ID,
            ),
        ),
    }
    values.update(updates)
    return report_types.PersistedReportInput.model_validate(values)


def test_build_and_validate_manifest_freezes_exact_ordered_input_set() -> None:
    report_types = _report_types()
    bundle = _bundle(report_types)

    manifest = report_types.build(bundle)
    result = report_types.validate(manifest, bundle)

    assert isinstance(result, report_types.VerifiedReportInput)
    assert result.manifest == manifest
    assert result.input == bundle
    assert manifest.claim_ids == (CLAIM_ID, IDENTITY_CLAIM_ID)
    assert manifest.evidence_ids == (EVIDENCE_ID, IDENTITY_EVIDENCE_ID)
    assert manifest.link_ids == (LINK_ID, IDENTITY_LINK_ID)
    assert manifest.citation_ids == (CITATION_ID,)
    assert manifest.claim_version == "claim-v1"
    assert manifest.evidence_version == "evidence-v1"
    assert manifest.package_version == "research-package-v1"
    assert manifest.research_mode.value == "REAL_RESEARCH"
    assert len(manifest.claims_checksum) == 64
    assert len(manifest.evidence_checksum) == 64
    assert len(manifest.links_checksum) == 64
    assert len(manifest.citations_checksum) == 64
    assert len(manifest.lineage_checksum) == 64
    assert len(manifest.section_states) == len(ResearchSection)
    assert len(manifest.canonical_payload_checksum) == 64


def test_repeated_bundle_builds_have_stable_checksum_and_created_time() -> None:
    report_types = _report_types()
    bundle = _bundle(report_types)

    first = report_types.build(bundle)
    second = report_types.build(bundle)

    assert first == second
    assert first.created_at == bundle.package.created_at
    assert first.canonical_payload_checksum == second.canonical_payload_checksum


def test_build_manifest_requires_matching_validated_issuer_identity_evidence() -> None:
    report_types = _report_types()
    bundle = _bundle(report_types)
    invalid_identity = bundle.evidence[1].model_copy(
        update={
            "payload": {
                **bundle.evidence[1].payload,
                "issuer_id": str(UUID(int=999)),
            }
        }
    )

    with pytest.raises(report_types.ReportInputValidationError) as raised:
        report_types.build(
            bundle.model_copy(update={"evidence": (bundle.evidence[0], invalid_identity)})
        )

    assert raised.value.code == "ISSUER_IDENTITY_MISMATCH"


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (
            lambda bundle: bundle.model_copy(
                update={"run": bundle.run.model_copy(update={"security_id": UUID(int=999)})}
            ),
            "RUN_SECURITY_MISMATCH",
        ),
        (
            lambda bundle: bundle.model_copy(
                update={
                    "evidence": (
                        bundle.evidence[0].model_copy(update={"snapshot_id": UUID(int=999)}),
                        bundle.evidence[1],
                    )
                }
            ),
            "EVIDENCE_SNAPSHOT_MISMATCH",
        ),
        (
            lambda bundle: bundle.model_copy(
                update={
                    "evidence": (
                        bundle.evidence[0].model_copy(
                            update={"published_at": NOW + timedelta(seconds=1)}
                        ),
                        bundle.evidence[1],
                    )
                }
            ),
            "FUTURE_DATA",
        ),
        (
            lambda bundle: bundle.model_copy(
                update={
                    "evidence": (
                        bundle.evidence[0].model_copy(
                            update={"synthetic_status": SyntheticStatus.SYNTHETIC_TEST_ONLY}
                        ),
                        bundle.evidence[1],
                    )
                }
            ),
            "SYNTHETIC_EVIDENCE_FOR_REAL_RUN",
        ),
        (
            lambda bundle: bundle.model_copy(update={"links": ()}),
            "CLAIM_EVIDENCE_LINK_MISSING",
        ),
        (
            lambda bundle: bundle.model_copy(
                update={
                    "citation_verifications": (
                        CitationVerification(
                            status=CitationStatus.INVALID,
                            citation_id=CITATION_ID,
                        ),
                    )
                }
            ),
            "INVALID_CITATION",
        ),
        (
            lambda bundle: bundle.model_copy(
                update={
                    "claims": (
                        *bundle.claims,
                        bundle.claims[0].model_copy(
                            update={"id": UUID("ffffffff-0000-0000-0000-000000000001")}
                        ),
                    )
                }
            ),
            "UNUSED_CLAIM",
        ),
        (
            lambda bundle: bundle.model_copy(
                update={"package": bundle.package.model_copy(update={"checksum": "f" * 64})}
            ),
            "PACKAGE_CHECKSUM_MISMATCH",
        ),
    ],
)
def test_build_manifest_fails_closed_with_stable_validation_codes(
    mutator: object,
    code: str,
) -> None:
    report_types = _report_types()
    bundle = _bundle(report_types)
    invalid = mutator(bundle)

    with pytest.raises(report_types.ReportInputValidationError) as raised:
        report_types.build(invalid)

    assert raised.value.code == code
    assert str(raised.value) == code


def test_validate_rejects_manifest_record_set_or_checksum_tampering() -> None:
    report_types = _report_types()
    bundle = _bundle(report_types)
    manifest = report_types.build(bundle)

    with pytest.raises(report_types.ReportInputValidationError) as raised:
        report_types.validate(manifest.model_copy(update={"claim_ids": ()}), bundle)
    assert raised.value.code == "MANIFEST_RECORD_SET_MISMATCH"

    with pytest.raises(report_types.ReportInputValidationError) as raised:
        report_types.validate(
            manifest.model_copy(update={"canonical_payload_checksum": "f" * 64}),
            bundle,
        )
    assert raised.value.code == "MANIFEST_CHECKSUM_MISMATCH"
