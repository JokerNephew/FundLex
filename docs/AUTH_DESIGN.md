# FundLex 用户登录与会话设计

本文记录 `fundlex/auth.py` 与 `fundlex/api.py` 中账号/会话能力的实现边界。目标：在不新增第三方依赖的前提下，为工作台提供本地可用的账号登录，并为生产身份接入预留同一契约。

## 表结构（由 `fundlex/db.py` 适配 SQLite / MySQL）

```sql
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,          -- uuid4().hex
    username      TEXT UNIQUE NOT NULL,      -- 3-64 位 [A-Za-z0-9_.-]
    password_hash TEXT NOT NULL,             -- scrypt$n$r$p$salt_b64$hash_b64
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'member',  -- admin | member
    disabled      INTEGER NOT NULL DEFAULT 0,
    created_at    DOUBLE NOT NULL,
    updated_at    DOUBLE NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,             -- SHA-256(token) 十六进制
    user_id    TEXT NOT NULL,
    created_at DOUBLE NOT NULL,
    expires_at DOUBLE NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0
);
```

`create_app()` 启动时对传入的 `data_dir`（或 `auth_db` 参数、`FUNDLEX_AUTH_DATABASE` / `FUNDLEX_DATABASE_URL`）执行建表；数据库不可用时启动失败（fail closed）。默认位置为 `data_dir/auth.db`。

## 密码与令牌

- 哈希：`hashlib.scrypt(n=2**14, r=8, p=1, dklen=32)` + 16 字节 `os.urandom` 盐，存储格式 `scrypt$n$r$p$salt_b64$hash_b64`。验证解析失败、参数越界一律拒绝，比较使用 `hmac.compare_digest`。未知用户名也会执行一次等价 scrypt 计算，避免按响应时间枚举账号。
- 令牌：`secrets.token_urlsafe(32)`，数据库只存 SHA-256 摘要，泄库不可重放。客户端通过 `Authorization: Bearer <token>` 提交。
- 有效期：`FUNDLEX_SESSION_HOURS`（默认 12 小时），`expires_at = created_at + hours*3600`。

## 会话生命周期

1. `POST /api/auth/login`：`users.authenticate()` 常数时间校验；禁用账号拒绝（403），错误凭据统一 401（不区分用户名/密码）。成功后签发令牌。
2. 每个请求由 `_user` 依赖解析令牌 → `sessions.resolve()`（未撤销且未过期）→ 校验账号仍存在且未禁用，返回 `user_id` 作为 owner，保持与 dev 模式一致的隔离语义。
3. `POST /api/auth/logout`：幂等撤销当前令牌。
4. `POST /api/auth/password`：校验旧密码后更新；撤销该账号其它会话，保留当前令牌。
5. 管理员禁用账号时撤销其全部会话；即使会话残留，`_user` 也会因 `disabled` 拒绝。

## 认证模式与端点

| `FUNDLEX_AUTH_MODE` | `_user` 行为 |
|---|---|
| `dev`（默认） | 读取 `X-FundLex-User`（3-128 字符），缺失 401；现有开发身份语义不变 |
| `password` | 读取 `Authorization: Bearer`，无效 401；`/api/auth/*` 与 `/api/admin/*` 生效 |
| 其它值 | 维持 503（生产身份提供方未配置，fail closed） |

- `GET /api/capabilities`：新增 `login_required`。password 模式下未登录时只返回 `{auth_mode, login_required, task_api}` 最小载荷，供登录页判断模式；带令牌时返回完整能力（`login_required` 仍为 `true`，表示该部署要求登录）。
- 账号端点：`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`、`POST /api/auth/password`。非 password 模式一律 404（账号面不激活）。
- 管理员端点：`GET /api/admin/users`、`POST /api/admin/users`、`POST /api/admin/users/{user_id}/disable`。非管理员（含未登录、dev 模式）一律 404，不暴露端点与账号存在性；禁用可用 `{"disabled": false}` 恢复。
- 首个管理员：`FUNDLEX_BOOTSTRAP_ADMIN=user:password`，仅在 users 表为空时创建 admin；密钥只读取一次，不打印、不落盘（仅 scrypt 哈希入库）。格式非法时启动失败而不是静默跳过。

## 生产 MySQL 部署注意

- `fundlex/db.py` 负责把 `?` 占位符与建表语句适配到 MySQL：`CREATE TABLE` 中的 `TEXT` 会自动改写为 `VARCHAR(255)`（键列可用），`INSERT OR REPLACE`、PRAGMA、`BEGIN IMMEDIATE` 等 SQLite 方言也会转换；本模块的 DDL 保持 SQLite 写法即可。
- 建议为 `sessions.token_hash`、`sessions.user_id`、`users.username` 建立索引（SQLite 下 username 的 UNIQUE 已隐式建索引）；`sessions.expires_at` 可加索引以支持定期清理。
- 连接必须启用 TLS 与最小权限账号；账号/会话库与任务库可共库也可分库，但不要放在同步盘。
- Bearer 令牌应只经 HTTPS 传输；浏览器端当前存于 `sessionStorage`（关闭标签页即失效），生产可评估 HttpOnly Cookie + CSRF 防护。
- 过期/撤销会话目前只做逻辑失效，需定期清理（如 `DELETE FROM sessions WHERE expires_at < ? OR revoked=1`）。
- 建议在网关层增加登录限流与审计日志；`FUNDLEX_BOOTSTRAP_ADMIN` 只在首次部署注入，创建后立即从环境移除。

## 未做项（明确排除）

- 邮箱/短信找回密码、自助注册、邮件验证。
- 多因素认证（MFA/TOTP）、WebAuthn。
- OIDC/SSO/企业身份网关对接（`FUNDLEX_AUTH_MODE` 其它值仍 503）。
- 登录失败限流/锁定、验证码、审计事件表。
- 会话滑动续期与"记住我"；角色/权限细粒度（当前仅 admin/member 两种角色）。
- 修改密码后的全端登出通知（仅撤销其它会话，不推送前端）。

## 2026-10-14 变更：按用户要求开放自助注册

上表"自助注册"一项按用户明确要求调整，新增 `POST /api/auth/register`（仅 password 模式）：

- 载荷 `{username, password, display_name?}`；创建 role=member 账号并直接签发会话（与登录同构，前端注册后自动登录）。
- 重复用户名 409；载荷校验失败 422（含试图指定 role 等额外字段）；非 password 模式 404。
- 开关：`FUNDLEX_ALLOW_REGISTRATION=0` 可关闭（关闭时 403，登录页隐藏注册入口）。`/api/capabilities` 新增 `registration_open`，前端据此显示或隐藏注册链接。
- **不做**：邮箱验证、邀请码、注册限流/验证码（维持"未做项"其余部分）。生产网络暴露前建议在网关层加注册与登录限流。
- 前端配套：登录页新增"注册新账号"表单；管理员新增"用户管理"页（账号列表、新建账号、禁用/启用，对应既有 `/api/admin/users` 接口；非管理员不显示入口）。

