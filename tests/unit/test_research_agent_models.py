from __future__ import annotations

import importlib
import importlib.util

from sqlalchemy import CheckConstraint, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from stock_research_agent.db.base import Base

MODULE = "stock_research_agent.db.models.research_agent"
STAGE7_TABLES = {
    "research_policies",
    "research_requests",
    "research_agent_runs",
    "research_plans",
    "research_steps",
    "research_tool_invocations",
    "research_observations",
    "research_evidence",
    "research_claims",
    "claim_evidence_links",
    "research_packages",
    "research_run_events",
}
EARLIER_TABLES = {
    "markets",
    "exchanges",
    "issuers",
    "securities",
    "data_snapshots",
    "snapshot_items",
    "calculation_runs",
    "derived_metrics",
    "document_versions",
    "citation_anchors",
    "retrieval_runs",
}


def _load() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def test_stage7_defines_exactly_twelve_pluralized_tables_without_removing_history() -> None:
    module = _load()

    assert set(module.STAGE7_MODEL_TABLES) == STAGE7_TABLES
    assert STAGE7_TABLES.issubset(Base.metadata.tables)
    assert EARLIER_TABLES.issubset(Base.metadata.tables)
    assert len(module.STAGE7_MODEL_TABLES) == 12


def test_all_stage7_tables_use_named_uuid_primary_keys_and_restrict_foreign_keys() -> None:
    _load()

    for name in STAGE7_TABLES:
        table = Base.metadata.tables[name]
        assert table.primary_key.name == f"pk_{name}"
        assert tuple(column.name for column in table.primary_key.columns) == ("id",)
        assert isinstance(table.c.id.type, Uuid)
        for foreign_key in table.foreign_keys:
            assert foreign_key.ondelete == "RESTRICT"
            assert foreign_key.constraint.name
        for constraint in table.constraints:
            assert constraint.name is not None


def test_core_uniques_checks_and_indexes_match_query_paths() -> None:
    _load()
    expected_uniques = {
        "research_policies": {"uq_research_policies_version"},
        "research_plans": {"uq_research_plans_run"},
        "research_steps": {
            "uq_research_steps_plan_index",
            "uq_research_steps_plan_key",
        },
        "research_tool_invocations": {"uq_research_tool_invocations_step_attempt"},
        "research_claims": {"uq_research_claims_run_key"},
        "claim_evidence_links": {"uq_claim_evidence_links_pair"},
        "research_packages": {"uq_research_packages_run"},
        "research_run_events": {"uq_research_run_events_sequence"},
    }
    for table_name, names in expected_uniques.items():
        table = Base.metadata.tables[table_name]
        actual = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert names.issubset(actual)

    for name in STAGE7_TABLES:
        table = Base.metadata.tables[name]
        checks = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert checks

    index_names = {
        index.name for name in STAGE7_TABLES for index in Base.metadata.tables[name].indexes
    }
    assert {
        "ix_research_requests_security_as_of",
        "ux_research_agent_runs_reusable_key",
        "ix_research_agent_runs_security_snapshot",
        "ix_research_agent_runs_status",
        "ix_research_steps_plan_index",
        "ix_research_tool_invocations_run",
        "ix_research_observations_run",
        "ux_research_observations_invocation_nonnull",
        "ux_research_observations_component_step",
        "ix_research_evidence_run_type",
        "ix_research_evidence_security_snapshot",
        "ix_research_claims_run_support",
        "ix_claim_evidence_links_claim",
        "ix_claim_evidence_links_evidence",
        "ix_research_run_events_run_sequence",
        "ix_research_run_events_run_created",
    }.issubset(index_names)


def test_jsonb_is_limited_to_bounded_collections_and_payload_summaries() -> None:
    _load()
    json_columns = {
        (table.name, column.name)
        for table in (Base.metadata.tables[name] for name in STAGE7_TABLES)
        for column in table.columns
        if isinstance(column.type, JSONB)
    }

    assert json_columns == {
        ("research_policies", "definition"),
        ("research_requests", "requested_sections"),
        ("research_requests", "requested_budgets"),
        ("research_agent_runs", "budget"),
        ("research_agent_runs", "warning_codes"),
        ("research_plans", "steps"),
        ("research_steps", "dependency_keys"),
        ("research_steps", "input_binding"),
        ("research_tool_invocations", "redacted_input"),
        ("research_observations", "payload"),
        ("research_observations", "warnings"),
        ("research_evidence", "calculation_input_ids"),
        ("research_evidence", "payload"),
        ("research_evidence", "warning_codes"),
        ("research_packages", "sections"),
        ("research_packages", "evidence_ids"),
        ("research_packages", "unsupported_claim_ids"),
        ("research_packages", "conflicting_claim_ids"),
        ("research_packages", "blocked_capabilities"),
        ("research_packages", "warnings"),
        ("research_run_events", "event_metadata"),
    }
