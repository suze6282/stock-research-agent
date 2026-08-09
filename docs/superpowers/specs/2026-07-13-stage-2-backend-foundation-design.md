# Stage 2 Backend Foundation Design

## Purpose and scope

Stage 2 creates a reproducible Python backend foundation for Stock Research
Agent. It deliberately excludes stock data ingestion, financial calculations,
Tool Use implementations, RAG, Agent logic, Reflection workflows, MCP servers,
frontends, broker integrations, and automated trading.

The deliverable is an installable Python 3.12 project with a FastAPI application,
validated settings, structured and redacted logging, uniform errors, a Typer CLI,
SQLAlchemy and Alembic infrastructure, real PostgreSQL integration tests, Docker
and native-Windows development instructions, and CI quality gates.

## Chosen approach

The application is a small modular monolith. `create_app(settings)` is the only
FastAPI construction boundary and performs no database connection during module
import. Configuration is immutable after validation. Database engines and
sessions are created explicitly and injected into API and CLI boundaries.

Native PostgreSQL 17 is the local integration baseline. Docker Compose uses the
same PostgreSQL major version so local, container, and CI behavior stay aligned.
Docker runtime verification is recorded honestly if Docker Desktop remains
unavailable. SQLite may be used only for narrow unit tests and never as evidence
that PostgreSQL migrations or behavior passed.

`tools`, `retrieval`, `reflection`, `mcp`, and `orchestration` remain importable
package boundaries without business implementations or heavyweight dependencies.

## Components and responsibilities

- `config.py` loads and validates development, test, and production settings and
  exposes redacted representations of sensitive values.
- `logging.py` configures structlog, request IDs, environment-appropriate output,
  and recursive redaction of credentials, tokens, authorization values, and
  database URLs.
- `api/` owns routing, request-scoped dependencies, safe error responses, and the
  liveness/readiness endpoints.
- `db/` owns SQLAlchemy metadata, engine/session factories, transaction rollback,
  and connectivity checks. It contains no stock-domain models.
- Alembic reads the same Settings model as the application and supports online
  and offline operation. The initial migration creates only a minimal
  `schema_meta` table.
- `cli.py` exposes version, configuration, health, upgrade, and downgrade commands
  with truthful non-zero failures and production safeguards.
- Tests are split into unit, integration, and contract suites. They never call
  stock providers, SEC, OpenAI, or other internet services.

## Runtime and data flow

On startup, the entry point loads Settings, configures logging, and calls the
application factory. Liveness reads only in-process metadata. Readiness resolves
the configured database dependency and executes a minimal `SELECT 1`; success is
returned as a stable schema, while failures become a safe 503 response and a
redacted structured log event.

For database work, each request or CLI operation obtains its own Session from a
factory. Successful contexts commit only when the caller explicitly chooses a
transactional helper; exceptions roll back, and all sessions close reliably.
Alembic and runtime connections consume the same normalized PostgreSQL URL.

## Error and security design

All API errors use `{\"error\": {\"code\", \"message\", \"request_id\"}}`.
Validation errors are client-safe, database failures disclose no connection
details, and unexpected production errors disclose no stack trace. Logs retain
error types and correlation identifiers but redact passwords, tokens, complete
authorization headers, and credential-bearing URLs.

Production configuration fails at startup without an explicit PostgreSQL URL.
Test settings reject obvious production database targets. Destructive production
migration commands require explicit confirmation. Containers run as a non-root
user, and no secret is copied into an image or committed to Git.

## Verification strategy

Behavior is implemented test-first. Every feature begins with a focused failing
test, followed by the minimum implementation and a green rerun. PostgreSQL tests
use isolated development and test databases. Migration verification executes
`upgrade head`, `downgrade base`, and `upgrade head` against real PostgreSQL.

The completion gate is a fresh run of Ruff linting, Ruff format checking, mypy,
the complete pytest suite, CLI smoke checks, FastAPI startup and both health
paths, and real Alembic migration cycling. CI repeats the same checks with a
temporary PostgreSQL 17 service. Two written Reflection rounds then check
engineering/security findings and cross-file reproducibility.

## Approved implementation boundaries

The user supplied the detailed Stage 2 specification and approved execution on
2026-07-13. This design resolves the environment choice as native PostgreSQL 17
for local proof plus PostgreSQL 17 in Docker/CI, keeps the project in
`<project-root>`, and prohibits Stage 3 work.
