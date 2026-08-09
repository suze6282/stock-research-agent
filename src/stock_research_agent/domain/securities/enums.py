"""Stable string vocabularies for security master contracts."""

from enum import StrEnum


class MasterDataStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


class IssuerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


class ListingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELISTED = "DELISTED"
    UNKNOWN = "UNKNOWN"


class SecurityType(StrEnum):
    COMMON_STOCK = "COMMON_STOCK"


class ExchangeAliasType(StrEnum):
    MIC = "MIC"
    SUFFIX = "SUFFIX"
    SHORT_NAME = "SHORT_NAME"
    DISPLAY_NAME = "DISPLAY_NAME"


class SecurityAliasType(StrEnum):
    SYMBOL = "SYMBOL"
    SYMBOL_WITH_EXCHANGE = "SYMBOL_WITH_EXCHANGE"
    COMPANY_SHORT_NAME = "COMPANY_SHORT_NAME"
    LEGAL_NAME = "LEGAL_NAME"
    ENGLISH_NAME = "ENGLISH_NAME"
    PROVIDER_SYMBOL = "PROVIDER_SYMBOL"
    FORMER_NAME = "FORMER_NAME"


class IdentifierScheme(StrEnum):
    SEC_CIK = "SEC_CIK"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    INVALID_QUERY = "INVALID_QUERY"


class MatchType(StrEnum):
    EXACT_EXCHANGE_SYMBOL = "EXACT_EXCHANGE_SYMBOL"
    EXACT_SYMBOL = "EXACT_SYMBOL"
    EXACT_IDENTIFIER = "EXACT_IDENTIFIER"
    EXACT_ALIAS = "EXACT_ALIAS"
    EXACT_ISSUER_NAME = "EXACT_ISSUER_NAME"
    PREFIX_SUGGESTION = "PREFIX_SUGGESTION"
    NONE = "NONE"
