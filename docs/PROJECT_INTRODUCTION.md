# Stock Research Agent 项目介绍书

## 项目定位

Stock Research Agent 是一个面向中国 A 股与美国股票研究的证据驱动、可审计
Agent 工程。它解决的不是“让模型直接评价一只股票”，而是如何让研究请求在明确
时点、受控工具、可验证证据和诚实降级的约束下形成可追溯报告。

项目当前适合作为 AI Agent、Agent Harness、RAG、金融数据工程和可验证报告的
工程作品。它不是已上线的实时投研产品，也不提供自动交易或投资建议。

## 为什么建设这个项目

普通股票聊天机器人常见的风险包括：

- 将不同时间的数据混在同一结论中，造成未来数据污染；
- 给出结论却无法定位财报、公告、计算或引用来源；
- 在数据缺失时补造数字或补全叙述；
- 重复调用工具、无限循环或越过数据权限边界；
- 将 Synthetic Fixture、元数据或缓存误当成真实公司证据；
- 报告文字与底层 Claim、Evidence、Citation 脱节；
- 忽略 Provider 许可、Credential、存储权和 Live 授权。

Stock Research Agent 将这些问题拆成可测试、可持久化、可审计的工程边界。

## Evidence-first 研究链

```text
Research Request
  -> Security Resolution
  -> As-of Snapshot
  -> Controlled Planner
  -> Read-only Tool Catalog
  -> Financial / Document / Retrieval Tools
  -> Evidence Ledger
  -> Claim and Claim-Evidence Validation
  -> Research Package
  -> Verifiable Report
  -> Runtime Reflection
  -> Deterministic Revision
  -> Internal Release Gate
```

事实性报告内容应尽可能形成以下反向追踪链：

```text
Report Block
  -> Claim
  -> Claim-Evidence Link
  -> Evidence
  -> Citation or Calculation Lineage
```

## Agent 设计思想

### 受控，而非无限自治

Agent Harness 使用确定性 Planner、有限 DAG、固定 Tool Catalog、Tool Policy、
预算、状态机和 Checkpoint。Agent 可见工具保持只读、`writes=false`、
`requires_network=false`。同步数据、解析文档、运行 Agent 和生成报告分别通过明确的
CLI/application 写入口执行，查询 API 不隐式触发这些动作。

### 时点正确性

研究必须绑定 `research_as_of_time`。不可变 Snapshot 和版本化记录防止后续公告、
修订数据或行情进入较早研究时点。

### 诚实降级

数据或授权不足时，系统返回 `PARTIAL`、`BLOCKED`、`NO_EVIDENCE` 或 `N/M`，
而不是生成看似完整的答案。

### 确定性与模型边界

当前稳定实现是 deterministic、model-free 的研究 Harness。Production Narrative、
Reflection Model 和 Embedding Provider 尚未接入，不能将接口或设计预留描述为已运行的
模型能力。

## 核心能力

### Security Master

Market、Exchange、Issuer、Security、Identifier 与 Alias 分层，支持一家企业多证券、
A 股/美股代码和别名解析，并对歧义与错误输入采取保守结果。

### 财务标准化

原始事实和标准化事实分离；支持 Canonical Concept、Provider Mapping、A 股累计期间
拆分、美股非自然财年、TTM、Formula Registry、Derived Metric、Decimal 精度以及
Calculation Lineage。

### 文档、RAG 与 Citation

Document Version、受限解析、Chunk、Lexical Retrieval、Retrieval Run、Citation 和
Evidence Bundle 形成可验证文档证据。Production Vector/Embedding 尚未启用。

### Controlled Agent Orchestration

Research Request、Plan、Step、Tool Call、Evidence、Claim、Conflict 和 Research Package
均有显式状态和持久化边界；缺少证据时不得补造事实。

### Verifiable Report 与 Reflection

Stage 8 以 ReportInputManifest 冻结输入，以结构化 JSON 为事实源，以 Markdown 为
确定性投影；Runtime Reflection 最多两轮，Deterministic Revision 最多一轮，Release
Gate 不能被强制绕过。

### Provider Governance

Stage 9 完成了离线工程治理：Definition、Capability、License、Credential Reference、
Configuration、Live Authorization、HTTP 安全、Rate Limit、Retry、Circuit Breaker、
Cache、Sync、Checkpoint、Raw Artifact、Manifest、Quality、Health、API、Tool 与 CLI。
阶段结论是 `CONDITIONAL GO`，不是 Live Provider 全面可用。

## 与普通 AI 股票机器人的区别

| 普通实现 | Stock Research Agent |
|---|---|
| Ticker 直接交给模型 | 先进行 Security Resolution |
| 使用“最新数据”但时点不透明 | 显式 As-of Snapshot |
| 结论无法追踪 | Claim、Evidence、Citation、Lineage 可追踪 |
| Tool 调用开放 | 固定 Catalog、预算、策略和状态机 |
| 数据不足仍输出完整分析 | PARTIAL/BLOCKED/NO_EVIDENCE |
| 测试数据与真实数据易混淆 | Synthetic/Offline/Live 显式隔离 |
| 文本即最终事实 | 结构化报告为事实源，Markdown 为投影 |
| “发布”语义模糊 | `PUBLISHABLE` 仅为内部工程门禁 |

## 当前真实状态

- **Stage 1–8：Completed。** 后端基础、Security Master、数据访问、财务标准化、
  RAG/Citation、Controlled Agent、Verifiable Report、Reflection 和 Release Gate 已完成
  阶段验收。
- **Stage 9：Completed / Conditional Go。** 77/77 个离线工程任务、两轮 Reflection、
  PostgreSQL 验证与实施报告已完成，并以等价文件树合入 `main`。SEC Live 仍为
  `CONDITIONAL / NOT_ATTEMPTED`，其他生产 Provider 仍可能 `BLOCKED`。
- **Stage 10：Started / Work in Progress / Development Paused。** 独立分支
  `stage-10/controlled-live-evidence` 已完成 Task 0–77 并保存 WIP checkpoint；Task
  78–80、最终实现报告和 Gate A 验收尚未完成，也未合入 `main`。

因此，项目不能描述为 `Production Ready`、`Live Data Fully Supported` 或完整覆盖 A 股与
美股生产数据。

## Portfolio 价值

本项目重点展示：

- Agent Harness 与受控工作流设计；
- Context、Evidence 与 State Engineering；
- RAG、Tool Use、Reflection 和可验证输出；
- 金融数据时点、期间、版本与 Lineage 建模；
- Provider 许可、凭证和网络边界；
- PostgreSQL 约束、迁移和真实集成测试；
- 对未完成能力和阻塞条件的诚实表达。

## 免责声明

This project is for research, engineering, and educational purposes. It does not
provide investment advice, brokerage execution, automated trading, or guaranteed
financial outcomes.

`PUBLISHABLE` 只表示内部确定性工程门禁通过，不代表公开发布、合规批准或投资建议。
