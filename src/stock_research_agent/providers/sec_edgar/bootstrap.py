"""Idempotent SEC Provider control-plane bootstrap composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from pydantic import model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    ProviderRepositoryConflict,
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.capabilities import (
    ProviderCapabilityRecord,
    ProviderCapabilityWrite,
)
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.policies import (
    ProviderPolicyRecord,
    ProviderPolicyWrite,
)
from stock_research_agent.domain.providers.schemas import (
    Checksum,
    FrozenProviderContract,
    ProviderDefinitionRecord,
    ProviderDefinitionWrite,
)


class SecProviderCapabilityBootstrapSpec(FrozenProviderContract):
    code: str
    capability_version: str
    status: ProviderCapabilityStatus
    data_domain: str
    market_codes: tuple[str, ...]
    security_types: tuple[str, ...]
    operations: tuple[str, ...]

    def materialize(self, provider_definition_id: UUID) -> ProviderCapabilityWrite:
        return ProviderCapabilityWrite(
            provider_definition_id=provider_definition_id,
            **self.model_dump(mode="python"),
        )


class SecProviderPolicyBootstrapSpec(FrozenProviderContract):
    policy_version: str
    endpoint_policy_version: str
    network_enabled: bool
    max_requests: int
    max_response_bytes: int
    max_total_bytes: int
    max_duration_seconds: int
    max_attempts: int
    max_redirects: int
    rate_limit_per_second: Decimal
    retry_base_delay_seconds: Decimal
    cache_enabled: bool
    cache_ttl_seconds: int | None
    retention_days: int | None

    def materialize(self, provider_definition_id: UUID) -> ProviderPolicyWrite:
        return ProviderPolicyWrite(
            provider_definition_id=provider_definition_id,
            **self.model_dump(mode="python"),
        )


class SecProviderControlPlaneBootstrapManifest(FrozenProviderContract):
    manifest_name: str
    manifest_version: str
    definition: ProviderDefinitionWrite
    capability: SecProviderCapabilityBootstrapSpec
    policy: SecProviderPolicyBootstrapSpec

    @property
    def manifest_checksum(self) -> str:
        return provider_checksum(self)

    @model_validator(mode="after")
    def validate_exact_contract(self) -> SecProviderControlPlaneBootstrapManifest:
        expected = _manifest_payload()
        if self.model_dump(mode="python") != expected:
            raise ValueError("SEC_PROVIDER_BOOTSTRAP_MANIFEST_INVALID")
        return self


class SecProviderControlPlaneBootstrapStatus(StrEnum):
    WOULD_CREATE = "WOULD_CREATE"
    CREATED = "CREATED"
    REUSED = "REUSED"
    CONFLICT = "CONFLICT"


class SecProviderControlPlaneComponentResult(FrozenProviderContract):
    component: str
    status: SecProviderControlPlaneBootstrapStatus
    record_id: UUID | None
    checksum: Checksum | None
    conflict_code: str | None = None


class SecProviderControlPlaneBootstrapResult(FrozenProviderContract):
    status: SecProviderControlPlaneBootstrapStatus
    database_name: str
    manifest_name: str
    manifest_version: str
    manifest_checksum: Checksum
    definition_id: UUID | None
    definition_checksum: Checksum | None
    capability_id: UUID | None
    capability_checksum: Checksum | None
    policy_id: UUID | None
    policy_checksum: Checksum | None
    components: tuple[SecProviderControlPlaneComponentResult, ...]


SEC_PROVIDER_BOOTSTRAP_CONFLICT_CODES = (
    "SEC_PROVIDER_BOOTSTRAP_DEFINITION_CONFLICT",
    "SEC_PROVIDER_BOOTSTRAP_CAPABILITY_CONFLICT",
    "SEC_PROVIDER_BOOTSTRAP_POLICY_CONFLICT",
    "SEC_PROVIDER_BOOTSTRAP_READBACK_MISMATCH",
    "SEC_PROVIDER_BOOTSTRAP_DATABASE_INVALID",
    "SEC_PROVIDER_BOOTSTRAP_PERSISTENCE_CONFLICT",
)


class SecProviderControlPlaneBootstrapConflict(ValueError):
    def __init__(self, code: str) -> None:
        if code not in SEC_PROVIDER_BOOTSTRAP_CONFLICT_CODES:
            raise ValueError("SEC_PROVIDER_BOOTSTRAP_CONFLICT_CODE_INVALID")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _CommittedBootstrapState:
    database_name: str
    definition: ProviderDefinitionRecord
    capability: ProviderCapabilityRecord
    policy: ProviderPolicyRecord
    definition_status: SecProviderControlPlaneBootstrapStatus
    capability_status: SecProviderControlPlaneBootstrapStatus
    policy_status: SecProviderControlPlaneBootstrapStatus
    status: SecProviderControlPlaneBootstrapStatus


def _manifest_payload() -> dict[str, object]:
    return {
        "manifest_name": "SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE",
        "manifest_version": "1.0.0",
        "definition": {
            "code": "SEC_EDGAR_PUBLIC_V1",
            "definition_version": "1.0.0",
            "adapter_version": "1.0.0",
            "display_name": "SEC EDGAR public data",
            "data_domain": "US_SEC_FILINGS",
            "definition_status": ProviderDefinitionStatus.ACTIVE,
            "production_status": ProviderProductionStatus.CONDITIONAL,
            "official_domains": ("data.sec.gov", "www.sec.gov"),
            "policy_version": "1.0.0",
            "license_policy_version": "1.0.0",
            "credential_reference_id": None,
            "source_register_version": "1.0.0",
        },
        "capability": {
            "code": "FETCH_SEC_FILING_DOCUMENTS",
            "capability_version": "1.0.0",
            "status": ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
            "data_domain": "US_SEC_FILINGS",
            "market_codes": ("US_EQUITY",),
            "security_types": ("COMMON_STOCK",),
            "operations": ("READ_LIVE_VALIDATION",),
        },
        "policy": {
            "policy_version": "1.0.0",
            "endpoint_policy_version": "1.0.0",
            "network_enabled": True,
            "max_requests": 3,
            "max_response_bytes": 20_971_520,
            "max_total_bytes": 26_214_400,
            "max_duration_seconds": 120,
            "max_attempts": 3,
            "max_redirects": 0,
            "rate_limit_per_second": Decimal("1"),
            "retry_base_delay_seconds": Decimal("1"),
            "cache_enabled": False,
            "cache_ttl_seconds": None,
            "retention_days": 30,
        },
    }


SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP = (
    SecProviderControlPlaneBootstrapManifest.model_validate(_manifest_payload())
)


class SecProviderControlPlaneBootstrapApplication:
    """Inspect or atomically materialize the exact SEC control-plane manifest."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        manifest: SecProviderControlPlaneBootstrapManifest,
    ) -> None:
        self._session_factory = session_factory
        self._manifest = manifest

    def inspect(self) -> SecProviderControlPlaneBootstrapResult:
        with self._session_factory() as session:
            database_name = self._database_name(session)
            return self._inspect_result(session, database_name)

    def bootstrap(self) -> SecProviderControlPlaneBootstrapResult:
        try:
            with self._session_factory() as session:
                with session.begin():
                    database_name = self._database_name(session)
                    self._acquire_lock(session)
                    definition_repository = SqlAlchemyProviderDefinitionRepository(session)
                    governance_repository = SqlAlchemyProviderGovernanceRepository(session)
                    existing_definition = definition_repository.get_definition(
                        self._manifest.definition.code,
                        self._manifest.definition.definition_version,
                    )
                    definition = definition_repository.add_definition(self._manifest.definition)
                    capability_write = self._manifest.capability.materialize(definition.id)
                    policy_write = self._manifest.policy.materialize(definition.id)
                    existing_capability = governance_repository.get_capability(
                        definition.id,
                        capability_write.code,
                        capability_write.capability_version,
                    )
                    existing_policy = governance_repository.get_policy(
                        definition.id,
                        policy_write.policy_version,
                    )
                    capability = governance_repository.add_capability(capability_write)
                    policy = governance_repository.add_policy(policy_write)
                    session.flush()
                    self._verify_readback(
                        definition_repository,
                        governance_repository,
                        definition.id,
                    )
                    component_statuses = tuple(
                        SecProviderControlPlaneBootstrapStatus.CREATED
                        if value is None
                        else SecProviderControlPlaneBootstrapStatus.REUSED
                        for value in (
                            existing_definition,
                            existing_capability,
                            existing_policy,
                        )
                    )
                    committed = _CommittedBootstrapState(
                        database_name=database_name,
                        definition=definition,
                        capability=capability,
                        policy=policy,
                        definition_status=component_statuses[0],
                        capability_status=component_statuses[1],
                        policy_status=component_statuses[2],
                        status=(
                            SecProviderControlPlaneBootstrapStatus.CREATED
                            if SecProviderControlPlaneBootstrapStatus.CREATED in component_statuses
                            else SecProviderControlPlaneBootstrapStatus.REUSED
                        ),
                    )
            return self._result(committed)
        except ProviderRepositoryConflict as error:
            raise SecProviderControlPlaneBootstrapConflict(
                self._translate_repository_conflict(str(error))
            ) from error
        except IntegrityError as error:
            raise SecProviderControlPlaneBootstrapConflict(
                "SEC_PROVIDER_BOOTSTRAP_PERSISTENCE_CONFLICT"
            ) from error

    def _inspect_result(
        self,
        session: Session,
        database_name: str,
    ) -> SecProviderControlPlaneBootstrapResult:
        definitions = SqlAlchemyProviderDefinitionRepository(session)
        governance = SqlAlchemyProviderGovernanceRepository(session)
        definition = definitions.get_definition(
            self._manifest.definition.code,
            self._manifest.definition.definition_version,
        )
        if definition is None:
            return self._empty_inspection(database_name)
        capability_write = self._manifest.capability.materialize(definition.id)
        policy_write = self._manifest.policy.materialize(definition.id)
        capability = governance.get_capability(
            definition.id, capability_write.code, capability_write.capability_version
        )
        policy = governance.get_policy(definition.id, policy_write.policy_version)
        expected = (
            provider_checksum(self._manifest.definition),
            provider_checksum(capability_write),
            provider_checksum(policy_write),
        )
        records = (definition, capability, policy)
        components = ("definition", "capability", "policy")
        values: list[SecProviderControlPlaneComponentResult] = []
        for component, record, checksum in zip(components, records, expected, strict=True):
            status = (
                SecProviderControlPlaneBootstrapStatus.WOULD_CREATE
                if record is None
                else SecProviderControlPlaneBootstrapStatus.REUSED
                if record.checksum == checksum
                else SecProviderControlPlaneBootstrapStatus.CONFLICT
            )
            values.append(
                SecProviderControlPlaneComponentResult(
                    component=component,
                    status=status,
                    record_id=None if record is None else record.id,
                    checksum=None if record is None else record.checksum,
                    conflict_code=(
                        self._component_conflict_code(component)
                        if status is SecProviderControlPlaneBootstrapStatus.CONFLICT
                        else None
                    ),
                )
            )
        aggregate = (
            SecProviderControlPlaneBootstrapStatus.CONFLICT
            if any(
                value.status is SecProviderControlPlaneBootstrapStatus.CONFLICT for value in values
            )
            else SecProviderControlPlaneBootstrapStatus.WOULD_CREATE
            if any(
                value.status is SecProviderControlPlaneBootstrapStatus.WOULD_CREATE
                for value in values
            )
            else SecProviderControlPlaneBootstrapStatus.REUSED
        )
        return SecProviderControlPlaneBootstrapResult(
            status=aggregate,
            database_name=database_name,
            manifest_name=self._manifest.manifest_name,
            manifest_version=self._manifest.manifest_version,
            manifest_checksum=self._manifest.manifest_checksum,
            definition_id=definition.id,
            definition_checksum=definition.checksum,
            capability_id=None if capability is None else capability.id,
            capability_checksum=None if capability is None else capability.checksum,
            policy_id=None if policy is None else policy.id,
            policy_checksum=None if policy is None else policy.checksum,
            components=tuple(values),
        )

    def _empty_inspection(self, database_name: str) -> SecProviderControlPlaneBootstrapResult:
        components = tuple(
            SecProviderControlPlaneComponentResult(
                component=name,
                status=SecProviderControlPlaneBootstrapStatus.WOULD_CREATE,
                record_id=None,
                checksum=None,
            )
            for name in ("definition", "capability", "policy")
        )
        return SecProviderControlPlaneBootstrapResult(
            status=SecProviderControlPlaneBootstrapStatus.WOULD_CREATE,
            database_name=database_name,
            manifest_name=self._manifest.manifest_name,
            manifest_version=self._manifest.manifest_version,
            manifest_checksum=self._manifest.manifest_checksum,
            definition_id=None,
            definition_checksum=None,
            capability_id=None,
            capability_checksum=None,
            policy_id=None,
            policy_checksum=None,
            components=components,
        )

    def _verify_readback(
        self,
        definitions: SqlAlchemyProviderDefinitionRepository,
        governance: SqlAlchemyProviderGovernanceRepository,
        definition_id: UUID,
    ) -> None:
        definition = definitions.get_definition(
            self._manifest.definition.code,
            self._manifest.definition.definition_version,
        )
        capability_write = self._manifest.capability.materialize(definition_id)
        policy_write = self._manifest.policy.materialize(definition_id)
        capability = governance.get_capability(
            definition_id, capability_write.code, capability_write.capability_version
        )
        policy = governance.get_policy(definition_id, policy_write.policy_version)
        if (
            definition is None
            or capability is None
            or policy is None
            or definition.checksum != provider_checksum(self._manifest.definition)
            or capability.checksum != provider_checksum(capability_write)
            or policy.checksum != provider_checksum(policy_write)
        ):
            raise SecProviderControlPlaneBootstrapConflict(
                "SEC_PROVIDER_BOOTSTRAP_READBACK_MISMATCH"
            )

    def _result(
        self,
        committed: _CommittedBootstrapState,
    ) -> SecProviderControlPlaneBootstrapResult:
        records: tuple[
            ProviderDefinitionRecord | ProviderCapabilityRecord | ProviderPolicyRecord,
            ...,
        ] = (committed.definition, committed.capability, committed.policy)
        statuses = (
            committed.definition_status,
            committed.capability_status,
            committed.policy_status,
        )
        components = tuple(
            SecProviderControlPlaneComponentResult(
                component=name,
                status=status,
                record_id=record.id,
                checksum=record.checksum,
            )
            for name, record, status in zip(
                ("definition", "capability", "policy"),
                records,
                statuses,
                strict=True,
            )
        )
        return SecProviderControlPlaneBootstrapResult(
            status=committed.status,
            database_name=committed.database_name,
            manifest_name=self._manifest.manifest_name,
            manifest_version=self._manifest.manifest_version,
            manifest_checksum=self._manifest.manifest_checksum,
            definition_id=committed.definition.id,
            definition_checksum=committed.definition.checksum,
            capability_id=committed.capability.id,
            capability_checksum=committed.capability.checksum,
            policy_id=committed.policy.id,
            policy_checksum=committed.policy.checksum,
            components=components,
        )

    @staticmethod
    def _database_name(session: Session) -> str:
        value = session.scalar(text("SELECT current_database()"))
        if not isinstance(value, str) or not value:
            raise SecProviderControlPlaneBootstrapConflict(
                "SEC_PROVIDER_BOOTSTRAP_DATABASE_INVALID"
            )
        return value

    @staticmethod
    def _acquire_lock(session: Session) -> None:
        identity = "SEC_PROVIDER_CONTROL_PLANE_BOOTSTRAP:\nSEC_EDGAR_PUBLIC_V1:\n1.0.0"
        key = int.from_bytes(sha256(identity.encode()).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    @staticmethod
    def _translate_repository_conflict(code: str) -> str:
        mapping = {
            "PROVIDER_DEFINITION_CONFLICT": "SEC_PROVIDER_BOOTSTRAP_DEFINITION_CONFLICT",
            "PROVIDER_CAPABILITY_CONFLICT": "SEC_PROVIDER_BOOTSTRAP_CAPABILITY_CONFLICT",
            "PROVIDER_POLICY_CONFLICT": "SEC_PROVIDER_BOOTSTRAP_POLICY_CONFLICT",
        }
        return mapping.get(code, "SEC_PROVIDER_BOOTSTRAP_PERSISTENCE_CONFLICT")

    @staticmethod
    def _component_conflict_code(component: str) -> str:
        return {
            "definition": "SEC_PROVIDER_BOOTSTRAP_DEFINITION_CONFLICT",
            "capability": "SEC_PROVIDER_BOOTSTRAP_CAPABILITY_CONFLICT",
            "policy": "SEC_PROVIDER_BOOTSTRAP_POLICY_CONFLICT",
        }[component]
