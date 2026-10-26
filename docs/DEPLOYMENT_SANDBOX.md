# 生产服务沙箱与 Compare 发布契约

本文件配合 `tools/deploy/production-deployment.conf` 和三个
`tools/deploy/*.service.template` 使用。模板是生产 unit 的仓库内来源；运维
审阅后将它们安装到 `/etc/systemd/system/`。本次变更没有写入生产 `/etc`，也
没有调用发布器或重启服务。

## 已核对的边界

| 项目 | 生产实况/要求 |
| --- | --- |
| 部署目录 | `/opt/fundlex-recall-first`，API/两个 Worker 只读执行 |
| 持久写目录 | `/var/lib/fundlex`，包括 `objects/`、`checkpoints/`、`traces/`、`model_budget.sqlite`、SQLite WAL/运行状态 |
| API 监听 | `127.0.0.1:8010`；公网流量由既有反代转发 |
| 数据库 | `127.0.0.1:3307`，地址族 `AF_INET` |
| 模型/可观测性 | 环境文件指定的 HTTPS 出站端点，地址族 `AF_INET`/`AF_INET6` |
| 本地 IPC | Python/数据库库可能使用 Unix socket，保留 `AF_UNIX` |
| 临时目录 | 每个 unit 独立 `PrivateTmp=true` |
| 环境文件 | `/etc/fundlex-recall.env`，只读注入；凭据不进入仓库模板 |

三个服务都使用 `NoNewPrivileges=true`、`ProtectHome=true`、
`ProtectSystem=strict`、`ReadWritePaths=/var/lib/fundlex`、
`RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6` 和 `UMask=0077`。
`ProtectSystem=strict` 使部署目录和其他主机路径保持只读，唯一声明的持久写
边界与 `FUNDLEX_DATA_DIR=/var/lib/fundlex` 一致。

## 隔离验证

在仓库根目录执行以下命令。它只解析仓库模板，不改变系统 unit，也不触发
服务操作：

```bash
bash tools/deploy/verify_sandbox_templates.sh
```

`verify_sandbox_templates.sh` 会把 `.service.template` 临时复制为合法的
`.service` unit 名称，再运行 `systemd-analyze verify` 和沙箱字段断言；临时文件
位于 `/tmp/opencode`，退出时清理。安装到隔离测试主机后，再对实际 unit 运行：

```bash
systemd-analyze security fundlex-test-api.service \
  fundlex-test-worker.service fundlex-test-compare-worker.service
```

运维安装前应在隔离测试目录替换 `/opt/fundlex-recall-first`、环境文件和
`/var/lib/fundlex` 为测试路径，然后执行：

```bash
systemd-analyze verify /tmp/fundlex-test-units/*.service
systemctl --root=/tmp/fundlex-test-root daemon-reload  # 仅在测试 root 有 systemd 时
```

在已经运行的隔离测试服务上，使用与生产不同的端口和数据目录完成 API 登录、
Compare 上传→seal→Worker→结果查看/下载以及普通 Worker 的写入检查。健康检查
应同时记录三项 `active`、服务的 `MainPID`、部署目录 engine hash 和
`/api/capabilities` HTTP 状态；未认证健康端点返回 401 时需按认证契约判断，
不能单独作为进程失败证据。

## 标准发布与回滚

`tools/deploy/fundlex-publish.sh` 是应安装到
`/usr/local/sbin/fundlex-publish` 的 root 侧来源。它同步代码和三个 unit，固定
同一 engine hash，重启并检查：

```text
fundlex-recall-api.service
fundlex-recall-worker.service
fundlex-compare-worker.service
```

它还检查三个 `MainPID` 使用 `/opt/fundlex-recall-first`、三项均为 `active`、
部署 hash 相同，以及 API `127.0.0.1:8010/api/capabilities` 返回 2xx。运维需
在安装该脚本前审阅 source/destination、unit 列表和环境文件路径；脚本不会改
写环境文件或数据库。

发布前应保存应用目录和三个 unit 的备份，并记录旧 engine hash。若任一服务不
能 active、hash 不一致或 Compare 任务无法被 Worker 领取：停止继续发布，恢复
备份的应用目录和 unit，执行 `systemctl daemon-reload`，再只重启上述三项并复
核三项 active/hash/API。回滚不删除 `/var/lib/fundlex`，也不恢复或覆盖合同
对象、数据库和凭据。
