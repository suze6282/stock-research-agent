"""Pydantic contracts shared by security master services and adapters."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stock_research_agent.domain.securities.enums import (
    ExchangeAliasType,
    IdentifierScheme,
    IssuerStatus,
    ListingStatus,
    MasterDataStatus,
    MatchType,
    ResolutionStatus,
    SecurityAliasType,
    SecurityType,
)
from stock_research_agent.domain.securities.normalization import (
    MAX_SECURITY_QUERY_LENGTH,
    normalize_company_name,
    normalize_exchange_alias,
    normalize_external_identifier,
    normalize_symbol,
)

_COUNTRY_PATTERN = re.compile(r"[A-Z]{2}\Z")
_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}\Z")
_MIC_PATTERN = re.compile(r"[A-Z0-9]{4}\Z")
_SCHEME_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{1,63}\Z")
SUPPORTED_COUNTRY_CODES = frozenset({"CN", "US"})
SUPPORTED_CURRENCY_CODES = frozenset({"CNY", "USD"})
SUPPORTED_EXCHANGE_MICS = frozenset({"XNAS", "XSHG"})


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


def _validate_country(value: str) -> str:
    if not _COUNTRY_PATTERN.fullmatch(value):
        raise ValueError("country code must be ISO 3166-1 alpha-2 uppercase")
    if value not in SUPPORTED_COUNTRY_CODES:
        raise ValueError("country code is not supported by the V0.1 master data")
    return value


def _validate_currency(value: str) -> str:
    if not _CURRENCY_PATTERN.fullmatch(value):
        raise ValueError("currency code must be ISO 4217 uppercase")
    if value not in SUPPORTED_CURRENCY_CODES:
        raise ValueError("currency code is not supported by the V0.1 master data")
    return value


def _validate_mic(value: str) -> str:
    if not _MIC_PATTERN.fullmatch(value):
        raise ValueError("MIC must contain four uppercase letters or digits")
    if value not in SUPPORTED_EXCHANGE_MICS:
        raise ValueError("MIC is not supported by the V0.1 master data")
    return value


def validate_scheme_token(value: str) -> str:
    """Validate storage vocabulary without enabling runtime resolution."""
    if not _SCHEME_PATTERN.fullmatch(value):
        raise ValueError("identifier scheme must be an uppercase token")
    return value


class TimestampedRecord(DomainModel):
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone aware")
        return value.astimezone(UTC)


class MarketRecord(TimestampedRecord):
    id: UUID
    code: str
    name: str
    country_code: str
    default_currency_code: str
    status: MasterDataStatus

    _country = field_validator("country_code")(_validate_country)
    _currency = field_validator("default_currency_code")(_validate_currency)


class ExchangeRecord(TimestampedRecord):
    id: UUID
    market_id: UUID
    mic: str
    name: str
    short_name: str
    country_code: str
    timezone: str
    default_currency_code: str
    calendar_code: str | None
    status: MasterDataStatus

    _mic = field_validator("mic")(_validate_mic)
    _country = field_validator("country_code")(_validate_country)
    _currency = field_validator("default_currency_code")(_validate_currency)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must be a valid IANA name") from error
        return value


class ExchangeAliasRecord(TimestampedRecord):
    id: UUID
    exchange_id: UUID
    alias: str
    normalized_alias: str
    alias_type: ExchangeAliasType
    is_active: bool

    @model_validator(mode="after")
    def normalized_value_matches(self) -> Self:
        if self.normalized_alias != normalize_exchange_alias(self.alias):
            raise ValueError("normalized exchange alias does not match raw alias")
        return self


class IssuerRecord(TimestampedRecord):
    id: UUID
    legal_name: str
    normalized_legal_name: str
    display_name: str
    normalized_display_name: str
    country_code: str
    issuer_status: IssuerStatus

    _country = field_validator("country_code")(_validate_country)

    @model_validator(mode="after")
    def normalized_names_match(self) -> Self:
        if self.normalized_legal_name != normalize_company_name(self.legal_name):
            raise ValueError("normalized legal name does not match raw legal name")
        if self.normalized_display_name != normalize_company_name(self.display_name):
            raise ValueError("normalized display name does not match raw display name")
        return self


class IdentifierRecord(TimestampedRecord):
    id: UUID
    owner_id: UUID
    scheme: str
    value: str
    normalized_value: str
    source_name: str
    valid_from: date | None
    valid_to: date | None
    is_primary: bool | None

    _scheme = field_validator("scheme")(validate_scheme_token)

    @model_validator(mode="after")
    def validate_identifier(self) -> Self:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("identifier valid_to cannot precede valid_from")
        if (
            self.scheme == IdentifierScheme.SEC_CIK
            and self.normalized_value != normalize_external_identifier(self.scheme, self.value)
        ):
            raise ValueError("normalized identifier does not match raw identifier")
        return self


class SecurityRecord(TimestampedRecord):
    id: UUID
    issuer_id: UUID
    exchange_id: UUID
    symbol: str
    normalized_symbol: str
    display_name: str
    security_type: SecurityType
    share_class: str | None
    currency_code: str
    listing_status: ListingStatus
    listing_date: date | None
    delisting_date: date | None
    is_primary_listing: bool | None

    _currency = field_validator("currency_code")(_validate_currency)

    @model_validator(mode="after")
    def validate_security(self) -> Self:
        if self.normalized_symbol != normalize_symbol(self.symbol):
            raise ValueError("normalized symbol does not match raw symbol")
        if self.listing_date and self.delisting_date and self.delisting_date < self.listing_date:
            raise ValueError("delisting date cannot precede listing date")
        return self


class SecurityAliasRecord(TimestampedRecord):
    id: UUID
    security_id: UUID
    alias: str
    normalized_alias: str
    alias_type: SecurityAliasType
    locale: str | None
    source_name: str
    valid_from: date | None
    valid_to: date | None
    is_active: bool

    @model_validator(mode="after")
    def validate_alias(self) -> Self:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("alias valid_to cannot precede valid_from")
        if self.alias_type in {
            SecurityAliasType.SYMBOL,
            SecurityAliasType.SYMBOL_WITH_EXCHANGE,
            SecurityAliasType.PROVIDER_SYMBOL,
        }:
            expected = normalize_symbol(self.alias)
        else:
            expected = normalize_company_name(self.alias)
        if self.normalized_alias != expected:
            raise ValueError("normalized security alias does not match raw alias")
        return self


class SecurityCandidate(DomainModel):
    security_id: UUID
    issuer_id: UUID
    issuer_display_name: str
    security_display_name: str
    symbol: str
    exchange_mic: str
    exchange_name: str
    market_code: str
    currency_code: str
    listing_status: ListingStatus
    match_reason: str

    _mic = field_validator("exchange_mic")(_validate_mic)
    _currency = field_validator("currency_code")(_validate_currency)


class SecurityResolutionResult(DomainModel):
    status: ResolutionStatus
    original_query: str
    normalized_query: str = Field(max_length=MAX_SECURITY_QUERY_LENGTH)
    match_type: MatchType
    candidate_count: int = Field(ge=0, le=10)
    candidates: tuple[SecurityCandidate, ...] = Field(default_factory=tuple, max_length=10)
    warnings: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_result_semantics(self) -> Self:
        if self.candidate_count != len(self.candidates):
            raise ValueError("candidate_count must equal candidates length")
        if self.status is ResolutionStatus.RESOLVED and self.candidate_count != 1:
            raise ValueError("RESOLVED must contain exactly one candidate")
        if self.status is ResolutionStatus.AMBIGUOUS and self.candidate_count < 1:
            raise ValueError("AMBIGUOUS must contain at least one candidate")
        if self.status in {ResolutionStatus.NOT_FOUND, ResolutionStatus.INVALID_QUERY}:
            if self.candidate_count != 0:
                raise ValueError("terminal empty status cannot contain candidates")
            if self.match_type is not MatchType.NONE:
                raise ValueError("terminal empty status must use NONE match type")
        elif self.match_type is MatchType.NONE:
            raise ValueError("candidate-bearing status cannot use NONE match type")
        if self.match_type is MatchType.PREFIX_SUGGESTION:
            if self.status is not ResolutionStatus.AMBIGUOUS:
                raise ValueError("prefix suggestions must use AMBIGUOUS status")
        return self


class IssuerDetail(DomainModel):
    issuer: IssuerRecord
    identifiers: tuple[IdentifierRecord, ...] = ()


class SecurityDetail(DomainModel):
    security: SecurityRecord
    issuer: IssuerRecord
    exchange: ExchangeRecord
    market: MarketRecord
    identifiers: tuple[IdentifierRecord, ...] = ()
    aliases: tuple[SecurityAliasRecord, ...] = ()


class SeedMarket(DomainModel):
    id: UUID
    code: str
    name: str
    country_code: str
    default_currency_code: str
    status: MasterDataStatus

    _country = field_validator("country_code")(_validate_country)
    _currency = field_validator("default_currency_code")(_validate_currency)


class SeedExchange(DomainModel):
    id: UUID
    market_id: UUID
    mic: str
    name: str
    short_name: str
    country_code: str
    timezone: str
    default_currency_code: str
    calendar_code: str | None = None
    status: MasterDataStatus

    _mic = field_validator("mic")(_validate_mic)
    _country = field_validator("country_code")(_validate_country)
    _currency = field_validator("default_currency_code")(_validate_currency)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must be a valid IANA name") from error
        return value


class SeedExchangeAlias(DomainModel):
    id: UUID
    exchange_id: UUID
    alias: str
    normalized_alias: str
    alias_type: ExchangeAliasType
    is_active: bool = True

    @model_validator(mode="after")
    def normalized_value_matches(self) -> Self:
        if self.normalized_alias != normalize_exchange_alias(self.alias):
            raise ValueError("normalized exchange alias does not match raw alias")
        return self


class SeedIssuer(DomainModel):
    id: UUID
    legal_name: str
    normalized_legal_name: str
    display_name: str
    normalized_display_name: str
    country_code: str
    issuer_status: IssuerStatus

    _country = field_validator("country_code")(_validate_country)

    @model_validator(mode="after")
    def normalized_names_match(self) -> Self:
        if self.normalized_legal_name != normalize_company_name(self.legal_name):
            raise ValueError("normalized legal name does not match raw legal name")
        if self.normalized_display_name != normalize_company_name(self.display_name):
            raise ValueError("normalized display name does not match raw display name")
        return self


class SeedIssuerIdentifier(DomainModel):
    id: UUID
    issuer_id: UUID
    scheme: IdentifierScheme
    value: str
    normalized_value: str
    source_name: str
    valid_from: date | None = None
    valid_to: date | None = None
    is_primary: bool | None = None

    @model_validator(mode="after")
    def validate_identifier(self) -> Self:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("identifier valid_to cannot precede valid_from")
        if self.normalized_value != normalize_external_identifier(self.scheme, self.value):
            raise ValueError("normalized identifier does not match raw identifier")
        return self


class SeedSecurity(DomainModel):
    id: UUID
    issuer_id: UUID
    exchange_id: UUID
    symbol: str
    normalized_symbol: str
    display_name: str
    security_type: SecurityType
    share_class: str | None = None
    currency_code: str
    listing_status: ListingStatus
    listing_date: date | None = None
    delisting_date: date | None = None
    is_primary_listing: bool | None = None

    _currency = field_validator("currency_code")(_validate_currency)

    @model_validator(mode="after")
    def validate_security(self) -> Self:
        if self.normalized_symbol != normalize_symbol(self.symbol):
            raise ValueError("normalized symbol does not match raw symbol")
        if self.listing_date and self.delisting_date and self.delisting_date < self.listing_date:
            raise ValueError("delisting date cannot precede listing date")
        return self


class SeedSecurityAlias(DomainModel):
    id: UUID
    security_id: UUID
    alias: str
    normalized_alias: str
    alias_type: SecurityAliasType
    locale: str | None = None
    source_name: str
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_alias(self) -> Self:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("alias valid_to cannot precede valid_from")
        if self.alias_type in {
            SecurityAliasType.SYMBOL,
            SecurityAliasType.SYMBOL_WITH_EXCHANGE,
            SecurityAliasType.PROVIDER_SYMBOL,
        }:
            expected = normalize_symbol(self.alias)
        else:
            expected = normalize_company_name(self.alias)
        if self.normalized_alias != expected:
            raise ValueError("normalized security alias does not match raw alias")
        return self


class SecurityMasterSeedManifest(DomainModel):
    version: str
    evidence_paths: tuple[str, ...]
    markets: tuple[SeedMarket, ...]
    exchanges: tuple[SeedExchange, ...]
    exchange_aliases: tuple[SeedExchangeAlias, ...]
    issuers: tuple[SeedIssuer, ...]
    issuer_identifiers: tuple[SeedIssuerIdentifier, ...]
    securities: tuple[SeedSecurity, ...]
    security_aliases: tuple[SeedSecurityAlias, ...]


class SeedResult(DomainModel):
    version: str
    inserted_count: int = Field(ge=0)
    existing_count: int = Field(ge=0)
