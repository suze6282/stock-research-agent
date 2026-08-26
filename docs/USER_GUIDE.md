# Stock Research Agent 使用说明书

## 1. 适用范围

本文对应 sanitized public engineering candidate：Stage 1–9 已完成工程验收，Stage 9
结论为 `CONDITIONAL GO`；Stage 10 Offline Production Acceptance 和 Gate A 已完成，
Gate B engineering 仅部分实现且 readiness 为 `NO_GO`。

当前适合本地工程运行、离线 Fixture 工作流、PostgreSQL 迁移、测试、RAG/Agent/Report
架构验证。它不是实时投资产品或自动交易系统。

## 2. 环境要求

- Python `>=3.12,<3.13`（开发基线 3.12.13）；
- uv；
- PostgreSQL 17（阶段验收使用过 17.10）；
- Git；
- Windows PowerShell（使用仓库自带数据库脚本时）。

依赖版本以 `pyproject.toml` 和 `uv.lock` 为准。Docker 是可选方案；Windows 本地脚本不会
控制系统 PostgreSQL 服务，只管理项目自己的 cluster。

## 3. 安装

```powershell
git clone <repository-url>
Set-Location stock-research-agent
uv sync --frozen --all-groups
```

若锁文件与 `pyproject.toml` 不一致，`--frozen` 会失败并如实暴露问题，而不会改写锁文件。

## 4. 环境变量

```powershell
Copy-Item .env.example .env
```

编辑本地 `.env`：

- 为 `DATABASE_URL` 选择仅用于本地开发的密码；
- 将 `BLOB_STORAGE_ROOT` 改为本机绝对、非根目录路径；
- 保持 `PROVIDER_NETWORK_ENABLED=false` 和 `PROVIDER_NETWORK_MODE=OFFLINE`；
- 不要填写未经批准的真实 Provider Credential。

完整测试使用独立变量：

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://stock_user:<local-test-password>@127.0.0.1:55432/stock_research_test"
```

开发库和测试库必须不同，测试数据库名必须以 `_test` 结尾。真实 `.env`、Token、Cookie、
Authorization、私钥和生产连接串不得进入 Git。

## 5. 启动本地 PostgreSQL

仓库包含：

- `scripts/dev/start-postgres.ps1`
- `scripts/dev/stop-postgres.ps1`

启动项目自有 PostgreSQL 17 cluster：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev\start-postgres.ps1
Test-NetConnection 127.0.0.1 -Port 55432
```

脚本要求 PostgreSQL 17 binaries 可用，并拒绝操作项目自有目录之外的 cluster。首次初始化
和数据库说明见 [database.md](database.md)。

停止时：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev\stop-postgres.ps1
```

不要删除 PostgreSQL 数据目录、重置密码或用 SQLite 替代 PostgreSQL 验证。

## 6. 配置和迁移

```powershell
uv run stock-research check-config
uv run stock-research health
uv run alembic current
uv run alembic upgrade head
```

当前 Alembic head 是 `0013_gate_b_attempt_number_capacity.py`。

仅在可丢弃的开发/测试数据库验证回滚：

```powershell
uv run alembic downgrade -1
uv run alembic upgrade head
```

## 7. CLI 入口

真实入口由 `pyproject.toml` 定义：

```toml
[project.scripts]
stock-research = "stock_research_agent.cli:app"
```

首先查看帮助：

```powershell
uv run stock-research --help
uv run stock-research securities --help
uv run stock-research data --help
uv run stock-research financials --help
uv run stock-research documents --help
uv run stock-research rag --help
uv run stock-research agent --help
uv run stock-research report --help
uv run stock-research provider --help
uv run stock-research live --help
uv run stock-research evidence --help
uv run stock-research snapshot-ingestion --help
uv run stock-research research-pipeline --help
uv run stock-research tools --help
```

稳定分组及职责：

| 分组 | 主要用途 |
|---|---|
| `securities` | seed、resolve、show Security Master |
| `data` | 明确离线 Fixture ingestion、Snapshot 创建和持久化数据查询 |
| `financials` | seed、normalize、calculate、period/fact/metric/lineage 查询 |
| `documents` | 已持久化文档的注册、解析、状态、section/chunk/verify |
| `rag` | lexical index、offline search、citation、retrieval run、vector status |
| `agent` | 显式 plan/run/control/read Research Run |
| `report` | 显式 generate/reflect/revise/release-check/read/export |
| `provider` | Provider 治理查询及显式受控操作；默认仍不允许 Live |
| `live` | 规划和检查受控 Live evidence；不会自行授权或执行生产操作 |
| `evidence` | 显式导入和审核离线 Manual Evidence |
| `snapshot-ingestion` | 从已治理 ingestion 显式规划/创建 Snapshot |
| `research-pipeline` | 针对精确 Snapshot 运行离线研究链 |
| `tools` | 查看固定 read-only Tool Catalog |

精确参数以每个命令的 `--help` 为准，不应从旧文档猜测。

## 8. FastAPI

启动入口已核对为 `stock_research_agent.main:app`：

```powershell
uv run uvicorn stock_research_agent.main:app --host 127.0.0.1 --port 8000
```

默认 API prefix 是 `/api/v1`：

- Liveness：`http://127.0.0.1:8000/api/v1/health/live`
- Database readiness：`http://127.0.0.1:8000/api/v1/health/ready`
- OpenAPI UI：`http://127.0.0.1:8000/docs`

稳定业务 API 注册 securities、issuers、data、snapshots、financials、rag、research-agent、
reports、providers 和 `live-evidence`。它们是 GET-only 查询边界，不会隐式同步
Provider、运行 Agent 或生成 Report。

## 9. 最小离线示例

```powershell
uv run stock-research securities seed-v0
uv run stock-research securities resolve "601138" --json
uv run stock-research securities resolve "MU" --json
uv run stock-research tools list --json
```

后续 financial、RAG、Agent 和 Report 命令需要明确的 Snapshot、Retrieval Run、Research
Package 或 Report ID。系统不会自动选择 latest Snapshot。

Public Export 中的 SEC/SSE/Nasdaq Synthetic Fixture 使用虚构证券，只通过隔离测试环境
注入，不写入稳定 Security Master seed。它们用于验证解析、Manifest、Checksum、as-of、
Citation 和 Provider 合同，不能作为真实公司的研究证据或 Live 能力证明。缺少正式正文和
数值财务证据时，研究流程应合法返回 `PARTIAL` 或 `BLOCKED`。

## 10. 一次研究流程

```text
1. Resolve Security
2. Fix research_as_of_time
3. Select/create explicit Snapshot
4. Read/normalize persisted financial facts
5. Parse/retrieve persisted documents
6. Build and validate Evidence/Citations
7. Persist finite Agent Plan and Run
8. Seal Research Package
9. Freeze ReportInputManifest
10. Generate canonical JSON and Markdown projection
11. Run bounded Reflection
12. Apply at most one deterministic Revision
13. Evaluate internal Release Gate
```

数据或证据不足时，应返回 `PARTIAL`、`BLOCKED`、`NO_EVIDENCE` 或 `N/M`。

## 11. Offline、Fixture 与 Live

### Offline/Synthetic

用于单元、集成、Golden、迁移和架构验证。Fixture 必须保留来源/许可、Manifest、checksum、
LF 和 `SYNTHETIC_TEST_ONLY / NOT_COMPANY_EVIDENCE / OFFLINE / NOT_LIVE` 标记。

### Live

Live 访问需要逐 Provider、Capability、Security、时点、次数、字节、期限和 Credential
Reference 的单独批准。默认测试不会读取真实 Credential 或访问外部网络。

稳定状态：

- SEC Live：`CONDITIONAL / NOT_ATTEMPTED`；
- Tushare production：`BLOCKED`；
- A 股正式披露正文：`BLOCKED`；
- Licensed U.S. EOD：Provider 未选择；
- Production Embedding：`BLOCKED`。

`provider live-check` 的存在不表示已获 Live 授权；在缺少 gate 时它应安全返回
`BLOCKED/NOT_ATTEMPTED`。

## 12. 质量检查与测试

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
$env:TEST_DATABASE_URL = "postgresql+psycopg://stock_user:<local-test-password>@127.0.0.1:55432/stock_research_test"
uv run pytest -W error
```

默认 suite 收集 `tests/`，允许 loopback PostgreSQL，阻止外部网络，并清除真实 Credential
环境变量。测试数量会变化，精确数量以当前输出为准。

如果 PostgreSQL 未运行、`TEST_DATABASE_URL` 缺失或 Schema 不一致，不要通过删除测试、
降低断言、加入 skip 或继续开发 WIP 功能来伪造绿色结果。

## 13. Report 状态

- `PARTIAL`：只有部分内容具备充分证据；
- `BLOCKED`：关键数据、授权、Provider 或正文缺失；
- `PUBLISHABLE`：内部确定性工程门禁通过。

`PUBLISHABLE` 不表示公开发布、合规审批、投资建议、券商执行或自动交易许可。

## 14. Stage 10 Gate A 与 Gate B 边界

Stage 10 Offline Production Acceptance 和 Gate A 已完成。Gate B engineering 仅部分实现，
readiness 为 `NO_GO`，Production Authorization 为 `NOT AUTHORIZED`，Production Live
Execution 为 `NOT EXECUTED`，SEC Production Pilot 尚未执行，Stage 11 为 `NOT STARTED`。
不要把工程代码存在描述为生产完成或 Live 获批。

## 15. 安全提示

不要提交 `.env`、Token、API Key、Password、Cookie、Authorization、Private Key、真实
数据库 URL、Provider Raw Artifact、响应缓存、运行 Blob、受限数据、个人路径或本地日志。

本项目用于研究、工程和教育，不构成投资建议，也不提供券商执行或自动交易。
