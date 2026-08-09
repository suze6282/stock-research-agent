"""Persistence ports consumed by the security master domain services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.securities.enums import IdentifierScheme
from stock_research_agent.domain.securities.schemas import (
    IssuerDetail,
    SecurityCandidate,
    SecurityDetail,
    SecurityMasterSeedManifest,
    SeedResult,
)


@dataclass(frozen=True, slots=True)
class ExchangeSymbolLookup:
    """Distinguish an unknown exchange alias from a known exchange with no symbol."""

    exchange_recognized: bool
    candidates: tuple[SecurityCandidate, ...] = ()


class SecurityMasterRepository(Protocol):
    def find_exchange_symbol(
        self, exchange_alias: str, symbol: str, limit: int
    ) -> ExchangeSymbolLookup: ...

    def find_external_identifier(
        self, values: Mapping[IdentifierScheme, str], limit: int
    ) -> Sequence[SecurityCandidate]: ...

    def find_symbol(self, normalized_symbol: str, limit: int) -> Sequence[SecurityCandidate]: ...

    def find_active_alias(
        self, normalized_alias: str, as_of: date, limit: int
    ) -> Sequence[SecurityCandidate]: ...

    def find_issuer_name(self, normalized_name: str, limit: int) -> Sequence[SecurityCandidate]: ...

    def suggest_prefix(
        self, normalized_query: str, as_of: date, limit: int
    ) -> Sequence[SecurityCandidate]: ...

    def get_security(self, security_id: UUID) -> SecurityDetail | None: ...

    def get_issuer(self, issuer_id: UUID) -> IssuerDetail | None: ...


class SecurityMasterSeedRepository(Protocol):
    def acquire_seed_lock(self, seed_version: str) -> None: ...

    def apply_manifest(self, manifest: SecurityMasterSeedManifest) -> SeedResult: ...
