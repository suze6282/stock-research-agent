# Stage 10 Real-Company Research Runbook

Status: design runbook. Every command below is a future interface unless it is an
existing read-only verification command. No Live or real-file procedure has been
executed.

## 1. Non-negotiable stop conditions

Stop before network/file admission/Snapshot whenever any of these applies:

- Git baseline, default tests, PostgreSQL or Alembic is not clean/current;
- Provider, Capability, Policy, License, Credential Reference, Security, CIK,
  accession, form, path, budget or as-of scope is not exact;
- official access/license rules are stale, unclear or changed;
- the grant or execution approval is absent, expired, consumed, revoked,
  cancelled or checksum-mismatched;
- contact identity is unavailable after the authorized resolution gate;
- host/IP/redirect, request, byte, time, retry, rate or circuit gate fails;
- manual path/content/identity/source/license/period/future/synthetic validation
  fails;
- any evidence would modify historical data or mix Security/Snapshot/source scope;
- any CRITICAL or HIGH issue is unresolved.

Stopping is a valid `BLOCKED` or `NOT_ATTEMPTED` result. It is never converted to
PASS by a fixture, retry, waiver, model or manual database edit.

## 2. Gate A offline engineering runbook

After the user says `批准第10阶段设计并继续实现`, the implementation session must:

1. repeat the `main` Git, PostgreSQL, quality, pytest and Alembic baseline;
2. create an isolated Stage 10 branch, not implement on `main`;
3. create a precise checkbox implementation plan and self-check it;
4. implement the grant/event/consumption/approval domain using TDD;
5. implement manual quarantine/security/review using TDD;
6. implement source-neutral artifact/manifest binding without fake HTTP lineage;
7. implement Snapshot planning, real-company validation and read-only query APIs;
8. implement explicit CLI commands with Fake Transport only;
9. add PostgreSQL migration and upgrade/downgrade/re-upgrade tests;
10. add fully offline Agent/Report integration using non-company synthetic data;
11. run two development Reflection rounds and fix all CRITICAL/HIGH findings;
12. run `uv sync`, Ruff, format, mypy, default pytest and Alembic validation; and
13. publish a Gate A implementation report and stop.

Gate A must report Live as `NOT_ATTEMPTED`, Provider credentials as `NOT_READ`,
real manual imports as zero, and real-company downstream objects as zero.

## 3. Gate B authorization preparation

The offline command:

```text
stock-research live authorization-plan --provider SEC_EDGAR_PUBLIC_V1 \
  --security-id 40000000-0000-0000-0000-000000000002 \
  --plan-checksum <exact-generated-checksum>
```

must resolve the persisted security/issuer/CIK, select one exact filing, expand
concrete Stage 9 endpoint paths and display every item in the 22-point disclosure
list from `docs/live-authorization-matrix.md`. It does not resolve contact identity,
DNS or open a socket.

The operator then re-reviews current official SEC rules. The review records exact
official source IDs, policy version/checksum, review time and rights decisions.
Unclear rules block the plan.

## 4. SEC limited Live approval

Only after Gate A passes and the concrete disclosure is shown may the user approve
that exact plan with:

`批准执行该SEC有限Live验证`

The approval is invalid if Provider, Security, CIK, Capability, filing, endpoint,
request/byte/time budget, retention, license or contact-reference status changes.
The system creates an immutable grant and a single-use execution approval; it does
not infer approval from the command line or conversation history.

## 5. SEC limited Live execution

Future explicit commands are separated:

```text
stock-research live authorization-activate --authorization-id <id> --approval-id <id>
stock-research live sec validate --authorization-id <id> --plan-id <id>
stock-research live sec run --authorization-id <id> --plan-id <id>
stock-research live sec show --run-id <id> --json
```

Execution sequence:

1. revalidate exact checksums, current time, status and remaining budgets;
2. resolve the approved contact reference inside the transport boundary;
3. acquire one submissions JSON resource;
4. validate CIK, form, accession, dates and primary filename;
5. acquire one filing index resource;
6. validate the exact primary document identity;
7. acquire one primary document with streaming bounds;
8. checksum and atomically persist original bytes;
9. commit attempts, Raw Artifacts, Manifests and checkpoint atomically where
   lineage requires it;
10. parse/chunk/Citation-verify offline;
11. record quality, Live validation status and final consumption; and
12. stop without Snapshot, Agent or Report.

At most one transient retry is allowed for the entire run. Permission, license,
identity, schema, future-data, blocked, not-found, invalid Citation and permanent
HTTP failures are not retried. No sleep/random retry masks an error.

## 6. SEC post-run acceptance

The pilot is `LIVE_VALIDATION_PASS` only if:

- every request belongs to the grant and budgets reconcile;
- artifact bytes, MIME, size and SHA-256 verify;
- manifest canonical checksum verifies;
- CIK/accession/form/period/filing dates match;
- body evidence is a primary document, not metadata/index alone;
- source publication/filing time does not exceed as-of;
- DocumentVersion and parse result are immutable;
- at least one Citation candidate passes the deterministic verifier;
- rights permit the performed storage/derived use; and
- no incident or unresolved CRITICAL/HIGH issue exists.

Partial parse, missing Citation readiness or incomplete evidence yields `PARTIAL`
or `BLOCKED`, never Live PASS. Success does not set production active.

## 7. Manual Industrial FII plan

The user must first place one legally obtained official file beneath the configured
manual inbox and supply its declaration. The plan command is local and read-only:

```text
stock-research evidence import-plan --security 601138.SH \
  --file <inbox-relative-file> --declaration <safe-local-declaration>
```

It resolves `601138.SH` to the persisted Security/issuer, validates the relative
path without reading beyond bounded metadata, displays source/license/retention
requirements and outputs a plan checksum. It does not fetch the declared URL.

The user must explicitly approve that exact file checksum/import plan before:

```text
stock-research evidence import --plan-id <id> --approval-id <id>
```

Approval for a filename does not cover replacement bytes.

## 8. Manual validation and review

Future commands remain separate:

```text
stock-research evidence validate --import-id <id>
stock-research evidence show --import-id <id> --json
stock-research evidence approve --import-id <id> --validation-checksum <checksum>
stock-research evidence reject --import-id <id> --reason-code <stable-code>
```

`approve` cannot waive malware, path, rights, identity, future-data or synthetic
blocks. An approved PDF/HTML continues through DocumentVersion parsing and Citation
verification. An approved structured export continues only through an explicitly
approved raw-fact schema/mapping. The workflow then stops before Snapshot.

## 9. Snapshot plan and creation

Only admitted immutable manifests can be selected:

```text
stock-research snapshot plan-from-ingestion --security-id <id> \
  --research-as-of-time <aware-UTC-time> --manifest-id <id> --json
stock-research snapshot create-from-ingestion --plan-id <id> \
  --plan-checksum <checksum> --json
```

The plan lists all DocumentVersion/raw fact IDs, mapping/formula versions, license
decisions, publication cutoff, quality/synthetic states and exclusions. Creation
rechecks them transactionally. It never defaults to the latest Snapshot, never
modifies an old Snapshot and never starts the Agent.

## 10. Research Agent Run

Only a sealed new Snapshot is eligible:

```text
stock-research research run-from-snapshot --snapshot-id <id> \
  --research-type <approved-type> --policy-version <exact-version> --json
```

The Stage 7 policy fixes Security, as-of, Snapshot, tool catalog and budgets. All
Tools remain read-only/offline. The run cannot call the Live subsystem or manual
inbox. Industrial FII or Micron evidence gaps yield `PARTIAL`/`BLOCKED`; synthetic
evidence cannot fill them.

## 11. Report generation

Only a sealed Research Package is eligible:

```text
stock-research report generate-from-package --package-id <id> \
  --report-policy-version <exact-version> --json
```

The existing Stage 8 flow creates a new immutable report version, deterministic
JSON/Markdown, two Reflection rounds with at most one revision and a Release Gate.
No command can force `PUBLISHABLE`, overwrite an old report, call a model, produce
a target price/rating or publish/send content.

## 12. End-to-end validation view

```text
stock-research validation show --validation-run-id <id> --json
```

The bounded view reports each stage separately: source authorization, intake,
artifact, manifest, document/fact, Citation, Snapshot, Agent Run, Package, Report
and Release Gate. It distinguishes `PASS`, `PARTIAL`, `BLOCKED`, `NOT_ATTEMPTED`
and `FAIL`; a downstream PASS cannot hide an upstream limitation.

## 13. Rollback and cleanup

### Live failure

- cancel/pause the Sync Run;
- revoke or consume the grant;
- open only the scoped circuit where policy requires;
- delete uncommitted temporary bytes;
- retain safe attempt/incident audit;
- do not advance checkpoint, admit manifest, create Snapshot, run Agent or report.

### Manual failure

- keep the request `QUARANTINED`, `REJECTED` or `BLOCKED` by derived state;
- delete temporary/unapproved bytes at the applicable deadline;
- retain only allowed audit metadata;
- do not admit document/facts or create downstream objects.

### Business correction

Create new Artifact/Manifest/DocumentVersion/Snapshot/Run/Report. Never update
history to make the failed/corrected record disappear.

## 14. Restricted-data deletion

1. open an `evidence_retention_action` bound to exact artifacts/manifests;
2. stop new use and identify affected downstream lineage;
3. remove raw bytes, cache and temporary copies;
4. verify absence without reproducing restricted content;
5. append deletion evidence and incident/validation impact;
6. mark future use blocked through new records;
7. notify the user when Snapshot/report reproducibility is impaired; and
8. require a new Snapshot/Run/Report if corrected evidence remains available.

Historical rows are not silently edited; the system must not claim complete
reproducibility after required byte deletion.

## 15. Incident response matrix

| Incident | Detection and automatic stop | Isolation/audit | Recovery and downstream action | User confirmation |
|---|---|---|---|---|
| Credential/contact exposure | redaction scanner or forbidden field/value pattern; revoke grant and stop transport | incident + affected attempts/log sinks | rotate/change reference outside app; verify logs; new grant | Required before any retry |
| Rate excess/provider block | meter/429/policy mismatch; stop retries, open scoped circuit | request attempts and consumption | re-review current rules; no budget reset | Required for new grant |
| Excessive download | byte meter or content-length bound; abort stream | partial temp object quarantined then removed | lower plan/choose one document | Required |
| Non-approved domain/SSRF/redirect | exact host/path and resolved-IP gate; no socket/follow | safe endpoint/IP class code only | correct policy/plan; never whitelist ad hoc | Required for changed scope |
| Corrupt artifact/checksum conflict | streamed and persisted checksum mismatch | quarantine both identities, do not manifest | reacquire only with new approved attempt or re-import bytes | Required if Live/new file |
| License/terms change | version/expiry/review gate | freeze affected artifacts and open incident | delete/restrict as required; reassess Snapshot/report | Required |
| Future data | published/filed/accepted time check | exclude record and bind quality issue | create a new later-as-of Snapshot if appropriate | Required for new Snapshot |
| Wrong Security/CIK/issuer | resolver/identifier/content mismatch | quarantine entire run/import | correct master data only through its governed workflow; new intake | Required |
| Forged source/malicious file | source review or content safety block | quarantine; no parser promotion | reject/delete, preserve safe audit | Required for any replacement |
| Wrong Snapshot | plan/checksum/security/as-of mismatch | block Agent/report | create a correct new Snapshot | Required |
| Agent evidence misuse | Evidence Ledger/Claim validator | terminal PARTIAL/BLOCKED and incident | new Agent Run after corrected Snapshot/policy | Required |
| Invalid report Citation | Citation verifier/Release Gate | non-publishable report retained | new report version from corrected package | Required for replacement/release |

Every incident records detection, stop condition, affected lineage, safe events,
remediation, whether a new Snapshot/Report is required and closure approval.

## 16. GET-only API operational boundary

Operators may query authorization, plan/run, import/validation, manifest, Snapshot
readiness and end-to-end status through bounded GET endpoints under `/api/v1`.
The API cannot activate/revoke grants, run Live, upload files, approve imports,
create Snapshot, run Agent or generate Report. It exposes no absolute path, blob
key, contact/credential detail, raw restricted body or SQL.

## 17. Default and Live test operations

Default verification remains:

```text
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run alembic current
```

Default pytest must make DNS/socket creation fail, avoid credential resolution and
exclude `tests_live`. Live tests run only as part of a separately approved Gate B
plan; without one, the external validation state is `NOT_ATTEMPTED/BLOCKED`, not a
skipped PASS.

## 18. Design self-check

The following design checks are complete:

- [x] Prompt coverage: route comparison, authorization, SEC, manual intake,
  evidence, Snapshot, Agent, Report, database, CLI/API, tests and incidents are
  specified.
- [x] Stage 1-9 compatibility: existing security, Provider, immutable evidence,
  Agent and Report contracts remain authoritative.
- [x] Historical immutability: corrections always append versions/events.
- [x] Provider Policy compatibility: the Stage 9 fixed gate order is preserved.
- [x] License gate: every use right is evaluated independently and fail-closed.
- [x] Credential isolation: references only; no design/Gate A value resolution.
- [x] Finite authorization: exact scope, time, request, byte, retry and document
  bounds plus atomic consumption.
- [x] Minimal SEC pilot: one company, one filing, three resources, no exhibits or
  backfill.
- [x] Manual source boundary: source types, declarations and human review are
  explicit.
- [x] File safety: path, MIME/magic, active content, bomb/size/depth and parser
  isolation are specified.
- [x] Raw Artifact: original bytes, checksum, source, license and retention remain
  immutable.
- [x] Manifest: exact artifact, parser/schema, source/review, temporal and checksum
  lineage is frozen.
- [x] Future Data: publication time is never replaced by retrieval time and late
  evidence is excluded.
- [x] Snapshot boundary: explicit new Snapshot only, no latest shortcut or Agent
  chaining.
- [x] Agent Tool boundary: persisted Snapshot only; all Tools remain read-only and
  offline.
- [x] Report version boundary: new immutable version and existing Release Gate.
- [x] Synthetic isolation: synthetic/fixture/unverified evidence cannot support a
  real-company Claim.
- [x] Trading/advice boundary: no broker, order, position, target, rating or advice.
- [x] Live-test isolation: not in default pytest/CI; absent grant is not a skipped
  PASS.
- [x] Stage 11 boundary: undefined and not entered.

Design-stage factual checks:

- [x] no Live request, DNS lookup or external socket was executed;
- [x] no Provider credential/contact value was read;
- [x] no Stage 10 branch, migration, dependency or production-code change exists;
- [x] no real file was imported;
- [x] no Snapshot, Agent Run or Report was created;
- [x] no Stage 11 work was performed.

## 19. Approval boundary

The next authorized phrase for Gate A implementation is:

`批准第10阶段设计并继续实现`

That phrase does not approve Gate B. After offline implementation and a concrete
SEC plan, Gate B still requires:

`批准执行该SEC有限Live验证`

A real Industrial FII import separately requires the file and explicit approval
of that exact import plan/checksum.
