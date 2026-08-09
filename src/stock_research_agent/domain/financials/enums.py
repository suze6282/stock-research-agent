"""Stable vocabularies for financial normalization contracts."""

from enum import StrEnum


class StatementType(StrEnum):
    INCOME_STATEMENT = "INCOME_STATEMENT"
    BALANCE_SHEET = "BALANCE_SHEET"
    CASH_FLOW = "CASH_FLOW"
    SHARES = "SHARES"


class FactNature(StrEnum):
    DURATION = "DURATION"
    INSTANT = "INSTANT"
    PER_SHARE = "PER_SHARE"
    SHARES = "SHARES"
    RATIO_INPUT = "RATIO_INPUT"


class UnitType(StrEnum):
    MONETARY_AMOUNT = "MONETARY_AMOUNT"
    PER_SHARE = "PER_SHARE"
    SHARES = "SHARES"
    RATIO = "RATIO"


class ConceptStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class MappingStatus(StrEnum):
    APPROVED = "APPROVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMAPPED = "UNMAPPED"
    DEPRECATED = "DEPRECATED"


class QualityStatus(StrEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"
