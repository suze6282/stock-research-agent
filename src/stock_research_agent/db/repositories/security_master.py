"""SQLAlchemy persistence for security master seed data."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from hashlib import sha256
from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, and_, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.models import (
    Exchange,
    ExchangeAlias,
    Issuer,
    IssuerIdentifier,
    Market,
    Security,
    SecurityAlias,
    SecurityIdentifier,
)
from stock_research_agent.db.models.security_master import TimestampedUuidMixin
from stock_research_agent.domain.securities.enums import IdentifierScheme, ListingStatus
from stock_research_agent.domain.securities.exceptions import SeedConflictError
from stock_research_agent.domain.securities.repositories import ExchangeSymbolLookup
from stock_research_agent.domain.securities.schemas import (
    ExchangeRecord,
    IdentifierRecord,
    IssuerDetail,
    IssuerRecord,
    MarketRecord,
    SecurityAliasRecord,
    SecurityCandidate,
    SecurityDetail,
    SecurityMasterSeedManifest,
    SecurityRecord,
    SeedResult,
)

ModelT = TypeVar("ModelT", bound=TimestampedUuidMixin)


class SqlAlchemySecurityMasterRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_exchange_symbol(
        self, exchange_alias: str, symbol: str, limit: int
    ) -> ExchangeSymbolLookup:
        statement = (
            select(ExchangeAlias.exchange_id, Security, Issuer, Exchange, Market)
            .select_from(ExchangeAlias)
            .join(Exchange, ExchangeAlias.exchange_id == Exchange.id)
            .join(Market, Exchange.market_id == Market.id)
            .outerjoin(
                Security,
                and_(
                    Security.exchange_id == Exchange.id,
                    Security.normalized_symbol == symbol,
                ),
            )
            .outerjoin(Issuer, Security.issuer_id == Issuer.id)
            .where(
                ExchangeAlias.normalized_alias == exchange_alias,
                ExchangeAlias.is_active.is_(True),
            )
            .limit(1)
        )
        self._validated_limit(limit)
        row = self._session.execute(statement).tuples().one_or_none()
        if row is None:
            return ExchangeSymbolLookup(exchange_recognized=False)
        _, security, issuer, exchange, market = row
        if security is None:
            return ExchangeSymbolLookup(exchange_recognized=True)
        if issuer is None:
            raise RuntimeError("security candidate is missing its issuer")
        return ExchangeSymbolLookup(
            exchange_recognized=True,
            candidates=(
                self._candidate_from_entities(
                    security,
                    issuer,
                    exchange,
                    market,
                    "explicit exchange and symbol",
                ),
            ),
        )

    def find_external_identifier(
        self, values: Mapping[IdentifierScheme, str], limit: int
    ) -> tuple[SecurityCandidate, ...]:
        cik = values.get(IdentifierScheme.SEC_CIK)
        if cik is None:
            return ()
        statement = (
            self._candidate_statement()
            .join(IssuerIdentifier, IssuerIdentifier.issuer_id == Issuer.id)
            .where(
                IssuerIdentifier.scheme == IdentifierScheme.SEC_CIK,
                IssuerIdentifier.normalized_value == cik,
            )
        )
        return self._load_candidates(statement, "exact SEC CIK", limit)

    def find_symbol(self, normalized_symbol: str, limit: int) -> tuple[SecurityCandidate, ...]:
        statement = self._candidate_statement().where(
            Security.normalized_symbol == normalized_symbol
        )
        return self._load_candidates(statement, "exact normalized symbol", limit)

    def find_active_alias(
        self, normalized_alias: str, as_of: date, limit: int
    ) -> tuple[SecurityCandidate, ...]:
        statement = (
            self._candidate_statement()
            .join(SecurityAlias, SecurityAlias.security_id == Security.id)
            .where(
                SecurityAlias.normalized_alias == normalized_alias,
                SecurityAlias.is_active.is_(True),
                or_(SecurityAlias.valid_from.is_(None), SecurityAlias.valid_from <= as_of),
                or_(SecurityAlias.valid_to.is_(None), SecurityAlias.valid_to >= as_of),
            )
            .distinct()
        )
        return self._load_candidates(statement, "exact current alias", limit)

    def find_issuer_name(self, normalized_name: str, limit: int) -> tuple[SecurityCandidate, ...]:
        statement = self._candidate_statement().where(
            or_(
                Issuer.normalized_legal_name == normalized_name,
                Issuer.normalized_display_name == normalized_name,
            )
        )
        return self._load_candidates(statement, "exact issuer name", limit)

    def suggest_prefix(
        self, normalized_query: str, as_of: date, limit: int
    ) -> tuple[SecurityCandidate, ...]:
        pattern = self._escaped_prefix(normalized_query)
        current_alias = and_(
            SecurityAlias.is_active.is_(True),
            or_(SecurityAlias.valid_from.is_(None), SecurityAlias.valid_from <= as_of),
            or_(SecurityAlias.valid_to.is_(None), SecurityAlias.valid_to >= as_of),
            SecurityAlias.normalized_alias.like(pattern, escape="\\"),
        )
        statement = (
            self._candidate_statement()
            .outerjoin(SecurityAlias, SecurityAlias.security_id == Security.id)
            .where(
                or_(
                    Security.normalized_symbol.like(pattern, escape="\\"),
                    Issuer.normalized_legal_name.like(pattern, escape="\\"),
                    Issuer.normalized_display_name.like(pattern, escape="\\"),
                    current_alias,
                )
            )
            .distinct()
        )
        return self._load_candidates(statement, "bounded prefix suggestion", limit)

    def get_security(self, security_id: UUID) -> SecurityDetail | None:
        security = self._session.get(Security, security_id)
        if security is None:
            return None
        identifiers = tuple(
            self._identifier_record(identifier, security.id)
            for identifier in sorted(
                security.identifiers,
                key=lambda item: (item.scheme, item.normalized_value, str(item.id)),
            )
        )
        aliases = tuple(
            SecurityAliasRecord.model_validate(alias)
            for alias in sorted(
                security.aliases,
                key=lambda item: (item.alias_type, item.normalized_alias, str(item.id)),
            )
        )
        return SecurityDetail(
            security=SecurityRecord.model_validate(security),
            issuer=IssuerRecord.model_validate(security.issuer),
            exchange=ExchangeRecord.model_validate(security.exchange),
            market=MarketRecord.model_validate(security.exchange.market),
            identifiers=identifiers,
            aliases=aliases,
        )

    def get_issuer(self, issuer_id: UUID) -> IssuerDetail | None:
        issuer = self._session.get(Issuer, issuer_id)
        if issuer is None:
            return None
        identifiers = tuple(
            self._identifier_record(identifier, issuer.id)
            for identifier in sorted(
                issuer.identifiers,
                key=lambda item: (item.scheme, item.normalized_value, str(item.id)),
            )
        )
        return IssuerDetail(
            issuer=IssuerRecord.model_validate(issuer),
            identifiers=identifiers,
        )

    @staticmethod
    def _identifier_record(
        identifier: IssuerIdentifier | SecurityIdentifier, owner_id: UUID
    ) -> IdentifierRecord:
        return IdentifierRecord(
            id=identifier.id,
            owner_id=owner_id,
            scheme=identifier.scheme,
            value=identifier.value,
            normalized_value=identifier.normalized_value,
            source_name=identifier.source_name,
            valid_from=identifier.valid_from,
            valid_to=identifier.valid_to,
            is_primary=identifier.is_primary,
            created_at=identifier.created_at,
            updated_at=identifier.updated_at,
        )

    @staticmethod
    def _escaped_prefix(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"{escaped}%"

    @staticmethod
    def _validated_limit(limit: int) -> int:
        if not 1 <= limit <= 10:
            raise ValueError("candidate limit must be between 1 and 10")
        return limit

    @staticmethod
    def _candidate_statement() -> Select[tuple[Security, Issuer, Exchange, Market]]:
        return (
            select(Security, Issuer, Exchange, Market)
            .join(Issuer, Security.issuer_id == Issuer.id)
            .join(Exchange, Security.exchange_id == Exchange.id)
            .join(Market, Exchange.market_id == Market.id)
        )

    def _load_candidates(
        self,
        statement: Select[tuple[Security, Issuer, Exchange, Market]],
        match_reason: str,
        limit: int,
    ) -> tuple[SecurityCandidate, ...]:
        bounded_statement = statement.order_by(
            Exchange.mic,
            Security.normalized_symbol,
            Security.id,
        ).limit(self._validated_limit(limit))
        rows = self._session.execute(bounded_statement).tuples().all()
        return tuple(
            self._candidate_from_entities(
                security,
                issuer,
                exchange,
                market,
                match_reason,
            )
            for security, issuer, exchange, market in rows
        )

    @staticmethod
    def _candidate_from_entities(
        security: Security,
        issuer: Issuer,
        exchange: Exchange,
        market: Market,
        match_reason: str,
    ) -> SecurityCandidate:
        return SecurityCandidate(
            security_id=security.id,
            issuer_id=issuer.id,
            issuer_display_name=issuer.display_name,
            security_display_name=security.display_name,
            symbol=security.symbol,
            exchange_mic=exchange.mic,
            exchange_name=exchange.name,
            market_code=market.code,
            currency_code=security.currency_code,
            listing_status=ListingStatus(security.listing_status),
            match_reason=match_reason,
        )

    def acquire_seed_lock(self, seed_version: str) -> None:
        digest = sha256(seed_version.encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def apply_manifest(self, manifest: SecurityMasterSeedManifest) -> SeedResult:
        inserted_count = 0
        existing_count = 0

        def apply(
            model: type[ModelT],
            record_id: UUID,
            natural_query: Select[tuple[ModelT]],
            values: Mapping[str, object],
            new_instance: ModelT,
            label: str,
        ) -> None:
            nonlocal inserted_count, existing_count
            if self._apply_record(
                model=model,
                record_id=record_id,
                natural_query=natural_query,
                values=values,
                new_instance=new_instance,
                label=label,
            ):
                inserted_count += 1
            else:
                existing_count += 1

        for market_record in manifest.markets:
            values = market_record.model_dump(mode="python")
            apply(
                Market,
                market_record.id,
                select(Market).where(Market.code == market_record.code),
                values,
                Market(**values),
                f"market:{market_record.code}",
            )
        for exchange_record in manifest.exchanges:
            values = exchange_record.model_dump(mode="python")
            apply(
                Exchange,
                exchange_record.id,
                select(Exchange).where(Exchange.mic == exchange_record.mic),
                values,
                Exchange(**values),
                f"exchange:{exchange_record.mic}",
            )
        for exchange_alias_record in manifest.exchange_aliases:
            values = exchange_alias_record.model_dump(mode="python")
            apply(
                ExchangeAlias,
                exchange_alias_record.id,
                select(ExchangeAlias).where(
                    ExchangeAlias.normalized_alias == exchange_alias_record.normalized_alias
                ),
                values,
                ExchangeAlias(**values),
                f"exchange_alias:{exchange_alias_record.normalized_alias}",
            )
        for issuer_record in manifest.issuers:
            values = issuer_record.model_dump(mode="python")
            apply(
                Issuer,
                issuer_record.id,
                select(Issuer).where(Issuer.id == issuer_record.id),
                values,
                Issuer(**values),
                f"issuer:{issuer_record.id}",
            )
        for issuer_identifier_record in manifest.issuer_identifiers:
            values = issuer_identifier_record.model_dump(mode="python")
            apply(
                IssuerIdentifier,
                issuer_identifier_record.id,
                select(IssuerIdentifier).where(
                    IssuerIdentifier.scheme == issuer_identifier_record.scheme,
                    IssuerIdentifier.normalized_value == issuer_identifier_record.normalized_value,
                ),
                values,
                IssuerIdentifier(**values),
                "issuer_identifier:"
                f"{issuer_identifier_record.scheme}:"
                f"{issuer_identifier_record.normalized_value}",
            )
        for security_record in manifest.securities:
            values = security_record.model_dump(mode="python")
            apply(
                Security,
                security_record.id,
                select(Security).where(
                    Security.exchange_id == security_record.exchange_id,
                    Security.normalized_symbol == security_record.normalized_symbol,
                ),
                values,
                Security(**values),
                f"security:{security_record.exchange_id}:{security_record.normalized_symbol}",
            )
        for security_alias_record in manifest.security_aliases:
            values = security_alias_record.model_dump(mode="python")
            apply(
                SecurityAlias,
                security_alias_record.id,
                select(SecurityAlias).where(
                    SecurityAlias.security_id == security_alias_record.security_id,
                    SecurityAlias.alias_type == security_alias_record.alias_type,
                    SecurityAlias.normalized_alias == security_alias_record.normalized_alias,
                ),
                values,
                SecurityAlias(**values),
                "security_alias:"
                f"{security_alias_record.security_id}:"
                f"{security_alias_record.alias_type}:"
                f"{security_alias_record.normalized_alias}",
            )

        return SeedResult(
            version=manifest.version,
            inserted_count=inserted_count,
            existing_count=existing_count,
        )

    def _apply_record(
        self,
        *,
        model: type[ModelT],
        record_id: UUID,
        natural_query: Select[tuple[ModelT]],
        values: Mapping[str, object],
        new_instance: ModelT,
        label: str,
    ) -> bool:
        by_id = self._session.get(model, record_id)
        by_natural_key = self._session.scalar(natural_query)
        if by_id is not None and by_natural_key is not None:
            if by_id.id != by_natural_key.id:
                raise SeedConflictError(f"seed key collision for {label}")

        existing = by_id if by_id is not None else by_natural_key
        if existing is not None:
            if existing.id != record_id:
                raise SeedConflictError(f"seed UUID collision for {label}")
            mismatched_fields = [
                field_name
                for field_name, expected_value in values.items()
                if getattr(existing, field_name) != expected_value
            ]
            if mismatched_fields:
                joined_fields = ", ".join(sorted(mismatched_fields))
                raise SeedConflictError(f"seed conflict for {label}: {joined_fields}")
            return False

        self._session.add(new_instance)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise SeedConflictError(f"database rejected seed record {label}") from error
        return True
