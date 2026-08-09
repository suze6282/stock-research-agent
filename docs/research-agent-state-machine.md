# Research Run state machine

The non-terminal sequence is `CREATED → PLANNING → PLANNED → RUNNING`.
`RUNNING` may become `PAUSED`, `COMPLETED`, `PARTIAL`, `BLOCKED`, `FAILED`, or
`CANCELLED`; `PAUSED` may only resume to `RUNNING` or become `CANCELLED`.

Every transition appends a `ResearchRunEvent`. Terminal runs cannot return to a
mutable state. Policy, Snapshot, Plan, Tool invocation, observation, Evidence,
Claim, package, and historical events remain bound to the original run. A new
attempt creates a new run unless exact idempotency rules permit reuse.

Database trigger guards and the domain transition map enforce the same rules.
Pause/resume preserves consumed budgets and the original
`tool_catalog_version`.
