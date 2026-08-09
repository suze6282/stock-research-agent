from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from stock_research_agent.domain.providers import artifacts, quality
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.errors import (
    ProviderFailure,
    ProviderFailureCode,
)

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _record() -> artifacts.ProviderRecord:
    return artifacts.ProviderRecord(
        identity=artifacts.ProviderRecordIdentity(
            provider_definition_id=uuid4(),
            provider_capability_id=uuid4(),
            source_identity="fixture:dead-letter",
            record_key="A",
            revision=1,
        ),
        raw_artifact_id=uuid4(),
        source_checksum="a" * 64,
        source_published_at=NOW,
        status=artifacts.ProviderRecordStatus.COMPLETE,
        numeric_values={"close": "12.34"},
        text_values={},
        synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
    )


def test_reject_persists_only_bounded_safe_diagnostic_not_raw_record() -> None:
    record = _record()
    failure = ProviderFailure(
        code=ProviderFailureCode.SCHEMA_DRIFT,
        safe_message="Provider schema validation failed",
        retryable=False,
        blocked_reason=None,
    )
    context = quality.DeadLetterContext(
        sync_run_id=uuid4(),
        manifest_id=uuid4(),
        retention_permitted=True,
    )
    dead_letter = quality.DeadLetterService().reject(record, failure, context)
    payload = dead_letter.model_dump(mode="json")
    assert dead_letter.status is artifacts.ProviderDeadLetterStatus.OPEN
    assert payload["safe_error_code"] == "SCHEMA_DRIFT"
    assert "numeric_values" not in payload
    assert "raw_artifact_id" not in payload
    assert "12.34" not in str(payload)


def test_unknown_exception_never_copies_secret_path_sql_or_body() -> None:
    record = _record()
    unsafe = RuntimeError("token=SECRET C:\\private\\payload.json SELECT * FROM data raw-body")
    result = quality.DeadLetterService().reject_exception(
        record,
        unsafe,
        quality.DeadLetterContext(
            sync_run_id=uuid4(),
            manifest_id=uuid4(),
            retention_permitted=True,
        ),
    )
    serialized = str(result.model_dump(mode="json"))
    for forbidden in ("SECRET", "C:\\", "SELECT", "raw-body"):
        assert forbidden not in serialized


def test_repair_requires_explicit_authorization_and_audit_sink() -> None:
    events: list[tuple[object, str]] = []
    service = quality.DeadLetterService(
        repair_audit=lambda item_id, action: events.append((item_id, action))
    )
    item_id = uuid4()
    with pytest.raises(PermissionError, match="EXPLICIT_REPAIR"):
        service.repair(item_id, authorized=False)
    service.repair(item_id, authorized=True)
    assert events == [(item_id, "DEAD_LETTER_REPAIR_AUTHORIZED")]


def test_retention_policy_blocks_dead_letter_creation() -> None:
    with pytest.raises(PermissionError, match="RETENTION"):
        quality.DeadLetterService().reject(
            _record(),
            ProviderFailure(
                code=ProviderFailureCode.SCHEMA_DRIFT,
                safe_message="Provider schema validation failed",
                retryable=False,
                blocked_reason=None,
            ),
            quality.DeadLetterContext(
                sync_run_id=uuid4(),
                manifest_id=uuid4(),
                retention_permitted=False,
            ),
        )
