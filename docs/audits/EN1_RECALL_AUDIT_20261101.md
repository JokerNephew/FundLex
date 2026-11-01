# EN1 recall 线全覆盖审计（COVERAGE_MATRIX 签认，2026-11-01，qa-recall-miss 树）

**纪律**：逐文件全覆盖，禁止抽样；✅+发现编号或「无发现」；只读代码；发现入册 FL-D92x（号段待主线裁决，若与他线冲突以主线为准顺延）。
**审计方式**：recall.py / recall_pipeline.py 由独立子会话逐块（≤300 行/块）顺序全读，主 agent 复核其报告并抽查证据行；其余 8 文件由主 agent 亲自逐行全读。
**已读确认**：10/10 文件全读完毕签认（recall.py 11449 行 38 块 + recall_pipeline.py 6677 行 23 块由子会话逐块全读、主 agent 亲核全部发现关键证据行；其余 8 文件由主 agent 亲自逐行全读）。

## 签认总表

| # | 文件 | 行数 | 方式 | 结果 | 发现 |
|---|---|---|---|---|---|
| E1 | fundlex/recall.py | 11449 | 子会话全读+主复核 | ✅ 有发现 | F1(FL-D921)/F2(FL-D922)/F3(FL-D923)/F4(FL-D924)/F5(FL-D925) |
| E2 | fundlex/recall_pipeline.py | 6677 | 子会话全读+主复核 | ✅ 有发现 | F1(FL-D927)/F2~F6(FL-D928)/F7(并入FL-D921)/F8~F11(FL-D929) |
| E3 | fundlex/targeting.py | 1323 | 主亲读 | ✅ 有发现 | FL-D921（同族扩展）、容貌项×1 |
| E4 | fundlex/rule_scope.py | 1248 | 主亲读 | ✅ 有发现 | FL-D921（同族扩展） |
| E5 | fundlex/applicability.py | 290 | 主亲读 | ✅ 无实质发现 | 观察×2 |
| E6 | fundlex/fee_evidence.py | 157 | 主亲读 | ✅ 无实质发现 | 观察×1 |
| E7 | fundlex/fact_evidence.py | 109 | 主亲读 | ✅ 无实质发现 | 观察×1 |
| E8 | fundlex/semantic_evidence.py | 742 | 主亲读 | ✅ 无实质发现 | 观察×2 |
| E9 | fundlex/facts_recovery.py | 271 | 主亲读 | ✅ 无实质发现 | 观察×1 |
| E10 | fundlex/edit_summary.py | 274 | 主亲读 | ✅ 有发现 | F-es1(FL-D926)、观察×1 |

---

## E1 recall.py（子会话全读 11449/11449，38 块；主 agent 抽查 F1/F2 证据行属实）

### FL-D921【高·系统性】指引耦合硬编码遍布确定性通道，新指引静默失效（F1）
rule_id 字面量与现行指引中文文案写死在 survey/触达/合并/site guard/补漏各层；换任意新指引后这些机制不报错不记账、静默失效或 fail-open 放行。主证据：
- `_DELETE_SENTENCE_ANCHORS`（10716-10721）仅 G06/G13/G15/G17 + 中文锚词；入口过滤 `if rule_id not in _DELETE_SENTENCE_ANCHORS`（11197）→ 新指引规则一律无残句补漏通道。
- site guard `_TARGET_ANCHORS`（10157 起）+ **fail-open**：`rule_id not in _TARGET_ANCHORS: return True`（10425-10426）→ 未收录规则任意段落通过。
- `_RULE_TOPIC_TOKENS`（6184 起）按 G-id 硬编码话题词；`_EXAMPLE_GROUP_PATTERNS`（5952-5955）写死示例字母 A/B、C/D；`_G08_ACTUAL_RATE`（10442）、G22 终结锚（7682）、`_G22_ORDERED_ITEM`（10465）、`_G06_SUBSECTION_RE`（1315）。
- 量级：`"G01"-"G22"` 字面量 242 处、`rule_id ==/in` 分支 111 处。
**处置**：架构级修复——规则元数据/锚词从指引解析产物注入而非源码常量（FL-D897 总图原则 3 的系统性复发面）。现状如实：内置 guide 全绿但机制不可迁移。

### FL-D922【中·延迟正确性缺陷】`_ensure_delete_targets_page` 残句一律误挂 operation index 0（F2）
句池来自规则**全部** delete ops（11241-11242/11313-11314），但三处建 Target 写死 `operation_key(rule_id, 0)`（11351/11359/11388）；对照 G17 专用分支正确的 `_rule_operation_key(rule, idx)`（11249/11252）。现状不 live（内置 guide 锚定规则各 1 个 delete op，G05 双 op 不在 anchors 内）；锚定规则在新指引下获第 2 个 delete op 即错挂 → replay 覆盖/ledger 误判。**验证用例**：双 delete-op 假指引断言携带 `:1`。

### FL-D923【低】`derive_fact_statuses` 对缺失 polarity 映射 fail-open 返回 VERIFIED（F3）
`fee_group_status` 在 `fee_polarities is None` 时跳过 UNKNOWN 检查直接 VERIFIED（719-728）；`family_conflict` 同把 None 当无冲突（702-712）；参数默认 None（680）。现不 live（两调用点均传真实 dict）。建议 None→UNKNOWN 或改必填。

### FL-D924【低】`resolve_quote` 尾分隔符容差回退无唯一性校验（F4）
引句末标点差异用 `find_normalized` 取**首个**命中（413-422）；上方 `resolve_source_quote` 对同问题严格要求唯一候选（378-379）。同段两个仅末标点不同的句串会绑错副本；段已定位故低危，属守卫不对称降级。建议非唯一→None。

### FL-D925【低】`span_slice` broad except 吞 location 不存在（F5-1）
8464-8469 `except Exception: return ""`，调用方可能把空串当已取证据。建议收窄 KeyError/DocxError。其余 4 处 broad except（8985-8993/6778-6783/9148-9158/9328-9332）经核为诚实留存或降级路径，排除级留档。

### 排除项（核实非问题，摘录）
`operations_cover_hit` None→fail-open 有注释设计意图；`_repair_fee_quote` `class_name[0]` 仅真实类名到达；`compose_variant` 有界重试+最终拒绝；`assign_target_operations` 吞 RecallError 带 errors 记录；无文件 I/O/网络/eval/subprocess；无 TODO/FIXME。

---

## E2 recall_pipeline.py（子会话全读 6677/6677，23 块；主 agent 亲核 F1~F7 关键证据行属实）

### FL-D927【中·目标归因完整性】inventory 目标被 setdefault 误标为 `T3_open_rule`，"inventory" 默认永不触发（F1）
- 5256 `for target in targets: origins.setdefault(target.target_id, "T3_open_rule")` 在首个 `_target_ledger`（5289）之前，把**所有**尚无 origin 的目标——即全部 inventory 目标（`_inventory` 从不写 origins）——批量标为 `T3_open_rule`；ledger 886 行 `origins.get(target.target_id, "inventory")` 的 inventory 默认因此**永不触发**。
- 对照：survey/survey_satisfied（1468/1474）、rebind（1633/1711）、audit_missed（3215）、sweep 族（3297/3339/3360）、delete_residual_copy（4978）、variant 族（4994/5006/5029）均有显式 origin——仅 inventory 无。
- 影响：报告层 origin 字段系统性失真，inventory 路径的覆盖账永远算到 T3 头上；不影响门禁（origin 仅展示/账本），但违反「目标归因完整性」纪律。
- 处置：setdefault 改为只对 locator 本批新增目标生效（或 `_inventory`/`_collect_targets` 处显式登记 `origins="inventory"`）。

### FL-D928【低】死代码族五项（F2~F6，合一条目治理）
- F2 重复死分支 2903-2912：`elif code in {"AUDIT_VERDICT_MISSING","REVIEW_UNPROVEN"}: VERIFICATION` 与 2903 首支**同条件**永不可达（演进残留，两分支注释含义不同）。
- F3 findings 空转 5561/5607-5610/6098：`findings=[]` 初始化后，pending_findings 追加与 `_apply_artifact_proof_to_findings(findings,...)` 均作用于恒空列表（最终 sweep 到 6144 才重新初始化 findings）；误导读者以为 sweep 成果参与了 claim-replay 前投影。
- F4 `recovery_sweep_unverified` 5721 永为 False → 6082 分支（SWEEP_RECOVERY_UNVERIFIED）不可达（claim recovery 后必有终扫 6144+，旧顺序残留）。
- F5 `no_progress_rounds` 5723/6003/6016 只增/清零、从不读取（死计数器；真正防死循环走 snapshot 比较 6002 与 audit 侧 5343）。
- F6 `if True:` 残迹门 5614（注释自认 intentional，缩进层应消除）。
- 处置：删除/注释明确化，一次小修清掉；删除前确认无测试引用这些标识。

### 扩展 FL-D921 同族证据【最高优先级·脆弱假设】（F7，并入 FL-D921）
编排层对内置指引 rule_id/中文锚词字面量硬编码 10+ 处，新指引不报错、仅静默失去调优辅助（降级为质量损失，同 E3 性质）：`_FEE_SCOPE_RULES={"G15","G16","G17"}`+「销售服务费」锚词（1067/1100）；摘要复制仅 {"G18","G22"}（1221）；G22 scope 豁免（1285）；G01/G03 append-rebind（1287-1300）；satisfied 整段绑定仅 G02/G04（1453-1456）；G16 partial-clause 放行（1922）；G14 veto（1941）；「A类基金份额」字面量↔固定事实名（2161-2166）；class 等价仲裁仅 G02/G04/G08/G11/G18（2292-2333）；NO_GUIDE_SITE 关闭仅 G22/G08/G01（3764-3800）；`_BUSINESS_PENDING_RULES={"G14","G18"}`（4004）；`FUNDLEX_SEMANTIC_V2_RULES` 默认 "G09"（5035）；required terms 仅 G02/G04（5641）；`_quote_confirms_class_facts` 内置中文正则（2427-2432）。
处置并入 FL-D921 架构治理（指引元数据注入/集中注册表+未知 id 告警）。

### FL-D929【低】并发/身份/观测四项（F8~F11，合一条目）
- F8 审计并发 2660-2664：ThreadPoolExecutor 直接共享同一 model 网关，本层无锁，正确性依赖 ModelGateway 线程安全契约（未文档化）；另 3592 模块级 `_DOCUMENT_COMPACT_CACHE` 跨任务共享（id() 键，GIL 下基本安全但属跨运行状态）。
- F9 增量复扫身份键 6318-6319/6179：以 chunk 文本为已扫身份，文本相同而位置集不同的第二窗不复扫（低风险：文本同发现同；键应含 `chunk.locations`）。
- F10 `business_unresolved` 等值过滤 4649：两侧 dict 形态不同，`item not in notices` 恒真（将来形态意外相等会静默漏报一项，仅影响报告展示）。
- F11 `SWEEP_CHUNK_LIMIT` gap 只记一次（3553-3557，注释自认）：多轮 cap 后续次数不可见，观测损失，建议计数聚合。

### 排除项（疑似但核实非问题，摘录）
`_guide_sha` 宽 except 注释明示故意（223-224）；`_apply_artifact_proof_to_findings` 宽 except 落错误码不静默（4281/4294）；residual 解析 worker→诚实失败（5801）；指标/关闭宽 except 仅观测层（6572/6640-6659）；证据未验证入 results 由上游 3005 REVIEW_UNPROVEN 兜住（2705-2720）；audit 上下文超限 fail-closed 重抛（2199-2200）；chunk cap/截断诚实记录（3559-3890）；review_assisted 放行受 4073-4120 全策略硬阻断（4060-4069）；上下文预算溢出记 deferred（5370）；`_finalize_failure` 无误标 final 路径（4436-4449）；mandatory 过包容但方向安全（6162-6164）。

### 区段地图（33 区段，摘要）
95-124 gateway/Stop；131-224 规则扁平化；227-338 窗口盘点；341-473 guide 缺席/scope 账本；476-679 恢复指纹/根因路由；682-870 plan/ledger 桥接；892-1054 `_collect_targets` 去重；1057-1260 物理 scope 闸门；1262-1346 scope gate 标废；1351-1486 survey 补网；1488-1786 跨段重绑；1792-2096 plan/generate；2103-2243 audit 上下文/并发；2245-2531 证据仲裁器族；2534-2813 `_run_audit`；2816-3119 状态合并/恢复上下文；3126-3363 findings 吸收；3370-3547 产物分块；3550-3988 批量截取/站点关闭/`_sweep_batch`；3991-4124 交付门禁；4127-4221 最终遗漏复核；4224-4406 findings 仲裁/`_resolve_pending`；4413-4449 发布/降级；4452-4700 报告渲染；4707-4880 入口/facts/资格；4882-5094 scope/盘点/survey；5095-5263 归因/去重/定位器；5266-5557 write 循环；5559-6143 claim replay 循环；6144-6355 终扫循环；6356-6601 投影/交付；6603-6677 异常分层/finally。

---

## E3 targeting.py（主 agent 亲读 1323/1323）

### 扩展 FL-D921 同族证据
- `_open_operation_candidates.classify` rule_id 专用锚：G12（258-260）/G11（261-262）/G08（263-264）/G13（265-268）/G09（269-276）中文文案写死；append 站点语义写死 销售服务费+支付词（282-288）；G11 跨段拼合特例（345-354）；G05 显式排除（1195/1212-1217）；`_open_rule_quote_ok` G16/G02/G04 特例（490-511）；`target_for_missing_operation`/`targets_for_open_rules` G11 composite 特例（1058-1067/1297-1311）。
- 降级性质评估（与 E1 关键差异）：此处特判锚只提供**优先级**（P1-P4 阶梯的 score 加权），通用 P2/P3 片段锚来自指引自带 old_text/old_text_variants，故新指引下候选阶梯降级为通用形态而非饿死——属「质量损失静默」而非「通道关闭」。仍登记：质量损失无账本可见性。
- 容貌项：`_facts_stub` docstring（995「Facts are irrelevant…」）与 FL-D863 修复后语义不符（该通路现在必须接真实 facts），注释已过时。

### 排除项
`_scan_scope_pages` 游标算术（806-807）经推演 round-trip 正确（base_cursor + len(accepted) == page.next_cursor）；`locate_unresolved_targets` broad except 重抛 INFRA/RESOURCE 合规且入 record；`operation_closed` 文档级缺省快道仍受 replay/证书门约束；`_candidate_context` 半径回退只用于非 open 目标且 coverage 如实记录。

---

## E4 rule_scope.py（主 agent 亲读 1248/1248）

### 扩展 FL-D921 同族证据
- `resolve_rule_scopes` policy 调度表（1187-1204）按 rule_id 字面量分派 definition/class_basics/fee_tax/income/liquidation/purchase 六族——新指引全部落 `_resolve_default`（title 锚+section_fallback，**有设计的通用回退**，优于 E1 形态）；`_KNOWN_TITLES`（108-134）与「收益分配原则/清算剩余资产/申购和赎回的价格」等中文条款标题词（1013/1056/1089）属**合同词表**（跨指引稳定），可接受但应随语料剖析复核覆盖；G06 精确句 fallback 硬编码引入句「不同基金份额类别之间不得互相转换。」（849）为现行指引证词字面量。
- 纪律亮点：resolution 永不抛错（1209-1211 `except Exception` → `_unresolved` + resolution_error evidence，诚实）；「规则永不回退全文」设计红线成立（docstring 与实现一致）。

### 观察
- `_class_definition_leaves`（676-683）：candidates>1 且无一标题携类别词时返回空——有意保守（宁 unresolved 不猜），evidence 如实，非缺陷。

---

## E5 applicability.py（主亲读 290/290）
**无实质发现。** 三态纪律完备：UNKNOWN 永不落任一分支；deterministic→primary→review 链每级 quo te 码验；`resolve` 在 required facts 未 VERIFIED 时提前 fail-closed；`resolve_ledger` FALSE→NOT_APPLICABLE / UNKNOWN→UNRESOLVED 如实，condition_overrides 绑定 branch 身份。
观察：①APPLICABILITY_SCHEMA 与 ARBITRATION_SCHEMA 结构重复（仅多 rejected_evidence 字段且消费侧未读）——可合并，非缺陷；②`branch_key` sha256[:8] 截断碰撞概率对本规模无虞。

## E6 fee_evidence.py（主亲读 157/157）
**无实质发现。** 归属句收窄（FL-D862）与裁量句不证的守护语义在 `_polarities`（费率由…决定仅在字母化 block 内证）与 `fee_value` 无字母闸（仅「费用由…承担」形）两层一致；豁免句式先于 _UNCERTAIN；多币种类名归一不改证据引句；`verify_fee_evidence` 要求原文精确连续quote。
观察：中文费制词表（认购费/申购费/销售服务费/豁免/承担）为**合同词表**非指引词表，跨指引稳定。

## E7 fact_evidence.py（主亲读 109/109）
**无实质发现。** 跨段窗口拼合限制为相邻连续段（FL-D251 来源边界纪律）；枚举动词闸+标签集精确相等+截断反证三层；币种变体基字母归一有 fallback 链；`_name_in_text` 名词宽容不改变类身份。
观察：窗口搜索 O(n²·L) 上界由「joined 超 quote 长即 break」截住，1300 段规模无虞。

## E8 semantic_evidence.py（主亲读 742/742）
**无实质发现。** 批准簿纪律完备：state≠approved 拒消费、guide sha 过期拒、operation 集合空拒（FL-D457 注释在案）、scope 缺失拒、evidence 多份歧义拒；`_approval_binds_target` 物理站点精确比对 location/start/end/exact_quote；`approval_from_target` 对 stale quote 双验（offsets+quote 并验，660-666 注释明确设计原因）。
观察：①`condition_digest` 校验仅在双侧非空时进行——ApprovalBook 未配 digests 时该层防御静默缺席（纵深缺口，调用方责任，非本文件缺陷）；②`EvidenceRef.verify` 对 by_location 用 broad except 但带回错误码 EVIDENCE_LOCATION_NOT_FOUND，可接受。

## E9 facts_recovery.py（主亲读 271/271）
**无实质发现。** 恢复纪律完好：`_candidate_usable` 要求计数改善+每类码验 quote+枚举句完整性；`_merge_candidate` 只取候选费事实不取资格事实；INFRA/RESOURCE 类 ModelError 重抛其余入 attempt.detail（诚实账本）；仲裁仅接受码验 quote 的 candidate 选择。
观察：`_enabled()==False 且 missing 非空`时 final 标签仍 "not_required"（语义略偏，账本展示级）。

## E10 edit_summary.py（主亲读 274/274）

### FL-D926【低-中·展示层诚实性】`verdict_text` 把未知审计判定显示为「通过」
`verdict_text`（约 :121）：`.get(verdict or "", "通过（规则校验＋独立复核）" if verdict else "—")`——verdict 为非空但**不在映射内**的新值（未来 audit 新增判定类如 partial/waived）时落入默认分支，向用户显示「通过」。未知判定应回显原文或「未识别」，不得默认成通过。修法一行：default 分支返回 `str(verdict)`。

### 观察
RULE_SHORT 缺 G21（108-133 表无 G21 键）——有 `rule_title(guide, part)` 兜底显示指引原标题，无害不报错；属表完整性瑕疵。

---

## 汇总
- 新发现登记（FL-D921~929，本线自取号段，待主线裁决冲突）：
  - **FL-D921【高】** 指引耦合硬编码，跨 E1（通道关闭+fail-open）/E2（降级静默 10+ 处）/E3（优先级降级）/E4（通用回退存在但特判族静默失效）四文件同族复发——与 FL-D897 总图原则直接联动，建议架构级治理（指引元数据注入）。
  - **FL-D927【中】** 目标归因污染：inventory 目标被误标 T3_open_rule（origin 字段系统性失真）。
  - **FL-D922【中】** delete 残句一律误挂 operation index 0（延迟正确性缺陷，新指引下 live）。
  - FL-D923/F3、FL-D924/F4、FL-D925/F5、FL-D928（死代码族五项）、FL-D929（并发/身份/观测四项）凡此低危项均有明确小修法。
  - **FL-D926【低-中】** edit_summary.verdict_text 未知判定默认显示「通过」（展示层假阳性，一行修）。
- 排除项与观察项已在各节留存，防止后续重复发现。
