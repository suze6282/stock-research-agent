# Deterministic security resolution

The resolver answers which stable security a user meant without a model,
external provider, spelling distance, popularity score, or pseudo-confidence.
API and CLI instantiate the same `SecurityResolutionService` over the same
repository protocol. The domain service has no FastAPI or SQLAlchemy dependency
and is reusable by a future approved Tool or MCP adapter; Stage 3 does not build
either adapter.

## Normalization

All functions are deterministic and begin with Unicode NFKC. They enforce a
256-character input limit, trim edges, collapse whitespace, reject control or
invisible characters, and reject empty or punctuation-only input.

- `normalize_free_text` preserves meaningful punctuation and uppercases Latin
  text.
- `normalize_symbol` removes whitespace, uppercases, and permits validated
  alphanumerics separated by `.`, `:`, or `-`.
- `normalize_exchange_alias` accepts the restricted exchange grammar and maps a
  single leading `.SH` form to `SH`; it does not guess an exchange from a code
  prefix.
- `normalize_company_name` normalizes common English/Chinese punctuation while
  preserving meaningful name characters.
- `normalize_external_identifier` currently accepts only digits-only `SEC_CIK`
  and left-pads it to ten digits.

Raw database values are never overwritten by their normalized forms.

## Fixed priority

The first non-empty exact step wins. Candidate order is stable by exchange MIC,
normalized symbol, then security UUID; output is capped at **最多 10** candidates.

1. `EXACT_EXCHANGE_SYMBOL` — an active, recognized exchange alias plus an exact
   symbol, read in one PostgreSQL statement snapshot.
2. `EXACT_IDENTIFIER` — a confirmed external identifier such as `SEC_CIK`.
3. `EXACT_SYMBOL` — the normalized symbol across exchanges.
4. `EXACT_ALIAS` — a current active SecurityAlias whose validity includes the
   injected clock date.
5. `EXACT_ISSUER_NAME` — exact normalized legal or display name, returning all
   securities of every matching issuer.
6. `PREFIX_SUGGESTION` — bounded prefix candidates only.
7. `NOT_FOUND` — no exact match or prefix candidate.

An explicitly recognized exchange with a missing symbol terminates as
`NOT_FOUND`; the full query is not reinterpreted as an alias. `%`, `_`, and `\`
are escaped before SQL LIKE prefix lookup. All SQLAlchemy queries are
parameterized.

## Result semantics

`SecurityResolutionResult` contains `status`, raw and normalized queries,
`match_type`, the returned candidate count, candidates, and warnings. Status is
one of `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, or `INVALID_QUERY`.

- one exact candidate is `RESOLVED`;
- multiple exact candidates are `AMBIGUOUS`;
- every non-empty prefix result is `AMBIGUOUS` with
  `PREFIX_SUGGESTION`, even when only one candidate exists;
- malformed, empty, control-character, or overlong input is `INVALID_QUERY` in
  the domain; the HTTP adapter maps it to 422;
- no result is `NOT_FOUND` and contains no candidate.

Each candidate states its IDs, issuer/security names, symbol, exchange, market,
currency, listing status, and deterministic `match_reason`. There is no
confidence score. Shared ticker or name data never selects the more famous
company.

## Status and alias behavior

A `DELISTED` security remains resolvable and carries a warning. `SUSPENDED` and
`UNKNOWN` are also visible and warned rather than hidden. An **inactive alias**
does not resolve or produce a current prefix suggestion; a future or expired
alias is treated the same way for the current date.

Examples:

```powershell
uv run stock-research securities resolve "601138"
uv run stock-research securities resolve "601138.SH"
uv run stock-research securities resolve "工业富联"
uv run stock-research securities resolve "MU"
uv run stock-research securities resolve "NASDAQ:MU"
uv run stock-research securities resolve "Micron Technology" --json
```

`MU.US`, `US:MU`, misspellings, ambiguous shared names, or unknown exchange
forms are not guessed. They produce the deterministic result supported by the
current database, normally `NOT_FOUND`, `AMBIGUOUS`, or `INVALID_QUERY`.

证券身份解析**不使用大模型**，不访问互联网，也不实现行情、财务、RAG、Agent 或 MCP。
