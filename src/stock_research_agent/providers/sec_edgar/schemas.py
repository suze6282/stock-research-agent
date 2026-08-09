"""Strict offline SEC EDGAR schemas."""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
)

SEC_PROVIDER_CODE = "SEC_EDGAR_PUBLIC_V1"
_CIK_PATTERN = re.compile(r"^\d{1,10}$")
_ACCESSION_DASHED_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_ACCESSION_COMPACT_PATTERN = re.compile(r"^\d{18}$")
_FORM_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,14}(?:/A)?$")
_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_DOCUMENT_TYPE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,31}$")
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "application/xhtml+xml",
        "application/xml",
        "text/html",
        "text/plain",
        "text/xml",
    }
)

Cik = Annotated[str, Field(pattern=r"^\d{10}$")]
AccessionNumber = Annotated[str, Field(pattern=r"^\d{10}-\d{2}-\d{6}$")]
SecForm = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9-]{0,14}(?:/A)?$")]
SecFilename = Annotated[
    str,
    Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]


class SecEndpointType(StrEnum):
    SUBMISSIONS_JSON = "SEC_SUBMISSIONS_JSON"
    COMPANY_FACTS_JSON = "SEC_COMPANY_FACTS_JSON"
    FILING_INDEX = "SEC_FILING_INDEX"
    FILING_DOCUMENT = "SEC_FILING_DOCUMENT"


class SecEvidenceRole(StrEnum):
    METADATA_ONLY = "METADATA_ONLY"
    COMPANY_BODY = "COMPANY_BODY"


class SecArtifactKind(StrEnum):
    SUBMISSIONS_METADATA = "SUBMISSIONS_METADATA"
    COMPANY_FACTS = "COMPANY_FACTS"
    FILING_INDEX = "FILING_INDEX"
    PRIMARY_FILING_DOCUMENT = "PRIMARY_FILING_DOCUMENT"
    COMPLETE_SUBMISSION_TEXT = "COMPLETE_SUBMISSION_TEXT"
    XBRL_INSTANCE = "XBRL_INSTANCE"
    EXHIBIT = "EXHIBIT"


def normalize_cik(value: str) -> str:
    """Return a ten-digit SEC CIK without accepting decorated input."""

    if _CIK_PATTERN.fullmatch(value) is None:
        raise ValueError("SEC_CIK_INVALID")
    return value.zfill(10)


def normalize_accession(value: str) -> str:
    """Return the canonical dashed SEC accession number."""

    if _ACCESSION_DASHED_PATTERN.fullmatch(value) is not None:
        return value
    if _ACCESSION_COMPACT_PATTERN.fullmatch(value) is not None:
        return f"{value[:10]}-{value[10:12]}-{value[12:]}"
    raise ValueError("SEC_ACCESSION_INVALID")


def accession_without_dashes(value: str) -> str:
    """Return the compact accession only after validating the dashed value."""

    return normalize_accession(value).replace("-", "")


def _validate_content_type(value: str) -> str:
    if value not in _ALLOWED_CONTENT_TYPES:
        raise ValueError("SEC_CONTENT_TYPE_INVALID")
    return value


def _validate_source_text(value: str, *, field_name: str, max_length: int) -> str:
    if (
        value != value.strip()
        or not value
        or len(value) > max_length
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{field_name} is invalid")
    return value


class SecFilingMetadata(FrozenProviderContract):
    accession_number: AccessionNumber
    form: SecForm
    filed_date: date
    report_date: date | None
    accepted_at: AwareUtcDateTime
    primary_document: SecFilename

    @field_validator("form")
    @classmethod
    def validate_form(cls, value: str) -> str:
        if _FORM_PATTERN.fullmatch(value) is None:
            raise ValueError("SEC_FORM_INVALID")
        return value


class SecSubmissionsMetadata(FrozenProviderContract):
    provider_code: Literal["SEC_EDGAR_PUBLIC_V1"]
    source_endpoint_type: Literal[SecEndpointType.SUBMISSIONS_JSON]
    source_identity: str = Field(min_length=1, max_length=128)
    cik: Cik
    entity_name: str = Field(min_length=1, max_length=512)
    tickers: tuple[str, ...] = Field(max_length=128)
    exchanges: tuple[str, ...] = Field(max_length=128)
    filings: tuple[SecFilingMetadata, ...] = Field(max_length=10_000)
    evidence_role: Literal[SecEvidenceRole.METADATA_ONLY]

    @model_validator(mode="after")
    def validate_source_identity(self) -> SecSubmissionsMetadata:
        if self.source_identity != f"{self.source_endpoint_type.value}:{self.cik}":
            raise ValueError("SEC_SOURCE_IDENTITY_MISMATCH")
        _validate_source_text(self.entity_name, field_name="entity_name", max_length=512)
        return self


class SecCompanyFactsEnvelope(FrozenProviderContract):
    provider_code: Literal["SEC_EDGAR_PUBLIC_V1"]
    source_endpoint_type: Literal[SecEndpointType.COMPANY_FACTS_JSON]
    source_identity: str = Field(min_length=1, max_length=128)
    cik: Cik
    entity_name: str = Field(min_length=1, max_length=512)
    taxonomy_names: tuple[str, ...] = Field(max_length=64)
    fact_count: int = Field(ge=0, le=10_000_000)
    evidence_role: Literal[SecEvidenceRole.METADATA_ONLY]

    @model_validator(mode="after")
    def validate_envelope(self) -> SecCompanyFactsEnvelope:
        if self.source_identity != f"{self.source_endpoint_type.value}:{self.cik}":
            raise ValueError("SEC_SOURCE_IDENTITY_MISMATCH")
        if self.taxonomy_names != tuple(sorted(set(self.taxonomy_names))):
            raise ValueError("SEC_TAXONOMIES_MUST_BE_UNIQUE_AND_SORTED")
        _validate_source_text(self.entity_name, field_name="entity_name", max_length=512)
        return self


class SecFilingDocument(FrozenProviderContract):
    sequence: int = Field(ge=1, le=100_000)
    filename: SecFilename
    description: str = Field(min_length=1, max_length=512)
    document_type: str = Field(min_length=1, max_length=32)
    content_type: str = Field(min_length=1, max_length=64)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return _validate_source_text(value, field_name="description", max_length=512)

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        if _DOCUMENT_TYPE_PATTERN.fullmatch(value) is None:
            raise ValueError("SEC_DOCUMENT_TYPE_INVALID")
        return value

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        return _validate_content_type(value)


class SecFilingIndex(FrozenProviderContract):
    provider_code: Literal["SEC_EDGAR_PUBLIC_V1"]
    source_endpoint_type: Literal[SecEndpointType.FILING_INDEX]
    source_identity: str = Field(min_length=1, max_length=160)
    cik: Cik
    accession_number: AccessionNumber
    documents: tuple[SecFilingDocument, ...] = Field(min_length=1, max_length=10_000)
    evidence_role: Literal[SecEvidenceRole.METADATA_ONLY]

    @model_validator(mode="after")
    def validate_index(self) -> SecFilingIndex:
        expected = f"{self.source_endpoint_type.value}:{self.cik}:{self.accession_number}"
        if self.source_identity != expected:
            raise ValueError("SEC_SOURCE_IDENTITY_MISMATCH")
        identities = tuple((document.sequence, document.filename) for document in self.documents)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("SEC_FILING_DOCUMENTS_MUST_BE_UNIQUE_AND_SORTED")
        return self


class SecDocumentArtifactDescriptor(FrozenProviderContract):
    provider_code: Literal["SEC_EDGAR_PUBLIC_V1"]
    source_endpoint_type: Literal[SecEndpointType.FILING_DOCUMENT]
    source_identity: str = Field(min_length=1, max_length=512)
    cik: Cik
    accession_number: AccessionNumber
    filename: SecFilename
    artifact_kind: SecArtifactKind
    content_type: str = Field(min_length=1, max_length=64)
    source_published_at: AwareUtcDateTime | None
    evidence_role: SecEvidenceRole

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        return _validate_content_type(value)

    @model_validator(mode="after")
    def validate_descriptor(self) -> SecDocumentArtifactDescriptor:
        expected = (
            f"{self.source_endpoint_type.value}:{self.cik}:{self.accession_number}:{self.filename}"
        )
        if self.source_identity != expected:
            raise ValueError("SEC_SOURCE_IDENTITY_MISMATCH")
        metadata_only = {
            SecArtifactKind.SUBMISSIONS_METADATA,
            SecArtifactKind.COMPANY_FACTS,
            SecArtifactKind.FILING_INDEX,
            SecArtifactKind.XBRL_INSTANCE,
        }
        if (
            self.artifact_kind in metadata_only
            and self.evidence_role is SecEvidenceRole.COMPANY_BODY
        ):
            raise ValueError("SEC_METADATA_CANNOT_BE_COMPANY_BODY")
        return self
