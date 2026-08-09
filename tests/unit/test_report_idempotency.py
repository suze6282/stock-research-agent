from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.generation import (
    ReportGenerationRunRecord,
    ReportGenerationStatus,
)
from stock_research_agent.domain.reports.schemas import (
    ReportInputManifest,
    ReportRequestRecord,
)
from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchPackageStatus,
    SyntheticStatus,
)

NOW = datetime(2026, 7, 28, 8, tzinfo=UTC)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.idempotency")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report idempotency functions are missing")


def _manifest(**updates: object) -> ReportInputManifest:
    values: dict[str, object] = {
        "schema_version": "report-input-manifest-v1",
        "research_package_id": UUID(int=1),
        "research_agent_run_id": UUID(int=2),
        "security_id": UUID(int=3),
        "issuer_id": UUID(int=4),
        "snapshot_id": UUID(int=5),
        "research_as_of_time": NOW,
        "package_status": ResearchPackageStatus.PARTIAL,
        "research_mode": ResearchMode.REAL_RESEARCH,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "package_checksum": "1" * 64,
        "claims_checksum": "2" * 64,
        "evidence_checksum": "3" * 64,
        "links_checksum": "4" * 64,
        "citations_checksum": "5" * 64,
        "lineage_checksum": "6" * 64,
        "canonical_payload_checksum": "7" * 64,
        "claim_ids": (),
        "evidence_ids": (),
        "link_ids": (),
        "citation_ids": (),
    }
    values.update(updates)
    return ReportInputManifest.model_construct(**values)


def _request(**updates: object) -> ReportRequestRecord:
    values: dict[str, object] = {
        "id": UUID(int=10),
        "manifest": _manifest(),
        "report_type": ReportType.FINANCIAL_RESEARCH_DRAFT,
        "report_locale": ReportLocale.EN_US,
        "template_name": "data_only_full",
        "template_version": "1.0.0",
        "report_policy_version": "verifiable-report-policy-v1",
        "reflection_policy_version": "runtime-reflection-policy-v1",
        "requested_sections": (
            ReportSection.FINANCIAL_HEALTH,
            ReportSection.LIMITATIONS,
        ),
        "include_evidence_appendix": True,
        "include_claim_index": True,
        "max_excerpt_length": 200,
        "idempotency_key": "0" * 64,
        "created_at": NOW,
    }
    values.update(updates)
    return ReportRequestRecord.model_validate(values)


def _run(**updates: object) -> ReportGenerationRunRecord:
    values: dict[str, object] = {
        "id": UUID(int=20),
        "report_request_id": UUID(int=10),
        "research_package_id": UUID(int=1),
        "research_agent_run_id": UUID(int=2),
        "security_id": UUID(int=3),
        "snapshot_id": UUID(int=5),
        "research_as_of_time": NOW,
        "report_type": ReportType.FINANCIAL_RESEARCH_DRAFT,
        "report_locale": ReportLocale.EN_US,
        "report_policy_version": "verifiable-report-policy-v1",
        "template_name": "data_only_full",
        "template_version": "1.0.0",
        "renderer_version": "deterministic-report-renderer-v1",
        "manifest_schema_version": "report-input-manifest-v1",
        "manifest_checksum": "7" * 64,
        "package_checksum": "1" * 64,
        "claims_checksum": "2" * 64,
        "evidence_checksum": "3" * 64,
        "links_checksum": "4" * 64,
        "citations_checksum": "5" * 64,
        "lineage_checksum": "6" * 64,
        "idempotency_key": "0" * 64,
        "status": ReportGenerationStatus.CREATED,
        "warning_count": 0,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return ReportGenerationRunRecord.model_validate(values)


def test_request_key_is_stable_and_excludes_id_key_and_created_at() -> None:
    module = _module()
    baseline = module.report_request_idempotency_key(_request())

    assert baseline == module.report_request_idempotency_key(
        _request(
            id=UUID(int=999),
            idempotency_key="f" * 64,
            created_at=NOW.replace(hour=9),
        )
    )


@pytest.mark.parametrize(
    "update",
    (
        {"report_type": ReportType.EVIDENCE_SUMMARY},
        {"report_locale": ReportLocale.ZH_CN},
        {"template_version": "1.0.1"},
        {"report_policy_version": "verifiable-report-policy-v2"},
        {"reflection_policy_version": "runtime-reflection-policy-v2"},
        {"requested_sections": (ReportSection.LIMITATIONS,)},
        {"include_evidence_appendix": False},
        {"include_claim_index": False},
        {"max_excerpt_length": 100},
        {"manifest": _manifest(package_checksum="8" * 64)},
        {"manifest": _manifest(canonical_payload_checksum="9" * 64)},
    ),
)
def test_request_key_changes_for_every_semantic_input(
    update: dict[str, object],
) -> None:
    module = _module()

    assert module.report_request_idempotency_key(
        _request()
    ) != module.report_request_idempotency_key(_request(**update))


def test_generation_key_excludes_lifecycle_outcome_and_audit_fields() -> None:
    module = _module()
    baseline = module.report_generation_idempotency_key(_run())

    assert baseline == module.report_generation_idempotency_key(
        _run(
            id=UUID(int=999),
            idempotency_key="f" * 64,
            status=ReportGenerationStatus.PARTIAL,
            warning_count=3,
            blocked_reason_code="INPUT_PARTIAL",
            created_at=NOW.replace(hour=7),
            updated_at=NOW.replace(hour=9),
            terminal_at=NOW.replace(hour=9),
        )
    )


@pytest.mark.parametrize(
    "update",
    (
        {"report_request_id": UUID(int=999)},
        {"snapshot_id": UUID(int=999)},
        {"report_locale": ReportLocale.ZH_CN},
        {"report_policy_version": "verifiable-report-policy-v2"},
        {"template_version": "1.0.1"},
        {"renderer_version": "deterministic-report-renderer-v2"},
        {"manifest_checksum": "8" * 64},
        {"package_checksum": "8" * 64},
        {"claims_checksum": "8" * 64},
        {"evidence_checksum": "8" * 64},
        {"links_checksum": "8" * 64},
        {"citations_checksum": "8" * 64},
        {"lineage_checksum": "8" * 64},
    ),
)
def test_generation_key_changes_for_every_fixed_generation_input(
    update: dict[str, object],
) -> None:
    module = _module()

    assert module.report_generation_idempotency_key(
        _run()
    ) != module.report_generation_idempotency_key(_run(**update))


@pytest.mark.parametrize(
    ("status", "reusable"),
    (
        (ReportGenerationStatus.CREATED, True),
        (ReportGenerationStatus.RUNNING, True),
        (ReportGenerationStatus.COMPLETED, True),
        (ReportGenerationStatus.PARTIAL, True),
        (ReportGenerationStatus.BLOCKED, True),
        (ReportGenerationStatus.FAILED, False),
    ),
)
def test_only_active_or_non_failed_terminal_runs_are_reusable(
    status: ReportGenerationStatus,
    reusable: bool,
) -> None:
    module = _module()
    updates: dict[str, object] = {"status": status}
    if status is ReportGenerationStatus.FAILED:
        updates.update(
            error_code="GENERATION_FAILED",
            safe_error_message="Safe failure.",
            terminal_at=NOW,
        )
    elif status is ReportGenerationStatus.BLOCKED:
        updates.update(blocked_reason_code="INPUT_BLOCKED", terminal_at=NOW)
    elif status is ReportGenerationStatus.PARTIAL:
        updates.update(blocked_reason_code="INPUT_PARTIAL", terminal_at=NOW)
    elif status is ReportGenerationStatus.COMPLETED:
        updates["terminal_at"] = NOW

    assert module.is_reusable_generation_run(_run(**updates)) is reusable
