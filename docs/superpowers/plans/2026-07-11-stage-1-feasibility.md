# Stock Research Agent Stage 1 Feasibility Plan

> **For agentic workers:** This plan is executed inline in the current session. It is documentation-only and must not create production modules or enter Stage 2.

**Goal:** Determine whether the proposed A-share and U.S. equity research system has sufficiently clear scope, lawful/stable data paths, deterministic metric definitions, and architectural boundaries to proceed to backend scaffolding.

**Architecture:** Stage 1 produces evidence-backed decisions and read-only probes only. Official exchange, regulator, issuer, and vendor documentation is preferred; every unconfirmed entitlement or interface contract remains explicitly unverified.

**Tech Stack:** Markdown decision records, Python 3.12 standard-library read-only probes, optional `pdfplumber` for in-memory PDF inspection, Git read-only status checks.

## Global Constraints

- Validate only `601138.SH` and `MU`.
- Do not create production business modules, RAG, MCP servers, agents, frontend, trading, or brokerage integrations.
- Never record secret values or commit full provider responses.
- Use timeouts, a named User-Agent, low request frequency, and official sources first.
- Stop after Stage 1 and return `GO`, `CONDITIONAL GO`, or `NO-GO`.

## Tasks

- [x] Audit the repository, runtime, Docker availability, network, and configured key names.
- [x] Establish the evidence hierarchy and run minimal read-only public-source probes.
- [ ] Write product scope and data-source feasibility decisions.
- [ ] Define deterministic metrics, report modules, and fact classes.
- [ ] Record orchestration, snapshot, adapter, RAG, Reflection, MCP, price, and model boundaries.
- [ ] Record security, compliance, and deployment constraints.
- [ ] Perform the five-role round-one review and correct the documents.
- [ ] Perform the round-two consistency review and publish the risk/open-question registers.
- [ ] Verify required artifacts and issue the final readiness decision without entering Stage 2.
