from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.enums import ReportLocale, ReportType

NOW = datetime(2026, 7, 26, 14, tzinfo=UTC)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.generation")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report generation lifecycle is missing")


def _write(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": UUID("10000000-0000-0000-0000-000000000001"),
        "report_request_id": UUID("10000000-0000-0000-0000-000000000002"),
        "research_package_id": UUID("10000000-0000-0000-0000-000000000003"),
        "research_agent_run_id": UUID("10000000-0000-0000-0000-000000000004"),
        "security_id": UUID("10000000-0000-0000-0000-000000000005"),
        "snapshot_id": UUID("10000000-0000-0000-0000-000000000006"),
        "research_as_of_time": NOW,
        "report_type": ReportType.EVIDENCE_SUMMARY,
        "report_locale": ReportLocale.ZH_CN,
        "report_policy_version": "verifiable-report-policy-v1",
        "template_name": "evidence_summary",
        "template_version": "1.0.0",
        "renderer_version": "deterministic-report-renderer-v1",
        "manifest_schema_version": "report-input-manifest-v1",
        "manifest_checksum": "a" * 64,
        "package_checksum": "b" * 64,
        "claims_checksum": "c" * 64,
        "evidence_checksum": "d" * 64,
        "links_checksum": "e" * 64,
        "citations_checksum": "f" * 64,
        "lineage_checksum": "0" * 64,
        "idempotency_key": "1" * 64,
        "status": module.ReportGenerationStatus.CREATED,
        "warning_count": 0,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return module.ReportGenerationRunWrite.model_validate(values)


def test_generation_state_machine_allows_only_approved_transition_graph() -> None:
    module = _module()
    machine = module.ReportGenerationStateMachine()
    terminals = (
        module.ReportGenerationStatus.COMPLETED,
        module.ReportGenerationStatus.PARTIAL,
        module.ReportGenerationStatus.BLOCKED,
        module.ReportGenerationStatus.FAILED,
    )

    assert (
        machine.transition(
            module.ReportGenerationStatus.CREATED,
            module.ReportGenerationStatus.RUNNING,
        )
        is module.ReportGenerationStatus.RUNNING
    )
    for terminal in terminals:
        assert (
            machine.transition(
                module.ReportGenerationStatus.RUNNING,
                terminal,
            )
            is terminal
        )

    for current in module.ReportGenerationStatus:
        for target in module.ReportGenerationStatus:
            allowed = (
                current is module.ReportGenerationStatus.CREATED
                and target is module.ReportGenerationStatus.RUNNING
            ) or (current is module.ReportGenerationStatus.RUNNING and target in terminals)
            if not allowed:
                with pytest.raises(module.ReportGenerationTransitionError):
                    machine.transition(current, target)


def test_generation_run_seals_exact_context_versions_and_checksums() -> None:
    module = _module()
    record = module.ReportGenerationRunRecord.model_validate(_write().model_dump(mode="python"))

    assert record.renderer_version == "deterministic-report-renderer-v1"
    assert record.template_version == "1.0.0"
    assert record.manifest_checksum == "a" * 64
    assert record.lineage_checksum == "0" * 64
    assert record.status is module.ReportGenerationStatus.CREATED

    with pytest.raises(ValidationError, match="Instance is frozen"):
        record.snapshot_id = UUID(int=999)


def test_terminal_transition_requires_completion_and_safe_bounded_failure_shape() -> None:
    module = _module()

    running = module.ReportGenerationTransition(
        expected_status=module.ReportGenerationStatus.CREATED,
        target_status=module.ReportGenerationStatus.RUNNING,
        warning_count=0,
        changed_at=NOW,
    )
    assert running.target_status is module.ReportGenerationStatus.RUNNING

    completed = module.ReportGenerationTransition(
        expected_status=module.ReportGenerationStatus.RUNNING,
        target_status=module.ReportGenerationStatus.PARTIAL,
        warning_count=2,
        blocked_reason_code="REAL_COMPANY_EVIDENCE_PARTIAL",
        changed_at=NOW,
    )
    assert completed.target_status is module.ReportGenerationStatus.PARTIAL

    with pytest.raises(ValidationError):
        module.ReportGenerationTransition(
            expected_status=module.ReportGenerationStatus.RUNNING,
            target_status=module.ReportGenerationStatus.FAILED,
            warning_count=0,
            safe_error_message="x" * 257,
            changed_at=NOW,
        )
    with pytest.raises(ValidationError, match="requires safe error"):
        module.ReportGenerationTransition(
            expected_status=module.ReportGenerationStatus.RUNNING,
            target_status=module.ReportGenerationStatus.FAILED,
            warning_count=0,
            changed_at=NOW,
        )


def test_generation_run_rejects_unknown_fields_naive_time_and_bad_checksum() -> None:
    module = _module()
    values = _write().model_dump(mode="python")
    values["unexpected"] = "forbidden"
    with pytest.raises(ValidationError):
        module.ReportGenerationRunWrite.model_validate(values)

    values = _write().model_dump(mode="python")
    values["research_as_of_time"] = datetime(2026, 7, 26, 14)
    with pytest.raises(ValidationError):
        module.ReportGenerationRunWrite.model_validate(values)

    values = _write().model_dump(mode="python")
    values["manifest_checksum"] = "bad"
    with pytest.raises(ValidationError):
        module.ReportGenerationRunWrite.model_validate(values)
