# Stock Research Agent 超级详细项目交接文档

交接基准时间：2026-07-13
当前状态：第1阶段 `CONDITIONAL GO`；第2阶段尚未开始实现
用途：将本文件完整粘贴到新的 AI 对话，使新 AI 能无缝接手。

> 最高优先级提醒：Stock Research Agent 目前没有独立仓库。第1阶段文档和一次性可行性脚本临时位于一个存在大量用户改动的简历网站仓库中。第2阶段虽然获得原则性授权，但强制预检发现仓库与开发环境门槛未满足，因此没有创建后端代码。新 AI 不得直接在当前简历网站目录搭建后端，不得执行 `git add .`、`git init`、重置、清理或覆盖用户文件。

---

# 1. 项目基本信息

## 项目名称与目标

项目名称：Stock Research Agent（A股与美股股票研究智能体）。

目标是让用户输入股票代码、公司名称或别名后，系统能够识别证券，获取有来源和时间戳的行情、财务报表、公告及公司行动，标准化A股/美股数据，用确定性Python代码计算指标和估值，用RAG检索财报与公告，由有限自主权的单Agent生成分析，再通过最多两轮Reflection检查单位、时间、财务口径、引用、反面证据和未来数据泄漏，最终输出可复核、可复现的Markdown和JSON报告。

项目要解决的核心问题：跨市场数据口径不一致；A股累计季度不能直接当单季度；美股非自然财年和XBRL上下文复杂；大模型心算和事实分类不可靠；引用可能不支持结论；历史研究容易使用未来数据；公开网页可访问不等于生产授权；普通聊天无法复现研究所用数据、公式和证据。

确定的总体方案：

```text
固定程序流水线
+ 受控Tool Use
+ 结构化数据与确定性计算
+ 非结构化材料RAG
+ 有边界的单Agent分析
+ 最多两轮Reflection
+ 完整数据血缘与版本记录
```

## 当前阶段

```text
第1阶段：完成，结论 CONDITIONAL GO
第2阶段：尚未开始实现，在强制预检阶段被阻塞
第3阶段及以后：禁止进入
```

第2阶段阻塞原因：当前目录不是独立股票项目仓库；它是有未提交修改的简历网站仓库；用户PowerShell没有可用Git/Python；Docker和PostgreSQL未检测到；也没有批准并验证非Docker PostgreSQL替代方案。用户的第2阶段指令明确规定遇到这种情况必须停止，因此该停止不是自行缩减任务。

## 技术栈

当前股票相关内容只有Python 3.12.13（Codex私有运行时）、Python标准库、可选`pdfplumber`、Markdown文档和一次性探测脚本。

第2阶段计划但尚未安装/实现：Python 3.12、FastAPI、Pydantic v2、pydantic-settings、SQLAlchemy 2.x、Alembic、PostgreSQL、psycopg、Typer、structlog、httpx、pytest、pytest-asyncio、respx、Ruff、mypy、Docker Compose、GitHub Actions。

当前工作区原有React 18、Vite 6、JavaScript、GSAP和CSS全部属于简历网站，不属于股票后端。

## 运行环境

- 操作系统：Windows 11 Home 中文版，64位，版本`10.0.26200`，时区Asia/Shanghai。
- PowerShell行为：Windows PowerShell 5.1。
- 用户`python`：仅`<local-user-root>\AppData\Local\Microsoft\WindowsApps\python.exe` Store别名，执行退出`9009`。
- 用户PATH：未找到`git`、`node`、`docker`、`uv`、`psql`、`pg_isready`。
- PostgreSQL：未发现服务或常见安装目录。
- Codex私有Python：`<local-user-root>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，版本3.12.13。
- Codex私有Git：`<local-user-root>\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe`，版本2.53.0.windows.3。
- Codex私有Node：版本24.14.0。

Codex缓存路径可能随应用更新变化，禁止写入项目配置或当成可复现环境。

## 目录、Git、部署与数据库

逻辑上的独立项目路径尚未确定。推荐但未确认：

```text
<project-root>
```

第1阶段文件临时位于：

```text
<legacy-workspace>
```

当前Git分支`main`，HEAD`63f874b`。已跟踪用户修改包括`src/data/profile.js`和`src/styles/global.css`，另有大量无关未跟踪文件。股票项目`docs/`和`scripts/`也整体未跟踪。没有股票项目Git提交。

Stock Research Agent没有线上部署、API服务、Docker容器、云数据库、腾讯云资源、域名或CI部署。当前网站仓库含Vercel/CloudBase/EdgeOne文件，但线上状态不确定且与股票项目无关。

最终计划使用PostgreSQL；当前没有数据库、SQLAlchemy、Alembic、迁移、表或连接配置。第2阶段禁止提前创建`Issuer`、`Security`、`MarketPrice`、`FinancialFact`、`ResearchRun`、`Citation`等后续业务表。

## 第三方API与敏感信息

真实只读探测过：SSE、CNINFO、SEC、Nasdaq公开网站、Micron IR、工业富联官方PDF、OpenAI公共端点。计划但未接入：A股结构化供应商、许可明确的美国EOD/公司行动供应商、OpenAI或其他模型服务、腾讯云、对象存储、向量服务和MCP。

没有发现股票项目真实API Key、Token或密码。没有配置OpenAI Key、Tushare Token、美国行情供应商Key、数据库密码或SEC真实联系人。任何真实敏感值必须写作`[REDACTED]`。SEC当前占位符`USER_CONTACT_NOT_CONFIGURED`不是合规生产联系人。

---

# 2. 当前项目进度

## 模块A：产品范围

- 状态：文档完成，功能未实现
- 文件：`docs/product-scope-v0.1.md`、`docs/compliance-boundaries.md`、`docs/stage-1-readiness-report.md`
- 核心：只验证工业富联`601138.SH`和美光`MU`；最新可用日线收盘价；固定流水线；单Agent；最多两轮Reflection。
- 已验证：范围状态、成功/失败标准、排除项已写清。
- 未验证：没有完整流水线或最终研究报告。
- 下一步：先解除第2阶段门禁，不扩展范围。

## 模块B：环境审计与门禁

- 状态：审计完成；Stage 2仍阻塞
- 文件：`environment-audit.md`、`open-questions.md`、`risk-register.md`、`stage-1-readiness-report.md`
- 已验证：仓库、分支、用户改动、Python/Git/Docker/PostgreSQL缺口。
- 下一步：确认独立路径和数据库方案后重跑预检。

## 模块C：数据源可行性

- 状态：部分验证，不等于生产接入
- 文件：`data-source-matrix.md`、`sample-data-validation/601138.SH.md`、`sample-data-validation/MU.md`、可行性脚本
- 已验证：工业富联身份、SSE网站日线、定期报告、官方PDF、人民币千元单位、累计季度口径；MU ticker/CIK、SEC submissions、Company Facts；Nasdaq公开MU OHLCV和分红交叉验证。
- 未完整验证：SEC filing index、自定义XBRL、拆股历史、A股复权因子、供应商授权。
- 问题：SEC主文档403；index因客户端不同而变化；公开网页无生产授权/SLA。
- 下一步：第2阶段不得继续数据接入，这些属于`BLOCKS_DATA_INTEGRATION`。

## 模块D：可行性脚本

- 状态：已修复并验证
- 文件：`scripts/feasibility/validate_public_sources.py`、测试、README
- 逻辑：`PASS=0`、`FAIL=1`、`PARTIAL=2`、`BLOCKED=3`；输出单个结构化JSON；必选检查失败不返回0。
- 验证：5个单元测试通过；完整运行`BLOCKED`，JSON和子进程退出码均为3。
- 注意：不是生产adapter，不要在第2阶段扩展为业务模块。

## 模块E：财务指标和估值

- 状态：定义完成，无实现
- 文件：`metric-definitions-v0.1.md`、`report-schema-v0.1.md`、`ADR-009-model-and-calculation-boundary.md`
- 指标：增长、毛利率、营业/净利率、ROE/ROA/ROIC、OCF、FCF、负债率、净债务、基本/稀释EPS、PE/PB/PS/EV/EV-EBITDA/FCF Yield及三项TTM。
- 边界：金额使用Decimal；累计季度确定性还原；归母与总净利润不混用；基本与稀释EPS不混用；缺失EBITDA不估算。
- 估值：工业富联主方法为正常化归母PE；美光优先正常化/中周期EV/EBITDA；EV/Revenue不是通用默认；增长率和倍数全部是SCENARIO。
- 下一步：第2阶段禁止实现，正式计算属于第5阶段。

## 模块F：Tool Use、RAG、Reflection、MCP和报告

- 状态：架构文档完成，全部未实现
- Tool Use：固定编排、白名单只读工具、Schema/版本/权限/超时/审计；第2阶段只可留`tools/`空包。
- RAG：文档获取→解析→切分→索引→过滤→混合检索→重排→引用；第2阶段只可留`retrieval/`空包。
- Reflection：确定性、证据、反方三层，最多两轮；第2阶段只可留空包。
- MCP：V0.1推迟正式Server，第2阶段不安装SDK。
- 报告：八个模块化输出；FACT/CALCULATION/INFERENCE/SCENARIO/UNVERIFIED；置信度只用HIGH/MEDIUM/LOW。

## 模块G：安全、合规与部署

- 状态：边界文档完成，控制未实现
- 已定义：外部文档不可信；禁止任意URL；模型不能读密钥；日志脱敏；数据库最小权限；个人自用；不自动交易、不保证收益；公开服务前重做授权与合规审查。
- 第2阶段只实现通用配置、错误处理和日志脱敏，不实现股票业务。

## 模块H：Stage 1 Reflection和Stage 2

- Stage 1两轮审查已完成，修复通用EV/Revenue、OpenAI误述、SEC过度概括、阻塞分类、脚本退出0和运行环境混淆。
- Stage 2状态：未开始；没有`pyproject.toml`、锁文件、FastAPI、Settings、SQLAlchemy、Alembic、CLI、日志、健康检查、Docker、CI、正式tests目录或实施报告。

## 已废弃、证明不可行或明确推迟

- 当前简历网站作为默认股票项目目录；
- Codex缓存运行时作为正式环境；
- SSE/Nasdaq网站端点作为生产数据源；
- OpenAI公共端点401作为API可用证明；
- 所有公司统一一年期EV/Revenue；
- 早期多Agent、MCP、实时行情、自动交易；
- 用SQLite假装PostgreSQL已通过。

---

# 3. 文件结构说明

```text
<legacy-workspace>\
├── AGENTS.md                         # 简历网站约束，不是股票项目约束
├── README.md                         # 简历网站README
├── package.json                      # React/Vite配置
├── .env.example                      # 网站占位配置
├── src\                              # 简历网站前端源码
├── docs\                             # 股票项目Stage 1文档，当前未跟踪
│   ├── product-scope-v0.1.md
│   ├── data-source-matrix.md
│   ├── metric-definitions-v0.1.md
│   ├── report-schema-v0.1.md
│   ├── tool-use-design-v0.1.md
│   ├── rag-design-v0.1.md
│   ├── reflection-design-v0.1.md
│   ├── mcp-roadmap.md
│   ├── security-boundaries.md
│   ├── compliance-boundaries.md
│   ├── deployment-feasibility.md
│   ├── environment-audit.md
│   ├── open-questions.md
│   ├── risk-register.md
│   ├── stage-1-readiness-report.md
│   ├── architecture-decisions\ADR-001...ADR-009
│   ├── sample-data-validation\601138.SH.md / MU.md
│   └── reflection\round-1-review.md / round-2-consistency-check.md
└── scripts\feasibility\
    ├── README.md
    ├── validate_public_sources.py
    └── test_validate_public_sources.py
```

重要文件说明：

- `AGENTS.md`、根README、package.json和`.env.example`属于简历网站，禁止为股票项目修改。
- `product-scope-v0.1.md`定义范围和验收；新增需求前先核对。
- `data-source-matrix.md`记录18类来源、权限、验证状态和风险；公开访问不等于授权。
- 两份sample validation记录工业富联和MU真实探测边界。
- `metric-definitions-v0.1.md`是未来确定性计算规范，不是实现。
- `report-schema-v0.1.md`要求模块化Schema，禁止大单体。
- tool/RAG/reflection/MCP文档定义后续边界，Stage 2不得实现其业务。
- security/compliance/deployment文档定义不可信输入、密钥、日志、网络和对外服务边界。
- environment/open questions/risk/readiness是继续开发的门禁依据。
- 九份ADR全部Accepted：固定编排、快照、adapter、结构化/RAG、Reflection、MCP延期、模块化报告、日线收盘价、模型/计算边界。

`validate_public_sources.py`的重要对象：`Reader`、`fetch_with_error()`、`emit()`、`build_summary()`、`exit_code_for_status()`、各`probe_*()`和`main()`。它是只读probe，不是生产adapter。测试文件包含`SummaryStatusTests`和`FetchIsolationTests`；导入路径已修正为`from scripts.feasibility...`。

当前不存在股票后端入口、API路由、数据库模块、CLI、正式配置、部署文件和以下结构：

```text
pyproject.toml
uv.lock
Dockerfile
docker-compose.yml
alembic.ini
migrations/
src/stock_research_agent/
tests/
.github/workflows/backend-ci.yml
docs/stage-2-implementation-report.md
```

---

# 4. 核心逻辑说明

## 当前真正可运行的流程

当前没有用户请求入口、FastAPI入口或正式CLI。唯一可运行的股票程序是可行性脚本：

```text
执行 validate_public_sources.py
→ main()解析参数
→ 创建Reader
→ 运行网络、SSE、PDF、SEC和Nasdaq探测
→ emit()保存每项内存结果
→ build_summary()区分必选/可选和成功/失败
→ exit_code_for_status()选择退出码
→ 输出一个JSON对象
→ 使用0/1/2/3退出
```

`Reader.fetch()`负责User-Agent、Accept、30秒超时、HTTPError响应、gzip和每次请求后0.25秒延迟。`fetch_with_error()`把超时转为结构化结果，避免单个SEC端点失败终止整个探测。

状态优先级：必选FAIL→FAIL；否则必选BLOCKED→BLOCKED；否则存在未完全通过、配置缺口或警告→PARTIAL；完全无问题→PASS。

## 最终系统计划流程

```text
用户输入代码或名称
→ 证券识别
→ 固定research_as_of_time
→ 创建数据快照
→ Provider Adapter获取结构化数据
→ 校验时间、币种、单位、报告期
→ A股累计季度转离散季度
→ 美股财年和XBRL上下文选择
→ 确定性计算TTM、指标和估值
→ RAG检索财报、公告和反面证据
→ 单Agent分析商业模式、财务、行业、估值、催化剂、风险
→ 生成模块化初稿
→ 确定性检查
→ 引用和证据检查
→ 反方与假设检查
→ 最多两轮定向修正
→ 输出Markdown和JSON
→ 保存快照、公式、提示词、模型和引用版本
```

固定流程的原因：防止跳过必选步骤；防止Agent修改研究时点；防止模型心算关键数字；使失败可定位、研究可重放。

容易出Bug：A股累计季度误当单季度；XBRL上下文/自定义标签选错；未来数据泄漏；股本、分红、拆股和复权口径不一致；负利润估值展示错误；引用存在但不支持结论；SEC访问不稳定；日志泄露连接串和Token；健康检查误调用外部服务；测试误连生产数据库。

已经改过的逻辑：脚本从固定退出0改为四状态；端点异常改为隔离；测试改为仓库根可导入；OpenAI改为仅公共端点网络可达；SEC改为逐端点/客户端记录；估值改为公司特定方法；问题改为四类阻塞等级。

技术债：Stage 1文件混在网站仓库且未跟踪；公开网页只适合交叉验证；Python/Git依赖Codex缓存；无锁文件；SEC联系人占位；数据授权未完成；没有数据库、CI和独立股票项目AGENTS.md。

---

# 5. 环境变量与配置

## 当前状态

- 股票项目`.env`：不存在；
- 根`.env.example`：属于简历网站，只有前端注释；
- 股票`config.py`/`settings.py`：不存在；
- 数据库、API、代理、股票部署配置：不存在或不确定。

## Stage 2计划配置

- `APP_NAME`
  - 用途：服务名、OpenAPI标题、日志服务名
  - 是否必填：开发可默认，生产规则待实现
  - 示例：`stock-research-agent`
  - 缺失：应使用安全默认值

- `APP_ENV`
  - 用途：development/test/production
  - 是否必填：必须是合法枚举
  - 示例：`development`
  - 缺失：开发可默认；production应安全失败

- `APP_DEBUG`
  - 用途：调试模式
  - 是否必填：否
  - 示例：`false`
  - 缺失：应默认关闭

- `APP_HOST`
  - 用途：监听地址
  - 是否必填：否
  - 示例：`127.0.0.1`
  - 缺失：使用本地安全默认值

- `APP_PORT`
  - 用途：API端口
  - 是否必填：否
  - 示例：`8000`
  - 缺失：使用默认端口；非法值必须清晰报错

- `LOG_LEVEL`
  - 用途：日志级别
  - 是否必填：否
  - 示例：`INFO`
  - 缺失：使用安全默认值

- `DATABASE_URL`
  - 用途：PostgreSQL连接
  - 是否必填：production必须显式配置；test必须指向隔离库
  - 示例：`postgresql+psycopg://stock_user:[REDACTED]@localhost:5432/stock_research`
  - 缺失：readiness应503；production启动应失败

- `DATABASE_ECHO`
  - 用途：SQLAlchemy SQL输出
  - 是否必填：否
  - 示例：`false`
  - 缺失：应默认为false

- `API_PREFIX`
  - 用途：API前缀
  - 是否必填：否
  - 示例：`/api/v1`
  - 缺失：使用默认值

未来但不属于Stage 2的变量：`OPENAI_API_KEY=[REDACTED]`、`TUSHARE_TOKEN=[REDACTED]`、尚未命名的美国EOD Key、尚未最终命名的SEC真实联系人配置。SEC脚本当前使用`--contact`参数；不得编造联系人。

脚本CLI标志：`--contact`、`--tushare-configured`、`--us-eod-configured`、`--openai-auth-verified`。后三项只表示外部配置已确认，不读取密钥。

---

# 6. 启动、运行和测试

## 股票后端

当前没有后端，无法启动。不存在可用uvicorn入口、`stock-research` CLI、迁移命令、Docker Compose或CI命令。不得声称后端已启动。

## 已验证的Stage 1单元测试

```powershell
& '<local-user-root>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  -B -m unittest -v scripts/feasibility/test_validate_public_sources.py
```

真实结果：5个测试通过，`Ran 5 tests`、`OK`、退出码0。该绝对路径只作为历史证据，不能写入未来项目README。

## 已验证的完整探测

```powershell
& '<local-user-root>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  scripts/feasibility/validate_public_sources.py
```

真实结果：`overall_status=BLOCKED`、JSON `exit_code=3`、子进程退出码3。非零是诚实结果，因为SEC Archive必选检查被阻断。

SEC真实联系人测试未执行。未来命令形式：

```powershell
python scripts/feasibility/validate_public_sources.py --contact "REAL_PROJECT_CONTACT_EMAIL_OR_URL"
```

不得使用虚假联系人。

简历网站的`npm install`、`npm run dev`、`npm run build`和`npm run check`与股票项目无关，本次没有重新验证。不要将`npm run dev`当成股票后端。

数据库当前无法启动。Docker、psql、pg_isready均不可用。恢复Stage 2前必须真实验证Docker Compose PostgreSQL或本地非Docker PostgreSQL；禁止用SQLite冒充PostgreSQL集成通过。

常见失败：用户`python`命中Store别名；PATH找不到git/docker/psql/uv；当前目录没有Python工程；在当前目录创建pyproject会污染网站；`git add .`会暂存大量无关文件；完整探测当前预期返回3；高频SEC重试可能加重阻断。

---

# 7. 已知问题和坑

## 问题：没有独立仓库

- 表现：Stage 1文件临时位于简历网站仓库。
- 可能原因：Stage 1只做文档和可行性验证。
- 已尝试方案：Stage 2开始时执行强制预检。
- 有效方案：停止，等待用户确认独立路径。
- 无效方案：直接在当前src/docs/scripts继续搭建。
- 相关文件：AGENTS、environment audit、readiness report。
- 下一步：先确认独立路径，未确认前不创建代码。

## 问题：Git工作区很脏

- 表现：两个已跟踪修改和大量未跟踪内容。
- 原因：简历网站存在其他开发、部署和归档工作。
- 已尝试：只读检查，没有暂存或提交。
- 有效方案：独立股票仓库。
- 无效方案：`git add .`、`git reset --hard`、清理未跟踪目录。
- 相关文件：`src/data/profile.js`、`src/styles/global.css`及整个工作树。
- 下一步：不修改、暂存或清理用户内容。

## 问题：用户Python/Git不可用

- 表现：Python Store别名退出9009；Git不在PATH。
- 原因：未安装或未配置。
- 已尝试：用Codex私有路径完成Stage 1。
- 有效方案：安装用户可访问Python 3.12和Git。
- 无效方案：硬编码Codex缓存路径。
- 相关文件：`docs/environment-audit.md`。
- 下一步：验证普通PowerShell中的`python --version`、`git --version`。

## 问题：Docker/PostgreSQL不可用

- 表现：docker、psql、pg_isready、服务和常见目录均不存在。
- 原因：尚未安装。
- 有效方案：安装Docker或批准并验证非Docker PostgreSQL。
- 无效方案：SQLite冒充PostgreSQL。
- 下一步：让用户选择方案并做真实迁移验证。

## 问题：SEC主文档403且index不稳定

- 表现：MU 10-Q/10-K主文档403；Python index 403；相同声明头.NET index 200且为83项有效JSON；再次Python仍403。
- 可能原因：联系人占位、客户端指纹、时点、网络出口或SEC策略。
- 已尝试：urllib、HttpClient、明确UA、低频请求。
- 有效方案：尚无完整方案。
- 无效方案：伪造联系人、高频重试、凭一次200宣称稳定。
- 相关文件：MU验证、矩阵、脚本。
- 下一步：第4阶段使用真实联系人、固定客户端、限流、退避和缓存重复验收。

## 问题：OpenAI只验证公共端点网络可达

- 表现：无凭证返回401。
- 原因：没有API Key。
- 有效结论：网络可达，但鉴权、模型、配额、Responses API、Structured Outputs和目标地区生产连通性未验证。
- 无效方案：把401写成API可用。
- 下一步：Stage 2不需要OpenAI；生产前从目标地区鉴权测试。

## 问题：正式供应商未确定

- 表现：没有Tushare Token或许可明确的美国EOD供应商。
- 原因：账号、费用、合同未决。
- 有效方案：Stage 4前选择并确认缓存、展示、商业权限。
- 无效方案：把SSE/Nasdaq网站端点当生产授权。
- 下一步：Stage 2只做供应商中立边界。

## 问题：脚本旧版退出0及测试导入失败

- 表现：内部失败曾返回0；根目录测试曾`ModuleNotFoundError`。
- 原因：main固定0；测试同目录裸导入。
- 有效方案：四状态退出码；改用`from scripts.feasibility...`。
- 当前状态：均已修复，5个测试通过。
- 无效方案：恢复固定0或裸导入。
- 下一步：保留当前语义。

## 问题：PowerShell 5.1兼容性

- 表现：不支持PowerShell 7三元表达式和`Invoke-WebRequest -SkipHttpErrorCheck`。
- 有效方案：使用if/else和.NET HttpClient。
- 下一步：默认使用PowerShell 5.1兼容命令，除非先确认pwsh。

## 问题：估值方法曾过度固定

- 表现：早期倾向通用一年期EV/Revenue。
- 原因：最小模板被过度泛化。
- 有效方案：按盈利状态、周期性、资本强度和字段可用性选方法。
- 当前状态：文档已修复。
- 下一步：不要恢复通用默认值。

---

# 8. 最近修改记录

## 2026-07-11：完成Stage 1文档

- 原因：正式开发前确认范围、数据、指标和架构边界。
- 文件：docs下全部Stage 1文档。
- 内容：产品范围、矩阵、样本、指标、九份ADR、安全、合规、部署、报告。
- 验证：文档检查和两轮Reflection。

## 2026-07-11：实现并修复可行性脚本

- 原因：真实验证SSE/SEC/Nasdaq；修复失败退出0和单端点异常中止。
- 文件：脚本、测试、README。
- 内容：四状态、0/1/2/3退出码、结构化JSON、端点异常隔离。
- 验证：5个测试通过；完整运行返回3。
- 风险：只能作为probe，不能成为生产adapter。

## 2026-07-11：完成最终收尾

- 原因：消除环境、OpenAI、SEC、估值和阻塞分类矛盾。
- 文件：环境审计、矩阵、MU验证、指标、报告Schema、ADR-009、open questions、risk register、readiness等。
- 内容：四环境区分；严格OpenAI表述；SEC逐端点；公司特定估值；四类阻塞项。
- 验证：重跑环境、单测、完整探测、SEC诊断、文档扫描和Git状态。

## 2026-07-13：Stage 2预检后停止

- 原因：用户正式下达Stage 2指令。
- 修改文件：无。
- 检查：AGENTS、Stage 1文档、Git、Python、Git、Docker、PostgreSQL、uv和根文件冲突。
- 停止原因：脏的简历网站仓库且环境门槛未满足。
- 结论：Stage 2没有代码、迁移、测试体系或实施报告，不能声称已开始开发。

---

# 9. 下一步开发计划

## 第一优先级：解除仓库和环境阻塞

- 目标：建立独立、用户可复现的Stock Research Agent环境。
- 原因：这是Stage 2硬门禁。
- 步骤：
  1. 用户确认绝对路径，建议`<project-root>`；
  2. 检查路径是否存在、为空、已有Git或用户文件；
  3. 只有确认独立新路径后才考虑`git init`；
  4. 安装/验证用户可访问Python 3.12和Git；
  5. 选择Docker PostgreSQL或非Docker PostgreSQL；
  6. 验证普通PowerShell的Python/Git和数据库；
  7. 复制Stage 1文档/脚本到独立仓库，保留原文件；
  8. 创建股票项目专用AGENTS.md；
  9. 用户再次明确授权Stage 2。
- 验收：路径独立、Git清晰、用户Python/Git可用、至少一种PostgreSQL方案可复现。

## 第二优先级：TDD建立Python后端骨架

- 目标：可安装、可配置、可测试的FastAPI基础。
- 原因：Stage 2核心，不依赖股票供应商。
- 步骤：实施计划→依赖管理与锁文件→配置测试/Settings→应用工厂测试/create_app→liveness→错误模型/request ID/log脱敏→Typer CLI→每步Ruff/mypy/pytest。
- 验收：项目可安装；无导入副作用；liveness 200；配置、错误、日志、CLI测试通过；无股票业务。

## 第三优先级：PostgreSQL、迁移、Docker、CI和验收

- 目标：完成数据库可复现性和Stage 2质量门。
- 步骤：SQLAlchemy engine/session和回滚；Alembic；真实PostgreSQL upgrade/downgrade/upgrade；readiness 200/503；Dockerfile/Compose；GitHub Actions临时PostgreSQL；Ruff、format、mypy、pytest；两轮Stage 2 Reflection；实施报告；只暂存股票文件。
- 验收：迁移真实通过；readiness双场景通过；静态检查、类型和测试全通过；无CRITICAL/HIGH；不进入Stage 3。

## 现在不要做

- 不在简历网站仓库创建后端；
- 不`git add .`、重置或清理用户文件；
- 不正式接入SSE/Tushare/Nasdaq/SEC/OpenAI；
- 不创建股票业务表；
- 不实现证券识别、标准化、TTM、估值、RAG、Agent、Reflection业务或MCP；
- 不安装向量数据库、Agent框架、Celery、MCP SDK；
- 不开发前端、券商连接、实时行情或自动交易；
- 不进入Stage 3。

## 容易过度开发

完整领域模型、LangChain/LlamaIndex、MCP、向量库、事件总线、任务队列、过度Provider抽象、大量空文件、全市场识别、健康检查调用外部服务、SQLite伪装PostgreSQL，当前都不要做。

## 必须先验证再写代码

独立路径；用户Python/Git；依赖管理工具；Docker或非Docker PostgreSQL；Python依赖兼容性；测试库隔离；Alembic在线/离线；Windows与CI/Linux差异；production配置安全失败；日志对数据库URL、Token和Authorization的脱敏。

---

# 新 AI 接手后的第一条行动

不要立即生成代码。先确认并真实验证：

```text
1. Stock Research Agent独立仓库的绝对路径是什么？
2. 数据库开发环境选择Docker还是非Docker PostgreSQL？
3. 用户本地Python 3.12和Git是否已安装并能从普通PowerShell运行？
```

三项通过后才能重新开始Stage 2。不得进入Stage 3。
