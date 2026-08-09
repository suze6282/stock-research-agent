"""Deterministic Research Request preflight."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.data_access.schemas import DataSnapshotRecord
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.repositories import (
    ResearchRequestRepository,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchPolicyRecord,
    ResearchRequestCreate,
    ResearchRequestRecord,
    ResearchRequestWrite,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot
from stock_research_agent.domain.securities.enums import ResolutionStatus
from stock_research_agent.domain.securities.schemas import SecurityResolutionResult


class SecurityResolver(Protocol):
    def resolve(self, query: str) -> SecurityResolutionResult: ...


class SnapshotReader(Protocol):
    def get_snapshot(self, snapshot_id: UUID) -> DataSnapshotRecord | None: ...


class PolicyReader(Protocol):
    def require(self, version: str) -> ResearchPolicyRecord: ...


class ResearchRequestError(RuntimeError):
    """Safe fixed-code request failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ResearchRequestService:
    def __init__(
        self,
        *,
        resolver: SecurityResolver,
        snapshots: SnapshotReader,
        policies: PolicyReader,
        catalog_provider: Callable[[], ToolCatalogSnapshot],
        repository: ResearchRequestRepository,
        id_factory: Callable[[], UUID],
        now: Callable[[], object],
    ) -> None:
        self._resolver = resolver
        self._snapshots = snapshots
        self._policies = policies
        self._catalog_provider = catalog_provider
        self._repository = repository
        self._id_factory = id_factory
        self._now = now

    def create(self, command: ResearchRequestCreate) -> ResearchRequestRecord:
        resolution = self._resolver.resolve(command.security_query)
        if resolution.status != ResolutionStatus.RESOLVED or len(resolution.candidates) != 1:
            raise ResearchRequestError("SECURITY_NOT_RESOLVED")
        security_id = resolution.candidates[0].security_id

        snapshot = self._snapshots.get_snapshot(command.snapshot_id)
        if snapshot is None:
            raise ResearchRequestError("SNAPSHOT_NOT_FOUND")
        if snapshot.status != "COMPLETE":
            raise ResearchRequestError("SNAPSHOT_NOT_COMPLETE")
        if snapshot.security_id != security_id:
            raise ResearchRequestError("SNAPSHOT_SECURITY_MISMATCH")
        if snapshot.research_as_of_time > command.research_as_of_time:
            raise ResearchRequestError("SNAPSHOT_AFTER_RESEARCH_AS_OF")

        policy = self._policies.require(command.policy_version)
        if command.research_type not in policy.allowed_research_types:
            raise ResearchRequestError("RESEARCH_TYPE_NOT_ALLOWED")
        if any(section not in policy.allowed_sections for section in command.requested_sections):
            raise ResearchRequestError("RESEARCH_SECTION_NOT_ALLOWED")
        self._validate_requested_budgets(command, policy)

        catalog = self._catalog_provider()
        request_basis = {
            **command.model_dump(mode="python"),
            "normalized_security_query": resolution.normalized_query,
            "resolved_security_id": security_id,
            "tool_catalog_version": catalog.catalog_version,
            "tool_catalog_checksum": catalog.catalog_checksum,
        }
        values = {
            **request_basis,
            "id": self._id_factory(),
            "request_checksum": stable_checksum(request_basis),
            "created_at": self._now(),
        }
        write = ResearchRequestWrite.model_validate(values)
        return self._repository.add_request(write)

    @staticmethod
    def _validate_requested_budgets(
        command: ResearchRequestCreate,
        policy: ResearchPolicyRecord,
    ) -> None:
        requested = command.requested_budgets
        maxima = {
            "max_steps": policy.max_steps,
            "max_tool_calls": policy.max_tool_calls,
            "max_calls_per_tool": policy.max_calls_per_tool,
            "max_retries_per_step": policy.max_retries_per_step,
            "max_duration_seconds": policy.max_duration_seconds,
        }
        for field, maximum in maxima.items():
            value = getattr(requested, field)
            if value is not None and value > maximum:
                raise ResearchRequestError("REQUESTED_BUDGET_EXCEEDS_POLICY")
