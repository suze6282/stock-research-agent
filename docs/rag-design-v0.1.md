# RAG Design V0.1

## Pipeline

```text
file acquisition
→ content-hash deduplication
→ malware/type/size checks
→ parsing and sanitization
→ section recognition
→ semantic chunking
→ keyword index
→ vector index
→ metadata filtering
→ hybrid retrieval
→ reranking
→ citation construction
```

RAG is for narrative evidence. It cannot calculate canonical financial facts.

## Document and chunk identity

A document record contains `document_id`, `security_id`, issuer, source/provider, source URL/accession, document type, form/report period, published/filed/amended time, retrieved time, language, MIME, byte size, SHA-256, parser version, sanitization version, page count/HTML anchors, supersedes relation and eligibility interval.

A chunk contains:

```text
chunk_id, document_id, security_id, issuer_id
document_type, form_type, report_period_start/end
published_at, filed_at, retrieved_at
page_start/page_end or html_anchor_start/end
section_path, heading, chunk_ordinal
text, text_hash, language
parser_version, chunker_version, embedding_model_version
source_url, accession, warnings
```

## Filtering and retrieval

Mandatory filters are applied before retrieval:

- exact `security_id` and authorized issuer relation;
- allowed document types;
- `published_at/filed_at <= research_as_of_time`;
- requested date/report-period window;
- not superseded by an eligible correction unless historical version is explicitly requested.

Keyword retrieval supports codes, accounting terms and exact names. Vector retrieval supports semantic passages. Scores are normalized and fused, then a reranker considers query relevance, authority, recency within cutoff, section type and contradiction diversity. Reranking cannot bypass mandatory filters.

## Citation construction

- **PDF:** document hash + source URL + 1-based PDF page + section path + bounded quote offsets. Printed-page number is stored separately when detected.
- **HTML/Inline XBRL:** accession/source URL + stable element/heading/HTML anchor + normalized text offsets; DOM path is a fallback because it can drift.
- A citation resolves to the exact sanitized passage and preserves a hash for later integrity checks.
- OCR-derived text carries `ocr=true` and lower evidence confidence until visually checked.

## Updates and rebuilds

Content hash prevents duplicate documents. A new filing/correction creates a new document version and supersedes link. Parser, chunker or embedding changes create a new index generation; old generations remain addressable by report snapshot until retention rules permit deletion. Rebuild is blue/green: build, validate counts/citations/filters, then switch an alias.

## Untrusted-document and prompt-injection controls

- Treat every document string as data, never instructions.
- Strip scripts, styles, forms, event handlers, hidden text and external resource loads.
- The model receives passages inside explicit untrusted-data delimiters and a policy that forbids following embedded commands.
- Retrieval content cannot modify system/tool policy, select arbitrary tools, reveal secrets, alter cutoff/security filters or cause URL fetches.
- Flag phrases that attempt instruction override, credential requests, tool calls or data exfiltration; keep the text as evidence but quarantine it from instruction channels.
- Allowlisted acquisition domains and validated redirect targets only.

## Failure degradation

If vector search is unavailable, use filtered keyword retrieval plus citation checks. If parsing fails, fall back to official HTML/text or mark the document unavailable. If retrieval finds no supporting passage, the claim is `UNVERIFIED` and excluded from core conclusions. The system never fills an evidence gap from model memory.

## Acceptance tests for Stage 6

Entity/date filter leakage, future filing exclusion, corrected filing precedence, PDF page resolution, HTML anchor resolution, hybrid recall set, reranker diversity, prompt-injection corpus, malicious HTML sanitization, parser-version rebuild and no-result degradation.
