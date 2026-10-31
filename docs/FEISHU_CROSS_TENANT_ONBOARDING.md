# 飞书跨企业接入（自有应用）运维说明

> 适用：2026-11-01 起（FL-D780..789）。面向部署/运维与接续开发；终端用户只需要看工作台“设置 → 飞书绑定”里的向导。

## 1. 为什么需要它

FundLex 部署方有一个飞书自建应用，只能被**同一企业**的成员授权。企业外用户扫码时，飞书在授权页直接报“不是一个企业”，浏览器不会回到 FundLex 回调，服务端无法感知或补救。

因此提供第二条路径：用户在**自己的飞书企业**里创建自建应用，把凭证交给 FundLex；FundLex 真实验证后加密保存，并用长连接接收该应用的事件，回复也走该应用。身份绑定仍使用既有“绑定码私聊”机制。

原同企业扫码路径保持不变。

## 2. 用户侧流程（工作台 → 设置 → 飞书绑定）

1. 点“用我的飞书企业连接”。
2. 第 1 步：按页面说明在飞书开放平台创建企业自建应用（需企业管理员）。
3. 第 2 步：粘贴 App ID / App Secret，点“验证并保存”。失败会给出具体原因与直达页面。
4. 第 3 步：按清单添加 3 个权限、启用机器人、事件订阅选“长连接”并添加 `im.message.receive_v1`、发布版本；可“重新检测”。
5. 第 4 步：在飞书私聊该机器人发一句话；页面自动出现绑定码，把绑定码发给机器人即完成。

必需权限（页面可一键复制）：

```
im:message:send_as_bot
im:message.p2p_msg:readonly
im:resource
```

可选：`im:message.pins:write_only`（置顶任务卡）。`application:application:self_manage` 仅用于自动核对权限清单；没有它时页面显示“待验证”，以首条消息作为真实证明。

## 3. 服务端

- 状态与凭证：`feishu_apps` 表（`fundlex/integrations/feishu/onboarding.py`）；由发布脚本 `migrate_schema()` 在部署时创建，API 启动也会补建。
- 加密：复用 `/etc/fundlex-recall.env` 中的 `FUNDLEX_MODEL_SECRETS_KEY`（Fernet）。**无需新增环境变量**；该键缺失时保存接口返回 503，状态页提示重新填写凭证。
- 运行时：`fundlex/integrations/feishu/runtime.py`，由 `python -m fundlex.integrations.feishu.service_main` 启动；每 5s 同步应用列表，为每个应用建一条长连接；连接失败按 15s→300s 退避。
- 路由：`FeishuService._client(tenant_key)` 按事件租户选择应用；找不到时回退部署机器人。
- 状态机：`no_app → ready → waiting_message → active`，配置不全/凭证不可读为 `needs_attention`；心跳 45s 过期视为断开。

## 4. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/integrations/feishu/app` | 当前账号的接入状态、检查项、深链；不含 Secret |
| POST | `/api/integrations/feishu/app/credentials` | 真实验证并保存 `{app_id, app_secret}`；Secret 加密、不回显 |
| POST | `/api/integrations/feishu/app/verify` | 用已存凭证重新向飞书核验 |
| DELETE | `/api/integrations/feishu/app` | 移除应用（断开长连接，保留已完成的身份绑定） |

失败统一返回 `{error_code, message, detail, link, correlation_id}`；`message` 是给用户看的原因，`detail` 是下一步，`link` 是飞书修复页面。

## 5. 排障

| 现象 | 原因 / 处理 |
| --- | --- |
| 保存返回 `FEISHU_APP_CREDENTIALS_INVALID` | App ID/Secret 不匹配或 Secret 已重置；重新复制 |
| 一直“正在建立连接…”，第 3 步事件“待验证” | 事件订阅不是“长连接”、没加 `im.message.receive_v1`、版本未发布，或 worker 未运行 |
| 权限显示“待验证”而非“已完成” | 应用没有 `application:application:self_manage`，无法自动读 scopes；按清单人工确认，收到消息即生效 |
| `FEISHU_APP_SECRET_UNREADABLE` | 部署密钥更换/缺失；让用户点“重新填写凭证” |
| 机器人搜不到 | 机器人能力未启用或版本未发布 |

日志只包含 app_id 和异常类型，不含任何凭证。

## 6. 已验证范围

- 真实飞书 OpenAPI：错误 Secret 诊断、正确凭证的 token/机器人状态/scopes 读取（`scopes_checked=true`）。
- 真实浏览器首次用户路径：入口 → 4 步 → 配置核对 → 绑定码；截图为证（见交付状态文件）。
- 单元/集成：23 项新增 + 既有飞书 43 项。
- **未验证**：没有第二家真实企业账号，“外部企业真实发消息 → 长连接 → 绑定码回绑”需在生产发布后用外部账号补一次。
