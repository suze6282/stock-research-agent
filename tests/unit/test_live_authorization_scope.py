from __future__ import annotations

from uuid import uuid4

import pytest

from stock_research_agent.domain.live_evidence.authorization import (
    validate_execution_scope,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.schemas import (
    AuthorizationExecutionScope,
    LiveAuthorizationGrantWrite,
)


def _grant() -> LiveAuthorizationGrantWrite:
    return LiveAuthorizationGrantWrite.model_construct(
        provider_definition_id=uuid4(),
        provider_code="SEC_EDGAR_PUBLIC_V1",
        provider_definition_version="1.0.0",
        provider_capability_id=uuid4(),
        capability_code="FETCH_SEC_FILING_DOCUMENTS",
        capability_version="1.0.0",
        security_id=uuid4(),
        issuer_id=uuid4(),
        provider_security_identifier="0000723125",
    )


def _scope(grant: LiveAuthorizationGrantWrite) -> AuthorizationExecutionScope:
    return AuthorizationExecutionScope(
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


@pytest.mark.parametrize(
    "change",
    [
        {"provider_definition_id": uuid4()},
        {"provider_code": "OTHER_PROVIDER"},
        {"provider_definition_version": "2.0.0"},
    ],
)
def test_provider_mismatch(change: dict[str, object]) -> None:
    grant = _grant()
    scope = _scope(grant).model_copy(update=change)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_execution_scope(grant, scope)

    assert exc_info.value.code == "AUTH_PROVIDER_MISMATCH"


def test_exact_provider_scope_is_allowed() -> None:
    grant = _grant()

    decision = validate_execution_scope(grant, _scope(grant))

    assert decision.allowed is True
    assert decision.failure_code is None


@pytest.mark.parametrize(
    "change",
    [
        {"provider_capability_id": uuid4()},
        {"capability_code": "FETCH_OTHER_DOCUMENTS"},
        {"capability_version": "2.0.0"},
    ],
)
def test_capability_mismatch(change: dict[str, object]) -> None:
    grant = _grant()
    scope = _scope(grant).model_copy(update=change)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_execution_scope(grant, scope)

    assert exc_info.value.code == "AUTH_CAPABILITY_MISMATCH"


@pytest.mark.parametrize(
    "change",
    [
        {"security_id": uuid4()},
        {"issuer_id": uuid4()},
    ],
)
def test_security_or_issuer_mismatch(change: dict[str, object]) -> None:
    grant = _grant()
    scope = _scope(grant).model_copy(update=change)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_execution_scope(grant, scope)

    assert exc_info.value.code == "AUTH_SECURITY_MISMATCH"


def test_provider_security_identifier_cannot_be_overridden() -> None:
    grant = _grant()
    scope = _scope(grant).model_copy(update={"provider_security_identifier": "0000000001"})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_execution_scope(grant, scope)

    assert exc_info.value.code == "AUTH_PROVIDER_IDENTIFIER_MISMATCH"
