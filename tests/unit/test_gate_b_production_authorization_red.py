from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent import cli_live
from stock_research_agent.domain.live_evidence import gate_b_authorization
from stock_research_agent.domain.live_evidence.canonical import grant_checksum
from stock_research_agent.domain.live_evidence.enums import (
    LiveAuthorizationEventType,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.execution_approval import (
    ExecutionApprovalService,
)
from stock_research_agent.domain.live_evidence.schemas import (
    AuthorizationExecutionScope,
    LiveAuthorizationGrantRecord,
    LiveAuthorizationGrantWrite,
    LiveExecutionApprovalWrite,
    ValidateExecutionApprovalRequest,
)
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import ProviderCredentialStatus
from stock_research_agent.domain.providers.sync import ProviderSyncPlanRecord
from stock_research_agent.providers.credentials import (
    CredentialBindingKind,
    ResolvedCredentialContext,
)

NOW = datetime(2026, 8, 13, 1, 0, tzinfo=UTC)
SECURITY_ID = UUID("40000000-0000-0000-0000-000000000002")
ISSUER_ID = UUID("30000000-0000-0000-0000-000000000002")
PLAN_ID = UUID("50000000-0000-0000-0000-000000000001")
AUTHORIZATION_ID = UUID("60000000-0000-0000-0000-000000000001")
PLAN_CHECKSUM = "a" * 64
CONTACT_SECRET_SENTINEL = "SECRET_SENTINEL_DO_NOT_LOG"


def _grant_values(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "provider_definition_id": UUID("10000000-0000-0000-0000-000000000001"),
        "provider_code": "SEC_EDGAR_PUBLIC_V1",
        "provider_definition_version": "1.0.0",
        "provider_definition_checksum": "1" * 64,
        "provider_capability_id": UUID("10000000-0000-0000-0000-000000000002"),
        "capability_code": "FETCH_SEC_FILING_DOCUMENTS",
        "capability_version": "1.0.0",
        "official_domains": ("data.sec.gov", "www.sec.gov"),
        "security_id": SECURITY_ID,
        "issuer_id": ISSUER_ID,
        "provider_security_identifier": "0000723125",
        "request_methods": ("GET",),
        "request_limit": 4,
        "byte_limit": 26_214_400,
        "date_from": date(2025, 8, 13),
        "date_to": date(2026, 8, 13),
        "filing_types": ("10-K",),
        "allowed_document_count": 1,
        "credential_reference_id": UUID("10000000-0000-0000-0000-000000000003"),
        "user_agent_reference_id": UUID("10000000-0000-0000-0000-000000000004"),
        "license_policy_id": UUID("10000000-0000-0000-0000-000000000005"),
        "license_policy_version": "1.0.0",
        "license_policy_checksum": "2" * 64,
        "provider_policy_id": UUID("10000000-0000-0000-0000-000000000006"),
        "provider_policy_version": "1.0.0",
        "provider_policy_checksum": "3" * 64,
        "raw_storage_allowed": True,
        "cache_allowed": False,
        "retention_deadline": NOW + timedelta(days=30),
        "approved_at": NOW,
        "expires_at": NOW + timedelta(minutes=30),
        "approved_by": "LOCAL_OPERATOR",
        "canonical_checksum": "4" * 64,
    }
    values.update(updates)
    return values


def _approval() -> LiveExecutionApprovalWrite:
    return LiveExecutionApprovalWrite(
        authorization_id=AUTHORIZATION_ID,
        authorization_checksum="4" * 64,
        sync_plan_id=PLAN_ID,
        plan_checksum=PLAN_CHECKSUM,
        approval_registry_id="LOCAL_OPERATOR_CONFIRMATION",
        approval_registry_version="1.0.0",
        approval_registry_checksum="5" * 64,
        approved_by="LOCAL_OPERATOR",
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


def _authorization_create_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": "SEC_EDGAR_PUBLIC_V1",
        "candidate": {
            "security_id": str(SECURITY_ID),
            "issuer_id": str(ISSUER_ID),
            "symbol": "MU",
            "exchange": "XNAS",
            "cik": "0000723125",
        },
        "plan_id": str(PLAN_ID),
        "plan_checksum": PLAN_CHECKSUM,
        "allowed_hosts": ("data.sec.gov", "www.sec.gov"),
        "allowed_paths": (
            "/submissions/CIK0000723125.json",
            "/Archives/edgar/data/723125/000072312525000028/index.json",
            "/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm",
        ),
        "max_resource_count": 3,
        "max_actual_attempts": 4,
        "retry_limit": 1,
        "redirect_limit": 0,
        "concurrency": 1,
        "connect_timeout_seconds": 10,
        "idle_read_timeout_seconds": 30,
        "total_timeout_seconds": 120,
        "contact_identity_reference": "SEC_EDGAR_CONTACT_IDENTITY",
        "grant_id": "GATE_B_FINITE_GRANT",
        "single_use": True,
        "approved_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
    }
    payload.update(updates)
    return payload


def _authoritative_records() -> tuple[
    LiveAuthorizationGrantRecord,
    object,
    ProviderSyncPlanRecord,
    AuthorizationExecutionScope,
    CredentialReferenceRecord,
]:
    draft = LiveAuthorizationGrantWrite.model_validate(_grant_values(canonical_checksum="0" * 64))
    grant_write = draft.model_copy(update={"canonical_checksum": grant_checksum(draft)})
    grant = LiveAuthorizationGrantRecord(
        **grant_write.model_dump(),
        id=AUTHORIZATION_ID,
        created_at=NOW,
    )
    approval = ExecutionApprovalService.create(
        _approval().model_copy(update={"authorization_checksum": grant.canonical_checksum})
    )
    plan = ProviderSyncPlanRecord(
        sync_request_id=UUID("50000000-0000-0000-0000-000000000002"),
        adapter_version="1.0.0",
        checkpoint_revision=None,
        slices=({"slice_id": "ONE"}, {"slice_id": "TWO"}, {"slice_id": "THREE"}),
        plan_checksum=PLAN_CHECKSUM,
        id=PLAN_ID,
        slice_count=3,
        created_at=NOW,
    )
    scope = AuthorizationExecutionScope(
        provider_definition_id=grant.provider_definition_id,
        provider_code=grant.provider_code,
        provider_definition_version=grant.provider_definition_version,
        provider_capability_id=grant.provider_capability_id,
        capability_code=grant.capability_code,
        capability_version=grant.capability_version,
        security_id=grant.security_id,
        issuer_id=grant.issuer_id,
        provider_security_identifier=grant.provider_security_identifier,
    )
    reference = CredentialReferenceRecord(
        provider_definition_id=grant.provider_definition_id,
        reference_version="1.0.0",
        resolver_kind=CredentialResolverKind.ENVIRONMENT,
        declared_name="SEC_EDGAR_CONTACT_IDENTITY",
        status=ProviderCredentialStatus.CONFIGURED_METADATA_ONLY,
        safe_label="SEC EDGAR contact identity",
        id=grant.user_agent_reference_id,
        checksum="6" * 64,
        created_at=NOW,
    )
    return grant, approval, plan, scope, reference


def _production_authorization_create() -> object:
    try:
        application = cli_live.authorization_application_factory()
    except RuntimeError as error:
        pytest.fail(f"production authorization composition missing: {error}")
    create = getattr(application, "create", None)
    assert callable(create), "production authorization application has no create operation"
    return create


def test_red_028_production_authorization_creation_composition_exists() -> None:
    create = _production_authorization_create()

    result = create(_authorization_create_payload())  # type: ignore[operator]
    assert result.provider == "SEC_EDGAR_PUBLIC_V1"
    assert result.plan_checksum == PLAN_CHECKSUM
    assert result.single_use is True


def test_red_029_production_authorization_rejects_fail_closed_matrix() -> None:
    create = _production_authorization_create()
    invalid_updates: tuple[dict[str, object], ...] = (
        {"provider": None},
        {"provider": "OTHER_PROVIDER"},
        {"candidate": None},
        {"plan_checksum": None},
        {"grant_id": None},
        {"single_use": False},
        {"allowed_hosts": ()},
        {"max_resource_count": 4},
        {"max_actual_attempts": 5},
        {"redirect_limit": 1},
        {"contact_identity_reference": None},
        {"expires_at": NOW},
    )

    for updates in invalid_updates:
        with pytest.raises(LiveEvidenceValidationError):
            create(_authorization_create_payload(**updates))  # type: ignore[operator]


def test_production_authorization_rejects_coerced_scalar_types() -> None:
    create = _production_authorization_create()

    for updates in (
        {"single_use": "true"},
        {"max_resource_count": "3"},
        {"redirect_limit": "0"},
    ):
        with pytest.raises(LiveEvidenceValidationError):
            create(_authorization_create_payload(**updates))  # type: ignore[operator]


def test_red_030_authorization_is_immutable_and_execution_approval_is_single_use() -> None:
    grant = LiveAuthorizationGrantWrite.model_validate(_grant_values())
    with pytest.raises(ValidationError):
        grant.request_limit = 5

    approval = ExecutionApprovalService.create(_approval())
    with pytest.raises(LiveEvidenceValidationError, match="EXEC_APPROVAL_REPLAYED"):
        ExecutionApprovalService.validate(
            ValidateExecutionApprovalRequest(
                approval=approval,
                authorization_checksum=approval.authorization_checksum,
                plan_checksum=approval.plan_checksum,
                checked_at=NOW + timedelta(minutes=1),
                consumed=True,
            )
        )


def test_red_031_authorization_binds_contact_reference_without_secret_value() -> None:
    create = _production_authorization_create()

    result = create(_authorization_create_payload())  # type: ignore[operator]
    serialized = repr(result)
    assert "SEC_EDGAR_CONTACT_IDENTITY" in serialized
    assert CONTACT_SECRET_SENTINEL not in serialized


def test_production_gate_requires_valid_persisted_grant_approval_and_contact_metadata() -> None:
    gate_type = getattr(gate_b_authorization, "ProductionAuthorizationGate", None)
    assert gate_type is not None, "production persisted-record authorization gate is missing"
    grant, approval, plan, scope, reference = _authoritative_records()
    envelope = _production_authorization_create()(
        _authorization_create_payload(grant_id=str(grant.id))
    )

    capability = gate_type().authorize(
        envelope,
        grant=grant,
        events=(LiveAuthorizationEventType.APPROVE, LiveAuthorizationEventType.ACTIVATE),
        approval=approval,
        plan=plan,
        scope=scope,
        contact_reference=reference,
        checked_at=NOW + timedelta(minutes=1),
    )

    assert isinstance(capability, gate_b_authorization.GateBAuthorizationValidation)
    assert not isinstance(capability, gate_b_authorization.AuthorizedGateBExecution)
    assert capability.authorization_id == grant.id
    assert capability.approval_id == approval.id
    assert capability.user_agent_reference_id == reference.id


def test_production_gate_never_exposes_or_resolves_contact_value() -> None:
    gate_type = getattr(gate_b_authorization, "ProductionAuthorizationGate", None)
    assert gate_type is not None, "production persisted-record authorization gate is missing"
    grant, approval, plan, scope, reference = _authoritative_records()
    envelope = _production_authorization_create()(
        _authorization_create_payload(grant_id=str(grant.id))
    )
    wrong_reference = reference.model_copy(update={"declared_name": "OTHER_CONTACT_IDENTITY"})

    with pytest.raises(LiveEvidenceValidationError, match="GATE_B_CONTACT_REFERENCE_INVALID"):
        gate_type().authorize(
            envelope,
            grant=grant,
            events=(LiveAuthorizationEventType.APPROVE, LiveAuthorizationEventType.ACTIVATE),
            approval=approval,
            plan=plan,
            scope=scope,
            contact_reference=wrong_reference,
            checked_at=NOW + timedelta(minutes=1),
        )

    assert CONTACT_SECRET_SENTINEL not in repr(envelope)


def test_red_034_gate_b_authorization_rejects_fifth_actual_attempt() -> None:
    create = _production_authorization_create()

    with pytest.raises(LiveEvidenceValidationError):
        create(_authorization_create_payload(max_actual_attempts=5))  # type: ignore[operator]


def test_red_040_authorization_binds_exact_sec_paths_not_only_hosts() -> None:
    approval = ExecutionApprovalService.create(_approval())

    with pytest.raises(LiveEvidenceValidationError, match="EXEC_APPROVAL_PLAN_MISMATCH"):
        ExecutionApprovalService.validate(
            ValidateExecutionApprovalRequest(
                approval=approval,
                authorization_checksum=approval.authorization_checksum,
                plan_checksum="9" * 64,
                checked_at=NOW + timedelta(minutes=1),
                consumed=False,
            )
        )


def test_red_044_audit_models_cover_gate_b_authorization_and_artifact_lineage() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import GateBAuditView

    required = {
        "artifact_id",
        "authorization_id",
        "candidate",
        "content_checksum",
        "plan_checksum",
        "provider",
        "retrieved_at",
    }

    assert required <= set(GateBAuditView.model_fields), "RED-044 Gate B audit view is incomplete"


def test_red_047_authorization_binds_filing_path_and_plan_checksum() -> None:
    approval = ExecutionApprovalService.create(_approval())

    with pytest.raises(LiveEvidenceValidationError, match="EXEC_APPROVAL_PLAN_MISMATCH"):
        ExecutionApprovalService.validate(
            ValidateExecutionApprovalRequest(
                approval=approval,
                authorization_checksum=approval.authorization_checksum,
                plan_checksum="8" * 64,
                checked_at=NOW + timedelta(minutes=1),
                consumed=False,
            )
        )


def test_existing_resolved_contact_context_cannot_be_logged_or_serialized() -> None:
    context = ResolvedCredentialContext(
        CredentialBindingKind.HEADER,
        "User-Agent",
        CONTACT_SECRET_SENTINEL,
    )

    assert CONTACT_SECRET_SENTINEL not in repr(context)
    assert CONTACT_SECRET_SENTINEL not in str(context)
    with pytest.raises(TypeError, match="cannot be serialized"):
        context.__reduce__()


def test_existing_authorization_scope_still_rejects_wrong_candidate_identity() -> None:
    from stock_research_agent.domain.live_evidence.authorization import (
        validate_execution_scope,
    )

    grant = LiveAuthorizationGrantWrite.model_validate(_grant_values())
    wrong_scope = AuthorizationExecutionScope(
        provider_definition_id=grant.provider_definition_id,
        provider_code=grant.provider_code,
        provider_definition_version=grant.provider_definition_version,
        provider_capability_id=grant.provider_capability_id,
        capability_code=grant.capability_code,
        capability_version=grant.capability_version,
        security_id=UUID("40000000-0000-0000-0000-000000000099"),
        issuer_id=grant.issuer_id,
        provider_security_identifier=grant.provider_security_identifier,
    )

    with pytest.raises(LiveEvidenceValidationError, match="AUTH_SECURITY_MISMATCH"):
        validate_execution_scope(grant, wrong_scope)


def test_existing_active_authorization_event_sequence_is_explicit() -> None:
    from stock_research_agent.domain.live_evidence.authorization import derive_state
    from stock_research_agent.domain.live_evidence.enums import LiveAuthorizationState

    grant = LiveAuthorizationGrantWrite.model_validate(_grant_values())
    state = derive_state(
        grant,
        (LiveAuthorizationEventType.APPROVE, LiveAuthorizationEventType.ACTIVATE),
        NOW + timedelta(minutes=1),
    )

    assert state is LiveAuthorizationState.ACTIVE
