"""Deterministic bounded indexes and appendices for research reports."""

from __future__ import annotations

import hashlib
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.data_access.schemas import SourceDocumentRecord
from stock_research_agent.domain.documents.enums import CitationStatus
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    DocumentVersionRecord,
)
from stock_research_agent.domain.reports.bindings import (
    ReportCitationBindingWrite,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
    citation_locator_summary,
)
from stock_research_agent.domain.reports.blocks import ReportBlockDraft
from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    StructuredReportContent,
)
from stock_research_agent.domain.reports.schemas import (
    FrozenReportContract,
    ReportInputManifest,
)
from stock_research_agent.domain.research_agent.enums import (
    ClaimSupportStatus,
    EvidenceStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)


class ReportAppendixError(ValueError):
    """Stable rejection for an incomplete or inconsistent appendix graph."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class EvidenceAppendixBindingView(FrozenReportContract):
    """Read-only sealed input needed for one bounded Evidence appendix row."""

    visible_reference: str = Field(pattern=r"^(EV|MET|LIM|CON)-[0-9]{3}$")
    claim: ResearchClaimRecord
    claim_binding: ReportClaimBindingWrite
    evidence: ResearchEvidenceRecord | None = None
    evidence_binding: ReportEvidenceBindingWrite | None = None


class CitationAppendixBindingView(FrozenReportContract):
    """Verified immutable records required for one Citation appendix row."""

    citation_binding: ReportCitationBindingWrite
    evidence_binding: ReportEvidenceBindingWrite
    citation: CitationAnchorRecord
    document: DocumentVersionRecord
    source_document: SourceDocumentRecord


def build_claim_index(
    content: StructuredReportContent,
    claims: tuple[ResearchClaimRecord, ...],
    bindings: tuple[ReportClaimBindingWrite, ...],
) -> ReportBlockDraft:
    """Project each bound Claim used by report content exactly once."""

    claim_by_id = _unique_claims(claims)
    bound_claim_ids = {binding.claim_id for binding in bindings}
    used_claim_ids = _used_claim_ids(content)
    rows: list[dict[str, str]] = []
    for claim_id in used_claim_ids:
        claim = claim_by_id.get(claim_id)
        if claim is None:
            raise ReportAppendixError("CLAIM_INDEX_CLAIM_MISSING")
        if claim_id not in bound_claim_ids:
            raise ReportAppendixError("CLAIM_INDEX_BINDING_MISSING")
        if claim.support_status is None:
            raise ReportAppendixError("CLAIM_INDEX_SUPPORT_STATUS_MISSING")
        rows.append(
            {
                "claim_id": str(claim.id),
                "statement_code": claim.statement_code,
                "claim_type": claim.claim_type.value,
                "support_status": claim.support_status.value,
                "classification": _claim_classification(claim.support_status),
            }
        )
    values = {
        "block_key": "appendix.claim_index",
        "block_index": 0,
        "block_type": ReportBlockType.CLAIM_INDEX,
        "status": (
            ReportBlockStatus.COMPLETE
            if all(
                claim_by_id[claim_id].support_status is ClaimSupportStatus.SUPPORTED
                for claim_id in used_claim_ids
            )
            else ReportBlockStatus.PARTIAL
        ),
        "text": None,
        "payload": {"rows": rows},
        "factual_location_key": "claim_index.rows",
    }
    return ReportBlockDraft.model_validate({**values, "checksum": report_checksum(values)})


def build_evidence_appendix(
    manifest: ReportInputManifest,
    bindings: tuple[EvidenceAppendixBindingView, ...],
) -> ReportBlockDraft:
    """Project safe fields from bound Evidence without exposing raw payloads."""

    ordered = tuple(sorted(bindings, key=_evidence_reference_order))
    references = [item.visible_reference for item in ordered]
    if len(references) != len(set(references)):
        raise ReportAppendixError("EVIDENCE_APPENDIX_REFERENCE_DUPLICATE")
    rows = [_evidence_row(manifest, item) for item in ordered]
    values = {
        "block_key": "appendix.evidence",
        "block_index": 0,
        "block_type": ReportBlockType.EVIDENCE_TABLE,
        "status": (
            ReportBlockStatus.COMPLETE
            if all(
                item.claim.support_status is ClaimSupportStatus.SUPPORTED
                and item.evidence is not None
                and item.evidence.status is EvidenceStatus.VALID
                for item in ordered
            )
            else ReportBlockStatus.PARTIAL
        ),
        "text": None,
        "payload": {"rows": rows},
        "factual_location_key": "evidence_appendix.rows",
    }
    return ReportBlockDraft.model_validate({**values, "checksum": report_checksum(values)})


def _evidence_row(
    manifest: ReportInputManifest,
    item: EvidenceAppendixBindingView,
) -> dict[str, object]:
    claim = item.claim
    evidence = item.evidence
    binding = item.evidence_binding
    if claim.id not in manifest.claim_ids:
        raise ReportAppendixError("EVIDENCE_APPENDIX_CLAIM_NOT_IN_MANIFEST")
    if item.claim_binding.claim_id != claim.id:
        raise ReportAppendixError("EVIDENCE_APPENDIX_CLAIM_BINDING_MISMATCH")
    structured_reference = item.visible_reference.startswith(("EV-", "MET-"))
    if structured_reference:
        if evidence is None or binding is None:
            raise ReportAppendixError("EVIDENCE_APPENDIX_BINDING_MISSING")
        if evidence.id not in manifest.evidence_ids:
            raise ReportAppendixError("EVIDENCE_APPENDIX_EVIDENCE_NOT_IN_MANIFEST")
        if (
            binding.evidence_id != evidence.id
            or binding.report_claim_binding_id != item.claim_binding.id
        ):
            raise ReportAppendixError("EVIDENCE_APPENDIX_BINDING_MISMATCH")
        if binding.visible_reference != item.visible_reference:
            raise ReportAppendixError("EVIDENCE_APPENDIX_REFERENCE_MISMATCH")
        if (
            evidence.security_id != manifest.security_id
            or evidence.snapshot_id != manifest.snapshot_id
            or evidence.research_as_of_time != manifest.research_as_of_time
        ):
            raise ReportAppendixError("EVIDENCE_APPENDIX_CONTEXT_MISMATCH")
    elif evidence is not None or binding is not None:
        raise ReportAppendixError("EVIDENCE_APPENDIX_DISCLOSURE_HAS_EVIDENCE")
    return {
        "reference": item.visible_reference,
        "claim_id": str(claim.id),
        "evidence_id": None if evidence is None else str(evidence.id),
        "statement_code": claim.statement_code,
        "value": None if claim.value is None else str(claim.value),
        "unit": claim.unit,
        "currency_code": claim.currency_code,
        "period": claim.period,
        "as_of_time": (
            None
            if claim.as_of_time is None
            else claim.as_of_time.isoformat().replace("+00:00", "Z")
        ),
        "source_record_type": (None if evidence is None else evidence.source_record_type),
        "source_record_id": (
            None
            if evidence is None or evidence.source_record_id is None
            else str(evidence.source_record_id)
        ),
        "source_checksum": None if evidence is None else evidence.source_checksum,
        "calculation_run_id": (
            None
            if evidence is None or evidence.calculation_run_id is None
            else str(evidence.calculation_run_id)
        ),
        "calculation_input_ids": (
            [] if evidence is None else [str(value) for value in evidence.calculation_input_ids]
        ),
        "formula_version": None if evidence is None else evidence.formula_version,
        "support_status": (None if claim.support_status is None else claim.support_status.value),
        "evidence_status": None if evidence is None else evidence.status.value,
    }


def _evidence_reference_order(
    item: EvidenceAppendixBindingView,
) -> tuple[int, int]:
    prefix, number = item.visible_reference.split("-", maxsplit=1)
    return (
        {"EV": 0, "MET": 1, "LIM": 2, "CON": 3}[prefix],
        int(number),
    )


def build_citation_appendix(
    manifest: ReportInputManifest,
    bindings: tuple[CitationAppendixBindingView, ...],
    max_excerpt_length: int,
) -> ReportBlockDraft:
    """Project one bounded safe row per used and verified Citation."""

    if not 1 <= max_excerpt_length <= 1000:
        raise ReportAppendixError("CITATION_APPENDIX_EXCERPT_LIMIT_INVALID")
    ordered = tuple(
        sorted(
            bindings,
            key=lambda item: int(item.citation_binding.visible_reference.split("-", maxsplit=1)[1]),
        )
    )
    references = [item.citation_binding.visible_reference for item in ordered]
    citation_ids = [item.citation.id for item in ordered]
    if len(references) != len(set(references)) or len(citation_ids) != len(set(citation_ids)):
        raise ReportAppendixError("CITATION_APPENDIX_DUPLICATE")
    rows = [_citation_row(manifest, item, max_excerpt_length) for item in ordered]
    values = {
        "block_key": "appendix.citations",
        "block_index": 0,
        "block_type": ReportBlockType.CITATION_LIST,
        "status": ReportBlockStatus.COMPLETE,
        "text": None,
        "payload": {"rows": rows},
        "factual_location_key": "citation_appendix.rows",
    }
    return ReportBlockDraft.model_validate({**values, "checksum": report_checksum(values)})


def _citation_row(
    manifest: ReportInputManifest,
    item: CitationAppendixBindingView,
    max_excerpt_length: int,
) -> dict[str, object]:
    binding = item.citation_binding
    evidence_binding = item.evidence_binding
    citation = item.citation
    document = item.document
    source_document = item.source_document
    excerpt = binding.rendered_excerpt
    if len(excerpt) > max_excerpt_length:
        raise ReportAppendixError("CITATION_APPENDIX_EXCERPT_TOO_LONG")
    if _unsafe_citation_text(excerpt):
        raise ReportAppendixError("CITATION_APPENDIX_EXCERPT_UNSAFE")
    if citation.id not in manifest.citation_ids:
        raise ReportAppendixError("CITATION_APPENDIX_NOT_IN_MANIFEST")
    if (
        binding.report_evidence_binding_id != evidence_binding.id
        or binding.citation_id != citation.id
        or evidence_binding.citation_id != citation.id
        or binding.document_version_id != document.id
        or citation.document_version_id != document.id
        or evidence_binding.source_record_id != document.id
        or document.source_document_id != source_document.id
    ):
        raise ReportAppendixError("CITATION_APPENDIX_CHAIN_MISMATCH")
    if (
        binding.citation_status is not CitationStatus.VALID
        or document.published_at is None
        or document.published_at > manifest.research_as_of_time
        or document.security_id != manifest.security_id
        or source_document.security_id != manifest.security_id
    ):
        raise ReportAppendixError("CITATION_APPENDIX_DOCUMENT_INVALID")
    if (
        citation.document_checksum != document.checksum
        or evidence_binding.source_checksum != document.checksum
        or binding.locator_summary != citation_locator_summary(citation)
    ):
        raise ReportAppendixError("CITATION_APPENDIX_SOURCE_MISMATCH")
    excerpt_checksum = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    if (
        excerpt != citation.excerpt
        or excerpt_checksum != citation.excerpt_checksum
        or binding.rendered_excerpt_checksum != excerpt_checksum
    ):
        raise ReportAppendixError("CITATION_APPENDIX_EXCERPT_MISMATCH")
    if _unsafe_citation_text(source_document.title):
        raise ReportAppendixError("CITATION_APPENDIX_TITLE_UNSAFE")
    return {
        "reference": binding.visible_reference,
        "citation_id": str(citation.id),
        "title": source_document.title,
        "document_type": source_document.document_type,
        "document_version_id": str(document.id),
        "version_number": document.version_number,
        "published_at": document.published_at.isoformat().replace("+00:00", "Z"),
        "period_end": (None if document.period_end is None else document.period_end.isoformat()),
        "locator": binding.locator_summary,
        "excerpt": excerpt,
        "citation_status": binding.citation_status.value,
        "trust_level": _enum_value(document.trust_level),
    }


def _unsafe_citation_text(value: str) -> bool:
    normalized = value.casefold()
    return any(
        token in normalized
        for token in (
            "<script",
            "</",
            "file://",
            "blob://",
            "password=",
            "secret=",
            "token=",
            "api_key",
            "\u200b",
            "\ufeff",
        )
    ) or (len(value) >= 3 and value[1:3] == ":\\")


def _enum_value(value: object) -> str:
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _unique_claims(
    claims: tuple[ResearchClaimRecord, ...],
) -> dict[UUID, ResearchClaimRecord]:
    claim_by_id: dict[UUID, ResearchClaimRecord] = {}
    for claim in claims:
        if claim.id in claim_by_id:
            raise ReportAppendixError("CLAIM_INDEX_DUPLICATE_CLAIM")
        claim_by_id[claim.id] = claim
    return claim_by_id


def _used_claim_ids(content: StructuredReportContent) -> tuple[UUID, ...]:
    ordered: list[UUID] = []
    seen: set[UUID] = set()
    for section in content.sections:
        for block in section.blocks:
            raw_claim_id = block.payload.get("claim_id")
            if raw_claim_id is None:
                continue
            try:
                claim_id = UUID(str(raw_claim_id))
            except (TypeError, ValueError) as error:
                raise ReportAppendixError("CLAIM_INDEX_CLAIM_ID_INVALID") from error
            if claim_id not in seen:
                seen.add(claim_id)
                ordered.append(claim_id)
    return tuple(ordered)


def _claim_classification(status: ClaimSupportStatus) -> str:
    if status is ClaimSupportStatus.PARTIALLY_SUPPORTED:
        return "PARTIAL"
    return status.value
