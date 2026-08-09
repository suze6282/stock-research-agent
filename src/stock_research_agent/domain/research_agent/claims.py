"""Deterministic Claim candidate construction and support validation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceRole,
    EvidenceStatus,
    EvidenceType,
    ResearchMode,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkWrite,
    ResearchClaimCompletion,
    ResearchClaimWrite,
    ResearchEvidenceRecord,
)


class ResearchClaimProposal(ResearchClaimWrite):
    """Candidate plus the exact Evidence IDs proposed by deterministic rules."""

    proposed_evidence_ids: tuple[UUID, ...] = Field(max_length=100)


class ClaimValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    completion: ResearchClaimCompletion
    links: tuple[ClaimEvidenceLinkWrite, ...] = Field(max_length=100)


class DeterministicClaimBuilder:
    """Map bounded structured Evidence to untrusted candidate Claims."""

    def __init__(self, *, id_factory: Callable[[], UUID]) -> None:
        self._id_factory = id_factory

    def propose_claims(
        self,
        *,
        run_id: UUID,
        evidence: Sequence[ResearchEvidenceRecord],
        created_at: datetime,
        research_mode: ResearchMode = ResearchMode.REAL_RESEARCH,
    ) -> tuple[ResearchClaimProposal, ...]:
        claims: list[ResearchClaimProposal] = []
        for item in evidence:
            if item.run_id != run_id:
                continue
            proposal = self._propose(item, created_at, research_mode=research_mode)
            if proposal is not None:
                claims.append(proposal)
        return tuple(claims)

    def _propose(
        self,
        evidence: ResearchEvidenceRecord,
        created_at: datetime,
        *,
        research_mode: ResearchMode,
    ) -> ResearchClaimProposal | None:
        if evidence.evidence_type is EvidenceType.BLOCKED_CAPABILITY_EVIDENCE:
            return self._basic(
                evidence,
                created_at,
                ClaimType.LIMITATION,
                str(evidence.payload.get("capability_code", "CAPABILITY_BLOCKED")),
            )
        if evidence.status is not EvidenceStatus.VALID:
            return None
        if evidence.synthetic_status is SyntheticStatus.UNKNOWN or (
            evidence.synthetic_status is SyntheticStatus.SYNTHETIC_TEST_ONLY
            and research_mode is not ResearchMode.SYNTHETIC_TEST_ONLY
        ):
            return None

        if evidence.evidence_type is EvidenceType.SECURITY_MASTER_EVIDENCE:
            required = {"security_id", "issuer", "symbol", "exchange"}
            if required.issubset(evidence.payload):
                return self._basic(
                    evidence,
                    created_at,
                    ClaimType.IDENTITY,
                    "SECURITY_IDENTITY",
                )
        if evidence.evidence_type is EvidenceType.DATA_QUALITY_EVIDENCE:
            return self._basic(
                evidence,
                created_at,
                ClaimType.DATA_QUALITY,
                str(evidence.payload.get("quality_code", "DATA_QUALITY_LIMITATION")),
            )
        if evidence.evidence_type in {
            EvidenceType.DERIVED_METRIC_EVIDENCE,
            EvidenceType.STRUCTURED_FACT_EVIDENCE,
        }:
            numeric = self._numeric(evidence, created_at)
            if numeric is not None:
                return numeric
            return self._basic(
                evidence,
                created_at,
                ClaimType.LIMITATION,
                "METRIC_INPUT_INCOMPLETE",
            )
        if evidence.evidence_type is EvidenceType.DOCUMENT_CITATION_EVIDENCE:
            code = evidence.payload.get("disclosure_code")
            if isinstance(code, str):
                return self._basic(
                    evidence,
                    created_at,
                    ClaimType.DOCUMENT_DISCLOSURE,
                    code,
                )
        if evidence.evidence_type is EvidenceType.CORPORATE_ACTION_EVIDENCE:
            code = evidence.payload.get("action_code")
            if isinstance(code, str):
                return self._basic(
                    evidence,
                    created_at,
                    ClaimType.CORPORATE_ACTION,
                    code,
                )
        return None

    def _numeric(
        self,
        evidence: ResearchEvidenceRecord,
        created_at: datetime,
    ) -> ResearchClaimProposal | None:
        payload = evidence.payload
        try:
            raw_value = payload["value"]
            raw_unit = payload["unit"]
            raw_period = payload["period"]
            raw_as_of = payload["as_of_time"]
            raw_basis = payload["metric_basis"]
            code = payload["metric_code"]
            if not isinstance(raw_value, str):
                return None
            if not isinstance(raw_unit, str):
                return None
            if not isinstance(raw_period, str):
                return None
            if not isinstance(raw_as_of, str):
                return None
            if not isinstance(raw_basis, str):
                return None
            if not isinstance(code, str):
                return None
            value = Decimal(raw_value)
            if not value.is_finite():
                return None
            as_of = datetime.fromisoformat(raw_as_of.replace("Z", "+00:00"))
        except (KeyError, InvalidOperation, ValueError):
            return None
        claim_type = (
            ClaimType.FINANCIAL_METRIC
            if evidence.evidence_type is EvidenceType.DERIVED_METRIC_EVIDENCE
            else ClaimType.FINANCIAL_FACT
        )
        currency = payload.get("currency_code")
        return ResearchClaimProposal(
            id=self._id_factory(),
            run_id=evidence.run_id,
            claim_type=claim_type,
            lifecycle_status=ClaimLifecycleStatus.CANDIDATE,
            support_status=None,
            statement_code=code,
            value=value,
            unit=raw_unit,
            currency_code=currency if isinstance(currency, str) else None,
            period=raw_period,
            as_of_time=as_of,
            metric_basis=raw_basis,
            builder_version="deterministic-claim-builder-v1",
            created_at=created_at,
            proposed_evidence_ids=(evidence.id,),
        )

    def _basic(
        self,
        evidence: ResearchEvidenceRecord,
        created_at: datetime,
        claim_type: ClaimType,
        statement_code: str,
    ) -> ResearchClaimProposal:
        return ResearchClaimProposal(
            id=self._id_factory(),
            run_id=evidence.run_id,
            claim_type=claim_type,
            lifecycle_status=ClaimLifecycleStatus.CANDIDATE,
            support_status=None,
            statement_code=statement_code,
            builder_version="deterministic-claim-builder-v1",
            created_at=created_at,
            proposed_evidence_ids=(evidence.id,),
        )


class ClaimSupportValidator:
    """The only component authorized to assign final Claim support."""

    def __init__(self, *, id_factory: Callable[[], UUID]) -> None:
        self._id_factory = id_factory

    def validate(
        self,
        *,
        claim: ResearchClaimProposal,
        evidence: Sequence[ResearchEvidenceRecord],
        completed_at: datetime,
        real_research: bool,
    ) -> ClaimValidationResult:
        proposed = set(claim.proposed_evidence_ids)
        unique: dict[UUID, ResearchEvidenceRecord] = {}
        for item in evidence:
            if item.run_id == claim.run_id and item.id in proposed:
                unique.setdefault(item.id, item)
        selected = tuple(unique.values())

        support, role = self._support(claim, selected, real_research)
        links = tuple(
            ClaimEvidenceLinkWrite(
                id=self._id_factory(),
                run_id=claim.run_id,
                claim_id=claim.id,
                evidence_id=item.id,
                role=role,
                created_at=completed_at,
            )
            for item in selected
            if self._linkable(item, support, claim.claim_type)
        )
        return ClaimValidationResult(
            completion=ResearchClaimCompletion(
                lifecycle_status=ClaimLifecycleStatus.VALIDATED,
                support_status=support,
                validator_version="claim-support-validator-v1",
                completed_at=completed_at,
            ),
            links=links,
        )

    @staticmethod
    def _support(
        claim: ResearchClaimProposal,
        evidence: Sequence[ResearchEvidenceRecord],
        real_research: bool,
    ) -> tuple[ClaimSupportStatus, EvidenceRole]:
        if not evidence:
            return ClaimSupportStatus.UNSUPPORTED, EvidenceRole.CONTEXT
        if any(item.status is EvidenceStatus.CONFLICTING for item in evidence):
            return ClaimSupportStatus.CONFLICTING, EvidenceRole.CONTRADICTING
        blocked = tuple(
            item
            for item in evidence
            if item.evidence_type is EvidenceType.BLOCKED_CAPABILITY_EVIDENCE
            or item.status is EvidenceStatus.BLOCKED
        )
        if blocked:
            if claim.claim_type in {ClaimType.DATA_QUALITY, ClaimType.LIMITATION}:
                return ClaimSupportStatus.BLOCKED, EvidenceRole.LIMITATION
            return ClaimSupportStatus.UNSUPPORTED, EvidenceRole.CONTEXT
        if any(item.status is not EvidenceStatus.VALID for item in evidence):
            return ClaimSupportStatus.UNSUPPORTED, EvidenceRole.CONTEXT
        if real_research and any(
            item.synthetic_status in {SyntheticStatus.SYNTHETIC_TEST_ONLY, SyntheticStatus.UNKNOWN}
            for item in evidence
        ):
            return ClaimSupportStatus.UNSUPPORTED, EvidenceRole.CONTEXT

        if claim.claim_type is ClaimType.IDENTITY:
            valid = any(
                item.evidence_type is EvidenceType.SECURITY_MASTER_EVIDENCE
                and {"security_id", "issuer", "symbol", "exchange"}.issubset(item.payload)
                for item in evidence
            )
            return (
                ClaimSupportStatus.SUPPORTED if valid else ClaimSupportStatus.UNSUPPORTED,
                EvidenceRole.PRIMARY,
            )
        if claim.claim_type in {
            ClaimType.FINANCIAL_FACT,
            ClaimType.FINANCIAL_METRIC,
            ClaimType.VALUATION_METRIC,
        }:
            if any(_metric_matches_claim(claim, item) for item in evidence):
                return ClaimSupportStatus.SUPPORTED, EvidenceRole.PRIMARY
            return ClaimSupportStatus.PARTIALLY_SUPPORTED, EvidenceRole.CONTEXT
        if claim.claim_type is ClaimType.DOCUMENT_DISCLOSURE:
            documents = tuple(
                item
                for item in evidence
                if item.evidence_type is EvidenceType.DOCUMENT_CITATION_EVIDENCE
            )
            if any(item.published_at is None for item in documents):
                return ClaimSupportStatus.BLOCKED, EvidenceRole.LIMITATION
            valid = any(
                item.citation_id is not None
                and item.payload.get("disclosure_code") == claim.statement_code
                for item in documents
            )
            return (
                ClaimSupportStatus.SUPPORTED if valid else ClaimSupportStatus.UNSUPPORTED,
                EvidenceRole.PRIMARY,
            )
        if claim.claim_type in {ClaimType.DATA_QUALITY, ClaimType.LIMITATION}:
            return ClaimSupportStatus.SUPPORTED, EvidenceRole.PRIMARY
        return ClaimSupportStatus.UNSUPPORTED, EvidenceRole.CONTEXT

    @staticmethod
    def _linkable(
        evidence: ResearchEvidenceRecord,
        support: ClaimSupportStatus,
        claim_type: ClaimType,
    ) -> bool:
        if support is ClaimSupportStatus.SUPPORTED:
            return evidence.status is EvidenceStatus.VALID
        if support in {ClaimSupportStatus.CONFLICTING, ClaimSupportStatus.BLOCKED}:
            return True
        return claim_type in {ClaimType.DATA_QUALITY, ClaimType.LIMITATION}


def _metric_matches_claim(
    claim: ResearchClaimProposal,
    evidence: ResearchEvidenceRecord,
) -> bool:
    if evidence.evidence_type not in {
        EvidenceType.DERIVED_METRIC_EVIDENCE,
        EvidenceType.STRUCTURED_FACT_EVIDENCE,
    }:
        return False
    if claim.claim_type in {ClaimType.FINANCIAL_METRIC, ClaimType.VALUATION_METRIC} and (
        evidence.calculation_run_id is None
        or not evidence.calculation_input_ids
        or evidence.formula_version is None
    ):
        return False
    payload = evidence.payload
    try:
        raw_value = payload["value"]
        raw_as_of = payload["as_of_time"]
        if not isinstance(raw_value, str) or not isinstance(raw_as_of, str):
            return False
        evidence_value = Decimal(raw_value)
        evidence_as_of = datetime.fromisoformat(raw_as_of.replace("Z", "+00:00"))
    except (KeyError, InvalidOperation, ValueError):
        return False
    return (
        evidence_value == claim.value
        and payload.get("unit") == claim.unit
        and payload.get("period") == claim.period
        and evidence_as_of == claim.as_of_time
        and payload.get("metric_basis") == claim.metric_basis
        and (
            claim.claim_type is ClaimType.FINANCIAL_FACT
            or evidence.formula_version == claim.metric_basis
        )
    )
