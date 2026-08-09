from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import ResearchRunStatus
from stock_research_agent.domain.research_agent.schemas import (
    Page,
    PageRequest,
    ResearchAgentRunRecord,
    RunBudget,
)

MODULE = "stock_research_agent.domain.research_agent.queries"
RUN_ID = UUID("74000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 24, tzinfo=UTC)


def _run() -> ResearchAgentRunRecord:
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=UUID("74000000-0000-4000-8000-000000000002"),
        security_id=UUID("74000000-0000-4000-8000-000000000003"),
        snapshot_id=UUID("74000000-0000-4000-8000-000000000004"),
        research_as_of_time=NOW,
        status=ResearchRunStatus.PARTIAL,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
        tool_catalog_checksum="a" * 64,
        idempotency_key="b" * 64,
        budget=RunBudget(
            max_steps=12,
            max_tool_calls=24,
            max_calls_per_tool=5,
            max_retries_per_step=1,
            max_duration_seconds=120,
            model_token_budget=0,
            consumed_steps=4,
            consumed_tool_calls=2,
            consumed_model_tokens=0,
            elapsed_seconds=Decimal("1.25"),
        ),
        warning_codes=("DOCUMENT_EVIDENCE_BLOCKED",),
        terminal_reason_code="EVIDENCE_INCOMPLETE",
        created_at=NOW,
        updated_at=NOW,
        terminal_at=NOW,
    )


class FakeQueries:
    def __init__(self, *, exists: bool = True) -> None:
        self.exists = exists
        self.calls: list[tuple[object, ...]] = []
        self.run = _run()

    def get_run_view(self, run_id: UUID) -> object | None:
        self.calls.append(("run", run_id))
        return self.run if self.exists else None

    def get_plan_view(self, run_id: UUID) -> object | None:
        self.calls.append(("plan", run_id))
        return {"run_id": str(run_id)} if self.exists else None

    def list_step_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append(("steps", run_id, page))
        return Page(items=({"step_index": 0},), limit=page.limit, offset=page.offset, total=1)

    def list_invocation_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append(("invocations", run_id, page))
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_evidence_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append(("evidence", run_id, page))
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_claim_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append(("claims", run_id, page))
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def get_package_view(self, run_id: UUID) -> object | None:
        self.calls.append(("package", run_id))
        return {"run_id": str(run_id)} if self.exists else None

    def list_event_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append(("events", run_id, page))
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)


def _queries() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def test_eight_methods_are_bounded_read_delegates_with_stable_page_contract() -> None:
    module = _queries()
    repository = FakeQueries()
    service = module.ResearchAgentQueryService(repository)
    page = PageRequest(limit=10, offset=20)

    assert service.get_run(RUN_ID) == repository.run
    assert service.get_plan(RUN_ID) == {"run_id": str(RUN_ID)}
    assert service.list_steps(RUN_ID, page).items == ({"step_index": 0},)
    assert service.list_invocations(RUN_ID, page).total == 0
    assert service.list_evidence(RUN_ID, page).total == 0
    assert service.list_claims(RUN_ID, page).total == 0
    assert service.get_package(RUN_ID) == {"run_id": str(RUN_ID)}
    assert service.list_events(RUN_ID, page).total == 0
    assert repository.calls == [
        ("run", RUN_ID),
        ("plan", RUN_ID),
        ("steps", RUN_ID, page),
        ("invocations", RUN_ID, page),
        ("evidence", RUN_ID, page),
        ("claims", RUN_ID, page),
        ("package", RUN_ID),
        ("events", RUN_ID, page),
    ]


@pytest.mark.parametrize("method", ["get_run", "get_plan", "get_package"])
def test_missing_single_resource_raises_only_fixed_safe_code(method: str) -> None:
    module = _queries()
    service = module.ResearchAgentQueryService(FakeQueries(exists=False))

    with pytest.raises(module.ResearchQueryNotFoundError) as raised:
        getattr(service, method)(RUN_ID)

    assert raised.value.code == "RESEARCH_RESOURCE_NOT_FOUND"
    assert str(raised.value) == "RESEARCH_RESOURCE_NOT_FOUND"


@pytest.mark.parametrize(
    "values",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 10_001},
    ],
)
def test_page_request_rejects_unbounded_or_invalid_ranges(values: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        PageRequest.model_validate(values)


def test_run_projection_has_no_sensitive_or_unbounded_body_fields() -> None:
    payload = _run().model_dump(mode="json")
    forbidden = {
        "raw_payload",
        "document_body",
        "input_body",
        "output_body",
        "storage_uri",
        "local_path",
        "database_url",
        "sql",
        "secret",
        "token",
        "password",
    }
    assert forbidden.isdisjoint(payload)
