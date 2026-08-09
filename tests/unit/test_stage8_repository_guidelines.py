from pathlib import Path

ROOT = Path(__file__).parents[2]
GUIDELINES = ROOT / "AGENTS.md"


def test_repository_guidelines_preserve_stage8_scope_as_historical_context() -> None:
    text = GUIDELINES.read_text(encoding="utf-8")

    for required in (
        "stage-8/verifiable-report-reflection",
        "stage-8-verifiable-report-reflection-design.md",
        "stage-8-verifiable-report-reflection.md",
        "ReportInputManifest",
        "DeterministicReportRenderer",
        "JSON",
        "Markdown",
        "Claim-Evidence Link",
        "Reflection最多2轮",
        "Revision最多1轮",
        "internal PUBLISHABLE",
        "不得进入第9阶段",
    ):
        assert required in text

    assert "Do not implement directly on `main`" in text
    assert "Stage 10: Started / Work in Progress / Development Paused" in text


def test_repository_guidelines_preserve_stage7_evidence_and_safety_boundaries() -> None:
    text = GUIDELINES.read_text(encoding="utf-8")

    for required in (
        "READ_ONLY",
        "writes=false",
        "requires_network=false",
        "Citation evidence must be `VALID`",
        "Industrial FII",
        "Micron",
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "OFFLINE",
        "NOT_LIVE",
        "PostgreSQL",
        "no model",
        "no target price",
        "no automatic trading",
    ):
        assert required in text
