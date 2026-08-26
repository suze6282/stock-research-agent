from __future__ import annotations

from pathlib import Path

from sqlalchemy import DateTime

from stock_research_agent.db.models.live_evidence import STAGE10_MODEL_TABLES
from stock_research_agent.db.repositories.live_evidence import _QUERY_RESOURCES

ROOT = Path(__file__).resolve().parents[2]


def test_all_stage10_timestamps_are_explicit_timezone_aware() -> None:
    for model in STAGE10_MODEL_TABLES.values():
        for column in model.__table__.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True, f"{model.__tablename__}.{column.name}"


def test_lineage_foreign_keys_and_parent_query_semantics_are_closed() -> None:
    manifest = STAGE10_MODEL_TABLES["evidence_ingestion_manifests"].__table__
    validation = STAGE10_MODEL_TABLES["real_company_validation_runs"].__table__
    assert any(
        fk.target_fullname == "raw_payloads.id" for fk in manifest.c.artifact_id.foreign_keys
    )
    assert any(
        fk.target_fullname == "research_reports.id" for fk in validation.c.report_id.foreign_keys
    )
    assert _QUERY_RESOURCES["list_live_authorization_events"] == (
        "live_authorization_events",
        "authorization_id",
        True,
    )
    assert _QUERY_RESOURCES["list_live_incident_events"] == (
        "live_incident_events",
        "incident_id",
        True,
    )


def test_round_one_has_no_open_critical_or_high_after_remediation() -> None:
    source = (ROOT / "docs" / "reflection" / "stage-10-round-1.md").read_text(encoding="utf-8")
    high_rows = [line for line in source.splitlines() if "| HIGH |" in line]
    critical_rows = [line for line in source.splitlines() if "| CRITICAL |" in line]
    assert high_rows
    assert all("| CLOSED |" in line for line in high_rows)
    assert all("| CLOSED |" in line for line in critical_rows)
