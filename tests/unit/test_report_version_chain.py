from __future__ import annotations

from importlib import import_module
from uuid import UUID

import pytest

from tests.unit.test_research_report_aggregate import _record_values


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.versioning")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report version-chain validator is missing")


def _report(**updates: object) -> object:
    reporting = import_module("stock_research_agent.domain.reports.reporting")
    return reporting.ResearchReportRecord.model_validate(_record_values(**updates))


def test_valid_successor_is_same_context_and_exactly_next_version() -> None:
    module = _module()
    parent = _report()
    child = _report(
        id=UUID("20000000-0000-0000-0000-000000000001"),
        report_version=2,
        previous_report_id=parent.id,
        status=import_module(
            "stock_research_agent.domain.reports.reporting"
        ).ResearchReportStatus.REVISED,
    )

    assert module.next_report_version(parent) == 2
    assert module.validate_report_successor(parent, child) is None


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"report_version": 3}, "REPORT_VERSION_NOT_CONTIGUOUS"),
        (
            {"previous_report_id": UUID(int=999)},
            "REPORT_PARENT_MISMATCH",
        ),
        (
            {"report_generation_run_id": UUID(int=999)},
            "REPORT_GENERATION_RUN_MISMATCH",
        ),
        ({"security_id": UUID(int=999)}, "REPORT_SECURITY_MISMATCH"),
        ({"snapshot_id": UUID(int=999)}, "REPORT_SNAPSHOT_MISMATCH"),
        (
            {"input_manifest_checksum": "9" * 64},
            "REPORT_MANIFEST_MISMATCH",
        ),
    ],
)
def test_successor_rejects_context_or_chain_drift(
    updates: dict[str, object],
    code: str,
) -> None:
    module = _module()
    parent = _report()
    child_values: dict[str, object] = {
        "id": UUID("20000000-0000-0000-0000-000000000001"),
        "report_version": 2,
        "previous_report_id": parent.id,
    }
    child_values.update(updates)
    child = _report(**child_values)

    with pytest.raises(module.ReportVersionError) as raised:
        module.validate_report_successor(parent, child)

    assert raised.value.code == code


def test_self_reference_is_rejected() -> None:
    module = _module()
    parent = _report()
    child = _report(
        id=parent.id,
        report_version=2,
        previous_report_id=parent.id,
    )

    with pytest.raises(module.ReportVersionError) as raised:
        module.validate_report_successor(parent, child)

    assert raised.value.code == "REPORT_SELF_REFERENCE"


def test_publishable_seal_cannot_change_any_content_checksum() -> None:
    module = _module()
    reporting = import_module("stock_research_agent.domain.reports.reporting")
    parent = _report()
    valid = _report(
        id=UUID("20000000-0000-0000-0000-000000000001"),
        report_version=2,
        previous_report_id=parent.id,
        status=reporting.ResearchReportStatus.PUBLISHABLE,
    )
    module.validate_report_successor(parent, valid)

    changed = valid.model_copy(update={"markdown_checksum": "9" * 64})
    with pytest.raises(module.ReportVersionError) as raised:
        module.validate_report_successor(parent, changed)
    assert raised.value.code == "PUBLISHABLE_CONTENT_MISMATCH"


def test_initial_report_requires_version_one_and_no_parent() -> None:
    module = _module()

    assert module.validate_initial_report(_report()) is None
    with pytest.raises(module.ReportVersionError):
        module.validate_initial_report(
            _report(
                report_version=2,
                previous_report_id=UUID(int=999),
            )
        )
