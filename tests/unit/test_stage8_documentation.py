from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE8_DOCS = (
    "docs/report-architecture.md",
    "docs/report-policy.md",
    "docs/report-templates.md",
    "docs/report-bindings.md",
    "docs/report-runtime-reflection.md",
    "docs/report-release-gate.md",
    "docs/report-localization.md",
    "docs/report-security.md",
    "docs/report-cli.md",
)


def _text(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def test_stage8_document_set_covers_canonical_report_and_lineage_contract() -> None:
    combined = "\n".join(_text(path) for path in STAGE8_DOCS)

    for required in (
        "ReportInputManifest",
        "structured JSON",
        "Markdown",
        "Claim-Evidence Link",
        "VALID Citation",
        "structured calculation lineage",
        "previous_report_id",
        "PARTIAL",
        "BLOCKED",
        "NO_EVIDENCE",
    ):
        assert required in combined


def test_stage8_documents_cover_finite_runtime_and_internal_release_semantics() -> None:
    combined = "\n".join(_text(path) for path in STAGE8_DOCS)

    for required in (
        "two rounds",
        "one round",
        "internal_release_status=PUBLISHABLE",
        "does not mean public publication",
        "investment advice",
        "target price",
        "automatic trading",
    ):
        assert required in combined


def test_stage8_documents_distinguish_real_synthetic_and_provider_limits() -> None:
    combined = "\n".join(
        _text(path)
        for path in (
            *STAGE8_DOCS,
            "README.md",
            "docs/risk-register.md",
            "docs/open-questions.md",
        )
    )
    for required in (
        "601138.SH",
        "Micron",
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "OFFLINE",
        "NOT_LIVE",
        "production Narrative",
        "production Reflection",
        "BLOCKED",
        "Stage 9",
    ):
        assert required in combined


def test_shared_api_database_testing_and_cli_docs_match_implemented_boundaries() -> None:
    api = _text("docs/api.md")
    database = _text("docs/database.md")
    testing = _text("docs/testing.md")
    cli = _text("docs/report-cli.md")

    assert "ten GET-only routes" in api
    assert "15 purpose-specific tables" in database
    assert "0007_verifiable_reports" in database
    assert "Git blobs" in testing
    for command in (
        "report generate",
        "report reflect",
        "report revise",
        "report release-check",
        "report export-markdown",
    ):
        assert command in cli
