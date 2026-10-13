# FundLex 部署指南（4 核 8G + MySQL 8）

版本：2026-10-14。适用：单机部署（1 个 API 进程组 + **1 个 worker 进程** + MySQL 8 + 本地磁盘存储）。本指南随"全部 22 个动作可用"版本一起发布。

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
LLM_PROVIDER=DeepSeek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=...                      # 只放服务端环境，禁止入库/入日志

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
FUNDLEX_MODEL_CONCURRENCY=2
FUNDLEX_MODEL_INPUT_USD_PER_M=0.3
FUNDLEX_MODEL_OUTPUT_USD_PER_M=1.2
FUNDLEX_MODEL_CONTEXT_CHARS=12000
FUNDLEX_MODEL_MAX_OUTPUT_TOKENS=2500
FUNDLEX_MODEL_REQUEST_OPTIONS_JSON={"thinking":{"type":"disabled"}}
```

## 3. MySQL 初始化

```sql
CREATE DATABASE fundlex CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'fundlex'@'127.0.0.1' IDENTIFIED BY '<强密码>';
GRANT ALL PRIVILEGES ON fundlex.* TO 'fundlex'@'127.0.0.1';
FLUSH PRIVILEGES;
```

应用启动自动建表；升级后首次启动会补齐缺列。

## 4. 部署步骤

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e .   # 或 uv sync
set -a; source /etc/fundlex.env; set +a

# 首次登录账号
.venv/bin/python -m fundlex.api      # 或直接由 systemd 启动；启动时创建 admin（如已配置）

# 发布规则包（重要）：用部署环境的模型配置运行
.venv/bin/python -X utf8 -m rules.release_v2 --audit-output /var/lib/fundlex/audit
```

发布说明：`rules/release_v2.py` 重跑确定性动作审计（22 动作正反例）并把发布包绑定到**当前引擎构建与模型传输指纹**。任何代码或模型配置变化都会让已发布包在运行期被拒绝（`V2_RELEASE_CONTEXT_UNVERIFIED`），需重新运行发布命令。

## 5. systemd（示例）

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

- 单份合同处理会调用模型 5—20 次（视命中动作数），4C8G 下单 worker 串行是稳定的默认值；模型并发由 `FUNDLEX_MODEL_CONCURRENCY` 控制（建议 ≤ 2）。
- 任务查询在服务端聚合任务元数据后筛选，不是数据库 SQL 分页；已验证数百份任务交互，万份规模需另做压测。
- 数据库备份覆盖 MySQL 与 `FUNDLEX_DATA_DIR`；对象存储（S3 等）适配尚未实现，当前为本地磁盘。
- 数据保留/地域、模型固定版本、费用上限需按业务合规确认后再上线。

## 7. 安全清单

- `LLM_API_KEY`、数据库密码、bootstrap 管理员密码只经环境注入，不写仓库、不入日志、不入报告。
- `FUNDLEX_AUTH_MODE=password` 时所有 API 需登录令牌；owner 隔离按用户 id 生效。
- 生产身份（OIDC/SSO）接入未实现；本指南的登录为本地账号体系。
- 目录、域、超链接、文本框等非目标区域由结构逻辑保护；跨段/跨 cell/屏障目标失败关闭。
