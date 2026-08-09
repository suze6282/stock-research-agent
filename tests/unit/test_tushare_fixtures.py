from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "providers" / "tushare"
PAYLOAD_PATH = FIXTURE_ROOT / "synthetic_protocol_response.json"
MANIFEST_PATH = FIXTURE_ROOT / "synthetic_protocol_response.manifest.json"


def test_tushare_synthetic_contract_fixture_files_exist() -> None:
    assert PAYLOAD_PATH.is_file(), "synthetic Tushare protocol payload is absent"
    assert MANIFEST_PATH.is_file(), "synthetic Tushare protocol manifest is absent"


def test_tushare_fixture_checksum_and_lf_bytes_are_independently_reproducible() -> None:
    payload = PAYLOAD_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert b"\r" not in payload
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert len(payload) == manifest["payload_byte_size"]
    assert hashlib.sha256(payload).hexdigest() == manifest["checksum"]["value"]
    assert manifest["checksum"]["algorithm"] == "SHA-256"


def test_tushare_fixture_manifest_is_complete_test_only_offline_and_not_live() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    required_fields = {
        "fixture_schema_version",
        "payload_filename",
        "provider",
        "source_url",
        "source_endpoint_type",
        "security",
        "captured_at",
        "source_published_at",
        "content_type",
        "original_response_cropped",
        "full_response_bytes_retained",
        "crop_rules",
        "payload_byte_size",
        "checksum",
        "authorization_use_restrictions",
        "production_live_qualification",
        "data_origin",
        "company_evidence_status",
        "access_mode",
        "live_status",
        "license_status",
        "credential_status",
    }
    assert required_fields <= manifest.keys()
    assert manifest["provider"] == "TUSHARE_PRO_V1"
    assert manifest["source_url"] is None
    assert manifest["source_endpoint_type"] == "TUSHARE_SYNTHETIC_PROTOCOL"
    assert manifest["security"] == "SYNTHETIC_SECURITY"
    assert manifest["source_published_at"] is None
    assert manifest["content_type"] == "application/json"
    assert manifest["original_response_cropped"] is False
    assert manifest["full_response_bytes_retained"] is True
    assert manifest["crop_rules"]
    assert manifest["authorization_use_restrictions"]
    assert manifest["data_origin"] == "SYNTHETIC_TEST_ONLY"
    assert manifest["company_evidence_status"] == "NOT_COMPANY_EVIDENCE"
    assert manifest["access_mode"] == "OFFLINE"
    assert manifest["live_status"] == "NOT_LIVE"
    assert manifest["license_status"] == "TEST_ONLY"
    assert manifest["credential_status"] == "ABSENT"
    assert manifest["production_live_qualification"].startswith(
        "SYNTHETIC_TEST_ONLY; NOT_COMPANY_EVIDENCE; OFFLINE; NOT_LIVE"
    )


def test_tushare_fixture_is_an_empty_protocol_envelope_not_company_evidence() -> None:
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False).upper()

    assert payload == {
        "code": 0,
        "msg": None,
        "data": {
            "fields": ["ts_code", "trade_date", "close"],
            "items": [],
        },
    }
    assert "601138" not in serialized
    assert '"MU"' not in serialized
    assert "MICRON" not in serialized
    assert "INDUSTRIAL FULIAN" not in serialized
    assert "工业富联" not in serialized
    assert payload["data"]["items"] == []


def test_tushare_fixture_contains_no_endpoint_or_credential_material() -> None:
    payload_text = PAYLOAD_PATH.read_text(encoding="utf-8").lower()
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8").lower()

    assert "http://" not in payload_text
    assert "https://" not in payload_text
    assert "token" not in payload_text
    assert "password" not in payload_text
    assert "api_key" not in payload_text
    assert "api.tushare.pro" not in manifest_text
    assert "tushare_token" not in manifest_text
