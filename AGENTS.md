# Public Repository Guidelines

This file applies only to the sanitized, history-free portfolio export. It does not
authorize changes in the private development repository.

## Current release boundary

- Stage 1–8: Completed.
- Stage 9: Completed / Conditional Go on `stage-9/production-data-providers`; offline
  governance is complete, while Live authorization remains separate.
- Stage 10 Offline Production Acceptance and Stage 10 Gate A: Complete.
- Gate B engineering: Partially implemented / active engineering baseline.
- Gate B readiness: `NO_GO`; Production Authorization is `NOT AUTHORIZED` and
  Production Live Execution is `NOT EXECUTED`.
- Stage 11: `NOT STARTED`.
- Do not continue Stage 9 or Stage 10 feature work during public-release preparation.
- Do not implement directly on `main`.

Public sanitization may change documentation, Synthetic Fixture assets, Fixture-only
allowlists, and publication configuration. It must not change Agent behavior, production
Provider behavior, database Schema, or trading capabilities.

## Public Fixture boundary

Public Fixtures must be project-authored and marked `SYNTHETIC_TEST_ONLY`,
`NOT_COMPANY_EVIDENCE`, `NOT_PROVIDER_DATA`, `OFFLINE`, and `NOT_LIVE`. They are for
parser, checksum, Manifest, Provider contract, as-of, and deterministic-report tests.
They must never be presented as Industrial FII, Micron, or any other company evidence.

No real SEC response, SSE/Nasdaq market-data crop, Provider Raw Artifact, credential,
cookie, or licensed dataset may be added. Citation evidence must be `VALID` before a
claim is treated as supported.

## Runtime and security boundary

- API and registered Research Run query Tools are strictly read-only.
- Read tools declare `READ_ONLY`, `writes=false`, and `requires_network=false`.
- Default tests are offline and may use only an isolated loopback PostgreSQL instance.
- Do not read real Provider credentials, execute Live Provider requests, create a
  production Snapshot, run an Agent against Live data, or generate a production Report.
- Public Provider validation remains `NOT_ATTEMPTED` unless a separate approved process
  records otherwise.
- 不得读取真实Provider凭证；不得创建Snapshot；不得运行Agent；不得生成Report。
- A future SEC production pilot requires the exact separate approval phrase
  `批准执行该SEC有限Live验证`; it is not granted by public-export work.
- There is no model-backed investment recommendation, no target price, no automatic trading,
  and no broker execution.
- `PUBLISHABLE` is an internal engineering gate, not investment advice or public-release
  authorization.

## Historical design references

### Stage 8

The preserved Stage 8 design references are
`stage-8/verifiable-report-reflection`,
`stage-8-verifiable-report-reflection-design.md`, and
`stage-8-verifiable-report-reflection.md`. That stage introduced
`ReportInputManifest`, `DeterministicReportRenderer`, JSON and Markdown output,
Claim-Evidence Link validation, Reflection最多2轮, Revision最多1轮, and the internal
PUBLISHABLE gate (`internal PUBLISHABLE`). Its historical boundary stated `不得进入第9阶段`.

### Stage 9

The preserved Stage 9 references are
`stage-9/production-data-providers`,
`stage-9-production-data-provider-design.md` and
`stage-9-production-data-providers.md`. Its governance sequence included
Definition → Capability → License → Provider Policy,
Credential Reference → Configuration Validation, and
Live Authorization → Network. The original plan allowed
`批准执行该Provider的有限Live验证` only after the gates passed and stated
`不得进入第10阶段`. These are historical design constraints, not claims that Stage 10
was never started.

## Earlier stage exclusions

Stage 4 did not implement 财务标准化、财务指标、TTM、估值、RAG、Agent、MCP or 自动交易.
Those historical exclusions must not be used to deny the later completed stages.
