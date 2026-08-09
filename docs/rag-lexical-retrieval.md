# Lexical retrieval

`tokenizer-v1` applies Unicode NFKC and Latin case folding, preserves financial mixed tokens,
emits bounded CJK whole runs and overlapping bigrams, and retains negation. It performs no
stemming, translation, fuzzy guessing or model call. Postings store exact token, chunk, TF,
positions and field. `lexical-rank-v1` uses Decimal BM25 with k1=1.2, b=0.75 and 12-decimal
quantization, then deterministic phrase/heading and locator tie-breaks.

Snapshot indexes include only linked versions. Strict as-of indexes require known published_at at
or before the exact cutoff; unknown and future publication are excluded. Queries are 1–256
characters, at most 64 tokens, default 10 results and hard maximum 20. LEXICAL can PASS when a
compatible persisted index exists. Tool/API cannot build it and不得隐式刷新; explicit CLI/internal
orchestration owns writes.
