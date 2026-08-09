# Verifiable citations

A Citation Anchor binds one exact DocumentVersion and Parse Run, native Page/Section and Chunk, a
typed locator, bounded excerpt, excerpt checksum, canonical-text checksum, document checksum and
versioned parser/sanitizer/citation identifiers. It never binds only a logical document. Historical
citations are immutable when a source is revised, withdrawn or superseded.

The deterministic verifier checks exact Blob bytes/MIME/size/SHA-256, parse generation, locator
bounds, excerpt containment within the claimed page/section, Snapshot membership and strict as-of
eligibility. Page/Section use RESTRICT foreign keys and a lineage trigger prevents cross-generation
anchors. Results are VALID,
INVALID, STALE_REFERENCE, FUTURE_DATA, SOURCE_MISSING or PARSE_VERSION_MISMATCH; no confidence
score exists. Unknown published_at is invalid in strict history rather than substituted with
retrieved_at. Retrieval Hits require a Citation bound to the same Chunk, and only VALID citations
may enter evidence. Verification requires exactly one Snapshot or aware as-of scope. 不调用大模型 and document instructions
cannot alter verification or permissions.
