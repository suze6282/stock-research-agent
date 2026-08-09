# Current Status & Roadmap

## Status Summary

本项目当前是 **Development Preview**，不是 Production Ready。

| 范围 | 状态 | 当前事实 |
|---|---|---|
| Stable baseline | `main` at `d6368d5` | Stage 1–9 稳定文件树；Stage 9 离线工程结论为 `CONDITIONAL GO`。 |
| Stage 9 branch | `stage-9/production-data-providers` at `74f3b23` | 独立开发历史保留；其文件树与 `main` 一致，但因 squash/聚合式合入而不是 `main` 的 ancestor。 |
| Stage 10 branch | `stage-10/controlled-live-evidence` | Started / Work in Progress / Development Paused；未合入 `main`。 |
| Stage 10 checkpoint | `db39858` | 本地 WIP 现场已保存；不代表完成或验收。 |

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

## Work in Progress / Development Paused

### Stage 10 — Controlled Live Evidence

Stage 10 已实际开始，不能写 `Not Started`。当前暂停在独立分支，未合入 `main`。

已实现并提交/保存的方向包括：

- finite Live Authorization、消费、预算、过期、撤销与 scope 保护；
- Manual Evidence request/declaration/validation/review/quarantine/file safety；
- Evidence Manifest、Document admission、Snapshot binding 与显式离线 pipeline；
- Agent/Report 现有边界复用；
- retention、incident、read-only Tool/API、CLI；
- PostgreSQL models、migration、integration/security/offline tests；
- Reflection Round 1 及 CRITICAL/HIGH remediation。

尚未完成：

- Task 78：Reflection Round 2；
- Task 79：Stage 10 Implementation Report 和相关文档验收；
- Task 80：Gate A full acceptance、全量命令证据与最终迁移循环；
- Gate B：真实受控 Live Provider 验证。

因此 Stage 10 当前只能写：

> **Started / Work in Progress / Development Paused**

不得写 `Stage 10 Complete`、`GATE_A_COMPLETE`、`Production Ready` 或 `Live Evidence
Complete`。

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

1. 在 `stage-10/controlled-live-evidence` 上重新确认 clean checkpoint 和计划；
2. 完成 Task 78 Reflection Round 2；
3. 完成 Task 79 Implementation Report 和状态文档；
4. 完成 Task 80 全量 Ruff/format/mypy/pytest 与 PostgreSQL migration acceptance；
5. 根据正式证据决定 Stage 10 Gate A 结论；
6. 由用户单独决定是否合入 `main`；
7. 对每个 Live Provider 进行独立授权、许可和有限预算审批。

不提供虚假完成时间，也不因公开 GitHub 而把 WIP 合入稳定分支。

## Recommended GitHub Branch Strategy

- `main`：GitHub 默认分支，展示 Stage 1–9 稳定基线；
- `stage-9/production-data-providers`：可选公开，保留 Stage 9 逐任务开发历史；
- `stage-10/controlled-live-evidence`：明确标记 WIP/paused，可选公开；
- `docs/github-publication-prep`：仅用于人工审阅 GitHub 文档差异，不应替代 `main`。

任何 WIP 分支都不应为了仓库展示而自动合入 `main`。
