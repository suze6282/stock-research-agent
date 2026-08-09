# Vector interface

EmbeddingProvider and VectorIndex are narrow injectable ports with immutable provider/model/version,
dimensions and input bounds. Requests cannot choose a key, model, URL or backend. Stage 6 installs
no pgvector, downloads no local embedding model and calls neither OpenAI nor another model.

The production default is `BlockedEmbeddingProvider`: VECTOR: BLOCKED with warning
`EMBEDDING_PROVIDER_NOT_CONFIGURED`. Fixed vectors exist only under tests and require
SYNTHETIC_TEST_ONLY, NOT_COMPANY_EVIDENCE, OFFLINE and NOT_LIVE. They verify port/filter/ranking
contracts only and are not semantic-quality evidence. No fixture vector is registered in the
production package or described as live. Adding production embeddings requires a later formally
authorized stage and cannot weaken document/citation/as-of rules.
