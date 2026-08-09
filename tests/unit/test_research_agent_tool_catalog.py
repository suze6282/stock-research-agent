from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

from stock_research_agent.tools.registry import create_tool_metadata_registry

MODULE = "stock_research_agent.domain.research_agent.tool_catalog"
MANIFEST = Path("docs/tool-catalog-stage-7-baseline.json")
EXPECTED_NAMES = (
    "get_calculation_run",
    "get_citation",
    "get_corporate_actions",
    "get_daily_price_history",
    "get_data_snapshot",
    "get_document_chunk",
    "get_document_metadata",
    "get_evidence_bundle",
    "get_financial_metrics",
    "get_financial_periods",
    "get_latest_close",
    "get_metric_detail",
    "get_metric_lineage",
    "get_normalized_financial_facts",
    "get_reported_financial_facts",
    "get_retrieval_run",
    "get_source_document_metadata",
    "list_document_versions",
    "list_snapshot_items",
    "list_source_documents",
    "search_document_chunks",
    "verify_citation",
)


def _build_snapshot() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    module = importlib.import_module(MODULE)
    return module.build_tool_catalog_snapshot(create_tool_metadata_registry())


def test_baseline_catalog_freezes_all_22_tools_and_required_contract_fields() -> None:
    snapshot = _build_snapshot()

    assert tuple(entry.tool_name for entry in snapshot.entries) == EXPECTED_NAMES
    assert snapshot.entry_count == 22
    assert snapshot.catalog_version == f"tool-catalog-v1:{snapshot.catalog_checksum}"
    assert len(snapshot.catalog_checksum) == 64
    for entry in snapshot.entries:
        assert entry.tool_version == "1.0.0"
        assert entry.permission == "READ_ONLY"
        assert entry.read_only is True
        assert entry.writes is False
        assert entry.requires_network is False
        assert len(entry.input_schema_version) == 64
        assert len(entry.output_schema_version) == 64
        assert entry.data_domain


def test_baseline_catalog_is_stable_and_matches_checked_in_manifest() -> None:
    first = _build_snapshot()
    second = _build_snapshot()

    assert first == second
    assert MANIFEST.exists()
    assert json.loads(MANIFEST.read_text(encoding="utf-8")) == first.model_dump(mode="json")
