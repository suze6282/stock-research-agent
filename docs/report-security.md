# Report security boundaries

Production report generation is offline and deterministic. Model Narrative and
Reflection providers are explicitly `BLOCKED`; API keys or environment values
cannot enable them. Scripted providers exist only under `tests/support`, are
`TEST_ONLY`, and are not production defaults. Model token budget and consumption
are always zero.

Renderer, Reflection, Revision, Gate, Tool and GET API cannot execute document
instructions, templates, expressions, HTML, scripts, URLs, SQL, Shell commands,
local paths, providers or models. They cannot refresh data or create Research,
Calculation, Retrieval, Snapshot, Claim, Evidence or Citation records.

Logs and responses must not contain full Packages, Markdown reports, full
documents, storage roots, database URLs, credentials, cookies, authorization
headers, stack traces or unbounded excerpts. Export is explicit, checksum
verified, confined to an approved root and refuses overwrite by default.
