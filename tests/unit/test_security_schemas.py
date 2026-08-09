from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.securities.enums import (
    ListingStatus,
    MatchType,
    ResolutionStatus,
)
from stock_research_agent.domain.securities.schemas import (
    ExchangeRecord,
    IdentifierRecord,
    SecurityAliasRecord,
    SecurityCandidate,
    SecurityMasterSeedManifest,
    SecurityRecord,
    SecurityResolutionResult,
    TimestampedRecord,
)

SECURITY_ID = UUID("00000000-0000-0000-0000-000000000001")
ISSUER_ID = UUID("00000000-0000-0000-0000-000000000002")
EXCHANGE_ID = UUID("00000000-0000-0000-0000-000000000003")
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def test_timestamped_record_converts_aware_database_timestamp_to_utc() -> None:
    database_timestamp = NOW.astimezone(timezone(timedelta(hours=8)))

    record = TimestampedRecord(
        created_at=database_timestamp,
        updated_at=database_timestamp,
    )

    assert record.created_at == NOW
    assert record.created_at.tzinfo is UTC
    assert record.updated_at.tzinfo is UTC


def _candidate(*, listing_status: ListingStatus = ListingStatus.UNKNOWN) -> SecurityCandidate:
    return SecurityCandidate(
        security_id=SECURITY_ID,
        issuer_id=ISSUER_ID,
        issuer_display_name="Micron Technology",
        security_display_name="Micron Technology",
        symbol="MU",
        exchange_mic="XNAS",
        exchange_name="Nasdaq",
        market_code="US_EQUITY",
        currency_code="USD",
        listing_status=listing_status,
        match_reason="unique normalized symbol",
    )


def test_resolution_result_has_stable_contract() -> None:
    result = SecurityResolutionResult(
        status=ResolutionStatus.RESOLVED,
        original_query="MU",
        normalized_query="MU",
        match_type=MatchType.EXACT_SYMBOL,
        candidate_count=1,
        candidates=(_candidate(),),
        warnings=(),
    )

    assert result.model_dump(mode="json") == {
        "status": "RESOLVED",
        "original_query": "MU",
        "normalized_query": "MU",
        "match_type": "EXACT_SYMBOL",
        "candidate_count": 1,
        "candidates": [
            {
                "security_id": str(SECURITY_ID),
                "issuer_id": str(ISSUER_ID),
                "issuer_display_name": "Micron Technology",
                "security_display_name": "Micron Technology",
                "symbol": "MU",
                "exchange_mic": "XNAS",
                "exchange_name": "Nasdaq",
                "market_code": "US_EQUITY",
                "currency_code": "USD",
                "listing_status": "UNKNOWN",
                "match_reason": "unique normalized symbol",
            }
        ],
        "warnings": [],
    }
    assert "confidence" not in result.model_dump()


@pytest.mark.parametrize(
    ("status", "candidate_count", "candidates"),
    [
        (ResolutionStatus.RESOLVED, 0, ()),
        (ResolutionStatus.RESOLVED, 2, (_candidate(), _candidate())),
        (ResolutionStatus.NOT_FOUND, 1, (_candidate(),)),
        (ResolutionStatus.INVALID_QUERY, 1, (_candidate(),)),
        (ResolutionStatus.AMBIGUOUS, 0, ()),
    ],
)
def test_resolution_result_rejects_inconsistent_candidate_semantics(
    status: ResolutionStatus,
    candidate_count: int,
    candidates: tuple[SecurityCandidate, ...],
) -> None:
    with pytest.raises(ValidationError):
        SecurityResolutionResult(
            status=status,
            original_query="MU",
            normalized_query="MU",
            match_type=MatchType.EXACT_SYMBOL,
            candidate_count=candidate_count,
            candidates=candidates,
        )


@pytest.mark.parametrize("candidate_count", [-1, 11])
def test_resolution_result_limits_candidate_count(candidate_count: int) -> None:
    with pytest.raises(ValidationError):
        SecurityResolutionResult(
            status=ResolutionStatus.AMBIGUOUS,
            original_query="M",
            normalized_query="M",
            match_type=MatchType.PREFIX_SUGGESTION,
            candidate_count=candidate_count,
            candidates=(_candidate(),),
        )


def test_invalid_result_can_preserve_an_overlong_original_query() -> None:
    original_query = "A" * 257

    result = SecurityResolutionResult(
        status=ResolutionStatus.INVALID_QUERY,
        original_query=original_query,
        normalized_query="",
        match_type=MatchType.NONE,
        candidate_count=0,
    )

    assert result.original_query == original_query


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mic", "NAS"),
        ("mic", "xnas"),
        ("country_code", "USA"),
        ("country_code", "us"),
        ("default_currency_code", "US"),
        ("default_currency_code", "usd"),
        ("timezone", "Mars/Olympus"),
        ("mic", "ZZZZ"),
        ("country_code", "ZZ"),
        ("default_currency_code", "ZZZ"),
    ],
)
def test_exchange_record_validates_standard_codes(field: str, value: str) -> None:
    payload: dict[str, object] = {
        "id": EXCHANGE_ID,
        "market_id": UUID("00000000-0000-0000-0000-000000000004"),
        "mic": "XNAS",
        "name": "Nasdaq",
        "short_name": "Nasdaq",
        "country_code": "US",
        "timezone": "America/New_York",
        "default_currency_code": "USD",
        "calendar_code": None,
        "status": "ACTIVE",
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ExchangeRecord.model_validate(payload)


def test_security_record_rejects_inverted_listing_dates() -> None:
    with pytest.raises(ValidationError):
        SecurityRecord(
            id=SECURITY_ID,
            issuer_id=ISSUER_ID,
            exchange_id=EXCHANGE_ID,
            symbol="MU",
            normalized_symbol="MU",
            display_name="Micron Technology",
            security_type="COMMON_STOCK",
            share_class=None,
            currency_code="USD",
            listing_status="DELISTED",
            listing_date=date(2020, 1, 2),
            delisting_date=date(2020, 1, 1),
            is_primary_listing=True,
            created_at=NOW,
            updated_at=NOW,
        )


@pytest.mark.parametrize("record_type", [IdentifierRecord, SecurityAliasRecord])
def test_validity_records_reject_inverted_dates(
    record_type: type[IdentifierRecord] | type[SecurityAliasRecord],
) -> None:
    common: dict[str, object] = {
        "id": UUID("00000000-0000-0000-0000-000000000005"),
        "valid_from": date(2020, 1, 2),
        "valid_to": date(2020, 1, 1),
        "created_at": NOW,
        "updated_at": NOW,
    }
    if record_type is IdentifierRecord:
        common.update(
            owner_id=ISSUER_ID,
            scheme="SEC_CIK",
            value="0000723125",
            normalized_value="0000723125",
            source_name="SEC",
            is_primary=True,
        )
    else:
        common.update(
            security_id=SECURITY_ID,
            alias="Micron",
            normalized_alias="MICRON",
            alias_type="COMPANY_SHORT_NAME",
            locale="en-US",
            source_name="stage-1",
            is_active=True,
        )

    with pytest.raises(ValidationError):
        if record_type is IdentifierRecord:
            IdentifierRecord(**common)
        else:
            SecurityAliasRecord(**common)


def test_records_are_frozen_and_reject_unknown_fields() -> None:
    candidate = _candidate()

    with pytest.raises(ValidationError):
        candidate.symbol = "OTHER"
    with pytest.raises(ValidationError):
        SecurityCandidate.model_validate({**candidate.model_dump(), "confidence": 0.92})


@pytest.mark.parametrize(
    ("status", "match_type", "candidate_count", "candidates"),
    [
        (ResolutionStatus.RESOLVED, MatchType.NONE, 1, (_candidate(),)),
        (ResolutionStatus.RESOLVED, MatchType.PREFIX_SUGGESTION, 1, (_candidate(),)),
        (ResolutionStatus.AMBIGUOUS, MatchType.NONE, 1, (_candidate(),)),
        (ResolutionStatus.NOT_FOUND, MatchType.EXACT_SYMBOL, 0, ()),
        (ResolutionStatus.INVALID_QUERY, MatchType.EXACT_ALIAS, 0, ()),
    ],
)
def test_resolution_result_rejects_impossible_status_match_combinations(
    status: ResolutionStatus,
    match_type: MatchType,
    candidate_count: int,
    candidates: tuple[SecurityCandidate, ...],
) -> None:
    with pytest.raises(ValidationError):
        SecurityResolutionResult(
            status=status,
            original_query="MU",
            normalized_query="MU",
            match_type=match_type,
            candidate_count=candidate_count,
            candidates=candidates,
        )


def test_v0_seed_rejects_unconfirmed_security_identifier_rows() -> None:
    with pytest.raises(ValidationError):
        SecurityMasterSeedManifest.model_validate(
            {
                "version": "security-master-v0.1.0",
                "evidence_paths": (),
                "markets": (),
                "exchanges": (),
                "exchange_aliases": (),
                "issuers": (),
                "issuer_identifiers": (),
                "securities": (),
                "security_identifiers": (
                    {
                        "id": "00000000-0000-0000-0000-000000000006",
                        "security_id": str(SECURITY_ID),
                        "scheme": "CUSIP",
                        "value": "unverified",
                        "normalized_value": "anything",
                        "source_name": "unverified",
                    },
                ),
                "security_aliases": (),
            }
        )
