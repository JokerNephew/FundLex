# 飞书企业自建应用接入

FundLex 的飞书 V1 接入只处理机器人私聊。用户先在 FundLex 设置页生成一次性绑定码，再在飞书私聊发送 `绑定 绑定码`。绑定后可以连续发送多个公开 DOCX，点击卡片中的“确认创建任务”或发送 `确认`，由现有 `TaskApplicationService` 创建正式任务、上传并封存文件；任务仍由持久 Worker 和当前指引处理。

飞书服务是独立进程，FastAPI 不运行阻塞式 WebSocket。服务通过官方 `lark-oapi` 长连接接收 `im.message.receive_v1` 和 `p2.card.action.trigger`，并使用数据库中的事件表和 outbox 表保存去重、状态回传和重试状态。状态卡片包含任务状态、已处理/失败数量和 FundLex 详情 deep link；下载权限仍由 FundLex 登录会话和 owner 校验控制。

## 配置

凭据只允许通过服务进程环境注入：

```ini
FUNDLEX_FEISHU_APP_ID=从部署密钥系统注入
FUNDLEX_FEISHU_APP_SECRET=从部署密钥系统注入
FUNDLEX_PUBLIC_BASE_URL=https://你的工作台域名
```

飞书开放平台自建应用需要启用机器人能力，并在事件订阅中选择长连接模式，订阅消息接收事件和卡片行为事件。应用权限至少要覆盖发送/回复/编辑消息以及读取消息附件资源。事件回调地址不配置为 FastAPI 路由；长连接由独立服务建立。

生产环境必须使用与 API/Worker 相同的 `FUNDLEX_DATA_DIR`、`FUNDLEX_DATABASE_URL` 和当前指引配置。服务启动时只检查凭据是否存在，不把凭据写入日志、数据库、报告或本仓库。

## systemd

模板位于 [`tools/deploy/fundlex-feishu.service.template`](../tools/deploy/fundlex-feishu.service.template)。安装时应由运维人员根据实际部署目录和运行用户复制到 `/etc/systemd/system/fundlex-feishu.service`，确认 `/etc/fundlex-recall.env` 已包含上述变量后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fundlex-feishu.service
sudo systemctl status fundlex-feishu.service
```

本项目的标准工作区发布器只发布 API/Worker 代码并重启既有服务；安装或启用飞书单元属于一次性的运维动作。后续发布要确认 `fundlex-recall-api`、`fundlex-recall-worker` 和 `fundlex-feishu` 使用同一环境文件和数据目录。

## 用户流程

1. 用户登录 FundLex 设置页，生成绑定码；绑定码短期有效且只能消费一次。
2. 用户在飞书与机器人私聊发送 `绑定 <绑定码>`。
3. 用户发送一个或多个 `.docx` 附件。每个附件都会经过与 Web 上传相同的 DOCX 包校验，并在正式 Task 创建前写入 staging 对象。
4. 用户点击确认卡片或发送 `确认创建`。任务创建使用 Draft 的幂等键；上传、封存或卡片发送中断后，Draft 保留为可重试状态。
5. 用户通过飞书状态卡片查看进度，完成后从详情 deep link 登录 FundLex，按授权下载最终版、修订版和报告。

群聊协作、飞书 SSO、自然语言意图和飞书内逐条审查不属于当前版本。真实生产验收仍必须使用真实飞书用户、真实附件、真实 Worker/模型、真实 DOCX 产物、状态回传、详情查看和授权下载完整走通。

## 诊断

管理员接口 `GET /api/admin/integrations/feishu/health` 只返回配置存在性、事件/outbox 统计和服务进程是否已安装，不返回 `FUNDLEX_FEISHU_APP_SECRET` 或其他凭据。事件 ID 按 provider、事件 ID 和 payload hash 去重；同一 ID 的不同 payload 会记录为 `INTEGRATION_EVENT_PAYLOAD_CONFLICT`。排查时同时查看：

```bash
systemctl status fundlex-feishu.service
journalctl -u fundlex-feishu.service --since today
```

日志只应记录事件 ID、错误类型和错误码，不应输出消息正文、附件内容、绑定码或凭据。
