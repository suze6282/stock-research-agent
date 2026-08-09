from __future__ import annotations

from importlib import import_module

import pytest
from pydantic import ValidationError


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.reflection_policy")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 runtime reflection policy is missing")


class _Repository:
    def __init__(self) -> None:
        self.value: object | None = None
        self.add_calls = 0

    def get_runtime_reflection_policy(self, version: str) -> object | None:
        if self.value is not None and self.value.version == version:
            return self.value
        return None

    def add_runtime_reflection_policy(self, value: object) -> object:
        self.add_calls += 1
        self.value = value
        return value


def test_default_runtime_policy_has_exact_closed_check_set_and_limits() -> None:
    module = _module()

    policy = module.build_default_runtime_reflection_policy()

    assert policy.version == "runtime-report-reflection-v1"
    assert policy.required_checks == tuple(module.RuntimeReflectionCheck)
    assert len(policy.required_checks) == 40
    assert len(set(policy.required_checks)) == 40
    assert policy.severity_threshold is module.ReflectionSeverity.HIGH
    assert policy.max_reflection_rounds == 2
    assert policy.max_revision_rounds == 1
    assert policy.allow_model_reflection is False
    assert policy.require_release_gate is True
    assert len(policy.checksum) == 64


def test_runtime_policy_is_frozen_and_schema_rejects_expansion() -> None:
    module = _module()
    policy = module.build_default_runtime_reflection_policy()

    with pytest.raises(ValidationError, match="Instance is frozen"):
        policy.max_reflection_rounds = 1
    for field, value in (
        ("max_reflection_rounds", 3),
        ("max_revision_rounds", 2),
        ("allow_model_reflection", True),
        ("require_release_gate", False),
        ("severity_threshold", module.ReflectionSeverity.MEDIUM),
        ("required_checks", policy.required_checks[:-1]),
    ):
        with pytest.raises(ValidationError):
            module.RuntimeReflectionPolicyRecord.model_validate(
                {**policy.model_dump(mode="python"), field: value}
            )


def test_runtime_policy_checksum_covers_exact_definition() -> None:
    module = _module()
    policy = module.build_default_runtime_reflection_policy()

    assert policy.checksum == module.report_checksum(
        policy.model_dump(mode="python", exclude={"version", "checksum"})
    )


def test_runtime_policy_seed_is_idempotent_without_overwrite() -> None:
    module = _module()
    repository = _Repository()
    service = module.RuntimeReflectionPolicySeedService(repository)

    first = service.seed_v1()
    second = service.seed_v1()

    assert first.created is True
    assert second.created is False
    assert first.policy == second.policy
    assert repository.add_calls == 1


def test_runtime_policy_seed_rejects_incompatible_existing_version() -> None:
    module = _module()
    repository = _Repository()
    expected = module.build_default_runtime_reflection_policy()
    repository.value = expected.model_copy(update={"checksum": "f" * 64})

    with pytest.raises(module.RuntimeReflectionPolicyError) as raised:
        module.RuntimeReflectionPolicySeedService(repository).seed_v1()

    assert raised.value.code == "RUNTIME_REFLECTION_POLICY_VERSION_CONFLICT"
    assert repository.add_calls == 0
