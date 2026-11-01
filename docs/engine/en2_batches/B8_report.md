# 批次B8回报（delivery/artifact_review/frozen/html_view/recall_prompts/variants/qualification/qualification_evidence）

来源：子审计员 ses_e69bbd002（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B8报告

### fundlex/delivery.py（全读 634 行）
- 结论：✅ 无发现
- ① 用户可见交付摘要/二态投影，与 worker 门禁共用 `requires_blocker`，无死代码（`_requires_blocker` 为显式标注的兼容别名）。
- ② fail-closed 矩阵完备：未知码默认阻断、replay failures/truncated/remaining_unknown 均阻断；不存在静默吞错或假 complete 新证据。
- ③ holds 全中文业务文案；`miss_reason_en`/`engine_status`/`code` 机器字段属 FL-D654 已登记的有意设计（次级审计字段），前端 app.js 未消费这些字段。
- ④ 无 TODO/legacy；`VERIFICATION_BLOCKED` 常量同时作状态值与错误码键，两用途均真实使用。
- ⑤ 抽查 `effect_proof_passed(operation_id, obligation_id=kws)` 签名匹配（generation/effects.py:428）；`miss_classification.entries[].en` 与 reconciliation.py:207 字段吻合；pipeline 写入 `business_notices`/`verification_blockers` 均存在。
- 已知命中：FL-D456（jobs/store 侧）、FL-D653/654（本文件已实现的 miss 融合与二态）、历史分类器分歧条目；FL-D894 在集中文档中 grep 无命中（尚未立号）。

### fundlex/artifact_review.py（全读 370 行）
- 结论：⚠️ 候选发现 1条
- ① V3 独立产物语义复核；仅被 `v2_pipeline.py:25` 调用，不在 recall-first 生产路径（jobs.py 走 `process_recall_first`），但 store.py 指纹清单与 rules/release_v2.py 仍引用，非死代码。
- ② `MODEL_SCHEMA_INVALID` 被容器化为本窗口证据失败，其余 ModelError 上抛——非静默吞错；dissent 机制用代码证明推翻模型误判并有注释论证。
- ③ 仅产生复核数据，无用户可见文案。
- ④ 无 TODO/legacy 标记。
- ⑤ 抽查 `.v2` 导入符号（canonical_sha/_rule_text/_event_summary/_check_requirement/_instantiate_slots/profile_facts_text）与 `PROMPT_VERSIONS_V2["artifact_verify"]` 均存在。
- 候选发现1：评估面引用断裂风险｜证据 tools/evaluation/development_gate_reconciliation.py:417-429 只比对旧 JSON 键 `artifact_review_path`，与本模块 v3 产物（actions/windows）不同源｜影响：reconciliation 工具可能校验不到当前产物复核记录｜建议：报主线判定是否属既有旧评测边界。
- 已知命中：无

### fundlex/frozen.py（全读 186 行）
- 结论：⚠️ 候选发现 2条
- ① 磁带/冻结运行完整性与原子写，在 stage_replay、model.py、recall_pipeline、tools 真实使用，非死代码。
- ② load/save/verify 均以 FrozenError 显式失败，无静默吞错；os.link 冲突时比对内容，安全。
- ③ 无用户可见输出。
- ④ 「legacy recordings」注释为有意只读兼容，非半成品。
- ⑤ digest 规范（sort_keys/ensure_ascii）在 _path/load/save 三处一致；verify() 清单复检防注入正常。
- 候选发现1：`_path()` 内局部 `identity` 死代码｜证据 frozen.py:57-59 组装后未参与返回值（return 用 digest(request)），仅 load() 自算同名变量｜影响：无功能，阅读误导｜建议：删除死变量
- 候选发现2：`ModelCassette._locks` 类级字典无界增长｜证据 frozen.py:47-64 按 目录+digest 永久 setdefault 无清理｜影响：长跑 replay 进程内存缓增（量级小）｜建议：报主线判定是否接受
- 已知命中：命中均为 replay 工具/cassette 行为记录，无针对本文件的缺陷条目

### fundlex/html_view.py（全读 491 行）
- 结论：⚠️ 候选发现 2条
- ① 只读 DOCX→HTML 投影，api.py `_project_revision_view` 真实使用；职责单一。
- ② 样式/关系 XML 解析失败回退 `{}`，属渲染降级而非吞错；锚点安全 scheme 白名单到位。
- ③ 修订 title/图形占位均为中文；未发现内部 ID/路径泄漏——但见候选发现1 的用户可见信息缺失。
- ④ 无 TODO。
- ⑤ 与 docx.py 修订 ID 契约存在两处不一致（见候选发现）。
- 候选发现1：manifest 分支丢失 rule_id/section｜证据 html_view.py:380-390（manifest 优先于 plan 重建）与 docx.py:1561-1564（manifest 条目无 rule_id/section 字段）、frontend/app.js:954（仅 rule_id 非空才显示「规则 G0x」）｜影响：当前所有带 revision_manifest 的报告，修订审阅 UI 规则标签静默消失｜建议：manifest 写入时并入 rule_id/section 或投影时回查 plan
- 候选发现2：修订奇偶配对假设与外来修订冲突｜证据 html_view.py:405-441 假定 del=奇数/ins=偶数配对，docx.py:1544-1547 注释明示「Foreign revision ids carry no parity guarantee」｜影响：allow_existing_revisions=True 产物的偶数自带 ins/奇数自带 del 内容在 revisions 清单中可能丢失或错配｜建议：报主线判定（选择性审阅是否覆盖 overlay 产物）
- 已知命中：FL-D087（temp .docx staging，已实现记录）

### fundlex/recall_prompts.py（全读 361 行）
- 结论：✅ 无发现
- ① 模型任务指令/schema 注册表，recall.py 全面使用。
- ② schema 均带 maxItems 上限，符合防截断治理；无失败路径代码。
- ③ 内容为模型指令非用户文案，英文技术表述属合理范围。
- ④ 无 TODO/legacy。
- ⑤ 版本常量与 facts 消费方一致；但 qualification.py 的 `recall_qualification_review_v1` 未入本注册表（见该文件候选发现1）。
- 已知命中：集中文档一条「已实施已发布」记录，无未决缺陷。

### fundlex/variants.py（全读 331 行）
- 结论：⚠️ 候选发现 1条
- ① FL-D655 变体管线，recall.py/recall_pipeline.py 多处真实调用，非死代码。
- ② 分类 fail-closed：认证不过仅降级 ANOMALOUS/IGNORE，不授权删除；MAX_VARIANTS_PER_OPERATION 封顶爆破半径。
- ③ 无用户可见输出；ANOMALOUS 行 code `VARIANT_PENDING_CERTIFICATION` 已在 delivery.py `_KNOWN_ITEM_PREFIXES` 登记（FL-D655 记录为有意）。
- ④ 无 TODO。
- ⑤ `_replace_operations` 私有函数被 recall.py:3416 跨模块导入（私有 API 耦合，均已测试）；`scope.contains` 谓词与 rule_scope.py:76 匹配。
- 候选发现1：`authorized_variant_sentences(rule, operation, before)` 形参 rule 未使用｜证据 variants.py:249-265 函数体只读 operation/before；recall.py:7149 调用方仍按签名传 rule｜影响：接口冗余易误导｜建议：删参或注释声明保留意图
- 已知命中：FL-D655 及 FL-D658 变体管线已实施/已测试记录（docs 行7572-7574）

### fundlex/qualification.py（全读 68 行）
- 结论：⚠️ 候选发现 1条
- ① 排除型产品类型独立认证，recall_pipeline.py:4858 真实调用。
- ② `except Exception` 不吞错：记录 review_error 并将 fund_type 降级 UNKNOWN（fail-closed），ModelError 原样上抛。
- ③ 无用户可见文案。
- ④ 无 TODO。
- ⑤ `facts.fund_type_certification`/`fact_status` 字段与 recall.py:567/575 dataclass 一致；调用签名吻合。
- 候选发现1：prompt 版本/schema 游离于注册表外｜证据 qualification.py:10-12,42 硬编码 SCHEMA 与 `recall_qualification_review_v1`，未入 recall_prompts.PROMPT_VERSIONS 治理清单｜影响：版本治理/cassette 追溯口径不统一｜建议：报主线判定是否纳入注册表
- 已知命中：命中为 qualification 通道/资格状态类条目，无针对本文件缺陷。

### fundlex/qualification_evidence.py（全读 178 行）
- 结论：✅ 无发现
- ① 基本情况/基金投资章节定位与类别取值证据，rules.py/rule_scope.py 真实使用。
- ② 歧义/冲突显式抛 QualificationEvidenceError，rules.py:208-212 转 RuleError，无静默吞错。
- ③ 无用户可见输出。
- ④ 无 TODO。
- ⑤ 抽查类别取值偏移：compact 索引经 `positions` 非同空白字符映射回原文（行167-170），含跨段取值（source=following 时 value_start 归零）逻辑自洽；`_SECTIONS` 词表与 _CHAPTER 正则配套。
- 已知命中：无

### 批次小结
全读 8 文件完成。新增候选 8 条：最实为 html_view 两处（manifest 丢 rule_id 致前端「规则 Gxx」标签消失；修订奇偶配对与外来修订契约冲突，后者报主线判定）；其余多为小型死代码/治理一致性（frozen 死变量与锁表增长、variants 冗余形参、qualification 版本游离、reconciliation 工具新旧产物键不对齐）。交付完整性（delivery）未发现新的不完整交付/假 complete 路径。FL-D894 在集中文档中未立号，请主审计员核实编号口径。
