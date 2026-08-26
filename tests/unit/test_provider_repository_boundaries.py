import ast
from pathlib import Path

SOURCE = Path("src/stock_research_agent/domain/providers/repositories.py")
EXPECTED_METHODS = {
    "ProviderDefinitionRepository": {
        "add_definition",
        "get_definition",
        "list_definitions",
    },
    "ProviderGovernanceRepository": {
        "add_capability",
        "add_policy",
        "add_license_policy",
        "add_credential_reference",
        "add_health_snapshot",
        "get_capability",
        "get_policy",
        "get_license_policy",
        "get_credential_reference",
        "get_latest_health_snapshot",
    },
    "ProviderSyncRepository": {
        "create_request",
        "add_plan",
        "create_run",
        "get_run",
        "transition",
        "append_attempt",
        "reserve_attempt",
        "settle_attempt",
        "compare_and_swap_checkpoint",
        "get_checkpoint",
    },
    "ProviderArtifactRepository": {
        "add_artifact",
        "add_artifact_with_id",
        "add_manifest",
        "add_quality_issue",
        "add_dead_letter",
    },
    "ProviderQueryRepository": {
        "list_provider_views",
        "get_provider_view",
        "list_capability_views",
        "get_health_view",
        "get_license_view",
        "get_sync_run_view",
        "list_attempt_views",
        "list_artifact_views",
        "list_quality_issue_views",
        "list_dead_letter_views",
        "get_readiness_view",
    },
}
FORBIDDEN_IMPORT_ROOTS = {
    "sqlalchemy",
    "fastapi",
    "typer",
    "psycopg",
    "httpx",
    "requests",
    "socket",
    "pathlib",
    "os",
}


def test_provider_repository_ports_have_exact_bounded_surface() -> None:
    assert SOURCE.exists(), "Stage 9 Provider repository ports are absent"
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    classes = {
        node.name: {child.name for child in node.body if isinstance(child, ast.FunctionDef)}
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }

    assert {name: classes.get(name) for name in EXPECTED_METHODS} == EXPECTED_METHODS


def test_provider_repository_ports_have_no_framework_or_io_imports() -> None:
    assert SOURCE.exists(), "Stage 9 Provider repository ports are absent"
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    import_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert import_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS)
    assert "Any" not in SOURCE.read_text(encoding="utf-8")
