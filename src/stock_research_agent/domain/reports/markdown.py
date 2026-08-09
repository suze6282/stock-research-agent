"""Pure Markdown projection from canonical structured report content."""

from __future__ import annotations

from pydantic import Field, field_validator

from stock_research_agent.domain.reports.canonical import (
    canonical_report_json,
    report_checksum,
)
from stock_research_agent.domain.reports.reporting import StructuredReportContent
from stock_research_agent.domain.reports.schemas import (
    Checksum,
    FrozenReportContract,
    Version,
)

MARKDOWN_RENDERER_VERSION = "deterministic-markdown-v1"


class RenderedMarkdown(FrozenReportContract):
    renderer_version: Version
    markdown_content: str = Field(min_length=1, max_length=1_048_576)
    markdown_checksum: Checksum

    @field_validator("markdown_content")
    @classmethod
    def require_canonical_line_endings(cls, value: str) -> str:
        if "\r" in value or not value.endswith("\n") or value.endswith("\n\n"):
            raise ValueError("Markdown must use LF and exactly one trailing newline")
        return value


class DeterministicMarkdownRenderer:
    """Project JSON content without source, repository, Tool, or model access."""

    def render(self, content: StructuredReportContent) -> RenderedMarkdown:
        lines = [
            f"# {_escape('Research Report')} "
            f"[{_escape(content.schema_version)}] "
            f"[{_escape(content.locale.value)}]",
            "",
        ]
        for section in content.sections:
            lines.extend(
                (
                    f"## {_escape(section.title)} "
                    f"[{_escape(section.section.value)}] "
                    f"[{_escape(section.status.value)}]",
                    "",
                )
            )
            for block in section.blocks:
                lines.append(
                    f"### {_escape(block.block_key)} "
                    f"[{_escape(block.block_type.value)}] "
                    f"[{_escape(block.status.value)}]"
                )
                if block.text is not None:
                    lines.append(_escape(block.text))
                for key in sorted(block.payload):
                    lines.append(
                        f"- {_escape(key)}: {_escape(canonical_report_json(block.payload[key]))}"
                    )
                lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
        markdown = "\n".join(lines) + "\n"
        return RenderedMarkdown(
            renderer_version=MARKDOWN_RENDERER_VERSION,
            markdown_content=markdown,
            markdown_checksum=report_checksum(markdown),
        )


def _escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
    escaped = escaped.replace("\n", "\\n")
    escaped = escaped.replace("<", "&lt;").replace(">", "&gt;")
    for marker in ("`", "*", "_", "[", "]", "#", "|"):
        escaped = escaped.replace(marker, f"\\{marker}")
    return escaped
