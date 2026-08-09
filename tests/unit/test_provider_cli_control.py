from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from typer.testing import CliRunner

from stock_research_agent import cli_providers
from stock_research_agent.cli import app
from stock_research_agent.cli_providers import ProviderControlCommand
from tests.contract.test_provider_tools import PROVIDER_CODE, RUN_ID, SECURITY_ID

CAPABILITY_CODE = "SEC_SUBMISSIONS_METADATA"
REQUEST_ID = UUID("33333333-3333-4333-8333-333333333333")
PLAN_ID = UUID("44444444-4444-4444-8444-444444444444")
DEFINITION_ID = UUID("55555555-5555-4555-8555-555555555555")
CAPABILITY_ID = UUID("66666666-6666-4666-8666-666666666666")
DEAD_LETTER_ID = UUID("77777777-7777-4777-8777-777777777777")


@dataclass
class _FakeControlApplication:
    commands: list[ProviderControlCommand] = field(default_factory=list)

    def control(self, command: ProviderControlCommand) -> dict[str, object]:
        self.commands.append(command)
        if command.operation == "live-check":
            return {
                "status": "BLOCKED",
                "live_status": "NOT_ATTEMPTED",
                "warning": "LIVE_AUTHORIZATION_REQUIRED",
            }
        return {
            "status": "PLANNED" if command.operation == "sync-plan" else "PASS",
            "operation": command.operation,
        }


def _sync_command(operation: str) -> list[str]:
    return [
        "provider",
        operation,
        PROVIDER_CODE,
        CAPABILITY_CODE,
        "--provider-version",
        "1.0.0",
        "--capability-version",
        "1.0.0",
        "--policy-version",
        "1.0.0",
        "--license-version",
        "1.0.0",
        "--security-id",
        str(SECURITY_ID),
        "--as-of",
        "2026-07-29T00:00:00Z",
        "--range-start",
        "2026-07-01",
        "--range-end",
        "2026-07-29",
        "--max-requests",
        "2",
        "--max-bytes",
        "4096",
        "--max-attempts",
        "1",
        "--max-duration-seconds",
        "30",
        "--confirm",
        "--json",
    ]


def _control_command(operation: str) -> list[str]:
    return [
        "provider",
        operation,
        str(RUN_ID),
        "--sync-request-id",
        str(REQUEST_ID),
        "--sync-plan-id",
        str(PLAN_ID),
        "--provider-definition-id",
        str(DEFINITION_ID),
        "--provider-capability-id",
        str(CAPABILITY_ID),
        "--confirm",
        "--json",
    ]


def test_provider_cli_exposes_all_explicit_control_commands(monkeypatch) -> None:
    fake = _FakeControlApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    result = CliRunner().invoke(app, ["provider", "--help"])

    assert result.exit_code == 0
    for command in (
        "credential-check",
        "sync-plan",
        "sync-run",
        "sync-pause",
        "sync-resume",
        "sync-cancel",
        "repair",
        "live-check",
    ):
        assert command in result.stdout


def test_sync_plan_and_run_require_exact_scope_versions_as_of_budgets_and_confirmation(
    monkeypatch,
) -> None:
    fake = _FakeControlApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    runner = CliRunner()

    plan = runner.invoke(app, _sync_command("sync-plan"))
    run = runner.invoke(app, _sync_command("sync-run"))

    assert plan.exit_code == run.exit_code == 0
    assert [command.operation for command in fake.commands] == ["sync-plan", "sync-run"]
    for command in fake.commands:
        assert command.provider_version == "1.0.0"
        assert command.capability_version == "1.0.0"
        assert command.policy_version == "1.0.0"
        assert command.license_version == "1.0.0"
        assert command.security_id == SECURITY_ID
        assert command.universe_code is None
        assert command.max_requests == 2
        assert command.max_bytes == 4096
        assert command.max_attempts == 1
        assert command.max_duration_seconds == 30
        assert command.confirmed is True


def test_lifecycle_and_repair_commands_bind_exact_persisted_context(monkeypatch) -> None:
    fake = _FakeControlApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    runner = CliRunner()
    results = [
        runner.invoke(app, _control_command(operation))
        for operation in ("sync-pause", "sync-resume", "sync-cancel")
    ]
    repair = runner.invoke(
        app,
        [
            "provider",
            "repair",
            str(DEAD_LETTER_ID),
            "--provider-definition-id",
            str(DEFINITION_ID),
            "--confirm",
            "--json",
        ],
    )

    assert all(result.exit_code == 0 for result in (*results, repair))
    assert all(command.run_id == RUN_ID for command in fake.commands[:3])
    assert fake.commands[3].dead_letter_id == DEAD_LETTER_ID
    assert all(command.provider_definition_id == DEFINITION_ID for command in fake.commands)


def test_credential_check_never_accepts_or_outputs_a_secret(monkeypatch) -> None:
    fake = _FakeControlApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    runner = CliRunner()
    success = runner.invoke(
        app,
        [
            "provider",
            "credential-check",
            PROVIDER_CODE,
            "--provider-version",
            "1.0.0",
            "--confirm",
            "--json",
        ],
    )
    secret = runner.invoke(
        app,
        [
            "provider",
            "credential-check",
            PROVIDER_CODE,
            "--provider-version",
            "1.0.0",
            "--token",
            "do-not-read",
            "--confirm",
        ],
    )

    assert success.exit_code == 0
    assert json.loads(success.stdout)["operation"] == "credential-check"
    assert secret.exit_code != 0
    assert len(fake.commands) == 1


def test_live_check_is_not_attempted_without_separate_authorization(monkeypatch) -> None:
    fake = _FakeControlApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    result = CliRunner().invoke(
        app,
        [
            "provider",
            "live-check",
            PROVIDER_CODE,
            CAPABILITY_CODE,
            "--provider-version",
            "1.0.0",
            "--capability-version",
            "1.0.0",
            "--max-requests",
            "1",
            "--max-bytes",
            "1024",
            "--confirm",
            "--json",
        ],
    )

    assert result.exit_code == 3
    assert json.loads(result.stdout) == {
        "status": "BLOCKED",
        "live_status": "NOT_ATTEMPTED",
        "warning": "LIVE_AUTHORIZATION_REQUIRED",
    }


def test_control_commands_reject_missing_confirmation_future_latest_and_unsafe_inputs(
    monkeypatch,
) -> None:
    fake = _FakeControlApplication()
    monkeypatch.setattr(cli_providers, "application_factory", lambda: fake)
    runner = CliRunner()
    missing_confirmation = _sync_command("sync-run")
    missing_confirmation.remove("--confirm")
    latest = _sync_command("sync-run")
    security_index = latest.index("--security-id")
    latest[security_index : security_index + 2] = ["--universe", "latest"]
    future = _sync_command("sync-run")
    future[future.index("--range-end") + 1] = "2026-07-30"
    excessive = _sync_command("sync-run")
    excessive[excessive.index("--max-requests") + 1] = "10001"
    unsafe = _sync_command("sync-run") + ["--url", "https://example.invalid"]

    results = [
        runner.invoke(app, command)
        for command in (missing_confirmation, latest, future, excessive, unsafe)
    ]

    assert all(result.exit_code != 0 for result in results)
    assert fake.commands == []
