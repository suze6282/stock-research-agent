from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.live_evidence.enums import (
    EvidenceSourceType,
    ManualEvidenceSourceType,
    ManualEvidenceState,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.manual import ManualEvidenceService
from stock_research_agent.domain.live_evidence.schemas import (
    ManualEvidenceImportPlanRequest,
    ManualEvidenceReceiveRequest,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus


def _request() -> ManualEvidenceImportPlanRequest:
    return ManualEvidenceImportPlanRequest(
        security_id=uuid4(),
        issuer_id=uuid4(),
        opaque_file_reference="INBOX_FILE_0001",
        original_filename="synthetic-filing.html",
        declared_source_type=ManualEvidenceSourceType.USER_SUPPLIED_UNVERIFIED_DOCUMENT,
        source_description="Synthetic parser contract document.",
        source_url=None,
        document_type="SYNTHETIC_FILING",
        report_period_start=date(2026, 1, 1),
        report_period_end=date(2026, 3, 31),
        source_published_at=datetime(2026, 4, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        language="en",
        acquisition_method="USER_SUPPLIED_LOCAL_FILE",
        declared_content_type="text/html",
        declared_byte_size=128,
        declared_checksum="a" * 64,
        submitted_by="LOCAL_OPERATOR",
        acquisition_kind=EvidenceSourceType.MANUAL_IMPORT,
        synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
        company_evidence_status="NOT_COMPANY_EVIDENCE",
        offline=True,
        not_live=True,
    )


def test_manual_plan_is_frozen_offline_not_live_and_received() -> None:
    request = _request()

    plan = ManualEvidenceService.plan(request)

    assert plan.acquisition_kind is EvidenceSourceType.MANUAL_IMPORT
    assert plan.synthetic_status is ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY
    assert plan.company_evidence_status == "NOT_COMPANY_EVIDENCE"
    assert plan.offline is True
    assert plan.not_live is True
    assert plan.state is ManualEvidenceState.RECEIVED
    assert len(plan.plan_checksum) == 64
    with pytest.raises(ValidationError):
        plan.original_filename = "changed.html"


def test_same_manual_plan_has_stable_checksum() -> None:
    request = _request()

    assert ManualEvidenceService.plan(request).plan_checksum == (
        ManualEvidenceService.plan(request).plan_checksum
    )


@pytest.mark.parametrize(
    "change",
    [
        {"acquisition_kind": EvidenceSourceType.PROVIDER_LIVE},
        {"offline": False},
        {"not_live": False},
        {"company_evidence_status": "COMPANY_EVIDENCE"},
    ],
)
def test_gate_a_manual_plan_rejects_non_offline_or_company_evidence(
    change: dict[str, object],
) -> None:
    request = _request().model_copy(update=change)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.plan(request)

    assert exc_info.value.code == "MANUAL_IMPORT_SCOPE_INVALID"


def test_manual_plan_rejects_unknown_source_type_with_stable_code() -> None:
    request = _request().model_copy(update={"declared_source_type": "UNKNOWN"})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.plan(request)

    assert exc_info.value.code == "MANUAL_SOURCE_TYPE_INVALID"


def test_receive_binds_observed_file_identity_without_a_path() -> None:
    plan = ManualEvidenceService.plan(_request())
    received_at = datetime(2026, 8, 1, 1, tzinfo=UTC)

    record = ManualEvidenceService.receive(
        ManualEvidenceReceiveRequest(
            plan=plan,
            observed_byte_size=plan.declared_byte_size,
            observed_checksum=plan.declared_checksum,
            received_at=received_at,
        )
    )

    assert record.state is ManualEvidenceState.RECEIVED
    assert record.received_at == received_at
    assert not hasattr(record, "absolute_path")


@pytest.mark.parametrize(
    "change",
    [
        {"observed_byte_size": 127},
        {"observed_checksum": "b" * 64},
    ],
)
def test_receive_rejects_identity_mismatch(change: dict[str, object]) -> None:
    plan = ManualEvidenceService.plan(_request())
    receive = ManualEvidenceReceiveRequest(
        plan=plan,
        observed_byte_size=plan.declared_byte_size,
        observed_checksum=plan.declared_checksum,
        received_at=datetime(2026, 8, 1, 1, tzinfo=UTC),
    ).model_copy(update=change)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        ManualEvidenceService.receive(receive)

    assert exc_info.value.code == "MANUAL_IMPORT_SCOPE_INVALID"
