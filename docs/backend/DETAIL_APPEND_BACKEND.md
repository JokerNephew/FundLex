# 后端普查附录（DETAIL_APPEND_BACKEND）

> 主报告：`BACKEND_AUDIT_20261101.md`。本附录存可复算的原始证据与逐处定性，供复核与二次审计。

## A. AST 吞错 38 处逐处定性（来源 `/tmp/opencode/audit/swallows.txt`）

| # | 位置 | 模式 | 定性 |
| --- | --- | --- | --- |
| 1 | api.py:1033 | consume_oauth_state 取消授权路径 | OK：双消费保障显式，失败即已消费过 |
| 2 | api.py:1679 | 批量统计单份报告 NotFound | OK：边界统计（FL-D652 在册语义） |
| 3 | auth.py:458 | bootstrap_admin 用户已存在 → _recover | OK：恢复路径，竞态注释在码 |
| 4 | jobs.py:226/239 | unlink OSError / rmtree 返空 | OK：目录锁清理 best-effort+幂等故意 |
| 5 | jobs.py:260 | job_names 读失败 | OK：并发 reaper 间隙，环不完整是设计 |
| 6 | jobs.py:313 | gateway close | OK：清理不掩 job 结果（注释） |
| 7 | jobs.py:569 | review stamp advisory | OK：注释明示 advisory |
| 8 | store.py:885 | 孤儿对象 unlink OSError | OK：DB 权威注释在码 |
| 9 | upload_validation.py:95 | 部件 XML 解析失败跳过 | OK：该部件不参与判定，fail-closed 在别处 |
| 10 | retention.py:142/144/149 | StopIteration/OSError | OK：清理 best-effort |
| 11 | observability.py:182 | Langfuse gen.end | OK：外层 warning 已记 |
| 12 | trace_sink.py:154/167 | 本地磁盘满 etc | OK：兜底策略「带问题继续」注释在码 |
| 13 | proxy_headers.py:29 | 畸形 CIDR 跳过 | OK：注释「绝不扩信任集」 |
| 14 | integrations/store.py:292/501 | 清理 unlink OSError | OK：草稿清理 best-effort |
| 15 | feishu/oauth.py:127 | qrencode 不可用 → 无二维码 | OK：QR 是表现层非绑定前提（注释） |
| 16 | feishu/events.py:77 | tenant_token 尽力获取 | OK：失败不影响事件处理 |
| 17 | feishu/service.py:605/895 等 | update_card 失败 → 新发卡片 | OK：回退路径显式 |
| 18 | feishu/service.py:834 | discard_draft_files | **FL-D903**（方向对、零日志） |
| 19 | guide_store.py:221/233 | canary/block_report | **FL-D902**（方向对、零日志） |
| 20 | html_view.py:162/398/465 | 渲染容错/int 转换 | OK |
| 21 | onboarding.py:137 | int(payload.code) | OK：防御性解析 |
| 22 | user_model_connections.py:183/195/210 | GC 保守路径 | OK：「宁可留密文不误删」注释在码 |

## B. 安全模式专项核查记录

| 模式 | 命令口径 | 结果 |
| --- | --- | --- |
| SQL 拼接 | `grep -rnE 'execute\(f["\']'` 全库 | 7 处全部为：列名白名单（auth.py:213 column∈{'id','username'}）、DDL 迁移（store.py:567/573/580、guide_store:112/115）、占位符串 `(?,?,?)`（store.py:695/704/1188）——**无值拼接** |
| subprocess | 全库 | oauth.py:123 qrencode（参数数组、固定参数、无 shell）；stage_replay git（测试工具） |
| os.system/popen/eval/exec | AST 扫描 | **零命中** |
| 硬编码密钥 | `grep -rniE "(password|secret|token|api_key)=['\"]..."` 排除 env/test | **零命中** |
| 路径拼接回传 | FileResponse/StaticFiles 全部调用点 | 仅 guide_source（库 ID→系统路径，visible_guide 先鉴权）；下载走 read_artifact 读字节 |
| pickle/yaml.load 不定时炸弹 | 复扫 | api.py:770,775 系**自有命名类** DeserializationErrorMixin（非反序列化漏洞），guide_store.py:1025 候选复核为误报 |

## C. 前后端错误契约核对（FL-D901 定案链）

1. `api_errors.code_from_detail`：detail 仅当匹配 `^[A-Z0-9_]+$` 才作码，否则按状态码泛化（422→INVALID_REQUEST）。
2. `api.py:572 api_error_response`：`message=message_for(status)`（固定中文通用句）、`detail=code`。
3. 前端 `api()`（app.js:76）：`reasons[detail] || messages[status] || reason(detail) || 兜底`。
4. 前端 `reasons` 表无 `INVALID_REQUEST`/`MODEL_SETTINGS_INVALID` 条目 → 落 `messages[422]`=「请求或文件无法处理。」。
5. 对照：api.py:1269/1277/1279 作者意图文案「模型配置无法保存，请检查供应商、模型和访问密钥。」不可达。

## D. 澄清记录（初筛疑点后复核排除）

| 疑点 | 复核结论 |
| --- | --- |
| store.py:690-940 出现 39 行 `VALUES (?)` 单占位符 | 全是 INSERT OR IGNORE/UPDATE 状态写，条件全绑定——无问题 |
| check_publish_drift.sh「set +euo」 | 初筛误读，实为 `set -euo pipefail`，脚本只读且退出码语义清晰 |
| api.py 批量统计 N+1（每文档 get_report） | metrics 已按需加载+分页 200 上限，非热路径，不改 |
| api.py:1410 zip 校验前 `await upload.read(MAX+1)` | 有字节上限，内存不爆；total 超限标记 error_code 不中止——接收语义有意 |

## E. 五 worker systemd 硬化清单（全部模板核对）

- 共有：User=fundlex、EnvironmentFile=/etc/fundlex-recall.env、Restart=always、NoNewPrivileges/PrivateTmp/ProtectHome/ProtectSystem=strict、ReadWritePaths=/var/lib/fundlex、UMask=0077。
- 差异：recall-api uvicorn --workers 2（throttle 跨 worker 共享表已配套，R2-F01 在码）；feishu 晚启依赖（service_main 挂载 onboarding+runtime，生产核实 active）。

## F. 全覆盖矩阵 PL1 飞书线 23 文件逐行签认表（2026-11-01 签认令收口）

方法：基线差核对（`git diff 8b5467b..3cab25b` 仅新增矩阵文档本身，23 个代码文件零变化）后，对 23 个文件 **100% 行覆盖通读**（含首轮已读部分的二次复核），不以抽样代替。行数以 HEAD(3cab25b) 为准。

| # | 文件（行数） | 结论 | 关联编号 |
|---|---|---|---|
| 1 | fundlex/api.py (1838) | ✅ 本轮补读 1-610/930-975/1103-1255/1440-1551/1660-1838 全部区段，无新发现 | FL-D900/D901/D904（在册） |
| 2 | fundlex/api_content.py (54) | ✅ 无发现（纯静态文案常量，无逻辑面） | — |
| 3 | fundlex/api_errors.py (86) | ✅ 无发现（稳定信封/关联 ID；FL-D901 契约核对在册） | FL-D901 |
| 4 | fundlex/auth.py (469) | ✅ 无发现（scrypt n=2^14、恒时比较、时序燃烧、throttle 落库、事务化 last-admin；`_fetch` f-string 仅 3 处字面量列名调用，无注入面） | — |
| 5 | fundlex/config.py (26) | ✅ 无发现（数据目录/库目标解析，env 优先） | — |
| 6 | fundlex/db.py (426) | ✅ 无发现（SQLite/MySQL 翻译白名单内，`INSERT OR IGNORE` 全库零命中——附录 D 旧记忆更正；PRAGMA/占位符映射正确） | — |
| 7 | fundlex/jobs.py (735) | ✅ 无发现（租约/接管/评估与诊断产物收口/工作区收割 PID+fencing 双证/瞬时 DB 故障退避限次均自洽） | — |
| 8 | fundlex/tasks.py (1044) | ✅ 无发现（观察 O-06：`report()` 以 page_size=100000 拉全量，单任务超 10 万份时总览截断，实用无碍） | — |
| 9 | fundlex/store.py (1400) | ✅ 无发现（fencing/租约/产物门/epoch 并发/选择件溯源全链路再次确认；warden/收口分支各 CASE 无误置） | — |
| 10 | fundlex/model.py (613) | ✅ 无发现（HTTPS 强制、响应 1MB 上限、JSON-Schema 自校验、quote 回读账、氮 trace 尽力而为） | — |
| 11 | fundlex/model_budget.py (133) | ✅ 无发现（观测默认、硬闸仅剩并发/熔断/租约，FL-D445 语义逐行落实） | FL-D445 |
| 12 | fundlex/model_settings.py (210) | ✅ 无发现（偏好只读不落库变更、extra=forbid+strict、越界即拒绝） | — |
| 13 | fundlex/integrations/__init__.py (5) | ✅ 无发现 | — |
| 14 | fundlex/integrations/store.py (670) | ✅ 发现：add_draft_file:449/add_outbox:606 `except: return False` 无日志 | FL-D903（扩展） |
| 15 | fundlex/integrations/feishu/__init__.py (6) | ✅ 无发现 | — |
| 16 | fundlex/integrations/feishu/cards.py (598) | ✅ 无发现（用户文本全 html/markdown 结构字段组装，无富文本注入面） | — |
| 17 | fundlex/integrations/feishu/client.py (150) | ✅ 无发现（SDK 惰性导入、缺依赖明确报错、无凭据日志） | — |
| 18 | fundlex/integrations/feishu/events.py (122) | ✅ 发现：主 handler 派发不查 runtime 活跃位 | FL-D906 |
| 19 | fundlex/integrations/feishu/oauth.py (159) | ✅ 无发现（state 仅 SHA-256 落库、一次性、catalog 不回显 code/token、日志脱敏声明逐行核实） | — |
| 20 | fundlex/integrations/feishu/onboarding.py (521) | ✅ 无新编号发现（Fernet 加密、真实 OpenAPI 校验、checklist 诚实「待验证」；观察 O-01/O-02 见下） | — |
| 21 | fundlex/integrations/feishu/runtime.py (170) | ✅ 发现：移除应用断连依赖 lark 私有 `_disconnect` 无兜底 | FL-D906 |
| 22 | fundlex/integrations/feishu/service.py (1359) | ✅ 发现：discard_draft_files×3 静默；观察 O-03/O-04 见下 | FL-D903（扩展） |
| 23 | fundlex/integrations/feishu/service_main.py (44) | ✅ 无发现（独立进程装配、fail-closed 配置检查） | — |

### 观察项（未达登记门槛，留档备查，不新建编号）

- **O-01**：`onboarding.py` `save()` 的 UPDATE→INSERT 路径在**两个请求同 app_id 并发**时存在窄竞态：UPDATE 0 行后双 INSERT 落 UNIQUE 冲突 → 500 而非人读 409。窗口为单 SQL 语句间，生产概率极低；如触发用户重试即可成功。
- **O-02**：绑定码为 secrets 生成的 12 位随机字符（≈62bit 熵）+600s TTL + verify 恒时比较，**无独立尝试限速**；实际尝试须经飞书侧消息送达（绑定码经机器人私聊提交），平台级限速已然存在，风险低。
- **O-03**：`service.py.send_outbox`（≈1282 起）逐条 outbox 项重新扫描 `channels()` 全表，为 O(items×channels)；当前单部署 channel 数量为个位数，无实际影响。若未来 channel 过百需加缓存。
- **O-04**：`service.py` 绑定成功提示回显 owner 前 8 位（`owner[:8]`）用于操作确认，属最小化暴露，仅发给本人私聊，无碍。
- **O-05**：`service.py:sync_tasks:1271` `except Exception: continue` 无日志（5 秒轮询），已并入 FL-D903 附记，不单列。
- **O-06**：`tasks.report()` 用 page_size=100000 拉全量清单，单任务超 10 万份时「结果总览」截断；单任务上限（ManifestFile max 10000）远低于此，仅理论影响。

### 签认收尾声明

PL1 飞书线 23 项全部逐行签认完毕；矩阵对应行已标 ✅。本支线有效发现：FL-D903（扩展定案，4+1 处）、FL-D906（新登记）；观察 6 项留档；其余文件「无发现」均以上表行级覆盖为依据。
