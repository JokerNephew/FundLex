# FundLex 部署指南（4 核 8G + MySQL 8）

版本：2026-10-14。适用：4C8G 单机部署（**2 个 API 进程 + 1 个 worker 进程** + MySQL 8 + 本地磁盘存储）。合同及模型调用串行，API 独立处理查询、上传和下载。以下为初始配置；本机评测不能代替目标服务器容量验收。

## 1. 组件与目录

| 组件 | 说明 |
| --- | --- |
| API | FastAPI（`fundlex.api:app`），无状态，可起多进程 |
| Worker | `python -m fundlex.jobs`，**必须且只能 1 个进程**（本地 profile 的单 worker OS 锁；多 worker 未验收） |
| 数据库 | MySQL 8（任务、批次、文档、产物索引、用户、会话、模型账本）；表结构由应用启动时自动创建 |
| 存储 | `FUNDLEX_DATA_DIR` 指向的本地磁盘目录（输入对象、结果 DOCX、报告）；4C8G 建议预留 ≥ 50 GB |
| 前端 | `frontend/` 静态文件，由 API 直接提供（也可由 Nginx 托管） |

## 2. 环境变量（`.env` 或 systemd Environment）

```ini
# 模型（供应商中立；发布包绑定该配置的指纹，改动后需重新发布）
# 示例：OpenCode Go（需稳定会话头与自定义 User-Agent；数据不用于训练、0 天保留）
LLM_PROVIDER=OpenCodeGo
LLM_BASE_URL=https://opencode.ai/inference/go/v1
LLM_MODEL=deepseek-v4.1-flash
LLM_API_KEY=...                      # 只放服务端环境，禁止入库/入日志
FUNDLEX_MODEL_USER_AGENT=fundlex/0.3.0
FUNDLEX_MODEL_EXTRA_HEADERS_JSON={"x-opencode-session":"fundlex-prod-001"}
# 其他供应商同样适用：只改 LLM_*；若端点要求客户端标识，用上面两个变量，不写供应商分支代码。

# 数据库与存储
FUNDLEX_DATABASE_URL=mysql://fundlex:****@127.0.0.1:3306/fundlex?charset=utf8mb4
FUNDLEX_DATA_DIR=/var/lib/fundlex/data

# 登录（password 模式；dev 模式仅供本机开发）
FUNDLEX_AUTH_MODE=password
FUNDLEX_SESSION_HOURS=12
FUNDLEX_BOOTSTRAP_ADMIN=admin:<强密码>   # 仅首次启动且用户表为空时创建，创建后建议移除

# 预算与并发（按业务审批设置硬上限）
FUNDLEX_MODEL_LEDGER=mysql://fundlex:****@127.0.0.1:3306/fundlex?charset=utf8mb4
FUNDLEX_MODEL_MAX_REQUESTS=20000
FUNDLEX_MODEL_MAX_COST_USD=50
FUNDLEX_MODEL_CONCURRENCY=1
FUNDLEX_MODEL_INPUT_USD_PER_M=0.3
FUNDLEX_MODEL_OUTPUT_USD_PER_M=1.2
FUNDLEX_MODEL_CONTEXT_CHARS=20000
FUNDLEX_MODEL_MAX_OUTPUT_TOKENS=3000
FUNDLEX_MODEL_MAX_CALLS=192
FUNDLEX_MODEL_TIMEOUT_S=60
FUNDLEX_MODEL_RETRIES=1
FUNDLEX_MODEL_REQUEST_OPTIONS_JSON={"thinking":{"type":"disabled"}}
```

## 3. MySQL 初始化

```sql
CREATE DATABASE fundlex CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'fundlex'@'127.0.0.1' IDENTIFIED BY '<强密码>';
GRANT ALL PRIVILEGES ON fundlex.* TO 'fundlex'@'127.0.0.1';
FLUSH PRIVILEGES;
```

应用启动自动建表；升级后首次启动会补齐缺列。MySQL 与应用共用 8 GB 内存时，建议初始 `innodb_buffer_pool_size=1536M`、`max_connections=40`，其余内存留给操作系统、API、worker 和文件页缓存；以实际峰值及慢查询再调整。数据库密码仅经服务进程环境注入。

## 4. 部署步骤

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e .   # 或 uv sync
set -a; source /etc/fundlex.env; set +a

# 首次登录账号
.venv/bin/python -m fundlex.api      # 或直接由 systemd 启动；启动时创建 admin（如已配置）

# 发布规则包：先按预登记协议完成当前引擎/模型配置的5+16+8隔离评测
.venv/bin/python -X utf8 -m rules.release_v2 --audit-output /var/lib/fundlex/audit \
  --evidence-run /var/lib/fundlex/evidence/fixtures \
  --evidence-run /var/lib/fundlex/evidence/regression \
  --evidence-run /var/lib/fundlex/evidence/historical-generalization
```

发布说明：`rules/release_v2.py` 重跑确定性动作审计，并验证传入的完整真实运行证据属于当前引擎、规则、提示与模型传输配置；v3 修改产物还必须通过最终实际产物复核授权门禁。证据目录必须是评测工具实际生成的当前运行，不能手工填写批准或仅重新绑定指纹。任何代码或模型配置变化都需重新取得证据并发布。源码以 LF 固定换行，避免 Windows/Linux checkout 换行造成构建字节漂移；源码内容变化仍会被指纹拒绝。

## 5. systemd（示例）

> **当前服务器实况**（与下方示例不同，以实况为准）：
> - 部署目录 `/opt/fundlex-recall-first`（示例写 `/opt/fundlex`）
> - 环境文件 `/etc/fundlex-recall.env`（示例写 `/etc/fundlex.env`）
> - 服务名 `fundlex-recall-api` / `fundlex-recall-worker`（示例写 `fundlex-api` / `fundlex-worker`）
> - API 监听 `127.0.0.1:8010`（示例写 `:8000`）
> - 运行用户 `fundlex`；发布走 `/home/opencode/fundlex/tools/deploy/publish_workspace.sh`（内部调 root 的 `/usr/local/sbin/fundlex-publish`）
> 下方示例为通用模板，保留供新环境参考。

```ini
# /etc/systemd/system/fundlex-api.service
[Service]
WorkingDirectory=/opt/fundlex
EnvironmentFile=/etc/fundlex.env
ExecStart=/opt/fundlex/.venv/bin/uvicorn fundlex.api:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
```

```ini
# /etc/systemd/system/fundlex-worker.service
[Service]
WorkingDirectory=/opt/fundlex
EnvironmentFile=/etc/fundlex.env
ExecStart=/opt/fundlex/.venv/bin/python -m fundlex.jobs
Restart=always
```

Nginx 反代 8000，开启 `client_max_body_size`（与 `FUNDLEX_MAX_REQUEST_BYTES` 一致）。

## 6. 运行与容量注意

- 单份合同的调用量取决于命中动作、子节备用定位、原文变体以及实际产物复核窗口；新增流程不能再沿用旧版 5—20 次估计。单 gateway 最多 192 次逻辑调用，每次最多 2 次 HTTP 尝试；共享请求及费用硬上限同时生效，192 是拒绝边界而非预计用量。
- 模型并发设为 1，单 worker 每次只处理一份合同。2 个 API 进程负责交互；增加 API 进程不会增加修订并发。先记录每合同耗时、HTTP 尝试、worker 峰值内存与排队长度，待有目标机证据再增加处理并发。
- 上下文上限 20000 字符，输出上限 3000 token，超长章节按段落边界分窗；到窗口上限明确拒绝，不静默截断。这些模型传输参数改变后必须重新取得对应证据并发布规则包。
- 任务查询在服务端聚合任务元数据后筛选，不是数据库 SQL 分页；已验证数百份任务交互，万份规模需另做压测。
- 数据库备份覆盖 MySQL 与 `FUNDLEX_DATA_DIR`；对象存储（S3 等）适配尚未实现，当前为本地磁盘。
- 数据保留/地域、模型固定版本、费用上限需按业务合规确认后再上线。示例生产预算 20000 次/USD 50 是独立生产额度的配置示例；本轮评测严格沿用实施计划登记的私有共享账本上限，不能把生产示例用于绕过评测上限。

## 7. 安全清单

- `LLM_API_KEY`、数据库密码、bootstrap 管理员密码只经环境注入，不写仓库、不入日志、不入报告。
- `FUNDLEX_AUTH_MODE=password` 时所有 API 需登录令牌；owner 隔离按用户 id 生效。
- 生产身份（OIDC/SSO）接入未实现；本指南的登录为本地账号体系。
- 目录、域、超链接、文本框等非目标区域由结构逻辑保护；跨段/跨 cell/屏障目标失败关闭。
