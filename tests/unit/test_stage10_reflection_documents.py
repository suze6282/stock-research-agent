from __future__ import annotations

from pathlib import Path

ROUND_ONE = Path(__file__).resolve().parents[2] / "docs" / "reflection" / "stage-10-round-1.md"
ROUND_TWO = Path(__file__).resolve().parents[2] / "docs" / "reflection" / "stage-10-round-2.md"


def test_round_one_records_roles_evidence_and_actionable_findings() -> None:
    source = ROUND_ONE.read_text(encoding="utf-8")
    for role in (
        "Provider governance",
        "Compliance and security",
        "Database architecture",
        "Evidence, Snapshot, Agent, and Report architecture",
        "API, Tool, and CLI",
        "Test and reliability",
        "Operations and incident response",
    ):
        assert role in source
    assert "S10-R1-001" in source
    assert "CRITICAL=0" in source
    assert "HIGH=5" in source
    assert "Gate B remained `NOT_ATTEMPTED`" in source
    assert "TBD" not in source
    assert "TODO" not in source


def test_round_two_rechecks_every_high_with_actual_gate_evidence() -> None:
    source = ROUND_TWO.read_text(encoding="utf-8")
    for finding_id in (
        "S10-R1-001",
        "S10-R1-002",
        "S10-R1-003",
        "S10-R1-004",
        "S10-R1-007",
    ):
        assert finding_id in source
    for evidence in (
        "643 files already formatted",
        "Success: no issues found in 280 source files",
        "19 passed in 4.66s",
        "2975 passed in 549.03s",
        "unresolved CRITICAL=0",
        "unresolved HIGH=0",
        "Gate B remains `NOT_ATTEMPTED`",
    ):
        assert evidence in source
    assert "TBD" not in source
    assert "TODO" not in source
