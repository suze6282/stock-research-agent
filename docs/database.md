# PostgreSQL 17 development database

## Safety boundary

Native development uses only the project-owned cluster at
`%LOCALAPPDATA%\stock-research-agent\postgres\data`, listening on loopback port
55432. `scripts/dev/start-postgres.ps1` and `stop-postgres.ps1` derive this path
from `LOCALAPPDATA`, resolve it, verify it remains below the project-owned root,
reject reparse points at each project-controlled path component, require
`PG_VERSION`, and never accept an arbitrary data directory. They do not
initialize, delete, or control a system PostgreSQL service or any resume-site
directory. Ordinary ancestors of `LOCALAPPDATA` are outside this project-owned
component check.

Use `-WhatIf` to audit an action without changing cluster state:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev\start-postgres.ps1 -WhatIf
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev\stop-postgres.ps1 -WhatIf
```

## One-time native initialization

The following is only for a new project-owned cluster. Confirm `$data` prints
the exact path below before running `initdb`. `initdb -W` prompts for the local
`stock_admin` password without storing it in Git.

```powershell
$env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
$root = Join-Path $env:LOCALAPPDATA "stock-research-agent\postgres"
$data = Join-Path $root "data"
$data
New-Item -ItemType Directory -Force -Path $root | Out-Null
initdb.exe -D $data -U stock_admin -W --auth-host=scram-sha-256 --auth-local=scram-sha-256 --encoding=UTF8
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev\start-postgres.ps1
psql.exe -h 127.0.0.1 -p 55432 -U stock_admin -d postgres -c "CREATE ROLE stock_user LOGIN"
psql.exe -h 127.0.0.1 -p 55432 -U stock_admin -d postgres -c "\password stock_user"
createdb.exe -h 127.0.0.1 -p 55432 -U stock_admin -O stock_user stock_research
createdb.exe -h 127.0.0.1 -p 55432 -U stock_admin -O stock_user stock_research_test
```

The application URL targets `stock_research`; tests use the separately named
`stock_research_test`. The Settings model rejects a test URL whose database name
does not end in `_test`.

## Migrations and rollback

Set `DATABASE_URL` to the intended database, verify it with `stock-research
check-config` and `health`, then migrate:

Repository checkouts use their own `alembic.ini`. For a non-editable wheel or
deployment, set `STOCK_RESEARCH_ALEMBIC_CONFIG` to the trusted absolute path of
that file. Relative paths and implicit current-working-directory lookup are
rejected.

```powershell
uv run alembic current
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

`0001_create_schema_meta` creates the Stage 2 schema marker.
`0002_create_security_master` creates the eight Stage 3 master-data tables,
named constraints, and focused exact/prefix indexes. A downgrade by one revision
drops only the Stage 3 tables in reverse dependency order and retains
`schema_meta`; re-upgrade recreates them. Downgrade to `base` also drops the
Stage 2 schema table. Production CLI downgrades require
`--confirm-production`; back up production data and obtain operational approval
before any future destructive migration.

**Seed data is not stored in Alembic.** Migrations never access the network and
contain no Industrial FII or Micron business rows. After upgrading, apply the
versioned transactional seed separately:

```powershell
uv run stock-research securities seed-v0
uv run stock-research securities seed-v0
```

The second command must insert zero rows. The seed uses a transaction advisory
lock, never overwrites a mismatch, and requires an explicit commit owned by the
CLI. API requests own a separate Session and always close it; they do not share
global Sessions.

Docker and CI also use PostgreSQL major version 17. SQLite is never accepted as
PostgreSQL migration or integration proof.

`session_scope()` owns rollback-on-exception and permanent close only. It never
commits implicitly; callers must invoke `session.commit()` at an explicit unit
of work boundary when persistence is intended.

## Stage 4 data-access schema

Revision `0003_create_data_access_and_snapshots` adds Provider mappings, ingestion
lineage, immutable RawPayload/raw records, DataSnapshot and SnapshotItem tables.
Foreign keys are restrictive; exact values use NUMERIC; query paths have named
indexes. PostgreSQL triggers enforce completed-snapshot immutability. The migration
contains no fixture or business rows and supports downgrade/re-upgrade. See
[raw-data-model.md](raw-data-model.md) and [data-snapshots.md](data-snapshots.md).

## Stage 5 financial-normalization schema

Revision `0004_financial_normalization` adds nine tables:
`canonical_financial_concepts`, `provider_fact_mappings`, `financial_periods`,
`normalized_financial_facts`, `normalized_fact_inputs`, `formula_definitions`,
`calculation_runs`, `calculation_inputs`, and `derived_metrics`.

All ownership foreign keys use `RESTRICT`. Monetary/fact/input/metric values use
`NUMERIC(38,18)`, never float. Named constraints validate codes, states, versions,
dates, finite scale/value semantics, unit/currency shape and idempotency. Focused
indexes cover exact provider mapping, snapshot/concept/period fact selection,
security/snapshot runs, run/metric inputs and metric/lineage reads. No extension,
native ENUM, business row or network call is introduced.

Reference seed and calculation concurrency use transaction advisory locks. Terminal
calculation runs plus their inputs/metrics, normalized facts and reference rows are
protected by PostgreSQL immutability triggers. The migration fully downgrades only
Stage 5 objects; Stage 1-4 tables and raw evidence remain.

After `upgrade head`, run the versioned seed explicitly and twice to prove idempotency:

```powershell
uv run stock-research financials seed-v0
uv run stock-research financials seed-v0
```
# Stage 6 schema

Revision `0005_rag_citations` adds exactly fourteen tables for logical documents, immutable byte
versions, snapshot links, parse artifacts, chunks/citations, lexical/vector metadata and immutable
retrieval history. Foreign keys use `RESTRICT`; terminal/version triggers prevent historical
mutation and a deferred trigger rejects section-parent cycles. The migration inserts no business
or fixture data and fully downgrades to Stage 5.
# Stage 7 controlled research schema

Migration `0006_controlled_research_agent` adds 12 PostgreSQL tables:
policies, requests, runs, plans, steps, Tool invocations, observations,
Evidence, Claims, Claim-Evidence links, packages, and run events. Foreign keys
use restrictive deletion, core query paths are indexed, events are append-only,
and triggers protect lineage and terminal immutability. Downgrade removes only
Stage 7 structures and preserves Stage 2–6 tables.

# Stage 8 verifiable report schema

Migration `0007_verifiable_reports` adds 15 purpose-specific tables: report and
runtime-Reflection policies, templates, Requests, Generation Runs, immutable
Reports, normalized Sections/Blocks, three binding tables, Reflection Runs/
Findings, Revision Runs and Release Gates.

All foreign keys use `RESTRICT`. Named CHECK/unique/index constraints enforce
statuses, bounds, versions, rounds, references and checksums. PostgreSQL
triggers reject mutation of immutable rows, terminal lifecycle rows and invalid
report-version chains. Downgrade removes only Stage 8 triggers, functions,
indexes and tables, returning to `0006_controlled_research_agent`.

The migration contains no business seed data and performs no network access.
Policies and templates use explicit idempotent CLI seed operations.
# Stage 9 database migration

`0008_create_production_data_providers` adds 20 Stage 9 tables for definitions,
capabilities, policies, license and credential metadata, requests/plans/runs,
attempts, artifacts/manifests/cache, checkpoints, circuit state, dead letters,
quality/freshness/health, audit and Live validation. Stage 2–8 tables are unchanged.

Foreign keys use `RESTRICT` where deleting governance or historical evidence would
break lineage. Immutable and append-only records are protected by constraints and
triggers; terminal/historical rows are not rewritten. The required replay is
`0008 → 0007 → 0008`, which removes/recreates only Stage 9 structures. Application
rollback reverts Stage 9 commits without rewriting earlier migrations. The current
engineering conclusion is `CONDITIONAL GO`; no database change authorizes Stage 10.
