from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.queries import (
    ReportQueryService,
)
from stock_research_agent.domain.research_agent.schemas import Page, PageRequest
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.permissions import SnapshotBehavior, ToolPermission
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolRegistryError,
    create_final_tool_metadata_registry,
    create_report_tool_registry,
    create_stage8_final_tool_metadata_registry,
    create_tool_metadata_registry,
)
from tests.unit.test_report_reflection_engine import _aggregate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = UUID("81000000-0000-4000-8000-000000000001")
REPORT_TOOL_NAMES = tuple(
    sorted(
        (
            "get_research_report",
            "get_report_sections",
            "get_report_blocks",
            "get_report_claim_bindings",
            "get_report_evidence_bindings",
            "get_report_citations",
            "get_report_reflection_runs",
            "get_report_reflection_findings",
            "get_report_revision_runs",
            "get_report_release_gate",
        )
    )
)
PAGED_REPORT_TOOL_NAMES = (
    "get_report_blocks",
    "get_report_citations",
    "get_report_claim_bindings",
    "get_report_evidence_bindings",
    "get_report_reflection_findings",
    "get_report_reflection_runs",
    "get_report_revision_runs",
    "get_report_sections",
)


class FakeReportQueryRepository:
    def __init__(self, *, exists: bool = True) -> None:
        report, _ = _aggregate()
        self.report = report.report.model_copy(update={"id": REPORT_ID})
        self.exists = exists
        self.calls: list[str] = []

    def get_report_view(self, report_id: UUID) -> object | None:
        self.calls.append("get_report_view")
        return self.report if self.exists and report_id == REPORT_ID else None

    def list_section_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_section_views")
        return Page(
            items=self.report.structured_content.sections[page.offset : page.offset + page.limit],
            limit=page.limit,
            offset=page.offset,
            total=len(self.report.structured_content.sections),
        )

    def list_block_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_block_views")
        blocks = tuple(
            block for section in self.report.structured_content.sections for block in section.blocks
        )
        return Page(
            items=blocks[page.offset : page.offset + page.limit],
            limit=page.limit,
            offset=page.offset,
            total=len(blocks),
        )

    def list_claim_binding_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_claim_binding_views")
        return _empty(page)

    def list_evidence_binding_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_evidence_binding_views")
        return _empty(page)

    def list_citation_binding_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_citation_binding_views")
        return _empty(page)

    def list_reflection_run_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_reflection_run_views")
        return _empty(page)

    def list_finding_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_finding_views")
        return _empty(page)

    def list_revision_views(self, report_id: UUID, page: PageRequest) -> Page[object]:
        self.calls.append("list_revision_views")
        return _empty(page)

    def get_release_gate_view(self, report_id: UUID) -> object | None:
        self.calls.append("get_release_gate_view")
        return {"candidate_report_id": str(report_id), "decision": "PARTIAL"}


def _empty(page: PageRequest) -> Page[object]:
    return Page(items=(), limit=page.limit, offset=page.offset, total=0)


def _registry(
    repository: FakeReportQueryRepository | None = None,
) -> object:
    return create_report_tool_registry(
        ReportQueryService(repository or FakeReportQueryRepository())
    )


def test_report_registry_has_exact_ten_versioned_read_only_offline_tools() -> None:
    registry = _registry()
    metadata = registry.list()

    assert tuple(item.name for item in metadata) == REPORT_TOOL_NAMES
    assert all(item.version == "1.0.0" for item in metadata)
    assert all(item.domain == "reports" for item in metadata)
    assert all(item.permission is ToolPermission.READ_ONLY for item in metadata)
    assert all(item.read_only is True for item in metadata)
    assert all(item.writes is False for item in metadata)
    assert all(item.requires_network is False for item in metadata)
    assert all(item.snapshot_behavior is SnapshotBehavior.PERSISTED_METADATA for item in metadata)


def test_stage7_catalogs_and_manifest_remain_unchanged() -> None:
    baseline = json.loads(
        (PROJECT_ROOT / "docs" / "tool-catalog-stage-7-baseline.json").read_text(encoding="utf-8")
    )
    final = json.loads(
        (PROJECT_ROOT / "docs" / "tool-catalog-stage-7-final.json").read_text(encoding="utf-8")
    )

    assert len(create_tool_metadata_registry().list()) == 22
    assert (
        build_tool_catalog_snapshot(create_final_tool_metadata_registry()).model_dump(mode="json")
        == final
    )
    assert baseline["catalog_checksum"] == (
        "89b3ac1b0b8ca248e9f94385e9eeb08cad4b0f31c4627092298afc02db7e3163"
    )
    assert final["catalog_checksum"] == (
        "b6840728084ce7ea687edd47ec394d44781321fe6136149f3b3f1330e24f7e52"
    )


def test_stage8_final_catalog_is_additive_stable_and_versioned() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "docs" / "tool-catalog-stage-8-final.json").read_text(encoding="utf-8")
    )
    snapshot = build_tool_catalog_snapshot(create_stage8_final_tool_metadata_registry())

    assert snapshot.entry_count == 40
    assert manifest == snapshot.model_dump(mode="json")
    assert set(REPORT_TOOL_NAMES).issubset({entry.tool_name for entry in snapshot.entries})


def test_report_tool_returns_persisted_projection_and_missing_is_safe() -> None:
    found = _registry().execute(
        "get_research_report",
        "1.0.0",
        {"report_id": REPORT_ID},
    )
    payload = found.model_dump(mode="json")

    assert payload["status"] == "PASS"
    assert payload["data"]["id"] == str(REPORT_ID)
    assert payload["data"]["markdown_content"]
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    for forbidden in (
        "database_url",
        "storage_uri",
        "local_path",
        "raw_payload",
        "source_body",
        "authorization",
        "password",
        "traceback",
    ):
        assert forbidden not in serialized

    missing = _registry(FakeReportQueryRepository(exists=False)).execute(
        "get_research_report",
        "1.0.0",
        {"report_id": REPORT_ID},
    )
    assert missing.model_dump(mode="json") == {
        "tool_name": "get_research_report",
        "tool_version": "1.0.0",
        "status": "BLOCKED",
        "data": None,
        "warnings": ["REPORT_RESOURCE_NOT_FOUND"],
    }


@pytest.mark.parametrize(
    "name",
    PAGED_REPORT_TOOL_NAMES + ("get_report_release_gate",),
)
def test_report_tools_reject_unbounded_or_extra_input(name: str) -> None:
    registry = _registry()
    for payload in (
        {"report_id": REPORT_ID, "limit": 101},
        {"report_id": REPORT_ID, "offset": 10_001},
        {
            "report_id": REPORT_ID,
            "limit": 10,
            "sort": "DROP TABLE report_revision_runs",
        },
    ):
        with pytest.raises(ToolRegistryError) as raised:
            registry.execute(name, "1.0.0", payload)
        assert raised.value.code is ToolErrorCode.INVALID_INPUT


def test_each_query_only_reads_one_approved_projection_and_never_writes() -> None:
    repository = FakeReportQueryRepository()
    registry = _registry(repository)

    for name in REPORT_TOOL_NAMES:
        payload: dict[str, object] = {"report_id": REPORT_ID}
        if name not in {"get_research_report", "get_report_release_gate"}:
            payload.update(limit=10, offset=0)
        result = registry.execute(name, "1.0.0", payload)
        assert result.status == "PASS"

    assert repository.calls.count("get_report_view") == 10
    assert len(repository.calls) == 19
    assert all(
        repository.calls.count(call) == 1
        for call in set(repository.calls)
        if call != "get_report_view"
    )
    assert all(call.startswith(("get_", "list_")) for call in repository.calls)


def test_report_registry_exposes_no_workflow_or_provider_tool() -> None:
    names = {item.name for item in _registry().list()}
    forbidden = {
        "generate_report",
        "reflect_report",
        "revise_report",
        "release_check_report",
        "publish_report",
        "refresh_report",
        "get_latest_report",
        "invoke_model",
        "call_provider",
        "get_document_body",
    }

    assert names.isdisjoint(forbidden)
