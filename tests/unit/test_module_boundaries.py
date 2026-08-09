from __future__ import annotations

import importlib
import subprocess
import sys
from datetime import UTC
from pathlib import Path

import yaml

from stock_research_agent.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "src" / "stock_research_agent"
BOUNDARY_PACKAGES = (
    "domain",
    "domain.common",
    "domain.data_access",
    "infrastructure",
    "orchestration",
    "providers",
    "tools",
    "retrieval",
    "reflection",
    "mcp",
)
FORBIDDEN_STAGE_3_NAMES = {
    "agent",
    "broker",
    "calculation",
    "financials",
    "ingestion",
    "rag",
    "stock",
    "trading",
    "vector",
}
FORBIDDEN_DEPENDENCIES = {
    "anthropic",
    "chromadb",
    "langchain",
    "llama-index",
    "mcp",
    "openai",
    "pinecone",
    "qdrant-client",
    "yfinance",
}


def _env_keys(path: Path) -> set[str]:
    return {
        line.split("=", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_boundary_packages_import_without_heavy_imports_or_output() -> None:
    script = f"""
import importlib
import json
import sys

names = {BOUNDARY_PACKAGES!r}
before = set(sys.modules)
for name in names:
    importlib.import_module(f"stock_research_agent.{{name}}")
loaded = set(sys.modules) - before
heavy = sorted(
    name for name in loaded
    if name.split(".", 1)[0] in {{"alembic", "fastapi", "sqlalchemy", "structlog"}}
)
print(json.dumps(heavy))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stderr == ""
    assert result.stdout.strip() == "[]"


def test_security_domain_imports_without_framework_or_network_modules() -> None:
    script = """
import importlib
import json
import sys

before = set(sys.modules)
for name in (
    "stock_research_agent.domain.securities.enums",
    "stock_research_agent.domain.securities.exceptions",
    "stock_research_agent.domain.securities.normalization",
    "stock_research_agent.domain.securities.schemas",
    "stock_research_agent.domain.securities.repositories",
    "stock_research_agent.domain.securities.resolution",
    "stock_research_agent.domain.securities.seed",
):
    importlib.import_module(name)
loaded = set(sys.modules) - before
forbidden = sorted(
    name for name in loaded
    if name.split(".", 1)[0] in {
        "alembic", "fastapi", "httpx", "openai", "psycopg", "requests", "sqlalchemy"
    }
)
print(json.dumps(forbidden))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stderr == ""
    assert result.stdout.strip() == "[]"


def test_boundaries_contain_only_markers_and_common_foundations() -> None:
    allowed_files = {
        "domain/__init__.py",
        "domain/common/__init__.py",
        "domain/common/clock.py",
        "domain/common/types.py",
        "domain/data_access/__init__.py",
        "domain/data_access/enums.py",
        "domain/data_access/ingestion.py",
        "domain/data_access/provenance.py",
        "domain/data_access/queries.py",
        "domain/data_access/repositories.py",
        "domain/data_access/schemas.py",
        "domain/data_access/snapshots.py",
        "domain/documents/__init__.py",
        "domain/documents/chunking.py",
        "domain/documents/citations.py",
        "domain/documents/enums.py",
        "domain/documents/identity.py",
        "domain/documents/injection.py",
        "domain/documents/mime.py",
        "domain/documents/parsing.py",
        "domain/documents/repositories.py",
        "domain/documents/schemas.py",
        "domain/documents/parsers/__init__.py",
        "domain/documents/parsers/base.py",
        "domain/documents/parsers/html.py",
        "domain/documents/parsers/json.py",
        "domain/documents/parsers/pdf.py",
        "domain/documents/parsers/text.py",
        "domain/providers/__init__.py",
        "domain/providers/artifacts.py",
        "domain/providers/authorization.py",
        "domain/providers/canonical.py",
        "domain/providers/capabilities.py",
        "domain/providers/configuration.py",
        "domain/providers/credentials.py",
        "domain/providers/enums.py",
        "domain/providers/errors.py",
        "domain/providers/freshness.py",
        "domain/providers/health.py",
        "domain/providers/http.py",
        "domain/providers/licenses.py",
        "domain/providers/policies.py",
        "domain/providers/quality.py",
        "domain/providers/queries.py",
        "domain/providers/repositories.py",
        "domain/providers/schemas.py",
        "domain/providers/sync.py",
        "domain/providers/temporal.py",
        "domain/financials/__init__.py",
        "domain/financials/as_of.py",
        "domain/financials/calculation_service.py",
        "domain/financials/calculations.py",
        "domain/financials/concepts.py",
        "domain/financials/enums.py",
        "domain/financials/exceptions.py",
        "domain/financials/formulas.py",
        "domain/financials/mapping.py",
        "domain/financials/normalization.py",
        "domain/financials/periods.py",
        "domain/financials/queries.py",
        "domain/financials/repositories.py",
        "domain/financials/schemas.py",
        "domain/financials/seed.py",
        "domain/financials/units.py",
        "domain/retrieval/__init__.py",
        "domain/retrieval/enums.py",
        "domain/retrieval/evidence.py",
        "domain/retrieval/hybrid.py",
        "domain/retrieval/lexical.py",
        "domain/retrieval/repositories.py",
        "domain/retrieval/schemas.py",
        "domain/retrieval/service.py",
        "domain/retrieval/tokenizer.py",
        "domain/retrieval/vector.py",
        "domain/research_agent/__init__.py",
        "domain/research_agent/application.py",
        "domain/research_agent/budgets.py",
        "domain/research_agent/canonical.py",
        "domain/research_agent/claims.py",
        "domain/research_agent/conflicts.py",
        "domain/research_agent/enums.py",
        "domain/research_agent/evidence.py",
        "domain/research_agent/idempotency.py",
        "domain/research_agent/invocations.py",
        "domain/research_agent/observations.py",
        "domain/research_agent/orchestration.py",
        "domain/research_agent/packages.py",
        "domain/research_agent/planning.py",
        "domain/research_agent/plan_validation.py",
        "domain/research_agent/policies.py",
        "domain/research_agent/providers.py",
        "domain/research_agent/queries.py",
        "domain/research_agent/repositories.py",
        "domain/research_agent/requests.py",
        "domain/research_agent/resume.py",
        "domain/research_agent/schemas.py",
        "domain/research_agent/state_machine.py",
        "domain/research_agent/tool_catalog.py",
        "domain/research_agent/tool_context.py",
        "domain/research_agent/tool_execution.py",
        "domain/research_agent/tool_policy.py",
        "domain/reports/__init__.py",
        "domain/reports/appendices.py",
        "domain/reports/application.py",
        "domain/reports/binding_schemas.py",
        "domain/reports/bindings.py",
        "domain/reports/blocks.py",
        "domain/reports/canonical.py",
        "domain/reports/checksums.py",
        "domain/reports/composition.py",
        "domain/reports/enums.py",
        "domain/reports/formatting.py",
        "domain/reports/generation.py",
        "domain/reports/idempotency.py",
        "domain/reports/input_verification.py",
        "domain/reports/markdown.py",
        "domain/reports/policies.py",
        "domain/reports/providers.py",
        "domain/reports/queries.py",
        "domain/reports/references.py",
        "domain/reports/reflection.py",
        "domain/reports/reflection_policy.py",
        "domain/reports/release_gate.py",
        "domain/reports/rendering.py",
        "domain/reports/reporting.py",
        "domain/reports/repositories.py",
        "domain/reports/requests.py",
        "domain/reports/revision.py",
        "domain/reports/schemas.py",
        "domain/reports/sections.py",
        "domain/reports/templates.py",
        "domain/reports/versioning.py",
        "domain/securities/__init__.py",
        "domain/securities/enums.py",
        "domain/securities/exceptions.py",
        "domain/securities/normalization.py",
        "domain/securities/repositories.py",
        "domain/securities/resolution.py",
        "domain/securities/schemas.py",
        "domain/securities/seed.py",
        "infrastructure/__init__.py",
        "infrastructure/blob_storage.py",
        "infrastructure/provider_artifact_storage.py",
        "orchestration/__init__.py",
        "providers/__init__.py",
        "providers/base.py",
        "providers/blocked.py",
        "providers/bridges/__init__.py",
        "providers/bridges/documents.py",
        "providers/bridges/financials.py",
        "providers/bridges/market_data.py",
        "providers/bridges/security_master.py",
        "providers/cache.py",
        "providers/capabilities.py",
        "providers/circuit_breaker.py",
        "providers/control_plane.py",
        "providers/credentials.py",
        "providers/errors.py",
        "providers/http_client.py",
        "providers/http_policy.py",
        "providers/http_executor.py",
        "providers/http_redaction.py",
        "providers/http_response.py",
        "providers/production_registry.py",
        "providers/rate_limit.py",
        "providers/registry.py",
        "providers/retry.py",
        "providers/fixtures/__init__.py",
        "providers/fixtures/provider.py",
        "providers/fixtures/data/__init__.py",
        "providers/sec_edgar/__init__.py",
        "providers/sec_edgar/adapter.py",
        "providers/sec_edgar/endpoints.py",
        "providers/sec_edgar/schemas.py",
        "providers/tushare/__init__.py",
        "providers/tushare/adapter.py",
        "providers/tushare/endpoints.py",
        "providers/tushare/schemas.py",
        "tools/__init__.py",
        "tools/documents.py",
        "tools/financial_data.py",
        "tools/financials.py",
        "tools/market_data.py",
        "tools/permissions.py",
        "tools/providers.py",
        "tools/rag.py",
        "tools/reports.py",
        "tools/research_agent.py",
        "tools/registry.py",
        "tools/schemas.py",
        "tools/schemas_providers.py",
        "tools/schemas_rag.py",
        "tools/schemas_reports.py",
        "tools/schemas_research_agent.py",
        "tools/snapshots.py",
        "retrieval/__init__.py",
        "reflection/__init__.py",
        "mcp/__init__.py",
    }
    actual_files = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for boundary in {name.split(".", 1)[0] for name in BOUNDARY_PACKAGES}
        for path in (PACKAGE_ROOT / boundary).rglob("*.py")
    }

    assert actual_files == allowed_files
    module_names = {path.stem.lower() for path in PACKAGE_ROOT.rglob("*.py")}
    stage_six_allowed = {"calculation", "financials", "ingestion", "rag", "vector"}
    assert not (module_names & (FORBIDDEN_STAGE_3_NAMES - stage_six_allowed))


def test_example_environment_matches_settings_contract() -> None:
    expected_keys = {name.upper() for name in Settings.model_fields}
    example_keys = _env_keys(PROJECT_ROOT / ".env.example")
    documented_keys = {
        line.removeprefix("- `").split("`", 1)[0]
        for line in (PROJECT_ROOT / "docs" / "configuration.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("- `")
    }

    assert example_keys == expected_keys
    assert documented_keys == expected_keys


def test_project_declares_no_stage_3_dependencies() -> None:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8").lower()

    assert not any(f'"{dependency}' in text for dependency in FORBIDDEN_DEPENDENCIES)


def test_snapshot_routes_do_not_import_private_helpers_from_data_routes() -> None:
    source = (PACKAGE_ROOT / "api" / "routes" / "snapshots.py").read_text(encoding="utf-8")

    assert "stock_research_agent.api.routes.data import" not in source


def test_compose_contract_is_api_and_postgres_17() -> None:
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert set(compose["services"]) == {"api", "db"}
    assert compose["services"]["db"]["image"].startswith("postgres:17")
    assert compose["services"]["api"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert set(compose["volumes"]) == {"postgres_data"}


def test_docker_image_is_locked_non_root_and_health_checked() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.startswith("FROM python:3.12.13-slim")
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER appuser" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/api/v1/health/live" in dockerfile
    assert "STOCK_RESEARCH_ALEMBIC_CONFIG=/app/alembic.ini" in dockerfile


def test_docker_context_excludes_secrets_worktrees_and_local_artifacts() -> None:
    patterns = set((PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())

    assert {
        ".env",
        ".env.*",
        "!.env.example",
        ".git",
        ".venv/",
        "__pycache__/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".superpowers/",
        ".coverage",
        "htmlcov/",
        ".idea/",
        ".vscode/",
    } <= patterns


def test_ci_repeats_all_quality_and_postgres_gates() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "backend-ci.yml").read_text(
        encoding="utf-8"
    )

    for required in (
        "postgres:17",
        "uv sync --frozen --all-groups",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src",
        'uv run pytest -m "not integration"',
        "uv run pytest -m integration tests/integration",
        "uv run alembic upgrade head",
        "uv run alembic downgrade base",
    ):
        assert required in workflow
    assert "OPENAI" not in workflow


def test_native_scripts_are_fixed_to_project_owned_localappdata_cluster() -> None:
    for name in ("start-postgres.ps1", "stop-postgres.ps1"):
        script = (PROJECT_ROOT / "scripts" / "dev" / name).read_text(encoding="utf-8")

        assert "$env:LOCALAPPDATA" in script
        assert "stock-research-agent" in script
        assert "postgres" in script
        assert "data" in script
        assert "Resolve-Path" in script
        assert "OrdinalIgnoreCase" in script
        assert "ShouldProcess" in script
        assert "简历网站" not in script


def test_readme_docker_flow_migrates_and_explains_connection_override() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    configuration = (PROJECT_ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "## Repository layout" in readme
    assert "docker compose run --rm api stock-research db-upgrade" in readme
    assert "COMPOSE_DATABASE_URL" in readme
    assert "COMPOSE_DATABASE_URL" in configuration
    assert "does not consume the native `DATABASE_URL`" in configuration
    assert "${COMPOSE_DATABASE_URL:-" in compose
    assert "STOCK_RESEARCH_ALEMBIC_CONFIG: /app/alembic.ini" in compose


def test_boundary_imports_resolve_to_expected_modules() -> None:
    for name in BOUNDARY_PACKAGES:
        module = importlib.import_module(f"stock_research_agent.{name}")
        assert module.__name__ == f"stock_research_agent.{name}"


def test_system_clock_returns_utc_aware_time() -> None:
    from stock_research_agent.domain.common.clock import SystemClock

    assert SystemClock().now().tzinfo is UTC
