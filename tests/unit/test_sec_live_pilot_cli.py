from __future__ import annotations

import json
from uuid import UUID

import pytest
from typer.testing import CliRunner

from stock_research_agent import cli_live

runner = CliRunner()


class _FakeSecPilot:
    def operate(
        self,
        operation: str,
        plan_id: UUID,
        plan_checksum: str,
    ) -> dict[str, object]:
        if operation == "run":
            return {
                "status": "BLOCKED",
                "warning_codes": ["LIVE_TRANSPORT_NOT_CONFIGURED"],
            }
        return {
            "status": "NOT_ATTEMPTED",
            "security": "MU",
            "provider_identifier": "SEC_CIK:723125",
            "plan_id": str(plan_id),
            "plan_checksum": plan_checksum,
        }


def test_sec_pilot_plan_is_offline_and_resolves_exact_mu_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_live, "sec_pilot_application_factory", _FakeSecPilot)
    result = runner.invoke(
        cli_live.live_app,
        ["sec", "plan", str(UUID(int=1)), "a" * 64, "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "NOT_ATTEMPTED"
    assert payload["security"] == "MU"


def test_sec_pilot_run_fails_before_transport_without_gate_b_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_live, "sec_pilot_application_factory", _FakeSecPilot)
    result = runner.invoke(
        cli_live.live_app,
        ["sec", "run", str(UUID(int=1)), "a" * 64, "--json"],
    )

    assert result.exit_code == 3
    assert "LIVE_TRANSPORT_NOT_CONFIGURED" in result.stdout
