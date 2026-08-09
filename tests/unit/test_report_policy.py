from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.policies")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 immutable report policy is missing")


class _Repository:
    def __init__(self) -> None:
        self.value: object | None = None
        self.add_calls = 0

    def get_policy(self, version: str) -> object | None:
        if self.value is not None and self.value.version == version:
            return self.value
        return None

    def add_policy(self, value: object) -> object:
        self.add_calls += 1
        self.value = value
        return value


def _services() -> SimpleNamespace:
    module = _module()
    repository = _Repository()
    return SimpleNamespace(
        module=module,
        repository=repository,
        seeds=module.ReportPolicySeedService(repository),
        policies=module.ReportPolicyService(repository),
    )


def test_default_policy_has_exact_allowlists_disclosures_bounds_and_no_models() -> None:
    module = _module()

    policy = module.build_default_report_policy()

    assert policy.version == "verifiable-report-policy-v1"
    assert policy.allowed_report_types == tuple(ReportType)
    assert policy.allowed_locales == tuple(ReportLocale)
    assert policy.allowed_sections == tuple(ReportSection)
    assert policy.include_unsupported_claims is True
    assert policy.include_conflicting_claims is True
    assert policy.include_blocked_capabilities is True
    assert policy.include_data_quality is True
    assert policy.include_limitations is True
    assert policy.require_claim_binding is True
    assert policy.require_evidence_binding is True
    assert policy.require_valid_document_citation is True
    assert policy.allow_synthetic_evidence is False
    assert policy.allow_unknown_published_at is False
    assert policy.max_report_blocks == 300
    assert policy.max_claims_per_block == 20
    assert policy.max_citations_per_block == 20
    assert policy.max_excerpt_length == 1000
    assert policy.max_reflection_rounds == 2
    assert policy.max_revision_rounds == 1
    assert policy.allow_model_narrative is False
    assert policy.allow_model_reflection is False
    assert len(policy.checksum) == 64


def test_policy_seed_is_idempotent_and_does_not_overwrite() -> None:
    services = _services()

    first = services.seeds.seed_v1()
    second = services.seeds.seed_v1()

    assert first.created is True
    assert second.created is False
    assert first.policy == second.policy
    assert services.repository.add_calls == 1


def test_policy_seed_rejects_incompatible_existing_version() -> None:
    services = _services()
    expected = services.module.build_default_report_policy()
    services.repository.value = expected.model_copy(update={"max_excerpt_length": 999})

    with pytest.raises(services.module.ReportPolicyError) as raised:
        services.seeds.seed_v1()

    assert raised.value.code == "REPORT_POLICY_VERSION_CONFLICT"
    assert services.repository.add_calls == 0


def test_require_recomputes_checksum_and_rejects_missing_or_tampered_policy() -> None:
    services = _services()

    with pytest.raises(services.module.ReportPolicyError) as raised:
        services.policies.require("verifiable-report-policy-v1")
    assert raised.value.code == "REPORT_POLICY_NOT_FOUND"

    expected = services.module.build_default_report_policy()
    services.repository.value = expected.model_copy(update={"checksum": "f" * 64})
    with pytest.raises(services.module.ReportPolicyError) as raised:
        services.policies.require(expected.version)
    assert raised.value.code == "REPORT_POLICY_CHECKSUM_MISMATCH"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_report_blocks", 301),
        ("max_claims_per_block", 21),
        ("max_citations_per_block", 21),
        ("max_excerpt_length", 1001),
        ("max_reflection_rounds", 3),
        ("max_revision_rounds", 2),
        ("allow_model_narrative", True),
        ("allow_model_reflection", True),
        ("allow_synthetic_evidence", True),
    ],
)
def test_policy_schema_rejects_expansion_beyond_approved_bounds(
    field: str,
    value: object,
) -> None:
    module = _module()
    policy = module.build_default_report_policy()

    with pytest.raises(ValidationError):
        module.ReportPolicyRecord.model_validate({**policy.model_dump(mode="python"), field: value})
