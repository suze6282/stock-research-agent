from __future__ import annotations

from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.offline_pipeline import (
    validate_report_predecessor,
)
from stock_research_agent.domain.reports.reporting import ResearchReportRecord
from tests.unit.test_research_report_aggregate import _record_values


def _report(**updates: object) -> ResearchReportRecord:
    return import_module(
        "stock_research_agent.domain.reports.reporting"
    ).ResearchReportRecord.model_validate(_record_values(**updates))


def test_gate_a_report_successor_requires_new_row_and_exact_predecessor() -> None:
    parent = _report()
    successor = _report(
        id=UUID(int=987),
        report_version=2,
        previous_report_id=parent.id,
    )

    assert validate_report_predecessor(parent, successor).status == "PASS"


def test_gate_a_rejects_overwrite_and_wrong_predecessor() -> None:
    parent = _report()
    overwrite = _report(id=parent.id, report_version=2, previous_report_id=parent.id)
    wrong = _report(id=UUID(int=987), report_version=2, previous_report_id=UUID(int=999))

    with pytest.raises(LiveEvidenceValidationError) as history:
        validate_report_predecessor(parent, overwrite)
    assert history.value.code == "REPORT_HISTORY_MUTATION"

    with pytest.raises(LiveEvidenceValidationError) as mismatch:
        validate_report_predecessor(parent, wrong)
    assert mismatch.value.code == "REPORT_PREDECESSOR_MISMATCH"
