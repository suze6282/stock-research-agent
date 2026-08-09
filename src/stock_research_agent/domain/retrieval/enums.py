"""Closed retrieval vocabularies."""

from enum import StrEnum


class RetrievalMode(StrEnum):
    LEXICAL = "LEXICAL"
    VECTOR = "VECTOR"
    HYBRID = "HYBRID"


class IndexStatus(StrEnum):
    BUILDING = "BUILDING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class VectorHealth(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class RetrievalStatus(StrEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"
