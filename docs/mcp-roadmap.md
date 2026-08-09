# MCP Roadmap

## Why V0.1 does not implement MCP

The immediate uncertainties are data entitlement, provider semantics, financial normalization and evidence quality. Adding a remote tool protocol before those contracts stabilize would make failures harder to isolate and could expose immature tools beyond their intended trust boundary. MCP is a connector standard, not a cure for incorrect data, RAG or calculations.

## MCP-compatible internal design now

- JSON-compatible, explicitly versioned input/output schemas.
- Narrow tools with independent contract/security tests.
- Stable typed errors, request IDs and audit events.
- Adapter/runtime owns credentials; model never receives them.
- No raw SQL/database/filesystem/environment tools.
- Idempotent reads and explicit write scopes.
- Domain and tool allowlists, rate/cost policies and per-caller authorization.

## Possible later servers

1. **Market Data MCP:** security master, calendars, daily close/history and corporate actions.
2. **Financial Research MCP:** versioned facts, normalized periods, calculations, valuations and snapshot lineage.
3. **Filings RAG MCP:** filing acquisition status, filtered retrieval and citation resolution.

Servers should be split by data sensitivity, provider entitlement and scaling profile, not merely by code folder.

## Authentication and authorization

Use workload identity or short-lived tokens, TLS, audience-bound credentials, per-tool scopes, tenant/user context if multi-user is later added, and deny by default. Secrets stay server-side in a secret manager. Remote MCP does not inherit database credentials.

## Whitelist, audit and versions

Each deployment declares an allowlist of tool name + major version + caller scope. Audit logs record authenticated caller, tool/version, normalized parameter hash, decision, provider, cost, latency, snapshot and result status with redaction. Breaking schema/semantic changes require a new major version and controlled deprecation.

## Remote MCP network/security risks

- prompt-injected tool calls and confused-deputy behavior;
- SSRF/arbitrary URL or redirect escape;
- credential forwarding/leakage;
- provider license violations by remote callers;
- cross-tenant data leakage;
- oversized payload/resource exhaustion;
- supply-chain/server impersonation;
- insufficient egress control and audit retention.

Mitigations include egress allowlists, signed/verified server configuration, schema size limits, timeouts, caller quotas, provenance, content sanitization and independent penetration/security review.

## Entry conditions for formal MCP work

- Both sample pipelines pass end to end on frozen snapshots.
- Internal tools have stable major versions and contract tests.
- Provider contracts permit the intended remote access/caching/display.
- Authentication, tool scopes, network topology and audit retention are approved.
- Threat model and SSRF/prompt-injection tests pass.
- A real external consumer demonstrates that MCP adds interoperability value.
- No unresolved `CRITICAL` security or data-lineage finding.
