from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_stage_three_security_documents_exist() -> None:
    for relative_path in (
        "docs/security-master.md",
        "docs/security-resolution.md",
        "docs/api.md",
        "docs/database.md",
        "docs/testing.md",
        "README.md",
    ):
        assert (PROJECT_ROOT / relative_path).is_file()


def test_security_master_document_preserves_entity_boundaries_and_seed_facts() -> None:
    text = _read("docs/security-master.md")

    for required in (
        "Issuer ≠ Security",
        "Market ≠ Exchange",
        "SecurityIdentifier",
        "SecurityAlias",
        "ON DELETE RESTRICT",
        "security-master-v0.1.0",
        "601138",
        "MU",
        "unknown",
    ):
        assert required in text


def test_resolution_document_matches_deterministic_contract() -> None:
    text = _read("docs/security-resolution.md")

    priorities = (
        "EXACT_EXCHANGE_SYMBOL",
        "EXACT_IDENTIFIER",
        "EXACT_SYMBOL",
        "EXACT_ALIAS",
        "EXACT_ISSUER_NAME",
        "PREFIX_SUGGESTION",
        "NOT_FOUND",
    )
    positions = [text.index(item) for item in priorities]
    assert positions == sorted(positions)
    for required in (
        "AMBIGUOUS",
        "INVALID_QUERY",
        "inactive alias",
        "DELISTED",
        "不使用大模型",
        "最多 10",
    ):
        assert required in text


def test_api_document_matches_routes_and_http_semantics() -> None:
    text = _read("docs/api.md")

    for required in (
        "GET /api/v1/securities/resolve?query=",
        "GET /api/v1/securities/{security_id}",
        "GET /api/v1/issuers/{issuer_id}",
        "HTTP 200",
        "HTTP 422",
        "HTTP 404",
        "X-Request-ID",
    ):
        assert required in text


def test_readme_and_database_document_runnable_stage_three_commands() -> None:
    readme = _read("README.md")
    database = _read("docs/database.md")

    for required in (
        "stock-research securities seed-v0",
        'stock-research securities resolve "601138"',
        'stock-research securities resolve "Micron Technology"',
    ):
        assert required in readme
    assert "Stage 3 has not started" not in readme
    assert "0002_create_security_master" in database
    assert "Seed data is not stored in Alembic" in database
    assert "uv run alembic downgrade -1" in database


def test_testing_document_and_ci_run_postgres_api_contract() -> None:
    testing = _read("docs/testing.md")
    workflow = _read(".github/workflows/backend-ci.yml")

    command = (
        "uv run pytest -m integration tests/integration "
        "tests/contract/test_security_api_contract.py"
    )
    assert command in testing
    assert command in workflow
    for required in (
        "uv sync --frozen --all-groups",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src",
        "uv run pytest -W error",
    ):
        assert required in testing
