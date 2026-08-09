# Stage 2 Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an installable, configurable, testable FastAPI foundation with
real PostgreSQL migrations, truthful health checks, CLI operations, reproducible
native/Docker workflows, and no stock-research business implementation.

**Architecture:** A small modular monolith uses an application factory, immutable
Pydantic Settings, explicit SQLAlchemy engine/session factories, one error model,
and injected readiness dependencies. Alembic, API, CLI, tests, Docker, and CI use
the same settings names and PostgreSQL 17 contract.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, pydantic-settings,
SQLAlchemy 2.x, Alembic, PostgreSQL 17, psycopg 3, Typer, structlog, httpx,
pytest, pytest-asyncio, respx, Ruff, and mypy.

## Global Constraints

- Work only in `<project-root>` on
  `stage-2/backend-foundation`; preserve the source Stage 1 files.
- Python must satisfy `>=3.12,<3.13`; dependencies must be locked by `uv.lock`.
- No stock data provider, financial calculation, RAG, Agent, Reflection business,
  MCP SDK/server, frontend, task queue, vector database, or external API call.
- `tools`, `retrieval`, `reflection`, `mcp`, and `orchestration` are package
  boundaries only.
- No import-time database connection or implicit global Session.
- Tests do not access the internet, production databases, stock APIs, or OpenAI.
- SQLite cannot stand in for PostgreSQL migration or integration verification.
- No real secret is committed; logs and responses never disclose credentials.
- Every behavior-changing implementation follows RED, GREEN, REFACTOR.
- Do not enter Stage 3.

---

### Task 1: Project packaging and validated Settings

**Files:**
- Create: `AGENTS.md`, `.gitignore`, `.python-version`, `pyproject.toml`, `uv.lock`
- Create: `src/stock_research_agent/__init__.py`
- Create: `src/stock_research_agent/config.py`
- Create: `tests/unit/test_config.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `AppEnvironment(StrEnum)` with `development`, `test`, `production`.
- Produces: `Settings(BaseSettings)` with `app_name`, `app_env`, `app_debug`,
  `app_host`, `app_port`, `log_level`, `database_url`, `database_echo`, and
  `api_prefix`.
- Produces: `Settings.safe_summary() -> dict[str, object]` with redacted URL.
- Produces: package `__version__ = "0.1.0"`.

- [ ] **Step 1: Add the minimum package configuration**

  Configure the `src` layout, `stock-research` console entry point, production
  dependencies, development group, Ruff, mypy, and pytest. Pin `.python-version`
  to `3.12.13`, then run `uv lock` and `uv sync --all-groups`.

- [ ] **Step 2: Write failing Settings tests**

  Tests instantiate Settings with `_env_file=None` and cover development
  defaults, case-insensitive environment overrides, invalid environment, ports
  outside `1..65535`, production without `DATABASE_URL`, test configuration that
  resembles a production database, and password-free `safe_summary()` output.

- [ ] **Step 3: Verify RED**

  Run `uv run pytest tests/unit/test_config.py -v`. Expected: collection fails
  because `stock_research_agent.config` does not exist.

- [ ] **Step 4: Implement the minimum Settings model**

  Use `SettingsConfigDict(env_file=".env", extra="ignore",
  case_sensitive=False)`, explicit field validators, and a model validator for
  environment/database rules. Redact credential-bearing URLs without returning
  `SecretStr` representations.

- [ ] **Step 5: Verify GREEN and static checks**

  Run `uv run pytest tests/unit/test_config.py -v`, `uv run ruff check` on the
  created Python files, and `uv run mypy src/stock_research_agent/config.py`.

- [ ] **Step 6: Commit exact files**

  Commit as `chore: establish Python project and settings`.

---

### Task 2: Logging, request IDs, errors, application factory, and liveness

**Files:**
- Create: `src/stock_research_agent/logging.py`
- Create: `src/stock_research_agent/api/errors.py`
- Create: `src/stock_research_agent/api/router.py`
- Create: `src/stock_research_agent/api/routes/health.py`
- Create: `src/stock_research_agent/main.py`
- Create package `__init__.py` files under `api/` and `api/routes/`
- Create: `tests/unit/test_logging.py`, `tests/unit/test_app.py`
- Create: `tests/contract/test_health_contract.py`

**Interfaces:**
- Produces: `redact_sensitive_data(event_dict) -> dict[str, object]`.
- Produces: `configure_logging(settings: Settings) -> None`.
- Produces: `ApiError(code: str, message: str, status_code: int)`.
- Produces: `create_app(settings: Settings | None = None) -> FastAPI`.
- Produces: `GET /health/live` and request header `X-Request-ID`.

- [ ] **Step 1: Write failing redaction tests**

  Cover nested dictionaries/lists, `DATABASE_PASSWORD`, `OPENAI_API_KEY`, keys
  containing `token`, complete Authorization values, and credential-bearing
  PostgreSQL URLs. Assert sentinel secrets are absent from serialized output.

- [ ] **Step 2: Verify logging RED, implement, and verify GREEN**

  Run the logging test and confirm the import failure. Implement recursive key
  and URL redaction plus structlog processors for timestamp, level, service, and
  environment-appropriate renderers. Re-run the test to green.

- [ ] **Step 3: Write failing application and contract tests**

  Assert `create_app(test_settings)` has configured title/version/prefix, import
  performs no database connection, liveness returns the exact status/service/
  version fields, validation errors use the uniform envelope, unexpected errors
  return no stack, and every response includes a non-empty request ID.

- [ ] **Step 4: Verify API RED**

  Run the two test files. Expected: imports or route assertions fail because the
  factory, middleware, handlers, and route do not exist.

- [ ] **Step 5: Implement the minimum API foundation**

  Add request-ID middleware, exception handlers for `ApiError`, request
  validation, and unknown errors, a router factory using `settings.api_prefix`,
  a pure liveness route, and `main.py` exporting `app = create_app()` without a
  database connection side effect.

- [ ] **Step 6: Verify GREEN and commit**

  Run focused tests, Ruff, and mypy. Commit as
  `feat: add application factory logging and liveness`.

---

### Task 3: SQLAlchemy infrastructure and readiness

**Files:**
- Create: `src/stock_research_agent/db/base.py`
- Create: `src/stock_research_agent/db/session.py`
- Create: `src/stock_research_agent/api/dependencies.py`
- Modify: `src/stock_research_agent/api/routes/health.py`
- Modify: `src/stock_research_agent/main.py`
- Create: `tests/unit/test_db_session.py`
- Create: `tests/integration/test_postgres.py`
- Create: `tests/contract/test_readiness_contract.py`

**Interfaces:**
- Produces: `Base(DeclarativeBase)` with UTC-aware timestamp conventions.
- Produces: `create_engine_from_settings(settings) -> Engine`.
- Produces: `create_session_factory(engine) -> sessionmaker[Session]`.
- Produces: `session_scope(factory) -> Iterator[Session]` with rollback/close.
- Produces: `check_database(engine) -> None` executing `SELECT 1`.
- Produces: `GET /health/ready` with ready/503 stable response schemas.

- [ ] **Step 1: Write failing unit and readiness tests**

  Use injected fake engines/sessions to prove lazy engine creation, close on
  success, rollback and close after exceptions, readiness 200 on a passing check,
  readiness 503 on `SQLAlchemyError`, no URL disclosure, and request ID presence.

- [ ] **Step 2: Verify RED and implement minimum infrastructure**

  Run the focused tests and confirm missing interfaces. Implement explicit
  engine/session factories, context-managed rollback/close, and a readiness
  dependency stored in `app.state` during lifespan without connecting at import.

- [ ] **Step 3: Verify unit GREEN**

  Run unit and contract readiness tests until green, then run Ruff and mypy.

- [ ] **Step 4: Add real PostgreSQL integration tests**

  Use only `TEST_DATABASE_URL`; fail collection with a clear message when the
  explicitly selected integration run lacks it. Verify `SELECT 1`, transaction
  rollback, session closure, UTC round-trip behavior using a temporary integration
  table, and readiness against the isolated test database.

- [ ] **Step 5: Verify PostgreSQL GREEN and commit**

  Run the integration marker against PostgreSQL 17 and commit as
  `feat: add database sessions and readiness checks`.

---

### Task 4: Alembic and minimal schema migration

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`, `migrations/script.py.mako`
- Create: `migrations/versions/0001_create_schema_meta.py`
- Create: `tests/integration/test_migrations.py`

**Interfaces:**
- Alembic reads the same `DATABASE_URL` contract as Settings.
- Migration `0001` creates only `schema_meta(id, schema_version, applied_at)` and
  drops it completely on downgrade.

- [ ] **Step 1: Write failing migration tests**

  In an isolated PostgreSQL test database, invoke Alembic programmatically and
  assert upgrade creates `schema_meta`, downgrade removes it, and a second upgrade
  succeeds. Add an offline SQL test that contains PostgreSQL DDL without opening
  a connection.

- [ ] **Step 2: Verify RED**

  Run the migration test and confirm it fails because Alembic configuration and
  revisions do not exist.

- [ ] **Step 3: Implement Alembic configuration and revision**

  Escape percent characters in URLs before passing them to ConfigParser, use
  `Base.metadata`, support online/offline modes, and keep the revision independent
  of application runtime side effects.

- [ ] **Step 4: Verify GREEN and manual migration cycle**

  Run the migration test, then execute `alembic upgrade head`, `alembic downgrade
  base`, and `alembic upgrade head` against the isolated development database.

- [ ] **Step 5: Commit**

  Commit as `feat: add PostgreSQL migration foundation`.

---

### Task 5: Typer CLI

**Files:**
- Create: `src/stock_research_agent/cli.py`
- Create: `tests/unit/test_cli.py`
- Create: `tests/integration/test_cli_database.py`

**Interfaces:**
- Produces commands: `version`, `check-config`, `health`, `db-upgrade`, and
  `db-downgrade`.
- `health` checks configuration and the database only.
- Production downgrade requires `--confirm-production`.

- [ ] **Step 1: Write failing CLI tests**

  Assert exact version output, config success without secrets, invalid config
  non-zero status, healthy/unhealthy database exit codes, Alembic invocation,
  and production downgrade refusal without the explicit flag.

- [ ] **Step 2: Verify RED, implement, and verify GREEN**

  Run focused tests, implement the Typer application with injectable helpers and
  safe messages, then rerun unit and real PostgreSQL CLI tests.

- [ ] **Step 3: Run installed-entry smoke checks and commit**

  Execute `uv run stock-research version`, `check-config`, `health`, migration
  help, Ruff, and mypy. Commit as `feat: add operational command line interface`.

---

### Task 6: Reproducible environments, CI, documentation, and boundaries

**Files:**
- Create: `.env.example`, `Dockerfile`, `docker-compose.yml`
- Create: `.github/workflows/backend-ci.yml`
- Create: `README.md`
- Create: `docs/development.md`, `docs/configuration.md`, `docs/database.md`,
  `docs/testing.md`
- Create: `scripts/dev/start-postgres.ps1`, `scripts/dev/stop-postgres.ps1`
- Create package boundaries under `domain/common`, `infrastructure`,
  `orchestration`, `tools`, `retrieval`, `reflection`, and `mcp`
- Create: `tests/unit/test_module_boundaries.py`

**Interfaces:**
- Docker Compose services are `api` and `db`; `db` is PostgreSQL 17.
- The image runs as a non-root user and uses the lock file.
- Native scripts start/stop only the project-owned local PostgreSQL cluster.

- [ ] **Step 1: Write failing boundary/config consistency tests**

  Assert boundary packages import without extra dependencies or side effects,
  `.env.example` keys equal documented Settings keys, and no forbidden business
  commands/modules/dependencies appear.

- [ ] **Step 2: Verify RED, add boundaries/config, and verify GREEN**

  Create only required package markers and clock/common type foundations. Add
  example configuration without real secrets and rerun tests.

- [ ] **Step 3: Add and statically validate Docker assets**

  Build from a Python 3.12 slim image, install locked dependencies, create a
  non-root user, expose the API health check, and configure PostgreSQL 17 with a
  named volume. Run `docker compose config` if Docker is available; otherwise
  record the exact unavailable command and perform YAML/static review.

- [ ] **Step 4: Add CI matching local commands**

  CI installs uv and locked dependencies, runs Ruff, format, mypy, unit/contract
  tests, starts a PostgreSQL 17 service, runs integration tests, and cycles
  Alembic without any external stock/API credential.

- [ ] **Step 5: Write operational documentation and verify commands**

  Document native and Docker setup, configuration and safety rules, migration
  rollback, test markers, and every explicitly unimplemented Stage 3 capability.
  Execute each locally applicable README command.

- [ ] **Step 6: Commit**

  Commit as `docs: add reproducible development and CI workflows`.

---

### Task 7: Whole-stage verification, Reflection, and implementation report

**Files:**
- Create: `docs/reflection/stage-2-round-1.md`
- Create: `docs/reflection/stage-2-round-2.md`
- Create: `docs/stage-2-implementation-report.md`

**Interfaces:**
- Reflection findings use `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW`.
- Stage conclusion is exactly `GO`, `CONDITIONAL GO`, or `NO-GO`.

- [ ] **Step 1: Run the complete fresh quality gate**

  Execute `uv sync --frozen --all-groups`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy src`, and `uv run pytest` with
  real PostgreSQL integration settings. Record exit codes and test counts.

- [ ] **Step 2: Run operational verification**

  Cycle migrations, run all CLI commands, start the API, verify liveness 200,
  readiness 200 with PostgreSQL, readiness 503 with an unreachable database, and
  confirm responses/logs contain no sentinel secret.

- [ ] **Step 3: Perform Reflection round 1**

  Review as Python backend, DevOps, security, and Agent architecture roles.
  Record all findings and fix every CRITICAL/HIGH through new failing tests before
  continuing.

- [ ] **Step 4: Perform Reflection round 2**

  Cross-check README commands, file structure, Settings/example fields, native/
  Docker/CI consistency, Alembic configuration, production failure behavior,
  unavailable-database coverage, redaction, imports, and absence of fake tests or
  Stage 3 implementation.

- [ ] **Step 5: Write the implementation report**

  Include the 22 required report sections, actual versions and paths, exact
  command evidence, Docker status, native PostgreSQL status, fixes, remaining
  risks, rollback, Git status, and Stage 3 gate decision.

- [ ] **Step 6: Run final review and commit**

  Request a whole-branch code review, address Critical/Important findings with
  focused tests, rerun the complete gate, and commit as
  `docs: report stage 2 implementation evidence`.
