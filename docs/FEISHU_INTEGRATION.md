# 飞书企业自建应用接入

FundLex 的飞书 V1 接入只处理机器人私聊。用户先在 FundLex 设置页生成一次性绑定码并在飞书私聊发送 `绑定 绑定码`，或在设置页生成**个人 OAuth 二维码**，用飞书扫码授权后自动绑定当前 FundLex 账号。绑定后可以连续发送多个公开 DOCX，点击卡片中的“确认创建任务”或发送 `确认`，由现有 `TaskApplicationService` 创建正式任务、上传并封存文件；任务仍由持久 Worker 和当前指引处理。

飞书服务是独立进程，FastAPI 不运行阻塞式 WebSocket。服务通过官方 `lark-oapi` 长连接接收 `im.message.receive_v1` 和 `p2.card.action.trigger`，并使用数据库中的事件表和 outbox 表保存去重、状态回传和重试状态。状态卡片包含任务状态、已处理/失败数量和 FundLex 详情 deep link；下载权限仍由 FundLex 登录会话和 owner 校验控制。

## 配置

凭据只允许通过服务进程环境注入：

```ini
FUNDLEX_FEISHU_APP_ID=从部署密钥系统注入
FUNDLEX_FEISHU_APP_SECRET=从部署密钥系统注入
FUNDLEX_PUBLIC_BASE_URL=https://你的工作台域名
```

飞书开放平台自建应用需要启用机器人能力，并在事件订阅中选择长连接模式，订阅消息接收事件和卡片行为事件。应用权限至少要覆盖发送/回复/编辑消息、读取消息附件资源，以及扫码绑定所需的用户资料权限：
- tenant：`im:message.p2p_msg:readonly`、`im:message:send_as_bot`、`im:message:readonly`；
- user：`im:message.send_as_user`、`im:message`、`im:chat:readonly`、`contact:user.base:readonly`。

个人扫码绑定还必须在应用安全设置中配置重定向 URL：

```text
https://<工作台域名>/api/integrations/feishu/oauth/callback
```

二维码由 API 主机的 `/usr/bin/qrencode` 生成 SVG；如果部署环境没有该二进制，接口仍返回授权链接但 `qr_svg` 为空。OAuth 只用于把飞书身份绑定到已登录的 FundLex 账号，不作为 FundLex 登录 SSO。扫描二维码的用户必须在飞书应用可用范围内；企业自建应用仅在同一飞书租户内可用。`/usr/bin/qrencode` 是宿主依赖，发布时需确认存在。

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

1. 用户登录 FundLex 设置页。推荐点击“生成扫码绑定二维码”，用飞书扫描个人二维码并确认授权；也可以生成一次性绑定码后，在飞书与机器人私聊发送 `绑定 <绑定码>`。OAuth `state` 和绑定码均短期有效且只能消费一次。
2. 用户在飞书与机器人私聊发送一个或多个 `.docx` 附件。每个附件都会经过与 Web 上传相同的 DOCX 包校验，并在正式 Task 创建前写入 staging 对象。
3. 用户点击确认卡片或发送 `确认创建`。任务创建使用 Draft 的幂等键；上传、封存或卡片发送中断后，Draft 保留为可重试状态。
4. 用户通过飞书状态卡片查看进度，完成后从详情 deep link 登录 FundLex，按授权下载最终版、修订版和报告。`/tasks/<id>` 会重定向到 V1 的 `/?task=<id>#task` 并自动选中任务。

群聊协作、飞书登录 SSO、自然语言意图和飞书内逐条审查不属于当前版本。OAuth 目前只做“绑定身份”，不替代 FundLex 账号登录。真实生产验收仍必须使用真实飞书用户、真实附件、真实 Worker/模型、真实 DOCX 产物、状态回传、详情查看和授权下载完整走通。

## 可用范围与二维码

企业自建应用只在同一飞书租户内可用。管理员需要把 FundLex 的可用范围设置为“全部成员”或指定部门/成员；不在范围内的人即使拿到二维码也无法使用。全员可见可通过管理后台或 `PATCH /open-apis/application/v6/applications/:app_id/visibility` 设置，查询接口为 `GET /open-apis/application/v2/app/visibility`。修改全员可见使用 `admin:app.visibility` 权限，属于权限扩大，应由管理员确认。

公共机器人二维码只用于打开机器人私聊，内容是：

```text
https://applink.feishu.cn/client/bot/open?appId=<APP_ID>
```

公共二维码不能携带共享绑定码，否则会把多人绑定到同一 FundLex 账号。个人绑定二维码必须由已登录用户在设置页生成，二维码中的 `state` 只对应一个 FundLex 用户。

## 诊断

管理员接口 `GET /api/admin/integrations/feishu/health` 只返回配置存在性、事件/outbox 统计和服务进程是否已安装，不返回 `FUNDLEX_FEISHU_APP_SECRET` 或其他凭据。事件 ID 按 provider、事件 ID 和 payload hash 去重；同一 ID 的不同 payload 会记录为 `INTEGRATION_EVENT_PAYLOAD_CONFLICT`。排查时同时查看：

```bash
systemctl status fundlex-feishu.service
journalctl -u fundlex-feishu.service --since today
```

日志只应记录事件 ID、错误类型和错误码，不应输出消息正文、附件内容、绑定码或凭据。
