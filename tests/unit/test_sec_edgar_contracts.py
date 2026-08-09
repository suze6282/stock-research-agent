from __future__ import annotations

from datetime import UTC, date, datetime
from importlib import import_module

import pytest
from pydantic import ValidationError


def _contracts() -> object:
    return import_module("stock_research_agent.providers.sec_edgar.schemas")


def test_sec_identifiers_normalize_deterministically() -> None:
    contracts = _contracts()

    assert contracts.normalize_cik("723125") == "0000723125"  # type: ignore[attr-defined]
    assert (  # type: ignore[attr-defined]
        contracts.normalize_accession("000072312525000028") == "0000723125-25-000028"
    )
    assert (  # type: ignore[attr-defined]
        contracts.accession_without_dashes("0000723125-25-000028") == "000072312525000028"
    )

    for invalid in ("", "CIK723125", "-1", "12345678901"):
        with pytest.raises(ValueError):
            contracts.normalize_cik(invalid)  # type: ignore[attr-defined]
    for invalid in ("0000723125-25-28", "0000723125/25/000028", "not-accession"):
        with pytest.raises(ValueError):
            contracts.normalize_accession(invalid)  # type: ignore[attr-defined]


def test_submissions_and_company_facts_envelopes_are_strict_metadata() -> None:
    contracts = _contracts()
    filing = contracts.SecFilingMetadata(  # type: ignore[attr-defined]
        accession_number="0000723125-25-000028",
        form="10-K",
        filed_date=date(2025, 10, 3),
        report_date=date(2025, 8, 28),
        accepted_at=datetime(2025, 10, 3, 10, 30, tzinfo=UTC),
        primary_document="mu-20250828.htm",
    )
    submissions = contracts.SecSubmissionsMetadata(  # type: ignore[attr-defined]
        provider_code="SEC_EDGAR_PUBLIC_V1",
        source_endpoint_type="SEC_SUBMISSIONS_JSON",
        source_identity="SEC_SUBMISSIONS_JSON:0000723125",
        cik="0000723125",
        entity_name="Micron Technology, Inc.",
        tickers=("MU",),
        exchanges=("Nasdaq",),
        filings=(filing,),
        evidence_role="METADATA_ONLY",
    )
    company_facts = contracts.SecCompanyFactsEnvelope(  # type: ignore[attr-defined]
        provider_code="SEC_EDGAR_PUBLIC_V1",
        source_endpoint_type="SEC_COMPANY_FACTS_JSON",
        source_identity="SEC_COMPANY_FACTS_JSON:0000723125",
        cik="0000723125",
        entity_name="Micron Technology, Inc.",
        taxonomy_names=("dei", "us-gaap"),
        fact_count=0,
        evidence_role="METADATA_ONLY",
    )

    assert submissions.filings == (filing,)
    assert company_facts.fact_count == 0
    with pytest.raises(ValidationError):
        contracts.SecSubmissionsMetadata(  # type: ignore[attr-defined]
            **submissions.model_dump(),
            unexpected_raw_field={"must": "remain only in raw artifact"},
        )
    with pytest.raises(ValidationError):
        contracts.SecSubmissionsMetadata(  # type: ignore[attr-defined]
            **(submissions.model_dump() | {"evidence_role": "COMPANY_BODY"})
        )


def test_filing_index_and_document_descriptor_preserve_source_identity() -> None:
    contracts = _contracts()
    document = contracts.SecFilingDocument(  # type: ignore[attr-defined]
        sequence=1,
        filename="mu-20250828.htm",
        description="10-K",
        document_type="10-K",
        content_type="text/html",
    )
    index = contracts.SecFilingIndex(  # type: ignore[attr-defined]
        provider_code="SEC_EDGAR_PUBLIC_V1",
        source_endpoint_type="SEC_FILING_INDEX",
        source_identity=("SEC_FILING_INDEX:0000723125:0000723125-25-000028"),
        cik="0000723125",
        accession_number="0000723125-25-000028",
        documents=(document,),
        evidence_role="METADATA_ONLY",
    )
    descriptor = contracts.SecDocumentArtifactDescriptor(  # type: ignore[attr-defined]
        provider_code="SEC_EDGAR_PUBLIC_V1",
        source_endpoint_type="SEC_FILING_DOCUMENT",
        source_identity=("SEC_FILING_DOCUMENT:0000723125:0000723125-25-000028:mu-20250828.htm"),
        cik="0000723125",
        accession_number="0000723125-25-000028",
        filename="mu-20250828.htm",
        artifact_kind=contracts.SecArtifactKind.PRIMARY_FILING_DOCUMENT,  # type: ignore[attr-defined]
        content_type="text/html",
        source_published_at=datetime(2025, 10, 3, 10, 30, tzinfo=UTC),
        evidence_role=contracts.SecEvidenceRole.COMPANY_BODY,  # type: ignore[attr-defined]
    )

    assert index.documents == (document,)
    assert descriptor.evidence_role.value == "COMPANY_BODY"


@pytest.mark.parametrize(
    ("model_name", "overrides"),
    [
        ("SecFilingMetadata", {"form": "10 K"}),
        ("SecFilingMetadata", {"accepted_at": datetime(2025, 10, 3, 10, 30)}),
        ("SecFilingDocument", {"content_type": "application/octet-stream"}),
        (
            "SecDocumentArtifactDescriptor",
            {"source_identity": "SEC_FILING_DOCUMENT:wrong"},
        ),
        (
            "SecDocumentArtifactDescriptor",
            {
                "artifact_kind": "FILING_INDEX",
                "evidence_role": "COMPANY_BODY",
            },
        ),
    ],
)
def test_invalid_sec_contract_values_fail(model_name: str, overrides: dict[str, object]) -> None:
    contracts = _contracts()
    values: dict[str, object]
    if model_name == "SecFilingMetadata":
        values = {
            "accession_number": "0000723125-25-000028",
            "form": "10-K",
            "filed_date": date(2025, 10, 3),
            "report_date": date(2025, 8, 28),
            "accepted_at": datetime(2025, 10, 3, 10, 30, tzinfo=UTC),
            "primary_document": "mu-20250828.htm",
        }
    elif model_name == "SecFilingDocument":
        values = {
            "sequence": 1,
            "filename": "mu-20250828.htm",
            "description": "10-K",
            "document_type": "10-K",
            "content_type": "text/html",
        }
    else:
        values = {
            "provider_code": "SEC_EDGAR_PUBLIC_V1",
            "source_endpoint_type": "SEC_FILING_DOCUMENT",
            "source_identity": (
                "SEC_FILING_DOCUMENT:0000723125:0000723125-25-000028:mu-20250828.htm"
            ),
            "cik": "0000723125",
            "accession_number": "0000723125-25-000028",
            "filename": "mu-20250828.htm",
            "artifact_kind": contracts.SecArtifactKind.PRIMARY_FILING_DOCUMENT,  # type: ignore[attr-defined]
            "content_type": "text/html",
            "source_published_at": datetime(2025, 10, 3, 10, 30, tzinfo=UTC),
            "evidence_role": contracts.SecEvidenceRole.COMPANY_BODY,  # type: ignore[attr-defined]
        }
        if "artifact_kind" in overrides:
            overrides["artifact_kind"] = contracts.SecArtifactKind(  # type: ignore[attr-defined]
                overrides["artifact_kind"]
            )
        if "evidence_role" in overrides:
            overrides["evidence_role"] = contracts.SecEvidenceRole(  # type: ignore[attr-defined]
                overrides["evidence_role"]
            )
    values.update(overrides)

    with pytest.raises(ValidationError):
        getattr(contracts, model_name)(**values)
