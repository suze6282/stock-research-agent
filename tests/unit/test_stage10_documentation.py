from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_public_docs_describe_gate_a_without_authorizing_gate_b() -> None:
    requirements = {
        "README.md": (
            "Stage 10 Gate A",
            "Gate B",
            "NOT_ATTEMPTED",
            "stock-research live",
            "stock-research evidence",
        ),
        "docs/database.md": (
            "0009_controlled_live_evidence",
            "live_authorization_grants",
            "evidence_ingestion_manifests",
            "ingestion_to_snapshot_bindings",
            "live_incident_events",
        ),
        "docs/testing.md": (
            "Stage 10 Gate A",
            "tests_live",
            "SYNTHETIC_TEST_ONLY",
            "NOT_COMPANY_EVIDENCE",
            "OFFLINE",
            "NOT_LIVE",
        ),
        "docs/api.md": (
            "/api/v1/live-evidence",
            "GET-only",
            "READ_ONLY",
            "requires_network=false",
        ),
        "docs/security-boundaries.md": (
            "Stage 10 Gate A",
            "Gate B",
            "Credential",
            "manual evidence",
            "25 MiB",
        ),
        "AGENTS.md": (
            "Stage 10 Gate A",
            "Gate B",
            "Stage 11",
            "批准执行该SEC有限Live验证",
        ),
    }
    for relative_path, markers in requirements.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in source, f"{relative_path}: missing {marker}"
        assert "TBD" not in source
        assert "TODO" not in source
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "GATE_A_CONDITIONAL" in readme or "GATE_A_COMPLETE" in readme


def test_public_docs_do_not_claim_live_success_or_real_company_execution() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/database.md",
            "docs/testing.md",
            "docs/api.md",
            "docs/security-boundaries.md",
            "AGENTS.md",
        )
    )
    for forbidden in (
        "SEC Live: PASS",
        "Live validation: PASS",
        "Credential values read: YES",
        "Industrial FII real report: COMPLETE",
        "Micron real report: COMPLETE",
        "Stage 11 authorized",
    ):
        assert forbidden not in sources
