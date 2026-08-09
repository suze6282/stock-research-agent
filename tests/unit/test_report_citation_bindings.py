from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    LocatorType,
)
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    CitationVerification,
    DocumentVersionRecord,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import EvidenceRole

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)
SECURITY_ID = UUID("10000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000002")
BLOCK_ID = UUID("20000000-0000-0000-0000-000000000001")
CLAIM_BINDING_ID = UUID("20000000-0000-0000-0000-000000000002")
EVIDENCE_BINDING_ID = UUID("20000000-0000-0000-0000-000000000003")
EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000001")
CITATION_ID = UUID("40000000-0000-0000-0000-000000000001")
DOCUMENT_ID = UUID("50000000-0000-0000-0000-000000000001")
EXCERPT = "Verified company disclosure."
EXCERPT_CHECKSUM = hashlib.sha256(EXCERPT.encode("utf-8")).hexdigest()
DOCUMENT_CHECKSUM = "a" * 64
LOCATOR_CHECKSUM = "b" * 64


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.bindings")


def _evidence_binding(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": EVIDENCE_BINDING_ID,
        "report_block_id": BLOCK_ID,
        "report_claim_binding_id": CLAIM_BINDING_ID,
        "claim_evidence_link_id": UUID("60000000-0000-0000-0000-000000000001"),
        "evidence_id": EVIDENCE_ID,
        "role": EvidenceRole.PRIMARY,
        "visible_reference_kind": module.VisibleReferenceKind.EVIDENCE,
        "visible_reference": "EV-001",
        "item_or_row_key": "disclosure.0",
        "citation_id": CITATION_ID,
        "source_record_id": DOCUMENT_ID,
        "source_checksum": DOCUMENT_CHECKSUM,
        "created_at": NOW,
    }
    values.update(updates)
    return module.ReportEvidenceBindingWrite.model_validate(values)


def _citation(**updates: object) -> CitationAnchorRecord:
    values: dict[str, object] = {
        "id": CITATION_ID,
        "document_version_id": DOCUMENT_ID,
        "parse_run_id": UUID("60000000-0000-0000-0000-000000000002"),
        "page_id": None,
        "section_id": None,
        "chunk_id": UUID("60000000-0000-0000-0000-000000000003"),
        "locator_type": LocatorType.TEXT_OFFSET_RANGE,
        "start_page": None,
        "end_page": None,
        "html_anchor": None,
        "json_pointer": None,
        "start_offset": 10,
        "end_offset": 38,
        "excerpt": EXCERPT,
        "excerpt_checksum": EXCERPT_CHECKSUM,
        "canonical_text_checksum": "c" * 64,
        "document_checksum": DOCUMENT_CHECKSUM,
        "citation_version": "citation-v1",
        "parser_version": "text-parser-v1",
        "sanitizer_version": "document-sanitizer-v1",
        "locator_checksum": LOCATOR_CHECKSUM,
        "created_at": NOW,
    }
    values.update(updates)
    return CitationAnchorRecord.model_validate(values)


def _document(**updates: object) -> DocumentVersionRecord:
    values: dict[str, object] = {
        "id": DOCUMENT_ID,
        "logical_document_id": UUID("70000000-0000-0000-0000-000000000001"),
        "source_document_id": UUID("70000000-0000-0000-0000-000000000002"),
        "security_id": SECURITY_ID,
        "provider_id": UUID("70000000-0000-0000-0000-000000000003"),
        "source_payload_id": UUID("70000000-0000-0000-0000-000000000004"),
        "version_number": 1,
        "supersedes_document_version_id": None,
        "storage_uri": "blob://documents/verified",
        "mime_type": "text/plain",
        "checksum_algorithm": "sha256",
        "checksum": DOCUMENT_CHECKSUM,
        "byte_size": 1024,
        "published_at": NOW - timedelta(days=1),
        "filed_at": None,
        "period_end": None,
        "retrieved_at": NOW,
        "document_language": "en-US",
        "trust_level": "OFFICIAL_REGULATORY",
        "evidence_origin": "REAL_VERIFIED",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
        "source_version_status": "ACTIVE",
        "created_at": NOW,
    }
    return DocumentVersionRecord.model_construct(**{**values, **updates})


def _verification(**updates: object) -> CitationVerification:
    return CitationVerification.model_validate(
        {
            "status": CitationStatus.VALID,
            "citation_id": CITATION_ID,
            "warnings": (),
            **updates,
        }
    )


def _manifest(**updates: object) -> ReportInputManifest:
    values: dict[str, object] = {
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "citation_ids": (CITATION_ID,),
    }
    values.update(updates)
    return ReportInputManifest.model_construct(**values)


def _binding(**updates: object) -> object:
    module = _module()
    citation = _citation()
    values: dict[str, object] = {
        "id": UUID("80000000-0000-0000-0000-000000000001"),
        "report_evidence_binding_id": EVIDENCE_BINDING_ID,
        "citation_id": CITATION_ID,
        "document_version_id": DOCUMENT_ID,
        "visible_reference": "CIT-001",
        "locator_summary": module.citation_locator_summary(citation),
        "rendered_excerpt": EXCERPT,
        "rendered_excerpt_checksum": EXCERPT_CHECKSUM,
        "citation_status": CitationStatus.VALID,
        "created_at": NOW,
    }
    values.update(updates)
    return module.ReportCitationBindingWrite.model_validate(values)


def test_valid_exact_citation_projection_passes_and_is_frozen() -> None:
    module = _module()
    binding = _binding()

    assert (
        module.validate_citation_binding(
            _evidence_binding(),
            _citation(),
            _document(),
            _verification(),
            binding,
            _manifest(),
        )
        is None
    )
    with pytest.raises(ValidationError, match="Instance is frozen"):
        binding.rendered_excerpt = "rewritten"


@pytest.mark.parametrize(
    ("citation_updates", "document_updates", "evidence_updates", "expected_code"),
    [
        (
            {"id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            {},
            "CITATION_BINDING_CITATION_ID_MISMATCH",
        ),
        (
            {"document_version_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            {},
            "CITATION_DOCUMENT_VERSION_MISMATCH",
        ),
        (
            {},
            {"id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            "CITATION_DOCUMENT_VERSION_MISMATCH",
        ),
        (
            {},
            {},
            {"citation_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            "EVIDENCE_CITATION_ID_MISMATCH",
        ),
    ],
)
def test_citation_must_follow_exact_evidence_and_document_chain(
    citation_updates: dict[str, object],
    document_updates: dict[str, object],
    evidence_updates: dict[str, object],
    expected_code: str,
) -> None:
    module = _module()
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_citation_binding(
            _evidence_binding(**evidence_updates),
            _citation(**citation_updates),
            _document(**document_updates),
            _verification(),
            _binding(),
            _manifest(),
        )
    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("document_updates", "manifest_updates", "expected_code"),
    [
        (
            {"security_id": UUID("ffffffff-0000-0000-0000-000000000001")},
            {},
            "CITATION_DOCUMENT_SECURITY_MISMATCH",
        ),
        (
            {"published_at": NOW + timedelta(seconds=1)},
            {},
            "FUTURE_CITATION_DOCUMENT",
        ),
        (
            {"published_at": None},
            {},
            "CITATION_DOCUMENT_PUBLISHED_AT_UNKNOWN",
        ),
        (
            {"checksum": "f" * 64},
            {},
            "CITATION_DOCUMENT_CHECKSUM_MISMATCH",
        ),
        (
            {},
            {"citation_ids": ()},
            "CITATION_NOT_IN_REPORT_MANIFEST",
        ),
    ],
)
def test_citation_document_must_match_strict_historical_manifest(
    document_updates: dict[str, object],
    manifest_updates: dict[str, object],
    expected_code: str,
) -> None:
    module = _module()
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_citation_binding(
            _evidence_binding(),
            _citation(),
            _document(**document_updates),
            _verification(),
            _binding(),
            _manifest(**manifest_updates),
        )
    assert raised.value.code == expected_code


def test_only_valid_verifier_result_can_be_bound() -> None:
    module = _module()
    for status in CitationStatus:
        if status is CitationStatus.VALID:
            continue
        with pytest.raises(module.ReportBindingError) as raised:
            module.validate_citation_binding(
                _evidence_binding(),
                _citation(),
                _document(),
                _verification(status=status),
                _binding(),
                _manifest(),
            )
        assert raised.value.code == "CITATION_VERIFICATION_NOT_VALID"


@pytest.mark.parametrize(
    ("binding_updates", "expected_code"),
    [
        ({"rendered_excerpt": "Rewritten text."}, "CITATION_EXCERPT_REWRITE_FORBIDDEN"),
        ({"rendered_excerpt_checksum": "f" * 64}, "CITATION_EXCERPT_CHECKSUM_MISMATCH"),
        ({"locator_summary": "text:0-1"}, "CITATION_LOCATOR_SUMMARY_MISMATCH"),
        ({"rendered_excerpt": "<script>hidden</script>"}, "UNSAFE_CITATION_EXCERPT"),
        ({"rendered_excerpt": "token=secret"}, "UNSAFE_CITATION_EXCERPT"),
        ({"rendered_excerpt": "C:\\private\\file.txt"}, "UNSAFE_CITATION_EXCERPT"),
    ],
)
def test_citation_cannot_rewrite_locator_excerpt_or_expose_unsafe_text(
    binding_updates: dict[str, object],
    expected_code: str,
) -> None:
    module = _module()
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_citation_binding(
            _evidence_binding(),
            _citation(),
            _document(),
            _verification(),
            _binding(**binding_updates),
            _manifest(),
        )
    assert raised.value.code == expected_code


def test_citation_binding_set_is_bounded_and_references_are_unique() -> None:
    module = _module()
    duplicate = _binding(
        id=UUID("80000000-0000-0000-0000-000000000002"),
        citation_id=UUID("40000000-0000-0000-0000-000000000002"),
    )
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_citation_binding_set((_binding(), duplicate))
    assert raised.value.code == "DUPLICATE_VISIBLE_CITATION_REFERENCE"

    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_citation_binding_set(tuple(_binding() for _ in range(1001)))
    assert raised.value.code == "CITATION_BINDING_LIMIT_EXCEEDED"
