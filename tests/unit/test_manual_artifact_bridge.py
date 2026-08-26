from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.live_evidence.artifacts import (
    ManualArtifactBridgeRequest,
    bridge_raw_payload,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)


def _request() -> ManualArtifactBridgeRequest:
    return ManualArtifactBridgeRequest(
        ingestion_run_id=uuid4(),
        manual_evidence_import_request_id=uuid4(),
        provider_request_log_id=None,
        local_provider_id=uuid4(),
        security_id=uuid4(),
        category=DataCategory.SOURCE_DOCUMENTS,
        content_type="text/html",
        storage_uri="blob://manual/quarantine/opaque-artifact",
        declared_checksum="a" * 64,
        storage_checksum="a" * 64,
        source_published_at=datetime(2026, 4, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        provider_version="CONTROLLED_MANUAL_EVIDENCE_V1",
        parser_version="manual-parser-v1",
        schema_version="manual-schema-v1",
        byte_size=128,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def test_manual_bridge_creates_raw_payload_without_fake_http_lineage() -> None:
    request = _request()

    record = bridge_raw_payload(request)

    assert record.manual_evidence_import_request_id == (request.manual_evidence_import_request_id)
    assert record.provider_request_log_id is None
    assert record.provider_id == request.local_provider_id
    assert record.storage_uri == request.storage_uri
    assert record.inline_json is None


def test_manual_bridge_rejects_provider_and_manual_source_conflict() -> None:
    request = _request().model_copy(update={"provider_request_log_id": uuid4()})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        bridge_raw_payload(request)

    assert exc_info.value.code == "RAW_ARTIFACT_SOURCE_CONFLICT"


def test_manual_bridge_rejects_storage_checksum_mismatch() -> None:
    request = _request().model_copy(update={"storage_checksum": "b" * 64})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        bridge_raw_payload(request)

    assert exc_info.value.code == "RAW_ARTIFACT_CHECKSUM_MISMATCH"


def test_manual_bridge_is_offline_and_has_no_request_or_url_field() -> None:
    fields = set(ManualArtifactBridgeRequest.model_fields)

    assert "url" not in fields
    assert "method" not in fields
    assert "headers" not in fields
    assert "response_status" not in fields
