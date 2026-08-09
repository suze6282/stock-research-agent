from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.securities.enums import (
    ListingStatus,
    MatchType,
    ResolutionStatus,
)
from stock_research_agent.domain.securities.repositories import ExchangeSymbolLookup
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.domain.securities.schemas import (
    IssuerDetail,
    SecurityCandidate,
    SecurityDetail,
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 14, 12, tzinfo=UTC)


class FakeRepository:
    def __init__(self) -> None:
        self.responses: dict[str, tuple[SecurityCandidate, ...]] = {}
        self.calls: list[tuple[object, ...]] = []
        self.exchange_recognized = False

    def find_exchange_symbol(
        self, exchange_alias: str, symbol: str, limit: int
    ) -> ExchangeSymbolLookup:
        self.calls.append(("exchange", exchange_alias, symbol, limit))
        candidates = self.responses.get("exchange", ())
        return ExchangeSymbolLookup(
            exchange_recognized=self.exchange_recognized or bool(candidates),
            candidates=candidates,
        )

    def find_external_identifier(self, values: object, limit: int) -> tuple[SecurityCandidate, ...]:
        self.calls.append(("identifier", values, limit))
        return self.responses.get("identifier", ())

    def find_symbol(self, normalized_symbol: str, limit: int) -> tuple[SecurityCandidate, ...]:
        self.calls.append(("symbol", normalized_symbol, limit))
        return self.responses.get("symbol", ())

    def find_active_alias(
        self, normalized_alias: str, as_of: date, limit: int
    ) -> tuple[SecurityCandidate, ...]:
        self.calls.append(("alias", normalized_alias, as_of, limit))
        return self.responses.get("alias", ())

    def find_issuer_name(self, normalized_name: str, limit: int) -> tuple[SecurityCandidate, ...]:
        self.calls.append(("issuer", normalized_name, limit))
        return self.responses.get("issuer", ())

    def suggest_prefix(
        self, normalized_query: str, as_of: date, limit: int
    ) -> tuple[SecurityCandidate, ...]:
        self.calls.append(("prefix", normalized_query, as_of, limit))
        return self.responses.get("prefix", ())

    def get_security(self, security_id: UUID) -> SecurityDetail | None:
        raise AssertionError(f"unexpected detail lookup: {security_id}")

    def get_issuer(self, issuer_id: UUID) -> IssuerDetail | None:
        raise AssertionError(f"unexpected detail lookup: {issuer_id}")


def _candidate(
    number: int = 1,
    *,
    symbol: str = "MU",
    mic: str = "XNAS",
    listing_status: ListingStatus = ListingStatus.ACTIVE,
) -> SecurityCandidate:
    return SecurityCandidate(
        security_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        issuer_id=UUID(f"10000000-0000-0000-0000-{number:012d}"),
        issuer_display_name=f"Issuer {number}",
        security_display_name=f"Security {number}",
        symbol=symbol,
        exchange_mic=mic,
        exchange_name="Nasdaq" if mic == "XNAS" else "Shanghai Stock Exchange",
        market_code="US_EQUITY" if mic == "XNAS" else "CN_A",
        currency_code="USD" if mic == "XNAS" else "CNY",
        listing_status=listing_status,
        match_reason="test match",
    )


def _service(repository: FakeRepository) -> SecurityResolutionService:
    return SecurityResolutionService(repository, clock=FixedClock())


@pytest.mark.parametrize(
    ("query", "expected_alias", "expected_symbol"),
    [("NASDAQ:MU", "NASDAQ", "MU"), ("601138.SH", "SH", "601138")],
)
def test_explicit_exchange_symbol_has_highest_priority(
    query: str, expected_alias: str, expected_symbol: str
) -> None:
    repository = FakeRepository()
    repository.responses["exchange"] = (_candidate(),)

    result = _service(repository).resolve(query)

    assert result.status is ResolutionStatus.RESOLVED
    assert result.match_type is MatchType.EXACT_EXCHANGE_SYMBOL
    assert repository.calls == [("exchange", expected_alias, expected_symbol, 10)]


def test_explicit_confirmed_identifier_precedes_symbol_and_alias() -> None:
    repository = FakeRepository()
    repository.responses["identifier"] = (_candidate(),)

    result = _service(repository).resolve("SEC_CIK:723125")

    assert result.match_type is MatchType.EXACT_IDENTIFIER
    assert result.status is ResolutionStatus.RESOLVED
    assert repository.calls[0][0] == "identifier"
    assert all(call[0] not in {"symbol", "alias"} for call in repository.calls)


def test_recognized_exchange_with_missing_symbol_is_terminal_not_found() -> None:
    repository = FakeRepository()
    repository.exchange_recognized = True
    repository.responses["symbol"] = (_candidate(),)
    repository.responses["alias"] = (_candidate(),)
    repository.responses["prefix"] = (_candidate(),)

    result = _service(repository).resolve("NASDAQ:XYZ")

    assert result.status is ResolutionStatus.NOT_FOUND
    assert result.match_type is MatchType.NONE
    assert repository.calls == [("exchange", "NASDAQ", "XYZ", 10)]


@pytest.mark.parametrize(
    ("response_key", "query", "expected_match", "expected_call_prefix"),
    [
        ("symbol", "MU", MatchType.EXACT_SYMBOL, ("symbol", "MU")),
        ("alias", "Micron Technology", MatchType.EXACT_ALIAS, ("alias", "MICRON TECHNOLOGY")),
        (
            "issuer",
            "Micron Technology, Inc.",
            MatchType.EXACT_ISSUER_NAME,
            ("issuer", "MICRON TECHNOLOGY INC"),
        ),
    ],
)
def test_exact_resolution_steps_follow_fixed_priority(
    response_key: str,
    query: str,
    expected_match: MatchType,
    expected_call_prefix: tuple[str, str],
) -> None:
    repository = FakeRepository()
    repository.responses[response_key] = (_candidate(),)

    result = _service(repository).resolve(query)

    assert result.status is ResolutionStatus.RESOLVED
    assert result.match_type is expected_match
    assert expected_call_prefix in {call[:2] for call in repository.calls}


def test_multiple_exact_candidates_are_ambiguous_and_stably_sorted() -> None:
    repository = FakeRepository()
    repository.responses["alias"] = (
        _candidate(2, symbol="601138", mic="XSHG"),
        _candidate(1, symbol="MU", mic="XNAS"),
    )

    result = _service(repository).resolve("Shared Name")

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.match_type is MatchType.EXACT_ALIAS
    assert [candidate.exchange_mic for candidate in result.candidates] == ["XNAS", "XSHG"]


def test_prefix_candidate_never_auto_resolves_even_when_unique() -> None:
    repository = FakeRepository()
    repository.responses["prefix"] = (_candidate(),)

    result = _service(repository).resolve("MICR")

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.match_type is MatchType.PREFIX_SUGGESTION
    assert result.candidate_count == 1
    assert any("suggestion" in warning.lower() for warning in result.warnings)


def test_not_found_does_not_apply_fuzzy_or_popularity_matching() -> None:
    repository = FakeRepository()

    result = _service(repository).resolve("Micorn")

    assert result.status is ResolutionStatus.NOT_FOUND
    assert result.match_type is MatchType.NONE
    assert result.candidates == ()


@pytest.mark.parametrize(
    ("listing_status", "warning_fragment"),
    [
        (ListingStatus.DELISTED, "delisted"),
        (ListingStatus.SUSPENDED, "suspended"),
        (ListingStatus.UNKNOWN, "unknown"),
    ],
)
def test_non_active_listing_status_is_visible_and_warned(
    listing_status: ListingStatus, warning_fragment: str
) -> None:
    repository = FakeRepository()
    repository.responses["symbol"] = (_candidate(listing_status=listing_status),)

    result = _service(repository).resolve("MU")

    assert result.status is ResolutionStatus.RESOLVED
    assert result.candidates[0].listing_status is listing_status
    assert any(warning_fragment in warning.lower() for warning in result.warnings)


def test_candidate_limit_is_always_ten_and_results_are_deduplicated() -> None:
    repository = FakeRepository()
    repository.responses["prefix"] = tuple(_candidate(index) for index in range(12, 0, -1))

    result = _service(repository).resolve("M")

    assert result.candidate_count == 10
    assert repository.calls[-1][-1] == 10
    assert [str(item.security_id) for item in result.candidates] == sorted(
        str(item.security_id) for item in result.candidates
    )


def test_candidate_order_uses_normalized_not_raw_symbol() -> None:
    repository = FakeRepository()
    repository.responses["alias"] = (
        _candidate(1, symbol="B"),
        _candidate(2, symbol="a"),
    )

    result = _service(repository).resolve("Shared")

    assert [candidate.symbol for candidate in result.candidates] == ["a", "B"]


@pytest.mark.parametrize("query", ["", "   ", "...", "MU\nDROP", "A" * 257])
def test_invalid_query_returns_stable_domain_result_without_repository_access(
    query: str,
) -> None:
    repository = FakeRepository()

    result = _service(repository).resolve(query)

    assert result.status is ResolutionStatus.INVALID_QUERY
    assert result.match_type is MatchType.NONE
    assert result.candidate_count == 0
    assert result.candidates == ()
    assert repository.calls == []


def test_repeated_resolution_serializes_identically() -> None:
    repository = FakeRepository()
    repository.responses["symbol"] = (_candidate(),)
    service = _service(repository)

    first = service.resolve("MU")
    second = service.resolve("MU")

    assert json.dumps(first.model_dump(mode="json"), sort_keys=True) == json.dumps(
        second.model_dump(mode="json"), sort_keys=True
    )
