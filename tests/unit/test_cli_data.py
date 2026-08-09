from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from typer.testing import CliRunner

from stock_research_agent import cli
from stock_research_agent.domain.data_access.enums import QualityStatus
from stock_research_agent.tools import registry as tool_registry
from stock_research_agent.tools.schemas import ToolProvenance

runner = CliRunner()


def test_root_help_exposes_exact_stage_four_command_groups() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "data" in result.stdout
    assert "tools" in result.stdout


def test_data_help_exposes_exact_commands_without_live_claims() -> None:
    result = runner.invoke(cli.app, ["data", "--help"])

    assert result.exit_code == 0
    for command in (
        "providers",
        "mappings",
        "ingest",
        "snapshot",
        "latest-close",
        "price-history",
        "financial-facts",
        "documents",
    ):
        assert command in result.stdout
    lowered = result.stdout.lower()
    assert "current data" not in lowered
    assert "live data" not in lowered


def test_ingest_without_fixture_is_blocked_before_settings_or_provider_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stock_research_agent.cli_data as cli_data

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("resource access was not expected")

    monkeypatch.setattr(cli_data, "_load_settings", forbidden)
    monkeypatch.setattr(cli_data, "create_stage1_fixture_registry", forbidden)

    result = runner.invoke(
        cli.app,
        [
            "data",
            "ingest",
            "MU",
            "--category",
            "DAILY_PRICES",
            "--as-of",
            "2026-07-16T00:00:00Z",
        ],
    )

    assert result.exit_code == 5
    assert "BLOCKED" in result.stdout
    assert "LIVE" in result.stdout
    assert "fetch" not in result.stdout.lower()


def test_read_commands_reject_missing_or_conflicting_scope_with_exit_four() -> None:
    missing = runner.invoke(cli.app, ["data", "latest-close", "MU"])
    conflicting = runner.invoke(
        cli.app,
        [
            "data",
            "latest-close",
            "MU",
            "--as-of",
            "2026-07-16T00:00:00Z",
            "--snapshot",
            "40000000-0000-0000-0000-000000000002",
        ],
    )

    assert missing.exit_code == 4
    assert conflicting.exit_code == 4
    assert missing.stdout == "Status: INVALID_INPUT\n"
    assert conflicting.stdout == "Status: INVALID_INPUT\n"


def test_ingest_rejects_naive_as_of_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stock_research_agent.cli_data as cli_data

    monkeypatch.setattr(
        cli_data,
        "_load_settings",
        lambda: (_ for _ in ()).throw(AssertionError("database access was not expected")),
    )

    result = runner.invoke(
        cli.app,
        [
            "data",
            "ingest",
            "MU",
            "--category",
            "DAILY_PRICES",
            "--as-of",
            "2026-07-16T00:00:00",
            "--fixture",
        ],
    )

    assert result.exit_code == 4
    assert result.stdout == "Status: INVALID_INPUT\n"


class _NeverCalledService:
    def __getattr__(self, name: str) -> Callable[..., object]:
        raise AssertionError(f"query service access was not expected: {name}")


def test_metadata_only_registry_has_stage4_and_stage5_tools_without_execution() -> None:
    factory = getattr(tool_registry, "create_tool_metadata_registry", None)
    assert callable(factory)
    registry = factory()

    metadata = registry.list()
    described = tuple(registry.describe(item.name, item.version) for item in metadata)

    assert len(metadata) == 22
    assert metadata == described
    assert all(
        item.read_only and not item.writes and not item.requires_network for item in metadata
    )


def test_tools_list_and_describe_json_need_no_database() -> None:
    import stock_research_agent.cli_tools as cli_tools

    assert not hasattr(cli_tools, "create_tool_registry")

    listed = runner.invoke(cli.app, ["tools", "list", "--json"])
    described = runner.invoke(
        cli.app,
        ["tools", "describe", "get_latest_close", "--json"],
    )

    assert listed.exit_code == 0
    assert len(json.loads(listed.stdout)) == 22
    assert described.exit_code == 0
    assert json.loads(described.stdout)["name"] == "get_latest_close"


def test_tools_describe_unknown_name_is_safe_not_found() -> None:
    result = runner.invoke(cli.app, ["tools", "describe", "not-a-tool"])

    assert result.exit_code == 3
    assert result.stdout == "Tool was not found\n"


@pytest.mark.parametrize(
    "arguments",
    [
        ["data", "mappings"],
        ["data", "ingest", "MU", "--fixture"],
        [
            "data",
            "price-history",
            "MU",
            "--as-of",
            "2026-07-16T00:00:00Z",
            "--limit",
            "101",
        ],
        ["data", "snapshot", "show", "not-a-uuid"],
        ["tools", "describe"],
        ["tools", "describe", "get_latest_close", "--version", "not-semver"],
        ["tools", "describe", "get_latest_close", "--version", "9.9.9"],
    ],
)
def test_stage_four_parser_and_semantic_input_errors_exit_four_without_echoing_values(
    arguments: list[str],
) -> None:
    result = runner.invoke(cli.app, arguments)

    assert result.exit_code == 4
    assert result.stdout == "Status: INVALID_INPUT\n"
    assert result.stderr == ""


def test_existing_security_parser_contract_is_not_globally_changed() -> None:
    result = runner.invoke(cli.app, ["securities", "show", "not-a-uuid"])

    assert result.exit_code == 2


def test_tool_version_validation_preserves_unknown_tool_not_found() -> None:
    result = runner.invoke(
        cli.app,
        ["tools", "describe", "not-a-tool", "--version", "1.0.0"],
    )

    assert result.exit_code == 3
    assert result.stdout == "Tool was not found\n"


@pytest.mark.parametrize(
    ("origin", "access", "live", "warnings"),
    [
        ("FIXTURE", "OFFLINE", "NOT_LIVE", ()),
        ("LIVE", "ONLINE", "LIVE", ()),
        ("MIXED", "MIXED", "MIXED", ("PROVENANCE_MIXED",)),
        ("UNKNOWN", "UNKNOWN", "UNKNOWN", ("PROVENANCE_UNKNOWN",)),
    ],
)
def test_snapshot_payload_uses_read_only_tool_evidence_instead_of_hardcoded_fixture(
    origin: str,
    access: str,
    live: str,
    warnings: tuple[str, ...],
) -> None:
    import stock_research_agent.cli_data as cli_data

    built = SimpleNamespace(
        snapshot=SimpleNamespace(
            id=UUID("40000000-0000-0000-0000-000000000001"),
            security_id=UUID("10000000-0000-0000-0000-000000000001"),
            snapshot_version=1,
        ),
        status="PARTIAL",
        checksum="a" * 64,
        items=(),
        warnings=("SNAPSHOT_PARTIAL",),
    )
    evidence = SimpleNamespace(
        status=QualityStatus.PARTIAL,
        retrieved_at=datetime(2026, 7, 16, tzinfo=UTC),
        warnings=warnings,
        provenance=ToolProvenance(
            data_origin=origin,
            access_mode=access,
            live_status=live,
        ),
    )

    payload = cli_data._snapshot_payload(built, evidence)

    assert payload["data_origin"] == origin
    assert payload["access_mode"] == access
    assert payload["live_status"] == live
    assert payload["retrieved_at"] == "2026-07-16T00:00:00Z"
    assert payload["warnings"] == list(dict.fromkeys(("SNAPSHOT_PARTIAL", *warnings)))
