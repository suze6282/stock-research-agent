# Stage 2 Reflection — Round 1 engineering review

Review window: 2026-07-13 to 2026-07-14 (Asia/Shanghai). The review covers
Stage 2 only; no Stage 3 stock-research behavior was implemented.

## Severity summary

| Severity | Found | Open |
| --- | ---: | ---: |
| CRITICAL | 0 | 0 |
| HIGH | 2 | 0 |
| MEDIUM | 3 | 3 |
| LOW | 2 | 2 |

Every CRITICAL/HIGH finding is closed. The remaining MEDIUM/LOW items are
explicitly recorded limitations, not hidden test failures.

## Python backend engineer

### HIGH — request and exception logs lacked the required correlation fields (fixed)

The first operational API run showed only Uvicorn access lines. Application
logs did not provide a `request_id` for every response and a database failure
did not record a safe exception type. This violated the explicit Stage 2
logging contract.

TDD evidence:

- RED: focused application/readiness tests failed `3 failed, 10 passed` because
  success, `ApiError`, validation, database, and unknown-error events were
  absent.
- GREEN: `13 passed` after adding one safe `api_request_failed` event at the
  uniform error boundary and one `request_completed` event for every response.
- The failure event contains only `error_type`, `code`, and `request_id`; the
  completion event contains method, path, status, and request ID. Exception
  messages and connection URLs are not logged.
- A real unreachable-database request logged `OperationalError`, the request
  ID, and status 503 while the sentinel
  `S2_SECRET_SENTINEL_7e9c4f2a` was absent.

### HIGH — database connection failure was not bounded by the engine (fixed)

An unreachable database URL without `connect_timeout` could leave readiness
waiting on the driver/OS timeout. The engine now supplies a five-second default
only when the URL does not already specify `connect_timeout`; a caller's shorter
explicit value remains authoritative.

TDD evidence:

- RED: the default-timeout unit assertion failed once; the explicit-timeout
  preservation assertion then failed once against the unconditional draft.
- GREEN: unit plus real PostgreSQL focused tests passed `13 passed` with zero
  warnings.
- Real API evidence with a closed loopback port and no URL timeout: safe 503 in
  5,156 ms, `OperationalError` logged, sentinel absent, listener stopped.

### Review result

The application factory remains side-effect free at import, engines and sessions
are explicit, sessions commit/rollback/close deterministically, type checking is
strict, the error envelope is stable, and tests include real PostgreSQL rather
than SQLite substitution. No open Python-backend CRITICAL/HIGH issue remains.

## DevOps engineer

### MEDIUM — Docker runtime is unavailable on this machine (open)

`docker compose config` cannot run because `docker` is not installed
(`CommandNotFoundException`). Dockerfile/Compose contracts are parsed and tested,
but image build, container startup, health, persistence, and shutdown are not
runtime evidence. This is explicitly permitted by the Stage 2 acceptance rule
when recorded honestly.

### MEDIUM — hosted CI has not executed in this local-only repository (open)

The workflow statically contains locked installation, Ruff, format, mypy,
separate unit/contract and PostgreSQL integration tests, and an Alembic cycle.
No remote Actions run exists yet because nothing was pushed.

### LOW — container tags are not digest-pinned (open)

The Python patch tag, uv version, and PostgreSQL major version are fixed, but
registry image digests are not pinned. Digest pinning can be added during a
deployment-hardening stage after Docker runtime verification.

### Review result

Native Windows PostgreSQL 17.10 is real and project-owned, both database names
are isolated, migration rollback was exercised, native start is idempotent, and
the stop script was checked with `-WhatIf` so the required running cluster was
not stopped. No open DevOps CRITICAL/HIGH issue remains.

## Security engineer

### MEDIUM — no dedicated dependency vulnerability scanner is in the gate (open)

Dependencies are locked and the installed graph is reproducible, but Stage 2
does not run a dedicated advisory scanner or produce an SBOM. This is a future
supply-chain hardening task; it is not evidence that a known vulnerability
exists.

### LOW — production debug is not forcibly rejected (open)

Production requires a PostgreSQL URL and destructive production downgrade is
explicitly guarded. `APP_DEBUG=true` is not rejected by Settings, although the
application does not expose stack traces. A stricter production policy can be
added when deployment configuration is designed.

### Review result

No credential-like token was found by the repository scan. `.env`, local
artifacts, worktrees, and caches are excluded from Git/Docker context. Settings
summaries redact credentials and all query values. API failures and logs omit
exception text and connection URLs. The image uses a non-root user. No open
security CRITICAL/HIGH issue remains.

## Agent architect

The `tools`, `retrieval`, `reflection`, `mcp`, and `orchestration` packages are
import-only architectural boundaries. They contain no provider adapter, tool
registry, vector store, Agent loop, model call, Reflection workflow, MCP SDK, or
research state machine. Boundary imports load none of FastAPI, SQLAlchemy,
Alembic, or structlog. The modular-monolith seams remain suitable for a later,
separately approved stage. No Agent-architecture finding was identified.

## Round 1 decision

All two HIGH findings were fixed through failing tests before implementation and
were reverified against real PostgreSQL/API processes. There are zero open
CRITICAL or HIGH findings.

## Whole-branch review addendum

The final whole-branch review found two **Important** blockers and one **Minor**
observability issue. All three were fixed before final acceptance:

- **Important — fixed:** a non-editable wheel/container resolved `alembic.ini`
  relative to the installed module. The CLI now resolves an explicit absolute
  `STOCK_RESEARCH_ALEMBIC_CONFIG` at invocation, rejects relative/missing paths,
  and uses only the checkout-root file as fallback. Docker sets
  `/app/alembic.ini`. An isolated installed wheel completed a real test-database
  upgrade/downgrade/upgrade from outside the checkout.
- **Important — fixed:** `session_scope()` committed every successful scope,
  contradicting explicit unit-of-work ownership. It now only rolls back
  exceptions and always closes; persistence callers commit explicitly.
- **Minor — fixed:** request IDs were not bound for internal/downstream logs.
  Middleware now binds the ID with `structlog.contextvars` and clears it in
  `finally`; sequential requests plus an out-of-request log prove no leak.

Focused RED reproduced five failures; focused GREEN passed all six selected
contracts, followed by 60 relevant unit/integration tests under `-W error`. No
whole-branch review blocker remains open.
