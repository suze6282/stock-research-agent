"""Canonical, secret-free identity for one Gate B SEC sync request."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
)
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderSyncRequestWrite,
)
from stock_research_agent.providers.sec_edgar.schemas import (
    AccessionNumber,
    Cik,
    SecForm,
)

GATE_B_SYNC_REQUEST_CONTRACT_VERSION = "1.0.0"
GATE_B_SYNC_REQUEST_IDEMPOTENCY_NAMESPACE = "GATE_B_LIVE_VALIDATION_SYNC_REQUEST"

_PLACEHOLDER_CHECKSUM = "0" * 64


class GateBSyncRequestScope(FrozenProviderContract):
    """Exact SEC filing identity admitted by the Gate B request layer."""

    provider_code: Literal["SEC_EDGAR_PUBLIC_V1"]
    cik: Cik
    form: SecForm
    accession_number: AccessionNumber
    filed_date: date
    report_period: date


class GateBSyncRequestIdentity(FrozenProviderContract):
    """Replay-significant, non-executable Gate B request identity."""

    contract_version: Literal["1.0.0"]
    provider_definition_id: UUID
    provider_capability_id: UUID
    policy_id: UUID
    license_policy_id: UUID
    credential_reference_id: UUID
    security_id: UUID
    universe_code: None = None
    research_as_of_time: AwareUtcDateTime
    range_start: date
    range_end: date
    execution_mode: Literal[ProviderExecutionMode.LIVE_VALIDATION]
    scope: GateBSyncRequestScope
    budget: dict[str, object]

    @model_validator(mode="after")
    def validate_provider_request_contract(self) -> GateBSyncRequestIdentity:
        _build_request(
            self,
            request_checksum=_PLACEHOLDER_CHECKSUM,
            idempotency_key=_PLACEHOLDER_CHECKSUM,
        )
        return self


def build_gate_b_sync_request(
    identity: GateBSyncRequestIdentity,
) -> ProviderSyncRequestWrite:
    """Build a deterministic Provider sync request without I/O or persistence."""

    fresh_identity = GateBSyncRequestIdentity.model_validate(identity.model_dump(mode="python"))
    request_checksum = provider_checksum(fresh_identity)
    idempotency_key = provider_checksum(
        {
            "namespace": GATE_B_SYNC_REQUEST_IDEMPOTENCY_NAMESPACE,
            "version": GATE_B_SYNC_REQUEST_CONTRACT_VERSION,
            "identity": fresh_identity,
        }
    )
    return _build_request(
        fresh_identity,
        request_checksum=request_checksum,
        idempotency_key=idempotency_key,
    )


def _build_request(
    identity: GateBSyncRequestIdentity,
    *,
    request_checksum: str,
    idempotency_key: str,
) -> ProviderSyncRequestWrite:
    return ProviderSyncRequestWrite(
        provider_definition_id=identity.provider_definition_id,
        provider_capability_id=identity.provider_capability_id,
        policy_id=identity.policy_id,
        license_policy_id=identity.license_policy_id,
        credential_reference_id=identity.credential_reference_id,
        security_id=identity.security_id,
        universe_code=identity.universe_code,
        research_as_of_time=identity.research_as_of_time,
        range_start=identity.range_start,
        range_end=identity.range_end,
        execution_mode=identity.execution_mode,
        scope=identity.scope.model_dump(mode="json"),
        budget=dict(identity.budget),
        request_checksum=request_checksum,
        idempotency_key=idempotency_key,
    )
