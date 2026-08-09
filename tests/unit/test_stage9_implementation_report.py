from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT = PROJECT_ROOT / "docs/stage-9-implementation-report.md"

REQUIRED_SECTIONS = (
    "1. Stage conclusion",
    "2. Current branch",
    "3. Design approval",
    "4. Implementation scope",
    "5. Out-of-scope work",
    "6. Provider architecture",
    "7. Capability Matrix",
    "8. License Matrix",
    "9. Credential boundary",
    "10. HTTP security",
    "11. Rate Limit",
    "12. Retry",
    "13. Circuit Breaker",
    "14. Cache",
    "15. Sync",
    "16. Checkpoint",
    "17. Raw Artifact",
    "18. Ingestion Manifest",
    "19. Dead Letter",
    "20. Data Quality",
    "21. Freshness",
    "22. Health",
    "23. SEC Provider",
    "24. Tushare Provider",
    "25. A-share body Providers",
    "26. U.S. EOD Provider",
    "27. Embedding Provider",
    "28. Industrial FII readiness",
    "29. Micron readiness",
    "30. Live validation status",
    "31. Database migration",
    "32. PostgreSQL integration",
    "33. Tool",
    "34. API",
    "35. CLI",
    "36. Fixture LF",
    "37. Ruff",
    "38. Format check",
    "39. mypy",
    "40. Default pytest",
    "41. Live test result",
    "42. Reflection round one",
    "43. Reflection round two",
    "44. Fixed findings",
    "45. Unresolved findings",
    "46. Unresolved CRITICAL",
    "47. Unresolved HIGH",
    "48. BLOCKED Providers",
    "49. Credential status",
    "50. License status",
    "51. Current limitations",
    "52. Rollback",
    "53. Git status",
    "54. Stage 10 authorization",
    "55. Stage 10 allowed scope",
    "56. Stage 10 prohibited scope",
)


def test_stage9_report_has_all_required_sections_and_truthful_conclusion() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for section in REQUIRED_SECTIONS:
        assert f"## {section}" in text
    assert "Conclusion: `CONDITIONAL GO`" in text
    assert "Task 0–76: `77/77`" in text
    assert "0008_production_providers (head)" in text
    assert "unresolved CRITICAL=0" in text
    assert "unresolved HIGH=0" in text
    assert "Live validation executed: `NO`" in text
    assert "Credential values read: `NO`" in text
    assert "External network access: `NO`" in text
    assert "Stage 10 authorized: `NO`" in text


def test_stage9_report_records_real_quality_results_without_placeholders() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert re.search(
        r"Default pytest: `\d+ passed, 0 failed, 0 errors, 0 skipped, 0 warnings`, "
        r"duration `[^`]+`",
        text,
    )
    assert "Ruff: `PASS`" in text
    assert "Format: `PASS`" in text
    assert "mypy: `PASS`" in text
    assert "PostgreSQL: `PASS`" in text
    assert "Migration upgrade/downgrade/re-upgrade: `PASS`" in text
    assert not any(marker in text for marker in ("TBD", "TODO", "FIXME"))


def test_stage9_report_preserves_real_company_and_provider_boundaries() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for statement in (
        "SEC_EDGAR_PUBLIC_V1: `CONDITIONAL`, Live `NOT_ATTEMPTED`",
        "TUSHARE_PRO_V1: `BLOCKED`, Live `NOT_ATTEMPTED`",
        "SSE_DISCLOSURE_BODIES_V1: `BLOCKED`",
        "SZSE_DISCLOSURE_BODIES_V1: `BLOCKED`",
        "CNINFO_DISCLOSURE_BODIES_V1: `BLOCKED`",
        "LICENSED_US_EOD_V1: `BLOCKED`",
        "PRODUCTION_EMBEDDING_V1: `BLOCKED`",
        "Industrial FII company evidence: `BLOCKED`",
        "Micron verified filing body: `BLOCKED`",
        "Synthetic fixtures used as real-company evidence: `0`",
        "Snapshots created during Stage 9: `0`",
        "Agent Runs created during Stage 9: `0`",
        "Reports generated during Stage 9: `0`",
    ):
        assert statement in text
