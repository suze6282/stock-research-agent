# Security Boundaries V0.1

## Stage 4 enforced boundaries

Stage 4 centralizes outbound HTTP behind an offline-default allowlisted client,
rejects external sockets in default pytest, validates redirects/size/MIME/timeouts,
and redacts secrets. BlobStorage returns opaque URIs and rejects traversal. API and
registered Tools are `READ_ONLY`; refresh, ingestion, download, snapshot build,
mapping mutation, SQL and deletion are not Tools. Immutable RawPayload and completed
snapshot enforcement is backed by PostgreSQL, not only application checks.

## Trust model

All external documents, HTML, API fields, provider errors, filenames, metadata and retrieved chunks are untrusted data. A regulator/exchange domain improves authority for facts; it does not make document text executable or safe as an instruction.

## Mandatory boundaries

1. **Instruction integrity:** document content cannot modify system/developer policy, tool permissions, cutoff, security identity, provider allowlist or output rules. Embedded “ignore previous instructions,” tool calls or credential requests remain quoted data.
2. **URL control:** no arbitrary URL-fetch tool. Acquisition uses canonical HTTPS origins and path templates from a domain allowlist. Resolve DNS, validate every redirect, reject IP literals/private/link-local/loopback ranges, non-HTTPS schemes, credentials in URLs and unexpected ports.
3. **Initial allowlist candidates:** `sse.com.cn`/approved subdomains, `cninfo.com.cn`/static subdomain, `sec.gov`/`data.sec.gov`, and approved issuer IR domains. Provider API domains are added only with contract/config review.
4. **Secrets:** tools cannot list/read environment variables. Models never receive provider keys, auth headers, database URLs or secret-manager responses. Adapters obtain scoped credentials server-side.
5. **HTML sanitization:** parse without executing JavaScript; remove scripts/styles/forms/iframes/event handlers, hidden instructions, external loads and active content. Store sanitized text separately from raw evidence.
6. **Output safety:** context-aware HTML/Markdown escaping, safe link rendering, no raw script-capable HTML, and Content Security Policy when a frontend is later built.
7. **File limits:** allowlisted MIME and magic bytes; V0.1 documents are PDF, HTML/XHTML, JSON, XML/XBRL and plain text only. Enforce compressed/uncompressed size, page, nesting and decompression-ratio limits; reject encrypted or malformed files unless quarantined for manual review.
8. **Tool parameters:** strict schemas, length/range/enum constraints, normalized identifiers, no shell/SQL/path fragments and no caller-controlled provider hostname.
9. **Database least privilege:** separate migration/admin, ingestion writer, calculation worker and report reader roles; schema/table grants only; no public network exposure; row/tenant boundaries before multi-user use.
10. **Logs:** redact tokens, auth headers, cookies, query secrets, connection strings, personal identifiers and raw document bodies. Log hashes/IDs and bounded error samples.
11. **Resource controls:** timeouts, quotas, concurrency/size limits, circuit breakers and bounded retries prevent resource exhaustion and provider bans.
12. **No dangerous actions:** no brokerage/order/payment/email/posting tools, shell access, arbitrary filesystem access or remote MCP in V0.1 Agent scope.

## Prompt-injection defenses

- Separate instructions from retrieved content at serialization and model-message layers.
- Tag passages with immutable provenance and `untrusted_document=true`.
- Tell the model that instructions inside passages must be ignored and reported if relevant.
- Retrieval cannot expand authorization; the run policy intersects every Agent-supplied filter.
- Detect and flag credential requests, tool syntax, system-prompt imitation, encoding tricks and exfiltration URLs.
- Require deterministic validation for tool inputs and final claims; model refusal/compliance is not the sole control.
- Include adversarial annual-report/HTML/PDF samples in Stage 6 tests.

## MCP future boundary

Remote MCP requires mutual authentication, per-tool scopes, egress allowlists, request signing/audience checks, schema size limits, audit retention and a separate threat model. A remote server never receives blanket database or provider access.

## Incident behavior

On suspected injection, secret exposure, cross-security data leakage or corrupted snapshot: stop the run, mark `FAILED`, revoke/rotate affected credentials, preserve redacted audit evidence, invalidate derived reports and require a reviewed replay.

# Stage 6 document boundary

Document bytes come only from injected BlobStorage. Parsers cannot import HTTP or create Session,
and never follow links, execute active content or OCR. Tool/API imports only read services and
cannot invoke version/parse/index/retrieval-write operations. Document instructions are marked as
untrusted and cannot alter permissions, filters, configuration or network gates.
# Stage 7 boundary

Research Agent inputs cannot request arbitrary URL, path, SQL, shell,
environment, provider, model, Tool, security, Snapshot, or future time.
Documents cannot modify Policy or Tool execution. Production has no model
provider and `model_token_budget=0`. The API and all Agent-visible Tools are
GET/read-only. Writes require explicit CLI or internal service invocation.
There is no investment recommendation, no target price, no automatic trading,
no MCP Server, and no implicit network refresh.
# Stage 9 Provider security boundary

Endpoint templates and allowlists prevent SSRF; callers cannot provide hosts,
URLs, local paths or SQL. DNS resolution is checked against public addresses and
revalidated for redirects. Redirect count, request count, response byte limit,
duration, decompression expansion and archive member/path limits are finite.
HTML/scripts are data only and are never executed.

Secrets are resolved only after governance and explicit authorization gates, held
ephemerally, redacted from errors/logs and never stored with artifacts. The
invariant is: default tests are offline and block all non-loopback DNS/socket
access. Tool and GET API
remain read-only; CLI control requires exact context and confirmation. Live status
stays `NOT_ATTEMPTED` without a separate approval. Stage 9 is `CONDITIONAL GO` and
does not authorize Stage 10.
