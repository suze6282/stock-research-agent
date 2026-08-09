# ADR-005: Three-Layer Bounded Reflection

- Status: Accepted for V0.1
- Date: 2026-07-11

## Decision

Reflection has three ordered layers:

1. **Deterministic rule validation:** schema, units, currency, periods, arithmetic, formula version, cutoff and required fields.
2. **Citation and evidence validation:** citation resolution, passage existence, entity/date match, entailment/support and conflicting evidence.
3. **Bear-case and assumption review:** challenge inference, scenarios, omitted contrary evidence and invalidation conditions.

At most two targeted correction rounds are allowed. Each finding points to affected section/fields. A round runs only if it has new evidence or a concrete failed check. Stop when all blocking checks pass, after round two, or when no new evidence exists. Unresolved required checks yield `PARTIAL` or failure, never endless rewriting.

## Consequences

Reflection is a quality gate, not an invitation for the model to repeatedly paraphrase itself. Deterministic failures cannot be waived by model confidence.
