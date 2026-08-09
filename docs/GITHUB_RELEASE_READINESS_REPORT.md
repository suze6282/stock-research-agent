# GitHub Release Readiness Report

Report date: 2026-08-09 (Asia/Shanghai)

## 1. Repository

- Name: `stock-research-agent`
- Repository root: represented publicly as `<project-root>`
- Git remote: none configured
- Public upload performed: no

## 2. Branch and Commit State

| Item | Value | Assessment |
|---|---|---|
| Documentation branch | `docs/github-publication-prep` | Correct isolated branch; documentation changes remain uncommitted for review. |
| Documentation branch HEAD | `d6368d598e714382f9ce419da8fb760d15ddc362` | Same commit as `main`; no documentation commit created. |
| `main` HEAD | `d6368d598e714382f9ce419da8fb760d15ddc362` | Stable Stage 1–9 baseline. |
| Stage 9 branch | `stage-9/production-data-providers` at `74f3b23fa5552571b414ca86c932ea135f885233` | Branch remains available with task-level history. Its tree matches `main`; history differs because Stage 9 entered `main` through an aggregate/squash-style commit plus a follow-up fix. |
| Stage 10 branch | `stage-10/controlled-live-evidence` at `db398589f04647dc8230eaf0095e09773f169ed0` | WIP branch; not merged into `main`. |
| Stage 10 WIP checkpoint | `db39858` — `wip: checkpoint stage 10 controlled live evidence` | Local safety checkpoint only; it does not mean Stage 10 is complete. |

## 3. Stage Status

### Stable / Completed

- Stage 1–8: completed and accepted.
- Stage 9 — Production Data Provider Governance: completed as offline engineering with
  `CONDITIONAL GO`; 77/77 tasks, two Reflection rounds, implementation report and
  PostgreSQL acceptance evidence exist in `main`.

Stage 9 completion does not authorize or validate all Live Providers.

### Work in Progress / Development Paused

- Stage 10 — Controlled Live Evidence: started and paused.
- Tasks 0–77 and Round 1 remediation are present on the WIP branch.
- Tasks 78–80 (Round 2, implementation report and Gate A final acceptance) are not
  complete.
- Gate B and real Live Provider execution remain `NOT_ATTEMPTED`.
- Stage 10 is not merged into `main` and must not be described as complete.

## 4. Documentation Integrated

The following user-provided source documents were found and used as the content basis:

- `README.md`
- `docs/PROJECT_INTRODUCTION.md`
- `docs/PROJECT_MANUAL.md`
- `docs/USER_GUIDE.md`
- `docs/CURRENT_STATUS_AND_ROADMAP.md`
- `docs/GITHUB_UPLOAD_CHECKLIST.md`

This report was added as `docs/GITHUB_RELEASE_READINESS_REPORT.md`. Existing `docs/`,
including specs, plans, reflections and implementation reports, were preserved.

## 5. README Status

Status: revised and code-checked.

The README now explains the project in 3–5 minute form, distinguishes it from an LLM
wrapper, documents the Evidence-first Agent Harness, includes the actual research chain,
records stable/WIP/blocked boundaries, provides verified CLI/API/database commands, links
all publication documents, states current limitations, and records that no License has
been selected.

Corrected stale claims:

- Stage 9 is no longer described as paused or incomplete; it is completed with
  `CONDITIONAL GO` and merged into `main`.
- Stage 10 is no longer described as not started; it is WIP/paused and unmerged.
- Production Narrative, Reflection Model, Embedding and Live Provider capabilities are
  not represented as active.
- `PUBLISHABLE` is explicitly limited to an internal deterministic engineering gate.

## 6. Detailed Documentation Status

| Document | Status | Key correction |
|---|---|---|
| Project Introduction | Integrated and revised | Portfolio-facing Evidence-first explanation; Stage 9/10 status corrected. |
| Project Manual | Integrated and revised | Architecture, domain, Snapshot, financials, RAG, Agent, reports, Provider governance, PostgreSQL, API, CLI, testing and security checked against the stable tree. |
| User Guide | Integrated and revised | Python, uv, PostgreSQL 17, `.env`, local scripts, Alembic, CLI groups, API entry, offline/Live boundaries and quality commands verified. |
| Current Status & Roadmap | Integrated and revised | Records Stage 9 completion and Stage 10 Task 78–80 remaining work without a false schedule. |
| Upload Checklist | Integrated and expanded | Covers Secrets, credentials, paths, data, fixtures, large files, history, generated files, License and prohibited publication actions. |

## 7. Quick Start Verification

Status: verified for the current local environment.

Evidence:

- `uv sync --frozen --all-groups`: passed; 54 packages checked.
- `uv run stock-research version`: passed; version `0.1.0`.
- `uv run stock-research check-config`: passed.
- `uv run stock-research health`: passed against project-owned loopback PostgreSQL.
- `uv run alembic current`: passed; `0008_production_providers (head)`.
- Project PostgreSQL startup script: PostgreSQL 17.10 recovered and accepted connections.

The first startup exceeded the script's 60-second wait because PostgreSQL was recovering
from an earlier abnormal Windows shutdown. No cluster reinitialization, deletion, password
reset or Schema repair was performed.

## 8. CLI Verification

Status: passed.

The executable script is `stock-research = stock_research_agent.cli:app`. Root help and
the following stable groups were executed successfully:

`securities`, `data`, `financials`, `documents`, `rag`, `agent`, `report`, `provider`,
and `tools`.

Documented Stage 3–5 and Stage 9 command strings also pass the repository's existing
documentation contract tests.

## 9. API Verification

Status: passed.

- Application entry verified: `stock_research_agent.main:app`.
- Uvicorn command checked: `uv run uvicorn stock_research_agent.main:app --host 127.0.0.1 --port 8000`.
- FastAPI runtime smoke through `TestClient`:
  - `/api/v1/health/live`: HTTP 200, `ok`;
  - `/api/v1/health/ready`: HTTP 200, `ready`;
  - `/openapi.json`: HTTP 200, 56 paths.
- Stable business routes are GET-only query surfaces; writes remain explicit CLI/application
  actions.

## 10. Secret and Credential Scan

Status: no suspected real Secret found in the current tree.

The scan covered Token/API Key/Secret/Password/Authorization/Cookie/Private Key,
Tushare/OpenAI/Anthropic/Google/GitHub/AWS names, database URLs, Bearer literals and
risky credential filenames. Values were not printed during review.

Keyword hits were manually classified as:

- variable/type names and security tests;
- local/CI example database URLs with explicit fake passwords;
- one dummy Bearer literal in a log-redaction test;
- one historical prose placeholder for a future API key;
- the phrase `BEGIN PRIVATE KEY` in this upload checklist.

No real `.env`, PEM/key/certificate bundle, credential file, private key, Provider Token,
production URL or authorization header was found.

## 11. `.env` Status

- Real `.env` or `.env.*` file present: no.
- `.env.example`: present, tracked and limited to variable names/local fake defaults.
- Personal blob path replaced with `C:/path/to/stock-research-agent/blobs`.
- Provider network defaults remain disabled and `OFFLINE`.
- `.gitignore` preserves `!.env.example` while excluding real environment files.

## 12. Local Path and Privacy Scan

Current-tree result: no occurrence of the actual local username or its Windows user path
remains. Early environment/handoff documents were retained but generalized to
`<project-root>`, `<legacy-workspace>` or `<local-user-root>`.

Generic checklist patterns such as `C:\Users\` and code/test `file://` rejection strings
remain intentionally because they are security rules, not local environment leakage.

Git-history result: **risk found**. Seven historical commits/files still contain the old
personal path in reachable history:

- `docs/development.md`
- `docs/environment-audit.md`
- `docs/plans/2026-07-13-stage-2-backend-foundation.md`
- `docs/specs/stage-6-rag-citation-design.md`
- `docs/stage-2-implementation-report.md`
- `docs/stock-research-agent-project-handoff-2026-07-13.md`
- `docs/superpowers/specs/2026-07-13-stage-2-backend-foundation-design.md`

This round did not run `filter-repo`, `filter-branch`, BFG, rebase or force push. Public
upload of full history must wait for an explicit owner decision on history sanitation or a
new-history publication strategy.

## 13. Database and Raw Data Scan

- Tracked/untracked `*.db`, `*.sqlite`, `*.sqlite3`, dump, backup or PostgreSQL data
  directories: none.
- Test database files: none in the repository.
- Runtime Raw Provider Artifacts, Provider cache, download, logs or Blob directories:
  none in the Git candidate set.
- The project-owned PostgreSQL cluster exists outside the repository and is ignored by
  Git scope.

## 14. Large File Scan

| Scope | >10MB | >50MB | >100MB |
|---|---:|---:|---:|
| Current tracked/untracked candidate files | 0 | 0 | 0 |
| Reachable Git-history blobs | 0 | 0 | 0 |

The largest reachable historical blobs are under 100KB. Git LFS is not required and was
not installed.

## 15. Fixture Review

- Tushare fixture: 84-byte synthetic empty protocol envelope; explicitly
  `SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`, `OFFLINE`, `NOT_LIVE`, credential
  absent and test-only license status. Public risk is low subject to normal review.
- SEC fixture: 432-byte cropped metadata fixture, not a filing body and not a full
  response. Manifest/checksum and LF policy are present, but the manifest states
  personal offline research use and does not explicitly establish public redistribution
  permission. **Owner/legal/source-policy review remains required before publication.**
- Existing fixture checksum and `text eol=lf` rules were preserved.
- No Fixture is evidence of Live or production data coverage.

## 16. `.gitignore` Status

Status: strengthened without replacing existing rules.

Added coverage for environment variants, virtual environments, caches, coverage/build
outputs, IDE files, logs/temp files, local databases/backups, PostgreSQL data, Provider
data/cache, runtime blobs, credential directories and key/certificate extensions. Existing
fixture paths are not ignored.

Three existing `.superpowers/sdd/task-*-report.md` files are already tracked historical
artifacts even though `.superpowers/` is ignored. Numerous additional `.superpowers`
review diffs and cache files are ignored and will not upload. The owner should decide
whether the three tracked task reports are useful public history; this round did not delete
them.

## 17. `.gitattributes` and Line Endings

Status: unchanged and preserved.

The stable branch keeps the existing Stage 6–9 Fixture-specific `text eol=lf` rules,
including Provider JSON Fixtures. No `git add --renormalize .` or global line-ending
rewrite was performed.

Git produced Windows LF-to-CRLF conversion notices for several edited text files. These
are conversion notices, not `git diff --check` content errors. Stage 10's branch separately
contains its Live Evidence Fixture LF rules.

## 18. License

No `LICENSE`, `LICENSE.md` or `COPYING` file exists. No License was selected or added.
README states: `License: Not yet selected.`

This is not a Secret risk, but it requires an owner decision before presenting the project
as open source. A code License would not grant rights to third-party financial data.

## 19. Git History Risk

History review found:

- no committed `.env` other than `.env.example`;
- no private key history candidate;
- no real named Credential candidate;
- one dummy Bearer test history entry;
- no database, Raw Data or >100MB path/blob;
- reachable historical personal paths in seven files, as listed above.

Risk rating: **blocking for public full-history upload until the owner chooses a safe
history strategy.** No history was rewritten in this task.

## 20. Quality Verification

| Check | Result |
|---|---|
| `uv sync --frozen --all-groups` | PASS — 54 packages checked |
| `uv run ruff check .` | PASS — all checks passed |
| `uv run ruff format --check .` | PASS — 539 files already formatted |
| `uv run mypy src` | PASS — no issues in 248 source files |
| Focused documentation contracts | PASS — 6/6 after README/example correction |
| `uv run pytest -W error` | PASS — 2537 passed in 541.05s; zero failed/errors/skipped/warnings |

An earlier preliminary pytest run without `TEST_DATABASE_URL` was not accepted as evidence:
it skipped PostgreSQL tests and exposed six documentation-contract failures. The README and
`.env.example` were corrected, PostgreSQL 17.10 was started safely, and the complete valid
suite then passed.

## 21. Business-Code Modifications

Business code modifications in `src/`, `migrations/` or `tests/`: **none** on the
documentation branch.

Changes are limited to README, publication documents, generalized historical Markdown
paths, `.gitignore` and `.env.example`.

## 22. Remaining Blockers

1. Reachable Git history contains the previous personal Windows path.
2. SEC cropped Fixture public redistribution status is not explicitly cleared.
3. No project License has been selected.
4. Root `AGENTS.md` still records an older Stage 9 transition instruction and conflicts
   with the now-observed Stage 10 WIP history; it was outside this round's authorized edit
   list and needs an owner-approved update.
5. The owner must decide whether three tracked `.superpowers/sdd` task reports belong in
   the public repository.
6. Documentation changes require human diff review and remain uncommitted.

## 23. Recommended GitHub Branch Strategy

- Default branch: `main`, representing the stable Stage 1–9 baseline.
- Optional WIP branch: `stage-9/production-data-providers`, to preserve its task-level
  history if the owner accepts the history/privacy strategy.
- Optional WIP branch: `stage-10/controlled-live-evidence`, clearly labeled paused WIP.
- Do not merge Stage 10 into `main` for publication.
- Do not use the documentation branch as the public default branch.

## 24. Safe to Upload?

# NO

The current working tree is substantially cleaner and all quality gates pass, but a full
public upload would still expose historical personal paths and includes an SEC Fixture whose
public redistribution status has not been explicitly confirmed. License and stale repository
guidance also need owner decisions.

## 25. Recommended Next Action

Review the complete documentation diff, then decide separately:

1. how to publish without exposing historical personal paths;
2. whether to retain/remove or replace the SEC metadata Fixture;
3. which License, if any, to adopt;
4. whether to update `AGENTS.md` and retain tracked `.superpowers` reports;
5. only after those decisions, whether to commit the documentation changes.

No commit, push, remote, PR, merge, tag, release or Git-history rewrite was performed for
the GitHub documentation work.
