# Stock Research Agent 项目说明书

## 1. 文档目的

本文档说明 Stock Research Agent 的产品定位、系统边界、领域模型、研究链、阶段状态、
工程门禁和当前限制。它面向维护者、工程师、AI Agent/AI 产品岗位面试官，以及后续继续
开发本项目的人员。

仓库的稳定默认基线是 `main`。Stage 10 仅存在于独立 WIP 分支，本文会明确区分稳定能力
和开发中能力。

## 2. 系统定位与边界

Stock Research Agent 是一个面向 A 股和美股的证据驱动股票研究后端。核心目标是让研究
输入、数据时点、工具调用、证据、结论和报告可追踪、可复现、可审计。

当前系统：

- 不连接券商，不执行订单，不自动交易；
- 不输出目标价、自动评级或收益承诺；
- 不在稳定运行时调用生产 Narrative/Reflection 模型；
- 不把 Synthetic Fixture、缓存或元数据冒充正式公司证据；
- 不把内部 `PUBLISHABLE` 状态解释为合规批准或投资建议。

## 3. 总体架构

```text
Research Request
        |
Security Master and Resolver
        |
Point-in-time Data Snapshot
        |
        +-----------------------+
        |                       |
Financial Facts            Documents
Normalization              Parsing / Versioning
Formula / Metrics          Retrieval / Citation
        |                       |
        +-----------+-----------+
                    |
Controlled Planner and Read-only Tool Catalog
                    |
Evidence Ledger -> Claims -> Claim-Evidence Validation
                    |
Sealed Research Package
                    |
Structured Verifiable Report
                    |
Runtime Reflection -> Deterministic Revision -> Release Gate
```

FastAPI 和注册 Tool 只暴露受限的持久化查询。显式 CLI/application 服务负责写入动作。
数据库集成基线是 PostgreSQL 17，禁止用 SQLite 代替迁移或 PostgreSQL 行为证明。

## 4. Domain Model

### 4.1 Security Master

Market、Exchange、Issuer、Security、Identifier、Alias 和 Provider Identifier 分层，避免
将字符串 ticker 当作唯一身份。Resolver 使用本地确定性规则处理交易所限定代码、别名、
歧义、失效标识和不支持输入。

### 4.2 Data Access 与 Snapshot

Provider 数据读取、Repository 和 Snapshot 以明确的 category、security、
`research_as_of_time` 和 provenance 运行。

Snapshot 关键规则：

- 完成或部分完成的 Snapshot 不可变；
- Future Data 不得进入更早研究时点；
- 新数据产生新记录或新 Snapshot，不覆盖历史；
- API/Tool 查询不隐式刷新、同步或选择“最新 Snapshot”。

### 4.3 Financial Normalization

财务领域包括 Raw Fact、Canonical Concept、Provider Mapping、Normalized Fact、Period、
Formula、Calculation Input、Calculation Run、Derived Metric 和 Lineage。

系统保留币种、单位、精度、期间和修订语义，支持 A 股累计期间拆分、美股非自然财年与
52/53 周财年边界、TTM 和版本化公式。缺失值不是零；`N/M`、`PARTIAL`、`BLOCKED`、
`ZERO` 等状态不可混用。

### 4.4 Document、Retrieval 与 RAG

Document Version 保存来源与版本身份，Parser 只处理已持久化字节；Chunk、Retrieval Run、
Citation 与 Evidence Bundle 形成可验证链。当前验证基线是 Lexical Retrieval。Vector 接口
可插拔，但 Production Embedding 被配置层强制阻止。

Metadata 不是正文；Synthetic Fixture 不是公司证据；Citation 必须指向有效 Document
Version，且研究时点不能使用未来文档。

### 4.5 Claim 与 Evidence

Evidence Ledger 记录 Agent 可使用的结构化或文档证据。Claim 通过 Claim-Evidence Link
绑定证据，并接受支持性、冲突、时点、Synthetic 和 Citation 有效性检查。证据不足时，
Claim 或 Research Package 必须降级。

## 5. Agent Harness

Stage 7 的 Agent Harness 包括：

- Research Request 与 Research Run；
- Deterministic Planner 与有限 DAG；
- 固定版本 Tool Catalog；
- Tool Policy、调用预算和模型 token 预算；
- Step、Tool Call、Event 与 Checkpoint；
- Evidence Ledger、Claim、Conflict；
- sealed Research Package。

当前 Planner 和 Claim Builder 是确定性实现，模型 token 预算为零。Agent-visible Tools
保持 `READ_ONLY`、`writes=false`、`requires_network=false`。Harness 不能读取凭据、同步
Provider、绕过 Snapshot 或在缺少 Evidence 时补造事实。

## 6. Report、Reflection 与 Release Gate

Stage 8 以不可变 Research Package 为输入，并创建 ReportInputManifest、Generation Run、
Report Version、Section、Block 以及 Claim/Evidence/Citation bindings。

- canonical JSON 是报告事实源；
- Markdown 是确定性投影；
- factual block 必须可追踪至有效 Evidence 或 Calculation Lineage；
- Runtime Reflection 最多两轮；
- Deterministic Revision 最多一轮，并采用保守、删减式修正；
- Release Gate 不能被 force flag 绕过。

`PUBLISHABLE` 只代表内部工程规则通过，不代表公开发布、分析师签字、监管批准或投资建议。

## 7. Provider Governance（Stage 9）

Stage 9 在 `main` 中以 `Completed / Conditional Go` 结束，完成 77/77 个离线工程任务。
核心层包括：

- Provider Definition、Capability、Policy 与 License Policy；
- secret-free Credential Reference；
- Configuration 与 finite Live Authorization gate；
- endpoint template、DNS/IP SSRF、redirect、streaming、MIME/charset 安全；
- Rate Limit、Retry、Circuit Breaker 与 license-aware Cache；
- Sync Request、Plan、Run、Checkpoint 与有限预算；
- immutable Raw Artifact、Ingestion Manifest 与 lineage；
- Data Quality、Dead Letter、Freshness、Health 与 Audit；
- read-only Tool/GET API 和显式 CLI control surface；
- SEC EDGAR 与 Tushare 的严格离线 Adapter/Fixture 合同。

Gate 顺序固定为：

```text
Definition -> Capability -> License -> Provider Policy -> Credential Reference
-> Configuration Validation -> Live Authorization -> Network
```

任一前置 gate 阻塞时，不得解析真实 Credential，也不得创建 DNS、socket 或 HTTP transport。

## 8. Provider 与数据边界

| Provider/能力 | 稳定状态 | 含义 |
|---|---|---|
| SEC EDGAR offline contracts | Implemented offline | 端点、计划、解析和最小 Fixture 已验证。 |
| SEC Live | Conditional / Not Attempted | 未完成正式生产验证，默认不执行。 |
| Tushare offline contracts | Implemented offline | 离线 schema/plan/parser 可测试。 |
| Tushare production access | Blocked | License、Credential 与生产授权未满足。 |
| SSE/SZSE/CNINFO disclosure bodies | Blocked | 自动访问、正文存储、商业使用和再分发边界未批准。 |
| Licensed U.S. EOD | Blocked / provider unselected | 尚无批准的供应商、合同和端点。 |
| Production Embedding | Blocked | 无批准模型、版本、许可和缓存策略。 |
| Production Narrative/Reflection model | Not configured | 当前稳定报告与 Reflection 为确定性工程实现。 |

Provider Cache 不是 Evidence；Raw Artifact 必须保留来源、checksum、时间、Synthetic 和
license decision；Fixture 必须明确 `SYNTHETIC_TEST_ONLY`、`NOT_COMPANY_EVIDENCE`、
`OFFLINE`、`NOT_LIVE`。

## 9. Stage 10：Controlled Live Evidence

Stage 10 已开始，但只存在于 `stage-10/controlled-live-evidence` WIP 分支，未合入 `main`。
当前实现包含有限 Live Authorization、单次消费/预算、Manual Evidence 安全导入、
Evidence Manifest 与 Snapshot 绑定、显式 Snapshot/Agent/Report pipeline、Retention、
Incident、read-only Tool/API、CLI、PostgreSQL models/migration 和离线安全测试。

当前事实：

- Task 0–77 已实现并保存 checkpoint；
- Round 1 的 CRITICAL/HIGH remediation 已完成；
- Task 78（Reflection Round 2）、Task 79（Implementation Report）和 Task 80（Gate A
  final acceptance）尚未完成；
- Gate B 与任何真实 Live Provider 执行仍为 `NOT_ATTEMPTED`；
- Stage 10 状态必须写为 `Work in Progress / Development Paused`，不能写 `Complete`。

## 10. PostgreSQL 与迁移

稳定 `main` 的 Alembic head 是 `0008_create_production_data_providers.py`；Stage 10 WIP
分支另有未合入 `main` 的 `0009_controlled_live_evidence.py`。

仓库使用 SQLAlchemy 2 typed mappings、命名约束、RESTRICT foreign keys、状态检查、索引和
不可变触发器。开发与测试数据库必须分离，测试数据库名以 `_test` 结尾。

常用迁移命令：

```powershell
uv run alembic current
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

回滚会改变数据库 Schema，只能在明确的开发/测试数据库执行。

## 11. API

应用入口是 `stock_research_agent.main:app`，默认前缀 `/api/v1`。稳定 `main` 注册 health、
securities、issuers、data、snapshots、financials、rag、research-agent、reports 和 providers
路由。业务路由均为 GET 查询；写操作不通过查询 API 隐式发生。

启动命令：

```powershell
uv run uvicorn stock_research_agent.main:app --host 127.0.0.1 --port 8000
```

## 12. CLI

`pyproject.toml` 定义：

```toml
stock-research = "stock_research_agent.cli:app"
```

稳定分组为 `securities`、`data`、`tools`、`financials`、`documents`、`rag`、`agent`、
`report`、`provider`。使用 `uv run stock-research --help` 和分组 `--help` 获取精确参数。

## 13. Testing 与工程门禁

```powershell
uv sync --frozen --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
```

默认 pytest 收集 `tests/`，阻止外部网络和真实 Credential 读取，同时允许隔离的 loopback
PostgreSQL。Live 测试必须显式、独立运行，`NOT_ATTEMPTED` 不能记录为 PASS。

测试总数随阶段变化；精确数量以当前命令输出为准。

## 14. Security 与公开数据边界

不得进入 Git 或日志：真实 Token/API Key/Cookie/Authorization、私钥、生产数据库连接串、
Credential 值、个人绝对路径、PostgreSQL 数据目录、Provider 响应缓存、运行 Blob、未授权
Raw Data 或完整受限文档。

`.env.example` 只允许变量名和明确的本地假值；真实 `.env` 被忽略。公开 Fixture 需要最小、
离线、来源/许可说明、Manifest 和 checksum。

## 15. 阶段状态

| Stage | 状态 |
|---|---|
| Stage 1–8 | Completed |
| Stage 9 — Production Data Provider Governance | Completed / Conditional Go; merged to `main` |
| Stage 10 — Controlled Live Evidence | Started / Work in Progress / Development Paused; not merged |

“Stage completed”表示该阶段工程验收完成，不表示所有外部数据源已经获得生产许可。

## 16. 当前限制与后续工作

恢复开发时应在 Stage 10 WIP 分支完成 Task 78–80、全量质量门禁和迁移循环，再决定是否合入
`main`。SEC/Tushare/A 股正文/U.S. EOD/Embedding/模型 Provider 的 Live 工作均需独立授权，
不能因上传 GitHub 而放宽边界。

## 17. License 与免责声明

本 Public Export 采用 `PROPRIETARY / NO OPEN-SOURCE LICENSE GRANTED`：公开可见仅供作品集、
研究与工程评估，不授予复制、修改、再分发、再许可或商业使用权。未来可由项目所有者另行
加入正式开源许可证。代码许可状态不能替代第三方金融数据许可。

This project is for research, engineering, and educational purposes. It does not
provide investment advice, brokerage execution, automated trading, or guaranteed
financial outcomes.
