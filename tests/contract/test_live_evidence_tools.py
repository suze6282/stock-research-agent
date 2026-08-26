from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

import pytest
from pydantic import JsonValue

from stock_research_agent.domain.live_evidence.queries import LiveEvidenceQueryService
from stock_research_agent.tools.permissions import SnapshotBehavior, ToolPermission
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolRegistry,
    ToolRegistryError,
    create_live_evidence_tool_registry,
)

NAMES = tuple(
    sorted(
        (
            "get_live_authorization",
            "list_live_authorization_events",
            "list_live_authorization_consumptions",
            "get_live_execution_approval",
            "get_manual_evidence_import",
            "get_evidence_ingestion_manifest",
            "get_real_company_validation_run",
            "list_end_to_end_validations",
            "get_live_incident",
            "list_live_incident_events",
        )
    )
)


class _Repository:
    def query_view(
        self,
        resource_type: str,
        resource_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> Mapping[str, JsonValue] | None:
        return {
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "limit": limit,
            "offset": offset,
        }


def _registry() -> ToolRegistry:
    return create_live_evidence_tool_registry(LiveEvidenceQueryService(_Repository()))


def test_live_evidence_registry_has_exact_ten_read_only_offline_tools() -> None:
    metadata = _registry().list()
    assert tuple(item.name for item in metadata) == NAMES
    assert all(item.permission is ToolPermission.READ_ONLY for item in metadata)
    assert all(item.writes is False and item.requires_network is False for item in metadata)
    assert all(item.snapshot_behavior is SnapshotBehavior.PERSISTED_METADATA for item in metadata)


@pytest.mark.parametrize("name", NAMES)
def test_live_evidence_tools_are_bounded_and_reject_extra_fields(name: str) -> None:
    registry = _registry()
    result = registry.execute(name, "1.0.0", {"resource_id": UUID(int=1), "limit": 10})
    assert result.status == "PASS"
    with pytest.raises(ToolRegistryError) as error:
        registry.execute(name, "1.0.0", {"resource_id": UUID(int=1), "limit": 101})
    assert error.value.code is ToolErrorCode.INVALID_INPUT
    with pytest.raises(ToolRegistryError):
        registry.execute(name, "1.0.0", {"resource_id": UUID(int=1), "url": "x"})
