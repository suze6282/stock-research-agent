# Stage 7 Implementation Report

## 1. Stage conclusion

**CONDITIONAL GO**

The controlled research orchestration, deterministic Planner, bounded Tool
execution, Evidence Ledger, Claim validation, conflict preservation, immutable
audit trail, read-only API/Tools and explicit CLI workflows are implemented and
verified. The condition is evidentiary: Industrial FII and Micron still lack the
approved company-body and financial evidence required for a complete real-company
research package.

This report does not authorize a merge to `main` or any Stage 8 implementation.

## 2. Branch and scope

- Branch: `stage-7/controlled-agent-orchestration`
- Planner: `DeterministicTemplatePlanner`
- Claim proposer: `DeterministicClaimBuilder`
- Production model Planner: `BLOCKED`
- Production model Reasoner: `BLOCKED`
- Model token budget and consumption: `0`
- Runtime default: offline, no model requests

Implemented:

- immutable, versioned Research Policy and exact Tool Catalog binding;
- Research Request, Run, Plan, Step, Invocation, Observation, Evidence, Claim,
  Package and append-only Event records;
- finite deterministic state machine and DAG validation;
- hard budgets and bounded read-only Tool execution;
- deterministic Evidence and Claim validation with conflict preservation;
- explicit CLI write/control commands;
- eight read-only Research query Tools and eight GET API endpoints;
- PostgreSQL migration `0006_controlled_research_agent`;
- honest real-company degradation and isolated Synthetic engineering flow.

Not implemented:

- final natural-language stock report, rating, target price, forecast or trading
  advice;
- production Model Provider or any model call;
- open-ended ReAct or multi-Agent runtime;
- production Reflection runtime, MCP Server, frontend, broker access or trading;
- any Stage 8 capability.

## 3. Deterministic orchestration

Identical Research Request, Security, Snapshot, as-of, Policy, Planner version and
Tool Catalog version produce the same finite Step graph, order, exact Tool
name/version and Plan checksum. A Planner cannot change controlled context, expand
the Plan from Tool/document output, increase budgets or authorize a Tool.

The production execution service routes exact Tool name/version pairs across the
approved offline registries, persists each Invocation as `RUNNING`, completes it
once, records safe Observations, accumulates budgets and produces an honest
terminal Package. Resume revalidates Policy, catalog, COMPLETE Snapshot,
Security and as-of and never resets consumed budgets.

## 4. Tool Catalog and permission model

The bound catalog records 22 audited Stage 3–6 data Tools, including name, version,
permission, write/network flags, schema versions and domain, under a stable catalog
checksum. Research Policy uses an exact allowlist; no prefix or pattern
authorization exists. Eight additional Research query Tools expose persisted Runs,
Plans, Steps, Invocations, Evidence, Claims, Packages and Events. All Agent-visible
Tools are `READ_ONLY`, `writes=false`, `requires_network=false`.

Tool/API reads never ingest, refresh, parse, index, embed, calculate, create a
Snapshot or call a model.

## 5. Evidence, Claims and conflicts

Evidence validation checks Run, Security, Snapshot, as-of, source existence and
checksum, Citation validity, metric calculation lineage, publication time and
synthetic status. Unknown or future publication evidence cannot support strict
Claims. `SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE` and unknown sources cannot
serve as primary evidence for real-company Claims.

Only `ClaimSupportValidator` assigns final support:
`SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONFLICTING`, `UNSUPPORTED` or `BLOCKED`.
Numeric Claims retain value, unit, period, as-of and metric/formula/source lineage.
Conflicts remain visible; no averaging, popularity choice, latest-value override
or confidence score is used.

## 6. Real-company results

### Industrial FII — 601138.SH

- Security identity and persisted Snapshot binding: verified.
- Approved company-body evidence: absent.
- Approved financial facts sufficient for full research: absent.
- Document Evidence: `BLOCKED`.
- Package: `PARTIAL` or `BLOCKED`, never `COMPLETE`.
- Prohibited unverified AI-server, order, profit or growth Claims: absent.
- Synthetic evidence used: none.

### Micron — MU

- Security identity and persisted Snapshot binding: verified.
- SEC filing metadata: available only as metadata.
- Approved 10-K/10-Q/8-K body evidence: absent.
- Document Evidence: `BLOCKED`.
- Package: `PARTIAL` or `BLOCKED`, never `COMPLETE`.
- Prohibited unverified HBM, inventory-cycle, data-center and risk-factor Claims:
  absent.
- Synthetic evidence used: none.

These states reflect missing approved evidence, not a failed orchestration engine.

## 7. Synthetic engineering flow

The neutral Synthetic Security fixture is marked:

- `SYNTHETIC_TEST_ONLY`
- `NOT_COMPANY_EVIDENCE`
- `OFFLINE`
- `NOT_LIVE`

It validates complete finite orchestration, Evidence/Claim/Citation contracts,
conflict behavior, pause/resume, budget degradation and idempotency. It cannot
link to or support either real company and is not production research validation.

## 8. API and CLI

The API has eight approved GET-only Research routes. Contract tests cover stable
schemas, bounded pagination, UUID/query validation, safe 404/422 responses,
`X-Request-ID`, no sensitive fields and no write method.

The CLI provides explicit Policy seed/list, Tool Catalog list, plan, run, pause,
resume, cancel and all approved read commands. Run creation requires a Snapshot,
Research Type, Policy and as-of. It never chooses a latest Snapshot implicitly and
does not network, refresh, parse, index, embed, calculate or call a model.

## 9. Database and migrations

`0006_controlled_research_agent` adds exactly 12 Stage 7 tables:

1. `research_policies`
2. `research_requests`
3. `research_agent_runs`
4. `research_plans`
5. `research_steps`
6. `research_tool_invocations`
7. `research_observations`
8. `research_evidence`
9. `research_claims`
10. `claim_evidence_links`
11. `research_packages`
12. `research_run_events`

Foreign keys, CHECK/unique constraints, query indexes, terminal immutability
triggers and append-only events were verified with PostgreSQL. Both the development
database and isolated test database completed:

`current → upgrade head → downgrade -1 → upgrade head → current`

Both ended at `0006_controlled_research_agent (head)`. Stage 2–6 structures remain
present, and the isolated test suite does not target the development database.

## 10. Quality results

- `uv sync`: 55 packages resolved, 54 checked.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: 314 files already formatted.
- `uv run mypy src`: success, 160 source files.
- Stage 7 focused suite: 150 passed, 1397 deselected, 14.29 seconds.
- Full suite: 1547 collected, 1547 passed, 0 failed, 0 errors, 0 skipped,
  0 warnings, 237.82 seconds.
- Residual project pytest processes after the full suite: none.

Five full-suite failures found during the first final run were stale earlier-stage
architecture/migration assertions. They were updated to recognize the approved
Stage 7 tables, repository export, modules, branch documentation and Tool modules.
A separate HIGH finding fixed Invocation persistence so terminal immutability is
not violated.

## 11. Reflection and risks

Round 1 found three HIGH issues: missing production execution composition,
insufficient resume validation and terminal-status Invocation insertion. All are
fixed. Round 2 reran 36 checks.

- Unresolved CRITICAL: 0
- Unresolved HIGH: 0

Remaining limitations:

- Industrial FII and Micron lack sufficient approved real evidence.
- Production Planner/Reasoner providers remain `BLOCKED`.
- Live providers blocked in prior stages remain blocked unless separately
  authorized and configured.

## 12. Rollback and handoff

Database rollback: point `DATABASE_URL` only at the explicitly verified target and
run `uv run alembic downgrade -1`; this removes only Stage 7 objects. Re-upgrade
with `uv run alembic upgrade head`.

Git rollback remains a branch-level decision. The Stage 7 branch is preserved and
has not been merged. The user must select the finishing action. Stage 8 scope must
come from a new explicit prompt; it cannot be inferred from this report.
