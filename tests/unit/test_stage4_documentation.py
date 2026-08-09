from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from stock_research_agent.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS = PROJECT_ROOT / "docs"
REQUIRED_STAGE4_DOCS = (
    "data-providers.md",
    "data-ingestion.md",
    "data-snapshots.md",
    "tool-contracts.md",
    "raw-data-model.md",
)


@pytest.mark.parametrize("filename", REQUIRED_STAGE4_DOCS)
def test_stage4_operational_document_exists_and_is_substantive(filename: str) -> None:
    content = (DOCS / filename).read_text(encoding="utf-8")

    assert content.startswith("# ")
    assert len(content) >= 800


def test_stage4_docs_cover_required_data_and_evidence_boundaries() -> None:
    content = "\n".join(
        (DOCS / filename).read_text(encoding="utf-8") for filename in REQUIRED_STAGE4_DOCS
    )

    for required in (
        "Provider",
        "ProviderInstrumentMapping",
        "RawPayload",
        "BlobStorage",
        "research_as_of_time",
        "source_published_at",
        "COMPLETE",
        "PARTIAL",
        "FIXTURE",
        "OFFLINE",
        "NOT_LIVE",
        "READ_ONLY",
        "INTERNAL_WRITE",
        "TUSHARE_PRO",
        "SEC_ARCHIVES",
        "BLOCKED",
    ):
        assert required in content


def test_stage4_docs_preserve_historical_exclusions_without_rewriting_later_stages() -> None:
    paths = (
        *(DOCS / filename for filename in REQUIRED_STAGE4_DOCS),
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "AGENTS.md",
    )
    content = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for exclusion in (
        "财务标准化",
        "财务指标",
        "TTM",
        "估值",
        "RAG",
        "Agent",
        "MCP",
        "自动交易",
    ):
        assert exclusion in content
    assert "No Stage 4 work has started" not in content
    assert (
        "Those historical exclusions must not be used to deny the later completed stages" in content
    )


def test_readme_and_agents_describe_the_actual_stage4_boundary() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Stage 4" in readme
    assert "data ingest" in readme
    assert "data snapshot create" in readme
    assert "tools list" in readme
    assert "stage-10/controlled-live-evidence" in agents
    assert "stage-8-verifiable-report-reflection-design.md" in agents
    assert "API and registered Research Run query Tools are strictly read-only" in agents


def test_documented_stage4_cli_command_groups_exist() -> None:
    runner = CliRunner()

    for group in ("data", "tools"):
        result = runner.invoke(app, [group, "--help"])
        assert result.exit_code == 0

    data_help = runner.invoke(app, ["data", "--help"]).stdout
    for command in ("providers", "mappings", "ingest", "snapshot", "latest-close"):
        assert command in data_help


def test_updated_reference_docs_link_stage4_operational_guides() -> None:
    references = (
        "api.md",
        "database.md",
        "testing.md",
        "security-boundaries.md",
        "risk-register.md",
        "open-questions.md",
    )

    for filename in references:
        content = (DOCS / filename).read_text(encoding="utf-8")
        assert "Stage 4" in content
