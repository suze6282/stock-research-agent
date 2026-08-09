from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.data_access.schemas import SourceDocumentRecord
from stock_research_agent.domain.documents.enums import CitationStatus, LocatorType
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    DocumentVersionRecord,
)
from stock_research_agent.domain.reports.bindings import (
    ReportCitationBindingWrite,
    ReportEvidenceBindingWrite,
    VisibleReferenceKind,
)
from stock_research_agent.domain.reports.blocks import validate_report_block
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import EvidenceRole

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)
SECURITY_ID = UUID(int=11)
SNAPSHOT_ID = UUID(int=12)
SOURCE_DOCUMENT_ID = UUID(int=13)
DOCUMENT_VERSION_ID = UUID(int=14)
CITATION_ID = UUID(int=15)
EVIDENCE_BINDING_ID = UUID(int=16)
EXCERPT = "Revenue increased during the reported period."
EXCERPT_CHECKSUM = hashlib.sha256(EXCERPT.encode("utf-8")).hexdigest()


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.appendices")


def _source_document() -> SourceDocumentRecord:
    return SourceDocumentRecord.model_construct(
        id=SOURCE_DOCUMENT_ID,
        security_id=SECURITY_ID,
        provider_id=UUID(int=20),
        source_payload_id=UUID(int=21),
        provider_document_id="filing-2025",
        document_type="ANNUAL_REPORT",
        title="Verified Annual Report 2025",
        form_type=None,
        accession_number=None,
        announcement_id=None,
        period_end=date(2025, 12, 31),
        filed_at=NOW - timedelta(days=1),
        published_at=NOW - timedelta(days=1),
        source_url="https://example.invalid/must-not-leak",
        primary_document_name=None,
        mime_type="text/plain",
        storage_uri="blob://must-not-leak/private",
        checksum="a" * 64,
        byte_size=1024,
        document_status="AVAILABLE",
        retrieved_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _document() -> DocumentVersionRecord:
    return DocumentVersionRecord.model_construct(
        id=DOCUMENT_VERSION_ID,
        logical_document_id=UUID(int=30),
        source_document_id=SOURCE_DOCUMENT_ID,
        security_id=SECURITY_ID,
        provider_id=UUID(int=20),
        source_payload_id=UUID(int=21),
        version_number=2,
        supersedes_document_version_id=UUID(int=29),
        storage_uri="blob://must-not-leak/version",
        mime_type="text/plain",
        checksum_algorithm="sha256",
        checksum="a" * 64,
        byte_size=1024,
        published_at=NOW - timedelta(days=1),
        filed_at=NOW - timedelta(days=1),
        period_end=date(2025, 12, 31),
        retrieved_at=NOW,
        document_language="en-US",
        trust_level="OFFICIAL_COMPANY",
        evidence_origin="REAL_VERIFIED",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        source_version_status="ACTIVE",
        created_at=NOW,
    )


def _citation() -> CitationAnchorRecord:
    return CitationAnchorRecord.model_validate(
        {
            "id": CITATION_ID,
            "document_version_id": DOCUMENT_VERSION_ID,
            "parse_run_id": UUID(int=40),
            "page_id": None,
            "section_id": None,
            "chunk_id": UUID(int=41),
            "locator_type": LocatorType.TEXT_OFFSET_RANGE,
            "start_page": None,
            "end_page": None,
            "html_anchor": None,
            "json_pointer": None,
            "start_offset": 10,
            "end_offset": 58,
            "excerpt": EXCERPT,
            "excerpt_checksum": EXCERPT_CHECKSUM,
            "canonical_text_checksum": "b" * 64,
            "document_checksum": "a" * 64,
            "citation_version": "citation-v1",
            "parser_version": "text-parser-v1",
            "sanitizer_version": "document-sanitizer-v1",
            "locator_checksum": "c" * 64,
            "created_at": NOW,
        }
    )


def _evidence_binding() -> ReportEvidenceBindingWrite:
    return ReportEvidenceBindingWrite(
        id=EVIDENCE_BINDING_ID,
        report_block_id=UUID(int=50),
        report_claim_binding_id=UUID(int=51),
        claim_evidence_link_id=UUID(int=52),
        evidence_id=UUID(int=53),
        role=EvidenceRole.PRIMARY,
        visible_reference_kind=VisibleReferenceKind.EVIDENCE,
        visible_reference="EV-001",
        item_or_row_key="disclosure.0",
        citation_id=CITATION_ID,
        source_record_id=DOCUMENT_VERSION_ID,
        source_checksum="a" * 64,
        created_at=NOW,
    )


def _citation_binding(**updates: object) -> ReportCitationBindingWrite:
    values: dict[str, object] = {
        "id": UUID(int=60),
        "report_evidence_binding_id": EVIDENCE_BINDING_ID,
        "citation_id": CITATION_ID,
        "document_version_id": DOCUMENT_VERSION_ID,
        "visible_reference": "CIT-001",
        "locator_summary": "text:10-58",
        "rendered_excerpt": EXCERPT,
        "rendered_excerpt_checksum": EXCERPT_CHECKSUM,
        "citation_status": CitationStatus.VALID,
        "created_at": NOW,
    }
    values.update(updates)
    return ReportCitationBindingWrite.model_validate(values)


def _manifest() -> ReportInputManifest:
    return ReportInputManifest.model_construct(
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        citation_ids=(CITATION_ID,),
    )


def _view(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "citation_binding": _citation_binding(),
        "evidence_binding": _evidence_binding(),
        "citation": _citation(),
        "document": _document(),
        "source_document": _source_document(),
    }
    values.update(updates)
    return module.CitationAppendixBindingView.model_validate(values)


def test_citation_appendix_projects_exact_bounded_original_excerpt() -> None:
    module = _module()

    block = module.build_citation_appendix(_manifest(), (_view(),), 200)

    assert block.block_key == "appendix.citations"
    assert block.block_type is ReportBlockType.CITATION_LIST
    assert block.status is ReportBlockStatus.COMPLETE
    assert block.payload["rows"] == [
        {
            "reference": "CIT-001",
            "citation_id": str(CITATION_ID),
            "title": "Verified Annual Report 2025",
            "document_type": "ANNUAL_REPORT",
            "document_version_id": str(DOCUMENT_VERSION_ID),
            "version_number": 2,
            "published_at": "2026-07-26T08:00:00Z",
            "period_end": "2025-12-31",
            "locator": "text:10-58",
            "excerpt": EXCERPT,
            "citation_status": "VALID",
            "trust_level": "OFFICIAL_COMPANY",
        }
    ]
    serialized = str(block.payload).casefold()
    assert "source_url" not in serialized
    assert "storage_uri" not in serialized
    assert "must-not-leak" not in serialized
    assert "<script" not in serialized
    validate_report_block(block)


def test_citation_appendix_rejects_oversized_or_unsafe_excerpt() -> None:
    module = _module()

    for view, maximum, code in (
        (_view(), len(EXCERPT) - 1, "CITATION_APPENDIX_EXCERPT_TOO_LONG"),
        (
            _view(
                citation_binding=_citation_binding(
                    rendered_excerpt="<script>alert(1)</script>",
                    rendered_excerpt_checksum=hashlib.sha256(
                        b"<script>alert(1)</script>"
                    ).hexdigest(),
                )
            ),
            200,
            "CITATION_APPENDIX_EXCERPT_UNSAFE",
        ),
    ):
        with pytest.raises(module.ReportAppendixError) as raised:
            module.build_citation_appendix(_manifest(), (view,), maximum)
        assert raised.value.code == code


def test_citation_appendix_rejects_unsealed_or_mismatched_chain() -> None:
    module = _module()

    for manifest, view, code in (
        (
            _manifest().model_copy(update={"citation_ids": ()}),
            _view(),
            "CITATION_APPENDIX_NOT_IN_MANIFEST",
        ),
        (
            _manifest(),
            _view(
                evidence_binding=_evidence_binding().model_copy(
                    update={"citation_id": UUID(int=999)}
                )
            ),
            "CITATION_APPENDIX_CHAIN_MISMATCH",
        ),
    ):
        with pytest.raises(module.ReportAppendixError) as raised:
            module.build_citation_appendix(manifest, (view,), 200)
        assert raised.value.code == code
