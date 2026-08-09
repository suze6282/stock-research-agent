from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

PROVIDER_ID = UUID("00000000-0000-4000-8000-000000000091")
CAPABILITY_ID = UUID("00000000-0000-4000-8000-000000000092")
ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000000093")
SECURITY_ID = UUID("00000000-0000-4000-8000-000000000009")
AS_OF = datetime(2026, 7, 29, tzinfo=UTC)


def _module() -> object:
    return import_module("stock_research_agent.providers.sec_edgar.adapter")


def _adapter() -> object:
    module = _module()
    return module.SecEdgarAdapter(  # type: ignore[attr-defined]
        security_id=SECURITY_ID,
        cik="0000723125",
        approved_capabilities=tuple(module.SecEdgarCapability),  # type: ignore[attr-defined]
        approved_forms=("10-K", "10-Q", "8-K"),
    )


def _context(body: bytes, **changes: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "provider_definition_id": PROVIDER_ID,
        "provider_capability_id": CAPABILITY_ID,
        "raw_artifact_id": ARTIFACT_ID,
        "source_checksum": hashlib.sha256(body).hexdigest(),
        "manifest_checksum": "b" * 64,
        "source_identity": "SEC_SUBMISSIONS_JSON:0000723125",
        "source_endpoint_type": "SEC_SUBMISSIONS_JSON",
        "artifact_kind": module.SecArtifactKind.SUBMISSIONS_METADATA,  # type: ignore[attr-defined]
        "content_type": "application/json",
        "research_as_of_time": AS_OF,
        "retrieved_at": AS_OF,
        "source_published_at": None,
        "expected_accession_number": None,
        "expected_document_path": None,
        "synthetic_status": ProviderSyntheticStatus.FIXTURE_REAL_EXCERPT,
    }
    values.update(changes)
    return module.SecParseContext(**values)  # type: ignore[attr-defined]


def _submissions_body(*, accepted_at: str = "2025-10-03T10:30:00Z") -> bytes:
    return json.dumps(
        {
            "cik": "0000723125",
            "name": "Micron Technology, Inc.",
            "tickers": ["MU"],
            "exchanges": ["Nasdaq"],
            "filings": [
                {
                    "accessionNumber": "0000723125-25-000028",
                    "form": "10-K",
                    "filingDate": "2025-10-03",
                    "reportDate": "2025-08-28",
                    "acceptanceDateTime": accepted_at,
                    "primaryDocument": "mu-20250828.htm",
                    "unknownRawField": "retained only in raw artifact",
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def test_sec_submissions_parse_as_metadata_with_exact_lineage() -> None:
    body = _submissions_body()

    batch = _adapter().parse_response(body, _context(body))

    assert batch.record_count == 1
    record = batch.records[0]
    assert record.source_checksum == hashlib.sha256(body).hexdigest()
    assert record.source_published_at == datetime(2025, 10, 3, 10, 30, tzinfo=UTC)
    assert record.text_values["evidence_role"] == "METADATA_ONLY"
    assert record.text_values["form"] == "10-K"
    assert record.text_values["accession_number"] == "0000723125-25-000028"
    assert "unknownRawField" not in record.text_values


def test_sec_company_facts_preserve_exact_decimal_and_unknown_publication() -> None:
    module = _module()
    body = json.dumps(
        {
            "cik": 723125,
            "entityName": "Micron Technology, Inc.",
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "label": "Revenue",
                        "description": "Revenue",
                        "units": {
                            "USD": [
                                {
                                    "start": "2024-08-30",
                                    "end": "2025-08-28",
                                    "val": "37378000000.00",
                                    "accn": "0000723125-25-000028",
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2025-10-03",
                                }
                            ]
                        },
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    context = _context(
        body,
        source_identity="SEC_COMPANY_FACTS_JSON:0000723125",
        source_endpoint_type="SEC_COMPANY_FACTS_JSON",
        artifact_kind=module.SecArtifactKind.COMPANY_FACTS,  # type: ignore[attr-defined]
    )

    batch = _adapter().parse_response(body, context)

    assert batch.records[0].numeric_values["value"] == "37378000000.00"
    assert batch.records[0].source_published_at is None
    assert batch.records[0].warning_codes == ("UNKNOWN_PUBLISHED_AT",)
    assert batch.records[0].text_values["filed_date"] == "2025-10-03"


def test_sec_primary_document_is_body_but_raw_bytes_are_not_projected() -> None:
    module = _module()
    body = b"<!doctype html><html><body>synthetic parser protocol</body></html>"
    context = _context(
        body,
        source_identity=("SEC_FILING_DOCUMENT:0000723125:0000723125-25-000028:mu-20250828.htm"),
        source_endpoint_type="SEC_FILING_DOCUMENT",
        artifact_kind=module.SecArtifactKind.PRIMARY_FILING_DOCUMENT,  # type: ignore[attr-defined]
        content_type="text/html",
        source_published_at=datetime(2025, 10, 3, 10, 30, tzinfo=UTC),
        expected_accession_number="0000723125-25-000028",
        expected_document_path="mu-20250828.htm",
    )

    record = _adapter().parse_response(body, context).records[0]

    assert record.text_values["evidence_role"] == "COMPANY_BODY"
    assert record.text_values["artifact_kind"] == "PRIMARY_FILING_DOCUMENT"
    assert body.decode() not in record.text_values.values()


def test_sec_parser_never_substitutes_retrieved_time_for_publication() -> None:
    module = _module()
    body = b"<html><body>synthetic parser protocol</body></html>"
    context = _context(
        body,
        source_identity=("SEC_FILING_DOCUMENT:0000723125:0000723125-25-000028:mu-20250828.htm"),
        source_endpoint_type="SEC_FILING_DOCUMENT",
        artifact_kind=module.SecArtifactKind.PRIMARY_FILING_DOCUMENT,  # type: ignore[attr-defined]
        content_type="text/html",
        expected_accession_number="0000723125-25-000028",
        expected_document_path="mu-20250828.htm",
    )

    record = _adapter().parse_response(body, context).records[0]

    assert record.source_published_at is None
    assert record.warning_codes == ("UNKNOWN_PUBLISHED_AT",)
    assert record.source_published_at != context.retrieved_at


@pytest.mark.parametrize(
    ("body_factory", "context_changes", "error"),
    (
        (
            lambda: b"{not-json",
            {},
            "SEC_RESPONSE_MALFORMED",
        ),
        (
            lambda: b"not html",
            {
                "source_identity": (
                    "SEC_FILING_DOCUMENT:0000723125:0000723125-25-000028:mu-20250828.htm"
                ),
                "source_endpoint_type": "SEC_FILING_DOCUMENT",
                "artifact_kind": "PRIMARY_FILING_DOCUMENT",
                "content_type": "text/html",
                "expected_accession_number": "0000723125-25-000028",
                "expected_document_path": "mu-20250828.htm",
            },
            "SEC_RESPONSE_MALFORMED",
        ),
    ),
)
def test_sec_parser_rejects_malformed_json_or_html(
    body_factory: object,
    context_changes: dict[str, object],
    error: str,
) -> None:
    module = _module()
    body = body_factory()  # type: ignore[operator]
    if "artifact_kind" in context_changes:
        context_changes["artifact_kind"] = module.SecArtifactKind(  # type: ignore[attr-defined]
            context_changes["artifact_kind"]
        )

    with pytest.raises(ValueError, match=error):
        _adapter().parse_response(body, _context(body, **context_changes))


def test_sec_parser_rejects_checksum_future_and_accession_mismatch() -> None:
    body = _submissions_body()
    with pytest.raises(ValueError, match="CHECKSUM"):
        _adapter().parse_response(body, _context(body, source_checksum="a" * 64))
    future = _submissions_body(accepted_at=(AS_OF + timedelta(seconds=1)).isoformat())
    with pytest.raises(ValueError, match="FUTURE"):
        _adapter().parse_response(future, _context(future))

    module = _module()
    document = b"<html><body>synthetic parser protocol</body></html>"
    context = _context(
        document,
        source_identity=("SEC_FILING_DOCUMENT:0000723125:0000723125-25-000028:mu-20250828.htm"),
        source_endpoint_type="SEC_FILING_DOCUMENT",
        artifact_kind=module.SecArtifactKind.PRIMARY_FILING_DOCUMENT,  # type: ignore[attr-defined]
        content_type="text/html",
        expected_accession_number="0000723125-26-000015",
        expected_document_path="mu-20250828.htm",
    )
    with pytest.raises(ValueError, match="ACCESSION"):
        _adapter().parse_response(document, context)
