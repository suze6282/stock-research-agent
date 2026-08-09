# Open Questions by Blocking Class

## Stage 4 unresolved decisions

- Which licensed Live Provider and contract will cover A-share prices/actions?
- Which named, entitled U.S. EOD Provider will be approved for persistence and cache?
- What real SEC contact/User-Agent and Archive access policy will operations approve?
- What production BlobStorage retention, encryption and backup policy is required?
- Which exchange-calendar implementation may later supply trading sessions?

Until answered, the Live sources remain `BLOCKED`; Stage 4 fixture, snapshot and
read-only Tool behavior remains reproducible and offline.

## BLOCKS_STAGE_2

| ID | Question/decision | Why it blocks the engineering skeleton | Needed from |
|---|---|---|---|
| OQ-001 | What dedicated directory/repository will hold Stock Research Agent? | Current workspace is a dirty, unrelated portfolio repository. Stage 2 must not add backend scaffolding here without an explicit monorepo decision. | User |
| OQ-002 | What reproducible local development path will be used? | User PowerShell lacks usable Python and Git. Configure user-accessible pinned Python/Git. For PostgreSQL/services, either install/verify Docker or approve an explicit non-Docker alternative. | User + engineering |

Docker alone is not an unconditional blocker: a documented local PostgreSQL/service setup can replace it for Stage 2. Node is not required for the Python backend skeleton.

## BLOCKS_DATA_INTEGRATION

| ID | Question/decision | Required before | Needed from |
|---|---|---|---|
| OQ-003 | Which A-share structured provider/plan will be used, and does it permit the intended personal cache? | Stage 4 A-share adapter | User/provider |
| OQ-004 | Which licensed U.S. EOD/corporate-actions provider will be used? | Stage 4 U.S. market-data adapter | User/provider |
| OQ-005 | What real project email or URL will identify SEC traffic? | Live SEC Archive integration | User |
| OQ-006 | Can the final SEC User-Agent, chosen HTTP client and conservative rate/cache policy reproduce both the filing index and primary documents without intermittent 403? The current index result differs by client; documents remain 403. | SEC filing-document adapter acceptance | Engineering after OQ-005 |
| OQ-007 | What authorized artifact-retention period is allowed? | Persistent filing/object-store design | User/provider/legal |

These items do **not** block a provider-neutral Stage 2 skeleton. They do block claiming real data integration is complete.

## BLOCKS_PRODUCTION

| ID | Question/decision | Why it is production-only | Needed from |
|---|---|---|---|
| OQ-008 | Which deployment region and model provider are authorized? | Desktop reachability does not validate Tencent Cloud egress, OpenAI regional support, authentication, quota or model features. | User + architecture/compliance |
| OQ-009 | Do Tencent Cloud, SEC, A-share provider and U.S. provider work from the selected cloud region? | Requires provisioned target infrastructure and production-like credentials/network. | Engineering/operations |
| OQ-010 | Will the product remain personal or become public/paid/multi-user? | Public/commercial use triggers new market-data display/redistribution and securities-advice review. | User |
| OQ-011 | What production secret-management, backup, RPO/RTO and restore policy is approved? | These are deployment controls, not Stage 2 local scaffolding gates. | Operations/security |

Commercialization blocks public release and data licensing, not personal local engineering scaffolding.

## NON_BLOCKING

| ID | Question/decision | Deadline | Needed from |
|---|---|---|---|
| OQ-012 | Who authors/approves bear/base/bull assumptions? | Before Stage 7 | User/product |
| OQ-013 | Which industry sources are accepted for each sample company? | Before Stage 7 | Research lead |
| OQ-014 | Which embedding/vector provider will be used? | Before Stage 6 | Architecture/security |
| OQ-015 | Is Node needed before Stage 10 frontend work? | Stage 10 | Frontend engineering |
| OQ-016 | Which verified provider concepts/taxonomies and reviewer evidence may become the first production `APPROVED` mappings? | Before numeric Stage 5 sample qualification | User + accounting/data owner |
| OQ-017 | Which authorized numeric financial-fact source will supply reproducible 601138.SH and MU evidence without changing the accepted fixture history? | Before production metric validation | User/provider |
| OQ-018 | Should a later formula version reconcile reported gross profit before selecting the revenue-minus-cost path? | Before formula V0.2 | Research + accounting owner |
# Stage 6 deferred decisions

Future authorization must decide compliant company-body acquisition, a licensed production
EmbeddingProvider/vector backend, and whether a later stage may allow append-only retrieval writes
through another boundary. Stage 6 does not answer these by installing pgvector, downloading a
model, calling OpenAI, treating metadata as body, or weakening strict published-at filtering.
# Stage 7 deferred decisions

- Selection and authorization of any production PlannerProvider or
  ReasoningProvider requires a future explicit stage.
- Any change from GET/cache-only reads to API-triggered execution requires a
  future explicit stage.
- Verified Industrial FII and Micron company bodies and financial facts require
  separately approved acquisition.
- The scope of Stage 8 is not inferred here.

# Stage 8 deferred decisions

| ID | Question | Required before |
|---|---|---|
| OQ-801 | Which authorized production Narrative Provider, if any, may propose bounded blocks? | Enabling a production model |
| OQ-802 | Which authorized production Reflection Provider, if any, may propose findings? | Enabling model-assisted Reflection |
| OQ-803 | What analyst/compliance workflow follows internal PUBLISHABLE? | Any external publication |
| OQ-804 | Which verified filings and financial sources may support the two samples? | Complete real-company reports |
| OQ-805 | What is Stage 9 scope? | Any Stage 9 implementation |

These questions do not authorize provider/model activation, external
publication, real-company inference, or Stage 9 work.
