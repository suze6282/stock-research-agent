"""Deterministic, offline normalization for security identity input."""

from __future__ import annotations

import re
import unicodedata

from stock_research_agent.domain.securities.enums import IdentifierScheme
from stock_research_agent.domain.securities.exceptions import InvalidSecurityQuery

MAX_SECURITY_QUERY_LENGTH = 256
MAX_EXCHANGE_ALIAS_LENGTH = 32
_SYMBOL_PATTERN = re.compile(r"[A-Z0-9]+(?:[.:-][A-Z0-9]+)*\Z")
_EXCHANGE_ALIAS_PATTERN = re.compile(r"[A-Z0-9]{1,32}\Z")
_COMPANY_SEPARATOR_PATTERN = re.compile(r"[,.;。、、]+")


def _nfkc_checked(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidSecurityQuery("query must be a string")
    if len(value) > MAX_SECURITY_QUERY_LENGTH:
        raise InvalidSecurityQuery("query exceeds 256 characters")

    normalized = unicodedata.normalize("NFKC", value)
    if len(normalized) > MAX_SECURITY_QUERY_LENGTH:
        raise InvalidSecurityQuery("normalized query exceeds 256 characters")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise InvalidSecurityQuery("query contains a control or invisible character")
    return normalized


def _require_meaningful(value: str) -> str:
    if not value or not any(character.isalnum() for character in value):
        raise InvalidSecurityQuery("query must contain a letter or number")
    return value


def normalize_free_text(value: str) -> str:
    """Normalize safe free text while preserving meaningful punctuation."""
    normalized = " ".join(_nfkc_checked(value).strip().split()).upper()
    return _require_meaningful(normalized)


def normalize_symbol(value: str) -> str:
    """Normalize a symbol or explicitly qualified symbol."""
    normalized = "".join(_nfkc_checked(value).split()).upper()
    _require_meaningful(normalized)
    if not _SYMBOL_PATTERN.fullmatch(normalized):
        raise InvalidSecurityQuery("symbol contains unsupported characters or separators")
    return normalized


def normalize_exchange_alias(value: str) -> str:
    """Normalize only allow-listed exchange aliases without guessing."""
    normalized = _nfkc_checked(value).strip().upper()
    if normalized.startswith("."):
        normalized = normalized[1:]
    normalized = "".join(normalized.split())
    _require_meaningful(normalized)
    if len(normalized) > MAX_EXCHANGE_ALIAS_LENGTH:
        raise InvalidSecurityQuery("exchange alias exceeds 32 characters")
    if not _EXCHANGE_ALIAS_PATTERN.fullmatch(normalized):
        raise InvalidSecurityQuery("exchange alias contains unsupported characters")
    return normalized


def normalize_company_name(value: str) -> str:
    """Normalize company names without removing legal name characters broadly."""
    normalized = _nfkc_checked(value).strip()
    normalized = _COMPANY_SEPARATOR_PATTERN.sub(" ", normalized)
    normalized = " ".join(normalized.split()).upper()
    return _require_meaningful(normalized)


def normalize_external_identifier(scheme: str, value: str) -> str:
    """Normalize a confirmed external identifier scheme supported by V0.1."""
    normalized_scheme = "_".join(_nfkc_checked(scheme).strip().upper().split())
    if normalized_scheme != IdentifierScheme.SEC_CIK:
        raise InvalidSecurityQuery("external identifier scheme is not supported")

    normalized_value = "".join(_nfkc_checked(value).split())
    if not normalized_value or not normalized_value.isascii() or not normalized_value.isdigit():
        raise InvalidSecurityQuery("SEC CIK must contain only digits")
    if len(normalized_value) > 10:
        raise InvalidSecurityQuery("SEC CIK exceeds 10 digits")
    return normalized_value.zfill(10)
