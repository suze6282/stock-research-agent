# Reflection Design V0.1

## State machine

```text
draft report
→ deterministic checks
→ citation resolution and support checks
→ contrary-evidence/conflict/time/assumption review
→ targeted correction (if actionable)
→ final validation
→ FINAL or PARTIAL/FAILED
```

## Layer 1 — deterministic validation

Validate schema, required modules, claim class, cutoff, security identity, currency/unit, report period, cumulative/discrete-quarter logic, TTM completeness, Decimal result replay, share basis, valuation bridge, formula version and missing-value policy. A deterministic failure cannot be overridden by model prose.

## Layer 2 — citation and evidence validation

For each `FACT` and material `INFERENCE`, resolve citation IDs, verify document hash/location, security, publication time and passage existence. Check whether the passage entails the factual payload, merely provides context, or conflicts. Numbers in prose are reconciled to structured calculation outputs when applicable.

## Layer 3 — contrary case and assumptions

Search specifically for contradictory disclosures, downside drivers and conditions that falsify the thesis. Review whether scenarios disclose their assumption author/source, horizon, formula and sensitivity. Challenge causal language, omitted uncertainty and stale data. The reviewer cannot add unsourced “facts.”

## Correction and stop rules

- Findings have severity, rule ID, affected JSON pointer/section, evidence and prescribed correction scope.
- Only failed fields/sections are regenerated; deterministic calculations are rerun rather than edited by text.
- Maximum two correction rounds.
- A second round requires a remaining concrete failure or newly retrieved eligible evidence.
- If no new evidence exists, do not repeatedly rewrite.
- Stop immediately when all required gates pass.
- Stop after round two even if issues remain; output `PARTIAL` with unresolved findings, or `FAILED` when identity/cutoff/calculation integrity is compromised.

## Final statuses

- `FINAL`: all blocking checks pass; warnings may remain.
- `PARTIAL`: useful evidence exists but one or more required modules/claims cannot be supported; core conclusion is narrowed.
- `FAILED`: wrong/ambiguous security, future-data contamination, unreplayable key calculation, corrupted snapshot or unsafe tool behavior.

## Audit output

`ReflectionResult` records rounds, checks, findings, evidence, changed fields, before/after hashes, model/prompt versions, deterministic validator version, stop reason and final status.

## Required tests later

Unsupported citation, citation-to-wrong-company, future document, unit mismatch, parent/total mix, stale price, negative PE/PB handling, omitted contrary evidence, injection text, no-new-evidence stop, two-round ceiling, targeted-change diff and PARTIAL fallback.
