# Hybrid retrieval

Hybrid retrieval combines actual lexical and vector ranks with Decimal reciprocal-rank fusion.
Duplicate chunk IDs collapse, unavailable channel ranks and scores remain null, and ties use the
immutable locator checksum and chunk index. The stable reranker uses only exact phrase,
section-heading token count, fusion score, best actual channel rank and stable locator. It has no
randomness, popularity, recency boost or model.

With a compatible lexical index and no production embedding provider, HYBRID: PARTIAL and warns
`VECTOR_CHANNEL_BLOCKED`; it must not claim semantic validation. VECTOR remains BLOCKED. Search
Tool and GET API are cache-only and不得隐式刷新, parse, index, embed or network. A miss returns
`RETRIEVAL_RUN_NOT_PRECOMPUTED`; only an explicit CLI/internal write may create a Retrieval Run.
