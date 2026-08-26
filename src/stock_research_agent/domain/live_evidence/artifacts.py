"""Source-neutral bridge from governed manual intake to immutable RawPayload."""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import Field

from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
)
from stock_research_agent.domain.data_access.schemas import RawPayloadRecord
from stock_research_agent.domain.live_evidence.enums import EvidenceSourceType
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)


class ArtifactSourceContext(FrozenProviderContract):
    provider_request_log_id: UUID | None
    manual_evidence_import_request_id: UUID | None
    data_origin: DataOrigin
    access_mode: AccessMode
    live_status: LiveStatus
    synthetic_status: ProviderSyntheticStatus


def classify_artifact_source(context: ArtifactSourceContext) -> EvidenceSourceType:
    """Classify immutable evidence lineage without conflating live and offline data."""
    has_provider = context.provider_request_log_id is not None
    has_manual = context.manual_evidence_import_request_id is not None
    if has_provider == has_manual:
        raise LiveEvidenceValidationError("ARTIFACT_SOURCE_AMBIGUOUS")

    is_offline = (
        context.data_origin is DataOrigin.FIXTURE
        and context.access_mode is AccessMode.OFFLINE
        and context.live_status is LiveStatus.NOT_LIVE
    )
    if has_manual:
        if not is_offline:
            raise LiveEvidenceValidationError("ARTIFACT_SOURCE_AMBIGUOUS")
        return EvidenceSourceType.MANUAL_IMPORT

    if (
        context.data_origin is DataOrigin.LIVE
        and context.access_mode is AccessMode.ONLINE
        and context.live_status is LiveStatus.LIVE
        and context.synthetic_status is ProviderSyntheticStatus.REAL_VERIFIED
    ):
        return EvidenceSourceType.PROVIDER_LIVE

    if is_offline:
        if context.synthetic_status is ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY:
            return EvidenceSourceType.SYNTHETIC_TEST
        if context.synthetic_status is ProviderSyntheticStatus.FIXTURE_REAL_EXCERPT:
            return EvidenceSourceType.OFFLINE_FIXTURE

    raise LiveEvidenceValidationError("ARTIFACT_SOURCE_AMBIGUOUS")


class ManualArtifactBridgeRequest(FrozenProviderContract):
    ingestion_run_id: UUID
    manual_evidence_import_request_id: UUID
    provider_request_log_id: UUID | None = None
    local_provider_id: UUID
    security_id: UUID
    category: DataCategory
    content_type: str = Field(min_length=1, max_length=128)
    storage_uri: str = Field(min_length=10, max_length=1024)
    declared_checksum: Checksum
    storage_checksum: Checksum
    source_published_at: AwareUtcDateTime | None
    retrieved_at: AwareUtcDateTime
    provider_version: str = Field(min_length=1, max_length=64)
    parser_version: str = Field(min_length=1, max_length=64)
    schema_version: str = Field(min_length=1, max_length=64)
    byte_size: int = Field(ge=1, le=26_214_400)
    created_at: AwareUtcDateTime


def bridge_raw_payload(request: ManualArtifactBridgeRequest) -> RawPayloadRecord:
    if request.provider_request_log_id is not None:
        raise LiveEvidenceValidationError("RAW_ARTIFACT_SOURCE_CONFLICT")
    if request.declared_checksum != request.storage_checksum:
        raise LiveEvidenceValidationError("RAW_ARTIFACT_CHECKSUM_MISMATCH")
    return RawPayloadRecord(
        id=uuid4(),
        ingestion_run_id=request.ingestion_run_id,
        provider_request_log_id=None,
        manual_evidence_import_request_id=request.manual_evidence_import_request_id,
        provider_id=request.local_provider_id,
        security_id=request.security_id,
        category=request.category,
        content_type=request.content_type,
        storage_uri=request.storage_uri,
        inline_json=None,
        checksum_algorithm="sha256",
        checksum=request.declared_checksum,
        source_published_at=request.source_published_at,
        retrieved_at=request.retrieved_at,
        provider_version=request.provider_version,
        parser_version=request.parser_version,
        schema_version=request.schema_version,
        byte_size=request.byte_size,
        created_at=request.created_at,
    )
