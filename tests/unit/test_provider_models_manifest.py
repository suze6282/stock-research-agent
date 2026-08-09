import importlib
from types import SimpleNamespace

import pytest
from sqlalchemy import Float
from sqlalchemy.dialects.postgresql import ENUM, JSONB

EXPECTED_MODELS = {
    "ProviderDefinition": "provider_definitions",
    "ProviderCapability": "provider_capabilities",
    "ProviderPolicy": "provider_policies",
    "ProviderLicensePolicy": "provider_license_policies",
    "ProviderCredentialReference": "provider_credential_references",
    "ProviderSyncRequest": "provider_sync_requests",
    "ProviderSyncPlan": "provider_sync_plans",
    "ProviderSyncRun": "provider_sync_runs",
    "ProviderSyncCheckpoint": "provider_sync_checkpoints",
    "ProviderRequestAttempt": "provider_request_attempts",
    "ProviderRawArtifact": "provider_raw_artifacts",
    "ProviderIngestionManifest": "provider_ingestion_manifests",
    "ProviderCacheEntry": "provider_cache_entries",
    "ProviderCircuitBreaker": "provider_circuit_breakers",
    "ProviderDeadLetter": "provider_dead_letters",
    "ProviderDataQualityIssue": "provider_data_quality_issues",
    "ProviderFreshnessPolicy": "provider_freshness_policies",
    "ProviderHealthSnapshot": "provider_health_snapshots",
    "ProviderAuditEvent": "provider_audit_events",
    "ProviderLiveValidationRun": "provider_live_validation_runs",
}
FORBIDDEN_CREDENTIAL_COLUMNS = {
    "value",
    "secret",
    "token",
    "api_key",
    "password",
    "prefix",
    "suffix",
    "hash",
    "cookie",
    "authorization",
}
FORBIDDEN_CATCH_ALL_JSON_COLUMNS = {"payload", "data", "record", "metadata"}


def _models() -> SimpleNamespace:
    try:
        module = importlib.import_module("stock_research_agent.db.models.providers")
    except ModuleNotFoundError:
        pytest.fail("Stage 9 Provider ORM manifest is missing")
    return SimpleNamespace(
        module=module,
        classes={name: getattr(module, name) for name in EXPECTED_MODELS},
    )


def test_provider_model_manifest_has_exact_reviewed_tables_and_purposes() -> None:
    models = _models()

    assert {name: model.__tablename__ for name, model in models.classes.items()} == EXPECTED_MODELS
    assert set(models.module.PROVIDER_TABLE_PURPOSES) == set(EXPECTED_MODELS.values())
    assert all(models.module.PROVIDER_TABLE_PURPOSES.values())
    for model in models.classes.values():
        assert tuple(model.__table__.primary_key.columns.keys()) == ("id",)
        assert model.__table__.primary_key.name == f"pk_{model.__tablename__}"


def test_provider_model_manifest_rejects_unsafe_storage_types_and_deletes() -> None:
    models = _models()

    for model in models.classes.values():
        table = model.__table__
        for column in table.columns:
            assert not isinstance(column.type, (Float, ENUM))
            if isinstance(column.type, JSONB):
                assert column.name not in FORBIDDEN_CATCH_ALL_JSON_COLUMNS
        assert all(foreign_key.ondelete != "CASCADE" for foreign_key in table.foreign_keys)


def test_credential_reference_model_has_no_secret_bearing_column() -> None:
    models = _models()
    columns = set(models.classes["ProviderCredentialReference"].__table__.columns)

    assert columns.isdisjoint(FORBIDDEN_CREDENTIAL_COLUMNS)


def test_model_registry_exports_every_provider_control_plane_model() -> None:
    models = _models()
    registry = importlib.import_module("stock_research_agent.db.models")

    for name, model in models.classes.items():
        assert getattr(registry, name) is model
        assert name in registry.__all__
