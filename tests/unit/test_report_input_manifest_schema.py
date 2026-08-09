from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.research_agent.enums import (
    PackageSectionStatus,
    ResearchMode,
    ResearchPackageStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)

PACKAGE_ID = UUID("10000000-0000-0000-0000-000000000001")
RUN_ID = UUID("10000000-0000-0000-0000-000000000002")
REQUEST_ID = UUID("10000000-0000-0000-0000-000000000003")
SECURITY_ID = UUID("10000000-0000-0000-0000-000000000004")
ISSUER_ID = UUID("10000000-0000-0000-0000-000000000005")
SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000006")
CLAIM_A = UUID("20000000-0000-0000-0000-000000000001")
CLAIM_B = UUID("20000000-0000-0000-0000-000000000002")
EVIDENCE_A = UUID("30000000-0000-0000-0000-000000000001")
CITATION_A = UUID("40000000-0000-0000-0000-000000000001")
LINK_A = UUID("50000000-0000-0000-0000-000000000001")
LINEAGE_A = UUID("60000000-0000-0000-0000-000000000001")
CHECKSUM = "a" * 64


def _report_types() -> SimpleNamespace:
    module_name = "stock_research_agent.domain.reports.schemas"
    try:
        module = import_module(module_name)
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report schemas are missing")
    return SimpleNamespace(
        ReportInputIssue=module.ReportInputIssue,
        ReportInputManifest=module.ReportInputManifest,
        ReportInputSectionState=module.ReportInputSectionState,
    )


def _manifest_values(report_types: SimpleNamespace) -> dict[str, object]:
    return {
        "research_package_id": PACKAGE_ID,
        "research_agent_run_id": RUN_ID,
        "research_request_id": REQUEST_ID,
        "security_id": SECURITY_ID,
        "issuer_id": ISSUER_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": datetime(2026, 7, 1, 8, tzinfo=UTC),
        "research_type": ResearchType.FULL_RESEARCH_PACKAGE,
        "research_mode": ResearchMode.REAL_RESEARCH,
        "package_status": ResearchPackageStatus.PARTIAL,
        "package_checksum": CHECKSUM,
        "policy_version": "controlled-offline-v1",
        "planner_version": "deterministic-template-v1",
        "tool_catalog_version": "b" * 80,
        "evidence_version": "evidence-v1",
        "claim_version": "claim-v1",
        "package_version": "research-package-v1",
        "claim_ids": (CLAIM_A, CLAIM_B),
        "evidence_ids": (EVIDENCE_A,),
        "link_ids": (LINK_A,),
        "citation_ids": (CITATION_A,),
        "lineage_ids": (LINEAGE_A,),
        "claims_checksum": CHECKSUM,
        "evidence_checksum": CHECKSUM,
        "links_checksum": CHECKSUM,
        "citations_checksum": CHECKSUM,
        "lineage_checksum": CHECKSUM,
        "section_states": (
            report_types.ReportInputSectionState(
                section=ResearchSection.DATA_QUALITY,
                status=PackageSectionStatus.PARTIAL,
                claim_ids=(CLAIM_A,),
                warning_codes=("COMPANY_BODY_MISSING",),
            ),
        ),
        "blocked_capabilities": ("COMPANY_BODY_MISSING",),
        "warnings": ("PARTIAL_RESEARCH_PACKAGE",),
        "data_quality_items": (
            report_types.ReportInputIssue(
                code="COMPANY_BODY_MISSING",
                claim_id=CLAIM_A,
                evidence_id=EVIDENCE_A,
            ),
        ),
        "limitation_items": (report_types.ReportInputIssue(code="INSUFFICIENT_FINANCIAL_FACTS"),),
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "manifest_schema_version": "report-input-manifest-v1",
        "canonical_payload_checksum": "c" * 64,
        "created_at": datetime(2026, 7, 26, 10, tzinfo=UTC),
    }


def test_manifest_accepts_complete_ordered_point_in_time_contract() -> None:
    report_types = _report_types()
    manifest = report_types.ReportInputManifest.model_validate(_manifest_values(report_types))

    assert manifest.research_package_id == PACKAGE_ID
    assert manifest.claim_ids == (CLAIM_A, CLAIM_B)
    assert manifest.evidence_ids == (EVIDENCE_A,)
    assert manifest.citation_ids == (CITATION_A,)
    assert manifest.synthetic_status is SyntheticStatus.REAL_VERIFIED
    assert manifest.manifest_schema_version == "report-input-manifest-v1"


def test_manifest_preserves_honest_empty_input_sets() -> None:
    report_types = _report_types()
    values = _manifest_values(report_types)
    values.update(
        {
            "claim_ids": (),
            "evidence_ids": (),
            "link_ids": (),
            "citation_ids": (),
            "lineage_ids": (),
            "section_states": (
                report_types.ReportInputSectionState(
                    section=ResearchSection.DATA_QUALITY,
                    status=PackageSectionStatus.NO_EVIDENCE,
                    claim_ids=(),
                    warning_codes=(),
                ),
            ),
            "data_quality_items": (),
            "limitation_items": (),
        }
    )

    manifest = report_types.ReportInputManifest.model_validate(values)

    assert manifest.claim_ids == ()
    assert manifest.evidence_ids == ()
    assert manifest.citation_ids == ()


@pytest.mark.parametrize(
    "field",
    ["claim_ids", "evidence_ids", "link_ids", "citation_ids", "lineage_ids"],
)
def test_manifest_rejects_unsorted_or_duplicate_record_ids(
    field: str,
) -> None:
    report_types = _report_types()
    values = _manifest_values(report_types)
    high = UUID("ffffffff-0000-0000-0000-000000000001")
    low = UUID("00000000-0000-0000-0000-000000000001")
    values[field] = (high, low)

    with pytest.raises(ValidationError, match="stable sorted unique"):
        report_types.ReportInputManifest.model_validate(values)

    values[field] = (low, low)
    with pytest.raises(ValidationError, match="stable sorted unique"):
        report_types.ReportInputManifest.model_validate(values)


def test_manifest_rejects_unsorted_codes_and_issues() -> None:
    report_types = _report_types()
    values = _manifest_values(report_types)
    values["warnings"] = ("Z_WARNING", "A_WARNING")
    with pytest.raises(ValidationError, match="stable sorted unique"):
        report_types.ReportInputManifest.model_validate(values)

    values = _manifest_values(report_types)
    values["limitation_items"] = (
        report_types.ReportInputIssue(code="Z_LIMIT"),
        report_types.ReportInputIssue(code="A_LIMIT"),
    )
    with pytest.raises(ValidationError, match="stable sorted unique"):
        report_types.ReportInputManifest.model_validate(values)


def test_manifest_rejects_naive_times_bad_checksums_and_unknown_fields() -> None:
    report_types = _report_types()
    values = _manifest_values(report_types)
    values["research_as_of_time"] = datetime(2026, 7, 1, 8)
    with pytest.raises(ValidationError, match="timezone-aware"):
        report_types.ReportInputManifest.model_validate(values)

    values = _manifest_values(report_types)
    values["canonical_payload_checksum"] = "not-a-checksum"
    with pytest.raises(ValidationError):
        report_types.ReportInputManifest.model_validate(values)

    values = _manifest_values(report_types)
    values["unexpected"] = "forbidden"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        report_types.ReportInputManifest.model_validate(values)


def test_manifest_and_issue_records_are_frozen() -> None:
    report_types = _report_types()
    manifest = report_types.ReportInputManifest.model_validate(_manifest_values(report_types))

    with pytest.raises(ValidationError, match="Instance is frozen"):
        manifest.package_checksum = "d" * 64
    with pytest.raises(ValidationError, match="Instance is frozen"):
        manifest.data_quality_items[0].code = "REPLACED"
