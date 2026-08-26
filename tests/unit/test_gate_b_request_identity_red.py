from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import UTC, date, datetime
from types import ModuleType
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers.canonical import (
    canonical_provider_json,
    provider_checksum,
)
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderSyncRequestWrite,
)

MODULE_NAME = "stock_research_agent.domain.live_evidence.gate_b_request_identity"
PROVIDER_DEFINITION_ID = UUID("71000000-0000-4000-8000-000000000001")
PROVIDER_CAPABILITY_ID = UUID("71000000-0000-4000-8000-000000000002")
POLICY_ID = UUID("71000000-0000-4000-8000-000000000003")
LICENSE_POLICY_ID = UUID("71000000-0000-4000-8000-000000000004")
CREDENTIAL_REFERENCE_ID = UUID("71000000-0000-4000-8000-000000000005")
SECURITY_ID = UUID("71000000-0000-4000-8000-000000000006")
RESEARCH_AS_OF = datetime(2026, 8, 22, 18, 47, 59, 661193, tzinfo=UTC)
FILING_DATE = date(2026, 6, 25)
REPORT_PERIOD = date(2026, 5, 28)


def _api() -> ModuleType:
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as error:
        if error.name == MODULE_NAME:
            pytest.fail("Gate B request identity API is not implemented", pytrace=False)
        raise
    required = {
        "GateBSyncRequestScope",
        "GateBSyncRequestIdentity",
        "build_gate_b_sync_request",
    }
    missing = sorted(name for name in required if not hasattr(module, name))
    if missing:
        pytest.fail("Gate B request identity API is not implemented", pytrace=False)
    return module


def _scope_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "provider_code": "SEC_EDGAR_PUBLIC_V1",
        "cik": "0000723125",
        "form": "10-Q",
        "accession_number": "0000723125-26-000015",
        "filed_date": FILING_DATE,
        "report_period": REPORT_PERIOD,
    }
    values.update(changes)
    return values


def _identity_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
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
        "scope": _scope_values(),
        "budget": {
            "max_requests": 3,
            "max_bytes": 26 * 1024 * 1024,
            "max_attempts": 3,
            "max_duration_seconds": 120,
        },
    }
    values.update(changes)
    return values


def _identity(api: ModuleType, **changes: object) -> object:
    return api.GateBSyncRequestIdentity.model_validate(_identity_values(**changes))


def _build(api: ModuleType, **changes: object) -> ProviderSyncRequestWrite:
    result = api.build_gate_b_sync_request(_identity(api, **changes))
    assert isinstance(result, ProviderSyncRequestWrite)
    return result


def test_red_gateb_req_001_canonical_equivalent_inputs_have_identical_identity() -> None:
    api = _api()
    first_scope = _scope_values()
    second_scope = dict(reversed(tuple(first_scope.items())))

    first_identity = _identity(api, scope=first_scope)
    second_identity = _identity(api, scope=second_scope)
    first = api.build_gate_b_sync_request(first_identity)
    second = api.build_gate_b_sync_request(second_identity)

    assert first.request_checksum == second.request_checksum == provider_checksum(first_identity)
    expected_idempotency = provider_checksum(
        {
            "namespace": "GATE_B_LIVE_VALIDATION_SYNC_REQUEST",
            "version": "1.0.0",
            "identity": first_identity,
        }
    )
    assert first.idempotency_key == second.idempotency_key == expected_idempotency


def test_red_gateb_req_002_research_as_of_changes_checksum_and_idempotency() -> None:
    api = _api()
    first = _build(api)
    second = _build(
        api,
        research_as_of_time=datetime(2026, 8, 22, 18, 48, tzinfo=UTC),
    )

    assert first.request_checksum != second.request_checksum
    assert first.idempotency_key != second.idempotency_key


def test_red_gateb_req_003_security_change_changes_identity() -> None:
    api = _api()
    first = _build(api)
    second = _build(api, security_id=UUID("71000000-0000-4000-8000-000000000106"))

    assert first.request_checksum != second.request_checksum
    assert first.idempotency_key != second.idempotency_key


def test_red_gateb_req_004_accession_or_exact_scope_change_changes_identity() -> None:
    api = _api()
    first = _build(api)
    second = _build(
        api,
        scope=_scope_values(accession_number="0000723125-26-000016"),
    )

    assert first.request_checksum != second.request_checksum
    assert first.idempotency_key != second.idempotency_key
    assert set(first.scope) >= {
        "provider_code",
        "cik",
        "form",
        "accession_number",
        "filed_date",
        "report_period",
    }


def test_red_gateb_req_005_raw_contact_cannot_enter_request_identity() -> None:
    api = _api()
    synthetic_raw_contact = "SYNTHETIC_RAW_CONTACT_MUST_NOT_PERSIST"
    with pytest.raises(ValidationError):
        api.GateBSyncRequestIdentity.model_validate(
            _identity_values(raw_contact=synthetic_raw_contact)
        )

    identity = _identity(api)
    serialized = canonical_provider_json(identity)
    assert str(CREDENTIAL_REFERENCE_ID) in serialized
    assert "credential_reference_id" in serialized
    if synthetic_raw_contact in serialized:
        pytest.fail("raw contact entered canonical Gate B request identity", pytrace=False)


def test_red_gateb_req_007_offline_sync_semantics_are_rejected_by_gate_b_builder() -> None:
    api = _api()
    invalid_values = (
        _identity_values(execution_mode=ProviderExecutionMode.OFFLINE),
        _identity_values(security_id=None, universe_code="OFFLINE_EXACT_SCOPE"),
        _identity_values(scope=_scope_values(cik="723125")),
        _identity_values(scope=_scope_values(form="10 q")),
        _identity_values(scope=_scope_values(accession_number="000072312526000015")),
        _identity_values(scope={**_scope_values(), "namespace": "offline_sync"}),
        _identity_values(scope={**_scope_values(), "slice_id": "OFFLINE_EXACT_SCOPE"}),
        _identity_values(
            scope={**_scope_values(), "request_parameters": {"mode": "OFFLINE_FIXTURE_ONLY"}}
        ),
        _identity_values(scope={**_scope_values(), "url": "https://example.invalid/filing"}),
        _identity_values(scope={**_scope_values(), "path": "/tmp/filing"}),
        _identity_values(
            budget={
                "max_requests": 3,
                "max_bytes": 1.5,
                "max_attempts": 3,
                "max_duration_seconds": 120,
            }
        ),
    )

    for values in invalid_values:
        with pytest.raises(ValidationError):
            identity = api.GateBSyncRequestIdentity.model_validate(values)
            api.build_gate_b_sync_request(identity)


def test_red_gateb_req_008_identity_is_deterministic_across_process_restart() -> None:
    _api()
    json_values = {
        **_identity_values(),
        "provider_definition_id": str(PROVIDER_DEFINITION_ID),
        "provider_capability_id": str(PROVIDER_CAPABILITY_ID),
        "policy_id": str(POLICY_ID),
        "license_policy_id": str(LICENSE_POLICY_ID),
        "credential_reference_id": str(CREDENTIAL_REFERENCE_ID),
        "security_id": str(SECURITY_ID),
        "research_as_of_time": RESEARCH_AS_OF.isoformat(),
        "range_start": FILING_DATE.isoformat(),
        "range_end": FILING_DATE.isoformat(),
        "execution_mode": ProviderExecutionMode.LIVE_VALIDATION.value,
        "scope": {
            **_scope_values(),
            "filed_date": FILING_DATE.isoformat(),
            "report_period": REPORT_PERIOD.isoformat(),
        },
    }
    script = (
        "import json,sys;"
        f"from {MODULE_NAME} import GateBSyncRequestIdentity,build_gate_b_sync_request;"
        "identity=GateBSyncRequestIdentity.model_validate_json(sys.argv[1]);"
        "request=build_gate_b_sync_request(identity);"
        "print(json.dumps([request.request_checksum,request.idempotency_key]))"
    )
    payload = json.dumps(json_values, separators=(",", ":"), sort_keys=True)

    results = tuple(
        subprocess.run(
            [sys.executable, "-c", script, payload],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        for _ in range(2)
    )

    assert results[0] == results[1]


def test_red_gateb_req_009_credential_reference_change_changes_identity() -> None:
    api = _api()
    first = _build(api)
    second = _build(
        api,
        credential_reference_id=UUID("71000000-0000-4000-8000-000000000105"),
    )

    assert first.request_checksum != second.request_checksum
    assert first.idempotency_key != second.idempotency_key


def test_red_gateb_req_010_license_policy_change_changes_identity() -> None:
    api = _api()
    first = _build(api)
    second = _build(
        api,
        license_policy_id=UUID("71000000-0000-4000-8000-000000000104"),
    )

    assert first.request_checksum != second.request_checksum
    assert first.idempotency_key != second.idempotency_key


def test_red_gateb_req_011_request_identity_does_not_expand_generic_attempt_budget() -> None:
    api = _api()
    expanded_budget = {
        "max_requests": 3,
        "max_bytes": 26 * 1024 * 1024,
        "max_attempts": 4,
        "max_duration_seconds": 120,
    }

    with pytest.raises(ValidationError):
        identity = _identity(api, budget=expanded_budget)
        api.build_gate_b_sync_request(identity)
