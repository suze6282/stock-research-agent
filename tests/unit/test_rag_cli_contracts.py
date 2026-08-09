from __future__ import annotations

from typer.testing import CliRunner

from stock_research_agent.cli import app

runner = CliRunner()


def test_cli_registers_explicit_document_and_rag_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "documents" in result.stdout
    assert "rag" in result.stdout


def test_explicit_commands_are_honestly_blocked_without_company_body_or_embedding() -> None:
    parse = runner.invoke(app, ["documents", "parse", "601138.SH"])
    assert parse.exit_code != 0
    assert "COMPANY_DOCUMENT_BODY_NOT_AVAILABLE" in parse.stdout

    vector = runner.invoke(app, ["rag", "vector-status"])
    assert vector.exit_code == 0
    assert "EMBEDDING_PROVIDER_NOT_CONFIGURED" in vector.stdout
    assert "BLOCKED" in vector.stdout


def test_rag_help_marks_search_as_explicit_persisted_write() -> None:
    result = runner.invoke(app, ["rag", "search", "--help"])
    assert result.exit_code == 0
    assert "explicit" in result.stdout.casefold()
    assert "network" in result.stdout.casefold()


def test_cli_exposes_document_and_retrieval_inspection_commands() -> None:
    document_help = runner.invoke(app, ["documents", "--help"])
    rag_help = runner.invoke(app, ["rag", "--help"])

    assert document_help.exit_code == 0
    assert {"parse-status", "sections", "chunks", "verify"} <= set(document_help.stdout.split())
    assert rag_help.exit_code == 0
    assert {"vector-index", "citation", "retrieval-run"} <= set(rag_help.stdout.split())
