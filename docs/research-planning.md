# Deterministic research planning

`DeterministicTemplatePlanner` selects one approved finite template for the
requested research type. Inputs include the normalized request, security,
Snapshot, `research_as_of_time`, Policy version, planner version, and
`tool_catalog_version`.

The output has stable step order, dependencies, exact Tool names and versions,
and a stable Plan checksum. The validator rejects cycles, self-dependencies,
unknown dependencies, duplicate keys, non-contiguous indexes, unapproved Tools,
and more than 20 steps.

`FULL_RESEARCH_PACKAGE` is only a composition of approved templates. Documents
and Tool results are untrusted data: they cannot add a step or rewrite a Plan.
