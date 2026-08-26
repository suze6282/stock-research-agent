from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
MODULE = ROOT / "src/stock_research_agent/providers/sec_edgar/bootstrap.py"


def _tree() -> ast.Module:
    if not MODULE.is_file():
        pytest.fail("SEC Provider bootstrap production module is not implemented", pytrace=False)
    return ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))


def _imports() -> set[str]:
    values: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            values.add(node.module)
    return values


def test_bootstrap_imports_only_definition_and_governance_repositories() -> None:
    imports = _imports()

    assert "stock_research_agent.db.repositories.providers" in imports
    assert "stock_research_agent.db.repositories.live_evidence" not in imports


def test_bootstrap_does_not_import_live_authorization_or_execution_modules() -> None:
    imports = _imports()

    assert not any("live_evidence" in name or "authorization" in name for name in imports)


def test_bootstrap_does_not_import_sync_artifact_terminal_or_transport_owners() -> None:
    imports = _imports()
    forbidden = ("sync", "artifact", "terminal", "http_client", "transport", "credentials")

    assert not any(any(part in name for part in forbidden) for name in imports)


def test_bootstrap_manifest_is_the_only_production_sec_control_plane_payload() -> None:
    tree = _tree()
    exported_manifests = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id.endswith("CONTROL_PLANE_BOOTSTRAP")
    }

    assert exported_manifests == {"SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP"}


def test_tests_reference_production_manifest_instead_of_redeclaring_sec_values() -> None:
    assert (
        importlib.util.find_spec("stock_research_agent.providers.sec_edgar.bootstrap") is not None
    )


def test_alembic_contains_no_sec_business_seed() -> None:
    _tree()
    migrations = ROOT / "migrations/versions"
    contents = "\n".join(path.read_text(encoding="utf-8") for path in migrations.glob("*.py"))

    assert "SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP" not in contents
