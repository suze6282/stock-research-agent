from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "reports"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def _git_blob(relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"HEAD:tests/fixtures/reports/{relative_path}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def test_report_fixture_worktree_git_blob_and_manifest_checksums_match() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for record in manifest["files"]:
        path = FIXTURE_ROOT / record["path"]
        worktree = path.read_bytes()
        blob = _git_blob(record["path"])
        assert worktree == blob
        assert hashlib.sha256(worktree).hexdigest() == record["sha256"]
        assert b"\r\n" not in worktree
        assert worktree.endswith(b"\n")


def test_report_fixture_git_attributes_force_lf_without_global_changes() -> None:
    result = subprocess.run(
        [
            "git",
            "check-attr",
            "text",
            "eol",
            "--",
            "tests/fixtures/reports/synthetic_report_input.json",
            "tests/fixtures/reports/synthetic_report_expected_en_us.md",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.count("text: set") == 2
    assert result.stdout.count("eol: lf") == 2


def test_report_fixture_manifest_keeps_all_four_non_company_markers() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert set(manifest["classification"]) == {
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "OFFLINE",
        "NOT_LIVE",
    }
    assert "prohibited as company evidence" in manifest["authorization"].casefold()
