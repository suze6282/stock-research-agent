"""Immutable runtime Reflection policy and explicit idempotent seed."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol, Self

from pydantic import Field, model_validator

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.schemas import (
    Checksum,
    FrozenReportContract,
    Version,
)

RUNTIME_REFLECTION_POLICY_VERSION = "runtime-report-reflection-v1"


class ReflectionSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RuntimeReflectionCheck(StrEnum):
    FACTUAL_BLOCK_HAS_CLAIM = "FACTUAL_BLOCK_HAS_CLAIM"
    PRIMARY_CLAIM_HAS_EVIDENCE = "PRIMARY_CLAIM_HAS_EVIDENCE"
    DOCUMENT_CLAIM_HAS_VALID_CITATION = "DOCUMENT_CLAIM_HAS_VALID_CITATION"
    STRUCTURED_CLAIM_HAS_LINEAGE = "STRUCTURED_CLAIM_HAS_LINEAGE"
    SECURITY_MATCHES = "SECURITY_MATCHES"
    SNAPSHOT_MATCHES = "SNAPSHOT_MATCHES"
    AS_OF_MATCHES = "AS_OF_MATCHES"
    NO_FUTURE_EVIDENCE = "NO_FUTURE_EVIDENCE"
    STRICT_DOCUMENT_PUBLISHED_AT_KNOWN = "STRICT_DOCUMENT_PUBLISHED_AT_KNOWN"
    NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE = "NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE"
    NO_CROSS_SECURITY_RECORDS = "NO_CROSS_SECURITY_RECORDS"
    NO_CROSS_SNAPSHOT_RECORDS = "NO_CROSS_SNAPSHOT_RECORDS"
    CONFLICTING_CLAIMS_DISCLOSED = "CONFLICTING_CLAIMS_DISCLOSED"
    PARTIAL_SUPPORT_QUALIFIED = "PARTIAL_SUPPORT_QUALIFIED"
    UNSUPPORTED_CLAIMS_RESTRICTED = "UNSUPPORTED_CLAIMS_RESTRICTED"
    BLOCKED_CAPABILITY_NOT_COMPLETED = "BLOCKED_CAPABILITY_NOT_COMPLETED"
    DATA_QUALITY_PRESENT = "DATA_QUALITY_PRESENT"
    LIMITATIONS_PRESENT = "LIMITATIONS_PRESENT"
    NO_ORPHAN_BODY_REFERENCE = "NO_ORPHAN_BODY_REFERENCE"
    NO_UNUSED_APPENDIX_REFERENCE = "NO_UNUSED_APPENDIX_REFERENCE"
    CITATION_VALID = "CITATION_VALID"
    CLAIM_SET_CHECKSUM_MATCHES = "CLAIM_SET_CHECKSUM_MATCHES"
    EVIDENCE_LINK_SET_CHECKSUMS_MATCH = "EVIDENCE_LINK_SET_CHECKSUMS_MATCH"
    PACKAGE_CHECKSUM_MATCHES = "PACKAGE_CHECKSUM_MATCHES"
    NO_RATING_LANGUAGE = "NO_RATING_LANGUAGE"
    NO_TARGET_PRICE = "NO_TARGET_PRICE"
    NO_POSITION_ADVICE = "NO_POSITION_ADVICE"
    NO_TRADING_INSTRUCTION = "NO_TRADING_INSTRUCTION"
    NO_UNSUPPORTED_OVERSTATEMENT = "NO_UNSUPPORTED_OVERSTATEMENT"
    FIXTURE_NOT_DESCRIBED_AS_LIVE = "FIXTURE_NOT_DESCRIBED_AS_LIVE"
    SYNTHETIC_NOT_REAL_COMPANY_RESEARCH = "SYNTHETIC_NOT_REAL_COMPANY_RESEARCH"
    EXCERPT_WITHIN_POLICY = "EXCERPT_WITHIN_POLICY"
    UNIT_CURRENCY_MATCH = "UNIT_CURRENCY_MATCH"
    REPORT_AS_OF_PRESENT = "REPORT_AS_OF_PRESENT"
    SNAPSHOT_IDENTITY_PRESENT = "SNAPSHOT_IDENTITY_PRESENT"
    NO_FALSE_MODEL_CALL_CLAIM = "NO_FALSE_MODEL_CALL_CLAIM"
    RETRIEVAL_CAPABILITY_HONEST = "RETRIEVAL_CAPABILITY_HONEST"
    JSON_MARKDOWN_CHECKSUMS_MATCH = "JSON_MARKDOWN_CHECKSUMS_MATCH"
    REPORT_STRUCTURE_VERSION_CHAIN_VALID = "REPORT_STRUCTURE_VERSION_CHAIN_VALID"
    REPORT_INPUT_MANIFEST_UNCHANGED = "REPORT_INPUT_MANIFEST_UNCHANGED"


class RuntimeReflectionPolicyRecord(FrozenReportContract):
    version: Version
    checksum: Checksum
    required_checks: tuple[RuntimeReflectionCheck, ...] = Field(
        min_length=40,
        max_length=40,
    )
    severity_threshold: Literal[ReflectionSeverity.HIGH]
    max_reflection_rounds: Literal[2]
    max_revision_rounds: Literal[1]
    allow_model_reflection: Literal[False]
    require_release_gate: Literal[True]

    @model_validator(mode="after")
    def require_exact_check_registry(self) -> Self:
        if self.required_checks != tuple(RuntimeReflectionCheck):
            raise ValueError("required checks must equal the approved registry")
        return self


class RuntimeReflectionPolicySeedResult(FrozenReportContract):
    policy: RuntimeReflectionPolicyRecord
    created: bool


class RuntimeReflectionPolicyRepository(Protocol):
    def get_runtime_reflection_policy(
        self,
        version: str,
    ) -> RuntimeReflectionPolicyRecord | None: ...

    def add_runtime_reflection_policy(
        self,
        value: RuntimeReflectionPolicyRecord,
    ) -> RuntimeReflectionPolicyRecord: ...


class RuntimeReflectionPolicyError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_default_runtime_reflection_policy() -> RuntimeReflectionPolicyRecord:
    definition = {
        "required_checks": tuple(RuntimeReflectionCheck),
        "severity_threshold": ReflectionSeverity.HIGH,
        "max_reflection_rounds": 2,
        "max_revision_rounds": 1,
        "allow_model_reflection": False,
        "require_release_gate": True,
    }
    return RuntimeReflectionPolicyRecord.model_validate(
        {
            "version": RUNTIME_REFLECTION_POLICY_VERSION,
            "checksum": report_checksum(definition),
            **definition,
        }
    )


class RuntimeReflectionPolicySeedService:
    def __init__(self, repository: RuntimeReflectionPolicyRepository) -> None:
        self._repository = repository

    def seed_v1(self) -> RuntimeReflectionPolicySeedResult:
        expected = build_default_runtime_reflection_policy()
        existing = self._repository.get_runtime_reflection_policy(expected.version)
        if existing is not None:
            if existing != expected:
                raise RuntimeReflectionPolicyError("RUNTIME_REFLECTION_POLICY_VERSION_CONFLICT")
            return RuntimeReflectionPolicySeedResult(
                policy=existing,
                created=False,
            )
        created = self._repository.add_runtime_reflection_policy(expected)
        return RuntimeReflectionPolicySeedResult(policy=created, created=True)
