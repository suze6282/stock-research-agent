# Stage 6 RAG and verifiable citation design

- Status: `PROPOSED — USER APPROVAL REQUIRED`
- Design date: 2026-07-20
- Baseline: `main` at `01db051`
- Implementation branch: not created; it may be created only after approval and baseline checks
- Implementation status: not started

## 1. Approval gate and scope

This document is the Stage 6 design artifact. It does not authorize a migration,
production implementation, dependency installation, document download, embedding call,
model call, or index build. The next step is user review. Implementation starts only after
the explicit response `批准设计并继续实现`.

Stage 6 builds an offline-first, point-in-time document knowledge base for already
persisted and approved PDF, HTML, text, and selected JSON evidence. It returns passages,
locations, provenance, and deterministic citation status. It does not generate an
investment conclusion, report, target price, recommendation, or canonical financial fact.

## 2. Existing-system audit

### 2.1 Repository and runtime

- The repository is `<project-root>`.
- The design audit started on clean `main`; the latest commit was `01db051 feat: add
  financial normalization and deterministic metrics`.
- Python is pinned to 3.12 and the project uses `uv`, FastAPI, SQLAlchemy 2, Alembic,
  PostgreSQL, Pydantic, Typer, Ruff, mypy strict mode, and pytest.
- No PDF parser, HTML DOM library, embedding client, vector database client, `pgvector`,
  or Chinese tokenizer is currently a project dependency.
- The loopback PostgreSQL service was not reachable during the optional design-only
  compatibility probe on 2026-07-20. The service was not started because the prompt puts
  database/runtime checks after design approval. Formal implementation preflight must
  prove development and test database connectivity and migration head `0004`.
- `AGENTS.md` still describes the superseded Stage 4 boundary. The current user prompt
  explicitly authorizes Stage 6 and therefore takes precedence. After approval, the Stage 6
  branch must update that file before implementation so repository-local instructions no
  longer contradict the active phase.

### 2.2 Existing evidence boundaries

| Component | Existing behavior | Stage 6 consequence |
|---|---|---|
| `RawPayload` | Immutable provider bytes or inline JSON, SHA-256, source/retrieval times, parser/schema/provider versions | Preserve unchanged; a document version points to exact raw lineage rather than replacing it |
| `BlobStorage` | Injected protocol; local implementation uses opaque `blob://local/...`, verifies size/checksum, and rejects traversal, absolute caller paths, symlink/reparse/hardlink attacks and overwrite | Reuse as the only parser byte source; never expose the configured filesystem root |
| `SourceDocument` | Provider document metadata with optional body URI/checksum/size; it has `updated_at` and is not a durable content-version abstraction | Treat as the provider document record, not as immutable content; add logical identity and exact content versions |
| `DataSnapshot` / `SnapshotItem` | Immutable terminal point-in-time selection with PostgreSQL triggers and deterministic checksum | Retrieval must require exact snapshot membership or an aware as-of cutoff and must never mutate a terminal snapshot |
| Tool Registry | Canonical allowlist; every registered Tool is `READ_ONLY`, `writes=false`, `requires_network=false` | Add RAG tools only through the same strict metadata/handler registry; parsing/indexing remain absent from it |
| API | GET-only bounded data/financial routes, strict query allowlists, request IDs and safe errors | Add read routes only; no parse/index/embedding/download endpoint |
| CLI | Explicit ingestion, snapshot, normalization and calculation writes; reads share domain services | Add explicit document/version/parse/index/retrieval-run commands; no implicit download or network |

### 2.3 Evidence gap found by the audit

The repository does not currently contain an approved company-document body for either
sample security:

- `601138.SH`: Stage 1 recorded that an official annual-report PDF was transiently
  downloaded and parsed, but the original PDF bytes or an approved crop were not retained.
  The authored validation note is not a substitute for the filing body.
- `MU`: the approved SEC fixture contains submissions metadata only. It explicitly states
  that no Archive primary document body, filename, MIME, size, or checksum was retained.

Therefore synthetic parser fixtures can validate safety and contracts, but the two required
company retrieval acceptance slices remain `BLOCKED` until authentic source bytes or a
documented safe crop and manifest are supplied and checksum-verified. The implementation
must not turn the Stage 1 notes into company evidence or invent passages for the requested
queries.

## 3. Candidate implementation routes

### Route A — PostgreSQL native full-text search plus a vector port

Store chunks and a `tsvector`, use a GIN index and PostgreSQL ranking, and keep vector
search behind an interface.

Advantages:

- Few application tables and good English operational maturity.
- Rebuild and transaction behavior fit the existing PostgreSQL deployment.
- No external search service is required.

Limitations:

- PostgreSQL ships useful English/simple configurations but no project-validated Chinese
  segmentation strategy. Enabling an unverified extension would violate the prompt.
- PostgreSQL ranking/token semantics are less transparent for mixed Chinese, stock codes,
  percentages and units.
- A tokenizer or pre-tokenization layer is still required, which weakens the simplicity
  advantage.

### Route B — Versioned application tokenizer and PostgreSQL postings, plus a vector port

Tokenize in deterministic Python, persist bounded postings and index statistics in
PostgreSQL, calculate a documented lexical score, and isolate all vector behavior behind
`EmbeddingProvider` and `VectorIndex` protocols.

Advantages:

- Same reproducible behavior on Windows and PostgreSQL without extensions.
- Explicit bilingual rules can preserve `601138.SH`, `NASDAQ:MU`, percentages, units and
  accounting negations.
- Tokenizer, stopword, chunk and scoring versions are first-class data.
- Static test vectors can exercise the vector contract without becoming a production
  embedding claim.
- Missing production embeddings degrade honestly without blocking lexical retrieval.

Limitations:

- More rows and more application code than native FTS.
- Initial scale is appropriate for two securities and bounded documents, not an unbounded
  market-wide corpus.
- A future production corpus may justify migration to GIN/pgvector or an external engine.

### Route C — Production multilingual embeddings with pgvector or an external search service

Use a multilingual embedding service/model and pgvector, OpenSearch, or a dedicated vector
database for full hybrid retrieval.

Advantages:

- Strongest future semantic-retrieval ceiling and mature approximate-nearest-neighbor
  options at larger scale.
- Can consolidate lexical/vector operations in a dedicated search backend.

Limitations:

- Currently blocked by model approval, credentials, authorization, egress and semantic
  quality validation.
- `pgvector` is not installed or required by the existing environment; external engines add
  a second operational datastore. Windows setup and CI become materially harder.
- Default tests could no longer remain fully self-contained without a substitute backend.
- It would create a false Stage 6 success if static or hash vectors were presented as real
  semantic quality.

### 3.1 Comparison

| Criterion | Route A: native FTS | Route B: application postings | Route C: production vector stack |
|---|---|---|---|
| Reproducibility | High for English; medium for mixed Chinese | High; every rule/version is explicit | Medium until provider/backend/model are pinned |
| Windows compatibility | High for built-in PostgreSQL | High; Python + existing PostgreSQL | Medium/low; extension/service setup required |
| PostgreSQL compatibility | Native | Plain tables, constraints and B-tree indexes | Extension or second datastore |
| English retrieval | Good | Good exact lexical behavior | Potentially good after real evaluation |
| Chinese retrieval | Weak without extra tokenizer/extension | Explicit CJK token strategy | Potentially good, but blocked and unvalidated |
| External model dependency | None for lexical | None for lexical | Required |
| Extra database extension | None | None | Usually pgvector or external backend |
| Test difficulty | Medium | Medium, but deterministic | High; provider/backend isolation required |
| Later extension cost | Medium | Medium; ports provide migration seam | Low after expensive initial adoption |
| Credential/blocker risk | Low | Low for lexical; vector stays blocked | High now |

## 4. Recommended route and decision

Use **Route B** for Stage 6:

1. PostgreSQL owns logical document identity, exact versions, parse artifacts, chunks,
   citations, lexical index versions/postings, embedding metadata, vector index metadata,
   retrieval runs and hits.
2. The application owns a versioned, deterministic English/CJK tokenizer and scoring
   implementation.
3. `EmbeddingProvider` and `VectorIndex` are ports. No production provider is configured.
4. Static vectors exist only in isolated tests and are marked `TEST_ONLY`,
   `NOT_PRODUCTION`, and `NOT_SEMANTICALLY_VALIDATED`.
5. Lexical retrieval may be `PASS`; vector is `BLOCKED` without a production provider;
   hybrid falls back to lexical with `PARTIAL` and a specific warning.
6. The design creates a clean migration seam to native FTS, pgvector, or an external vector
   backend without changing document, citation, as-of, Tool or API contracts.

## 5. Layered architecture

```text
approved RawPayload / opaque BlobStorage bytes
        |
        v
logical document -> immutable DocumentVersion -> SnapshotDocumentVersion
        |
        v
explicit CLI/internal parse service -> DocumentParseRun
        |                              | Pages / Sections
        v                              v
deterministic chunker ------------> immutable DocumentChunks
        |
        +--> explicit lexical build -> LexicalIndexVersion / LexicalPostings
        |
        +--> optional embedding port -> EmbeddingRecord / VectorIndexVersion
                                             (production BLOCKED in V0.1)

explicit CLI/internal retrieval execution -> immutable RetrievalRun / RetrievalHits
                                                     |
read-only Tool/API cache lookup ---------------------+
                                                     v
                                      verified Citations / EvidenceBundle
```

Domain modules must not depend on FastAPI, Typer, SQLAlchemy sessions, concrete blob paths,
or provider HTTP clients. Repositories do not parse. Parsers do not create sessions. The
retrieval service receives repositories/index ports and cannot download or refresh data.

## 6. Document identity and versioning

### 6.1 Existing `source_documents`

Keep the Stage 4 table unchanged. It is a provider metadata record and raw-lineage anchor.
Its ID is never redefined as a content version.

### 6.2 `logical_documents`

One row represents the stable document identity within a security:

- `id`, `security_id`, `document_type`, `form_type`
- `identity_scheme`, `identity_value`, `normalized_identity_value`
- `title`, `created_at`

Examples of identity schemes are `SEC_ACCESSION`, `EXCHANGE_ANNOUNCEMENT_ID`, and
`PROVIDER_DOCUMENT_ID`. Identity is constructed only from confirmed provider fields. A
missing stable external identity blocks automatic logical-document unification; it must not
be guessed from title similarity.

Unique key: `(security_id, identity_scheme, normalized_identity_value)`. All foreign keys use
`RESTRICT` deletion.

### 6.3 `document_versions`

An immutable row represents exact bytes:

- identity: `id`, `logical_document_id`, `source_document_id`, `security_id`,
  `provider_id`, `source_payload_id`, `version_number`,
  `supersedes_document_version_id`
- content: opaque `storage_uri`, allowlisted `mime_type`, `checksum_algorithm=sha256`,
  `checksum`, `byte_size`
- time: `published_at`, `filed_at`, `period_end`, `retrieved_at`, `created_at`
- policy: `document_language`, `trust_level`, `evidence_origin`, `access_mode`,
  `live_status`, `source_version_status`

Constraints:

- unique `(logical_document_id, version_number)` and unique
  `(logical_document_id, checksum)`;
- `version_number > 0`, SHA-256 format, positive bounded size, aware UTC times;
- `published_at` is never inferred from `retrieved_at`;
- storage URI must match the existing opaque `blob://...` grammar;
- the referenced `SourceDocument` must be `AVAILABLE` and have non-null storage URI,
  checksum and byte size that agree with BlobStorage and the source payload;
- trust level is one of `OFFICIAL_REGULATORY`, `OFFICIAL_COMPANY`,
  `APPROVED_PROVIDER`, `TEST_FIXTURE`, `UNKNOWN`;
- language is `zh-CN`, `en-US`, `MIXED`, or `UNKNOWN`;
- source version status is immutable `ACTIVE`, `WITHDRAWN`, or `UNKNOWN`;
- an optional supersedes pointer must target an older version of the same logical document;
  whether an older version is superseded at a cutoff is derived from this new-row relation,
  never by editing the old row;
- terminal versions are update/delete protected by PostgreSQL triggers.

The service reads BlobStorage metadata and exact bytes, validates MIME/magic/checksum/size,
and either reuses the same content version or inserts the next version. Different bytes never
overwrite an old row. A checksum collision with incompatible metadata fails safely.

### 6.4 `snapshot_document_versions`

This association preserves the distinction between content version and research snapshot:

- `snapshot_id`, `document_version_id`, `snapshot_item_id`, `created_at`
- unique `(snapshot_id, document_version_id)` and unique `snapshot_item_id`

The referenced `SnapshotItem` must point to the version's `source_document_id` with
`category=SOURCE_DOCUMENTS` and `source_record_type=source_documents`. Existing
`FILING_METADATA` items remain metadata-only and cannot satisfy this body-evidence relation. A
document body discovered later requires a new raw record and snapshot selection; it is never
attached to an old terminal snapshot as if it had been present earlier.

## 7. Parse model and parser contracts

### 7.1 `document_parse_runs`

Fields follow the prompt and add `sanitizer_version` and `config_checksum`. Unique identity:
`(document_version_id, parser_name, parser_version, sanitizer_version, config_checksum)`.
`RUNNING` can transition once to `PASS`, `PARTIAL`, `BLOCKED`, or `FAIL`; terminal rows and
their children are immutable. A parser-version/config change creates a new run.

### 7.2 `DocumentParser` port

```text
parse(version, blob_reader, parser_config) -> ParsedDocument
```

The result contains canonical text, pages, sections, table-text blocks, warnings, safety
markers and parse metadata. `ParserRegistry` selects only an allowlisted parser from verified
MIME plus magic bytes. Callers cannot supply a class, executable, URL, local path or parser
option map.

Parsers never access the network, follow links, execute scripts/macros/attachments, inspect
environment variables, call a model, invoke OCR, or create a database session.

### 7.3 Proposed parser dependencies

- PDF: add a narrowly constrained `pypdf` dependency after approval and lock its resolved
  version in `uv.lock`. Use text-layer extraction only. Do not access attachments, actions,
  JavaScript or remote resources.
- HTML: use a bounded subclass of Python's `html.parser.HTMLParser` for V0.1. It is pure
  Python and does not execute JavaScript or load resources. It preserves approved headings,
  anchors, paragraphs and table text while discarding active elements/attributes.
- Text/JSON: use Python standard-library decoders and `json`; no dynamic object hooks or
  schema selected by document content.

No dependency is added before design approval. OCR, XML entity processing, local models,
OpenAI and external parsers remain out of scope.

### 7.4 Initial hard limits

Limits are configuration values included in `config_checksum`; changing them creates a new
parse generation:

| Limit | V0.1 value |
|---|---:|
| document bytes | 10,000,000 |
| PDF pages | 500 |
| PDF characters per page | 100,000 |
| canonical document characters | 5,000,000 |
| HTML nodes | 50,000 |
| HTML nesting depth | 64 |
| JSON nesting depth | 32 |
| JSON array items per array | 10,000 |
| excerpt characters | 1,000 |

An approved safe crop is required when a real document exceeds the V0.1 limit. The crop
manifest must describe the omitted range; the crop must not be presented as a complete filing.

### 7.5 Format behavior

- PDF: `%PDF-` magic, encryption detection, 1-based physical page order, explicit blank/no
  text page status, partial-page warnings, no OCR. Printed page labels are optional metadata
  and never replace physical page numbers.
- HTML: remove `script`, `style`, `iframe`, `object`, `embed`, `form`, active URLs and all
  `on*` attributes; ignore CSS/remote resources; keep explicit `id`/`name` anchors after safe
  normalization; preserve table rows/cells as delimited text; cap nodes/depth/chars.
- Text: UTF-8 first, UTF-8 BOM accepted, invalid decoding is `BLOCKED` unless an explicitly
  allowlisted encoding is part of the parser configuration; normalize CRLF/CR to LF and retain
  canonical offsets.
- JSON: only approved field paths become searchable text; paths are recorded as RFC 6901 JSON
  Pointers. Unknown values remain metadata and are not promoted to text. Strings are data only.

## 8. Pages, sections, chunks and offsets

### 8.1 Persistence

- `document_pages`: unique `(parse_run_id, page_number)`, text/checksum/count/status.
- `document_sections`: unique `(parse_run_id, section_path)`, parent FK with `RESTRICT`,
  level/title/ranges/checksum/content type.
- `document_chunks`: unique `(parse_run_id, chunk_version, chunk_index)` and immutable text,
  normalized text, language, content kind, source ranges and checksum.

A deferred database trigger rejects section parent cycles. Range CHECK constraints reject
negative, reversed, or inconsistent page/offset intervals.

### 8.2 Canonical location model

- PDF offsets are page-relative and always paired with 1-based start/end page numbers.
- HTML, text and JSON maintain a canonical sanitized text stream; offsets are half-open
  `[start_offset, end_offset)` positions in that stream.
- Section and chunk records retain the location type and enough source ranges to re-read the
  exact canonical source. Chunking never renumbers pages or rewrites page/section text.

### 8.3 `chunk-v1`

- Preserve section boundaries first, paragraph boundaries second, then sentence/character
  windows.
- Target 1,000 canonical characters, hard maximum 1,600, minimum 120.
- Overlap is at most 200 characters and never more than 20% of the target length.
- Never split inside a contiguous stock code, percentage, decimal+unit, date or ASCII word
  unless the hard limit would otherwise be exceeded; such a forced split emits a warning.
- Table blocks stay independent when reliable; unreliable tables remain page text and make the
  parse `PARTIAL`.
- `token_count` means `tokenizer-v1 lexical token estimate`, not a model token count.
- Chunk checksum hashes document checksum, parse/config versions, chunk version, index,
  location tuple and exact chunk text using canonical JSON and SHA-256.

Rebuilding identical inputs yields identical ordered descriptors and checksums. IDs may be
random database identities; equality and idempotency are established by the versioned natural
key and checksums, not UUID coincidence.

## 9. Citation anchors and verification

### 9.1 `citation_anchors`

Every citation binds an immutable document version and parse run. It may reference a page,
section and chunk, but all referenced records use `RESTRICT` deletion. Locator types are:
`PDF_PAGE_RANGE`, `HTML_ANCHOR_RANGE`, `TEXT_OFFSET_RANGE`, `JSON_POINTER`, and
`SECTION_RANGE`.

The row stores physical page range, HTML anchor, JSON pointer, half-open offsets, bounded
excerpt, excerpt checksum, canonical source-text checksum, document checksum,
`citation_version`, and creation time. Unique identity is a canonical locator checksum within
the document version/parse run.

### 9.2 Deterministic `CitationVerifier`

Verification proceeds without a model:

1. load the exact document version and verify its immutable SHA-256;
2. verify BlobStorage still contains bytes whose checksum/size/MIME match the version;
3. load the exact parse run and require the citation's parser/sanitizer versions;
4. resolve the page/section/chunk and validate page and offset bounds;
5. re-slice canonical source text and compare excerpt and both text checksums;
6. require version membership in the requested snapshot when snapshot scope is used;
7. require known `published_at <= research_as_of_time` in strict historical mode;
8. reject a citation to an ineligible/superseded version unless that historical version is
   explicitly selected.

The result is one of `VALID`, `INVALID`, `STALE_REFERENCE`, `FUTURE_DATA`,
`SOURCE_MISSING`, or `PARSE_VERSION_MISMATCH`. Unknown publication time is `INVALID` with
`SOURCE_PUBLISHED_AT_UNKNOWN` under strict mode; it is never mislabeled as future. Only
`VALID` citations enter an Evidence Bundle. There is no confidence score.

## 10. Lexical tokenizer and index

### 10.1 `tokenizer-v1`

1. Reject NUL and unsafe control characters; normalize safe text with Unicode NFKC.
2. Case-fold Latin text without translating it.
3. Preserve validated mixed tokens such as `601138.SH`, `NASDAQ:MU`, `10-K`, `12.5%`,
   `RMB`, `USD`, and unit-bearing decimals.
4. Tokenize ordinary English/alphanumeric words exactly; no stemming in V0.1.
5. For each contiguous CJK run, emit overlapping bigrams, the single character only when the
   run length is one, and one bounded whole-run token up to 32 characters.
6. Use a versioned minimal English stopword list. Negations including `not`, `no`, `without`,
   `未`, `不`, `无` are never stopwords.
7. Limit normalized query length to 256 characters and tokens to 64.

### 10.2 Tables

- `lexical_index_versions`: name, security, tokenizer/chunk/scoring versions, exactly one of
  `snapshot_id` or aware `index_as_of_time`, document-set checksum, document count, chunk count,
  average length, status, checksum and terminal timestamps. A snapshot index includes only
  `snapshot_document_versions`; an as-of index includes only versions with known publication
  time not later than its cutoff.
- `lexical_postings`: index version, token, chunk, term frequency, field kind and positions
  needed for exact phrase checks. Unique `(index_version_id, token, chunk_id, field_kind)`.

Indexes support exact token lookup and chunk/version joins; no user query becomes SQL, LIKE,
regex, `tsquery`, sort expression or column name.

### 10.3 Stable scoring

`lexical-rank-v1` uses BM25 with Python `Decimal`, fixed `k1=1.2`, `b=0.75`, documented
document frequency and length statistics, and a 12-decimal quantization. An exact normalized
phrase and section-title token match are separate deterministic rerank features, not hidden
score adjustments. Default results are 10; hard maximum is 20. Tie-breakers are the stable
locator checksum and chunk index.

Snapshot retrieval requires the exact snapshot-scoped index. As-of retrieval selects an exact
as-of index generation whose cutoff equals the requested cutoff; it does not silently use a
later corpus and rely only on post-filtering. If no compatible generation exists, explicit CLI
index build is required and read-only callers return `BLOCKED`.

## 11. Embedding and vector ports

### 11.1 `EmbeddingProvider`

The strict port exposes fixed provider/model/version/dimensions/max length, document/query
embedding methods and health status. Provider/model/base URL are application configuration,
not request parameters. Keys are never stored or logged; no embedding occurs at import time.

### 11.2 `VectorIndex`

The port supports version creation by an explicit internal service, bounded filtered search,
health and immutable version metadata. It receives already eligible chunk IDs; it cannot
expand security, snapshot, document type or time filters.

### 11.3 Persistence and V0.1 status

- `embedding_records` store chunk checksum, provider/model/version/dimensions, embedding
  checksum, opaque vector reference and status. They do not claim semantic validity.
- `vector_index_versions` store backend/model/chunk versions, dimensions, status and terminal
  timestamps.
- No vector column or pgvector extension is required in Stage 6.
- `StaticFixtureEmbeddingProvider` and an in-memory static vector index are available only in
  tests with the three required markers. Their vectors are fixed independent test inputs,
  never hash embeddings and never production defaults.
- Without an approved production provider, vector build/search returns `BLOCKED` with
  `EMBEDDING_PROVIDER_NOT_CONFIGURED`.

## 12. Retrieval, fusion and reranking

Modes are `LEXICAL`, `VECTOR`, and `HYBRID`.

- Lexical: `PASS` when a compatible terminal lexical index exists; a valid zero-hit search is
  still `PASS` with zero items.
- Vector: `BLOCKED` without a production provider/index. Test execution is labeled
  `TEST_ONLY/NOT_PRODUCTION/NOT_SEMANTICALLY_VALIDATED`.
- Hybrid: use both channels when available. With lexical only, return lexical evidence as
  `PARTIAL`, set all vector ranks/scores to null, and warn `VECTOR_CHANNEL_BLOCKED`.

`fusion-v1` is Reciprocal Rank Fusion with `k=60`. Only actual channel ranks contribute.
Duplicate chunk IDs are collapsed. `reranker-v1` applies the stable tuple:

1. exact phrase present;
2. count of query-token matches in section title;
3. RRF score;
4. best available channel rank;
5. document-version locator checksum;
6. chunk index.

It does not use a model, company popularity, randomness or post-cutoff recency. Every hit stores
nullable lexical/vector ranks and scores, fusion score, final rank and enumerated rerank reasons.

## 13. Filters and point-in-time rules

Mandatory filters run before lexical or vector candidate selection:

- exact security, and issuer only through the persisted Security relationship;
- exact snapshot membership or aware `research_as_of_time`;
- document/form/language/trust/period/version/section allowlists;
- requested published range intersected with
  `document_version.published_at <= research_as_of_time`;
- parser/chunk/index versions compatible with the selected document version.

Unknown `published_at` is excluded by default. `allow_unknown_published_at=true` must be an
explicit typed input, changes status to `PARTIAL`, emits a warning, and still cannot override a
snapshot-membership mismatch. A later correction/version never enters an earlier cutoff.

## 14. Retrieval runs, read-only boundary and Evidence Bundles

### 14.1 `retrieval_runs` and `retrieval_hits`

An explicit retrieval execution stores the bounded original/normalized query, exact scope,
filters, tokenizer/index/model/fusion/reranker versions, a canonical
`request_fingerprint`, status, warnings and counts. The fingerprint is unique for the full
query/scope/filter/index/version tuple and enables cache-only lookup. Terminal runs and hits are
protected by triggers. Hits are unique by run/chunk and run/final rank, and every final hit has
a `VALID` citation.

### 14.2 Resolution of the read-only-versus-persistence conflict

The prompt simultaneously requires every retrieval run to be recorded and every Tool/API to
be strictly read-only with `writes=false`. A search endpoint cannot insert audit rows while
honestly claiming zero writes. V0.1 therefore uses a strict cache-only boundary:

- `stock-research rag search ...` is an **explicit CLI/internal write operation**. It executes
  retrieval and atomically creates the immutable run/hits.
- Tool `search_document_chunks` and GET `/rag/search` compute the exact request fingerprint and
  read a compatible terminal run. They never insert, update, parse, index or embed.
- A cache miss returns HTTP 200 with business status `BLOCKED` and warning
  `RETRIEVAL_RUN_NOT_PRECOMPUTED`. It never performs a hidden write.
- `get_retrieval_run` and `get_evidence_bundle` read the persisted result.

This is deliberately conservative. A future stage may authorize an append-only retrieval
execution capability, but it must not be mislabeled `writes=false`.

### 14.3 Evidence Bundle

Evidence Bundles are read models derived from an immutable run, hits, documents and citations;
no separate table is needed in V0.1. Each item contains bounded excerpt and exact document,
version, trust, publication, section/page, chunk, citation and retrieval-reason metadata. It
contains no full document and no generated conclusion.

## 15. Tool, API and CLI contracts

### 15.1 Tools

Register the eight prompt-specified names at version `1.0.0`. Every registration is canonical,
`READ_ONLY`, `read_only=true`, `writes=false`, `requires_network=false`, and uses a persisted
snapshot/as-of/run boundary. Tool handlers receive only query services. They cannot obtain a
parser, BlobStorage writer, embedding provider, provider registry or HTTP client.

`verify_citation` may read BlobStorage bytes/checksum but cannot modify them. Tool output always
includes parser/chunk/tokenizer/index/citation versions, citation status, cutoff, provenance and
bounded warnings. Full documents, RawPayload bodies and local paths are forbidden.

### 15.2 API

Add the eight GET routes under the existing API prefix. Query keys and filters are allowlisted;
security and snapshot/as-of scope are mandatory; max results is capped at 20. The search GET is
the cache-only read described above. Invalid input is 422, missing persisted identity is 404,
and valid `PARTIAL`/`BLOCKED` outcomes are HTTP 200. Existing request ID and safe error handling
remain unchanged.

### 15.3 CLI/internal writes and reads

Explicit writes:

- register/reuse a version only from an approved persisted `SourceDocument`/`RawPayload` and
  BlobStorage URI;
- parse one version;
- build one lexical index for a snapshot;
- attempt vector build, which is `BLOCKED` without approved configuration;
- execute and persist one retrieval run.

Reads include parse status, sections, chunks, document/citation verification, retrieval-run and
evidence display. No command accepts an arbitrary URL or arbitrary local path, performs an
implicit download, starts an interactive loop, or logs an absolute path.

## 16. Security and prompt-injection controls

- External bytes and all extracted text are always `untrusted_document=true`.
- Sanitization removes active capabilities, not inconvenient disclosure. Instruction-like text
  remains quoted evidence and cannot change policy.
- `prompt-injection-rules-v1` performs deterministic NFKC/case-folded pattern marking for
  instruction override, credential request, system-prompt imitation, tool invocation and data
  exfiltration language. A marker is a warning, not a malware verdict and not a deletion rule.
- Parser configuration, security ID, cutoff, filters, providers and Tool permissions are passed
  outside document content and cannot be overridden by it.
- No parser has HTTP, shell, environment, dynamic import, subprocess, arbitrary filesystem or
  database access.
- MIME and magic bytes must agree with an allowlisted parser. Extension and provider metadata
  alone are insufficient.
- Query/body/DOM/page/depth/result limits prevent unbounded work. PostgreSQL statements remain
  parameterized and no raw FTS/SQL expression crosses an interface.
- Logs use IDs, checksums, bounded safe codes and query hashes. They never contain raw bodies,
  excerpts over the output limit, credentials, database URLs or local storage roots.
- Default tests install a socket-denial guard and use only loopback PostgreSQL where required.

## 17. Fixture and sample policy

Every real document fixture must have the manifest fields required by the prompt, exact original
and fixture checksums, explicit crop/redaction statements, usage restrictions and
`FIXTURE/OFFLINE/NOT_LIVE`. Parser/security counterexamples may be synthetic only when marked
`SYNTHETIC_TEST_ONLY/NOT_COMPANY_EVIDENCE`.

Acceptance behavior until real document bodies are approved:

- Industrial FII company queries return no company evidence or `BLOCKED/PARTIAL`; no Stage 1
  summary is indexed as a filing.
- Micron company queries return no company evidence or `BLOCKED/PARTIAL`; SEC submissions
  metadata is not represented as a 10-K/10-Q body.
- The generic PDF/HTML/text/JSON parser, chunk, lexical, hybrid degradation and citation
  contracts can still be proven with clearly synthetic security fixtures.

Production-like sample acceptance becomes possible only after authentic bytes/crops are supplied
with confirmed source publication time, provenance and use restrictions. Reacquisition is a
separate authorized ingestion activity and is not hidden inside Stage 6 parsing.

## 18. Database migration design

Migration `0005_create_rag_and_citations` will create only Stage 6 structures:

1. `logical_documents`
2. `document_versions`
3. `snapshot_document_versions`
4. `document_parse_runs`
5. `document_pages`
6. `document_sections`
7. `document_chunks`
8. `citation_anchors`
9. `lexical_index_versions`
10. `lexical_postings`
11. `embedding_records`
12. `vector_index_versions`
13. `retrieval_runs`
14. `retrieval_hits`

It will add named PK/FK/UNIQUE/CHECK constraints, query-driven indexes and immutability/cycle
triggers. It will not alter or delete Stage 2–5 tables, parse a file, build an index, create an
embedding, call a network, read a secret, insert sample business data or depend on manual state.
Downgrade drops Stage 6 objects in reverse dependency order.

Planned indexes and purposes:

- logical identity and version unique keys: idempotent registration;
- `(security_id, published_at)` on versions: mandatory cutoff filtering;
- checksum indexes: content reconciliation, not global identity;
- parse-run version key and page/section/chunk natural keys: replay and bounded lookup;
- chunk text checksum: citation/rebuild verification;
- `(index_version_id, token)` and `(index_version_id, chunk_id)` postings indexes: lexical
  candidate selection and rebuild audit;
- chunk/model-version embedding key: stale-vector rejection;
- `(security_id, research_as_of_time)` plus unique request-fingerprint retrieval indexes:
  bounded cache lookup;
- `(retrieval_run_id, final_rank)` unique index: stable evidence order.

Large text fields do not receive blind B-tree indexes. PostgreSQL extensions are not enabled.

## 19. Status and degradation matrix

| Condition | Status | Required warning/behavior |
|---|---|---|
| Lexical index available and query executed | `PASS` | Zero hits allowed; no fabricated passage |
| Approved parser salvages only part of a document | `PARTIAL` | Page/section warnings retained |
| Scan-only/encrypted PDF with no approved text path | `BLOCKED` | No OCR |
| Production embedding absent | `BLOCKED` for VECTOR | `EMBEDDING_PROVIDER_NOT_CONFIGURED` |
| HYBRID with lexical only | `PARTIAL` | `VECTOR_CHANNEL_BLOCKED`; vector ranks null |
| Unknown published time explicitly allowed | `PARTIAL` | `SOURCE_PUBLISHED_AT_UNKNOWN` |
| Unknown published time in strict mode | excluded | Never substitute retrieval time |
| Tool/API cache miss for new query | `BLOCKED` | `RETRIEVAL_RUN_NOT_PRECOMPUTED`; no write |
| Citation checksum/location mismatch | citation not valid | Exclude from Evidence Bundle |
| Repository/parser failure | `FAIL` | Fixed safe error without path/SQL/body |

## 20. Testing strategy after approval

The detailed file-by-file plan is created only after approval. It will use strict
RED → observed expected failure → minimal GREEN → refactor cycles for every production behavior.
Test groups will cover:

- identity/version immutability, checksum idempotency and snapshot membership;
- PDF, HTML, text and approved JSON parsing limits and counterexamples;
- stable section/chunk locations, overlap, checksums and rebuilds;
- every citation locator and verifier outcome;
- bilingual tokenizer/golden postings, independent lexical ranking expectations and filters;
- static test-vector dimension/checksum/ranking contracts and production BLOCKED behavior;
- deterministic RRF, duplicate removal, stable reranking and lexical-only degradation;
- retrieval-run/hit immutability and cache-only Tool/API search;
- prompt injection, scripts, paths, MIME mismatch, bombs, arbitrary URLs and logging leaks;
- the eight Tool contracts, eight GET routes, CLI writes/reads and correct exit codes;
- real PostgreSQL constraints/indexes/triggers/concurrency/rollback/migration cycle;
- default offline regression with zero skipped and zero warnings;
- company sample tests only when compliant source fixtures exist; otherwise explicit acceptance
  blockers, never meaningless PASS tests.

Golden expectations are authored independently from the implementation. Synthetic fixture
coverage is reported separately from company-evidence coverage. Live and production embedding
tests remain separate and explicitly enabled.

## 21. Rollout and rollback

After approval:

1. run the complete main-branch baseline and database/snapshot/fixture checks;
2. create `stage-6/rag-citations` only if the worktree is clean;
3. update stale repository guidance and create the detailed implementation plan;
4. implement vertical slices with TDD and focused PostgreSQL tests;
5. validate migration `0004 -> 0005 -> 0004 -> 0005` on development and isolated databases;
6. perform both Reflection rounds and full quality gates;
7. stop on the feature branch and present the user-selected finish options.

Rollback is Alembic downgrade of Stage 6 tables plus application rollback to the pre-Stage 6
commit. RawPayload, BlobStorage bytes, SourceDocument, snapshots and Stage 5 financial records
remain untouched. No branch merge or deletion is automatic.

## 22. Approval decisions

Approval of this design accepts the following concrete choices:

1. Route B application-level versioned postings is the Stage 6 lexical implementation.
2. No pgvector, external vector database, external embedding call or downloaded model is required.
3. `pypdf` may be added only after approval; HTML/text/JSON begin with bounded standard-library
   parsers.
4. Tool/API search is cache-only; explicit CLI/internal retrieval creates immutable runs.
5. Current Industrial FII and Micron body-evidence acceptance remains blocked until compliant
   document bytes/crops and manifests are available.
6. The repository's stale Stage 4 `AGENTS.md` is corrected on the Stage 6 branch after approval.

## 23. Design self-review

- [x] Document logical identity, provider record, exact version, raw payload and snapshot binding
  are distinct.
- [x] PDF, HTML, text and approved JSON parsers have explicit no-network/no-code/OCR boundaries.
- [x] Page, section, chunk, offset and version semantics are deterministic.
- [x] Citation construction and verification are checksum- and location-based, not model-based.
- [x] Chinese/English tokenization and lexical scoring are versioned and reproducible.
- [x] PostgreSQL native FTS, a versioned tokenizer/postings design, and production vector stacks
  were compared across every required criterion.
- [x] Embedding and vector interfaces are pluggable; production vector is honestly blocked.
- [x] Hybrid RRF and reranking are deterministic and expose null unavailable-channel ranks.
- [x] Security, as-of, unknown-publication, future-data and prompt-injection rules are explicit.
- [x] Tool/API remain read-only; parsing/indexing/retrieval persistence are explicit CLI/internal
  operations.
- [x] Fixture/Live/TEST_ONLY boundaries and the two missing company bodies are recorded.
- [x] PostgreSQL migration, indexes, rollback, concurrency and test strategy are covered.
- [x] No production code, migration, dependency, model, embedding, Agent, MCP, report, target
  price, trade, frontend or Stage 7 work was created during design.

## 24. Explicit non-goals

No Agent loop, model-controlled Tool use, model summary, model reranker, Reflection runtime, MCP
Server, target price, recommendation, portfolio action, broker/trade, frontend, arbitrary web
acquisition, OCR, canonical financial promotion from RAG tables, or Stage 7 behavior is part of
this design.
