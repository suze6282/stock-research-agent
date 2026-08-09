"""Deterministic immutable research report version-chain rules."""

from __future__ import annotations

from stock_research_agent.domain.reports.reporting import (
    ResearchReportRecord,
    ResearchReportStatus,
)


class ReportVersionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def next_report_version(parent: ResearchReportRecord) -> int:
    return parent.report_version + 1


def validate_initial_report(report: ResearchReportRecord) -> None:
    if report.report_version != 1 or report.previous_report_id is not None:
        raise ReportVersionError("INITIAL_REPORT_CHAIN_INVALID")


def validate_report_successor(
    parent: ResearchReportRecord,
    child: ResearchReportRecord,
) -> None:
    if child.id == parent.id:
        raise ReportVersionError("REPORT_SELF_REFERENCE")
    if child.report_version != parent.report_version + 1:
        raise ReportVersionError("REPORT_VERSION_NOT_CONTIGUOUS")
    if child.previous_report_id != parent.id:
        raise ReportVersionError("REPORT_PARENT_MISMATCH")
    if child.report_generation_run_id != parent.report_generation_run_id:
        raise ReportVersionError("REPORT_GENERATION_RUN_MISMATCH")
    if child.security_id != parent.security_id:
        raise ReportVersionError("REPORT_SECURITY_MISMATCH")
    if child.snapshot_id != parent.snapshot_id:
        raise ReportVersionError("REPORT_SNAPSHOT_MISMATCH")
    if child.research_as_of_time != parent.research_as_of_time:
        raise ReportVersionError("REPORT_AS_OF_MISMATCH")
    if child.research_package_id != parent.research_package_id:
        raise ReportVersionError("REPORT_PACKAGE_MISMATCH")
    if child.input_manifest_checksum != parent.input_manifest_checksum:
        raise ReportVersionError("REPORT_MANIFEST_MISMATCH")
    if child.report_type is not parent.report_type:
        raise ReportVersionError("REPORT_TYPE_MISMATCH")
    if child.report_locale is not parent.report_locale:
        raise ReportVersionError("REPORT_LOCALE_MISMATCH")
    if (
        child.renderer_version != parent.renderer_version
        or child.template_name != parent.template_name
        or child.template_version != parent.template_version
    ):
        raise ReportVersionError("REPORT_RENDER_CONTRACT_MISMATCH")
    if child.status is ResearchReportStatus.PUBLISHABLE:
        _validate_publishable_content_identity(parent, child)


def _validate_publishable_content_identity(
    parent: ResearchReportRecord,
    child: ResearchReportRecord,
) -> None:
    fields = (
        "structured_content",
        "markdown_content",
        "structured_checksum",
        "markdown_checksum",
        "content_checksum",
        "claim_set_checksum",
        "evidence_set_checksum",
        "link_set_checksum",
        "citation_set_checksum",
    )
    if any(getattr(parent, field) != getattr(child, field) for field in fields):
        raise ReportVersionError("PUBLISHABLE_CONTENT_MISMATCH")
