from __future__ import annotations

from datetime import UTC, date, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

SECURITY_ID = UUID("00000000-0000-4000-8000-000000000009")
OTHER_SECURITY_ID = UUID("00000000-0000-4000-8000-000000000010")
REQUEST_ID = UUID("00000000-0000-4000-8000-000000000052")
AS_OF = datetime(2026, 7, 29, tzinfo=UTC)


def _adapter_module() -> object:
    return import_module("stock_research_agent.providers.sec_edgar.adapter")


def _adapter() -> object:
    module = _adapter_module()
    return module.SecEdgarAdapter(  # type: ignore[attr-defined]
        security_id=SECURITY_ID,
        cik="0000723125",
        approved_capabilities=(
            module.SecEdgarCapability.COMPANY_FACTS,  # type: ignore[attr-defined]
            module.SecEdgarCapability.FILING_DOCUMENTS,  # type: ignore[attr-defined]
            module.SecEdgarCapability.SUBMISSIONS_METADATA,  # type: ignore[attr-defined]
        ),
        approved_forms=("10-K", "10-Q", "8-K"),
    )


def _request(**changes: object) -> object:
    module = _adapter_module()
    values: dict[str, object] = {
        "sync_request_id": REQUEST_ID,
        "security_id": SECURITY_ID,
        "capability": module.SecEdgarCapability.SUBMISSIONS_METADATA,  # type: ignore[attr-defined]
        "form_filters": ("10-K", "10-Q"),
        "range_start": date(2025, 1, 1),
        "range_end": date(2026, 7, 29),
        "research_as_of_time": AS_OF,
        "checkpoint_revision": 3,
        "max_requests": 2,
        "max_bytes": 2_000_000,
        "documents": (),
    }
    values.update(changes)
    return module.SecEdgarPlanRequest(**values)  # type: ignore[attr-defined]


def test_sec_plan_is_finite_stable_and_source_scoped() -> None:
    adapter = _adapter()
    request = _request()

    first = adapter.plan(request)
    second = adapter.plan(request)

    assert first == second
    assert first.to_write().plan_checksum == second.to_write().plan_checksum
    assert len(first.slices) == 1
    assert first.slices[0].request_parameters == {
        "cik": "0000723125",
        "endpoint_id": "SEC_SUBMISSIONS_JSON",
        "form_filters": ("10-K", "10-Q"),
        "max_response_bytes": 2_000_000,
    }
    assert first.checkpoint_revision == 3


def test_sec_document_plan_is_prebounded_and_stably_ordered() -> None:
    module = _adapter_module()
    adapter = _adapter()
    later = module.SecPlannedDocument(  # type: ignore[attr-defined]
        accession_number="0000723125-26-000015",
        filed_date=date(2026, 6, 25),
        form="10-Q",
        document_path="mu-20260528.htm",
    )
    earlier = module.SecPlannedDocument(  # type: ignore[attr-defined]
        accession_number="0000723125-25-000028",
        filed_date=date(2025, 10, 3),
        form="10-K",
        document_path="mu-20250828.htm",
    )
    request = _request(
        capability=module.SecEdgarCapability.FILING_DOCUMENTS,  # type: ignore[attr-defined]
        documents=(later, earlier),
        max_requests=2,
        max_bytes=4_000_000,
    )

    plan = adapter.plan(request)

    assert tuple(item.slice_id for item in plan.slices) == (
        "SEC_DOCUMENT_0000",
        "SEC_DOCUMENT_0001",
    )
    assert tuple(item.request_parameters["accession_number"] for item in plan.slices) == (
        "0000723125-25-000028",
        "0000723125-26-000015",
    )
    assert all(item.request_parameters["max_response_bytes"] == 2_000_000 for item in plan.slices)


@pytest.mark.parametrize(
    "changes",
    (
        {"security_id": OTHER_SECURITY_ID},
        {"range_start": date(1900, 1, 1), "checkpoint_revision": None},
        {"range_end": date(2026, 7, 30)},
        {"form_filters": ("10-K", "S-1")},
        {"form_filters": ("latest",)},
    ),
)
def test_sec_plan_rejects_wrong_scope_open_history_future_or_forms(
    changes: dict[str, object],
) -> None:
    with pytest.raises((ValueError, ValidationError)):
        _adapter().plan(_request(**changes))


def test_sec_plan_rejects_unsupported_capability() -> None:
    module = _adapter_module()
    adapter = module.SecEdgarAdapter(  # type: ignore[attr-defined]
        security_id=SECURITY_ID,
        cik="0000723125",
        approved_capabilities=(module.SecEdgarCapability.SUBMISSIONS_METADATA,),  # type: ignore[attr-defined]
        approved_forms=("10-K",),
    )

    with pytest.raises(ValueError, match="SEC_CAPABILITY_NOT_APPROVED"):
        adapter.plan(
            _request(
                capability=module.SecEdgarCapability.COMPANY_FACTS,  # type: ignore[attr-defined]
                form_filters=(),
            )
        )


def test_sec_plan_cannot_expand_beyond_request_or_byte_budget() -> None:
    module = _adapter_module()
    document = module.SecPlannedDocument(  # type: ignore[attr-defined]
        accession_number="0000723125-25-000028",
        filed_date=date(2025, 10, 3),
        form="10-K",
        document_path="mu-20250828.htm",
    )

    with pytest.raises(ValueError, match="SEC_REQUEST_BUDGET_EXCEEDED"):
        _adapter().plan(
            _request(
                capability=module.SecEdgarCapability.FILING_DOCUMENTS,  # type: ignore[attr-defined]
                documents=(document,),
                max_requests=0,
            )
        )
    with pytest.raises(ValueError, match="SEC_BYTE_BUDGET_TOO_SMALL"):
        _adapter().plan(
            _request(
                capability=module.SecEdgarCapability.FILING_DOCUMENTS,  # type: ignore[attr-defined]
                documents=(document,),
                max_requests=1,
                max_bytes=0,
            )
        )
