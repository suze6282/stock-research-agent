from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.gate_b_request_identity import (
    GateBSyncRequestIdentity,
    GateBSyncRequestScope,
    build_gate_b_sync_request,
)
from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.sync import ProviderExecutionMode

PROVIDER_DEFINITION_ID = UUID("71000000-0000-4000-8000-000000000001")
PROVIDER_CAPABILITY_ID = UUID("71000000-0000-4000-8000-000000000002")
POLICY_ID = UUID("71000000-0000-4000-8000-000000000003")
LICENSE_POLICY_ID = UUID("71000000-0000-4000-8000-000000000004")
CREDENTIAL_REFERENCE_ID = UUID("71000000-0000-4000-8000-000000000005")
SECURITY_ID = UUID("71000000-0000-4000-8000-000000000006")
RESEARCH_AS_OF = datetime(2026, 8, 22, 18, 47, 59, 661193, tzinfo=UTC)
FILING_DATE = date(2026, 6, 25)
REPORT_PERIOD = date(2026, 5, 28)


def _scope() -> GateBSyncRequestScope:
    return GateBSyncRequestScope.model_validate(
        {
            "provider_code": "SEC_EDGAR_PUBLIC_V1",
            "cik": "0000723125",
            "form": "10-Q",
            "accession_number": "0000723125-26-000015",
            "filed_date": FILING_DATE,
            "report_period": REPORT_PERIOD,
        }
    )


def _identity() -> GateBSyncRequestIdentity:
    return GateBSyncRequestIdentity.model_validate(
        {
            "contract_version": "1.0.0",
            "provider_definition_id": PROVIDER_DEFINITION_ID,
            "provider_capability_id": PROVIDER_CAPABILITY_ID,
            "policy_id": POLICY_ID,
            "license_policy_id": LICENSE_POLICY_ID,
            "credential_reference_id": CREDENTIAL_REFERENCE_ID,
            "security_id": SECURITY_ID,
            "universe_code": None,
            "research_as_of_time": RESEARCH_AS_OF,
            "range_start": FILING_DATE,
            "range_end": FILING_DATE,
            "execution_mode": ProviderExecutionMode.LIVE_VALIDATION,
            "scope": _scope(),
            "budget": {
                "max_requests": 3,
                "max_bytes": 26 * 1024 * 1024,
                "max_attempts": 3,
                "max_duration_seconds": 120,
            },
        }
    )


def test_red_gateb_req_012_builder_revalidates_copied_offline_identity() -> None:
    copied = _identity().model_copy(update={"execution_mode": ProviderExecutionMode.OFFLINE})
    assert isinstance(copied, GateBSyncRequestIdentity)

    with pytest.raises(ValidationError):
        build_gate_b_sync_request(copied)


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
def test_red_gateb_req_013_builder_revalidates_copied_universe_identity() -> None:
    copied = _identity().model_copy(
        update={"security_id": None, "universe_code": "OFFLINE_EXACT_SCOPE"}
    )
    assert isinstance(copied, GateBSyncRequestIdentity)

    with pytest.raises(ValidationError):
        build_gate_b_sync_request(copied)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("provider_code", "OTHER_PROVIDER"),
        ("cik", "723125"),
        ("accession_number", "000072312526000015"),
        ("form", "10 q"),
    ),
)
def test_red_gateb_req_014_builder_revalidates_copied_invalid_sec_scope(
    field_name: str,
    invalid_value: str,
) -> None:
    copied_scope = _scope().model_copy(update={field_name: invalid_value})
    copied = _identity().model_copy(update={"scope": copied_scope})
    assert isinstance(copied_scope, GateBSyncRequestScope)
    assert isinstance(copied, GateBSyncRequestIdentity)

    with pytest.raises(ValidationError):
        build_gate_b_sync_request(copied)


def test_red_gateb_req_015_builder_revalidates_unchecked_constructed_identity() -> None:
    valid = _identity()
    unchecked = GateBSyncRequestIdentity.model_construct(
        **{
            **valid.__dict__,
            "execution_mode": ProviderExecutionMode.OFFLINE,
        }
    )
    assert isinstance(unchecked, GateBSyncRequestIdentity)

    with pytest.raises(ValidationError):
        build_gate_b_sync_request(unchecked)


def test_red_gateb_req_016_idempotency_uses_approved_gate_b_namespace_and_version() -> None:
    identity = _identity()
    expected = provider_checksum(
        {
            "namespace": "GATE_B_LIVE_VALIDATION_SYNC_REQUEST",
            "version": "1.0.0",
            "identity": identity,
        }
    )

    assert build_gate_b_sync_request(identity).idempotency_key == expected
