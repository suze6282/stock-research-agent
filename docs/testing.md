# Testing and quality gates

## Suites and markers

- `tests/unit`: normalization, schemas, resolution, settings, logging, CLI, and boundaries.
- `tests/contract`: stable health/security API schemas and error envelopes; the security
  API contract is marked integration because it uses seeded PostgreSQL.
- `tests/integration`: real PostgreSQL 17 models, constraints, migrations, seed,
  resolution, CLI, transaction, and lifecycle behavior.
- `integration`: pytest marker for every test that requires `TEST_DATABASE_URL`.

Tests do not call the internet, stock providers, the SEC, OpenAI, brokers, or a
production database. Explicit integration selection without `TEST_DATABASE_URL`
fails with a clear usage error. A valid test database name must end in `_test`.

## Focused and complete commands

```powershell
uv run pytest tests/unit/test_module_boundaries.py -v
uv run pytest -m "not integration"
$env:TEST_DATABASE_URL = "postgresql+psycopg://stock_user:local-dev-only-password@127.0.0.1:55432/stock_research_test"
uv run pytest -m integration tests/integration tests/contract/test_security_api_contract.py
```

Run the complete Stage 3 gate from a locked environment:

```powershell
uv sync --frozen --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
```

With `TEST_DATABASE_URL` set, the final command includes all real PostgreSQL
integration tests and requires zero warnings. Also cycle Alembic `upgrade head`,
`downgrade -1`, and `upgrade head`; run the seed twice; smoke the installed
security CLI; verify Industrial FII, Micron, ambiguity, invalid input, and
not-found behavior; and verify API liveness/readiness plus all security routes.

Tests use only loopback PostgreSQL. They do not access the internet, SEC, stock
exchanges, company IR, model providers, brokers, or production data. SQLite is
not accepted as PostgreSQL evidence. Fixtures are separate from the production
versioned seed and every destructive test validates an `_test` database.

CI reproduces these gates with a PostgreSQL 17 service, separate
`stock_research` and `stock_research_test` databases, and no external stock or
model credential. Docker contract tests are static when Docker is unavailable;
they do not replace an actual image build and Compose runtime test.

## Stage 4 offline and Live isolation

Default pytest uses `testpaths=["tests"]` and an autouse socket guard that denies
external DNS/IP while allowing literal loopback PostgreSQL. `live_tests/` is outside
default collection and CI. An explicit `uv run pytest live_tests -v -rs` currently
records Tushare, licensed U.S. EOD, and SEC Archive as `BLOCKED`; it performs no
request and must never be folded into the default gate. Fixture/provider, snapshot,
Tool, API, CLI, and real PostgreSQL contracts are covered separately.

## Stage 5 financial test matrix

Stage 5 adds unit/golden tests for 35 concepts, exact mappings, Decimal unit scaling,
period shapes, non-calendar and 52/53-week years, as-of/restatement leakage,
A-share cumulative split, both TTM methods, all 23 formula codes and NULL/N/M/ZERO
semantics. Service/contract tests cover normalization, immutable/idempotent runs,
lineage, six read-only Tools, GET-only API and explicit CLI commands.

Real PostgreSQL tests cover the 0004 migration, constraints/triggers, reference-seed
idempotency, raw-fact preservation, exact synthetic mapping/calculation, transaction
rollback and concurrent calculation reuse. Synthetic values are test-only and never
enter fixtures or production seeds. Both approved sample snapshots are separately
verified to produce zero normalized facts and 23 `BLOCKED/NULL` metrics because their
offline evidence contains no numeric financial facts.

The complete gate remains:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://stock_user:<local-test-password>@127.0.0.1:55432/stock_research_test"
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
```

Default tests stay offline. `live_tests/` remains separately selected and its Tushare,
licensed U.S. EOD and SEC Archive cases remain explained `BLOCKED` skips until real
credentials, entitlement and SEC contact configuration exist.
# Stage 6 tests

Default tests remain offline. Synthetic parser/retrieval fixtures require all four test-only
markers and checksum manifests. They validate contracts, never company research or semantic
quality. PostgreSQL tests exercise 0005 upgrade/downgrade/re-upgrade and immutability. Live company
body acceptance is BLOCKED until compliant bytes exist; production vector tests remain BLOCKED.
# Stage 7 testing

Default pytest remains offline and uses PostgreSQL 17 for integration coverage.
Stage 7 tests cover Policy/catalog fingerprints, finite Plans, state parity,
budgets, Tool context and permissions, Evidence/Claim/conflict rules, immutable
database records, read-only GET API/Tools, explicit CLI, real-company honest
degradation, and isolated Synthetic flow. Model packages and network requests
are absent. Synthetic fixtures are marked `SYNTHETIC_TEST_ONLY`,
`NOT_COMPANY_EVIDENCE`, `OFFLINE`, and `NOT_LIVE`.

# Stage 8 focused verification

Stage 8 tests cover Manifest canonicalization, JSON/Markdown parity, all binding
validators, both locales, formatting, stable references, two Reflection rounds,
one Revision, Release Gate, Tools, GET API, CLI transactions, all 15 PostgreSQL
tables/triggers, downgrade/re-upgrade and three acceptance flows.

Synthetic report fixtures are fixed LF Git blobs. Their manifest checksums,
worktree bytes and CRLF count are verified independently. They are never company
evidence. Default pytest remains offline, has no model request, no unexplained
skip and treats warnings as errors.

```powershell
uv run pytest -W error tests/integration/test_report_migrations.py
uv run pytest -W error tests/integration/test_report_repository_postgres.py tests/integration/test_report_postgres.py tests/integration/test_report_cli_postgres.py
uv run pytest -W error tests/integration/test_report_industrial_fii.py tests/integration/test_report_micron.py tests/integration/test_report_synthetic_flow.py
uv run pytest -W error
```
# Stage 9 offline and Live test isolation

Default collection is fixed by `testpaths = ["tests"]`. The autouse guard removes
Provider credential environment names and blocks non-loopback DNS/socket access;
literal loopback remains available for isolated PostgreSQL. Default CI never
collects `tests_live/providers` and never treats a configured secret as approval.

Live tests require a separate disclosure of official domains, exact capability,
request/byte/record/document/duration budgets, credential references, license,
cost, database impact and rollback. Only the exact phrase
`批准执行该Provider的有限Live验证` authorizes one bounded validation. SEC approval
does not authorize Tushare. Without it, status is `NOT_ATTEMPTED`, not PASS.

Stage 9 acceptance uses `-W error`, zero unexplained skips/warnings, PostgreSQL
migration replay and offline fixtures. Its expected conclusion is `CONDITIONAL GO`;
the suite does not authorize Stage 10.
