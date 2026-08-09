# ADR-004: Structured Data versus RAG

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

Canonical financial amounts, prices, shares, corporate actions, calendars, identifiers and calculations use **database + API/provider adapters + deterministic code**. Non-structured narrative material uses **RAG**.

Vector retrieval must never select or calculate canonical financial numbers. A number quoted from a filing passage is evidence, not the calculation record. The calculation engine consumes normalized structured facts and emits lineage. RAG consumes sanitized documents and emits passages/citations for business description, management explanation, risks, catalysts and evidence checks.

Where only a PDF is available, extracted tables enter a quarantine/reconciliation workflow and are not automatically promoted to canonical structured data.

## Consequences

- Calculation correctness is independently testable.
- RAG failures cannot silently alter valuation inputs.
- A-share structured-data access remains a real dependency rather than being “solved” by embeddings.
