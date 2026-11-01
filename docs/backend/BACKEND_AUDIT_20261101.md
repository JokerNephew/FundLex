# 后端非引擎域穷尽代码普查（2026-11-01）

> 令源：第七轮饱和式普查——用户原话「对所有的代码…挨个检查，不要有任何遗漏」。
> 范围：**后端非引擎域**——api 路由 / tasks 生命周期 / 五 worker plumbing / 鉴权会话 / 静态托管 / 部署脚本（tools/deploy）。
> 明确不碰：recall/gg 引擎（recall 线）、compare 比对（比对线）——仅在其 plumbing 与主域交叉处做接口级核对。
> 执行：`qa-backend-audit-20261101` worktree @ 8b5467b；方法 = AST 风险扫描（38 处吞错逐批现场复核）+ 逐文件通读 + 前后端契约交叉核对 + 生产环境事实核对。
> 编号段：FL-D900~919（本次用 900~905；附录 `DETAIL_APPEND_BACKEND.md`）。

## 一、结论先行

| 档 | 数量 | 条目 |
| --- | --- | --- |
| 中高危 | **0** | — |
| 低/观察 | 5 | FL-D900 死代码、FL-D901 中文 422 detail 不可达、FL-D902 canary 静默、FL-D903 草稿清理静默、FL-D904 feishu_health 假探活 |
| 正向确认 | 6 大面 | 注入 / 路径穿越 / 越权 / 密钥管理 / 错误信封 / 部署硬化（见第三节逐项证据） |

**普查范围内不存在需要立即修复的安全或正确性问题。** 五项低风险项均可随对应模块下次改动顺手处理。

## 二、模块×问题矩阵

| 模块（文件:行） | 关注点 | 判定 | 问题编号 |
| --- | --- | --- | --- |
| api.py:1413 上传 `reasons` 字面量 | 死代码 | 定义后零引用（现行用 `exc.code`） | FL-D900 |
| api.py:1269/1277/1279 模型设置 422 | 失败路径用户可读性 | 中文指引被信封泛化吞掉，前端 reason 表无对应 | FL-D901 |
| guide_store.py:221/233 | 静默吞错 | advisory 方向正确但零日志，假干净风险 | FL-D902 |
| feishu/service.py:834 | 静默吞错 | 建卡成功后草稿清理失败零日志 | FL-D903 |
| api.py:1065 feishu_health | 可观测性/异味 | `__import__` 单例测不到独立进程 worker | FL-D904 |
| api.py 全 71 路由 | 认证依赖一致性 | 全部 `Depends(_user/_admin)`，无裸路由 | OK |
| api.py:581-605 错误信封 | 稳定码+通用文案 | code 白名单、日志只记 metadata、Retry-After 透传 | OK（中文 detail 泛化属设计，副作用记 FL-D901） |
| api.py:1397/1643 下载 | 路径穿越 | kind 白名单 → `store.read_artifact` 读字节回 Response（注释明示不回流路径） | OK |
| api.py:1402 上传 | 注入/穿越/DoS | 文件名 `Path().name` 归一、`validate_docx_upload` 验包（ZIP 炸弹/条数比/加密/重复成员）、单件与批量字节上限、client_ids 形状校验 | OK |
| api.py:1799 catch-all + StaticFiles | 静态托管 | 仅前缀重定向，不做文件系统拼接；带后缀请求 404；api/ 前缀 404 防穿透 | OK |
| auth.py 全线 | 会话/密码 | scrypt 2^14、`_burn_password_check` 防枚举、token 仅存 SHA、throttle 跨 worker 共享表（10/300s 登录、10/3600s 注册）、last-admin 事务化、disabled fail-closed | OK |
| api.py:851-927 登录/注册/改密 | 失败路径文案 | 前端按状态码出人话（401/403/429 均有专属文案） | OK |
| proxy_headers.py | 伪头信任 | 默认空信任集、CIDR 白名单、右端走链防走私 | OK |
| tasks.py 生命周期 | 事务/幂等 | 幂等键唯一约束、staged 对象「未 commit 即删」双路径、control 事务+FL-D553 修复注释在码 | OK |
| jobs.py 租约/接管 | worker plumbing | fencing token、lease 心跳、advisory stamp 吞错有注释正当理由 | OK |
| store.py:885 等 OSError 吞错 | 静默吞错 | DB 权威+孤儿对象注释在码，retention 兜底 | OK |
| retention.py | 清理 | 全 OSError best-effort，符号链接防御 | OK |
| upload_guard.py | DoS 防护 | multipart 流式解析部件/字段/字节三层闸、每 IP 上传速率 | OK |
| user_model_connections.py | 密钥管理 | owner 双向绑定、密文封套绑定 owner+id、GC 保守（宁可留密文不误删）三处吞错均有注释正当事由 | OK |
| integrations/store.py | 事件幂等 | dedupe UNIQUE、lease、fencing、草稿文件级 UNIQUE | OK |
| observability.py / trace_sink.py | 观测 | Langfuse emit 失败仅 warning 不炸业务（设计正确） | OK |
| tools/deploy unit×5 | 部署硬化 | NoNewPrivileges/PrivateTmp/ProtectHome/ProtectSystem=strict/UMask 0077/ReadWritePaths | OK |
| nginx-upload-limits 模板 | 网关 | client_max_body 26m、12r/m 限速 burst=4、429 状态 | OK |
| push_with_token.sh / ssh_probe.py / migrate_*.py | 凭据卫生 | token 走文件+临时 credential helper 不回显；无硬编码；无凭据入日志 | OK |
| check_publish_drift.sh | 部署一致性 | 只读、set -euo pipefail、退出码 0/1/2 语义清晰（初筛疑点后复核澄清） | OK |
| 全部 SQL | 注入 | f-string 仅表白名单标识符（auth.py:213 列名白名单、store.py:695/704 占位符串、guide_store:112/115 迁移 DDL） | OK |
| 全库 secrets 扫描 | 硬编码 | 零命中（env/文件引用全覆盖） | OK |

## 三、38 处 AST 吞错复核结论

- **36/38 有意且正确**：advisory 增强（canary/review stamp）、清理兜底（OSError 孤儿对象/retention）、渲染容错（html_view）、防御性解析（int 转换）、保守 GC（密钥宁可留不可删）、卡片更新失败回退新发（feishu×多处）、best-effort tracing。
- **2/38 观察项**：FL-D902（canary/parse_report 零日志）、FL-D903（discard_draft_files 零日志）——方向均正确，仅缺可观测性。
- 扫描器与结果：`/tmp/opencode/audit_scan.py`、`/tmp/opencode/audit/swallows.txt`。

## 四、既有在册项引用（不重复登记）

- **CSP 缺失**：api.py:619 注释自承「strict CSP deferred，FL-D 在册」。
- **慢查询日志**：api.py `log_slow_queries` 中间件已在（SLOW_QUERY 阈值 INFO 级）。
- 测试基线红/脆测（FL-D756/757/758）归前端线册，与本域无关。

## 五、修复优先级建议（均非阻塞）

1. FL-D901（用户可感、高频踩坑点）：稳定码+前端 reason 表补文案，前后端各一处小改。
2. FL-D902/903（可观测性）：三行日志，随对应模块下次改动。
3. FL-D900（死代码）：单删一字面量。
4. FL-D904（运维语义）：先确认监控有无消费 `service_process_active` 再定改法。

## 六、方法与覆盖声明

| 步骤 | 证据 |
| --- | --- |
| AST 扫描全部 32 个在域文件（吞错/eval/os.cmd/subprocess） | `/tmp/opencode/audit/swallows.txt` 38 行 |
| api.py 1838 行全路由通读 + 71 端点认证依赖核对 | 本报告矩阵 |
| SQL/secrets/subprocess/路径拼接 rg 复查 | 第三节零命中记录 |
| 生产事实核对（双服务 active、模板一致性此前 drift 检查工具在库） | tools/deploy/check_publish_drift.sh 复核 |
| 前端错误展示契约交叉核对（信封 code → reason 表） | FL-D901 定案依据 |

**未动用**：引擎内部（recall*.py/guide*.py 核心）、compare 域实现——按域划分归各自线册。
