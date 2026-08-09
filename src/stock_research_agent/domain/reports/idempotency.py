"""Canonical idempotency keys for report requests and generation runs."""

from __future__ import annotations

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.generation import (
    ReportGenerationRunRecord,
    ReportGenerationStatus,
)
from stock_research_agent.domain.reports.schemas import ReportRequestRecord

_REQUEST_AUDIT_FIELDS = {
    "id",
    "idempotency_key",
    "created_at",
}

_GENERATION_OUTCOME_AND_AUDIT_FIELDS = {
    "id",
    "idempotency_key",
    "status",
    "warning_count",
    "blocked_reason_code",
    "error_code",
    "safe_error_message",
    "created_at",
    "updated_at",
    "terminal_at",
}


def report_request_idempotency_key(request: ReportRequestRecord) -> str:
    """Hash every Request semantic field and its complete sealed manifest."""

    return report_checksum(
        request.model_dump(
            mode="python",
            exclude=_REQUEST_AUDIT_FIELDS,
        )
    )


def report_generation_idempotency_key(
    run: ReportGenerationRunRecord,
) -> str:
    """Hash fixed generation inputs while excluding lifecycle outcome and audit."""

    return report_checksum(
        run.model_dump(
            mode="python",
            exclude=_GENERATION_OUTCOME_AND_AUDIT_FIELDS,
        )
    )


def is_reusable_generation_run(run: ReportGenerationRunRecord) -> bool:
    """Allow identical active or non-failed terminal runs to converge."""

    return run.status is not ReportGenerationStatus.FAILED
