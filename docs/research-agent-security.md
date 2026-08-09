# Research Agent security

The Agent is deny-by-default. Policy uses an exact allowlist, Tool Catalog
versions are immutable fingerprints, Tool calls are read-only and offline, and
the database is accessed through parameterized SQLAlchemy operations.

Controlled context rejects security, Snapshot, as-of, run, request, Policy, and
catalog overrides. It also rejects URL, path, SQL, shell, environment, provider,
model, and budget injection. Documents are untrusted Evidence and never
instructions.

Production provider factories are deterministic. OpenAI, Anthropic, Gemini, and
local model downloads are absent. `model_token_budget=0`, consumed model tokens
stay zero, and environment keys cannot auto-enable a model.

Additional boundaries: no investment recommendation, no target price, no
automatic trading, no MCP Server, no production model provider, and no implicit
network refresh.
