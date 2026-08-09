# Provider financial fact mapping

Normalization accepts only an exact, versioned `APPROVED` mapping. A rule is scoped
by provider, provider concept, taxonomy, statement type, form type, context and
dimensions. An approved rule must reference a canonical concept and carry a source
reference and reviewer. Valid states are `APPROVED`, `AMBIGUOUS`, `UNMAPPED`, and
`DEPRECATED`.

There is no fuzzy label match, spelling similarity, LLM decision, or automatic custom
taxonomy approval. Missing, conflicting, deprecated, or out-of-validity mappings keep
the raw Stage 4 fact intact and produce a warning; they do not create a canonical fact.
Mappings are versioned and old versions remain available for replay.

The V0.1 production seed intentionally contains no provider mappings because the
approved offline fixtures contain no numeric provider facts and there is no verified
source evidence for a mapping. Synthetic mappings exist only inside isolated tests and
are labeled as such. They are never written by the production seed.
