# Current Status & Roadmap

## Status Summary

本项目当前是 **Development Preview**，不是 Production Ready。

| 范围 | 状态 | 当前事实 |
|---|---|---|
| Engineering source baseline | `main` at `059a6ef` | Stage 1–9、Stage 10 Gate A，以及部分 Gate B engineering 的已审核源文件树。 |
| Public history baseline | `main` at `a113bcba` | 独立的 sanitized public history；不包含 Engineering commit history。 |
| Public update branch | `public-update/stage-10-gate-a-sync` | 本地、未提交、未推送的公开候选。 |

提交短 ID 记录的是本次 GitHub 发布准备时的审计证据；后续提交不会改变这里描述的阶段
结论，但公开前应再次核对分支 tip。

## Completed

### Stage 1–2 — Feasibility and Backend Foundation

- 项目边界、数据源风险和工程可行性；
- Python 3.12、uv、FastAPI、PostgreSQL 17、SQLAlchemy、Alembic；
- 配置、日志、CLI、API、Docker/本地数据库合同和测试基线。

### Stage 3 — Security Master

- Market、Exchange、Issuer、Security、Identifier 与 Alias；
- A 股/美股确定性证券解析；
- versioned seed、PostgreSQL Repository、API 与 CLI。

### Stage 4 — Data Access and Snapshot

- Provider/Repository/HTTP 边界；
- approved offline Fixture ingestion；
- point-in-time immutable Snapshot；
- read-only Data Tools 和 GET API。

### Stage 5 — Financial Normalization

- Canonical Concept、Provider Mapping、Normalized Fact 与 Period；
- A 股累计拆分、美股非自然财年、TTM、Formula Registry；
- Derived Metric、Calculation Run 和 Lineage。

### Stage 6 — RAG and Verifiable Citation

- Document Version、bounded parser、Chunk、Lexical Retrieval；
- Retrieval Run、Citation validation、Evidence Bundle；
- Fixture/真实公司证据隔离；Production Embedding 仍被阻止。

### Stage 7 — Controlled Agent Orchestration

- deterministic Planner、finite DAG、Tool Catalog、Policy 和 Budget；
- Research Run、Step、Tool Call、Evidence、Claim、Conflict；
- sealed Research Package 和 honest degradation。

### Stage 8 — Verifiable Report and Runtime Reflection

- ReportInputManifest、canonical JSON、deterministic Markdown；
- Claim/Evidence/Citation/Lineage bindings；
- bounded Reflection、one Revision、internal Release Gate。

### Stage 9 — Production Data Provider Governance

状态：**Completed / Conditional Go**。

Git 证据和阶段文档显示：

- Task 0–76，合计 77/77，全部完成；
- 两轮 Reflection、CRITICAL/HIGH remediation、Implementation Report 完成；
- Ruff、format、mypy、pytest 和 PostgreSQL migration replay 形成验收证据；
- Stage 9 文件树已通过聚合式提交进入 `main`；
- Stage 9 独立分支仍保留完整逐任务历史。

完成的是离线 Provider 治理工程，不是 Live 数据授权。`CONDITIONAL GO` 不得改写为
`Production Ready`。

## Stage 10 Acceptance and Work in Progress

### Stage 10 — Controlled Live Evidence

Stage 10 Offline Production Acceptance 与 Gate A 已完成；Gate B engineering 已开始，
但只达到部分实现的 active engineering baseline。整个项目仍不是 Production Ready。

已实现并提交/保存的方向包括：

- finite Live Authorization、消费、预算、过期、撤销与 scope 保护；
- Manual Evidence request/declaration/validation/review/quarantine/file safety；
- Evidence Manifest、Document admission、Snapshot binding 与显式离线 pipeline；
- Agent/Report 现有边界复用；
- retention、incident、read-only Tool/API、CLI；
- PostgreSQL models、migration、integration/security/offline tests；
- Reflection Round 1 及 CRITICAL/HIGH remediation。

当前结论：

- Stage 10 Offline Production Acceptance：**Complete**；
- Gate A：**Complete / `GATE_A_COMPLETE`**；
- Gate B Engineering：**Partially Implemented / Active Engineering Baseline**；
- Gate B Readiness：**`NO_GO`**；
- Production Authorization：**`NOT AUTHORIZED`**；
- Production Live Execution：**`NOT EXECUTED`**；
- SEC Production Pilot：**Not complete / `NOT_EXECUTED`**；
- Stage 11：**`NOT STARTED`**。

不得写 `Gate B Complete`、`Production Ready` 或 `Live Evidence Complete`。

## Current Provider Blockers

- **SEC Live authorization:** offline contracts are implemented; formal production Live
  validation remains `NOT_ATTEMPTED`.
- **Tushare production licensing:** production access remains `BLOCKED`; no real Token was
  read or approved.
- **A-share official disclosure bodies:** approved access, full-text storage, excerpt,
  commercial-use and redistribution boundaries remain unresolved.
- **Licensed U.S. EOD:** no approved vendor, contract, endpoint or entitlement.
- **Production Embedding:** no approved production model/version/license/cache policy.
- **Production Narrative Provider:** not configured.
- **Production Reflection Model Provider:** not configured; stable Reflection is deterministic.

## Research Limitations

- Industrial FII and Micron still lack sufficient verified body/numeric evidence for a fully
  supported real-company research report.
- SEC metadata is not filing body evidence.
- Synthetic Fixture success is not Live success or company evidence.
- Provider Cache is not Evidence.
- `PUBLISHABLE` is an internal engineering decision only.
- There is no brokerage execution, automatic trading, target price or investment rating.

## Planned Next Work

开发恢复后，按以下顺序处理：

1. 解决 Gate B readiness review 中仍开放的阻塞项；
2. 重新运行 offline quality、migration 与 readiness evidence；
3. 对 SEC production pilot 单独披露有限范围并获取精确授权；
4. 对每个 Live Provider 独立完成许可、Credential Reference、范围和预算审批；
5. Gate B 未获得 GO 前不执行 Production Live；
6. Stage 11 继续保持未开始。

不提供虚假完成时间，也不因公开 GitHub 而把 WIP 合入稳定分支。

## Recommended GitHub Branch Strategy

- `main`：GitHub 默认分支，只接收审核通过的 sanitized public candidate；
- 内部 Engineering 分支与完整开发历史不导入 Public Repository；
- `public-update/stage-10-gate-a-sync`：仅用于本轮本地人工审阅，不在 Phase 1 推送。

任何 WIP 分支都不应为了仓库展示而自动合入 `main`。
