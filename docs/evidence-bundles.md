# Evidence bundles and cache-only reads

An Evidence Bundle is a bounded immutable read model derived from a completed Retrieval Run, its
ordered Hits and VALID Citation Anchors. It exposes exact run/index/document/chunk/citation IDs,
cutoff, match reason and excerpts up to 1,000 characters. It excludes full body, raw payload,
local storage path, SQL, credentials, conclusions, target prices and recommendations.

Tool and GET API look up the canonical versioned request fingerprint. They never write, parse,
build an index, generate embeddings, refresh providers or access the network. If no compatible run
exists the stable response is BLOCKED with `RETRIEVAL_RUN_NOT_PRECOMPUTED`. This cache-only rule is
a deliberate Stage 6 limitation and can change only in a later authorized stage. Synthetic bundle
tests are SYNTHETIC_TEST_ONLY and NOT_COMPANY_EVIDENCE. 工业富联真实正文验收：BLOCKED；美光科技真实正文验收：BLOCKED。
