from stock_research_agent.db.models.providers import (
    ProviderCapability,
    ProviderCredentialReference,
    ProviderDefinition,
    ProviderLicensePolicy,
    ProviderPolicy,
)

EXPECTED_COLUMNS = {
    ProviderDefinition: {
        "id",
        "code",
        "definition_version",
        "adapter_version",
        "display_name",
        "data_domain",
        "definition_status",
        "production_status",
        "official_domains",
        "policy_version",
        "license_policy_version",
        "credential_reference_id",
        "source_register_version",
        "checksum",
        "created_at",
    },
    ProviderCapability: {
        "id",
        "provider_definition_id",
        "code",
        "capability_version",
        "status",
        "data_domain",
        "market_codes",
        "security_types",
        "operations",
        "checksum",
        "created_at",
    },
    ProviderPolicy: {
        "id",
        "provider_definition_id",
        "policy_version",
        "endpoint_policy_version",
        "network_enabled",
        "max_requests",
        "max_response_bytes",
        "max_total_bytes",
        "max_duration_seconds",
        "max_attempts",
        "max_redirects",
        "rate_limit_per_second",
        "retry_base_delay_seconds",
        "cache_enabled",
        "cache_ttl_seconds",
        "retention_days",
        "checksum",
        "created_at",
    },
    ProviderLicensePolicy: {
        "id",
        "provider_definition_id",
        "policy_version",
        "status",
        "acquisition",
        "raw_storage",
        "cache",
        "derived_use",
        "redistribution",
        "retention_days",
        "deletion_required",
        "attribution_required",
        "terms_source_ids",
        "reviewed_at",
        "expires_at",
        "checksum",
        "created_at",
    },
    ProviderCredentialReference: {
        "id",
        "provider_definition_id",
        "reference_version",
        "resolver_kind",
        "declared_name",
        "status",
        "safe_label",
        "checksum",
        "created_at",
    },
}


def test_provider_governance_models_have_exact_columns() -> None:
    for model, expected in EXPECTED_COLUMNS.items():
        assert set(model.__table__.columns.keys()) == expected


def test_provider_governance_models_use_restrictive_foreign_keys() -> None:
    expected_targets = {
        ProviderDefinition: {"provider_credential_references.id"},
        ProviderCapability: {"provider_definitions.id"},
        ProviderPolicy: {"provider_definitions.id"},
        ProviderLicensePolicy: {"provider_definitions.id"},
        ProviderCredentialReference: {"provider_definitions.id"},
    }

    for model, targets in expected_targets.items():
        table = model.__table__
        assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == targets
        assert {foreign_key.ondelete for foreign_key in table.foreign_keys} == {"RESTRICT"}


def test_provider_governance_models_have_named_identity_constraints_and_indexes() -> None:
    expected_constraints = {
        ProviderDefinition: {
            "uq_provider_definitions_identity",
            "ck_provider_definitions_code",
            "ck_provider_definitions_status",
            "ck_provider_definitions_checksum",
        },
        ProviderCapability: {
            "uq_provider_capabilities_identity",
            "ck_provider_capabilities_code",
            "ck_provider_capabilities_status",
            "ck_provider_capabilities_checksum",
        },
        ProviderPolicy: {
            "uq_provider_policies_identity",
            "ck_provider_policies_limits",
            "ck_provider_policies_checksum",
        },
        ProviderLicensePolicy: {
            "uq_provider_license_policies_identity",
            "ck_provider_license_policies_status",
            "ck_provider_license_policies_permissions",
            "ck_provider_license_policies_window",
            "ck_provider_license_policies_checksum",
        },
        ProviderCredentialReference: {
            "uq_provider_credential_references_identity",
            "ck_provider_credential_references_resolver",
            "ck_provider_credential_references_status",
            "ck_provider_credential_references_checksum",
        },
    }
    expected_indexes = {
        ProviderDefinition: {"ix_provider_definitions_code_status"},
        ProviderCapability: {"ix_provider_capabilities_lookup"},
        ProviderPolicy: {"ix_provider_policies_lookup"},
        ProviderLicensePolicy: {"ix_provider_license_policies_lookup"},
        ProviderCredentialReference: {"ix_provider_credential_references_provider"},
    }

    for model, required in expected_constraints.items():
        assert required.issubset({constraint.name for constraint in model.__table__.constraints})
    for model, required in expected_indexes.items():
        assert required == {index.name for index in model.__table__.indexes}


def test_credential_reference_columns_cannot_hold_secret_material() -> None:
    columns = set(ProviderCredentialReference.__table__.columns.keys())

    assert columns.isdisjoint(
        {
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
    )
