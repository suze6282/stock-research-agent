# ADR-006: Defer Production MCP until Tools Mature

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

V0.1 does not implement a production MCP Server. Internal tools must nevertheless have explicit JSON-compatible schemas, semantic versions, independent tests, narrow authorization, stable error contracts, audit logs and no direct database exposure. MCP later maps these proven contracts rather than defining business semantics prematurely.

Entry conditions for MCP include stable adapters for both sample securities, passing contract/security tests, finalized auth and network boundaries, tool allowlists, rate/cost controls, audit retention and a demonstrated consumer that benefits from MCP interoperability.

## Consequences

The project avoids two simultaneous uncertainties: unreliable data semantics and a remote tool protocol. Future Market Data, Financial Research and Filings RAG servers remain possible.
