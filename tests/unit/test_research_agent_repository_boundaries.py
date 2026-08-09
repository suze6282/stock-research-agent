from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path("src/stock_research_agent/domain/research_agent/repositories.py")
EXPECTED_METHODS = {
    "ResearchPolicyRepository": {"get_policy", "add_policy"},
    "ResearchRequestRepository": {"add_request"},
    "ResearchRunRepository": {
        "create_run",
        "get_run",
        "find_reusable_run",
        "update_run",
        "append_event",
    },
    "ResearchPlanningRepository": {"add_plan", "add_steps", "get_plan", "list_steps"},
    "ResearchExecutionRepository": {
        "add_invocation",
        "complete_invocation",
        "add_observation",
    },
    "ResearchEvidenceRepository": {"add_evidence", "list_evidence"},
    "ResearchClaimRepository": {"add_claim", "add_links", "complete_claim"},
    "ResearchPackageRepository": {"add_package"},
    "ResearchQueryRepository": {
        "get_run_view",
        "get_plan_view",
        "list_step_views",
        "list_invocation_views",
        "list_evidence_views",
        "list_claim_views",
        "get_package_view",
        "list_event_views",
    },
}
FORBIDDEN_IMPORT_ROOTS = {"sqlalchemy", "fastapi", "typer", "psycopg"}


def test_repository_ports_have_exact_small_surface_without_infrastructure_imports() -> None:
    assert SOURCE.exists()
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    classes = {
        node.name: {child.name for child in node.body if isinstance(child, ast.FunctionDef)}
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
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

    assert {name: classes.get(name) for name in EXPECTED_METHODS} == EXPECTED_METHODS
    assert import_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS)
