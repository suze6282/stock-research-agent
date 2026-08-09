# Deterministic report templates

Templates are versioned data, selected only by exact `(report_type, locale,
template_version)`. The V1 registry has fixed Section rules, statement codes,
columns and placeholders. Unknown placeholders, attribute traversal,
expressions, scripts, URLs, filesystem paths, environment access, Shell and SQL
syntax are rejected.

`zh-CN` and `en-US` localize headings, status labels and fixed template text.
They do not translate company excerpts, legal text, official security names,
metric/formula codes or document-type codes. This is deterministic localization,
not machine translation.
