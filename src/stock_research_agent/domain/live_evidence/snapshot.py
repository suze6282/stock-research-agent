"""Immutable bindings between governed evidence manifests and data snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from stock_research_agent.domain.data_access.snapshots import (
    SnapshotBuilder,
    SnapshotBuildRequest,
    SnapshotBuildResult,
)
from stock_research_agent.domain.live_evidence.enums import EvidenceSourceType
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)


class IngestionSnapshotBindingWrite(FrozenProviderContract):
    manifest_id: UUID
    manifest_checksum: Checksum
    manifest_security_id: UUID
    snapshot_id: UUID
    snapshot_checksum: Checksum
    snapshot_security_id: UUID
    security_id: UUID
    research_as_of_time: AwareUtcDateTime
    source_published_at: AwareUtcDateTime | None
    bound_at: AwareUtcDateTime


class IngestionSnapshotBindingRecord(IngestionSnapshotBindingWrite):
    id: UUID
    binding_checksum: Checksum


class SnapshotImmutabilityDecision(FrozenProviderContract):
    status: Literal["PASS", "BLOCKED"]
    warning_codes: tuple[str, ...]


def bind_manifest_to_snapshot(
    value: IngestionSnapshotBindingWrite,
    *,
    existing: IngestionSnapshotBindingRecord | None = None,
) -> IngestionSnapshotBindingRecord:
    if (
        value.security_id != value.manifest_security_id
        or value.security_id != value.snapshot_security_id
        or (
            value.source_published_at is not None
            and value.source_published_at > value.research_as_of_time
        )
    ):
        raise LiveEvidenceValidationError("SNAPSHOT_BINDING_SCOPE_MISMATCH")

    checksum = _binding_checksum(value)
    if existing is not None:
        if existing.binding_checksum == checksum:
            raise LiveEvidenceValidationError("SNAPSHOT_BINDING_DUPLICATE")
        raise LiveEvidenceValidationError("SNAPSHOT_BINDING_SCOPE_MISMATCH")

    return IngestionSnapshotBindingRecord(
        **value.model_dump(),
        id=uuid4(),
        binding_checksum=checksum,
    )


def verify_snapshot_immutability(
    snapshot_id: UUID,
    *,
    snapshot_status: str,
    binding: IngestionSnapshotBindingRecord | None,
    expected_binding_checksum: Checksum,
) -> SnapshotImmutabilityDecision:
    if snapshot_status not in {"COMPLETE", "PARTIAL", "SUPERSEDED"}:
        return SnapshotImmutabilityDecision(
            status="BLOCKED",
            warning_codes=("SNAPSHOT_IMMUTABLE",),
        )
    if (
        binding is None
        or binding.snapshot_id != snapshot_id
        or binding.binding_checksum != expected_binding_checksum
    ):
        return SnapshotImmutabilityDecision(
            status="BLOCKED",
            warning_codes=("SNAPSHOT_BINDING_IMMUTABLE",),
        )
    return SnapshotImmutabilityDecision(status="PASS", warning_codes=())


def _binding_checksum(value: IngestionSnapshotBindingWrite) -> str:
    canonical = json.dumps(
        value.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


class SnapshotManifestReference(FrozenProviderContract):
    manifest_id: UUID
    manifest_checksum: Checksum
    approved: bool
    license_allowed: bool


class SnapshotTemporalEvidence(FrozenProviderContract):
    evidence_id: UUID
    scope_as_of_time: AwareUtcDateTime
    published_at: AwareUtcDateTime | None
    filed_at: AwareUtcDateTime | None
    fact_available_at: AwareUtcDateTime | None
    imported_at: AwareUtcDateTime
    requires_publication_time: bool


class TemporalDecision(FrozenProviderContract):
    status: Literal["PASS", "BLOCKED"]
    warning_codes: tuple[str, ...]


class SnapshotScopeEvidence(FrozenProviderContract):
    evidence_id: UUID
    evidence_kind: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    security_id: UUID
    issuer_id: UUID


class ScopeDecision(FrozenProviderContract):
    status: Literal["PASS", "BLOCKED"]
    warning_codes: tuple[str, ...]


class SnapshotSyntheticEvidence(FrozenProviderContract):
    evidence_id: UUID
    source_type: EvidenceSourceType
    synthetic_status: ProviderSyntheticStatus
    company_evidence_status: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    security_is_neutral_synthetic: bool
    offline: bool
    not_live: bool


class SnapshotFromIngestionPlanRequest(FrozenProviderContract):
    security_id: UUID
    issuer_id: UUID
    research_as_of_time: AwareUtcDateTime
    manifests: tuple[SnapshotManifestReference, ...] = Field(min_length=1, max_length=128)
    document_version_ids: tuple[UUID, ...] = Field(max_length=512)
    financial_fact_ids: tuple[UUID, ...] = Field(max_length=4096)
    mapping_version_ids: tuple[UUID, ...] = Field(max_length=512)
    formula_version_ids: tuple[UUID, ...] = Field(max_length=512)
    required_input_kinds: tuple[str, ...] = Field(min_length=1, max_length=16)
    available_input_kinds: tuple[str, ...] = Field(max_length=16)
    temporal_evidence: tuple[SnapshotTemporalEvidence, ...] = Field(default=(), max_length=4096)
    scope_evidence: tuple[SnapshotScopeEvidence, ...] = Field(default=(), max_length=4096)
    synthetic_evidence: tuple[SnapshotSyntheticEvidence, ...] = Field(default=(), max_length=4096)
    execution_mode: Literal["REAL_COMPANY", "TEST_ONLY"] = "REAL_COMPANY"
    strict_publication: bool = True
    planner_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")

    @field_validator("manifests")
    @classmethod
    def validate_manifests(
        cls, value: tuple[SnapshotManifestReference, ...]
    ) -> tuple[SnapshotManifestReference, ...]:
        identities = tuple(item.manifest_id for item in value)
        if identities != tuple(sorted(set(identities), key=str)):
            raise ValueError("manifests must have unique sorted IDs")
        return value

    @field_validator(
        "document_version_ids",
        "financial_fact_ids",
        "mapping_version_ids",
        "formula_version_ids",
    )
    @classmethod
    def validate_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("IDs must be unique and sorted")
        return value

    @field_validator("required_input_kinds", "available_input_kinds")
    @classmethod
    def validate_input_kinds(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))) or any(
            re.fullmatch(r"^[A-Z][A-Z0-9_]{2,63}$", item) is None for item in value
        ):
            raise ValueError("input kinds must be unique sorted stable codes")
        return value

    @field_validator("temporal_evidence")
    @classmethod
    def validate_temporal_evidence(
        cls, value: tuple[SnapshotTemporalEvidence, ...]
    ) -> tuple[SnapshotTemporalEvidence, ...]:
        identities = tuple(item.evidence_id for item in value)
        if identities != tuple(sorted(set(identities), key=str)):
            raise ValueError("temporal evidence IDs must be unique and sorted")
        return value

    @field_validator("scope_evidence")
    @classmethod
    def validate_scope_evidence(
        cls, value: tuple[SnapshotScopeEvidence, ...]
    ) -> tuple[SnapshotScopeEvidence, ...]:
        identities = tuple(item.evidence_id for item in value)
        if identities != tuple(sorted(set(identities), key=str)):
            raise ValueError("scope evidence IDs must be unique and sorted")
        return value

    @field_validator("synthetic_evidence")
    @classmethod
    def validate_synthetic_evidence(
        cls, value: tuple[SnapshotSyntheticEvidence, ...]
    ) -> tuple[SnapshotSyntheticEvidence, ...]:
        identities = tuple(item.evidence_id for item in value)
        if identities != tuple(sorted(set(identities), key=str)):
            raise ValueError("synthetic evidence IDs must be unique and sorted")
        return value


class SnapshotFromIngestionPlan(SnapshotFromIngestionPlanRequest):
    status: Literal["READY", "PARTIAL", "BLOCKED"]
    warning_codes: tuple[str, ...]
    plan_checksum: Checksum
    registry_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    registry_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    registry_checksum: Checksum
    registry_signature: Checksum


class SnapshotFromIngestionResult(FrozenProviderContract):
    snapshot: SnapshotBuildResult
    bindings: tuple[IngestionSnapshotBindingRecord, ...]
    status: Literal["COMPLETE", "PARTIAL"]
    plan_checksum: Checksum


def validate_temporal_scope(plan: SnapshotFromIngestionPlanRequest) -> TemporalDecision:
    if any(item.scope_as_of_time != plan.research_as_of_time for item in plan.temporal_evidence):
        return TemporalDecision(status="BLOCKED", warning_codes=("AS_OF_MISMATCH",))
    if plan.strict_publication and any(
        item.requires_publication_time and item.published_at is None
        for item in plan.temporal_evidence
    ):
        return TemporalDecision(
            status="BLOCKED",
            warning_codes=("SOURCE_PUBLISHED_AT_UNKNOWN_STRICT",),
        )
    if any(
        timestamp is not None and timestamp > plan.research_as_of_time
        for item in plan.temporal_evidence
        for timestamp in (item.published_at, item.filed_at, item.fact_available_at)
    ):
        return TemporalDecision(status="BLOCKED", warning_codes=("FUTURE_DATA",))
    return TemporalDecision(status="PASS", warning_codes=())


def validate_security_scope(plan: SnapshotFromIngestionPlanRequest) -> ScopeDecision:
    if any(item.security_id != plan.security_id for item in plan.scope_evidence):
        return ScopeDecision(
            status="BLOCKED",
            warning_codes=("SNAPSHOT_SECURITY_MISMATCH",),
        )
    if any(item.issuer_id != plan.issuer_id for item in plan.scope_evidence):
        return ScopeDecision(
            status="BLOCKED",
            warning_codes=("SNAPSHOT_ISSUER_MISMATCH",),
        )
    return ScopeDecision(status="PASS", warning_codes=())


def validate_synthetic_scope(plan: SnapshotFromIngestionPlanRequest) -> ScopeDecision:
    fixture_present = any(
        item.source_type is EvidenceSourceType.OFFLINE_FIXTURE
        or item.synthetic_status is ProviderSyntheticStatus.FIXTURE_REAL_EXCERPT
        for item in plan.synthetic_evidence
    )
    if fixture_present:
        return ScopeDecision(
            status="BLOCKED",
            warning_codes=("FIXTURE_COMPANY_EVIDENCE_FORBIDDEN",),
        )

    synthetic_present = any(
        item.source_type is EvidenceSourceType.SYNTHETIC_TEST
        or item.synthetic_status is ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY
        for item in plan.synthetic_evidence
    )
    if plan.execution_mode == "REAL_COMPANY" and synthetic_present:
        return ScopeDecision(
            status="BLOCKED",
            warning_codes=("SYNTHETIC_COMPANY_EVIDENCE_FORBIDDEN",),
        )
    if plan.execution_mode == "TEST_ONLY" and any(
        item.source_type is not EvidenceSourceType.SYNTHETIC_TEST
        or item.synthetic_status is not ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY
        or item.company_evidence_status != "NOT_COMPANY_EVIDENCE"
        or not item.security_is_neutral_synthetic
        or not item.offline
        or not item.not_live
        for item in plan.synthetic_evidence
    ):
        return ScopeDecision(
            status="BLOCKED",
            warning_codes=("SYNTHETIC_COMPANY_EVIDENCE_FORBIDDEN",),
        )
    return ScopeDecision(status="PASS", warning_codes=())


class SnapshotPlanRegistry:
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

    def plan(self, value: SnapshotFromIngestionPlanRequest) -> SnapshotFromIngestionPlan:
        if any(not item.approved for item in value.manifests):
            return self._seal(value, "BLOCKED", ("SNAPSHOT_MANIFEST_NOT_APPROVED",))
        if any(not item.license_allowed for item in value.manifests):
            return self._seal(value, "BLOCKED", ("SNAPSHOT_LICENSE_BLOCKED",))
        temporal = validate_temporal_scope(value)
        if temporal.status == "BLOCKED":
            return self._seal(value, "BLOCKED", temporal.warning_codes)
        scope = validate_security_scope(value)
        if scope.status == "BLOCKED":
            return self._seal(value, "BLOCKED", scope.warning_codes)
        synthetic = validate_synthetic_scope(value)
        if synthetic.status == "BLOCKED":
            return self._seal(value, "BLOCKED", synthetic.warning_codes)

        missing = set(value.required_input_kinds) - set(value.available_input_kinds)
        if missing:
            status: Literal["PARTIAL", "BLOCKED"] = (
                "PARTIAL" if value.available_input_kinds else "BLOCKED"
            )
            return self._seal(value, status, ("SNAPSHOT_INPUT_INCOMPLETE",))
        return self._seal(value, "READY", ())

    def create(
        self,
        plan: SnapshotFromIngestionPlan,
        *,
        build_request: SnapshotBuildRequest,
        builder: SnapshotBuilder,
    ) -> SnapshotFromIngestionResult:
        expected = self.plan(
            SnapshotFromIngestionPlanRequest.model_validate(
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
        )
        if (
            plan.status == "BLOCKED"
            or plan.plan_checksum != expected.plan_checksum
            or plan.registry_signature != expected.registry_signature
            or plan.registry_id != self.registry_id
            or plan.registry_version != self.registry_version
            or plan.registry_checksum != self.registry_checksum
            or build_request.security_id != plan.security_id
            or build_request.research_as_of_time != plan.research_as_of_time
        ):
            raise LiveEvidenceValidationError("SNAPSHOT_PLAN_CHECKSUM_MISMATCH")

        try:
            result = builder.build(build_request)
            completed_at = result.snapshot.completed_at
            if completed_at is None:
                raise ValueError("terminal snapshot is missing completed_at")
            bindings = tuple(
                bind_manifest_to_snapshot(
                    IngestionSnapshotBindingWrite(
                        manifest_id=manifest.manifest_id,
                        manifest_checksum=manifest.manifest_checksum,
                        manifest_security_id=plan.security_id,
                        snapshot_id=result.snapshot.id,
                        snapshot_checksum=result.checksum,
                        snapshot_security_id=result.snapshot.security_id,
                        security_id=plan.security_id,
                        research_as_of_time=plan.research_as_of_time,
                        source_published_at=None,
                        bound_at=completed_at,
                    )
                )
                for manifest in plan.manifests
            )
        except LiveEvidenceValidationError:
            raise
        except Exception as exc:
            raise LiveEvidenceValidationError("SNAPSHOT_PERSISTENCE_FAILED") from exc

        status: Literal["COMPLETE", "PARTIAL"] = (
            "PARTIAL" if plan.status == "PARTIAL" or result.status == "PARTIAL" else "COMPLETE"
        )
        return SnapshotFromIngestionResult(
            snapshot=result,
            bindings=bindings,
            status=status,
            plan_checksum=plan.plan_checksum,
        )

    def _seal(
        self,
        value: SnapshotFromIngestionPlanRequest,
        status: Literal["READY", "PARTIAL", "BLOCKED"],
        warning_codes: tuple[str, ...],
    ) -> SnapshotFromIngestionPlan:
        payload = {
            **value.model_dump(mode="json"),
            "status": status,
            "warning_codes": warning_codes,
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "registry_checksum": self.registry_checksum,
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        plan_checksum = hashlib.sha256(canonical.encode("ascii")).hexdigest()
        signature = hashlib.sha256(
            f"{self.registry_checksum}:{plan_checksum}".encode("ascii")
        ).hexdigest()
        return SnapshotFromIngestionPlan(
            **value.model_dump(),
            status=status,
            warning_codes=warning_codes,
            plan_checksum=plan_checksum,
            registry_id=self.registry_id,
            registry_version=self.registry_version,
            registry_checksum=self.registry_checksum,
            registry_signature=signature,
        )
