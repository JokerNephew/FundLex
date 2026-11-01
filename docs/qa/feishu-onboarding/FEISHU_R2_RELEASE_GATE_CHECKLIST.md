# 飞书侧发布守门核对单（R2，PL1 代拟，主线按单实走）

> 用途：R2 发布前后主线逐项勾选；全部 ✅ 才允许宣布「飞书侧上线合格」。
> 原则：每条都是**可勾选**的确定操作 + 确定预期；取证一律只读、凭据不落盘（只引用变量名/文件路径）。
> 顺序即执行顺序；任一条 ❌ → 停在该条处理，不勾后续标记「阻塞」。

## G0 预条件（30 秒）

- [ ] **G0-1** 确认工作机：`hostname` = `iZf8zemhifedxdow1zefr0Z`，工作树 HEAD = 拟发布哈希（记录哈希前 8 位：____）。
- [ ] **G0-2** 提权可用：`sudo -n true && echo ok` → 输出 `ok`。
- [ ] **G0-3** 备份现网配置：`sudo -n cp /etc/fundlex-recall.env /etc/fundlex-recall.env.bak-$(date +%s)` → 无报错（不打印文件内容）。

## G1 代码与部署一致性（发布=同哈希）

- [ ] **G1-1** 发布脚本执行：`bash tools/deploy/publish_workspace.sh` → 输出含发布后哈希，与 G0-1 记录一致。
- [ ] **G1-2** onboarding/runtime 两侧同哈希：`sha256sum /opt/fundlex-recall-first/fundlex/integrations/feishu/onboarding.py /opt/fundlex-recall-first/fundlex/integrations/feishu/runtime.py fundlex/integrations/feishu/onboarding.py fundlex/integrations/feishu/runtime.py` → `/opt` 与工作树两个文件哈希分别相同。
- [ ] **G1-3** 前端锚点在场：`grep -c "feishu-app-" /opt/fundlex-recall-first/frontend/app.js` → ≥ 60（本线实测 64）。
- [ ] **G1-4** 入口文案在场：`grep -o "不是我的企业\|用我的飞书企业连接" /opt/fundlex-recall-first/frontend/compare.html | sort -u` → 两条均出现。

## G2 服务与进程

- [ ] **G2-1** 五单元 active：`systemctl is-active fundlex-recall-api fundlex-recall-worker fundlex-recall-feishu（飞书单名单元名以现场 unit 为准——先 `systemctl list-units 'fundlex*' --no-pager` 列出后逐个核对）` → 全部 `active`。
- [ ] **G2-2** API 存活：`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/health`（密码模式需带会话 token；拿不到时以 401/403 为准，禁止为 000/5xx）→ 200 或 401/403。
- [ ] **G2-3** 飞书运行时挂载：`sudo -n journalctl -u fundlex-recall-feishu --since "-1h" --no-pager | grep -m1 "app runtime sync\|connection started\|registry"` → 有任一运行日志（首启无自建应用时为空属正常，则勾 G2-4 替代）。
- [ ] **G2-4**（G2-3 无日志时）进程内存活：`pgrep -af "feishu\|service_main" | grep -v grep` → 有进程行。

## G3 数据库与存储（只读，凭据只引用变量名）

- [ ] **G3-1** 连库只查结构：`sudo -n bash -c 'set -a; . /etc/fundlex-recall.env; set +a; mysql <参数按$FUNDLEX_*变量装配> -e "SHOW TABLES LIKE \"feishu_apps\""'` → 返回 1 行表名。
- [ ] **G3-2** 列完整：`... -e "SHOW COLUMNS IN feishu_apps"` → 含 `secret_cipher MEDIUMTEXT`、`tenant_key`、`status`、`first_event_at`（FL-D793 迁移在场）。
- [ ] **G3-3** 行数基线：`... -e "SELECT COUNT(*) FROM feishu_apps"` → 记录当前行数（0=未接第二企业，正常；>0=已有人接入，G5 电可靠性证据加分）。
- [ ] **G3-4** 无明文 secret：`... -e "SELECT app_id FROM feishu_apps WHERE secret_cipher NOT LIKE 'gAAAA%' AND secret_cipher NOT LIKE 'enc:%'"`（如加密格式变动以后缀判断）→ 0 行。禁止 SELECT secret_cipher 本身。
- [ ] **G3-5** 对象存储可写余量：`df -h /var/lib/fundlex | tail -1` → 可用 > 预留线（FUNDLEX_MIN_FREE_BYTES 默认 256MB）的 10 倍。

## G4 飞书侧配置（第一企业/部署方机器人，页面操作）

- [ ] **G4-1** 飞书开放平台→部署方自建应用→「事件订阅」= **长连接** 方式；已订阅 `im.message.receive_v1` → 页面可见两项。
- [ ] **G4-2** 机器人能力已启用；已发布版本为生产版本（版本管理页最新状态=已发布）。
- [ ] **G4-3** 权限三项（`im:message`、`im:resource`、`im:chat` 读权限，按向导复制清单=`onboarding.py` guide 所列）在「权限管理」已开启 → 三项状态=已开通。
- [ ] **G4-4** 工作台（任意账号）→ 设置/飞书绑定页可见「不是我的企业」提示与「用我的飞书企业连接」按钮（截图存档 P1）。

## G5 端到端消息流（需要操作者自己的账号；默认第一企业即可，二企业另按 RUNBOOK）

- [ ] **G5-1** 飞书客户端私聊部署方机器人发「你好」→ 机器人回菜单/提示卡（非报错），截图 P2。
- [ ] **G5-2** 绑定码闭环（若当前账号未绑定）：工作台生成绑定码 → 私聊发送 → 页面显示已连接，截图 P3。
- [ ] **G5-3** 私聊发送一份 ≤2MB 真实 DOCX 合同 → 机器人确认受理/排队 → 返回进度→结果链接，截图 P4。
- [ ] **G5-4** 点开结果链接 → 结果页可查看 → 下载修订版/最终版 DOCX，文件可打开且内容与报告改动数一致，截图 P5。
- [ ] **G5-5** worker 日志佐证：`sudo -n journalctl -u fundlex-recall-worker --since "-10m" --no-pager | grep -c -i "secret\|token\|password"` → **0**（凭证零落日志）。

## G6 安全与日志

- [ ] **G6-1** 全单元近 1 小时无凭证：`for u in fundlex-recall-api fundlex-recall-worker fundlex-recall-feishu; do sudo -n journalctl -u $u --since "-1h" --no-pager | grep -c -iE "secret|app_secret|access_token"; done` → 每行 0。
- [ ] **G6-2** onboarding API 不回显 secret：以登录用户 `GET /api/integrations/feishu/app` → 响应 JSON 中无 `secret`明文字段（密文亦不回显）。
- [ ] **G6-3** 无新增 5xx：`sudo -n journalctl -u fundlex-recall-api --since "-10m" --no-pager | grep -c " INTERNAL_ERROR\| 500 "` → 0 或与基线持平。

## G7 回滚点（守门不过时执行）

- [ ] **G7-1** 回滚脚本在场：`ls tools/deploy/ | grep -i "rollback\|restore"` → 记录实际文件名：____（如正式回滚单元缺，发布前必须补）。
- [ ] **G7-2** 配置回档命令可用：恢复 G0-3 的 `.bak-*` 并 `systemctl restart fundlex-recall-api fundlex-recall-worker`（守门失败才执行，平时只确认 .bak 文件存在）。

## G8 守门判定（全部勾完才填）

- [ ] **G8-1** G0–G6 全 ✅ → 守门通过，发布宣布；任一条 ❌/阻塞 → 写明条目与证据后发回主线，不宣布上线。
- [ ] 实测耗时：____ 分钟；执行人：____；日期：2026-__-__。

---

**证据归集**：P1–P5 截图与 G1–G6 命令输出存 `docs/qa/feishu-onboarding/r2-gate/`（凭据与变量值一律不入档）。
**关联**：第二企业真实闭环另按同目录 `REAL_CROSS_ENTERPRISE_RUNBOOK.md` 执行并销 FL-D788；本单只守「发布步骤可执行 + 现网飞书链路不断」。
