# Controlled Manual Evidence Import Policy

Status: Stage 10 design policy; no real file has been imported.

This policy governs evidence a user has already obtained legally and deliberately
places in a configured local inbox. It does not authorize web scraping, automatic
source verification, Provider Live access, OCR, code execution or public upload.

## 1. Purpose and non-bypass rule

Manual import exists because A-share disclosure-body automation remains blocked.
It is not an escape hatch around Provider, license, identity, temporal, synthetic
or Citation gates. The local intake mechanism is always labeled
`CONTROLLED_MANUAL_EVIDENCE`, `USER_SUPPLIED`, `OFFLINE` and `NOT_LIVE`.

All accepted bytes follow:

`Source Declaration -> Import Request -> Quarantine -> Raw Artifact -> Validation
-> Review -> Ingestion Manifest -> DocumentVersion or approved Raw Financial Fact
-> Data Quality -> explicit new Snapshot`.

It never writes directly to Claim, Research Package, Report, Derived Metric or
Agent output.

## 2. Source classification

| Source type | Minimum proof | Company evidence eligibility |
|---|---|---|
| `USER_SUPPLIED_OFFICIAL_DOCUMENT` | identifiable issuer/security, official document identity, source institution, source URL or complete acquisition explanation, publication/period evidence, rights declaration | Eligible only after all validations and human approval |
| `USER_SUPPLIED_PROVIDER_EXPORT` | named Provider/export type, entitlement/use declaration, schema identity and Security mapping | Eligible only for the specifically approved use; never described as Live |
| `USER_SUPPLIED_STRUCTURED_DATA` | stable schema, source, period/as-of, units and rights declaration | Eligible only for approved typed facts after mapping and quality gates |
| `USER_SUPPLIED_UNVERIFIED_DOCUMENT` | file and basic declaration | Never supports a real-company Claim or VALID Citation; quarantine/limitation only |

Screenshots, chat text, pasted summaries, secondary reposts and files whose source
cannot be verified cannot be upgraded by plausibility or company-name matching.

## 3. Required immutable declaration

One `manual_evidence_source_declaration` freezes:

- request, Security and issuer IDs;
- source type, source institution and exact source description;
- declared URL as provenance text only, never a fetch instruction;
- acquisition method and submitting actor;
- document/export/schema type, language and original safe filename;
- report period, publication and retrieval times;
- license status and policy/source references;
- acquisition, raw storage, excerpt, derived use, commercial use,
  redistribution and long-term retention decisions;
- synthetic status and explicit `allowed_for_company_research` decision;
- declaration version and canonical checksum.

The declaration cannot store a credential, token, cookie, local absolute path or
raw body. Empty/unknown critical rights block promotion.

## 4. Intake root and path policy

The CLI receives a path relative to a configured `MANUAL_EVIDENCE_INBOX_ROOT`.
The resolver must:

1. reject absolute, drive-relative and UNC paths;
2. reject `..`, empty segments, alternate data streams and NUL/control characters;
3. reject Windows device names such as `CON`, `PRN`, `AUX`, `NUL`, `COM1` and
   `LPT1`, including names followed by extensions;
4. normalize Unicode NFKC for validation without overwriting the submitted name;
5. reject hidden extension tricks, trailing dot/space and double extensions;
6. resolve symlinks/reparse points and verify the final regular file remains
   under the inbox root;
7. refuse directories, named pipes, devices, sockets and hard-link ambiguity;
8. open without following a post-check replacement and revalidate file identity;
9. persist only a sanitized filename and opaque quarantine/blob reference; and
10. never return or log the source absolute path.

Stable blocking checks include `PATH_TRAVERSAL`, `ABSOLUTE_PATH`, `UNC_PATH`,
`WINDOWS_DEVICE_NAME`, `ALTERNATE_DATA_STREAM`, `DOUBLE_EXTENSION`,
`SYMLINK_ESCAPE` and `UNICODE_EXTENSION_CONFUSION`.

The inbox and quarantine roots are distinct. Import copies bytes atomically to a
UUID-based quarantine key before parsing.

## 5. Initial format allowlist

| Extension | Declared/detected MIME | Required magic/encoding | Parser mode |
|---|---|---|---|
| `.pdf` | `application/pdf` | `%PDF-` and structurally readable | existing text-layer parser after safety scan; no OCR |
| `.html` / `.htm` | `text/html` | inert HTML prefix and valid bounded decoding | standard-library safe text extraction; no resource load |
| `.json` | `application/json` | UTF-8 object/array | bounded deterministic JSON parser |

All archive/container formats, XML, SVG, images, Office files, executable/binary
formats and unknown MIME are rejected in the initial implementation. Adding a
format requires a later versioned policy and tests; extension matching cannot
implicitly enable it.

## 6. Resource bounds

- one file per import request;
- maximum 25 MiB raw bytes;
- maximum sanitized filename length 160 Unicode scalar values;
- parser wall time 30 seconds and bounded memory configured by the worker;
- HTML/decoded text maximum 10 million characters;
- JSON depth 32, total nodes 100,000 and string value 1 million characters;
- PDF page count 2,000, object count 200,000 and decompressed text 10 million
  characters;
- no nested data, archive expansion, OCR or child process.

Exceeding a bound produces a stable BLOCKED validation code and no partial
evidence admission.

## 7. Common validation sequence

Validators run in this order and append immutable results:

1. file/root/identity validation;
2. size and exact-byte SHA-256;
3. extension, MIME and magic agreement;
4. format-specific active-content and structural safety;
5. deterministic parse readiness without external access;
6. source declaration completeness and license rights;
7. Security/issuer/document/period/publication matching;
8. future-data and synthetic-state checks;
9. retention/excerpt/company-research eligibility; and
10. human review bound to all prior checksums.

An earlier BLOCKED or REJECTED result stops later parsing/promotion. Safe warning
codes may yield `PARTIAL` but cannot silently elevate evidence.

## 8. PDF safety policy

PDF validation rejects:

- encryption or password protection;
- `/JavaScript`, `/JS`, `/Launch`, `/OpenAction` and additional actions;
- embedded files, file specifications that launch/open, multimedia and rich media;
- external/local URI actions that a parser could follow;
- malformed cross-reference/object structures or suspicious object counts;
- inconsistent MIME/magic, trailing executable/container payloads and corruption;
- pages that require OCR for meaningful text.

The corresponding active-content checks include `PDF_JAVASCRIPT`,
`PDF_LAUNCH_ACTION`, `PDF_OPEN_ACTION`, `PDF_EMBEDDED_FILE` and
`PDF_EXTERNAL_REFERENCE`.

`pypdf` is used only for a present text layer. A successful text extraction does
not assert perfect reading order. Scanned, complex-layout, corrupted or partially
failed PDFs produce `PARTIAL` or `BLOCKED`. Unreliable tables remain safe text with
`TABLE_STRUCTURE_UNVERIFIED`; they never create pseudo-precise rows or Stage 5
financial facts.

## 9. HTML safety policy

HTML is treated as hostile inert content. Validation blocks or strips before any
evidence use:

- script, style with external imports, object, embed, iframe, frame, form and
  executable/template content;
- event-handler attributes, `javascript:`, `data:`, `file:`, UNC/local paths and
  external-resource references;
- meta refresh, base URL changes and active SVG content;
- oversized/deep malformed markup that exceeds bounds.

Stable checks include `HTML_SCRIPT`, `HTML_EVENT_HANDLER`,
`HTML_EXTERNAL_RESOURCE`, `HTML_LOCAL_FILE_REFERENCE` and `HTML_ACTIVE_SVG`.

The parser never executes script, follows links, resolves DNS, loads images/fonts,
or reads local files. Complex/malformed structure yields `PARTIAL` or `BLOCKED`.

## 10. JSON safety policy

JSON must be valid UTF-8, contain one object or array, use no duplicate object keys,
remain within depth/node/string bounds and reject NaN/Infinity. It may not contain
an instruction to fetch a URL, open a file, execute SQL, select a Provider, resolve
a credential or invoke a model. Such strings may be preserved as inert source text
but cannot alter system behavior. A schema must be explicitly selected by the
reviewed source type; arbitrary keys never become financial facts.

Stable checks include `JSON_DEPTH_EXCEEDED`, `JSON_NODE_LIMIT_EXCEEDED`,
`JSON_DUPLICATE_KEY` and `JSON_NONFINITE_NUMBER`.

## 11. Identity and time validation

The import must match the exact resolved Security and issuer, not only a company
name. Validators compare available official identifiers, ticker/exchange,
document title/issuer, report period and publication date. Conflicting or absent
identity evidence blocks company-evidence status.

`declared_published_at` is never replaced with import/retrieval time. Unknown
publication time blocks strict historical Claims and a publishable report. Any
publication or fact date later than `research_as_of_time` is `FUTURE_DATA` and
excluded. A report-period mismatch is not auto-corrected.

## 12. Synthetic and evidence status

Real-company evidence requires `REAL_VERIFIED`. `SYNTHETIC_TEST_ONLY`,
`NOT_COMPANY_EVIDENCE`, fixture, unknown or contradictory source status cannot
support a real-company Claim. A minimal official excerpt fixture may test parsers
only; it is not a substitute for the full admitted document.

## 13. Derived request status

The request row is immutable; status is derived from append-only records:

| Derived status | Evidence |
|---|---|
| `RECEIVED` | request and declaration accepted |
| `QUARANTINED` | exact bytes atomically copied and checksummed |
| `VALIDATING` | a bounded validation run has started and is not terminal |
| `APPROVED` | all blocking checks pass and human approval checksum matches |
| `PARTIAL` | safe content with explicit non-blocking limitations; downstream eligibility is restricted |
| `REJECTED` | user/reviewer rejects source, identity, relevance or rights |
| `BLOCKED` | security, license, identity, future, corruption or policy gate fails |
| `INGESTED` | an admitted immutable manifest/document or fact set is committed |

No terminal status is overwritten. Re-review appends a new decision; expansion or
replacement creates a new request.

## 14. Human review

Approval requires the reviewer to see only safe metadata and bounded inert
previews. The review freezes:

- validator-set checksum and exact file checksum;
- source/identity/period/license decisions;
- permitted evidence roles and excerpt/retention limits;
- reason and warning codes;
- reviewer identity, decision time and review-policy version.

The reviewer cannot waive malware, path, future-data, synthetic or prohibited-use
blocks. Approval of one checksum cannot apply to replacement bytes.

## 15. Artifact and manifest admission

On approval, the local-only control path creates a Stage 4 `IngestionRun` for
`CONTROLLED_MANUAL_EVIDENCE_V1` and writes the original quarantined bytes to
immutable `raw_payloads`. Migration 0009 adds a manual import FK and an
exactly-one-source CHECK, so the manual payload references the import request and
has no fabricated `provider_request_log`. Its `provider_id` identifies the
local-only intake mechanism, not a Live source.

An immutable source-neutral `evidence_ingestion_manifests` row then binds the
RawPayload, request, declaration, all validations and approval review. Its
acquisition mode is `MANUAL_IMPORT/NOT_LIVE`. Provider-backed evidence uses the
other mutually exclusive arm and links an existing Stage 9 Provider Manifest.
Existing Provider Artifact/Manifest/RawPayload rows are never rewritten.

## 16. Document and structured-data admission

A PDF/HTML document enters the existing logical-document/DocumentVersion pipeline.
Version, parse, chunk and Citation rows bind the exact artifact checksum. A later
replacement or correction creates a successor DocumentVersion.

Structured JSON enters typed raw financial facts only when an approved schema,
Provider/concept mapping, units, periods, publication time and line-level lineage
exist. Missing values remain missing. The importer cannot calculate TTM, metrics
or valuation, and unverified table text cannot become a fact.

## 17. Claim and release eligibility

Only an approved, non-future, `REAL_VERIFIED` DocumentVersion with a VALID Citation,
or an approved typed fact with complete Calculation lineage, may support a Claim.
`PARTIAL` or unverified intake can only support limitations/data-quality records.
It cannot enter a normal factual block or `PUBLISHABLE` report.

## 18. Retention and deletion

Quarantine retention defaults to seven days and may be shorter. Approved raw
retention is the minimum of declaration, license policy and any future grant.
Deletion:

1. creates an append-only retention action;
2. verifies the exact artifact and all cache/temp locations;
3. removes restricted bytes without copying them into logs/fixtures;
4. preserves only legally permitted audit metadata;
5. records impacted Snapshots, Claims, Citations and Reports;
6. prevents future evidence use; and
7. reports that full reproducibility is no longer available where applicable.

Historical Snapshot/Report rows are not rewritten to hide the event.

## 19. Logging and output

Logs contain request ID, opaque import ID, safe status/reason codes, byte count and
checksum when policy permits. They exclude absolute paths, raw content, excerpts,
credentials, SQL, stack traces and source declarations containing personal data.
CLI/API responses never expose inbox/quarantine/blob absolute paths.

## 20. Industrial FII decision

The current project has no admitted Industrial FII company body. A future official
annual/semiannual/quarterly report or announcement may be considered only after the
user supplies it and approves that exact import. One admitted annual report permits
period-specific cited historical Claims and at most a `PARTIAL` report. It does not
establish current quarter, price, valuation, target, rating or recommendation.

## 21. Test fixtures

Gate A uses only minimal synthetic PDF/HTML/JSON fixtures or a legally retainable
safe official crop. Every fixture has a manifest recording purpose, source,
license, crop rule, synthetic status, SHA-256 and LF policy. Full unapproved company
documents and real credentials never enter Git.
