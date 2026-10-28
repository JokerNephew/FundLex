# FundLex 部署指南（4 核 8G + MySQL 8）

版本：2026-10-29。适用：4C8G 单机部署（**2 个 API 进程 + 修订/比对/指引三个 Worker + 飞书进程** + MySQL 8 + 本地磁盘存储）。合同及模型调用串行，API 独立处理查询、上传和下载。以下为初始配置；本机评测不能代替目标服务器容量验收。

## 1. 组件与目录

| 组件 | 说明 |
| --- | --- |
| API | FastAPI（`fundlex.api:app`），无状态，可起多进程 |
| Worker | `python -m fundlex.jobs`，**必须且只能 1 个进程**（本地 profile 的单 worker OS 锁；多 worker 未验收） |
| Compare Worker | `python -m fundlex.compare.worker`，独立进程 |
| Guide Worker | `python -m fundlex.guide_generation.worker`，独立进程 |
| Feishu | `python -m fundlex.integrations.feishu.service_main`，独立 WebSocket/状态同步进程 |
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
FUNDLEX_BOOTSTRAP_ADMIN=admin:<强密码>   # 首次启动空库时创建；锁定后重新注入同账号密码可恢复；创建后建议移除

# 调用观测与并发（按需调用，无需费用/次数审批；FL-D445/FL-D449）
# MAX_REQUESTS/MAX_COST_USD/MAX_CALLS 是旧运行时cap示例，不是用户要求。
# 当前无禁用cap/仅观测开关，运行时待整改；0不表示无限，勿照此配置。
# 以下正数仅描述旧配置，不代表新政策已实现；并发/上下文/重试边界保留。
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

# 上传门禁（可选；与 Nginx 模板和 UploadGuardSettings 一起调整）
# FUNDLEX_UPLOAD_REQUEST_BYTES=54525952
# FUNDLEX_GUIDE_REQUEST_BYTES=27262976
# FUNDLEX_REGULATION_REQUEST_BYTES=85983232
# FUNDLEX_MAX_UPLOAD_BYTES=26214400
# FUNDLEX_MAX_BATCH_BYTES=52428800
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
> - 服务名 `fundlex-recall-api` / `fundlex-recall-worker` / `fundlex-compare-worker` / `fundlex-guide-worker` / `fundlex-feishu`（示例仅写 `fundlex-api` / `fundlex-worker`）
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

### 5.1 统一五服务候选发布（FL-D303/382/448/451）

生产运行五个独立单元，发布器必须同时停启并核验：

| 单元 | 作用 |
| --- | --- |
| `fundlex-recall-api.service` | FastAPI（含 `/api/workspace/tasks`） |
| `fundlex-recall-worker.service` | 合同修订 Worker |
| `fundlex-compare-worker.service` | 合同比对 Worker |
| `fundlex-guide-worker.service` | 法规指引生成 Worker |
| `fundlex-feishu.service` | 飞书 WebSocket/状态同步 |

发布只接受显式、可审核的候选工作树，不再固定发布 `/home/opencode/fundlex`：

```bash
# 1) 候选冻结：在独立 worktree 完成审阅和测试，记录 commit/tree。
cd /tmp/opencode/fundlex-release-candidate
git status --short
git rev-parse HEAD

# 2) 只做 staging、导入和双 hash 预检，不停服务、不替换部署树。
bash tools/deploy/publish_workspace.sh --source "$PWD" --commit HEAD --dry-run

# 3) 审核 dry-run 的 candidate/release-record.json 和两个 hash，再执行发布。
bash tools/deploy/publish_workspace.sh --source "$PWD" --commit HEAD
```

`--source` 必须指向干净候选；`--commit` 会拒绝 HEAD 不匹配或存在已跟踪未提交改动的工作树。发布器在事务目录写入 `release-record.json`（source、commit、manifest、engine、service、dry_run），并执行：

1. 用部署解释器 staging 导入 `fundlex/api.py`、普通/Compare Worker、Guide Worker、飞书入口，断言所有模块来自候选树；
2. 计算完整文件 manifest、`engine_build()` 与 `service_build()`，写入 `.fundlex-engine-build` / `.fundlex-service-build`；
3. 一次性停五个单元，串行初始化 RunStore、TaskStore、IntegrationStore、CompareStore、GuideGenerationStore、guide/session/auth schema，再按 API→Recall→Compare→Guide→Feishu 顺序启动；
4. 每个单元检查 active、MainPID、cwd、NRestarts，检查启动日志和 capability；切换后再次核对 manifest 与双 marker；
5. 失败时停服务、回滚代码与单元、重启，并校验恢复树 manifest、旧 engine/service marker 和对应 hash 后才写 `recovered`。

**root 侧仍需主 agent 在部署阶段受控替换**：`/usr/local/sbin/fundlex-publish` 是 root-owned 脚本，仓库改动不会自动生效。发布前先同步该脚本，再用只读检查确认：

```bash
bash tools/deploy/check_publish_drift.sh --units
```

该检查只读，发现 root 脚本或五个 unit 与仓库模板不一致时返回非零；不得用截断脚本片段替代。生产旧脚本没有 `--source/--commit/--dry-run` 时，wrapper 会拒绝无参发布，不会退回隐式主工作区。

发布器不替换 `.venv`、`/etc/fundlex-recall.env`、运行时数据或 unit drop-in；数据库迁移是向前兼容的，代码回滚不会撤销 schema。涉及 schema 的发布前必须另行做数据库+对象备份（见 §8）。

**前端入口边界**：生产 V1 的 `compare.html` 已引用 `/static/workspace.js` 并包含工作台表格/统计标记；仓库当前 `app.js`/`compare.html` 与生产仍有分叉，不由本组整树覆盖。整树发布前必须由前端 owner 合并生产 V1 入口和脚本标签，否则 `/api/workspace/tasks` 虽已注册，页面也不会加载 `workspace.js`。`workspace.js` 只依赖 `window.FundLexWorkbench` 的 `json/navigate/epoch/route` 接口和本文列出的 JSON 字段，新增静态入口测试会检查该依赖。

### 5.2 Nginx 上传门禁（FL-D288）

`tools/deploy/nginx-upload-limits.conf.template` 提供 `http{}` 的 `limit_req_zone`/`limit_conn_zone` 和 `server{}` 的普通上传（52m）、指引上传（26m）、法规生成上传（82m，匹配 80MiB 法规解析上限）与比对上传 location。部署步骤：

1. 备份当前站点配置（例如 `cp -p /www/server/panel/vhost/nginx/fundlex.conf{,.bak-$(date +%Y%m%d-%H%M%S)}`）；
2. 把模板的两段 zone 指令放入 `http{}`，location 放入 FundLex `server{}`，且位于通用 `/api/` proxy 之前；
3. 保留现有证书、`client_max_body_size 60m` 和上游地址，先执行 `nginx -t`；
4. 仅在维护窗口 reload，并用登录用户验证普通上传、指引上传、法规生成上传、慢上传/超限请求；不要用真实大包压测生产。

模板只是版本化候选，不自动安装；本仓库不修改 `/www/server/panel` 或生产 Nginx。应用层 `upload_guard` 在 multipart 解析前处理 `/api/guide-generation/runs`，并对已退休的 `POST /api/batches` 直接返回 `RULESET_RETIRED`，Nginx 预缓冲仍是第一道资源边界。


## 6. 运行与容量注意

- 单份合同的调用量取决于命中动作、子节备用定位、原文变体以及实际产物复核窗口；新增流程不能再沿用旧版 5—20 次估计。真实模型按需调用，不需费用/次数审批，不因本地cap停止，账本仅观测。当前示例192次单gateway及共享请求/费用cap仍由旧代码强制执行，属于待整改项，不是用户要求；没有支持0=无限或禁用cap的配置开关，不伪称已解除。每次最多2次HTTP尝试是有限技术重试边界，继续保留。
- 模型并发设为 1，单 worker 每次只处理一份合同。2 个 API 进程负责交互；增加 API 进程不会增加修订并发。先记录每合同耗时、HTTP 尝试、worker 峰值内存与排队长度，待有目标机证据再增加处理并发。
- 上下文上限 20000 字符，输出上限 3000 token，超长章节按段落边界分窗；到窗口上限明确拒绝，不静默截断。这些模型传输参数改变后必须重新取得对应证据并发布规则包。
- 任务查询在服务端聚合任务元数据后筛选，不是数据库 SQL 分页；已验证数百份任务交互，万份规模需另做压测。
- 数据库备份覆盖 MySQL 与 `FUNDLEX_DATA_DIR`；对象存储（S3 等）适配尚未实现，当前为本地磁盘。
- 数据保留/地域、模型固定版本及发布条件仍须核验；费用/调用次数不需审批或预登记上限。20000次/USD50是旧运行时配置示例，不是用户限额；保留账本历史与真实费用记录，不以重置账本冒称解除cap。API限流/并发、上下文token容量、物理资源、无进展保护、供应商真实余额/鉴权故障与业务权限边界不变。

## 7. 安全清单

- `LLM_API_KEY`、数据库密码、bootstrap 管理员密码只经环境注入，不写仓库、不入日志、不入报告。
- `FUNDLEX_AUTH_MODE=password` 时所有 API 需登录令牌；owner 隔离按用户 id 生效。
- 生产身份（OIDC/SSO）接入未实现；本指南的登录为本地账号体系。
- 目录、域、超链接、文本框等非目标区域由结构逻辑保护；跨段/跨 cell/屏障目标失败关闭。
- TLS 信任包 `certifi` 在 `pyproject.toml`/`uv.lock` 中锁定为 `>=2026.10.19,<2027`（当前解析 `2026.10.23`）；这是候选锁文件，生产 `.venv` 仍需在受控部署阶段重建/同步并做 TLS/模型/集成回归，不能把锁更新当成生产已升级。

## 8. 数据库与对象一致性备份（FL-D463/465）

`tools/ops/fundlex_backup.py` 只创建备份和做只读校验，不停止服务、不恢复生产库。生产备份目录、备份子目录均为 `0700`，文件 `0600`，进程 `umask 077`；manifest 同时记录数据库、`data_dir/objects` 的 SHA-256、大小、文件数、创建时间和一致性观察窗口。

```bash
# 维护窗口内先停止 writer，或由运维明确声明 --quiesced；不要把有写入的窗口
# 冒称一致性快照。数据库凭据只从环境文件/环境变量读取，不写入 manifest。
sudo -n /opt/fundlex-recall-first/.venv/bin/python tools/ops/fundlex_backup.py create \
  --backup-root /var/backups/fundlex \
  --data-dir /var/lib/fundlex \
  --quiesced --label before-release

sudo -n /opt/fundlex-recall-first/.venv/bin/python tools/ops/fundlex_backup.py verify \
  /var/backups/fundlex/fundlex-<stamp>-before-release
```

`verify` 校验两个归档的大小/哈希、gzip/tar 可读性、tar 成员路径/链接安全和对象文件数；`--extract-objects /tmp/opencode/fundlex-restore-objects` 只在空目录还原对象用于核对，不会接触生产。数据库恢复演练必须在**独立、空的 MySQL 数据库**中导入 `database.sql.gz`，核对表数和下载产物 hash；不要对生产库执行恢复。当前生产历史备份权限和云备份策略属于待运维核实项，见 `docs/FL_D478_OPERATIONS_CHECKLIST_20261028.md`；本工具不会改写历史备份或删除证据。

## 9. 发布/运维待核实清单

管理面板 `8888`、云安全组、主机 firewall、数据库网络暴露面只做核实记录，不在代码或本指南中改动。核对项、命令和当前未验证边界见 `docs/FL_D478_OPERATIONS_CHECKLIST_20261028.md`。
