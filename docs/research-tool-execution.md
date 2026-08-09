# Controlled Tool execution

Execution requires an exact Policy allowlist entry and matching catalog
contract. Every permitted Tool is `READ_ONLY`, `writes=false`, and
`requires_network=false`. Input and output schemas are validated, and the run
context fixes security, Snapshot, request, run, Policy, catalog, and
`research_as_of_time`.

URL, local path, SQL, shell, environment, provider, model, budget, and context
override fields are rejected. Output outside the bound security, Snapshot, run,
request, or as-of is rejected. No document instruction can alter permissions.

Only transient internal failures of idempotent reads may retry, at most once.
`BLOCKED`, invalid input, not found, permission denial, future data, invalid
Citation, missing Evidence, and schema errors do not retry. There is no sleep
or random retry and no implicit network refresh.
