# ADR-009: Model and Deterministic Calculation Boundary

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

Deterministic code owns identity rules, period selection, unit/currency normalization, cumulative-quarter conversion, TTM, corporate-action/share treatment, all ratios/valuation arithmetic, scenario formulas, cutoff checks and schema validation.

Valuation method selection is also bounded. Code evaluates method eligibility from available fields and declared company characteristics; the research layer supplies an evidence-backed rationale and explicit scenario assumptions. No method is universal. V0.1 may implement the smallest testable eligible template first, while the schema preserves PE, EV/EBITDA, EV/Revenue and PB candidates. EV/Revenue is a fallback/auxiliary method, not a permanent default.

For `601138.SH`, the recommended primary method is attributable/normalized-earnings PE with EV/EBITDA or EV/Revenue as auxiliary checks. For `MU`, normalized mid-cycle EV/EBITDA is preferred when EBITDA is deterministically available, with PB and EV/Revenue as auxiliary checks and PE only when current earnings are representative. Every growth, normalized driver and multiple remains `SCENARIO`.

The model may summarize evidence, explain computed results, compare supported arguments, identify catalysts/risks, propose explicitly labeled scenario assumptions and draft prose. It may not calculate canonical metrics, invent missing inputs, select future facts, convert currencies without a recorded rate, treat provider metrics as truth, or turn `INFERENCE`/`SCENARIO` into `FACT`.

Model outputs are untrusted proposals until validated. The model cannot silently choose a fallback method or manufacture a missing EBITDA/normalization input. Prompts and model identifiers are versioned; changing a model cannot change stored deterministic calculations.

## Consequences

Model quality affects explanation but not arithmetic truth. Reports can be reproduced even if the original model later becomes unavailable, subject to preserved narrative snapshots.
