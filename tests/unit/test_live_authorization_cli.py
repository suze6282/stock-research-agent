from __future__ import annotations

import json
from uuid import UUID

import pytest
from typer.testing import CliRunner

from stock_research_agent import cli_live

runner = CliRunner()


class _FakeAuthorizationApplication:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID, str | None]] = []

    def plan(self, authorization_id: UUID, checksum: str) -> dict[str, object]:
        self.calls.append(("plan", authorization_id, checksum))
        return {"status": "DRAFT", "authorization_id": str(authorization_id)}

    def show(self, authorization_id: UUID) -> dict[str, object]:
        self.calls.append(("show", authorization_id, None))
        return {"status": "APPROVED", "authorization_id": str(authorization_id)}

    def activate(self, authorization_id: UUID, checksum: str) -> dict[str, object]:
        self.calls.append(("activate", authorization_id, checksum))
        return {"status": "ACTIVE", "authorization_id": str(authorization_id)}

    def revoke(self, authorization_id: UUID, checksum: str) -> dict[str, object]:
        self.calls.append(("revoke", authorization_id, checksum))
        return {"status": "REVOKED", "authorization_id": str(authorization_id)}


def test_authorization_cli_uses_exact_ids_and_checksums(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAuthorizationApplication()
    monkeypatch.setattr(cli_live, "authorization_application_factory", lambda: fake)
    identifier = UUID(int=1)

    result = runner.invoke(
        cli_live.live_app,
        ["authorization", "activate", str(identifier), "a" * 64, "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "ACTIVE"
    assert fake.calls == [("activate", identifier, "a" * 64)]


def test_authorization_cli_help_has_no_implicit_run_or_transport() -> None:
    result = runner.invoke(cli_live.live_app, ["authorization", "--help"])

    assert result.exit_code == 0
    assert all(name in result.stdout for name in ("plan", "show", "activate", "revoke"))
    assert "force" not in result.stdout.lower()
    assert "transport" not in result.stdout.lower()
