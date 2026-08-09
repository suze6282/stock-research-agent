from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

PACKAGE = "stock_research_agent.domain.research_agent"
FORBIDDEN_ROOTS = {"fastapi", "typer", "sqlalchemy", "httpx", "uvicorn"}


def test_research_agent_package_exists_without_infrastructure_imports() -> None:
    spec = importlib.util.find_spec(PACKAGE)

    assert spec is not None

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib, json, sys; "
                f"importlib.import_module({PACKAGE!r}); "
                "print(json.dumps(sorted({name.split('.')[0] for name in sys.modules})))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    imported_roots = set(json.loads(completed.stdout))

    assert imported_roots.isdisjoint(FORBIDDEN_ROOTS)
