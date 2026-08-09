# Stage 3 Implementation Report

Date: 2026-07-14

## 1. Stage conclusion

**GO.** All Stage 3 acceptance gates are satisfied: domain separation,
deterministic resolution, versioned seed, PostgreSQL migration/integration,
read-only API, CLI, documentation, two Reflection rounds, zero unresolved
CRITICAL/HIGH finding, and all final quality commands exit 0. GO means Stage 3
is technically complete on its feature branch; it does not authorize a merge or
Stage 4.

## 2. Branch name

`stage-3/security-master`. Development did not occur on `main`, and the branch
has not been merged or pushed by this work.

## 3. Implemented scope

- Market, Exchange, ExchangeAlias, Issuer, IssuerIdentifier, Security,
  SecurityIdentifier, and SecurityAlias.
- Unicode-aware deterministic normalization and fixed-priority resolution.
- Unique, ambiguous, not-found, invalid, delisted, suspended, unknown, inactive,
  and dated-alias semantics.
- Versioned offline Industrial FII/Micron seed with per-field provenance.
- SQLAlchemy repository, Alembic revision, PostgreSQL tests, API, CLI, and docs.

## 4. Unimplemented scope

No price/bar/quote data, financial statement, filing or announcement body,
metric, valuation, report, RAG/vector database, model call, Agent workflow,
Agent Tool, MCP Server, frontend, broker, trading, or exchange calendar exists.
No Stage 4 work was started.

## 5. Data model

Issuer is the legal entity; Security is a specific listed instrument. Market is
the broad market type; Exchange is the concrete MIC venue. UUIDs are stable
internal keys. Raw and normalized identifiers/names/aliases are retained.
Controlled values use strings plus database CHECK constraints, not PostgreSQL
native ENUMs.

## 6. Tables and relationships

`markets 1→* exchanges 1→* exchange_aliases`; `issuers 1→* securities`;
`exchanges 1→* securities`; issuer/security identifiers and security aliases
belong to their respective owner. All owner foreign keys are `ON DELETE
RESTRICT`; ORM relationships do not silently delete children.

## 7. Constraint inventory

- Every table: named UUID primary key; non-null timezone-aware timestamps.
- `markets`: unique code; code/name/country/currency/status checks.
- `exchanges`: restricted market FK; unique MIC; MIC/name/country/timezone/
  currency/calendar/status checks.
- `exchange_aliases`: restricted exchange FK; globally unique normalized alias;
  raw/normalized length/grammar and alias-type checks.
- `issuers`: legal/display normalized length, V0.1 country, and status checks;
  names are intentionally not unique.
- issuer and security identifiers: restricted owner FK; unique scheme plus
  normalized value; scheme/value/source/validity checks.
- `securities`: restricted issuer/exchange FKs; unique exchange plus normalized
  symbol; symbol/type/currency/status/share-class/date checks.
- `security_aliases`: restricted security FK; unique security/type/normalized
  alias; raw/normalized/source/locale/validity checks. Cross-security shared
  aliases remain legal.

Pydantic validation mirrors structural codes and dates, adds IANA timezone and
normalization checks, and converts aware database timestamps to UTC.

## 8. Index inventory and purpose

- unique market code and MIC: exact master lookup;
- unique normalized exchange alias and exchange-id FK index: explicit venue;
- issuer normalized legal/display indexes: exact names;
- issuer legal/display `text_pattern_ops`: bounded prefix suggestions;
- issuer/security identifier unique scheme/value and owner indexes: exact ID
  lookup and ownership joins;
- exchange/symbol unique, normalized symbol, issuer-id, and symbol
  `text_pattern_ops`: exact/cross-exchange/prefix paths;
- security alias normalized, security-id, and alias `text_pattern_ops`: current
  exact alias and escaped bounded prefix paths.

No blind all-column index, `pg_trgm`, full-text, or vector index was added.

## 9. Normalization rules

NFKC, raw/post-NFKC maximum 256, trim, whitespace collapse, Latin uppercase,
full-width conversion, control/invisible rejection, and meaningful-content
validation apply deterministically. Symbol/exchange grammars restrict
separators. Company names retain meaningful Chinese/English characters.
`SEC_CIK` is digits-only, at most ten digits, and zero-padded to ten. Raw values
are never overwritten.

## 10. Resolution priority

1. explicit active exchange alias plus symbol;
2. confirmed external identifier;
3. normalized symbol;
4. current active alias;
5. issuer legal/display name;
6. bounded prefix suggestion;
7. NOT_FOUND.

Exact candidates resolve only when unique. Multiple exact candidates and every
non-empty prefix result are AMBIGUOUS. Venue recognition and symbol lookup use
one PostgreSQL statement snapshot. LIKE wildcard characters are escaped.
Candidate order is MIC, normalized symbol, UUID and is capped at ten.

## 11. API

- `GET /api/v1/securities/resolve?query=...`
- `GET /api/v1/securities/{security_id}`
- `GET /api/v1/issuers/{issuer_id}`

Safe business outcomes return HTTP 200; invalid query/UUID is 422; missing
details are 404. Success and error responses carry `X-Request-ID`. Every request
owns and closes one Session. Response models expose only master data.

## 12. CLI

- `stock-research securities seed-v0`
- `stock-research securities resolve QUERY [--json]`
- `stock-research securities show SECURITY_ID [--json]`

Exit codes are 0 resolved/success, 2 ambiguous, 3 not found, 4 invalid, and 1
operational/seed failure. The installed entry point was exercised by subprocess
against the isolated test database.

## 13. Industrial FII results

`601138` → RESOLVED/EXACT_SYMBOL; `601138.SH` →
RESOLVED/EXACT_EXCHANGE_SYMBOL; `工业富联` and
`富士康工业互联网股份有限公司` → RESOLVED/EXACT_ALIAS. Candidate is symbol
`601138`, MIC `XSHG`, market `CN_A`, currency `CNY`, listing status `UNKNOWN`.

## 14. Micron results

`MU` → RESOLVED/EXACT_SYMBOL; `NASDAQ:MU` →
RESOLVED/EXACT_EXCHANGE_SYMBOL; `Micron`, `Micron Technology`, and
`Micron Technology, Inc.` → RESOLVED/EXACT_ALIAS; `SEC_CIK:723125` →
RESOLVED/EXACT_IDENTIFIER. Candidate is `MU`, MIC `XNAS`, market `US_EQUITY`,
currency `USD`, listing status `UNKNOWN`.

## 15. Ambiguity results

The same `MU` on XNAS/XSHG returns AMBIGUOUS for the bare ticker while
`NASDAQ:MU` resolves XNAS. Two securities sharing `Micron` return AMBIGUOUS.
Prefix `MICR` returns AMBIGUOUS/PREFIX_SUGGESTION even with one candidate.
Ordering and ten-candidate truncation are byte-stable.

## 16. Negative examples

Empty, whitespace, punctuation-only, control-character, and overlong input are
INVALID_QUERY. `Micorn` remains NOT_FOUND; no spelling distance is used. A
recognized exchange with a missing symbol terminates NOT_FOUND. Inactive,
future, and expired aliases do not resolve. Literal `%`, `_`, and `\` prefixes
cannot expand into arbitrary LIKE patterns.

## 17. Seed idempotency

Development database run 1: version `security-master-v0.1.0`, inserted 21,
existing 0. Run 2: inserted 0, existing 21. PostgreSQL tests prove UUID-only,
natural-key-only, combined key collisions, concurrent advisory locking,
non-overwrite, and rollback of an earlier insert when a later conflict occurs.

## 18. Migration upgrade and rollback

Development: `0002 head → downgrade -1 → upgrade head`, exit 0. Isolated test:
`base → 0001_create_schema_meta → 0002_create_security_master → downgrade -1 →
upgrade head`, exit 0. Both end at `0002_create_security_master (head)`.
Downgrade is complete and does not remove Stage 2 `schema_meta` when moving back
one revision.

## 19. PostgreSQL integration

Real PostgreSQL 17 proves table creation, catalog constraints/indexes/opclasses,
foreign keys, uniqueness, CHECK rejection, deletion restrictions, rollback,
Session closure, seed idempotence/conflict/concurrency, alias validity, ticker
ambiguity, inactive/delisted behavior, snapshot-consistent explicit venue,
escaped prefix, API requests, CLI transactions, and data isolation. SQLite was
not used.

## 20. Ruff result

`uv run ruff check .` → exit 0, all checks passed.

## 21. Format result

`uv run ruff format --check .` → exit 0, 67 files already formatted.

## 22. mypy result

`uv run mypy src` → exit 0, no issues in 38 source files; strict mode remains.

## 23. pytest result

`uv run pytest -W error` → **300 passed in 36.03s**, exit 0, zero warnings,
no deleted Stage 2 tests, no ignored failure, and no unexplained skip.

## 24. Reflection Round 1

Five required roles reviewed the stage. Findings included recognized-exchange
fallthrough, alias deduplication before limit, two-statement snapshot risk,
unreachable INVALID_QUERY, raw-symbol ordering, timezone normalization, and
evidence gaps. All HIGH findings were fixed through targeted tests and approved
on independent re-review. See `docs/reflection/stage-3-round-1.md`.

## 25. Reflection Round 2

All 22 consistency/reproducibility checks passed using actual test or
operational evidence. No new CRITICAL/HIGH finding remains. See
`docs/reflection/stage-3-round-2.md`.

## 26. Fixed issues

All Round 1 findings and independent reviewer findings are FIXED: deterministic
terminal venue behavior, SQL deduplication, single-statement snapshot,
reachable invalid status, normalized sorting, validity boundaries, aware-time
UTC conversion, partial rollback proof, and installed-entry proof.

## 27. Unresolved issues

No unresolved Stage 3 implementation issue is known. Current limitations are
deliberate scope boundaries, not incomplete Stage 3 acceptance items.

## 28. CRITICAL and HIGH risk

Unresolved CRITICAL: 0. Unresolved HIGH: 0. No claim is made about production
load/performance, external providers, or later-stage behavior because those are
outside Stage 3.

## 29. Current limitations

Only two verified sample securities and two venues exist. Market/exchange
statuses and listing statuses remain UNKNOWN where evidence is absent.
No calendar, provider sync, fuzzy search, history ingestion, price, financial,
filing, RAG, Agent, Tool, MCP, frontend, broker, or trading feature exists.

## 30. Rollback

Code: revert Stage 3 commits on `stage-3/security-master`; do not reset user
work. Database: back up any non-sample data, then run `uv run alembic downgrade
0001_create_schema_meta` to remove Stage 3 tables while retaining Stage 2.
Re-upgrade with `uv run alembic upgrade head`; the seed never deletes records.

## 31. Git status

Branch is `stage-3/security-master`. Stage 3 is not merged into `main`, not
pushed by this work, and contains no Stage 4 file. Final handoff verification
requires a clean worktree after committing this report.

## 32. Eligibility for Stage 4

Technically GO for a future Stage 4 authorization because Stage 3 gates pass.
Operationally, Stage 4 is **not authorized in this task** and must not begin
until the user selects a Stage 3 finishing option and supplies/approves its
scope.

## 33. Stage 4 allowed scope

None is inferred. Only work explicitly enumerated in a future user-approved
Stage 4 specification is allowed. Stable `security_id` is ready for later data
binding, but readiness is not authorization to ingest that data.

## 34. Stage 4 prohibited scope

Until separately authorized: all Stage 4 implementation, external provider
connections, prices, financials, filing bodies, metrics, valuation, reports,
RAG, Agent/Tool/MCP, frontend, broker, and trading remain prohibited. The
current branch must not be auto-merged or force-pushed.
