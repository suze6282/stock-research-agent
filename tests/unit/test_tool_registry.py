from __future__ import annotations

import importlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import BaseModel

from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.tools.permissions import SnapshotBehavior, ToolPermission
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolMetadata,
    ToolRegistration,
    ToolRegistry,
    ToolRegistryError,
    create_tool_registry,
)
from stock_research_agent.tools.schemas import (
    DailyPriceHistoryEnvelope,
    GetDailyPriceHistoryInput,
    GetLatestCloseInput,
    LatestCloseEnvelope,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TOOLS = (
    "get_corporate_actions",
    "get_daily_price_history",
    "get_data_snapshot",
    "get_latest_close",
    "get_reported_financial_facts",
    "get_source_document_metadata",
    "list_snapshot_items",
    "list_source_documents",
)
EXPECTED_DESCRIPTIONS = {
    "get_corporate_actions": "Read bounded persisted corporate actions.",
    "get_daily_price_history": "Read bounded persisted daily price history.",
    "get_data_snapshot": "Read one exact persisted data snapshot.",
    "get_latest_close": "Read one latest persisted daily close.",
    "get_reported_financial_facts": "Read bounded raw reported financial facts.",
    "get_source_document_metadata": "Read one persisted source-document metadata record.",
    "list_snapshot_items": "List exact bounded public snapshot items.",
    "list_source_documents": "List bounded persisted source-document metadata.",
}


class _NeverCalledService:
    def __getattr__(self, name: str) -> Callable[..., object]:
        raise AssertionError(f"query service access was not expected: {name}")


def _registry() -> ToolRegistry:
    return create_tool_registry(cast(DataAccessQueryService, _NeverCalledService()))


def test_default_registry_has_exactly_eight_stable_read_only_v1_tools() -> None:
    metadata = _registry().list()

    assert tuple(item.name for item in metadata) == EXPECTED_TOOLS
    assert {item.version for item in metadata} == {"1.0.0"}
    assert {item.permission for item in metadata} == {ToolPermission.READ_ONLY}
    assert all(item.read_only for item in metadata)
    assert all(not item.requires_network for item in metadata)
    assert all(not item.writes for item in metadata)
    assert {item.name: item.description for item in metadata} == EXPECTED_DESCRIPTIONS
    assert all(
        unsafe not in item.description.lower()
        for item in metadata
        for unsafe in ("download", "network", "refresh", "write")
    )
    assert {item.snapshot_behavior for item in metadata} == {
        SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        SnapshotBehavior.SNAPSHOT_REQUIRED,
        SnapshotBehavior.PERSISTED_METADATA,
    }


def test_list_and_describe_are_sorted_deterministic_and_do_not_execute_tools() -> None:
    registry = _registry()

    first = registry.list()
    second = registry.list()
    described = tuple(registry.describe(item.name, item.version) for item in first)

    assert first == second == described
    assert tuple((item.name, item.version) for item in first) == tuple(
        sorted((item.name, item.version) for item in first)
    )


def test_registry_rejects_duplicate_name_and_version() -> None:
    registry = _registry()
    existing = registry._registrations[("get_latest_close", "1.0.0")]

    with pytest.raises(ToolRegistryError) as captured:
        registry.register(existing)

    assert captured.value.code is ToolErrorCode.DUPLICATE_TOOL
    assert str(captured.value) == "Tool registration was rejected"


def _latest_close_registration(
    *,
    metadata: ToolMetadata | None = None,
    input_model: type[BaseModel] = GetLatestCloseInput,
    output_model: type[BaseModel] = LatestCloseEnvelope,
) -> ToolRegistration:
    model_metadata = metadata or ToolMetadata(
        name="get_latest_close",
        version="1.0.0",
        domain="market_data",
        description=EXPECTED_DESCRIPTIONS["get_latest_close"],
        input_schema=input_model.model_json_schema(),
        output_schema=output_model.model_json_schema(),
        permission=ToolPermission.READ_ONLY,
        read_only=True,
        requires_network=False,
        writes=False,
        snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
    )
    return ToolRegistration(
        metadata=model_metadata,
        input_model=input_model,
        output_model=output_model,
        handler=cast(Callable[[BaseModel], BaseModel], lambda value: value),
    )


@pytest.mark.parametrize("version", ("1", "1.0", "v1.0.0", "1.0.0-beta", "01.0.0"))
def test_registry_rejects_invalid_semantic_versions(version: str) -> None:
    registration = _latest_close_registration()
    invalid = registration.metadata.model_copy(update={"version": version})

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=invalid))

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION


def test_registry_rejects_schema_and_model_metadata_mismatch() -> None:
    registration = _latest_close_registration()
    mismatched = registration.metadata.model_copy(update={"input_schema": {"type": "object"}})

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=mismatched))

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION


@pytest.mark.parametrize("version", ("1.0.1", "1.1.0", "2.0.0"))
def test_registry_rejects_semantic_versions_other_than_canonical_v1(version: str) -> None:
    registration = _latest_close_registration()
    alternate = registration.metadata.model_copy(update={"version": version})

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=alternate))

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION


def test_registry_rejects_noncanonical_domain_even_when_other_metadata_is_safe() -> None:
    registration = _latest_close_registration()
    alternate = registration.metadata.model_copy(update={"domain": "financial_data"})

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=alternate))

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION


def test_registry_rejects_noncanonical_input_and_output_models_with_matching_schemas() -> None:
    metadata = ToolMetadata(
        name="get_latest_close",
        version="1.0.0",
        domain="market_data",
        description="Read one latest persisted close.",
        input_schema=GetDailyPriceHistoryInput.model_json_schema(),
        output_schema=DailyPriceHistoryEnvelope.model_json_schema(),
        permission=ToolPermission.READ_ONLY,
        read_only=True,
        requires_network=False,
        writes=False,
        snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
    )

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(
            _latest_close_registration(
                metadata=metadata,
                input_model=GetDailyPriceHistoryInput,
                output_model=DailyPriceHistoryEnvelope,
            )
        )

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION


def test_registry_rejects_noncanonical_snapshot_behavior() -> None:
    registration = _latest_close_registration()
    alternate = registration.metadata.model_copy(
        update={"snapshot_behavior": SnapshotBehavior.SNAPSHOT_REQUIRED}
    )

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=alternate))

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION


@pytest.mark.parametrize("name", EXPECTED_TOOLS)
def test_registry_rejects_unsafe_description_for_every_approved_tool(name: str) -> None:
    existing = _registry()._registrations[(name, "1.0.0")]
    unsafe = existing.metadata.model_copy(
        update={
            "description": "Download or refresh over the network and write persisted data.",
        }
    )

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(
            ToolRegistration(
                metadata=unsafe,
                input_model=existing.input_model,
                output_model=existing.output_model,
                handler=existing.handler,
            )
        )

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION
    assert str(captured.value) == "Tool registration was rejected"


def test_registry_rejects_even_safe_noncanonical_description() -> None:
    registration = _latest_close_registration()
    alternate = registration.metadata.model_copy(
        update={"description": "Read the latest persisted daily closing price."}
    )

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=alternate))

    assert captured.value.code is ToolErrorCode.INVALID_REGISTRATION
    assert str(captured.value) == "Tool registration was rejected"


@pytest.mark.parametrize(
    "updates",
    (
        {"permission": ToolPermission.INTERNAL_WRITE},
        {"permission": ToolPermission.ADMIN_ONLY},
        {"permission": ToolPermission.FORBIDDEN_FOR_AGENT},
        {"read_only": False},
        {"requires_network": True},
        {"writes": True},
    ),
)
def test_registry_rejects_every_non_read_only_or_resource_using_registration(
    updates: dict[str, Any],
) -> None:
    registration = _latest_close_registration()
    unsafe = registration.metadata.model_copy(update=updates)

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=unsafe))

    assert captured.value.code is ToolErrorCode.FORBIDDEN_REGISTRATION


@pytest.mark.parametrize(
    "name",
    (
        "refresh_market_data",
        "download_document",
        "build_snapshot",
        "execute_sql",
        "delete_snapshot",
        "agent_run",
    ),
)
def test_registry_rejects_forbidden_or_unapproved_tool_names(name: str) -> None:
    registration = _latest_close_registration()
    forbidden = registration.metadata.model_copy(update={"name": name})

    with pytest.raises(ToolRegistryError) as captured:
        ToolRegistry().register(_latest_close_registration(metadata=forbidden))

    assert captured.value.code is ToolErrorCode.FORBIDDEN_REGISTRATION


def test_registered_json_schemas_are_strict_stable_and_have_no_unsafe_input_controls() -> None:
    forbidden = {
        "download",
        "filesystem",
        "path",
        "provider_command",
        "refresh",
        "sort",
        "sql",
        "url",
        "write",
    }
    for item in _registry().list():
        assert item.input_schema.get("additionalProperties") is False
        assert item.output_schema.get("additionalProperties") is False
        serialized = json.dumps(item.input_schema, sort_keys=True).lower()
        assert not any(value in serialized for value in forbidden)
        assert item.input_schema == json.loads(json.dumps(item.input_schema, sort_keys=True))
        assert item.output_schema == json.loads(json.dumps(item.output_schema, sort_keys=True))


def test_execute_rejects_unknown_and_invalid_input_with_fixed_non_echoing_errors() -> None:
    registry = _registry()
    sentinel = "SECRET_SENTINEL"

    with pytest.raises(ToolRegistryError) as unknown:
        registry.execute("not_registered", "1.0.0", {})
    assert unknown.value.code is ToolErrorCode.TOOL_NOT_FOUND
    assert str(unknown.value) == "Tool was not found"

    with pytest.raises(ToolRegistryError) as invalid:
        registry.execute(
            "get_latest_close",
            "1.0.0",
            {"security_id": sentinel, "refresh": True},
        )
    assert invalid.value.code is ToolErrorCode.INVALID_INPUT
    assert str(invalid.value) == "Tool input was invalid"
    assert sentinel not in str(invalid.value)
    assert sentinel not in repr(invalid.value)


def test_import_list_and_describe_have_no_session_network_or_resource_side_effects() -> None:
    script = """
import json
import socket
import sys

def blocked(*args, **kwargs):
    raise AssertionError("resource access is forbidden")

socket.socket = blocked
before = set(sys.modules)
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.tools.registry import create_tool_registry

class Service:
    def __getattr__(self, name):
        raise AssertionError(name)

registry = create_tool_registry(Service())
registry.list()
for item in registry.list():
    registry.describe(item.name, item.version)
loaded = set(sys.modules) - before
forbidden = sorted(
    name for name in loaded
    if name.split(".", 1)[0] in {
        "alembic", "fastapi", "httpx", "psycopg", "sqlalchemy", "typer"
    }
)
print(json.dumps(forbidden))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stderr == ""
    assert result.stdout.strip() == "[]"


def test_tool_package_contains_only_approved_read_only_implementations() -> None:
    modules = {
        path.stem for path in (PROJECT_ROOT / "src" / "stock_research_agent" / "tools").glob("*.py")
    }
    assert modules == {
        "__init__",
        "documents",
        "financial_data",
        "financials",
        "market_data",
        "permissions",
        "providers",
        "registry",
        "rag",
        "reports",
        "research_agent",
        "schemas",
        "schemas_providers",
        "schemas_rag",
        "schemas_reports",
        "schemas_research_agent",
        "snapshots",
    }
    for name in modules - {"__init__"}:
        module = importlib.import_module(f"stock_research_agent.tools.{name}")
        names = set(module.__dict__)
        assert "Session" not in names
        assert "FastAPI" not in names
        assert "Typer" not in names
        assert "Agent" not in names
