from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.canonical import (
    canonical_grant,
    grant_checksum,
    verify_grant_checksum,
)
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.schemas import (
    LiveAuthorizationGrantRecord,
    LiveAuthorizationGrantWrite,
)


def _grant() -> LiveAuthorizationGrantWrite:
    approved_at = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    return LiveAuthorizationGrantWrite(
        provider_definition_id=UUID("10000000-0000-0000-0000-000000000001"),
        provider_code="SEC_EDGAR_PUBLIC_V1",
        provider_definition_version="1.0.0",
        provider_definition_checksum="1" * 64,
        provider_capability_id=UUID("10000000-0000-0000-0000-000000000002"),
        capability_code="FETCH_SEC_FILING_DOCUMENTS",
        capability_version="1.0.0",
        official_domains=("data.sec.gov", "www.sec.gov"),
        security_id=UUID("40000000-0000-0000-0000-000000000002"),
        issuer_id=UUID("30000000-0000-0000-0000-000000000002"),
        provider_security_identifier="0000723125",
        request_methods=("GET",),
        request_limit=4,
        byte_limit=26_214_400,
        date_from=date(2025, 8, 1),
        date_to=date(2026, 8, 1),
        filing_types=("10-K",),
        allowed_document_count=1,
        credential_reference_id=UUID("10000000-0000-0000-0000-000000000003"),
        user_agent_reference_id=UUID("10000000-0000-0000-0000-000000000004"),
        license_policy_id=UUID("10000000-0000-0000-0000-000000000005"),
        license_policy_version="1.0.0",
        license_policy_checksum="2" * 64,
        provider_policy_id=UUID("10000000-0000-0000-0000-000000000006"),
        provider_policy_version="1.0.0",
        provider_policy_checksum="3" * 64,
        raw_storage_allowed=True,
        cache_allowed=False,
        retention_deadline=approved_at + timedelta(days=30),
        approved_at=approved_at,
        expires_at=approved_at + timedelta(minutes=30),
        approved_by="LOCAL_OPERATOR",
        canonical_checksum="0" * 64,
    )


def test_canonical_grant_is_stable_compact_json() -> None:
    grant = _grant()

    first = canonical_grant(grant)
    second = canonical_grant(grant)
    parsed = json.loads(first)

    assert first == second
    assert first == json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert parsed["schema"] == "live-authorization-grant-v1"
    assert parsed["approved_at"] == "2026-08-01T08:00:00Z"
    assert parsed["date_from"] == "2025-08-01"
    assert "canonical_checksum" not in parsed


def test_checksum_ignores_stored_checksum_and_database_identity() -> None:
    grant = _grant()
    record = LiveAuthorizationGrantRecord(
        **grant.model_dump(),
        id=UUID("10000000-0000-0000-0000-000000000099"),
        created_at=datetime(2026, 8, 1, 8, 1, tzinfo=UTC),
    )
    another_checksum = grant.model_copy(update={"canonical_checksum": "f" * 64})

    assert grant_checksum(grant) == grant_checksum(record)
    assert grant_checksum(grant) == grant_checksum(another_checksum)
    assert len(grant_checksum(grant)) == 64


def test_every_scope_change_changes_checksum() -> None:
    grant = _grant()

    assert grant_checksum(grant) != grant_checksum(grant.model_copy(update={"request_limit": 3}))
    assert grant_checksum(grant) != grant_checksum(
        grant.model_copy(update={"provider_security_identifier": "0000000001"})
    )
    assert grant_checksum(grant) != grant_checksum(
        grant.model_copy(update={"expires_at": grant.expires_at - timedelta(minutes=1)})
    )


def test_verify_checksum_accepts_exact_material() -> None:
    grant = _grant()
    exact = grant.model_copy(update={"canonical_checksum": grant_checksum(grant)})

    verify_grant_checksum(exact)


def test_verify_checksum_rejects_noncanonical_record() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        verify_grant_checksum(_grant())

    assert exc_info.value.code == "AUTH_CHECKSUM_INVALID"
    assert str(exc_info.value) == "AUTH_CHECKSUM_INVALID"
