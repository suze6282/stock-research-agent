# ADR-001: Fixed Orchestration with Limited Tool Autonomy

- Status: Accepted for V0.1
- Date: 2026-07-11

## Context

Financial research must be reproducible and cannot depend on an Agent choosing a different sequence each run.

## Decision

Use **fixed program orchestration + limited autonomous Tool Use**. The program always performs identity resolution, cutoff creation, snapshot selection, structured-data validation, deterministic calculation, evidence retrieval, draft generation, three-layer Reflection and final validation in that order.

The Agent may choose among whitelisted read-only retrieval tools to fill an already-defined research section, refine a query or seek contrary evidence. It may not change `research_as_of_time`, select an unapproved provider, write canonical financial facts, calculate key metrics, skip required stages, invoke arbitrary URLs, access secrets or create orders.

## Consequences

- Replays and failure localization are possible.
- Tool outputs need typed schemas and provenance.
- Exploration is narrower but safer.
- Multi-Agent is not justified until the single fixed pipeline passes both samples.
