"""Immutable deterministic report policy and idempotent seed service."""

from __future__ import annotations

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.repositories import ReportPolicyRepository
from stock_research_agent.domain.reports.schemas import (
    ReportPolicyRecord,
    ReportPolicySeedResult,
    ReportPolicyWrite,
)

REPORT_POLICY_VERSION = "verifiable-report-policy-v1"


class ReportPolicyError(RuntimeError):
    """Safe fixed-code policy failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_default_report_policy() -> ReportPolicyRecord:
    """Build the exact approved production-offline policy."""

    definition = {
        "allowed_report_types": tuple(ReportType),
        "allowed_locales": tuple(ReportLocale),
        "allowed_sections": tuple(ReportSection),
        "include_unsupported_claims": True,
        "include_conflicting_claims": True,
        "include_blocked_capabilities": True,
        "include_data_quality": True,
        "include_limitations": True,
        "require_claim_binding": True,
        "require_evidence_binding": True,
        "require_valid_document_citation": True,
        "allow_synthetic_evidence": False,
        "allow_unknown_published_at": False,
        "max_report_blocks": 300,
        "max_claims_per_block": 20,
        "max_citations_per_block": 20,
        "max_excerpt_length": 1000,
        "max_reflection_rounds": 2,
        "max_revision_rounds": 1,
        "allow_model_narrative": False,
        "allow_model_reflection": False,
    }
    return ReportPolicyRecord.model_validate(
        {
            "version": REPORT_POLICY_VERSION,
            "checksum": report_checksum(definition),
            **definition,
        }
    )


class ReportPolicyService:
    def __init__(self, repository: ReportPolicyRepository) -> None:
        self._repository = repository

    def require(self, version: str) -> ReportPolicyRecord:
        policy = self._repository.get_policy(version)
        if policy is None:
            raise ReportPolicyError("REPORT_POLICY_NOT_FOUND")
        if policy.checksum != _policy_checksum(policy):
            raise ReportPolicyError("REPORT_POLICY_CHECKSUM_MISMATCH")
        return policy


class ReportPolicySeedService:
    def __init__(self, repository: ReportPolicyRepository) -> None:
        self._repository = repository

    def seed_v1(self) -> ReportPolicySeedResult:
        expected = build_default_report_policy()
        existing = self._repository.get_policy(expected.version)
        if existing is not None:
            if existing.model_dump(mode="python") != expected.model_dump(mode="python"):
                raise ReportPolicyError("REPORT_POLICY_VERSION_CONFLICT")
            return ReportPolicySeedResult(policy=existing, created=False)
        created = self._repository.add_policy(
            ReportPolicyWrite.model_validate(expected.model_dump(mode="python"))
        )
        return ReportPolicySeedResult(policy=created, created=True)


def _policy_checksum(policy: ReportPolicyRecord) -> str:
    return report_checksum(policy.model_dump(mode="python", exclude={"version", "checksum"}))
