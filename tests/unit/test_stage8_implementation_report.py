from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT = PROJECT_ROOT / "docs" / "stage-8-implementation-report.md"

REQUIRED_SECTIONS = (
    "1. Stage conclusion",
    "2. Current branch",
    "3. Design approval record",
    "4. Implemented scope",
    "5. Excluded scope",
    "6. Report architecture",
    "7. Input contract",
    "8. Report Policy",
    "9. Template",
    "10. Generation Run",
    "11. Report versions",
    "12. Section",
    "13. Block",
    "14. Claim Binding",
    "15. Evidence Binding",
    "16. Citation Binding",
    "17. JSON Renderer",
    "18. Markdown Renderer",
    "19. zh-CN",
    "20. en-US",
    "21. Reference format",
    "22. Evidence appendix",
    "23. Citation appendix",
    "24. Runtime Reflection",
    "25. Finding",
    "26. Revision",
    "27. Release Gate",
    "28. Idempotency",
    "29. Fixtures and LF",
    "30. Tools",
    "31. API",
    "32. CLI",
    "33. Industrial FII result",
    "34. Micron result",
    "35. Synthetic result",
    "36. Narrative Provider status",
    "37. Reflection Provider status",
    "38. Live Provider status",
    "39. Database migration",
    "40. PostgreSQL integration",
    "41. Ruff",
    "42. Format check",
    "43. mypy",
    "44. Actual pytest count",
    "45. Failures, errors, skips, and warnings",
    "46. Development Reflection Round 1",
    "47. Development Reflection Round 2",
    "48. Fixed findings",
    "49. Unresolved findings",
    "50. BLOCKED items",
    "51. CRITICAL and HIGH risk",
    "52. Current limitations",
    "53. Rollback",
    "54. Git status",
    "55. Stage 9 authorization",
    "56. Stage 9 allowed scope",
    "57. Stage 9 prohibited scope",
)


def test_stage8_implementation_report_has_all_57_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for section in REQUIRED_SECTIONS:
        assert f"## {section}" in text


def test_stage8_implementation_report_records_verified_results_and_limits() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for required in (
        "**CONDITIONAL GO**",
        "`stage-8/verifiable-report-reflection`",
        "`0007_verifiable_reports (head)`",
        "2028 collected",
        "2028 passed",
        "0 failed",
        "0 errors",
        "0 skipped",
        "0 warnings",
        "Industrial FII",
        "Micron",
        "SYNTHETIC_TEST_ONLY",
        "Production Narrative Provider: `BLOCKED`",
        "Production Reflection Provider: `BLOCKED`",
        "Unresolved CRITICAL: `0`",
        "Unresolved HIGH: `0`",
        "Stage 9 is not authorized",
    ):
        assert required in text
