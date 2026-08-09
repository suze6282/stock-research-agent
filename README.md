# Stock Research Agent

An evidence-driven, auditable stock research agent for A-share and U.S. equity research.

Stock Research Agent is a backend research system built around point-in-time data,
controlled tools, explicit evidence, and deterministic release gates. It is not a
"ticker in, GPT opinion out" wrapper: the stable `main` branch contains an offline-first
research pipeline through Stage 9, while Stage 10 remains paused work in progress on a
separate branch.

## Project Overview

The project turns a research request into a traceable set of persisted artifacts:

```text
Research Request
  -> Security Resolution
  -> As-of Snapshot
  -> Controlled Planner
  -> Read-only Tool Catalog
  -> Financial / Document / Retrieval Tools
  -> Evidence Ledger
  -> Claims and Claim-Evidence Validation
  -> Research Package
  -> Verifiable Report
  -> Runtime Reflection
  -> Deterministic Revision
  -> Internal Release Gate
```

The exact implementation is deterministic and model-free today. Production narrative,
reflection-model, embedding, and several Live data providers are deliberately blocked
until their runtime, licensing, and evidence boundaries are approved.

## Why This Project

LLM-generated equity research can mix dates, omit provenance, invent missing numbers,
or call tools without a bounded execution policy. This repository addresses those
failure modes with:

- an explicit `research_as_of_time` and immutable Snapshots;
- normalized financial facts with formula and calculation lineage;
- versioned documents, retrieval runs, citations, and Evidence Bundles;
- a finite Agent Harness with a planner, DAG, tool policy, budgets, and checkpoints;
- Claim-to-Evidence validation before report release;
- bounded Reflection and deterministic Revision;
- Provider capability, license, credential-reference, network, and storage gates;
- honest `PARTIAL`, `BLOCKED`, `NO_EVIDENCE`, and `N/M` outcomes.

## Key Features

- **Security Master:** Market, Exchange, Issuer, Security, Identifier, Alias, and
  deterministic A-share/U.S. symbol resolution.
- **Point-in-time data:** immutable evidence ingestion and Snapshot semantics that
  reject future information.
- **Financial normalization:** canonical concepts, period handling, A-share cumulative
  period decomposition, non-calendar U.S. fiscal years, TTM, Formula Registry, derived
  metrics, and calculation lineage.
- **RAG and citations:** immutable Document Versions, bounded parsing, deterministic
  chunks, lexical retrieval, cache-only vector interfaces, and verifiable citations.
- **Agent Harness:** finite deterministic planning and execution over a fixed read-only
  Tool Catalog, with Evidence, Claims, conflicts, and sealed Research Packages.
- **Verifiable reports:** canonical structured JSON, deterministic Markdown projection,
  evidence bindings, Runtime Reflection, one bounded Revision, and an internal gate.
- **Provider governance:** offline-verified capability, license, policy, credential
  reference, HTTP safety, rate limit, retry, circuit breaker, cache, sync, artifact,
  lineage, quality, health, Tool, API, and CLI contracts.

## Agent Harness

The Agent Harness is the control plane around research execution. It persists a finite
Plan, restricts every Tool by catalog metadata and budget, records tool calls and
Evidence, validates Claims, and seals a Research Package. Agent-visible Tools are
read-only, `writes=false`, and `requires_network=false`; Provider sync, document parsing,
Agent execution, and report generation use separate explicit CLI/application commands.

The stable implementation does not silently fetch data, select a latest Snapshot, call
a model, or turn missing evidence into a complete conclusion.

## Architecture

```text
FastAPI GET API / Typer CLI
             |
Application and orchestration services
             |
Security | Data/Snapshot | Financials | Documents/RAG | Agent | Reports | Providers
             |
SQLAlchemy repositories and PostgreSQL 17
             |
Immutable records, manifests, checksums, lineage, and state machines
```

FastAPI and registered Tools expose bounded persisted reads. Explicit CLI/application
services own controlled writes. PostgreSQL—not SQLite—is the integration baseline.

## Current Development Status

| Scope | Status | Evidence-backed meaning |
|---|---|---|
| Stages 1–8 | **Completed** | Backend foundation through verifiable reports, Runtime Reflection, and Release Gate passed their stage acceptance. |
| Stage 9 — Production Data Provider Governance | **Completed / Conditional Go** | All 77 offline engineering tasks, two Reflection rounds, PostgreSQL checks, and the implementation report are complete and merged into `main`. Live Provider approval is separate and remains conditional or blocked. |
| Stage 10 — Controlled Live Evidence | **Work in Progress / Development Paused** | Implemented on `stage-10/controlled-live-evidence`; Tasks 0–77 and a local WIP checkpoint exist, but Tasks 78–80 and final Gate A acceptance are incomplete. It is not merged into `main`. |

Stage 9 completion does **not** mean production data coverage is complete. SEC Live is
`CONDITIONAL / NOT_ATTEMPTED`; Tushare production access, A-share disclosure bodies,
licensed U.S. EOD, and production embedding remain `BLOCKED` or unselected.

## Tech Stack

- Python `>=3.12,<3.13` (development baseline: Python 3.12.13)
- FastAPI and Uvicorn
- PostgreSQL 17 and psycopg 3
- SQLAlchemy 2 and Alembic
- Pydantic 2 and pydantic-settings
- Typer
- pytest, Ruff, and strict mypy
- uv with `uv.lock`

## Repository layout

```text
stock-research-agent/
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── src/stock_research_agent/
├── tests/
├── migrations/
├── scripts/dev/
└── docs/
    ├── PROJECT_INTRODUCTION.md
    ├── PROJECT_MANUAL.md
    ├── USER_GUIDE.md
    ├── CURRENT_STATUS_AND_ROADMAP.md
    ├── GITHUB_UPLOAD_CHECKLIST.md
    ├── specs/
    ├── plans/
    └── reflection/
```

## Quick Start

Prerequisites: Git, uv, Python 3.12, and PostgreSQL 17. The project includes a
Windows script for its project-owned local PostgreSQL cluster.

```powershell
uv sync --frozen --all-groups
Copy-Item .env.example .env
# Edit .env: choose a local password and an absolute BLOB_STORAGE_ROOT.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev\start-postgres.ps1
uv run stock-research check-config
uv run alembic upgrade head
uv run stock-research version
uv run uvicorn stock_research_agent.main:app --host 127.0.0.1 --port 8000
```

The API is served under `/api/v1`; liveness and database readiness are available at
`/api/v1/health/live` and `/api/v1/health/ready`. See the [User Guide](docs/USER_GUIDE.md)
before running database-backed commands.

## Example Workflow

The stable branch supports explicit offline workflows such as:

```powershell
uv run stock-research securities seed-v0
uv run stock-research securities resolve "601138"
uv run stock-research securities resolve "Micron Technology"
uv run stock-research securities resolve "MU" --json
uv run stock-research tools list --json
```

The Stage 3 resolver establishes identity before later data boundaries operate on
persisted evidence. The Public Export's SEC/SSE/Nasdaq Synthetic Fixtures use
deliberately fictitious identities and are exercised through the isolated test suite;
they are not added to the stable Security Master seed or presented as a Live-data Quick
Start.

Stage 4 exposes the explicit `data ingest`, `data snapshot create`, and `tools list`
boundaries. Running the first two requires a compatible persisted security and reviewed
offline input; their presence does not authorize Live access or turn Synthetic Fixtures
into company evidence.

Snapshot-dependent financial, RAG, Agent, and report commands require explicit
persisted IDs; they do not use an implicit latest-data shortcut.

Stage 5 financial commands are explicit writes or bounded reads over one persisted
Snapshot:

```powershell
uv run stock-research financials seed-v0
uv run stock-research financials normalize "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials calculate "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials periods "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials facts "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials metrics "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials metric "MU" gross_margin --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials lineage <CALCULATION_RUN_ID> gross_margin --json
```

Stage 9 Provider control commands remain fail-closed and require exact scope and
confirmation. Their presence does not authorize Live access:

```powershell
uv run stock-research provider sync-plan SEC_EDGAR_PUBLIC_V1 SEC_SUBMISSIONS_METADATA --help
uv run stock-research provider live-check SEC_EDGAR_PUBLIC_V1 SEC_SUBMISSIONS_METADATA --help
```

## Docker Compose

Docker is optional. Compose builds its internal database connection for host `db` and
does not consume the native host `DATABASE_URL`. Set a private local password and the
matching `COMPOSE_DATABASE_URL`, migrate, then start the API:

```powershell
$env:POSTGRES_PASSWORD = "choose-a-local-password"
$env:COMPOSE_DATABASE_URL = "postgresql+psycopg://stock_user:choose-a-local-password@db:5432/stock_research"
docker compose build api
docker compose up -d db
docker compose run --rm api stock-research db-upgrade
docker compose up -d api
docker compose ps
```

The Compose password is a local example only. Do not commit a real value or reuse it in
production.

## Testing

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
```

The default suite is offline and permits only isolated loopback PostgreSQL access.
See current test output for the exact count.

The sanitized Public Export omits all source-derived SEC, SSE, and Nasdaq Fixtures.
Project-authored, schema-equivalent Synthetic Fixtures cover the public parser, manifest,
checksum, as-of, Citation, and Provider-contract tests. They are offline engineering
assets only and are never company evidence or proof of Live Provider support.

## Documentation

- [Project Introduction](docs/PROJECT_INTRODUCTION.md)
- [Project Manual](docs/PROJECT_MANUAL.md)
- [User Guide](docs/USER_GUIDE.md)
- [Current Status & Roadmap](docs/CURRENT_STATUS_AND_ROADMAP.md)
- [GitHub Upload Checklist](docs/GITHUB_UPLOAD_CHECKLIST.md)
- [Public Fixture Replacement Matrix](docs/PUBLIC_FIXTURE_REPLACEMENT_MATRIX.md)
- [Public Release Readiness Report](docs/PUBLIC_RELEASE_READINESS_REPORT.md)

## Current Limitations

- No broker integration, order execution, or automatic trading.
- No target-price or investment-rating output.
- No production model runtime for narrative generation or Reflection.
- Production vector embedding is blocked; lexical retrieval is the verified baseline.
- SEC Live has not completed formal production validation.
- Tushare production access remains blocked.
- Approved A-share disclosure-body and licensed U.S. EOD providers are not available.
- Synthetic and offline Fixtures are engineering evidence, not company evidence or Live proof.

## Security & Data Boundaries

Never commit `.env`, credentials, authorization headers, cookies, private keys,
production database URLs, Provider Raw Artifacts, licensed datasets, or local runtime
storage. Credential references are secret-free; default Provider networking is disabled.

`PUBLISHABLE` means only that the internal deterministic engineering gate passed. It
does not mean public publication, regulatory approval, investment advice, or permission
to trade.

## Roadmap

If development is later resumed, the next action is to finish Stage 10 Tasks 78–80 on
its WIP branch, rerun final acceptance, and only then decide whether it is eligible for
merge. Live Provider work requires separate, narrowly scoped authorization.

## Disclaimer

This project is for research, engineering, and educational purposes. It does not
provide investment advice, brokerage execution, automated trading, or guaranteed
financial outcomes.

## License

This repository is publicly viewable for portfolio, research, and engineering
demonstration purposes.

No license is currently granted for copying, modifying, redistributing, sublicensing, or
commercial use of the source code unless explicitly permitted by the repository owner.

A formal open-source license may be added in the future. Third-party financial data
remains subject to its own source and Provider terms. See [LICENSE.md](LICENSE.md).
