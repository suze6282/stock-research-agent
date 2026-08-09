"""Deterministic security identity resolution independent of delivery frameworks."""

from __future__ import annotations

from collections.abc import Sequence

from stock_research_agent.domain.common.clock import Clock, SystemClock
from stock_research_agent.domain.securities.enums import (
    IdentifierScheme,
    ListingStatus,
    MatchType,
    ResolutionStatus,
)
from stock_research_agent.domain.securities.exceptions import InvalidSecurityQuery
from stock_research_agent.domain.securities.normalization import (
    normalize_company_name,
    normalize_exchange_alias,
    normalize_external_identifier,
    normalize_free_text,
    normalize_symbol,
)
from stock_research_agent.domain.securities.repositories import SecurityMasterRepository
from stock_research_agent.domain.securities.schemas import (
    SecurityCandidate,
    SecurityResolutionResult,
)

_DEFAULT_CANDIDATE_LIMIT = 10
_PREFIX_WARNING = "Prefix matches are suggestions only and were not auto-resolved."
_LISTING_WARNINGS = {
    ListingStatus.SUSPENDED: "A matched security is currently suspended.",
    ListingStatus.DELISTED: "A matched security is delisted.",
    ListingStatus.UNKNOWN: "A matched security has unknown listing status.",
}


class SecurityResolutionService:
    """Resolve security queries using a fixed, repeatable precedence order."""

    def __init__(
        self,
        repository: SecurityMasterRepository,
        *,
        max_candidates: int = _DEFAULT_CANDIDATE_LIMIT,
        clock: Clock | None = None,
    ) -> None:
        if not 1 <= max_candidates <= _DEFAULT_CANDIDATE_LIMIT:
            raise ValueError("max_candidates must be between 1 and 10")
        self._repository = repository
        self._max_candidates = max_candidates
        self._clock = clock or SystemClock()

    def resolve(self, query: str) -> SecurityResolutionResult:
        """Resolve a query without fuzzy matching, popularity rules, or network access."""
        try:
            normalized_query = normalize_free_text(query)
            return self._resolve_valid_query(query, normalized_query)
        except InvalidSecurityQuery:
            return SecurityResolutionResult(
                status=ResolutionStatus.INVALID_QUERY,
                original_query=query,
                normalized_query="",
                match_type=MatchType.NONE,
                candidate_count=0,
                candidates=(),
                warnings=("Query is invalid.",),
            )

    def _resolve_valid_query(self, query: str, normalized_query: str) -> SecurityResolutionResult:
        as_of = self._clock.now().date()

        explicit_exchange_symbol = self._explicit_exchange_symbol(normalized_query)
        if explicit_exchange_symbol is not None:
            exchange_alias, symbol = explicit_exchange_symbol
            lookup = self._repository.find_exchange_symbol(
                exchange_alias,
                symbol,
                self._max_candidates,
            )
            if lookup.candidates:
                return self._candidate_result(
                    query,
                    normalized_query,
                    MatchType.EXACT_EXCHANGE_SYMBOL,
                    lookup.candidates,
                )
            if lookup.exchange_recognized:
                return self._not_found_result(query, normalized_query)

        identifier = self._external_identifier(normalized_query)
        if identifier is not None:
            candidates = self._repository.find_external_identifier(
                {IdentifierScheme.SEC_CIK: identifier},
                self._max_candidates,
            )
            if candidates:
                return self._candidate_result(
                    query,
                    normalized_query,
                    MatchType.EXACT_IDENTIFIER,
                    candidates,
                )

        try:
            normalized_symbol: str | None = normalize_symbol(normalized_query)
        except InvalidSecurityQuery:
            normalized_symbol = None
        if normalized_symbol is not None:
            candidates = self._repository.find_symbol(normalized_symbol, self._max_candidates)
            if candidates:
                return self._candidate_result(
                    query,
                    normalized_query,
                    MatchType.EXACT_SYMBOL,
                    candidates,
                )

        normalized_name = normalize_company_name(normalized_query)
        candidates = self._repository.find_active_alias(
            normalized_name,
            as_of,
            self._max_candidates,
        )
        if candidates:
            return self._candidate_result(
                query,
                normalized_query,
                MatchType.EXACT_ALIAS,
                candidates,
            )

        candidates = self._repository.find_issuer_name(
            normalized_name,
            self._max_candidates,
        )
        if candidates:
            return self._candidate_result(
                query,
                normalized_query,
                MatchType.EXACT_ISSUER_NAME,
                candidates,
            )

        candidates = self._repository.suggest_prefix(
            normalized_name,
            as_of,
            self._max_candidates,
        )
        if candidates:
            return self._candidate_result(
                query,
                normalized_query,
                MatchType.PREFIX_SUGGESTION,
                candidates,
            )

        return self._not_found_result(query, normalized_query)

    @staticmethod
    def _not_found_result(original_query: str, normalized_query: str) -> SecurityResolutionResult:
        return SecurityResolutionResult(
            status=ResolutionStatus.NOT_FOUND,
            original_query=original_query,
            normalized_query=normalized_query,
            match_type=MatchType.NONE,
            candidate_count=0,
            candidates=(),
            warnings=(),
        )

    @staticmethod
    def _explicit_exchange_symbol(normalized_query: str) -> tuple[str, str] | None:
        if normalized_query.startswith(f"{IdentifierScheme.SEC_CIK}:"):
            return None
        if ":" in normalized_query:
            exchange, symbol = normalized_query.split(":", 1)
            return normalize_exchange_alias(exchange), normalize_symbol(symbol)
        if "." in normalized_query:
            symbol, exchange = normalized_query.rsplit(".", 1)
            if symbol and exchange:
                return normalize_exchange_alias(exchange), normalize_symbol(symbol)
        return None

    @staticmethod
    def _external_identifier(normalized_query: str) -> str | None:
        prefix = f"{IdentifierScheme.SEC_CIK}:"
        if not normalized_query.startswith(prefix):
            return None
        value = normalized_query.removeprefix(prefix)
        return normalize_external_identifier(IdentifierScheme.SEC_CIK, value)

    def _candidate_result(
        self,
        original_query: str,
        normalized_query: str,
        match_type: MatchType,
        candidates: Sequence[SecurityCandidate],
    ) -> SecurityResolutionResult:
        bounded_candidates = self._stable_unique_candidates(candidates)
        status = (
            ResolutionStatus.RESOLVED
            if len(bounded_candidates) == 1 and match_type is not MatchType.PREFIX_SUGGESTION
            else ResolutionStatus.AMBIGUOUS
        )
        warnings = self._warnings(bounded_candidates, match_type)
        return SecurityResolutionResult(
            status=status,
            original_query=original_query,
            normalized_query=normalized_query,
            match_type=match_type,
            candidate_count=len(bounded_candidates),
            candidates=bounded_candidates,
            warnings=warnings,
        )

    def _stable_unique_candidates(
        self, candidates: Sequence[SecurityCandidate]
    ) -> tuple[SecurityCandidate, ...]:
        by_security_id = {candidate.security_id: candidate for candidate in candidates}
        ordered = sorted(
            by_security_id.values(),
            key=lambda candidate: (
                candidate.exchange_mic,
                normalize_symbol(candidate.symbol),
                str(candidate.security_id),
            ),
        )
        return tuple(ordered[: self._max_candidates])

    @staticmethod
    def _warnings(
        candidates: Sequence[SecurityCandidate], match_type: MatchType
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if match_type is MatchType.PREFIX_SUGGESTION:
            warnings.append(_PREFIX_WARNING)
        present_statuses = {candidate.listing_status for candidate in candidates}
        warnings.extend(
            warning for status, warning in _LISTING_WARNINGS.items() if status in present_statuses
        )
        return tuple(warnings)
