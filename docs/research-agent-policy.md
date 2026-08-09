# Research Policy

`controlled-offline-v1` is immutable and uses an exact Tool allowlist. Tool
names are matched exactly; prefix matching is forbidden. A future Tool is
unavailable until a new Policy version explicitly allows its exact name and
version.

Hard limits are: at most 12 steps, 24 Tool calls, 5 calls per Tool, one retry
per step, 120 seconds, and `model_token_budget=0`. Consumption is cumulative
across pause/resume and cannot be reset by a Planner or document.

The Policy requires an explicit COMPLETE Snapshot and UTC
`research_as_of_time`. It rejects future Evidence and synthetic Evidence in
real-company research. Budget exhaustion returns `PARTIAL` or `BLOCKED`; it
never creates a child run to bypass limits.

Default production Tools are `READ_ONLY`, `writes=false`, and
`requires_network=false`. There is no implicit network refresh.
