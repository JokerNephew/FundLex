# 飞书企业自建应用接入

FundLex 的飞书接入只处理机器人私聊。用户先在 FundLex 设置页生成一次性绑定码并在飞书私聊发送 `绑定 绑定码`，或在设置页生成**个人 OAuth 二维码**，用飞书扫码授权后自动绑定当前 FundLex 账号。绑定后机器人发送“任务中心”卡片并**自动 Pin 置顶**，可办理合同修订、合同对比、法规指引生成、只读诊断/评测，并查看最近任务和回传结果文件。用户不需要先发“菜单”。

产品与体验复核见 [`FEISHU_UX_REVIEW_20261028.md`](FEISHU_UX_REVIEW_20261028.md)。

## 任务中心与命令

| 入口 | 文本命令 | 说明 |
| --- | --- | --- |
| 任务中心 | `菜单`、`任务中心`、`帮助` | 显示任务类型卡片 |
| 合同修订 | `合同修订`、`修订` | 按当前指引修改 DOCX，交付最终版/修订版/报告 |
| 合同对比 | `合同对比`、`对比` | 依次发送左侧原版、右侧对比版 DOCX，创建 Compare 任务 |
| 法规指引生成 | `生成指引`、`法规指引` | 发送法规 PDF/DOCX，创建指引生成 run；审核和发布仍在 Web |
| 只读诊断 | `只读诊断`、`诊断` | 跑完整修订流程，但只交付诊断报告，不交付修改后的合同 |
| 评测 | `评测` | 跑完整修订流程，产出 `evaluation_final`/`evaluation_redline` 和报告；不能作为正式合同 |
| 我的任务 | `我的任务`、`任务` | 最近任务卡片，可查看详情和发送报告 |

所有入口、步骤确认、状态和结果摘要都使用飞书交互卡片。点击任务类型后，卡片**直接提示发送文件**；任务名在创建草稿时按当前时间生成（如 `合同修订 2026-10-28 12:45:30`），不提供命名/改名入口。附件和结果文件仍是普通文件消息，因为飞书卡片 JSON 2.0 没有文件上传/附件选择组件，不能在卡片内直接选文件。一个私聊同时只有一个活跃草稿；点其他任务类型时卡片会提供“取消并开始新任务”。

同一草稿只保留一张可操作卡：发送新卡时旧卡会被改成“卡片已更新”，任务提交或取消后输入卡也会失效，避免用户点旧按钮。

### 文件收集规则

- 点击任务后直接发送文件消息；卡片显示已接收/未接收文件、总大小，并支持逐文件“移除”。
- 修订/诊断/评测：只收 `.docx`，单文件默认 ≤25MB，总大小 ≤50MB；**不再限制单批文件数量**（网页端同步移除 20 个限制）。
- 合同对比：左右各一份 DOCX，单文件 ≤25MB，总大小 ≤50MB；支持“替换左侧/右侧”。
- 指引生成：一份 PDF/DOCX，≤80MB；支持“替换文件”。
- 同一草稿内相同 SHA-256 的文件不会重复添加；下载/校验失败会在卡片提示，不静默丢事件。
- 修订/诊断/评测会预检 Word 修订痕迹和文档保护；带未处理修订的合同会直接提示“先接受/拒绝全部修订并另存”，不会创建必然无交付的任务（Compare 仍允许既有修订，由 Compare 归一化）。
- 取消或提交成功后清理草稿暂存文件；提交后的文件不会混入新任务。取消后会自动重发任务中心卡并更新 Pin，用户可直接开始新任务。

### 合同修订

发送一个或多个 `.docx`，点击“确认创建任务”或发送 `确认`。任务名默认取第一份文件名；确认后不可再向该草稿追加文件。

### 合同对比

1. 点击“合同对比”；
2. 发送左侧（原版）DOCX；
3. 发送右侧（对比版）DOCX；
4. 可交换左右或替换任一侧；
5. 点击“开始对比”或发送 `确认`。

飞书只创建 Compare 任务并展示状态/差异摘要；双栏阅读、逐处选择和生成选择版仍在 `/compare`。状态卡提供 `/compare?task=<id>` 深链。

### 法规指引生成

直接发送法规 PDF/DOCX（默认上限 80 MB），确认后创建 guide-generation run；任务名默认取文件名。生成是长时间、模型密集型任务，完成后状态卡给出 `/guide-generation?run=<id>` 深链；审核、修改和发布仍在 Web，飞书不提供“直接发布规则”按钮。生产环境必须部署 `fundlex-guide-worker.service`。

### 只读诊断 / 评测

- **只读诊断**：跑完整修订流程，交付校验通过后只发布 `report_md`/`report_json`，明确不发布 `final`/`redline`/`working_*`。
- **评测**：完整产物以 `evaluation_final`/`evaluation_redline` 发布，状态为 `evaluation_modified*` 或 `evaluation_unmodified`；正式 `final`/`redline` 一律不可下载。
- 两者都会消耗模型预算；不完整任务只保留工作文件或报告，不能冒充正式合同。

### 任务查询与结果回传

“我的任务”卡片聚合合同修订、合同对比和指引生成任务，按 6 条/页翻页。完成卡可按权限发送最终版、修订版、报告或对比 JSON；多项交付可点“发送全部交付”；超过飞书文件限制或发送失败时回退到 FundLex 深链。所有操作重新校验 `tenant_key + open_id + chat_id + owner`，不信任卡片中的任务 ID。

飞书服务是独立进程，FastAPI 不运行阻塞式 WebSocket。服务通过官方 `lark-oapi` 长连接接收 `im.message.receive_v1` 和 `p2.card.action.trigger`，并使用数据库中的事件表和 outbox 表保存去重、状态回传和重试状态。状态卡片包含任务中文状态、合同进度、交付统计和 FundLex 详情 deep link；下载权限仍由 FundLex 登录会话和 owner 校验控制。若任务完成但没有生成 final/redline（例如合同带修订痕迹或受保护），卡片会显示橙色“任务未生成交付文件”，说明原因并提供“发送报告”，不再用绿色“已完成”掩盖。

## 配置

凭据只允许通过服务进程环境注入：

```ini
FUNDLEX_FEISHU_APP_ID=从部署密钥系统注入
FUNDLEX_FEISHU_APP_SECRET=从部署密钥系统注入
FUNDLEX_PUBLIC_BASE_URL=https://你的工作台域名
```

飞书开放平台自建应用需要启用机器人能力，并在事件订阅中选择长连接模式，订阅消息接收事件和卡片行为事件。应用权限至少要覆盖发送/回复/编辑消息、读取消息附件资源，以及扫码绑定所需的用户资料权限：
- tenant：`im:message.p2p_msg:readonly`、`im:message:send_as_bot`、`im:message:readonly`、`im:resource`（结果文件回传需要上传文件资源）；
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

法规指引生成还需要独立 worker：

```bash
sudo cp tools/deploy/fundlex-guide-worker.service.template /etc/systemd/system/fundlex-guide-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now fundlex-guide-worker.service
```

飞书 API 只会把 run 入队；没有该 worker 时方案会停留在 queued。该 worker 使用与 API/Worker 相同的 `FUNDLEX_DATA_DIR`、`FUNDLEX_DATABASE_URL` 和模型预算配置。

本项目的标准工作区发布器只发布 API/Worker 代码并重启既有服务；安装或启用飞书单元属于一次性的运维动作。后续发布要确认 `fundlex-recall-api`、`fundlex-recall-worker` 和 `fundlex-feishu` 使用同一环境文件和数据目录。

## 用户流程

1. 用户登录 FundLex 设置页。推荐点击“生成扫码绑定二维码”，用飞书扫描个人二维码并确认授权；也可以生成一次性绑定码后，在飞书与机器人私聊发送 `绑定 <绑定码>`。OAuth `state` 和绑定码均短期有效且只能消费一次。
2. 用户在飞书与机器人私聊发送一个或多个 `.docx` 附件。每个附件都会经过与 Web 上传相同的 DOCX 包校验，并在正式 Task 创建前写入 staging 对象。
3. 用户点击确认卡片或发送 `确认创建`。任务创建使用 Draft 的幂等键；上传、封存或卡片发送中断后，Draft 保留为可重试状态。
4. 用户通过飞书状态卡片查看进度，完成后从详情 deep link 登录 FundLex，按授权下载最终版、修订版和报告。`/tasks/<id>` 会重定向到 V1 的 `/?task=<id>#task` 并自动选中任务。

群聊协作、飞书登录 SSO、自然语言意图和飞书内逐条审查不属于当前版本。OAuth 目前只做“绑定身份”，不替代 FundLex 账号登录。真实生产验收仍必须使用真实飞书用户、真实附件、真实 Worker/模型、真实 DOCX 产物、状态回传、详情查看和授权下载完整走通。

当前实现状态（2026-10-28）：多任务卡片、Compare、指引生成、任务查询/回传、诊断/评测代码已落地并受控发布生产；文件优先交互、旧卡失效、自动 Pin、任务分页、卡片回调超时保护、修订痕迹预检已生产发布；`fundlex-feishu`、API、两个 worker 和 `fundlex-guide-worker` 均 active。真实 Feishu Compare 任务已完成，状态卡、报告文件回传和浏览器深链通过；指引 PDF 上传/确认/取消通过，但未启动真实 model run；诊断/评测仅有隔离测试。不能仅凭卡片可点击或隔离测试宣称全部任务类型生产验收通过。真实用户还需用一份**无修订痕迹**的 DOCX 完成“置顶卡 → 发送文件 → 确认 → Worker → 最终版/修订版/报告回传”全链路。

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
