from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.schemas import (
    PersistedReportInput,
    ReportInputManifest,
    ReportRequestRecord,
    ReportRequestWrite,
    VerifiedReportInput,
)
from stock_research_agent.domain.research_agent.enums import ResearchPackageStatus

NOW = datetime(2026, 7, 26, 12, tzinfo=UTC)
PACKAGE_ID = UUID("10000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("10000000-0000-0000-0000-000000000002")


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.requests")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report request preflight is missing")


def _manifest(status: ResearchPackageStatus) -> ReportInputManifest:
    return ReportInputManifest.model_construct(
        research_package_id=PACKAGE_ID,
        package_status=status,
        canonical_payload_checksum="a" * 64,
        package_checksum="b" * 64,
        claims_checksum="c" * 64,
        evidence_checksum="d" * 64,
        links_checksum="e" * 64,
        citations_checksum="f" * 64,
        lineage_checksum="0" * 64,
    )


class _Inputs:
    def __init__(self, bundle: PersistedReportInput | None) -> None:
        self.bundle = bundle

    def get_package_bundle(
        self,
        research_package_id: UUID,
    ) -> PersistedReportInput | None:
        assert research_package_id == PACKAGE_ID
        return self.bundle


class _Requests:
    def __init__(self) -> None:
        self.values: list[ReportRequestWrite] = []

    def add_request(self, value: ReportRequestWrite) -> ReportRequestRecord:
        self.values.append(value)
        return ReportRequestRecord.model_construct(**value.__dict__)

    def get_request(self, request_id: UUID) -> ReportRequestRecord | None:
        return next((item for item in self.values if item.id == request_id), None)


def _service(
    monkeypatch: pytest.MonkeyPatch,
    status: ResearchPackageStatus,
) -> tuple[object, _Requests]:
    module = _module()
    bundle = PersistedReportInput.model_construct()
    manifest = _manifest(status)
    monkeypatch.setattr(module, "build_report_input_manifest", lambda value: manifest)
    monkeypatch.setattr(
        module,
        "validate_report_input_manifest",
        lambda value, persisted: VerifiedReportInput(
            manifest=value,
            input=persisted,
        ),
    )
    requests = _Requests()
    service = module.ReportRequestService(
        inputs=_Inputs(bundle),
        requests=requests,
        id_factory=lambda: REQUEST_ID,
        now=lambda: NOW,
    )
    return service, requests


def _command(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "research_package_id": PACKAGE_ID,
        "report_type": ReportType.EVIDENCE_SUMMARY,
        "report_locale": ReportLocale.ZH_CN,
        "template_name": "evidence_summary",
        "template_version": "1.0.0",
        "report_policy_version": "verifiable-report-policy-v1",
        "reflection_policy_version": "runtime-report-reflection-v1",
        "requested_sections": (
            ReportSection.SECURITY_IDENTITY,
            ReportSection.DATA_QUALITY,
            ReportSection.LIMITATIONS,
        ),
        "include_evidence_appendix": False,
        "include_claim_index": False,
        "max_excerpt_length": 500,
    }
    values.update(updates)
    return module.CreateReportRequest.model_validate(values)


def test_request_is_sealed_with_exact_versions_and_stable_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _service(monkeypatch, ResearchPackageStatus.PARTIAL)

    first = service.create(_command())
    second = service.create(_command())

    assert first.id == REQUEST_ID
    assert first.report_locale is ReportLocale.ZH_CN
    assert first.template_version == "1.0.0"
    assert first.report_policy_version == "verifiable-report-policy-v1"
    assert first.reflection_policy_version == "runtime-report-reflection-v1"
    assert first.max_excerpt_length == 500
    assert first.idempotency_key == second.idempotency_key
    assert repository.values[0].manifest.package_status is ResearchPackageStatus.PARTIAL


@pytest.mark.parametrize(
    ("status", "report_type", "code"),
    [
        (
            ResearchPackageStatus.FAILED,
            ReportType.DATA_QUALITY_REPORT,
            "RESEARCH_PACKAGE_FAILED",
        ),
        (
            ResearchPackageStatus.BLOCKED,
            ReportType.FULL_RESEARCH_DRAFT,
            "BLOCKED_PACKAGE_REPORT_TYPE_NOT_ALLOWED",
        ),
        (
            ResearchPackageStatus.BLOCKED,
            ReportType.FINANCIAL_RESEARCH_DRAFT,
            "BLOCKED_PACKAGE_REPORT_TYPE_NOT_ALLOWED",
        ),
    ],
)
def test_failed_or_blocked_package_rules_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    status: ResearchPackageStatus,
    report_type: ReportType,
    code: str,
) -> None:
    service, _ = _service(monkeypatch, status)

    with pytest.raises(_module().ReportRequestError) as raised:
        service.create(_command(report_type=report_type))

    assert raised.value.code == code


def test_blocked_package_allows_only_data_quality_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service(monkeypatch, ResearchPackageStatus.BLOCKED)

    result = service.create(_command(report_type=ReportType.DATA_QUALITY_REPORT))

    assert result.report_type is ReportType.DATA_QUALITY_REPORT


def test_missing_package_has_stable_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    service = module.ReportRequestService(
        inputs=_Inputs(None),
        requests=_Requests(),
        id_factory=lambda: REQUEST_ID,
        now=lambda: NOW,
    )

    with pytest.raises(module.ReportRequestError) as raised:
        service.create(_command())

    assert raised.value.code == "RESEARCH_PACKAGE_NOT_FOUND"


@pytest.mark.parametrize(
    "updates",
    [
        {"template_name": "../template"},
        {"template_name": "C:\\report"},
        {"template_version": "latest"},
        {"report_policy_version": "LATEST"},
        {"reflection_policy_version": "runtime/report"},
        {"max_excerpt_length": 1001},
        {
            "requested_sections": (
                ReportSection.DATA_QUALITY,
                ReportSection.DATA_QUALITY,
            )
        },
    ],
)
def test_request_schema_rejects_paths_latest_bounds_and_duplicate_sections(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _command(**updates)


def test_idempotency_changes_for_any_semantic_request_reduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service(monkeypatch, ResearchPackageStatus.PARTIAL)

    full = service.create(_command())
    reduced = service.create(
        _command(
            requested_sections=(
                ReportSection.DATA_QUALITY,
                ReportSection.LIMITATIONS,
            ),
            max_excerpt_length=200,
        )
    )

    assert full.idempotency_key != reduced.idempotency_key
