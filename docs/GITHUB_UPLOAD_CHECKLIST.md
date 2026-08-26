# GitHub Upload Checklist

本清单用于第一次公开 Stock Research Agent 前的人工检查。完成清单不等于自动允许上传；
最终结论以 `PUBLIC_RELEASE_READINESS_REPORT.md` 和项目所有者确认 为准。

## 1. Git 状态和分支

```powershell
git branch --show-current
git status --short
git log -10 --oneline
git diff --check
git log --graph --decorate --oneline --all -40
git branch -vv
```

- [ ] 默认公开分支是稳定 `main`；
- [ ] Public candidate 的 parent 仍是批准的 `a113bcba`，没有导入 Engineering commits；
- [ ] Stage 10 Gate A 与部分 Gate B engineering 文件是经过分类和清洗的文件同步；
- [ ] 工作区没有来源不明的修改；
- [ ] 待上传提交和未跟踪文件均经过人工审阅；
- [ ] 没有 stash/reset/restore/clean 覆盖用户工作；
- [ ] 没有为了发布重写 Git 历史。

## 2. Secrets 与 Credentials

至少搜索以下关键词，并人工区分变量名、测试假值和真实值：

```text
TOKEN API_KEY SECRET PASSWORD AUTHORIZATION COOKIE PRIVATE_KEY
TUSHARE_TOKEN OPENAI_API_KEY ANTHROPIC_API_KEY GOOGLE_API_KEY
DATABASE_URL postgresql:// Bearer BEGIN PRIVATE KEY AWS_ GH_TOKEN GITHUB_TOKEN
```

- [ ] 没有真实 Token/API Key/Password/Cookie/Authorization；
- [ ] 没有 Private Key、SSH key、certificate bundle；
- [ ] 没有 production database URL；
- [ ] 没有 Provider Credential 值、前缀、后缀或 hash；
- [ ] 代码、日志、Fixture、Markdown 和 Git history 均已扫描；
- [ ] Secret 扫描结果只报告文件、行号和类别，不复制 Secret 值。

需要重点检查的文件名：

```text
.env  .env.*  *.pem  *.key  *.p12  *.pfx
credentials*  secrets*  token*  cookies*
```

`.env.example` 允许变量名和明确的本地假值，不允许真实 Credential。

## 3. `.env` 与公开配置

- [ ] `.env` 和 `.env.*` 被忽略；
- [ ] `!.env.example` 被保留；
- [ ] `.env.example` 没有个人路径或真实密码；
- [ ] Provider 默认是 `OFFLINE`，网络未启用；
- [ ] `BLOB_STORAGE_ROOT` 是通用绝对路径示例；
- [ ] 开发与测试数据库示例明确分离；
- [ ] 配置文档不会鼓励读取真实 Credential。

## 4. 本地路径与隐私

扫描：

```text
C:\Users\
C:/Users/
/Users/
/home/
个人用户名、邮箱、Desktop、Documents、file://
```

- [ ] 没有真实用户名或个人目录；
- [ ] 没有本机临时目录、下载目录或桌面路径；
- [ ] 通用示例使用 `<project-root>`、`C:\path\to\...` 或仓库相对路径；
- [ ] 历史文档中的环境审计信息已人工判断是否适合公开。

`127.0.0.1` 和 loopback PostgreSQL 可以作为合理本地开发示例，但不得包含真实生产密码。

## 5. Database 与运行数据

不得上传：

```text
*.db  *.sqlite  *.sqlite3  *.dump  *.backup  *.bak
PostgreSQL data directory  test database files  database exports
```

- [ ] 没有 PostgreSQL cluster/data directory；
- [ ] 没有测试数据库文件或 dump；
- [ ] 没有数据库备份；
- [ ] 没有本地 migration scratch output；
- [ ] Docker named-volume 数据没有进入工作区。

## 6. Raw Data、Artifacts 与 Provider 数据

- [ ] 没有运行生成的 Raw Provider Artifact；
- [ ] 没有 Provider response cache；
- [ ] 没有未授权 SEC 完整文档；
- [ ] 没有 Tushare 生产数据；
- [ ] 没有 licensed U.S. EOD 数据；
- [ ] 没有公告/财报全文或第三方受限数据集；
- [ ] 没有运行 Blob、quarantine 文件或下载文件；
- [ ] Cache 未被描述为 Evidence。

## 7. Fixture 审查

每个保留 Fixture 均应确认：

- [ ] 文件最小化且确有测试用途；
- [ ] 来源和允许用途明确；
- [ ] 没有 Secret、隐私或真实 Credential；
- [ ] License/redistribution 风险已审查；
- [ ] Manifest 对应正确；
- [ ] Checksum 与当前 Git blob/工作区字节一致；
- [ ] `.gitattributes` 的 LF 规则有效；
- [ ] Synthetic Fixture 标记为 `SYNTHETIC_TEST_ONLY`、`NOT_COMPANY_EVIDENCE`、
  `OFFLINE`、`NOT_LIVE`；
- [ ] Offline parser success 没有被描述为 Production/Live success。

## 8. 大文件与二进制

分别检查 tracked、untracked 和 Git history：

- [ ] 已列出所有 `>10MB` 文件；
- [ ] 已列出所有 `>50MB` 文件；
- [ ] `>100MB` 文件数量为 0，或已明确阻止上传；
- [ ] 没有无意义 screenshot、archive、installer 或 generated binary；
- [ ] 没有未经批准安装 Git LFS；
- [ ] 必要二进制 Fixture 已完成许可和最小化审查。

## 9. `.gitignore`

至少覆盖：

```gitignore
.env
.env.*
!.env.example
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
coverage/
htmlcov/
dist/
build/
*.egg-info/
.idea/
.vscode/
logs/
tmp/
temp/
*.log
```

并覆盖项目本地 PostgreSQL data、Raw Artifact、Provider cache、Credential 和 Secret
目录，但不得忽略合法 `tests/fixtures/`。

## 10. `.gitattributes`

- [ ] 保留所有已有 Fixture `text eol=lf` 规则；
- [ ] 未重写整个文件；
- [ ] 未执行 `git add --renormalize .`；
- [ ] LF/CRLF 提示已区分为转换提示或内容错误；
- [ ] Checksum Fixture 在 Windows checkout 下保持稳定。

## 11. 文档真实性

- [ ] README 适合 3–5 分钟理解项目；
- [ ] Stage 1–8 写为 Completed；
- [ ] Stage 9 写为 Completed / Conditional Go，而不是 Production Ready；
- [ ] Stage 10 Offline Production Acceptance 与 Gate A 写为 Complete；
- [ ] Gate B Engineering 写为 Partially Implemented / Active Engineering Baseline；
- [ ] Gate B Readiness 写为 `NO_GO`；
- [ ] Production Authorization / Live Execution 写为 `NOT AUTHORIZED` / `NOT EXECUTED`；
- [ ] Stage 11 写为 `NOT STARTED`；
- [ ] Synthetic 没有写成 Live；
- [ ] Fixture 没有写成 Production；
- [ ] SEC metadata 没有写成 filing body；
- [ ] `PUBLISHABLE` 没有写成投资建议或公开批准；
- [ ] 当前没有券商执行或自动交易；
- [ ] Quick Start、CLI、API、Alembic、Ruff、mypy、pytest 命令已按代码核对；
- [ ] Markdown 相对链接全部存在。

## 12. 文档清单

- [ ] `README.md`
- [ ] `docs/PROJECT_INTRODUCTION.md`
- [ ] `docs/PROJECT_MANUAL.md`
- [ ] `docs/USER_GUIDE.md`
- [ ] `docs/CURRENT_STATUS_AND_ROADMAP.md`
- [ ] `docs/GITHUB_UPLOAD_CHECKLIST.md`
- [ ] `docs/PUBLIC_FIXTURE_REPLACEMENT_MATRIX.md`
- [ ] `docs/PUBLIC_RELEASE_READINESS_REPORT.md`
- [ ] 原有 `docs/specs/`、`docs/plans/`、`docs/reflection/` 和实施报告均保留。

## 13. License 与 Disclaimer

- [ ] 已检查 `LICENSE`、`LICENSE.md`、`COPYING`；
- [ ] `LICENSE.md` 明确 `All rights reserved` 和仅供查看、评估；
- [ ] README 明确 `PROPRIETARY / NO OPEN-SOURCE LICENSE GRANTED`；
- [ ] 未擅自添加 MIT、Apache、GPL、BSD 或其他开源 License；
- [ ] 代码 License 与第三方金融数据 License 明确分离；
- [ ] README 和介绍书包含简洁免责声明。

## 14. 质量与迁移验证

```powershell
uv sync --frozen --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run alembic current
```

- [ ] 结果记录在 Release Readiness Report；
- [ ] 测试失败没有通过修改业务逻辑、删测试、弱化断言或 skip 隐藏；
- [ ] 完整 pytest 使用独立 `_test` PostgreSQL 数据库；
- [ ] 默认测试没有执行 Live Provider 请求。

## 15. Git History

- [ ] `git log --oneline --decorate --all` 已审查；
- [ ] 历史没有 `.env`、Secret、Credential、数据库、Raw Artifact 或 >100MB 文件；
- [ ] 如发现风险，只报告，不运行 `filter-repo`、`filter-branch`、BFG 或 force push；
- [ ] 原开发仓库的 Stage 9/10 分支与历史没有被改写；Public Export 不复制旧历史。

## 16. 发布动作（本轮禁止）

在项目所有者明确批准前：

- [ ] 没有 `git push`；
- [ ] `origin` 只用于读取批准的 Public baseline；没有新增或改写 remote；
- [ ] 没有安装或登录 GitHub CLI；
- [ ] 没有创建 GitHub repository、PR、Tag 或 Release；
- [ ] 没有把 Engineering Git history 合并到 Public Repository；
- [ ] Public update branch 修改保持未提交，等待人工差异审阅。
