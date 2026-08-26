from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_default_pytest_collects_only_tests_not_tests_live() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'testpaths = ["tests"]' in pyproject
    assert (
        "tests_live"
        not in pyproject.split("[tool.pytest.ini_options]", 1)[1].split("[tool.ruff]", 1)[0]
    )


def test_sec_live_harness_reports_not_attempted_or_blocked_without_skip() -> None:
    source = (PROJECT_ROOT / "tests_live" / "test_sec_controlled_live.py").read_text(
        encoding="utf-8"
    )
    assert "NOT_ATTEMPTED" in source
    assert "BLOCKED" in source
    assert "pytest.skip" not in source
    assert "skipif" not in source
    assert 'status != "PASS"' in source
