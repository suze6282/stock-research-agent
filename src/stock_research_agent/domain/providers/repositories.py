from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from stock_research_agent.domain.providers.artifacts import (
    ProviderDataQualityIssueRecord,
    ProviderDataQualityIssueWrite,
    ProviderDeadLetterRecord,
    ProviderDeadLetterWrite,
    ProviderIngestionManifestRecord,
    ProviderIngestionManifestWrite,
    ProviderRawArtifactRecord,
    ProviderRawArtifactWrite,
)
from stock_research_agent.domain.providers.capabilities import (
    ProviderCapabilityRecord,
    ProviderCapabilityWrite,
)
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialReferenceWrite,
)
from stock_research_agent.domain.providers.health import (
    ProviderHealthSnapshotRecord,
    ProviderHealthSnapshotWrite,
)
from stock_research_agent.domain.providers.licenses import (
    SourceLicensePolicyRecord,
    SourceLicensePolicyWrite,
)
from stock_research_agent.domain.providers.policies import (
    ProviderPolicyRecord,
    ProviderPolicyWrite,
)
from stock_research_agent.domain.providers.schemas import (
    ProviderDefinitionRecord,
    ProviderDefinitionWrite,
)
from stock_research_agent.domain.providers.sync import (
    CheckpointAdvance,
    CheckpointScope,
    ProviderCheckpointRecord,
    ProviderRequestAttemptRecord,
    ProviderRequestAttemptWrite,
    ProviderRunTransition,
    ProviderSyncPlanRecord,
    ProviderSyncPlanWrite,
    ProviderSyncRequestRecord,
    ProviderSyncRequestWrite,
    ProviderSyncRunRecord,
    ProviderSyncRunWrite,
)


@runtime_checkable
class ProviderDefinitionRepository(Protocol):
    def add_definition(
        self,
        value: ProviderDefinitionWrite,
    ) -> ProviderDefinitionRecord: ...

    def get_definition(
        self,
        code: str,
        version: str,
    ) -> ProviderDefinitionRecord | None: ...

    def list_definitions(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[ProviderDefinitionRecord, ...]: ...


@runtime_checkable
class ProviderGovernanceRepository(Protocol):
    def add_capability(
        self,
        value: ProviderCapabilityWrite,
    ) -> ProviderCapabilityRecord: ...

    def add_policy(self, value: ProviderPolicyWrite) -> ProviderPolicyRecord: ...

    def add_license_policy(
        self,
        value: SourceLicensePolicyWrite,
    ) -> SourceLicensePolicyRecord: ...

    def add_credential_reference(
        self,
        value: CredentialReferenceWrite,
    ) -> CredentialReferenceRecord: ...

    def add_health_snapshot(
        self,
        value: ProviderHealthSnapshotWrite,
    ) -> ProviderHealthSnapshotRecord: ...

    def get_capability(
        self,
        provider_id: UUID,
        code: str,
        version: str,
    ) -> ProviderCapabilityRecord | None: ...

    def get_policy(
        self,
        provider_id: UUID,
        version: str,
    ) -> ProviderPolicyRecord | None: ...

    def get_license_policy(
        self,
        provider_id: UUID,
        version: str,
    ) -> SourceLicensePolicyRecord | None: ...

    def get_credential_reference(
        self,
        reference_id: UUID,
    ) -> CredentialReferenceRecord | None: ...

    def get_latest_health_snapshot(
        self,
        provider_id: UUID,
    ) -> ProviderHealthSnapshotRecord | None: ...


@runtime_checkable
class ProviderSyncRepository(Protocol):
    def create_request(
        self,
        value: ProviderSyncRequestWrite,
    ) -> ProviderSyncRequestRecord: ...

    def add_plan(self, value: ProviderSyncPlanWrite) -> ProviderSyncPlanRecord: ...

    def create_run(self, value: ProviderSyncRunWrite) -> ProviderSyncRunRecord: ...

    def get_run(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> ProviderSyncRunRecord | None: ...

    def transition(
        self,
        run_id: UUID,
        value: ProviderRunTransition,
    ) -> ProviderSyncRunRecord: ...

    def append_attempt(
        self,
        value: ProviderRequestAttemptWrite,
    ) -> ProviderRequestAttemptRecord: ...

    def compare_and_swap_checkpoint(
        self,
        value: CheckpointAdvance,
    ) -> ProviderCheckpointRecord: ...

    def get_checkpoint(
        self,
        scope: CheckpointScope,
    ) -> ProviderCheckpointRecord | None: ...


@runtime_checkable
class ProviderArtifactRepository(Protocol):
    def add_artifact(
        self,
        value: ProviderRawArtifactWrite,
    ) -> ProviderRawArtifactRecord: ...

    def add_manifest(
        self,
        value: ProviderIngestionManifestWrite,
    ) -> ProviderIngestionManifestRecord: ...

    def add_quality_issue(
        self,
        value: ProviderDataQualityIssueWrite,
    ) -> ProviderDataQualityIssueRecord: ...

    def add_dead_letter(
        self,
        value: ProviderDeadLetterWrite,
    ) -> ProviderDeadLetterRecord: ...


@runtime_checkable
class ProviderQueryRepository(Protocol):
    def list_provider_views(self, *, limit: int, offset: int) -> tuple[object, ...]: ...

    def get_provider_view(self, provider_code: str) -> object | None: ...

    def list_capability_views(
        self,
        provider_code: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[object, ...]: ...

    def get_health_view(self, provider_code: str) -> object | None: ...

    def get_license_view(self, provider_code: str) -> object | None: ...

    def get_sync_run_view(self, run_id: UUID) -> object | None: ...

    def list_attempt_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[object, ...]: ...

    def list_artifact_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[object, ...]: ...

    def list_quality_issue_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[object, ...]: ...

    def list_dead_letter_views(
        self,
        run_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[object, ...]: ...

    def get_readiness_view(self, security_id: UUID) -> object: ...
