# 批次B10回报（models/config|roles / recovery/* / regulatory/*）

来源：子审计员 ses_e69bb1f44（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B10报告

### fundlex/models/config.py
- 结论：⚠️ 候选发现 2条
- ① 活代码：`load_role_config()` 被 model_router/model_settings/build_role_gateway 真实调用。② 异常均抛 RoleConfigError 带变量名，无静默吞错。③ 无用户可见输出，api_key 不写日志（safe_dict 弹出）。④ 无 TODO；L223 `retries if ... is not None` 为恒真防御式冗余（轻微）。⑤ L253 跨端点凭据防护逻辑抽查与预期一致但存在下方绕过。
- 候选发现1：review api_key_env 落空静默继承 primary 凭据并绕过跨端点防护｜config.py:136-138,145,253-258 `api_key = os.environ.get(api_key_env, "")`→`api_key or base.api_key`；guard 的 `explicit_key` 因 `review_entry.get("api_key_env")` 非空为 True｜review 指向异 host 且所命名环境变量未设置时，主端点凭据被发往该 host｜api_key_env 解析为空应报 RoleConfigError 而非回退继承（报主线判定）
- 候选发现2：user_agent 硬编码 "fundlex/0.3.0" 与 pyproject version="0.1.0" 不一致｜config.py:54,159 vs pyproject.toml:7｜对外 UA 版本失真（与 model.py:154 同样 0.3.0，属全库口径）｜统一从包元数据取版本（报主线判定）
- 已知命中：FL-D445/FL-D830 区（roles enforce_limits 默认关）已记录，本文件配置路径与之一致，无恶化。

### fundlex/models/roles.py
- 结论：⚠️ 候选发现 1条
- ① 活代码：recall_pipeline.py:37,113 经 build_role_gateway 走真实路径。② `call()` 不吞错，透传 gateway 异常。③ `roles`/`metrics` 含模型名，属内部观测不直接面向用户。④ 无 TODO/死代码。⑤ 已抽查：`_make_gateway` kwargs 与 model.py:150-155 ModelGateway.__init__ 签名逐项匹配；TASK_ALIASES 与 DEFAULT_TASK_ROLES 键一致。
- 候选发现1：metrics() 就地改写 gateway 内部 event dict｜roles.py:209-213 `base["events"] = list(...) + list(...)` 后 `event["role"] = ...` 修改的是原 dict 引用｜网关观测数据被外部读取方污染，role 字段在 metrics 调用前后表现不同｜拷贝 event dict 再标注（报主线判定）
- 已知命中：FL-D830（用户侧预算文案，前端执行）条目提及 roles.py 读 enforce flag，与现状一致。

### fundlex/recovery/__init__.py
- 结论：✅ 无发现
- ① 纯导出，导出项均被真实使用。②③⑤ 不适用。④ 无死导出（FAILURE_CODE_MAP 等外部有引用）。
- 已知命中：无

### fundlex/recovery/history.py
- 结论：✅ 无发现
- ① 被 orchestrator/recall.py/recall_pipeline.py 真实使用，`_same_subject` 身份归并有明确设计注释（plan §18.3）。② 无异常路径。③ summary() 进报告但字段为受控枚举/ID。④ 无 TODO。⑤ Attempt 字段与 types.py RecoveryAttempt dataclass 一致（抽查 as_dict 15 字段匹配）。
- 已知命中：无

### fundlex/recovery/orchestrator.py
- 结论：⚠️ 候选发现 2条
- ① 活代码：recall_pipeline.py:5305/5717、recall.py:9224 均真实调度 decide/record；`run()` 仅测试引用（tests/test_recovery.py:139），生产仅走 decide/record 手动环——属半使用而非死代码。② handler 异常有记录非静默。③ 见候选1。④ `failure_codes()` 全库（含 tests）零调用，孤儿 helper。⑤ 已抽查：`_strategy_decision` 调 router.py:228 `strategy_for_failure(code, current_tier, content_source, attempt, mode)` 签名匹配；`_STRATEGY_ACTIONS` 键与 RecoveryStrategy 值逐一对应。
- 候选发现1：handler 异常原文进 history detail 可入用户报告｜orchestrator.py:177 `detail = f"{type(exc).__name__}:{exc}"`；recall.py:9236 `return history.summary(context)`｜FL-D894 口径下异常消息可能携带内部路径/变量名至报告｜detail 仅记异常类型名，原文进内部日志（报主线判定）
- 候选发现2：`failure_codes()` 死代码｜orchestrator.py:195-196，全仓库无调用点｜维护噪音｜删除或归入测试工具
- 已知命中：无

### fundlex/recovery/policies.py
- 结论：⚠️ 候选发现 1条
- ① 活代码：Orchestrator 默认 load_policy()。② 配置错误均抛 RecoveryPolicyError（除候选1）。③④⑤ 无异常；limit() 对未知 key fail-closed。
- 候选发现1：单键环境变量 int() 裸解析｜policies.py:86 `overrides[key] = int(raw_value)` 未包 try（与同文件 with_overrides:59-62 不一致）｜运维配错 FUNDLEX_RECOVERY_* 时抛无变量名的裸 ValueError 栈｜包 try 抛 RecoveryPolicyError 并带 env 名
- 已知命中：无

### fundlex/recovery/types.py
- 结论：✅ 无发现
- ① 分类 map 被 recall/recall_pipeline/facts_recovery 等真实使用。② classify 默认 VERIFICATION，fail-closed 不静默放行。③ 错误码仅内部枚举。④ "legacy" 仅为注释。⑤ 抽查：map 中 4 个 MODEL_*BUDGET 显式 RESOURCE 先于 _PREFIX_CLASSES 的 MODEL_→INFRASTRUCTURE 生效，顺序正确；VALIDATOR 码与 generation/validators.py 使用一致。
- 已知命中：FL-D830 裁决记录提及本文件旁路名单保留属合理，不重复。

### fundlex/regulatory/__init__.py
- 结论：✅ 无发现
- ① 导出 ingest/validate 被 guide_generation/pipeline.py:301-302 真实调用。②③④⑤ 无异常。
- 已知命中：无

### fundlex/regulatory/anchors.py
- 结论：✅ 无发现
- ① 活代码：requirements.py:29 用 article_number/split_article_groups。②③⑤ 无异常。④ 无 TODO；正则不处理"第X条之一"等变体属既有口径非 TODO。
- 已知命中：无

### fundlex/regulatory/docx_parser.py
- 结论：✅ 无发现
- ① 活代码（ingestion 分发）。② 解析失败全部 RegulationParseError 带结构化 code，fail-closed（压缩比/展开大小/加密拒绝），无伪造成功。③ 错误面向内部 code，无路径外泄。④ 无 TODO。⑤ SourceAnchor(block_index, xml_path) 与 guide_generation/models.py:74-82 字段匹配。
- 已知命中：无

### fundlex/regulatory/ingestion.py
- 结论：⚠️ 候选发现 1条
- ① 活代码：pipeline.py:301-302 真实路径，validate 同步调用。② 解析异常统一转 RegulationIngestError 保留 code/details，无吞错。③ 无用户文案。⑤ ingest→parse_regulation_docx/pdf(…, source_sha256=digest) 与两解析器签名匹配。
- 候选发现1：DOCX 标题合并段存在死赋值与怪异 for+break｜ingestion.py:61-64 `for block in document.blocks[:consumed]: block.text = merged; break` 后 `document.blocks = document.blocks[consumed:]` 立即丢弃被赋值块｜merged 文本仅存于 document.title，赋值为无效操作，疑似半成品清理残留｜删除死赋值或明确注释意图
- 已知命中：FL-D334（导入路径+PyMuPDF 依赖已修复验证）条目覆盖本包，无新恶化。

### fundlex/regulatory/pdf_parser.py
- 结论：⚠️ 候选发现 1条
- ① 活代码（ingestion 分发至 parse_regulation_pdf）。② 无文本层/页数超限/空块均 fail-closed 报错，无伪造成功；L74 `except Exception` 过宽（MemoryError 等也归为 REGULATION_PDF_INVALID）但 detail 仅记类型名、不吞错。③ 错误 details 只含异常类型名与计数，无路径外泄。④ 无 TODO；L24 "optional dependency" 注释与 pyproject 已强制声明 PyMuPDF 略不符（FL-D334 已修复后的小残留口径）。⑤ parse 产物 RegulationDocument 字段与 models.py:100-110 匹配。
- 候选发现1：pymupdf Document 打开后从不 close()｜pdf_parser.py:73 `document = pymupdf.open(stream=raw...)`，全函数无 close/try-finally｜每次法规 PDF 解析泄漏文档句柄与页面缓存内存，worker 长进程累积｜try/finally 或 contextlib.closing 包裹
- 已知命中：FL-D334（fitz→pymupdf 导入与依赖声明，已验证闭合）。

---
批次小结：12 文件全读毕。recovery 包经 recall.py/recall_pipeline.py 真实调度（orchestrator.run 仅测试路径）；regulatory 包在 guide 生成真实路径。主要候选：config.py review api_key_env 落空致凭据错发并绕过跨端点防护（报主线判定，建议优先）；orchestrator 异常原文可入报告（FL-D894 联动）；failure_codes 死代码；ingestion 死赋值；pdf_parser 资源未关闭。无解析失败伪造成功、无静默吞错。
