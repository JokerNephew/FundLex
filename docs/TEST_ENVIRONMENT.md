# FundLex Test 环境

本文说明当前独立 Test/Staging 安装的边界、启动方式和验收证据。Test 用于在不改变 Production 的情况下验证前端、FastAPI、持久 Recall Worker、独立 Compare Worker、认证、持久化和真实模型合同交付。

## 固定边界

| 项目 | Test | Production（只读参考） |
| --- | --- | --- |
| 应用目录 | `/opt/fundlex-test` | `/opt/fundlex-recall-first` |
| 数据根目录 | `/var/lib/fundlex-test` | `/var/lib/fundlex` |
| 配置 | `/etc/fundlex-test.env` | `/etc/fundlex-recall.env` |
| 认证数据库 | `/var/lib/fundlex-test/auth.sqlite3` | Production 独立数据库 |
| API | `127.0.0.1:8110` | `127.0.0.1:8010` |
| 公网 Test 入口 | `https://test.8-155-130-168.sslip.io` | `https://fundlex.club` |
| API 服务 | `fundlex-test-api.service` | `fundlex-recall-api.service` |
| Recall Worker | `fundlex-test-worker.service` | `fundlex-recall-worker.service` |
| Compare Worker | `fundlex-test-compare-worker.service` | `fundlex-compare-worker.service` |

Test 配置必须使用 `FUNDLEX_ENV=test`，并且 `FUNDLEX_DATABASE_URL` 为空。模型账本、trace、heartbeat、对象文件、任务数据库、Compare 数据和部署 manifest 都位于 Test 数据根目录下。Test 进程在配置、路径和运行时身份不符合这些边界时 fail closed。

Test 当前使用 password authentication，注册关闭。部署脚本生成的管理员和成员登录信息位于 `/etc/fundlex-test-credentials`，权限为 `0600`；凭据值不写入仓库、文档或日志。

## 本机访问

按当前验收约定，Test 直接使用本机地址：

```text
工作台：http://127.0.0.1:8110/
Compare：http://127.0.0.1:8110/compare
能力检查：http://127.0.0.1:8110/api/capabilities
```

前端资源使用 `/test/` 基址，并由 Test API 同时提供 `/test/assets`、`/test/static` 别名；因此直接打开 `127.0.0.1:8110/` 和深层 React 路由时资源仍可加载，`/test/` 反向代理剥离前缀后则使用标准 `/assets`、`/static` 挂载。运行时 Router/API 仅在浏览器地址为 `/test` 时使用 `/test` 路由前缀。两种入口共用 Test 服务和 Test 数据边界。

最近一次本机静态检查：工作台首页、JS、CSS 和 Compare 页面均 HTTP 200；`/api/capabilities` 返回 `environment=test`、`registration_open=false`。Chromium Compare 真实浏览器证据位于 `/tmp/opencode/fundlex-browser-evidence/local-e2e.json`，登录、上传两份 DOCX、持久 Compare Worker、结果查看、1 处修改和 `覆盖完整` 均通过，页面/控制台/HTTP 错误为 0。

## 公网访问

当前可直接打开 Test 工作台：

```text
https://test.8-155-130-168.sslip.io/
```

该入口由服务器 Nginx 独立反代到 `127.0.0.1:8110`，使用 Test 专用 Let's Encrypt 证书，HTTP 会跳转到 HTTPS。入口的 `/api/capabilities` 必须返回 `registration_open=false`；Production 入口 `https://fundlex.club/` 继续反代到 `127.0.0.1:8010`。

当前链接使用 `sslip.io` 的 IP 解析服务，因此无需修改 `fundlex.club` 的 Production DNS。若需要正式的 Test 子域名，应在 DNS 服务商新增 `test.fundlex.club A 8.155.130.168`，再为该名称单独申请证书；不能把 `fundlex.club` 改指向 Test。

## 部署与服务操作

在当前 Linux 云服务器工作区执行：

```bash
cd /home/opencode/.local/share/opencode/worktree/29a9a9/full-stack-test-environment
sudo -n true
bash tools/deploy/deploy_test.sh
```

部署脚本执行前检查 Test 配置、路径、端口和依赖，然后运行前端检查、后端目标测试，复制代码和构建产物到 `/opt/fundlex-test`，安装三个 systemd unit，启动服务并写入部署 manifest。它不会安装或重启 Production unit。

常用只读检查：

```bash
sudo -n systemctl is-active fundlex-test-api.service fundlex-test-worker.service fundlex-test-compare-worker.service
curl -fsS http://127.0.0.1:8110/api/capabilities
ss -ltnp | rg ':8110|:8010'
sudo -n find /var/lib/fundlex-test -maxdepth 2 -type f -printf '%p\n' | sort
```

Test 健康接口需要登录：

```text
GET /api/health
```

`/api/capabilities` 可匿名读取并必须返回 `environment=test`。健康结果还检查 Test task/auth/Compare 数据库、两个 Worker heartbeat 和模型配置；模型字段为空时，健康状态为 `degraded`，这是配置阻塞的明确结果。

## 认证用户 smoke

smoke 必须使用真实 `.docx`，并且只允许访问 Test API。它执行 capabilities、password login、health、创建任务、上传、seal，然后轮询持久 Worker 的真实文档状态直到 `succeeded` 或 `failed`。终态证据会记录任务状态、文档状态、错误代码、交付状态、报告 URL、报告 JSON 和授权 artifact links。

```bash
.venv/bin/python tools/test_env_smoke.py \
  --base-url http://127.0.0.1:8110 \
  --credentials /etc/fundlex-test-credentials \
  --docx /home/opencode/data/funds_word/<公开合同>.docx \
  --output /tmp/opencode/fundlex-test-smoke.json
```

由于 `/etc/fundlex-test-credentials` 是 root-owned `0600` 文件，实际执行时应由受控 sudo 读取凭据；命令中的 Python 和脚本路径按当前工作区调整：

```bash
sudo -n /home/opencode/fundlex/.venv/bin/python \
  tools/test_env_smoke.py --base-url http://127.0.0.1:8110 \
  --credentials /etc/fundlex-test-credentials \
  --docx /home/opencode/data/funds_word/<公开合同>.docx \
  --output /tmp/opencode/fundlex-test-smoke.json
```

`--output` 是可选的。命令输出和证据文件都不得包含密码；报告可能包含合同处理元数据，应按公开合同授权范围保存。通过公网入口运行 smoke 时，将 `--base-url` 改为 `https://test.8-155-130-168.sslip.io`。模型缺失时，smoke 仍会记录 Worker 的实际失败终态，例如 `MODEL_CONFIG_MISSING` 与 `delivery_status=not_generated`，不能把该结果解释为合同交付成功。

## Test 重置

重置只允许作用于固定 Test 数据根目录。默认是 dry-run：

```bash
bash tools/deploy/reset_test_environment.sh
```

确认需要清空 Test 任务、对象、账本、trace、Compare 数据和认证库后执行：

```bash
bash tools/deploy/reset_test_environment.sh --apply
```

该命令会停止三个 Test 服务、清理 `/var/lib/fundlex-test` 子项、重新创建 Test 用户并启动三个 Test 服务。它拒绝 Production 配置、路径、服务名和端口。

## 当前验收边界

已验证的基础链路包括 Test API 身份、独立数据库和文件根目录、三个持久服务、heartbeat、password login、真实 DOCX 上传与 seal、Worker 终态错误报告，以及 Compare API → Compare Worker → 持久结果 → 授权查看和成员/admin 权限隔离。

当前 Test 已按用户要求复用 Production 的模型连接配置、模型名、密钥、预算/超时、请求选项和可观测性配置；模型请求产生的账本和 trace 仍写入 Test 专属路径。Production 的数据目录、认证库、账本、trace、端口和服务没有复制到 Test。配置同步前会创建 root-only 备份，并通过路径和环境身份校验。公网入口配置只增加了独立 Test Nginx server block 和 Test 专用证书，没有修改 Production server block。

配置同步后的真实 Test 任务已完成模型调用，但该公开合同结果为 `incomplete`，有 43 个 unresolved，生成 `working_final`、`working_redline` 和报告。模型配置已可用不等于合同内容已经完整交付；仍需按实际文件、修订和报告完成业务复核。

已运行的真实 Compare 合同包含 header、footer 和 drawing 等当前 Compare 不支持的可见内容，结果被正确标为 `incomplete`，并报告 `UNSUPPORTED_VISIBLE_CONTENT`。这证明边界被显式暴露，不构成完整 Compare 交付通过。

本机 React 工作台的全新浏览器登录→新任务→真实 DOCX 上传→seal→Worker→结果页→修订复核→下载仍需由分阶段证据闭合；此前一次 120 秒脚本窗口未写出最终证据，不能算通过。支持正文内容的 Compare 完整成功例已通过，当前不支持 header/footer/drawing 的 incomplete 边界结果继续保留。

部署 manifest 当前记录 Test commit `f59c4521d4a4c34e32feacf6999756e3fc783dc0` 和 `dirty=true`；该 Test 安装尚未达到可发布的干净版本。模型-backed DOCX 修改和既有真实任务的结果页/授权下载已经通过服务端路径验证，但该合同仍为 `incomplete`，不能把 working 文件称为完整最终合同。
