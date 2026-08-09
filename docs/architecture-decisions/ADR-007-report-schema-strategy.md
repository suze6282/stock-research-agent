# ADR-007: Modular Versioned Report Schemas

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

Use multiple small, versioned output schemas rather than one giant report object:

`SecurityIdentityOutput`, `DataSnapshotOutput`, `CompanyProfileOutput`, `FinancialAnalysisOutput`, `ValuationOutput`, `CatalystRiskOutput`, `ReflectionResult` and `FinalResearchReport`.

The final report composes module references and a rendered Markdown view. Every claim has a fact class, confidence band, source references, time and warnings. Missing is explicit `null + reason`, not omitted or fabricated. Backward-compatible additions increment minor schema version; breaking semantic changes increment major version.

## Consequences

Modules can fail or be revised independently, JSON stays machine-valid, and the final renderer does not become the source of truth.
