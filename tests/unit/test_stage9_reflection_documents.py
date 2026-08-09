from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUND_ONE = PROJECT_ROOT / "docs/reflection/stage-9-round-1.md"
ROUND_TWO = PROJECT_ROOT / "docs/reflection/stage-9-round-2.md"


def test_stage9_round_one_records_all_roles_fields_and_closed_high_findings() -> None:
    text = ROUND_ONE.read_text(encoding="utf-8")

    for role in (
        "Data platform",
        "Provider contracts",
        "Licensing and compliance",
        "HTTP and security",
        "Database and concurrency",
        "Operations",
        "API, Tool, and CLI",
        "Fixtures and testing",
        "Historical immutability",
    ):
        assert role in text
    for required in (
        "| ID | Role | Severity | Description | Evidence | "
        "Affected files | Fix | Blocking | Status |",
        "S9-R1-001",
        "S9-R1-010",
        "Unresolved `CRITICAL`: 0",
        "Unresolved `HIGH`: 0",
        "network=FORBIDDEN",
        "credentials=NOT_READ",
        "live=NOT_ATTEMPTED",
    ):
        assert required in text
    for finding_id in ("S9-R1-001", "S9-R1-002", "S9-R1-003", "S9-R1-010"):
        row = next(line for line in text.splitlines() if line.startswith(f"| {finding_id} "))
        assert "| HIGH |" in row
        assert "| YES | FIXED |" in row


def test_stage9_round_one_records_actual_database_evidence() -> None:
    text = ROUND_ONE.read_text(encoding="utf-8")

    for evidence in (
        "ProviderHealthSnapshot",
        "ck_provider_health_snapshots_states",
        "trg_provider_health_snapshots_immutable",
        "get_readiness_view",
        "0008_create_production_data_providers.py",
        "real PostgreSQL",
    ):
        assert evidence in text


def test_stage9_round_two_rechecks_all_approved_boundaries() -> None:
    text = ROUND_TWO.read_text(encoding="utf-8")

    for requirement in (
        "Credential not persisted",
        "Secret not logged",
        "UNKNOWN license blocks requests",
        "BLOCKED license blocks requests",
        "Provider URL injection rejected",
        "SSRF rejected",
        "private IP rejected",
        "redirect controlled",
        "response size bounded",
        "content type validated",
        "retry finite",
        "shared rate limit effective",
        "circuit breaker effective",
        "cache credential isolation",
        "sync finite",
        "checkpoint correct",
        "resume budget retained",
        "Raw Artifact immutable",
        "Manifest stable",
        "future data rejected",
        "synthetic contamination rejected",
        "SEC metadata is not body",
        "Tushare remains BLOCKED",
        "A-share bodies remain BLOCKED",
        "U.S. EOD remains BLOCKED",
        "Embedding remains BLOCKED",
        "default tests offline",
        "default skipped=0",
        "Live tests excluded",
        "migration replay passed",
        "historical Snapshot unchanged",
        "historical Research Package unchanged",
        "historical Report unchanged",
        "PostgreSQL integration passed",
        "documents match implementation",
        "unresolved CRITICAL=0",
        "unresolved HIGH=0",
    ):
        assert requirement in text
