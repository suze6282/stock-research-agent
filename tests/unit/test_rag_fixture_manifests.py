from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "rag"
MARKERS = {"SYNTHETIC_TEST_ONLY", "NOT_COMPANY_EVIDENCE", "OFFLINE", "NOT_LIVE"}
TEXT_FIXTURE_SUFFIXES = {".html", ".json", ".txt"}


def _manifest_payloads() -> list[Path]:
    return [
        path
        for path in sorted(FIXTURES.glob("synthetic_contract.*"))
        if not path.name.endswith(".manifest.json")
    ]


def _manifest_text_payloads() -> list[Path]:
    return [path for path in _manifest_payloads() if path.suffix in TEXT_FIXTURE_SUFFIXES]


def test_manifest_text_fixtures_use_deterministic_lf_bytes() -> None:
    payloads = _manifest_text_payloads()
    assert {path.suffix for path in payloads} == TEXT_FIXTURE_SUFFIXES
    for payload in payloads:
        content = payload.read_bytes()
        assert b"\r\n" not in content
        assert b"\r" not in content


def test_each_synthetic_fixture_has_exact_manifest_checksum_and_markers() -> None:
    payloads = _manifest_payloads()
    assert {path.suffix for path in _manifest_text_payloads()} == TEXT_FIXTURE_SUFFIXES
    for payload in payloads:
        manifest_path = payload.with_name(f"{payload.name}.manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert set(manifest["markers"]) == MARKERS
        assert manifest["checksum"] == hashlib.sha256(payload.read_bytes()).hexdigest()
        assert manifest["security"] == "SYNTHETIC_NONE"
        assert manifest["source_published_at"] is None
        assert manifest["cropped"] is False
        assert manifest["crop_rule"] == "NONE"


def test_no_synthetic_fixture_claims_to_be_company_evidence() -> None:
    corpus = "\n".join(
        path.read_text(encoding="utf-8") for path in FIXTURES.glob("synthetic_contract.*")
    )
    forbidden = ("工业富联", "富士康工业互联网", "Micron", "601138", "NASDAQ:MU")
    assert not any(value.casefold() in corpus.casefold() for value in forbidden)
