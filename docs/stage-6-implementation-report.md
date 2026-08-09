# Stage 6 Implementation Report

## 1. Stage conclusion

CONDITIONAL GO. The offline parser, deterministic lexical retrieval, citations, persistence and
read-only contracts pass. Real Industrial FII and Micron body evidence and production embeddings
remain unavailable.

## 2. Current branch

`stage-6/rag-citations`; it has not been merged to `main`.

## 3. Design approval

The user approved `docs/specs/stage-6-rag-citation-design.md` and the offline-first PostgreSQL plus
application-layer lexical architecture before production implementation.

## 4. Implemented scope

Immutable document/version records, snapshot links, four safe parsers, pages, sections, chunks,
citations, tokenizer-v1, postings/BM25, vector ports, TEST_ONLY vectors, RRF/reranking, Retrieval
Runs/Hits, Evidence Bundles, eight Tools, eight GET routes and explicit CLI operations.

## 5. Unimplemented scope

OCR, pgvector, production embeddings, model calls, Agent, MCP, reports, recommendations, frontend,
broker access and trading are absent.

## 6. Document data model

Fourteen tables separate logical identity, exact versions, snapshot membership, parse artifacts,
index generations and immutable retrieval history. All foreign keys use RESTRICT.

## 7. Parsers

PDF uses pypdf text layers only; HTML uses a bounded standard-library parser; text is UTF-8 only;
JSON promotes approved pointers only. Partial/blocked degradation is explicit.

## 8. Chunk strategy

`chunk-v1` uses deterministic page/section-first half-open offsets, 1,000-character target, 1,600
hard maximum, bounded overlap and SHA-256 descriptors. PDF page, HTML anchor and JSON pointer
locations are retained. It does not claim model token counts.

## 9. Citation strategy

`citation-v1` binds exact DocumentVersion, Parse Run, Page/Section/Chunk, native locator, excerpt
and checksums. Excerpts must be contained by the claimed locator. Historical records are never
rewritten.

## 10. Tokenizer

`tokenizer-v1` applies NFKC/casefold, minimal English stopwords and deterministic CJK whole-run plus
bigram tokens while preserving codes, percentages and negations.

## 11. Lexical index

Versioned application-layer postings and Decimal BM25 support exact filters, bounded results and
stable ties without PostgreSQL text extensions.

## 12. Embedding interface

`EmbeddingProvider` is a pluggable port with fixed metadata, health and bounded methods.

## 13. Vector interface

`VectorIndex` is pluggable; no pgvector or external vector service is installed.

## 14. Production embedding status

BLOCKED: `EMBEDDING_PROVIDER_NOT_CONFIGURED`.

## 15. TEST_ONLY status

Static vectors live only under tests and are marked SYNTHETIC_TEST_ONLY / NOT_COMPANY_EVIDENCE /
OFFLINE / NOT_LIVE. They prove contracts, not semantic quality.

## 16. Hybrid retrieval

RRF is deterministic. With lexical available and vector unavailable, HYBRID returns PARTIAL and
`VECTOR_CHANNEL_BLOCKED`.

## 17. Reranker

Model-free ordering uses exact phrase, heading-token matches, fusion score, channel rank, locator
checksum and chunk index.

## 18. As-of behavior

Future publications and unknown publication time in strict historical mode are excluded. Snapshot
scope requires exact immutable membership.

## 19. Prompt injection

Untrusted instruction patterns are marked but never executed; content cannot alter permissions,
filters, configuration or Tool behavior.

## 20. Tool inventory

`list_document_versions`, `get_document_metadata`, `search_document_chunks`,
`get_document_chunk`, `get_citation`, `verify_citation`, `get_evidence_bundle` and
`get_retrieval_run`; all are READ_ONLY with no network or writes.

## 21. API

Eight GET routes expose bounded persisted metadata and cache-only retrieval. Exactly one aware
Snapshot/as-of scope is required for scoped reads and citation verification. A missing fingerprint
returns BLOCKED / `RETRIEVAL_RUN_NOT_PRECOMPUTED`; no GET performs parsing, indexing or refresh.

## 22. CLI

Explicit version registration, parse/chunk/citation persistence, parse status, sections, chunks,
document verification, lexical build, vector BLOCKED status, Retrieval Run creation and citation/
run inspection are implemented. No command downloads content implicitly.

## 23. Industrial FII result

BLOCKED. Development DB has two Industrial FII snapshots but zero approved AVAILABLE company-body
SourceDocuments. No synthetic text was presented as company research.

## 24. Micron result

BLOCKED. Development DB has one Micron snapshot and SEC filing metadata only; no approved 10-K,
10-Q or 8-K body is stored.

## 25. Citation verification

Synthetic parser/citation cases pass deterministic checksum, generation, native locator, as-of and
Blob checks. Retrieval Hits require a Citation bound to the same Chunk; invalid citations are
excluded before persistence and from Evidence Bundles.

## 26. Fixture sources

Three generic synthetic fixtures and manifests cover text, HTML and JSON contracts. Each manifest
contains source/capture/crop/checksum/use metadata and all four mandatory test-only markers.

## 27. Live document status

Tushare, licensed U.S. EOD and SEC Archive Live remain BLOCKED / NOT_ATTEMPTED. Fixture output is
never labeled live.

## 28. Embedding provider status

Production provider BLOCKED; no key, endpoint, SDK or model is configured or downloaded.

## 29. Database migration

`0005_rag_citations` creates 14 tables, constraints, indexes and immutability, supersession,
document-lineage, citation-lineage and section-cycle triggers; full downgrade removes only Stage 6
objects.

## 30. PostgreSQL integration

Real PostgreSQL 17 validates catalog creation, native JSON Pointer persistence, Page/Section and
Citation–Chunk foreign keys, cross-security rejection, terminal immutability, version/parse/index/
Retrieval Run convergence, upgrade/downgrade/re-upgrade and test isolation. The focused Stage 6
PostgreSQL suite has 11 passing tests.

## 31. Ruff

`uv run ruff check .`: exit 0.

## 32. Format check

`uv run ruff format --check .`: exit 0 after checking 235 Python files.

## 33. mypy

`uv run mypy src`: exit 0; 127 source files checked.

## 34. pytest result

`uv run pytest -q -W error`: 1263 passed in 183.15 seconds; 0 failed.

## 35. Skips and warnings

Default suite: 0 skipped and 0 warnings.

## 36. New test categories

Schemas, identity, MIME, four parsers, chunk stability, citations, injection markers, tokenizer,
BM25, vector ports, RRF/reranking, persistence, migrations, concurrency, Tool/API/CLI and manifests.

## 37. Reflection round 1

Eighteen findings were recorded; all seventeen HIGH findings and the MEDIUM finding are FIXED.

## 38. Reflection round 2

Thirty-six checks were rerun. Core offline architecture passes; real-company bodies remain BLOCKED.

## 39. Fixed issues

Missing lexical execution, fixed read placeholders, unconditional CLI stubs, missing canonical text,
incomplete Citation/Blob/locator checks, stale cache fingerprints, pre-filter BM25 statistics,
unverified or nullable Hit citations, cross-security lineage, concurrency ownership/policy races and
obsolete migration reset assumptions.

## 40. Unresolved issues

No unresolved implementation CRITICAL or HIGH. Approved real company bodies and production
Embedding remain externally unavailable.

## 41. BLOCKED items

Industrial FII body evidence, Micron filing bodies, VECTOR production retrieval, and all three Live
providers listed above.

## 42. CRITICAL/HIGH risk

Unresolved CRITICAL=0; unresolved HIGH=0. BLOCKED external evidence must not be treated as PASS.

## 43. Current limitations

Text-layer PDFs only, best-effort reading order, conservative HTML/table degradation, no OCR,
cache-only Tool/API search and no production semantic retrieval.

## 44. Rollback

Run `uv run alembic downgrade 0004_financial_normalization`; Stage 2–5 tables remain. Re-upgrade
with `uv run alembic upgrade head`.

## 45. Git status

Stage 6 implementation is uncommitted on `stage-6/rag-citations`; approved design and plan have
separate documentation commits. No merge to main occurred.

## 46. Stage 7 readiness

Technically ready only on a CONDITIONAL basis. Stage 7 may consume verified persisted evidence and
must tolerate BLOCKED company RAG evidence.

## 47. Stage 7 allowed scope

The next stage's allowed scope is defined only by the user's future formal prompt. Existing verified
evidence contracts may be reused; this report does not authorize new functionality.

## 48. Stage 7 prohibited scope

Until that prompt, no Stage 7 work is authorized. Missing RAG evidence must not be used to generate
complete company conclusions, recommendations or fabricated citations.
