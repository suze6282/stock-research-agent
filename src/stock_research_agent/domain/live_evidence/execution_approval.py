from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from stock_research_agent.domain.live_evidence.enums import ExecutionApprovalState
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.schemas import (
    ExecutionApprovalDecision,
    LiveExecutionApprovalRecord,
    LiveExecutionApprovalWrite,
    ValidateExecutionApprovalRequest,
)


def _signature(value: LiveExecutionApprovalWrite) -> str:
    canonical = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExecutionApprovalService:
    @staticmethod
    def create(value: LiveExecutionApprovalWrite) -> LiveExecutionApprovalRecord:
        return LiveExecutionApprovalRecord(
            id=uuid4(),
            **value.model_dump(),
            approval_signature=_signature(value),
            state=ExecutionApprovalState.VALID,
            created_at=value.approved_at,
        )

    @staticmethod
    def validate(
        request: ValidateExecutionApprovalRequest,
    ) -> ExecutionApprovalDecision:
        approval = request.approval
        if (
            approval.authorization_checksum != request.authorization_checksum
            or approval.plan_checksum != request.plan_checksum
        ):
            raise LiveEvidenceValidationError("EXEC_APPROVAL_PLAN_MISMATCH")
        if request.consumed:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_REPLAYED")
        if request.checked_at >= approval.expires_at:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_EXPIRED")

        write = LiveExecutionApprovalWrite.model_validate(
            approval.model_dump(exclude={"id", "approval_signature", "state", "created_at"})
        )
        if approval.approval_signature != _signature(write):
            return ExecutionApprovalDecision(
                state=ExecutionApprovalState.BLOCKED,
                failure_code="EXEC_APPROVAL_SIGNATURE_INVALID",
            )
        return ExecutionApprovalDecision(
            state=ExecutionApprovalState.VALID,
            failure_code=None,
        )
