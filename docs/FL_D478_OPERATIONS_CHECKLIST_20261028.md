# FL-D478 / FL-D463 运维待核实清单

日期：2026-10-29。范围：只读核实与记录；**不修改**面板、云安全组、firewall、Nginx 生产配置，也不修改或删除历史备份。本文件不是“已修复”或“已收敛”的声明。

主机身份先按 `AGENTS.md` 用事实确认：`hostname`、`ip -4 addr`、`curl ifconfig.me`、实例 metadata。2026-10-28 审查记录的生产主机为 `iZf8zemhifedxdow1zefr0Z`；接续操作前重新确认，不能仅凭内网地址判断。

## 1. 管理面板与网络暴露面（FL-D478）

已只读观察到的事实（来自 `ops.md` O-附加控制核对）：

- BT-Panel 监听 `0.0.0.0:8888`，active firewalld 的 public 区允许 `8888`；Nginx 另有 `888` 监听。
- MySQL 为 `*:3306` 监听，但主机 firewall 未放行 `3306`；这不等于云安全组未放行，也不等于已从公网验证可达。
- 未检查云安全组、面板来源白名单、面板最新安全更新；未从公网扫描，**不宣称公网可利用或已发生攻击**。

待运维核实（只读命令，按实际环境调整）：

```bash
# 监听与主机防火墙（只读）
ss -lntp | grep -E ':(8888|888|3306|8010|8110)\b' || true
sudo -n firewall-cmd --state
sudo -n firewall-cmd --list-all
# 云控制台：核对实例安全组入方向 8888/888/3306/8010 的来源与必要性
# 面板：核对来源 IP 白名单、面板版本/更新、是否必须对公网开放
# 外部端口连通性只能由授权运维从受控外部主机验证，不在本任务执行扫描
```

处置边界：由运维/主 agent 在确认业务需求和来源限制后再决定是否收敛；本仓库不修改 `/www/server/panel`、云安全组、firewalld 或无关系统服务。核实结果应回填集中问题记录，状态从“未验证”改为有证据的结论。

## 2. 历史备份权限与一致性（FL-D463/465）

已记录的历史事实，不在本任务改动：

- `/tmp/opencode/fundlex-compare-revisions-20261028/` 为 `0755 root:root`，其中 `db-before.sql`、`db-before.sql.gz` 为 `0644`；普通非 sudo 账号可读，且包含认证相关表。证据只读统计，未输出凭据值。
- `/var/backups/fundlex` 为 `0755`，抽查旧 gzip 为 `0644`；旧备份完整性/表数也不齐。
- 没有可见的 FundLex backup timer/cron；云备份策略（HBR/控制台）尚未核实，不能断言“没有云备份”。

待主 agent/运维在部署阶段处理：

1. 盘点历史备份副本及可读范围，按证据决定是否轮换会话/口令；不要删除或改写证据文件。
2. 新建备份使用 `tools/ops/fundlex_backup.py`：目录 `0700`、文件 `0600`、`umask 077`，manifest 记录 DB+对象 hash 与一致性窗口。
3. 在独立空库做一次 verified restore（导入 `database.sql.gz`，核对表数/对象 hash/下载产物），记录 RPO/RTO 和最近成功点；不执行生产恢复。
4. 核实云备份策略与保留期；本机没有证据时保持“未验证”，不以 gzip 存在冒充可恢复。

## 3. 发布前仍需 root 侧动作（FL-D303/382/448）

- 仓库 `tools/deploy/fundlex-publish.sh` 是候选；`/usr/local/sbin/fundlex-publish` 仍为生产旧版，必须由主 agent 在部署阶段受控同步/替换，不能用本工作树直接覆盖或重启。
- 同步后用 `bash tools/deploy/check_publish_drift.sh --units` 只读确认 root 脚本和五个 unit 与仓库模板一致；不一致即停止发布。
- 发布器要求显式 `--source`（可选 `--commit`），先 `--dry-run`；五个服务包含 Guide Worker，迁移包含 `GuideGenerationStore`；失败回滚会校验旧 manifest 与 engine/service marker/hash。
- 本任务未执行发布、未重启、未改 `/opt/fundlex-recall-first`、未改 `/etc/fundlex-recall.env`、未改 `/etc/systemd/system` 或 root 脚本。

## 4. 状态

| 项 | 状态 |
| --- | --- |
| FL-D478 面板/云安全组/防火墙 | **未核实，未改动**；待运维按上表只读核对并决定收敛 |
| FL-D463 历史备份权限 | **已记录，未改动**；历史文件仍在原处，待主 agent 部署阶段处理 |
| FL-D465 一致性备份/恢复证据 | **工具候选已提供，生产未执行**；隔离 verify 只验证归档，不等于已完成生产恢复演练 |
| 五服务发布器 | **仓库候选已改，未同步 root、未发布**；root 脚本与生产 unit 仍为旧状态 |
