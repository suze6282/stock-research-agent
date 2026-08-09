from __future__ import annotations

import hashlib
import importlib
import json
import socket
from decimal import Decimal
from importlib import resources
from pathlib import Path

import pytest
from pydantic import ValidationError

from stock_research_agent.providers.fixtures.provider import (
    FixtureManifest,
    FixtureResourceError,
    load_fixture_resource,
)

FIXTURES = {
    "test001_sse_public": {
        "provider": "STAGE1_SSE_FIXTURE",
        "security": "TEST001.SH",
    },
    "tstx_nasdaq_public": {
        "provider": "STAGE1_NASDAQ_FIXTURE",
        "security": "TSTX",
    },
    "tstx_sec_public": {
        "provider": "STAGE1_SEC_FIXTURE",
        "security": "TSTX",
    },
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_fixture_payload_bytes_are_pinned_to_lf_across_git_checkouts() -> None:
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "src/stock_research_agent/providers/fixtures/data/*.json text eol=lf" in attributes


@pytest.mark.parametrize(("fixture_name", "expected"), FIXTURES.items())
def test_manifest_has_strict_provenance_and_exact_payload_checksum(
    fixture_name: str, expected: dict[str, object]
) -> None:
    package = resources.files("stock_research_agent.providers.fixtures.data")
    manifest_bytes = package.joinpath(f"{fixture_name}.manifest.json").read_bytes()
    manifest = FixtureManifest.model_validate_json(manifest_bytes)
    payload = package.joinpath(manifest.payload_filename).read_bytes()

    assert manifest.fixture_schema_version == "1.0.0"
    assert manifest.payload_filename == f"{fixture_name}.json"
    assert manifest.provider == expected["provider"]
    assert manifest.security == expected["security"]
    assert manifest.source_url is not None or manifest.source_endpoint_type is not None
    assert manifest.captured_at.date.isoformat() == "2026-01-16"
    assert manifest.captured_at.precision == "DAY"
    assert manifest.captured_at.timezone == "Asia/Shanghai"
    assert "project-authored synthetic fixture" in manifest.captured_at.evidence_note
    assert manifest.source_published_at is None
    assert manifest.content_type == "application/json"
    assert manifest.original_response_cropped is False
    assert manifest.full_response_bytes_retained is False
    assert manifest.crop_rules
    assert any("synthetic" in rule.lower() for rule in manifest.crop_rules)
    assert manifest.payload_byte_size == len(payload)
    assert manifest.checksum.algorithm == "SHA-256"
    assert manifest.checksum.value == hashlib.sha256(payload).hexdigest()
    assert manifest.authorization_use_restrictions
    assert "NOT_LIVE" in manifest.production_live_qualification
    assert manifest.data_origin == "FIXTURE"
    assert manifest.access_mode == "OFFLINE"
    assert manifest.live_status == "NOT_LIVE"
    assert manifest.synthetic is True
    assert manifest.test_only is True
    assert manifest.company_evidence is False
    assert manifest.live is False
    assert manifest.markers == (
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "NOT_PROVIDER_DATA",
        "OFFLINE",
        "NOT_LIVE",
    )


def test_manifest_rejects_unknown_fields_and_false_capture_precision() -> None:
    package = resources.files("stock_research_agent.providers.fixtures.data")
    raw = json.loads(package.joinpath("test001_sse_public.manifest.json").read_bytes())

    with pytest.raises(ValidationError):
        FixtureManifest.model_validate({**raw, "unexpected": "value"})
    with pytest.raises(ValidationError):
        FixtureManifest.model_validate(
            {**raw, "captured_at": {**raw["captured_at"], "precision": "SECOND"}}
        )
    with pytest.raises(ValidationError):
        FixtureManifest.model_validate({**raw, "source_published_at": "2026-07-11T20:25:00+08:00"})


def test_payloads_equal_the_explicit_stage1_evidence_allowlist() -> None:
    package = resources.files("stock_research_agent.providers.fixtures.data")

    def decoded(name: str) -> object:
        return json.loads(package.joinpath(name).read_bytes(), parse_float=Decimal)

    assert decoded("test001_sse_public.json") == {
        "security": "TEST001.SH",
        "provider_symbol": "TEST001",
        "trading_date": "2026-01-15",
        "observed_row": [
            20260115,
            Decimal("10.00"),
            Decimal("10.50"),
            Decimal("9.50"),
            Decimal("10.25"),
            100000,
            1025000,
        ],
        "currency_code": "CNY",
        "markers": [
            "SYNTHETIC_TEST_ONLY",
            "NOT_COMPANY_EVIDENCE",
            "NOT_PROVIDER_DATA",
            "OFFLINE",
            "NOT_LIVE",
        ],
    }
    assert decoded("tstx_nasdaq_public.json") == {
        "security": "TSTX",
        "provider_symbol": "TSTX",
        "trading_date": "2026-01-15",
        "display_values": {
            "open": Decimal("20.00"),
            "high": Decimal("21.00"),
            "low": Decimal("19.50"),
            "close": Decimal("20.50"),
            "volume": 100000,
        },
        "currency_code": "USD",
        "markers": [
            "SYNTHETIC_TEST_ONLY",
            "NOT_COMPANY_EVIDENCE",
            "NOT_PROVIDER_DATA",
            "OFFLINE",
            "NOT_LIVE",
        ],
    }
    assert decoded("tstx_sec_public.json") == {
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


@pytest.mark.parametrize("fixture_name", FIXTURES)
def test_loader_returns_verified_exact_package_bytes(fixture_name: str) -> None:
    loaded = load_fixture_resource(fixture_name)

    assert loaded.manifest.payload_filename == f"{fixture_name}.json"
    assert loaded.payload_bytes
    assert hashlib.sha256(loaded.payload_bytes).hexdigest() == loaded.manifest.checksum.value


def test_loader_verifies_checksum_before_json_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    package_type = type(resources.files("stock_research_agent.providers.fixtures.data"))
    original_read_bytes = package_type.read_bytes

    def tampered_read_bytes(resource: object) -> bytes:
        result = original_read_bytes(resource)  # type: ignore[arg-type]
        if str(resource).endswith("test001_sse_public.json"):
            return b"not-json-and-wrong-checksum"
        return result

    monkeypatch.setattr(package_type, "read_bytes", tampered_read_bytes)

    with pytest.raises(FixtureResourceError, match="checksum") as raised:
        load_fixture_resource("test001_sse_public")
    assert "not-json" not in str(raised.value)
    assert "\\" not in str(raised.value)


def test_fixture_module_import_does_not_read_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    package_type = type(resources.files("stock_research_agent.providers.fixtures.data"))

    def forbidden_read_bytes(_resource: object) -> bytes:
        raise AssertionError("fixture resource read during import")

    def forbidden_socket(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("fixture module opened network during import")

    monkeypatch.setattr(package_type, "read_bytes", forbidden_read_bytes)
    monkeypatch.setattr(socket, "socket", forbidden_socket)
    monkeypatch.setattr(socket, "create_connection", forbidden_socket)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden_socket)
    module = importlib.import_module("stock_research_agent.providers.fixtures.provider")
    importlib.reload(module)
