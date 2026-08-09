"""Checksums and exact JSON-to-Markdown projection verification."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import ReportLocale
from stock_research_agent.domain.reports.markdown import (
    MARKDOWN_RENDERER_VERSION,
    DeterministicMarkdownRenderer,
)
from stock_research_agent.domain.reports.references import ReferenceEntry
from stock_research_agent.domain.reports.reporting import StructuredReportContent
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenReportContract,
    Version,
)


class ReportChecksumError(ValueError):
    """Stable deterministic checksum or projection failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReportChecksumContext(FrozenReportContract):
    """Semantic versions included in the aggregate content checksum."""

    schema_version: str = Field(pattern=r"^research-report-v[1-9][0-9]*$")
    template_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    renderer_version: Version
    markdown_renderer_version: Version
    locale: ReportLocale
    input_manifest_checksum: Checksum
    visible_references: tuple[ReferenceEntry, ...] = Field(max_length=5000)
    audit_report_id: UUID | None = None
    audit_created_at: AwareUtcDateTime | None = None


class ReportProjectionChecksums(FrozenReportContract):
    structured_checksum: Checksum
    markdown_checksum: Checksum
    content_checksum: Checksum


def structured_report_checksum(content: StructuredReportContent) -> str:
    """Hash the full canonical structured semantic payload."""

    return report_checksum(content)


def markdown_checksum(markdown_content: str) -> str:
    """Hash canonical Markdown text including its exact line endings."""

    return report_checksum(markdown_content)


def combined_report_checksum(
    structured_checksum: str,
    markdown_checksum_value: str,
    context: ReportChecksumContext,
) -> str:
    """Hash semantic versions, projections, manifest, and visible references."""

    return report_checksum(
        {
            "schema_version": context.schema_version,
            "structured_checksum": structured_checksum,
            "markdown_checksum": markdown_checksum_value,
            "template_name": context.template_name,
            "template_version": context.template_version,
            "renderer_version": context.renderer_version,
            "markdown_renderer_version": context.markdown_renderer_version,
            "locale": context.locale,
            "input_manifest_checksum": context.input_manifest_checksum,
            "visible_references": context.visible_references,
        }
    )


def verify_report_projection(
    content: StructuredReportContent,
    markdown_content: str,
    context: ReportChecksumContext,
    expected: ReportProjectionChecksums,
) -> ReportProjectionChecksums:
    """Require exact renderer parity and all three persisted checksums."""

    if content.schema_version != context.schema_version or content.locale is not context.locale:
        raise ReportChecksumError("REPORT_CHECKSUM_CONTEXT_MISMATCH")
    rendered = DeterministicMarkdownRenderer().render(content)
    if (
        context.markdown_renderer_version != MARKDOWN_RENDERER_VERSION
        or rendered.markdown_content != markdown_content
    ):
        raise ReportChecksumError("REPORT_MARKDOWN_PROJECTION_MISMATCH")
    actual_structured = structured_report_checksum(content)
    if actual_structured != expected.structured_checksum:
        raise ReportChecksumError("REPORT_STRUCTURED_CHECKSUM_MISMATCH")
    actual_markdown = markdown_checksum(markdown_content)
    if (
        actual_markdown != expected.markdown_checksum
        or rendered.markdown_checksum != actual_markdown
    ):
        raise ReportChecksumError("REPORT_MARKDOWN_CHECKSUM_MISMATCH")
    actual_combined = combined_report_checksum(
        actual_structured,
        actual_markdown,
        context,
    )
    if actual_combined != expected.content_checksum:
        raise ReportChecksumError("REPORT_CONTENT_CHECKSUM_MISMATCH")
    return ReportProjectionChecksums(
        structured_checksum=actual_structured,
        markdown_checksum=actual_markdown,
        content_checksum=actual_combined,
    )
