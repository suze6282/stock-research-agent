from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "stage-10-implementation-report.md"
PLAN = ROOT / "docs" / "plans" / "stage-10-controlled-live-evidence.md"


def test_stage10_report_covers_all_required_acceptance_sections() -> None:
    source = REPORT.read_text(encoding="utf-8")
    required_sections = (
        "Gate A conclusion",
        "Current branch",
        "Design approval",
        "Task completion",
        "Database tables",
        "Alembic",
        "LiveAuthorizationGrant",
        "Consumption",
        "Execution Approval",
        "Atomic budgets",
        "Manual Import",
        "File security",
        "Raw Artifact",
        "Ingestion Manifest",
        "Snapshot",
        "Agent",
        "Report",
        "CLI",
        "API",
        "Fixture",
        "Default network status",
        "Credential access status",
        "Live request status",
        "Ruff",
        "Format check",
        "mypy",
        "pytest",
        "PostgreSQL",
        "Reflection Round 1",
        "Reflection Round 2",
        "Fixed findings",
        "Unresolved CRITICAL",
        "Unresolved HIGH",
        "Gate B blockers",
        "SEC filing selection",
        "SEC accession selection",
        "SEC rules revalidation",
        "SEC contact identity",
        "Retention approval",
        "Industrial FII real file",
        "Real Snapshot",
        "Real Agent",
        "Real Report",
        "Gate B application readiness",
        "Stage 11",
    )
    for index, title in enumerate(required_sections, start=1):
        assert f"## {index}. {title}" in source
    assert "Task 1–79: `79/80`" in source or "Task 1–80: `80/80`" in source
    assert "Stage 10 overall: `CONDITIONAL GO`" in source
    assert "Gate B: `NOT_ATTEMPTED`" in source
    assert "Credential values read: `NO`" in source
    assert "Live requests executed: `NO`" in source
    assert "unresolved CRITICAL=0" in source
    assert "unresolved HIGH=0" in source
    assert "TBD" not in source
    assert "TODO" not in source


def test_gate_a_status_tracks_task_80_instead_of_claiming_completion_early() -> None:
    source = REPORT.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    if "| - [x] 80. Gate A final acceptance |" in plan:
        assert "Gate A status: `GATE_A_COMPLETE`" in source
        assert "Task 1–80: `80/80`" in source
        assert "Final revision: `0009_controlled_live_evidence (head)`" in source
    else:
        assert "Gate A status: `GATE_A_CONDITIONAL`" in source
        assert "Task 1–79: `79/80`" in source
