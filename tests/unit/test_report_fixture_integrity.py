from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "reports"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def test_report_fixture_export_bytes_and_manifest_checksums_match() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for record in manifest["files"]:
        path = FIXTURE_ROOT / record["path"]
        worktree = path.read_bytes()
        assert hashlib.sha256(worktree).hexdigest() == record["sha256"]
        assert b"\r\n" not in worktree
        assert worktree.endswith(b"\n")


def test_report_fixture_attributes_force_lf_without_requiring_git_history() -> None:
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "tests/fixtures/reports/*.json text eol=lf" in attributes
    assert "tests/fixtures/reports/*.md text eol=lf" in attributes
    assert not (PROJECT_ROOT / ".git").exists()


def test_report_fixture_manifest_keeps_all_four_non_company_markers() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert set(manifest["classification"]) == {
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "OFFLINE",
        "NOT_LIVE",
    }
    assert "prohibited as company evidence" in manifest["authorization"].casefold()
