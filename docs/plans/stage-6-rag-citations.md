# Stage 6 Document Retrieval and Verifiable Citations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute this plan task-by-task with strict
> test-driven development. Each production behavior begins with an observed failing test.

**Goal:** Build an offline-first, point-in-time document knowledge base with immutable document
versions, safe parsers, deterministic chunks, bilingual lexical retrieval, pluggable vector
ports, cache-only read surfaces, and cryptographically verifiable citations.

**Architecture:** PostgreSQL stores identity, versions, parse artifacts, chunks, citations,
index metadata/postings, retrieval runs and hits. Pure domain services receive repository,
BlobStorage, parser, embedding and vector ports by injection. CLI/internal services perform all
writes; Tool and GET API handlers perform cache-only reads.

**Tech Stack:** Python 3.12.13, `uv`, Pydantic 2, SQLAlchemy 2, PostgreSQL 17, Alembic,
FastAPI, Typer, pytest, Ruff, strict mypy, standard-library HTML/text/JSON parsing, and a locked
`pypdf>=6,<7` dependency for PDF text layers.

## Global constraints

- Work only on `stage-6/rag-citations`; do not merge or enter Stage 7.
- Do not install pgvector, download an embedding model, call OpenAI or another model, implement
  Agent/MCP/Reflection runtime, generate a report/target/recommendation, add a frontend, connect a
  broker, or trade.
- Default tests deny external network and use only literal loopback PostgreSQL.
- Existing Industrial FII and Micron evidence contains no approved document body. Company-body
  acceptance remains `BLOCKED`; synthetic files are never company evidence.
- Every synthetic resource carries `SYNTHETIC_TEST_ONLY`, `NOT_COMPANY_EVIDENCE`, `OFFLINE`,
  and `NOT_LIVE`.
- Document content is untrusted data. It cannot alter parser configuration, filters, cutoff,
  Tool permissions, network policy or code execution.
- `DocumentVersion`, terminal parse/index/retrieval records, old snapshots and citations are
  immutable. Revision, withdrawal and supersession use new records/relations.
- Unknown `published_at` is excluded from strict historical retrieval. Future documents are
  always excluded.
- Production VECTOR is `BLOCKED`; lexical-only HYBRID is `PARTIAL`; successful LEXICAL may be
  `PASS`.
- Tool/API are `READ_ONLY`, `writes=false`, `requires_network=false`. A missing precomputed
  request returns `BLOCKED` and `RETRIEVAL_RUN_NOT_PRECOMPUTED`.
- RAG table text never creates or changes Stage 5 canonical financial facts.
- Every RED command must fail for the intended missing behavior, not syntax, fixture or setup.
- Every GREEN command must exit zero without warning before the next task starts.

## File map

### Domain documents

- `src/stock_research_agent/domain/documents/enums.py`: controlled document, parse, locator,
  citation and trust vocabularies.
- `src/stock_research_agent/domain/documents/schemas.py`: immutable input/output models for
  versions, parse artifacts, chunks, citations and safety markers.
- `src/stock_research_agent/domain/documents/repositories.py`: repository protocols only.
- `src/stock_research_agent/domain/documents/identity.py`: immutable version registration and
  snapshot-body association rules.
- `src/stock_research_agent/domain/documents/mime.py`: byte/MIME allowlist and magic checks.
- `src/stock_research_agent/domain/documents/parsers/base.py`: parser protocol/config/result.
- `src/stock_research_agent/domain/documents/parsers/pdf.py`: bounded text-layer PDF parser.
- `src/stock_research_agent/domain/documents/parsers/html.py`: bounded active-content-free HTML.
- `src/stock_research_agent/domain/documents/parsers/text.py`: UTF-8 canonical text parser.
- `src/stock_research_agent/domain/documents/parsers/json.py`: approved-path JSON parser.
- `src/stock_research_agent/domain/documents/parsing.py`: explicit parse-run orchestration.
- `src/stock_research_agent/domain/documents/chunking.py`: stable section/paragraph chunking.
- `src/stock_research_agent/domain/documents/citations.py`: anchor creation and verification.
- `src/stock_research_agent/domain/documents/injection.py`: deterministic suspicious-text marker.

### Domain retrieval

- `src/stock_research_agent/domain/retrieval/enums.py`: modes, index states and evidence status.
- `src/stock_research_agent/domain/retrieval/schemas.py`: lexical/vector/search/run/evidence models.
- `src/stock_research_agent/domain/retrieval/repositories.py`: lexical and run read/write protocols.
- `src/stock_research_agent/domain/retrieval/tokenizer.py`: `tokenizer-v1` English/CJK tokens.
- `src/stock_research_agent/domain/retrieval/lexical.py`: index drafts, Decimal BM25 and search.
- `src/stock_research_agent/domain/retrieval/vector.py`: embedding/vector ports and blocked default.
- `src/stock_research_agent/domain/retrieval/hybrid.py`: RRF and stable reranking.
- `src/stock_research_agent/domain/retrieval/service.py`: explicit write and cache-only read flows.
- `src/stock_research_agent/domain/retrieval/evidence.py`: verified Evidence Bundle assembly.

### Persistence and surfaces

- `src/stock_research_agent/db/models/knowledge.py`: fourteen Stage 6 SQLAlchemy models.
- `src/stock_research_agent/db/repositories/knowledge.py`: SQLAlchemy repository implementation.
- `migrations/versions/0005_create_rag_and_citations.py`: schema, constraints, indexes and triggers.
- `src/stock_research_agent/tools/rag.py`: eight cache-only read adapters.
- `src/stock_research_agent/tools/schemas_rag.py`: strict RAG Tool request/envelope schemas.
- `src/stock_research_agent/tools/registry.py`: canonical Stage 6 registrations/composition.
- `src/stock_research_agent/api/routes/rag.py`: eight GET routes.
- `src/stock_research_agent/api/dependencies.py`: document/retrieval query-service composition.
- `src/stock_research_agent/api/read_only.py`: safe RAG outcome mapping.
- `src/stock_research_agent/api/router.py`: include RAG router.
- `src/stock_research_agent/cli_documents.py`: explicit version/parse and document reads.
- `src/stock_research_agent/cli_rag.py`: explicit index/run writes and cache reads.
- `src/stock_research_agent/cli.py`: register new Typer groups.
- `src/stock_research_agent/config.py`, `.env.example`: bounded parser/retrieval configuration.
- `pyproject.toml`, `uv.lock`: locked PDF dependency only.

## Interface catalog

The names below are defined before use and remain stable across tasks.

```python
# domain/documents/parsers/base.py
class DocumentParser(Protocol):
    @property
    def parser_name(self) -> str: ...
    @property
    def parser_version(self) -> str: ...
    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument: ...

# domain/documents/repositories.py
class DocumentVersionRepository(Protocol):
    def get_source_body(self, source_document_id: UUID) -> SourceBodyRecord | None: ...
    def find_version(self, logical_document_id: UUID, checksum: str) -> DocumentVersionRecord | None: ...
    def next_version_number(self, logical_document_id: UUID) -> int: ...
    def add_version(self, value: DocumentVersionWrite) -> DocumentVersionRecord: ...
    def add_snapshot_version_link(self, value: SnapshotDocumentVersionWrite) -> SnapshotDocumentVersionRecord: ...

class DocumentArtifactRepository(Protocol):
    def find_parse_run(self, key: ParseRunKey) -> DocumentParseRunRecord | None: ...
    def create_parse_run(self, value: DocumentParseRunWrite) -> DocumentParseRunRecord: ...
    def replace_running_artifacts(self, parse_run_id: UUID, value: ParsedDocument) -> None: ...
    def finish_parse_run(self, parse_run_id: UUID, result: ParseCompletion) -> DocumentParseRunRecord: ...
    def get_citation_context(self, citation_id: UUID) -> CitationContext | None: ...

# domain/retrieval/vector.py
class EmbeddingProvider(Protocol):
    @property
    def metadata(self) -> EmbeddingProviderMetadata: ...
    def health_status(self) -> VectorHealth: ...
    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[Decimal, ...], ...]: ...
    def embed_query(self, text: str) -> tuple[Decimal, ...]: ...

class VectorIndex(Protocol):
    def build(self, request: VectorBuildRequest) -> VectorIndexResult: ...
    def search(self, request: VectorSearchRequest) -> tuple[VectorHit, ...]: ...

# domain/retrieval/repositories.py
class RetrievalWriteRepository(Protocol):
    def find_run_by_fingerprint(self, fingerprint: str) -> RetrievalRunRecord | None: ...
    def create_run(self, value: RetrievalRunWrite) -> RetrievalRunRecord: ...
    def add_hits(self, run_id: UUID, hits: tuple[RetrievalHitWrite, ...]) -> None: ...
    def finish_run(self, run_id: UUID, completion: RetrievalCompletion) -> RetrievalRunRecord: ...

class RetrievalReadRepository(Protocol):
    def find_terminal_run(self, fingerprint: str) -> RetrievalRunRecord | None: ...
    def list_hits(self, run_id: UUID, limit: int) -> tuple[RetrievalHitRecord, ...]: ...

# domain service signatures
class DocumentVersionService:
    def __init__(self, repository: DocumentVersionRepository, blob_storage: BlobStorage) -> None: ...
    def register(self, request: RegisterDocumentVersionRequest) -> DocumentVersionResult: ...

class DocumentParseService:
    def __init__(self, repository: DocumentArtifactRepository, parsers: ParserRegistry) -> None: ...
    def parse(self, request: ParseDocumentRequest) -> DocumentParseResult: ...

class DocumentChunker:
    def chunk(self, document: ParsedDocument, config: ChunkConfig) -> tuple[DocumentChunkDraft, ...]: ...

class CitationVerifier:
    def verify(self, context: CitationContext) -> CitationVerification: ...

class VersionedTokenizer:
    def tokenize(self, text: str, *, language: DocumentLanguage) -> tuple[str, ...]: ...

class LexicalIndexService:
    def build(self, request: LexicalBuildRequest) -> LexicalIndexResult: ...

class LexicalSearchService:
    def search(self, request: LexicalSearchRequest) -> tuple[LexicalHit, ...]: ...

class RetrievalExecutionService:
    def execute(self, request: RetrievalExecutionRequest) -> RetrievalExecutionResult: ...

class PrecomputedRetrievalQueryService:
    def get(self, request: PrecomputedRetrievalRequest) -> RetrievalResult: ...
```

## Task 1: Document vocabularies and strict schemas

**Files:** create `domain/documents/__init__.py`, `enums.py`, `schemas.py`; test
`tests/unit/test_document_schemas.py`.

**Produces:** `DocumentLanguage`, `TrustLevel`, `SourceVersionStatus`, `ParseStatus`,
`PageStatus`, `LocatorType`, `CitationStatus`, `EvidenceMarkers`, `SourceBodyRecord`,
`RegisterDocumentVersionRequest`, `DocumentVersionWrite`, `DocumentVersionRecord`,
`DocumentVersionResult`, `BindSnapshotDocumentVersionRequest`,
`SnapshotDocumentVersionWrite`, `SnapshotDocumentVersionRecord`,
`SnapshotDocumentVersionResult`, `ParserConfig`, `ParsedPage`, `ParsedSection`,
`ParsedDocument`, `ParseRunKey`, `DocumentParseRunWrite`, `DocumentParseRunRecord`,
`ParseCompletion`, `DocumentParseResult`, `ChunkConfig`, `DocumentChunkDraft`,
`DocumentChunkRecord`, `CreateCitationRequest`, `CitationAnchorDraft`,
`CitationAnchorRecord`, `CitationContext`, `CitationScope`, and `CitationVerification`.

- [x] Write strict model tests for aware UTC timestamps, SHA-256, opaque URI, enum rejection,
  reversed page/offset ranges, exact fixture markers and frozen input.
- [x] Run `uv run pytest tests/unit/test_document_schemas.py -q`; expect collection failure for
  missing `stock_research_agent.domain.documents`.
- [x] Add the enums and minimal Pydantic models with `extra=forbid`, `strict=True`,
  `frozen=True`, and safe validators.
- [x] Re-run the focused file; expect all tests to pass with no warning.
- [x] Run `uv run mypy src/stock_research_agent/domain/documents`; expect success.

## Task 2: Immutable logical identity and version service

**Files:** create `domain/documents/repositories.py`, `identity.py`; test
`tests/unit/test_document_identity.py`.

**Produces:**

```python
class DocumentVersionService:
    def __init__(self, repository: DocumentVersionRepository, blob_storage: BlobStorage) -> None: ...
    def register(self, request: RegisterDocumentVersionRequest) -> DocumentVersionResult: ...
```

- [x] Write failing tests proving same logical-document/checksum reuse, changed bytes create the
  next version, incompatible checksum metadata fails, old versions are untouched, withdrawal and
  supersession are new rows/relations, and missing stable external identity is `BLOCKED`.
- [x] Run the focused file; expect imports/service behavior to fail because `identity.py` is absent.
- [x] Implement canonical identity keys and register/reuse behavior using repository and
  BlobStorage metadata only; do not create a Session or read a local path.
- [x] Re-run the focused file and document schema tests; expect pass.

## Task 3: Snapshot-to-body version association

**Files:** modify `identity.py`, `repositories.py`, `schemas.py`; test
`tests/unit/test_snapshot_document_versions.py`.

**Produces:**

```python
def bind_version_to_snapshot(
    repository: DocumentVersionRepository,
    request: BindSnapshotDocumentVersionRequest,
) -> SnapshotDocumentVersionResult: ...
```

- [x] Write failing tests for exact security/source linkage, required
  `category=SOURCE_DOCUMENTS`, required `source_record_type=source_documents`, rejection of
  metadata-only `FILING_METADATA`, terminal old-snapshot protection and idempotent reuse.
- [x] Run the focused file; expect missing function/behavior failure.
- [x] Implement the minimum association validation and repository call.
- [x] Re-run Tasks 1–3 tests; expect pass.

## Task 4: Blob, MIME and magic-byte validation

**Files:** create `domain/documents/mime.py`; modify `schemas.py`; test
`tests/unit/test_document_mime.py` and extend `tests/unit/test_blob_storage.py` only for read
integrity behavior reused by Stage 6.

**Produces:**

```python
def validate_document_content(content: bytes, declared_mime_type: str, max_bytes: int) -> ValidatedDocumentContent: ...
```

- [x] Write failing cases for PDF magic, safe HTML/text/JSON, empty/oversized input, MIME mismatch,
  executable/archive magic, NUL-heavy text, absolute paths in metadata and checksum mismatch.
- [x] Run both focused files; expect missing validator failures while old Blob tests stay green.
- [x] Implement a fixed MIME allowlist and bounded magic checks without extension trust or network.
- [x] Re-run both focused files; expect pass.

## Task 5: Parse-run port and orchestration

**Files:** create `parsers/__init__.py`, `parsers/base.py`, `parsing.py`; test
`tests/unit/test_document_parsing_service.py`.

**Produces:** `DocumentParser`, `ParserRegistry`, `ParseRunKey`, `DocumentParseService.parse`.

```python
class DocumentParseService:
    def parse(self, document_version_id: UUID, config: ParserConfig) -> DocumentParseResult: ...
```

- [x] Write failing tests for parser allowlisting, same-version/config idempotency, parser version
  creating a new run, terminal reuse, PASS/PARTIAL/BLOCKED/FAIL propagation and safe errors without
  absolute paths.
- [x] Run the focused file; expect missing parser/service failure.
- [x] Implement orchestration that reads exact BlobStorage bytes, invokes one injected parser,
  persists artifacts in one transaction, and never accesses network.
- [x] Re-run Tasks 4–5 tests; expect pass.

## Task 6: Text-layer PDF parser

**Files:** create `parsers/pdf.py`; modify `pyproject.toml`, `uv.lock`; create
`tests/fixtures/rag/pdf_samples.py`; test `tests/unit/test_pdf_parser.py`.

**Produces:** `PdfTextParser.parse(content: bytes, config: ParserConfig) -> ParsedDocument`.

- [x] Add independent base64 PDF byte constants for one text page, a blank page, two pages and an
  encrypted document; every constant is synthetic and marker-bound.
- [x] Write failing tests for 1-based pages, preserved text layer, blank/no-text status, encrypted
  BLOCKED, size/page/per-page character limits, partial-page warning and no OCR/attachment/action
  execution.
- [x] Run the focused file; expect missing `PdfTextParser` failure.
- [x] Run `uv add "pypdf>=6,<7"`; verify only `pyproject.toml` and `uv.lock` dependency resolution
  changes before implementation.
- [x] Implement bounded pypdf text extraction. Treat reading order as best-effort metadata and
  downgrade uncertain/partial extraction honestly.
- [x] Re-run PDF and parsing-service tests; expect pass.

## Task 7: Safe bounded HTML parser

**Files:** create `parsers/html.py`; test `tests/unit/test_html_parser.py`.

**Produces:** `SafeHtmlParser.parse(content: bytes, config: ParserConfig) -> ParsedDocument`.

- [x] Write failing tests for heading paths, paragraphs, stable `id`/`name` anchors, table text,
  script/style/iframe/object/embed/form removal, event-attribute removal, hidden text, malformed
  SEC-like markup downgrade, node/depth/character limits and no URL/resource loading.
- [x] Run the focused file; expect missing parser failure.
- [x] Implement a bounded standard-library `HTMLParser` subclass with an explicit allowed content
  model and active-tag suppression.
- [x] Re-run HTML and parse orchestration tests; expect pass.

## Task 8: Canonical text parser

**Files:** create `parsers/text.py`; test `tests/unit/test_text_parser.py`.

**Produces:** `PlainTextParser.parse(content: bytes, config: ParserConfig) -> ParsedDocument`.

- [x] Write failing tests for UTF-8/BOM, CRLF/CR normalization, canonical half-open offsets,
  decode failure, character limits, control characters and instruction-like text remaining data.
- [x] Run the focused file; expect missing parser failure.
- [x] Implement UTF-8-only V0.1 decoding and bounded canonical text output.
- [x] Re-run the focused file; expect pass.

## Task 9: Approved-path JSON parser

**Files:** create `parsers/json.py`; test `tests/unit/test_json_document_parser.py`.

**Produces:**

```python
class JsonDocumentParser:
    def __init__(self, approved_pointers: tuple[str, ...]) -> None: ...
    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument: ...
```

- [x] Write failing tests for RFC 6901 pointers, only approved strings becoming text, unknown fields
  remaining non-searchable metadata, depth/array/size limits, duplicate keys, invalid JSON and
  strings never becoming instructions.
- [x] Run the focused file; expect missing parser failure.
- [x] Implement strict JSON loading with duplicate-key rejection, iterative bound checks and
  deterministic pointer ordering.
- [x] Re-run JSON, text and parsing-service tests; expect pass.

## Task 10: Page and section invariants

**Files:** modify document `schemas.py`; create `tests/unit/test_document_structure.py`.

**Produces:** canonical page-relative PDF locations and document-relative HTML/text/JSON ranges.

- [x] Write failing tests for nested section paths, missing PDF sections, page/offset bounds,
  section parent cycles in domain drafts, table content kind and no invented headings.
- [x] Run the focused file; expect validation failures to be absent.
- [x] Add range and parent/path validation helpers used by parsers and persistence.
- [x] Re-run parser and structure suites; expect pass.

## Task 11: Deterministic chunk construction

**Files:** create `chunking.py`; test `tests/unit/test_document_chunking.py`.

**Produces:**

```python
class DocumentChunker:
    def chunk(self, parsed: ParsedDocument, config: ChunkConfig) -> tuple[DocumentChunkDraft, ...]: ...
```

- [x] Write failing tests for section-first/paragraph-second splitting, 1,000 target, 1,600 hard
  maximum, 120 minimum, at most 200/20% overlap, empty rejection, short merge, table isolation and
  avoiding splits inside `601138.SH`, `12.5%`, decimal+unit and ASCII words.
- [x] Run the focused file; expect missing chunker failure.
- [x] Implement the minimum deterministic chunker with canonical range retention.
- [x] Re-run the focused file; expect pass.

## Task 12: Chunk stability and versioning

**Files:** modify `chunking.py`, `schemas.py`; test
`tests/unit/test_document_chunk_stability.py`.

**Produces:** `chunk-v1` canonical descriptor and SHA-256.

- [x] Write failing tests proving identical input/order yields identical descriptors/checksums,
  parser/config/chunk version changes yield different generations, overlap is bounded and old
  chunks are never edited.
- [x] Run the focused file; expect checksum/version behavior failure.
- [x] Implement canonical JSON hashing and natural keys independent of random UUIDs.
- [x] Re-run Tasks 11–12 tests; expect pass.

## Task 13: Citation anchor construction

**Files:** create `citations.py`; test `tests/unit/test_citation_anchors.py`.

**Produces:**

```python
def create_citation(request: CreateCitationRequest) -> CitationAnchorDraft: ...
```

- [x] Write failing tests for PDF page range, HTML anchor+offset, text offset, JSON pointer and
  section range; excerpt maximum; 1-based pages; source/checksum fields; nonexistent/out-of-bound
  locations; and binding to exact `document_version_id`.
- [x] Run the focused file; expect missing constructor failure.
- [x] Implement deterministic locator/excerpt checksums without a model.
- [x] Re-run the focused file; expect pass.

## Task 14: Deterministic citation verifier

**Files:** modify `citations.py`, `repositories.py`; test
`tests/unit/test_citation_verifier.py`.

**Produces:**

```python
class CitationVerifier:
    def verify(self, citation_id: UUID, scope: CitationScope) -> CitationVerification: ...
```

- [x] Write failing tests for `VALID`, `INVALID`, `STALE_REFERENCE`, `FUTURE_DATA`,
  `SOURCE_MISSING`, `PARSE_VERSION_MISMATCH`, unknown publication strict exclusion, Blob checksum,
  parse/checksum/location/excerpt mismatch and snapshot membership.
- [x] Run the focused file; expect missing verifier behavior.
- [x] Implement ordered deterministic checks using read-only repositories and BlobStorage.
- [x] Re-run citation suites; expect pass.

## Task 15: Prompt-injection marker

**Files:** create `injection.py`; test `tests/unit/test_prompt_injection_marker.py`.

**Produces:** `mark_untrusted_instructions(text: str) -> tuple[SafetyMarker, ...]` using
`prompt-injection-rules-v1`.

- [x] Write failing cases for override language, system-prompt imitation, credential requests,
  Tool syntax and exfiltration URLs in English/Chinese; verify ordinary risk disclosure remains
  present and markers never change parser/filter configuration.
- [x] Run the focused file; expect missing marker failure.
- [x] Implement bounded deterministic rule matching that marks but never executes or deletes text.
- [x] Re-run marker/parser tests; expect pass.

## Task 16: Retrieval vocabularies and strict schemas

**Files:** create `domain/retrieval/__init__.py`, `enums.py`, `schemas.py`; test
`tests/unit/test_retrieval_schemas.py`.

**Produces:** `RetrievalMode`, `IndexStatus`, `VectorHealth`, `LexicalToken`,
`TokenizedQuery`, `RetrievalFilters`, `RetrievalRequest`, `LexicalBuildRequest`,
`LexicalIndexResult`, `LexicalSearchRequest`, `LexicalHit`, `Bm25Stats`,
`EmbeddingProviderMetadata`, `VectorBuildRequest`, `VectorIndexResult`,
`VectorSearchRequest`, `VectorHit`, `HybridHit`, `RetrievalRunWrite`,
`RetrievalRunRecord`, `RetrievalHitWrite`, `RetrievalHitRecord`,
`RetrievalCompletion`, `RetrievalExecutionResult`, and `EvidenceBundle`.

- [x] Write failing validation tests for exact security plus snapshot/as-of scope, aware UTC,
  query 1–256, max results 1–20, filter allowlists, strict unknown-publication option and null ranks.
- [x] Run the focused file; expect missing package failure.
- [x] Implement frozen strict models and enums.
- [x] Re-run focused schemas and mypy for both domain packages; expect pass.

## Task 17: Versioned bilingual tokenizer

**Files:** create `tokenizer.py`; test `tests/unit/test_retrieval_tokenizer.py`.

**Produces:** `VersionedTokenizer.tokenize(value: str, *, query: bool) -> tuple[LexicalToken, ...]`.

- [x] Write independent golden tokens for NFKC, case folding, Chinese bigrams/whole run, single CJK
  characters, `601138.SH`, `NASDAQ:MU`, `10-K`, percentages, currencies, decimal units, negations,
  punctuation, controls, empty, 256-char and 64-token bounds.
- [x] Run the focused file; expect missing tokenizer failure.
- [x] Implement `tokenizer-v1` with a versioned minimal stopword tuple and no stemming/translation.
- [x] Re-run focused tokenizer tests twice and compare results; expect stable pass.

## Task 18: Lexical index drafts and postings

**Files:** create `retrieval/repositories.py`, `lexical.py`; test
`tests/unit/test_lexical_index.py`.

**Produces:**

```python
class LexicalIndexService:
    def build(self, request: LexicalBuildRequest) -> LexicalIndexResult: ...
```

- [x] Write failing tests for snapshot/as-of exact scope, known-publication selection, future and
  unknown exclusion, stable document-set checksum, posting TF/positions, repeated build reuse,
  tokenizer/chunk version generation and bounded transaction rollback.
- [x] Run the focused file; expect missing index service failure.
- [x] Implement pure posting drafts plus repository orchestration; no PostgreSQL FTS expression.
- [x] Re-run tokenizer/index tests; expect pass.

## Task 19: Decimal BM25 and lexical search

**Files:** modify `lexical.py`; test `tests/unit/test_lexical_bm25.py`.

**Produces:**

```python
def bm25_score(stats: Bm25Stats) -> Decimal: ...
class LexicalSearchService:
    def search(self, request: LexicalSearchRequest) -> tuple[LexicalHit, ...]: ...
```

- [x] Hand-calculate golden BM25 values for fixed TF/DF/N/length cases using k1=1.2, b=0.75 and
  12-decimal quantization; add zero-hit, multi-token, phrase, security/type/language/trust/section,
  stable tie and max-result tests.
- [x] Run the focused file; expect missing score/search failure.
- [x] Implement Decimal BM25 and exact-token candidate queries with stable locator/checksum ties.
- [x] Re-run lexical suites; expect pass.

## Task 20: EmbeddingProvider and VectorIndex ports

**Files:** create `vector.py`; test `tests/unit/test_vector_interfaces.py`.

**Produces:** `EmbeddingProvider`, `VectorIndex`, `BlockedEmbeddingProvider`.

- [x] Write failing tests for fixed metadata, strict dimensions/max length, health, model/base URL
  not request-controlled, no key fields, no import-time work and blocked provider build/search.
- [x] Run the focused file; expect missing ports/default failure.
- [x] Implement protocols and production blocked default without any SDK, HTTP or model dependency.
- [x] Re-run focused tests under socket denial; expect pass.

## Task 21: Isolated static test vectors

**Files:** create `tests/fixtures/rag/static_vectors.py`; extend
`tests/unit/test_vector_interfaces.py`.

**Produces:** test-only `StaticFixtureEmbeddingProvider` and `InMemoryStaticVectorIndex` under
`tests/`, never production package.

- [x] Write failing tests first for marker enforcement, fixed independent vectors, dimension and
  chunk-checksum rejection, stable cosine ordering, no hash embedding and no production registry.
- [x] Run focused tests; expect missing test fixture implementation failure.
- [x] Add the minimum test-only provider/index in the test fixture module.
- [x] Re-run focused tests and module-boundary scan; expect pass.

## Task 22: Hybrid RRF

**Files:** create `hybrid.py`; test `tests/unit/test_hybrid_retrieval.py`.

**Produces:** `reciprocal_rank_fusion(lexical, vector, *, k=60) -> tuple[HybridHit, ...]`.

- [x] Hand-calculate RRF golden scores; test two channels, lexical-only PARTIAL, vector BLOCKED,
  null unavailable ranks, duplicate chunk collapse and deterministic ties.
- [x] Run focused tests; expect missing fusion failure.
- [x] Implement Decimal RRF using actual ranks only.
- [x] Re-run focused tests; expect pass.

## Task 23: Stable reranker

**Files:** modify `hybrid.py`; test `tests/unit/test_stable_reranker.py`.

**Produces:** `stable_rerank(query: TokenizedQuery, hits: tuple[HybridHit, ...]) -> tuple[HybridHit, ...]`.

- [x] Write failing tests for exact phrase, heading-token count, fusion, best channel, locator and
  chunk-index tuple order; no popularity, future-recency, randomness or model effects.
- [x] Run focused tests; expect missing reranker failure.
- [x] Implement the documented stable tuple and enumerated `rerank_reason`.
- [x] Re-run hybrid/reranker tests; expect pass.

## Task 24: Retrieval run and hit service

**Files:** create `service.py`; extend `repositories.py`; test
`tests/unit/test_retrieval_service.py`.

**Produces:**

```python
class RetrievalExecutionService:
    def execute(self, request: RetrievalRequest) -> RetrievalExecutionResult: ...
class PrecomputedRetrievalQueryService:
    def lookup(self, request: RetrievalRequest) -> EvidenceBundle: ...
```

- [x] Write failing tests for canonical request fingerprint, explicit run/hit persistence,
  idempotent terminal reuse, run version changes, stable final ranks, invalid citations excluded,
  terminal immutability, write rollback and cache-only missing status/warning.
- [x] Run focused tests; expect missing service failure.
- [x] Implement explicit write orchestration and a separate read service whose repository protocol
  has no write methods.
- [x] Re-run focused tests; expect pass.

## Task 25: Verified Evidence Bundle

**Files:** create `evidence.py`; test `tests/unit/test_evidence_bundles.py`.

**Produces:** `build_evidence_bundle(run, hits, citations, *, excerpt_limit=1000) -> EvidenceBundle`.

- [x] Write failing tests for only VALID citations, bounded excerpts, no full body/path/raw payload,
  exact versions/index versions/cutoff/reasons, zero evidence, PARTIAL/BLOCKED components and no
  conclusion/recommendation fields.
- [x] Run focused tests; expect missing builder failure.
- [x] Implement the immutable read model and warning aggregation.
- [x] Re-run retrieval/evidence tests; expect pass.

## Task 26: SQLAlchemy Stage 6 models

**Files:** create `db/models/knowledge.py`; modify `db/models/__init__.py` and migration metadata
imports; test `tests/unit/test_knowledge_models.py`.

**Produces:** exactly these fourteen SQLAlchemy model/table pairs:

- `LogicalDocument` / `logical_documents`;
- `DocumentVersion` / `document_versions`;
- `SnapshotDocumentVersion` / `snapshot_document_versions`;
- `DocumentParseRun` / `document_parse_runs`;
- `DocumentPage` / `document_pages`;
- `DocumentSection` / `document_sections`;
- `DocumentChunk` / `document_chunks`;
- `CitationAnchor` / `citation_anchors`;
- `LexicalIndexVersion` / `lexical_index_versions`;
- `LexicalPosting` / `lexical_postings`;
- `EmbeddingRecord` / `embedding_records`;
- `VectorIndexVersion` / `vector_index_versions`;
- `RetrievalRun` / `retrieval_runs`;
- `RetrievalHit` / `retrieval_hits`.

- [x] Write table-metadata tests for every column, FK `RESTRICT`, controlled string CHECK,
  checksum/range/status constraints, exact unique keys, query indexes and absence of vector/native
  enum extensions.
- [x] Run focused tests; expect missing models failure.
- [x] Implement SQLAlchemy 2 typed models matching document/retrieval records.
- [x] Re-run model/domain tests; expect pass.

## Task 27: Alembic 0005 migration and immutability triggers

**Files:** create `migrations/versions/0005_create_rag_and_citations.py`; test
`tests/integration/test_rag_migrations.py`.

**Produces:** upgrade/downgrade for `logical_documents`, `document_versions`,
`snapshot_document_versions`, `document_parse_runs`, `document_pages`, `document_sections`,
`document_chunks`, `citation_anchors`, `lexical_index_versions`, `lexical_postings`,
`embedding_records`, `vector_index_versions`, `retrieval_runs`, and `retrieval_hits`; section-cycle
checks; and terminal immutability triggers.

- [x] Write PostgreSQL catalog tests for all tables, columns, FKs, unique/CHECK constraints,
  indexes, triggers, Stage 2–5 preservation, downgrade and re-upgrade.
- [x] Run with `TEST_DATABASE_URL`; expect failure because revision/tables are absent.
- [x] Implement migration with no data, parsing, index build, embedding, network or secrets.
- [x] Re-run migration test; expect pass ending at `0005_create_rag_and_citations (head)`.

## Task 28: PostgreSQL knowledge repository

**Files:** create `db/repositories/knowledge.py`; test
`tests/integration/test_knowledge_repository_postgres.py`.

**Produces:** concrete implementations of all document, lexical and retrieval protocols.

- [x] Write failing PostgreSQL tests for version/link/run/posting/hit idempotency, as-of selection,
  future/unknown exclusion, parameterized bounded reads, transaction rollback, terminal mutation
  rejection, old citation survival and Session closure.
- [x] Run focused integration tests; expect missing repository failure.
- [x] Implement SQLAlchemy statements and record mapping without provider/parser/network access.
- [x] Re-run focused integration and unit repository tests; expect pass.

## Task 29: Concurrency and immutable-history PostgreSQL tests

**Files:** extend `tests/integration/test_knowledge_repository_postgres.py` and
`tests/integration/test_rag_migrations.py`.

- [x] Add failing concurrent duplicate version, parse run, lexical build and retrieval-run tests;
  add direct SQL mutation/delete attempts for terminal versions/artifacts/runs and version-event
  historical access.
- [x] Run focused tests; observe the exact race/immutability failures.
- [x] Add minimal unique-conflict recovery and trigger fixes in repository/migration.
- [x] Re-run focused tests repeatedly; expect one canonical record and preserved history.

## Task 30: Synthetic fixture corpus and manifests

**Files:** create `tests/fixtures/rag/manifests/*.json`, `synthetic_html.py`,
`synthetic_json.py`, `synthetic_text.py`; test `tests/unit/test_rag_fixture_manifests.py`.

- [x] Write failing manifest tests for required source/checksum/crop/use fields and all four
  synthetic markers; reject company symbols/claims, missing markers and checksum mismatch.
- [x] Run focused tests; expect missing fixtures failure.
- [x] Add only clearly synthetic parser/citation/search/injection content and exact manifests.
- [x] Re-run fixture and parser tests; expect pass.
- [x] Add explicit tests asserting no Industrial FII or Micron company body fixture exists and both
  company acceptance statuses are `BLOCKED`.

## Task 31: Eight read-only RAG Tools

**Files:** create `tools/schemas_rag.py`, `tools/rag.py`; modify `tools/registry.py`; test
`tests/unit/test_rag_tools.py` and extend `tests/unit/test_tool_registry.py`.

**Produces:** `list_document_versions`, `get_document_metadata`, `search_document_chunks`,
`get_document_chunk`, `get_citation`, `verify_citation`, `get_evidence_bundle`,
`get_retrieval_run`, all version `1.0.0`.

- [x] Write failing metadata/schema/handler tests for strict READ_ONLY flags, cache hit/miss,
  no parser/index/embedding/provider/network/write dependency, bounded output, version/citation
  metadata, no full body/path and stable Decimal serialization.
- [x] Run focused tests; expect missing canonical registrations failure.
- [x] Implement thin adapters over document/retrieval read services and canonical registry entries.
- [x] Re-run Tool and old registry suites; expect pass.

## Task 32: Eight GET API routes

**Files:** create `api/routes/rag.py`; modify `api/dependencies.py`, `api/read_only.py`,
`api/router.py`; test `tests/contract/test_rag_api_contract.py`.

- [x] Write failing OpenAPI/TestClient/PostgreSQL contracts for all routes, security plus exact
  snapshot/as-of, query/filter/max bounds, future exclusion, cache miss BLOCKED 200, vector
  BLOCKED, hybrid PARTIAL, 404/422/request ID and no write/SQL/path/key leakage.
- [x] Run focused contract tests; expect missing routes failure.
- [x] Implement GET-only routes and safe outcome mapping using read-only service dependencies.
- [x] Re-run RAG and existing API contracts; expect pass.

## Task 33: Explicit document and RAG CLI

**Files:** create `cli_documents.py`, `cli_rag.py`; modify `cli.py`; test
`tests/integration/test_rag_cli.py` and `tests/unit/test_rag_cli_contracts.py`.

- [x] Write failing tests for version registration from persisted body only, parse/reuse/status,
  sections/chunks/verify, lexical build/reuse, vector BLOCKED, explicit persisted search,
  cache/show/citation/run/evidence, JSON/human output, exit codes and no URL/path/network/model.
- [x] Run focused tests; expect missing command groups failure.
- [x] Implement `documents` and `rag` Typer groups with injected service factories and explicit
  transaction boundaries.
- [x] Re-run CLI and all existing CLI tests; expect pass.

## Task 34: Configuration and module-boundary enforcement

**Files:** modify `config.py`, `.env.example`; extend
`tests/unit/test_config.py`, `tests/unit/test_module_boundaries.py`,
`tests/unit/test_default_network_policy.py`.

- [x] Write failing tests for exact parser/query limits, redacted Blob root, no embedding secret/
  URL/model request setting, no pgvector/model/Agent/MCP modules, parser no network/Session and
  Tool/API no write-service imports.
- [x] Run focused tests; expect missing configuration/boundary behavior.
- [x] Add only approved bounded settings and imports needed by explicit CLI composition.
- [x] Re-run focused and configuration contract tests; expect pass.

## Task 35: Documentation set

**Files:** create `docs/document-versions.md`, `docs/document-parsing.md`,
`docs/document-chunking.md`, `docs/rag-lexical-retrieval.md`,
`docs/rag-vector-interface.md`, `docs/rag-hybrid-retrieval.md`, `docs/citations.md`,
`docs/evidence-bundles.md`, `docs/prompt-injection-defense.md`; modify
`docs/tool-contracts.md`, `docs/api.md`, `docs/database.md`, `docs/testing.md`,
`docs/security-boundaries.md`, `docs/risk-register.md`, `docs/open-questions.md`, and
`README.md`; test `tests/unit/test_stage6_documentation.py`.

- [x] First write `tests/unit/test_stage6_documentation.py` with exact required file/command/status/
  boundary assertions; run it and observe missing-document failure.
- [x] Write documents that match actual commands, versions, blocked samples, parser degradation,
  cache-only limitation and no-model/no-Agent boundaries.
- [x] Re-run the documentation test plus CLI `--help` examples; expect pass.

## Task 36: Reflection round 1 and fixes

**Files:** create `docs/reflection/stage-6-round-1.md`; add regression tests and minimal fixes in
the exact affected files.

- [x] Review as RAG architect, citation researcher, database architect, security engineer,
  Tool/Agent/MCP architect and reliability engineer; record ID, role, severity, evidence, files,
  fix, blocker and status for every finding.
- [x] For each CRITICAL/HIGH finding, first add a focused failing regression and observe failure.
- [x] Implement the minimum fix and rerun the focused/related suites.
- [x] Require unresolved CRITICAL=0 and HIGH=0 before continuing.

## Task 37: Reflection round 2

**Files:** create `docs/reflection/stage-6-round-2.md`; add regression tests/fixes only for actual
findings.

- [x] Execute and record these 36 checks with named commands/evidence: (1) version cannot be
  overwritten, (2) old snapshot cannot acquire a new version, (3) PDF physical pages are exact,
  (4) HTML anchors/offsets verify, (5) chunks rebuild stably, (6) overlap is bounded, (7) citation
  re-verifies, (8) no fabricated citation exists, (9) future data is excluded, (10) unknown
  publication is excluded in strict mode, (11) Chinese lexical retrieval works, (12) English
  lexical retrieval works, (13) ordering is stable, (14) missing vector provider is BLOCKED,
  (15) hybrid lexical fallback is PARTIAL, (16) static vectors retain all test-only markers,
  (17) instruction-like text cannot change behavior, (18) HTML scripts never execute,
  (19) parsers cannot network, (20) Tools are read-only, (21) API is read-only, (22) CLI writes
  are explicit, (23) no model call exists, (24) no Agent exists, (25) no runtime Reflection
  pipeline exists, (26) no MCP Server exists, (27) no target price exists, (28) no trade exists,
  (29) migration upgrade/downgrade succeeds, (30) PostgreSQL integration passes, (31) Industrial
  FII body acceptance is honestly BLOCKED, (32) Micron body acceptance is honestly BLOCKED,
  (33) all old tests pass, (34) default tests have zero skips/warnings, (35) collection has no
  mass duplicate/value-free tests, and (36) documentation matches code.
- [x] Reproduce each new defect with a failing test before fixing it.
- [x] Require unresolved CRITICAL=0 and HIGH=0.

## Task 38: Full migration, PostgreSQL and quality acceptance

**Files:** create `docs/stage-6-implementation-report.md`; modify no implementation unless a new
failing regression first demonstrates a defect.

- [x] Run development and isolated test migration cycle:
  `current -> upgrade head -> downgrade -1 -> upgrade head -> current`; require final `0005` and
  all Stage 2–5 tables preserved.
- [x] Run the complete PostgreSQL integration, Tool/API/CLI and synthetic fixture acceptance; run
  explicit Industrial FII/Micron evidence checks and require honest `BLOCKED` while bodies are
  absent.
- [x] Run `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src`, and `uv run pytest -W error`; require exit zero, zero default skips and zero
  warnings.
- [x] Run collection/test-quality audit for duplicate node IDs, empty assertions, self-generated
  expected values, meaningless parameter products, unexplained skips, weakened mypy and permanent
  production ignores.
- [x] Write the 48-section report with separate Parser, retrieval architecture, Citation,
  synthetic-fixture and both real-company-body outcomes. Use `CONDITIONAL GO` while compliant
  company bodies and production embeddings are absent unless actual evidence requires `NO-GO`.
- [x] Confirm clean Stage 6-only Git scope, remain on `stage-6/rag-citations`, do not merge, and
  present the four user finish options.

## Plan self-review record

- [x] Prompt coverage: all 38 required component/validation areas map to a numbered task.
- [x] Approved design coverage: identity, exact versions, body snapshot links, parser limits,
  chunk/citation/tokenizer/postings/vector/hybrid/cache-only boundaries are explicit.
- [x] Interface consistency: the catalog defines every cross-task protocol and service name before
  use; later tasks use the same signatures.
- [x] Model/migration consistency: the fourteen table names match the approved design and Task 26
  precedes migration/repository integration.
- [x] Dependency order: schemas/ports precede services, pure domains precede persistence, and
  persistence precedes Tool/API/CLI.
- [x] Every production behavior has an explicit RED command, expected missing behavior, minimal
  implementation step and GREEN rerun.
- [x] Real versus synthetic evidence is separated; no company result is fabricated.
- [x] Scope check: no pgvector, model, Agent, runtime Reflection, MCP, report generation,
  recommendation, frontend, broker, trade or Stage 7 implementation task exists.
- [x] Placeholder scan: no incomplete implementation marker or vague test instruction remains.
