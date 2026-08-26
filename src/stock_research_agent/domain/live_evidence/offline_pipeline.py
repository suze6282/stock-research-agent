"""Explicit offline plans for Snapshot-bound Agent and report execution."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)
from stock_research_agent.domain.reports.release_gate import ReleaseGateDecision
from stock_research_agent.domain.reports.reporting import ResearchReportRecord
from stock_research_agent.domain.reports.versioning import (
    ReportVersionError,
    validate_report_successor,
)
from stock_research_agent.domain.research_agent.enums import ResearchType
from stock_research_agent.domain.research_agent.schemas import ResearchAgentRunRecord
from stock_research_agent.domain.research_agent.state_machine import TERMINAL_RUN_STATUSES
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot

from .exceptions import LiveEvidenceValidationError


class OfflineAgentPlanRequest(FrozenProviderContract):
    snapshot_id: UUID
    snapshot_checksum: Checksum
    snapshot_status: Literal["BUILDING", "COMPLETE", "PARTIAL", "FAILED", "SUPERSEDED"]
    security_id: UUID
    research_as_of_time: AwareUtcDateTime
    research_type: ResearchType
    policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")
    policy_checksum: Checksum
    approved_policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")
    approved_policy_checksum: Checksum
    tool_catalog_version: str = Field(min_length=1, max_length=128)
    tool_catalog_checksum: Checksum
    planner_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")


class OfflineAgentPlan(OfflineAgentPlanRequest):
    status: Literal["READY", "PARTIAL", "BLOCKED"]
    warning_codes: tuple[str, ...]
    plan_checksum: Checksum
    registry_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    registry_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    registry_checksum: Checksum
    registry_signature: Checksum


class OfflineAgentExecutionResult(FrozenProviderContract):
    run: ResearchAgentRunRecord
    package_id: UUID


class OfflineAgentExecutor(Protocol):
    def execute(self, plan: OfflineAgentPlan) -> OfflineAgentExecutionResult: ...


class OfflineReportPlanRequest(FrozenProviderContract):
    package_id: UUID
    package_checksum: Checksum
    package_status: Literal["BUILDING", "COMPLETE", "PARTIAL", "BLOCKED", "FAILED"]
    run_id: UUID
    snapshot_id: UUID
    security_id: UUID
    policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")
    policy_checksum: Checksum
    template_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")
    template_checksum: Checksum
    reflection_policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")
    reflection_policy_checksum: Checksum
    manifest_checksum: Checksum
    approved_manifest_checksum: Checksum


class OfflineReportPlan(OfflineReportPlanRequest):
    status: Literal["READY", "PARTIAL", "BLOCKED"]
    warning_codes: tuple[str, ...]
    plan_checksum: Checksum
    registry_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    registry_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    registry_checksum: Checksum
    registry_signature: Checksum


class OfflineReportExecutionResult(FrozenProviderContract):
    report_request_id: UUID
    generation_run_id: UUID
    report_id: UUID
    reflection_run_ids: tuple[UUID, UUID]
    release_gate_id: UUID
    status: Literal["COMPLETE", "PARTIAL", "BLOCKED", "FAILED"]
    package_id: UUID
    snapshot_id: UUID
    security_id: UUID


class OfflineReportExecutor(Protocol):
    def generate(self, plan: OfflineReportPlan) -> OfflineReportExecutionResult: ...


class ExistingReleaseGate(Protocol):
    def release(self, report_id: UUID, round_two_id: UUID) -> ReleaseGateDecision: ...


def release_report(
    report_id: UUID,
    round_two_id: UUID,
    *,
    gate: ExistingReleaseGate,
) -> ReleaseGateDecision:
    try:
        result = gate.release(report_id, round_two_id)
    except Exception as exc:
        raise LiveEvidenceValidationError("RELEASE_GATE_BYPASS_FORBIDDEN") from exc
    if result is not ReleaseGateDecision.PUBLISHABLE:
        raise LiveEvidenceValidationError("RELEASE_REQUIREMENT_FAILED")
    return result


class OfflineBoundaryDecision(FrozenProviderContract):
    status: Literal["PASS", "BLOCKED"]
    warning_codes: tuple[str, ...]


def validate_report_predecessor(
    predecessor: ResearchReportRecord,
    successor: ResearchReportRecord,
) -> OfflineBoundaryDecision:
    if predecessor.id == successor.id:
        raise LiveEvidenceValidationError("REPORT_HISTORY_MUTATION")
    try:
        validate_report_successor(predecessor, successor)
    except ReportVersionError as exc:
        raise LiveEvidenceValidationError("REPORT_PREDECESSOR_MISMATCH") from exc
    return OfflineBoundaryDecision(status="PASS", warning_codes=())


def validate_agent_boundary(
    catalog: ToolCatalogSnapshot,
    *,
    credential_access: bool,
    provider_sync: bool,
) -> OfflineBoundaryDecision:
    if credential_access:
        raise LiveEvidenceValidationError("AGENT_CREDENTIAL_ACCESS_FORBIDDEN")
    if provider_sync:
        raise LiveEvidenceValidationError("AGENT_PROVIDER_SYNC_FORBIDDEN")
    if any(entry.permission != "READ_ONLY" or entry.writes for entry in catalog.entries):
        raise LiveEvidenceValidationError("AGENT_TOOL_NOT_READ_ONLY")
    if any(entry.requires_network for entry in catalog.entries):
        raise LiveEvidenceValidationError("AGENT_TOOL_NETWORK_FORBIDDEN")
    return OfflineBoundaryDecision(status="PASS", warning_codes=())


class OfflinePipelineRegistry:
    def __init__(
        self,
        *,
        registry_id: str,
        registry_version: str,
        registry_checksum: str,
    ) -> None:
        if re.fullmatch(r"^[A-Z][A-Z0-9_]{2,63}$", registry_id) is None:
            raise ValueError("registry_id must be a stable code")
        if re.fullmatch(r"^\d+\.\d+\.\d+$", registry_version) is None:
            raise ValueError("registry_version must be semantic")
        if re.fullmatch(r"^[0-9a-f]{64}$", registry_checksum) is None:
            raise ValueError("registry_checksum must be sha256")
        self.registry_id = registry_id
        self.registry_version = registry_version
        self.registry_checksum = registry_checksum

    def plan_agent(self, value: OfflineAgentPlanRequest) -> OfflineAgentPlan:
        if value.snapshot_status not in {"COMPLETE", "PARTIAL"}:
            return self._seal_agent(
                value,
                "BLOCKED",
                ("AGENT_SNAPSHOT_NOT_SEALED",),
            )
        if (
            value.policy_version != value.approved_policy_version
            or value.policy_checksum != value.approved_policy_checksum
        ):
            return self._seal_agent(value, "BLOCKED", ("AGENT_POLICY_MISMATCH",))
        if value.snapshot_status == "PARTIAL":
            return self._seal_agent(value, "PARTIAL", ("AGENT_SNAPSHOT_PARTIAL",))
        return self._seal_agent(value, "READY", ())

    def run_agent(
        self,
        plan: OfflineAgentPlan,
        *,
        executor: OfflineAgentExecutor,
    ) -> OfflineAgentExecutionResult:
        request = OfflineAgentPlanRequest.model_validate(
            plan.model_dump(
                exclude={
                    "status",
                    "warning_codes",
                    "plan_checksum",
                    "registry_id",
                    "registry_version",
                    "registry_checksum",
                    "registry_signature",
                }
            )
        )
        expected = self.plan_agent(request)
        if (
            plan.status == "BLOCKED"
            or plan.plan_checksum != expected.plan_checksum
            or plan.registry_signature != expected.registry_signature
            or plan.registry_id != self.registry_id
            or plan.registry_version != self.registry_version
            or plan.registry_checksum != self.registry_checksum
        ):
            raise LiveEvidenceValidationError("AGENT_PLAN_CHECKSUM_MISMATCH")

        try:
            result = executor.execute(plan)
        except Exception as exc:
            raise LiveEvidenceValidationError("AGENT_EXECUTION_BLOCKED") from exc
        if (
            result.run.status not in TERMINAL_RUN_STATUSES
            or result.run.snapshot_id != plan.snapshot_id
            or result.run.security_id != plan.security_id
            or result.run.research_as_of_time != plan.research_as_of_time
            or result.run.policy_version != plan.policy_version
            or result.run.planner_version != plan.planner_version
            or result.run.tool_catalog_version != plan.tool_catalog_version
            or result.run.tool_catalog_checksum != plan.tool_catalog_checksum
        ):
            raise LiveEvidenceValidationError("AGENT_EXECUTION_BLOCKED")
        return result

    def plan_report(self, value: OfflineReportPlanRequest) -> OfflineReportPlan:
        if value.package_status not in {"COMPLETE", "PARTIAL"}:
            return self._seal_report(value, "BLOCKED", ("REPORT_PACKAGE_NOT_SEALED",))
        if value.manifest_checksum != value.approved_manifest_checksum:
            return self._seal_report(value, "BLOCKED", ("REPORT_MANIFEST_INVALID",))
        if value.package_status == "PARTIAL":
            return self._seal_report(value, "PARTIAL", ("REPORT_PACKAGE_PARTIAL",))
        return self._seal_report(value, "READY", ())

    def generate_report(
        self,
        plan: OfflineReportPlan,
        *,
        executor: OfflineReportExecutor,
    ) -> OfflineReportExecutionResult:
        request = OfflineReportPlanRequest.model_validate(
            plan.model_dump(
                exclude={
                    "status",
                    "warning_codes",
                    "plan_checksum",
                    "registry_id",
                    "registry_version",
                    "registry_checksum",
                    "registry_signature",
                }
            )
        )
        expected = self.plan_report(request)
        if (
            plan.status == "BLOCKED"
            or plan.plan_checksum != expected.plan_checksum
            or plan.registry_signature != expected.registry_signature
            or plan.registry_id != self.registry_id
            or plan.registry_version != self.registry_version
            or plan.registry_checksum != self.registry_checksum
        ):
            raise LiveEvidenceValidationError("REPORT_PLAN_CHECKSUM_MISMATCH")
        try:
            result = executor.generate(plan)
        except Exception as exc:
            raise LiveEvidenceValidationError("REPORT_PIPELINE_BLOCKED") from exc
        if (
            result.package_id != plan.package_id
            or result.snapshot_id != plan.snapshot_id
            or result.security_id != plan.security_id
        ):
            raise LiveEvidenceValidationError("REPORT_PIPELINE_BLOCKED")
        return result

    def _seal_agent(
        self,
        value: OfflineAgentPlanRequest,
        status: Literal["READY", "PARTIAL", "BLOCKED"],
        warning_codes: tuple[str, ...],
    ) -> OfflineAgentPlan:
        payload = {
            **value.model_dump(mode="json"),
            "status": status,
            "warning_codes": warning_codes,
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "registry_checksum": self.registry_checksum,
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        checksum = hashlib.sha256(canonical.encode("ascii")).hexdigest()
        signature = hashlib.sha256(
            f"{self.registry_checksum}:{checksum}".encode("ascii")
        ).hexdigest()
        return OfflineAgentPlan(
            **value.model_dump(),
            status=status,
            warning_codes=warning_codes,
            plan_checksum=checksum,
            registry_id=self.registry_id,
            registry_version=self.registry_version,
            registry_checksum=self.registry_checksum,
            registry_signature=signature,
        )

    def _seal_report(
        self,
        value: OfflineReportPlanRequest,
        status: Literal["READY", "PARTIAL", "BLOCKED"],
        warning_codes: tuple[str, ...],
    ) -> OfflineReportPlan:
        payload = {
            **value.model_dump(mode="json"),
            "status": status,
            "warning_codes": warning_codes,
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "registry_checksum": self.registry_checksum,
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        checksum = hashlib.sha256(canonical.encode("ascii")).hexdigest()
        signature = hashlib.sha256(
            f"{self.registry_checksum}:{checksum}".encode("ascii")
        ).hexdigest()
        return OfflineReportPlan(
            **value.model_dump(),
            status=status,
            warning_codes=warning_codes,
            plan_checksum=checksum,
            registry_id=self.registry_id,
            registry_version=self.registry_version,
            registry_checksum=self.registry_checksum,
            registry_signature=signature,
        )
