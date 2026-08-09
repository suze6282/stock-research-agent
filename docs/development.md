# Development workflow

## Repository and runtime

Work only in `<project-root>`. The migrated
Stage 1 documents are historical artifacts; do not modify the resume website or
copy its application files here. Python must be 3.12.x (the project pins
3.12.13), and dependency resolution is locked by `uv.lock`.

```powershell
$env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
python --version
git --version
uv --version
uv sync --frozen --all-groups
```

Use `.env.example` only as a template. `.env` is ignored by Git. Prefer session
environment variables for disposable test values and never paste credentials
into logs or reports.

## API development

Start the project-owned PostgreSQL cluster and export the native URLs from the
README. Apply migrations before starting the server:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev\start-postgres.ps1
uv run stock-research check-config
uv run alembic upgrade head
uv run uvicorn stock_research_agent.main:app --host 127.0.0.1 --port 8000 --reload
```

Liveness proves only that the process can respond. Readiness executes `SELECT 1`
against the configured database and returns 503 without disclosing its URL when
the database is unavailable.

## Change discipline

Write a focused failing test before behavior changes, implement the minimum
change, then run the focused test, Ruff, and mypy. Before handoff, run the full
quality gate in `docs/testing.md` against PostgreSQL 17. Do not use SQLite as
migration or integration evidence.

The current package boundaries under `tools`, `retrieval`, `reflection`, `mcp`,
and `orchestration` deliberately contain no Stage 3 behavior. Adding data
providers, calculations, RAG, agents, reflection, MCP services, a frontend,
queues, model calls, brokers, or trading requires a separately approved stage.

## Docker limitation

The Compose workflow uses its own internal database URL targeting `db:5432` and
requires `stock-research db-upgrade` before starting normal API use. A native
`DATABASE_URL` targeting `127.0.0.1:55432` is deliberately ignored by Compose;
see the root README for `COMPOSE_DATABASE_URL` override rules.

The Stage 2 source machine had no Docker executable. `docker compose config`
therefore could not run. YAML parsing and repository contract tests passed, but
image build, service startup, health, persistence, and shutdown still require a
Docker-enabled host before claiming Docker runtime reproducibility.
