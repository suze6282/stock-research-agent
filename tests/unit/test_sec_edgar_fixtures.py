from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "providers" / "sec_synthetic"
PAYLOAD_PATH = FIXTURE_ROOT / "tstx_sec_public.json"
MANIFEST_PATH = FIXTURE_ROOT / "tstx_sec_public.manifest.json"


def test_governed_sec_fixture_files_exist() -> None:
    assert PAYLOAD_PATH.is_file(), "synthetic SEC contract fixture is absent"
    assert MANIFEST_PATH.is_file(), "synthetic SEC contract manifest is absent"


def test_sec_fixture_checksum_and_lf_bytes_are_independently_reproducible() -> None:
    payload = PAYLOAD_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert b"\r" not in payload
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert len(payload) == manifest["payload_byte_size"]
    assert hashlib.sha256(payload).hexdigest() == manifest["checksum"]["value"]
    assert manifest["checksum"]["algorithm"] == "SHA-256"


def test_sec_fixture_manifest_is_project_authored_offline_and_not_live() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["provider"] == "SEC_EDGAR_PUBLIC_V1"
    assert manifest["source_url"] == "https://example.invalid/synthetic/sec-submissions"
    assert manifest["source_endpoint_type"] == "SYNTHETIC_SEC_SUBMISSIONS_SCHEMA"
    assert manifest["security"] == "TSTX"
    assert manifest["captured_at"]["date"] == "2026-01-16"
    assert manifest["source_published_at"] is None
    assert manifest["content_type"] == "application/json"
    assert manifest["original_response_cropped"] is False
    assert manifest["crop_rules"]
    assert manifest["authorization_use_restrictions"]
    assert manifest["data_origin"] == "FIXTURE"
    assert manifest["access_mode"] == "OFFLINE"
    assert manifest["live_status"] == "NOT_LIVE"
    assert manifest["production_live_qualification"].startswith("SYNTHETIC_TEST_ONLY")
    assert manifest["synthetic"] is True
    assert manifest["test_only"] is True
    assert manifest["company_evidence"] is False
    assert manifest["live"] is False
    assert manifest["markers"] == [
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "NOT_PROVIDER_DATA",
        "OFFLINE",
        "NOT_LIVE",
    ]


def test_sec_fixture_contains_only_synthetic_metadata_not_company_body() -> None:
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))

    assert payload == {
        "issuer": "Example Semiconductor Research Corp.",
        "ticker": "TSTX",
        "cik": "0000000000",
        "exchange_label": "Nasdaq",
        "filings": [
            {
                "form": "10-K",
                "filed_date": "2026-01-10",
                "report_date": "2025-12-31",
                "accession": "0000000000-26-000001",
            },
            {
                "form": "10-Q",
                "filed_date": "2026-01-11",
                "report_date": "2025-09-30",
                "accession": "0000000000-26-000002",
            },
            {
                "form": "8-K",
                "filed_date": "2026-01-12",
                "report_date": None,
                "accession": "0000000000-26-000003",
            },
        ],
        "financial_facts": [],
        "fixture_notice": "This synthetic filing exists solely for parser and citation tests.",
        "markers": [
            "SYNTHETIC_TEST_ONLY",
            "NOT_COMPANY_EVIDENCE",
            "NOT_PROVIDER_DATA",
            "OFFLINE",
            "NOT_LIVE",
        ],
    }
    assert "body" not in payload
    assert payload["financial_facts"] == []
