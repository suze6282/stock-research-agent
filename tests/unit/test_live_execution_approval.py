from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.enums import ExecutionApprovalState
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.execution_approval import (
    ExecutionApprovalService,
)
from stock_research_agent.domain.live_evidence.schemas import (
    LiveExecutionApprovalWrite,
    ValidateExecutionApprovalRequest,
)


def _write() -> LiveExecutionApprovalWrite:
    approved_at = datetime(2026, 8, 1, 2, 0, tzinfo=UTC)
    return LiveExecutionApprovalWrite(
        authorization_id=uuid4(),
        authorization_checksum="a" * 64,
        sync_plan_id=uuid4(),
        plan_checksum="b" * 64,
        approval_registry_id="LOCAL_OPERATOR_CONFIRMATION",
        approval_registry_version="1.0.0",
        approval_registry_checksum="c" * 64,
        approved_by="LOCAL_OPERATOR",
        approved_at=approved_at,
        expires_at=approved_at + timedelta(minutes=5),
    )


def test_execution_approval_states_are_finite() -> None:
    assert {item.value for item in ExecutionApprovalState} == {
        "VALID",
        "EXPIRED",
        "CONSUMED",
        "BLOCKED",
    }


def test_create_binds_grant_plan_and_registry_in_signature() -> None:
    write = _write()

    record = ExecutionApprovalService.create(write)

    assert record.authorization_checksum == "a" * 64
    assert record.plan_checksum == "b" * 64
    assert record.approval_registry_checksum == "c" * 64
    assert len(record.approval_signature) == 64
    assert record.state is ExecutionApprovalState.VALID


def test_signature_is_stable_and_changes_with_plan() -> None:
    write = _write()

    first = ExecutionApprovalService.create(write)
    repeated = ExecutionApprovalService.create(write)
    changed = ExecutionApprovalService.create(write.model_copy(update={"plan_checksum": "d" * 64}))

    assert first.approval_signature == repeated.approval_signature
    assert first.approval_signature != changed.approval_signature


def test_approval_lifetime_cannot_exceed_ten_minutes() -> None:
    write = _write()

    with pytest.raises(ValidationError):
        LiveExecutionApprovalWrite(
            **{
                **write.model_dump(exclude={"expires_at"}),
                "expires_at": write.approved_at + timedelta(minutes=10, seconds=1),
            }
        )


def test_validation_accepts_exact_unexpired_unused_binding() -> None:
    record = ExecutionApprovalService.create(_write())
    request = ValidateExecutionApprovalRequest(
        approval=record,
        authorization_checksum=record.authorization_checksum,
        plan_checksum=record.plan_checksum,
        checked_at=record.approved_at + timedelta(minutes=1),
        consumed=False,
    )

    decision = ExecutionApprovalService.validate(request)

    assert decision.state is ExecutionApprovalState.VALID
    assert decision.failure_code is None


def test_validation_rejects_plan_mismatch() -> None:
    record = ExecutionApprovalService.create(_write())
    request = ValidateExecutionApprovalRequest(
        approval=record,
        authorization_checksum=record.authorization_checksum,
        plan_checksum="d" * 64,
        checked_at=record.approved_at,
        consumed=False,
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ExecutionApprovalService.validate(request)

    assert exc_info.value.code == "EXEC_APPROVAL_PLAN_MISMATCH"


def test_validation_rejects_expired_approval() -> None:
    record = ExecutionApprovalService.create(_write())
    request = ValidateExecutionApprovalRequest(
        approval=record,
        authorization_checksum=record.authorization_checksum,
        plan_checksum=record.plan_checksum,
        checked_at=record.expires_at,
        consumed=False,
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ExecutionApprovalService.validate(request)

    assert exc_info.value.code == "EXEC_APPROVAL_EXPIRED"


def test_validation_rejects_replay() -> None:
    record = ExecutionApprovalService.create(_write())
    request = ValidateExecutionApprovalRequest(
        approval=record,
        authorization_checksum=record.authorization_checksum,
        plan_checksum=record.plan_checksum,
        checked_at=record.approved_at,
        consumed=True,
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ExecutionApprovalService.validate(request)

    assert exc_info.value.code == "EXEC_APPROVAL_REPLAYED"


def test_validation_rejects_tampered_registry_bound_signature() -> None:
    record = ExecutionApprovalService.create(_write()).model_copy(
        update={"approval_signature": "f" * 64}
    )
    request = ValidateExecutionApprovalRequest(
        approval=record,
        authorization_checksum=record.authorization_checksum,
        plan_checksum=record.plan_checksum,
        checked_at=record.approved_at,
        consumed=False,
    )

    decision = ExecutionApprovalService.validate(request)

    assert decision.state is ExecutionApprovalState.BLOCKED
    assert decision.failure_code == "EXEC_APPROVAL_SIGNATURE_INVALID"
