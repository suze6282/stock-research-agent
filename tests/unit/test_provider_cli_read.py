from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from typer.testing import CliRunner

from stock_research_agent import cli_providers
from stock_research_agent.cli import app
from stock_research_agent.domain.providers.queries import (
    PageRequest,
    ProviderQueryPage,
    ProviderQueryResource,
    SafeProviderProjection,
)
from tests.contract.test_provider_tools import PROVIDER_CODE, RUN_ID, SECURITY_ID

READ_COMMANDS = (
    "list",
    "show",
    "capabilities",
    "policy",
    "license",
    "health",
    "circuit-status",
    "sync-show",
    "checkpoints",
    "raw-artifacts",
    "quality-issues",
    "dead-letters",
    "readiness",
)


@dataclass
class _FakeProviderCliApplication:
    calls: list[tuple[str, str | UUID | None, PageRequest]] = field(default_factory=list)
    missing: bool = False
    fail: bool = False

    def invoke(
        self,
        operation: str,
        identity: str | UUID | None,
        page: PageRequest,
    ) -> SafeProviderProjection | ProviderQueryPage | None:
        self.calls.append((operation, identity, page))
        if self.fail:
            raise RuntimeError("private database failure")
        if self.missing:
            return None
        projection = SafeProviderProjection(
            resource_type=ProviderQueryResource.PROVIDER,
            values={"provider_code": PROVIDER_CODE, "status": "BLOCKED"},
        )
        if operation in {
            "list",
            "capabilities",
            "checkpoints",
            "raw-artifacts",
            "quality-issues",
            "dead-letters",
        }:
            return ProviderQueryPage(
                items=(projection,),
                limit=page.limit,
                offset=page.offset,
                returned=1,
            )
        return projection


def test_provider_cli_exposes_all_approved_read_commands_and_no_implicit_actions(
    monkeypatch,
) -> None:
    fake = _FakeProviderCliApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    runner = CliRunner()

    result = runner.invoke(app, ["provider", "--help"])

    assert result.exit_code == 0
    assert all(command in result.stdout for command in READ_COMMANDS)
    for forbidden in ("refresh", "probe", "download", "latest", "model", "agent", "report"):
        assert forbidden not in result.stdout.casefold()


def test_provider_cli_read_commands_share_one_safe_query_application(monkeypatch) -> None:
    fake = _FakeProviderCliApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    runner = CliRunner()
    commands = (
        ["provider", "list", "--limit", "10", "--offset", "5", "--json"],
        ["provider", "show", PROVIDER_CODE, "--json"],
        ["provider", "capabilities", PROVIDER_CODE, "--json"],
        ["provider", "policy", PROVIDER_CODE, "--json"],
        ["provider", "license", PROVIDER_CODE, "--json"],
        ["provider", "health", PROVIDER_CODE, "--json"],
        ["provider", "circuit-status", PROVIDER_CODE, "--json"],
        ["provider", "sync-show", str(RUN_ID), "--json"],
        ["provider", "checkpoints", PROVIDER_CODE, "--json"],
        ["provider", "raw-artifacts", str(RUN_ID), "--json"],
        ["provider", "quality-issues", str(RUN_ID), "--json"],
        ["provider", "dead-letters", str(RUN_ID), "--json"],
        ["provider", "readiness", str(SECURITY_ID), "--json"],
    )

    results = [runner.invoke(app, command) for command in commands]

    assert all(result.exit_code == 0 for result in results)
    assert all(json.loads(result.stdout) for result in results)
    assert [call[0] for call in fake.calls] == list(READ_COMMANDS)
    assert fake.calls[0][2] == PageRequest(limit=10, offset=5)
    assert all(call[2].limit <= 100 for call in fake.calls)


def test_provider_cli_human_output_is_safe_and_missing_or_failure_is_nonzero(monkeypatch) -> None:
    runner = CliRunner()
    found = _FakeProviderCliApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: found)
    response = runner.invoke(app, ["provider", "show", PROVIDER_CODE])
    assert response.exit_code == 0
    assert "provider_code" in response.stdout
    assert "BLOCKED" in response.stdout

    missing = _FakeProviderCliApplication(missing=True)
    monkeypatch.setattr(cli_providers, "application_factory", lambda: missing)
    response = runner.invoke(app, ["provider", "show", PROVIDER_CODE, "--json"])
    assert response.exit_code == 3
    assert "not found" in response.stdout.casefold()

    failed = _FakeProviderCliApplication(fail=True)
    monkeypatch.setattr(cli_providers, "application_factory", lambda: failed)
    response = runner.invoke(app, ["provider", "show", PROVIDER_CODE, "--json"])
    assert response.exit_code == 4
    assert "private" not in response.stdout.casefold()
    assert "database" not in response.stdout.casefold()


def test_provider_cli_rejects_unbounded_pagination_and_unapproved_arguments(monkeypatch) -> None:
    fake = _FakeProviderCliApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    runner = CliRunner()

    responses = (
        runner.invoke(app, ["provider", "list", "--limit", "101"]),
        runner.invoke(app, ["provider", "list", "--offset", "100001"]),
        runner.invoke(app, ["provider", "list", "--sort", "created_at desc"]),
        runner.invoke(app, ["provider", "show", PROVIDER_CODE, "--refresh"]),
        runner.invoke(app, ["provider", "sync-show", "not-a-uuid"]),
    )

    assert all(response.exit_code != 0 for response in responses)
    assert fake.calls == []


def test_installed_provider_cli_uses_production_offline_application_factory() -> None:
    assert cli_providers.application_factory.__name__ == "_production_application"
