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

## G. FL-D900~906 分级处置提案 v2（总攻令口径：A/B/C 三级+现象/位置/建议逐条）

行号以签认基线 HEAD(3cab25b) 为准。FL-D905 为正向结论归档，无处置项。
分级口径：**A=可直修**（线内代码即可，无跨线依赖、无外部事实缺口）；**B=需裁决**（跨线归口或命名需主线定稿）；**C=需用户定**（修法取决于只有用户/运维能答的事实）。

### A 类·可直修（4 项，线内可独立完成）

| 编号 | 现象 | 位置 | 建议修法（一句话） |
|---|---|---|---|
| FL-D900 | 上传路由内构造九项「旧错误消息→错误码」映射，全文件从未被读取，现行路径已直接用 `UploadValidationError.code`——演进残留死代码，误导读者以为还有消息串匹配 | `api.py:1413`（`reasons = {...}` 字面量，引用为零静态可证） | 删除该字面量，零行为变化，无需回归 |
| FL-D902 | executability canary 与 block_report 两处 advisory 增强 `except Exception: pass` 无日志，canary 自身坏掉时 needs_review 标记静默消失，审核面假干净无线索 | `guide_store.py:221/233` | 两处各补 `LOGGER.warning(..., exc_info=True)`，best-effort 语义不动 |
| FL-D903 | 飞书线 4+1 处持久化/清理失败静默：建卡后草稿清理失败无迹、draft 文件行/outbox 行写库失败返 False 无日志（凭指纹/dedupe 自愈，但持续故障零痕迹）、5 秒轮询单条 channel 异常每 5 秒静默重试 | `integrations/feishu/service.py:834/899/942`（discard_draft_files)、`integrations/store.py:449/606`(add_draft_file/add_outbox)、`service.py:sync_tasks:1271` | 四处统一补 `warning` 日志（integrations/store.py 新增 module logger；outbox/add_draft_file 带 draft_id/dedupe_key，sync_tasks 带 channel id)，吞错/返值语义不变 |
| FL-D906 | 移除用户自建应用后断连依赖 lark-oapi 私有 `_disconnect`,SDK 缺该方法时静默跳过且 ws.start(auto_reconnect) 不退出；events.py 主 handler 派发不查 `entry["active"]`——「移除即断连」语义有落空缝（现状 SDK 含该方法，非已知缺陷） | `integrations/feishu/runtime.py:146`(_close_socket)、`integrations/feishu/events.py:91`(on_message 派发闭包) | ①`_close_socket` 找不到私有方法时 `log.warning`；②handler 闭包头一行加 `if not entry["active"]: return`；③requirements 锁 lark-oapi 当前版本 |

### B 类·需裁决（1 项，跨线归口）

| 编号 | 现象 | 位置 | 建议修法（一句话） |
|---|---|---|---|
| FL-D901 | 模型设置三处中文 422 detail（查供应商/密钥/HTTPS 的排障指引）被稳定错误信封归为通用 `INVALID_REQUEST`，前端 reason 表亦无该码——用户实际只见「请求或文件无法处理」，排障指引不可达（恰是高频踩坑点） | `api.py:1269/1277/1279` 三处 `HTTPException(422, 中文)`；信封 `api_errors.code_from_detail`；前端 `reason()` 映射表 | 三处改 `raise_api_error(422, "MODEL_SETTINGS_INVALID"/"MODEL_CONNECTION_INVALID")`+前端 reason 表补两条人话译文——需主线裁决：**稳定码命名定稿**+**前端 reason 表归口**（前端线名下，本线只改 api.py 三行） |

### C 类·需用户定（1 项，修法取决于外部事实）

| 编号 | 现象 | 位置 | 建议修法（一句话） |
|---|---|---|---|
| FL-D904 | `feishu_health` 用 `__import__` 探 `active_service()` 判断 worker 存活——API 进程与 worker 是独立 systemd 单元，API 进程内 import 到的单例恒为 None，`service_process_active` 字段长期 false/误导 | `api.py:1065` | 二选一取决于「生产监控是否消费 `service_process_active`」这一只有用户/运维能答的事实：无消费者→改名标记「仅同进程诊断」（A 级工事量）；有消费者→做跨进程探活（worker 心跳行落 integrations store 再聚合） |

### 执行小结（待主线批单后施工）

- A 类 4 项（FL-D900/902/903/906）：合计约 15 行改动+1 个模块 logger，批单后一个 commit 完成，每条附 grep 校验（无 `except Exception` 无日志残留/死代码段消失/私有调用有兜底日志/active 闸在场）。
- B 类 1 项（FL-D901）：等主线定码名与前端归口后，本线只改 api.py 三行。
- C 类 1 项（FL-D904）：请总指挥向运维确认 `service_process_active` 有无消费者，答复即定修法。
