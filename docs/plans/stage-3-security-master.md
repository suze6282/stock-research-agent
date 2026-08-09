# Stage 3 Security Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build an offline, PostgreSQL-backed security master that separates issuers from listed securities and resolves supported symbols, names, aliases, exchange-qualified symbols, and confirmed identifiers deterministically.

**Architecture:** Domain normalization, schemas, repository protocols, and the resolution service live under `domain/securities` and depend on neither FastAPI nor SQLAlchemy. SQLAlchemy models and the PostgreSQL repository implement persistence under `db/`; API and CLI create the same domain service over that repository. Versioned seed data is code-managed, transactionally applied, sourced only from the Stage 1 local evidence, and never embedded in Alembic.

**Tech Stack:** Python 3.12, Pydantic 2, SQLAlchemy 2, PostgreSQL 17, Alembic, FastAPI, Typer, structlog, pytest, Ruff, and strict mypy.

## Global Constraints

- Develop only on `stage-3/security-master`; never commit Stage 3 work directly to `main`.
- Runtime behavior and tests must not require the external internet. Loopback PostgreSQL is the only network dependency.
- Implement only security master data and deterministic identity resolution. Do not add prices, financial statements, filings, RAG, research Agents, Reflection runtime, MCP Server, frontend, broker, trading, or Stage 4 behavior.
- Preserve the Stage 2 application, error, request-ID, logging, CLI, migration, CI, Docker, and test contracts.
- Follow strict RED -> GREEN -> REFACTOR TDD for every production behavior. Never delete, skip, or weaken an existing test.
- Use real PostgreSQL integration tests; SQLite is not accepted as evidence.
- Use SQLAlchemy parameter binding and bounded queries. Escape `%`, `_`, and the escape character in every prefix `LIKE` query.
- Do not add `citext`, `pg_trgm`, full-text search, vector search, PostgreSQL native ENUMs, or other extensions.
- Use string columns plus named `CHECK` constraints for controlled values. Migrations must fully downgrade without deleting the Stage 2 `schema_meta` table.
- Do not connect during module import, create global Sessions, or share a Session across requests.
- `session_scope` never commits implicitly. Callers explicitly commit seed writes.
- Preserve raw values and store separate normalized values. Normalization is deterministic, local, Unicode NFKC based, and never model-assisted.
- Resolution input is at most 256 characters and candidate output is at most 10, with a stable order.
- Do not emit pseudo-confidence scores, choose a “famous” company, or use spelling distance to auto-resolve.
- Seed only facts confirmed in `docs/sample-data-validation/601138.SH.md`, `docs/sample-data-validation/MU.md`, and `docs/product-scope-v0.1.md`. Do not invent ISIN, CUSIP, SEDOL, LEI, Chinese unified credit code, provider IDs, dates, or status history.
- Keep raw database errors, SQL, table names, connection strings, secrets, and long raw queries out of API/CLI responses and logs.
- The final branch must remain unmerged; do not enter Stage 4.

---

## 1. Objective

- [x] Represent market type, exchange, issuer, listed security, identifiers, and aliases with stable internal UUIDs.
- [x] Resolve supported user input reproducibly to a security or a bounded result state.
- [x] Make the same service reusable by API, CLI, and future approved Tool/MCP adapters without implementing those adapters now.

## 2. In Scope

- [x] `Market`, `Exchange`, `ExchangeAlias`, `Issuer`, `IssuerIdentifier`, `Security`, `SecurityIdentifier`, and `SecurityAlias`.
- [x] Pure normalization, fixed-priority resolution, PostgreSQL repository, versioned seed, read-only API, CLI, migration, documentation, tests, and two Reflection rounds.
- [x] Industrial FII `601138` / `601138.SH` and Micron `MU` / `NASDAQ:MU` samples.

## 3. Out of Scope

- [x] No market data, prices, filings, financial facts, calculations, valuation, research reports, RAG, vector database, Agent workflow, runtime Reflection, MCP protocol, frontend, broker, trading, or production deployment.
- [x] No fuzzy spelling correction, popularity ranking, arbitrary sorting, unbounded search, or external network lookup.

## 4. Data Model

| Entity | Required Stage 3 fields | Controlled values |
| --- | --- | --- |
| `markets` | UUID id, code, name, country, default currency, status, UTC timestamps | status: `ACTIVE`, `INACTIVE`, `UNKNOWN` |
| `exchanges` | UUID id, market FK, MIC, names, country, IANA timezone, currency, nullable calendar code, status, timestamps | same status values |
| `exchange_aliases` | UUID id, exchange FK, raw/normalized alias, alias type, active flag, timestamps | type: `MIC`, `SUFFIX`, `SHORT_NAME`, `DISPLAY_NAME` |
| `issuers` | UUID id, legal/display names and normalized forms, country, issuer status, timestamps | status: `ACTIVE`, `INACTIVE`, `UNKNOWN` |
| `issuer_identifiers` | UUID id, issuer FK, scheme, raw/normalized value, source, validity, primary flag, timestamps | uppercase scheme token; V0.1 seed/runtime explicitly supports confirmed `SEC_CIK` only |
| `securities` | UUID id, issuer/exchange FKs, raw/normalized symbol, display name, type, nullable share class, currency, listing status/dates, primary flag, timestamps | type: `COMMON_STOCK`; status: `ACTIVE`, `SUSPENDED`, `DELISTED`, `UNKNOWN` |
| `security_identifiers` | UUID id, security FK, scheme, raw/normalized value, source, validity, primary flag, timestamps | uppercase scheme token; no SecurityIdentifier row is seeded in V0.1 because no required non-symbol security identifier is confirmed |
| `security_aliases` | UUID id, security FK, raw/normalized alias, type, locale, source, validity, active flag, timestamps | prompt-defined alias types |

Stable UUIDs are internal keys. Human names, ticker symbols, exchange aliases, and external identifiers never become primary keys.

## 5. Table Relationships

```text
Market 1 ── * Exchange 1 ── * ExchangeAlias
                    │
Issuer 1 ── * Security * ───┘
   │              │
   *              ├── * SecurityIdentifier
IssuerIdentifier  └── * SecurityAlias
```

- All master-data foreign keys use `ON DELETE RESTRICT` and ORM relationships omit delete cascade.
- Issuer deletion is blocked while securities or issuer identifiers exist.
- Exchange deletion is blocked while securities or exchange aliases exist.
- The schema does not assert that one issuer has only one security or only one primary listing.

## 6. Database Constraints

- Named primary, foreign-key, unique, and check constraints are present in both ORM metadata and migration.
- `markets.code` and `exchanges.mic` are unique uppercase stable codes.
- Country codes match two uppercase letters; currencies match three uppercase letters; MICs match four uppercase letters/digits.
- Exchange alias normalized values are globally unique so cross-exchange conflicts fail explicitly.
- Issuer names are not unique.
- `(scheme, normalized_value)` is unique independently for issuer and security identifiers.
- `(exchange_id, normalized_symbol)` is unique; the same symbol remains valid on another exchange.
- `(security_id, alias_type, normalized_alias)` is unique, while different securities may share an alias.
- Identifier and alias `valid_to >= valid_from`; security `delisting_date >= listing_date`.
- UTC-aware timestamp columns are non-null.
- Pydantic validators enforce the same structural rules plus semantic IANA timezone validation through `zoneinfo.ZoneInfo`.

## 7. Index Design

| Index/query key | Purpose |
| --- | --- |
| unique `markets.code` | exact market lookup |
| unique `exchanges.mic` | exact exchange lookup |
| unique `exchange_aliases.normalized_alias` | exchange-qualified symbol parsing and conflict detection |
| issuer legal/display normalized B-trees plus `text_pattern_ops` prefix indexes | exact issuer-name match and bounded prefix suggestions |
| unique issuer identifier scheme/value | exact issuer identifier match and cross-issuer conflict prevention |
| unique exchange/symbol plus symbol exact and pattern index | explicit-exchange, unique-symbol, and prefix paths |
| unique security identifier scheme/value | exact security identifier match and conflict prevention |
| security alias normalized exact and pattern indexes | current alias match and bounded prefix suggestions |

No index is added for fields without a Stage 3 query path.

## 8. Migration Order

1. Create markets.
2. Create exchanges and exchange aliases.
3. Create issuers and issuer identifiers.
4. Create securities, security identifiers, and security aliases.
5. Add named indexes after their tables.
6. Downgrade in exact reverse dependency order, retaining `schema_meta`.

Migration `0002_create_security_master` contains schema only. Seed data is never inserted by Alembic.

## 9. Normalization Rules

- `normalize_free_text`: require a string, enforce raw and post-NFKC length <= 256, Unicode NFKC, reject Unicode control/format characters, trim, collapse whitespace, reject empty or punctuation-only content.
- `normalize_symbol`: apply free-text safety, remove internal whitespace, uppercase ASCII letters, normalize full-width forms through NFKC, preserve only validated alphanumerics plus `.`, `:`, and `-` where syntactically relevant.
- `normalize_exchange_alias`: apply NFKC, trim and uppercase, then validate an allow-list grammar before normalization. Only a single authorized leading dot and whitespace are removable; any other punctuation/control character (for example `$NASDAQ`, `NAS%DAQ`, or repeated separators) is rejected instead of being silently stripped. `.SH` and `SH` normalize to `SH`.
- `normalize_company_name`: NFKC, trim/collapse whitespace, uppercase Latin text, normalize common Chinese/full-width punctuation deterministically, and preserve meaningful alphanumeric/CJK content.
- `normalize_external_identifier`: scheme-specific and deterministic. V0.1 runtime support is limited to confirmed `SEC_CIK`: digits-only and left-padded to exactly 10 digits. The database scheme column remains a structurally validated uppercase token so the schema need not migrate when a future stage authorizes another verified scheme; unknown schemes are not accepted by V0.1 resolution or Seed.
- Functions return new strings and never mutate or replace stored raw values.

## 10. Resolution Priority

`SecurityResolutionResult` contains `status`, `original_query`, `normalized_query`, `match_type`, `candidate_count`, `candidates`, and `warnings`. Status is exactly `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, or `INVALID_QUERY`; match type is exactly `EXACT_EXCHANGE_SYMBOL`, `EXACT_SYMBOL`, `EXACT_IDENTIFIER`, `EXACT_ALIAS`, `EXACT_ISSUER_NAME`, `PREFIX_SUGGESTION`, or `NONE`. Each candidate exposes `security_id`, `issuer_id`, issuer/security display names, symbol, exchange MIC/name, market code, currency, listing status, and a deterministic `match_reason`—never a confidence score.

1. Parse a verified exchange alias plus exact normalized symbol (`EXACT_EXCHANGE_SYMBOL`).
2. Exact issuer/security external identifier (`EXACT_IDENTIFIER`).
3. Unique normalized symbol (`EXACT_SYMBOL`).
4. Current active alias whose validity includes today or is open-ended (`EXACT_ALIAS`).
5. Exact issuer legal/display name, returning all securities for matching issuers (`EXACT_ISSUER_NAME`).
6. Bounded prefix suggestions (`PREFIX_SUGGESTION`), always non-resolved.
7. `NOT_FOUND`.

The service receives an injectable UTC clock/as-of date so alias validity is testable and reproducible. `ALIAS:SYMBOL` and `SYMBOL.SUFFIX` are treated as exchange-qualified only when the exchange alias exists; explicit `SCHEME:VALUE` is treated as an identifier only for supported schemes and only after exchange-symbol matching. Multiple exact candidates return `AMBIGUOUS`. Because the result vocabulary has no separate `SUGGESTIONS` status and prefix matches must never resolve, every non-empty prefix result uses `AMBIGUOUS` plus `PREFIX_SUGGESTION` and a warning, including a single candidate; empty prefix results use `NOT_FOUND`. Delisted securities remain visible with a warning. Inactive aliases do not participate. Candidate order is `(exchange_mic, normalized_symbol, security_id)` and final results are capped at 10.

## 11. Repository Boundary

```python
class SecurityMasterRepository(Protocol):
    def find_exchange_symbol(self, exchange_alias: str, symbol: str, limit: int) -> Sequence[SecurityCandidate]: ...
    def find_external_identifier(self, values: Mapping[IdentifierScheme, str], limit: int) -> Sequence[SecurityCandidate]: ...
    def find_symbol(self, normalized_symbol: str, limit: int) -> Sequence[SecurityCandidate]: ...
    def find_active_alias(self, normalized_alias: str, limit: int) -> Sequence[SecurityCandidate]: ...
    def find_issuer_name(self, normalized_name: str, limit: int) -> Sequence[SecurityCandidate]: ...
    def suggest_prefix(self, normalized_query: str, limit: int) -> Sequence[SecurityCandidate]: ...
    def get_security(self, security_id: UUID) -> SecurityDetail | None: ...
    def get_issuer(self, issuer_id: UUID) -> IssuerDetail | None: ...

class SecurityMasterSeedRepository(Protocol):
    def acquire_seed_lock(self, seed_version: str) -> None: ...
    def apply_manifest(self, manifest: SecurityMasterSeedManifest) -> SeedResult: ...
```

The domain service accepts these protocols and never creates a Session. SQLAlchemy implementation uses a caller-owned Session, parameterized statements, hard-coded ordering, escaped prefix patterns, and bounded limits.

## 12. API

- `GET {api_prefix}/securities/resolve?query=...`: HTTP 200 for `RESOLVED`, `AMBIGUOUS`, and `NOT_FOUND`; domain-invalid input maps to the uniform 422 error envelope.
- `GET {api_prefix}/securities/{security_id}`: master data only; invalid UUID uses existing validation handling and missing UUID returns safe 404.
- `GET {api_prefix}/issuers/{issuer_id}`: issuer master data only; missing UUID returns safe 404.
- Candidate fields follow the prompt exactly. Request correlation remains in `X-Request-ID` and application logs.
- FastAPI depends on a per-request Session and the same `SecurityResolutionService` used by CLI.

## 13. CLI

```text
stock-research securities seed-v0
stock-research securities resolve QUERY [--json]
stock-research securities show SECURITY_ID [--json]
```

- Exit codes: resolved/seed success `0`, ambiguous `2`, not found `3`, invalid query `4`, operational/seed conflict `1`.
- Human output is concise and JSON output is the domain model serialization.
- CLI creates and disposes its engine, uses a caller-owned Session, explicitly commits successful seed writes, and invokes the shared domain service.

## 14. Seed Mechanism

- Manifest version: `security-master-v0.1.0`.
- Internal UUID constants, raw values, normalized values, and local evidence paths are versioned in a production manifest module.
- PostgreSQL advisory transaction lock serializes concurrent seed attempts.
- Existing identical rows are counted and left unchanged; missing rows are inserted; any incompatible seeded field or natural-key/UUID collision raises `SeedConflictError`.
- User-added unrelated aliases/identifiers are preserved. The seed never updates or deletes existing rows.
- The CLI owns transaction commit/rollback. Repeated execution produces zero duplicates.

## 15. Sample Data and Provenance

The manifest records provenance per field. Issuer/security names, symbols, currencies, exchange names, `601138.SH`, Nasdaq/MU, and Micron CIK come from the Stage 1 validation files. MICs, IANA timezones, and the explicitly listed exchange aliases are deterministic Stage 3 specification mappings required to represent and resolve those exchanges; they are not mislabeled as Stage 1 business facts. The implementation report keeps these two provenance classes separate. No other mapping is inferred.

| Sample | Seeded Stage 1 facts plus Stage 3-required mappings | Deliberately missing/unknown |
| --- | --- | --- |
| Industrial FII | Stage 1: issuer `富士康工业互联网股份有限公司`, display/security name `工业富联`, symbol `601138`, Shanghai Stock Exchange, `601138.SH`, market `CN_A`, currency `CNY`; Stage 3 mappings: MIC `XSHG`, timezone `Asia/Shanghai`, exchange aliases `.SH`, `SH`, `SSE`, `XSHG` | no unverified issuer identifier, listing date, calendar, ISIN, provider ID, or active-status claim; listing status `UNKNOWN` |
| Micron | Stage 1: issuer `Micron Technology, Inc.`, display `Micron Technology`, symbol `MU`, Nasdaq, market `US_EQUITY`, currency `USD`, confirmed CIK `0000723125`; Stage 3 mappings: MIC `XNAS`, timezone `America/New_York`, aliases `NASDAQ:MU`, `NASDAQ`, `XNAS`; confirmed company-name aliases `Micron`, `Micron Technology`, and the legal name | no SecurityIdentifier, ISIN, CUSIP, SEDOL, LEI, listing date, provider ID, calendar, or separately confirmed current listing-state record; listing status `UNKNOWN` |

Calendar codes remain null because Stage 3 does not implement or claim exchange calendars.

## 16. Test Matrix

- Pure unit tests cover all prompt normalization inputs, Pydantic data rules, deterministic priority, ambiguity, inactive aliases, delisted warnings, prefix behavior, limit 10, stable ordering, raw-value preservation, and fake-repository service isolation.
- PostgreSQL tests inspect all tables, foreign keys, named unique/check constraints, indexes, delete restrictions, cross-exchange same symbol, identifier conflicts, rollback, session closure, seed idempotence/conflict/concurrency, and real resolution queries.
- Migration tests run base -> 0001 -> 0002 -> downgrade 0001 -> upgrade head on the isolated test database and a development upgrade -> downgrade -1 -> upgrade cycle.
- API contract tests use seeded PostgreSQL and cover both samples, ambiguity, not found, invalid/long input, stable schemas, headers, 404, OpenAPI, and absence of price/financial fields.
- CLI integration tests cover seed twice, sample queries, ambiguity, not found, invalid input, JSON, help, exit codes, and shared service behavior.
- The complete Stage 2 suite remains present and passing with warnings treated as errors.

## 17. Reflection

- Round 1 writes `docs/reflection/stage-3-round-1.md` with the five required roles and fields for every finding.
- Every `CRITICAL` and `HIGH` finding is reproduced by a failing test and fixed before Round 2.
- Round 2 writes `docs/reflection/stage-3-round-2.md` and executes all 22 required consistency/reproducibility checks.

## 18. Acceptance Criteria

- All original Stage 3 model, constraint, normalization, resolution, seed, API, CLI, migration, documentation, PostgreSQL, and safety requirements have direct test evidence.
- Both samples resolve under every required input.
- `uv sync`, Ruff, format, strict mypy, and full pytest all exit 0 with zero warnings.
- Both Reflection rounds exist and have zero open `CRITICAL`/`HIGH` findings.
- No external network dependency, prohibited feature, main merge, or Stage 4 work exists.

## 19. Rollback

- Code rollback: revert Stage 3 commits only on `stage-3/security-master`.
- Schema rollback: back up the explicitly confirmed non-production database, run `uv run alembic downgrade 0001_create_schema_meta`, and verify all eight Stage 3 tables are absent while `schema_meta` remains.
- Seed rollback is schema rollback for this sample-only stage; the seed command itself never deletes user data.
- Native PostgreSQL stop remains limited to the project-owned cluster and is not required for a code rollback.

---

### Task 1: Domain contracts and deterministic normalization

**Files:**
- Create: `src/stock_research_agent/domain/securities/__init__.py`
- Create: `src/stock_research_agent/domain/securities/enums.py`
- Create: `src/stock_research_agent/domain/securities/exceptions.py`
- Create: `src/stock_research_agent/domain/securities/normalization.py`
- Create: `src/stock_research_agent/domain/securities/schemas.py`
- Create: `src/stock_research_agent/domain/securities/repositories.py`
- Create: `tests/unit/test_security_normalization.py`
- Create: `tests/unit/test_security_schemas.py`
- Modify: `tests/unit/test_module_boundaries.py`

**Interfaces:** Produces the enums, `InvalidSecurityQuery`, `SecurityCandidate`, `SecurityResolutionResult`, detail schemas, seed record schemas, and repository protocols described above.

- [x] Write table-driven normalization tests for every prompt case and observe missing-module RED.
- [x] Implement free-text, symbol, exchange, company-name, and scheme-specific identifier normalization with raw values unchanged.
- [x] Write schema validation tests for MIC/country/currency/timezone/date/status and observe RED.
- [x] Implement Pydantic schemas and string enums without FastAPI/SQLAlchemy imports.
- [x] Add import/boundary tests proving no framework, network, Agent, MCP, RAG, price, or financial dependency.
- [x] Run focused tests, Ruff, format, strict mypy, and the full suite.
- [x] Commit `feat: add security master domain contracts`.

### Task 2: SQLAlchemy models, indexes, and reversible migration

**Files:**
- Create: `src/stock_research_agent/db/models/__init__.py`
- Create: `src/stock_research_agent/db/models/security_master.py`
- Create: `migrations/versions/0002_create_security_master.py`
- Create: `tests/unit/test_security_models.py`
- Create: `tests/integration/test_security_master_postgres.py`
- Modify: `migrations/env.py`
- Modify: `tests/integration/test_migrations.py`

**Interfaces:** Produces ORM classes `Market`, `Exchange`, `ExchangeAlias`, `Issuer`, `IssuerIdentifier`, `Security`, `SecurityIdentifier`, and `SecurityAlias` registered on `Base.metadata`.

- [x] Write metadata and real PostgreSQL constraint/index/delete-policy tests; run them to RED before model/migration code exists.
- [x] Implement annotated SQLAlchemy 2 models with UUID keys, named constraints, restricted foreign keys, and focused indexes.
- [x] Write migration-chain tests for 0001 -> 0002 -> downgrade -> upgrade and offline SQL; observe RED.
- [x] Implement `0002_create_security_master` schema-only upgrade/downgrade and register model metadata in Alembic.
- [x] Prove duplicate exchange symbol fails, same symbol on another exchange succeeds, invalid dates/codes/statuses fail, and identifier conflicts fail in PostgreSQL.
- [x] Run development and isolated-test migration cycles, leaving both at head.
- [x] Run focused/static/type/full gates and commit `feat: add security master schema and migration`.

### Task 3: Versioned idempotent seed and PostgreSQL repository

**Files:**
- Create: `src/stock_research_agent/domain/securities/seed.py`
- Create: `src/stock_research_agent/db/repositories/__init__.py`
- Create: `src/stock_research_agent/db/repositories/security_master.py`
- Create: `tests/unit/test_security_seed.py`
- Create: `tests/integration/test_security_seed_postgres.py`

**Interfaces:** Produces `SECURITY_MASTER_SEED_V0`, `SecurityMasterSeedService.seed(repository) -> SeedResult`, and `SqlAlchemySecurityMasterRepository(session)` implementing both protocols.

- [x] Write manifest/source/normalization tests and fake-repository idempotence/conflict tests; observe RED.
- [x] Implement the confirmed two-sample manifest with fixed internal UUIDs and explicit source paths.
- [x] Write real PostgreSQL tests for first seed, second seed, no duplicate security, incompatible user modification, advisory-lock concurrency, transaction rollback, and user-added row preservation; observe RED.
- [x] Implement parameterized lookups, advisory transaction locking, insert-if-missing, and compare-without-overwrite behavior.
- [x] Verify no seed data exists in migration files and no network function is imported or called.
- [x] Run focused/integration/static/type/full gates and commit `feat: add versioned security master seed`.

### Task 4: Deterministic resolution service and SQL query paths

**Files:**
- Create: `src/stock_research_agent/domain/securities/resolution.py`
- Create: `tests/unit/test_security_resolution.py`
- Create: `tests/integration/test_security_resolution_postgres.py`
- Modify: `src/stock_research_agent/db/repositories/security_master.py`

**Interfaces:** Produces `SecurityResolutionService(repository, max_candidates=10)` with `resolve(query: str) -> SecurityResolutionResult`, and repository detail/query methods.

- [x] Write fake-repository RED tests for every required query, fixed priority, ambiguity, delisted warning, inactive alias, prefix non-resolution, no fuzzy match, stable ordering, and limit 10.
- [x] Implement syntax parsing and the exact seven-step priority without FastAPI or Session construction.
- [x] Write real seeded-PostgreSQL RED tests for both samples, shared aliases, duplicate cross-exchange ticker, identifiers, prefix escaping, and bounded candidates.
- [x] Implement parameterized SQLAlchemy queries, active/validity filters, deduplication, hard-coded stable ordering, and escaped prefix `LIKE` patterns.
- [x] Verify repeated input/database state produces byte-equivalent JSON serialization.
- [x] Run focused/integration/static/type/full gates and commit `feat: add deterministic security resolution`.

### Task 5: Read-only security master API

**Files:**
- Create: `src/stock_research_agent/api/routes/securities.py`
- Create: `src/stock_research_agent/api/routes/issuers.py`
- Create: `tests/contract/test_security_api_contract.py`
- Modify: `src/stock_research_agent/api/dependencies.py`
- Modify: `src/stock_research_agent/api/router.py`
- Modify: `src/stock_research_agent/main.py`

**Interfaces:** Produces the three specified GET endpoints under the existing prefix and per-request Session/repository/service dependencies.

- [x] Write seeded PostgreSQL contract tests for all required resolution/detail/OpenAPI/error/no-leak cases and observe route-not-found RED.
- [x] Extend lifespan with a session factory but no connection-at-import, and add a per-request closing Session dependency.
- [x] Implement thin routes that call `SecurityResolutionService` and repository detail methods; map invalid query to 422 and missing details to 404 through `ApiError`.
- [x] Assert candidate schemas, request IDs, max query length, no price/financial fields, no SQL/URL leakage, and no internet calls.
- [x] Run focused/integration/static/type/full gates and commit `feat: add security master API`.

### Task 6: Securities CLI over the shared service

**Files:**
- Create: `tests/integration/test_security_cli.py`
- Modify: `src/stock_research_agent/cli.py`
- Modify: `tests/unit/test_cli.py`

**Interfaces:** Produces the `securities` Typer group with `seed-v0`, `resolve`, and `show`, using the same domain service and SQL repository as the API.

- [x] Write CLI unit and real PostgreSQL RED tests for help, seed twice, sample inputs, ambiguity, not found, invalid query, JSON, exit codes, safe failures, and engine/session cleanup.
- [x] Implement shared engine/session setup helpers, explicit seed commit, human/JSON rendering, and fixed exit codes without copied resolution logic.
- [x] Add an adversarial test that proves conflicting seed data fails without overwrite or partial commit.
- [x] Run installed-entry smoke tests plus focused/integration/static/type/full gates.
- [x] Commit `feat: add security master CLI`.

### Task 7: Documentation, security consistency, and operational migration proof

**Files:**
- Create: `docs/security-master.md`
- Create: `docs/security-resolution.md`
- Create: `docs/api.md`
- Modify: `README.md`
- Modify: `docs/database.md`
- Modify: `docs/testing.md`
- Modify: `.github/workflows/backend-ci.yml` only if Stage 3 commands require an explicit additional gate.

**Interfaces:** Documents exact models, sample facts/gaps, indexes, normalization, resolution semantics, seed, API, CLI, migration, current limits, and future `security_id` binding.

- [x] Write documentation-consistency tests/checks for commands, paths, endpoints, forbidden features, and sample evidence.
- [x] Write all six required documents/updates with the twenty prompt topics and no unsupported claims.
- [x] Execute every locally applicable documented command, including seed twice, API/CLI samples, and migration downgrade/upgrade.
- [x] Prove external internet is not required and scan tracked files for secret/provider-ID placeholders or prohibited Stage 4 modules.
- [x] Run complete quality gates and commit `docs: document security master workflows`.

### Task 8: Two-round Reflection, whole-stage evidence, and report

**Files:**
- Create: `docs/reflection/stage-3-round-1.md`
- Create: `docs/reflection/stage-3-round-2.md`
- Create: `docs/stage-3-implementation-report.md`

**Interfaces:** Reflection findings use `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW`; the report conclusion is exactly `GO`, `CONDITIONAL GO`, or `NO-GO` and contains all 34 required sections.

- [x] Run a fresh complete gate and operational verification against real PostgreSQL with both databases at head.
- [x] Perform Round 1 from all five required roles, record every required finding field, and fix all `CRITICAL`/`HIGH` findings through RED/GREEN tests.
- [x] Perform all 22 Round 2 checks through actual tests and fix all `CRITICAL`/`HIGH` findings.
- [x] Write the 34-section implementation report with exact commands, counts, constraints/index purposes, sample/ambiguity/negative results, rollback, risks, branch/Git state, and Stage 4 gate.
- [x] Request a broad whole-branch review, fix every Critical/Important finding with focused tests, and re-review.
- [x] Rerun `uv sync`, Ruff, format, strict mypy, and `pytest -W error`; restore development/test databases to head and confirm clean Git status.
- [x] Commit `docs: report stage 3 implementation evidence` and present the four user-selected finishing options without choosing one.

## Plan Self-Review

- [x] All 29 prompt sections map to an explicit design section or task.
- [x] All eight entities, relationships, delete policies, constraints, indexes, migration order, API, CLI, seed, samples, tests, Reflection rounds, acceptance, and rollback are covered.
- [x] Issuer/Security and Market/Exchange are separate throughout.
- [x] Confirmed sample facts are distinguished from unknown fields; prohibited identifiers are absent.
- [x] Resolution priority, result statuses, match types, bounded candidates, deterministic ordering, and no-confidence rule are explicit.
- [x] PostgreSQL, downgrade/upgrade, seed idempotence, ambiguity, inactive alias, delisted security, and Stage 2 regressions have real test tasks.
- [x] No task adds external network calls, price/financial/RAG/Agent/MCP/trading/frontend behavior, or a main merge.
- [x] No `TBD`, `TODO`, placeholder implementation, or contradictory interface remains.
