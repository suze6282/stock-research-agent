from stock_research_agent.db.models.providers import (
    ProviderRequestAttempt,
    ProviderSyncCheckpoint,
    ProviderSyncPlan,
    ProviderSyncRequest,
    ProviderSyncRun,
)

EXPECTED_COLUMNS = {
    ProviderSyncRequest: {
        "id",
        "provider_definition_id",
        "provider_capability_id",
        "policy_id",
        "license_policy_id",
        "credential_reference_id",
        "security_id",
        "universe_code",
        "research_as_of_time",
        "range_start",
        "range_end",
        "execution_mode",
        "scope",
        "budget",
        "request_checksum",
        "idempotency_key",
        "created_at",
    },
    ProviderSyncPlan: {
        "id",
        "sync_request_id",
        "adapter_version",
        "checkpoint_revision",
        "slices",
        "slice_count",
        "plan_checksum",
        "created_at",
    },
    ProviderSyncRun: {
        "id",
        "sync_request_id",
        "sync_plan_id",
        "provider_definition_id",
        "provider_capability_id",
        "status",
        "consumed_requests",
        "consumed_bytes",
        "consumed_attempts",
        "started_at",
        "paused_at",
        "completed_at",
        "lease_owner",
        "lease_expires_at",
        "warning_codes",
        "created_at",
    },
    ProviderSyncCheckpoint: {
        "id",
        "provider_definition_id",
        "provider_capability_id",
        "scope_checksum",
        "watermark",
        "revision",
        "updated_at",
        "created_at",
    },
    ProviderRequestAttempt: {
        "id",
        "sync_run_id",
        "slice_id",
        "attempt_number",
        "status",
        "endpoint_id",
        "response_status_code",
        "response_bytes",
        "started_at",
        "completed_at",
        "safe_error_code",
        "created_at",
    },
}


def test_provider_sync_models_have_exact_columns_and_restrict_fks() -> None:
    for model, expected in EXPECTED_COLUMNS.items():
        table = model.__table__
        assert set(table.columns.keys()) == expected
        assert {foreign_key.ondelete for foreign_key in table.foreign_keys} <= {"RESTRICT"}
        assert all(foreign_key.ondelete == "RESTRICT" for foreign_key in table.foreign_keys)


def test_provider_sync_models_have_named_lifecycle_constraints() -> None:
    expected = {
        ProviderSyncRequest: {
            "uq_provider_sync_requests_idempotency",
            "ck_provider_sync_requests_mode",
            "ck_provider_sync_requests_range",
            "ck_provider_sync_requests_checksums",
            "ck_provider_sync_requests_json_bounds",
        },
        ProviderSyncPlan: {
            "uq_provider_sync_plans_identity",
            "ck_provider_sync_plans_slice_count",
            "ck_provider_sync_plans_checksum",
            "ck_provider_sync_plans_json_bound",
        },
        ProviderSyncRun: {
            "uq_provider_sync_runs_identity",
            "ck_provider_sync_runs_status",
            "ck_provider_sync_runs_counters",
            "ck_provider_sync_runs_terminal_time",
        },
        ProviderSyncCheckpoint: {
            "uq_provider_sync_checkpoints_scope",
            "ck_provider_sync_checkpoints_checksum",
            "ck_provider_sync_checkpoints_revision",
        },
        ProviderRequestAttempt: {
            "uq_provider_request_attempts_identity",
            "ck_provider_request_attempts_status",
            "ck_provider_request_attempts_bounds",
            "ck_provider_request_attempts_time",
        },
    }

    for model, required in expected.items():
        assert required.issubset({constraint.name for constraint in model.__table__.constraints})


def test_provider_sync_models_have_only_query_path_indexes() -> None:
    expected = {
        ProviderSyncRequest: {"ix_provider_sync_requests_provider_created"},
        ProviderSyncPlan: {"ix_provider_sync_plans_request"},
        ProviderSyncRun: {"ix_provider_sync_runs_provider_status"},
        ProviderSyncCheckpoint: {"ix_provider_sync_checkpoints_lookup"},
        ProviderRequestAttempt: {"ix_provider_request_attempts_run_order"},
    }

    for model, names in expected.items():
        assert {index.name for index in model.__table__.indexes} == names
