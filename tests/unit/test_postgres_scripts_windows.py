from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows junction regression")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_NAMES = ("start-postgres.ps1", "stop-postgres.ps1")
JUNCTION_COMPONENTS = ("stock-research-agent", "postgres", "data")


def _create_junction(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"Unable to create junction for regression test: {result.stderr}")


def _build_junction_cluster(tmp_path: Path, component: str) -> tuple[Path, Path]:
    local_appdata = tmp_path / "local"
    project = local_appdata / "stock-research-agent"
    postgres = project / "postgres"
    data = postgres / "data"
    outside = tmp_path / "outside" / component

    if component == "stock-research-agent":
        (outside / "postgres" / "data").mkdir(parents=True)
        (outside / "postgres" / "data" / "PG_VERSION").write_text("17\n", encoding="ascii")
        junction = project
    elif component == "postgres":
        (outside / "data").mkdir(parents=True)
        (outside / "data" / "PG_VERSION").write_text("17\n", encoding="ascii")
        project.mkdir(parents=True)
        junction = postgres
    else:
        outside.mkdir(parents=True)
        (outside / "PG_VERSION").write_text("17\n", encoding="ascii")
        postgres.mkdir(parents=True)
        junction = data

    _create_junction(junction, outside)
    return local_appdata, junction


@pytest.mark.parametrize("script_name", SCRIPT_NAMES)
@pytest.mark.parametrize("component", JUNCTION_COMPONENTS)
def test_scripts_reject_project_path_junction_before_pg_ctl(
    tmp_path: Path,
    script_name: str,
    component: str,
) -> None:
    local_appdata, junction = _build_junction_cluster(tmp_path, component)
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(local_appdata)

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "scripts" / "dev" / script_name),
                "-WhatIf",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        os.rmdir(junction)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Refusing PostgreSQL action through reparse point" in output
    assert "pg_ctl" not in output.lower()
