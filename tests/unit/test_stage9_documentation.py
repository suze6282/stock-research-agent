from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS = {
    "readme": PROJECT_ROOT / "README.md",
    "providers": PROJECT_ROOT / "docs" / "data-providers.md",
    "ingestion": PROJECT_ROOT / "docs" / "data-ingestion.md",
    "raw": PROJECT_ROOT / "docs" / "raw-data-model.md",
    "database": PROJECT_ROOT / "docs" / "database.md",
    "testing": PROJECT_ROOT / "docs" / "testing.md",
    "api": PROJECT_ROOT / "docs" / "api.md",
    "tools": PROJECT_ROOT / "docs" / "tool-contracts.md",
    "compliance": PROJECT_ROOT / "docs" / "compliance-boundaries.md",
    "security": PROJECT_ROOT / "docs" / "security-boundaries.md",
}


def _text(name: str) -> str:
    return DOCS[name].read_text(encoding="utf-8")


def test_all_stage9_documentation_files_exist_without_placeholders() -> None:
    assert all(path.is_file() for path in DOCS.values())
    combined = "\n".join(_text(name) for name in DOCS)
    assert "Stage 9" in combined
    assert "CONDITIONAL GO" in combined
    assert "Stage 10" in combined
    assert "TBD" not in combined
    assert "FIXME" not in combined


def test_provider_and_ingestion_docs_define_gate_order_statuses_and_temporal_rules() -> None:
    providers = _text("providers")
    ingestion = _text("ingestion")
    for term in (
        "Definition → Capability → License → Policy → Configuration",
        "SEC_EDGAR_PUBLIC_V1",
        "TUSHARE_PRO_V1",
        "CONDITIONAL",
        "BLOCKED",
        "NOT_ATTEMPTED",
        "credential reference",
    ):
        assert term in providers
    for term in (
        "OFFLINE",
        "NOT_LIVE",
        "caller-owned transaction",
        "Checkpoint",
        "research_as_of_time",
        "revision",
        "does not create a Snapshot",
    ):
        assert term in ingestion


def test_raw_and_database_docs_cover_rights_immutability_migration_and_rollback() -> None:
    raw = _text("raw")
    database = _text("database")
    for term in (
        "provider_raw_artifacts",
        "source checksum",
        "BlobStorage",
        "license",
        "retention",
        "raw payload is never overwritten",
    ):
        assert term in raw
    for term in (
        "0008_create_production_data_providers",
        "20 Stage 9 tables",
        "RESTRICT",
        "immutable",
        "0008 → 0007 → 0008",
    ):
        assert term in database


def test_testing_api_tool_and_cli_docs_match_executable_contracts() -> None:
    testing = _text("testing")
    api = _text("api")
    tools = _text("tools")
    readme = _text("readme")
    assert 'testpaths = ["tests"]' in testing
    assert "批准执行该Provider的有限Live验证" in testing
    assert "tests_live/providers" in testing
    assert "GET /providers" in api
    assert "GET /provider-readiness/{security_id}" in api
    assert "POST" in api and "forbidden" in api.casefold()
    assert "10 Provider query Tools" in tools
    assert "READ_ONLY" in tools
    assert "requires_network=false" in tools
    assert "docs/tool-catalog-stage-9-final.json" in tools
    assert "not automatically added" in tools
    assert "stock-research provider sync-plan" in readme
    assert "stock-research provider live-check" in readme


def test_compliance_and_security_docs_keep_credentials_license_and_live_fail_closed() -> None:
    compliance = _text("compliance")
    security = _text("security")
    for term in (
        "SEC",
        "Tushare",
        "credential values are never persisted",
        "license",
        "Live",
        "NOT_ATTEMPTED",
    ):
        assert term in compliance
    for term in (
        "SSRF",
        "DNS",
        "redirect",
        "response byte",
        "decompression",
        "archive",
        "secret",
        "default tests are offline",
    ):
        assert term in security
