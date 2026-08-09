# Controlled Research Agent architecture

Stage 7 implements a finite, deterministic research coordinator. Production uses
`DeterministicTemplatePlanner` and `DeterministicClaimBuilder`; there is no
production model provider and `model_token_budget=0`.

Every run binds one security, one immutable Snapshot, one
`research_as_of_time`, one `controlled-offline-v1` Policy, one planner version,
and one `tool_catalog_version`. A Plan is a bounded DAG. Tool output cannot add
steps, increase budgets, replace the security or Snapshot, or change the as-of.

The architecture separates request preflight, planning, Tool authorization,
execution audit, Evidence admission, conflict detection, Claim validation,
package assembly, persistence, CLI writes, and GET-only API reads. Tool
execution is `READ_ONLY`, `writes=false`, and `requires_network=false`.

Current boundaries: no investment recommendation, no target price, no automatic
trading, no MCP Server, no production model provider, and no implicit network
refresh.

Real-company status:

- Industrial FII verified company body: BLOCKED
- Micron verified company body: BLOCKED
- Engineering acceptance may use `SYNTHETIC_TEST_ONLY`, but it is never company
  Evidence.

The Stage 7 conclusion is `CONDITIONAL GO`.
