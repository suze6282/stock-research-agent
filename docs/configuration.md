# Configuration

Configuration is loaded by `Settings` from environment variables or a local
`.env` file. Environment names are case-insensitive. `.env` is ignored by Git;
`.env.example` contains local placeholders only and must not be used as a
production secret source.

## Supported settings

- `APP_NAME`: service name; default `stock-research-agent`.
- `APP_ENV`: `development`, `test`, or `production`.
- `APP_DEBUG`: boolean debug flag.
- `APP_HOST`: bind host.
- `APP_PORT`: bind port in the range 1–65535.
- `LOG_LEVEL`: application log level.
- `DATABASE_URL`: SQLAlchemy PostgreSQL or `postgresql+psycopg` URL.
- `DATABASE_ECHO`: boolean SQL logging flag; keep disabled around sensitive data.
- `API_PREFIX`: API route prefix; default `/api/v1`.
- `PROVIDER_NETWORK_ENABLED`: provider network gate; default `false` (offline).
- `PROVIDER_NETWORK_MODE`: explicit `OFFLINE` or `LIVE` mode; default `OFFLINE`.
  Enabling the provider network is invalid unless this is explicitly `LIVE`.
- `BLOB_STORAGE_ROOT`: absolute LocalBlobStorage root for durable RawPayload bytes;
  defaults below the current user's application-data directory and is redacted from
  configuration summaries.
- `PROVIDER_CONNECT_TIMEOUT_SECONDS`: positive finite connect timeout; default `5.0`.
- `PROVIDER_READ_TIMEOUT_SECONDS`: positive finite read/write timeout; default `15.0`.
- `PROVIDER_TOTAL_TIMEOUT_SECONDS`: positive finite total GET deadline; default `30.0`.
- `PROVIDER_MAX_RESPONSE_BYTES`: response cap in `1..52428800`; default `5242880`.
- `PROVIDER_MAX_REDIRECTS`: manual redirect limit in `0..5`; default `3`.
- `PROVIDER_MAX_ATTEMPTS`: per-target GET attempt limit in `1..3`; default `3`.
- `PROVIDER_RETRY_BASE_DELAY_SECONDS`: positive finite retry base delay; default `0.25`.
- `PROVIDER_RATE_LIMIT_PER_SECOND`: positive finite per-host request rate; default `1.0`.
- `PROVIDER_USER_AGENT`: 1–256 characters with no controls; default
  `stock-research-agent/0.1 (offline-default)`.
- `DOCUMENT_MAX_BYTES`: offline document byte cap; default and maximum `10000000`.
- `DOCUMENT_MAX_PDF_PAGES`: text-layer PDF page cap; default and maximum `500`.
- `DOCUMENT_MAX_CHARACTERS`: canonical text cap; default and maximum `5000000`.
- `RAG_QUERY_MAX_CHARACTERS`: deterministic retrieval query cap; maximum `256`.
- `RAG_MAX_RESULTS`: persisted retrieval result cap; maximum `20`.
- `RAG_PRODUCTION_EMBEDDING_ENABLED`: fixed `false` until a production provider is approved.

Production requires `DATABASE_URL`. Test database names must end in `_test`.
Configuration summaries redact database credentials and query values. Never put
production credentials in `.env.example`, Docker images, CI YAML, source code,
logs, or issue reports.

Provider network access remains disabled unless `PROVIDER_NETWORK_ENABLED` is
explicitly enabled. Provider adapters, not API, CLI, or Tool callers, own their
fixed endpoints and host allowlists.

For native local development, copy `.env.example` to `.env` and replace the
local-only password if your project-owned cluster uses a different value.

Docker Compose does not consume the native `DATABASE_URL`. Its API URL uses host
`db` and port 5432. When changing the development database password, set both
`POSTGRES_PASSWORD` and the complete `COMPOSE_DATABASE_URL` in the shell. Keep
the password URL-safe (`A-Z`, `a-z`, digits, `.`, `_`, `~`, or `-`), or
percent-encode reserved characters in `COMPOSE_DATABASE_URL`; the decoded value
must match `POSTGRES_PASSWORD`. These two Compose-only variables are not Settings
fields and therefore do not belong in `.env.example`. The defaults are explicit
local-development placeholders, never production credentials.

`STOCK_RESEARCH_ALEMBIC_CONFIG` is an operational CLI variable, not an
application Settings field. Non-editable deployments must set it to the
absolute path of their trusted `alembic.ini`; relative paths are rejected.
Repository checkouts use their own root file as a safe fallback and never search
the process's current working directory.
