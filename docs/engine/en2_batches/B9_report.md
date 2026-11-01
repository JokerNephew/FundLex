# 批次B9回报（workspace/checkpoints/retention/trace_sink/observability/proxy_headers/upload_guard/upload_validation/user_model_connections/application_*/fundlex_init/models_init）

来源：子审计员 ses_e69bb1f49（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B9报告

### fundlex/workspace.py
- 结论：✅ 无发现
- ① 只读聚合视图：revision/compare/generation 三类状态归并为 active/attention/completed，派生状态梳理清晰（`_revision` 优先级 completed>paused>running>queued>uploading）。② 数据库失败向上传播（docstring 明示），无静默兜底。③ 面向用户的 attention label 全为中文（"任务已暂停""待补传合同"等），无内部哈希/路径外泄；`id`/`legacy` 属任务标识契约。④ 无 TODO；`legacy-*` 历史批次分支是真实业务路径（batches 表查询有界）。⑤ 抽查：`register_workspace_routes(application, store, _user)` 与 api.py:1713 匹配；`owner_items(..., generation_available=...)` 默认参数贯通一致；`store._connect()` 与 store 内既有用法一致。`date.max` 校验在路由与函数层重复，冗余无害。
- 已知命中：FL-D451（workspace 生产接线，历史部署问题，与当前代码无关）

### fundlex/checkpoints.py
- 结论：✅ 无发现
- ① 任务级模型判断缓存：load 多层次完整性校验（schema/依赖/上下文哈希/quote 回溯原文），save 只收成功且有界的响应。② load 的 except 宽捕获是刻意失效降级并计入 `invalidations`，非静默吞错。③ 无用户可见输出。④ 无 TODO；真实调用点确认：model.py:201、recall_pipeline.py:4838、models/roles.py:187。⑤ `engine_build` 于 store.py:137 存在；`_path` 64-hex 命名与 retention.py 正责声明一致；`bind_checkpoints(directory, dependencies)` 三处签名一致。
- 已知命中：FL-D557 家族（无界增长，已由 retention 治理）

### fundlex/retention.py
- 结论：✅ 无发现
- ① 检查点保留策略（按龄/按量），fail-closed、只动自有命名。② 每层 OSError 均跳过不删，设计明示，合理。③ 仅日志输出。④ 无 TODO；真实调度确认 jobs.py:130 `_prune_storage` 于 Worker 循环调用（jobs.py:268）。⑤ `prune_checkpoints(self.store.root, now=now)` 签名匹配；环境变量与 docstring 三处一致。
- 已知命中：B13 F5（已实现并测试）

### fundlex/trace_sink.py
- 结论：⚠️ 候选发现 1条
- ① 本地 JSONL 追加式 trace 汇，文档级 trace/调用级 generation/评分 score 三类记录。② `_write` 宽捕获有注释声明"tracing must never break a run"，刻意降级。③ 无用户可见输出。④ 无 TODO；接线点真实（model.py:39-41、jobs.py:91）。⑤ `record_generation(trace_seed=…)` 与 model.py 调用签名匹配；`trace_id_for` 与 observability seed 同构。
- 候选发现1：`_CAPTURE_TEXT` 模块级全局在 `trace_document` 内 `global` 改写，非 thread-local，多 worker 线程并发打开 trace 时存在互相覆盖的竞态窗口｜证据 trace_sink.py:196-197 `global _CAPTURE_TEXT; _CAPTURE_TEXT = _env_flag(...)`｜影响：env 运行时不变则无害，测试/动态改 env 时可能串值｜建议：移入线程本地或改为只读快照（报主线判定）
- 已知命中：FL-D085（Langfuse 丢 payload，本模块为其选定 fallback）

### fundlex/observability.py
- 结论：✅ 无发现
- ① Langfuse 可选追踪唯一收口，无 key 纯 no-op。② 全部交互刻意降级为"不追踪"，注释与 FL-D111 修复记录一致（主体异常不再被吞）。③ 无用户可见输出；凭据只进 SDK 不落日志。④ 无 TODO。⑤ `record_generation/record_score/trace_document` 与 model.py、jobs.py 调用签名匹配；`reset_for_tests` 被测试使用。小记：`reset_for_tests` 不复位 `_CAPTURE_TEXT`，无碍。
- 已知命中：FL-D111 类（generator didn't stop after throw()，已修）

### fundlex/proxy_headers.py
- 结论：✅ 无发现
- ① 仅受信代理才采信 XFF，从右向左跳过中继，默认不信任。② 畸形代理条目跳过不放宽信任集，fail-closed。③ 无用户可见输出。④ 无 TODO；被 upload_guard `_client_key` 真实使用。⑤ `client_host(Headers(scope=scope), peer)` 与 upload_guard.py:238 匹配。

### fundlex/upload_guard.py
- 结论：⚠️ 候选发现 2条
- ① ASGI 层请求资源守卫：尺寸/并发/速率/超时/multipart 预算。② 无静默吞错；但**上传失败提示用户可读性不足**：detail 全为英文技术短语。③ 见候选。
- 候选发现1：守护拒绝的 `message` 为英文技术腔（"too many uploads in progress"、"upload request body is too large"），前端无对应 code 映射（app.js:477 回退到 payload.message），用户直见英文｜证据 upload_guard.py:251/317 + `grep UPLOAD_CONCURRENCY_LIMIT frontend/` 无命中｜影响：限流/超时场景用户提示不可读｜建议：报主线判定（前端补映射或后端中文文案）
- 候选发现2：退休路由 410 响应 `detail="RULESET_RETIRED"` 把内部错误码当用户消息回显｜证据 upload_guard.py:299-300｜影响：命中旧 `/api/batches` 的客户端见到裸内部码｜建议：改中性文案（报主线判定）
- 已知命中：FL-D297（413/415 flake，已判环境性并保留记录）；R2-F02/F03/F08（已修）；O4 生产代理层缺口（部署面）

### fundlex/upload_validation.py
- 结论：✅ 无发现
- ① 统一 DOCX 上传校验（魔数/包结构/加密/重复条目/解压炸弹/文件名）。② 拒绝路径全部显式抛 `UploadValidationError`；英文 message 但前端 reason() 有全量中文映射（app.js:23），用户侧可读。③ 无内部信息外泄（`{MAX_FILENAME_BYTES} bytes` 属合理参数说明）。④ 无 TODO；`_ = count` 为刻意的数量上限移除声明。⑤ `has_tracked_revisions`/`validate_batch_limits` 与 delivery/api 调用一致（既有记录佐证）。
- 已知命中：FL-D 系列 .doc 拒收（已实施）、tracked-revisions 转检测职责（7173，已改）

### fundlex/user_model_connections.py
- 结论：⚠️ 候选发现 2条
- ① owner 私有不可变 BYOK 连接：保存→Fernet 信封（绑定 owner+id）→快照引用→GC 孤儿。② 凭据处理安全：SecretStr、parse() 抑制 Pydantic 回显、密钥校验去控制字符、传输 IP 钉死+禁用环境代理与重定向、解密信封绑定校验、错误全部归一为 code 不回显密钥。③ test_connection 全部中文用户可读文案（338-358），api.py:1276 兜底亦为中文。④ 无 TODO。⑤ `_collect_unreferenced` 在 model_settings.py:182/198 真实调用；`gateway` 在 model_settings.py:208 调用；局部 `ConnectionError` 遮蔽内建类属刻意（模块内及外部均按名导入）。
- 候选发现1：PROVIDERS 内置模型清单可能过时（moonshot-v1-8k/32k/128k、glm-4-flash 等为旧代命名），决定前端下拉可选项；离线无法核验供应商现行模型名｜证据 user_model_connections.py:20-35｜影响：新供应商模型无法从下拉选择（custom 可绕过）｜建议：报主线判定，与供应商现行目录核对
- 候选发现2：模块级类名 `ConnectionError` 遮蔽 Python 内建同名异常，外部 `except ConnectionError` 在混杂导入处易误捕/漏捕｜证据 user_model_connections.py:38｜影响：当前调用点均按名导入（api.py:1276），暂无实际错乱，但属可维护性风险｜建议：报主线判定是否更名（如 ModelConnectionError）
- 已知命中：无

### fundlex/application/task_service.py
- 结论：✅ 无发现
- ① 唯一任务编排缝（Web+飞书共用），指引解析+规则开关+模型偏好快照同事务。② `_resolve_guide` KeyError→ValueError(GUIDE_NOT_FOUND) 显式翻译，无吞错。③ 仅错误码，由路由层映射。④ 无 TODO。⑤ `tasks.create(..., model_preferences_factory=...)` 与 tasks.py:104 签名匹配；`snapshot_in_task_transaction(db, owner, mysql=...)` 与 model_settings.py:72 匹配；`guide_store` 三处函数与 ENABLEABLE_STATUSES 均存在。
- 已知命中：无

### fundlex/application/__init__.py
- 结论：✅ 无发现（导出与 task_service 定义一致；被 api.py:51、feishu/service_main.py:13 真实使用）

### fundlex/__init__.py
- 结论：✅ 无发现（仅包文档串与 `__version__`，无导出）

### fundlex/models/__init__.py
- 结论：✅ 无发现（__all__ 六项均存在于 .config/.roles 定义，无死导出）

结尾·批次小结：
1. 13 文件全部逐行读完；9 个文件无发现，4 个文件共 5 条候选（2 条用户可读性/内部码外泄、1 条竞态、2 条报主线判定）。
2. 用户可读性最实的一条：upload_guard 限流/超时英文提示前端无映射，用户直见（app.js:477 回退 message）。
3. trace_sink/retention/checkpoints 均已确认被真实调度（jobs.py worker 循环与 model.py 接线），非半吊子死代码。
4. 凭据链路（user_model_connections）安全设计完整，未发现密钥外泄点。
5. 注意：指令联动的 FL-D894 在 docs/DETAIL_ISSUES_AND_RESOLUTIONS.md 中无命中（grep 空），该编号可能未入册，建议主线核对。
（主线注：FL-D894 于 2026-11-01 第六轮用户令立项 USER_REQUIREMENTS_20261101_SESSION2.md:131，入册编号待 FL-D920 后统一补登。）
