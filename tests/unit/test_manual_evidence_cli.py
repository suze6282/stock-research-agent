from __future__ import annotations

import json
from uuid import UUID

import pytest
from typer.testing import CliRunner

from stock_research_agent import cli_evidence

runner = CliRunner()


class _FakeEvidenceApplication:
    def operate(
        self,
        operation: str,
        request_id: UUID,
        value: str | None,
    ) -> dict[str, object]:
        return {
            "operation": operation,
            "request_id": str(request_id),
            "value": value,
            "source_type": "MANUAL_IMPORT",
            "offline": True,
            "not_live": True,
        }


def test_import_file_uses_inbox_relative_name_and_explicit_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_evidence, "evidence_application_factory", _FakeEvidenceApplication)
    result = runner.invoke(
        cli_evidence.evidence_app,
        ["import-file", str(UUID(int=1)), "filing.pdf", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["value"] == "filing.pdf"
    assert payload["offline"] is True
    assert payload["not_live"] is True


def test_import_file_rejects_absolute_or_parent_path() -> None:
    for unsafe in ("../filing.pdf", "C:\\temp\\filing.pdf"):
        result = runner.invoke(
            cli_evidence.evidence_app,
            ["import-file", str(UUID(int=1)), unsafe],
        )
        assert result.exit_code != 0


def test_manual_cli_exposes_separated_review_commands() -> None:
    result = runner.invoke(cli_evidence.evidence_app, ["--help"])
    assert result.exit_code == 0
    for command in ("import-plan", "import-file", "validate", "approve", "reject", "show"):
        assert command in result.stdout
