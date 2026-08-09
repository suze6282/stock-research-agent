from stock_research_agent.db.models.providers import (
    ProviderAuditEvent,
    ProviderCircuitBreaker,
    ProviderDataQualityIssue,
    ProviderDeadLetter,
    ProviderFreshnessPolicy,
    ProviderHealthSnapshot,
    ProviderLiveValidationRun,
)

EXPECTED_COLUMNS = {
    ProviderCircuitBreaker: {
        "id",
        "provider_definition_id",
        "provider_capability_id",
        "status",
        "failure_count",
        "opened_at",
        "half_open_probe_at",
        "updated_at",
        "created_at",
    },
    ProviderDeadLetter: {
        "id",
        "sync_run_id",
        "manifest_id",
        "source_identity",
        "status",
        "safe_error_code",
        "safe_detail",
        "created_at",
    },
    ProviderDataQualityIssue: {
        "id",
        "sync_run_id",
        "manifest_id",
        "rule_code",
        "severity",
        "status",
        "safe_detail",
        "created_at",
    },
    ProviderFreshnessPolicy: {
        "id",
        "provider_definition_id",
        "provider_capability_id",
        "market_code",
        "policy_version",
        "expected_delay_seconds",
        "unknown_published_at_status",
        "checksum",
        "created_at",
    },
    ProviderHealthSnapshot: {
        "id",
        "provider_definition_id",
        "status",
        "configuration_status",
        "credential_status",
        "license_status",
        "live_validation_status",
        "limiting_reasons",
        "observed_at",
        "checksum",
        "created_at",
    },
    ProviderAuditEvent: {
        "id",
        "provider_definition_id",
        "sync_run_id",
        "actor_type",
        "action_code",
        "decision_code",
        "safe_summary",
        "event_checksum",
        "created_at",
    },
    ProviderLiveValidationRun: {
        "id",
        "provider_definition_id",
        "provider_capability_id",
        "authorization_id",
        "status",
        "max_requests",
        "max_bytes",
        "consumed_requests",
        "consumed_bytes",
        "expires_at",
        "started_at",
        "completed_at",
        "created_at",
    },
}


def test_provider_operational_models_have_exact_columns_and_restrict_fks() -> None:
    for model, expected in EXPECTED_COLUMNS.items():
        table = model.__table__
        assert set(table.columns.keys()) == expected
        assert {foreign_key.ondelete for foreign_key in table.foreign_keys} <= {"RESTRICT"}


def test_provider_operational_models_have_named_constraints_and_query_indexes() -> None:
    required_constraints = {
        ProviderCircuitBreaker: {
            "uq_provider_circuit_breakers_scope",
            "ck_provider_circuit_breakers_state",
        },
        ProviderDeadLetter: {"ck_provider_dead_letters_status", "ck_provider_dead_letters_safe"},
        ProviderDataQualityIssue: {"ck_provider_data_quality_issues_state"},
        ProviderFreshnessPolicy: {
            "uq_provider_freshness_policies_identity",
            "ck_provider_freshness_policies_bounds",
        },
        ProviderHealthSnapshot: {
            "ck_provider_health_snapshots_states",
            "ck_provider_health_snapshots_checksum",
        },
        ProviderAuditEvent: {"ck_provider_audit_events_checksum", "ck_provider_audit_events_safe"},
        ProviderLiveValidationRun: {
            "ck_provider_live_validation_runs_status",
            "ck_provider_live_validation_runs_budgets",
        },
    }
    for model, required in required_constraints.items():
        assert required.issubset({item.name for item in model.__table__.constraints})
        assert model.__table__.indexes


def test_live_validation_status_default_is_not_attempted() -> None:
    assert ProviderLiveValidationRun.__table__.columns.status.default is not None
    assert ProviderLiveValidationRun.__table__.columns.status.default.arg == "NOT_ATTEMPTED"
