# Environment Audit

Audit updated: 2026-07-11 +08:00
Workspace: `<legacy-workspace>`

## Summary

The apparent runtime contradiction is real but explainable: the user's ordinary PowerShell PATH and the Codex execution runtime are different environments. Codex injects/knows absolute paths under its private runtime cache; those executables are not discoverable from the user's normal PATH. Neither environment is yet the future Stock Research Agent development or deployment environment.

The current directory is also an existing, dirty portfolio website repository. A dedicated Stock Research Agent repository/path is a Stage 2 entry condition.

## Four distinct environments

### 1. User local PowerShell environment

Actual commands requested by the user were run without modifying PATH:

```powershell
Get-Command python -ErrorAction SilentlyContinue
Get-Command node -ErrorAction SilentlyContinue
Get-Command git -ErrorAction SilentlyContinue
Get-Command docker -ErrorAction SilentlyContinue

where.exe python
where.exe node
where.exe git
where.exe docker
```

Observed results:

| Executable | `Get-Command` / `where.exe` result | Execution result | Reproducibility meaning |
|---|---|---|---|
| Python | `<local-user-root>\AppData\Local\Microsoft\WindowsApps\python.exe`, version metadata `0.0.0.0` | `python --version` produced no version and process exit `9009` | This is a Microsoft Store/App Execution Alias placeholder, not a usable configured Python runtime. |
| Node | Not found | Not executable | User shell cannot run Node. Node is not required for the Stage 2 Python backend, but will be needed later for frontend work. |
| Git | Not found | Not executable | User shell cannot reproduce Git commands without an absolute Codex path. This blocks a reproducible Stage 2 workflow. |
| Docker | Not found; common locations under Program Files and LocalAppData also absent | Not executable | Docker is unavailable. Stage 2 may proceed only if Docker is installed/verified or an explicit non-Docker PostgreSQL/local-service plan is approved. |

### 2. Codex execution runtime

Codex supplied private, absolute executable paths:

| Executable | Exact source/path | Verified version | Scope/risk |
|---|---|---|---|
| Python | `<local-user-root>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` | `3.12.13` | Works for this Codex desktop thread. It is a bundled dependency, not proof that the user's shell or CI has Python. |
| Node | `<local-user-root>\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe` | `v24.14.0` | Works by absolute path only. It should not be selected as the project's support policy merely because Codex bundles it. |
| Git | `<local-user-root>\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe` | `2.53.0.windows.3` | Can inspect the repository, but normal user/CI reproducibility is absent. |
| Docker | No bundled path and no common system installation found | Not available | Codex cannot validate containers locally. |

Codex cache paths may change with app/runtime updates and are not a supported project dependency. Stage 2 must not hard-code them into project files.

### 3. Future project development environment

Not yet created. Before Stage 2 it must have:

- a dedicated repository/path;
- a user-accessible, pinned supported Python version and dependency manager;
- user-accessible Git;
- PostgreSQL through either verified Docker Compose **or** a documented non-Docker local/service alternative;
- a reproducible bootstrap/health-check procedure usable outside Codex;
- no dependency on the portfolio site's Node installation or Codex cache paths.

Node is not a Stage 2 blocker because the first backend is Python-only. It becomes relevant when frontend work is authorized in Stage 10.

### 4. Future deployment environment

Not provisioned or tested. Tencent Cloud region, network egress, PostgreSQL, object storage, secrets, model provider and provider connectivity remain production decisions. Desktop reachability cannot prove cloud-region reachability, authorization, quota or compliance.

## Repository state

| Item | Actual result | Impact |
|---|---|---|
| Operating system | Windows 11 Home Chinese, 64-bit, version `10.0.26200` | Local OS identified; Linux/production parity untested. |
| Git repository | Existing `.git/`, branch `main`, HEAD `63f874b9` | Do not run `git init`. |
| Git status | Existing modifications to `src/data/profile.js`, `src/styles/global.css`, plus many unrelated untracked paths | Do not stage unrelated work. |
| `AGENTS.md` | Portfolio visual-direction instructions | Confirms this is an unrelated resume-site repository. |
| `docs/` before Stage 1 | Did not exist | Stage 1 created it for evidence/decisions only. |

## Network and API interpretation

| Target | Actual observation | Strict interpretation |
|---|---|---|
| SSE/CNINFO/Micron IR | Public pages returned HTTP 200 | Public-page network reachability only; production API/licence not implied. |
| SEC submissions | HTTP 200 | `data.sec.gov` submissions endpoint is usable in the current probe. |
| SEC Company Facts | HTTP 200 | `data.sec.gov` Company Facts endpoint is usable in the current probe. |
| SEC Archives filing index | Python `urllib` 403; same-header .NET retry 200 with valid JSON/83 items; Python retry 403 | Client/time-sensitive and not reproducible; see MU validation. |
| SEC Archives primary documents | HTTP 403 with contact placeholder in Python and .NET checks | Current request configuration is blocked on the tested 10-Q/10-K document paths. |
| OpenAI public endpoint | HTTP 401 without credentials | **OpenAI公共端点网络可达，但API鉴权、模型权限、配额、Responses API、Structured Outputs以及目标部署地区的生产连通性尚未验证。** |

Public endpoint availability must not be described as API availability. OpenAI's official supported-country list also omits mainland China, so a mainland Tencent deployment cannot assume OpenAI API support.

## Credentials

Only environment-variable names were inspected; values were not read or logged. No matching OpenAI, Tushare, Alpha Vantage, Nasdaq Data Link or other planned provider key name was found.

## Current risks and later-stage impact

1. Dedicated repository and user-accessible Git/Python are `BLOCKS_STAGE_2`.
2. Docker itself is not an unconditional blocker if an explicit, testable non-Docker alternative is approved; without either path, local services are `BLOCKS_STAGE_2`.
3. A-share structured and U.S. EOD providers are `BLOCKS_DATA_INTEGRATION`, not the provider-neutral Stage 2 skeleton.
4. Tencent/model/provider cloud tests are `BLOCKS_PRODUCTION`, not Stage 2 scaffolding.
5. Commercial/public distribution decisions are `BLOCKS_PRODUCTION` for public release and licensing, not personal local scaffolding.

## Commands and real outcomes

| Command | Output summary | Result |
|---|---|---|
| Requested `Get-Command` and `where.exe` checks | Python Store alias found; Node/Git/Docker absent; overall PowerShell command returned 1 because three `where.exe` lookups failed | Partial/expected environment gap |
| Python alias execution | No version; exit 9009 | Failed; placeholder only |
| Codex absolute-path version checks | Python 3.12.13, Node 24.14.0, Git 2.53.0 | Success inside Codex runtime only |
| Common Docker-path checks | Both tested paths absent | Docker not installed/verified |
| `python -m unittest -v scripts/feasibility/test_validate_public_sources.py` | Five tests passed after the root-import path was corrected | Success |
| Updated feasibility script | Structured `BLOCKED`, internal/process exit code 3; SEC data endpoints passed; full Python Archive checks blocked | Honest non-success; later index-only .NET success does not make the filing-document chain complete |
