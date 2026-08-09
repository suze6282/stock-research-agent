from stock_research_agent.db.models.providers import (
    ProviderCacheEntry,
    ProviderIngestionManifest,
    ProviderRawArtifact,
)

EXPECTED_COLUMNS = {
    ProviderRawArtifact: {
        "id",
        "provider_definition_id",
        "provider_capability_id",
        "sync_run_id",
        "request_attempt_id",
        "license_policy_id",
        "source_identity",
        "source_checksum",
        "byte_count",
        "content_type",
        "blob_key",
        "acquired_at",
        "source_published_at",
        "synthetic_status",
        "created_at",
    },
    ProviderIngestionManifest: {
        "id",
        "raw_artifact_id",
        "sync_run_id",
        "adapter_version",
        "parser_version",
        "schema_version",
        "batch_checksum",
        "record_count",
        "source_published_at",
        "warning_codes",
        "synthetic_status",
        "manifest_checksum",
        "created_at",
    },
    ProviderCacheEntry: {
        "id",
        "provider_definition_id",
        "provider_capability_id",
        "license_policy_id",
        "artifact_id",
        "cache_key",
        "expires_at",
        "created_at",
    },
}


def test_provider_artifact_models_have_exact_columns_and_restrict_lineage() -> None:
    for model, expected in EXPECTED_COLUMNS.items():
        table = model.__table__
        assert set(table.columns.keys()) == expected
        assert table.foreign_keys
        assert {foreign_key.ondelete for foreign_key in table.foreign_keys} == {"RESTRICT"}


def test_provider_artifact_models_have_named_integrity_constraints() -> None:
    expected = {
        ProviderRawArtifact: {
            "uq_provider_raw_artifacts_identity",
            "ck_provider_raw_artifacts_checksum",
            "ck_provider_raw_artifacts_size",
            "ck_provider_raw_artifacts_blob_key",
            "ck_provider_raw_artifacts_synthetic",
        },
        ProviderIngestionManifest: {
            "uq_provider_ingestion_manifests_identity",
            "ck_provider_ingestion_manifests_checksums",
            "ck_provider_ingestion_manifests_count",
            "ck_provider_ingestion_manifests_synthetic",
        },
        ProviderCacheEntry: {
            "uq_provider_cache_entries_key",
            "ck_provider_cache_entries_key",
            "ck_provider_cache_entries_expiry",
        },
    }
    for model, required in expected.items():
        assert required.issubset({constraint.name for constraint in model.__table__.constraints})


def test_provider_artifact_models_index_only_real_queries() -> None:
    expected = {
        ProviderRawArtifact: {"ix_provider_raw_artifacts_source_checksum"},
        ProviderIngestionManifest: {"ix_provider_ingestion_manifests_run"},
        ProviderCacheEntry: {"ix_provider_cache_entries_expiry"},
    }
    for model, names in expected.items():
        assert {index.name for index in model.__table__.indexes} == names


def test_blob_key_is_not_named_or_typed_as_an_absolute_storage_path() -> None:
    columns = ProviderRawArtifact.__table__.columns

    assert "blob_key" in columns
    assert "path" not in columns
    assert "storage_path" not in columns
