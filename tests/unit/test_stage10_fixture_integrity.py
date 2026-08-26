from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "live_evidence"


def test_stage10_security_fixtures_are_lf_reproducible_and_manifested() -> None:
    manifest = json.loads((ROOT / "fixtures.manifest.json").read_text(encoding="utf-8"))
    assert manifest["markers"] == [
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "NOT_PROVIDER_DATA",
        "OFFLINE",
        "NOT_LIVE",
    ]
    assert manifest["license"] == "PROJECT_TEST_FIXTURE_ONLY"
    for entry in manifest["fixtures"]:
        payload = (ROOT / entry["filename"]).read_bytes()
        assert b"\r\n" not in payload
        assert len(payload) == entry["byte_size"]
        assert hashlib.sha256(payload).hexdigest() == entry["checksum"]


def test_stage10_fixtures_are_attacks_not_company_evidence() -> None:
    pdf = (ROOT / "active-action.pdf").read_bytes()
    html = (ROOT / "active-resource.html").read_bytes()
    json_payload = (ROOT / "bounded-attack.json").read_bytes()
    assert b"/JavaScript" in pdf and b"/OpenAction" in pdf
    assert b"<script>" in html
    assert json_payload.count(b'"duplicate"') == 2
