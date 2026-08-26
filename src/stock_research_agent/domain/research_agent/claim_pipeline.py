"""Production deterministic Claim construction, validation, and persistence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.research_agent.claims import (
    ClaimSupportValidator,
    DeterministicClaimBuilder,
)
from stock_research_agent.domain.research_agent.enums import ResearchMode
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ClaimEvidenceLinkWrite,
    ResearchClaimCompletion,
    ResearchClaimRecord,
    ResearchClaimWrite,
    ResearchEvidenceRecord,
)


class ClaimPipelineRepository(Protocol):
    def list_evidence(self, run_id: UUID) -> tuple[ResearchEvidenceRecord, ...]: ...

    def add_claim(self, value: ResearchClaimWrite) -> ResearchClaimRecord: ...

    def add_links(
        self, values: tuple[ClaimEvidenceLinkWrite, ...]
    ) -> tuple[ClaimEvidenceLinkRecord, ...]: ...

    def complete_claim(
        self,
        claim_id: UUID,
        value: ResearchClaimCompletion,
    ) -> ResearchClaimRecord: ...


class ProductionDeterministicClaimPipeline:
    """Persist candidates and let the deterministic Validator assign support."""

    def __init__(
        self,
        *,
        repository: ClaimPipelineRepository,
        builder: DeterministicClaimBuilder,
        validator: ClaimSupportValidator,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._builder = builder
        self._validator = validator
        self._clock = clock

    def build_and_validate(
        self,
        *,
        run_id: UUID,
        research_mode: ResearchMode,
    ) -> tuple[ResearchClaimRecord, ...]:
        evidence = self._repository.list_evidence(run_id)
        proposals = self._builder.propose_claims(
            run_id=run_id,
            evidence=evidence,
            created_at=self._clock(),
            research_mode=research_mode,
        )
        completed: list[ResearchClaimRecord] = []
        for proposal in proposals:
            self._repository.add_claim(
                ResearchClaimWrite.model_validate(
                    proposal.model_dump(
                        mode="python",
                        exclude={"proposed_evidence_ids"},
                    )
                )
            )
            validation = self._validator.validate(
                claim=proposal,
                evidence=evidence,
                completed_at=self._clock(),
                real_research=research_mode is ResearchMode.REAL_RESEARCH,
            )
            if validation.links:
                self._repository.add_links(validation.links)
            completed.append(self._repository.complete_claim(proposal.id, validation.completion))
        return tuple(completed)
