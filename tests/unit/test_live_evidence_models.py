from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from stock_research_agent.db.models.live_evidence import STAGE10_MODEL_TABLES


def test_stage10_models_cover_exact_registry_with_named_constraints_and_indexes() -> None:
    assert set(STAGE10_MODEL_TABLES) == {
        "live_authorization_grants",
        "live_authorization_events",
        "live_authorization_consumptions",
        "live_execution_approvals",
        "manual_evidence_import_requests",
        "manual_evidence_source_declarations",
        "manual_evidence_validations",
        "manual_evidence_reviews",
        "evidence_ingestion_manifests",
        "ingestion_to_snapshot_bindings",
        "real_company_validation_runs",
        "end_to_end_research_validations",
        "evidence_retention_actions",
        "live_incidents",
        "live_incident_events",
    }
    for model in STAGE10_MODEL_TABLES.values():
        table = model.__table__
        assert table.primary_key.name is not None
        for constraint in table.constraints:
            if isinstance(constraint, (CheckConstraint, UniqueConstraint)):
                assert constraint.name is not None
        assert all(isinstance(index, Index) and index.name for index in table.indexes)


def test_stage10_source_and_lineage_columns_are_explicit() -> None:
    manifests = STAGE10_MODEL_TABLES["evidence_ingestion_manifests"].__table__.c
    bindings = STAGE10_MODEL_TABLES["ingestion_to_snapshot_bindings"].__table__.c
    assert {"source_type", "artifact_id", "security_id", "issuer_id", "manifest_checksum"} <= set(
        manifests.keys()
    )
    assert {"ingestion_manifest_id", "snapshot_id", "binding_checksum"} <= set(bindings.keys())
