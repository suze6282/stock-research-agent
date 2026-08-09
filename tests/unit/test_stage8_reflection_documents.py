from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUND_ONE = PROJECT_ROOT / "docs" / "reflection" / "stage-8-round-1.md"
ROUND_TWO = PROJECT_ROOT / "docs" / "reflection" / "stage-8-round-2.md"


def test_stage8_round_one_records_all_roles_fields_and_closed_high_findings() -> None:
    text = ROUND_ONE.read_text(encoding="utf-8")

    for role in (
        "Report architecture",
        "Financial research",
        "Citation and evidence",
        "Runtime Reflection",
        "Revision",
        "Release Gate",
        "Security",
        "PostgreSQL",
        "Fixture and cross-platform",
        "Testing reliability",
    ):
        assert role in text
    for field in (
        "| ID | Role | Severity | Description | Evidence | "
        "Affected files | Fix | Blocking | Status |",
        "S8-R1-001",
        "S8-R1-010",
        "Unresolved `CRITICAL`: 0",
        "Unresolved `HIGH`: 0",
    ):
        assert field in text


def test_stage8_round_two_rechecks_every_release_boundary() -> None:
    text = ROUND_TWO.read_text(encoding="utf-8")

    for requirement in (
        "Package-only input",
        "Claim/Evidence/Citation binding graph",
        "two deterministic Reflection rounds",
        "one subtractive Revision",
        "internal Release Gate",
        "Industrial FII",
        "Micron",
        "neutral Synthetic",
        "PostgreSQL",
        "production model providers remain BLOCKED",
        "no Stage 9",
        "unresolved CRITICAL=0",
        "unresolved HIGH=0",
    ):
        assert requirement in text
