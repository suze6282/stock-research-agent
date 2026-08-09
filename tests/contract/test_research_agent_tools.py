from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import ResearchRunStatus
from stock_research_agent.domain.research_agent.policies import (
    CONTROLLED_OFFLINE_TOOL_NAMES,
)
from stock_research_agent.domain.research_agent.queries import ResearchAgentQueryService
from stock_research_agent.domain.research_agent.schemas import (
    Page,
    PageRequest,
    ResearchAgentRunRecord,
    RunBudget,
)
from stock_research_agent.tools.permissions import SnapshotBehavior, ToolPermission
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolRegistryError,
    create_final_tool_metadata_registry,
    create_research_agent_tool_registry,
    create_tool_metadata_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_ID = UUID("75000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 7, 24, tzinfo=UTC)
QUERY_TOOL_NAMES = (
    "get_research_agent_run",
    "get_research_claims",
    "get_research_evidence",
    "get_research_package",
    "get_research_plan",
    "get_research_run_events",
    "get_research_steps",
    "get_research_tool_invocations",
)


def _run() -> ResearchAgentRunRecord:
    return ResearchAgentRunRecord(
        id=RUN_ID,
        request_id=UUID("75000000-0000-4000-8000-000000000002"),
        security_id=UUID("75000000-0000-4000-8000-000000000003"),
        snapshot_id=UUID("75000000-0000-4000-8000-000000000004"),
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
            elapsed_seconds=Decimal("1.0"),
        ),
        created_at=NOW,
        updated_at=NOW,
    )


class FakeRepository:
    def __init__(self, *, exists: bool = True) -> None:
        self.exists = exists
        self.run = _run()

    def get_run_view(self, run_id: UUID) -> object | None:
        return self.run if self.exists and run_id == RUN_ID else None

    def get_plan_view(self, run_id: UUID) -> object | None:
        return None

    def list_step_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_invocation_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_evidence_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def list_claim_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)

    def get_package_view(self, run_id: UUID) -> object | None:
        return None

    def list_event_views(self, run_id: UUID, page: PageRequest) -> Page[object]:
        return Page(items=(), limit=page.limit, offset=page.offset, total=0)


def test_query_registry_has_exact_eight_versioned_read_only_offline_tools() -> None:
    registry = create_research_agent_tool_registry(ResearchAgentQueryService(FakeRepository()))
    metadata = registry.list()

    assert tuple(item.name for item in metadata) == QUERY_TOOL_NAMES
    assert all(item.version == "1.0.0" for item in metadata)
    assert all(item.domain == "research_agent" for item in metadata)
    assert all(item.permission is ToolPermission.READ_ONLY for item in metadata)
    assert all(item.read_only is True for item in metadata)
    assert all(item.writes is False for item in metadata)
    assert all(item.requires_network is False for item in metadata)
    assert all(item.snapshot_behavior is SnapshotBehavior.PERSISTED_METADATA for item in metadata)
    assert set(QUERY_TOOL_NAMES).isdisjoint(CONTROLLED_OFFLINE_TOOL_NAMES)


def test_old_22_tool_catalog_remains_byte_stable_and_separate() -> None:
    baseline = json.loads(
        (PROJECT_ROOT / "docs" / "tool-catalog-stage-7-baseline.json").read_text(encoding="utf-8")
    )
    registry_names = tuple(item.name for item in create_tool_metadata_registry().list())

    assert len(baseline["entries"]) == 22
    assert len(registry_names) == 22
    assert registry_names == tuple(entry["tool_name"] for entry in baseline["entries"])
    assert baseline["catalog_checksum"] == (
        "89b3ac1b0b8ca248e9f94385e9eeb08cad4b0f31c4627092298afc02db7e3163"
    )


def test_final_catalog_manifest_has_30_tools_and_a_distinct_stable_checksum() -> None:
    from stock_research_agent.domain.research_agent.tool_catalog import (
        build_tool_catalog_snapshot,
    )

    manifest = json.loads(
        (PROJECT_ROOT / "docs" / "tool-catalog-stage-7-final.json").read_text(encoding="utf-8")
    )
    snapshot = build_tool_catalog_snapshot(create_final_tool_metadata_registry())

    assert manifest == snapshot.model_dump(mode="json")
    assert snapshot.entry_count == 30
    assert snapshot.catalog_checksum == (
        "b6840728084ce7ea687edd47ec394d44781321fe6136149f3b3f1330e24f7e52"
    )
    assert snapshot.catalog_checksum != (
        "89b3ac1b0b8ca248e9f94385e9eeb08cad4b0f31c4627092298afc02db7e3163"
    )


def test_run_tool_returns_bounded_dto_and_missing_run_is_safe_blocked() -> None:
    registry = create_research_agent_tool_registry(ResearchAgentQueryService(FakeRepository()))
    found = registry.execute(
        "get_research_agent_run",
        "1.0.0",
        {"run_id": RUN_ID},
    )
    payload = found.model_dump(mode="json")
    assert payload["status"] == "PASS"
    assert payload["data"]["id"] == str(RUN_ID)
    assert {
        "raw_payload",
        "storage_uri",
        "local_path",
        "database_url",
        "sql",
        "input_body",
        "output_body",
    }.isdisjoint(payload["data"])

    missing = create_research_agent_tool_registry(
        ResearchAgentQueryService(FakeRepository(exists=False))
    ).execute(
        "get_research_agent_run",
        "1.0.0",
        {"run_id": RUN_ID},
    )
    assert missing.model_dump(mode="json") == {
        "tool_name": "get_research_agent_run",
        "tool_version": "1.0.0",
        "status": "BLOCKED",
        "data": None,
        "warnings": ["RESEARCH_RESOURCE_NOT_FOUND"],
    }


@pytest.mark.parametrize(
    "name",
    [
        "get_research_steps",
        "get_research_tool_invocations",
        "get_research_evidence",
        "get_research_claims",
        "get_research_run_events",
    ],
)
def test_page_tools_reject_unbounded_or_extra_input(name: str) -> None:
    registry = create_research_agent_tool_registry(ResearchAgentQueryService(FakeRepository()))
    for payload in (
        {"run_id": RUN_ID, "limit": 101},
        {"run_id": RUN_ID, "offset": 10_001},
        {"run_id": RUN_ID, "limit": 10, "sort": "DROP TABLE"},
    ):
        with pytest.raises(ToolRegistryError) as raised:
            registry.execute(name, "1.0.0", payload)
        assert raised.value.code is ToolErrorCode.INVALID_INPUT


def test_registry_exposes_no_agent_write_or_recursive_execution_tool() -> None:
    names = {
        item.name
        for item in create_research_agent_tool_registry(
            ResearchAgentQueryService(FakeRepository())
        ).list()
    }
    forbidden_fragments = {
        "create",
        "execute",
        "resume",
        "pause",
        "cancel",
        "model",
        "refresh",
        "parse",
        "index",
        "embed",
    }
    assert all(fragment not in name for name in names for fragment in forbidden_fragments)
