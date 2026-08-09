"""Verified Provider security-master bridge with no issuer guessing."""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderIngestionManifestRecord,
    ProviderRecordStatus,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
    ProviderCode,
)
from stock_research_agent.domain.securities.enums import SecurityAliasType
from stock_research_agent.domain.securities.normalization import (
    normalize_company_name,
    normalize_external_identifier,
    normalize_symbol,
)


class SecurityMasterBinding(FrozenProviderContract):
    security_id: UUID
    issuer_id: UUID
    market_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,31}$")
    exchange_mic: str = Field(pattern=r"^[A-Z0-9]{4}$")


class SecurityIdentifierAppend(FrozenProviderContract):
    security_id: UUID
    scheme: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    value: str = Field(min_length=1, max_length=256)
    normalized_value: str = Field(min_length=1, max_length=256)
    source_name: str = Field(min_length=1, max_length=256)
    valid_from: date | None = None
    valid_to: date | None = None
    is_primary: bool = False


class SecurityAliasAppend(FrozenProviderContract):
    security_id: UUID
    alias: str = Field(min_length=1, max_length=256)
    normalized_alias: str = Field(min_length=1, max_length=256)
    alias_type: SecurityAliasType
    locale: str | None = Field(default=None, max_length=32)
    source_name: str = Field(min_length=1, max_length=256)
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool = True


class SecurityMasterBridgeContext(FrozenProviderContract):
    provider_code: ProviderCode
    research_as_of_time: AwareUtcDateTime
    derived_use_approved: bool


class SecurityMasterBridgeResult(FrozenProviderContract):
    security_ids: tuple[UUID, ...]
    appended_identifier_count: int = Field(ge=0)
    appended_alias_count: int = Field(ge=0)
    existing_record_count: int = Field(ge=0)
    manifest_id: UUID
    manifest_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class SecurityMasterBridgeRepository(Protocol):
    def get_security_binding(self, security_id: UUID) -> SecurityMasterBinding | None: ...

    def find_identifier_owner(self, scheme: str, normalized_value: str) -> UUID | None: ...

    def find_alias_owners(
        self,
        alias_type: SecurityAliasType,
        normalized_alias: str,
    ) -> tuple[UUID, ...]: ...

    def append_identifier(self, value: SecurityIdentifierAppend) -> UUID: ...

    def append_alias(self, value: SecurityAliasAppend) -> UUID: ...


class SecurityMasterProviderBridge:
    """Append verified identities through a caller-owned repository transaction."""

    def __init__(self, repository: SecurityMasterBridgeRepository) -> None:
        self._repository = repository

    def stage(
        self,
        manifest: ProviderIngestionManifestRecord,
        batch: ProviderBatch,
        context: SecurityMasterBridgeContext,
    ) -> SecurityMasterBridgeResult:
        if not context.derived_use_approved:
            raise ValueError("DERIVED_USE_NOT_APPROVED")
        if manifest.manifest_checksum != batch.manifest_checksum:
            raise ValueError("SECURITY_MASTER_MANIFEST_MISMATCH")
        if manifest.batch_checksum != batch.batch_checksum:
            raise ValueError("SECURITY_MASTER_BATCH_CHECKSUM_MISMATCH")
        if manifest.record_count != batch.record_count:
            raise ValueError("SECURITY_MASTER_RECORD_COUNT_MISMATCH")
        if (
            manifest.source_published_at is not None
            and manifest.source_published_at > context.research_as_of_time
        ):
            raise ValueError("SECURITY_MASTER_FUTURE_DATA")
        if manifest.synthetic_status in {
            ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
            ProviderSyntheticStatus.UNKNOWN,
        }:
            raise ValueError("SYNTHETIC_SECURITY_MASTER_WRITE_FORBIDDEN")

        identifiers: list[SecurityIdentifierAppend] = []
        aliases: list[SecurityAliasAppend] = []
        existing_count = 0
        security_ids: set[UUID] = set()
        planned_identifiers: dict[tuple[str, str], UUID] = {}
        planned_aliases: dict[tuple[SecurityAliasType, str], UUID] = {}
        source_name = f"{context.provider_code}:manifest:{manifest.id}"

        for record in batch.records:
            if record.raw_artifact_id != manifest.raw_artifact_id:
                raise ValueError("SECURITY_MASTER_RAW_ARTIFACT_MISMATCH")
            if record.synthetic_status is not manifest.synthetic_status:
                raise ValueError("SECURITY_MASTER_SYNTHETIC_STATUS_MISMATCH")
            if record.source_published_at is not None and (
                record.source_published_at > context.research_as_of_time
            ):
                raise ValueError("SECURITY_MASTER_FUTURE_DATA")
            if record.status is ProviderRecordStatus.MISSING:
                raise ValueError("SECURITY_MASTER_RECORD_NOT_VERIFIED")
            values = record.text_values
            if values.get("verification_status") != "VERIFIED":
                raise ValueError("SECURITY_MASTER_RECORD_NOT_VERIFIED")
            security_id = _uuid_value(values.get("security_id"))
            binding = self._repository.get_security_binding(security_id)
            if binding is None:
                raise ValueError("SECURITY_MAPPING_NOT_FOUND")
            if values.get("market_code") != binding.market_code:
                raise ValueError("SECURITY_MARKET_MISMATCH")
            if values.get("exchange_mic") != binding.exchange_mic:
                raise ValueError("SECURITY_EXCHANGE_MISMATCH")
            security_ids.add(security_id)

            identifier, identifier_existing = self._stage_identifier(
                values,
                security_id=security_id,
                source_name=source_name,
                planned=planned_identifiers,
            )
            if identifier is not None:
                identifiers.append(identifier)
            existing_count += identifier_existing

            alias, alias_existing = self._stage_alias(
                values,
                security_id=security_id,
                source_name=source_name,
                planned=planned_aliases,
            )
            if alias is not None:
                aliases.append(alias)
            existing_count += alias_existing

        for identifier in identifiers:
            self._repository.append_identifier(identifier)
        for alias in aliases:
            self._repository.append_alias(alias)
        return SecurityMasterBridgeResult(
            security_ids=tuple(sorted(security_ids, key=str)),
            appended_identifier_count=len(identifiers),
            appended_alias_count=len(aliases),
            existing_record_count=existing_count,
            manifest_id=manifest.id,
            manifest_checksum=manifest.manifest_checksum,
        )

    def _stage_identifier(
        self,
        values: dict[str, str | None],
        *,
        security_id: UUID,
        source_name: str,
        planned: dict[tuple[str, str], UUID],
    ) -> tuple[SecurityIdentifierAppend | None, int]:
        scheme = values.get("identifier_scheme")
        value = values.get("identifier_value")
        if scheme is None and value is None:
            return None, 0
        if scheme is None or value is None:
            raise ValueError("SECURITY_IDENTIFIER_INCOMPLETE")
        normalized = normalize_external_identifier(scheme, value)
        key = (scheme, normalized)
        owner = self._repository.find_identifier_owner(*key)
        planned_owner = planned.get(key)
        if owner not in {None, security_id} or planned_owner not in {None, security_id}:
            raise ValueError("SECURITY_IDENTIFIER_CONFLICT")
        if owner == security_id or planned_owner == security_id:
            return None, 1
        planned[key] = security_id
        return (
            SecurityIdentifierAppend(
                security_id=security_id,
                scheme=scheme,
                value=value,
                normalized_value=normalized,
                source_name=source_name,
            ),
            0,
        )

    def _stage_alias(
        self,
        values: dict[str, str | None],
        *,
        security_id: UUID,
        source_name: str,
        planned: dict[tuple[SecurityAliasType, str], UUID],
    ) -> tuple[SecurityAliasAppend | None, int]:
        alias = values.get("alias")
        alias_type_value = values.get("alias_type")
        if alias is None and alias_type_value is None:
            return None, 0
        if alias is None or alias_type_value is None:
            raise ValueError("SECURITY_ALIAS_INCOMPLETE")
        try:
            alias_type = SecurityAliasType(alias_type_value)
        except ValueError:
            raise ValueError("SECURITY_ALIAS_TYPE_INVALID") from None
        normalized = (
            normalize_symbol(alias)
            if alias_type
            in {
                SecurityAliasType.SYMBOL,
                SecurityAliasType.SYMBOL_WITH_EXCHANGE,
                SecurityAliasType.PROVIDER_SYMBOL,
            }
            else normalize_company_name(alias)
        )
        key = (alias_type, normalized)
        owners = self._repository.find_alias_owners(*key)
        planned_owner = planned.get(key)
        if alias_type is SecurityAliasType.PROVIDER_SYMBOL and (
            any(owner != security_id for owner in owners)
            or planned_owner not in {None, security_id}
        ):
            raise ValueError("SECURITY_ALIAS_CONFLICT")
        if security_id in owners or planned_owner == security_id:
            return None, 1
        planned[key] = security_id
        return (
            SecurityAliasAppend(
                security_id=security_id,
                alias=alias,
                normalized_alias=normalized,
                alias_type=alias_type,
                locale=values.get("locale"),
                source_name=source_name,
            ),
            0,
        )


def _uuid_value(value: str | None) -> UUID:
    if value is None:
        raise ValueError("SECURITY_MAPPING_NOT_FOUND")
    try:
        return UUID(value)
    except ValueError:
        raise ValueError("SECURITY_MAPPING_NOT_FOUND") from None


__all__ = [
    "SecurityAliasAppend",
    "SecurityIdentifierAppend",
    "SecurityMasterBinding",
    "SecurityMasterBridgeContext",
    "SecurityMasterBridgeRepository",
    "SecurityMasterBridgeResult",
    "SecurityMasterProviderBridge",
]
