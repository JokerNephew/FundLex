# 服务器常驻 OpenCode agent（安装记录）

日期：2026-10-15。执行：接续 agent（子 agent 安装，主 agent 复核汇报）。
性质：**已实施并验证**（安装、常驻、真实调用冒烟通过）；未提交 git，未改动应用部署。

> 说明：因开发 agent 正在使用仓库，本次未写入 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`（避免并行修改冲突）。请由主/开发 agent 将本记录合并为集中问题条目的引用，或在开发暂停后由本 agent 补登记。

## 目的

让 agent 工作不受用户电脑关机影响：在服务器上常驻一个 OpenCode 服务，随时可从任意设备接入继续对话与开发。

## 安装内容（服务器 8.155.130.168）

| 项目 | 值 |
| --- | --- |
| 版本 | OpenCode **v2.0.29**，`/home/opencode/.opencode/bin/opencode` |
| 专用用户 | `opencode`（uid 1002，非 root，无通用 sudo） |
| systemd 单元 | `opencode.service`（enabled + active，`Restart=always`） |
| 监听 | **仅 127.0.0.1:49374**（loopback，无新增公网端口） |
| 工作区 | `/home/opencode/fundlex`（168 文件 / 5.4MB，快照时间 2026-10-15 10:18:48 CST；不含 `var/`、`funds_word/`、`references/`、`.git`、`.venv`） |
| 提供方配置 | `/home/opencode/.config/opencode/opencode.json`（600）：provider `fundlex`（openai-compatible），模型 `deepseek-v4.1-flash`，baseURL/apiKey 用环境变量替换，**配置文件内不含密钥** |
| 凭据文件 | `/etc/fundlex-opencode.env`（600 root:root，opencode 用户不可读） |
| 发布脚本 | `/usr/local/sbin/fundlex-publish`（root 所有）+ `sudoers.d` 仅允许 `(root) NOPASSWD` 该脚本；工作区包装脚本 `tools/deploy/publish_workspace.sh`（**本次未运行**） |
| 使用说明 | `/home/opencode/README-RESIDENT-AGENT.md` |

## 接入方式（人类）

```bash
ssh -L 49374:127.0.0.1:49374 <FUNDLEX_SSH_USER>@<FUNDLEX_SSH_HOST>
# 服务器上：
su - opencode
opencode service status
opencode pair            # 打印一次性浏览器链接（经隧道在本地打开）
# 或直接 TUI：cd /home/opencode/fundlex && opencode
```

## 验证结果

- `opencode --version` = v2.0.29；`systemctl is-active/is-enabled` = active/enabled；SSH 断开后服务存活（NRestarts=0）。
- 冒烟：2 次真实调用均成功（`PONG`；shell 工具执行 OK），确认走 `providerID: fundlex` / `deepseek-v4.1-flash`，不是免费模型回退。
- **账本说明**：agent 调用**不进入**应用模型账本（`/var/lib/fundlex/model_budget.sqlite` 未变化），但消耗同一账号余额。预算跟踪需把 agent 用量单列。

## 已知限制 / 待确认

1. **重启未实测**（避免影响应用）；开机自启依据 `is-enabled`。
2. 无人值守执行工具需 `--auto` 或配置权限规则；交互式可在界面逐次批准。
3. 工作区无 `.git`/`.venv`（按隔离要求），需要时可自行创建 venv；不能本地 diff/commit。
4. 模型 `limit` 未设置（OpenCode 默认 200k/32k），与真实网关限制未知。
5. 是否给 `opencode` 用户开独立 SSH 登录：当前需先用 root 登录再 `su - opencode`（待用户确认）。
6. 卫生提示：`FUNDLEX_MODEL_EXTRA_HEADERS_JSON` 的值（固定会话标签头，**非凭据**）曾在一次工具输出中出现一次；密钥与 URL 未打印。
7. 密钥轮换时：更新 `/etc/fundlex-opencode.env` 后 `systemctl restart opencode.service`。

## 关闭 / 撤销

```bash
systemctl disable --now opencode.service
userdel -r opencode
rm -f /etc/fundlex-opencode.env /etc/sudoers.d/fundlex-opencode-publish \
      /usr/local/sbin/fundlex-publish /etc/systemd/system/opencode.service
systemctl daemon-reload
```

## 与应用部署的关系

- 常驻 agent 通过 `publish_workspace.sh`（→ root 发布脚本）把工作区代码发布到 `/opt/fundlex-recall-first` 并重启 FundLex 服务；**本次未执行任何发布**，应用与开发 agent 的工作未受影响。
- 流量：服务器在阿里云深圳（中国内地），所有出网流量（含 opencode 模型调用）计「中国内地 20GB/月」额度；模型调用量级为 MB 级，安装为一次性约百 MB 级。
