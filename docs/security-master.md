# Security master

## Domain boundaries

**Issuer ≠ Security.** An Issuer is the legal company. A Security is one listed
instrument issued by that company on one Exchange. One issuer may own several
securities, share classes, or listings; `is_primary_listing` does not impose a
one-security rule. Names and ticker symbols are mutable business attributes,
not primary keys. Future prices, statements, filings, documents, and research
must bind to the stable `security_id` (or to `issuer_id` when the fact truly
belongs to the company), never to a display name alone.

**Market ≠ Exchange.** A Market describes a broad market type such as `CN_A` or
`US_EQUITY`. An Exchange is a concrete venue identified by an ISO 10383 MIC,
such as `XSHG` or `XNAS`. Exchange timezone values are IANA names and currency
values are ISO 4217 codes. `calendar_code` is only a future mapping field; no
trading calendar, holiday, session, or trading-hours claim exists in Stage 3.

## Tables and relationships

```text
Market 1 ── * Exchange 1 ── * ExchangeAlias
                    │
Issuer 1 ── * Security * ───┘
   │              │
   *              ├── * SecurityIdentifier
IssuerIdentifier  └── * SecurityAlias
```

The eight tables are `markets`, `exchanges`, `exchange_aliases`, `issuers`,
`issuer_identifiers`, `securities`, `security_identifiers`, and
`security_aliases`. Every record has a UUID and UTC timestamps. PostgreSQL may
return a `timestamptz` in the session timezone; the domain contract converts
aware timestamps to UTC and rejects naive timestamps.

All ownership foreign keys use **ON DELETE RESTRICT**. Deleting an issuer cannot
silently delete its securities or future research data. ORM relationships do
not define delete cascade. The database uses named CHECK and UNIQUE constraints
rather than PostgreSQL native ENUMs.

Key uniqueness rules are:

- market `code` and exchange `mic` are unique;
- normalized exchange aliases are globally unique, so an alias conflict is an
  explicit data error;
- issuer names are intentionally not unique;
- `(scheme, normalized_value)` is unique independently for issuer and security
  identifiers;
- `(exchange_id, normalized_symbol)` is unique, while the same ticker on two
  exchanges is valid;
- `(security_id, alias_type, normalized_alias)` is unique, while two securities
  may share an alias and therefore resolve as `AMBIGUOUS`.

Dates obey `valid_to >= valid_from` and `delisting_date >= listing_date` when
both ends exist. Security type is currently `COMMON_STOCK`; listing status is
`ACTIVE`, `SUSPENDED`, `DELISTED`, or `UNKNOWN`.

## Identifiers and aliases

`IssuerIdentifier` and `SecurityIdentifier` retain raw and normalized values,
their source, optional validity, and nullable primary semantics. V0.1 runtime
resolution supports only the confirmed `SEC_CIK` issuer scheme. It does not
invent ISIN, CUSIP, SEDOL, LEI, a Chinese unified social credit code, or a
provider ID. No SecurityIdentifier row is needed by the V0.1 seed.

`ExchangeAlias` maps current spellings such as `.SH`, `SH`, `SSE`, `XSHG`,
`NASDAQ`, and `XNAS` to an exchange. `SecurityAlias` supports symbols with an
exchange, short/legal/English names, provider spellings, and former names.
Raw and normalized forms are both stored. An inactive alias or an alias outside
its validity interval does not participate in current exact or prefix lookup.

## Indexes and query purpose

- unique market code and MIC indexes serve exact master-data lookup;
- the unique normalized exchange-alias index serves qualified-symbol lookup;
- issuer normalized legal/display B-trees serve exact names;
- issuer-name, security-symbol, and security-alias `text_pattern_ops` indexes
  serve bounded prefix suggestions;
- the exchange/symbol unique index serves exact venue-qualified lookup;
- identifier scheme/value unique indexes serve exact external identifiers;
- security alias normalized indexes serve exact current alias lookup.

There is no `citext`, `pg_trgm`, full-text, vector, or unbounded fuzzy search.

## Versioned seed

The seed manifest is `security-master-v0.1.0` and is applied with:

```powershell
uv run stock-research securities seed-v0
```

It is offline, transactional, protected by a PostgreSQL transaction advisory
lock, and idempotent. The first application inserts the 21 versioned records;
the second reports the same records as existing and inserts none. Matching
records are never overwritten. UUID/natural-key collisions or a user-modified
seed field fail the transaction explicitly.

The manifest, production seed logic, and test fixtures are separate. Seed data
is not embedded in an Alembic migration. Per-field provenance distinguishes
Stage 1 evidence, deterministic normalization, and a required Stage 3 mapping.

## V0.1 samples and unknown fields

- Industrial FII: issuer `富士康工业互联网股份有限公司`, display/security name
  `工业富联`, `601138` on `XSHG`, market `CN_A`, currency `CNY`, plus confirmed
  name and `601138.SH` aliases.
- Micron: issuer `Micron Technology, Inc.`, display/security name
  `Micron Technology`, `MU` on `XNAS`, market `US_EQUITY`, currency `USD`,
  confirmed CIK `0000723125`, and the confirmed Micron name aliases.

Unconfirmed listing dates, calendar codes, share classes, primary-listing
claims, security identifiers, and active-status history remain null or
**unknown**. The samples deliberately use `UNKNOWN` where Stage 1 did not prove
a current status. No field is guessed merely to make the dataset look complete.

## Current limits

Stage 3 stores identity master data only. It has no prices, market bars,
financial statements, filings or announcement bodies, valuation, report
generation, RAG/vector database, Agent workflow, Agent Tool, MCP Server,
frontend, broker, or trading behavior. Exchange calendars are not implemented.
Resolution is deterministic and offline; see
[`security-resolution.md`](security-resolution.md).
