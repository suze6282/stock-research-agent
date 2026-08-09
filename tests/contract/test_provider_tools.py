from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID

import pytest

from stock_research_agent.domain.providers.queries import ProviderQueryService
from stock_research_agent.domain.research_agent.policies import CONTROLLED_OFFLINE_TOOL_NAMES
from stock_research_agent.domain.research_agent.tool_catalog import build_tool_catalog_snapshot
from stock_research_agent.tools.permissions import SnapshotBehavior, ToolPermission
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolRegistryError,
    create_provider_tool_registry,
    create_stage8_final_tool_metadata_registry,
    create_stage9_final_tool_metadata_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SECURITY_ID = UUID("22222222-2222-4222-8222-222222222222")
PROVIDER_CODE = "SEC_EDGAR_PUBLIC_V1"
PROVIDER_TOOL_NAMES = tuple(
    sorted(
        (
            "get_provider",
            "list_provider_capabilities",
            "get_provider_health",
            "get_provider_license_status",
            "get_provider_sync_run",
            "get_provider_sync_checkpoint",
            "list_provider_raw_artifacts",
            "list_provider_quality_issues",
            "list_provider_dead_letters",
            "get_provider_readiness",
        )
    )
)


class _ProviderQueryRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _one(self, resource_type: str) -> Mapping[str, object]:
        self.calls.append(resource_type)
        return {
            "resource_type": resource_type,
            "values": {"status": "BLOCKED", "provider_code": PROVIDER_CODE},
        }

    def _many(self, resource_type: str) -> tuple[Mapping[str, object], ...]:
        return (self._one(resource_type),)

    def list_provider_views(self, *, limit: int, offset: int) -> tuple[Mapping[str, object], ...]:
        return self._many("PROVIDER")

    def get_provider_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("PROVIDER")

    def list_capability_views(
        self, provider_code: str, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("CAPABILITY")

    def get_policy_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("POLICY")

    def get_license_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("LICENSE")

    def get_health_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("HEALTH")

    def get_circuit_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("CIRCUIT")

    def get_sync_run_view(self, run_id: UUID) -> Mapping[str, object]:
        return self._one("SYNC_RUN")

    def list_attempt_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("ATTEMPT")

    def list_artifact_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("ARTIFACT")

    def list_checkpoint_views(
        self, provider_code: str, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("CHECKPOINT")

    def list_quality_issue_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("QUALITY_ISSUE")

    def list_dead_letter_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("DEAD_LETTER")

    def get_readiness_view(self, security_id: UUID) -> Mapping[str, object]:
        return self._one("READINESS")


def _registry(repository: _ProviderQueryRepository | None = None) -> object:
    return create_provider_tool_registry(
        ProviderQueryService(repository or _ProviderQueryRepository())
    )


def test_provider_registry_has_exact_approved_read_only_offline_tools() -> None:
    metadata = _registry().list()

    assert tuple(item.name for item in metadata) == PROVIDER_TOOL_NAMES
    assert all(item.version == "1.0.0" for item in metadata)
    assert all(item.domain == "provider_governance" for item in metadata)
    assert all(item.permission is ToolPermission.READ_ONLY for item in metadata)
    assert all(item.read_only is True for item in metadata)
    assert all(item.writes is False for item in metadata)
    assert all(item.requires_network is False for item in metadata)
    assert all(item.snapshot_behavior is SnapshotBehavior.PERSISTED_METADATA for item in metadata)


def test_provider_tools_call_only_the_approved_query_service_reads() -> None:
    repository = _ProviderQueryRepository()
    registry = _registry(repository)
    payloads: dict[str, dict[str, object]] = {
        "get_provider": {"provider_code": PROVIDER_CODE},
        "list_provider_capabilities": {"provider_code": PROVIDER_CODE},
        "get_provider_health": {"provider_code": PROVIDER_CODE},
        "get_provider_license_status": {"provider_code": PROVIDER_CODE},
        "get_provider_sync_run": {"run_id": RUN_ID},
        "get_provider_sync_checkpoint": {"provider_code": PROVIDER_CODE},
        "list_provider_raw_artifacts": {"run_id": RUN_ID},
        "list_provider_quality_issues": {"run_id": RUN_ID},
        "list_provider_dead_letters": {"run_id": RUN_ID},
        "get_provider_readiness": {"security_id": SECURITY_ID},
    }

    for name in PROVIDER_TOOL_NAMES:
        result = registry.execute(name, "1.0.0", payloads[name])
        assert result.status == "PASS"

    assert repository.calls == [
        "PROVIDER",
        "HEALTH",
        "LICENSE",
        "READINESS",
        "CHECKPOINT",
        "SYNC_RUN",
        "CAPABILITY",
        "DEAD_LETTER",
        "QUALITY_ISSUE",
        "ARTIFACT",
    ]


@pytest.mark.parametrize("name", PROVIDER_TOOL_NAMES)
def test_provider_tools_reject_extra_mutation_network_and_unbounded_input(name: str) -> None:
    registry = _registry()
    identity = (
        {"run_id": RUN_ID}
        if name
        in {
            "get_provider_sync_run",
            "list_provider_raw_artifacts",
            "list_provider_quality_issues",
            "list_provider_dead_letters",
        }
        else {"security_id": SECURITY_ID}
        if name == "get_provider_readiness"
        else {"provider_code": PROVIDER_CODE}
    )
    invalid_payloads = (
        {**identity, "refresh": True},
        {**identity, "url": "https://example.invalid/private"},
        {**identity, "limit": 101},
        {**identity, "sort": "created_at desc; drop table provider_definitions"},
    )
    for payload in invalid_payloads:
        with pytest.raises(ToolRegistryError) as raised:
            registry.execute(name, "1.0.0", payload)
        assert raised.value.code is ToolErrorCode.INVALID_INPUT


def test_stage9_catalog_is_additive_stable_and_does_not_change_stage8_catalog() -> None:
    stage8_manifest = json.loads(
        (PROJECT_ROOT / "docs" / "tool-catalog-stage-8-final.json").read_text(encoding="utf-8")
    )
    stage9_manifest = json.loads(
        (PROJECT_ROOT / "docs" / "tool-catalog-stage-9-final.json").read_text(encoding="utf-8")
    )
    stage8 = build_tool_catalog_snapshot(create_stage8_final_tool_metadata_registry())
    stage9 = build_tool_catalog_snapshot(create_stage9_final_tool_metadata_registry())

    assert stage8_manifest == stage8.model_dump(mode="json")
    assert stage8.entry_count == 40
    assert stage9_manifest == stage9.model_dump(mode="json")
    assert stage9.entry_count == 50
    assert stage9.catalog_checksum != stage8.catalog_checksum
    assert set(PROVIDER_TOOL_NAMES).issubset({entry.tool_name for entry in stage9.entries})


def test_new_provider_tools_are_not_automatically_allowed_by_existing_research_policy() -> None:
    assert set(PROVIDER_TOOL_NAMES).isdisjoint(CONTROLLED_OFFLINE_TOOL_NAMES)
