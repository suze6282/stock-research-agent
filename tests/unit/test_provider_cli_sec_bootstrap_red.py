from __future__ import annotations

from typer.testing import CliRunner

from stock_research_agent.cli import app
from tests.support.cli_output import normalize_cli_output

runner = CliRunner()


def test_sec_bootstrap_cli_command_is_narrow_and_explicit() -> None:
    result = runner.invoke(app, ["provider", "bootstrap-sec-control-plane", "--help"])
    help_output = normalize_cli_output(result.stdout)

    assert result.exit_code == 0
    assert "--dry-run" in help_output
    assert "--confirm" in help_output
    assert "--json" in help_output


def test_sec_bootstrap_cli_requires_database_url(monkeypatch: object) -> None:
    result = runner.invoke(app, ["provider", "bootstrap-sec-control-plane", "--dry-run"])

    assert result.exit_code != 0
    assert "DATABASE" in result.stdout.upper()


def test_sec_bootstrap_cli_requires_confirm_for_write() -> None:
    result = runner.invoke(app, ["provider", "bootstrap-sec-control-plane"])

    assert result.exit_code != 0
    assert "CONFIRM" in result.stdout.upper()


def test_sec_bootstrap_cli_has_no_freeze_authorization_or_network_options() -> None:
    result = runner.invoke(app, ["provider", "bootstrap-sec-control-plane", "--help"])
    help_output = normalize_cli_output(result.stdout)
    forbidden = ("credential", "license", "request", "plan", "grant", "approval", "url", "host")

    assert result.exit_code == 0
    assert not any(f"--{name}" in help_output for name in forbidden)
