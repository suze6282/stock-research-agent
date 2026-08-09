from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_required_stage5_financial_documents_cover_contract_boundaries() -> None:
    required = (
        "docs/financial-concepts.md",
        "docs/financial-mapping.md",
        "docs/financial-periods.md",
        "docs/financial-normalization.md",
        "docs/financial-formulas.md",
        "docs/financial-metrics.md",
        "docs/metric-lineage.md",
        "docs/tool-contracts.md",
        "docs/api.md",
        "docs/database.md",
        "docs/testing.md",
        "docs/risk-register.md",
        "docs/open-questions.md",
        "README.md",
    )
    combined = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in required)

    for term in (
        "ProviderFinancialFact",
        "ProviderFactMapping",
        "Decimal",
        "Restatement",
        "research_as_of_time",
        "TTM",
        "NOT_MEANINGFUL",
        "FIXTURE",
        "OFFLINE",
        "NOT_LIVE",
        "BLOCKED",
        "RAG",
        "Agent",
        "MCP Server",
        "target price",
        "trading",
    ):
        assert term.casefold() in combined.casefold()


def test_stage5_documented_commands_exist_in_cli_help() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for command in (
        "financials seed-v0",
        "financials normalize",
        "financials calculate",
        "financials periods",
        "financials facts",
        "financials metrics",
        "financials metric",
        "financials lineage",
    ):
        assert command in readme
