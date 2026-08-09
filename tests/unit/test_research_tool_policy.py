from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import (
    ResearchStepStatus,
    ResearchStepType,
)
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    AllowedTool,
    ControlledRunContext,
    ResearchStepDefinition,
    ResearchStepRecord,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    ToolCatalogEntry,
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

MODULE = "stock_research_agent.domain.research_agent.tool_policy"
NOW = datetime(2026, 7, 24, tzinfo=UTC)
RUN_ID = UUID("33333333-3333-4333-8333-333333333333")
CATALOG = build_tool_catalog_snapshot(create_tool_metadata_registry())
POLICY = build_controlled_offline_policy()


def _tool_policy() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _context(**updates: object) -> ControlledRunContext:
    values = {
        "security_id": UUID("11111111-1111-4111-8111-111111111111"),
        "snapshot_id": UUID("22222222-2222-4222-8222-222222222222"),
        "research_as_of_time": NOW,
        "research_agent_run_id": RUN_ID,
        "research_request_id": UUID("44444444-4444-4444-8444-444444444444"),
        "policy_version": POLICY.version,
        "tool_catalog_version": CATALOG.catalog_version,
    }
    values.update(updates)
    return ControlledRunContext.model_validate(values)


def _step(
    tool_name: str | None = "get_data_snapshot",
    tool_version: str | None = "1.0.0",
) -> ResearchStepRecord:
    return ResearchStepRecord(
        id=UUID("55555555-5555-4555-8555-555555555555"),
        run_id=RUN_ID,
        plan_id=UUID("66666666-6666-4666-8666-666666666666"),
        definition=ResearchStepDefinition(
            step_index=1,
            step_key="load_snapshot",
            step_type=ResearchStepType.LOAD_SNAPSHOT,
            title="Load snapshot",
            required=True,
            dependency_keys=("resolve_security",),
            tool_name=tool_name,
            tool_version=tool_version,
            component_name=None if tool_name else "internal-component-v1",
            input_binding={"limit": 1},
            fanout_limit=1,
        ),
        status=ResearchStepStatus.READY,
        created_at=NOW,
        updated_at=NOW,
    )


def _catalog_with(entry: ToolCatalogEntry) -> object:
    return CATALOG.model_copy(
        update={
            "entries": (*CATALOG.entries, entry),
            "entry_count": CATALOG.entry_count + 1,
        }
    )


def test_exact_allowed_read_only_offline_tool_is_authorized() -> None:
    result = (
        _tool_policy()
        .ResearchToolPolicy()
        .authorize(
            _context(),
            _step(),
            CATALOG,
            POLICY,
        )
    )

    assert result.tool_name == "get_data_snapshot"
    assert result.tool_version == "1.0.0"
    assert result.payload == {"limit": 1}
    assert len(result.input_checksum) == 64


@pytest.mark.parametrize(
    ("context", "step", "catalog", "policy", "code"),
    [
        (
            _context(tool_catalog_version="tool-catalog-v1:" + "f" * 64),
            _step(),
            CATALOG,
            POLICY,
            "TOOL_CATALOG_VERSION_MISMATCH",
        ),
        (_context(), _step("get_data", "1.0.0"), CATALOG, POLICY, "TOOL_NOT_IN_CATALOG"),
        (
            _context(),
            _step("get_data_snapshot", "2.0.0"),
            CATALOG,
            POLICY,
            "TOOL_VERSION_NOT_IN_CATALOG",
        ),
        (
            _context(),
            _step(),
            CATALOG,
            POLICY.model_copy(update={"allowed_tools": ()}),
            "TOOL_NOT_ALLOWED_BY_POLICY",
        ),
        (
            _context(),
            _step(),
            CATALOG,
            POLICY.model_copy(
                update={
                    "denied_tools": (
                        AllowedTool(
                            tool_name="get_data_snapshot",
                            tool_version="1.0.0",
                        ),
                    )
                }
            ),
            "TOOL_DENIED_BY_POLICY",
        ),
        (_context(), _step(None, None), CATALOG, POLICY, "STEP_HAS_NO_TOOL"),
    ],
)
def test_authorization_is_exact_and_deny_by_default(
    context: object,
    step: ResearchStepRecord,
    catalog: object,
    policy: object,
    code: str,
) -> None:
    tool_policy = _tool_policy()

    with pytest.raises(tool_policy.ResearchToolAuthorizationError) as raised:
        tool_policy.ResearchToolPolicy().authorize(context, step, catalog, policy)

    assert raised.value.code == code


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("permission", "ADMIN"),
        ("read_only", False),
        ("writes", True),
        ("requires_network", True),
    ],
)
def test_catalog_metadata_cannot_expand_tool_permission(
    field: str,
    value: object,
) -> None:
    tool_policy = _tool_policy()
    original = next(entry for entry in CATALOG.entries if entry.tool_name == "get_data_snapshot")
    unsafe = original.model_copy(update={"tool_name": "unsafe_tool", field: value})
    catalog = _catalog_with(unsafe)
    policy = POLICY.model_copy(
        update={
            "allowed_tools": (
                *POLICY.allowed_tools,
                AllowedTool(tool_name="unsafe_tool", tool_version="1.0.0"),
            )
        }
    )

    with pytest.raises(tool_policy.ResearchToolAuthorizationError) as raised:
        tool_policy.ResearchToolPolicy().authorize(
            _context(),
            _step("unsafe_tool", "1.0.0"),
            catalog,
            policy,
        )

    assert raised.value.code == "TOOL_PERMISSION_DENIED"
