# FundLex 细节问题与处理记录

> 编号说明（2026-10-27）：历史记录中存在少量重复编号（例如 FL-D365、FL-D297–FL-D299 等），原因是并行工作分别登记。当前不删除、不重编号既有标题，避免破坏历史引用；引用时同时写明标题与日期。新增问题从 FL-D381 起编号，重复编号的归并映射另行处理。
>
> 测试中遇到的业务问题单独汇总在 [`BUSINESS_ISSUES_FROM_TESTS.md`](BUSINESS_ISSUES_FROM_TESTS.md)，与代码/定位缺陷分开维护。

## FL-D445 用户取消模型预算限制并授权按需调用真实模型（2026-10-28）

- 用户原话：“想调模型就调，不用管预算，以后都不要管这预算了”。
- 处理：自本条起，FundLex 整改/评测/端到端验证的真实模型调用不再以费用或调用数cap作为阻塞条件；不因预算问题暂停、询问或判定NO-GO。仍须保留调用/费用记录、账本与运行证据用于分析和回归对比，但**账本只作观测，不再作为停止门禁**。不泄露密钥，不修改无关系统配置，不绕过业务/权限/文件安全边界。
- 与历史记录的关系：FL-D306/FL-D304 等“未登记cap/超支”记录保留为历史事实，不再阻断新运行；`p6_run.py` 的冻结protocol/hash要求可继续用于可追溯性，但额度参数按本授权放宽。此前“真实模型预算阻塞”的NO-GO理由失效，剩余阻塞仅为工程/验收本身。
- 状态：用户授权已记录；后续agent不得再以“预算未批”为由停下。真实调用结果与产物仍需如实登记，不能把调用成功当业务通过。

## FL-D444 语义批准/多叶子scope/证明闭环首批实现（2026-10-28）

- 发现日期：2026-10-28，用户要求按方案开始开发。执行分支 `codex/semantic-engine-remediation-20261028`；本任务前工作树已有约2873行未提交改动，故**本批未提交Git**，以快照 `/tmp/opencode/semantic-remediation-slice-20261028-162300/` 与基线 `/tmp/opencode/semantic-remediation-baseline-20261028-150805/` 保证可恢复；S0基线分离仍待完成。
- 已实现：新增 `fundlex/semantic_evidence.py`（版本化EvidenceRef/SemanticApproval/ApprovalBook/CoverageRecord/guide_fingerprint）；`Target.approval_id`；`approval_book_for()` 在production与frozen replay确定性生成批准；`plan_target`/`_plan_target_inner` 在有效批准下不再被另一套site词表否决；`approved_span_delete` 在模型已选精确句子且代码核验quote/operation/scope后由程序精确删除（不调用模型）。`rule_scope.py` 支持同类多叶子与费用标题/copy_key词族；`structure_index` 默认全量；delete compose重试每次attempt独立校验；`effects.py` 无站点字面缺失默认`EFFECT_SITE_UNPROVEN`并增加G13/G17同义残留探针；重复效果按operation/授权站点收敛。
- 证据：`tools/evaluation/remediation_probe_20261028.py` / `docs/evidence/remediation-probe-20261028.json`（`model_calls=0`）：景宁G05同时含p148/p155（均body）；弘利G17 p784 0调用精确删除“销售服务费可用于……”；G14表述2可绑定；85节全索引；无站点effect为OPEN/UNPROVEN。离线全量 **1846 passed / 13 skipped**；新增 `tests/test_semantic_evidence.py`、`test_rule_scope_multileaf.py`、`test_effect_semantic_residual.py`、`test_claim_duplicate_scope.py`。
- 未完成/边界：S0基线分离与commit；T3/append/audit统一re-quote；事实依赖/语法；pipeline `absent_coverage_by_operation` 接线与`EFFECT_SITE_UNPROVEN`交付分类；12/20/40分页；真实前端、独立标签、真实模型、生产发布与用户E2E。以上均为**离线实现/验证**，不是业务或生产验收；项目仍NO-GO。
- 变更记录：2026-10-28 新增；不修改历史report/gold/manifest/合同。

## FL-D443 待定业务清单误把既有授权、语义判断及结构元数据错误当成新业务决策（2026-10-28）

- **2026-10-28 后续执行方案保存**：用户明确要修复此前列出的语义门禁、scope/标题、上限/分页、结构、证明/交付及补充缺陷，并交由其他模型多agent自主开发测试、掌握进度和版本、中途不询问、完成E2E；本轮不是开工改引擎。已保存 `docs/SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md`（R01–R17、S0–S11、契约/依赖/负例/真实验收/预算/发布回滚）、配套 `docs/NEXT_AGENT_SEMANTIC_ENGINE_EXECUTION_PROMPT_20261028.md` 和进度表。两名只读agent审阅架构及验证发布边界，主agent整合；明确不直接信claimed_operations、不放开范围外修改、不以strict只认字面、不把旧工具/fixture冒充E2E。**状态：方案已保存，整改/测试/真实模型/部署尚未执行**；实际外部阻塞如实NO-GO并落盘，不询问不等于无限费用或擅改冻结分母。

- **2026-10-28 用户后续裁定（优先于下文原“窄条件项”）**：用户原话“不在规则对应的范围之内就不要改”。据此，规则授权范围外保持原文，不为去重、润色或补写额外修改；BIZ-09/10范围外独立句去重问题已决定为不改，不再等待新增授权，也不制造必改义务。范围依据指引、适用条件和完整逻辑条款语义确认，不能用当前程序的漏选scope或planner短切片代替；属于其他规则授权范围的内容应由对应规则处理，不借去重扩权。此次仅更新业务目录、集中记录和交接，未改引擎/合同、未调用模型/部署；状态是**业务边界已确认、工程实现及真实验证待完成**。原先审计结论保留为历史，下一步按此边界核对G11完整条款归属与范围内完整修改、范围外原文保留。

- 发现日期：2026-10-28，用户要求重新检查此前待确定的业务问题哪些是真的，主agent与两名只读agent逐项核对原件、实际合同及历史裁定。
- 问题与影响：G14已授权变体（BIZ-02）、G18缺替换对象/已满足语义（BIZ-03/04）、G15旧例10日与新机制5日（BIZ-06）、自动支付变体（FL-D397）、已有摘要覆盖要求（BIZ-07）、G11完整条款授权（BIZ-09/10）、逐规则适用性和独立标签任务（BIZ-14/15）被混写为待业务批准，掩盖实现问题并反复要求用户决定已经决定的内容。
- 核实证据：指引原件 `references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx` SHA `b77be53c3439d785a9ffad0f09d8d03ba74f7722397576b999ae6f5dd6eef895`，零基段33–34/45–48/59–66/73–84/91–92；完整交接151–165行；生成策略计划§7.3/§10/§39与FL-D104/106/120/132/217/233/356。D06 p1256实际有“四、与基金财产管理、运作有关费用的提取、支付方式与比例”，p1269为“（三）销售服务费”，而p1286 inspection.section_path仍停在“三、基金的收益与分配”；**不能用错误元数据制造标题与内容冲突**。
- 本轮处理：更新 `docs/BUSINESS_ISSUES_FROM_TESTS.md` 的“最新核实结论”及原条目，撤回以上笼统待定归因，区分规则已明确/模型归属核对/工程失败/真正新增授权。G18原句不存在时，不擅自补写、不假称已满足，也不按QDII整份豁免；G15旧支付安排照常删除、新机制按5日落实、差异按既有裁定仅提示；实际摘要对应目标依既有要求分别盘点，技术默认排除不能撤销覆盖。
- 真正保留的窄条件项：**确认某重复句在任何已授权替换/删除条款之外后，是否允许仅为去重额外删除它**。指引G11条款1已含免收费句，不能说永远只授权bearer句；D06 p228–229先做完整条款语义归属复核，尚不能以planner切片或跨段句号断言p229是授权外独立句。本轮不直接推翻FL-D233现有保留措施，更不授权删除。另提“无原句也强制新增G18”、整份QDII/FOF豁免、改新期限或冻结评分分母，才属新增需求，不能当当前必答阻塞。
- 状态与验证：**只读原件/历史裁定复核与文档更正完成；引擎/产物未修复、未部署，无真实模型调用/新增费用。** 摘要一致性有持续项目设计依据，本次未找到用户专门逐字裁定G15–G17摘要同步的原话，不冒称直接用户发言。历史report/gold/manifest保持不变。
- 下一步：按已明确指引和裁定完成模型语义归属、scope覆盖及义务状态整改；仅将新出现、无法由现有授权解决的具体权利义务变化列为新业务问题，不再把错误码或程序未完成直接当待业务决定。

## FL-D441 章节/候选/删除/失败数上限存在局部静默截断，部分补扫仍被 scope 拦住（2026-10-28）

- 发现日期：2026-10-28，用户要求核实严格限制，离线生成小型 DOCX 和脚本响应复现。
- 问题与影响：`structure_index(max_sections=80)` 对85节返回80，尾部10段不进 inventory；section-aware sweep 原先能补出 unassigned 尾段，但 scope-aware sweep 又把无scope窗口跳过。`ensure_delete_targets(limit=20)` 在25处可删句时只补20处；定位候选/上下文最多12处，无通用分页。`replay_claims(max_failures=40)` 某些段落检查到40个失败即break、residual到40即return，45项案例提高上限才检查45。不能将这些数字一概说成“只截报告”，也不能断言局部上限必然导致最终漏改；其他召回/恢复路径可能补回。
- 证据：`recall.py:1124–1148,8852–9057`；`targeting.py:43–93,255–261`；`recall_pipeline.py:3196–3277`；`generation/claim_replay.py:1456–1457,1883,2045–2046`。完整探针、源指纹及复现输出见 `tools/evaluation/strictness_audit_20261028.py` / `docs/evidence/strictness-audit-20261028.json`。
- 现有保护/更正：sweep已有 splits/truncated/gaps/blind_windows，claim上限案例仍 verified=false，不因截断直接通过；32000字符/4000输出token是此前运行配置而非源码固定值，已有上下文拆分和输出截断恢复。`plan_windows` 按整段切窗不截段内文字，超长单段仍可能超过预算；事实上下文会在放不下的段落处break（合成例复现），但本次第一批27份可解析合同在28500字符探针下均未丢所检索的正文销售服务费段，不能虚报这27份已有此漏读。
- 处理方法（建议，未实施）：索引遍历全量；处理批次上限与业务覆盖总量分离，候选/删除/失败通过游标分页、续跑与饥饿保护；每次触顶报告 truncation/remaining/next_cursor，不把预算未做完当不适用；长段使用保留原始offset的段内窗口。预算与ZIP/XML安全上限保留。
- 状态与验证：**离线局部复现，最终真实漏改范围未验证；本轮未改引擎、未消耗模型预算。** 定向离线回归95 passed，不是修复验收。
- 下一步：优先修80节×scope的覆盖漏洞，随后补分页回归及实际输入/输出预算计量。

## FL-D442 删除 compose 重试沿用首次错误，第二次正确结果仍被拒（2026-10-28）

- 发现日期：2026-10-28，扩展严格性审计。
- 问题与影响：`compose_variant()` 在两次尝试循环外初始化 `last_error`；第一次删除返回原样触发 `DELETE_NOT_SHRINKING` 后，第二次虽正确返回保留句，也没有清空旧错误，最终仍报 `RECALL_COMPOSE_DELETE_NOT_SHRINKING`，独立 verify 没有机会执行。
- 证据：`fundlex/recall.py:7075–7127`；合成源“删除旧句。保留原句。”，脚本第一次回原样、第二次回“保留原句。”，两次 compose 后仍失败；本轮审计JSON的 `delete_retry_stale_error`。这是实际到达 delete-compose 的 legacy/兼容/扩展入口缺陷，默认 registry 的 DELETE-only 规则通常先被 executor 限制，不宣称所有默认删除均受影响。
- 处理方法（建议，未实施）：每次尝试用局部候选校验状态，只将当前失败写入历史；正确候选继续独立复核，不携带上次阻断状态；不得用粗暴整段删除绕过错误。
- 状态与验证：**脚本模型离线复现，未修复/部署/真实模型复测。** 下一步增加“首次失败、二次正确”与“二次仍错误”对照回归。

## FL-D442 Compare 选择版被 header/footer 覆盖警告整体阻断（2026-10-28）

- 发现日期：2026-10-28，继续完成真实合同选择路径时复现。
- 问题与影响：真实合同通常含非空页眉/页脚，Compare parser 报 `UNSUPPORTED_VISIBLE_CONTENT:header`/`footer`，coverage 为 `incomplete`；`selection_writer.generate_selection_artifacts()` 直接要求左右 coverage 均 complete，导致即使差异全部位于正文普通段落，选择版生成也返回 `SELECTION_COVERAGE_INCOMPLETE`。这使得选择版对真实合同基本不可用。
- 证据：`fundlex/compare/selection_writer.py:450` 原全局检查；真实合同 `广发ESG责任投资混合型证券投资基金基金合同.docx` 正文 1,417 段、header/footer 警告；正文 p831/p832 两处连续修改在修复前无法生成。
- 处理方法（已实施）：移除“coverage 非 complete 即整体拒绝”，保留警告为产物 limitations/报告例外；每个选择仍必须通过单块 body/table paragraph、run/field/drawing/合并单元格/content control 等逐操作结构校验，最终 DOCX 重新读取并核对文本。报告明确列出 header/footer 未覆盖，不宣称全文完整覆盖。
- 状态与验证：**已修复并生产验证。** 分支 `codex/compare-selection-group-fix` 提交 `85c8e42` 已推送；生产 `selection_writer.py` SHA `4b62a060...`，API active、capabilities 200。真实合同 128,805 字节、1,417 段：两处连续修改同组，全部采用右侧生成成功，final p831/p832 为 `1.00%`、段落数与页眉保持，redline 2 处 `w:ins` + 2 处 `w:del`，final 无残留修订，报告含 header/footer 例外。生产浏览器真实合同路径（登录、上传、全部采用 B、保存、预览、生成、下载 final/redline）通过，1440 视口无页面/控制台错误；证据 `/tmp/opencode/fundlex-compare-real-contract-20261028/`、`/tmp/opencode/fundlex-compare-browser-20261028/`。Compare 全套 **106 passed / 6 skipped**。
- 下一步：空侧 insert/delete、跨段、合并单元格等结构差异仍按设计阻断；若要把 header/footer 也纳入比较，需要单独扩展 parser/renderer，不在本次选择版范围。

## FL-D441 Compare 选择版对“相邻多个修改段”生成失败（2026-10-28）

- 发现日期：2026-10-28，生产 Compare 选择版真实 E2E 复核“按采用情况生成新文件”。
- 问题与影响：两份 DOCX 有**两个连续修改段落**时，对齐把两处 `modify` 放进同一组 `G0001`；`selection_writer._operations()` 对每个 `modify` 要求组形状为 `(1,1)`，于是生成返回 HTTP 409 `SELECTION_STRUCTURAL_DIFF_UNSUPPORTED`。用户已逐项选择但无法生成选择版/修订版；这属于常见合同修改形态，不是罕见结构。
- 证据：生产任务 `c30b9186...` / pair `e51536b6...`，D0001/D0002 均为 `modify`、同一 `G0001`，生成 409；证据 `/tmp/opencode/fundlex-compare-selection-e2e-20261028/production-selection-group-failure.json`。对照：两处修改之间隔一个未改段时，生产生成成功——final 采用第一处右侧、第二处左侧，修订版 1 处 `w:ins` + 1 处 `w:del`，final 无残留修订；证据 `production-selection-e2e2.json`、`selected_final2.docx`、`selected_redline2.docx`。
- 处理方法（已实施）：`selection_writer._modify_group_compatible()` 允许 `modify` 位于左右块数相等且**块序号一一对应**的 alignment group；每个 diff 仍必须单块、非跨段。左右块数不等、跨序号映射、多块 span、insert/delete 仍返回 `SELECTION_STRUCTURAL_DIFF_UNSUPPORTED`，不放开结构修改。新增“连续两个修改段”和“同组两个修改都采用右侧”回归。
- 状态与验证：**已修复并生产验证。** 分支 `codex/compare-selection-group-fix` 提交 `426892d` 已推送；`selection_writer.py` 生产 SHA `53c6cfd1...`，API active、capabilities 200。生产 API 小样本重跑：连续两个修改段、第一处采用右/第二处采用左时，final 为 `0.30%`/`0.10%`，修订版 1 处 `w:ins` + 1 处 `w:del`，final 无残留修订；同组两处都采用右时，final 为 `0.30%`/`0.08%`，修订版 2 + 2，final 无残留修订；四类产物均下载成功。证据 `/tmp/opencode/fundlex-compare-selection-e2e-20261028/production-selection-e2e.json`、`production-selection-e2e-all-right.json`。定向测试 writer **8 passed**、selection 套件 **20 passed / 1 skipped**、algorithm/API **37 passed**。临时账号、任务、对象已清理。
- 下一步：浏览器点击路径与完整真实合同选择路径均已完成，见 FL-D442；空侧 insert/delete、跨段、合并单元格等结构差异仍按设计阻断。发布备份 SHA 在 `/tmp/opencode/fundlex-compare-selection-fix-20261028/`。

## FL-D439 RuleScope 先选一个叶子造成正文同类条款漏改，景宁 p155 被误写成摘要（2026-10-28）

- 发现日期：2026-10-28，用户要求逐项确认“代码限制过严”时复核原件和实际 final。**更正此前 FL-D434、BIZ-18 及交接中“景宁 complete 即可交付”的结论。**
- 问题与影响：景宁 p148 与 p155 都在“第三部分基金的基本情况”，`zone=body`。p148 属于“八、基金份额类别设置”，p155 属于“九、基金份额的类别”；二者均有 G05 的类别调整、旧费率与备案句。`_class_set_leaf()` 优先第一个含“设置”的叶子，`_class_definition_leaf()` 多候选也直接取 `pool[0]`；G05 scope 只含 p147–p149，把正文 p155 当越界丢弃，Claim Replay/最终查漏复用此范围，不能发现范围自身漏选。
- 证据：`fundlex/rule_scope.py:537–565,613–618`；实际 `/tmp/opencode/smoke5-fix-20261028/run/002-广发景宁纯债债券型证券投资基金基金合同/final.docx` SHA `bc9cd2f52485517bbcfa2778be34bb90537e2e47b577ed98f716564e2ba63899`：p148 已无旧费率/备案，p155 仍有“调低赎回费率”“并报中国证监会备案”。同目录历史 report 仍为 complete/Claim verified/遗漏 PASS，不能作为全合同业务完成证据。指引原件第17–22段（零基段号）已授权类别调整费率及备案修改，不应因兄弟小节重复就排除。
- 处理方法（建议，**未实施**）：保留执行时的物理范围硬边界，但范围建立须由模型按指引解析、支持多个合法叶子和正文重复条款；独立覆盖审查需能在父章节提出“scope 漏选”并修订范围，而非既定范围外一律丢弃。不得直接取消 scope 或放开全文写入。
- 状态与验证：**已用真实原件/实际产物离线复现，未修复、未重跑、未部署。** 可重复探针 `tools/evaluation/strictness_audit_20261028.py`，证据 `docs/evidence/strictness-audit-20261028.json`。更正业务文档/交接，历史 report 保持不变。
- 下一步：与统一语义绑定/范围仲裁共同整改；原景宁 complete 不再计作本轮业务验收通过。摘要同步政策另议，不应拿摘要政策解释正文漏改。

## FL-D440 事实语法校验及依赖耦合可让模型重读/仲裁仍无法恢复（2026-10-28）

- 发现日期：2026-10-28，严格限制审计。
- 问题与影响：`verify_class_set()` 要求固定枚举动词；真实存在的“本基金现有A类与C类基金份额。”返回 quote_verified=true 但 `CLASS_SET_ENUMERATION_UNPROVEN`；`fee_value()` 对“C类基金份额销售服务费实行0.5%的年费率。”返回 None。`derive_fact_statuses()` 用同一个 fee_status 给申购费组和销售服务费组，单个服务费证据 UNKNOWN 会把已证实的申购费组也降为 UNKNOWN。`recover_fee_facts()` 的 primary/review 候选最终仍须通过同一语法门，review 不能仅靠有来源的语义解释纠正它。`applicability.resolve()`/`resolve_ledger()` 遇前置事实未验证会直接返回/跳过，不进入该阶段模型判断；这不是“完全没模型”，而是上游恢复仍受同一语法约束。
- 证据：`fact_evidence.py:48–50`、`fee_evidence.py:31–61,113–122`、`recall.py:641–661`、`facts_recovery.py:126–134,239–253`、`applicability.py:191–201,247–248`。离线最小例及 unknown 时模型调用次数0写入上述审计 JSON；合成例证明代码路径，不声称第一批所有合同都受影响。
- 处理方法（建议，未实施）：核验分成“来源确实存在”和“模型解释是否有充分支持”；语法抽取做快速路径，不作为语义仲裁唯一准入；按事实分别维护状态和实际依赖，UNKNOWN 仍不得自动当 FALSE。收费对象、缺失证据、渠道特例及数值矛盾仍需约束，不能直接信任模型布尔值。
- 状态：**合成离线复现/源码核验，影响范围待评测；未改引擎。** 下一步加独立证据仲裁路径、事实依赖隔离回归。

## FL-D438 `.doc` 自动转换 POC 未采用，统一改为提示用户另存为 `.docx`（2026-10-28）

- 问题与影响：合同修改和合同对比都可能收到 Word 97-2003 格式 `.doc`。该格式不是 OOXML，现有引擎只处理 `.docx`；若自动转换，版式、页眉页脚、编号、域、批注和修订都可能丢失，尤其是带既有修订的合同会直接影响 Compare 的“接受全部修订”输入。
- 证据或复现线索：尝试 WPS Open Platform POC 时，应用空间上传接口返回 HTTP 403 `{"code":20002,"message":"AppNotExist"}`，未创建转换任务；真实 WPS 凭证/应用状态和转换保真度均未完成验收。POC 适配器、批量脚本和本机受保护凭证文件已清理，未接入正式任务、数据库或上传页面。
- 处理方法：**明确不自动转换 `.doc`，保持 DOCX-only。** 后端共享上传校验检测 `.doc` 扩展名和 OLE 复合文档魔数，返回 `LEGACY_DOC_UNSUPPORTED`；合同修改前端把 `.doc` 标为“请用 Word/WPS 另存为 .docx 后重新上传”，合同对比前端在文件选择、文件夹选择和任务创建前给出同样提示，并在文件夹选择时显式说明忽略了 `.doc`，不再静默丢弃。后端仍拒绝 `.doc` 任务清单和绕过前端的 `.doc` 上传；不修改 `.doc` 后缀、不把二进制内容送入 OOXML 解析器。
- 状态与验证：**代码已实施。** `tests/test_upload_validation.py` 覆盖 `.doc` 后缀、OLE 魔数和普通非 DOCX；合同修改上传和合同对比上传/清单回归覆盖 `LEGACY_DOC_UNSUPPORTED`。正式上传仍只接收 `.docx`，未部署；V1 浏览器提示尚未在 Chromium 环境执行。
- 下一步：在可用浏览器环境验证合同修改和合同对比的 `.doc` 提示文案；真实用户上传 `.doc` 时确认不会创建任务、不会产生不完整记录。
- 变更记录：2026-10-28 新增；同日由 WPS 自动转换 POC 改为明确拒绝并引导另存为 `.docx`，POC 代码和凭证未保留。为避免与并行登记的 FL-D414 混淆，本条编号调整为 FL-D438。

## FL-D414 失败场景缺少简要原因，业务提示只有错误码（2026-10-28）

- 发现日期：2026-10-28，用户反馈生产任务 4 份合同全部 `not_generated`，工作台只显示“未生成”，没有说明是修订痕迹、目标结构还是模型失败；report.md 的阻断项也只有内部代码。
- 问题与影响：`business_reason()` 只覆盖少量规则级标记，文件级错误（`EXISTING_REVISION_UNSUPPORTED`）、目标结构（`RECALL_TARGET_STRUCTURE`）、模型失败（`MODEL_RETRY_EXHAUSTED` 等）都落到“未能可靠完成”的泛化提示；`not_generated` 文档没有 issue，前端只能显示状态。
- 处理方法：`delivery.py` 新增 `failure_reason()`，覆盖文件修订/保护/损坏、目标不可编辑结构、编辑重叠、模型重试/格式/截断/预算/上下文、指引与规则版本、旧句残留、claim/audit/coverage 等；`business_reason()` 优先使用它；`build_user_summary()` 对 `not_generated`/`errors` 生成“未生成修改文件：<原因>”标题和 issue；report.md 头部增加“失败原因”，阻断/复核项用中文原因替代裸代码；流水线把首个 error 写入 `error_code`。
- 状态与验证：**代码已实施。** 新增 3 条回归；`tests/test_delivery_summary.py` **16 passed**，delivery/pipeline/final-validation 合计 **198 passed**。
- 说明：生产任务由 10 月 26 日旧部署执行，旧代码不会生成这些提示；需发布新候选后新任务才会显示。

## FL-D432 QDII 费用条款标题为“3、C类基金份额的销售服务费”，G15–G17 scope 无法解析（2026-10-28）

- 发现日期：2026-10-28，第一批 smoke5 的 QDII 全球稳健合同 `incomplete`，Claim Replay 对 G15/G16/G17 均报 `RULE_SCOPE_UNRESOLVED`；报告 `scope_audit` 把正文 p969–p971 当作 `OUT_OF_RULE_SCOPE`，实际它们是销售服务费的支付/用途条款。
- 问题与影响：`rule_scope` 的叶子标题识别只接受精确的“销售服务费”标题；QDII 的正文标题是“3、C类基金份额的销售服务费”，`_known_title_key` 未识别类前缀，G15–G17 因此找不到 body leaf，scope 为空并失败关闭。摘要副本 p1151 被排除是正确的，但正文条款也被错误排除。
- 处理方法：
  - `_known_title_key()` 识别 `[A-Z]类(?:基金)?份额(?:的)?销售服务费`，但只在同一 section 没有普通“销售服务费”标题时把类前缀标题作为叶子；D06 同时有“3、销售服务费”和“（1）C类…”子标题时，子标题仍留在普通叶子内，不破坏原 p807–p810 范围。
  - 新增 QDII 回归：G15/G16/G17 解析到 `S17:L04`，包含 p969–p971，排除摘要 p1151。
- 状态与验证：**代码已实施并验证。** `tests/test_rule_scope.py` 新增 QDII 用例并通过；聚焦回归 **276 passed**。`/tmp/opencode/smoke5-fix-20261028` 重跑 QDII：G15/G16/G17 均 `ARTIFACT_VERIFIED`（G15/G16 p969、G17 p970），不再出现 `RULE_SCOPE_UNRESOLVED`；QDII 仍 incomplete 的 4 个 open obligation 全部是 G14:3/4/5 与 G18 的业务适用性（BIZ-02/BIZ-03），不是 scope 错配。
- 下一步：G14“转换费率”和 G18“QDII 无旧 A/C 表述”需业务决定；代码侧不再放宽 scope 或伪造站点。

## FL-D433 景宁 G03 作用域落在费率调整段，缺失操作恢复又在摘要 p1195 建目标（2026-10-28）

- 发现日期：2026-10-28，第一批 smoke5 的景宁纯债 `incomplete`，Claim Replay 报 G03 `CLAIM_OPERATION_UNPROVEN`/`verified site missing`，目标 R030 位于 p1195（第二十三部分基金合同内容摘要的收益分配句），且 `scope_id` 为空、`out_of_scope=false`。
- 问题与影响：两层错误叠加：
  1. G03 是“在基金基本情况份额类别设置条款后追加”，景宁把类别定义放在 p151（S05:L10），p148（S05:L09）只是费率调整句；原 scope 把 G03 指到 p148，真正的追加站点 p151 不在范围内。
  2. `target_for_missing_operation()` 仍按 section 级 mapping 扫描，mapping 含摘要 S26，于是把 p1195 当成 G03 候选；该恢复目标未经过 RuleScope 过滤，造成 scope 外目标进入 audit/unresolved。
- 处理方法：
  - `_resolve_class_basics()` 对 G03 优先使用基金基本情况中的完整类别定义叶子（p151），没有完整定义时才回退到“份额类别设置”叶子；G04 仍优先定义叶子，G05/G06 保持设置叶子。
  - `target_for_missing_operation(..., scopes=...)` 增加 scope 过滤：scope unresolved/空或候选不在 `scope.locations` 时返回 None，不再从摘要章节补目标；pipeline 调用传入当前 scopes。
  - `_open_operation_candidates()` 对 class rule 接受“将基金份额分为”作为“份额类别”的定义同义锚点，使 p151 能被恢复发现，同时仍由 scope 排除 p1195。
- 状态与验证：**代码已实施并验证。** 新增回归 `test_g03_recovery_stays_in_scope_and_prefers_class_definition`；景宁 no-model 恢复已从 p1195 改为 p151，D06 G03/G04/G05/G06 仍为 S04:L03（p130–p137）。聚焦回归 **276 passed**。`/tmp/opencode/smoke5-fix-20261028` 重跑景宁：**complete**（36 targets / 15 edits / 26 calls / 约 `$0.0267`，Claim Replay verified、open obligations 0、final omission PASS），G03 不再在 p1195 建目标。
- 下一步：不需要放宽 scope；若后续合同出现 G03 无完整定义，按 `_class_set_leaf` 回退并在报告中记录 `source=basic_info_class_leaf`。

## FL-D434 规则作用域仍是整章级，模型/召回可看到兄弟小节并产生错配（2026-10-28）

- **2026-10-28 业务清单重核补充**：此前“G15–G17摘要默认排除、同步仍待业务确认”只是技术策略，不能推翻完整交接151–165行既有实际正文/摘要目标分别盘点、关联语义一致的要求。D06原件p1256已进入“四、与基金财产管理、运作有关费用的提取、支付方式与比例”，p1269为“（三）销售服务费”；p1286 inspection.section_path停在“三、基金的收益与分配”是结构元数据不准，不是原件标题冲突。需要修结构/范围/副本语义识别，而非再要求用户决定是否修改已存在的同类目标；没有摘要目标且来源无新增义务仍不机械复制。与FL-D439的景宁正文p155漏改分开核验，代码尚未整改。

- 发现日期：2026-10-28，复盘 D06 G06 p280、景宁 G04 p148、D06 G15–G17 摘要 p1286–p1289 等错配。根因不是某条规则的特判缺失，而是 `Section` 只到“第三部分基金的基本情况”这种大章节，inventory/survey/append/delete/sweep/audit/plan 共享窗口或全章映射，规则可以借到同章兄弟条款。
- 问题与影响：G06 把“第六部分基金份额的申购与赎回”的 p280 当成 G06 候选；景宁 G04 把 p148 费率调整段当成类别定义；G15–G17 的摘要副本被自动当成必改站点；G19–G22 把 p982 的“对基金财产进行分配。”引导句当成清算分配条款。错误目标会进入规划、Claim Replay 和交付报告，属于跨路径的系统性错配。
- 处理方法：新增 `fundlex/rule_scope.py`：
  - `LeafSection` 把每个 `Section` 拆成物理叶子小节（编号标题/业务短标题），每个段落只归属一个叶子；摘要叶子按 `copy_key` 与正文条款 identity 关联，不按摘要标题猜。
  - `RuleScope` 保存 `leaf_ids/locations/zone/include_summary_copies/copy_keys/resolution/evidence`，提供 `contains()`、`as_dict()`。
  - `resolve_rule_scopes()` 以现有 `scope_map` 为基础收窄到叶子；显式策略覆盖 G01/G02、G03–G06、G07–G14、G15–G17、G18、G19–G22；无法唯一解析时 `resolution="unresolved"` 且 locations 为空，不回退全文。
  - 管线统一接入：inventory、survey、append recovery、semantic delete、sweep、audit、coverage、规划前门禁、Claim Replay、effect proof、delete residual 全部使用同一 scope；越界候选记录 `OUT_OF_RULE_SCOPE`，规划目标带 `scope_id`，无 scope 或越界则失败关闭。
  - 报告新增 `scope_audit`（每规则 leaf/locations/resolution/include_summary_copies、unresolved_rules、dropped/dropped_counts）。
- 证据与验证：
  - 无模型审计：D06 G06 仅 p130–p137，p280=False；G15/G16/G17 摘要 p1286=False，正文 p807–p810=True；G18/G19–G22 摘要按 copy_key 包含；景宁 G04 p148=False、p151=True。
  - D06 真实链路 `/tmp/opencode/d06-rule-scope3-20261028`：`complete`，39 targets / 15 edits / 27 calls / 约 `$0.0295`，Claim Replay `verified=true`，open obligations 0，final omission `PASS`；`scope_audit` 记录 `sweep:OUT_OF_RULE_SCOPE:G06:p280`，以及 `inventory:OUT_OF_RULE_SCOPE:G19–G22:p982`（引导句不是分配条款）。
  - 测试：`tests/test_rule_scope.py` 覆盖 D06/QDII/景宁真实 scope，`tests/test_rule_scope_integration.py` 覆盖 gate/sweep/delete/Claim Replay；全量回归 **1803 passed / 13 skipped**（分两批跑完全部测试文件）。
- 状态：**代码已实施，D06 真实链路已验证；第一批 3 份 smoke 中价值优选、景宁纯债可交付，QDII 仅剩 G14/G18 业务适用性；未部署生产。** 业务问题 BIZ-07（G15–G17 摘要副本是否必须与正文同步）仍待业务确认；当前技术口径是默认不把摘要副本当必改站点，只有显式 copy_key 才包含。
- 下一步：QDII 的 G14“转换费率”（BIZ-02）和 G18“无旧 A/C 表述”（BIZ-03）需业务决定；代码侧不通过放宽 scope 或伪造站点来消除 open obligation。
- 变更记录：2026-10-28 新增；与 FL-D370（窗口 scope 泄漏）和 FL-D381（bookmark 不可编辑）分开记录，本条是物理叶子作用域的一等公民化。

## FL-D435 Claim Replay/delete residual 绕过 RuleScope，把摘要副本重新加回必改站点（2026-10-28）

- 发现日期：2026-10-28，RuleScope 接入 inventory/survey/append/delete/sweep/plan 后首次 D06 真实运行 `/tmp/opencode/d06-rule-scope-20261028` 仍 `incomplete`。body p807/p808/p810 已改，但 Claim Replay 独立扫描全文，把 p1286/p1289 摘要副本重新算作 G15/G17 站点，产生 `CLAIM_OPERATION_NOT_PLANNED`/`RESIDUAL_OLD_TEXT` 和 open obligation。
- 问题与影响：作用域只在召回侧生效，证明侧仍可扩大站点集，导致“正文已正确修改但永远无法闭合”；也会让 scope 外副本成为 open obligation，污染交付状态。
- 处理方法：`replay_claims(..., scopes=None)`、`check_delete_residuals(..., scopes=None)`、`_verified_site_closure(..., allowed_locations=)`、`evaluate_operation_effect(..., boundary_locations=)` 增加可选 scope；target 站点、composite parts、duplicate 传播、edit unit、delete residual 全部限制在 `scope.contains(location)`；scope unresolved/空 locations 时不再全文补站点，返回 `RULE_SCOPE_UNRESOLVED` 并失败关闭；`scopes=None` 保留历史行为。pipeline 的 Claim Replay、recovery、audit、final omission 调用统一传入当前 scopes。
- 证据与验证：D06 `/tmp/opencode/d06-rule-scope3-20261028` Claim Replay `verified=true`、`checked=15`、`units_checked=17`、failures=[]，open obligations 0；`tests/test_rule_scope_integration.py` 新增 D06 摘要副本正反例与 unresolved 不回退测试；全量回归 **1803 passed / 13 skipped**。
- 状态：**代码已实施并验证。** 未部署。
- 下一步：smoke5 中若仍有摘要副本残留，先区分“scope 外副本按策略不应改”与“正文站点未证明”，不得重新放宽为全文扫描。

## FL-D436 G12 相邻 ONE_OF 历史措辞同时合并，p230 重复整句（2026-10-28）

- 发现日期：2026-10-28，D06 `/tmp/opencode/d06-rule-scope2-20261028` 报告 `delivery_status=complete` 但 Claim Replay 报 G12 p230 `CLAIM_DUPLICATE_EFFECT`。`G12:0` 与 `G12:1` 是同一 `one_of_group` 的两个历史措辞，规划分别覆盖 p230 的前后相邻 span，`merge_edits()` 的相邻分支把两个 replacement 直接拼接，最终写入两遍“赎回费用全额计入基金财产。”。
- 问题与影响：ONE_OF 语义被当成独立操作执行；产物出现重复政策句，Claim Replay 失败，且当时交付门禁未阻断（见 FL-D437）。
- 处理方法：`merge_edits()` 相邻分支先判断 `_operations_are_alternatives()`：
  - 两个非空 replacement 相同/互相包含时，保留包含方，另一个标记 covered；
  - 两个非空但政策文本不同，记录 `RECALL_EDIT_OVERLAP` + `ONE_OF_ALTERNATIVES_DIFFER`，失败关闭，不静默拼接；
  - 空 replacement/删除场景保留原有相邻合并行为，由后续删除/Claim Replay 证明兜底。
- 证据与验证：D06 `/tmp/opencode/d06-rule-scope3-20261028` p230 最终 edit 为 `G12+G13`，replacement 仅一句“赎回费用由……收取。赎回费用全额计入基金财产。”，`7 日` 旧句已删除；Claim Replay verified。新增回归 `test_adjacent_one_of_alternatives_are_written_once`、`test_adjacent_one_of_different_policies_fail_closed`；全量回归 **1803 passed / 13 skipped**。
- 状态：**代码已实施并验证。** 未部署。
- 下一步：检查其他 ONE_OF 组是否也存在相邻/非相邻双站点；若出现，按同一原则选择实际源措辞并证明，不得放宽 Claim Replay 重复检测。

## FL-D437 review_assisted 交付门禁忽略 Claim Replay 失败/open obligation，产生假 complete（2026-10-28）

- 发现日期：2026-10-28，D06 `/tmp/opencode/d06-rule-scope2-20261028` 报告 `delivery_status=complete`，但 `artifact_claim_replay.verified=false`、`delivery_gate.open_obligations=1`、`final_omission_review.status=FAIL`。`CLAIM_DUPLICATE_EFFECT`/`CLAIM_OPERATION_NOT_PLANNED` 被 `review_assisted` 归入人工复核，`_delivery_complete()` 只看 blockers，不看 Ledger 的 open obligation、Claim Replay 结果或最终遗漏中的证明失败。
- 问题与影响：这是假 complete，会把未完成合同发布为 final/redline，直接违反“报告自身证明失败不得宣称完成”。同时不能简单把所有 open obligation/FAIL 都当阻断，否则审计未完成、sweep 上限、事实未核验等原本设计为人工复核的项会全部退回 incomplete。
- 处理方法：
  - `_delivery_complete()` 增加 `claim_replay_verified`、`final_omission_blocking`；Claim Replay 失败或证明型最终遗漏失败时任何策略都阻断；`strict` 仍阻断全部 open obligation。
  - `review_assisted` 下 Ledger open obligation 仅当自身证据含 `CLAIM_`（Claim Replay 失败）时阻断；`AUDIT_NOT_COMPLETED`、`SWEEP_CHUNK_LIMIT`、`FACT_PREREQUISITE_UNVERIFIED` 等保留人工复核/业务待定。
  - `_classify_delivery_items()` 把 `claim_replay_failed`/`kind=claim_replay` 和证明型 `final_omission` 归为 blockers；新增 `_final_omission_issue_blocks()`，只把 `FINAL_OPERATION_UNPROVEN`、`FINAL_RESIDUAL_OLD_TEXT` 及含 `CLAIM_` 的 `FINAL_COVERAGE_UNRESOLVED` 视为证明失败。
  - 调用点传入 `replay.verified` 和按最终遗漏 issues 计算的 `final_omission_blocking`。
- 证据与验证：D06 `/tmp/opencode/d06-rule-scope3-20261028` 现为真 `complete`：Claim Replay verified、open obligations 0、final omission PASS、final/redline 哈希一致；原有审计失败、类集合未核验、sweep chunk 上限 3 条 review_assisted 用例仍为 complete。新增回归 `test_delivery_gate_blocks_claim_failure_open_obligations_only`、`test_delivery_gate_blocks_failed_claim_replay_and_final_omission`；全量回归 **1803 passed / 13 skipped**。
- 状态：**代码已实施并验证。** 未部署。
- 下一步：全量真实批次重跑后统计“真 complete/人工复核/业务待定”，不得把本次门禁修复当成业务准确率提升；任何 `complete` 必须同时满足 Claim Replay verified、open obligations 0、final omission PASS（或明确证明型 issue 已解释）。

## FL-D411 QDII 多币种类别导致事实核验失败，G16/G17 被保护性阻断（2026-10-28）

- 问题与影响：纳斯达克生物科技、美国房地产、道琼斯石油的事实类别名为 `A类人民币`/`A类美元现汇`/`C类人民币`/`C类美元`。`class_labels()` 只取字母，`verify_class_set()` 对非简单类别要求显式“四种”计数，`fee_value()` 不识别币种后缀、封顶申购费率、方括号净值费率，导致 `share_class_structure`/`service_fee_group` UNKNOWN、`FEE_QUOTE_UNPROVEN`/`CLASS_SET_MISMATCH`，G16 无法追加、G17 被 `G17_BLOCKED_G16_UNPLANNED` 阻断，3 份 incomplete。
- 处理方法：
  - `fee_value()` 解析前把 `A类人民币`/`A类美元现汇` 归一化为 `A类`（仅解析，不改证据原文）；
  - 识别“申购费率由基金管理人决定”和“申购费率最高不超过…X%”（仅申购费；销售服务费的封顶不等于计提）；
  - 净值费率允许方括号和“资产净值X%”（无“的”）；
  - `verify_class_set()` 允许完整全名枚举无显式计数，并允许币种子类归并到基础类别（“A类、C类和E类三种”覆盖 A类人民币/A类美元现汇/C/E）。
- 状态与验证：**代码修复已实施并验证。** 三份真实合同单跑均 `complete`：纳斯达克 31 calls/约 `$0.0346`，美国房地产 33 calls/约 `$0.0405`，道琼斯 35 calls/约 `$0.037`。新增 4 条回归；`tests/test_fee_evidence.py` **87 passed**，聚焦套件 **443 passed**。v3 全量批次验证中。

## FL-D412 G04 scope 扩展到释义后与 G02 编辑同一段，RECALL_EDIT_OVERLAP（2026-10-28）

- 问题与影响：纳斯达克 p169（基金的基本情况 S05）已有完整 A/C 定义，但 `expand_class_definition_scope()` 仍把释义 S04 加入 G04，G02 与 G04 同时替换 p102 的类别标签，计划报 `RECALL_EDIT_OVERLAP`，两个目标都 unresolved。
- 处理方法：扩展前先检查 G04 的非释义 section 是否已有完整定义锚点；有则从 G04 映射中移除释义 section（释义由 G02 负责），没有才扩展。
- 状态与验证：**代码修复已实施并验证。** 纳斯达克单跑 `complete`；新增回归 `test_g04_scope_drops_glossary_definition_when_basic_section_has_one`；聚焦套件 443 passed。

## FL-D413 claim-site 修复目标不检查规则 scope，在兄弟规则段落重建目标（2026-10-28）

- 问题与影响：G02 的 scope 只有 S04，但 Claim Replay 的 exact-duplicate 传播把 S05 p169 纳入 G02 站点，`target_for_claim_site()` 在 p169 创建 `R049`，与 G04 的目标重叠。
- 处理方法：`target_for_claim_site()` 增加 `allowed_locations`；pipeline 按 `mapping`/`sections` 计算该规则的允许位置，越界不创建修复目标。
- 状态与验证：**代码修复已实施并验证。** 纳斯达克单跑不再出现 p169 的 G02 目标；新增回归 `test_claim_site_repair_respects_rule_scope`。

## FL-D410 G12:1 的短持有期句子未随替换删除，QDII 残留旧句（2026-10-28）

- 发现日期：2026-10-28，v2 全量批次中广发全球稳健配置（QDII）仍 incomplete，Claim Replay 报 G12:1 `RESIDUAL_OLD_TEXT`（p260）。
- 问题与影响：G12:1 的 `old_text` 含“其中，对持续持有期少于7日的投资者收取不低于1.5%的赎回费，并全额计入基金财产。”，`new_text` 不含；`_g12_allocation_end()` 只算到“手续费。”，计划只替换前半段，短持有期句留在产物中。
- 处理方法：新增 `_g12_short_holding_end()`，仅当该 operation 自己的 `old_text` 含短持有期句时，把替换边界扩展到该句末；G12:0 仍不借用 G13 的句子。
- 状态与验证：**代码修复已实施并验证。** QDII 真实合同单跑 `complete`（26 calls / 约 `$0.0341`），G12 edit `end=146` 覆盖短持有期句；新增回归 `test_g12_operation_that_owns_short_holding_sentence_replaces_it`；聚焦套件 **374 passed**。

## FL-D408 交付策略改为 review_assisted：未证明项降级为人工复核，事实矛盾仍阻断（2026-10-28）

- 发现日期：2026-10-28，用户明确要求减少 incomplete：后期会有人工逐份复核，已修改的点不必再逐站点严格证明；业务未定项先放着，后续处理。
- 问题与影响：原 `_delivery_complete()` 只要存在任何 unresolved 或 open obligation 就拒绝发布，导致大量“改动正确但证明不了”的合同停在 incomplete；同时把业务未定项与工程缺陷混在同一状态里，无法区分。
- 处理方法：新增 `FUNDLEX_DELIVERY_POLICY`（默认 `review_assisted`，可设 `strict` 恢复旧行为）。`_classify_delivery_items()` 把未决项分为三类：
  - **阻断**：已编辑站点仍存在旧句（`RESIDUAL_OLD_TEXT`）、编辑未生效、文件/写入失败、模型调用失败，以及事实未核验（`FACT_PREREQUISITE_UNVERIFIED`/`RECALL_FACT_UNVERIFIED`，因为适用性未知时可能漏改）；
  - **人工复核**：未证明站点、审计未完成、查漏缺口、orphan evidence、模型 sweep 意见等；
  - **业务待定**：G14/G18，单独计数，不自动修改、不阻塞交付。
  报告新增 `delivery_policy`、`delivery_blockers`、`review_items`、`business_pending`、`review_required` 字段；`review_assisted` 下无阻断即发布 final/redline，并附人工复核清单。
- 状态与验证：**代码已实施，聚焦套件 418 passed（1 个与本改动无关的 Feishu `status_card` ImportError 被 deselect）。** 未跑新的真实批次；旧批次可离线重分类。
- 变更记录：2026-10-28 新增。此条改变了此前“业务歧义必须 fail-closed”的交付口径，依据是用户 2026-10-28 的决定；业务内容本身仍不自动修改。

## FL-D409 逐份 report.md 只有统计没有修改内容（2026-10-28）

- 发现日期：2026-10-28，用户反馈导出的逐份 `report_md.md` 没有任何有用信息，应该写清这份合同具体改了哪些地方、依据指引的什么内容、从什么内容改成什么内容。
- 问题与影响：原 `_write_report_markdown()` 只有目标计数、每规则处置和未完成清单（且未完成清单直接输出 JSON），没有逐处修改的原文/新文和指引依据，人工复核无法使用。
- 处理方法：重写报告生成。新增“逐处修改”章节：每条 edit 输出规则编号与标题、位置、操作、指引要求、修改前（`expected_old_text`）、修改后（`replacement`）、Claim Replay 证明状态；“已符合、无需修改”列出 satisfied 目标及原因；“业务待定”单列；“阻断项”和“人工复核清单”分列且改为可读文本；“处理概览”保留审计/查漏统计。
- 状态与验证：**代码已实施。** 新增回归 `test_report_markdown_lists_each_change_with_before_after_and_guide`；用 ESG 真实 report.json 重新生成报告，逐处修改含指引要求、修改前后原文与证明状态。
- 补充（同日）：`fundlex/jobs.py` 的 `Worker._markdown()` 原来只输出 10 行头信息，且会在流水线 report.md 后**追加**这段 stub，导致工作台下载的 `report_md` 仍然没有修改内容。现改为：报告含 `plan`/`guide` 时直接复用 `_report_markdown()`；流水线已写 report.md 时不再追加 stub。新增回归 `test_worker_markdown_uses_pipeline_change_detail`。
- 补充（同日）：`fundlex/delivery.py` 的 `build_user_summary()` 原来把任何 unresolved 都当作 PARTIAL，会与 review_assisted 的 complete 状态矛盾；现按 `delivery_policy` 读取 `delivery_blockers`，无阻断但有复核/业务项时返回 `complete_with_notices` 并在标题写明数量。新增两条回归。
- 变更记录：2026-10-28 新增。

## FL-D385 V1 Compare 差异栏收窄并将“采用合同A/B”简化为“采用 A/B”（2026-10-27）

- 发现日期：2026-10-27，用户反馈差异列表还可以改窄，并要求把“采用合同A/B”简化成“采用 A/B”。
- 问题与影响：生产 V1 差异栏为 `clamp(240px,20vw,280px)`，在 1440px 下接近 280px，压缩合同正文阅读宽度；单项和批量按钮文案“采用合同A/B”在窄栏内占用更多横向空间。
- 处理方法：生产 V1 差异栏改为 `clamp(200px,16vw,240px)`，761–1100px 档固定 200px；差异条目编号/类型列由 `23px/40px` 收窄为 `20px/36px`，字号约 11.5px；批量按钮改为“全部采用 A/B”，单项 radio 改为“采用 A/B”，aria-label 改为“采用 A 或 B”。React V2 右侧差异栏由 `minmax(280px,340px)` 改为 `clamp(220px,18vw,280px)`，761–1000px 档由 260px 改为 220px；V2 当前没有“合同A/B”选择文案，未改其“原版/对比版”语义。
- 证据与验证：生产同源 `f4bb2b7` worktree 在 1440px 实测差异栏宽 **230.39px**，截图 `/tmp/opencode/compare-v1-compact-rail.png`；批量按钮文本为“全部采用 A/B”，单项为“采用 A/B”，旧“采用合同A”计数为 0。生产 Compare 选择版浏览器套件 **14 passed**；V2 Compare 浏览器用例 **1 passed**；工作区前端 typecheck/lint、Vitest **14 passed**、build 通过；`git diff --check` 通过。
- 状态与验证：**生产 V1 已发布并验证；React V2 已改源码和构建但未发布**。生产文件哈希：`compare.html` `18b5924cc5db0c3a7a8b483e13230259695dd5cc63e31f238fc25bb674637d87`、`compare.css` `13c211d46a4f8f1f6bd65834c3822169dadab229581c3c50b3c4476d2fb4eaa5`、`compare.js` `22bb6be87b090d9123d58cbdf5d0aab18ef0e2e9094dd0778718b6f3201fd08c`；上一版备份 `/tmp/opencode/fundlex-compare-compact-20261027/`。公网资源版本 `adb3032a1052f46f`，1440/390 无页面错误/控制台错误/404，无横向溢出。
- 下一步：如需更窄，需要同时压缩差异摘要行和选择按钮，避免正文与“采用 A/B”换行拥挤；V2 仍未发布，生产基线分叉见 FL-D382。
- 变更记录：2026-10-27 新增；生产 V1 定向发布，V2 仅工作区构建；不涉及真实合同任务或模型调用。

## FL-D384 第一批 smoke 的重复摘要副本与无操作站点证明未闭合（2026-10-27）

- 发现日期：2026-10-27，修复 FL-D381 及 G04/G05 两项代码问题后重跑 3 份 smoke，目录 `/tmp/opencode/first-batch-smoke4-20261027`。三份仍均为 `incomplete`：价值优选 G15 p1258、QDII G05 p1331/p481、景宁 G04 p148 仍未闭合。
- 问题与影响：`duplicate_copy_targets()` 只克隆 `needs_edit` 目标；摘要副本若是短片段或已满足副本，不会被绑定/计数。价值优选 p1258 的 `销售服务费每日计提，按月支付。` 片段目标被 `TARGET_SOURCE_MISMATCH` 排除，最终仍残留旧句；QDII p1331 已满足、p481 无目标，Claim Replay 报 `CLAIM_OPERATION_NOT_PLANNED`；景宁 G04 p148 被模型判 satisfied/no replacement，但 quote_not_found、无站点，最终 `verified site missing`。这不是单纯业务措辞，包含重复副本覆盖、短片段绑定和 no-op 站点证明的代码缺口。
- 证据：`/tmp/opencode/first-batch-smoke4-20261027/run/*/report.json`；价值优选 G15 `DEL001/R033`；QDII G05 `S26#1:T003` 与 p481；景宁 G04 `T005/T006`。G04 scope 扩展和 G05 审计证据覆盖已实施，但未闭合上述站点。
- 处理方法：**代码部分已修复，业务部分待决定。** 重复副本/短片段/no-op 三个代码缺口分别由 FL-D394（G17 单句整段删除）、FL-D396（G02/G04 已满足定义站点）覆盖；FL-D395 补了 G05 协调费率列表的已满足证明。G15 支付条款变体与 G14/G18 措辞/适用性仍是业务决定（FL-D397/FL-D399）。
- 状态与验证：FL-D381 + G04 scope + G05 审计覆盖已通过 **372 passed** 聚焦回归；smoke4 仍 **0/3 complete**，不能宣称整批通过。未建 labels/gold，未部署。上述新修复尚未跑真实批次。
- 剩余 24 份批次（`/tmp/opencode/first-batch-remaining-20261027`）进一步确认问题不是 3 份特例：**4 complete / 20 incomplete**，772 calls / 约 `$0.9016`，12 次失败请求。通过：广发富信优选 FOF、广发沪深300指数增强、广发沪港深精选、广发聚安混合；未闭合规则以 G17 62、G14 60、G16 52、G02 33、G04 33、G05 27 为主。汇总见 `batch-analysis.json`；连同 3 份 smoke4，当前代码 27 份中仅 4 份 complete。该批次是管线 smoke，不是准确率或整批交付通过。
- 20 份 incomplete 的归因聚类（可重叠）：**7 份只差 G16**（ESG、品质优选、恒昌、恒裕、恒阳、恒隆、招利），是最大单一可修代码簇；11 份出现 `CLAIM_OPERATION_NOT_PLANNED`、3 份 `RESIDUAL_OLD_TEXT`（重复摘要副本/短片段）；9 份 `AUDIT_NOT_COMPLETED`、6 份 `LEDGER_EVIDENCE_UNBOUND`、8 份 `FINAL_MODEL_SWEEP_FINDING`（审计/证据绑定）；约 6 份涉及 G04/G02 类别定义/no-op 站点；约 7 份涉及 G14/G18 业务措辞/适用性；5 份有 `MODEL_RETRY_EXHAUSTED`/`MODEL_SCHEMA_INVALID` 模型事件（12 次失败请求），是叠加因素而非唯一原因。
- 下一步：代码缺口已由 FL-D394/FL-D395/FL-D396 修复；剩余业务决定见 FL-D397（G15 支付条款变体）、FL-D398（QDII/FOF 适用档）、FL-D399（G14/G18）。修复后先跑全量 27 份真实批次，按逐合同 complete 统计，不用单份通过代替整批。

## FL-D392 恒裕 G17 p888：absent 判定仍声明 operation 覆盖，压制确定性删除目标（2026-10-27）

- 问题与影响：模型对 G17 两句旧文报 `absent`（p888 只有第一句），该 absent 目标仍被 `known_operations_from_targets()` 计为覆盖 `G17:0@p888`，`_collect_targets()` 丢弃 `ensure_delete_targets()` 新建的 DEL001；最终 p888 残留旧句，Claim Replay 报 `CLAIM_OPERATION_NOT_PLANNED`/`RESIDUAL_OLD_TEXT`。
- 证据：`/tmp/opencode/g16-cluster-smoke-20261027/run/*恒裕*/report.json`（T021 absent、DEL002 p890、缺 DEL001）；离线复现 `ensure_delete_targets` 会建 DEL001，但 `_collect_targets` 丢弃。
- 处理方法：`known_operations_from_targets()` 跳过 `state == "absent"` 的目标——absent 断言此处没有材料，不能同时声明已覆盖（与 FL-D118 的 append 同类）。
- 状态与验证：**代码修复已实施；未跑真实批次。** 新增回归 `test_absent_inventory_target_does_not_suppress_delete_target`；恒裕真实 report 离线复算 DEL001(p888)+DEL002(p890) 均保留。

## FL-D393 恒裕 G15 SW002 用 ASCII 引号引用旧句，被当成 orphan evidence 阻塞交付（2026-10-27）

- 问题与影响：sweep 用单引号 `'...'` 引用 G15 旧支付条款；`_apply_artifact_proof_to_findings()` 只提取中文引号 `“…”`，`claimed` 为空 → `SEMANTIC_UNCERTAIN` → `LEDGER_EVIDENCE_UNBOUND`（orphan），即使该旧句在 artifact 中并不存在。
- 证据：`/tmp/opencode/g16-cluster-smoke-20261027/run/*恒裕*/report.json` 的 SW002。
- 处理方法：引号提取支持 `“”`/`「」`/`''`/`""`，并要求 claim 至少含 6 个汉字，避免英文撇号误匹配。
- 状态与验证：**代码修复已实施；未跑真实批次。** 新增回归；恒裕真实 report/working_final 复算 SW002 → `resolved`/`REMOVAL_UNCONFIRMED`/`claimed_residual_absent`。

## FL-D394 G17 单句用途条款无法删除（部分旧文删除）（2026-10-27）

- 2026-10-28 审计补充（**仍有未修复分支**）：第一批“广发弘利3个月滚动持有债券型证券投资基金”p784 的真实原句“销售服务费可用于本基金市场推广、销售以及基金份额持有人服务等各项费用。”在G17 scope内，精确原文quote＋合法G17:0归属通过，但 `target_site_ok` 只认“主要用于/使用范围”，`plan_target` 在零模型调用前报 `TARGET_SOURCE_MISMATCH`。因此本条原“已修复”仅覆盖原先缺类别前缀/拆句分支，不覆盖所有用途措辞。证据 `docs/evidence/strictness-audit-20261028.json` 的 real_G17，实际来源哈希随证据保存。建议转入受约束语义复核，不再新增同义词硬门；**本轮只审计，未修复。**

- 问题与影响：合同把 G17 的两句旧文拆成两个段落或只保留用途句；目标 span 正好是该句，但旧文带 `C类基金份额的` 前缀，`quote in reference` 子串检查失败，composer 报 `DELETE_NOT_SHRINKING`，残留 `RESIDUAL_OLD_TEXT`。24 份批次中生物科技 p940/p1413、美国房地产 p721/p1130、道琼斯 p902/p1357 等 5 份受影响。
- 处理方法：新增 `_g17_target_is_owned_sentence()`，目标 span 必须精确等于该 operation 的一条完整源句（`_g17_source_sentence_parts`，含类别前缀容错）时整段删除；不满足继续 fail-closed。
- 状态与验证：**代码修复已实施；未跑真实批次。** 三份真实合同目标离线判定 `owned=True`；新增 `plan_target` 回归 `test_g17_single_purpose_sentence_is_deleted_without_class_lead`。

## FL-D395 G05 已满足证明不识别“调低A和B”协调列表（2026-10-27）

- 问题与影响：QDII p1331 原文“调低赎回费率和销售服务费率”，已包含新文本“调低销售服务费率”的效果，但字面不存在 → satisfied 站点被判 `CLAIM_OPERATION_NOT_PLANNED`。
- 处理方法：`effects.py` 增加 `_coordinated_verb_equivalent()`（同一费率动词 + 同一宾语 + 真实并列分隔符），并只对协调列表中同一动词的旧项豁免残留（`_coordinated_member_residual_authorized`）。
- 状态与验证：**代码修复已实施；未跑真实批次。** QDII 真实 report/artifact 离线复算 `G05:0` → `PASS`/`ALREADY_SATISFIED`；反例（逗号句、缺并列项）仍失败。

## FL-D396 G02/G04 已满足定义缺少站点证明（2026-10-27）

- 问题与影响：景宁 p148 是 G05 的份额类别变更条款，模型把它判成 G04 satisfied 且 quote 无法绑定（`start/end` null），真正定义段 p151 未被证明 → `verified site missing`。
- 处理方法：`target_site_ok(G02/G04)` 拒绝“增加/变更/停止…份额类别”且无定义标记的段落；`survey_targets` 新增 `class_definition_satisfied_hits()`，在“将基金份额分为/称为”段落按每个实际类别的申赎/销售服务费极性生成 satisfied 站点（缺类或极性不符不生成）。
- 状态与验证：**代码修复已实施；未跑真实批次。** 景宁 p148=False / p151=True；p151 上 `G04:0`/`G04:1` 离线复算 `PASS`/`ALREADY_SATISFIED`；新增两个回归。

## FL-D397 业务待定：G15 旧文未覆盖 2023 自动划付式支付条款（2026-10-27）

- **2026-10-28 原件/裁定重核更正（优先于下文历史判断）**：不再列为待业务决定。指引零基段75–84及2026-10-19裁定（生成策略计划§7.3/§39）已有“删除照常、实质差异仅提示、不另外整改/不阻交付”的依据；自动支付/无需指令/五日属于旧支付安排变体，由模型确认归属和删除范围，不以登记old_text_variants作为业务授权前提。恒裕p887/p1352确有“无需指令”；价值优选p800/p1258没有该同一句，旧条目把不同合同措辞混在一起亦须更正。五日或自动支付本身不代表已实现返还等新机制。当前代码绑定/复核缺陷仍待修复，不等于业务未授权。

- 现状：恒裕 p887、价值优选 p1258 的支付条款是“逐日累计…次月初五个工作日内…自动支付…无需划付指令”，与 G15 `old_text`（划付指令/10个工作日/登记机构代付）不同。严格批次里 fail-closed：恒裕 `LEDGER_EVIDENCE_UNBOUND`、价值优选 `RESIDUAL_OLD_TEXT`。
- 2026-10-28 复测观察：review_assisted 全量批次与 3 份新链路 smoke 中，模型显式把这些变体判为“同属应删除的旧支付安排”，变体删除被接受，G15 义务 PASS，恒裕/价值优选均 complete。也就是说**当前引擎在模型显式命中时会删除该变体**，不再是 fail-closed；报告逐处列出修改前后，供人工确认。
- 需要决定：是否把该变体正式加入 G15 `old_text_variants`（视为需删除的旧安排），还是判定该合同已符合新规、G15 不适用。若决定不删除，这两份需要回退并重新交付。
- 状态：**业务未决定；当前行为是“模型显式命中即删除”，已在报告中可见。**

## FL-D398 业务待定：QDII/FOF/指数/养老目标合同的规则适用档与验收分母（2026-10-27）

- **2026-10-28 重核更正**：现有要求下不是必须新订业务档。按实际产品身份、收费事实和指引单/多类别分支逐规则判断是已有任务；ETF联接正常修改、货币等排除已有裁定。事实抽取未核验属于补证/实现问题，不能因失败较多整体豁免QDII/FOF或移出分母。只有另提“按产品名整份排除/降配/修改冻结分母”才需新范围授权；当前没有此新增授权，固定manifest/哈希/分母保持不变。

- 现状：纳斯达克生物科技 97、道琼斯石油 92、美国房地产 80、稳健养老 FOF 41 条 unresolved，覆盖 17–18 条规则，约占 24 份批次全部 unresolved 的 67%；这些合同的结构与费用安排和普通 A/C 混合基金差异大。
- 需要决定：是否为本类合同设独立规则档（哪些规则不适用），以及是否计入第一批验收分母。
- 2026-10-28 观察：3 份指数合同（纳斯达克生物科技/美国房地产/道琼斯）各 2 处 G17 残句，根因是 facts 未核验（`service_fee_group`/`share_class_structure`）→ G16 无法追加 → G17 被 `G17_BLOCKED_G16_UNPLANNED` 保护性阻断。不是新的定位缺陷，属于本条的适用档/事实核验问题。
- 状态：**未决定；当前按全规则 fail-closed。**

## FL-D399 业务待定：G14 多“转换费率”与 G18 QDII 适用性（2026-10-27）

- **2026-10-28 G18补充重核**：指引零基段91–92是对应原因句的替换，不是无条件新增。全球稳健QDII收益原则p990–996、摘要p1412–1418只有分红、币种、同等分配权等安排，未见对应费用原因句；p169基本情况虽有费用差异/净值分别计算，不得跨章借证为收益分配已满足。应语义复核后记录“无对应替换目标”的依据，不强制补写、不机械造open义务，也不判整份QDII豁免。**仅当另提无原句也必须新增该原因句时才需新授权**；在现有替换任务下不必等用户拍板才能保留原文。结合下条G14更正，本条不再作为两项待业务决定。

- **2026-10-28 更正**：本条G14“指引未覆盖转换费率”结论错误，已撤回；原件零基段59–66列出三种表述，编译guide G14:1/4已含表述2，:2/5已含表述3。QDII p263只在“赎回费率”前重复“基金”，属于匹配/绑定缺陷，不需业务另授删除转换费率权限。局部归一化尝试已在本轮审计前存在工作区，不能当统一语义绑定已实现或真实修复已通过。G18旧文缺失的适用性仍需单独核对，不随G14结论一起放宽。

- 现状：部分合同费率调整条款多出“转换费率”，G14 删除目标覆盖不到；QDII 合同缺少 G18 期望的旧 A/C 费用差异表述。当前 fail-closed，未自动删除或标记满足。
- 需要决定：G14 是否要求删除“转换费率”，G18 对 QDII/多币种合同是否适用。
- 状态：**未决定。**

## FL-D391 G16 append effect 借用 G15 支付头，导致 7 份 G16-only 合同 incomplete（2026-10-27）

- 发现日期：2026-10-27，分析 24 份批次中 7 份“只差 G16”的合同（ESG、品质优选、恒昌、恒裕、恒阳、恒隆、招利）。
- 问题与影响：G16 append 目标在条款尾 p849（摘要 p1296），G15 删除支付头 p847；`_verified_site_closure` 把 p847/p1296 作为 exact source duplicate 传播到 G16 站点集，Claim Replay 要求 G16 在 p847 也出现，但 p847 已被 G15 删除，报 `CLAIM_OPERATION_NOT_PLANNED`/`MISSING_EFFECT`，7 份全部 incomplete。
- 证据：`/tmp/opencode/first-batch-remaining-20261027/run/001-*` 的 G16 义务 sites `p847,p849,p1296`，p849/p1296 PASS、p847 FAIL；定向 smoke `/tmp/opencode/g16-cluster-smoke-20261027`。
- 处理方法：新增 `_own_rule_append_sites()`，G16 append 只保留本规则真实 target 的 location；`evaluate_operation_effect()` 增加 `allowed_locations`，在 `_verified_site_closure()` 之后再次限定，避免 duplicate 传播重新引入 G15 的支付头；`claim_replay` 对 append 传入 allowed locations。新增 helper 与 effect 回归。
- 状态与验证：**代码修复已实施并验证。** 聚焦套件 **385 passed**；ESG 真实 report/working_final 离线复算 p847 被排除、p849/p1296 均 PASS。定向真实 smoke 7 份：**6 complete / 1 incomplete**，实际 202 calls / 约 `$0.2310`；complete 为 ESG、品质优选、恒昌、恒阳、恒隆、招利。恒裕仍 incomplete，剩余 G17 p888 残句 `CLAIM_OPERATION_NOT_PLANNED` 和 G15 p888 `LEDGER_EVIDENCE_UNBOUND`。
- 下一步：恒裕剩余的 G17 p888 残句与 G15 orphan 证据已分别由 FL-D392/FL-D393 修复（离线复算通过），待整批真实运行确认；随后重跑 24/27 份，确认 G16 修复在整批的收益。不能把 6/7 定向通过当成 24 份或 27 份整批通过。
- 变更记录：2026-10-27 新增（原误编号 FL-D389，同日改为 FL-D391，避免与 model_error evidence 条目冲突）；与 FL-D384 的重复副本/no-op 问题分开记录。

## FL-D381 TOC bookmark/分页标记被当作只读屏障，导致第一批合同大量目标不可编辑（2026-10-27）

- 发现日期：2026-10-27，用清理后的 `基金合同第一批` 做 3 份真实 smoke 时。首轮 `/tmp/opencode/first-batch-smoke-20261027` 三份均 `incomplete`；QDII 和景宁纯债各只有 1 个 edit、97/112 unresolved，价值优选 G14 目标跨 barrier 失败。
- 问题与影响：真实基金合同大量使用 `_Toc...` bookmark 包住整节；`_protected_text_nodes()` 把 bookmark/comment/perm 范围内的文字全部标为受保护，导致 `ParagraphSpan.segments=[]`，正文目标全部被 `RECALL_TARGET_STRUCTURE` 拒绝。另有 `lastRenderedPageBreak`/`proofErr` 被当作编辑屏障；包含这些良性标记的 run 也被判为非普通 run。writer 只接受 `rPr+t` 的连续 run，进一步阻断跨 run 编辑。结果不是定位到了错误条款，而是大量正确正文目标无法进入规划。
- 证据：`/tmp/opencode/first-batch-smoke-20261027/run/*/report.json` 中 QDII/景宁 `segments=[]`、`RECALL_TARGET_STRUCTURE`；`/tmp/opencode/first-batch-smoke3-20261027` 为修复后重跑。结构回归新增/更新于 `tests/test_docx_structures.py`。
- 处理方法：bookmark 不再保护或切断文本；`lastRenderedPageBreak`/`proofErr` 不再作为 barrier，普通 run 允许 `rPr`、`t` 及这些良性标记；writer 允许一个文本 run 带良性标记，并在编辑范围内丢弃导航/分页标记、保留范围外标记；`_structure_snapshot` 在已编辑段落中忽略这些非业务标记。comment/perm 范围仍保持只读。
- 状态与验证：**代码修复已实施并通过聚焦回归；3 份 smoke 中 1 份 complete、2 份仍 incomplete，剩余问题不属于本条。** 聚焦套件 **370 passed**，`git diff --check` 通过。修复后 `/tmp/opencode/first-batch-smoke3-20261027`：价值优选 `complete`、16 edits、Claim Replay verified、final/redline 生成；QDII 13 edits、景宁 18 edits，但仍分别有 G14/G18 和 G04/G05 未闭合。首轮 smoke 的失败证据保留。
- 下一步：继续处理 QDII G14/G18 的业务措辞/站点缺失、景宁 G04 正确类别设置站点和 G05 摘要副本残留；完成后再跑全量 27 份。不能把本次 1/3 complete 当作整批通过。
- 变更记录：2026-10-27 新增；与 FL-D370 的物理范围/复合边界修复分开记录，不把 bookmark 兼容当成定位范围放宽。

## FL-D383 V1 Compare 拖动长合同时每帧重排导致明显延迟（2026-10-27）

- 发现日期：2026-10-27，用户反馈生产 Compare 拖动中间分隔条延迟很高。
- 问题与影响：V1 原实现每个 `pointermove` 都改写 `#compare-columns` 的 `grid-template-columns`，两栏内上千个差异标记随之重排；同时给 `body` 增加 `compare-resizing`（继承 `user-select:none`）和给栏容器增加 `is-resizing` 类，触发大规模样式重算。长合同（约 1200 处差异）拖动时出现 60ms 级长任务和明显卡顿。
- 证据：在生产同源 `f4bb2b7` worktree 用 1200 处差异做拖动基准。优化前：60 步拖动期间 `longCount=2`、`longTotal=124ms`、`longMax=65ms`、平均帧 21.10ms、最大帧 66.7ms。优化后（预览线 + 缓存差异标记 + 去掉全局/容器拖拽 class）：拖动期间 `longCount=0`、`longMax=0`、平均帧 16.84ms、最大帧 33.4ms；松手应用宽度后也无长任务，平均帧 16.82ms。基准脚本为生产 worktree 内临时测试，未提交。
- 处理方法：
  - 拖动期间不修改两栏 grid，只移动绝对定位的 `#compare-split-preview` 预览线；松手（pointerup）才一次性应用比例并重绘 SVG 连线；pointercancel 恢复原比例。
  - 指针按下时缓存容器 left 和可用宽度，避免每次 pointermove 读取 `getBoundingClientRect()` 强制布局。
  - 每次打开结果时缓存左右 `[data-diff-id]` 元素 Map，`drawLines()` 复用，不再每帧重新 `querySelectorAll` 全量标记。
  - 移除 `body.compare-resizing` 与 `#compare-columns.is-resizing` 的全量样式切换，预览线改用内联 `left/opacity`。
- 状态与验证：**工作区 V1 已同步优化；生产 V1 已发布并验证**。生产文件哈希：`compare.html` `0ae47e357fbcff6eb3a49e9a5355844397649c019b26357fc22425f8e933dc67`、`compare.css` `5ed37b4716e8e0ad0a50a1074f2a81ca804bbb0fd3e0ac3b545d7fc26f52cf17`、`compare.js` `95cb49865439dedb40ccf355aaccc0957c8fd2dfa0784657bef8537921d686c2`；上一版备份 `/tmp/opencode/fundlex-compare-splitter-lazy-20261027/`。后续 FL-D385 收窄差异栏并简化为“采用 A/B”，当前哈希以 FL-D385 为准。公网资源版本 `facff813d27d0f23`；1440/390 浏览器检查 0 页面错误/0 控制台错误/0 404，1440 分隔条可见、390 隐藏。工作区完整浏览器 **45 passed / 117.53s**，前端 typecheck/lint/Vitest **14 passed**；未创建真实合同任务、未调用模型。
- 下一步：如果产品要求拖动过程中栏宽实时跟随，而不是预览线，需要进一步做长文档虚拟化/分块渲染或降低重排范围；当前以“预览线 + 松手应用”换取稳定 60fps。V2 的 antd Splitter 仍为实时布局，未发布。
- 变更记录：2026-10-27 新增；同日完成 V1 工作区同步、生产定向发布和公网验证；生产基线分叉见 FL-D382。因并行登记已占用 FL-D380/FL-D381，本条改用 FL-D383，既有重复编号不重命名。

## FL-D382 生产前端基线 f4bb2b7 与当前工作区分叉，禁止整树发布（2026-10-27）

- **2026-10-28 引擎整改规划接续**：本条生产/工作区分叉列为新方案S0/S10发布前置条件；必须建立保留生产Compare/飞书/指引生成修复的唯一干净候选，不能从旧HEAD或dirty整树覆盖。详见 `docs/SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md` §7；主agent本轮未发布/合并生产文件，只记录计划。worktree不会自动继承相关未提交源码，先验证可恢复基线再并行。

- 发现日期：2026-10-27，部署 Compare 可调双栏前核对生产文件哈希。
- 问题与影响：生产 `/opt/fundlex-recall-first/frontend` 的 `workspace.js`、`compare.html`、`compare.js`、`compare.css`、`app.js`、`app.css` 与提交 `f4bb2b7` 完全一致；当前工作区 `frontend/compare.html`/`compare.js`/`compare.css` 是另一套较早的 Compare 实现，缺少生产已有的三业务工作台、独立差异 rail、选择版控件等。`tools/deploy/publish_workspace.sh` 会整树复制 `frontend` 等目录，直接执行会把生产 UI 回退，属于事故风险。
- 证据：生产 `compare.html` SHA-256 `47e255a43e04a5d146e2df7097f62b46e0fa7260d9d8d0127d096ac4b1a32f0d`，工作区 `compare.html` 为 `024620673cb6f62f32f78d6c53b3223e7abd3e03c28228b7f5538cf87f620f76`；生产 `workspace.js` 哈希 `5098f14c...` 对应 `f4bb2b7:frontend/workspace.js`，工作区没有该文件。生产 `compare.js`/`compare.css` 同样分别匹配 `073ee351...`/`706e1e07...`。
- 处理方法：未执行整树发布器。创建独立 worktree `/tmp/opencode/fundlex-prod-f4bb2b7`（detached `f4bb2b7`），仅移植 V1 Compare 分隔条改动；在该工作树用生产同源代码跑 Compare 选择版浏览器套件 **14 passed**（含临时分隔条拖动/键盘/复位验证）；备份生产原文件到 `/tmp/opencode/fundlex-compare-splitter-20261027/` 后，仅 `install` 替换 `compare.html`、`compare.css`、`compare.js` 三个文件并重启 API。
- 状态与验证：**生产 V1 已发布并验证；React V2 未发布，生产基线仍为 `f4bb2b7`**。首次发布文件哈希为 `compare.html` `619d21a5...`、`compare.css` `a16eb68f...`、`compare.js` `3718860e...`；后续 FL-D383 拖动性能优化再次替换三个文件，当前哈希和资源版本以 FL-D383 为准。首次发布后公网首页 200，资源版本 `9d96418f326f2ca7`，无登录浏览器检查 1440/390 两档均 `page_errors=[]`、`console_errors=[]`、`bad_responses=[]`，无横向溢出；1440px 下 `#compare-gutter` 为 `display:block`、`cursor=col-resize`，390px 下为 `display:none`。API active、capabilities 200；Worker/Compare/Feishu 服务 active。未创建真实合同任务、未调用模型。
- 下一步：下次正式候选发布前，先把工作区/目标分支与生产基线 `f4bb2b7` 的差异合并或建立唯一 clean candidate，禁止从当前 dirty 工作区直接运行 `publish_workspace.sh`；V2 的 antd Splitter 与 dist 仍只在工作区，未发布。
- 变更记录：2026-10-27 新增；本条记录的是生产前端基线与工作区分叉及本次受控定向发布，不把定向发布当作完整候选发布。

## FL-D379 React V2 与 V1 Compare 接入可调双栏（Ant Design Splitter / 原生等价实现）（2026-10-27）

- 发现日期：2026-10-27，用户明确要求把 Ant Design Splitter 加到合同对比双栏阅读器；首轮只改 React V2，用户指出默认入口是 V1，实际看不到改动，随后补齐 V1。
- 问题与影响：原 Compare 固定平分双栏，用户无法按合同排版或阅读习惯调整左右宽度。默认前端版本为 `v1`，仅改 React V2 不构成真实用户交付；V1 是原生 HTML/CSS/JS，不能直接挂 React 版 Ant Design Splitter。接入还要避免影响面板滚动、SVG 连线坐标、移动端单栏切换和首包体积。
- 处理方法：
  - React V2：新增 `antd@^6.6.8`，从 `antd/es/splitter` 引入 `Splitter`；桌面端两个 `Splitter.Panel` 默认 50/50、最小 20%、最大 80%，保留独立滚动；`onResize` 以 `requestAnimationFrame` 节流重算 SVG 连线；≤760px 继续单栏切换。Compare 路由改为懒加载，避免 antd 进入所有页面首包。
  - V1：把原 `#compare-gutter` 改为可聚焦的 `role="separator"`，支持指针拖动、ArrowLeft/ArrowRight（Shift 为 5%）、Home/End、Enter/Space 或双击恢复 50/50；同步更新 `aria-valuenow/aria-valuetext`，比例写入 `localStorage`，A/B 栏头跟随同一比例，拖动时重算 SVG 连线；≤760px 分隔条隐藏，保留原单栏切换。
- 证据与验证：`npm run typecheck`、`npm run lint`、Vitest **14 passed**、`npm run build` 通过；最终构建主包 `index-415qcxFU.js` 410.28 kB、Compare 分包 `ComparePage-Dxc-_qlf.js` 117.49 kB、CSS `index-x3FanAza.css` 37.49 kB，构建不再出现 >500 kB 警告。完整浏览器套件 **45 passed / 101.98s**：V2 Compare 用例在 1440px 验证 `.compare-splitter`、两个面板、拖拽条和 SVG 连线，拖动后左栏宽度由 358.89px 缩小；V1 新增用例真实拖动 `#compare-gutter`，验证键盘 ArrowLeft 继续缩窄、Enter 恢复 50/50、390px 自动隐藏。V1 截图 `/tmp/opencode/compare-v1-splitter.png` 已核对栏头与正文分界对齐。未部署、未调用真实模型。
- 状态与验证：**V1 默认工作台已完成生产定向发布并验证；React V2 已实施但未发布**。V1 分隔条键盘可调；V2 的 antd 拖拽条由组件内部实现，当前没有 tabIndex，键盘用户不能直接调整栏宽，且 V2 上方栏头仍按固定中缝布局，拖动后与面板边界会有轻微视觉偏差。生产发布细节、文件哈希、备份和基线分叉见 FL-D382。
- 下一步：如需 V2 也完整键盘可调，在外层增加可聚焦的“重置 50/50”或键盘调整入口；如需 V2 栏头严格跟随宽度，把栏头移入各面板或增加尺寸同步。后续正式候选发布前先解决 FL-D382 的基线与工作区分叉，不能把本次 V1 定向发布当作完整候选发布。
- 变更记录：2026-10-27 新增；首轮记录仅覆盖 React V2，随后按用户反馈补齐默认 V1 并更新验证；同日完成 V1 生产定向发布，新增 FL-D382；替代 FL-D361 中“暂不引入第三方组件”的当前判断，FL-D361 的历史评估保留。

## FL-D378 最终 sweep 将带源前缀的已满足 G09 最终句误判为 SEMANTIC_UNCERTAIN（2026-10-27）

- 发现日期：2026-10-27，隔离 V1 工作台真实浏览器运行 D06 时。任务 `245072062ecb4e6491efab7bf2573ee4`（文档 `ac3ce1d2d81d4448a1d07259359dc4d5`）以 `delivery_status=complete` 完成，但首轮浏览器运行 `86849152342e4e6d990d34d2f63c3267` 因 G09 最终 sweep finding 被保留为 `pending` 而 `incomplete`。
- 问题与影响：G09 `SW004` 的 quote 是最终 artifact 的完整句子“某类基金份额的赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额的基金份额净值并扣除或加上相应的费用，赎回金额单位为元。”，其 reason 明确写“G09 已满足”；但 `_quote_is_expected_effect()` 只接受“引文完全包含在实例化 new_text 中”，不接受“引文以完整 new_text 结尾且带源前缀”，导致 `expected_quote=false`，随后 `wrong_text + residual` 分支将 finding 标为 `SEMANTIC_UNCERTAIN`。最终遗漏复核因此产生 `FINAL_MODEL_SWEEP_FINDING` 和 `OPEN_OBLIGATION`，交付 fail-closed 为 `incomplete`，无法生成正式 final/redline 或完成结果页下载。
- 证据或复现线索：失败证据 `/tmp/opencode/d06-browser-real-20261027`，28 HTTP / 约 `$0.0332823`；报告对象中的 `sweep.findings` 含 `SW004`，`final_omission_review.status=FAIL`，`delivery_gate.open_obligations=1`。最小复现可直接用 G09 record、带“某类基金份额的”前缀的最终句和 `actual_text` 调用 `_quote_is_expected_effect()`，修复前返回 `False`。
- 处理方法：在 `fundlex/recall_pipeline.py` 的 `_quote_is_expected_effect()` 增加有界兼容：引文必须实际存在于最终 artifact，且在去除末尾标点后以该 operation 的完整实例化 new_text 结尾；调用方仍必须先有同 operation/site 的 `effect_proof_passed`，策略后追加未授权文本不会通过。新增回归 `tests/test_final_validation_regressions.py::test_g09_sweep_quote_with_source_prefix_is_expected_effect`，覆盖正例、策略后追加文本反例、以及 `_apply_artifact_proof_to_findings` 将该 finding 收敛为 `resolved`。
- 状态与验证：**代码修复已实施，隔离真实浏览器 D06 路径已验证；生产部署与固定 D01–D20/holdout 仍未完成。** 聚焦套件 `tests/test_recall_core.py tests/test_append_applicability.py tests/test_ff4d749_gate_closure.py tests/test_operation_execution_closure.py tests/test_final_validation_regressions.py tests/test_replay_site_provenance.py tests/test_recovery_final_invariants.py` 为 **306 passed**；`py_compile`、`git diff --check` 通过。用失败运行的真实最终 DOCX、plan、Claim Replay 和 findings 离线复算，`SW004` 由 `pending/SEMANTIC_UNCERTAIN` 变为 `resolved/REVIEW_UNPROVEN`，最终遗漏复核由 `FAIL` 变为 `PASS`。随后浏览器重跑 `/tmp/opencode/d06-browser-real-20261027b`：任务 `completed`、文档 `succeeded/complete`、49 targets/0 unresolved、Claim Replay verified、最终遗漏 PASS、19 个段落变化、final SHA `0b25951e...`、redline SHA `d52faf32...`；结果页显示“可直接使用/已通过交付校验/最终版 DOCX/修订版 DOCX”，下载与报告哈希一致，未授权下载 401。重跑临时脚本在下载后的 `docx_check` 字段名上误取 `sha256`，故原始 `result.json` 为 failed；独立 `browser-verification.json` 对保留证据的 12 项检查全部通过，原始失败记录保留不覆盖。
- 工具兼容：为运行隔离 API/Worker 路径，`tools/evaluation/delivery_e2e.py` 的 Claim Replay 断言同时接受当前 recall 报告的 `verified` 和旧 fixture 的 `passed`；`tests/test_delivery_e2e.py` **2 passed**，fixture 全用户路径仍通过。该修改只放宽报告字段别名，不放宽 Claim Replay 证据。
- 下一步：将隔离工作台验证与生产部署/普通工作台 E2E 分开记录；继续固定 D01–D20、holdout、独立标签和 candidate freeze，不能用本次单合同通过替代整批评测或生产交付。

## FL-D398 Residual 在 `MODEL_CIRCUIT_OPEN` 时五轮全部 blocked（2026-10-28）

- 发现日期：2026-10-28，smoke24 Residual 五轮 0 次实际调用。
- 问题与影响：`ModelBudget` 在最近 3 个请求均为服务错误时打开 circuit，冷却 120s；Residual 阶段紧接 quality/coverage，circuit 未冷却，五轮都直接失败并记 blocked，`saturated=false`，但这不是“未发现新影响”的证据。
- 处理方法：`ResidualConfig.circuit_wait_s=130`；`run_residual_mining()` 遇到 `MODEL_CIRCUIT_OPEN` 时等待冷却并重试一次，重试仍失败才记 finding/blocked。不把 blocked 当 clean。
- 状态与验证：**已实施并通过离线回归**。新增 circuit 首次失败、等待后成功的用例，断言 2 次调用且 `saturated=true`；`tests/test_guide_generation.py` **31 passed**。smoke25 待真实验证。
- 变更记录：2026-10-28 新增。

## FL-D397 扫描窗口全局轮转未按合同保证逐要求覆盖（2026-10-28）

- 发现日期：2026-10-28，smoke24 的 42 个 latest uncertain 全部为“该要求未被语义扫描覆盖”。
- 问题与影响：19 个窗口的 requirement_ids 并集覆盖 76/77 个要求，但窗口按两份合同混合分配；latest 合同仍有 42 个要求从未进入该合同窗口，逐要求覆盖无法区分 not_affected 与 never_scanned。
- 处理方法：`path_b_contract_sweep()` 按合同统计已覆盖要求；对未覆盖要求分组，并对该合同的**所有条款批次**补扫（coverage tail），确保每个要求在每个合同至少出现一次。smoke25 将 `path_b_max_calls` 放宽到 150 以容纳 tail。
- 状态与验证：**已实施并通过离线回归**。新增双合同/20 要求用例，断言每个合同的窗口覆盖全部要求；法规两套件 **31 + 52 passed**。smoke25 待验证。
- 变更记录：2026-10-28 新增。

## FL-D396 smoke24：quality 与独立复核已通过，剩余为按合同窗口缺口和 circuit 阻断 Residual（2026-10-28）

- 发现日期：2026-10-28，glm reviewer + 扁平轮转窗口 + 5 轮 Residual 的 smoke24。
- 结果：**quality `pass_with_findings`、critical_quality 0、requirement gaps 0、unresolved 3、independent_model_review_status=qualified**（reviewer glm-5.3-flash、author deepseek-v4.1-flash）。仍未 candidate_ready：latest contract uncertain **44**、Residual 五轮全部 `blocked`（`MODEL_CIRCUIT_OPEN`，0 次实际 residual 调用）、quality 518 findings 但无 critical。费用 $1.141186、603 requests。
- 证据：run `520a39742a4c47af8c1c15da65490d96`；44 个 uncertain 中 **42** 为“该要求未被语义扫描覆盖”，2 为批次 uncertain。19 个 sweep 窗口的 `requirement_ids` 并集覆盖 76/77 个要求，但窗口按合同混合分配；latest 合同仍有一批要求从未进入该合同的窗口。Residual 的 `MODEL_CIRCUIT_OPEN` 由前序 46 次 schema attempt、23 次网络错误、6 次 HTTP 错误触发；电路打开后 85 次 residual 调用全部未执行。
- 根因：轮转窗口是全局的，未按合同保证每个要求至少出现一次；模型网关 circuit breaker 在 provider 波动后保持打开，导致 Residual 无法执行。
- 处理方法（待实施）：(a) 按合同建立 coverage tail：构建 jobs 后统计该合同未出现在任何窗口的要求，追加若干窗口直到每个要求至少出现一次；(b) Residual 在独立进程/恢复 circuit 后运行，或调整 circuit 阈值/退避，不能用 blocked 轮次冒充饱和。
- 状态与验证：**quality 与独立复核已通过；覆盖/Residual 未闭合，未达资格**。smoke24 目录/账本保留。
- 下一步：实现按合同 coverage tail 和 circuit 恢复，跑最后一次定向验证；若仍失败，记录真实内容/覆盖限制，不再重复全量 smoke。
- 变更记录：2026-10-28 新增。

## FL-D395 smoke23：独立复核合格、文本 critical 清零，但窗口轮转与 glm 截断仍阻断（2026-10-28）

- 发现日期：2026-10-28，配置 glm-5.3-flash 独立 reviewer 后的真实 smoke23。
- 问题与影响：独立复核已合格（`qualified`），`critical_quality=0`、gaps=0、unresolved=3；但仍为 `candidate_with_findings`：latest uncertain **58**、Residual **10/4/1** 未饱和、quality `fail`（open critical：11 semantic_coverage + 1 contract_coverage）、`guide_quality_review` 出现 **47 次 MODEL_OUTPUT_TRUNCATED**。费用 $0.960993，626 requests。
- 证据：run `9f7872b1fd1041d499c46c30b4123a7c`；58 个 latest uncertain 全部原因为“该要求未被语义扫描覆盖”；reviewer identity 为 `glm-5.3-flash`、`same_model_as_author=false`、`independent_model_review_status=qualified`。
- 根因：(a) 轮转窗口按 12 条切片只取前 4 条，绝大多数要求从未进入窗口；(b) glm quality review 输出过长触发截断；(c) Residual 仅 3 轮。
- 处理方法：轮转游标改为在**扁平全量要求列表**上循环，并加 `rotating_attempts < len(requirements)` 上界（避免全部已在相关窗口时死循环）；QUALITY_INSTRUCTION 限制最多 8 条 finding、描述 ≤60 词、引文 ≤300 字符；TOPIC_COVERAGE_INSTRUCTION 明确等价条件/数字上限可判 covered；smoke24 将 reviewer max tokens 提到 12000、Residual 轮数 5。
- 状态与验证：**定向修复完成，待 smoke24**。法规两套件 39 passed；完整回归运行中。smoke23 仍不是资格证据。
- 变更记录：2026-10-28 新增。

## FL-D394 全量回归期间根分区写满，测试结果无效（2026-10-28）

- 发现日期：2026-10-28，`full_pytest_final14_20261028.log` 在 83%–99% 出现大量 E，日志在 traceback 中途截断；随后 shell 无法写 stdout，`echo` 失败。
- 问题与影响：根分区写满（`df` 显示 40G 中 37G 已用、仅约 608MB 可用，99%）。pytest 临时目录、模型 checkpoint 与历史 smoke 数据累积；该轮全量回归的 F/E 不能作为代码回归结论。
- 证据：日志 3%/19%/55%/67%/75% 出现 F，83%–99% 大量 E，末尾 traceback 截断；删除 `/tmp/pytest-of-opencode/pytest-*` 后 shell 恢复，`df` 报告 608MB 可用。法规六套件随后 **81 passed**，说明最后两项改动（单窗口、merge cluster 12）本身通过定向回归。
- 处理方法：只清理 pytest 临时目录（非历史证据），未删除 smoke 目录、账本、`operation-validation-20261024` 或用户文件；未反复清理 `/home/opencode/.cache`。
- 状态与验证：**环境阻塞，未解决**。全量回归需在扩容或释放至少数 GB 后重跑；smoke23 尚未启动。项目继续 NO-GO。
- 下一步：扩容根分区或把测试/运行临时目录迁到大盘，重跑全量回归；再运行 smoke23。不得用本轮被 ENOSPC 污染的日志宣称通过。
- 变更记录：2026-10-28 新增。

## FL-D393 smoke22 续跑撞共享账本上限，merge schema 失败与 Residual 预算耗尽（2026-10-28）

- 发现日期：2026-10-28，smoke22 首次运行被 2 小时工具时限终止后按阶段续跑完成。
- 问题与影响：续跑最终 `complete_with_unresolved / candidate_with_findings`；latest uncertain 0，但 unresolved 24、critical_quality 6、missing_topics 7、Residual 第一轮 5 个新影响后两轮因预算 `MODEL_GLOBAL_CALL_BUDGET_EXCEEDED` 记为 blocked，不能证明饱和。共享账本达到 2000 requests，实际计费约 $1.446136；`guide_merge` 出现 20 次逻辑 `MODEL_SCHEMA_INVALID`（ledger 107 次 attempt 级失败），`guide_residual_sweep` 68 次预算失败。该运行不是资格证据。
- 证据：run `3ce81c396a8443728e84b9f2a121e76e`，`gg_model_calls` 1994、findings 2635、requirements 82、impacts 1150、items 109；ledger 2000 requests；`gg_model_calls` 错误码为 merge 20 schema、residual 68 budget、local/coverage 预算；`gg_evidence` sweep 无 model_error。
- 处理方法：不降低 schema/门禁、不改写账本。下一轮必须：(a) 用更省调用的窗口策略（每批 top 相关 + 少量轮转，单窗口）降低 sweep/resolver 调用；(b) 对 merge 增加逐对象字段自检/更小 cluster，减少 20 次 schema 失败；(c) 预登记更高但明确的账本上限与并发 2，避免 Resid 因预算被迫 blocked；(d) 运行器使用更长时限或分段续跑。
- 状态与验证：**运行完成但未达资格；新问题已部分修复**。smoke22 目录/账本保留，不删除、不改写。
- 已实施：`path_b_contract_sweep` 每批改为单窗口（最多 8 条相关 + 轮转补齐至 12），避免窗口翻倍；`AuthoringConfig.merge_max_members` 30→12；MERGE_INSTRUCTION 增加逐对象全字段/local_ids 子集自检。smoke23 预登记 3000 requests / $36 账本、2400 calls / $32 运行、并发 2。
- 下一步：全量回归通过后跑 smoke23；只有质量/覆盖/Residual/独立身份全部通过才算完成。
- 变更记录：2026-10-28 新增。

## FL-D392 施行/废止条款被当作合同修改要求，产生不可用指引（2026-10-28）

- 发现日期：2026-10-28，smoke21 的 open `regulation_fidelity` 中包含“法规施行日期/废止条款被写成合同 new_text”类 critical。
- 问题与影响：要求抽取/复核会把“本规定自 2026-01-01 起施行、原公告废止”作为 `modify_contract` 或 `needs_external_baseline`，后续 authoring 生成以施行/废止为 scope 的 GuideItem；质量复核正确地判为“把法规生效条款塞进合同”，但该要求本不应进入合同修改集合。
- 处理方法：`extract_requirements()` 最终处置阶段对“纯施行/废止条款”（命中施行/生效/废止，且不含基金合同/销售协议/费用等合同义务词）统一改为 `out_of_contract_scope`，理由“施行/废止条款不直接产生合同修改义务”。不删除来源引文，不降低质量门禁。
- 状态与验证：**已实施并通过离线回归**。新增用例返回 modify_contract 的施行/废止要求，断言最终为 `out_of_contract_scope`；`tests/test_guide_generation.py` **29 passed**。smoke22 待验证该类 critical 是否消失。
- 变更记录：2026-10-28 新增。

## FL-D391 扫描窗口只取 top-12 导致部分要求从未被合同扫描覆盖（2026-10-28）

- 发现日期：2026-10-28，smoke21 的 latest uncertain 101 且无模型错误，确认是窗口缺口而非模型失败。
- 问题与影响：每个条款批次只选 top-12 相关要求；部分要求从未进入任何窗口。逐要求覆盖修复后，这些要求只能判“未被语义扫描覆盖” → uncertain，导致 latest uncertain 反弹。
- 处理方法：每个条款批次除相关窗口外，再增加一个轮转要求窗口（覆盖全部要求集合的滚动切片），保证每个要求至少进入一个 sweep 窗口；证据记录 `requirement_ids`。`resolve_uncertain_batches()` 扩展为对 `affected` 与 `uncertain` 批次都做逐要求裁决，并使用证据中的窗口而非重新计算 top-12，避免窗口漂移。
- 状态与验证：**已实施并通过离线回归**。既有 path_b/retry/窗口测试通过，`tests/test_guide_generation.py` **29 passed**。smoke22 待验证 latest uncertain 与召回。
- 变更记录：2026-10-28 新增；调用数会增加（约每批 +1 次），仍在 1800 calls 预算内。

## FL-D390 合同×要求覆盖被批次级状态拖累，未使用逐要求裁决（2026-10-27）

- 发现日期：2026-10-27，分析 smoke20 的 41 个 latest uncertain 时确认。
- 问题与影响：`coverage.py` 仍按合同聚合 sweep 状态；一个 affected/uncertain/error 批次会让该合同所有无 Impact 要求变成 uncertain。P10 已有逐要求 resolver 结果，但覆盖层没有使用，导致 41 个 latest uncertain 无法按证据关闭。
- 处理方法：每个 sweep 批次记录其 requirement 窗口；覆盖按 requirement 过滤批次。若批次有 `resolution.resolved`，该要求直接采用 resolver 的 `affected/not_affected/uncertain`；否则仅当批次窗口包含该要求时才使用批次状态。只有所有相关批次明确 not_affected 才关闭；affected 但无 Impact、uncertain、model_error、无相关批次均保持 uncertain。
- 状态与验证：**已实施并通过离线回归**。新增用例：一个 affected 批次只覆盖 R-0、一个 not_affected 批次只覆盖 R-1，断言 R-1 为 not_affected、R-0 为 uncertain；`tests/test_guide_generation.py` **28 passed**。smoke21 待验证 41 uncertain 是否下降。
- 变更记录：2026-10-27 新增；不放宽为合同级 not_affected。

## FL-D389 重试成功后仍残留 model_error evidence 导致整合同 uncertain（2026-10-27）

- 发现日期：2026-10-27，分析 smoke20 的 `gg_evidence` 时确认。
- 问题与影响：`path_b_contract_sweep()` 在首次失败时立即写入一条 `status=model_error` evidence；随后有界重试成功时又写入 success evidence，但旧的 error 行没有删除。覆盖 `_sweep_state` 看到 errors>0，就把该合同所有无 Impact 要求判 uncertain。smoke20 有 13 affected/6 not_affected/2 model_error，41 个 latest uncertain 由此产生。
- 处理方法：失败 attempt 不再立即写 evidence；重试成功只保留 success evidence，重试失败才写一条 `uncertain` + `MODEL_RETRY_EXHAUSTED`。success evidence 同时记录本批 requirement 窗口，供逐要求覆盖使用。
- 状态与验证：**已实施并通过离线回归**。新增“首次失败、重试成功”用例，断言 `calls=2`、evidence 只有一个 `not_affected`、无 `model_error`；`tests/test_guide_generation.py` **28 passed**。smoke21 待验证。
- 变更记录：2026-10-27 新增。

## FL-D388 repair 覆盖 item 后丢失直销渠道边界，重新引入 critical（2026-10-27）

- 发现日期：2026-10-27，分析 smoke19 唯一 `critical_quality`（直销禁止收费与历史份额收费被无条件拼接）时确认。
- 问题与影响：authoring 的 `_normalise_direct_sale_candidate()` 会给历史份额收费句加“通过其他基金销售机构销售本基金份额时”边界；但 `repair_items()` 用 repair 模型返回的完整 item 覆盖 `new_text`/conditions/exceptions，之后没有重新应用该规范化。repair 一旦返回拼接文本，就会把已修复的渠道边界丢掉，产生新的 regulation_fidelity critical，且第二轮 repair 仍可能重复。
- 证据：smoke19 open critical 描述“直销禁止收费与历史份额收费结构被无条件拼接，未保留销售渠道边界”；`repair.py` 原代码只调用 `_auto_fix_item()`，未再调用 `_normalise_direct_sale_candidate()`。
- 处理方法：repair 后用 `LocalGuideCandidate` 代理重跑 `_normalise_direct_sale_candidate()`，把规范化后的 new_text/conditions/exceptions/applicability 写回 GuideItem；不改变 critical 判定、不删除 finding。
- 状态与验证：**已实施并通过离线回归**。新增 repair 用例：模型返回“直销禁止 + A类收费”拼接文本，断言修复后包含“其他基金销售机构”边界；`tests/test_guide_generation.py` **26 passed**。smoke20 待验证该 critical 是否消失。
- 变更记录：2026-10-27 新增。

## FL-D387 覆盖缺口补写创建了 Impact 但 authoring 未产出 item（2026-10-27）

- 发现日期：2026-10-27，分析 smoke19 的 `supplement` 时确认。
- 问题与影响：`stage_supplement()` 为 10 个真实未覆盖主题创建了 coverage-topic Impact，但 `stage_authoring()` 对这些 Impact 没有产出任何 GuideItem（`created=10`、两轮 `new_items=0`），剩余 16 个主题仍未覆盖。原因是这些 Impact 的 `impact_status=possible` 且锚点条款可能并非真正需要修改；作者模型返回 no/空候选后，没有像 definite Impact 那样的保守兜底，补写空转。
- 证据：smoke19 run `3b4543d0ecda4feeaff169d30b894716`，payload `supplement={"created":10,"remaining_topics":16,"rounds":[{"created":5,"new_items":0},{"created":5,"new_items":0}]}`；`coverage.missing_topics` 仍有 16 条。
- 处理方法：`stage_authoring()` 的保守兜底扩展到带 `metadata.coverage_topic` 的 Impact；模型没有产出 yes+文案时，生成 `new_text=requirement.source_quote`、`new_text_origin=regulation_verbatim` 的候选，`notes=coverage_topic_fallback`，并保留 topic 描述与锚点证据。候选仍需质量复核/修复，不能用兜底绕过 critical 或覆盖门禁。
- 状态与验证：**已实施并通过离线回归**。补充 pipeline 用例让 coverage-topic authoring 返回空候选，断言补写轮次 `new_items>=1`；`tests/test_guide_generation_pipeline.py` **10 passed**。smoke20 待验证。
- 变更记录：2026-10-27 新增；兜底只在模型无候选时使用，不替代模型改写。

## FL-D386 单个 uncertain 扫描批次使整份合同所有要求变成 uncertain（2026-10-27）

- 发现日期：2026-10-27，分析 smoke17 的 115 个 latest contract uncertain 时确认。
- 问题与影响：`coverage.py` 的 contract×requirement 行按合同聚合扫描状态；只要该合同任意一个 sweep 批次状态为 `uncertain`，所有没有 impacted 的要求都被判 `uncertain`。smoke17 有 4 个 uncertain 批次、100 requirements，直接产生约 115 个 latest uncertain，成为覆盖门禁的主要阻断，而其中很多要求其实与 uncertain 批次无关。
- 处理方法：新增 `resolve_uncertain_batches()`，对每个 uncertain 批次用严格 `guide_batch_resolve` schema 逐要求判定 `affected/not_affected/uncertain`；`affected` 必须给出批次内 clause_ids 和可回查的 evidence_quote 才生成 Impact；只有模型明确把**该批次全部窗口要求**标为 `not_affected` 才把批次状态改为 `not_affected`；任何遗漏/uncertain/证据不匹配都保持 `uncertain`。`guide_batch_resolve` 已注册到 ModelGateway 任务白名单。
- 状态与验证：**已实施并通过离线回归，smoke19 真实验证成功**。新增三分支用例：全部 not_affected → 批次关闭、0 Impact；一个 affected → 生成对应 Impact、批次 affected；遗漏一个要求 → 批次保持 uncertain。`tests/test_guide_generation.py` **25 passed**。smoke18 在 P10 前启动，已中止（12 次逻辑调用、账本 14 requests、约 $0.0238）；smoke19 latest contract uncertain 从 **115 降为 0**，覆盖未决 impacts 从 10 降为 **2**。
- 变更记录：2026-10-27 新增；不把“批次不确定”直接当作全合同不确定，也不放宽为全合同 not_affected。

## FL-D385 单轮质量修复后仍有文本 critical（2026-10-27）

- 发现日期：2026-10-27，smoke17 仍有 9 个 `critical_quality_findings`（draft 4 + regulation 5）。
- 问题与影响：`stage_repair()` 只执行一轮 repair + 复审；新一轮 critical 没有第二次修复机会，导致可修复的文本缺陷停留在候选外。
- 处理方法：`PipelineConfig.repair_rounds=2`；每轮只读取最新 open critical，修复后只复审被修项，仍有 critical 才进入下一轮；不降低 severity、不删除 finding。
- 状态与验证：**已实施并通过离线回归**。新增“首轮 critical→修复→复审通过”用例；`tests/test_guide_generation_pipeline.py` **10 passed**。真实效果待 smoke18。
- 变更记录：2026-10-27 新增。

## FL-D384 覆盖审计主题级判定与补写闭环（2026-10-27）

- 发现日期：2026-10-27，smoke17 出现 78 个 `semantic_coverage` critical，需要区分审计误报与真实缺口。
- 问题与影响：覆盖审计按批次报告 missing topics，但没有主题级复核；真实缺口也不会进入 authoring，只停留在 critical finding。直接补写全部主题会放大误报，直接删除 critical 又会掩盖真实缺口。
- 处理方法：`CoverageResult.missing_topics` 结构化保存 topic_id/requirement_ids/description/evidence_quote；新增严格 `guide_topic_coverage` 判定（只允许命名真实候选 GuideItem，否则 uncertain/not_covered 保持 open）；仅未覆盖主题保留 critical。`stage_supplement()` 对有 requirement 与合同锚点的主题创建 coverage-topic Impact，进入 authoring→quality→coverage 复审，最多 `supplement_rounds=2`；覆盖复审计前把上一轮 coverage_gate open findings 标记 superseded，避免旧 critical 累积。无要求/无锚点主题保持 unresolved，不伪造。
- 状态与验证：**已实施并通过离线回归**。新增 topic judge covered/not_covered 用例、pipeline 覆盖缺口补写用例；`guide_topic_coverage` 已加入 `ModelGateway.TASK_TYPES` 与 `QUOTE_SELF_VALIDATED_TASKS`（否则真实运行会全部 `MODEL_TASK_UNSUPPORTED`）；法规套件 **75 passed**（含 22 guide + 10 pipeline）。smoke18 待真实复测。
- 变更记录：2026-10-27 新增；不把“审计未识别”当成“已覆盖”，也不删除未解决 critical。

## FL-D383 Residual 扫描只看到部分指引导致无法饱和（2026-10-27）

- 发现日期：2026-10-27，分析 smoke17 Residual 56/29/22 不收敛时确认。
- 问题与影响：`run_residual_mining()` 把 `_guide_summary(items)` 截到 6000 字符放入上下文，smoke17 有 100 个 GuideItem，扫描器只能看到约 20 个；被隐藏条目覆盖的模式被反复报告为新 uncovered impact，导致 Residual 永不饱和并放大覆盖缺口。
- 证据：`residual.py` 原上下文 `guide_context[:6000]`；smoke17 `guide_residual_sweep` 57 次、三轮新增 56/29/22。
- 处理方法：新增 `[ALL_GUIDE_ITEM_INDEX]` 全量紧凑索引（所有 item id/requirement_ids/title）+ 本批相关明细 `[GUIDE_ITEMS_RELEVANT]`；`RESIDUAL_VERSION=guide_residual_sweep_v2`；提示词明确“未在明细中出现不等于不存在”。
- 状态与验证：**已实施并通过离线回归**。40 条指引/40 条要求用例断言全部 ID 可见、上下文 ≤ 32000、单轮 clean 饱和；`test_guide_generation.py` **22 passed**。smoke18 验证真实收敛。
- 变更记录：2026-10-27 新增。

## FL-D382 独立复核模型不可用：现有 API key 对其他模型返回 403（2026-10-27）

- 发现日期：2026-10-27，为解决 `independent_model_review_status=independent_model_review_not_qualified` 做只读模型探测。
- 问题与影响：当前 FundLex 使用的 OpenCode Go API key 仅对 `deepseek-v4.1-flash` 可用；对 `minimax-m3.1-flash`、`glm-5.3-flash`、`qwen3.8-flash` 的 `/chat/completions` 探测均返回 **HTTP 403 Forbidden**。因此无法仅靠代码把 guide_reviewer 配成独立模型；独立模型复核资格仍被外部凭据/模型授权阻断。
- 证据：探测脚本 `/tmp/opencode/probe_second_model.py` 只输出模型名和状态，不打印密钥；三次请求均为 403。`/models` 列表接口同样 403。`GuideModelRouter.identity()` 仍显示 `guide_author` 与 `guide_reviewer` 同为 `deepseek-v4.1-flash`，`independent_model_review=false`。
- 处理方法：不在代码中伪造第二模型或把同一模型改名为“独立”；保留现状并记录阻塞。需要用户/运维提供可用的第二模型端点与凭据（或将当前 key 授权到另一模型），再通过 `FUNDLEX_GUIDE_GUIDE_REVIEWER_MODEL/BASE_URL/API_KEY` 或 roles 文件配置，并完成真实复核。
- 状态与验证：**已解决**。后续探测发现之前 403 是因为探测请求没有带 FundLex 实际使用的 `x-opencode-session`（以及 User-Agent）头；补上后 `glm-5.3-flash` 返回 HTTP 200。真实 `guide_quality_review` 探测返回合法严格 schema（`pass_with_findings`，含 `evidence_quote`/`evidence_quote_2`），成本约 $0.0029889；`GuideModelRouter.identity()` 显示 reviewer=`glm-5.3-flash`、`same_model_as_author=false`、`independent_model_review_status=qualified`。
- 下一步：在 smoke23 中配置 `FUNDLEX_GUIDE_GUIDE_REVIEWER_MODEL=glm-5.3-flash`（其余继承 primary），用完整真实运行验证独立复核；仍需质量/覆盖/Residual 全部门禁通过。
- 变更记录：2026-10-27 新增；本条不包含任何密钥值。

## FL-D381 smoke17 完成：运行稳定性修复生效，但真实覆盖/质量/Residual 仍未闭合（2026-10-27）

- 发现日期：2026-10-27，包含 FL-D379/FL-D380 的 smoke17 完成。
- 问题与影响：smoke17 证明批次/并发/审计可见性/合并完整性修复有效，运行不再中止、无逻辑模型失败；但最终仍未达到 `candidate_ready`。覆盖审计现在能看到全部指引，报告了更多真实/待判定缺口，说明剩余问题是内容覆盖与审计精度，而不是基础设施。
- 证据：run `fd1084ed48284cc5998ffd270a936ab5`，目录 `/tmp/opencode/gg-real-smoke17`，新账本。766 次逻辑调用 **0 error**（`guide_coverage_audit` 32 次、`guide_local_candidate` 425、`guide_quality_review` 110、`guide_residual_sweep` 57 均成功）；100 requirements、1094 impacts、100 guide items、679 findings。finalize `complete_with_unresolved / candidate_with_findings`：requirement gaps **0**、unresolved **10**、latest contract uncertain **115**、critical_quality_findings **9**（draft_text_fidelity 4 + regulation_fidelity 5）、quality `fail`；critical 合计 106（semantic_coverage **78**、draft_text_fidelity 14、regulation_fidelity 13、contract_coverage 1）；Residual 三轮新增 **56/29/22**，`saturated=false`。共享账本 771 requests、实际计费约 **$0.576609**；attempt 级失败 4 条 schema + 1 条 retry exhausted，未形成逻辑失败。
- 与 smoke14 对比：并发/逻辑失败仍为 0；critical_quality 从 0 变为 9，是因为 FL-D377 不再让第二引文把真实 critical 降级，门禁更严格而非质量变差；semantic_coverage 从 31 变为 78，是因为 FL-D379 让审计看到全部指引后报告更多主题，原先 31 个“不可见即缺失”的截断假缺口机制已消除，但仍不能证明剩余 78 个全是真实缺口。
- 处理方法：不降低门禁、不改写结果；确认 FL-D379/380 的运行稳定性收益，同时把剩余工作拆为：(a) P5 覆盖缺口回写闭环（把真实 missing topics 经严格证据绑定转成补充要求/候选并复审）；(b) 审计精度（区分真实缺口与跨批次/主题粒度误报）；(c) 文本 critical 修复与 Residual 饱和策略；(d) 独立模型复核身份。
- 状态与验证：**真实运行完成，确认未达资格**。项目继续 NO-GO；不启动 Blind Benchmark、不发布、不宣称 `candidate_ready`。
- 下一步：实施 P5 并补充回归；在新账本运行 smoke18 验证覆盖缺口是否进入候选并闭合。独立模型身份未解决前，即使其他门禁通过也不能关闭资格。
- 变更记录：2026-10-27 新增；保留 smoke17 目录与账本，不修改 smoke13/14 历史结果。

## FL-D380 local candidate 返回 yes 但无 new_text 导致合并门禁中止整个运行（2026-10-27）

- 发现日期：2026-10-27，smoke16 真实运行在 MERGE_AND_GENERALIZE 阶段中止。
- 问题与影响：smoke16 的 `LG-50b95879a1a1bea62fcc` 返回 `needs_modification=yes` 但 `new_text=""`。`stage_authoring()` 只把“yes 且有文案”的候选放入 `guide_relevant`/`induce_families`，但 `stage_marker_merge()` 把所有 `needs_modification=yes` 的 local 都要求出现在 family 中，于是抛出 `LOCAL_CANDIDATE_NOT_IN_FAMILY`，整个运行以 `ValueError` 中止，后续质量/覆盖/Residual 全部未执行。这是谓词不一致导致的 fail-abort，不是合法的资格失败；也不能靠伪造文案满足门禁。
- 证据：smoke16 run `68af3fbbe3fb43d4b598e92eea7d98cd`，日志错误 `LOCAL_CANDIDATE_NOT_IN_FAMILY:LG-50b95879a1a1bea62fcc`；该 local 的 payload 为 `needs_modification=yes`、`new_text=""`、`new_text_origin=model_drafted`；该运行共 720 local，其中 177 个 yes，只有 1 个 yes 且空文案。
- 处理方法：`stage_authoring()` 在构建 `guide_relevant` 前，把“yes 但没有可审核文案”的候选降级为 `uncertain`，写入 `yes_without_new_text: 无文案，不可作为候选指引` 说明；对应 Impact 保持 `unresolved`，由覆盖门禁阻断，绝不伪造 new_text。`stage_marker_merge()` 的严格检查保留，用于捕获未来不一致。
- 状态与验证：**代码已修复并通过离线回归**。新增流水线用例让 local candidate 返回 `yes + new_text=""`，断言运行不再中止、最终为 `complete_with_unresolved / candidate_with_findings`、相关 local 已降级为 `uncertain`；`tests/test_guide_generation_pipeline.py` **8 passed**，含该修复的全量回归 **1711 passed / 58 skipped / 0 failed**（442.25s）。smoke16 已中止，388 requests、实际计费约 $0.2347，登记为非资格尝试，不修改其账本/目录；smoke17 已用冻结代码完成，未再出现 `LOCAL_CANDIDATE_NOT_IN_FAMILY`，运行稳定性验证通过。
- 下一步：全量回归通过后用冻结代码运行 smoke17，核对 yes/empty 场景是否不再中止、覆盖是否保持 unresolved、质量/覆盖/Residual 结果；smoke16 不作为资格证据。
- 变更记录：2026-10-27 新增；本条修复谓词不一致，不降低合并完整性或覆盖门禁。

## FL-D379 覆盖审计上下文截断把未展示的指引误报为缺失主题（2026-10-27）

- 发现日期：2026-10-27，分析 smoke14 的 31 个 `semantic_coverage` critical 与真实指引条目对应关系时确认。
- 问题与影响：`run_coverage_gate()` 原先把全部要求和全部 GuideItem 放进一个 24000 字符上下文，`_audit_context()` 末尾直接 `text[:limit]` 截断。smoke14 有 76 requirements（requirements 段 **8,639** 字符）和 90 GuideItems；按实际格式复算，只有前 **59** 个 GuideItem 能在截断前出现，剩余 **31** 个完全不可见。审计模型因此把不可见条目对应的主题当作 missing topics，恰好产生 **31** 个 `semantic_coverage` critical，导致 quality `fail`，并非全部是真实法规缺口。该缺陷会让覆盖门禁既误报又误导后续 Residual/补写方向。
- 证据：`/tmp/opencode/gg-real-smoke14` 的 76 requirements / 90 items；requirements 段 8,639 字符；实际格式下 24,000 字符截断点在第 59 个 item；critical 分类为 `semantic_coverage` 31、`draft_text_fidelity` 2、`regulation_fidelity` 2、`contract_coverage` 1。另抽查显示“直销不得收费”“销售服务费上限”“客户维护费”等主题已有对应 GuideItem，佐证误报。
- 处理方法：要求覆盖审计按 16 条要求分批；每批只展示与该批要求绑定的 GuideItem 明细，同时加入 `[ALL_GUIDE_ITEM_INDEX]` 全量紧凑索引（id、requirement_ids、title），使所有指引在上下文预算内可见；`apply_audit()` 只接受属于本批 requirement_ids 的 requirement_results/missing_topics，避免跨批重复；`COVERAGE_INSTRUCTION` 明确“未在明细中出现不等于不存在”，`COVERAGE_VERSION` 提升为 `guide_coverage_audit_v3`。未降低 critical 或删除 finding。
- 状态与验证：**代码已修复并通过离线回归**。新增用例构造 40 requirements + 40 items，断言要求审计分 3 批、全部 40 个 GuideItem ID 出现在索引中、每个上下文 ≤ 24000 字符；`tests/test_guide_generation.py` **20 passed**，其余法规套件 **49 passed**，包含该修复的全量回归 **1709 passed / 57 skipped / 0 failed**（466.29s）。smoke15 在修复前启动，发现该缺陷后已中止，仅 31 次逻辑调用、账本 32 requests、约 $0.0533，登记为非资格尝试。smoke17（含本修复）完成：`guide_coverage_audit` 调用 8→32，审计看到全部 100 个 GuideItem；`semantic_coverage` critical 为 78，说明“不可见即缺失”的截断机制已消除，但仍有真实/待判定的覆盖主题，不能把 78 直接当作全部真实缺口。
- 下一步：用冻结代码运行 smoke16，比较 `semantic_coverage` critical 数量、quality run_status、coverage unresolved 和 Residual；若仍有真实缺口，再进入 P5 补写闭环，不能把本轮截断修复当成覆盖已完整。
- 变更记录：2026-10-27 新增；本条修正审计可见性，不改变真实覆盖判定标准。

## FL-D378 smoke14 真实重跑消除基础设施失败但质量/覆盖/Residual 仍未闭合（2026-10-27）

- 发现日期：2026-10-27，P1/P2/并发修复后的真实 smoke14 完成。
- 问题与影响：本轮验证了“批次/schema/并发”修复确实有效，但最终仍未达到 `candidate_ready`。结果是**设计/内容层仍有缺口**，不能把基础设施修复当成功能达预期。
- 证据：run `390677df707040d68839708c4f9e38c2`，目录 `/tmp/opencode/gg-real-smoke14`，新账本。614 次逻辑模型调用 **0 error**（smoke13 为 120 error，其中 119 次 `MODEL_CONCURRENCY_LIMIT`）；`guide_impact_sweep` 19 次调用全部成功（13 affected/2 not_affected/4 uncertain），`guide_local_candidate` 330、`guide_quality_review` 94、`guide_residual_sweep` 57 均无逻辑失败。结果：76 requirements、843 impacts、90 guide items、545 findings；finalize 为 `complete_with_unresolved / candidate_with_findings`，requirement gaps **0**（smoke13 为 4）、unresolved impacts **7**（88）、critical_quality_findings **0**（4）；但 quality `run_status=fail`（36 critical：31 `semantic_coverage`、2 `draft_text_fidelity`、2 `regulation_fidelity`、1 `contract_coverage`），latest contract uncertain **88**（86），Residual 三轮新增 **24/19/5**（54/72/82），`saturated=false`。共享账本 618 requests、实际计费约 **$0.479236**；attempt 级失败为 1 条 req_review schema + 3 条 retry exhausted，逻辑调用全部成功。
- 处理方法：不降低门禁、不改写结果；把剩余问题拆成三类继续处理：(a) 31 个 coverage audit missing topics 与 88 个 latest uncertain 属于真实覆盖缺口；(b) 2+2 个文本 critical 属于指南内容缺陷；(c) Residual 仍新增真实模式，不能靠增加轮数或放宽去重冒充饱和。smoke14 为修复前 v4 基线，FL-D374/376/377 和 v5 需 smoke15 验证。
- 状态与验证：**真实运行已完成并确认未达资格；基础设施修复已验证，内容/覆盖/Residual 与独立模型身份仍阻断**。不宣称 `candidate_ready`，不启动 Blind Benchmark，不发布。
- 下一步：等 smoke15（冻结代码）结果，重点看 quality critical 是否被新门禁正确计入/阻断、req_review v5 是否消除 attempt 失败、Residual 是否继续收敛；FL-D379 修复要求审计截断后，用 smoke16 复核 31 个假缺口是否消失，再针对剩余真实缺口设计“审计缺口→补写→复审”的闭环，而不是继续放大扫描轮数。
- 变更记录：2026-10-27 新增；本条不修改 smoke13 历史结果，也不把 smoke14 的改善写成资格通过。

## FL-D377 双证据校验要求全部引文匹配会把真实 critical 降级（2026-10-27）

- 发现日期：2026-10-27，复核 `evidence_quote_2` 绑定逻辑时确认。
- 问题与影响：`_review_one()` 最初用 `all(...)` 要求 `evidence_quote` 与 `evidence_quote_2` 都精确出现在上下文中才置 `evidence_verified=True`。模型只要在第二字段写一条近义或补充说明，整条 finding 就被判未验证；而 `stage_quality()`/`stage_finalize()` 会把“reviewer critical 且 evidence_verified=False”的 finding 排除出 critical 计数。结果是真实 critical 被第二引文拖累降级，属于 fail-open，与“证据绑定必须 fail-closed”相反。
- 证据：`quality.py` 原实现 `verified = bool(evidence_text) and all(...)`；`stage_quality()` 的 `critical_total` 与 `stage_finalize()` 的 `critical_quality` 均要求 `source != guide_reviewer or evidence_verified`。
- 处理方法：改为“任一提供的引文精确匹配即可验证”，并记录 `evidence_matched_quote_indexes`；不匹配的引文仍保留在 `evidence_quotes` 中供人工核对，但不允许它把已由真实引文支撑的 critical 降级。未放宽 severity 或删除 finding。
- 状态与验证：**已修复并通过离线回归**。新增用例：第一引文精确、第二引文不存在时，finding 仍为 critical、`evidence_verified=true`、`matched=[1]`，quality 为 `fail`；`test_guide_generation.py + test_guide_generation_pipeline.py` **26 passed**。
- 下一步：以冻结代码运行 smoke15，核对真实 critical 不再因第二引文被降级；仍需独立模型身份合格才能关闭资格。
- 变更记录：2026-10-27 新增；与 FL-D368 的双证据字段配套，但修正的是验证方向。

## FL-D376 要求抽取/复核 findings 只写 evidence、未进入质量与最终门禁（2026-10-27）

- 发现日期：2026-10-27，核对 `stage_extract()`、`stage_verify()` 与 `stage_quality()` 的 findings 来源时确认。
- 问题与影响：`extract_requirements()` 会产生 `requirement_coverage`、`REQ_REVIEW_FAILED` 等 critical findings；`stage_extract()` 只把它们写成 `requirement_finding` evidence，没有写入 `gg_findings`。`stage_verify()` 只检查未处置要求，`stage_quality()` 和 `stage_finalize()` 读取的是 `gg_findings`。因此要求复核批次失败、要求覆盖 critical 等不会进入质量门禁，也不会阻断 `candidate_ready`，属于 fail-open；smoke14 已出现 `guide_req_review` schema 失败，若其余门禁闭合就可能被静默忽略。
- 证据：`pipeline.stage_extract()` 原代码只有 `store.add_evidence_many(...)`；`stage_verify()` 仅计算 `unhandled`；`stage_quality()` 使用 `store.get_findings()`；smoke14 账本中存在 `guide_req_review` 的 `MODEL_SCHEMA_INVALID`（`article_assessment.4` 缺 `reason`）。
- 处理方法：`stage_extract()` 在保留 evidence 的同时调用 `_merge_findings(result.findings)`，把要求阶段 findings 作为一等对象持久化；随后由 `stage_quality()` 的 `run_status` 与 FL-D374 的 `quality_gate_passed` 共同阻断候选就绪。未删除 evidence，未放宽任何 critical 判定。
- 状态与验证：**已修复并通过离线回归**。新增流水线用例让 `guide_req_review` 全部失败，断言 `requirement_review` critical findings 已持久化、quality 为 `fail`、最终为 `candidate_with_findings`、`quality_gate_passed=false`；`tests/test_guide_generation_pipeline.py` **7 passed**。smoke14 运行的是修复前代码，其结果不能作为该链路已闭合并通过资格的证据。
- 下一步：用包含 FL-D374/FL-D375/FL-D376 的冻结代码执行 smoke15，核对要求复核失败是否进入 findings 并阻断资格；真实结果未出前不宣称 candidate_ready。
- 变更记录：2026-10-27 新增；本条补齐“要求阶段 finding 未入册”的持久化缺口，与 FL-D374 门禁聚合修复配套。

## FL-D375 要求复核 article_assessment 缺少 reason 触发严格 schema 失败（2026-10-27）

- 发现日期：2026-10-27，smoke14 真实运行早期账本。
- 问题与影响：`guide_req_review` 返回 HTTP 200，但 `article_assessment.4` 缺少必填 `reason`，触发 `MODEL_SCHEMA_INVALID`。该阶段失败会写入 `requirement_review` critical finding 并跳过该复核批次；按 FL-D374 修复后的门禁，该 critical 会阻断 `candidate_ready`。schema 本身要求 `reason` 是合理的，不能为通过而删除必填约束。
- 证据：smoke14 账本失败记录 `task_type=guide_req_review`、`schema_error_path=article_assessment.4`、`schema_error_message='reason' is a required property`；`REQUIREMENT_REVIEW_SCHEMA` 的 `article_assessment` 必填字段为 `article/status/reason`。
- 处理方法：保留严格 schema，补充 `REQUIREMENT_REVIEW_INSTRUCTION` 明确“每个 article_assessment 对象必须包含 article、status、reason，covered 状态同样必须提供 reason”，并将 `REQUIREMENT_REVIEW_VERSION` 从 v4 提升到 v5，便于证据区分。未把 reason 改为可选，未删除失败记录。
- 状态与验证：**提示词与版本已修改；尚未真实重跑验证**。smoke14 使用启动时加载的 v4，其该条失败作为 v4 基线保留；smoke15 才能验证 v5 是否降低该 schema 失败。
- 下一步：在 smoke14 完成后，以新目录/新账本运行 v5，核对 `guide_req_review` schema 失败是否消失；若仍出现，继续按 fail-closed 记录，不修改 schema 迁就模型。
- 变更记录：2026-10-27 新增；本条与 FL-D374 配合，确保复核失败不会被最终门禁忽略。

## FL-D374 最终资格门禁未纳入 quality.run_status，存在 fail-open（2026-10-27）

- 发现日期：2026-10-27，复核 `stage_quality()` 与 `stage_finalize()` 的门禁口径时确认。
- 问题与影响：`stage_quality()` 把所有 critical findings（包括 `requirement_review`、`contract_coverage`、`semantic_coverage` 等）计入 `quality.run_status`，任一 critical 即为 `fail`。但 `stage_finalize()` 的 `critical_quality` 只统计 `regulation_fidelity`、`draft_text_fidelity`、`provenance` 三类，`complete` 条件也未检查 `quality.run_status`。因此要求复核失败、覆盖审计 critical 或 guide_conflict critical 存在时，只要覆盖计数和 Residual 恰好闭合，运行仍可能被标记 `candidate_ready`，与项目“质量门禁未通过不得宣称候选就绪”的要求冲突，属于 fail-open。
- 证据：smoke13 的 quality 为 `fail`（436 findings、4 个三类 critical）；同时存在 `requirement_coverage` critical 12、`semantic_coverage` critical 112、`contract_coverage` critical 4，这些均不在 finalize 的 `critical_quality` 类别中。smoke13 最终因覆盖/Residual 未闭合而为 `candidate_with_findings`，但该结论依赖其他门禁，不能证明 quality 门禁本身生效。
- 处理方法：`stage_finalize()` 显式读取 `payload.quality.run_status`，把 `quality_gate_passed = run_status != "fail"` 纳入 `complete`；`finalize` 记录 `quality_run_status`，checklist 增加 `quality_gate_passed`。不放宽任何 critical 判定，不删除 findings。
- 状态与验证：**代码已修复并通过离线回归**。`tests/test_guide_generation_pipeline.py` **7 passed**，新增用例构造 critical quality finding、其余覆盖/Residual 门禁闭合，断言最终为 `candidate_with_findings`、`quality_run_status=fail`、`quality_gate_passed=false`。smoke17 已验证：quality `fail`、critical_quality 9、最终 `candidate_with_findings`，新门禁正常阻断；smoke14 为修复前基线。
- 下一步：用修复后代码重跑或对 smoke14 存储结果按新门禁重算并登记；最终资格仍需真实运行 + 独立模型身份全部通过。
- 变更记录：2026-10-27 新增；本条修复的是门禁聚合口径，不改变模型输出或历史运行记录。

## FL-D373 G06 单向外转语义探针被误排除导致门禁反而关闭（2026-10-27）

- 发现日期：2026-10-27，完整 `PYTHONPATH=. .venv/bin/pytest -q` 回归 **1688 passed / 57 skipped / 1 failed**，失败为 `tests/test_recovery_final_invariants.py::test_g06_semantic_absence_probe_keeps_one_way_class_limit_open`。
- 问题与影响：当前工作树在 `_semantic_delete_hits()` 中把“Y类基金份额不能转换为A/C/F类”这类单向外转句子排除出语义删除探针，导致探针返回空。该函数的契约是“规范文字缺失但合同仍有等价业务表述时保持操作 OPEN”；排除后探针无法证明等价表述仍存在，门禁会从 OPEN 误变为可关闭，属于 fail-open 方向回归。自动删除排除应只发生在 `_semantic_delete_sentences()` 和 review 路径，不应改变探针语义。
- 证据：失败断言 `_semantic_delete_hits("G06", "但Y类基金份额不能转换为A类、C类、F类基金份额。") == []`；`tests/test_recall_core.py::test_g06_one_way_conversion_is_not_a_semantic_delete_site` 仍要求 `_semantic_delete_sentences("G06", text) == []` 且 `target_site_ok` 为真；`evaluate_operation_effect()` 在调用探针前已用 `_semantic_delete_review_hits()` 返回 `semantic_delete_review_required`。
- 处理方法：移除 `_semantic_delete_hits()` 中的单向外转排除，恢复“等价表述仍命中探针”；保留 `_semantic_delete_review_hits()` 的 OPEN/review 分支和 `_semantic_delete_sentences()` 的自动删除排除。未修改测试期望，未放宽任何门禁。
- 状态与验证：**已修复并通过定向回归**。`tests/test_recovery_final_invariants.py tests/test_recall_core.py` 为 **101 passed**；直接调用探针确认单向外转命中、无关“可转换债券”不命中。完整全量回归重跑待执行并回填。
- 下一步：重跑完整 `PYTHONPATH=. pytest -q`；若通过，再以 smoke14 结果判断法规指引门禁。该项目失败与法规指引修复无直接依赖，但属于当前工作树真实缺陷，不能以“定向通过”掩盖。
- 变更记录：2026-10-27 新增；本条只修复探针契约，不改变 G06 的业务复核要求和历史证据。

## FL-D372 法规生成阶段并发与共享账本并发上限错配导致大量逻辑调用失败（2026-10-27）

- 发现日期：2026-10-27，逐条分析 smoke13 的 `gg_model_calls` 失败分布时确认，此前只依据共享账本 4 条终态失败明显低估了真实失败规模。
- 问题与影响：smoke13 共记录 702 次逻辑模型调用，其中 **120 次状态为 error**；按错误码拆分，**119 次是 `MODEL_CONCURRENCY_LIMIT`**，只有 1 次是 `MODEL_OUTPUT_TRUNCATED`。分布为 `guide_local_candidate` 64/429、`guide_quality_review` 26/78、`guide_impact_sweep` 17/29、`guide_impact_adjudicate` 13/31。原因是法规生成各阶段默认使用 4 个并行 worker，而共享账本 `FUNDLEX_MODEL_CONCURRENCY=1`：抢不到槽位的调用等待约 30 秒后抛 `MODEL_CONCURRENCY_LIMIT`。其后果不是简单的重试成本，而是 sweep 批次在有限重试后仍被丢弃、adjudicate 跳过影响裁决、local candidate 批次缺失，quality review 被记为调用失败并生成 major finding，直接放大了覆盖缺口和 Residual 新影响，可能被误判为模型质量问题。
- 证据：`/tmp/opencode/gg-real-smoke13/data/runs.sqlite3` 的 `gg_model_calls` 按 task_type/status/error_code 聚合；`fundlex/model.py` 的 `_budget_reserve_with_retry()` 在等待 `min(30, max(5, lease_seconds))` 后抛出并发错误；`fundlex/guide_generation/{discovery,authoring,quality}.py` 的阶段 worker 默认值为 4；共享账本 `/tmp/opencode/gg-real-smoke13/ledger.sqlite` 只记录 4 条 failed，说明仅看账本会漏掉阶段层逻辑失败。
- 处理方法：`GuideModelRouter` 初始化时读取共享预算的 `concurrency`，用进程内 `BoundedSemaphore` 把并发调用限制到该上限；阶段仍可使用多个 worker，但调用会在路由层排队，而不是在预算层等待超时后失败。预算缺失（离线 fake/replay）时不加门，保持测试行为不变；不放宽 schema、不删除失败记录。
- 状态与验证：**已实施并通过离线回归；smoke14 真实验证成功**。`tests/test_guide_generation.py` 3 线程并发用例断言实际最大并发为 1、无调用失败、3 条调用记录完整；该文件 **18 passed**。smoke14 的 614 次逻辑调用 **0 error**，`MODEL_CONCURRENCY_LIMIT` 从 smoke13 的 119 次降为 **0**；`guide_local_candidate`/`guide_quality_review`/`guide_impact_sweep`/`guide_impact_adjudicate` 均无逻辑失败。剩余 attempt 级失败为 1 条 schema 与 3 条 retry exhausted，未形成逻辑调用失败。
- 下一步：smoke15 继续观察跨进程/重试边界；若仍出现 `MODEL_CONCURRENCY_LIMIT`，再登记 Worker 租约处理。并发修复本身已验证，但质量、覆盖、Residual 和独立模型身份仍需闭合才可进入 Blind Benchmark。
- 变更记录：2026-10-27 新增；与 FL-D368 的批次/schema/Residual 修复分开记录，避免把并发失败误算成模型输出缺陷。

## FL-D370 定位窗口与确定性恢复的物理范围泄漏及多句引文缩窄（2026-10-27）

- 发现日期：2026-10-27。在继续审计章节映射、窗口切分、引文绑定、survey、append recovery、操作归属和复合规划时确认两类通用风险：窗口按字符切分后曾把整个输入 section 集合写入每个 chunk；inventory、确定性 survey 和 append recovery 也可能在共享窗口或全文 inspection 中看到规则未映射的同级段落。另有 `resolve_quote()` 在完整多句引文无法绑定时回退到其中最长句，可能把一个跨操作引文缩窄为兄弟操作的可编辑片段。
- 问题与影响：错误章节、相邻业务子节、重复条款或 sibling operation 可能先成为候选，再被错误归属或复合规划；一旦后续站点保护未覆盖该路径，就可能生成错误编辑。复合目标若跨越非空独立段、章节或 zone，整段拼接会把无关文本带入 operation attribution 或执行证据。正式交付前必须证明这些候选不会穿过规划、执行和 Claim Replay。
- 证据或复现线索：最小回归位于 `tests/test_recall_core.py` 的多句引文、实际 chunk section ID、survey scope 用例，以及 `tests/test_operation_execution_closure.py` 的跨非空物理段复合目标用例。原代码的 `resolve_quote()` 在缺失第二句时会返回第一句；`_window_from_sections()` 的 chunk 曾统一使用输入 `section_ids`；`survey_targets()`、append applicability 和 recovery inventory 没有共同的规则 location scope。
- 处理方法：`resolve_quote()` 仅接受完整 normalized quote、末尾分号/句号容错或严格 source quote，不再按最长句回退。窗口 chunk 记录实际包含的 section IDs；新增 `rule_locations_for_window()` 给 inventory 和 sweep 重盘点做规则级 location 过滤；新增 `rule_scope_locations()` 给 survey 和 append recovery 使用，只有映射 section 的物理 locations 可进入确定性恢复。新增 `source_parts_contiguous()` 与 `_target_source_body()`，复合 operation attribution 只读取目标切片，并要求同一 readable zone、section、物理顺序及无非空中间段。
- 状态与验证：**问题已确认，通用代码修复已实施并通过离线回归；尚未完成真实 Worker/model、实际 DOCX、Claim Replay、结果页和授权下载验证。** 当前聚焦套件 `tests/test_recall_core.py tests/test_append_applicability.py tests/test_ff4d749_gate_closure.py tests/test_operation_execution_closure.py tests/test_final_validation_regressions.py tests/test_replay_site_provenance.py` 为 **266 passed**；`py_compile` 与 `git diff --check` 通过。既有 G06 物理范围、G15/G18、操作闭环和 Replay 回归仍通过。
- 下一步：在新 evidence directory 中重放当前代码的 D06 checkpoint，核对 scope mapping 是否显式包含真实正文/摘要副本；资源恢复后用真实 Worker/model 运行一个含有确实应改目标的合同，逐项检查最终 DOCX、redline、Claim Replay、报告/哈希、结果页和授权下载。若发现合法跨段规则受影响，新增明确的同 section/zone 兼容夹具和规则级例外，不能恢复全文 fallback。
- 变更记录（2026-10-27，历史 checkpoint 精确回放阻塞）：用历史 D06 真实运行 `real-20261027-opencode-d06-fixed-600` 的 30 个 checkpoint 对当前代码做零网络精确回放时，前 4 次调用命中，第 5 次当前代码构造出 `recall_inventory_v2`、context SHA `56cdd23821bd4f0147e64a5b75ca37fdd3da58f40940a0ff250f7203872e1492`、6145 字符的请求；该上下文不在历史 bundle 中，严格回放按设计以 `PROCESSING_FAILED` / `AssertionError` 停止，未发生网络请求。原因是 scope 收紧改变了 inventory 上下文，不是当前代码异常，也不能用伪造响应补齐后称为完整回放。证据目录 `/tmp/opencode/d06-current-scope-replay-20261027`。
- 变更记录（2026-10-27，诊断回放限制）：为观察当前 scope/window 结构，另做 `/tmp/opencode/d06-current-scope-diagnostic-20261027`，37 次调用中 17 个缺失请求使用明确标记的空响应 fallback，结果 19 个 planned edit、34 unresolved。该目录只用于结构诊断，不能作为模型质量、Claim Replay 或正式交付证据。
- 变更记录（2026-10-27，当前代码真实模型 D06）：在 `/tmp/opencode/d06-current-real-20261027` 用当前 dirty workspace 代码、当前认证 guide `7b68...`（文件 SHA `20bc...`）和 D06 原件 `09b6...` 执行真实模型运行；独立新账本，预登记 120 calls / $2.00，实际 28 HTTP / 29 logical calls、约 `$0.0319953`、158.4 秒。结果 `delivery_status=complete`、46 targets、25 needs_edit、19 edits、0 unresolved；`artifact_claim_replay.verified=true`（19 edits / 22 units）、`delivery_gate.open_obligations=0`、`final_omission_review.status=PASS`、`audit.issues=[]`、`sweep.gaps=[]`。实际 `final.docx` SHA `9283b432...`、`redline.docx` SHA `141e8a2f...`，与报告一致；源文件到 final 仅 19 个段落变化，全部落在计划站点内。G06 `p135` 的错误站点目标被排除且 operation 为无站点 `ALREADY_SATISFIED`，`p280` Y 类单向转换未删除；G11 `p228→p229` 复合 bearer 替换与 Claim Replay 通过；G17 `p808→p809`、`p1287→p1288` 复合删除及 `p810/p1289` G16/G17 原子替换通过；G18 `p831/p1245` 为 `ALREADY_SATISFIED`。该运行是 `execution_mode=evaluation` 的库级真实模型运行，不是正式 Workbench/API/Worker 用户路径，不能据此宣称正式交付。
- 变更记录（2026-10-27，当前代码严格零网络回放）：用上述 28 个真实响应在 `/tmp/opencode/d06-current-strict-replay-20261027` 做零网络精确回放，29 次调用全部命中 checkpoint、0 次 HTTP、0 缺失上下文；`plan.sha256=adbdda...`、plan count 19、Claim Replay、delivery gate、scope mapping 和 target attribution 与真实运行完全一致。`final.docx` 的 `word/document.xml`、`docProps/core.xml` 及 1,411 个段落文本逐项一致；`redline.docx` 仅 `w:date` 修订时间不同，归一化后一致。两次 DOCX 容器哈希不同来自 ZIP/修订时间戳，真实运行的 `9283b432...`/`141e8a2f...` 为正式证据，回放不能用自己的容器哈希替代。
- 状态更新（2026-10-27）：FL-D370 的通用边界修复已通过当前代码真实模型 D06、实际 DOCX、Claim Replay、输出校验和严格零网络回放；**正式 Workbench/API/Worker 用户路径、结果页审阅和授权下载仍未完成，项目继续 NO-GO**。下一步是在新的证据目录和账本中通过正式工作台身份入口提交 D06，核对持久任务、Worker 真实模型、最终/修订文件、报告/哈希、结果页和授权下载，再继续固定 D01–D20/holdout 与候选冻结。

- 变更记录（2026-10-27，隔离正式 API/Worker 用户路径）：在 `/tmp/opencode/d06-delivery-real-20261027b` 通过隔离 V1 应用完成密码登录、guide 绑定、上传、持久任务、真实 Worker/模型、final/redline、报告/Claim Replay、下载、修订选择和授权检查。27 HTTP / 约 `$0.03283635`，`execution_mode=delivery`、`delivery_status=complete`、19 edits、0 unresolved、Claim Replay verified（19/22）、gate 0 open、final SHA `387759e0...`、redline SHA `1ab117a2...`；下载复核 19 个段落变化、19 条修订、未授权 401、跨用户 404。该运行是隔离本地应用，不是生产部署。
- 变更记录（2026-10-27，隔离浏览器用户路径）：在 `/tmp/opencode/d06-browser-real-20261027b` 用真实 Chromium/V1 工作台完成注册登录、指引页、上传、Worker/模型、结果详情页和 final/redline/report 下载；任务/文档 `complete`、49 targets/0 unresolved、Claim Replay verified、最终遗漏 PASS、19 个段落变化、final SHA `0b25951e...`、redline SHA `d52faf32...`、结果页显示“已通过交付校验”、未授权下载 401。首轮浏览器运行因 FL-D378 的 G09 sweep 误报为 `incomplete`，修复后重跑通过；重跑临时脚本在下载后的字段名检查处 failed，独立 `browser-verification.json` 12 项检查全部通过，原始失败记录保留不覆盖。
- 状态更新（2026-10-27，最新）：D06 当前代码已在隔离 V1 工作台完成真实用户路径；**生产部署、生产/普通工作台 E2E、固定 D01–D20/holdout、独立标签、candidate freeze 仍未完成，项目继续 NO-GO**。下一步继续固定评测与候选冻结，不能以单合同隔离通过替代整批或生产交付。

## FL-D371 Compare 上传修订版需先接受全部 Word 修订（2026-10-27）

- 发现日期：2026-10-27，用户要求 Compare 上传带有 Word 修订痕迹的 DOCX 时先自动接受已有修订，再进行比较。
- 问题与影响：原 Compare parser 对 WordprocessingML 的 `w:ins`、`w:del` 等已有修订返回 `EXISTING_REVISION_UNSUPPORTED`，用户上传的修订版无法进入比较；原始上传文件不能被覆盖，清理后的输入必须仍绑定到 Worker、结果校验和选择版产物。
- 证据：公开基金合同 `funds_word/基金合同第一批/广发ESG责任投资混合型证券投资基金基金合同.docx` 原文件包含 66 个 `w:ins`、45 个 `w:del`、97 个 `w:delText`，共 208 个 Word 修订标记；清理后可解析 1,427 个正文 block，coverage 仍报告 `header/footer` 未覆盖。
- 处理方法：新增 `fundlex/compare/revisions.py`，仅在 V1 Compare 上传链路生成私有清理副本，接受插入、删除、移动、表格行/单元格及属性变更标记；原始 SHA/大小、显式清理后 `normalized_sha256`/大小和接受的修订标记数量写入 `compare_pair_files` 与上传回执，旧 `source_sha256` 继续兼容并指向清理后对象。上传前后继续执行 DOCX/OOXML 包、关系、宏、签名、保护、Strict OOXML、DTD、扩展和压缩限制校验；清理失败安全返回 `COMPARE_INVALID_DOCX`。数据库启动时对旧 `compare_pair_files` 执行兼容字段迁移，Worker 与 selection writer 继续使用清理后对象的 SHA/大小。
- 状态与验证：代码已实施。Compare 全套回归 **102 passed / 6 skipped / 1 warning**（含算法、API、store、worker、selection、batch、review、render、corpus）；真实 A 文件清理、上传、Worker、结果完整性校验和 view 全链路通过，计数 208、正文 1,427 block，原始 138,515 字节、清理后 129,391 字节，coverage 警告保持；重复清理得到完全相同的清理后字节，重复上传保持 `already_accepted` 且不替换已存对象。修订版输入的 API→Worker→选择版生成回归通过：生成报告和最终产物的 `left_source_sha256` 等于清理后哈希，不等于原始上传哈希；受保护文档安全返回 `COMPARE_INVALID_DOCX`。新增 V1 浏览器上传提示用例已编写，但当前 Playwright Chromium 可执行文件未安装，页面断言尚未执行；未部署生产。
- 下一步：在具备 Chromium 的环境执行 V1 浏览器上传提示和回执字段验证；在受控发布前核对真实任务的原始/清理后审计字段、Worker 结果哈希和选择版下载产物。生产发布仍受磁盘空间与发布验收条件约束。
- 变更记录（2026-10-28，状态复核）：生产部署目录 `/opt/fundlex-recall-first` 当时无 `compare/revisions.py`；`compare/ingest.py` 已存在且飞书服务已引用，但因缺少 normalizer 只能走兼容分支；部署版 `compare/api.py` 仍直接调用 `parse_compare_document`，实测修订原件抛 `EXISTING_REVISION_UNSUPPORTED`。同一文件在当前工作区经 `compare.ingest.prepare_compare_upload` 接受 208 处修订并生成 129,391 字节清理副本，原始哈希不变。
- 变更记录（2026-10-28，已提交并生产发布）：分支 `codex/compare-tracked-revisions`（基于生产 Compare 后端基线 `f4bb2b7`）提交 `019a1cf`、发布记录 `a86f238`，已推送 `origin`。生产按受控逐文件发布，新增 `compare/revisions.py`，替换 `docx.py`、`compare/store.py`，并对生产 `compare/api.py` 回移同内容上传补丁；生产原有 `compare/ingest.py` 与发布版本同哈希、未发生内容变化。重启 `fundlex-recall-api`、`fundlex-compare-worker` 与 `fundlex-feishu` 后均为 active，capabilities 200，`compare_pair_files` 已迁移出 `original_sha256/original_size/normalized_sha256/revisions_accepted`。生产真实 API→Worker→view 使用修订原件备份：上传回执 208 处，原始 `bbe61101...`/138,515 字节，清理后 `80f72ef8...`/129,391 字节，45 处差异，view 双侧返回，未授权 401/403，原始文件未改；证据 `/tmp/opencode/fundlex-compare-revisions-e2e-20261028/production-e2e.json`，发布前代码/DB 备份与 SHA 在 `/tmp/opencode/fundlex-compare-revisions-20261028/`。候选树既有 Compare 套件 48 passed、新增修订测试 35 passed。**Web Compare 线上已支持修订版输入；飞书 Compare 复用同一 `ingest`，服务已重启加载 `revisions.py`，但尚未做飞书端真实上传 E2E。**
- 新下一步：生产 V1 `frontend/compare.js` 仍不展示“已自动接受 N 处”提示（回执字段已可用）；飞书 Compare 需补一次真实修订版上传 E2E；两者在下一次前端/飞书受控发布时验证。

## FL-D368 法规指引真实批次输出契约与 Residual 收敛缺陷（2026-10-27）

- 发现日期：2026-10-27，复核 smoke13 真实账本、当前法规指引代码和离线回归。
- 问题与影响：smoke13 的 `guide_impact_sweep` 出现 `requirement_ids.maxItems` 超限，`guide_quality_review` 出现未声明的 `evidence_quote_2`，严格契约拒绝这些批次；Residual 三轮持续产生新模式，无法证明扫描已收敛。若只放宽 schema 或提高轮数，会把不可验证结果和重复扫描误当作质量提升。
- 证据：smoke13 run `266823af9f9c474fb87a11e7a90c7fd2`，4 条模型失败中包含上述两类 schema/输出问题；Residual 新增影响为 54、72、82。代码中 `path_b_contract_sweep()` 将完整 requirements 放入每个批次，`_pattern_key()` 使用模型描述和整段证据，`stage_residual()` 重复使用初始 sweep batch 状态。
- 处理方法（已实施）：`DiscoveryConfig.path_b_max_requirements=12` 随 `PipelineConfig` 写入运行快照；合同扫描每个条款批次只携带与该批条款有证据关联的至多 12 条要求，`IMPACT_SWEEP_SCHEMA.requirement_ids.maxItems` 同步收紧为 12；模型返回空、超限或不在本批次白名单内的要求绑定时，整批按 `INVALID_REQUIREMENT_BINDINGS` fail closed 并进入一次有界重试，不再静默采信；一个 finding 绑定多个合法要求时按每个要求生成独立 Impact，避免只取第一个而丢失关联。`QUALITY_SCHEMA` 显式声明 `evidence_quote_2`，quality review 记录 `evidence_quotes` 与 `evidence_matched_quote_indexes`，任一引文精确匹配即可验证（FL-D377，避免第二引文把真实 critical 降级），未知字段仍由严格 schema 拒绝。Residual 模式键改为“合同版本 + 物理 clause 地址 + 规范化 requirement IDs”，不以模型描述或整段证据作为身份；启动时把已有 Impact 的物理模式加入 seen，同一位置换描述只算复核；Residual 同样按条款批次裁剪要求并拒绝越界绑定；模型错误、无效绑定或其他审计 finding 的轮次记为 `blocked` 并清零 clean streak，不能被当作饱和。
- 状态与验证：**代码修复与离线回归完成；smoke14 真实运行完成但未达资格**。法规生成两套件 **26 passed**；六套件 **67 passed**；最新冻结代码完整回归 **1701 passed / 57 skipped / 0 failed**（479.58s）；`compileall` 与 `git diff --check` 通过。smoke14 的 614 次逻辑调用 0 error，`guide_impact_sweep` 19 次调用 0 失败（smoke13 为 29 次/17 失败），`MODEL_CONCURRENCY_LIMIT` 完全消失；但 finalize 仍为 `complete_with_unresolved / candidate_with_findings`，quality fail（31 semantic_coverage critical 等）、unresolved 7、latest uncertain 88、Residual 24/19/5 未饱和。完整证据见 FL-D378。
- 下一步：以冻结代码运行 smoke15（v5 + FL-D374/376/377），验证新门禁和 v5；随后针对 coverage missing topics 设计“审计缺口→补写→复审”闭环。独立模型复核仍为同一模型，资格不能关闭。
- 变更记录：2026-10-27 新增；同日补充已实施的处理方法与离线验证结果。关联 FL-D362、FL-D364，保留其历史失败证据。

## FL-D367 历史评测目录的证据保留边界与清理前置条件（2026-10-27）

- 发现日期：2026-10-27，针对 `/tmp/opencode/operation-validation-20261024` 是否仍会被开发任务使用及是否可清理的只读依赖审计。
- 问题与影响：该目录不是当前应用运行时默认输入，也未发现活动评测进程读取；但当前文档、固定 D01–D20 对账、D06 独立复核、历史模型账本和多个离线回放脚本直接引用其中的路径。若现在删除或改写，会破坏历史分母、失败记录、费用账本、快照绑定和审计复现链。
- 证据：目录约 5.6 GB；历史隔离账本 `ledger.sqlite` 当前为 2,293 次 terminal requests、约 `$2.32384410`，已超过登记的 2,000/$2 cap。固定对账 JSON、`ACTIVE_HANDOFF.md`、`REAL_REVISION_EVALUATION_RESULTS.md` 和本记录仍包含直接路径引用。证据分类及文件/小文件 SHA-256 清单见 [`docs/evidence/operation-validation-20261024-retention-manifest.json`](evidence/operation-validation-20261024-retention-manifest.json)，清单 SHA-256 为 `386392788de44fd554f299ae2aa290905ad40dd35489fd3ff5783e9946b694fe`。
- 处理方法：当前决定为 `retain-in-place`，不删除、不重置、不重写历史账本或历史结果。清单将 D01–D20 对账所需批次/报告/复核包、target-19/20、绑定快照、运行上下文和账本列为权威证据；其他快照、数据库、回放和脚本列为支持性材料；日志和小型派生物列为诊断/派生材料；只有完成归档、哈希复核、引用迁移、归档根对账和负责人复核后，才可重新评估潜在清理候选。后续真实评测必须使用新的运行目录和新登记账本，不能复用已超 cap 的历史账本。
- 状态与验证：**审计完成，历史目录保留；未授权删除，未修改目录内容**。已核对当前仓库工具不会默认创建或读取该目录，已核对无活动 operation-validation/freeze/replay/review 进程；本轮只生成分类清单并完成 `git diff --check` 前置准备，未执行归档或空间回收。
- 下一步：先将最小权威证据集及其支持性 provenance 归档到耐久存储，验证归档提取后的哈希，再让对账器支持显式 archived evidence root；获得明确清理决定后，才可针对候选项逐项处理。根分区空间约束仍登记在 FL-D365，不能用未经核验的删除缓解来宣称已解决。
- 变更记录：2026-10-27 新增；本条只记录依赖边界和保留条件，不授权删除，也不把历史评测结果升级为当前资格或交付证据。

## FL-D366 第一批合同解析准入结果与评测分母边界（2026-10-27）

- 发现日期：2026-10-27，按用户指定的 `/home/opencode/fundlex/funds_word/基金合同第一批` 对 28 份公开 DOCX 做只读准入审计。
- 问题与影响：28 份中只有 9 份通过当前 `inspect_docx(..., full=True)`；19 份不能直接进入真实修改评测，其中 18 份为 `EXISTING_REVISION_UNSUPPORTED`，1 份为 `DOCUMENT_PROTECTED`。若把整目录直接作为评测分母，会把输入准入失败误计为引擎漏改或误改。
- 证据：审计脚本 `tools/evaluation/sample_corpus_audit.py`；结果 `/tmp/opencode/sample-corpus-first-batch.json`；总数 28，`parse_ok=9`、`parse_rejected=19`。18 份拒绝文件的 `word/document.xml` XML 本身可解析，不能笼统称作 XML 损坏。
- 处理方法：新增只读准入审计和 SHA-256 清单输出；后续新测试/评测入口默认指向 `funds_word/基金合同第一批`，固定 D01–D20 与既有 holdout manifest 保持原路径、哈希和分母不变。解析拒绝样本保留在审计总数中，不静默修复、转换或计入真实修改指标。
- 状态与验证：**准入审计已完成；19 份仍未取得可修改输入；9 份仅表示解析可用，不表示业务 gold、模型修改或正式交付通过**。审计命令成功结束，`py_compile` 和 `git diff --check` 通过。
- 下一步：为 9 份可解析合同建立独立标签和 dev/holdout 选择；对已有修订和保护文档另行确定业务允许的输入处理方式后再评测，不把转换后的文件冒充原件。
- 变更记录：2026-10-27 新增；只记录文件名、哈希、错误码和准入状态，不记录凭据或合同正文。
- 用户测试语料指令（2026-10-27）：后续新增测试/评测统一使用 `/home/opencode/fundlex/funds_word/基金合同第一批` 中的样本；`tools/evaluation/sample_corpus.py`、`recall_run.py`、`sample_corpus_audit.py` 已默认该目录。固定 D01–D20 与既有 holdout manifest 保持原路径、哈希和分母不变；当前 28 份中 9 份 `parse_ok`、18 份 `EXISTING_REVISION_UNSUPPORTED`、1 份 `DOCUMENT_PROTECTED`，解析拒绝样本不静默修复、不转换、不计入真实修改分母。
- 处理结果（2026-10-27）：已对 18 份含修订痕迹 DOCX 执行“拒绝全部修订”并替换第一批文件；原件备份在 `funds_word/基金合同第一批_修订原件备份_20261027/`，清理副本、清单和验证在 `funds_word/基金合同第一批_拒绝修订_20261027/`。18 份均通过插入文字消失、删除文字恢复、段落数守恒、无修订标签和重新解析校验；当前 27/28 `parse_ok`。唯一失败 `广发稳信六个月持有期混合型证券投资基金基金合同.docx` 无修订痕迹，仅 `documentProtection edit=trackedChanges, enforcement=0`，未改动；`广发恒裕一年持有期混合型证券投资基金基金合同.docx` 同时有修订和该非强制保护，清理副本移除了保护设置，原件备份保留。固定 D01–D20/holdout manifest 不变，本次未调用模型。

## FL-D365 G06 物理小节边界修复及兼容夹具验证（2026-10-27）

- 发现日期：2026-10-27，复核 D06 原件中 `p130–p137` 的“基金份额类别”范围与 `p280` 的“基金转换”范围时确认。
- 问题与影响：旧实现用大章节映射和全文语义补扫处理 G06，导致章节内其他“转换”条款可能被当成类别设置删除目标；这属于代码逻辑边界缺陷，不是单次模型偶然误判。G06 若没有物理小节证明，也不能用全文无字面命中替代范围证明。
- 处理方法：`g06_scope_locations()` 以“基本情况”章节中的“份额类别/份额类别设置”编号小节及下一编号小节为物理范围；target discovery、site guard、语义删除和 effect proof 均受该范围约束。Y 类单向转换仍只产生 review/fail-closed。没有结构元数据的旧隔离夹具只保留兼容路径，不放宽真实 DOCX。
- 证据：`fundlex/recall.py`、`fundlex/generation/effects.py`、`guides/builtin_guide_v1.json`；D06 结构回归确认范围为 `p130–p137`，不含 `p280`；第一批可解析沪深 300 合同确认范围为 `p157–p162`，不含 `p817`、`p903`。
- 状态与验证：**代码修复已实施并通过定向验证**。G06/语义删除/范围/operation closure 回归 36 passed；Worker 恢复回归 2 passed；占位目标回归 12 passed；G15/G18/Claim Replay/交付相关定向回归 14 passed；JSON、`py_compile` 和 `git diff --check` 通过。D06 最新真实 Worker/真实模型/正式 final-redline/授权下载仍未完成。
- 下一步：模型服务、磁盘空间和业务授权条件满足后，重新运行 D06 完整真实链路；复核 G06 p130–p137（p280 不属于 G06）、G15 p810、G18 p1245/p831、Claim Replay、报告/哈希、结果页和授权下载。当前项目继续 NO-GO。
- 变更记录：2026-10-27 新增；保留旧 D06 replay 的 `FL-D356` 历史证据，不将其升级为本次修复后的真实交付证据。
- 变更记录（2026-10-28，章节口径更正）：D06 p280 实际位于“第六部分基金份额的申购与赎回”，不是 G06 的“基金的基本情况—份额类别设置”；此前把 p280 列为 G06 未闭合/业务 review 是错误的。G06 只覆盖 p130–p137；Y 类单向转换如要处理应另立规则/业务决定。业务问题清单 BIZ-01 已排除，不再作为 G06 业务问题。

## FL-D363 合同切片已持久化但尚未写入向量数据库（2026-10-27）

- 发现日期：2026-10-27，针对“合同切割切片放进向量数据库有做吗”的代码和真实运行数据核对。
- 问题与影响：当前合同 DOCX 会被切成带段落锚点、章节路径、前后文和 `clause_id` 的 `ClauseUnit`，并写入共享 SQLite 的 `gg_clauses`；检索使用运行期间构建并丢弃的字符二元组倒排索引 `LexicalIndex`。当前仓库没有 Chroma、Qdrant、FAISS、pgvector、Milvus 或 embedding 依赖，也没有向量表/向量服务写入链路。因此“合同已切片并入库”成立，“已入向量数据库”不成立。
- 证据：`fundlex/guide_generation/corpus_segmenter.py` 定义 `MAX_CLAUSE_CHARS=1400` 并生成 `ClauseUnit`；`fundlex/guide_generation/store.py` 的 `gg_clauses` 只包含文本、段落范围、上下文和 JSON payload，没有 embedding/vector 列；`fundlex/guide_generation/lexical.py` 明确使用字符二元组倒排索引。真实 smoke12、smoke13 数据库均有 2 个合同版本、930 条 `gg_clauses`，未发现向量存储依赖或表。
- 处理方法：保留词法召回、法规要求级检索和独立合同语义扫描；新增 `SQLiteVectorIndex` 作为可重建的本地向量派生库，关系数据库继续保存权威 ClauseUnit、版本、锚点和证据链。向量 manifest 绑定 corpus snapshot/hash、embedding model/version、dimension 和 entry count；每条派生向量保存 `clause_id`、合同版本、源文件哈希和文本哈希。重建完成后才原子切换 active manifest，旧 manifest 可回滚，embedding 请求或写入失败不会改变 active 指针。discovery 使用词法与向量并集，回查当前 `ClauseUnit` 并拒绝地址或源文件哈希不匹配；向量不可用时继续词法召回。
- 状态与验证：**切片和 SQLite 权威持久化已完成；本地版本化向量派生层、Qdrant REST 后端和混合召回已实施**。`tests/test_guide_generation_vector.py` 覆盖 SQLite provenance、搜索、失败重建保留 active、回滚、Qdrant collection/payload/search/rollback、向量-only 召回及 stale source hash 拒绝；法规/流水线定向套件为 **23 passed / 1 warning**。当前尚未配置真实 embedding 服务或真实 Qdrant，尚未在真实合同上测量混合召回相对词法基线的召回率、误召回率、证据绑定率和覆盖率；因此向量路径仍不默认启用，不改变法规链路 NO-GO。
- 下一步：在磁盘和服务资源允许后，用受保护配置接入真实 embedding 服务和 Qdrant，在真实合同上建立词法基线与混合召回对照；保留相同 manifest/provenance/回滚契约。只有混合召回改善且不引入错误绑定才纳入默认路径。
- 变更记录：2026-10-27 新增；2026-10-27 实施本地向量派生库、混合召回和回归测试；不记录密钥、令牌或合同正文。
- 变更记录补充：2026-10-27 增加 Qdrant REST 派生后端、独立 collection 与 manifest 指针回滚；未启动真实 Qdrant 或 embedding 服务。

## FL-D365 本机磁盘空间不足以启动真实向量服务和 embedding 模型（2026-10-27）

- 发现日期：2026-10-27，混合检索实施后的真实后端验收准备。
- 问题与影响：本机根分区只有约 350 MB 可用空间，无法安全下载 Qdrant 二进制或本地 embedding 模型，也不适合启动新的真实向量服务。继续下载可能使现有 API/Worker、SQLite 数据库和真实 smoke 运行受到资源影响，因此真实 Qdrant/embedding 验证暂不能进行。
- 证据：`df -h /` 显示根分区总量约 40 GB、已用约 37 GB、可用约 350 MB；`free -m` 显示无 swap。当前代码测试使用本地模拟 provider/Qdrant REST 响应，没有产生真实向量服务请求或模型账本记录。
- 处理方法：不下载二进制、模型或启动额外服务；保留 Qdrant REST 适配器和 SQLite 派生后端作为可审查代码，向量配置默认关闭，真实运行继续词法回退。清理或扩容前不宣称真实向量验收通过。
- 状态与验证：**外部资源阻塞，未解决**。SQLite/Qdrant 协议模拟、provenance、原子 active、回滚和混合召回回归通过；真实 embedding、真实 Qdrant、真实合同召回指标尚未验证。
- 下一步：获得足够磁盘和明确 embedding/Qdrant 服务配置后，先做最小真实 embedding/Qdrant health smoke，再用公开合同建立词法基线与混合召回指标；失败继续 fail-closed 并保持词法回退。
- 变更记录：2026-10-27 新增；不记录密钥、令牌、合同正文或服务凭据。

## FL-D364 smoke13 最终仍未达到法规指引资格门禁（2026-10-27）

- 发现日期：2026-10-27，smoke13 真实运行自然收尾后的最终核对。
- 问题与影响：真实法规 PDF、2 个公开合同和真实模型链路已完成 15 个阶段，但运行仍不能作为 candidate-ready，也不能启动正式 Blind Benchmark、候选发布或部署。质量、覆盖和 Residual 门禁均未闭合；同一模型承担 author/reviewer，独立复核身份仍不合格。
- 证据：run `266823af9f9c474fb87a11e7a90c7fd2`，目录 `/tmp/opencode/gg-real-smoke13/`，退出码 0，状态 `complete_with_unresolved`、资格 `candidate_with_findings`；88 requirements、835 impacts、858 local candidates、88 families、77 guide items、467 findings、702 model calls。质量 `fail`，436 findings、4 critical findings；覆盖 88 unresolved impacts、86 latest contract uncertain、4 requirement gaps；Residual 三轮均 `new_uncovered`，新增 impacts 分别为 54、72、82，`max_rounds_reached/saturated=false`。独立账本 586 条请求中 582 completed、4 failed。
- 真实失败：2 条 `guide_impact_sweep`（一条 `MODEL_SCHEMA_INVALID`，`findings.0.requirement_ids` 超过 `maxItems`；一条 `MODEL_OUTPUT_TRUNCATED`）；1 条 `guide_residual_sweep` 的 HTTP 429 重试耗尽；1 条 `guide_quality_review` 的严格 schema `additionalProperties`（`findings.0.evidence_quote_2`）。这些批次继续按 fail-closed 处理，未用 fallback 结果冒充完整证据。
- 处理方法：保留 smoke13 作为当前代码和真实服务的最终未资格基线；不修改 schema 门禁、不删除失败记录、不运行 blind benchmark。impact sweep 后续按更小法规要求/合同条款窗口拆分，并限制单个 finding 的 `requirement_ids`；quality review 需拒绝未知字段并在 prompt/批次层控制输出；residual 需保留 429 账本和可恢复断点。
- 状态与验证：**已确认，未解决；项目继续 NO-GO**。smoke13 的法规、合同、模型和持久化流水线确实完成，但质量、覆盖、Residual 与独立模型身份资格条件均未通过。
- 下一步：先修复并用全新目录/独立账本重跑 impact sweep 与 quality review，再重新验证覆盖和 Residual；只有所有资格门禁通过且有独立模型身份，才执行 Blind Benchmark、候选发布和正式用户端到端交付。
- 变更记录：2026-10-27 新增；不记录密钥、令牌或合同正文。

## FL-D362 合同影响扫描单批次仍超出严格 schema 与输出容量（2026-10-27）

- 发现日期：2026-10-27，smoke13 运行中及自然收尾后的独立账本复核。
- 问题与影响：`guide_impact_sweep` 已出现 HTTP 200 但 `schema_failure=maxItems`、`schema_error_path=findings.0.requirement_ids`，以及 HTTP 200、`finish_reason=length`、`MODEL_OUTPUT_TRUNCATED`。合同扫描结果因此不能作为完整可验证证据，后续质量、覆盖和 Residual 不能据此判定通过。
- 证据：run `266823af9f9c474fb87a11e7a90c7fd2`，目录 `/tmp/opencode/gg-real-smoke13/`，最终退出码 0；最终有 88 requirements、835 impacts、858 local candidates、88 families、77 guide items、467 findings、702 model calls。账本 586 条请求中 582 completed、4 failed；其中两条 `guide_impact_sweep` 分别为 `findings.0.requirement_ids` 的 `maxItems` 和 `MODEL_OUTPUT_TRUNCATED`，响应正文未保存。最终质量/覆盖/Residual 结果和另外两条失败见 FL-D364。
- 处理方法：保持严格 `requirement_ids.maxItems=20`、完整 finding schema 和 `finish_reason=length` fail-closed；smoke13 的失败批次没有被放宽或丢弃。下一轮将合同扫描按更小法规要求/合同条款批次拆分，确保每个 finding 的 `requirement_ids` 有界且输出可闭合。
- 状态与验证：**问题已确认，尚未修复；smoke13 已完成但未资格**。最终未闭合结果登记见 FL-D364，项目继续 NO-GO。
- 下一步：使用全新目录和独立账本重跑拆批后的 impact sweep，并重新取得质量、覆盖和 Residual 证据。
- 变更记录：2026-10-27 新增；2026-10-27 smoke13 最终计数和失败分母补录；不记录密钥、令牌或模型响应正文。

## FL-D361 第三方前端组件对文档比对连线的适用边界（2026-10-27）

- 发现日期：2026-10-27，讨论 Ant Design 及第三方组件是否适合当前双栏合同比对连线。
- 问题与影响：Ant Design 官方没有将左右独立文档中的差异位置自动关联并绘制连线的组件。React Flow/XYFlow 等图连接组件可以提供节点、边、拖拽和缩放交互，但不能直接理解文档 DOM、滚动容器、DOCX 段落或差异端点；文本 diff 组件可以改善差异着色和导航，但通常不能直接连接两组独立滚动文档中的真实位置。盲目引入会增加包体积、渲染层级和滚动/定位适配成本。
- 证据：Ant Design 组件总览包含 Tree `showLine`、Timeline、Splitter、Anchor 等相关基础组件，但没有 DocumentDiff/Connector 组件；当前 React Compare 已在 `frontend/src/pages/Compare/ComparePage.tsx` 使用差异 DOM 标记、`getBoundingClientRect()` 和 SVG path 绘制左右连线，现有实现已覆盖当前核心交互。
- 处理方法：第三方组件只按局部收益评估。Ant Design Splitter 可用于双栏宽度调整，diff viewer 可用于统一文本差异样式，React Flow/XYFlow 仅在产品需要节点化映射、拖拽重连、缩放画布或复杂多对多关系图时考虑；当前文档连线继续使用 SVG overlay，并由 ResizeObserver、滚动同步和差异定位驱动。引入前需用真实长合同验证端点定位、滚动性能、表格/跨段内容和移动端行为。
- 状态与验证：**当时已完成设计判断，未引入第三方组件，未改变代码；后续用户确认先引入 Ant Design Splitter，见 FL-D379**。Ant Design 官方文档与当前 Compare React/V1 实现已核对；尚无 React Flow/XYFlow PoC 或真实用户端到端证据。
- 下一步：若产品要求可拖拽重连、缩放画布或复杂多对多关系展示，再针对 React Flow/XYFlow 建立隔离 PoC；双栏宽度调整已按 FL-D379 接入 Ant Design Splitter，文档连线继续使用 SVG overlay。
- 变更记录：2026-10-27 新增；同日补充 FL-D379 已引入 Splitter 的后续状态，本条历史判断保留。

## FL-D360 当前法规抽取/复核/候选批次仍超出严格输出边界（2026-10-27）

- 发现日期：2026-10-27，smoke12 使用 `guide_req_review_v3`、`guide_local_candidate_v3`、`guide_coverage_audit_v2` 的真实运行完成后复核独立账本。
- 问题与影响：真实运行继续未达资格。`guide_req_extract` 有 5 条 HTTP 200 但 `schema_failure=maxItems`、`schema_error_path=requirements`；`guide_req_review` 有 1 条 HTTP 200、`finish_reason=length`、`MODEL_OUTPUT_TRUNCATED`；`guide_local_candidate` 有 1 条 HTTP 200、`schema_failure=required`、`schema_error_path=candidates.1`、`schema_error_message='requirement_ids' is a required property`。严格门禁拒绝这些响应，虽然 pipeline 以保守 fallback 继续，但质量/覆盖/Residual 仍不能闭合。
- 证据：run `8d2ea4c4fd41480f846a9c1138525f3b`，目录 `/tmp/opencode/gg-real-smoke12/`，退出码 0；最终 53 requirements、545 impacts、581 local candidates、63 families、56 guide items、437 findings、523 model calls；quality `fail`，coverage 为 87 unresolved impacts、45 latest contract uncertain、9 requirement gaps，Residual 3 轮均 `new_uncovered`，`max_rounds_reached/saturated=false`，qualification `candidate_with_findings`。账本共 427 条请求，420 completed、7 failed；失败细节只记录结构化诊断，不保存响应正文。
- 处理方法：将 `REQUIREMENT_EXTRACT_VERSION` 升至 `guide_req_extract_v2`、`REQUIREMENT_REVIEW_VERSION` 升至 `guide_req_review_v4`，初始抽取、要求复核和缺口补漏窗口统一降至约 1500 字符，要求复核 baseline 限制为 3000 字符；将 `LOCAL_CANDIDATE_VERSION` 升至 `guide_local_candidate_v4`，要求 `requirement_ids` 必须从输入要求复制且非空；将 local batch size 从 12/8 降至 4。schema 继续严格，不放宽 required/maxItems。
- 状态与验证：**代码已实施；离线法规/模型/API 回归 53 passed / 1 warning，`py_compile`、`compileall` 和 `git diff --check` 通过；上述 v2/v4/v4 尚未真实验证**。smoke12 只验证了前一版 v3/v3/v3，不能作为新版本修复的验收。
- 下一步：使用全新目录和独立账本启动 smoke13，核对抽取 maxItems、复核截断和候选必填字段是否归零，并继续执行质量、覆盖、Residual 和模型身份门禁；不执行 blind benchmark。
- 变更记录：2026-10-27 新增；不记录密钥、令牌或模型响应正文。

## FL-D359 Local candidate 返回部分候选对象缺少必填字段（2026-10-27）

- 发现日期：2026-10-27，smoke11 真实模型账本中发现 `guide_local_candidate` 的 HTTP 200 响应以 `finish_reason=stop` 返回，但严格 schema 在 `candidates.1` 触发 `required`；模型响应正文未保存。
- 问题与影响：该批 local candidate 不能作为可验证候选使用，代码按 fail-closed 将缺失影响转为保守 fallback，运行继续，但会增加 uncertain/人工复核项并可能降低质量与覆盖资格。放宽 required 字段会让不可追溯候选进入后续 family，因此不采用。
- 证据：smoke11 run `e37e4b0deb4b4dd58830b2226347dfb1`，账本 `/tmp/opencode/gg-real-smoke11/ledger.sqlite`，记录为 `task_type=guide_local_candidate`、`error_code=MODEL_SCHEMA_INVALID`、`schema_failure=required`、`schema_error_path=candidates.1`、`schema_error_message='requirement_ids' is a required property`、HTTP 200、`finish_reason=stop`。该进程启动时已使用 local candidate v2 提示；没有记录响应正文。
- 处理方法：保留严格 `impact_ids`、`requirement_ids`、`needs_modification` required schema 和 fallback；将 `LOCAL_CANDIDATE_VERSION` 升至 `guide_local_candidate_v3`，增加逐对象字段自检、非空 ID 和枚举值约束提示。下一次真实运行使用新目录和独立账本核对发生率及最终门禁。
- 状态与验证：**代码已实施，离线法规/模型/API 回归 52 passed / 1 warning；v3 尚未真实验证**。新增模型截断分类回归通过。smoke11 已收尾但仍未资格：最终 618 local candidates、45 guide items、质量 `fail`，覆盖 68 unresolved impacts、19 latest contract uncertain、3 requirement gaps，Residual `max_rounds_reached/saturated=false`；旧版本失败不能验证 v3。
- 下一步：使用全新 smoke12 目录和独立账本验证 v3 local candidate；继续 fail-closed，完成后再按最终门禁决定是否需要进一步修复。
- 变更记录：2026-10-27 新增；不记录密钥、令牌或模型响应正文。

## FL-D358 要求独立复核单请求输出截断导致复核失败（2026-10-27）

- 发现日期：2026-10-27，smoke11 真实法规指引运行的模型账本显示 `guide_req_review` 首次 HTTP 429，按重试策略再次 HTTP 200，但 `finish_reason=length`、响应约 22322 字符，最终记录为 `MODEL_OUTPUT_TRUNCATED`。该进程启动时仍使用单次完整法规/完整 baseline 的要求复核实现。
- 问题与影响：严格门禁拒绝被截断的复核结果；如果重试相同上下文，只会重复消耗请求并再次碰到输出容量上限。要求抽取本身已完成并通过 source quote 绑定，但独立 challenger 复核阶段出现 critical finding，不能把该运行提升为资格通过。
- 证据：smoke11 run `e37e4b0deb4b4dd58830b2226347dfb1`，目录 `/tmp/opencode/gg-real-smoke11/`；账本中该任务有 `http_status=429/error_code=MODEL_RETRY_EXHAUSTED` 和随后 `http_status=200/finish_reason=length/error_code=MODEL_OUTPUT_TRUNCATED` 两条失败记录。运行已继续进入发现阶段，要求阶段最终 57 requirements、`requirement_verification.status=pass`、`unhandled=0`；失败响应正文未保存。
- 处理方法：将 `REQUIREMENT_REVIEW_VERSION` 升至 `guide_req_review_v3`；把独立 challenger 改为按法规 block 批次（约 6000 字符）审查，每批只发送对应原文和绑定 baseline，仍要求完整顶层数组、严格 source quote 校验和 fail-closed 批次失败记录。没有增加输出上限或放宽 schema。
- 状态与验证：**代码已实施，离线法规/模型/API 回归 52 passed / 1 warning，`py_compile` 和 `git diff --check` 通过；真实分批复核尚未重跑**。新增回归确认长法规会按批次产生 3 个独立复核请求，且 `finish_reason=length` 会 fail-closed 为 `MODEL_OUTPUT_TRUNCATED`。smoke11 已收尾但使用旧单次复核代码；其最终有 3 个 `new_uncovered` Residual 轮次、`max_rounds_reached/saturated=false`，不能作为 v3 验证。
- 下一步：smoke12 使用当前 v3 分批复核和 v2 覆盖审计在全新目录/账本重跑；不执行 blind benchmark，直到全部门禁和独立模型身份条件满足。
- 变更记录：2026-10-27 新增；不记录密钥、令牌或模型响应正文。

## FL-D357 覆盖审计单响应超出 schema 容量导致真实法规运行无法闭合（2026-10-27）

- 发现日期：2026-10-27，smoke9 真实法规指引运行完成后复核模型账本与阶段结果。
- 问题与影响：覆盖审计原先把所有要求、GuideItem 和未完成影响放入一次模型请求。smoke9 的 `guide_coverage_audit` 收到 HTTP 200，但响应多次触发 `MODEL_SCHEMA_INVALID`/`schema_failure=maxItems`；严格门禁因此不能采用审计结果，导致真实运行保留大量 unresolved impact。重试相同大请求不能改变响应规模，且会增加真实调用成本。
- 证据：run `a9f78342dc674524bf8c79fd77f47544`，目录 `/tmp/opencode/gg-real-smoke9/`，最终 `status=complete_with_unresolved`、`qualification_status=candidate_with_findings`；69 requirements、681 impacts、628 local candidates、71 families、59 guide items、536 model calls，coverage 为 111 unresolved impacts、59 latest contract uncertain、1 requirement gap，Residual 为 `max_rounds_reached/saturated=false`。账本中覆盖审计失败记录为 HTTP 200、`schema_failure=maxItems`，旧进程启动早于结构化路径诊断字段，因此不含正文或路径诊断；响应正文未保存。
- 处理方法：将 `COVERAGE_VERSION` 升级为 `guide_coverage_audit_v2`；要求级审计独立执行，未绑定 GuideItem 且仍为 definite/possible 的影响按每批 40 条执行；将影响结果 schema `maxItems` 设为 60、missing topics 设为 30；审计只有在已有 GuideItem 被明确绑定时才能把 unresolved 关闭为 covered，false_positive/not_applicable 仍需有模型理由。模型 schema 失败继续 fail-closed，并记录 bounded validator/path/message 诊断而不保存响应正文。
- 状态与验证：**代码已实施；smoke10 启动无效，smoke11 已完成但未资格**。模型、法规生成、pipeline、API 定向回归为 52 passed；新增覆盖批处理、无绑定 covered 保持 unresolved、要求复核分批和输出截断分类回归使法规主套件达到 37 passed；`py_compile` 和 `git diff --check` 通过。smoke10 目录 `/tmp/opencode/gg-real-smoke10/` 只留下 `gg_runs.status=queued/stage=QUEUED`、`gg_steps=0`、`gg_model_calls=0` 和空模型账本，没有进入 Worker，因此不计入真实模型失败分母。smoke11 run `e37e4b0deb4b4dd58830b2226347dfb1` 已完成 15 个阶段，最终 57 requirements、589 impacts、618 local candidates、50 families、45 guide items、353 findings、587 model calls；quality `fail`，coverage 有 68 unresolved impacts、19 latest contract uncertain、3 requirement gaps，Residual 为 3 轮 `new_uncovered`、`max_rounds_reached/saturated=false`，资格 `candidate_with_findings`。其旧版本账本错误详见 FL-D358/FL-D359。
- 下一步：smoke12 已完成并新增 FL-D360；启动 smoke13 核对当前 v2/v4/v4 真实结果。只有质量/覆盖/Residual 门禁通过且模型复核身份满足要求时才执行生成后 blind benchmark。
- 变更记录：2026-10-27 新增；后续补充 smoke10 无效启动证据并改用 smoke11；不记录密钥、令牌或模型响应正文。

## FL-D356 D06 当前代码离线重放闭合 G15/G18，但 G06 Y 类单向限制保持人工复核阻塞（2026-10-27）

- **2026-10-28 业务归因重核**：D06 p831/p1245“本基金各基金份额类别在费用收取上不同，各基金份额类别对应的可分配收益将有所不同”已表达G18新意，依FL-D106的语义判断原则，不需另问用户是否接受中性句。其他合同仍需逐站点核实完整语义，不泛化为任意中性句都满足；离线重放也不是业务裁定或正式验收证据。G15的10日是旧例、5日是新机制，已有差异仅提示裁定；不再列期限待业务决定。

- 发现日期：2026-10-27，使用 D06 真实运行的原件、checkpoint、working DOCX 和最新工作区代码执行完整 `offline_checkpoint_replay`；该验证没有新增模型请求。
- 问题与影响：旧真实报告是在本轮 G06/G18/G15 修复前生成，不能继续作为当前代码结论。最新完整重放显示 G18 的 p1245 概括句和原有 p831 物理站点均通过 `ALREADY_SATISFIED`/`source_operation_policy_equivalent`；G15 p810 的 sweep finding 被同一物理站点的 G16 已授权新支付机制证明消除。G06 p280 的“Y类基金份额不能转换为A类、C类、E类或F类基金份额”被识别为单向 Y 类路径，按业务约束保持 `semantic_delete_review_required`，不能自动删除或以规范旧句缺失关闭。
- 证据：最新重放目录 `/tmp/opencode/recall-runs/d06-current-full-replay/001-d06/`；`report.json` 为 `execution_mode=offline_checkpoint_replay`、`delivery_status=incomplete`、`artifact_claim_replay.verified=false`，唯一 Claim Replay failure 为 G06 `CLAIM_OPERATION_UNPROVEN / semantic_delete_review_required`。`operation_coverage` 中 G15 为 p807/p1286 `ARTIFACT_VERIFIED`，G18 为 p1245/p831 `ALREADY_SATISFIED`；sweep p810 为 `resolved / sibling_authorized_effect`。重放产物仅为 working files，最终交付目录没有正式 `final.docx`/`redline.docx`。
- 处理方法：保留 G06 review-only 和 fail-closed；不把离线重放、working DOCX、working 哈希或旧真实报告提升为正式合同交付。G15 兄弟 operation 授权仅限 G15 sweep，G18 概括句仍要求收益差异或分别计算等业务事实，p132 未分组类别句继续拒绝。
- 状态与验证：**G15/G18 当前代码门禁已通过离线重放；G06 等待人工业务适用性决定，D06 仍 incomplete，项目继续 NO-GO**。本轮代码定向组合回归为 310 passed；本次重放使用 31 个缓存模型响应、0 个 task fallback，不能替代真实 Worker/真实模型重跑或正式下载验收。
- 下一步：等待/完成 smoke9 后，若真实模型服务稳定，重新真实运行 D06；在 G06 业务授权明确前不删除 p280。真实运行通过后仍须完成 Claim Replay、残留、正式 final/redline、报告/哈希及授权下载核验。
- 变更记录：2026-10-27 新增；不记录密钥、令牌或其他凭据。

## FL-D355 smoke9 真实法规指引运行完成但未达到资格（2026-10-27）

- 发现日期：2026-10-27，smoke8 限流/熔断后按 FL-D354 启动新的真实法规指引运行。
- 问题与影响：smoke9 已完成真实运行，但生成候选仍未满足质量、覆盖和 Residual 完整性门禁；因此不能作为 candidate-ready 运行，也不能启动生成后 blind benchmark。
- 证据：运行目录 `/tmp/opencode/gg-real-smoke9/`，账本 `/tmp/opencode/gg-real-smoke9/ledger.sqlite`，输出 `/tmp/opencode/smoke9.out`，退出码 `/tmp/opencode/smoke9.exit=0`。最终 run `a9f78342dc674524bf8c79fd77f47544` 为 `status=complete_with_unresolved`、`stage=COMPLETED`、`qualification_status=candidate_with_findings`；69 requirements、681 impacts、628 local candidates、71 families、59 guide items、264 findings、536 model calls。质量为 `fail`，coverage 为 111 unresolved impacts、59 latest contract uncertain、1 requirement gap，Residual 为 `max_rounds_reached` 且 `saturated=false`。所有角色仍使用 `OpenCodeGo/deepseek-v4.1-flash`，`independent_model_review_status=independent_model_review_not_qualified`。
- 处理方法：保留 smoke9 作为未达资格的真实基线；针对覆盖审计单响应 `maxItems` 失败新增 FL-D357 的分批审计修复，使用新 prompt version、全新数据目录和独立账本重跑 smoke10，不修改 gold、质量门禁或历史结果。
- 状态与验证：**smoke9 已完成但未资格，FL-D357 的 smoke10 外部真实运行进行中，项目继续 NO-GO**。未生成正式盲评结果。
- 下一步：等待 `/tmp/opencode/smoke10.exit` 和最终 `runs.sqlite3` 状态，核对每个审计批次的真实 HTTP/schema 结果以及质量、覆盖、Residual 和 qualification；若资格仍失败，按新证据继续修复并登记。
- 变更记录：2026-10-27 新增；不记录密钥、令牌或其他凭据。

## FL-D354 法规指引 smoke8 触发上游 429 后共享熔断（2026-10-27）

- 发现日期：2026-10-27，模型恢复后按 FL-D347 要求使用当前受保护配置执行全新法规指引真实 smoke8；输入为真实销售费用管理规定 PDF 和 2 份公开基金合同，使用独立 SQLite 数据库与模型账本。
- 问题与影响：前三次 `guide_req_extract` 请求均收到 HTTP 200 并通过 schema 校验；随后 `guide_req_review` 连续 3 次收到 HTTP 429，未提供 `Retry-After`。共享账本按设计将最近 3 次 `MODEL_RETRY_EXHAUSTED` 判为服务熔断，之后 274 个调用在本地直接返回 `MODEL_CIRCUIT_OPEN`，没有继续访问上游。smoke8 因 fail-closed 保留了 53 条要求和 252 条 possible/unresolved impact，但没有 families 或 guide items，不能用于资格判断。
- 证据：run `9bf46661ec8444479a8451ddad6eb248`，数据库 `/tmp/opencode/gg-real-smoke8/data/runs.sqlite3`，账本 `/tmp/opencode/gg-real-smoke8/ledger.sqlite`；模型调用记录为 277 次，其中 3 次 `guide_req_extract` 成功、1 次 `guide_req_review` 逻辑调用对应账本中的 3 次 HTTP 429、其余记录为 `MODEL_CIRCUIT_OPEN`。账本 metadata 仅记录任务类型、错误码、HTTP 状态、耗时和模型标识，不含凭据值。
- 处理方法：没有修改质量、来源证明或 fail-closed 代码；使用两个全新账本分别验证完整 `guide_req_review` 和单条 `guide_intent`，均以 HTTP 200 成功。随后用新账本连续执行 3 次 `guide_intent` 加 1 次完整 `guide_req_review`，4 次均 HTTP 200。为下一次全量真实 smoke9 将 guide 运行时重试从 2 次提高到 4 次，仍保持单并发、独立账本、真实输入和原有质量门禁。
- 状态与验证：**smoke8 被服务限流/熔断阻塞，未通过资格；原因已定位，smoke9 正在使用新目录 `/tmp/opencode/gg-real-smoke9` 和新账本运行**。隔离探测证明审查 schema、角色配置和模型恢复路径可用，但尚未证明全量 smoke9 能稳定闭合。
- 下一步：smoke9 完成后核对每个阶段、实际 HTTP 错误、requirements/impacts/families/guide items、质量与覆盖门、Residual 和生成后盲评；若仍发生 429，按真实账本证据调整请求间隔、批量大小或服务侧限流处理，不降低质量门禁。
- 变更记录：2026-10-27 新增；不记录密钥、令牌或其他凭据。

## FL-D353 OpenCode Go 模型要求 workspace 使用 Global region（2026-10-27）

- 发现日期：2026-10-27，按用户要求仅将受保护配置中的 `LLM_API_KEY` 替换为新 key，并保持 OpenCode endpoint、`deepseek-v4.1-flash` 和其他请求配置不变后进行最小真实 smoke。
- 问题与影响：新 key 已通过认证，但 OpenCode `/chat/completions` 对当前模型返回 HTTP 400，模型服务明确回复：`This Go model requires Global regions. Select Global in your workspace's Privacy settings to use it.` FundLex 尚未进入真实合同事实提取、Worker 修改、Claim Replay 或 DOCX 交付阶段。
- 证据：当前配置仍为 `https://opencode.ai/inference/go/v1`、`deepseek-v4.1-flash`、原有 `thinking` 请求选项；使用当前配置分别发送带请求选项、无请求选项和最小请求的三次 smoke，均返回同一 HTTP 400 上游错误。错误正文未写入 API key。配置备份为 `/etc/fundlex-recall.env.bak-20261027-100547`。
- 处理方法：仅更新 `/etc/fundlex-recall.env` 的 `LLM_API_KEY`，并设置文件权限为 600；未修改 endpoint、模型、请求选项或仓库文件中的凭据配置。新 key 未写入仓库、文档、账本或日志。
- 状态与验证：**外部 workspace region 阻塞，项目继续 NO-GO**。新 key 的认证已验证，但模型调用仍被 workspace Privacy/region 设置拒绝；没有合同产物。
- 下一步：在 OpenCode workspace 的 Privacy settings 将 region 设置为 Global 后，保持当前 endpoint、模型和其他配置不变，重新执行最小 schema smoke；smoke 成功后再重跑修复后的 D06。
- 变更记录：2026-10-27 新增；不记录凭据值。

## FL-D352 当前受保护 key 与 gpt-6-luna 评测端点不匹配（2026-10-27）

- 发现日期：2026-10-27，修复后的 D06 真实评测重新启动时发现。
- 问题与影响：本机 `/etc/fundlex-recall.env` 当前配置的是 `https://opencode.ai/inference/go/v1`、`deepseek-v4.1-flash` 和 `thinking` 请求选项，不是既定评测路径 `https://free.quanthatch.com/v1`、`gpt-6-luna`、`reasoning_effort=high`。按受保护配置原样运行 D06 时，首个 `recall_facts` 请求返回 HTTP 402；仅在当前进程覆盖到既定端点和模型、继续使用同一 key 做最小真实 smoke 时返回 HTTP 401。D06 因此没有进入事实提取或修改阶段，没有正式合同产物。
- 证据：`/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06-fixed-600b/ledger.sqlite` 的请求记录为 `configured_model=deepseek-v4.1-flash`、`http_status=402`、`MODEL_HTTP_ERROR`；对应 `summary.json` 为 `STOP:MODEL_HTTP_ERROR`、`targets=0`。既定端点的独立 smoke 账本 `/tmp/opencode/gpt6luna-smoke-20261027.sqlite` 记录 `configured_model=gpt-6-luna`、`http_status=401`、`MODEL_HTTP_ERROR`。两个账本均未记录 API key 值。
- 处理方法：未修改 `/etc/fundlex-recall.env`，未把凭据写入仓库、日志、命令参数或文档；分别保留了“当前配置实际运行”和“既定端点最小认证 smoke”的失败证据。此前代码层 D06 定向回归为 **339 passed**，不能替代真实模型运行。
- 状态与验证：**外部认证/配置阻塞，项目继续 NO-GO**。D06 修复后的真实 Worker、真实模型、DOCX、Claim Replay 和授权下载链路尚未重新执行。
- 下一步：向既定 `free.quanthatch.com/v1` 提供可认证的 `gpt-6-luna` key，或明确批准使用当前 key 对应的模型服务并完成最小 schema smoke；服务认证成功后，再用独立账本重跑 D06，随后复测 D13、D09 及 D01–D20 固定分母。
- 变更记录：2026-10-27 新增；不记录凭据值。

## FL-D351 评测启动器直接 source env 文件会破坏 JSON 配置（2026-10-27）

- 发现日期：2026-10-27，启动修复后的 D06 真实评测时发现。
- 问题与影响：`/etc/fundlex-recall.env` 中的 `FUNDLEX_MODEL_EXTRA_HEADERS_JSON` 和 `FUNDLEX_MODEL_REQUEST_OPTIONS_JSON` 是合法 JSON；通过 `source /dev/stdin` 注入时，Shell 会移除 JSON 内的双引号，`ModelGateway.from_env()` 在首次构造网关时抛出 `MODEL_EXTRA_HEADERS_INVALID`，本次没有发出模型请求，也没有生成合同产物。
- 证据：失败进程输出为 `json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes`，随后为 `fundlex.model.ModelError: MODEL_EXTRA_HEADERS_INVALID`；失败命令对应输出目录 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06-fixed-600/`，仅留下空账本，没有模型事件或合同产物。之后一次保留 JSON 原文的子进程在评测器等待上限内未返回，目录 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06-fixed-600/` 同样没有报告；该次不计入模型请求或合同分母。受保护配置变量仅做存在性与长度/哈希检查，未输出值。
- 处理方法：本轮使用受保护管道读取 env 文件的原始 `name=value` RHS，先在当前进程验证两个 JSON 变量可解析，再通过子进程环境映射传入评测 runner；凭据未进入命令参数、日志或仓库。
- 状态与验证：**启动方式已绕过并重新启动真实运行，待运行完成后核对模型请求和交付产物**。原始 `source` 失败不计入模型评测分母，不修改历史合同失败分母。
- 下一步：评测完成后补充真实 D06 的 targets、plan、Claim Replay、residual、正式 final/redline 和授权下载门禁结果；若持续使用该 env 文件，后续部署/评测启动器应采用保留原始 RHS 的解析方式。
- 变更记录：2026-10-27 新增；不记录凭据值。

## FL-D350 gpt-6-luna 长上下文响应超时导致真实合同无法稳定闭合（2026-10-27）

- 发现日期：2026-10-27，使用 FundLex `ModelGateway` 接入 `https://free.quanthatch.com/v1` 的 `gpt-6-luna` 并带 `{"reasoning_effort":"high"}`，真实重跑 D06、D09、D13。
- 问题与影响：最小 schema 请求可成功，但 D06、D13 的 `recall_inventory` 长上下文请求在 180 秒客户端上限内连续两次 `MODEL_NETWORK_ERROR`，任务按 fail-closed 生成 `not_generated`，没有正式合同产物。即使将超时上限提高到 600 秒，合同也只能完成到 `incomplete`，尚有 Claim Replay、实际写入或审计缺口，不能进入正式交付。
- 证据：网关 smoke 实际返回 `gpt-6-luna` 合法 JSON，1 次 HTTP 请求、无错误，约 2.34 秒；D13 180 秒运行 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d13/` 记录 4 次请求、2 次 `recall_inventory` 网络超时、约 `$0.0197`，无 DOCX；D06 同样 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06/` 记录 4 次请求、2 次超时、约 `$0.0217`，无 DOCX。提高至 600 秒后，D13 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d13-600/` 为 `incomplete`、16 次 HTTP、13 targets、5 edits、约 `$0.0451`，生成 working final/redline；D06 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06-600/` 为 `incomplete`、32 次 HTTP、80 targets、17 edits、约 `$0.0886`，生成 working final/redline。所有账本均独立放在 `/tmp/opencode/`，未写入凭据。
- 处理方法：先以独立账本验证实际网关 schema 请求；180 秒失败后仅再做一次明确标注的 600 秒真实运行，不把超时重试或 working 文件冒充最终交付。D13 保留 G01–G04/G10/G16/G18 站点证明缺口、G10 执行错误和 G12 旧内容残留；D06 保留 G05/G06/G11 的 Claim Replay/最终操作证明缺口及 G18 类别实例化审计问题。新评测 runner 将从 model event 首个错误补入 `summary.json` 的 `error_code`，使批量摘要可审计，但不改详细报告或历史失败分母。
- 状态与验证：**外部服务性能与合同闭环均未解决，项目继续 NO-GO**。D09 使用正确原件 SHA `48e4b5b874a05e26beb87382469b5b77dffac3bf5e746c5059379569435f898f` 的运行 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d09/` 为 `incomplete`、13 次 HTTP、10 targets、4 edits、约 `$0.0367`；生成 working 文件但未通过交付门禁。D13/D06 的 600 秒运行均有实际 `final_sha256`/`redline_sha256`，但只有 working 文件和 unresolved，未生成正式 final/redline 下载交付。
- 下一步：若继续使用该模型，正式评测 runner 默认超时需按长上下文实际分位数重新登记；先修复 D13 G10/G12 与 D06 G05/G06/G11/G18 的执行闭环，再用独立账本复测。未完成 D01–D20 固定分母、holdout、候选冻结和普通工作台 E2E 前，不宣称资格或部署完成。
- 变更记录：2026-10-27 新增；本条不记录 API key 值。

## FL-D349 评测摘要未传播模型事件阻塞码（2026-10-27）

- 发现日期：2026-10-27，D06/D13 真实运行后检查 `tools/evaluation/recall_run.py` 的批量摘要。
- 问题与影响：管线详细 `report.json` 保留了 `model.events[*].error_code`，但当报告顶层没有 `error_code` 时，`summary.json` 的合同行仍写入 `null`。D06/D13 的真实网络超时因此在批量摘要中显示为无错误，降低停止原因和外部阻塞的可见性。
- 证据：D13 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d13/summary.json` 与 D06 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06/summary.json` 的 `error_code` 为 `null`；对应 `report.json` 的 model events 有 `recall_inventory`、`MODEL_NETWORK_ERROR`、两次尝试和 180 秒延迟。
- 处理方法：`_summary_row()` 在顶层错误码为空时读取 model events 的首个错误码，仅改善新运行摘要的可审计性；详细报告、账本、历史摘要和固定失败分母不回写。
- 状态与验证：**已实施，待定向测试验证**。当前未修改历史运行结果。
- 下一步：补最小 `_summary_row` 回归或运行相关评测测试；后续真实批量运行核对摘要与详细报告一致。
- 变更记录：2026-10-27 新增。

## FL-D348 free.quanthatch DeepSeek 对话端点不可用（2026-10-27）

- 发现日期：2026-10-27，用户提供 `https://free.quanthatch.com/v1` 与 API key 后进行最小兼容性探测。
- 问题与影响：Bearer 认证可以访问 `/v1/models`，但 DeepSeek 对话调用无法取得响应，当前不能替代 D09/D13/D06 的真实评测模型服务。
- 证据：`GET /v1/models` 返回 HTTP 200，列出 `deepseek-v4-flash`、`deepseek-v4-flash-ascend`、`deepseek-v4-pro`；`POST /v1/chat/completions` 的 Ascend/Pro 模型立即返回 HTTP 502，错误为 `upstream_error / Upstream service temporarily unavailable`；基础 Flash 模型使用 `max_tokens=1` 的最小请求等待 90 秒后仍为客户端超时。未记录或写入 API key 值。
- 处理方法：仅在当前进程内使用用户提供的凭据完成模型列表和最小请求探测，没有写入仓库、文档、环境文件、日志或评测账本；不把模型列表可见误判为对话服务可用。
- 状态与验证：**外部服务阻塞，未解决**。该端点暂不能作为正式真实模型路径；D09/D13/D06 仍保持未完成。
- 下一步：由于 key 已在聊天中暴露，正式评测前应先撤销并轮换该 key，再通过受保护的本机环境变量注入新 key。服务恢复后需用 FundLex 实际模型网关配置完成最小请求，再运行真实合同评测。
- 变更记录：2026-10-27 新增；不保存凭据值。

## FL-D347 法规复合源块部分引用导致要求条件/条款主题丢失（2026-10-27）

- 发现日期：2026-10-27，smoke7 真实法规要求与候选质量复核。
- 问题与影响：模型可以正确引用同一主题的多个法规 block，但只把首句写入 `source_quote`，导致第八条前端/后端收费、按金额（份额）数量或持有期限分档及“其他基金”范围等后续规范性内容没有独立可验证的要求；模型还可能保留“对于/除……外”等原文条件，却在结构化 `conditions`/`exceptions` 中丢失。另有候选把“基金管理人直销不得收费”与 A/D/C 类历史收费结构无渠道边界拼接，直接产生法规忠实性冲突。
- 证据：smoke7 run `3c694aebc9bd4579aec1996bf8dac9df` 的 `R-857358f863` 引用 B0030、B0031、B0032，但 `source_quote` 只包含 B0030；原始法规 block B0027–B0028 明确包含主动偏股型、其他混合型、指数/债券型及其他基金费率范围。quality findings 中 `F-5e4b0902e57520913921` 的新文案把直销禁令与 A/D/C 收费句无条件相邻。
- 处理方法：在模型抽取、repair 和 challenger 完成后增加 source-backed supplement：只对模型已经列入 `source_block_ids`、但完整源文没有进入 `source_quote` 的 block 补建原子 `PolicyRequirement`，保留精确 source quote、规范类型、合同处置和 provenance；完全未被模型引用的 block 继续走文章 coverage/challenger 路径，避免 supplement 取代独立抽取。对每个要求从其 source quote 恢复显式条件和例外。authoring 在 Local Candidate 和 Family 归并后均执行直销收费隔离：历史份额收费句自动附加“通过其他基金销售机构销售”边界，并保留直销条件；quality gate 对仍无渠道边界的历史收费句产生 critical fidelity finding。
- 状态与验证：**已实施，离线回归通过**。新增源块部分引用与未引用边界、直销收费候选隔离和 quality fail-closed 测试；法规/指引主套件 **15 passed**，浏览器法规套件 **1 skipped**；`PYTHONPATH=. .venv/bin/pytest -q` 完整 Python 回归 **1655 passed / 56 skipped / 3 warnings / 423.84s**；`compileall`、`py_compile` 和 `git diff --check` 通过。Fake pipeline 恢复为 `complete/candidate_ready`。尚未重新调用真实模型，smoke7 历史 75% 召回和 6 条 fidelity finding 仍保留为未修复真实基线。
- 下一步：模型服务恢复后用独立账本重新运行 smoke7，核对新增 requirements、条件覆盖、G-R02/G-R11/G-R12 及第八条费率主题；若达到 qualification，再运行 500+ corpus、D01–D20 和 holdout。未完成真实复测前不得把离线回归或旧 smoke7 修复结果宣称为资格通过。
- 变更记录：2026-10-27 新增；source supplement 范围在本轮收紧为“仅补模型已引用的部分跨度”，并补充最终 challenger 后的归一化调用。

## FL-D344 单类合同默认类别占位导致事实级联 UNKNOWN（2026-10-27）

- 发现日期：2026-10-27，D09/D13 单类基金真实评测复核。
- 问题与影响：模型在没有 A/B/C 等字母份额类别的合同中返回“默认份额类别”。该名称不可能在源文中验证，原实现因此同时丢失 `share_class_structure`、申购费组和销售服务费组，D09 原报告出现 64 条级联 unresolved；D13 还未进入事实提取就因模型熔断停止。
- 证据：D09 原报告 `var/recall-runs/real-20261026-single-a/002-*/report.json` 的 `facts.classes` 为“默认份额类别”，`share_class_structure` 状态为 `UNKNOWN`；真实合同费率段只写“申购费用由投资人承担，不列入基金财产”，没有当前基金销售服务费条款。
- 处理方法：`single_class_structure_verified()` 识别无字母/货币类别且无多类枚举的单一结构；对模型占位名统一归一为内部 `__single__`；只在源文申购费用引文可验证、且其前后限定范围没有当前基金销售服务费条款时，验证 `subscription_fee=True`、`service_fee=False`。`fee_value(..., single_bound=True)` 对无类别名称的单类费用引文按单类边界解析，费用事实仍必须由合同原文支持。
- 状态与验证：**已实施，定向回归通过**。单类/费用事实/条件状态/Replay 相关套件与本轮 survey 回归合计 **177 passed**；D09 检查点重放已输出 `classes=[('__single__', True, False)]`、规则映射 22/22。该重放在 inventory 阶段因事实变化造成 `MODEL_REPLAY_MISS`，不构成完整合同交付证据。
- 下一步：模型服务恢复后用独立账本重新真实运行 D09、D13，逐份核对事实、实际 DOCX、Claim Replay、报告和授权下载；在此之前不得把 D09/D13 标为 complete。
- 变更记录：2026-10-27 新增；保留原 D09 失败分母和 402/熔断证据，不修改 gold 或历史报告。

## FL-D345 类别替换 survey 短引文无法绑定完整物理站点（2026-10-27）

- 发现日期：2026-10-27，D06 真实批量报告复核。
- 问题与影响：G02 survey 用“F 类基金份额”作为已满足政策的短引文；同一段可能重复出现该类别，严格 `resolve_source_quote()` 会拒绝不完整或多次出现的引文。D06 因此产生 5 条 `SURVEY_QUOTE_UNRESOLVED` orphan，虽然这些段落本身已有完整政策文本。
- 证据：`var/recall-runs/real-20261026-dev20/006-D06-*/report.json` 的 survey 记录在 p131、p802、p829、p1243、p1282 均为 `quote: F类基金份额`；原始 p131 同时包含 A/Y 申购费组与 C/E/F 服务费组。D06 的 G06 另有实际单向 Y 类转换限制，不能用短引文问题掩盖。
- 处理方法：对 G02/G04 的 satisfied survey hit，先继续要求完整源引文或唯一句子边界；只有在短引文无法绑定、且完整段落自身可唯一作为 source quote 时，才将整个物理段绑定为 satisfied target，写入 `start/end`、`resolution` 和 segment proof。该兜底仅作用于已满足的类别替换证据，不放宽 needs_edit 或其他规则的源文门禁。
- 状态与验证：**已实施，离线/合成验证通过；真实 D06 尚未复跑**。新增短引文重复场景测试，相关定向套件 **177 passed**。使用旧 D06 检查点重放时事实提取成功，但 inventory 因上下文哈希变化 `MODEL_REPLAY_MISS` 停止，因此不能更新 D06 正式结果。
- 下一步：模型服务恢复后真实重跑 D06，核对 5 个 orphan 是否消失、G02/G04 物理站点是否正确、G06 单向转换限制是否仍保持阻塞；不得凭离线重放宣称 D06 完成。
- 变更记录：2026-10-27 新增；G06 的语义限制仍按 fail-closed 处理。

## FL-D346 真实模型服务 HTTP 402 阻塞 D09/D13 复测（2026-10-27）

- 发现日期：2026-10-27，单类结构修复后的真实合同复测。
- 问题与影响：新的 D09 真实运行在事实提取的首个请求收到 HTTP 402，未产生合同产物；此前 D13 使用旧共享隔离账本时因 `STOP:MODEL_CIRCUIT_OPEN` 停止。继续复用熔断账本会把服务侧阻塞误判为合同缺陷。
- 证据：`var/recall-runs/real-20261027-d09a/summary.json` 为 `delivery_status=stopped`、`error_code=STOP:MODEL_HTTP_ERROR`、targets=0；`/tmp/opencode/eval-ledger-20261027-single.sqlite` 的请求 metadata 记录 `http_status=402`。未带凭据的健康探测仅返回 401，不能据此判断凭据值或服务账户状态。
- 处理方法：新建独立账本重试并保留 402 账单证据；模型停止按 stop/verification-blocked 路径处理，不生成或冒充最终合同。等待服务恢复后分别使用新隔离账本重跑 D09、D13，保留真实请求费用和失败记录。
- 状态与验证：**外部服务阻塞，未解决**。D09/D13 均没有新的真实完成结果；D09 检查点仅用于事实层验证，inventory 重放因 `MODEL_REPLAY_MISS` 停止。
- 下一步：模型服务恢复后先做一次最小真实请求健康确认，再运行 D09、D13 全流程；若仍为 402，继续保持 NO-GO 并登记新的证据，不改写历史失败分母。
- 变更记录：2026-10-27 新增；本条不记录密钥、令牌或凭据值。

## FL-D342 盲评 CLI 初始化只读运行库时仍执行迁移写入（2026-10-27）

- 发现日期：2026-10-27，使用 root 生成、普通用户只读的法规 smoke7 SQLite 运行目录执行生成后 Blind Benchmark。
- 问题与影响：`benchmark` 评分只需要读取已完成运行，但原 CLI 通过普通 `RunStore` 初始化，初始化阶段会执行迁移更新并切换 WAL。对 root-owned 的 `runs.sqlite3` 会以 `sqlite3.OperationalError: attempt to write a readonly database` 退出，无法保存正式的生成后评分结果。该失败发生在评分读取前，不代表 benchmark 逻辑或生成结果失败。
- 证据：原始目录 `/tmp/opencode/gg-real-smoke7/` 的 `runs.sqlite3` 为 `root:root`、0644；原命令返回上述 SQLite 错误。将目录复制为可写副本后评分得到关键要求召回 75.0%、已知条款覆盖 100%、条件覆盖 58.33%、6 条关键忠实性问题、Residual `max_rounds_reached`；修复后同一原始目录命令成功，并生成 `benchmarks/sales_fee_regulation_2025/results/3c694aebc9bd4579aec1996bf8dac9df.json`。
- 处理方法：`RunStore` 增加 `read_only=True`，只读模式不创建目录、不建表、不迁移、不切换 WAL；`GuideGenerationStore` 在只读模式跳过 schema 写入；benchmark CLI 使用只读 Store。可写路径保持原有初始化行为。
- 状态与验证：**已实施并验证**。法规/指引相关定向套件 **22 passed / 1 skipped**；只读持久化边界和法规套件 **18 passed**；原始 root-owned smoke7 目录 benchmark 成功，评分结果与可写副本一致。未修改原始数据库内容，未读取人工 Guide 作为生成输入。
- 下一步：若扩展到其他离线评分器，统一检查其 Store 初始化是否显式使用只读模式；不要把可写副本评分当作原始产物权限边界的验证。
- 变更记录：2026-10-27 新增并修复；首次原始目录失败证据和修复后成功证据均保留。

## FL-D343 完整 Python 回归出现一次顺序相关的单类事实断言失败（2026-10-27）

- 发现日期：2026-10-27，完整 `PYTHONPATH=. .venv/bin/pytest -q` 第二次长跑。
- 问题与影响：全量运行在 **1651 passed / 56 skipped / 3 warnings / 1 failed** 时，`tests/test_replay_site_provenance.py::test_unnamed_single_class_normalizes_model_default_and_verifies_no_service_fee` 断言 `subscription_fee_group == VERIFIED` 失败，实际为 `UNKNOWN`。该测试验证无字母类别合同被归一为 `__single__` 后，申购费和销售服务费两类事实均应有证据；若稳定发生，会使单类合同的事实门禁过度保守并扩大未处理范围。
- 证据：失败发生在约 80% 位置；同一测试单独运行 **1 passed**，该测试文件独立运行 **23 passed**；手工用相同两段 DOCX 原文和模型返回值调用 `facts_from_value()` 得到 `subscription_fee_group=VERIFIED`、`service_fee_group=VERIFIED`、`value_verified=True`。当前未取得稳定的前置测试污染或源码分支复现，因此暂不能把它标记为已修复，也不能把一次重跑通过解释为根因已消除。
- 处理方法：本轮未修改该事实逻辑，保留单类结构、边界证据和既有回归；先进行完整回归重跑并记录是否复现。若再次出现，按完整测试顺序定位全局状态/环境污染并补最小回归。
- 状态与验证：**已确认一次、后续未复现，按疑似顺序/环境 flake 保留**。本轮完整 `PYTHONPATH=. .venv/bin/pytest -q` 为 **1655 passed / 56 skipped / 3 warnings / 423.84s**；失败测试单独运行 **1 passed**，所属文件此前 **23 passed**，本轮法规新增回归后主套件继续通过。没有证据表明当前源码仍有稳定事实状态错误，项目整体仍 NO-GO。
- 下一步：后续全量回归继续记录失败测试及顺序；若再次复现，先保存完整收集顺序和环境后定位，不以当前一次全量通过扩大真实模型资格结论。
- 变更记录：2026-10-27 新增；同日第二次完整回归通过，状态由“待第二次定性”更新为“未复现 flake”。

## 当前工作区验证补录（2026-10-26，source proof/Worker/前端收尾）

- 当前分支为 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`；工作区仍 dirty，保留 Compare、法规指引生成、Feishu、前端和本轮引擎/交付修改，未 commit、未 push、未部署。
- 固定源码验证快照位于 `/tmp/opencode/source-proof-validation-pfsxw_go/`，包含 2908 个源码/构建文件，manifest SHA-256 `551a2c2edaa0b10cf852f220bd0fbfdc3b7d03f5eb885f775f1d304d414149b8`。快照之后并行法规指引生成工作又写入 `frontend/guide_generation.js`、`fundlex/guide_generation/api.py`；两项不属于本轮 source proof/Worker/交付回归范围，已单独通过 9 个指引生成测试及 JS/Python 编译检查。
- 完整 Python 回归：**1632 passed / 53 skipped / 3 warnings / 428.35s**。任务/存储/API 定向套件：**77 passed / 1 skipped / 1 warning**。完整浏览器套件在构建完成且不并行写 `frontend/dist` 后：**41 passed / 82.63s**。本轮候选法规密码浏览器链路定向测试：**1 passed / 9.01s**。前端 `npm run build`、`npm run typecheck`、`npm run lint`、Vitest **14 passed**，`node --check`、`.venv/bin/python -m py_compile`、`git diff --check` 均通过。
- 一次并行执行浏览器测试与 Vite build 时出现 1 个 V2 Review 失败；独立重跑通过，随后在不并行构建的固定源码状态下完整浏览器套件 41/41 通过。该局部失败不改变代码回归结果，但已登记为 FL-D335，后续浏览器验收须先完成 build 再运行测试。
- 本轮未调用真实模型、未改变模型账本、未执行部署或生产重启。项目级状态继续 **NO-GO**：D01–D20 固定分母、labels/gold、预算授权、正式候选发布、真实 OAuth 回调、MySQL 8 并发和完整真实用户交付仍未闭合。

## FL-D335 浏览器回归与 Vite build 并行清空 dist 造成短暂资源竞态（2026-10-26）

- 发现日期：2026-10-26，完整浏览器回归与前端 production build 并行执行。
- 问题与影响：Vite build 使用 `emptyOutDir=true` 清空并重建 `frontend/dist`；浏览器服务同时从同一目录读取 React 入口及带 hash 的 assets 时，可能在资源切换窗口收到 404，表现为 V2 Review 深链返回空页面/后端 `NOT_FOUND`，造成单个浏览器用例失败。该现象会污染回归结论，但不代表 Review 路由本身失败。
- 证据：并行命令出现 `test_review_renders_void_document_tags_without_page_error` 失败，浏览器 body 为空；该用例独立运行通过，随后在 build 完成后重新运行 `FUNDLEX_BROWSER_TESTS=1 PYTHONPATH=. .venv/bin/pytest -q tests/browser` 得到 **41 passed / 82.63s**。同次 `npm run build` 成功。
- 处理方法：本轮采用先完成 build、再捕获源码/构建 manifest、最后运行浏览器套件的顺序；不改变路由或资源回退逻辑，也不把并行运行结果作为验收证据。后续需要并行开发时，浏览器测试使用已完成构建的只读 dist，或使用独立临时构建目录/服务。
- 状态与验证：**已通过验证流程规避；代码层隔离构建目录仍是后续工程改进项**。固定快照 manifest 已保存；完整 Python、浏览器和前端检查均通过。本轮未部署。
- 下一步：任何生产候选浏览器验收前先固定候选源码和 build 产物，记录 manifest/hash 后再启动服务与浏览器；禁止在验收期间清空或覆盖同一 dist 目录。

## FL-D340 D01/D04 真实合同暴露跨段引文、ONE_OF 变体、复合站点和 sweep 误报（2026-10-26）

- 发现日期：2026-10-26，真实模型运行 D04/D01 当前源码。
- 问题与影响：
  - D04 G04 的 `A 类基金份额` 引文被清单位于跨段句子的前半段 p82，真实定义续在 p83；严格 source proof 因此找不到 operation 站点，Claim Replay 一直报 `verified site missing`。
  - D04 G12 源文同时含“25% 归基金财产”和“7 日 1.5%”两段，属于指南 G12:1 的历史措辞；清单选成 G12:0 后，确定性分配替换拒绝执行，模型 compose 又删掉过多内容，最终只由 G13 删除 7 日句，G12 未完成。
  - D04 G17 同一复合删除站点同时存在 `needs_edit` 和 survey `satisfied` 两个 target，Claim Replay 将其误判为同一 operation/站点缺少 occurrence identity 的歧义。
  - D01 G13/G15 sweep 把 G12 新政策文本或 G16/G15 新支付条款误报为旧条款残留；其中 G15 理由声称“10 个工作日”，实际产物为“5 个工作日”。这些 orphan evidence 会阻止 complete。
  - D04 G09 实际段落已改写为“扣除或加上相应的费用”，但结尾“人民币元”未按指南改为“元”。
- 处理方法：
  - 已满足 target 的跨段引文：仅当前段落末句未结束、同 zone/section、引文在唯一相邻段中只出现一次时，才把完整句子重绑到续段；对“引文前半段在上一段、后半段在当前段”的形态，裁剪掉上一段前缀，只保留当前段实际可解析的完整边界，仍要求唯一。
  - G12 在 ONE_OF 组内按源文结构选择变体：源文含“赎回费总额”和“7 日”时选择含“未归入基金财产的部分”的 G12:1；确定性 `_g12_allocation_end` 只替换该 operation 自己的分配前缀，保留后续 G13 删除句。
  - G17 同一复合站点上 `needs_edit` 与 `satisfied` 重复时保留可执行 target，survey 重复标记 `DUPLICATE_OPERATION_TARGET`；Claim Replay 对完全相同的 composite 几何不再判歧义。
  - sweep orphan 若其 reason 引用的旧条款在产物中全部不存在，则确定性判为 `claimed_residual_absent`，不作为残留证据；没有引用旧条款、或引用仍存在时继续阻塞。
  - G09 增加已知变体“赎回金额单位为人民币元”→“赎回金额单位为元”。
- 证据与验证：
  - D04 修复前 `incomplete`（G04/G12/G17）；修复后 `var/recall-runs/real-20261026-d04h` 为 **complete**，44 targets、18 edits、28 calls、$0.0312、145 秒，Claim Replay `verified=true`（18 edits/22 units），final SHA `5bffa2e7...`、redline SHA `03b37d03...`，实际 p83/p194 内容正确。
  - D01 修复前 2 条 orphan evidence；修复后 `var/recall-runs/real-20261026-d01c` 为 **complete**，27 targets、19 edits、28 calls、$0.0269、149 秒，Claim Replay `verified=true`（19/21），final SHA `c4c2bbdb...`、redline SHA `874d7a29...`，p229 为 G12 新政策、p760 为授权的新支付条款。
  - 相关定向回归：G12/G17/G04/G09、replace closure、operation closure、final validation 等 **179 passed**；完整 Python **1644 passed / 56 skipped / 3 warnings / 414.87s**。
- 状态：**已实施并在 D01/D04 真实合同上验证 complete；D01–D20 固定分母批量正在运行，尚未完成全部 20 份及 holdout**。这些结果不等于所有合同已通过，也不等于生产部署或正式用户交付完成。
- 下一步：完成 D01–D20 批量，逐份核对实际 DOCX/哈希/Claim Replay；按失败原因继续修复，冻结候选后再跑 holdout、部署和生产普通入口 E2E。
- 变更记录：2026-10-26 新增；所有修复均按规则/源文结构判断，没有按合同文件名或样本 ID 特判。
- 批量结果（2026-10-26，D01–D20 开发集，`var/recall-runs/real-20261026-dev20/`）：**5 complete / 14 incomplete / 1 stopped**，587 calls，约 $0.675。complete 为 D02/D04/D11/D16/D17；D15 因 `MODEL_SCHEMA_INVALID` 停止；其余为真实/验证阻塞。批量 D01 仅 1 条 G13 orphan 误报，与单独运行 D01c complete 不一致，说明 sweep 输出存在波动，不能把单次 complete 当稳定结论。
- 批量后修复：
  - G06 删除 prohibition sentence 的确定性执行（修复 D03/D08/D18 的 `RECALL_ROUTED_EXECUTOR_UNAVAILABLE`）。
  - G02/G04 缺失 operation 的类别操作重绑：源文已含实例化新类别组时生成 satisfied target，而非空 quote unresolved（修复 D03/D05/D10/D14 的一批 open G02/G04）。
  - G16 已满足 target 若只含“持有超过一年返还”尾句，重分类为 needs_edit 并用完整 G16 新文本替换尾句；公式行等不匹配尾句的 target 不重分类。
  - 模型非截断 schema/JSON 错误按 retries 重试；输出截断仍不重试。
  - 定向复跑：D03 修复后 **complete**（35 targets/20 edits/28 calls/$0.0273/166s）；D05 **complete**；D18 **complete**；D14 G16 已不再阻塞，但仍有 G01/G03/G08/G14 open；D10/D14 曾在 schema 错误处停止，D14 重跑恢复。
  - 修复后完整 Python 回归 **1649 passed / 56 skipped / 3 warnings / 411.35s**。
- 当前保守完成口径：D01 单独运行 complete、D02/D03/D04/D05/D11/D16/D17/D18 为已完成或定向复跑 complete；D06/D07/D08/D09/D10/D12/D13/D14/D19/D20 仍有阻塞。D01 批量结果未重跑前不并入稳定 complete。
- 剩余热点：G01/G03 append、G08/G11/G14 多操作/类组、G16 D20 合并保留原文、D09/D13 单类 FOF/单类债基的 class structure、D06 survey 短引文 orphan、D07/D12 大范围 audit/coverage。下一轮应先修这些共性原因，再整批复跑；不能只挑 complete 的合同宣称通过。
- 账本：隔离副本累计约 **29,400 requests / $24.60**（含批量及所有定向复跑），起始 28,328 / $23.380108；生产在线账本另计。

## FL-D341 共享模型账本并发等待无界与 429 重试过短（2026-10-26）

- 发现日期：2026-10-26，D04 真实运行。
- 问题与影响：`_budget_reserve_with_retry` 在共享账本并发已满时按 `lease_seconds*2` 等待，单次调用最长约 7 分钟；生产/测试 Worker 或法规 Worker 持有 `reserved` 时，评测会在每个模型调用上反复等待，首次 D04 运行 30 分钟未写出报告。模型 API 返回 429 时限流退避仅 1–2 秒，重试 1 次即耗尽，D04 第二次运行直接 `MODEL_RETRY_EXHAUSTED`。
- 处理方法：并发等待改为最多 30 秒（lease 更短时取 lease）；`MODEL_CONCURRENCY_LIMIT`、`MODEL_RESERVATION_EXPIRED` 进入 RecallPipeline `STOP_CODES`，由 Worker/评测按暂停/重试路径处理，不再静默返回 `not_generated`；429 读取 `Retry-After`，否则按 5/10/20 秒指数退避，评测显式 `FUNDLEX_MODEL_RETRIES=3`。
- 证据与验证：修复后 D04 从 30 分钟超时降至 145–417 秒完成；限流重试回归 `tests/test_model.py` **22 passed**，并发等待有界回归通过。评测使用生产账本的独立副本（起始 28,328 requests / $23.380108），避免与在线 Worker 抢锁；当前副本约 28,558 requests / $23.64，费用按副本账本记录，原生产账本仍由在线服务单独记账。
- 状态：**已实施并用于真实 D04/D01 运行**。生产 Worker 的 429 路径要随候选发布后生效；本轮尚未部署。
- 下一步：候选发布后观察生产 Worker 的 429/并发暂停、恢复和报告持久化；不把评测账本副本与生产账本混为同一余额。
- 变更记录：2026-10-26 新增；用户已明确模型预算不设旧上限，本条不恢复旧 2000/$2 cap，也不隐藏真实调用费用。

## FL-D339 pytest 同名测试文件导致全量收集中断（2026-10-26）

- 发现日期：2026-10-26，完整 Python 回归收集阶段。
- 问题与影响：并行法规指引工作新增 `tests/test_guide_generation.py` 和 `tests/browser/test_guide_generation.py`，两个文件没有包隔离且模块名相同。pytest 默认 prepend 导入模式下先导入前者，收集后者时报 `import file mismatch`，全量回归直接以 collection error 退出，无法得到验证结果。
- 证据：`PYTHONPATH=. .venv/bin/pytest -q` 报错 `imported module 'test_guide_generation' ... tests/browser/test_guide_generation.py`；`tests/browser` 原无 `__init__.py`，`tests` 根也没有包标记。
- 处理方法：新增 `tests/browser/__init__.py` 使浏览器测试成为独立包命名空间，不改动并行测试文件内容、不删除任何用例。根 tests 继续使用现有顶层导入方式，避免破坏 `from test_recall_core import ...` 等既有测试依赖。
- 状态与验证：**已实施并通过全量收集**。修复后完整 Python 为 **1637 passed / 56 skipped / 3 warnings / 413.76s**；完整浏览器套件 **43 passed**；未部署、未调用模型。
- 下一步：新增长期测试文件时避免在不同目录复用相同 basename；若后续需要重命名文件，保留旧路径历史并单独提交，不与产品代码混提。
- 变更记录：2026-10-26 新增；本条只解决测试收集隔离，不代表并行法规功能本身验收状态变化。

## FL-D338 法规候选版本未绑定不可变内容且人工下载缺少认证头（2026-10-26）

- 发现日期：2026-10-26，法规候选 API、Store 与前端工作流审查。
- 问题与影响：流水线原先只写 `gg_guide_items` 和可替换的当前产物，候选版本表没有绑定实际指南内容；人工编辑可能覆盖当前 DOCX，审批/发布没有 HTTP 工作流；页面普通下载链接在密码模式下不会携带 Bearer token，用户不能可靠下载受保护产物。
- 证据：`fundlex/guide_generation/pipeline.py` 原完成阶段未创建 `candidate_ready` 内容快照；`human.py` 原只更新当前 `guide` artifact；`api.py` 原无候选查询/审批/发布路由；`frontend/guide_generation.js` 原使用普通 `<a href>` 下载。
- 处理方法：完成阶段创建带 source/regulation hash、GuideItem 快照、artifact key/sha/size 的不可变候选版本；人工编辑在候选锁和 expected current version 下创建新的 `human_draft` 版本，人工文件使用唯一对象名；审批仅允许 `candidate_ready`/`human_draft`，发布必须先 approved，published 版本禁止继续编辑；候选发布返回 `runtime_guide_import=not_requested`，不越过正式运行时指引发布；前端所有法规产物下载改为带当前开发身份或 Bearer token 的 fetch。
- 状态与验证：**已实施并通过离线及临时密码账号浏览器验证**。法规套件 `tests/test_guide_generation.py`、`tests/test_guide_generation_pipeline.py`、`tests/test_guide_api.py` 及新增持久化边界覆盖共 **21 passed / 1 warning**；覆盖候选版本链、owner 隔离、审批→发布、发布后编辑拒绝、artifact SHA/size、Worker fencing 和人工 DOCX/Evidence 下载。`FUNDLEX_BROWSER_TESTS=1 PYTHONPATH=. .venv/bin/pytest -q tests/browser/test_guide_generation.py` 为 **1 passed / 9.01s**，源证据为 [`tests/browser/test_guide_generation.py`](../tests/browser/test_guide_generation.py)：密码登录后上传法规、真实候选队列/Worker、人工编辑、批准、发布、发布后按钮锁定、认证下载均通过；同一产物无认证请求返回 401。`uv lock --check`、隔离 Python 3.11 clean sync/PyMuPDF import、`py_compile`、`compileall`、`node --check`、`git diff --check` 均通过。该浏览器测试仍使用 FakeGuideRouter，未证明真实模型语义质量，也未部署生产。
- 下一步：在预算、labels/gold 和正式发布条件满足后，以冻结候选完成真实模型资格与运行时导入门禁；候选内容仍需独立正式运行时指引导入，不因候选发布状态自动成为当前运行时指引。

## FL-D336 法规要求引文失效时文章处置会掩盖覆盖缺口（2026-10-26）

- 发现日期：2026-10-26，模型伪造 source quote 的要求抽取回归。
- 问题与影响：模型返回无法绑定法规原文的引文时，文章级 `modify_contract` disposition 原先会让覆盖门认为文章已有去向，未生成 `unresolved_article` 保留要求和 critical finding，可能把无证据的要求误报为已处理。
- 证据：`tests/test_guide_generation.py::test_requirement_extraction_quote_validation` 用模型返回“这是模型编造的法规原文”复现；修复前 `unresolved_article` 断言失败。
- 处理方法：文章没有有效原子要求时，只有明确 `no_contract_change` 或 `out_of_contract_scope` 才可关闭文章；`modify_contract`/其他处置继续进入补漏，补漏失败保留 `uncertain` 的 `unresolved_article` 和 critical `requirement_coverage` finding。
- 状态与验证：**已实施并通过离线验证**；法规套件 **19 passed / 1 warning**。真实监管文件和真实模型复核仍待预算与资格条件满足后执行。

## FL-D337 依赖锁检查工具不在当前工作机 PATH（2026-10-26）

- 发现日期：2026-10-26，法规模块收尾验证。
- 问题与影响：工作区已修改 `pyproject.toml`/`uv.lock` 声明 PyMuPDF，但当前工作机执行 `uv lock --check` 返回 `/bin/bash: uv: command not found`，因此本轮无法用 uv 命令重新确认锁文件生成一致性。
- 证据：`.venv/bin/python` 可导入 `pymupdf`；`uv.lock` 已包含 `pymupdf` 1.28.2 package 及项目依赖项；`compileall` 和 19 项法规套件通过；但系统 PATH 没有 `uv`。
- 处理方法：保留现有锁文件变更并以 Python import/compile 和法规测试验证当前环境；不宣称 clean-install 已验证。
- 状态与验证：**已验证**。当前项目虚拟环境提供 `.venv/bin/uv`（uv 0.13.5）；`.venv/bin/uv lock --check` 通过。使用 `UV_PROJECT_ENVIRONMENT=/tmp/opencode/fundlex-uv-clean-env .venv/bin/uv sync --project /home/opencode/fundlex --python 3.11 --no-install-project` 创建隔离环境并成功安装锁定依赖，随后 `/tmp/opencode/fundlex-uv-clean-env/bin/python` 导入 `pymupdf`（1.28.2）及 `fundlex.guide_generation.pipeline/api` 通过。该验证覆盖 Linux clean sync 与 PDF 依赖，不等于生产部署验证。
- 下一步：依赖锁和当前 Linux clean sync 已闭合；后续依赖变更需重新运行同一检查。生产发布仍需独立候选冻结、部署和真实用户路径验证。

## FL-D334 法规候选流水线包导入路径错误与 PDF 依赖未声明（2026-10-26）

- 发现日期：2026-10-26，法规候选模块完整 import 检查。
- 问题与影响：候选流水线曾使用不存在的 `fundlex.guide_generation.regulatory` 相对导入，导致 py_compile 通过而流水线运行时 import 失败。当前环境虽可导入 PyMuPDF，`pyproject.toml` 未声明该依赖，清洁安装无法据此保证 PDF 候选法规可处理。
- 证据：首次执行 `.venv/bin/python -m compileall -q fundlex/regulatory fundlex/guide_generation` 无输出；逐模块 import 时除 pipeline 外均通过，pipeline 报 `ModuleNotFoundError: No module named 'fundlex.guide_generation.regulatory'`。`fundlex/regulatory/pdf_parser.py` 直接导入 `fitz`，而项目依赖列表未包含 PyMuPDF。当前源码已显示为 `from ..regulatory.ingestion import ...`，说明导入修复已在工作区存在。
- 处理方法：保留并核验 `pipeline.py` 的父级导入路径；下一步在项目依赖中加入与当前环境兼容的 PyMuPDF 版本约束，并执行隔离清洁安装验证。
- 状态与验证：导入路径修复已实施，完整 import、离线 DOCX/PDF 流程和清洁安装仍待验证；本条不代表法规候选链路已完成。
- 下一步：重新执行全部新模块 import，补 focused tests，确认 API/Worker 使用相同依赖；在依赖变更后重新跑项目回归。

## 当前工作区验证补录（2026-10-26）

- 当前分支：`refactor/backend-engine-finalization`，HEAD `18093fa`，相对 `origin/refactor/backend-engine-finalization` ahead 35；工作区保留既有用户 dirty 修改及本轮 Engine/Replay 修复，尚未 push 或部署。
- 本轮已提交的代码块：`0466712`（API 稳定错误码、损坏报告边界、Review/下载响应）、`cdf0699`（V1/V2 任务状态、通知、暂停按钮、Feishu 状态卡片及设置入口）、`03eb30d`（Feishu OAuth/store 与测试）和 `75925d4`（文档与审计记录）。
- 最新完整 Python 回归：**1599 passed / 52 skipped / 3 warnings / 381.29s**；本轮新增 G03/G18、Replay/site 定向回归合计 **167 passed**；`.venv/bin/python -m py_compile`、`git diff --check` 通过。前端与浏览器数字沿用其各自已记录的候选证据，未因本轮后端回归重新宣称通过。
- 项目级结论仍为 **NO-GO**：D01–D20 固定分母、holdout、G06 授权、Compare 完整结构、真实 MySQL 8 并发、真实 OAuth 回调和完整真实用户交付仍未闭合。下述局部通过不改变该结论。

### 本轮后端回归补录（2026-10-26）

- 唯一 source quote 绑定现在对真实 `DocumentInspection` 要求当前物理段内唯一、完整句子边界、未跨 `BARRIER`、落在单一可编辑 segment；Word 空格、零宽字符和句末分隔符差异允许通过。短 survey 命中先扩展到真实句子再绑定，重复 occurrence、句中 prefix、受保护段和跨 segment 继续拒绝。历史只提供 `text` 的轻量 fixture 保留兼容解析，不改变真实 DOCX 门禁。
- Claim Replay/effects 的轻量 fixture 兼容回归恢复；Replay/site、effects、final-validation 相关套件 **221 passed**，扩大定向套件 **393 passed / 1 warning**。`.venv/bin/python -m py_compile` 与 `git diff --check` 通过。本轮未调用真实模型、未部署。
- Worker 对 `MODEL_REPLAY_MISS`、`MODEL_CHECKPOINT_UNAVAILABLE`、`MODEL_CASSETTE_UNAVAILABLE` 的 retry 报告保留 `verification_status=verification_blocked`、阻塞阶段和上下文证据，并暂停任务等待恢复；新增 Worker 持久化回归。任务/存储套件 **64 passed / 7 skipped / 1 warning**。
- 状态：**代码已实施并通过离线回归；真实 Worker/model、普通默认入口和最终 DOCX 交付仍未复验**。项目 NO-GO、预算和历史失败分母保持不变。

## FL-D332 严格 source quote 校验与旧轻量回放 fixture、短 survey 引文不兼容（2026-10-26）

- 发现日期：2026-10-26，唯一 source proof 回归及 Replay/site 定向测试。
- 问题与影响：新增严格 source quote 解析最初无条件读取 `span.segments`，使只提供 `text/location` 的 Claim Replay/effects fixture 触发属性错误；同时 survey 的语义判断可能只返回真实政策句的短 excerpt，直接按完整引文绑定会把已满足站点错误标为 unresolved。若放松到任意最长句或第一 occurrence，又会重新允许重复站点、句中 prefix 或 sibling 借证。
- 证据：严格改动后的定向回归首次为 **230 passed / 39 failed**；首个堆栈为 `fundlex/recall.py:307` 的 `SimpleNamespace.segments` 缺失，G18 satisfied survey 目标为空。修正后 Replay/site、effects、final-validation 相关套件 **221 passed**，扩大定向套件 **393 passed / 1 warning**。
- 处理方法：真实 `DocumentInspection` 继续要求 source quote 在当前物理段内唯一、完整句子边界、未跨 `BARRIER` 且包含于单一可编辑 segment；空格、零宽字符和终止分隔符差异可归一化。短 survey excerpt 只有在 source 中唯一匹配时才扩展到实际句子边界后重新严格绑定；重复 occurrence、句中 prefix、受保护段和跨 segment 返回 unresolved。缺少 `segments` 的旧轻量 fixture 保留普通解析兼容路径，不改变真实 DOCX 校验。
- 状态与验证：**已实施并通过离线代码回归；真实合同、Worker/model 和最终交付未复验**。`.venv/bin/python -m py_compile`、`git diff --check` 已通过；未调用真实模型、未部署。
- 下一步：预算、labels/gold 和候选发布条件满足后，重跑真实 D04/D01，核对 source offsets、Claim Replay、最终 DOCX、报告和授权下载；保持真实残留和错误物理站点 fail closed。
- 变更记录：2026-10-26 新增；与 FL-D309/FL-D310 的真实站点归因相关，但本条专门记录 source quote 解析兼容性和 survey excerpt 边界。

## FL-D333 Worker retry 未持久化验证阻塞报告（2026-10-26）

- 发现日期：2026-10-26，`verification_blocked` Worker/Store 契约复核。
- 问题与影响：RecallPipeline 已将 checkpoint/replay/预算阻塞写入报告，但 Worker 处理“报告自带可重试错误码”的路径只传 `error_code` 给 `retry`，会丢失阻塞阶段、上下文 SHA 和用户可见验证状态；checkpoint/replay 缺失也没有统一暂停任务。
- 证据：`fundlex/jobs.py` 的报告 retry 分支原先调用 `store.retry(..., error_code=...)`；新增回归构造 `MODEL_REPLAY_MISS` 报告，核对 `documents.report_json`、`verification_blockers[0].stage`、retry_wait 和 task paused 状态。
- 处理方法：retry 接受可选报告并在非终态保留 JSON；报告自带错误码路径传入完整报告；`MODEL_REPLAY_MISS`、`MODEL_CHECKPOINT_UNAVAILABLE`、`MODEL_CASSETTE_UNAVAILABLE` 与预算/ledger stop 同属暂停集合。任务仍保持非正式完成状态，恢复后继续处理。
- 状态与验证：**已实施并通过离线回归**。任务/存储套件 **64 passed / 7 skipped / 1 warning**，扩大定向套件 **393 passed / 1 warning**；真实 Worker/model 恢复链路和生产部署未验证。
- 下一步：候选发布后通过普通工作台真实 checkpoint/model 路径核对暂停、恢复、报告和下载门禁；没有新预算授权前不启动真实模型调用。
- 变更记录：2026-10-26 新增；不改变 FL-D304 的历史预算 cap 或项目 NO-GO 结论。

## FL-D312 V1 Review 第二次生成未提交选择版本校验字段（2026-10-26）

- 发现日期：2026-10-26，V1 前后端契约审查及隔离 API/浏览器复现。
- 问题与影响：V1 Review 的“生成选择版”和“一键接受全部”请求没有提交当前 `selection_epoch`、`manifest_hash`。首次生成通常成功；同一合同再次修改选择或再次生成时，后端会因已有选择版本返回 `SELECTION_EPOCH_REQUIRED`，用户无法从页面完成第二次选择版生成。
- 证据：`frontend/app.js:519-533` 的请求 body 只有 `decisions`，accept-all 没有 body；`fundlex/api.py:603-617` 在当前 epoch 非零且未提供 expected epoch 时明确抛出该冲突。隔离真实 DOCX fixture 对 `decisions` 和 `accept-all` 各执行两次，均为首次 200、第二次 409；浏览器夹具同时记录请求缺少两个字段。
- 处理方法：打开 Review 时保存服务端返回的 `selection_epoch` 和 `manifest_hash`，生成请求原样提交；成功后用响应的新版本更新本地状态；遇到 epoch/manifest 冲突时重新读取 Review，而不是把旧选择继续提交。保留服务端 fail-closed 并发保护。
- 状态与验证：**已确认，待修复**。隔离 API 复现 2 个参数化用例通过，浏览器复现通过；本轮未修改产品源码、未调用模型或部署。
- 下一步：修复 V1 选择请求和 Review 状态，再覆盖首次生成、重复生成、并发冲突、accept-all、下载文件哈希和实际选择结果。
- 变更记录：2026-10-26 新增；与 FL-D103/选择并发版本设计相关，但本条专门记录 V1 客户端未传版本字段。

## FL-D313 V1 修改密码的错误旧密码被识别为会话失效（2026-10-26）

- 发现日期：2026-10-26，V1 密码操作契约审查及隔离浏览器复现。
- 问题与影响：用户输入错误旧密码时，服务端返回 401，但稳定错误码被统一映射为 `AUTHENTICATION_REQUIRED`。V1 前端无法区分“当前密码不正确”和“登录会话失效”，会清除本地 token、关闭密码窗口并跳转登录，用户被不必要地登出。
- 证据：`fundlex/api.py:760-768` 为错误旧密码抛出文本 `current password is incorrect`；`fundlex/api_errors.py:60-67` 对该文本回退为 `AUTHENTICATION_REQUIRED`；V1 `frontend/app.js:581` 只比较原始英文 detail。隔离浏览器提交错误旧密码得到 401/detail `AUTHENTICATION_REQUIRED`，页面跳到登录且 sessionStorage token 被清除；同一 token 直接请求 `/api/auth/me` 仍为 200。
- 处理方法：为错误旧密码定义稳定的非认证错误码和用户提示，前端只对真正的会话失效执行登出；增加 API 与浏览器回归，确保修改成功仍撤销其他会话。
- 状态与验证：**已确认，待修复**。隔离浏览器复现通过，服务端会话存活证据通过；未修改产品源码。
- 下一步：修复错误码映射及 V1 错误分支，覆盖错误旧密码、过期 token、账号禁用和成功修改密码。
- 变更记录：2026-10-26 新增；与通用 401 会话处理相关，但不属于权限绕过。

## FL-D314 V1 身份切换后残留旧飞书 OAuth 状态并继续轮询（2026-10-26）

- 发现日期：2026-10-26，V1 OAuth 状态清理审查及隔离浏览器复现。
- 问题与影响：退出、换账号或开发身份切换后，旧账号的二维码、授权链接、提示文字和绑定轮询仍保留在页面；轮询可能继续请求绑定接口。用户可能把旧账号 OAuth 流程误认为当前账号流程，产生错误绑定认知。现有证据未证明服务端发生跨账号授权绕过。
- 证据：`frontend/app.js:212` 将定时器保存在 `feishuOAuthTimer`，`frontend/app.js:573-578` 的 `resetWorkspace()`/logout 没有清理该定时器和 OAuth DOM。隔离浏览器在 A 账号生成占位二维码后退出并登录 B 账号，旧 code、旧授权 href 和面板仍可见；退出后 2.8 秒内仍发生绑定请求。
- 处理方法：把 OAuth 轮询纳入身份 epoch，统一清理 timer、二维码、链接、消息和面板；新账号进入设置后重新读取绑定状态；轮询请求必须携带创建它的身份/流程令牌并忽略旧响应。
- 状态与验证：**已确认，待修复**。隔离 OAuth 复现通过；未访问真实飞书、未调用模型、未部署。
- 下一步：修复后覆盖退出、登录另一账号、开发身份切换、网络延迟和绑定成功等路径，确认旧请求不能更新新身份界面。
- 变更记录：2026-10-26 新增；与 FL-D291 设置入口、FL-D295 OAuth 功能实现和 FL-D300 二维码显示问题独立。

## FL-D315 V1 任务状态筛选缺少失败终态（2026-10-26）

- 发现日期：2026-10-26，V1 页面与任务 API 契约审查。
- 问题与影响：后端已经产生并支持筛选 `failed`、`completed_with_exceptions`，V1 任务状态下拉框只有上传中、排队中、处理中、已暂停和处理完成。用户不能从任务列表直接筛选失败关闭或含异常的终态任务。
- 证据：`frontend/compare.html:18` 的 `#task-filter` 缺少两个 option；`fundlex/tasks.py:216-219,294-297` 生成并处理这两个状态；前端 `labels` 虽有对应文案，但没有筛选入口。该项与已解决的 V2 FL-D299 不重复，页面实现属于 V1 原生工作台。
- 处理方法：补充两个筛选选项并保持 API 状态值、标签、排序和筛选 chips 一致；增加全成功、混合异常、全失败三种任务列表回归。
- 状态与验证：**已确认，待修复**。源码契约证据充分；V1 浏览器主回归 30 项通过，但未覆盖这两个缺失选项。
- 下一步：补选项并执行 V1 定向浏览器回归，确认筛选请求和空结果提示正确。
- 变更记录：2026-10-26 新增；V2 同类历史问题 FL-D299 已解决，不作为本条的替代证据。

## FL-D316 V1 Compare 刷新后无法恢复未封存上传任务（2026-10-26）

- 发现日期：2026-10-26，V1 Compare 恢复能力审查。
- 问题与影响：Compare 上传草稿和浏览器 `File` 对象只保存在内存。刷新页面后任务仍可从 `/api/compare/tasks` 读取，但 V1 页面没有针对 `uploading` 任务重新选择文件、继续上传并 seal 的入口；已上传文件被保留，用户仍需重新创建任务才能从正常页面完成流程。
- 证据：`frontend/compare.js:6,23,51-73,120,128`；`showCreate()` 和身份重置清空 `state.uploadDraft`，`openTask()` 对未完成任务只显示状态，不构造恢复 manifest 或文件选择流程。该问题与 V2 旧闭包 refetch 的 FL-D293 不同。
- 补充复现：隔离 Compare 浏览器在上传请求返回 503 后显示“继续上传”；点击“新建对比任务”后草稿消失；刷新后从历史任务打开原任务只显示“上传中 · 1 组”，创建区隐藏，无法重新选择缺失文件、补传或 seal。
- 处理方法：为服务端未封存任务提供可恢复 manifest 和继续上传入口；刷新后要求用户重新选择本地文件，按 `client_id`、名称和大小匹配已上传项，继续未完成组并最终 seal；无法安全匹配时 fail closed。
- 状态与验证：**已确认，待修复**。源码契约证据充分；未创建真实 Compare 任务或调用模型。
- 下一步：增加刷新后恢复、部分上传、失败重传、跨身份隔离和 seal 失败回退的 V1 浏览器/API 回归。
- 变更记录：2026-10-26 新增；Compare 既有完整性和视觉问题仍按 FL-D176/FL-D177 记录。

## FL-D317 V1 Review 决策只保存在内存，重开默认接受全部（2026-10-26）

- 发现日期：2026-10-26，V1 Review 前后端契约审查及隔离浏览器复现。
- 问题与影响：用户拒绝的修订只写入 `state.reviewDecisions`；刷新、重新进入任务或重新打开合同后，V1 没有读取服务端已发布决策，`chosen` 默认为空，界面把所有修订显示为接受。用户可能在第二次生成时误发布与上次选择不同的合同。
- 证据：`frontend/app.js:396,488-501,573`；后端 `fundlex/api.py:587-602` 的 revisions 响应只提供 epoch、manifest 和 hash，不提供每条决策。隔离浏览器拒绝第 1 条后关闭并重新打开，复现复选框恢复为接受；同一复现还显示第二次请求缺失版本字段并返回 409。
- 处理方法：让服务端返回当前选择版本的逐条决策，或由前端可靠保存并校验版本绑定的决策快照；打开 Review 时恢复实际状态，选择变化后提交当前 epoch/manifest，冲突时重新读取并提示用户。
- 状态与验证：**已确认，待修复**。隔离浏览器复现通过；未修改源码。
- 下一步：先确定服务端决策持久化契约，再覆盖刷新、重开、跨合同切换、冲突和 selected artifact 内容核对。
- 变更记录：2026-10-26 新增；与 React V2 FL-D244 的 Review 刷新问题相似，但本条仅针对 V1 原生 Review。

## FL-D318 V1 URL 前缀部署会丢失静态资源缓存头（2026-10-26）

- 发现日期：2026-10-26，V1 发布/缓存审查。
- 问题与影响：配置 `FUNDLEX_FRONTEND_BASE_PATH=/test` 后，静态资源请求先被前缀中间件剥离，缓存中间件判断的是剥离后的路径，导致 `/test/static/*` 没有预期的长期缓存头；根路径同一资源则返回 `public, max-age=31536000, immutable`。前缀部署与根路径部署缓存行为不一致。
- 证据：`fundlex/api.py:69-86,1471-1480`；隔离 TestClient 对根路径 `/static/app.js` 得到 immutable，对 `/test/static/app.js`、`compare.js` 和 logo 得到 200 但无 `Cache-Control`。
- 处理方法：缓存判断使用原始外部路径或响应资源类型，并为前缀部署增加静态资源头回归；入口 HTML 继续 no-store。
- 状态与验证：**已确认，待修复**。隔离 API 复现通过；不影响当前页面加载，但影响代理/测试部署缓存策略。本轮未部署。
- 下一步：修复后验证 `/static`、`/test/static`、`/assets`、入口 HTML 和错误响应的缓存头。
- 变更记录：2026-10-26 新增；FL-D092 已解决根路径脚本样式无版本缓存问题，本条是前缀中间件边界。

## FL-D319 V1 图片固定 URL 使用一年 immutable 缓存但没有内容版本号（2026-10-26）

- 发现日期：2026-10-26，V1 静态资源版本化审查。
- 问题与影响：V1 HTML 固定引用 `gf-logo-mark.png` 和 `gf-favicon.png`，静态中间件却对全部 `/static/*` 下发一年 `immutable`。替换同名图片后，浏览器或 CDN 可继续使用旧内容，导致图片发布无法可靠生效。
- 证据：`frontend/compare.html:7,12` 使用固定图片路径；`fundlex/api.py:1409-1411` 的 `_asset_version()` 只覆盖 CSS/JS；`fundlex/api.py:1475-1477` 对图片也设置 immutable。隔离 API 复现确认固定 URL 与一年 immutable 头。
- 处理方法：给图片引用加入内容 hash/query 版本，或对未版本化图片使用较短/可重新验证的缓存策略；补图片替换后的 URL/响应缓存回归。
- 状态与验证：**已确认，待修复**。隔离入口/静态资源复现通过；未替换生产图片、未部署。
- 下一步：统一 V1 图片与脚本样式的版本策略，并验证前缀 URL 组合。
- 变更记录：2026-10-26 新增；与 FL-D092 的脚本样式版本化问题相关但不重复。

## FL-D320 V1 过期 OAuth 二维码仍显示可用并继续轮询（2026-10-26）

- 发现日期：2026-10-26，V1 OAuth 生命周期审查及隔离浏览器复现。
- 问题与影响：OAuth start 返回已过期的 `expires_at` 后，V1 仍显示二维码和“1 分钟内有效”，并启动绑定状态轮询；过期后仍持续请求，用户可能继续扫描无效二维码，页面也没有明确要求重新生成。
- 证据：`frontend/app.js:212` 仅把时间差格式化为至少 1 分钟，没有 expiry guard 或到期清理。隔离浏览器用已过期占位响应复现：2.8 秒内仍出现 binding 请求，二维码链接仍可见，提示仍为“1 分钟内有效”。
- 处理方法：收到结果后立即检查 `expires_at`；已过期时隐藏/清理二维码和授权链接并提示重新生成；轮询按 deadline 设置一次性停止计时器，绑定成功或身份变化也统一清理。
- 状态与验证：**已确认，待修复**。隔离浏览器复现通过；未访问真实飞书。
- 下一步：覆盖正常倒计时、刚过期、后台恢复、绑定成功和服务端拒绝过期 state。
- 变更记录：2026-10-26 新增；与 FL-D300 二维码清晰度和 FL-D295 OAuth 功能实现独立。

## FL-D321 V1 帮助弹窗焦点可逃逸出 aria-modal 对话框（2026-10-26）

- 发现日期：2026-10-26，V1 键盘/无障碍审查及隔离浏览器复现。
- 问题与影响：帮助弹窗声明 `role="dialog" aria-modal="true"`，但只处理 Escape，没有 Tab/Shift+Tab 焦点循环。键盘用户可在弹窗保持打开时把焦点移到背景页面，实际交互与对话框语义不一致。
- 证据：`frontend/compare.html:49`、`frontend/app.js:154,668`；打开帮助后按 `Shift+Tab`，焦点离开 `#help-overlay`，隔离证据为 `insideDialog=false`。
- 处理方法：为 V1 帮助弹窗增加双向焦点循环、Escape 关闭和关闭后焦点恢复；打开期间保持背景 inert，并覆盖无可聚焦内容的边界。
- 状态与验证：**已确认，待修复**。隔离浏览器复现通过；V2 历史 FL-D253 已解决，不改变 V1 当前状态。
- 下一步：补 V1 键盘回归并检查帮助弹窗在登录页、窄屏和动态内容下的焦点顺序。
- 变更记录：2026-10-26 新增；仅记录 V1 `compare.html`/`app.js`，不把 V2 条目重复计入。

## FL-D322 V1 修改密码弹窗缺少对话框和焦点管理语义（2026-10-26）

- 发现日期：2026-10-26，V1 键盘/无障碍审查。
- 问题与影响：修改密码 overlay/form 没有 `role="dialog" aria-modal="true"`，没有焦点循环，关闭后也不恢复到“修改密码”按钮。键盘用户可把焦点移到背景或 body，且屏幕阅读器无法获得完整对话框语义。
- 证据：`frontend/compare.html:48`、`frontend/app.js:579-581,670`；隔离浏览器打开后按 `Shift+Tab` 焦点落到 body，关闭后焦点仍不在 `#password-btn`，对话框 role 数为 0。
- 处理方法：使用明确的 dialog 容器和标签，打开时保存触发按钮并聚焦首个输入，限制 Tab/Shift+Tab，Escape/取消关闭并恢复焦点；保留背景 inert。
- 状态与验证：**已确认，待修复**。隔离浏览器复现通过；本轮未改源码。
- 下一步：补 V1 修改密码键盘/读屏语义回归，并结合 FL-D313 验证错误输入后的焦点和提示。
- 变更记录：2026-10-26 新增；V2 历史 Review/弹窗审查不作为本条证据。

## FL-D323 V1 Compare 覆盖不完整警告的样式选择器未命中（2026-10-26）

- 发现日期：2026-10-26，V1 Compare UI/响应式审查。
- 问题与影响：Compare JS 给 `#compare-coverage` 设置的 class 是 `is-incomplete`，CSS 却要求 `.compare-coverage.is-incomplete`；元素本身没有 `compare-coverage` class。因此覆盖不完整警告没有边框、背景、内边距和断词样式，移动端长原因码可能难以阅读。
- 证据：`frontend/compare.js:118`、`frontend/compare.css:11,31`；隔离 DOM computed style 为 `className=is-incomplete`、`border=0px`、`padding=0px`、`overflowWrap=normal`。
- 处理方法：统一 id/class 选择器并补覆盖警告的视觉与长标识回归，确保文字警告不只依赖颜色。
- 状态与验证：**已确认，待修复**。隔离 UI 复现通过；与 FL-D255 的 V2 历史/已发布样式问题区分。
- 下一步：修复后在 390px、768px 和桌面宽度检查警告样式、断词和页面横向溢出。
- 变更记录：2026-10-26 新增；未创建 Compare 真实任务或调用模型。

## FL-D324 V1 Compare 文件夹选择入口无法通过键盘聚焦（2026-10-26）

- 发现日期：2026-10-26，V1 Compare 无障碍审查。
- 问题与影响：文件夹 input 使用 `hidden`，外层 label 只是鼠标可点击容器，没有可聚焦控件语义。键盘用户无法到达“选择原版文件夹”和“选择对比版文件夹”，不能使用按相对路径批量配对功能。
- 证据：`frontend/compare.html:24` 的两个 input 均为 `hidden`；外层 label 没有 tabindex/按钮语义；`frontend/compare.js:126` 只监听 change。隔离 DOM 证据为 input hidden、label tabindex 为 -1，连续 Tab 无法聚焦入口。
- 处理方法：使用可聚焦 button/label 代理并把激活转发到文件夹 input，保留 input 的原生文件选择语义和键盘激活；补键盘选择与配对回归。
- 状态与验证：**已确认，待修复**。隔离 UI 复现通过；未修改源码。
- 下一步：修复后覆盖 Tab、Enter/Space、取消选择、左右文件夹配对和未配对提示。
- 变更记录：2026-10-26 新增；V1 Compare 保留在本轮范围，V2 不纳入分母。

## FL-D325 V1 合同证据引文只能鼠标展开（2026-10-26）

- 发现日期：2026-10-26，V1 Review/证据区无障碍审查。
- 问题与影响：合同证据引文默认四行截断，点击才切换 `.expanded`；元素没有 tabindex、role 或 aria-expanded。键盘用户和屏幕阅读器用户无法通过正常焦点操作展开并查看完整引文。
- 证据：`frontend/app.js:320` 生成 `.evidence.quote`，`frontend/app.js:668` 只处理鼠标 click；隔离 DOM 证据为 tabindex、role、aria-expanded 均缺失。
- 处理方法：使用 button/details 等键盘原生语义，或补 tabindex、键盘事件和 aria-expanded/controls；展开状态应对读屏可见，并保留长文本换行。
- 状态与验证：**已确认，待修复**。无障碍隔离复现通过；Compare HTML 转义和 CSV 转义在同轮审查中未发现可确认缺陷。
- 下一步：补证据引文的 Tab、Enter/Space、读屏属性和窄屏回归，确保完整原文可访问。
- 变更记录：2026-10-26 新增；本条只涉及 V1 证据呈现，不改变报告内容或合同引擎逻辑。

## FL-D326 V1 无产物失败任务仍启用 ZIP 下载按钮（2026-10-26）

- 发现日期：2026-10-26，V1 任务结果下载契约复核及隔离浏览器/API 复现。
- 问题与影响：V1 根据 `completed + rejected > 0` 启用“下载全部结果 ZIP”。后端 `completed` 包含处理失败文档，因此失败且没有任何可下载产物的任务也会显示可下载；用户点击后只能得到 409，页面没有在点击前说明没有可下载结果。
- 证据：`frontend/app.js:205` 使用 `t.completed` 和 `t.rejected`，没有使用任务摘要提供的 `downloadable_count`；`fundlex/tasks.py:250` 暴露下载数量，`fundlex/api.py:1194` 对无产物 ZIP 返回冲突。隔离构造一份失败且无产物的任务后，按钮可点击，下载请求返回 `409 / CONFLICT`。
- 处理方法：以实际可下载产物数量作为按钮门禁；数量为零时禁用按钮并显示“暂无可下载结果”及失败/未生成原因。增加全失败无产物、部分有产物和含例外产物三种回归。
- 状态与验证：**已确认，待修复**。隔离浏览器结合 API 复现通过；未创建生产任务、未调用模型或部署。
- 下一步：修复 V1 下载按钮条件和提示，核对 ZIP 内容、报告下载与跨账号授权边界。
- 变更记录：2026-10-26 新增；与 React V2 的下载门禁背景不同，本条仅记录 V1 `app.js` 与任务摘要契约未接通。

## FL-D327 V1 Compare 移动端点击右侧差异不会切换阅读栏（2026-10-26）

- 发现日期：2026-10-26，V1 Compare 移动端交互复核。
- 问题与影响：移动端默认只显示原版栏；点击仅存在于对比版的新增差异时，`focusDiff()` 只滚动两侧 pane，不更新 `data-mobile-side`。右栏仍被 CSS 隐藏，用户看不到刚定位的差异，必须再手动点击“查看对比版”。
- 证据：`frontend/compare.js:115` 的 `focusDiff()` 没有切换移动阅读侧；`frontend/compare.js:123` 只在显式点击两侧按钮时设置 `data-mobile-side`；`frontend/compare.css:12` 在移动端按该属性隐藏另一栏。隔离 390px DOM 夹具点击右侧独有差异后，左栏仍可见、右栏和目标标记隐藏、对比版按钮未激活。
- 处理方法：在移动端 `focusDiff()` 根据差异标记所在侧自动切换 `data-mobile-side`，同步更新两个切换按钮的 active/ARIA 状态；保留用户手动切换和桌面双栏行为。
- 状态与验证：**已确认，待修复**。隔离移动端交互复现通过；未创建生产 Compare 任务或调用模型。
- 下一步：补右侧新增、左侧删除、两侧修改三类差异的 390px 回归，并确认差异导航、键盘定位和手动切换不会互相覆盖。
- 变更记录：2026-10-26 新增；与 V2 移动定位历史问题区分，V1 Compare 仍属于本轮审查范围。

## FL-D328 V1 Compare 任务列表、创建表单和结果阅读器堆叠在同一页面（2026-10-26）

- 发现日期：2026-10-26，V1 Compare 信息架构审查。
- 问题与影响：`frontend/compare.html:23-26` 在同一个 `#view-compare` 中连续放置任务列表、新建任务表单、任务结果/合同组选择和差异阅读器。用户从任务列表进入结果时，其他工作流区域仍属于同一页面结构；创建任务时也会保留任务列表上下文，导致页面纵向过长、当前任务边界不清晰，长文阅读时容易失去上下文。
- 证据：Compare 视图在源码中只有一个 section；`compare.js:23,43-48,117-120` 通过 hidden 属性切换部分内容，但没有独立的创建态、结果态或阅读态路由/页面边界。已有 Review 采用 `review-layout` 将正文和清单组织在一个明确的审查上下文中，而 Compare 当前仍把多个阶段纵向串联。
- 处理方法：将 Compare 设计为三层状态：任务列表页（搜索、筛选、分页、最近任务）、独立创建态（全页创建或创建弹窗/抽屉，创建后返回结果页）和结果阅读页（任务摘要、合同组导航、差异阅读器）。结果阅读页只保留当前任务上下文，任务列表通过“返回对比任务”进入；创建态保留草稿和恢复入口，刷新或上传中断后从未封存任务恢复，不依赖隐藏 DOM 中的浏览器 `File` 对象。无复杂业务判断的任务说明可用短摘要，详细上传回执和异常清单放在创建态内展开。
- 状态与验证：**已确认，设计待实施**。本条只记录 V1 页面边界和信息架构问题；尚未修改产品代码、未部署、未调用模型。与 FL-D260 的长文导航建议相关，但本条专门记录 V1 多工作流堆叠问题。
- 下一步：先确定采用全页状态切换还是可链接子路由；实现后覆盖任务列表→创建→结果→返回、刷新恢复、浏览器后退和 390px/768px/1440px 布局回归。
- 变更记录：2026-10-26 新增；来源为用户关于“各种东西堆在一起导致整个页面长长”的反馈及 V1 源码核对。

## FL-D329 V1 Compare 新建任务表单控件层级和样式不统一（2026-10-26）

- 发现日期：2026-10-26，V1 Compare 创建态视觉与键盘交互审查。
- 问题与影响：任务名称、文件夹批量选择、逐组文件选择、添加组、提交和断点继续都直接平铺在同一张卡片中；`compare.css:1,11` 只对部分输入和文件组做了局部样式，文件夹入口仍使用隐藏 `input` 包裹在 label 内。用户难以区分“准备文件”“检查配对”“提交上传”三个阶段，按钮主次不清；窄屏时表单会继续变成长列表。
- 证据：`frontend/compare.html:24` 将名称、两个文件夹按钮、配对清单、添加组、提交和继续上传放在同一 DOM 区块；工作台已有成熟的 `.btn`、`.btn-primary`、`.card-pad`、`.toolbar`、字段错误提示和导入页 dropzone 样式，但 Compare 创建态没有复用同样的分组层级。键盘不可聚焦的文件夹入口另见 FL-D324。
- 处理方法：创建态采用三段式表单：任务名称/方向说明、文件来源（拖放或文件夹批量配对/单组手工选择）、配对清单与上传状态。每段使用标题、辅助说明和独立容器；主操作只保留“开始上传并对比”，添加组和选择文件使用次级按钮，继续上传只在中断状态出现并紧邻失败原因。输入框、文件卡片、进度、错误和按钮统一复用工作台现有尺寸、边框、圆角、焦点和间距；不把技术错误码作为主文案。
- 状态与验证：**已确认，设计待实施**。本轮未改产品代码、未部署、未调用模型。表单信息层级与 FL-D328 的创建态边界一起实施；FL-D324 仍负责文件夹入口的键盘语义，不由本条替代。
- 下一步：实现后覆盖空表单、单组、多组、文件夹未配对、上传中断/继续、提交重复点击、字段错误和键盘 Tab/Enter/Space 路径。
- 变更记录：2026-10-26 新增；来源为用户关于按钮和输入框视觉质量的反馈、V1 Compare 源码与 V1 导入页样式对照。

## FL-D330 V1 Compare 差异清单应作为阅读器右侧独立滚动导航（2026-10-26）

- 发现日期：2026-10-26，V1 Compare 长文阅读器信息架构审查。
- 问题与影响：当前差异清单位于双栏正文之后，`compare.css:36` 的清单随正文继续向下堆叠；差异数量较大时用户不能同时看到正文和导航，也难以持续知道当前差异位置。仅依靠底部上一处/下一处按钮不能满足按章节、类型和摘要快速定位的复核路径。
- 证据：`frontend/compare.html:26` 先渲染 `#compare-columns`，再渲染差异工具栏和 `#compare-diff-list`；`compare.js:115-116` 负责清单定位，但清单没有与正文并列的有限高度滚动容器。既有审查样本曾出现约 2,772 条差异和约 148,616px 的列表高度；FL-D260 已记录相关长文导航建议，但该条补充 V1 原生 Compare 的源码边界和设计落点。
- 处理方法：桌面端将阅读器改为“左侧双合同正文 + 右侧差异导航 rail”：正文区域保持左右 pane 联动滚动，rail 使用固定/有限高度并独立滚动；顶部显示当前差异序号、总数、类型筛选和覆盖状态，清单条目显示编号、类型、章节和短摘要，当前条目与正文目标双向高亮。定位使用 pane 内相对 `scrollTop`，不滚动外层页面；差异清单过大时采用分页或虚拟滚动，保留当前项和相邻项可见。768px 以下将 rail 改为“差异”抽屉/独立面板，390px 默认单栏正文，点击差异自动切换到包含目标的原版或对比版。
- 状态与验证：**已确认，设计待实施**。本轮未修改 V1 Compare 代码、未部署、未调用模型。FL-D327 的移动端自动切栏、FL-D256 的类型视觉区分和 FL-D260 的长文建议是实施时必须共同验证的关联问题。
- 下一步：先完成桌面 rail 的 DOM/布局方案，再实现定位、独立滚动、筛选和移动端抽屉；使用真实 renderer 输出或等价大规模 fixture 覆盖 2,772 条差异规模，检查 390px、768px、1440px、键盘导航、焦点和外层页面滚动位置。
- 变更记录：2026-10-26 新增；来源为用户希望“差异列表放在右边，类似修订审查页”的反馈、V1 `compare.html`/`compare.js`/`compare.css` 核对及 FL-D260 关联证据。

## FL-D331 V1 Compare 差异阅读器缺少按左右文本生成选择版合同（2026-10-26）

- 发现日期：2026-10-26，用户新增需求及 V1 Compare 能力审查。
- 问题与影响：当前 Compare 只保存左右 DOCX 的差异 JSON 和 HTML 阅读投影，没有逐差异选择状态、选择版本或生成产物接口。用户无法在阅读器中决定某处采用原版（左侧）还是对比版（右侧），也无法得到根据这些选择生成的 DOCX。直接在浏览器拼接文本会丢失段落、表格、运行样式及未参与差异的内容，不能作为合同产物。
- 证据：`fundlex/compare/api.py:149-172` 只有 `/view` 只读接口；`fundlex/compare/store.py:70-73` 只有结果 JSON 产物表，没有选择版本/选择产物；`fundlex/compare/models.py:157-183` 的 `DiffItem` 有左右文本锚点但没有选择语义。现有 `fundlex/selective.py` 只适用于带 `w:ins/w:del` 修订标记的引擎 redline，Compare 的左右 DOCX 是两份独立源文件，不能直接套用其 revision ID 契约。
- 处理方法：以左侧 DOCX 为生成基底，逐差异接受 `left` 或 `right`。修改/新增/删除均需定义确定性合并规则：修改选择对应侧文本；左侧缺失的新增选择 left 表示不插入、选择 right 表示插入；右侧缺失的删除选择 left 表示保留、选择 right 表示删除。未明确选择默认采用右侧，并在页面显示默认口径。服务端保存选择快照和递增 `selection_epoch`，请求携带 `result_sha256`、左右源文件哈希、当前 epoch 和完整选择集合；重新读取并校验差异锚点、重叠范围、覆盖状态及版本后，使用保留的 DOCX 结构写入选择文本，独立验证生成文件可解析、目标段文本与选择结果一致、非目标部件保持不变，再保存 `selected_final.docx`、选择报告和哈希。源文件或结果变化、选择版本冲突、覆盖不完整且存在不可安全合并内容时关闭生成并要求重新读取/人工处理。
- 状态与验证：**需求已确认，阶段一契约和阶段二安全 writer 已实施，持久化/API、V1 阅读器和真实交付仍待实施**。已新增 `fundlex/compare/selection.py` 与 `fundlex/compare/selection_writer.py`，固定 `pending/left/right` 状态、三类差异的左右语义、未知/重复/冲突 ID 拒绝、decision/binding hash；writer 以左 DOCX 为基底，支持单段内 modify 和普通表格单元格 modify，生成选择版与选择修订痕迹版，重新读取并核对文本、修订接受等价和非目标部件。定向选择/算法/API 回归为 **34 passed / 1 warning**，writer 回归为 **6 passed**。空侧 insert/delete、跨段、整段结构、合并单元格和复杂部件当前明确阻断；尚未部署、未调用真实模型，尚未通过授权 API/工作台生成或下载真实选择版 DOCX。上文“未选择默认右侧”是初步建议，已由下方设计更新替代，不是用户确认的默认行为。“左侧为生成基底”仅为保留文档结构的技术方案建议，不代表用户选择左侧文本或要求输出完全复制左侧排版。不能以 HTML 文本拼接、fixture 或接口 200 代替最终产物核验。
- 下一步：先实现选择草稿/epoch/产物 API 和授权下载门禁，再接入 V1 阅读器；后续扩展有独立 OOXML 地址的段落 insert/delete 结构操作。必须继续覆盖修改/新增/删除（当前新增/删除先验证阻断）、相邻及多段差异、表格、源文件哈希变化、并发冲突、生成文件解析与前后文本差异。
- 变更记录：2026-10-26 新增；来源为用户“在差异阅读器选择接受左边还是右边，根据接受情况生成一版”的明确需求。
- 设计更新（2026-10-26，同轮）：沿用用户此前“先设计”的工作范围，不在本轮直接实施生成引擎。初始逐条状态为 `pending`（待选择），允许明确“全部采用左侧/右侧”和“仅为待选择项采用左侧/右侧”；仍有待选择项时不生成完整选择版。修改、新增、删除均使用明确的“采用左侧/采用右侧”文案，缺失侧显示“此处无文本（不保留/不新增）”，不能用空白内容掩盖删除语义。选择草稿需服务端持久保存，刷新/重开恢复，生成版本和草稿版本分开；选择变化后提示旧下载文件对应的生成版本，不能将旧文件冒充最新选择。跨段、整段新增删除、表格结构变化等须建立可写地址/结构操作和关联选择单元；现有 `TextSpan` 与空侧 anchor 仅足够展示定位，不能假定可以无损合并。不能独立选择的关联差异须在页面明确联合选择原因，仍无法生成时列出具体原因，不静默忽略差异。完整交互与验证要求见 `docs/V1_COMPARE_SELECTION_DESIGN_20261026.md`；本更新是方案建议，尚无产品实现或端到端验证证据。
- 变更记录（2026-10-26）：阶段一完成选择契约和纯逻辑验证；阶段二仍需实现安全 OOXML 写入、实际产物复读、持久化/API、V1 控件和真实用户端到端交付。
- 变更记录（2026-10-26）：阶段二完成单段内 modify writer 和真实 DOCX/修订版复读验证；空侧 insert/delete 仍为明确结构阻断，待后续建立段落级 OOXML 地址后再开放。
- 变更记录（2026-10-26，阶段三/四离线完成）：已新增 `compare_selection_drafts`、`compare_selection_artifacts` 两表及 `GET/PUT /api/compare/pairs/{id}/selection`、`preview`、`generate`、`selection-artifacts/{version}/{kind}` 路由。草稿绑定 epoch、result/左右源哈希和 canonical decision hash；增量保存与已有草稿合并；epoch/result/source 不匹配返回稳定冲突；同一 epoch/decision 重复生成返回同一版本；选择变更将旧版本标记 stale，旧文件仍可追溯下载。生成以真实左右 DOCX 重算 result、校验覆盖完整并重新读取产物，报告保存决策 hash、checks、limitations 和 manifest。V1 阅读器已加入逐差异左右 radio、进度、全部左右、清除、保存、预览、生成、版本/过期标记、选择报告和授权下载。真实 DOCX API/Worker/writer 测试、浏览器保存/刷新恢复/生成/下载/过期/390px 回归通过；Compare 定向 **91 passed / 5 skipped / 1 warning**，完整浏览器 **43 passed**，完整 Python **1637 passed / 56 skipped / 3 warnings**。一次性真实 MySQL 8.0.46 实例（数据库适配、RunStore 租约、Compare 并发、选择版事务）**27 passed**；该实例使用独立临时 datadir、独立端口和临时库/账号，结束后关闭，未接触生产 `fundlex` 库。以上均为离线/夹具/隔离服务器验证，不等于生产真实用户交付。
- 变更记录（2026-10-26，阶段五边界）：生产部署、候选冻结、普通工作台真实上传→Worker→选择→生成→实际 DOCX/哈希/授权下载尚未执行；未调用真实模型、未改变账本。结构新增/删除、跨段联合操作、header/footer 等覆盖缺口继续 fail closed/明确提示，不以离线通过冒充正式完成。

## FL-D297 全量回归出现 upload guard 顺序性 415 失败（2026-10-26）

- 发现日期：2026-10-26，OAuth/设置页改动后的全量回归。
- 问题与影响：`PYTHONPATH=. .venv/bin/pytest -q` 结果为 **1 failed / 1518 passed / 49 skipped / 3 warnings / 401.37s**。唯一失败为 `tests/test_upload_guard.py::test_app_rejects_oversized_content_length_before_multipart_parse`，预期 413 `UPLOAD_REQUEST_SIZE_LIMIT`，实际 415；该失败会降低“全量回归通过”的可信度，且可能掩盖上传守卫的顺序依赖。
- 证据：失败测试单独运行 `pytest -q tests/test_upload_guard.py::test_app_rejects_oversized_content_length_before_multipart_parse -vv` 为 **1 passed**；中间件逻辑 `fundlex/upload_guard.py:250-266` 在 Content-Length 超限时返回 413，缺失/非 multipart 时才返回 415。本轮 OAuth 改动未触及 `upload_guard.py` 或该测试，失败原因尚未定位。
- 处理方法：保留失败记录，不删除/跳过测试；同一源码再次全量回归以判断是否可重现；若复现，按测试顺序、全局 multipart 安装、TestClient/httpx 状态和上传守卫中间件逐项定位，不能用“单测通过”替代。
- 状态与验证：**已解决（第二次全量通过，首次失败未复现）**。同一源码第二次全量为 **1519 passed / 50 skipped / 3 warnings / 497.31s**；失败用例单独运行通过。未修改产品代码或跳过测试；判定为顺序/环境相关 flake，保留首次失败记录和复跑证据。
- 下一步：后续全量若再次出现该 415，按 FL-D297 记录复现条件；不把单次 flake 或单次通过写成稳定结论。
- 变更记录：2026-10-26 新增；第二次全量通过后更新状态，首次失败未删除。

## FL-D298 浏览器上传测试用 time.sleep 等待路由导致假失败（2026-10-26）

- 发现日期：2026-10-26，OAuth 改动后的 V1/V2 浏览器回归。
- 问题与影响：`tests/browser/test_workbench.py::test_upload_completion_preserves_new_draft[uploads]` 在等待 `pending` 时使用 Python `time.sleep` 轮询；Playwright sync API 的 route handler 需要测试线程继续泵事件，`time.sleep` 会让被拦截的 `POST /uploads` 一直停在路由队列，表现为“请求从未发生”，误判产品上传流程失败。`page.on("request")` 能看到 POST 创建和上传请求，route handler 却在测试失败后才执行。
- 证据：失败时 `pending` 为空但 `page.on("request")` 记录 `POST /api/tasks/.../uploads`；调试脚本用同样 route 模式可拦截。改为 `page.wait_for_timeout(100)` 泵事件后，两个参数化用例立即通过；产品代码未改。
- 处理方法：测试等待循环改用 `page.wait_for_timeout`；route handler 先登记请求再 `route.fetch()`，并等待响应；保留原有产品断言。没有降低断言或跳过用例。
- 状态与验证：**已解决（测试竞态已修正）**。参数化用例 **2 passed**；V1+V2 浏览器套件 **39 passed / 68.00s**。
- 下一步：浏览器异步 route 测试统一使用 Playwright 等待 API，禁止在需要处理 route 事件的循环中使用 `time.sleep`。
- 变更记录：2026-10-26 新增；与 FL-D297 的后端 flake 分开记录。

## FL-D300 飞书 OAuth 绑定二维码在设置页显示模糊、难以扫描（2026-10-26）

- 发现日期：2026-10-26，用户真实点击“生成扫码绑定二维码”反馈。
- 问题与影响：二维码是 65×65 模块，但设置页把 SVG 限制在 240px 宽（约 3.69px/模块），`qrencode` 生成的 SVG 又使用 `preserveAspectRatio="none"` 且没有 `shape-rendering="crispEdges"`，浏览器缩放时模块边缘被抗锯齿成灰边；用户看到“糊”，手机无法稳定识别。
- 证据：生产 OAuth start 的 SVG `viewBox="0 0 65 65"`、宽高 `6.88cm`、无 `shape-rendering`；旧 CSS `.feishu-oauth-qr{max-width:240px}`。真实页面旧渲染约 240px。
- 处理方法：二维码改为 **325×325 CSS px**，65 个模块正好 5px/模块；OAuth SVG 注入 `shape-rendering="crispEdges"` 并把 `preserveAspectRatio` 改为 `xMidYMid meet`。后端额外生成 650×650 高分辨率 PNG 作为回退（约 1.5KB，`qr_png`），V1/V2 优先使用带 crispEdges 的 SVG，PNG 回退使用平滑缩放；容器最大宽度 351px（含 12px padding + 1px border，内容区 325px）。V2 设置页同步。
- 状态与验证：**已解决（生产清晰度已验证）**。真实生产页面检查 `<svg>` 为 325×325、`shape-rendering="crispEdges"`、10 分钟提示正常、页面错误/控制台错误 0；PNG 回退 650×650、1,469 bytes。`tests/test_feishu_oauth_api.py` 等定向 **15 passed**，前端 typecheck/lint/build 通过。OAuth 真实扫码回调仍待用户扫码验证（FL-D295）。
- 下一步：用户强制刷新页面（旧 app.js/CSS 可能缓存）后再生成二维码；若相机仍难识别，可直接点“在飞书中打开授权页”。不得把二维码截图再压缩后转发。
- 变更记录：2026-10-26 新增；清晰度修复只改展示层与 QR PNG 回退，不改变 OAuth state/绑定权限模型。

## FL-D299 选择性发布 api.py 带入未部署依赖导致生产 API 启动失败（2026-10-26）

- 发现日期：2026-10-26 12:17，二维码清晰度修复的受控发布。
- 问题与影响：工作区 `fundlex/api.py` 已包含另一项未发布的 `manifest_fingerprint` 导入，但生产 `fundlex/selective.py` 仍是旧版本。仅复制 `api.py` 后重启 API，两个 uvicorn worker 均因 `ImportError: cannot import name 'manifest_fingerprint' from 'fundlex.selective'` 启动失败，8010 端口无监听，公网 OAuth start 返回 502。Worker 和 Feishu 服务未受影响，未发现数据损坏。
- 证据：`journalctl -u fundlex-recall-api.service` 在 12:17 记录 15 次 `ImportError`；发布前备份 `/tmp/opencode/fundlex-qr-sharp-20261026-121725/production-before.tgz`。恢复后 `/api/capabilities` 返回 200，API/Worker/Feishu 均 active。
- 处理方法：立即从发布前备份恢复生产可用的 `api.py`，只对其 OAuth start 响应补 `qr_png` 字段；单独部署自包含的 `fundlex/integrations/feishu/oauth.py`。未部署工作区 `selective.py` 或其他并发改动。当前工作区 `api.py` SHA `81bb09efcd5d6efc8c356e7836872c91f784e769a1ab2836d8cb5db9e718fb1f`，生产 `api.py` SHA `8048c11d54a896a75d8edb70ac43e1dc220e8a2e1ae3ed392cd9a71f7daf1fbf`；工作区 `selective.py` 含 `manifest_fingerprint`，生产旧版不含，两者暂不一致。
- 状态与验证：**已解决（服务已恢复，生产 API 未再使用不一致的 api.py）**。恢复后真实 OAuth start 返回 200、`qr_png` 650×650；生产页面二维码渲染 314px、自然尺寸 650、`image-rendering: pixelated`；页面错误 0。临时账号/state 已清理，当前 API/Worker/Feishu 均 active。
- 下一步：先在工作区完成 `api.py` 与 `selective.py` 依赖对齐并跑全量回归，再整仓/一致性发布；选择性发布前必须做目标环境导入检查（至少 `python -c 'import fundlex.api'`），并在发布清单中列出新增导入/模块。不得再次只复制 api.py 而遗漏依赖。
- 变更记录：2026-10-26 新增；这是一次发布边界事故，已恢复，不改变合同数据或报告；与 FL-D297/FL-D298 测试问题分开记录。

## FL-D296 飞书真实任务交付结果分化：D17 完整、D01/D02/D04 不完整（2026-10-26）

- 发现日期：2026-10-26，真实飞书多 DOCX 任务验收。
- 问题与影响：飞书绑定、草稿、附件接收、任务创建、状态卡片和详情深链均已真实跑通，但合同交付结果并不全部完整。第一个任务 `0a1122e359a94cbebf17d2782cfc0969` 的 D01/D02 均为 `incomplete`，只有 `working_final`/`working_redline` 和报告；第二个任务 `8da0ef68f2c8465986917a66e7835bf0` 的 D17 为 `complete`，D04 为 `incomplete`。因此不能把“飞书链路成功”写成“所有合同完整交付”。
- 证据：
  - D17（文档 `75c87caa35994695a87a0e90440d8fb9`）：final `f320b61c3fc42cb41c3c0fc489f85850c04a6ba597c387179f505bc29caf2b87`（141,191 bytes）、redline `e136a0da32bd94977e7869dc90a6371fa96b9a27e9be2b780aa578db91060e24`（142,517 bytes）、report_json `2930610c96b786a09c463e26ff50c4fd9cd6933736aedc7696e9bf9be4b9a8c0`；两份 DOCX 均可解析，实际变化 16 段，redline 16 insertions / 16 deletions，report 16 edits，14 个非空 replacement 全部出现在 final，`Claim Replay verified=true`，delivery gate `UNRESOLVED=0`/`blocking_unresolved=0`。浏览器登录后打开深链，final/redline/report 下载哈希与 API/报告 `output_validation` 完全一致。
  - D04（文档 `189c814f0a9c43789322dae04db9368e`）：`incomplete`，`Claim Replay verified=false`，open obligations 1、blocking_unresolved 3，原因为 G03 `CLAIM_REPLAY_FAILED` / `CLAIM_OPERATION_NOT_PLANNED`；只有 working 文件。
  - D01/D02：D01 未完成 G08/G11/G12；D02 也有未完成目标。两份均只有 working 文件，不能作为最终合同。
  - 真实模型：第二个任务 53 次请求（51 completed、2 failed）约 `$0.07428`、312,780 tokens，模型 `deepseek-v4.1-flash`；第一个任务 8 次调用（7 completed/1 reserved）约 `$0.02616`。
  - 飞书完成卡片已真实发送：第一个任务 `incomplete:2`；第二个任务 `incomplete:1, complete:1`，均带 `/tasks/<id>` 深链，深链登录后能自动打开对应任务。证据目录 `/tmp/opencode/feishu-e2e-20261026/`（`verification.json`、`verification-task2.json`、`browser-verification.json`、截图和下载件）。
- 处理方法：本轮不修改引擎规则来“制造”完整结果；D17 作为完整交付正向证据，D04/D01/D02 保留失败报告和工作文件，按例外清单人工核对。D04 的 G03 Claim Replay 缺口继续按既有引擎问题处理，不能以飞书链路通过替代。
- 状态与验证：**飞书集成主链路已验证；合同完整交付仅 D17 通过，整体仍为 NO-GO**。D17 的 final/redline/report 与浏览器授权下载已验证；D04/D01/D02 的 `incomplete` 明确保留。OAuth 扫码仍待真实回调验证（FL-D295）。
- 下一步：修复 G03 Claim Replay/未规划操作缺口后复测 D04；继续用 D17 或其它完整合同做 Feishu 详情/下载回归；D01/D02 的失败分类不得从分母或报告中移除。
- 变更记录：2026-10-26 新增；本条只记录真实 Feishu 路径结果，不改变 D01–D20 固定分母和 G06 既有门禁。

## FL-D295 飞书绑定需要手输一次性绑定码，缺少扫码自动绑定（2026-10-26）

- 发现日期：2026-10-26，用户提出给普通用户二维码、扫码后通过机器人连接 FundLex。
- 问题与影响：现有流程要求用户先在 FundLex 设置页生成 12 位绑定码，再切到飞书私聊手动发送 `绑定 <绑定码>`。公共二维码只能打开机器人，不能安全地自动绑定；同一绑定码给多人会导致合同权限串号。
- 处理方法：新增个人化飞书 OAuth 扫码绑定。登录用户在设置页生成一次性 `state` 二维码；飞书授权页回调用授权码换取用户身份，读取 `open_id/tenant_key`，只绑定到创建该 `state` 的 FundLex 用户。`state` 仅保存 SHA-256，10 分钟有效、一次性消费；绑定冲突仍按既有 `external_identities` 规则失败关闭。V1 设置页新增“生成扫码绑定二维码”并轮询绑定状态；V2 设置页同步增加。应用版本 `0.0.6`（`oav_d639cd9524601ba5d79ffd49944c3dd4`）增加 `contact:user.base:readonly`，并已通过应用配置 API 写入 OAuth 重定向 URL `https://fundlex.club/api/integrations/feishu/oauth/callback`；可用范围改为全员（`is_visible_to_all=1`）。
- 状态与验证：**已实现并发布，真实扫码回调尚未完成（用户未在有效期内扫码）**。定向后端测试 **30 passed / 1 warning**（Feishu 专项、OAuth API、入口、认证），前端 Vitest 最终 **14 passed**、typecheck/lint/build 通过，`node --check`、`compileall`、`git diff --check` 通过。OAuth start 在生产真实账号返回 200、二维码 SVG 约 103 KB、10 分钟有效；首次真实二维码等待 10 分钟后状态仍为未绑定，`integration_oauth_states` 中该 state 未消费且已过期，API 日志没有 `/api/integrations/feishu/oauth/callback` 请求，说明是未扫码而非回调失败。旧测试账号已用绑定码恢复绑定。另用新的未绑定临时账号在生产 V1 设置页点击“生成扫码绑定二维码”：按钮可见、渲染 112,472 bytes SVG、10 分钟提示和 Feishu 授权链接均正常、页面错误 0；随后已精确删除临时账号及未消费 state，旧链接立即失效。发布备份 `/tmp/opencode/fundlex-oauth-qr-20261026-104616/production-before.tgz`；部署后 API active，关键文件 SHA 与工作区一致。
- 下一步：重新生成个人二维码并让真实用户扫码，确认 `external_identities` 新增绑定、回调页提示成功、设置页轮询显示已绑定；OAuth 回调失败时必须重新生成二维码，不能复用已消费 state。随后用 D04/D17 做完整 delivery 验证。
- 变更记录：2026-10-26 新增；OAuth 二维码是个人化、一次性链接，不得作为公共海报分发；公共二维码仍只用于打开机器人。`admin:app.visibility` 为修改全员范围临时发布，后续应评估是否回收。

## FL-D294 飞书状态卡片的 FundLex 详情深链未打开具体任务（2026-10-26）

- 发现日期：2026-10-26，真实飞书任务状态卡片验收。
- 问题与影响：卡片生成 `https://fundlex.club/tasks/<task_id>`，但 V1 fallback 只识别 `/tasks`、`/tasks/new` 等固定路径，`/tasks/<id>` 被当作未知路径重定向到 `/#overview`。用户从飞书点击“打开 FundLex 详情”只会回到任务总览，不能直接看到对应任务，详情查看链路不完整。
- 证据：`fundlex/integrations/feishu/cards.py` 生成 `/tasks/{task_id}`；`fundlex/api.py` 原 fallback 的映射不包含动态任务 ID；真实飞书卡片文本包含该链接（`/tmp/opencode/feishu-e2e-20261026/messages-2.json`）。修复前点击只会到任务总览。
- 处理方法：V1 fallback 对 `/tasks/<id>` 返回 307 到 `/?task=<urlencoded-id>#task`，保留 `/tasks/new` 为新建任务；`frontend/app.js` 增加 `openDeepLinkedTask()`，在初始化刷新、登录成功和注册成功后读取 `task` 查询参数并调用 `selectTask()`。未登录时保持登录页，登录后自动继续打开目标任务。
- 状态与验证：**已解决（生产深链已验证）**。`tests/test_frontend_entry.py` 为 **3 passed**，覆盖默认入口、测试前缀和 `/tasks/new` 非任务 ID；浏览器 `test_task_deep_link_selects_task` 通过；`node --check` 与 `git diff --check` 通过。生产 `/tasks/<id>` 返回 `307 location: /?task=<id>#task`，真实 member 登录后自动打开“飞书合同任务”，`#view-task` 可见，页面错误 0。发布仅覆盖 `fundlex/api.py` 与 `frontend/app.js`，工作区/部署 SHA 分别为 `d5c459586fe6c3bf68881351b7be76a7f7466e1e474a0e5498f7969f9e412f1c`、`59e998dca6b56fb3da32673f5487dd6c3d0aa3532ee2297a1dba3397d5678a61`；备份 `/tmp/opencode/fundlex-deeplink-20261026-102313/production-before.tgz`，证据 `/tmp/opencode/feishu-e2e-20261026/deeplink-task.png`。
- 下一步：飞书完成摘要卡片继续使用该深链；后续若切换 React V2，需要为 `/tasks/:id` 增加等价的真实路由和任务选中行为。
- 变更记录：2026-10-26 新增；本轮修复未改动 Worker 处理逻辑，API 重启未中断已启动的 Worker 任务。

## FL-D292 飞书机器人缺少消息资源读取权限，DOCX 附件事件失败（2026-10-26）

- 发现日期：2026-10-26，真实飞书绑定后的首份 DOCX 发送。
- 问题与影响：真实用户发送 D01 后，`im.message.receive_v1` 文件事件到达并创建 `feishu_drafts`，但机器人下载附件时抛出 `RuntimeError`，事件状态变为 `dead`，草稿停在 `COLLECTING` 且没有 `feishu_draft_files` 记录，用户无法继续创建任务。
- 证据：`fundlex-feishu.service` 仅记录 `Feishu event failed ... error=RuntimeError`；用同一 `message_id`/`file_key` 直接调用机器人资源下载返回 `code=99991672`，明确要求 `im:message.history:readonly`、`im:message:readonly` 或 `im:message` 应用身份权限。首份文件名与事件证据保存在 `/tmp/opencode/feishu-e2e-20261026/`，未记录凭据。
- 处理方法：通过应用管理 API 增加 tenant scope `im:message:readonly`，发布飞书应用版本 `0.0.3`（`oav_a7195c49bfcb2ee5ec690c595dedecb7`，状态 `1`），切换 `online_version_id` 并重启 `fundlex-feishu.service`；同一资源下载调用随后返回 `code=0` 且 `has_file=true`。重新发送 D01 后附件变为 `accepted`，随后 D02 也 `accepted`，两份合同进入同一草稿。
- 状态与验证：**已解决（权限与两份附件接收已验证）**。`feishu_draft_files` 记录 D01 141,078 bytes、D02 162,609 bytes，状态均为 `accepted`；草稿随后 `SUBMITTED` 并创建任务 `0a1122e359a94cbebf17d2782cfc0969`。最终 Worker/模型、DOCX 产物和授权下载仍待任务终态验证。
- 下一步：在飞书应用发布检查中固定验证 `im:message:readonly`（或等价资源读取 scope），并把附件下载失败从笼统 `RuntimeError` 改为可诊断错误码；本轮未改代码。
- 变更记录：2026-10-26 新增；首份失败事件保留在 `integration_events` 中作为真实失败证据，未删除历史记录。

## FL-D293 用户身份不能直接向机器人 open_id 发送私聊消息（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：使用真实用户 token 调用 `im +messages-send --user-id <bot_open_id>` 时，飞书返回 `code=230001`、`this operation to bots is currently not supported`，无法直接完成 `绑定 <绑定码>` 消息。
- 证据：`/tmp/opencode/feishu-e2e-20261026/binding-send.err` 中脱敏错误；机器人信息接口返回 bot `open_id`，用户 token 正常。
- 处理方法：改用飞书支持的正常私聊建立路径：先由机器人向真实用户 `open_id` 发送一条私聊消息，取得返回的 `chat_id`；再由用户 token 在同一 `chat_id` 发送 `绑定 <绑定码>`。绑定随后成功，`external_identities` 新增 1 条有效记录，`/api/integrations/feishu/binding` 返回 `bound=true`。
- 状态与验证：**已解决（真实绑定已验证）**。绑定成功后飞书返回“绑定成功”卡片，绑定账号前缀为临时 FundLex 用户 ID；用户随后在同一私聊发送两份 DOCX 和“确认”，任务已创建。
- 下一步：文档和接入说明应记录“机器人先发起私聊、用户再回复”的绑定/消息路径，避免继续尝试用户直发 bot open_id。
- 变更记录：2026-10-26 新增；绑定码为一次性短期凭据，未写入文档或日志。

## FL-D291 生产密码用户被 V1 开发设置守卫阻断，无法生成飞书绑定码（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：生产 `auth_mode=password` 用户点击 V1 侧栏“设置”时，`frontend/app.js` 的点击监听器仍要求 `state.cap.auth_mode==='dev'`，直接提示“当前运行环境未开放开发设置”。这阻断了普通登录用户进入设置页生成飞书一次性绑定码，也使真实飞书 E2E 无法沿正式用户路径开始。`tests/browser/test_workbench.py` 旧断言还要求 member 的 `#view-settings` 隐藏，掩盖了合法入口。
- 证据：修复前生产 `frontend/app.js` SHA-256 为 `da2535e2f478550a29f8e6a97fa43e1e58171ff0326e90d0828cb07b2ad6f057`；`/settings` 深链正确 307 到 `/#settings`，但页面点击被上述守卫拦截。V1/V2 浏览器回归旧结果为 36 passed / 1 failed，失败断言位于 `tests/browser/test_workbench.py:353`。
- 处理方法：移除设置导航的 `auth_mode==='dev'` 守卫；V1 侧栏、顶栏和面包屑的“开发设置”改为“设置”；保留 `#dev-settings-panel` 在 password 模式隐藏、`#users` 仅管理员可见和 `/api/admin/*` 的管理员权限。浏览器契约改为断言 member 设置页可见、开发面板隐藏、飞书绑定按钮可见，并补管理员用户视图重定向检查。仅备份并发布 `frontend/app.js`、`frontend/compare.html`，重启 `fundlex-recall-api.service`。
- 状态与验证：**已解决（生产设置入口已验证）**。
  - 前端检查：`npm run typecheck`、`npm run lint`、`npm test -- --run`（4 files / 9 passed）、`npm run build`、`node --check frontend/app.js`、`git diff --check` 全部通过；V1+V2 浏览器回归 **37 passed**。
  - 生产发布：工作区与 `/opt/fundlex-recall-first/frontend/app.js` SHA-256 均为 `9a6ad9e43cfccce90431ce484d436c6b7085972207cfad903d78005dc7e5b134`，`compare.html` 均为 `42505246214d3be174c5ecb918fe41d0aae388df11023eee76ffaf9c8b6558a0`；API/Worker/Feishu 服务均 active，公网 `app.js` 与工作区哈希一致，旧拦截文案计数为 0。发布备份：`/tmp/opencode/fundlex-settings-fix-20261026-095645/production-frontend-before.tgz`。
  - 真实生产账号路径：注册并登录临时 member 后，`#view-settings` 可见，`#dev-settings-panel` 隐藏，`#feishu-binding-code-btn` 可见，顶栏和面包屑均为“设置”；点击后 UI 渲染 12 位绑定码和“10 分钟内有效”，`/api/integrations/feishu/binding-code` 返回 200；`#users` 重定向、`/api/admin/users` 返回 404（fail closed）；页面错误为 0。证据：`/tmp/opencode/fundlex-prod-settings-e2e-20261026/ui-evidence.json`、`settings.png`、`settings-code-generated.png`（绑定码已隐藏），账号凭据仅在 `credentials.json`（`0600`）。
- 下一步：沿该真实账号继续生成绑定码、在飞书私聊完成绑定，并完成多个 DOCX、Worker/model、产物、状态卡片、详情和授权下载验收；真实闭环完成前不宣称飞书验收通过。
- 变更记录：2026-10-26 新增；修复与生产发布完成。同日为设备授权补发飞书应用版本 `0.0.2`（`oav_a4befe0a6d1171c1075c7a10a6724d8d`），增加 user token 的 `im:message.send_as_user`、`im:message`、`im:chat:readonly`，应用 `online_version_id` 已切换；未记录任何 Secret 或用户 token。

## FL-D290 飞书应用平台配置与真实 E2E 主链路（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：用户已创建企业自建应用；此前尚未完成机器人、长连接、消息/卡片回调、消息权限和应用发布，导致真实用户、附件、Worker/模型、状态回传和授权下载闭环不能验收。
- 证据：服务器 `/etc/fundlex-recall.env` 已安全写入 App ID、新 Secret 和 `FUNDLEX_PUBLIC_BASE_URL=https://fundlex.club`，Secret 未写入仓库、文档、日志或聊天；`fundlex-feishu.service` 已 enable/active，API 和 Worker 当前 active。用户曾在聊天中发送旧 Secret，该旧值视为已暴露并且不再使用。
- 处理方法：用户完成 Secret 轮换并安全注入后，服务器安装并启用 `lark-oapi==1.7.5`、独立 systemd 服务和官方 `lark-cli==1.0.98`。2026-10-26 09:26–09:28 通过 CLI/API 写入 `im:message.p2p_msg:readonly`、`im:message:send_as_bot`、WebSocket 事件模式和新版 `card.action.trigger` 回调；09:29 提交发布版本 `0.0.1`。
- 状态与验证：**平台配置、应用发布和真实用户 E2E 主链路已验证；合同完整交付仅 D17 通过，D01/D02/D04 为 incomplete；OAuth 扫码真实回调仍待验证**。整体仍为 NO-GO，见 FL-D296。
  - 已实际验证（2026-10-26）：新 Secret 写入后 `fundlex-recall-api`、`fundlex-recall-worker` 已重启，`/proc/<MainPID>/environ` 中 `FUNDLEX_FEISHU_APP_SECRET` 各出现 1 次；两服务 `active`，uvicorn/worker 日志无启动错误；直接调用飞书 `auth/v3/tenant_access_token/internal` 返回 `code=0 msg=ok`，取到 tenant token（有效期 7199s），说明 App ID/Secret 组合有效且服务器可出网到 `open.feishu.cn`。
  - 平台验证：线上版本 `oav_aa33e3f12b97a8bcd1a22dc88c8823fb`、版本号 `0.0.1`、状态 `1（已发布）`；版本详情包含机器人能力、`im.message.receive_v1`，权限包含 `im:message.p2p_msg:readonly` 和 `im:message:send_as_bot`。机器人信息接口返回正常；服务重启后保持 `active/enabled` 并建立 WebSocket 连接。
  - 初始平台核验时尚无真实绑定/附件/产物证据；后续已完成真实绑定、4 份公开 DOCX 上传、两个正式任务、状态/完成卡片、D17 的 final/redline/report 和浏览器授权下载。应用版本详情不单独回显 callback 列表，但 `callback_type=websocket` 与新版 `card.action.trigger` 写入接口均返回成功；卡片确认按钮的点击回调仍建议单独回归（本轮以文字“确认”完成任务）。
  - 2026-10-26 10:04 补发版本 `0.0.2`（版本 ID `oav_a4befe0a6d1171c1075c7a10a6724d8d`，状态 `1`），在保留既有 tenant 权限的基础上增加 user token 的 `im:message.send_as_user`、`im:message`、`im:chat:readonly`，应用 `online_version_id` 已切换。该变更用于官方 CLI 设备授权的真实用户消息发送；设备授权文件仅保存在 `/tmp/opencode/feishu-device-auth-20261026/`（目录 `0700`、文件 `0600`），未写入仓库或文档。
  - 2026-10-26 真实 E2E：真实用户李嘉伟完成 CLI 设备授权；因飞书不允许用户直接向机器人 open_id 发消息，改为机器人先发起私聊取得 `chat_id` 后由用户发送绑定消息，`bound=true`。两份公开 DOCX 经飞书上传、草稿、确认后创建任务 `0a1122e359a94cbebf17d2782cfc0969`，状态卡片、完成卡片和 `/tasks/<id>` 深链均实测；该任务 D01/D02 均为 `incomplete`。第二个任务 `8da0ef68f2c8465986917a66e7835bf0` 的 D17 为 `complete`（final/redline/report、Claim Replay true、浏览器下载哈希一致），D04 为 `incomplete`。详见 FL-D292、FL-D293、FL-D294、FL-D296。
  - 2026-10-26 飞书应用另补发 `0.0.3`（`im:message:readonly`，修复附件下载）、`0.0.4`（临时 `admin:app.visibility`）、`0.0.5`（OAuth 重定向 URL）、`0.0.6`（`contact:user.base:readonly`，OAuth 扫码）。可用范围已改为全员（`is_visible_to_all=1`）；OAuth 首次真实二维码无人扫码，state 未消费并过期，回调仍未验证。
- 下一步：重新生成个人 OAuth 二维码并完成一次真实扫码回调；修复 D04 的 G03 Claim Replay/未规划操作缺口；如需验证卡片按钮而非文字确认，使用一张新草稿做真实点击回调。D17 已作为完整交付正向证据，D01/D02/D04 的失败不得从报告或分母移除。
- 变更记录：2026-10-26 新增；服务器环境备份路径为 `/etc/fundlex-recall.env.bak-20261026-084101` 和 `/etc/fundlex-recall.env.bak-20261026-085808`。用户轮换后的 Secret 已注入并验证 token 接口返回 `code=0`；09:08 飞书服务启用并建立 WebSocket；09:23 应用管理 scope 验证通过；09:26–09:28 配置消息权限、WebSocket 回调和卡片回调；09:29 发布 `0.0.1`；10:04 发布 `0.0.2` 用户身份 scope。全程未记录任何凭据值。

## FL-D277 前端测试工具链包含已知依赖漏洞（2026-10-26）

- 发现日期：2026-10-26，多 agent 全项目检查。
- 问题与影响：历史审查时 `frontend/package.json` 使用 Vitest `^2.1.9`，锁文件为 2.1.9，带入旧版嵌套工具链并触发审计告警。具体利用分别依赖 Vitest UI/开发服务器暴露、原型污染等条件，不能把包严重级别直接外推为当前生产网站可利用漏洞。
- 证据：`frontend/package.json`、`frontend/package-lock.json`；审计原始输出 `/tmp/opencode/fundlex-audit-20261026-npm.json`，包含 GHSA-5gmw-xhrv-c9v3、GHSA-85c8-ppgw-ccpr、GHSA-82fw-gwwq-j7x9 等。`npm audit --omit=dev --json` 的 `/tmp/opencode/fundlex-audit-20261026-npm-production.json` 为零漏洞，所有上述版本在锁文件中均标为 dev。
- 处理方法：建议升级 Vitest 及其嵌套工具链到修复版本，审查 Node 兼容性及配置迁移后执行 typecheck、lint、单元/组件与浏览器回归。审计建议 Vitest 4.1.12，属于跨大版本变更，本轮审查未自动修复依赖。
- 状态与验证：**依赖升级已实施；审计边界仍需复核**。`package.json` 和 `package-lock.json` 现锁定 Vitest `^4.1.12`/`4.1.12`；执行 `npm ci --ignore-scripts` 后实际版本为 **4.1.12**，前端 Vitest **14 passed**，typecheck、lint、build 通过。尚未把新的 `npm audit` 输出作为生产安全结论，且未部署本轮前端改动。
- 下一步：在最终 clean candidate 上重新运行完整 npm audit，确认新工具链的开发依赖告警及生产依赖零漏洞结论；保留浏览器回归和 Node 版本范围记录。
- 变更记录：2026-10-26 新增；后续依赖重建和版本核对后更新为 Vitest 4.1.12，保留原始审计证据及历史风险范围。

## FL-D278 项目主入口文档与当前实现/部署状态持续漂移（2026-10-26）

- 发现日期：2026-10-26，多 agent 全项目检查。
- 问题与影响：README 主体仍描述 2026-10-14 的 v1/v2、固定 22 action、两种提交模式与旧发布流程；`FULL_PROJECT_IMPLEMENTATION_PLAN.md` 的 P1–P8 多数仍未勾选，而最新代码、生产 V1 单例交付与 FL-D276 已证明部分能力实现。`ACTIVE_HANDOFF.md` 保留的后续历史段落仍写 dirty 和旧 HEAD。缺少清晰的当前状态总览时，接续者可能采用旧命令、误认为功能未实现，或将历史发布证据误用于当前完整质量门禁。
- 证据：本轮起点 HEAD `c46d6e8`、分支 `refactor/backend-engine-finalization`、工作区干净；README 第 5–15、41–50、95 行以后；实施计划 P0–P8；ACTIVE_HANDOFF 顶部 FL-D276 与后续历史断点。主入口本地链接扫描缺失目标为 0，说明问题为内容/时态一致性，而非死链。相关历史文档归档已见 FL-D071，本条记录归档后持续状态漂移。
- 处理方法：建议在 README 和实施计划顶部建立唯一当前快照索引，明确源码 HEAD、部署版本、实际通过范围、待验收项、运行命令和预算来源；历史状态保留并标日期，不自动把历史未勾选项全部改为完成。集中问题状态应在新证据出现时追加更新原编号。
- 状态与验证：**已确认、待收敛**。本轮报告已分开记录源码/运行/真实证据范围，未重写历史业务结论或评测分母。
- 下一步：结合本轮各方向审查形成可复查当前状态页，并按实证更新实施计划；20 dev/holdout、G06、Compare 覆盖和飞书/MySQL 缺口保持明确。
- 变更记录：2026-10-26 新增；不将文档状态过期解释为功能不存在，也不将单例成功写成全项目完成。

## FL-D279 V1 浏览器角色测试仍把普通用户设置页当作管理员页面（2026-10-26）

- 发现日期：2026-10-26，多 agent 全项目检查中的串行浏览器回归。
- 问题与影响：`FUNDLEX_BROWSER_TESTS=1 PYTHONPATH=. .venv/bin/python -m pytest tests/browser/test_workbench.py tests/browser/test_frontend_v2.py -q` 结果为 36 passed、1 failed。失败位于 `tests/browser/test_workbench.py:353`：普通 member 登录后切换 `#settings`，测试要求 `#view-settings` 隐藏。当前 V1 页面设置区包含普通用户可用的飞书绑定和运行能力；仅其中的本地开发身份面板在 password 模式隐藏。若继续使用旧断言，会把合法设置入口误判为角色越权；若未来设置页加入管理员操作，也可能因笼统测试无法区分权限边界。
- 证据：失败日志 `/tmp/opencode/fundlex-audit-20261026-browser.log`；`frontend/app.js:60-62,156` 仅对 `users` 做 admin hash guard，`updateSettingsNav()` 明确保留 settings；`frontend/compare.html:33` 的设置区包含 Feishu 用户绑定和能力信息；后端 `/api/admin/*` 仍通过 `fundlex/api.py:_admin` 只允许 admin，普通用户的指引/绑定接口使用 `_user`。
- 处理方法：更新 V1 浏览器测试契约，断言 member 可以访问 settings 的用户功能，同时断言开发身份控件隐藏、`#users` 重定向且普通用户无法访问 `/api/admin/users`；不要为通过旧断言而隐藏普通用户设置。补一项真实 password 模式 API/页面检查，确认 settings 中不出现管理员操作。
- 状态与验证：**已解决（测试契约与生产入口均已修正）**。`tests/browser/test_workbench.py` 现断言 member 的 `#view-settings` 可见、`#dev-settings-panel` 隐藏、`#feishu-binding-code-btn` 可见，并验证 `#users` 重定向和 `/api/admin/users` 404 fail-closed；V1+V2 浏览器回归 **37 passed**。生产真实 member 登录路径同样通过，详见 FL-D291。
- 下一步：保留“普通用户设置可用、管理员能力仍受限”的权限设计；若未来设置页加入管理员操作，需为这些操作单独增加角色断言，不能把整个设置页重新设为 admin-only。
- 变更记录：2026-10-26 新增；同日修正测试并完成生产设置入口验证。

本文件是项目细节问题与处理方法的唯一集中记录，依据根目录 `AGENTS.md` 持续维护。创建于 2026-10-14。

## FL-D301 生产合同大量 incomplete 的主因是业务交付门禁未闭合（2026-10-26）

- 发现日期：2026-10-26，用户询问创建的任务大部分为何为 `incomplete`；读取生产 MySQL 汇总并按每份合同的首要阻塞原因归类。
- 问题与影响：生产库共有 666 份合同，其中 335 份 `delivery_status=incomplete`（50.3%）。这 335 份全部为 `status=succeeded`，说明主要问题不是任务排队、Worker 未运行或模型请求整体失败，而是文档已处理后仍未通过业务交付完整性门禁；因此系统只保留 `working_final`/`working_redline` 和报告，不开放 `final/redline`。
- 证据：生产 MySQL 只读统计（2026-10-26）为 `succeeded/incomplete=335`、`succeeded/complete=246`、`failed/not_generated=52`、`succeeded/not_generated=18`；按任务汇总，595 个含合同任务中 318 个至少有一份 incomplete，307 个全部合同 incomplete。335 份 incomplete 的首要阻塞分类为：目标定位/规划/生成执行未闭合 212（63.3%）；独立业务复核未通过 86（25.7%）；Claim Replay 发现实际产物与授权操作不一致 25（7.5%）；最终查漏、覆盖和其他 12（3.6%）。分类按每份合同只计首要类别，诊断项之间可能重叠。
- 细分线索：所有诊断项累计出现最多的原因码为 `RECALL_EDIT_OVERLAP`、`SURVEY_QUOTE_UNRESOLVED`、`RECALL_TARGET_UNRESOLVED`、`RECALL_COMPOSE_FIXED_TEXT_MISSING` 和 `RECALL_TARGET_COMPOSITE_UNRESOLVED`。这些分别对应同一物理范围有多个编辑冲突、模型引文无法绑定原文、目标无法安全定位、固定文案生成/校验失败及跨段/复合目标无法闭合。生产近期 Feishu 任务也符合这一模式：D01/D02/D04 均 Worker 成功但交付 incomplete；D17 在 Claim Replay 和 delivery gate 均闭合后为 complete。
- 处理方法：本次不放宽交付门禁，也不把工作文件冒称最终合同。引擎应继续从原件重建并对每项适用义务完成目标、计划、实际 DOCX 和 Claim Replay 闭环；修复优先级为编辑重叠/复合目标与引文定位，其次是独立复核残留和生成错误，最后处理 Claim Replay 归因缺口。前端解释应明确区分“处理成功”与“交付完整”。
- 状态与验证：**已确认，根因统计完成；引擎问题仍待修复和真实复测**。生产 API/Worker 在数据库凭据轮换后均 active，数据库连接计数查询正常；本次未修改业务源码、规则或历史报告。
- 下一步：按当前 clean candidate 冻结版本，针对 `RECALL_EDIT_OVERLAP`、`SURVEY_QUOTE_UNRESOLVED`、`RECALL_TARGET_UNRESOLVED`、`RECALL_COMPOSE_FIXED_TEXT_MISSING` 和 Claim Replay 失败建立分母，修复后用真实合同重跑并比较 incomplete 比例；不以目标计数为零或 Worker `succeeded` 代替交付 gate。
- 变更记录：2026-10-26 新增；统计来自生产数据库当前全量，不代表 D01–D20 固定分母或正式发布 gate 已通过。

## FL-D302 生产数据库连接凭据在诊断命令输出中暴露并已轮换（2026-10-26）

- 发现日期：2026-10-26，执行生产任务统计时读取 `/etc/fundlex-recall.env` 的数据库连接配置，诊断命令输出曾包含数据库连接串中的旧密码。
- 问题与影响：该旧数据库密码按已泄露凭据处理；若不轮换，持有诊断输出者可能尝试连接生产 MySQL。凭据值不写入本记录、仓库、日志或聊天。
- 证据：发现位置为本次 agent 的 shell 输出；生产数据库用户为 `fundlex`，配置文件为 `/etc/fundlex-recall.env`。仅记录变量名和路径，不记录密码值。
- 处理方法：使用原连接验证后生成随机新密码，执行数据库用户密码轮换；修改前备份 `/etc/fundlex-recall.env.bak-20261026-db-rotation`，更新 `/etc/fundlex-recall.env`，重启 `fundlex-recall-api.service` 和 `fundlex-recall-worker.service`。后续诊断只使用直接环境注入和脱敏输出，不打印连接串。
- 状态与验证：**已解决（本机范围）**。2026-10-26 12:18 API、12:26 Worker 均为 `active`；使用新配置连接生产 MySQL，`batches/documents/task_batches/tasks` 计数查询成功。未发现凭据值写入仓库、集中文档或项目日志；外部已产生的 shell 输出由本次会话保留，无法从聊天历史撤回。
- 下一步：若该输出进入外部共享系统，应按同一泄露事件继续检查并轮换相关派生凭据；以后禁止用会展开连接串的命令读取环境文件。
- 变更记录：2026-10-26 新增；轮换的是生产数据库账号密码，未修改代码或数据库业务数据。

## FL-D303 根发布器与仓库规范发布脚本存在版本漂移（2026-10-26）

- **2026-10-28 多阶段整改方案只读核验补充（新发布能力缺口未修复）**：`tools/deploy/publish_workspace.sh`仅转发root脚本，仓库/实际root发布器`SRC`固定`/home/opencode/fundlex`；root脚本第282行拒绝全部参数。换到release worktree运行wrapper不会改变发布源，当前没有`--source/--commit/--dry-run`可用参数。两脚本`UNITS`均只含API/Recall/Compare/Feishu，但`systemctl is-active`核对上述四服务和`fundlex-guide-worker`五者均active，**Guide Worker尚未纳入此发布停启清单**。新方案S10前须实现/隔离验证显式冻结候选发布或同等受控方案、纳入适用服务的版本与迁移核验；禁止覆盖原dirty树迁就固定SRC，禁止执行截断脚本片段。代码回滚不能撤销schema，正式E2E失败后的恢复须预先设计。当前仅规划及只读发现，未改脚本/配置、未重启、未部署；历史四服务发布测试结论不扩展为五服务新候选验收。

- 发现日期：2026-10-26，P0 incomplete 修复发布边界核对。
- 问题与影响：仓库 `tools/deploy/fundlex-publish.sh` 已同步 API、Recall Worker、Compare Worker，执行 `engine_build()` 哈希核对及部署目录检查；本机 root 发布器 `/usr/local/sbin/fundlex-publish` 仍为旧版，仅重启 API/Recall Worker、检查 capabilities。直接调用将遗漏 Compare 重启和运行构建验证。
- 证据：本机只读比对两个脚本确认差异；基线证据目录 `/tmp/opencode/incomplete-remediation-20261026/`。生产当前 API/Recall Worker active，不代表发布器差异已解决。
- 处理方法：下一次候选发布前备份 root 发布器，核对仓库规范脚本并安全安装；先做 shell 语法和整仓 Python 导入检查，发布后核对三个 unit、构建哈希、部署目录和 capabilities。
- 状态与验证：**已处理，待候选发布验证**。已将仓库规范脚本安装到 `/usr/local/sbin/fundlex-publish`，安装前备份保存在 `/tmp/opencode/incomplete-remediation-20261026/`；两者 SHA-256 均为 `1ebe1b52...`，`bash -n` 通过。新增的源/部署 `fundlex.api` 导入预检使用临时数据目录并移除生产数据库环境变量，已实际通过；未重启服务或发布业务代码。
- 下一步：候选发布时验证三个 unit、`engine_build()`、部署目录和 capabilities；依赖检查失败时保留已知可用部署版本。
- 变更记录：2026-10-26 新增；FL-D299 记录此前事故恢复，本条记录持续存在的发布器漂移。

### FL-D303 变更记录（2026-10-26 13:24）

- 独立监督复现并确认：仅设置 `PYTHONPATH` 而不切换 cwd 时，发布预检可能从当前工作区导入同名 `fundlex`，不能证明部署目录可导入；已改为在被检查 root 内执行，断言 `fundlex`、`fundlex.api`、`fundlex.selective` 的 `__file__` 均位于该 root，并将临时数据目录放到 `/tmp/opencode`。
- 监督还确认旧发布器失败后会留下已覆盖的部署树，且遗漏 `fundlex-feishu.service`；发布脚本已补充部署树/unit 备份、失败回滚尝试和 Feishu unit 同步/重启。此改动尚未以完整发布流程验证，P5 仍保持 NO-GO。

### FL-D303 变更记录（2026-10-26，staging 发布器与隔离回归完成）

- 发布器已实现 staging transaction、候选 manifest、隔离导入及模块来源断言、停止四服务后串行 schema 初始化、API→Recall→Compare→Feishu 顺序启动，以及失败保留 transaction 并回滚部署树/unit；主线提交 `224c4e3`，隔离测试增强 `13a3380`。
- 最新仓库脚本、root `/usr/local/sbin/fundlex-publish`、部署脚本三者 SHA-256 均为 `a873e4b4961207a6fabdb5caf01f8d809c500b6a430ce9c80af8dad114de0338`，替代上文历史 `1ebe1b52...`；`bash -n` 与隔离回归 **11 passed**。覆盖真实项目 schema 初始化、迁移顺序、候选 import 来源、启动/迁移失败回滚、运行时写入、`.pyc` 并发、软链接边界。
- 当前状态：**实现及隔离验证完成，正式候选完整发布待验证**。最近四服务 active 不作为本候选发布成功依据；FL-D307 的生产 dirty 快照仍保留为事故证据。schema 为向前迁移，代码回滚不能撤销数据库迁移；正式发布仍需核对四服务重启计数、日志、build、manifest、capabilities 和真实交付。

## FL-D306 评测 runner 使用未登记 5000/$5 cap，导致隔离账本越过历史上限（2026-10-26）

- 发现日期：2026-10-26，Evaluation agent 对 FL-D304 的账本增量和 dev-21 运行 provenance 只读追查。
- 问题与影响：隔离账本 `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 的 rowid 1702–2293 共 592 次请求来自 `dev-21-full`，实际费用 `$0.67976100`，覆盖 D01–D20。标准 runner 登记的是 2000 requests/$2，但 dev-21 专用 runner 使用了未登记的 5000 requests/$5 override；因此运行越过 row 2000 和 `$2`，历史账本当前为 2,293/$2.32384410，旧的 20 份预算记录与实际启动配置不一致。
- 证据：`/tmp/opencode/operation-validation-20261024/dev-21-full/batch.json` 启动时间 2026-10-24 23:43:33 UTC；ledger 增量首末时间 23:43:35–00:49:15 UTC，连续 rowid 1702–2293，报告 metadata 与 592 行逐条唯一匹配。标准 runner `/tmp/opencode/fundlex-operation-validation.py` 写 2000/$2，dev-21 runner `/tmp/opencode/fundlex-operation-validation-dev21.py` 写 5000/$5；没有找到 cap 提升授权或 `run_context-21.json`。
- 处理方法：保留 dev-21 所有原件、报告、ledger 行和旧分母，标记为“未登记 cap 的历史批次”，不重置、不删除、不把其结果冒称当前合法评测。修复 runner，使 cap、ledger、build、run id、启动时间写入同一不可变 manifest，并在下一轮启动前 fail-closed 校验；重新运行前必须重新登记总预算。
- 状态与验证：**已确认，阻断下一轮新增真实模型调用**。本轮未写账本、未启动 `p6_run.py` 或 Langfuse；`reserved_cost` 累计 `$15.45037635` 是历史每次 reserve 的最坏估算总和，不代表当前未释放余额，当前 reserved 状态为 0。
- 下一步：预算负责人决定是否承认 592 次历史消耗；D06 重新独立标注并冻结 labels amendment；新预算和候选 build 未冻结前不启动开发集/留出批次。
- 变更记录：2026-10-26 新增；与 FL-D304 同一账本问题，FL-D304 记录汇总影响，本条记录未登记 cap 的具体 provenance 根因。

### FL-D306 变更记录（2026-10-26，预算 admission 接入）

- 主线 `da0562c/690c352` 新增只读 ledger admission，校验 protocol hash、run/build、selection/labels、ledger inode/历史前缀、请求/费用/并发上限、model mode、primary/review role 与每合同 allowance；用 O_EXCL 写不可覆盖 manifest，不创建或重置账本。
- `95a6836` 将 admission 强制接入 `p6_run.py`：参数缺失无法启动；拒绝返回 2，并在账号凭据、HTTP client、运行目录和上传之前停止。预算 guard **12 passed**，P6 拒绝顺序 **1 passed**；均为临时 fixture/替身测试，没有真实模型或历史账本写入。
- 状态：**本地 launcher admission 已实施并通过定向回归；预算阻塞未解除**。该 runner 通过 HTTP 调用既有 API/Worker，本地环境检查尚不能证明外部服务实际使用相同 ledger/cap/model/build/guide/prompt；正式批次前必须补齐服务侧身份核对，不能只凭本地 manifest 启动批次。历史 592 次超 cap 未获新的授权，当前 2293/$2.32384410 不变；禁止新建 ledger 绕过。

## FL-D307 误执行截断发布器片段，把 dirty 工作区快照同步到生产（2026-10-26）

- 发现日期：2026-10-26 13:23，监督检查发布预检时误用从 `fundlex-publish.sh` 截取的 shell 片段；片段执行了同步、unit 安装和三个服务重启，随后因截断语法错误退出。
- 问题与影响：生产部署目录短暂同步了当时主工作区 dirty 快照，不能作为正式候选发布证据；API、Recall Worker、Compare Worker 和 Feishu 服务均被重启。服务当前 active，但 Compare Worker 在重启前后日志持续出现 `DatabaseError`，需单独核查其既有数据库连接问题；本次未执行真实模型或用户任务，未发现数据写入证据。
- 证据：三个主服务启动时间约 2026-10-26 13:23:51–13:23:55；`/api/capabilities` 返回 200；工作区与部署 `engine_build()` 均为 `54b226ea...`；部署文件哈希与当时主工作区 dirty 文件相同。截断片段退出码为 shell syntax error；完整脚本未以正式候选方式运行。
- 处理方法：保留生产发布前备份目录和本次状态输出，不把该版本写入正式候选；先完成 Engine/Replay/Delivery 合并、全量回归、完整候选冻结，再使用修复后的完整发布器执行发布。任何脚本验证只使用 `bash -n` 或完整命令，禁止执行截断片段。
- 状态与验证：**已确认，事故影响已止住，正式候选仍未发布**。API/Recall/Compare/Feishu active，API capabilities 200；完整用户路径和 Compare 数据库错误尚未重新验收。
- 下一步：检查部署前可用备份，必要时恢复到事故前已知版本；完成发布器完整流程的隔离演练和 rollback 反例，再进行受控候选发布。
- 变更记录：2026-10-26 新增；这是运维验证失误，独立于引擎修复和 FL-D303 发布器本身的问题。

### FL-D307 变更记录（2026-10-26 13:40）

- 已完成事故后运行态核对：API、Recall Worker、Compare Worker、Feishu 均 active；API capabilities 返回 200；Compare Worker `NRestarts=1` 且 13:23:55 后无新错误。当前部署仍是事故期间同步的 dirty 快照，未作为候选验收。
- 已将发布器改为 staging transaction：先在候选树做实际部署解释器导入和模块路径断言，生成全托管文件 manifest，再停服务、串行 schema 初始化和切换；失败保留 transaction 并恢复旧文件/unit。隔离故障演练 7/7 通过；root 发布器和部署目录脚本 SHA-256 为 `a873e4b4...`，未执行完整生产发布。

## FL-D308 Compare Worker 并发 schema 迁移导致重启窗口启动失败（2026-10-26）

- 发现日期：2026-10-26 13:23，FL-D307 截断发布器片段触发 API、Recall、Compare、Feishu 同时重启后的运行态核对。
- 问题与影响：Compare Worker 启动时在共享 MySQL `documents` 表执行 `ALTER TABLE`，与 API/Recall 进程的同一迁移竞争，首个进程收到 `DATABASE_OPERATION_FAILED` 并退出；systemd 约 4 秒后重启成功。服务最终为 active，但发布重启窗口存在短暂 Compare 不可用，且单看 `systemctl active` 会漏掉重启计数和迁移错误。
- 证据：`journalctl -u fundlex-compare-worker` 记录 13:23:51 在 `RunStore` 初始化、`store.py:377` 的 `ALTER TABLE documents ADD COLUMN selection_decision_hash` 路径失败，13:23:55 重启后 active；`NRestarts=1`，之后未见新错误。未发现本次模型调用或合同数据写入证据。
- 处理方法：候选发布前先执行一次串行 schema 初始化/迁移，再按 API、Recall Worker、Compare Worker、Feishu 顺序重启；发布器健康检查同时检查四个 unit 的启动时间、重启计数和短窗口日志，不能只看 active。若迁移竞争仍可复现，必须在代码或运维层提供单一迁移锁并保持服务 fail-closed。
- 状态与验证：**已确认，待修复/候选发布验证**。当前四个服务 active，Compare 13:23:55 后无新错误；本轮未修改 schema 逻辑，正式候选发布仍阻断。
- 下一步：在隔离环境重现并验证串行迁移；发布前保留部署树和 unit 备份，失败自动回滚并重新核对四服务。
- 变更记录：2026-10-26 新增；与 FL-D303 发布边界、FL-D307 运维误操作关联，但不把短暂重启失败误报为引擎修复成功。

## FL-D304 隔离评测账本超过历史登记的调用与费用上限（2026-10-26）

- 发现日期：2026-10-26，Evaluation agent 对固定 D01–D20 对账器和保存的隔离账本做只读复核。
- 问题与影响：历史对账记录把 `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 记为 1,701 requests、`$1.64408310`、cap 2,000/$2.00、剩余 299 requests/$0.35591690；当前同一路径只读结果为 2,293 terminal requests、`$2.32384410`，已超过登记 cap。带账本的对账器因此报告 8 项不一致，不能把该账本继续作为下一轮真实评测的预算依据。
- 证据：Evaluation agent 定向回归 **29 passed**；对账器不带 ledger 时 valid=true、20 个 case、current gate 0/20；带 `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 时发现 2,293 total（completed 2,290、failed 2、abandoned 1）。`reserved` 状态为 0，但 `reserved_cost` 累计约 `$15.45037635`，其历史语义尚未确认。
- 处理方法：保留该账本及所有历史运行证据，不重置、不删除、不把超 cap 部分抹去；在重新运行前由评测负责人解释账本增长来源和 `reserved_cost` 语义，重新登记可执行的总预算与共享 ledger。生产应用账本 `/var/lib/fundlex/model_budget.sqlite` 与该隔离评测账本分开，不混算。
- 状态与验证：**已确认，阻断下一轮真实评测**。本轮未写入该账本、未启动 `p6_run.py`、未调用真实模型或 Langfuse。
- 下一步：新预算与账本方案确认后，重新生成 protocol/run manifest；每次运行前后保存请求数、费用、状态和余额，并让对账器验证 cap。
- 变更记录：2026-10-26 新增；历史对账数值和原始账本均保留，不能用新数字覆盖旧报告。

## FL-D305 冻结 D06 标签把 ETF 联接基金错误判为排除样本（2026-10-26）

- 发现日期：2026-10-26，Evaluation agent 对冻结 labels、D06 实际 snapshot-19 报告和 `p6_score.py` 的输入分母做只读核对。
- 问题与影响：当前冻结 labels 将 D06 标为 `fund_type=etf`、`excluded=true`、`target_count=0`；snapshot-19 实际报告为 `qualification_status=eligible`、`delivery_status=incomplete`、82 targets、2 unresolved、26 HTTP、约 `$0.03190155`。旧评分器因此对 D06 得到 0 个有效目标，这反映标签分母错误，不能证明合同没有修改目标，也不能用于 snapshot-19 的业务通过结论。
- 证据：固定 selection 仍为 D01–D20/H01–H08，selection SHA `95fe8121d5f0aceb4febf9cc76a79fde78cf44f711e9a6f029b08eb6ee5643f3`；labels SHA `f120d38175c83cd1c973045d0414a69bacb9d837fc4bf24d40a8a762fe588841`。保存报告显示 D06 eligible/82/2；该问题与历史 FL-D188 的 ETF 联接基金资格结论一致。
- 处理方法：保留旧 labels、旧 score 和 snapshot-19 结果作为历史证据，不覆盖或改写；在继续正式开发集评分前，由独立业务复核重新判断 D06 资格、目标数和适用性，并冻结新 labels/hash；已读取旧 D06 预测后，原 holdout/独立性边界按评测计划重新声明。
- 状态与验证：**已确认，阻断当前 labels 作为完整 D01–D20 gate**。29 项评测工具回归通过；本轮未调用真实模型。
- 下一步：修正并独立复核 D06 标签，检查其余 19 份标签与原件/指引对账，再决定是否保留本轮开发集和是否把旧 holdout 只能称为历史留出回归。
- 变更记录：2026-10-26 新增；不因标签修正删除旧分母，修正后的分母必须生成新版本并保留 hash。

### FL-D305 变更记录（2026-10-26，两次盲读与 provisional 对账）

- 独立盲读证据分别在 `/tmp/opencode/incomplete-remediation-20261026/blind-d06-20261026T055551877754Z/`、`blind-d06-review2-20261026T061322Z/`；均未读取旧 labels/预测/评测结果或对方结果，未调用模型。
- 两者一致确认 eligible、A/C/E/F/Y，申购费组 A/Y、销售服务费组 C/E/F、非浮动管理费；22 组规则为 13 needs_change、3 already_satisfied、6 not_applicable，G05/G06/G17 边界一致。第一份展开正文/摘要实际位置给出 17 个写入目标，第二份以规则组给出 13 个需改组和 16 个适用组；这些是不同粒度，尚未批准评分口径。
- 对账路径 `d06-label-amendment-draft-20261026/review-reconciliation.json`，SHA-256 `18d8d7cc3a45b07449f18870e66bff66ac8ff6c3939b0f1acb47c96a5e92497e`。第一份 guide `45dd7746...` 是语义 document hash；第二份 `b77be53c...` 对应源 DOCX hash，第一份 evidence 也包含该源 hash；不得将两种定义混为不一致的同一字段。冻结前仍须实际重算并分别命名。
- 状态：**两份独立标注及对账完成，业务口径批准、新 labels/hash、gold 冻结均未完成**。原 labels 和历史评分保持原样，不能用盲读一致直接冒称 gold 批准。

## FL-D309 传递重叠编辑未按连通分量联合规划（2026-10-26）

- 发现日期：2026-10-26，Engine agent 审查 `RECALL_EDIT_OVERLAP` 的规划和 Joint Compose 路径。
- 问题与影响：同一物理段的 A↔B、B↔C 等传递重叠被拆开处理时，联合编辑可能不完整或取决于冲突输入顺序；复合目标的其他段落 sibling 亦有被误消费风险，导致 unresolved 或 operation 归因缺失。
- 处理方法：按物理段建立冲突连通分量，再为整组联合规划；保留所有 operation keys、obligation IDs、原始 edit 和其他段落 sibling。联合生成失败仍 fail closed。
- 证据与验证：Engine 原提交 `66f6330`、`8350513`，主线 `165dbdf`、`a872628`；定向引擎 **260 passed**，包含成功/失败关闭、输入顺序、复合 sibling；合并主线全量 **1564 passed / 52 skipped / 3 warnings / 370.31s**。
- 状态：**已实施并通过代码回归，真实合同改善待验证**。未新增真实模型调用；零模型真实原件重放正在进行，不等于正式交付。
- 下一步：对保存真实失败报告离线重放；预算与标签门解除后按同一冻结候选真实复测。
- 变更记录：2026-10-26 新增，保留历史 overlap 失败分母。

### FL-D309 变更记录（2026-10-26，D01/D04 零模型重放）

- 当前候选与历史模型 checkpoint 在真实原件上的离线产物保存于 `/tmp/opencode/incomplete-remediation-20261026/offline-engine-d01-production/current-replay/` 与 `offline-engine-d04-production/current-replay/`。执行模式明确为 `offline_checkpoint_replay`，未发生新的网络/模型请求。
- D01 为 incomplete，5 个 open obligations、11 个 blocking unresolved；Claim Replay 本身 failures=[]，但 G08/G11/G12 的 sweep/final omission 继续阻塞。G08/G12 reason 包含“已匹配/No finding”而仍被结构化登记为 finding，G11 reason 指向残余 C 类免申购费重复句；需核对结构化 outcome、实际 DOCX 和同站点 effect，不能按 reason 关键词删除失败。
- D04 为 incomplete，2 个 open obligations、6 个 blocking unresolved；G03@p52 与 G18@p182 为 `CLAIM_OPERATION_NOT_PLANNED`，只输出 working_final/working_redline。现有连通分量修复不足以证明这两份合同完整交付，需继续分析目标/site 的来源和范围；不能据此推断两个失败均由 overlap 导致。
- 状态：**离线重放完成且仍有阻塞，真实复验未完成**。原报告、分母与产物保留；后续修复必须保持错误产物 fail closed，预算/labels 恢复后真实复验。

### FL-D309 变更记录（2026-10-26，G03 真实站点复核与通用修复）

- D04 固定计划工作版的独立复核确认：G03 应绑定基本情况定义的真实结束位置（p83），不能使用释义中的 G01 p52 编辑，也不能使用 p89 的 G05 业务条款。p89 target 保留 `TARGET_SOURCE_MISMATCH` / `out_of_scope=true`；没有把 sibling 编辑提升为 G03 证明。
- 处理方法：G01/G03 拆段定义先归并到定义结束段；Claim Replay 的 superseded-site recovery 仅接受当前 operation 自己的 edit/component key，父级多 operation union 没有 component provenance 时继续 OPEN；新增真实站点、operation identity 和 sibling 借证回归。
- 证据：引擎独立复核交接文档 `/home/opencode/.local/share/opencode/worktree/29a9a9/incomplete-engine/docs/ENGINE_INCOMPLETE_ANALYSIS_20261026.md`；本工作区 `tests/test_replay_site_provenance.py` 及 append/site 回归；定向相关套件 **167 passed**，全量 **1599 passed / 52 skipped / 3 warnings / 381.29s**。
- 状态：**代码已实施并通过回归；真实 Worker/model 复验未完成**。D04 的固定计划工作版仍是离线 working artifact，不能进入正式最终合同目录或关闭 D04 gate。
- 下一步：预算、labels/gold 和候选发布条件满足后，在普通默认入口重新执行真实 D04，核对 G03 p83 的 operation/site、实际 DOCX、Claim Replay、业务复核、下载和报告哈希。

## FL-D310 Replay 使用原文判断产物、占位污染站点及 sibling 借站点（2026-10-26）

- 发现日期：2026-10-26，Replay agent 审查 effects、Obligation Ledger 和 candidate retirement。
- 问题与影响：G02/G04 的 `after_has_expected` 用 source quote 判断类别组等价，可能把实际产物缺类/增类错误判为已满足；`absent/not_applicable` 占位参与真实 site 投影会制造 `OPERATION_SITE_DUPLICATE`；候选退役先合并 sibling proof sites，可能把其他 operation 在不同站点的完成借给当前未完成目标。
- 处理方法：类别组等价读取实际 artifact；占位不参与真实 site projection，缺证明仍 OPEN；每个 operation 分别证明 candidate 的全部 physical sites。
- 证据与验证：Replay 原提交 `ddbec744`，主线 `4fa137d`；新增回归在原 `1131a8c` 复现 12 场失败，修复后新增最小集 **18 passed**、定向 **291 passed**、该线全量 **1532 passed / 80 skipped**；主线合并全量 **1564 passed / 52 skipped**。
- 状态：**已实施并通过防错回归，真实合同复测未完成**。保持 fail closed；不得把该修复当作完整率提升证据。
- 下一步：核对真实 D04 G03 报告及整合同 obligation，保持错误产物阻断；预算有效后真实复验。
- 变更记录：2026-10-26 新增，三个同一 Replay 投影审查发现集中记录于本条。

### FL-D310 变更记录（2026-10-26，G18 satisfied site 与 sweep 归因）

- D04 p182 已有语义等价的 G18 政策，但原 satisfied target 缺少 `start/end`、`resolution` 和 `segment_ok`，因此 Claim Replay 把它当作未规划物理站点；同时 effect proof 用全合同 operation edit 列表判断 source satisfaction，p1 的编辑会污染 p182 的证明。
- 处理方法：survey satisfied target 创建时重新解析真实 quote 并写入 source offsets/segment；无法解析时登记 `SURVEY_QUOTE_UNRESOLVED`、不增加 operation coverage；effect proof 改为按当前 physical site 判断是否有 own unit；sweep 证据只有同一 operation/site 的有效 proof 才能关闭 finding。新增 G18 site-local、offset、unbound-gap 和 sibling proof 回归。
- 证据：`tests/test_replay_site_provenance.py`；`fundlex/recall_pipeline.py`、`fundlex/generation/effects.py`；定向相关套件 **167 passed**，全量 **1599 passed / 52 skipped / 3 warnings / 381.29s**。未新增模型请求。
- 状态：**代码已实施并通过回归；真实合同正式复验未完成**。离线 D04 固定工作版的 G18 证据仍不等于完整交付；strict checkpoint replay 仍因缺少新上下文响应而停止。
- 下一步：与 FL-D309 相同，预算和候选条件满足后重跑真实 D04，并保留原始失败分母和本次离线证据。

## FL-D311 incomplete 的 ZIP 与 V2 选择文件被呈现为最终文件（2026-10-26）

- 发现日期：2026-10-26，Delivery agent 审查 ZIP、任务原因码、V2 结果页。
- 问题与影响：`working_final` 与 incomplete 人工选择版原先可能归入 ZIP 最终版目录，V2 任务交付状态依赖调度状态推断，且未纳入顶层 Recall unresolved 原因，用户可能误把处理成功/选择版当完整合同。
- 处理方法：工作文件/未完成选择版归入“工作文件（未完成）”；V2 展示未完成说明和工作文件下载，目标读取 status/state；任务使用后端 delivery_counts，加入顶层 unresolved code；单独展示 complete_with_exceptions。
- 证据与验证：Delivery 原提交 `f727cd6`，主线 `18b4183`；后端 **65 passed**，前端 typecheck/lint/build、**14 tests passed**；合并主线全量 **1564 passed / 52 skipped**。
- 状态：**已实施并通过回归，部署后真实 UI/下载复验待完成**。store 正式产物校验门未修改，incomplete 不提升状态。
- 下一步：候选发布后验证登录、工作文件 ZIP、授权/跨账号下载、Review selected 与报告/哈希。
- 变更记录：2026-10-26 新增，历史工作文件不回写为最终合同。

本次补录来自原件阅读、用户讨论及三 agent 交叉审查。除明确说明外，下列处理方法属于设计结论或建议，尚未实施、评测或发布。记录不是问题已解决的证明，也不替代专题报告。

## 记录约定

- 稳定编号：`FL-D001` 起递增，不改号、不复用。
- 状态：待分析、待确认、待实现、待验证、阻塞、已解决。是否获用户确认单独写明。
- 条目字段：发现日期、问题与影响、证据、处理方法、状态与验证、下一步、变更记录。
- 同一问题更新原条目；重大结论变化注明日期和原因，不覆盖历史。

## FL-D262 测试环境发布缺少专用发布器导致环境边界与验收证据容易混淆（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：现有 `tools/deploy/publish_workspace.sh` 及其 root 发布器固定目标为生产目录 `/opt/fundlex-recall-first` 并重启生产服务；当前 Compare 候选需要发布到隔离测试目录 `/opt/fundlex-test`，若直接调用生产发布器会覆盖生产环境。测试 API 的健康端点也受密码认证保护，未登录请求返回 401，若将其当作服务健康失败会误判发布结果。
- 证据：测试 systemd 单元 `/etc/systemd/system/fundlex-test-api.service`、`fundlex-test-worker.service`、`fundlex-test-compare-worker.service` 明确使用 `/opt/fundlex-test`，API 监听 `127.0.0.1:8110`；生产服务仍监听 `127.0.0.1:8010`。发布前备份为 `/tmp/opencode/fundlex-test-publish-20261025-150535/test-deployment-before.tgz`，发布目录与工作区哈希核对文件位于同目录。未登录测试 API `/api/capabilities` 为 200，而 `/api/health` 和 `/api/auth/me` 为预期 401。
- 处理方法：本次使用 root 权限执行受控增量同步，只覆盖测试目录的 `fundlex/`、`frontend/`、`guides/`、`rules/`、`tools/`、`docs/`、`tests/` 和必要项目文件，保留测试环境数据与虚拟环境；随后只重启三项 `fundlex-test-*` 服务。通过首页引用的 JS/CSS 逐个 HTTP 200、Compare 模块导入、服务 active 状态和真实登录后的 `/compare` 浏览器 smoke 验收发布结果。临时验收账号在完成后删除，未创建任务、未新增模型调用。
- 状态与验证：**已解决（测试环境发布已验证）**。三项测试服务均 active；工作区与 `/opt/fundlex-test` 的 Compare Python 文件和当前入口静态资源 SHA-256 一致；390px/1440px Compare 页面无横向溢出，页面错误、控制台错误、静态 404 和 API 404 均为 0。生产 API/Worker 仍 active，生产目录和 8010 未因本次发布改变。浏览器证据为 `/tmp/opencode/fundlex-test-publish-20261025-150535/browser-smoke.json`。
- 下一步：如测试环境发布成为固定流程，应增加参数化测试发布器或受控 systemd 发布入口，明确目标目录、服务集合、认证健康检查和回滚备份，避免继续依赖手工命令。
- 变更记录：2026-10-25 新增；本次仅发布到隔离测试环境，未发布生产，未执行真实 Compare 合同任务或模型调用。

## FL-D264 V1 默认入口恢复后的测试前缀资源与环境隔离（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：V2 React 构建曾作为默认首页，导致用户熟悉的 V1 hash 工作台、任务入口、指引配置、Review 和 Compare 入口不再作为默认界面；测试环境通过 `https://fundlex.club/test/` 暴露时，V1 的绝对 `/static` 与 `/api` 路径还可能请求生产根路径。
- 证据：本地 V1/V2 浏览器回归 `FUNDLEX_BROWSER_TESTS=1 PYTHONPATH=. .venv/bin/python -m pytest tests/browser/test_workbench.py tests/browser/test_frontend_v2.py -q --maxfail=3` 为 **37 passed**；定向 API/入口回归为 **13 passed / 1 既有 Starlette/httpx warning**。测试入口 `/test/` 由 Nginx 去掉前缀后转发到 `127.0.0.1:8110`，公网返回的 V1 HTML 引用 `/test/static/...`，`/test/api/capabilities` 返回 200。
- 处理方法：`FUNDLEX_FRONTEND_VERSION` 默认设为 `v1`，显式设为 `v2` 才返回 Vite 入口；V1 `/compare`、`/tasks`、`/tasks/new`、`/guides` 等深链重定向到 hash 页面；`FUNDLEX_FRONTEND_BASE_PATH` 为测试入口注入资源前缀，V1 `app.js` 统一给 API fetch/XHR 加此前缀。保留测试 `api.py` 已有的健康检查、运行隔离和 `/test/static` 挂载改动，只重启 `fundlex-test-api`。
- 状态与验证：**已解决（V1 测试页面已发布并验证）**。`https://fundlex.club/test/` 登录成功后，任务总览、新建任务、指引配置、合同对比四个入口均通过；1440/768/390px 的 `scrollWidth` 分别等于视口宽度，无横向溢出；静态 404、API 404、页面错误均为 0。登录前 Compare 自动探测产生 1 个预期 401，登录后接口返回 200。测试 API、普通 Worker、Compare Worker、生产 API、生产 Worker 均 active；临时 smoke 用户与会话已删除。公网验收证据：`/tmp/opencode/fundlex-v1-public-smoke-20261026/browser-smoke.json`；测试发布前备份：`/tmp/opencode/fundlex-v1-restore-20261026/test-frontend-before.tgz`。
- 下一步：若继续使用 `/test/`，保留 `fundlex-test-api.service.d/frontend-v1.conf` 中的 `FUNDLEX_FRONTEND_VERSION=v1` 与 `FUNDLEX_FRONTEND_BASE_PATH=/test`；如迁移到独立测试域名，应同步清空前缀并重新做登录和静态资源验收。V1 页面验收不替代普通合同真实 Worker/model/DOCX 交付、D01–D20 gate、G06 和 selected artifact 的既有未决项。
- 变更记录：2026-10-26 新增；本次仅发布隔离测试环境，未调用生产发布器，未创建合同任务，未新增模型调用。`test.fundlex.club` 的 TLS 握手当前失败，因此最终证据使用已可用的 `https://fundlex.club/test/`。

## FL-D244 Frontend V2 统一会话失效与 Review/任务状态边界

- 发现日期：2026-10-25。
- 问题与影响：共享请求已把 HTTP 401 转成错误，但上传 XHR、下载和 mutation 没有统一清理认证、请求缓存和 workspace 的事件；Review 决策刷新丢失，pending 时生成按钮仍可点击；移动端正文/修订面板定位不会双向切换；任务详情从当前分页合同猜测 Worker 阶段，ZIP 按任务 completed 状态禁用。
- 证据：Frontend V2 Round 1 审计；`frontend/src/api/client.ts`、`frontend/src/pages/Review/ReviewPage.tsx`、`frontend/src/components/document/SplitPane.tsx`、`frontend/src/pages/TaskDetail/index.tsx`；本轮 `npm run typecheck`、`npm run lint`、`npm run build` 和 `tests/test_tasks_api.py` 通过。
- 处理方法：401 在 request/text/download/upload 共享错误解析路径中发出 `fundlex:session-expired`，auth 清 session，已有 auth 事件清 query，workspace 清选中对象；Review draft 使用 user/task/document/revision fingerprint 绑定，pending 直接禁用生成并保留服务端 fail-closed gate；SplitPane 接受受控面板并由两侧定位回调切换；任务摘要提供跨全部合同聚合的 phase 和 downloadable artifact count，CSV 复用当前 tab/status 参数，ZIP 以可下载 artifact count 为门禁。
- 状态与验证：待验证；代码已实施，当前静态检查和任务 API 回归通过，浏览器 401、Review 刷新/旧 payload 失效、移动端双向定位以及真实 Worker/DOCX 交付尚未验证。Full-Stack Test Environment 仍按现有记录阻塞。
- 下一步：补充前端单元/组件/浏览器回归，执行 390px Review 流程；随后在真实测试环境验证 Worker/model/DOCX 交付。
- 变更记录：2026-10-25 新增，保留 Round 1 发现和未验证边界。

## FL-D245 React server state 自研缓存缺少统一失效语义

- 发现日期：2026-10-25。
- 问题与影响：React V2 原先使用自研 Map/in-flight cache，query key、轮询、清缓存和失效语义分散；Review、任务轮询和登录切换容易出现旧 server state。该问题与 FL-D244 的业务边界修复相互关联，但独立记录架构迁移。
- 证据：迁移前 `frontend/src/api/hooks.ts` 的 Map cache；迁移后 `frontend/src/api/queryClient.ts`、`frontend/src/main.tsx`、`frontend/package.json`；`npm run typecheck`、`npm run lint`、`npm run build`、7 项 React 浏览器测试和 `tests/test_tasks_api.py` 通过。
- 处理方法：安装 TanStack Query 5，使用共享 QueryClient、结构化 query keys、`refetchInterval` 轮询和关闭自动重试；auth-cleared、auth-changed、session-expired 清理 QueryClient；保留页面既有 query state 接口并映射现有 prefix invalidation 调用。
- 状态与验证：待验证；自研 cache 已移除，mutation wrapper 已统一封装并接入主要写操作，静态/浏览器隔离测试通过；专门 mutation/401 组件证据、真实 Worker/model 任务和 Full-Stack Test Environment 尚未验证。
- 下一步：补专门 mutation/401/Review payload 组件与浏览器回归，随后在真实测试环境验证普通任务与 Compare 交付链路。
- 变更记录：2026-10-25 新增；不把 7 项壳层浏览器测试写成真实业务交付。
- 原件段落编号 `p` 为本次阅读提取器从0开始的序号，非Word页码、非应用内部地址。

### FL-D245 状态更新（2026-10-25）

- 变化：TanStack Query mutation wrappers 已实现并接入任务上传/封存/暂停恢复、Review 选择版生成、指引启用/上传/解析和 Compare 创建/上传/封存；Compare 已迁移到 React `/compare` 路由，并由 FastAPI 深链入口返回 React 应用。
- 验证：`npm run typecheck`、`npm run lint`、`npm run build` 通过；React 浏览器套件 7 passed；Compare/认证/任务/指引 API 回归 39 passed；`git diff --check` 通过。
- 当前状态：待验证。仍缺 dedicated mutation/401/Review payload 组件证据、真实 Compare Worker 端到端证据，以及 Full-Stack Test Environment 的普通 Worker/model/DOCX 交付验收。上述测试不改变当前真实交付阻塞状态。
- 下一步：补充前端组件/可访问性/390px 专项回归；随后在同一真实测试环境执行 Compare 和普通合同完整用户路径。

## FL-D001 长合同规模与页数元数据失真

- 发现日期：2026-10-14。
- 问题与影响：合同长，单请求或按页估算容易超上下文；DOCX的页数元数据可能明显失真。
- 证据：514份提取文本39257—109150字符；新城吾悦目录显示摘要从118页开始，app.xml却为4页。见 [原件阅读](CONTRACT_AND_GUIDE_READING_20261014.md)。字符统计不是token或实际渲染页数。
- 处理方法：按实际token容量拆分；保留所有原文地址、窗口和未完成任务；不静默截断，不依赖页数元数据规划调用。
- 状态与验证：待实现；本轮已验证文本统计与目录差异，未验证新长文链路或成本。
- 下一步：测量长合同token、分页、截断和跨窗口完整性。
- 变更记录：2026-10-14补录。

## FL-D002 章、物理段落与业务条款边界不一致

- 发现日期：2026-10-14。
- 问题与影响：整章过大；按物理段落处理会截断业务句或误改其他事项。
- 证据：品质回报p253—254促销句、p831—832支付句跨段；汇誉p247—248跨段并合入下一项；聚富p470、p472同段含多项业务。
- 处理方法：代码提取物理结构与精确地址；模型识别业务子节及完整逻辑条款。跨段语义修改优先拆成多个文字操作；删段、合段或改变表格结构单独验证。
- 状态与验证：待实现；用户已认可讨论方向，原件现象已读取，编辑能力未验证。
- 下一步：跨段句、同段多项及编号保留专项验证。
- 变更记录：2026-10-14补录。

## FL-D003 收费类别不能按字母或币种推断

- 发现日期：2026-10-14。
- 问题与影响：A/C惯例、类别或代码计数可能导致错误分组、漏改或误改。
- 证据：上海清算所p155、p779中A/D收申购费、C收销售服务费；QDII全球科技p134、p179—184有A/C与币种两维。
- 处理方法：模型建立类别、费用、渠道、持有期限关系并附来源证据；按指引授权的收费关系实例化槽位。
- 状态与验证：待实现；原件关系已读取，未验收新画像模型。
- 下一步：不同类别字母、币种和混合收费测试。
- 变更记录：2026-10-14补录。

## FL-D004 关键词相同不表示当前资格或费用机制相同

- 发现日期：2026-10-14。
- 问题与影响：ETF未来转换条件、投资范围或浮动管理费名称可能被误当成当前分类，造成整份漏处理。
- 证据：上海清算所p164是未来ETF联接转换；新城吾悦为封闭REITs且费用涉及经营；产业优选p70、p827—841为投资者持有期与收益关联管理费。
- 处理方法：模型结合产品事实、条件时态和具体收费机制判断；代码核对证据地址，不用关键词直接排除。
- 状态与验证：待实现；例证已读取，资格错排率未评测。
- 下一步：将错误排除纳入端到端评测。
- 变更记录：2026-10-14补录。

## FL-D005 正文与摘要不是逐字、逐目标对应

- 发现日期：2026-10-14。
- 问题与影响：按字符串相等或正文目标数量复制摘要，会漏掉变体或新增不存在的目标。
- 证据：品质回报正文p825—834、摘要p1281—1290；QDII正文p1018—1025有用途与范围，摘要p1518—1524未包含对应用途条款。
- 处理方法：两处分别盘点，建立业务关联；要求语义一致，不强求数量及措辞相同；强依赖修改联合规划。
- 状态与验证：待实现；原件差异已读取，联合修订未验证。
- 下一步：摘要省略、跨段和同文不同位置用例。
- 变更记录：2026-10-14补录。

## FL-D006 已符合条款可能跨段且不同于参考串

- 发现日期：2026-10-14。
- 问题与影响：逐字旧文/模板匹配会拒绝或重复追加已满足要求的条款。
- 证据：产业优选p132已有直销与持有期规则，p1069—1070及摘要p1487—1488已有返还清算要求，尾部括注换段。
- 处理方法：读完整条款，按要求要素判断已满足；固定政策文案以指引要求为准；避免以重复添加充当召回成功。
- 状态与验证：待实现；原文已读取，语义满足判定未评测。
- 下一步：已符合变体与混合旧新内容验证。
- 变更记录：2026-10-14补录。

## FL-D007 仅空结果或异常触发补扫会漏掉部分目标

- 发现日期：2026-10-14。
- 问题与影响：找到一处后其他位置仍可能遗漏；映射与修订模型共同遗漏时没有异常信号。
- 证据：C-R流程评审及三agent交叉讨论，见 [审查记录](MULTI_AGENT_DESIGN_REVIEW_20261014.md)。这是设计缺口分析，不是已测出的漏改率。
- 处理方法：已有命中的规则也做覆盖核查；三agent建议最终默认一次分块全文轻量查漏，深度修改集中于业务子节。
- 状态与验证：待确认；用户此前质疑全文读取必要性，最终默认轻扫尚未明确确认，也未进行成本收益评测。
- 下一步：统一默认策略，比较条件补扫与默认最终轻扫。
- 变更记录：2026-10-14补录，明确区分agent建议与用户决策。

## FL-D008 未发现不能写成确无，缺失不自动授权补写

- 发现日期：2026-10-14。
- 问题与影响：模型漏搜可能被包装为无需处理；不存在示例旧文不一定需要新增。
- 证据：指引区分追加、条件替换删除和单多类别分支；C-R方案将一次空补扫写成确无。
- 处理方法：分别记录未发现、不适用、已满足、缺失义务或未知；新增须有具体指引依据。
- 状态与验证：待实现；设计建议，未评测。
- 下一步：建立业务义务标签与状态定义。
- 变更记录：2026-10-14补录。

## FL-D009 核心词或全局引文唯一性成为召回门槛

- 发现日期：2026-10-14。
- 问题与影响：真实条款无关键词、或正文摘要同文时，被机械拒绝。
- 证据：C-R核心词校验与唯一性要求；原件存在重复及变体。
- 处理方法：以稳定块地址加引文绑定目标，代码核对对应位置；业务匹配由模型判断；地址错误提供真实原文重新定位。
- 状态与验证：待实现；新定位流程未验证。
- 下一步：同文多位置、无关键词和引文修复测试。
- 变更记录：2026-10-14补录。

## FL-D010 重叠规则不能用固定优先级覆盖

- 发现日期：2026-10-14。
- 问题与影响：先执行一条可能吞掉其他目标或留下矛盾。
- 证据：销售服务费同时涉及保留公式、替换支付、删除用途及新增要求。
- 处理方法：模型组织联合修订单元，同时满足关联规则；代码识别物理重叠并执行整合方案。
- 状态与验证：待实现；联合规划未实测。
- 下一步：多规则同段、插入替换冲突及关联原子性验证。
- 变更记录：2026-10-14补录。

## FL-D011 复核分歧不能只标记而跳过修复

- 发现日期：2026-10-14。
- 问题与影响：事实或业务错误会直接进入接受修订版；过度回滚又会丢失独立正确修改。
- 证据：用户明确选择自动修复与仲裁，无法解决才未完成；C-R提出核验不过照改。
- 处理方法：补上下文、具体错误反馈、修复与仲裁；仍未解决仅输出明确标记的工作文件，保留无关已核验修改。
- 状态与验证：待实现；处理方向已获用户确认，未验证自动修复质量。
- 下一步：完善问题类型、关联范围及状态契约。
- 变更记录：2026-10-14补录。

## FL-D012 技术重试、业务修复与补扫应分开

- 发现日期：2026-10-14。
- 问题与影响：原样重试不能解决缺上下文、截断或业务错误；耗尽重试不代表条款不存在。
- 证据：本轮用户讨论及草案第12节。
- 处理方法：临时技术故障退避重试；截断分页/拆分；定位错误重定位；业务错误有界修复与仲裁；预算/余额等阻塞保留断点。三次/三轮为当前建议默认值，非已实测最优值。
- 状态与验证：待实现；设计尚未完成真实故障测试。
- 下一步：验证分页、断点、重复失败和预算中断。
- 变更记录：2026-10-14补录。

## FL-D013 在修改版上叠加会重复追加并污染修订

- 发现日期：2026-10-14。
- 问题与影响：多轮位置漂移、重复新增、修订嵌套，难追溯原件到最终变化。
- 证据：用户询问重新执行基于哪份文档；讨论确定从原件重生成。
- 处理方法：模型参考当前产物及原件修复完整方案；代码从原件重放；复用未受影响文案，不重复生成无关修改。
- 状态与验证：待实现；方案已提出，未做新链路多轮验证。
- 下一步：补入主设计并验证两轮增改、删改与去重。
- 变更记录：2026-10-14补录。

## FL-D014 原件与产物需要双地址映射

- 发现日期：2026-10-14。
- 问题与影响：复核发现的问题位于产物，不能直接用新字符坐标修改原件。
- 证据：工程agent交叉审查。
- 处理方法：产物范围关联来源范围或生成操作；原文残留新增来源目标，生成错误修复原操作，缺失义务定位来源插入锚点；回查实际文件。
- 状态与验证：待实现；映射设计未实现。
- 下一步：跨段、删除、插入和重复文字映射夹具。
- 变更记录：2026-10-14补录。

## FL-D015 新事实会使旧方案及复核结论失效

- 发现日期：2026-10-14。
- 问题与影响：收费类别或机制更正后，保留的旧修改可能不再适用；新组合不能复用旧文件最终授权。
- 证据：三agent交叉审查。
- 处理方法：记录事实、规则、目标及正文摘要依赖；变化使相关结果失效；重大画像变动检查未声明影响；最终新文件重新验收。
- 状态与验证：待实现；依赖失效与新组合测试未运行。
- 下一步：更正收费事实后保留无关方案、重判相关方案的测试。
- 变更记录：2026-10-14补录。

## FL-D016 从原件重建仍需防过期提交与缓存

- 发现日期：2026-10-14。
- 问题与影响：迟到模型响应或旧Worker可提交旧方案，源地址不漂移也不能避免版本污染。
- 证据：工程审查，现有队列有租约等能力，但新业务版本契约尚待明确。
- 处理方法：每轮固定源、指引、事实、方案版本；临时产物及幂等提交；只接受当前版本，缓存按依赖复用。
- 状态与验证：待实现；不据既有队列测试推断新流程已验收。
- 下一步：过期响应、并发修复及缓存失效验证。
- 变更记录：2026-10-14补录。

## FL-D017 结构可读与可写必须分开

- 发现日期：2026-10-14。
- 问题与影响：过滤不可编辑区域会把应改目标隐藏，误标完整。
- 证据：工程与召回agent交叉讨论；合并表格、文本框、内容控件等结构边界。
- 处理方法：所有可读内容纳入发现；无法读取和无法编辑分别列缺口；编辑失败进入未完成，不冒充不适用。
- 状态与验证：待实现；复杂部件提取和结构能力未全面验证。
- 下一步：部件清单、不可读/不可写目标测试。
- 变更记录：2026-10-14补录。

## FL-D018 Word逐条回退不保证任意组合业务一致

- 发现日期：2026-10-14。
- 问题与影响：正文摘要、类别和相关条款分开接受拒绝后可能矛盾。
- 证据：工程与评测agent交叉审查。
- 处理方法：标识联合取舍的关联修改；验证接受全部等价final、拒绝全部恢复source内容，声明允许的必要元数据差异；检查编号、域、书签等，不承诺任意部分回退都一致。
- 状态与验证：待实现；新复杂修订与渲染未验证。
- 下一步：关联回退、编号书签及修订等价验证。
- 变更记录：2026-10-14补录。

## FL-D019 指引解析漏组会成为全链路共同盲点

- 发现日期：2026-10-14。
- 问题与影响：解析漏掉条件或业务组，定位、修改、审计可能共同忽略该要求。
- 证据：来源指引有红色说明、同前述引用及互斥分支；召回agent提出独立来源对账。
- 处理方法：独立读取来源期望要求，再对照解析规则；按业务组、新旧文、条件、引用及分支核查；指引解析与合同修改分别验收。
- 状态与验证：待实现；自定义指引解析未实现。
- 下一步：同结构不同内容、漏组、引用、格式与分支测试。
- 变更记录：2026-10-14补录。

## FL-D020 指引配置与任务绑定需分离

- 发现日期：2026-10-14。
- 问题与影响：任务页上传指引增加操作负担，切换指引可能改变正在运行任务。
- 证据：用户明确要求默认内置，上传切换仅配置页。
- 处理方法：任务页只上传合同，使用当前指引；配置页上传、查看、启用或恢复内置；上传不自动启用，任务固定绑定版本；来源和规则动态解析，不固定22动作。
- 状态与验证：待实现；用户要求已确认，设计文档已更新，功能未实现。
- 下一步：版本绑定、恢复默认及用户隔离验证。
- 变更记录：2026-10-14补录。

## FL-D021 覆盖、执行率与业务正确完成率不同

- 发现日期：2026-10-14。
- 问题与影响：读取完或执行过不证明找全/改对；137目标95%执行仍允许6处漏改。
- 证据：C-R指标讨论及评测agent审查。
- 处理方法：分开结构覆盖、规则处置覆盖及独立标签业务召回；主指标采用目标正确完成及整合同全完成，纳入错排、未知和结构目标；错误程度分别统计。
- 状态与验证：待实现；未建立或运行新方案完整独立评测。
- 下一步：冻结目标/义务标签，独立裁定争议，不反向改旧gold。
- 变更记录：2026-10-14补录。

## FL-D022 调用数和性能不能由理想流程推断

- 发现日期：2026-10-14。
- 问题与影响：约8次只是映射与按章盘点，不含拆分、生成、审计和重试；同模型复核仍有共同盲点。
- 证据：多agent审查，暂无新方案性能证据。
- 处理方法：比较条件补扫、最终全文轻扫、额外规则视角和不同模型；报告新增正确目标、错改、费用与p50/p95耗时，长合同单独统计。
- 状态与验证：待验证；策略需先确认，未发起真实模型调用。
- 下一步：预登记质量/预算及可比成本消融实验。
- 变更记录：2026-10-14补录。

## FL-D023 设计文件与最新讨论需要统一

- 发现日期：2026-10-14。
- 问题与影响：草案强制原件/产物全文扫描，口头调整为相关子节深读及必要时全扫；原件重生成和双地址也未完整并入主草案。
- 证据：[设计草案](superpowers/specs/2026-10-14-model-first-complete-revision-design.md) 与 [多agent讨论](MULTI_AGENT_DESIGN_REVIEW_20261014.md)。
- 处理方法：先明确最终扫描策略，把已确认的新执行原则同步到主方案，未确认建议保留状态；旧记录保留历史说明。
- 状态与验证：待确认；本次只建立集中记录，尚未重写主设计。
- 下一步：收敛最终设计并交叉核对流程、状态和术语。
- 变更记录：2026-10-14补录。

## FL-D024 诊断或隔离评测不能代替真实端到端交付

- 发现日期：2026-10-14。
- 问题与影响：最终只交诊断、评测结果或脚本生成文件，无法证明用户默认任务流程能够修改合同并下载真实交付物。
- 证据：用户明确要求“不要总是用测评模式……最后能按照用户真实的情况完成端到端交付”。隔离评测可以生成修改文件，但仍与正式任务交付不同。
- 处理方法：最终验收沿工作台身份入口、当前指引、合同上传、任务队列、真实模型和Worker、DOCX修改、产物复核、结果查看和授权下载完成。使用确有应改目标的真实合同核对实际差异、修订、报告与下载哈希；正常交付无需隐藏开发开关；发布条件正常完成，不手改标志绕过。
- 状态与验证：待实现；用户要求已明确确认，已写入AGENTS.md及目标设计；新方案端到端尚未实施或验收。
- 下一步：实施完成后运行真实用户路径，保存产物和验收证据；任何外部阻塞明确记录并续办。
- 变更记录：2026-10-14新增，作为最终交付验收要求。

## FL-D025 完整交付不能遗漏前端或云端真实验收

- 发现日期：2026-10-14。
- 问题与影响：新agent若只做引擎/API或本地脚本，用户仍无法使用整个项目；旧文档有冲突，当前未跟踪文档也不会随同名分支自动传到另一设备。
- 证据：用户要求详细开发接续文档并强调前端一起完成，提供云主机地址；本轮核对HEAD为3ed4e96、分支codex/fundlex-recall-first，新增文档尚未提交。
- 处理方法：建立 [整合开发文档](FULL_PROJECT_DEVELOPMENT_HANDOFF.md) 与 [启动prompt](NEXT_AGENT_FULL_DELIVERY_PROMPT.md)，明确前端每页、后端契约、实施顺序、动态指引、真实模型与文件、云部署及验收；AGENTS/README/历史设计加接续指向。主机8.155.130.168、用户root记录但密码不持久化；OS/资源/服务与部署尚需核实。
- 状态与验证：待实现；完整范围已获用户明确要求，接续文档已编写并经两名无聊天背景agent独立试读、修订；本轮未部署、未实现新链路。
- 下一步：完成试读修订，接续agent按实施阶段推进，核实服务器和安全凭据及授权模型预算，保存真实完整交付证据。
- 变更记录：2026-10-14新增；随后依据独立试读补齐发布启动、用户配置权限、中断恢复、双地址与epoch以及正式访问方式，未将文档完成冒称项目完成。

## FL-D026 首次发布证据与普通任务门禁可能循环依赖

- 发现日期：2026-10-14。
- 问题与影响：未发布不能正式跑任务，而发布又需真实任务证据，可能把新agent卡在永久评测模式；普通用户自定义指引没有验证入口也无法启用。
- 证据：接续文档独立试读engine与frontend均指出发布判据/启动流程缺失。这是设计可实施性问题，不是现有代码复现实测。
- 处理方法：独立qualification通道经正常队列/真实模型/实际修改产生明确验证工作文件；配置页可发起用户私有候选验证，普通合同提交页不混入验证。运行前冻结发布政策/标签/阈值，受控服务记录证据并发布；随后另跑普通默认正式端到端。内置与私有版本权限分开，不手改标志。
- 状态与验证：待实现；已补入整合文档§10及P5/P6，未实现发布服务或真实验证。
- 下一步：P2固定机器可执行政策及配置入口，P6运行证据与正式复验。
- 变更记录：2026-10-14试读发现并补充设计；第二轮试读收紧发布前qualification证据与发布后正式验收措辞，避免再次形成循环。

## FL-D027 可恢复停止、最终未完成与工作文件需区分

- 发现日期：2026-10-14。
- 问题与影响：预算耗尽被直接completed/incomplete会妨碍恢复；未审计新组合可能作为已核验工作文件泄露。
- 证据：engine试读指出暂停与未完成口径冲突，主文原有原则尚不够精确。
- 处理方法：可恢复停止paused+blocked_reason并持久化待办/epoch/轮次/账本；不无限自动重试。上限或用户结束才结算。工作文件必须来源和事实有效且对应实际组合核验成立；重新生成子集也要验，无预算则待恢复；无有效文件仅报告not_generated，不将候选文件冒称已核验。
- 状态与验证：待实现；整合文档§7E补契约，未实测中断恢复。
- 下一步：暂停恢复、失效事实、新组合与下载门禁专项。
- 变更记录：2026-10-14试读发现并补充设计；第二轮试读统一§7E/§7F的预算暂停及业务上限结算口径。

## FL-D028 云端身份和访问方式不能混淆

- 发现日期：2026-10-14。
- 问题与影响：SSH root与Web账号不同；只有IP和未配置TLS时可能将明文公网登录误称生产入口，或把SSH密码复制进文档。
- 证据：用户提供服务器信息；独立frontend试读要求明确访问安全条件，当前OS/服务/TLS未核实。
- 处理方法：根登录仅部署管理，Web账号单独安全创建；凭据不写项目文件，用户随后授权本机Windows用户级环境变量保存（见FL-D029）。生产password/上传/下载经HTTPS或安全隧道验收，无TLS先交付已验证隧道方法，公网要求缺条件如实列待办。
- 状态与验证：待实现；整合文档§15已明确，未连接服务器或验证入口。
- 下一步：安全获取访问能力，核实服务，部署并记录实际地址和访问方式。
- 变更记录：2026-10-14试读后补充工程默认约束。

## FL-D029 新agent不能仅凭主机地址自动取得认证信息

- 发现日期：2026-10-14。
- 问题与影响：密码仅在旧聊天中，新agent无历史时无法连接；已运行进程也可能未继承后来设置的用户变量。
- 证据：用户明确询问是否写环境变量并再次提供凭据，要求新agent可连接。
- 处理方法：按用户授权保存FUNDLEX_SSH_HOST、FUNDLEX_SSH_USER、FUNDLEX_SSH_PASSWORD到本机WindowsUser作用域；新agent显式读取并传入连接子进程，文档只记录变量名与无秘密加载片段。只验证存在性，不打印密码或写仓库；换机器/用户需另行安全提供。
- 状态与验证：已解决（本机接续凭据配置）；三个WindowsUser变量写入后存在性均True，未输出密码。SSH实际连通性与服务器状态尚未验证，不能将此项配置完成当作部署验收。
- 下一步：部署agent安全读取并认证，核实远端OS/资源/服务，不因变量存在宣称已登录。
- 变更记录：2026-10-14按用户补充要求新增，未进行服务器部署。

## FL-D030 长任务上下文需在60%前主动压缩或交接

- 发现日期：2026-10-14。
- 问题与影响：接近耗尽才压缩容易遗漏用户要求、未提交文件、进程及模型预算，导致接续重复工作。
- 证据：用户明确要求提醒新agent做好上下文控制，在60%之前压缩。
- 处理方法：50%开始整理，60%前完成支持的压缩/交接；先保存文件并更新ACTIVE_HANDOFF、实施计划及问题记录；记录状态、证据、阻塞、预算与下一动作，不记录秘密；不可用或不可观测时保守整理并如实说明，不虚构能力。
- 状态与验证：待验证；已写入AGENTS、接续文档及启动prompt；未来开发运行中的压缩执行尚未发生。
- 下一步：实施agent持续监控并按阶段维护断点，主agent与子agent均执行。
- 变更记录：2026-10-14按用户要求新增。

## FL-D031 缺少真实修改评测到优化复测的明确闭环

- 发现日期：2026-10-14。
- 问题与影响：只有专项检查或验收清单，没有批量真实修改、指标归因和优化复测流程；同批反复调优易高估质量。
- 证据：用户明确提出用20—30份合同真实修改、计算指标并根据结果优化。
- 处理方法：新增 [评测与优化计划](EVALUATION_AND_OPTIMIZATION_PLAN.md)，推荐28份20开发/8留出，独立标签冻结、实际文件评分，按漏改/事实/生成/执行/审计原因修复、局部复测与全回归，冻结后留出验收；同步P6、项目规定和prompt，保留各轮版本和失败结果，预算另登记。
- 状态与验证：待实现；范围与优化要求已获用户明确提出，样本拆分为建议；本轮只补执行文档，尚未选样本、冻结标签或运行新方案评测。
- 下一步：接续agent实现评分和运行工具，冻结数据/口径/预算后执行，形成实际指标及优化对比，继续正式交付。
- 变更记录：2026-10-14按用户补充新增。

## FL-D032 docx.py 只支持段内单段编辑，跨段/段级操作需拆分或扩展

- 发现日期：2026-10-14（接续 agent 代码基线调查）。
- 问题与影响：`fundlex/docx.py` 的编辑能力为 run 级：编辑范围必须位于同一段落同一 `TextSegment` 内，不可跨段、不可插入/删除段落、不可改表格结构、不可编辑书眉/脚注/文本框。若新引擎直接规划跨段整句替换会被 `EDIT_CROSSES_BARRIER` 拒绝。
- 证据：`validate_edit_plan` 的 `EDIT_CROSSES_BARRIER`/`EDIT_OVERLAP_OR_ADJACENT` 校验；`_apply_one` 仅处理同段连续 run；测试 `tests/test_docx.py`、`tests/test_docx_structures.py`。
- 处理方法：新引擎按整合文档 §7C“跨段文字优先保持原段落结构，多个精确操作构成一个单元”实现：跨段语义拆为多个段内精确操作。段级插入/删除、表格结构修改作为独立能力另行验证后再启用。
- 状态与验证：已核实（代码事实）；新引擎拆分实现待 P3 验证。
- 下一步：P3 用真实跨段合同（品质回报/汇誉/聚贤）验证拆分方案的实际效果；如确需段级能力，扩展 docx.py 并补专项验证。
- 变更记录：2026-10-14 新增。

## FL-D033 仓库无通用指引 DOCX 解析器，旧编译为硬编码索引

- 发现日期：2026-10-14（接续 agent 代码基线调查）。
- 问题与影响：`rules/compile_catalogue.py` 用硬编码段号从指引 DOCX 抽取 22 条动作；`rules/compile_v2.py` 只读 `rules_v1.json`，不读 DOCX。新引擎要求“指引解析独立核验漏组、条件及引用”“不固定22动作”，不能复用旧编译。
- 证据：compile_catalogue.py L12—124 硬编码 `add(...)` 段号；compile_v2.py 无 DOCX 读取；全仓库无“指引→分组”通用解析。
- 处理方法：新建 `fundlex/guide.py`：代码提取段落/编号/颜色 → 模型分组（guide_parse）→ 独立核验（guide_verify）→ 修复重核；结果冻结为 `guides/builtin_guide_v1.json`。解析质量与合同修改质量分别用独立标签验收（FL-D019）。
- 状态与验证：待实现（P2）。
- 下一步：P2 实现并跑通内置指引解析 + 核验；登记解析结果 hash。
- 变更记录：2026-10-14 新增。

## FL-D034 v2 链路无 checkpoint 复用，新引擎需显式绑定

- 发现日期：2026-10-14（接续 agent 代码基线调查）。
- 问题与影响：`jobs._default_processor` 只把 checkpoint_dir 传给 v1 `process`；`process_v2` 未绑定 checkpoints，v2 重复调用无缓存复用。新引擎若同样不绑定，重试/多轮将重复消耗真实预算。
- 证据：jobs.py L29—36/L131—135；v2_pipeline.process_v2 无 `bind_checkpoints` 调用；checkpoints.py 仅 v1 使用。
- 处理方法：新引擎在 Worker 与评测运行器中显式 `bind_checkpoints(document_checkpoint_dir, dependencies)`，依赖包含源/指引/规则哈希/解析与 prompt 版本/模型传输指纹；不缓存失败与不合格回答。
- 状态与验证：待实现（P3/P5）。
- 下一步：集成时验证缓存命中、失效与不误用。
- 变更记录：2026-10-14 新增。

## FL-D035 模型账本为累计上限，长期运行会耗尽且费率默认虚高

- 发现日期：2026-10-14（接续 agent 代码基线调查）。
- 问题与影响：`ModelBudget.reserve` 按账本文件内全部历史请求累计判断 `max_requests`/`max_cost_usd`，工作台长期运行到上限后所有任务 `MODEL_GLOBAL_CALL_BUDGET_EXCEEDED` 暂停；默认费率 input $1/M、output $5/M 与实际价格（$0.15/$0.60）不符，预估值虚高约 7—8 倍。
- 证据：model_budget.py L55—57 全表计数；model.py L86—87 默认费率；models 工具核对实际价格（2026-10-14）。
- 处理方法：账本不清零；工作台按操作者授权设置显式 cap（环境变量），费率按实际价格配置；评测/开发运行使用独立账本并写入 run_context；接近上限暂停并报告，不重置。
- 状态与验证：已核实；cap 策略待 P5/P7 部署配置与文档化。
- 下一步：P5 集成与 P7 部署时登记实际 cap 与费率，验证触顶暂停行为。
- 变更记录：2026-10-14 新增。

## FL-D036 seal 不阻止后续上传，与“断点补传”语义并存

- 发现日期：2026-10-14（接续 agent 代码基线调查）。
- 问题与影响：`POST /api/tasks/{id}/seal` 只置 `tasks.sealed=1`；`TaskStore.uploads` 不检查 sealed，封存后仍可继续补传（有测试断言）。上传状态 `sealed_incomplete` 表示“封存时未传完”。若前端/文档把 seal 当“不可再传”，会与实现不一致。
- 证据：tasks.py L293—294；tests/test_tasks_api.py L88—91（seal 后上传仍接受）。
- 处理方法：保留现语义并明确文档化：seal 仅标记“本轮提交完成”，补传继续允许；新契约中如需硬封存，另行设计并验证。前端按钮文案与帮助说明按此调整。
- 状态与验证：已核实；文档与前端措辞待 P5 统一。
- 下一步：P5 更新前端与接口说明。
- 变更记录：2026-10-14 新增。

## FL-D037 指引 G15 分支表述顺序歧义（单类别不替换 vs 有销售服务费则替换）

- 发现日期：2026-10-14（接续 agent 通读指引）。
- 问题与影响：指引段 104“如果仅有一个份额类别，则不做替换。”与段 105“如有收取销售服务费，则替换为：……并加上返还基金份额持有人的销售服务费（如有）。”在非浮动管理费产品的清算分配规则下顺序表述可能被解读为互斥或并列，直接决定单类别/无销售服务费产品是否修改。
- 证据：`var/design-reading-20261014/guide_paragraphs.txt` 段 101—106；人工通读结论见实施计划 §4。
- 处理方法：不自行杜撰；由指引解析的独立核验模型对照来源复核，并用真实合同（产业优选等）证据裁决；裁决结论登记后冻结进内置指引版本。
- 状态与验证：待核验（P2）。
- 下一步：P2 解析核验时专项检查该分支并记录结论。
- 变更记录：2026-10-14 新增。

## FL-D038 工作台模型账本与评测账本需分离登记，避免混算

- 发现日期：2026-10-14（接续 agent 计划整理）。
- 问题与影响：工作台 Worker 使用 `<data_dir>/model_budget.sqlite` 累计账本；评测运行建议使用独立 run 账本（EVALUATION_AND_OPTIMIZATION_PLAN §7）。若两处混算，会出现“评测未登记到工作台账本”或“工作台 cap 被评测消耗”的口径混乱。
- 证据：model.py L82—87 默认账本路径；评测计划 §7/§8；本轮预登记见实施计划 §5。
- 处理方法：工作台 cap 单独配置并文档化；评测运行在 protocol.json 登记独立账本路径与 cap，汇总时两本账分别报告；不重置任何账本。
- 状态与验证：待实现（P5/P6）。
- 下一步：P6 运行前在 protocol.json 落实并核对。
- 变更记录：2026-10-14 新增。

## FL-D039 指引独立核验把历史核验结论回灌，导致自我强化

- 发现日期：2026-10-15（接续 agent 构建内置指引时）。
- 问题与影响：`verify_guide` 的候选上下文最初序列化整个解析文档（含上一轮的 `validation.verification.findings`）。独立核验模型看到旧结论后直接复述，表现为“同一批 findings 跨轮不变”，无法收敛也无法发现真实问题（首轮 16 条 → 次轮 14 条 → 三轮 9 条，内容高度重复）。
- 证据：修复前连续两轮核验返回完全相同的 9 条 findings（含已被修正的 G19/G20/G21 条目）；修复 `_candidate_variants` 只提交 `{"groups": ...}` 后，核验结论立即变化为针对当前内容的 7—10 条新结论。
- 处理方法：候选上下文仅提交 groups，剥离 provenance 与历史 validation/verification；核验结论单独保存，不回灌。
- 状态与验证：已修复并实测（同日内核验结论内容变化，证明不再回灌）。
- 下一步：在评测中核对核验发现率是否真实反映缺陷。
- 变更记录：2026-10-15 新增。

## FL-D040 内置指引解析结论与人工修正冻结记录

- 发现日期：2026-10-15。
- 问题与影响：指引解析必须可执行、可追溯，且“独立核验发现”与“人工修正”要分清，不能把修正后的文档冒称核验通过。
- 证据：`guides/builtin_guide_v1.json`：22 组 / 34 操作（append 3、replace 24、delete 6、noop 1）；确定性校验 errors=0、warnings=0、coverage_gaps=0（107 段中仅空段 9/106 未覆盖）；独立核验 findings 全部逐条复核并记录处置（accepted_interpretation / false_positive / accepted_limitation）。
- 处理方法：人工修正四条（G19/G20 单/多类别条件、G21 明确 noop、G22 非浮动+服务费+多类别、G14 三种旧表述全覆盖），每条附指引段号证据；残留核验意见写入 `validation.residual_review`；`clean_basis` 说明依据。文档哈希 `document_sha256` 冻结（重建稳定）。
- 状态与验证：已实施；冻结哈希与处置记录在文档内。发布前仍需在 P2 完成“来源覆盖、条件/槽位/操作合法性、真实合同证据”的版本验证，本记录不等于发布验收。
- 下一步：P2 版本验证与 qualification 通道；P6 用真实合同检验指引执行质量。
- 变更记录：2026-10-15 新增。

## FL-D041 模型供应商余额耗尽（HTTP 402），真实模型链路受阻

- 发现日期：2026-10-15。
- 问题与影响：OpenCodeGo（`LLM_MODEL=deepseek-v4.1-flash`）返回 `402 Insufficient Balance (request_id 5097a491-…)`。所有需要真实模型调用的工作受阻：P3 真实合同修改冒烟、P6 20—30 份评测、P7 云端真实端到端、qualification 发布验证。前序构建（内置指引解析 14 次 / $0.0465）已完成，之后余额耗尽。
- 证据：直接 HTTP 探测（`POST {LLM_BASE_URL}/chat/completions`，最小请求）返回 402 与上述错误体；`tools/evaluation/recall_run.py` 首次调用即 `MODEL_HTTP_ERROR`（event.http_status=402）。模型账本本身未触顶（本地 cap 未到），是供应商余额问题，与 HANDOFF_MATCHING_V3_20261014.md 记录的 402 同类。
- 处理方法：按整合文档 §7E/§15 作为可恢复外部阻塞处理：暂停真实模型任务并保留断点与账本；不重置账本、不伪造调用、不用替身结果冒充交付。继续推进不需要模型的全部工作（API/前端集成、评测工具与样本、云端部署与 MySQL、文档）。需要用户提供新的可用额度或替代端点后方可继续真实修改与评测。
- 状态与验证：阻塞（外部余额）；已实测确认（402 原始响应）。本地已可复现：`python -X utf8 -m tools.evaluation.recall_run ...` 立即停止。
- 下一步：用户充值/更换端点后，先跑 1 份真实合同冒烟（P3 出口），再按 §5 预算登记继续评测与云端 E2E。
- 变更记录：2026-10-15 新增。

## FL-D042 类别槽位实例化产生重复后缀（真实云端运行发现）

- 发现日期：2026-10-15（云端首个真实 recall_first 运行）。
- 问题与影响：事实提取返回的类别名可能带后缀（如“A类基金份额”），`class_label` 只剥“类”，导致生成“A类基金份额类基金份额”；同时指引 G02/G04 的示例新文“A类、B类基金份额”未被识别为示例组，被逐字写入合同（出现不存在的 B 类）。
- 证据：云端任务（doc 58ec3504，deploy-verify.docx）实际产物含“申购本基金A类基金份额类基金份额时”与“称为A类、B类基金份额”；独立审计正确判 wrong 并交付 `working_*`（incomplete），sweep 亦报告 SW001 wrong_text。
- 处理方法：`class_label` 归一化名称后缀（类基金份额/基金份额/类）；`instantiate_slots` 先替换指引示例组（A/B 例 → 申购费组，C/D 例 → 销售服务费组）再替换单类别 token。
- 状态与验证：已修复；单元测试 `test_class_name_suffixes_and_example_tokens` 覆盖两种缺陷；待云端重跑同一合同复验。
- 下一步：云端重跑确认审计通过并产出 final/redline。
- 变更记录：2026-10-15 新增。

## FL-D043 云端凭据可用而本机凭据余额耗尽（双凭据并存）

- 发现日期：2026-10-15。
- 问题与影响：本机 User 环境变量中的 `LLM_API_KEY` 返回 402（FL-D041），而服务器 `/etc/fundlex-recall.env` 中的密钥可用（同日实测 45 次调用 / $0.0445 成功）。真实模型验证必须走云端凭据，本机 `tools/evaluation/recall_run.py` 暂时不可用；两边账本与额度互相独立。
- 证据：本机直接 HTTP 探测 402 Insufficient Balance；云端 worker 完成 recall_sweep/recall_audit 等 15+ 次调用且账本记录 completed。
- 处理方法：真实修改与评测改由云端部署（fundlex-recall-worker + 服务器账本 /var/lib/fundlex/model_budget.sqlite）执行，按同一 cap 监控；本机仅做离线/替身验证。密钥不导出、不比对明文（只比对哈希前缀）。
- 状态与验证：已核实（两处密钥哈希前缀不同）；云端真实运行已成功。
- 下一步：在云端完成 P3 出口与 P6 评测；本机凭据待用户充值后再用。
- 变更记录：2026-10-15 新增。

## FL-D044 公网 HTTP 未开放（云安全组），改用 SSH 隧道访问

- 发现日期：2026-10-15。
- 问题与影响：`8.155.130.168` 的公网 80/443/8000/8010 均无法从外部访问（TCP 可连但无 HTTP 响应；本机代理下返回 502）；服务器本地 nginx→8010 与应用均正常。用户无法直接以明文 HTTP 访问工作台。
- 证据：本机/外网探测 000/502；服务器内 `curl -H 'Host: 8.155.130.168' http://127.0.0.1/` 200；SSH 隧道（本地端口转发）实测 index 200、`/api/capabilities` 200、`/api/guides` 401。
- 处理方法：短期交付 SSH 隧道访问（`ssh -L 8080:127.0.0.1:8010 root@8.155.130.168` → http://127.0.0.1:8080）；同时请用户在阿里云安全组放行 80（或 443+TLS）后改为正式入口。不在文档中把明文公网 HTTP 称生产入口。
- 状态与验证：隧道已实测可用。**2026-10-15 用户已在安全组放行 80**：公网 `http://8.155.130.168/` 实测 200、返回工作台 index（`FundLex合同修订工作台`，size 26816）、`/api/capabilities` 200；服务器监听 `0.0.0.0:80`、nginx→8010。**443 仍未监听**（`https://8.155.130.168` 000）。
- **已解决（2026-10-15，正式 HTTPS 入口上线）**：用户提供域名 **`fundlex.club`**（含 `www.fundlex.club`），A 记录指向服务器公网 `8.155.130.168`（权威 `ns1/ns2.dyna-ns.net`，TTL 300；生效前曾因 NS 同步延迟短暂不一致，等待后两台 NS 一致）。已在服务器配置 **nginx + Let's Encrypt 免费证书（acme.sh，EC-256，ecc）**：
  - 证书域名 `fundlex.club` + `www.fundlex.club`，Issuer=Let's Encrypt（`CN=YE1`），有效期至 **2027-01-13**；acme.sh 自动续期 cron 已安装（`--reloadcmd` 自动 reload nginx）。
  - nginx 站点 `/www/server/panel/vhost/nginx/fundlex.conf`：`server_name fundlex.club www.fundlex.club 8.155.130.168`；80 端口保留 `/.well-known/acme-challenge/` 并 301 跳转 HTTPS；443 反代 `127.0.0.1:8010`（`proxy_read_timeout 600s`）。
  - 证书落宝塔标准目录 `/www/server/panel/vhost/cert/fundlex.club/{fullchain.pem,privkey.pem}`；旧配置备份为 `fundlex.conf.pre-ssl-*`。
  - **公网实测（外网 curl）**：`https://fundlex.club` 连续 3 次 **HTTP 200**（`remote_ip=8.155.130.168`、`ssl_verify_result=0`）；`https://www.fundlex.club` 200；`http://fundlex.club` **301 → https://fundlex.club/**；证书校验 `SSL certificate verify ok`。系统防火墙已放行 80/443，阿里云安全组 443 可达。
  - 环境事实：本机为**宝塔面板**管理 nginx（`/www/server/nginx/sbin/nginx -c /www/server/nginx/conf/nginx.conf`，`www` 运行用户，配置目录 `root:root drw-------`）；`opencode` 用户无 nginx 写权限，经用户提供的 root 凭据（**仅会话内使用，不落盘不入仓库**）完成配置。
  - 未碰应用部署 `/opt/fundlex-recall-first` 与 systemd 服务；未改应用代码。**未提交 git、未 push。**
- 下一步：HTTPS 入口已可用作正式生产入口（`https://fundlex.club`）。注意宝塔面板若重写该站点 SSL 设置可能覆盖上述配置，届时按备份恢复。P7 浏览器端到端（登录→上传真实合同→真实模型→下载核对）仍未执行。
- 变更记录：2026-10-15 新增；同日更新公网 80 已开放并实测 200；同日追加 `fundlex.club` 域名解析 + Let's Encrypt HTTPS 正式入口上线并公网实测通过。

## FL-D045 片段级替换/删除曾被路由到模型 compose，导致余文丢失

- 发现日期：2026-10-15（云端真实运行 quality-return-06）。
- 问题与影响：当模型给出的目标引文覆盖整段、而指引操作只针对段内某一片段时（如 G05 的“调低赎回费率”/“并报中国证监会备案”），引擎走 compose 路径让模型重写整段；模型把“或者在法律法规…变更现有基金份额类别的申购费率…或者停止现有基金份额类别的销售等，调整前…报中国证监会备案”等应保留内容删除，违反“余文保留”。审计能发现（AUDIT_NOT_COMPLETED）但无法在预算内修复，交付停在 incomplete。
- 证据：quality-return-06 的 working_final p142 只剩“…可以调整基金份额类别，投资者通过直销机构…”，原文其余内容丢失；重放检查（tools/evaluation/replay_checkpoints.py）显示合并编辑的 replacement 以追加文本开头。
- 处理方法：新增确定性片段拼接 `_splice_fragment`：当操作 old_text 以空白归一化包含于实际目标文本时，代码在实际文本中就地替换/删除该片段，其余内容逐字保留；content_source 记为 `fragment_replace`/`fragment_delete`，并在 content_check 中重算拼接结果比对（确定性校验，不依赖模型）。仅当片段也无法匹配时才回退 compose。
- 状态与验证：已修复并云端复验（quality-return-07：p142 现为“…变更现有基金份额类别的申购费率、调低销售服务费率或变更收费方式…调整前基金管理人需及时公告，无需召开份额持有人大会”，余文完整；“调低销售服务费率”已替换、备案句已删除）；单元测试与 526 项全量测试通过。
- 下一步：将同类确定性优先原则扩展到多片段/多操作组合场景。
- 变更记录：2026-10-15 新增。

## FL-D046 最终全文查漏（sweep）误报过多，阻塞完整交付


- 发现日期：2026-10-15（云端真实运行 quality-return-07）。
- 问题与影响：sweep 对同一份实际产物报出 47 条 findings（前几轮 3—38 条），其引文经核对全部存在于最终产物中，多为语义已满足却被判未满足（例如类别分组替换在产品仅 A/C 类别时本就无需改动、正文已符合指引）。这些 findings 进入修复队列后无法收敛，使 delivery 停在 incomplete，掩盖真实缺陷。
- 证据：quality-return-07 report_json：`sweep.findings` 47 条，逐条引文在 working_final 对应段落中命中（47/47），无一仅存在于原件；未解决项中 sweep 占 47。
- 处理方法：sweep 上下文已补 FACTS 与“已满足/条件不适用不得报告”指令；`_rule_already_satisfied` 前置过滤按实际产物段落重算删除/替换是否已完成；`_absorb_sweep_findings` 现在把 finding 重新绑定到规则参考旧文（含跨段 composite），不再只按模型引文建桩；判定为已满足的 finding 以 `SWEEP_ALREADY_SATISFIED` 记录后丢弃，不再进入 unresolved。
- 状态与验证：已实施（过滤与重绑定）；quality-return-09 findings 47→11→8 且 8 条经阅读为真实线索而非误报；误报治理效果待云端 quality-return-10 复验。
- 下一步：与 FL-D047 同批复验 findings 数量、误报率与完整交付。
- 变更记录：2026-10-15 新增；同日按 FL-D047 的实现更新处理方法与状态。


## FL-D047 覆盖率靠模型盘点会漏掉正文/摘要重复条款，需确定性补扫

- 发现日期：2026-10-15（接续 agent 在 quality-return-09 的真实产物上定位 sweep 缺口）。
- 问题与影响：单次窗口化盘点由模型承担，漏掉同一业务条款的第二处（正文与摘要、变更章节的同类句）时没有任何代码信号：
  - G22 清算分配条款，正文 p978 已改、摘要 p1357 未改（`scope_mapping` 已含 S27，模型未报告该目标）；
  - G05“并报中国证监会备案”在正文 p142 已改，变更加、摘要处（p954/p1332）残留；
  - G16 新增段只落在 p809，摘要对应位置（p1262/p1263 一带）未追加；
  - G15 支付句跨段（p806+p807、p1262+p1263），模型引文只取到 p806 的前半句，`_splice_fragment` 找不到目标 → 走 compose 删除 → `RECALL_COMPOSE_DELETE_NOT_SHRINKING`；
  - G18 参考旧文“由于本基金A类基金份额不收取销售服务费，而C类基金份额收取销售服务费”在合同中写作“由于基金费用的不同，本基金A类基金份额和C类基金份额将分别计算…”，逐字匹配失败。
- 证据：`var/cloud-runs/quality-return-09/report_json`：windows→1 个联合窗口（22 条规则）、targets 23 条、findings 8 条；本机对同一合同做确定性搜索复现上述位置（G22 2 处、G05 含摘要 4 处、G15 跨段 2 处）。
- 处理方法（已实现）：
  1. `recall.survey_targets`：盘点后按规则参考旧文（含 `old_text_variants`）在全部段落做确定性搜索，命中即生成绑定真实偏移的目标（`origin=survey`），不依赖模型记忆；
  2. 同句边界：逐字命中要求起点在段首或句读/停顿标点之后（`_BOUNDARY_MARKS` 补齐全角逗号、顿号、冒号），避免“清算结果报中国证监会备案”这类词中命中；
  3. 删除操作允许“参考旧文末句片段”作为锚点，但要求片段紧跟在参考旧文自己的引导语之后（`_lead_nearby`，且引导语至少 6 字、不少于参考引导语的 60%），避免把“变更并公告，并报中国证监会备案”这类无关备案句当目标；
  4. 跨段操作：`find_old_text_all` 检测“本段结尾 + 下一段开头”拼接命中，`plan_composite_target` 生成按段的精确编辑（锚段保留其前缀、后续段只删/替换属于参考旧文的部分），并复核每段替换结果；
  5. “已满足”判定：`satisfied_by_new_text` 在段内找到规则新文/末句且与参考旧文差异足够大时标记目标为已满足，避免把已改写的条款再报一次（G18 的“费用收取不同”变体即由此收敛）；
  6. sweep 报告→修复：`_absorb_sweep_findings` 把 finding 重新绑定到规则的参考旧文（跨段时升级为 composite 目标），不再只按模型引文建桩；审计与修复轮次中都强制重跑 survey（`_run_survey`）。
- 状态与验证：已实施；单元测试新增 6 项（survey 摘要命中/词中命中排除/跨段删除/多处同一旧文），全量 `pytest tests -q` 531 passed / 6 skipped。真实合同（广发品质回报）本机重跑见 `var/recall-runs/qr-local-01`；云端复验与最终交付状态在验证后更新。
- 遗留在本条目内说明：G05 的片段锚点在“估值差错更正”等章节仍可能产生额外候选（p760，审计判 wrong）；G18 的合同变体目前按“已满足”处理，尚需在评测中核对是否存在应当改写的情形。qr-local-12 复验另暴露：① survey 命中转目标时的引文切片疑似偏移一位（quote 记成“人并报中国证监会备”），使 `_splice_fragment` 失配并落入 compose；② 盘点目标引文未解析时（G15 p806）没有走 composite 重绑定（该路径目前只服务 sweep findings）。两项均待服务器开发副本上修复。
- 下一步：云端 quality-return-10 复验 findings 数与 delivery；P6 评测中统计 survey 命中真实率与误报率。
- 变更记录：2026-10-15 新增。

## FL-D048 条件不适用被判未解决、SQLite 占锁与并发限制被吞成部分失败

- 发现日期：2026-10-15（本机真实合同重跑 `var/recall-runs/qr-local-01`）。
- 问题与影响：
  1. 盘点给出的目标若其规则条件与产品事实不符（多变体合同上的单类别分支 G07/G10），规划层报 `RECALL_NO_APPLICABLE_OPERATION` 并记为 unresolved，把“不适用”当成失败项；
  2. 真实运行在本机多次被 `MODEL_LEDGER_UNAVAILABLE` 打成整轮停止（`stage=inventory/scope/plan`）。逐层追踪（`_budget_retry` 前的临时探针）确认底层异常是 `sqlite3.OperationalError: attempt to write a readonly database`，发生在账本 `finish()` 的 UPDATE；同一账本在独立进程探针中读写正常，属于短暂文件占锁/只读窗口（多进程或扫描器与运行并发）。该错误码属于 STOP_CODES，因此把一次可重试的瞬时抖动升级成整轮停止。
- 证据：`var/recall-runs/qr-local-01/report_json`（plan ledger 出现 `RECALL_NO_APPLICABLE_OPERATION`、`MODEL:MODEL_LEDGER_UNAVAILABLE`，errors 记录 `MODEL_CONCURRENCY_LIMIT`）；`var/recall-runs/dbg-local5` 探针打印 `sqlite3.OperationalError: attempt to write a readonly database`（`model_budget.py` finish → `db.py` `_run`）。
- 处理方法：
  1. 新增 `RECALL_RULE_NOT_APPLICABLE`（条件不成立 → ledger 记 `not_applicable`，不计入未解决）；
  2. `plan_edits` 对 `ModelError` 中属于 STOP_CODES 的码直接抛出 `RecallPipelineStop`，由 worker 暂停并从检查点续跑（不再按目标吞掉）；STOP_CODES 抽为 `recall._STOP_CODES`；
  3. 新增 `_budget_retry`：账本 `reserve`/`finish` 遇到 “readonly/locked/busy” 时按 0.4s→1.0s→2.5s 重试 3 次，仍失败才升级为停止；
  4. 复现与定位：`var/recall-runs/dbg-*` 系列探针显示同一代码在项目目录 `var/` 内的账本上 `finish` 稳定失败（三次重试全 readonly），把账本移到项目目录之外（`C:\Users\asus\AppData\Local\Temp\opencode\ledger-live.sqlite`）后全部 `finish ok`。同工作区有另一个 agent 会话在运行，`var/` 目录被其持续扫描/占用是稳定只读的来源；这不是 SQLite 瞬时抖动，重试无法覆盖。结论：**运行账本不要放在项目 `var/` 目录内**，用 `%LOCALAPPDATA%` 或系统临时目录；`var/` 只放产物。
  5. 顺带修复 `tools/evaluation/recall_run.py`：把 `--max-calls` 同时写入 `FUNDLEX_MODEL_MAX_REQUESTS`（账本请求上限），此前只设置 `FUNDLEX_MODEL_MAX_CALLS`，账本按默认 16 次请求触顶并整轮停止（`MODEL_GLOBAL_CALL_BUDGET_EXCEEDED`）。
- 状态与验证：已实施；全量单元测试通过；重跑 `var/recall-runs/qr-local-10`（账本在系统临时目录）复验。云端（Linux）无此占锁现象，但仍保持重试与不吞停止。
- 下一步：部署后 quality-return-10 复验；P6 评测的 `protocol.json` 登记账本路径时遵循“账本不进项目 var/”；如本机再次出现稳定 readonly，先确认是否有其他进程扫描账本所在目录。
- 变更记录：2026-10-15 新增；同日补入 readonly 根因（项目目录被其他 agent 占用）与“账本移出项目目录”的结论。

## FL-D049 工作区迁移到服务器后的 Git 状态差异与 .git 体积

- 发现日期：2026-10-15（开发主副本迁移到 `/home/opencode/fundlex`）。
- 问题与影响：
  1. 迁移后服务器上 `git status` 多出 21 个 ` M`（`docs/*.md|json`、`workbench/*.html`）。原因是本机 Windows Git 以 `core.autocrlf=true` 检出行尾 CRLF，而 blob 存 LF；Linux 副本默认视为已修改。不影响内容，但会污染状态与 diff；
  2. 非 ASCII 路径（`FundLex_Agent_设计方案_v4.md`、`frontend/assets/去白底 .png`）默认按八进制转义显示；
  3. 本机 `.git` 含 263MB 松散对象与 14 个 `tmp_obj_*` 垃圾文件（一次中断的 git 操作遗留），迁移包约 283MB；另有两条指向 Windows 路径的 worktree 记录（`frontend-fluent`、`frontend/workbench`）。
- 证据：迁移前 `git count-objects -vH`（count 1240 / 270MiB，garbage 14）；`git repack -d` 后仍有 550 个不可达松散对象；迁移后服务器 `git status --porcelain | wc -l` 76 →（设置后）55，本机 56（差一个未迁移的 `references/`）。
- 处理方法：服务器仓库设置 `core.autocrlf=input`（CRLF 工作树文件与 LF blob 视为一致）与 `core.quotepath=false`（直接显示中文路径）；迁移脚本排除 `tmp_obj_*` 垃圾；不执行 `git prune`（其他 agent 可能仍在用这些不可达对象），worktree 记录保留。不可达对象与 worktree 迁移留档，不清理。
- 状态与验证：已实施并复验（服务器 file 数 824 = 本机包内文件数；关键文件 sha256 全部一致；git HEAD `3ed4e96146a04d3092de6c57138289bdffeca526` 一致；服务器基线 `pytest tests -q` 530 passed / 1 failed / 6 skipped，唯一失败为 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`——它读取按迁移约定排除的 `references/source/…指引_文案勘误版.docx`，属预期差异而非代码回归）。
- 下一步：如需缩小服务器 .git，先确认两条 worktree 无使用方后再 `git gc --prune=now`；本机副本保持只读。
- 变更记录：2026-10-15 新增。

## FL-D050 资料迁移到服务器数据目录与合同清单口径

- 发现日期：2026-10-15（用户授权迁移资料，`funds_word/` 与 `references/` 移入服务器）。
- 问题与影响：
  1. 资料需与代码分开管理：不进仓库工作区、不写入 git，供评测抽样引用；
  2. `funds_word/` 实际有 **515** 个文件（用户口径 514）：多出的是 Word 占用锁文件 `~$广发…_20260909.docx`（162 字节，2026-10-15 09:18 生成）。按文件数直接抽样会把锁文件算作合同；
  3. 清单格式按要求为每行“sha256  相对路径  字节数”，三列格式不能被 `sha256sum -c` 直接消费。
- 证据：本地 `Get-ChildItem funds_word | Measure` 515（含 `~$`）/ 514（.docx 合同）；迁移后服务器 `find funds_word -type f | wc -l` = 514（已排除 `~$`），`references` = 24；`/home/opencode/data/MANIFEST.sha256` 538 行数据 + 4 行注释（files/total_bytes/generated_at/host）。
- 处理方法：迁移脚本 `tools/deploy/migrate_data.py` 排除 `~$*`、`.baiduyun.*` 等临时文件；上传到 `/home/opencode/data/{funds_word,references}`，`chown -R opencode:opencode`、目录 750、文件 640、根目录 750；服务器生成 MANIFEST.sha256（sha256 + 路径 + 字节数，注释行记录总数 538 / 总字节 82361614 / 生成时间 2026-10-15T11:26:00+08:00 / 主机名）；核对用 `awk '!/^###/ {print $1"  "$2}' MANIFEST.sha256 | sha256sum -c -`。
- 状态与验证：已实施并全量核对——538 个文件逐一与本地 sha256+字节数比对 **0 不一致、0 缺失、0 多余**；服务器自检 538 OK / 0 FAILED；抽样口径以 MANIFEST.sha256 为准（后续评测冻结样本时引用）。`funds/`（历史 PDF，514 份）按要求未迁移。
- 下一步：P6 评测的 manifest 与标签冻结直接引用 `/home/opencode/data/funds_word/` 与 `/home/opencode/data/MANIFEST.sha256`；若新增合同，重新生成清单并保留旧清单版本。
- 变更记录：2026-10-15 新增。

## FL-D052 qr-local-12 的 12 项未解决：切片偏移、跨段目标未重绑定、同段多操作被短路、查漏位置误报

- 发现日期：2026-10-15（服务器开发主副本 `/home/opencode/fundlex`，接续 agent 第 5 轮；证据 `data/evidence/qr-local-12/report.json`）。
- 问题与影响：qr-local-12（广发品质回报 `_20230708.docx`，143 调用 / $0.0748 / incomplete）剩 12 项未解决，逐条核对后发现**四类真实缺陷**，都会阻塞正常合同完整交付：
  1. **survey 引文切片偏移（compact→raw 换算错误）**：`find_old_text_all` 返回的是“去空白紧凑文本”偏移，而 `survey_targets` 用 `display_text` 的 raw 索引映射（保留空格），段内有空格时整体偏移。实测 p760 `并报中国证监会备案`（紧凑 34:43）被记成 raw `人并报中国证监会备`；p760 第二处记成 `告，并报中国证监会`。后果：`resolve_quote` 用错误引文对上概率失真、`_splice_fragment` 失配落 compose、`RECALL_COMPOSE_FIXED_TEXT_MISSING`。
  2. **跨段盘点目标未重绑定**：G15 支付句（正文 p806 结尾 + p807 开头；摘要 p1262+p1263）在盘点中按单段 `resolve_quote` 解析，跨段引文必然 `quote_not_found` → 规划 `RECALL_TARGET_UNRESOLVED`。既有 `_operation_fingerprints` 重绑定**只服务 sweep findings**，不覆盖“盘点/审计自己给出的未解析目标”。
  3. **同段多操作被首个命中短路**：G05 在 p142 同一句里既要 `replace 调低赎回费率→调低销售服务费率`、又要 `delete 并报中国证监会备案`；`plan_target` 按 delete→replace 顺序**首个成功即 return**，导致只删备案句、漏做替换 → 审计 `AUDIT_NOT_COMPLETED`（incomplete）。
  4. **查漏（sweep）位置误报**：sweep 按 section_hint 全文搜索，把规则报在**不属于该规则映射章节**的段落（G16 p227 在 S07、G22 p142 在 S04）；G18 报在 p139/p829/p1217（真实改写点只有“由于基金费用的不同，…”变体，已在合同中满足）。
  附带发现：本条修正了 FL-D047 遗留的“G05 摘要第二处 p954/p1332”判断——经确定性搜索，p954/p1332 是“基金合同的变更”条款（`变更并公告，并报中国证监会备案`），**不是** G05 费用类别调整句；真正的费用类别调整句在全文中只有 p142（G05 正确目标）。此前把 p954/p1332 当未改目标属误判。
- 证据：
  - 复现命令（服务器）：`.venv/bin/python -X utf8 -c "..."` 打印各段 `find_old_text_all` 命中与 raw/compact 切片差异；`report.json` 的 `unresolved`（12 项）与 `plan.ledger`（G05 T006 `fragment_delete` 仅删备案句、G03/G16 merged 丢基句、G15 unresolved）。
  - 映射证据：`report.json.scope_mapping`（G16→S16 p772–p820、G22→S20 p952–p982 与 S27 p1330–p1384、G18→S17 p821–p840），与误报位置 p227/p142/p139/p1217 均不相交（p829 在 S17 内但该句不在该处）。
- 处理方法（已实施）：
  1. `recall.compact_offsets`（新）：给出“去空白紧凑文本 + 紧凑偏移→raw 偏移”映射；`survey_targets` 改用它换算引文与偏移；`plan_composite_target` 同步改用（其原用 `display_text` 映射，p806 残留 `，`、p807 残留空格即为该错）。
  2. `recall_pipeline._rebind_unresolved_targets`（新）：对 `state=needs_edit` 且 `resolution∉{resolved,composite}` 的目标，按“目标自身引文跨段匹配 → 规则操作参考旧文 `_operation_fingerprints` 逐级降级”确定性重绑定；命中则写 `composite/start/end/resolution` 并记 `origin=rebind_*`，未命中记 `RECALL_TARGET_REBIND_FAILED`。在盘点后、首轮规划前以及每轮修复后各执行一次，报告新增 `rebind` 段。
  3. `recall.plan_target` 重构：把同段所有 `delete/replace` 的确定性片段操作**累积**到同一 replacement（新增 `fragment_mixed` 内容来源与 `applied` 证据），不再首个命中即返回；变体删除/替换循环相应去重。
  4. `recall.satisfied_by_new_text` 增加“同政策不同语序”等价识别（`_FEE_DIFFERENCE_MARKERS` + 类别 token 全含 + 旧文已消失），使 G18 在 p139 判为已满足；`recall_pipeline._rule_location_absent`（新）与 `_rule_mapped_locations`（新）+ `_sweep_batch(rule_locations=…)` 过滤：查漏 finding 的段落不在规则映射章节 → `SWEEP_LOCATION_OUT_OF_SCOPE`；段落既无规则参考旧文、规则要求又已在产物中满足 → `SWEEP_LOCATION_NOT_RULE`。
  5. `recall_pipeline._run_audit` 增加确定性确认 `_confirm_merged_append`：append 目标与同位置的**兄弟删除规则**合并后基句消失、但 append 新文原样存在于 AFTER 时，把模型的 wrong/incomplete 改为 completed（记 `deterministic=True`），覆盖 G03 p141 与 G16 p809 的误判。
  6. `recall.operation_search_keys` 旁的 `bare_tail_keys`/`rule_context_anchors`（新）：裸尾片段（无内部子句边界的参考旧文，如“并报中国证监会备案”）的 survey 命中必须由规则自身上下文措辞（如“调低赎回费率”）佐证，否则丢弃——排除 p760 估值差错条款等无关同形句。
- 状态与验证：已实施并有单元测试与真实合同核对：
  - 新增单测：`test_survey_quote_offsets_survive_interspersed_spaces`、`test_composite_plan_offsets_after_spaces`、`test_survey_drops_bare_tail_seen_in_unrelated_clause`、`test_plan_target_applies_delete_and_replace_in_one_span`（`tests/test_recall_core.py`）、`test_unresolved_inventory_target_is_rebound_cross_paragraph`、`test_rebind_records_failure_when_reference_absent`、`test_sweep_filters_finding_outside_rule_section`（`tests/test_recall_pipeline.py`）。
  - 全量：`.venv/bin/python -m pytest tests -q` → **537 passed / 1 failed / 6 skipped**，唯一失败为 `test_rules_catalogue::test_source_provenance_and_reproducible_compilation`（引用未随迁移带来的 `references/`，预期差异，非回归）。
  - 真实合同离线核对：G15 目标重绑定为 `p806:0:34 + p807:0:88` 的 composite 删除；G05 p142 现同时完成替换与删除（`fragment_mixed`）；12 项未解决的 target/audit/sweep 逐条判定完毕（详见集中记录后述分类）。**尚未**在应用链路（worker 真实模型）复验；未发布、未 push。
- 下一步：发布到应用（`tools/deploy/publish_workspace.sh`）后用云端真实任务 quality-return-10 复验 12 项收敛、`not_applicable` 不计未解决、`delivery_status` 能否 complete；再进 P6 评测。
- 变更记录：2026-10-15 新增（服务器接续第 5 轮）；同日区分四类缺陷并逐类实现，测试 530→537。
- 变更记录（2026-10-15 第二轮，真实链路复验后）：
  - 已发布（`tools/deploy/publish_workspace.sh` 成功），并完成 **quality-return-10 真实应用链路复验**（register→login→task→upload→seal→轮询→下载，真实模型）：`task_status=completed`、`job_status=succeeded`、**64 调用 / $0.0461 / 358s**、`delivery=incomplete`、**targets 28 / completed 27 / unresolved 1**（对比 qr-local-12 的 30/14/12）。四类修复方向均被证实有效：G05 p142 同目标 replace+delete（`fragment_mixed`）、G03 p141 与 G16 p809 审计经 `_confirm_merged_append` 判 completed、G15 p806/p1262 跨段已解决、G16/G18/G22 误报消失（sweep dropped 记录 `SWEEP_LOCATION_OUT_OF_SCOPE`/`SWEEP_LOCATION_NOT_RULE`/`SWEEP_ALREADY_SATISFIED`）。产物在 `var/cloud-runs/quality-return-10/`。
  - **仍有 3 类残留（同属 FL-D052，已实施第二轮修复）**：
    a. **G17 p808 `RECALL_COMPOSE_DELETE_NOT_SHRINKING`（审计 wrong）**：规则 `old_text` 是 p808+p809 两句拼接（`销售服务费主要用于…基金份额持有人服务费等。` + `销售服务费使用范围不包括基金募集期间的上述费用。`），盘点正确拆成 T018(p808)/T019(p809)；但 T018 的 span 只含其中一句，整段参考文在单段内永不匹配，`_splice_fragment`/`variant_delete` 均失配 → 落 compose-delete，模型两次都原样返回未删减。
    b/c. **G02 p106 / G04 p138 sweep 误报**：`class_substitution` 规则的 `new_text`（`A类、B类基金份额`/`C类、D类基金份额`）是**指引示例字母**，非字面需求；本产品实际仅 A/C 两类，盘点已正确判 `satisfied`，但 sweep 模型把示例当真实需求报“未分组替换”。（d. 该误报的审计/sweep 派生条目随 ① 一并消失。）
  - 第二轮修复（已实施，离线核对通过）：
    i. `recall.class_substitution_noop`（新）：`class_substitution` 规则各适用操作的实例化 `new_text` 与其 `old_text` 相等（产品实际类别已就是规则要的分组）即判定无需修改；`recall_pipeline._rule_already_satisfied` 前置调用 → finding 记 `SWEEP_ALREADY_SATISFIED`（修 b/c）。
    ii. `recall.plan_target` 新增“删除整段目标”确定性分支：delete-only 规则、目标引文（compact）等于目标 span 且为规则 delete 参考文的子串时，整段 `replacement=""`（`content_source=variant_delete`），不再走 compose-delete（修 a）；反向保护：span 还含规则不删的内容时不整段删除，仍走 compose。
  - 新增单测 3 项：`test_class_name_suffixes_and_example_tokens` 增 `class_substitution_noop` 断言、`test_delete_target_span_matching_one_sentence_of_reference`（`tests/test_recall_core.py`）、`test_sweep_filters_class_substitution_rule_that_needs_no_change`（`tests/test_recall_pipeline.py`）。
  - 全量：`.venv/bin/python -m pytest tests -q` → **539 passed / 1 failed（预期，references 未迁移）/ 6 skipped**。真实合同离线核对：G02/G04 sweep finding 判 `SWEEP_ALREADY_SATISFIED`；G17 T018/T019 均判 `variant_delete`（`replacement=""`），G16 追加仍与之正常 merged 到 p809，无冲突。
  - 第二轮已发布并启动 quality-return-11 真实链路复验（进行中）。
  - **第二轮复验结果（quality-return-11，真实应用链路）**：`completed` / `succeeded` / **79 调用 / $0.0510 / 404s** / `delivery=incomplete` / targets 28 / completed 27 / **unresolved 3**（target 1 + audit 2）；**`sweep_findings=0`**（G02/G04 误报已消除）、**G17 p808 已解决**（`variant_delete`）；但出现**新回归**：**G15 p806** `RECALL_COMPOSE_DELETE_NOT_SHRINKING` + 审计 wrong，且 **G16 p809** 审计 wrong（“替换掉原句”）。产物 `var/cloud-runs/quality-return-11/`。
  - 第三轮定位与修复（同属 FL-D052）：
    - 根因：合同把 G15 要删的销售服务费支付条款拆成 **p806（`…按月支付，`）+ p807（`由基金管理人与基金托管人核对一致后…支付日期顺延。`）** 两段；指引措辞（`每日计提`）与合同（`每日计算，逐日累计至每月月末`）不同，各参考文均不匹配。盘点某轮引了**全句**（跨段）→ `quote_not_found`；另一轮回落到**只有首段**（p806）→ `resolved`（单段）→ 删除无法覆盖续段，落 compose-delete 失败。`_rebind_unresolved_targets` 原先只处理未解析目标，已解析的单段目标被跳过。
    - 修复：① `_rebind_unresolved_targets` 增加 `extend_resolved` 参数与“多候选取覆盖最长”绑定，并新增 `_clause_continuation_binding`：当已解析目标**覆盖整段**（start=0、end=段末）、段末为逗号类未结句、且规则为删除/替换（非 append）时，把**紧随的一段**并入为 composite（偏移用 `compact_offsets` 的紧凑偏移）。安全约束：仅跨段 composite 才可替换已解析绑定；整段+逗号+删除/替换三重条件，避免误扩。
  - 新增单测：`test_rebind_extends_resolved_target_to_clause_continuation`（含“整段才扩、段中不扩”反向断言）。
  - 全量：`.venv/bin/python -m pytest tests -q` → **540 passed / 1 failed（预期）/ 6 skipped**。离线核对：G15 重绑定为 `p806:0:34 + p807:0:88` composite 删除、G17 p808 整段删除、G17+G16 p809 正常 merged、无冲突。
  - 第三轮已发布并启动 quality-return-12 真实链路复验（进行中）。
  - **第三轮复验结果（quality-return-12，真实应用链路，已通过）**：`task_status=completed`、`job_status=succeeded`、**`delivery_status=complete`**、**unresolved 0 / 0**、targets 27 / completed 27 / unresolved 0、`sweep_findings=0`、**25 调用 / $0.0236 / 127s**。`rebind` 段记录 G15 T007 重绑定为 `p806:0:34 + p807:0:88`（`clause_continuation`）。产物 `var/cloud-runs/quality-return-12/`（final/redline/report.json）。
  - **真实产物逐项核对（读实际 DOCX，非报告口径）**：
    - `final` sha256 `862548a7…c9c`、`redline` sha256 `2e586002…bdb`，与 `report.output_validation` 完全一致；redline 含 16 处 `w:ins` + 16 处 `w:del`（真实修订痕迹）。
    - p806 原支付句删除、p807 续段删除（G15 composite_delete）；p808 `销售服务费主要用于支付销售机构佣金…等服务费等。` 删除（G17 variant_delete）；p809 原句**保留** + 追加 G16 新内容（G16 审计通过）。
    - p142 同时完成 `调低赎回费率→调低销售服务费率`（G05 replace）与 `并报中国证监会备案` 删除（G05 delete，同段 `fragment_mixed`）。
    - G02 p106 / G04 p138 不再被 sweep 误报（`sweep_findings=0`）。
  - 结论：FL-D052 四类缺陷在真实应用链路（工作台 API → worker → 真实模型 → 实际 DOCX 修改 → 报告/修订版下载与哈希一致）下全部收敛，单份合同可完整交付。**本工作区未 commit、未 push。**
  - 待办（见 FL-D053）：quality-return-10/11/12 各注册的临时账号（`cloud-run-*`）与任务未清理（无 DELETE 接口、DB 需 root 凭据）；需用户协助或授权清理。

## FL-D053 真实链路复验临时账号与任务无法清理

- 发现日期：2026-10-15（quality-return-10/11/12 真实复验后）。
- 问题与影响：`/tmp/opencode/cloud_run_local.py` 通过公开 `/api/auth/register` 注册临时账号（用户名 `cloud-run-*`）并创建任务；应用**无 `DELETE /api/tasks/{id}` 接口**，且 MySQL 127.0.0.1:3307 需 root 凭据、`/etc/fundlex-recall.env` 为 `-rw------- root`、`sudo -n -l` 仅允许 `/usr/local/sbin/fundlex-publish`。因此 `opencode` 用户**无法自行清理**这 3 个临时账号及其任务，测试环境会留下 `users/sessions/tasks/task_files/batches/documents/artifacts` 残留行。
- 证据：`sudo -n -l` 输出仅 `(root) NOPASSWD: /usr/local/sbin/fundlex-publish`；`mysql -h 127.0.0.1 -P 3307 -u root` → `ERROR 1045 Access denied`；`/etc/fundlex-recall.env` 权限 `-rw------- root root`。
- 处理方法：短期由用户协助清理（提供 DB 凭据、或加一个安全的清理子命令/`DELETE` 接口、或授权 sudo 运行 `tools/deploy/cloud_verify.py` 同款清理逻辑）。参考 `tools/deploy/cloud_verify.py` 第 110-130 行的删除顺序（artifacts→documents→task_batches→batches→task_files→tasks→sessions→users）。
- 状态与验证：**已解决（2026-10-15）**。用户提供 FundLex MySQL 凭据（`/etc/fundlex-recall.env` 中 `FUNDLEX_DATABASE_URL` 的应用账号，127.0.0.1:3307/fundlex，MySQL 8.0.46）；以事务按 artifacts→documents→task_batches→batches（按 `owner IN users.id`）→task_files→tasks→sessions→users 顺序删除。验证：`cloud-run-*` 账号 0、其任务 0；`users 5`（admin + 4×`cloud-eval-*`）、`tasks/batches/documents 10`、`artifacts 32`、`sessions 12`；`admin` 与其他 `cloud-eval-*` 账号未受影响。不影响交付链路正确性。
- 安全说明：凭据仅在会话内以 `MYSQL_PWD` 环境变量传入子进程，未写入仓库/文档/日志/命令参数。
- 下一步：后续给测试账号加显式 TTL/清理任务或安全清理子命令，避免同类残留（不计入本轮完成条件）。
- 变更记录：2026-10-15 新增；同日晚些时候更新为已解决并附验证结果。

## FL-D057 为其他 agent 提供 3307 DB 访问的凭据方案（受限账号 + 600 文件）

- 发现日期：2026-10-15。用户要求把 MySQL 凭据给其他 agent 使用，并选择“方案1：受限 DB 账号 + 600 文件”。
- 问题与影响：现有 `opencode` 用户读不到 `/etc/fundlex-recall.env`（600 root），也没有创建 DB 用户/写 `/etc` 的权限（`sudo -n -l` 仅 `fundlex-publish`）。若把 `fundlex`（全库 ALL + 同文件含 LLM key）密码放进用户级环境变量，等于永久取消隔离，违反 AGENTS.md 凭据纪律，且环境变量对所有同用户进程可见、易入日志。需要一个“最小权限、可轮换、不暴露 LLM key”的专用账号。
- 证据：`SHOW GRANTS` 显示 `fundlex@127.0.0.1` 仅 `GRANT ALL ON fundlex.*`，`CREATE USER` 返回 `ERROR 1227`;`/etc` 对 opencode 不可写；`sudo -n -l` 仅 `/usr/local/sbin/fundlex-publish`。
- 处理方法：新增 `tools/deploy/setup_fundlex_ops.sh`（由 root 运行）：创建 `fundlex_ops@127.0.0.1`（随机密码），仅授 `SELECT ON fundlex.*` + 受控清理所需的 `DELETE`（不含 INSERT/UPDATE/DROP/ALTER/CREATE USER）；凭据写入 `/etc/fundlex-ops.env`（`root:opencode 640`，opencode 可读、其他人不可读）。配套 `tools/deploy/cleanup_test_accounts.sh`：从前述 env 读凭据，只删除 `username LIKE cloud-%/cloud-eval-%/p6-%` 且显式排除 `admin`，默认 dry-run、`--apply` 才执行。
- 状态与验证：**已实施并验证（2026-10-15）**。用户以 root 执行 `setup_fundlex_ops.sh` → 创建 `fundlex_ops@127.0.0.1`，凭据写入 `/etc/fundlex-ops.env`（`root:opencode 640`）。以 opencode 用户实测：`CURRENT_USER()=fundlex_ops@127.0.0.1`（MySQL 8.0.46）；`SHOW GRANTS` = `SELECT ON fundlex.*` + 8 张表的 `DELETE`；安全边界验证全部被拒：INSERT/UPDATE/DROP/CREATE USER → `ERROR 1142`/`1227`；只读 `SELECT COUNT(*) FROM users` 成功。`cleanup_test_accounts.sh` dry-run 正常列出 6 个 `cloud-eval-*` 且排除 `admin`。修复了脚本内 WHERE 拼接的语法缺陷（尾随 `OR`）。**未提交 git**。
- 安全说明：不采用“把现有 fundlex 密码写入环境变量”；新账号凭据只在 600 文件中、agent 经文件读取、不打印。`fundlex_ops` 无写入业务数据权限。
- 下一步：如需清理，运行 `bash tools/deploy/cleanup_test_accounts.sh --apply`（当前 `cloud-eval-*` 为 P6 评测账号，未删除，保留待评测用）。建议轮换已出现于会话中的 `fundlex` 应用账号密码。
- 变更记录：2026-10-15 新增。

## FL-D054 长合同在 sweep 阶段触发 MODEL_CONTEXT_LIMIT，整单不产出文件
- 发现日期：2026-10-15（P6 评测首轮 smoke：D01 `广发上海清算所0-4年央企80债券指数…_20250319.docx`，1363 段）。
- 问题与影响：长合同完成盘点/规划/审计后，在**最终查漏（sweep）**阶段抛 `MODEL_CONTEXT_LIMIT`（`fundlex/model.py:160`），任务 `status=completed` 但 `delivery_status=not_generated`、`artifacts={}`、无最终/修订文件，整单无法交付。根因：`_sweep_chunk_chars` 只按 `limit - 4000` 或 `limit - requirements - 1000` 计算窗口预算，**未扣减 `facts_text`** 与固定标题开销；实际 sweep 上下文为 `[GUIDE_REQUIREMENTS]+[FACTS]+[ARTIFACT_WINDOW]`，19 条规则的 requirements + 事实块 + 8000 字窗口 > 12000 上限。
- 证据：`var/recall-first-evaluation/p6-smoke-01/D01/report.json`：`errors=[{"code":"MODEL_CONTEXT_LIMIT","stage":"sweep"}]`、`output_validation.kind=null`、`artifacts={}`；同批 D07（1407 段）同样 `not_generated`。
- 处理方法：`_sweep_chunk_chars(model, requirements, facts_text="")` 改为按 `len(requirements)+len(facts_text)+_SWEEP_CONTEXT_OVERHEAD` 扣减，并把 facts 一并纳入 `RECALL_SWEEP_CONTEXT_LIMIT` 的判定；调用点传入 `facts_text`。
- 状态与验证：已实施；新增单测 `test_sweep_chunk_budget_subtracts_facts_block`、`test_sweep_context_limit_when_rules_and_facts_fill_context`（`tests/test_recall_pipeline.py`）。全量 `pytest` 541 passed/1 failed（预期）/6 skipped。已发布（`fundlex/recall_pipeline.py` `fc8efb5a…` 与部署一致）。真实链路复验见下方 FL-D054 变更记录。
- 下一步：用 P6 开发集真实链路复验长合同可正常产出。**注意**：D01 同时暴露 FL-D055（审计误判），修复后仍需复验。
- 变更记录：2026-10-15 新增（P6 首轮 smoke 发现）。

## FL-D055 审计把“份额类别占位符展开”误判为无依据新增

- 发现日期：2026-10-15（P6 首轮 smoke：D01）。
- 问题与影响：规则 `class_substitution=true`（G01/G03/G08/G11 等，槽位为占位符如 `A类基金份额`）时，生成器按产品实际份额类别展开（D01 为 A/C/D 三类 → 写成 `A类、D类基金份额`）。审计（`AUDIT_INSTRUCTION`）**未说明占位符展开规则**，把 `A类、D类` 判为 “adds policy the guide does not state” → `verdict=wrong` → 触发不必要的返修/未解决，甚至错误 complete 声明风险。同一 D01 出现 G01 审计 wrong。
- 证据：`var/recall-first-evaluation/p6-smoke-01/D01/report.json` → `audit.rounds[0].results` G01 `verdict=wrong`，`reason` 明确称“adding D类基金份额, which the guide does not state”。
- 处理方法：在 `AUDIT_INSTRUCTION` 增加一段总则：槽位类名是占位符，AFTER 必须命名 [FACTS] 中该组的**实际类别**；把合同真实定义的、且 [FACTS] 列于该组的类别加入，属正确展开而非无依据新增。属通用政策，不针对样本。
- 状态与验证：已实施（`fundlex/recall_prompts.py`）；已发布（sha256 `b95bc228…` 与部署一致）。需在 P6 真实链路复验审计不再误判。
- 下一步：P6 开发集复验；若仍误判，考虑在审计上下文显式带入 `class_substitution` 标志与类别分组表。
- 变更记录：2026-10-15 新增（P6 首轮 smoke 发现）。

## FL-D056 无销售服务费类别的产品被误判为销售服务费规则“未解决”

- 发现日期：2026-10-15（P6 首轮 smoke：D07 `广发均衡养老目标三年持有期混合型基金中基金（FOF）`，A類/Y類两类，均收申购费、均不计提销售服务费）。
- 问题与影响：G01/G03/G08/G11/G16 等规则正文含示例类 `C类基金份额`（服务费组占位符）。产品无任何计提销售服务费的份额类别时，`facts.service_group` 为空，`instantiate_slots` 报 `SERVICE_GROUP_EMPTY` → `plan_target` 抛 `RECALL_SLOT_UNRESOLVED` → 目标被判 unresolved，任务 `delivery=incomplete`。但该产品根本没有 C 类/销售服务费条款，规则应判**不适用**而非失败。D07 因此积压 26 项 unresolved（含 G16 append 误加销售服务费内容）。
- 证据：`var/recall-first-evaluation/p6-smoke-02/D07/report.json` → `unresolved` 含 `G02/G03/G04/G08/G11/G16 … RECALL_SLOT_UNRESOLVED`；`audit` 对 G16 要求追加销售服务费内容，而 D07 全篇无销售服务费类。
- 处理方法：在 `fundlex/recall.py` 增加 `_missing_slot_groups`/`slot_group_missing`：当规则 `class_substitution=true` 且其正文需要 `C类基金份额`，而产品 `service_group` 为空时，`plan_target`（含 composite 分支）抛 `RECALL_RULE_NOT_APPLICABLE`（映射为 `not_applicable`）。判定故意收窄：仅服务费组占位符 + 服务费组为空才触发，普通规则与不含该类占位符的规则不受影响。
- 状态与验证：已实施；新增单测 `test_service_fee_rule_not_applicable_without_service_class`（`tests/test_recall_core.py`，含“普通规则/无占位符规则不受影响”反向断言）。全量 `pytest` 543 passed/1 failed（预期）/6 skipped。
- 下一步：发布后真实链路复验 D07/D09/D13/H02（无服务费产品）。
- 变更记录：2026-10-15 新增（P6 首轮 smoke 发现）。

## FL-D058 旧方案文档散落根目录与 docs，易被误当现行方案

- 发现日期：2026-10-15。用户要求把当前目录里的旧方案整理归档。
- 问题与影响：仓库根目录与 `docs/` 混放 v1/v4/v2 时代的历史方案（PRD v4.1、Agent 设计 v4.1、详细设计 v1.1、`IMPLEMENTATION_BRIEF/PLAN`、v2 匹配升级、早期工作台原型等），与当前召回优先（`engine_id=recall_first`）文档并存。新 agent 可能误把旧方案当现行规范（如"仅空结果补扫""固定 22 动作"），与 `AGENTS.md`/`FULL_PROJECT_DEVELOPMENT_HANDOFF.md` 冲突。
- 证据：`docs/RECALL_FIRST_DESIGN.md` 开头已自标"历史目标方案"；`IMPLEMENTATION_PLAN.md` 开头自标"历史记录入口"；根目录仍有 5 个旧设计文档。
- 处理方法：建立 `docs/archive/{design,v2-matching,early-prototypes}/`，用 `git mv` 归档（保留历史，不删除，符合 AGENTS.md）；顶层 5 个设计文档移入 `docs/archive/design/`；`docs/` 根目录只留当前有效文档；新增 `docs/archive/README.md` 索引（列出每份文档及其被取代的原因、当前入口清单、归档原则）。同步修正 `README.md`、`workbench/prototypes/README.md` 中指向已移动文件的链接（加"（已归档）"并改路径）。
- 状态与验证：**已实施**。归档 27 份文档（design 5 / v2-matching 11 / early-prototypes 11）；`git status` 显示为 `R`（重命名，历史保留）；`docs/` 根目录余 16 份当前文档；链接死链扫描（README + `docs/*.md`）无残留。**未提交 git，未 push**。
- 下一步：如需进一步收敛，可在 `README.md` 顶部强化"当前入口"指向；本归档不改变任何代码或引擎行为。
- 变更记录：2026-10-15 新增。

## FL-D072 sweep 误报 G02/G04 分组替换未完成（残留旧标签）

- 发现日期：2026-10-15（P6 首轮 smoke：D01 `广发上海清算所0-4年央企80债券指数…_20250319.docx`，A/C/D 三类）。
- 问题与影响：规划阶段 G02/G04 已判 `satisfied`（`targets[].status=satisfied`），最终查漏（sweep）仍对 p130 报 `residual_old_text`/`wrong_text`，理由是“A类及D类…未按分组规则替换为 A类、D类”。该句是释义中说明收费规则的句子，不是 G04 要替换的**标签** `A类基金份额`；`_rule_already_satisfied` 判定为 False（既不含 instantiated 新文，也判定不了已满足），导致 `delivery_status=incomplete`。属模型判断波动：同一代码在 p6-smoke-07 该案 `complete`，p6-smoke-08 复现一次。
- 证据：`var/recall-first-evaluation/p6-smoke-08/D01/report.json` → `sweep.findings` SW002 `status=unresolved`、SW003 `status=resolved`；`targets` G02/G04 均 `satisfied`。
- 处理方法（部分）：已补齐 G02/G04 的确定性过滤——`class_substitution_noop`（含费用同质产品）与 `slot_group_missing` 在 sweep 过滤中生效；仍无法覆盖“合同用不同句子解释收费规则”的情形。评估按实际 DOCX 计分，sweep 仅影响 `delivery_status`。
- 状态与验证：**未完全解决**。规划侧正确（satisfied），查漏侧偶发误报。后续可让查漏上下文带入“该规则已判 satisfied 的目标位置”，或对 class_substitution 规则的残留标签改用标签级匹配。
- 下一步：全量开发集运行后统计该误报出现率；若为低频且不影响实际修改，记录为已知精度问题并保留 fail-closed 语义。
- 变更记录：2026-10-15 新增（P6 首轮 smoke 发现）；同日编号由误用的 FL-D057 更正为 **FL-D072**（FL-D057 已用于「3307 DB 受限账号凭据方案」，编号冲突）。

## FL-D073 无服务费类别产品的销售服务费规则判定（FL-D056 的正式结论）

- 发现日期：2026-10-15（P6 首轮 smoke：D07 A類/Y類按销售账户划分）。
- 结论：产品无任何计提销售服务费的份额类别时，G01/G03/G08/G11（含 C 类占位符）与含“销售服务费率”替换文本的规则（G14）应判**不适用**；G15/G16/G17 因源条款不存在也不适用。D07 由 26 项 unresolved 降至 0，最终 `delivery_status=complete`。
- 实现：`slot_group_missing`（服务组为空或费用同质）+ `plan_target` 对 class_substitution 规则整体判不适用 + `Target.out_of_scope` 令审计/未解决统计一致排除 + `unresolved_targets` 排除 `not_applicable`。
- 状态与验证：已实施并真实链路复验（p6-smoke-08 D07 `complete`/0 unresolved）；全量 `pytest` 544 passed / 1 expected failed / 6 skipped。
- 变更记录：2026-10-15 新增（并入 FL-D056 的实现结论）；同日编号由误用的 FL-D058 更正为 **FL-D073**（FL-D058 已用于「旧方案文档归档」，编号冲突）。

## FL-D059 删/替规则的合同措辞变体未进入 survey，导致真实应删条款被判 not_applicable

- 发现日期：2026-10-15（P6 开发集基线：D01 `广发上海清算所0-4年央企80债券指数…_20250319.docx`）。
- 问题与影响：指引 G15/G17 的删除引用以份额类别前缀开头（`C类基金份额的销售服务费每日计提，按月支付。…`、`C类基金份额的销售服务费主要用于支付销售机构佣金…`），合同实际写作 `基金销售服务费每日计提，逐日累计至每月月末，按月支付…` 与 `销售服务费主要用于支付销售机构佣金、以及…`。整串模糊匹配失败，`operation_search_keys` 只产出整串引用，survey 报不出目标，规划阶段判 `not_applicable`，最终 DOCX 仍保留应删条款（D01 的 p758/p1221、p759/p1222 各两处）。属**漏改**，直接压低目标完成率。
- 证据：`var/recall-first-evaluation/p6-dev-baseline-01/D01/report.json` → G15 p758、G17 p759 均 `state=absent status=not_applicable`；最终文件 `D01/final` 第 783/1246 段（G15 支付句）与 784/1247 段（G17 用途句）仍存在。
- 处理方法（已实施）：`operation_search_keys` 对**仅删除**的规则追加“去份额类别前缀后的首个分句”作为短锚点（`_strip_class_lead`，≥8 字且与规则标题/要求共享 3-gram），G15 得 `销售服务费每日计提`、G17 得 `销售服务费主要用于支付销售机构佣金`、G13 得赎回费短锚。实测 survey 对 D01 产出 G15 p758+p1221、G17 p759+p1222、G13 p230。
- 状态与验证：**已实施，独立验证**（`survey_targets` 直接调用命中双位置；新增单测 `test_search_keys_add_class_stripped_anchor_for_delete_rules`；全量 545 passed / 1 expected / 6 skipped）。真实链路复验需在应用修复后的批次内确认。
- 变更记录：2026-10-15 新增（P6 基线发现 → 同轮实施）。
- **跨 20 份开发集的离线验证（2026-10-15 补充）**：
  - G17（用途句“销售服务费主要用于支付销售机构佣金”）短锚 **11/11 命中**，措辞高度一致，属确定性收益、低误报。
  - G15（支付句）长尾严重：实测至少四种写法——`基金销售服务费每日计提`（D01/D20）、`基金销售服务费每日计算`（D04/D17）、`销售服务费每日计算`（D19）、`C类基金份额的销售服务费每日计提`（D11）、`对于投资者持续持有期限未超过一年…的份额收取的销售服务费，逐日累计…`（D10/D15）。“去前缀首分句”锚点覆盖不到“每日计算/每日”变体；改用更泛的 `逐日累计至每月月末，按月支付` 又会每份命中 4–6 处（含费率公式邻域），区分度不足。**结论：G15 的长尾识别不适合靠关键词穷举，应由模型盘点把“销售服务费支付句”作为必查项，survey 仅作兜底。**
  - G13（7 份标签）与 G06（3 份）亦有同类短锚漏配，待查措辞变体后评估。
  - 基线中 G15 漏删同时来自“模型盘点判 not_applicable”（D04 p845、D10/D11/D12 全部）与“survey 漏扫”，不能只靠 code 侧修复。

## FL-D078 工作区长期未提交、版本管理缺失（本轮完成规范化提交，push 受凭据阻塞）

- 发现日期：2026-10-15（用户要求「git 事情可自主判断，做好版本管理」）。
- 问题与影响：工作区自 `3ed4e96` 起长期未提交——整个 recall-first 引擎、指引、API/持久化扩展、前端工作台、测试、评测工具与文档共 **46 个未跟踪 + 11 个已跟踪修改** 堆积，无增量历史、无法回退、容易误入库样本/密钥。
- 处理方法（已实施）：按功能拆成 **9 个逻辑提交**（`3ed4e96..HEAD`）：
  1. `cc558ab` docs: 归档 early-prototype / v2-matching 旧文档（纯移动）。
  2. `35b0be6` feat(recall-first): 引擎 + 指引 + 提示词 + P6 评测工具 + 测试。
  3. `71ab437` feat(api): 多任务工作台 API、引擎绑定、模型账本 + 测试。
  4. `d37d633` feat(frontend): 工作台 UI（并发任务、可读证据、ZIP、去横幅、单行 KPI 等，含本轮 8 项）。
  5. `0896409` docs: 断点/交接/问题记录/评测计划/AGENTS。
  6. `b3d68f9` chore(deploy): 发布与迁移工具。
  7. `d7472c3` chore(research): 一次性研究脚本与工作台原型。
  8. `d7af552` docs(archive): 归档计划指向 recall-first 交接。
  9. `43626c2` chore: 忽略 3 个无引用散图（`640.png`/`t0183cba9196d3d9cc9.jpg`/`去白底 .png`，加 `.gitignore`）。
  - 提交前已扫描全部拟入库文件：无口令/密钥/私钥模式；原件/样本目录（`funds_word/`、`references/`、`var/`）由 `.gitignore` 覆盖。git 身份设为 `FundLex Agent <agent@fundlex.local>`（仅本地）。
  - 验证：提交后工作树**干净**（`git status` 空）；全量测试 **562 passed / 1 expected（references/ 未在服务器）/ 6 skipped**。
- 状态与验证：**已实施并已推送**（2026-10-15 晚）。本地提交 11 个（增 `3a3f524` 问题记录、`b1b084c` 断点、`05fc90f` 编号更正），工作树干净；全量测试 **562 passed / 1 expected / 6 skipped**。**push 已完成**：`git push -u origin codex/fundlex-recall-first` → 远端 `b1b084c..05fc90f`，本地与 `origin/codex/fundlex-recall-first` 一致。凭据由用户提供（OAuth token `gho_…`，经临时文件 + `GIT_ASKPASS` 使用，未入命令行历史/仓库/日志，用后即删）。**该 token 已在对话中出现，用户应撤销/轮换。** 已配置仓库级代理 `http.proxy=http://127.0.0.1:9981`。
- 下一步：后续增量提交直接 `git push`（upstream 已设）；**不把凭据写入仓库/文档/prompt/日志**；不 push 资料/样本/密钥。
- 变更记录：2026-10-15 新增；同日编号由误用的 FL-D072 更正为 **FL-D078**（FL-D072 已用于「sweep 误报 G02/G04」，编号冲突，见 FL-D077）；同日完成 push（原「push 未做」结论作废）。
- 凭据持久化（2026-10-15 晚，用户要求「你帮我保存凭据」）：token 存于**仓库外** `/home/opencode/.github_token`（`600`），推送统一走 `bash tools/deploy/push_with_token.sh`（默认读该文件；token 不打印、不入命令行/仓库/日志，经 `GIT_ASKPASS` 传入）。已用该脚本成功推送 `51ae7e6..0e2ae9b`。**记录只写文件路径与用法，不写 token 值**；撤销方式为删除该文件并轮换 GitHub token。
- 续推记录（2026-10-15 晚，本轮）：`99509fb`（push 助手脚本）、`e37aa21`（FL-D079 交付包 + 变体 span 句边界吸附）、`dcc715e`（FL-D080 复合偏移）经 `bash tools/deploy/push_with_token.sh ~/.github_token` 成功推送 → 远端 `807ba68..dcc715e`；本地 `codex/fundlex-recall-first` 与 `origin/…` 一致。仓库内 217 个跟踪文件扫描无密钥/样本/原件（`var/`、`references/`、`funds_word/` 均被 `.gitignore` 覆盖）。

## FL-D071 结果页可用性与多任务并行：前端 8 项 UX 问题（用户第 7 轮反馈）

- 发现日期：2026-10-15（用户反馈第 7 轮问题 1–8，前端部分）。
- 范围：`frontend/index.html`、`frontend/app.js`、`frontend/app.css`（本轮唯一改动的文件）。
- 问题与影响：①导入/上传期间全局 `state.uploading` 互斥，不能浏览或新建其他任务；②证据侧栏露出 `p142`、字符偏移、`mapping_safe` 等技术字段，业务不可读；③多处解释性小字重复啰嗦；④「下载全部结果 ZIP」按钮位置与空态提示不佳；⑥`#notice` 顶部横幅式提醒噪音、铃铛收噪音；⑦任务总进度 8 项指标窄屏折行；⑧批量导入 KPI 独占一行。
- 处理方法（已实施）：
  ①移除 `selectTask`/`newTask`/任务下拉/任务行/导入导航的上传互斥，仅保留当前上传会话自身控件禁用；上传时对 `sessionFiles = a.accepted.slice()` 快照，避免重置草稿破坏在途请求（对应后端结论 FL-D069）。
  ②删除 `candidateLine`，新增 `changedClauses`/`clauseRow`，按 `report.guide.groups` + `report.plan.edits` + `report.targets` 呈现「章节 + 状态 + 原因 + 改之前/改成了什么」，绝不显示 `location/start/end/anchor_sha256/content_source/mapping_safe/segment_ok`。
  ③按「每区域一句」精简说明文案。
  ④`download-all` 移到结果页操作区首位并升为 `btn-primary`，按 `delivery_counts` 判断可用性并给出友好提示（URL/文件名原本正确，未改）。
  ⑥彻底删除 `#notice` DOM 与 `.global-notice*` CSS；`notice()` 仅 `error=true` 进铃铛；成功类 `toast` 改行内 `flash()`（写入 `upload-message`），不进铃铛。
  ⑦`#overall-counts` 改为 flex 单行横向滚动、5 项核心指标，余项入 `title` tooltip。
  ⑧`#import-stats` 移入筛选 `.toolbar` 右侧紧凑内联 `.inline-kpis`。
- 状态与验证：**已实施**（前端）。验证方式：`node --check frontend/app.js` 通过（本机原无 node，已下载便携版 v20.18.0 到 `/tmp/opencode` 校验）；CSS 括号平衡；120 个 `$('id')` 引用在 HTML 中全部存在；`#2` 用真实 `var/cloud-runs/quality-return-12/report.json` 走渲染逻辑核对，得到 22 行可读输出、**无任何技术字段**。
- 未验证/限制：**未做浏览器端真实点击验收**（本机无浏览器/JS 运行时环境下的交互测试）。
- 下一步：在工作台真实页面登录后逐条点击验收问题 1/4/6/7/8，并打开一份真实合同的「查看证据」确认对照展示（问题 2）。
- 变更记录：2026-10-15 新增。（子 agent 建议编号 FL-D068 已被引擎修复占用，故本项记为 FL-D071。）

## FL-D070 P6 优化第 1 轮评测结果（较基线小幅改善，仍远低于阈值）

- 发现日期：2026-10-15（P6 优化第 1 轮 `p6-dev-round1-01` 完成后评分）。
- 结果：批次 20 个开发集合同全部完成（`delivery_complete` 13），677 次模型调用，$0.5738。
  - **开发集可编辑口径（18 份 / 236 标签目标）**：**completed 187 / 率 0.7924**；基线（较正后的 `/tmp/opencode/p6-baseline-full2.json`，`scored_at 08:26`）为 **178 / 0.7542** → **净 +9 目标（+3.8pt）**。
  - 规则层净变化：**G15 +9**（0/15 → 9/15，删除销售服务费支付句的长尾修复生效）、**G05 +2**、**G17 −2**。
  - `applicability_conflicts` 29 → 13。
  - `kept`（应删/应替仍保留原文）41 → 32。
  - **假完成 false_complete 13 → 12**（`actually_complete` 由 0 → 1），仍严重。
  - 全量口径（含 8 份未跑的留出）0.513 → 0.5389；其中 **111 个 `not_executed` 全部来自未跑的 8 份留出**（H01–H08 `no artifact`），非引擎缺陷。
- 证据：评分产物 `/tmp/opencode/p6-round1-score.json`（sha256 `07fb0112…`）；对照 `/tmp/opencode/p6-baseline-full2.json`（0.7542，弗 `p6-baseline-full.json` 的 0.712 系较早一次评分）。逐规则明细可由 `p6_score.py` 复算。
- 处理方法：本轮 FL-D059/062/063/064 修复确认**有效但不足**；开发集仍有 **17 个 append 目标「授权文案缺失」** 与 **32 个 kept** 是下一轮重点（G01/G03/G16/G05 等）。**不允许用 holdout 调参**；留出必须在开发集冻结达标后再跑。
- 状态与验证：**已实施并已评分**（开发集）。发布门槛（目标 0.95 / 整合 0.9）**未达标**，不满足正式交付条件。
- 下一步：针对开发集 not_executed（append 文案缺失）与 kept（G15/G17/G11/G18 删除未生效）继续修复后复跑开发集；达标后再跑留出 H01–H08 并冻结版本。
- 变更记录：2026-10-15 新增。

## FL-D069 前端把「上传中」当成全局互斥，导致有任务在跑时不能新建任务（后端本就支持并行）

- 发现日期：2026-10-15（用户反馈第 7 轮问题 1）。
- 问题与影响：用户报告「有任务在跑时不能新建任务，只能补交文件」。经核实：**后端完全支持一个用户建多个任务并行处理**——`tasks.create`（`fundlex/tasks.py:56`）只做 idempotency-key 去重，无「单一活动任务」限制；`POST /api/tasks`（`fundlex/api.py:670`）无并发守卫；worker `claim`（`fundlex/jobs.py:119`）按公平调度从任意任务的文档取活。限制**纯粹来自前端**：`frontend/app.js` 用全局 `state.uploading` 阻止 `newTask()`（line 129）、`addFiles()`（line 130）、`selectTask()` 切换（line 117）、并禁用任务下拉与 `[data-task]` 行（line 127）。
- 证据：`grep -n "state.uploading" frontend/app.js` 命中上述各点；后端 `create_task` 无并发检查（代码阅读）。
- 处理方法（已实施）：前端改为「导入会话」粒度——`state.uploading` 仅禁用当前会话自身的提交/选文件/移除/清空，不再阻止浏览、切换其他任务或新建任务；发起上传时对文件列表做快照，使重置草稿不影响在途上传。后端无需改动。
- 状态与验证：**已实施**（前端，随本轮前端交付）；后端支持性已核实。
- 下一步：发布后用真实浏览器/工作台验证任务 A 处理中同时新建任务 B 可上传并并行处理。
- 变更记录：2026-10-15 新增。

## FL-D068 引擎已修复的「无标点段落追加文案连在一起」仍有个别路径遗漏（fragment 拼接）

- 发现日期：2026-10-15（用户反馈第 7 轮问题 5；定位与复现）。
- 问题与影响：用户报告「合同中有的段落结尾没有标点符号，导致在后面新增文案的时候连在一起了」（例如 `…称为 C 类基金份额投资者通过直销机构…`，正确应为 `…份额。投资者…`）。核查发现：`append_separator`（`fundlex/recall.py:1759`）与 `plan_target` 的 append 分支（`recall.py:1818`）**已有**分隔符逻辑，2026-10-15 较早的部署版本导致的 `quality-return-12` 老报告已不缺标点；当前代码与部署副本在该路径**一致且正确**。但仍有**第三条路径**从未加固：`_splice_fragment`（原 `recall.py:1694`，`return actual[:start_raw] + new_text + actual[end_raw:]`）——它是 `fragment_replace` 的实现，在**段落中部**把授权文案直接拼到保留下来的、未以标点结尾的前导文字上，产生 `本基金 A 类基金份额的通过直销机构申购…`（P6 第 1 轮 D02 `p228` 真实复现）。
- 证据：round1 产物扫描（`var/recall-first-evaluation/p6-dev-round1-01/D02/working_final` p228）`本基金 A 类基金份额的通过直销机构申购本基金A类基金份额不收取申购费…`；`plan.edits` 中该处 `content_source=fragment_replace`、`replacement` 前导无标点。对比 `quality-return-12` 老报告中 `plan_target` append 分支已正确带 `。`（老版本已修复）。
- 处理方法（已实施）：`_splice_fragment` 改为在拼接 `new_text` 前后分别调用 `append_separator(prefix, new_text)` / `append_separator(new_text, suffix)`；`new_text` 为空（删除）时保持原文逐字拼接、不插入标点。同步在 `plan_composite_target`（composite 替换路径）加同样分隔符保护，作为防御性修复。
- 状态与验证：**已实施**。新增回归测试 `test_fragment_replace_separates_authorized_text_from_unterminated_lead` 与 `test_composite_replace_separates_unpunctuated_clause`；全量测试 **561 passed / 1 expected（references/ 未在服务器）/ 6 skipped**。
- 下一步：随本轮发布后，用真实合同（如 D02 对应 `广发上证50…联接基金`）复跑，确认 p228 不再出现粘连；并继续观察 `fragment_replace` 的 `本基金 A 类基金份额的。` 这类「悬空前导 + 句号」是否仍有语义缺陷（属独立精度问题，见 FL-D065 范畴）。
- 变更记录：2026-10-15 新增。

## FL-D074 评分器以短锚点判删除完成，误把“已删净”判为 kept

- 发现日期：2026-10-15（P6 优化第 1 轮评分）。
- 问题与影响：删除类标签的 `old_text` 是**定位用短锚**（G15 的“销售服务费每日计提”，6 字），评分器仅以该短串是否仍在区域内判 `kept/completed`。该短串会**原样出现在保留的另一条款**（G16 追加的“销售服务费每日计提。（1）直销机构：…”）里，导致已删除 G15 支付句的终稿被误判 `kept`。D05/D07 等实测：G15 支付句（“服务费每日计提，逐日累计…按月支付…划出”）确已删除，`划出`/`服务费每日计提，逐日累计` 均不在终稿，仅 `按月支付` 来自 G16 政策文本。
- 证据：`/tmp/opencode/p6-round1.json` → G15 `kept` 14 项；逐例核验 D05 终稿，G15 支付句确已删、G17 用途句确已删。
- 处理方法（已实施）：新增 `_superseded_survives()`。删除判定改用**标签 requirement 中引号内的整条被删条款**（`_requirement_clause`），取其 3 个**辨识性长片段**（首段后 8–40 字、中段 24 字、末 24 字）；只有这些长片段仍在终稿才算 `kept`。短锚仅在无可引条款时回退使用。
- 状态与验证：**已实施**。同一批次重评：开发集完成率 0.763→**0.792**，G15 `kept` 14→6。**对照真漏加/真漏删案例仍判 not_executed/kept**（未放宽到恒真）。
- 变更记录：2026-10-15 新增；同日编号由误用的 FL-D068 更正为 **FL-D074**（FL-D068 已用于「无标点段落追加 fragment 拼接遗漏」，编号冲突）。

## FL-D075 G17 删除义务跨两段，survey 只绑首段导致次段残留

- 发现日期：2026-10-15（P6 优化第 1 轮评分，FL-D074 修复后）。
- 问题与影响：G17 参考文本一次性删除两句——“C类基金份额的销售服务费主要用于支付销售机构佣金…服务费等。”**与**“C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。”。合同常把第二句放**下一段**（如 D01 p759/p760）。survey 的短锚只匹配首段，`_extend_to_clause_end` 的句数延伸无法跨段，故只删首句、次句仍在终稿（D01/D16/D18 实测 `使用范围不包括…` 残留）。
- 证据：`var/recall-first-evaluation/p6-dev-round1-01-prev/D01/final` 索引 785/1248 仍含“销售服务费使用范围不包括基金募集期间的上述费用。”；引擎报告 G17 仅 p759/p1222 两个单段目标。
- 处理方法（已实施）：新增 `_reference_continuation()`。删除规则命中后，若参考文本在被匹配句之后**仍有内容**且该内容（去类别前缀后）出现在**紧随段落**开头，则把两段合并为**一个跨段复合目标**（`parts` 含两段真实偏移）。
- 状态与验证：**已实施，离线验证**。D01/D06/D16/D18/H04 等 G17 由单段变为双段复合；G15 各变体与复合跨段绑定不回归（全 28 份逐例核对）。新增单测 `test_delete_reference_continues_into_next_paragraph`。全量 **562 passed / 1 expected / 6 skipped**。真实链路复验待本轮发布后批次。
- 变更记录：2026-10-15 新增；同日编号由误用的 FL-D069 更正为 **FL-D075**（FL-D069 已用于「前端上传全局互斥」，编号冲突）。

## FL-D067 遗留测试与当前 API 不同步（append 段落测试全红，非产品缺陷）

- 发现日期：2026-10-15（P6 优化第 1 轮期间全量测试）。
- 问题与影响：`tests/test_recall_core.py::test_append_at_unpunctuated_paragraph_end_generates_valid_docx`（8 个参数化用例）针对**旧 API** 编写：`validate_edit_plan(edits, inspection, content_check=...)`（缺 `templates`、参数顺序旧）、`assert plan.valid`（`ValidatedPlan` 无 `valid` 字段）、`generate_artifacts(source, plan, out)`（缺 `final_path`）、`artifacts["final"]`（应为 `ArtifactValidation.final_sha256` + 显式路径）。这些用例全红，会掩盖真正的产品回归。
- 证据：`TypeError: validate_edit_plan() missing 1 required positional argument: 'templates'` / `'ValidatedPlan' object has no attribute 'valid'` / `generate_artifacts() missing … 'final_path'`。
- 处理方法（已实施）：按当前 API 重写该测试（`validate_edit_plan(source, edits, {}, content_check=…)`、去掉 `plan.valid`、`generate_artifacts(source, plan, redline_path, final_path)`、读 `final_path`）。同文件 `build_docx_edits` 亦兼容 `PlannedEdit` 与 dict 两种入参。
- 状态与验证：**已实施**。全量 **559 passed / 1 expected / 6 skipped**（此前 551+8 红）。
- 变更记录：2026-10-15 新增。

## FL-D066 中断批次遗留模型账本 reserved 预留，阻塞后续任务（MODEL_CONCURRENCY_LIMIT）

- 发现日期：2026-10-15（P6 优化第 1 轮中止后的排查）。
- 问题与影响：杀死正在跑的评测批次后，worker 当时在途的模型调用预留（`requests.status='reserved'`）未释放。`ModelBudget.reserve` 仅在 `lease_until<=now` 时把过期预留转为 `abandoned`，且 `concurrency` 默认 **1**；因此一个未过期的预留会连续阻塞后续所有任务的 facts/compose 阶段，报 `MODEL_CONCURRENCY_LIMIT`，表现为任务长时间 `queued/running` 无进展。曾一度误判为“我的代码改动导致回归”。
- 证据：`/api/batches/{b}/documents/{d}/report` → `errors:[{code:MODEL_CONCURRENCY_LIMIT,stage:facts}]`；worker 进程 CPU 时间冻结（`time` 停在 2:08）且无 ESTAB 模型连接；重启 worker（经 `publish_workspace.sh`）后同一合同 10 秒完成。
- 处理方法：① 批次中止应通过**等待在途任务自然结束**或随后**重启 worker**（`publish_workspace.sh` 会重启服务）来释放；② 预留租约为 `timeout_s+30`（默认 75s），过期后由下一次 `reserve` 自动回收，本次等待即恢复；③ **不再在 worker 处理任务中途 kill 批次**；abort 后先重启服务再重跑。
- 状态与验证：**已缓解并验证**。重启服务后 D04 真实链路 `delivery complete`、35 目标、0 unresolved、耗时 260s。**残留风险**：`concurrency=1` 时任何在途中断都会短暂阻塞；如需，可评估提高 `FUNDLEX_MODEL_CONCURRENCY` 或缩短租约（未改，避免影响预算口径）。
- 变更记录：2026-10-15 新增。

## FL-D063 短锚点绑定过短：删除只删首分句、残留后半句（G17 半删 / G15 空删）

- 发现日期：2026-10-15（P6 优化第 1 轮真实链路：D01）。
- 问题与影响：FL-D059 的“去类别前缀首分句”短锚点（如 G17 的“销售服务费主要用于支付销售机构佣金”仅 17 字）在 survey 命中后**只把这段短片段绑定为目标 span**。删除执行时只删掉该片段，残留“、以及基金管理人的基金行销广告费…等服务费等”，整句未删干净（D01 摘要位 p1222 实测）；G15 同类短锚（“销售服务费每日计提”，9 字）绑定过短，composer 报 `RECALL_COMPOSE_DELETE_NOT_SHRINKING`，`whole_paragraph_delete` 因 `_same_compact(actual, span.text)` 不成立而不触发，最终整句仍在（p1221）。
- 证据：`var/recall-first-evaluation/p6-dev-round1-01-aborted/D01/report.json` → G17 p1222 `unresolved`（“仅删除了…仍残留…”）、G15 p1221 `unresolved RECALL_COMPOSE_DELETE_NOT_SHRINKING`；`working_final` 索引 783/1246 仍含支付句。
- 处理方法（已实施）：新增 `_extend_to_clause_end(text, start, end, key, *, delete_only)`。对**纯删除规则且命中键不是 bare tail 键**的短锚点，把 span 末端延伸到下一个句末终止符（`。；;！？!?`）。同时修 survey 兜底分支的 `SurveyHit` 未调用 `.with_parts()` 导致 `_survey_targets_from_hits` 读 `hit.parts[0]` 抛 `IndexError`（见 FL-D064）。
- 状态与验证：**已实施，独立验证**。D01 的 G15 由 2→110、G17 由 0→52 全句绑定；D04/D17 的 G15 变为**跨段复合**（`p844:0:18`+`p845:0:158`）。`bare tail` 键（G05“并报中国证监会备案”）**不受影响**（既有测试 `test_survey_quote_offsets_survive_interspersed_spaces` 仍精确等于引用串）。新增单测 `test_delete_anchor_extends_to_the_whole_clause`。全量 **547 passed / 1 expected / 6 skipped**。真实链路复验待修正版重新发布后的第 1 轮批次。
- 变更记录：2026-10-15 新增。

## FL-D064 survey 兜底命中未设置 parts，导致 worker `IndexError` 整任务失败

- 发现日期：2026-10-15（P6 优化第 1 轮：D02/D04 `PROCESSING_FAILED`）。
- 问题与影响：FL-D062 新增的删除词袋兜底分支构造 `SurveyHit(...)` 时**未调用 `.with_parts(...)`**，`hit.parts` 为空元组；`_survey_targets_from_hits` 首行 `hit.parts[0]` 抛 `IndexError`，worker 以 `PROCESSING_FAILED` 结束，整任务无产物（D02/D04 `not_generated`）。
- 证据：`report.json.errors=[{code:PROCESSING_FAILED,stage:worker,message:"IndexError"}]`；本地对 D04 复现同一栈（`recall_pipeline.py:279`）。
- 处理方法（已实施）：兜底分支补 `.with_parts(parts)`；单段命中 parts=`[(loc,0,len(text))]`，跨段命中 parts=`[(loc,0,len(text)),(follower,0,len(follower_text))]`，使复合目标带真实偏移。
- 状态与验证：**已实施**。D04/D01/D17 本地 `_survey_targets_from_hits` 不再抛错；D04/D17 的 G15 正常产出跨段复合目标。**注意**：该缺陷由本 agent 在本轮引入并已发布过一次，导致第 1 轮批次 D02/D04 失败；该批次作废（见下）。
- 变更记录：2026-10-15 新增。

## FL-D065 为通过而放宽评测器/标签的口径风险（本次的边界与处置）

- 发现日期：2026-10-15。
- 问题与影响：P6 评分中 append 判定过脆（FL-D060 拆分条目①）与标签对 append 过标（②）会同时拉低分数。若借“修评测器”之名把判定放宽到接近恒真，等于制造通过。
- 证据：修复前后对 D01/D05/D09/D10/D13/D15/D19 逐例核对：D05（原件无、终稿有→真追加）、D10/D15（原件已有）、D01/D09/D19（两处都无→真漏加）、D13（真漏加）。
- 处理方法与边界：`appendix_present` 仅在**归一化常见变体后匹配义务首分句**或**首段 ≥0.85 滑动重叠**时判通过；对真漏加案例（D01/D09/D19/D13）**仍判 not_executed**。**冻结标签不改**（改 gold 即制造通过）；标注器对 append 过标作为已知局限在结果报告如实披露，评分以“终稿是否含该义务”为准。
- 状态与验证：**已实施并逐例验证**（见上）。
- 变更记录：2026-10-15 新增。

## FL-D062 G15 销售服务费支付句长尾措辞，确定性锚点无法稳定覆盖

- 发现日期：2026-10-15（P6 开发集离线验证）。
- 问题与影响：G15 要求删除“C类基金份额的销售服务费每日计提…按月支付…”支付句。20 份开发集里该句至少 5 种措辞（见 FL-D059 补充表），且与费率计算公式段落（“H为C类基金份额每日应计提的销售服务费”）邻接。任何固定短锚要么漏（“每日计提”↔“每日计算”）、要么泛（“逐日累计至每月月末，按月支付”每份命中 4–6 处），误伤风险高。
- 证据：离线对 20 份 `funds_word` 合同跑 `find_old_text_all`，结果见本轮工具输出；`var/recall-first-evaluation/p6-dev-baseline-01/D10|D11|D12/report.json` 的 G15 均 `state=absent status=not_applicable`。
- 处理方法（方案②已实施）：survey 侧新增**通用结构化兜底**，不再使用单一字符串锚——
  - 仅对“纯删除（delete-only）”规则生效（`_delete_keyword_bag`）：从规则 `operations[*].old_text` 的**全部**删除引用中，按三组闭类词表各取首个命中词，组成三元签名：领域词（销售服务费/申购费/赎回费/认购费/管理费/托管费/销售服务费率）＋动作词（支付/划付/划出/划款/计提/计算）＋期间词（按月/次月/每月/逐日/每季）。三组缺一即返回空（不启用兜底）。当前 guide 中**只有 G15 命中**（`销售服务费/支付/按月`）；G17 无期间词、G13/G06 无期间词，均不启用，天然规避跨规则误伤。
  - 仅在该规则**所有固定锚点均未命中**时启用（`len(hits) == rule_hits_before`）。
  - 命中判定 `_keyword_bag_in_clause(body, bag, window=60)`：要求三词在**同一 60 字窗口**内共现，避免“托管费句 + 邻接（三）销售服务费 标题”被整段匹配误报（H06 p1203 实测：销售服务费与按月相距 96 字，被窗口排除）。
  - 支持**跨段续句**：本段窗口不满足时，测试“本段+紧随段”合并体；仅在合并体命中时产出**复合位置**命中 `(本段, 次段)`，不重复计两次。
- 状态与验证：**已实施，独立验证**。对全部 28 份样本（20 dev + 8 holdout）离线跑 `survey_targets`：有 G15 条款的合同**精确命中 2 处**（正文+摘要，单段或复合跨段），无销售服务费类别的 D07/D09/D13/H02 **正确为 0**，零明显误报。全量测试 **546 passed / 1 expected / 6 skipped**；新增单测 `test_delete_keyword_bag_finds_paraphrased_payment_clause`。真实链路复验待发布后第二轮批次。
- 变更记录：2026-10-15 新增（记录为“未解决”）；同日补充方案②实施与离线验证（本条保留历史结论）。

## FL-D060 无条件 append 规则在目标段落缺失被模型盘点判 not_applicable（漏加）

- 发现日期：2026-10-15（P6 开发集基线：D01）。
- 问题与影响：G01（释义-份额类别定义）、G03（基金的基本情况-份额类别设置）为条件 `none` 的 append，要求在原文该条款后追加“通过直销机构申购A类不收取认购/申购费用、直销机构申购C类不收取销售服务费、其他销售机构申购C类持有超一年不再收取”段落。D01 原文**完全不含“直销”字样**，属应新增；引擎盘点判 `not_applicable`（“该窗口未出现G01要求新增的…内容”），最终 DOCX 未追加。append 无 `old_text` 锚点，survey 不产出 append 目标，完全依赖模型盘点，长合同段落窗口覆盖不足即漏。
- 证据：`var/recall-first-evaluation/p6-dev-baseline-01/D01/report.json` → G01 p92、G03 p130 `state=absent status=not_applicable`；原件全文无“直销”。
- 处理方法（待定）：可对 `section_hint` 存在但新文本缺失的 append 规则增加确定性 survey 兜底（定位 section 末段插入）。需先评估跨样本出现率与误加风险，避免在错误位置追加。
- 状态与验证：**未解决**（已记录，等全量开发集统计出现率后决定是否实现）。
- 全量开发集统计（2026-10-15 基线 20 份完成）：G01/G03/G16 的 `not_executed` 在全量口径占 10/10/7；但**其中一部分是评测器与标注器口径问题而非引擎漏改**，拆分如下：
  - **评测器 `p6_score` append 判定过脆（已修复）**：原判定用 `required_text` 的前 40 字**精确前缀**匹配，合同把“申购”写成“认购/申购”、或多一个括注即判 `not_executed`。改为 `appendix_present()`：先归一化常见变体（`认购/申购`→`申购` 等），再匹配义务**首分句**，必要时对首段做 ≥0.85 滑动重叠匹配。修复后 D05（原件无、终稿有 → 引擎**确实正确追加**）由误判 `not_executed` 纠正为 `completed`；D10/D15（原件已有）纠正为 `completed`；D01/D09/D19（原件与终稿都无 → **真漏加**）仍为 `not_executed`；D13 仍为 `not_executed`。开发集口径 0.712→0.754。
  - **标注器对 append 过标（未解决）**：`p6_label.py` 对 append 目标一律记录（`anchor=None`、无 `compact_start`），**不检查合同是否已含该义务文本**。D10/D15 原件已含 G01 政策句，本不应成为目标。属独立标签的已知局限，**不修改冻结标签**（改 gold 即制造通过），在结果报告中如实披露，评分时以“终稿是否含该义务”为准（已由 `appendix_present` 覆盖）。
  - **引擎真漏加（未解决）**：D01/D09/D19 等确定原件无该政策句而终稿仍无。append 无 `old_text` 锚点、survey 不产 append 目标，完全依赖模型盘点；长合同/窗口覆盖不足即漏。**优化方向**：对条件为 `none` 的 append 规则，在 `section_hint` 命中且原合同无该义务文本时增加确定性目标（定位 section 末段插入），需评估误加风险。
- 变更记录：2026-10-15 新增；同日补全量统计与评测器/标注器/引擎三类归因拆分。

## ML-001 证据核对必须使用 inspect_docx 的段落 location，不能用 XML 段落序号

- 发现日期：2026-10-15（P6 开发集评分期间自查）。
- 问题与影响：用 `docx` 里 `<w:p>` 的顺序序号（`ps[459]`）核对措辞，与引擎/标签使用的 `inspect_docx` location（`p459`）**不是同一编号**。曾据此误判 D01 的 G05“只改了一处、其余漏改”，实际 `p135`（XML 160 段）才是 G05 的正确目标且已修复；`p434/p1100` 的两句本身同时含“调低赎回费率、调低销售服务费率”，属已满足，不构成漏改。同类疑点还出现在 D03 的 G15/G17（核后为 p751/p752 的正当目标，非误报）。
- 处理方法：一切证据核对统一用 `inspect_docx(path, full=True).by_location(loc).text`；评分器也按标签 `compact_start` 走自己的 `paragraphs_of` 枚举并保持与标签器一致。
- 状态：**已确立为核对规范**。评分器 `tools/evaluation/p6_score.py` 已按此校准（区域判定用 `locate_paragraph` 按内容找回段落）。
- 变更记录：2026-10-15 新增。

## FL-D061 机器身份混淆：云服务器内网地址被误当“另一台开发机”

- 发现日期：2026-10-15（接续 agent 在云服务器上作业时自曝）。
- 问题与影响：文档用“本机（笔记本）”指代**已停用的 Windows 开发机**，用“服务器”指代云端。接续 agent 在云服务器上读到“本机”字样时，把云服务器的**内网网卡地址** `172.28.217.241` 误当成“另一台开发机”，进而错误判断“我所在的是开发机、对外 `8.155.130.168` 是另一台”，并据此提出不需要的 root 权限请求。实际 `172.28.217.241` 是同一台机器的内网地址，公网出口即 `8.155.130.168`。属**认知错误**（文档表述可消除该歧义）。
- 证据（实测）：
  - `hostname` = `iZf8zemhifedxdow1zefr0Z`；
  - `ip -4 addr`：`lo 127.0.0.1`、`eth0 172.28.217.241/20`（内网）；
  - 公网出口 `curl ifconfig.me` = `8.155.130.168`；
  - 阿里云元数据 `http://100.100.100.200/latest/meta-data/instance-id` = `i-f8zemhifedxdow1zefr0`、`region-id` = `cn-heyuan`。
  - 结论：**`172.28.217.241`（内网）与 `8.155.130.168`（公网）是同一台云服务器**，主机名 `iZf8zemhifedxdow1zefr0Z`。
- 处理方法：
  1. 在接续文档头部固定“机器身份块”，写明当前工作机 = 云服务器（主机名/公网/内网/区域），并明确“**文档中的‘本机/笔记本’一律指已停用的 Windows 开发机，不是当前工作机**”。
  2. 核对任何环境信息前，先跑一遍身份采集（`hostname` + 内网 + 公网出口 + 元数据），禁止仅凭内网地址判断机器。
- 状态与验证：**已登记并加机器身份块**；本次实测通过。
- 变更记录：2026-10-15 新增。

## FL-D076 Codex CLI 独立二进制安装缺少 bundled bwrap，沙箱无法启动导致一条命令都执行不了

- 发现日期：2026-10-15（在云服务器 `iZf8zemhifedxdow1zefr0Z` 上安装并首次运行 Codex CLI v0.162.1 时）。
- 问题与影响：**独立二进制方式**安装的 Codex（`~/.local/bin/codex`，来自 GitHub release `codex-x86_64-unknown-linux-musl.tar.gz`）缺少随包发布的沙箱组件，导致 Codex 执行任何 shell 命令都直接 panic，无法读取项目、无法工作。表现为 Codex 回复「运行环境缺少沙箱组件 bwrap」，但实际上系统已装有 `/usr/bin/bwrap`（bubblewrap 0.4.0），并非"缺失"。共经历**两个独立故障点**，需分别修复。
- 证据（实测）：
  - 现象：`codex exec "运行 pwd"` 返回 `pwd 未能执行：运行环境缺少沙箱组件 bwrap`。
  - 开启 `RUST_LOG=debug` 后拿到真实 panic：
    `bubblewrap is unavailable: no system bwrap was found on PATH and no bundled codex-resources/bwrap binary was found next to the Codex executable`
    （`linux-sandbox/src/launcher.rs:60`，exit_code=101）。
  - **故障点 1：Codex 沙箱子进程的 PATH 与登录 shell 不一致**，虽 `/usr/bin/bwrap` 存在但查找失败；且 `~/.local/bin/codex-resources/` 目录不存在——官方发布版会把 bwrap 放在可执行文件旁的 `codex-resources/`，而裸二进制安装没有该目录。
  - **故障点 2：哈希校验**。把系统 `/usr/bin/bwrap`（sha256 `7b42f144d8…`）放到 `codex-resources/bwrap` 后，Codex 拒绝：
    `bundled bubblewrap digest mismatch … expected sha256:01fb705f067bd5365b63d8ad2323a61c8d007733ca5e649437e086f3fb9935d8, got sha256:7b42f144d8130404c265db4a0a5ee913632c369444a1d52128997a484fa3031b`
    → Codex 要求**指定版本**的 bwrap，不能随便用系统版本。
  - 官方 release 中名为 `bwrap` 的资源实为 **dotslash 脚本**（1.2 KB，指向 `bwrap-x86_64-unknown-linux-musl.zst`），不是可直接执行的二进制，环境无 `dotslash` 无法使用。
  - 正确来源：`bwrap-x86_64-unknown-linux-musl.zst`（233 KB，zstd 压缩），解压后 529776 字节，sha256 = `01fb705f067bd5365b63d8ad2323a61c8d007733ca5e649437e086f3fb9935d8`，`--version` 输出 `bubblewrap built for Codex`，与期望哈希**完全一致**。
  - 修复后验证：`codex exec "运行 pwd"` → `exec /bin/bash -lc pwd in /home/opencode/fundlex  succeeded in 0ms: /home/opencode/fundlex`（由 `panicked`/`denied` 变为 `succeeded`）。进一步实测 `codex exec` 成功列出项目目录并读取 `README.md`。
- 处理方法：
  1. 从 release 下载 `bwrap-x86_64-unknown-linux-musl.zst`（本次经 `gh-proxy.com` 镜像，直连 GitHub 极慢）。
  2. 用 Python `zstandard` 解压（环境无 `zstd` 命令行工具，`pip3 install --user zstandard` 可用）。
  3. 安装到 Codex 期望位置并保持原权限：
     `install -m 755 bwrap-new ~/.local/bin/codex-resources/bwrap`。
  4. **不要**用系统 `/usr/bin/bwrap` 顶替——哈希校验会失败。
  5. 同类注意：`codex-code-mode-host` 也需单独补装（否则报 `Code Mode is unavailable … host executable was not found`），来源为 `codex-code-mode-host-x86_64-unknown-linux-musl.tar.gz`，安装到 `~/.local/bin/codex-code-mode-host`。
  6. 独立二进制另一个已知限制：顶层 `codex` 交互模式需加 `--no-daemon`，否则报 `this CLI has no complete local package`；`codex exec` 等子命令不受影响。
- 状态与验证：**已实施并已验证**（2026-10-15）。范围：Codex CLI v0.162.1，独立二进制安装，Alibaba Cloud Linux 3（RHEL 系）/ bash。验证方式为真实 `codex exec` 命令执行成功并读取项目文件，非仅凭 doctor 通过。
- 下一步：若后续改用官方提供的打包安装方式（如 `.deb`/`.rpm` 或带 `codex-resources` 的完整包），上述手工补装步骤可省略；升级 Codex 版本后需重新核对 bundled bwrap 的期望哈希是否随版本变化。
- 变更记录：2026-10-15 新增；同日编号由误用的 FL-D066 更正为 **FL-D076**（FL-D066 已用于「中断批次遗留模型账本 reserved 预留」，编号冲突）。

## FL-D077 集中问题记录出现编号冲突（FL-D057/058/066/068/069 各有两个不同含义）

- 发现日期：2026-10-15（第 8 轮交接前自查，用户此前已强调"不要重复/遗失既有结论"）。
- 问题与影响：`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 中 5 个编号被两处不同问题重复占用，违反 AGENTS.md"每项问题使用稳定编号"与"不重建编号"的纪律，接续 agent 交叉引用会指错条目：
  - FL-D057：①「3307 DB 受限账号凭据方案」（line 605）②「sweep 误报 G02/G04 分组替换」；
  - FL-D058：①「旧方案文档归档」②「无服务费类别产品销售服务费判定」；
  - FL-D066：①「中断批次遗留账本 reserved 预留」②「Codex CLI 缺 bundled bwrap」；
  - FL-D068：①「无标点段落追加 fragment 拼接遗漏」②「评分器以短锚点判删除 kept」；
  - FL-D069：①「前端上传全局互斥」②「G17 删除义务跨两段」。
  根因：多轮并发写入时，后写入者按当时可见的最大编号递增，未先全文查重。
- 证据：`grep -n "^## FL-" docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 重号；`grep -oP "^## FL-D\K[0-9]+" | sort | uniq -d` 输出冲突编号。
- 处理方法（已实施）：保留**首次出现**的编号不变（其含义已被 `docs/TASK_PLAN_UX_AND_APPEND_20261015.md`、`docs/archive/README.md`、`docs/ACTIVE_HANDOFF.md` 引用），把**后出现的重复项**改为未占用的新编号并加"编号更正"变更记录，不删除历史、不重建编号：
  - FL-D057 → **FL-D072**（sweep 误报 G02/G04）；② FL-D058 → **FL-D073**（无服务费结论）；③ FL-D068 → **FL-D074**（评分器短锚误判）；④ FL-D069 → **FL-D075**（G17 跨段删除）；⑤ FL-D066 → **FL-D076**（Codex bwrap）。
  同步修正唯一一处代码内引用：`tools/evaluation/p6_score.py`（评分器短锚说明）FL-D068 → FL-D074。
- 状态与验证：**历史修复不完整，当前仍有重复标题编号**。本轮 `grep -n '^## FL-D'` 和排序去重核对确认 FL-D088、FL-D089、FL-D118、FL-D152、FL-D153、FL-D224 各仍有两个不同含义的一级标题；原条目中“75 条编号全部唯一”的结论已过期。当前未原地重排历史编号，也未修改外部文档引用，以免把历史证据指向错误问题。
- 复发（同日）：规范化提交轮次又新增一条占用 FL-D072 的条目（「工作区长期未提交、版本管理缺失」）→ 已按同一规则改号为 **FL-D078**，冲突清零。
- 下一步：后续新增条目必须先在全文搜 `^## FL-D` 确认编号未被占用；编号更正一律"保留旧条目 + 新增一行变更记录"，禁止原地重排。
- 变更记录：2026-10-15 新增；2026-10-26 复核发现上述六组重复编号复发/遗留，原“唯一”验证结论撤回，待按历史引用关系建立稳定的新编号并同步交叉引用。

## FL-D079 变体模糊匹配的 span 停在句中，替换后残留半句碎片（D01 p934 出现“…（如有）。配。”）

- 发现日期：2026-10-15（构建交付包时复核 D01 终稿实际文字）。
- 问题与影响：`variant_replace`（G22 等变体替换）用 `fuzzy_span(actual, old_text)` 定位参考文本，`find_fuzzy` 返回的是**字符窗口最优解**而非句边界。D01 p934 合同写作“按基金份额持有人持有的**各类**基金份额比例进行分配。”（80 字），指引参考为“持有的基金份额比例进行分配。”（无“各类”，相似度 0.974）。`fuzzy_span` 返回 `end=77`，即停在“……比例进行分”，保留下来的后缀“配。”被拼到新文之后，终稿出现“……销售服务费（如有）。配。”——语义正确但残留半句碎片，且 `（修改痕迹版）` 会把该碎片一并呈现给用户。
- 证据：`var/recall-first-evaluation/p6-dev-baseline-01/D01/report.json` → `plan.edits` 中 `location=p934`、`replacement` 以“……（如有）。配。”结尾；原件 p934 实为 80 字、`span=[0,79]`；`fuzzy_span(actual, reference, threshold=0.95) == (0, 77, 0.974)`，`actual[77:] == "配。"`。
- 处理方法（已实施）：新增 `fuzzy_span_clause()`——在 `fuzzy_span` 之上做**句边界吸附**：参考文本以句末标点（`。！？；`）结尾时，把窗口向后延伸到该段下一个句末标点，或回退到最后一个完整句边界，绝不保留半句尾巴。`variant_delete`/`variant_replace` 与审计复核（`_confirm` 的变体校验）三处统一改用该函数，保证生产与独立复核用同一判定，不会把修复判成不通过。
- 状态与验证：**已实施并验证**。D01 p934 复算：`fuzzy_span_clause` 返回 `(0, 79, 0.974)`，后缀为空，替换结果以“……（如有）。”正常结束，无“配。”。新增回归测试 `test_fuzzy_span_clause_snaps_to_sentence_boundary`（断言 raw 留“配。”、snapped 后缀为空且以“。”结束）。全量 `.venv/bin/python -m pytest tests -q` → **563 passed / 1 expected（references/ 未在服务器）/ 6 skipped**。**未 commit、未 push。**
- 下一步：该修复随下次发布生效；重跑 D01 类样本（含 G22 变体）复验终稿与痕迹版均无碎片。同类风险：任何“参考文本带句末标点、合同措辞略有出入”的变体替换路径。
- 变更记录：2026-10-15 新增。

## FL-D080 G17 同一删除义务在合同中出现两次（正文 + 后部重复章节），survey 只处理首处

- 发现日期：2026-10-15（P6 开发集第 1 轮交付包复核，D01）。
- 问题与影响：G17（删除“C类基金份额的销售服务费主要用于支付销售机构佣金…/使用范围不包括…”）的措辞在合同中出现**两次**：正文 p759+p760 一处、后部“基金费用与税收”重复章节 p1222+p1223 一处。规划侧只把 p759 绑为 `planned`（`variant_delete`，已删除）；survey 另把 p1222+p1223 绑为复合目标 `Y006`，但该目标进入 `unresolved`（未产出编辑），**次处条款原样保留**；同时 p760 的续句“销售服务费使用范围不包括基金募集期间的上述费用。”也因复合删除只覆盖 p759 分片而残留。开发集 G17 `kept` 11 例多由此引起（评分器按标签 `compact_start` 区域判定，次处仍在即判 `kept`）。
- 证据：`var/recall-first-evaluation/p6-dev-round1-01/D01/report.json` → `targets` 中 G17 有 `T019`（p759, planned）与 `Y006`（p1222+p1223, unresolved, `composite=["p1222:0:17","p1223:0:25"]`）；`plan.edits` 仅 p759（`variant_delete`）。终稿实读：p759=`' '`（已删）、p760 仍含“使用范围不包括…”、p1222=`'销售服务费主要用于支付销售机构佣金…'`、p1223=`'销售服务费使用范围不包括基金募集期间的上述费用。'`（两处均未删）。审计对 p759 判 `completed`、对 p1222 判 `wrong/incomplete`。
- 处理方法（已实施）：修正 `survey_targets` 中“引用续接”分支构建复合 parts 的方式。原代码 `parts = [parts[0], follower_part]` 直接复用 `find_old_text_all` 的**未延伸窗口**（`p1222:0:17`）并把 `_reference_continuation` 返回的**裸长**（`p1223:0:25`，含尾空格）混入同一 parts；`plan_composite_target` 要求 parts 的偏移都在**各段 compact 文本**内，`25 > compact_len(24)` 即抛 `RECALL_TARGET_COMPOSITE_UNRESOLVED`。现改为：part0 用本命中**延伸后的 raw span** 经新增 `_raw_to_compact()` 映射回 compact 偏移；part1 用跟随段 compact 长度。这样“同一删除义务多处出现”（正文 + 后部重复章节）都能产出可规划的复合目标。
- 状态与验证：**已实施并验证**。同一 D01 合同离线复算 G17 survey：两处（`p759+p760`、`p1222+p1223`）parts 均为 `(loc,0,compact_len)` 且 `0<=start<end<=compact_len` 全部 OK（修复前第二处为 `17/25` 越界）。新增断言到既有测试 `test_delete_reference_continues_into_next_paragraph`（校验每个 part 的偏移合法）。全量 **567 passed / 1 expected（references/）/ 6 skipped**。
- 下一步：用真实链路复跑 D01 等含 G17 双处出现的样本，确认两处均删除、`Y006` 不再 unresolved；再量化 G17 `kept` 是否随之下降（开发集 G17 残留 11 例）。
- 变更记录：2026-10-15 新增（构建结果交付包时发现）；同日实施 `_raw_to_compact` 与 parts 偏移修正并验证。
- 变更记录：2026-10-15 新增（构建结果交付包时发现）。

## FL-D081 模型中间结果缺乏可观测性，无法做评测回归对比与根因定位（接入 Langfuse Cloud）

- 发现日期：2026-10-15（用户提问「能否接入 Langfuse 对中间结果监控以改进评测」）。
- 问题与影响：模型调用的中间结果没有可检索的落点——`ModelGateway.call` 的 `event` 只存在于内存 `self.events`，report.json 只留最终决策；因此**无法跨轮对比逐目标 diff、无法把某个失败 verdict 追到具体模型调用与 prompt 阶段**，只能靠人工翻 report。用户要求按「①回归对比 ②根因定位 ③成本效率」的顺序解决。
- 选型证据：本机（生产服务器）**无 Docker/podman/containerd**，无 Postgres/ClickHouse/Redis/MinIO；内存 7.4GB、磁盘 40GB，且已跑生产 API/worker/nginx/MySQL。自托管 Langfuse v4 需 Postgres+ClickHouse+Redis+MinIO+web+worker 共 6 个常驻服务，官方建议 4 核/16GB/100GB → **自托管不可行**。用户明确「合同均为公开资料，可入库、可出服务器」，故采用 **Langfuse Cloud（方案 A）**：本机仅装 `langfuse==5.0.1`（+OTel 依赖），零常驻服务。
- 处理方法（已实施）：
  - 新增 `fundlex/observability.py`：所有 Langfuse 交互的唯一收口。**无 key 时纯 no-op**；任何导入/配置/网络异常都降级为「不追踪」并被吞掉（可观测性绝不能让一次修改失败）。
  - `fundlex/model.py`：`call()` 内新增 `_trace_attempt()`，每次模型尝试发一个 generation（复用已有 event 字段：task_type/prompt_version/model/usage/cost/latency/http_status/error_code/reused_checkpoint）。
  - `fundlex/jobs.py`：新增 `_document_trace(job, store)`，以 **document_id 为确定性 trace seed** 开根 span（重跑/重试落同一 trace，不重复）。
  - 新增 `tools/evaluation/p6_langfuse_sync.py`：把 `score.json` 的逐目标 verdict 作为 CATEGORICAL score 回写同一 trace，实现「过程↔结果」对齐；支持 `--dry-run`。
  - `.env.example` 登记 `FUNDLEX_LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST/CAPTURE_TEXT`（默认关、默认存原文；`CAPTURE_TEXT=0` 时只发 sha256+长度）。
  - 合同资料政策更新（用户授权）：`AGENTS.md` 注明合同为公开资料，可入库、可出服务器；**仅凭据仍严禁入库/写入日志/第三方**。
- 状态与验证：**已实施并本地验证；云接入待用户 API key**。
  - 用本地 OTLP 收集桩（`/tmp/opencode/otlp_stub.py`）验证真实发射：收到 `/api/public/otel/v1/traces`（根 span `recall-first:<file>` + 子 span `recall_facts`，**trace id 一致**）与 `/api/public/scores`；generation 带 input/output/model/usage_details/cost_details/`langfuse.version`；score 带完整 metadata（case_id/rule_id/target_id）。
  - 新增 `tests/test_observability.py`（5 项）：无 key no-op、双 key 才启用、脱敏哈希、真实 `call()` 发 span、trace seed 确定性。全量测试 **568 passed / 6 skipped**（无回归）。
  - 文档：`docs/LANGFUSE_OBSERVABILITY.md`（选型、架构、用法、验证、待办）。
- 下一步：① 用户提供 Langfuse Cloud public/secret key → 跑 2 例验证真实 trace 入库，再跑整轮开发集；② 可选把批次 id 作为 tag 便于回归对比。
- 变更记录：2026-10-15 新增；同日完成代码实施与本地 OTLP 验证。

## FL-D082 交付包需包含工作台同格式的「结果清单.csv」（用户要求放根目录）

> **编号更正**：本条原误用 FL-D081，与更早的「模型中间结果缺乏可观测性（Langfuse）」重号；按 FL-D077 规则（首次出现者保留编号），观测性条目保留 FL-D081，本条改号 **FL-D082**。

- 发现日期：2026-10-15（用户对交付包提出要求）。
- 问题与影响：`tools/evaluation/p6_package.py` 打出的交付包原先只有 `结果总览.md` + 最终版 + 逐份说明，缺**工作台点「导出结果清单」时下载的那个 CSV**。用户明确要求把它加上并放在**根目录**（`结果总览.md` 保持不变）。
- 证据：`frontend/app.js:156` 的 `exportResults()` 生成 `${task.name}_结果清单.csv`，列为 `序号,文件名,资格,处理状态,交付完整性,业务提示,原始原因码`，内容为 `'\ufeff'+ rows.map(csvEscape).join(',')`、行以 `\r\n` 连接（`csvEscape` 对含 `",\n\r` 的值加引号并双写引号）。
- 处理方法（已实施）：`p6_package.py` 新增 `build_result_csv()`/`delivery_reason()`/`reason_codes()`/`csv_escape()` 与 `CSV_LABELS`，在根目录写出 `结果清单.csv`，逐列对齐工作台：资格/处理状态/交付完整性走同一套中文标签，业务提示复刻 `docReason()` 的措辞，原始原因码只用**短机器码**（`RECALL_*`/`AUDIT_*`，不含审计散文）。文件带 UTF-8 BOM、CRLF 行、含逗号/引号/换行的字段按工作台规则转义；`结果总览.md` 的文件夹说明表新增一行指向该 CSV。
- 状态与验证：**已实施并验证**。用 `p6-dev-round1-01` 重新出包 `var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/`：根目录出现 `结果清单.csv`（BOM+CRLF，21 行=表头+20 份，列头与工作台完全一致；失败样本的最后列是 `RECALL_TARGET_COMPOSITE_UNRESOLVED；AUDIT_NOT_COMPLETED` 等短码）。新增测试 `test_result_csv_matches_workbench_columns`（断言 BOM、CRLF、列头、末列为机器码）；全量 **572 passed / 1 expected（references/）/ 6 skipped**。
- 下一步：交付含留出集的完整包时同样带上该 CSV；如工作台列顺序调整需同步本工具。
- 变更记录：2026-10-15 新增。

## FL-D083 Langfuse 新组织禁用 legacy REST API；凭据已配置并跑通真实云端链路

- 发现日期：2026-10-15（用户提供 Langfuse Cloud 凭据后做真实链路验证）。
- 问题与影响：Langfuse 对 **2026-09-16 及之后新建的组织**禁用了 legacy REST API——`/api/public/traces`、`/api/public/observations`、`/api/public/scores`、`/api/public/sessions` 均返回 **410 `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`**。这不影响**写入**（v5 SDK 走 OTLP，正常），但会影响日后写**查询/导出**脚本（如按 trace 拉评分做回归对比）。
- 证据：`GET https://jp.cloud.langfuse.com/api/public/observations` → `410 LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`；`GET /api/public/traces/<id>` → `410`；正确端点为 **`GET /api/public/v2/observations?traceId=<id>`** 与 **`GET /api/public/v3/scores?traceId=<id>`**（均返回 200）。
- 处理方法（已实施）：凭据写入**仓库外** `/home/opencode/.env`（权限 `600`，已 gitignore；键名从用户的 `LANGFUSE_*` 映射为项目前缀 `FUNDLEX_LANGFUSE_*`，`FUNDLEX_LANGFUSE_HOST=https://jp.cloud.langfuse.com` 日本区）。查询脚本一律用 v2/v3 端点。
- 状态与验证：**真实云端链路已跑通并验证**。
  - `auth_check: True`（`jp.cloud.langfuse.com`）。
  - 冒烟 trace `b1648f73fd644bd3e0d81e04271db3c6`：根 span `recall-first:smoke-test.docx`（SPAN）与 generation `recall_facts`（`version=facts_v1`）**同一 trace**；`/api/public/v2/observations?traceId=` 返回二者。
  - score `target_verdict=completed`（CATEGORICAL）经 `/api/public/v3/scores?traceId=` 过滤确认**已挂在该 trace 上**（返回 1 条）。trace URL：`https://jp.cloud.langfuse.com/project/cmv9mjp4a0007ad0l1xzij95v/traces/b1648f73fd644bd3e0d81e04271db3c6`。
- 下一步：跑 2 例真实开发集，确认六阶段（facts/scope/inventory/compose/audit/sweep）完整 trace 后跑整轮；查询脚本统一 v2/v3 端点。凭据仍严禁入库/写日志。
- 变更记录：2026-10-15 新增；同日发现 legacy API 410 并确认正确端点、跑通冒烟链路。

## FL-D084 用户授予 opencode 本机 root 写权限（部署/运维可用，全部 agent 须知）

- 发现日期：2026-10-15（用户明确要求「把这个信息记下来，让其他 agent 都知道有 root 的写权限」）。
- 问题与影响：此前 `opencode` 用户只有一条受限 sudo（`/usr/local/sbin/fundlex-publish`），无法改 `/etc/fundlex-recall.env`（root 600）、无法读 `/var/lib/fundlex/`、无法直接重启服务——导致 Langfuse 环境变量加不进生产 worker、部分运维验证做不了。用户已授予完整 root。
- 证据：`sudo -n -l` 显示 `(root) NOPASSWD: ALL`；规则文件 `/etc/sudoers.d/fundlex-agent`（用户提供的原文含两行：既有 `fundlex-publish` 白名单 + 新增 `ALL`）。`sudo -n true` 成功；已确认 `/etc/fundlex-recall.env` 可读（`item_count=23`）。
- 处理方法（已实施）：① 写入本文件与 `AGENTS.md`（项目级规定，含使用边界）；② 断点文档 `docs/ACTIVE_HANDOFF.md` 记录；③ **使用边界**：仅用于 FundLex 部署/配置/服务/验证，不动无关系统配置；**凭据值严禁写入仓库/文档/prompt/日志**，只记变量名与路径；改配置先备份。
- 状态与验证：**已实施并验证可用**。
  - 已用它完成：读 `/etc/fundlex-recall.env` 结构、**备份** 为 `.bak-langfuse`、**追加** `FUNDLEX_LANGFUSE_*` 四项（值已在文件中，未入库）。
  - 部署侧待办：`/opt/fundlex-recall-first` 尚无 `observability.py`，且该 venv **未装 `langfuse`**；需 `sudo -n /opt/fundlex-recall-first/.venv/bin/pip install langfuse` + `bash tools/deploy/publish_workspace.sh`（会 `cp` 并 `systemctl restart fundlex-recall-api fundlex-recall-worker`）后才能让生产 worker 发真实 trace。
- 下一步：装包→发布→重启→跑 2 例真实链路→确认 Langfuse 六阶段 trace。
- 变更记录：2026-10-15 新增。

## FL-D085 Langfuse JP 区（jp.cloud.langfuse.com）接收到的 span 丢失 input/output/usage/cost/metadata

- 发现日期：2026-10-15（跑完 2 例真实链路后核对 Langfuse 云端数据）。
- 问题与影响：真实 2 例（D04/D05，118 调用，$0.0867）的 trace **结构完整**（根 span + 六阶段 generation，`sessionId` 分组正确），但**每次调用的输入、输出、token 用量、成本、metadata 全部为空**。这直接废掉可观测性的核心价值（根因定位、成本效率），只剩「调过几次」。
- 证据（关键，已定位到平台侧，**排除我方代码**）：
  1. **我方发送正确**：用本地 OTLP 收集桩（`/tmp/opencode/otlp_stub.py`）抓取，`recall_facts` generation 的 span 属性含 `langfuse.observation.input`（原文）、`…output`（原文）、`…usage_details={"input":120,"output":30,"total":150}`、`…cost_details={"total":0.0001}`、11 个 `metadata.*`。
  2. **云端存储为空**：`GET /api/public/v2/observations?traceId=…` 与 SDK `observations.get_many` 对同一批 span 返回 `input=None, output=None, usage_details=None, cost_details=None, metadata=None, model=None`；`latency=0`。等待 60s 后复读仍为空。
  3. **纯 SDK 复现**：不经过 FundLex 任何代码，用教科书写法（`Langfuse()` + `start_as_current_observation(as_type="generation", input=..., output=..., usage_details=..., metadata=...)`）发一条，JP 区读取**同样全为 None**（trace `997b7c28…`）。→ **非本项目缺陷**。
  3b. **官方 `@observe()` 装饰器复现**：用 Langfuse 官方最惯用写法（`from langfuse import observe, get_client` + `@observe()` 函数返回 dict）发送，JP 区读取仍是 `input=None, output=None`（`my_llm` span）。→ 彻底排除我方调用方式问题。
  4. 账号/鉴权/ingest 均正常：`/api/public/projects` 200、`/api/public/v2/observations` 200、观测条数与名称正确；`auth_check` 偶发 UnauthorizedError（疑似限流，稍后即恢复）。
- 影响范围：`jp.cloud.langfuse.com`；同一对 key 在其他区（`cloud/us/eu.cloud.langfuse.com`）均 UnauthorizedError（key 仅属 JP 组织）。
- 处理方法（**待定，需用户决定/或向 Langfuse 报障**）：候选 ① 在 Langfuse 项目设置里检查是否开了 data masking / retention 仅存结构；② 换区（用户在有数据的区新建项目并给 key）；③ 向 Langfuse 支持报障（JP 区 ingest 丢 payload）；④ 退化为**本地 JSONL trace**（我方发送链已证明可靠），必要时再回灌。
- 状态与验证：**已复现并定位（平台侧，非我方代码）**。我方代码侧无改动必要；本地发送链已验证正确。
- 下一步：等用户确认走 ②/③/④ 之一；在此之前不宣称「Langfuse 中间结果监控可用」。
- 变更记录：2026-10-15 新增。

## FL-D086 前端「处理进度」与「合同结果」两页高度重复（同一数据源、同一加载逻辑）

- 发现日期：2026-10-15（用户在前端试用时指出两页「几乎一样」）。
- 问题与影响：`#view-progress` 与 `#view-results` 都调用同一个接口 `GET /api/tasks/{task_id}/documents`，共用 `loadDocuments()`、任务选择器循环、`showDetail()` 与分页逻辑；差异只在列、筛选项和头部按钮。用户要在两页之间来回切换才能看全「上传/资格/交付/处理」四类状态，容易漏看；维护上任何一处改动都要同步两份，属于**重复实现且易漂移**的问题。
- 处理方法（用户选定方案：**一张表 + 全部列常显**，明确否决「视图切换」方案）：
  - 合并为单页「任务详情」（`id="view-task"`，`data-nav="task"`），不删除任何一页的既有能力，能力全部保留到该页。
  - **一张 `<table>`，固定 7 列表头常显**：合同文件 / 上传状态 / 资格 / 交付完整性 / 处理状态 / 业务提示 / 操作。**不做视图切换、不做列切换、不做双表头**。
  - 用**筛选器**承担聚焦职责，而非切换视图：搜索 + 上传状态 + 资格 + 交付 + 处理状态 + 原因 + 排序。
  - 头部同时展示运行态与交付态两组按钮；`#overall-counts` 与 `#result-counts` 两组统计**始终显示**。
  - 统一 DOM id 前缀为 `doc-*`；`data-detail` 统一为 `doc:i`，状态合并为单数组 `state.taskDocs`。
  - 分页名必须用 `name='doc'`（→ `state.docPage/docSize`）：`pagination()` 按 `name` 推导 `state[`${name}Page`]`，而 `taskPage/taskSize` 已被任务列表占用，若沿用会把两处分页串在一起。
- 附带修复的隐性缺陷：原 `emptyRow(cols)` 传的列数与实际表头列数不一致（progress 传 5、results 传 7、`resetWorkspace` 传 6/5，而实际分别是 5/7）。合并后统一为 7，空态用 `colspan=7`，列错位问题消除。
- 状态与验证：**已实施并已在真实浏览器验证**（Chromium/Playwright，非仅静态检查）。
  - 验证方式：本地起真实 API（`FUNDLEX_AUTH_MODE=dev`），用真实接口种子任务与文档，驱动真实页面；脚本 `/tmp/opencode/browser_accept.py`、`/tmp/opencode/browser_accept2.py`。
  - 实测结果：控制台/页面 **0 报错**；`#view-task` 唯一存在，`#view-progress`/`#view-results` 已删除；导航只剩一个「任务详情」；表头 7 列且全部可见；数据行 7 个单元格；`data-detail="doc:0"`；空态 `colspan=7`；筛选会以 `upload_status=pending` 等参数真实请求接口；分页 `data-page` 为 `doc`；`#overall-counts`/`#result-counts` 均正常填充；刷新后页面保持一致。
  - 另有 572 passed / 6 skipped（`tests/test_rules_catalogue.py` 1 例失败为既有基线失败，与本改动无关）；`app.js` 通过 modern JS 引擎（quickjs）语法校验；HTML 结构闭合校验 0 错误；JS 引用的 118 个 DOM id 全部存在于 HTML。
- 影响范围：仅前端 3 个文件（`frontend/index.html`、`frontend/app.js`、`frontend/app.css`），无后端/数据库/引擎改动，可用单次 commit revert 回退。
- 下一步：发布到 `/opt/fundlex-recall-first` 后在公网入口复核一次真实页面。
- 变更记录：2026-10-15 新增；同日完成后端无关的浏览器实测验证。

## FL-D087 HTML 呈现方案丢失目录、超链接、分页等结构（用户 2026-10-16 在前端发现）

- 发现日期：2026-10-16（用户查看 A-html demo 时指出「目录丢失」，要求排查是否还有别的东西丢失）。
- 问题与影响：demo 的 DOCX→HTML 转换（`/tmp/opencode/demo/convert.py`）**只遍历 `body` 顶层 `w:p` 与 `w:tbl` 两类元素**，其余顶层元素被静默丢弃。真实合同 D01 的 `body` 顶层子元素计数为 `{p: 1338, sdt: 1, sectPr: 1}`，而**整份目录（TOC）位于唯一的 `w:sdt`（长度 20806 字符）内部**，因此目录整块消失。逐项核对确认丢失/降级清单：
  - **整块丢失**：目录 `w:sdt`（含 24 个 `w:hyperlink`、23 个 `PAGEREF` 域、24 个 `bookmarkStart`、24 个 `TOC1` 段落）。
  - **域代码丢失**：75 个 `fldChar`、29 个 `instrText` 未渲染，域结果不可见（页码引用失效）。
  - **超链接降级**：`w:hyperlink` 分支仅提取内部 `w:r` 文本，**不输出 `<a href>`**，链接不可点击（A 页实测 `<a>` 仅 3 个，均为页面自身的导航标签，非合同内链接）。
  - **空白/换行信息丢失**：`w:tab` 被硬编码为三个 `&nbsp;`，`w:br` 固化为 `<br>`，制表与分页语义丢失。
  - **`sectPr` 分页信息丢失**：正文 13 个显式分页符 + 2 个 `sectPr` 未映射，整篇连排，无分页。
  - 段落计数差异：原文档 `w:p` 递归总数 1363，A 页仅 1252 个 `doc-p`，差 111 段（主要为 sdt 内目录段落与被判空丢弃的段落）。
- 证据：`contract.docx` 结构统计（`w:p` 1363 / `sdt` 1 / `hyperlink` 24 / `fldChar` 75 / `instrText` 29 / `bookmarkStart` 24 / `br` 13 / `tab` 54）；A 页 HTML `doc-p` 1252、`<a>` 3、不含「目录」「PAGEREF」；`TOC1` 样式在 `styles.xml` 中定义且带 `<w:hidden/>`。
- 根因：demo 转换器是**为验证交互（修订勾选）写的最小实现**，只覆盖 `w:p`/`w:tbl`/`w:ins`/`w:del`，未做通用块级元素遍历与域/超链接/分页映射；并非 HTML 方案本身不可行。
- 处理方法（用户已选定 **A 服务端 HTML 方案**，据此制定全链路改造，见 `docs/HTML_PRESENTATION_PLAN.md`）：
  1. 服务端新增通用 DOCX→HTML 投影：遍历全部块级元素（`w:p`/`w:tbl`/`w:sdt`/`w:sdtContent`），递归进入容器，不再只认顶层两类。
  2. `w:hyperlink` 输出真实 `<a href>`（`r:id` 经 `document.xml.rels` 解析，锚点链接映射为 `#bookmark`）。
  3. `w:fldChar`/`w:instrText` 域：TOC 域渲染为目录块并保留目录条目文本；页码域保留缓存结果文本，不显示域代码。
  4. `w:bookmarkStart` 输出 `<a id="...">` 锚点，使目录链接可跳转。
  5. `w:tab`→对应空白，`w:br type=page`→分页标记，`w:sectPr`→分页边界，恢复版式感知。
  6. 修订（`w:ins`/`w:del`）继续输出带 `data-rev` 的可交互节点，**保持 A 方案的核心能力不因通用化而退化**。
- 状态与验证：**已定位根因、已列出完整丢失清单**；修复方案已确认为 A 方案全链路改造，实施与验证见 `docs/HTML_PRESENTATION_PLAN.md` 的进度记录。
- 下一步：按计划实施服务端投影 + 逐条接受/拒绝 API + 新产物 kind + 前端交互，并做真实端到端验证。
- 变更记录：2026-10-16 新增条目并完成根因定位与丢失清单核对。

## FL-D088 修订审查端到端验证中发现的两个集成缺陷（已修复）

- 发现日期：2026-10-16（HTML 呈现方案 P6 真实云端端到端验证过程中）。
- 问题与影响：
  1. **产物无 `.docx` 后缀导致读取被拒**。存储产物保留原始上传文件名（无扩展名），而 `_read_parts` 以 `.docx` 后缀作为上传防护直接抛 `DOCX_ONLY`。表现为 `/revisions` 与 `/decisions` 端点对真实任务一律返回 422，新功能在真实路径上完全不可用。本地用 `.docx` 命名的测试副本时不会暴露，只有在真实存储路径上才出现。
  2. **前端 `pathDoc` 取错字段**。文档行接口暴露的是 `document_id`（`_public_batch` 的 `documents[]`），前端却拼接 `doc.id`，生成 `/api/batches/{b}/documents/undefined/revisions`，浏览器实测 404、面板显示"无法生成合同呈现"。
- 证据：
  - 缺陷 1：`tests/test_revision_api.py` 首轮实测 `422 {"detail":"DOCX_ONLY"}`；真实云端 `POST /decisions` 同样 422。
  - 缺陷 2：真实 Chromium 抓到的请求 URL 为 `.../documents/undefined/revisions`，响应 404，控制台报 `Failed to load resource: 404`。
- 处理方法：
  1. `html_view.project_docx` 与 `selective._read_redline_parts` 在路径后缀不是 `.docx` 时，先写入临时 `.docx` 副本再读，读取后删除；`_read_parts` 的全部包限制（大小、条目数、压缩比、加密、重复成员）仍然生效，未降低上传防护强度。
  2. 前端 `pathDoc` 改用 `doc.document_id`。
- 状态与验证：**已修复并已在真实云端验证**。真实生产任务（`recall_first`、delivery complete、17 条修订）经 `/revisions` → `/decisions`（拒绝第 1 条）→ 下载 `selected_final`：0 条残留修订、被拒条目还原原文、被接受条目保留替换文本；真实浏览器走完同一路径，0 控制台错误。回归：全套 596 通过。
- 变更记录：2026-10-16 新增并修复，附真实云端验证。

## FL-D089 端到端验证必须使用默认工作台入口（`POST /api/tasks`），不能用遗留 `/api/batches` 或直接建批次

- 发现日期：2026-10-16（P6 验证中三次误判后定位）。
- 问题与影响：验证脚本若用遗留 `/api/batches` 或直接调 `store.create_batch` 建批次，批次 `engine_id` 为空，会被路由到**遗留 `pipeline.process`（仅 ruleset）**路径，而不是 recall-first 引擎。表现为报告 `guide groups: 0`、`targets: 0`、`plan edits: 0`、`delivery_status: not_generated`，看上去像"引擎找不到条款"，实际是入口错了。我一度据此误判为"规则未发布导致无修订"，险些把错误结论写进交付说明。
- 证据：同一份干净合同 D01（sha256 `2f2f7a36…`）两种入口对比——遗留 `/api/batches`：`engine_id=''`、guide groups 0、targets 0；默认 `POST /api/tasks` + `engine_id='recall_first'` + `/uploads` + `/seal`：guide groups 22、targets 30、plan edits 17、delivery complete，产出 `final`/`redline`。
- 处理方法：端到端验证一律使用前端实际调用的默认入口 `POST /api/tasks`（`engine_id=recall_first`）→ `POST /api/tasks/{id}/uploads`（带 `client_ids` 表单字段）→ `POST /api/tasks/{id}/seal`；注意任务 `id` 与上传回执返回的 `batch_id` **不是同一个值**，文档/报告/产物端点要用 `batch_id`。
- 状态与验证：已确认并写入 `docs/HTML_PRESENTATION_PLAN.md` 的验证说明，后续验证按此执行。
- 变更记录：2026-10-16 新增。

## FL-D090 规则未发布状态下默认入口产出 0 条修订是当前正确行为（非缺陷）

- 发现日期：2026-10-16（P6 验证中确认）。
- 问题与影响：`rules/rules_v1.json` 的 `release_policy.status = "unreleased"`，22 个 action 全部 `auto_write: false`、`approved: false`；`/api/capabilities` 返回 `auto_write_enabled: false`、`auto_write_count: 0`。因此**基于 ruleset 的发布门是关闭的**。但默认入口走 recall-first 引擎 + 绑定指引快照（`guides/builtin_guide_v1.json`，22 组规则），该路径**不读取 ruleset 的发布门**，实测能正常产出 17 条修订与 `final`/`redline`。需要区分这两条路径，避免把"ruleset 未发布"误当成"默认入口无法交付"。
- 证据：默认入口实测 `delivery_status: complete`、17 条修订（见 FL-D089 对比）；`/api/capabilities` 的 `auto_write_enabled: false` 只反映 ruleset 路径。
- 处理方法：不修改任何发布标志。修订审查新功能对两条路径都兼容：`_report_has_revisions` 判定报告是否含可选择的修订，无修订时 `/revisions` 明确返回 `409 REVISION_REVIEW_UNAVAILABLE`，前端显示不可用提示，不伪造交付。
- 状态与验证：已确认。真实默认入口产出 17 条修订并完成逐条选择与下载（见 FL-D088 验证）。
- 变更记录：2026-10-16 新增。

## FL-D088 Langfuse 云端两区均丢 payload，改用本地 JSONL trace 兜底（用户选定）

- 发现日期：2026-10-16（承接 FL-D085；用户指示「退化到本地 JSONL trace 兜底，并用来帮助评测优化」）。
- 问题与影响：FL-D085 已证明**我方发送正确、云端两区（`jp.cloud.langfuse.com` 与 `cloud.langfuse.com`）都丢 payload**（含官方 `@observe()` 复现）。用户换标准区新 key 后现象不变，故不可依赖云端做根因定位。
- 处理方法（已实施）：新增 `fundlex/trace_sink.py`——纯标准库的本地 JSONL 记录器，**一个合同一个 trace**（`trace_id = sha256(fundlex:{document_id})[:32]`，与云端 seed 同构、可复现），**一次模型调用一条 generation**（含 input/output/usage/cost/metadata），**一个评测结论一条 score**。开关 `FUNDLEX_TRACE_JSONL`（未设则完全 no-op）；`FUNDLEX_TRACE_CAPTURE_TEXT=0` 时只存哈希与长度。活动文档 id 以 **thread-local** 携带，使引擎深处的模型调用自动归到正确 trace（worker 每线程一个文档）。接线点与云端并列：`model.py:_trace_attempt`、`jobs.py:_document_trace`；`tools/evaluation/p6_langfuse_sync.py` 同时写两路。
- 配套工具：`tools/evaluation/p6_trace_report.py`——把 JSONL 与评分结果按 trace_id 关联，产出「按规则/按阶段」的失败画像。单测 `tests/test_trace_sink.py`（6 项）。
- 部署：生产 worker 以 `fundlex` 用户运行，`/var/lib/fundlex/traces/`（0750 fundlex）为可写落点；`/etc/fundlex-recall.env` 追加 `FUNDLEX_TRACE_JSONL` / `FUNDLEX_TRACE_CAPTURE_TEXT`（备份 `…env.bak-tracesink`），并经 `publish_workspace.sh` 发布重启。
- 状态与验证：**已实施、已发布、已用真实批次验证**。2026-10-16 开发集 20 例（594 调用 / $0.5158）真实链路写入 **1085 行** JSONL，单条 generation 达 25KB（真实合同原文），19/20 案例 trace 匹配、0 个缺失、0 次模型错误。
- 变更记录：2026-10-16 新增（FL-D085 的处置结果）。

## FL-D089 评分器把「已正确追加的政策句」误判为 not_executed（份额类别枚举差异）

- 发现日期：2026-10-16（用 FL-D088 的 JSONL trace 对照真实终稿时发现）。
- 问题与影响：`p6_score.appendix_present()` 对 G01/G03/G16 的 append 判定，用 `required_text` 的**首分句字面匹配**（`认购/申购→申购` 等归一化后）。但标签模板按「A类/C类」写，真实合同常为「A类、D类」「A类、B类」，**引擎正确地用合同自身的份额类别追加**（如「申购本基金A类、D类基金份额时，不收取申购/认购费用」），字面比对即失配。模糊兜底按 4 字符步长滑动、阈值 0.85，也跨过了唯一匹配窗口。→ 把**引擎的正确工作**记成漏改，压低指标。**三重证据**：① D01 `report.json` 的 ledger 显示 G01/G03/G16 状态为 `planned/insert` 且带位置 p92/p135/p758；② D01 终稿 p92/p758 **确实含**该政策句（A类、D类变体）；③ D01 评分却是 `not_executed`。
- 处理方法（已实施）：新增 `_normalise_policy()`，在归一化时把**份额类别枚举整体折叠**（`A类、D类基金份额` / `A类、B类和C类基金份额` → 同一 token）；模糊兜底改为**逐字符**步进，避免跳过匹配窗口。新增回归测试 `tests/test_p6_score_append.py`（6 项，含「枚举差异应通过」与「确实缺失不得通过」两类）。
- 状态与验证：**已实施并验证**。同一开发集重评：**0.7892 → 0.8161**（223 目标，completed 176→182，`not_executed` 17→11），**无任何引擎改动**。反例核对：D09（确无政策句）仍为 `False`，未被误放；D19（原件已有 A/B/C 三类别）由误判纠正为 `True`，经查 p101/p130 确有该句，属真阳性。
- 变更记录：2026-10-16 新增。

## FL-D091 G01/G03/G16 append 目标在「直销渠道」措辞合同上被模型盘点判 not_applicable（FL-D060 的残留子集）（原编号 FL-D090，与他人条目冲突后改号）

- 发现日期：2026-10-16（FL-D089 修复后，剩余 `not_executed` 全部落在此家族时定位）。
- 问题与影响：修掉评分器误判后，开发集剩余 `not_executed` 全部是 append 规则（G01/G03/G16）。逐案例核对，实为**三层叠加**缺陷：
  - **① 措辞变体致盘点漏判**（D07）：原件 `…FOF基金合同_20221116.docx` 含「直销」2 次、措辞为**「直销渠道」**（p231/p854），非模板的「直销机构」；含「基金份额类别」9 次、「消费服务费」4 次，**追加对象存在**。引擎 ledger 却记 `not_applicable`（`RECALL_RULE_NOT_APPLICABLE` / 「无销售服务费条款」），终稿确无政策句。
  - **② 缺 class group 时 append 被整体判不适用**（D07 二次确认）：盘点其实**已生成** `needs_edit` 目标（G01@p114、G03@p142，位置与指引条款一致），但 `plan_target` 阶段因 `slot_group_missing` 为真且规则带 `class_substitution` → 直接 `RECALL_RULE_NOT_APPLICABLE`；`_drop_empty_group_operations` 又把 append 整条丢弃，最终 0 个可执行操作。
  - **③ 目标被 `absent`/未解析判定挡住**（D09/D13/D12）：pass 产出了正确 hit，但 `_survey_targets_from_hits` 的 `known` 集合含该规则既有的 `absent` 目标，hit 被静默跳过；D12 的 G03 是 `needs_edit` 但模型引文（"本基金 A 类份额、C 类份额分别设置代码…"）在原件中**不存在**，rebind 亦失败（`RECALL_TARGET_REBIND_FAILED`）。
- 证据：`p6-dev-round3-01`/`round4-01`/`round5-01` 各案例 `report.json` 的 `plan.ledger`、`targets`、`survey`；D07 原件词频；各终稿实测段落。
- 处理方法（**已实施**，承 FL-D060 方向①）：
  1. **`recall.append_applicability_targets()`**（确定性 append 适用性兜底）：对条件为 `none` 的 append 规则，在 ①`section_hint` 命中章节、②该义务政策句全文缺失、③规则无**可执行**目标 时生成目标；锚点**优先用盘点已指向段落**，指向标题（`_looks_like_heading`）时回退章节末段。`SERVICE_GROUP_EMPTY` 不再跳过（append 本就无条件）。
  2. **`plan_target` 的 class-substitution 门限收窄**：新增 `_needs_missing_class_group()`——可执行操作**全为 append** 时不算「缺组致不适用」；`_drop_empty_group_operations` 保留 append 操作；append 路径用新增 `_append_without_missing_group()` 只删掉点名缺失类别的分句并补正句末标点，其余政策句照常追加。
  3. **`_survey_targets_from_hits(override_rules=…)`**：append pass 的命中规则进入 `override_rules`，不再被既有 `absent`/未解析目标压制；pass 的 `known` 只统计**已解析的 `needs_edit`** 目标。
- 状态与验证：**已实施、已发布、真实批次逐步验证**。
  - 评分器修复（FL-D089）：0.7892 → 0.8161。
  - `round3`：0.8051（分母因新增目标变大）。
  - `round4`（append 兜底 + class-group 收窄）：**0.8178**，`not_executed` 15→9；**D07 终稿 p114/p142 实测确含政策句**（A类、Y类变体，p142 追加到真实份额类别条款之后），G01/G03 由 `not_applicable` 变 `completed`。
  - `round5`（absent/unresolved 覆盖 + 锚点修正）：**0.8333**（222 目标 / completed 185），`not_executed` **仅剩 8 例且全为 append**。
  - `round6`（override_rules 修复 hit 被既有目标压制）：进行中。
  - 回归：`tests/test_append_applicability.py` 12 项；全量 597 passed（排除在飞的 `test_selective.py`、缺源文件的 `test_rules_catalogue.py`）。
- 下一步：视 `round6` 结果决定是否继续收敛 D09/D12/D13 残留；达标后冻结并跑留出 H01–H08。
- 变更记录：2026-10-16 新增；同日 编号 FL-D090→FL-D091（与并行 agent 的 FL-D090 冲突），并补记 round3–round6 证据。

## FL-D092 前端改动已部署但用户页面看到旧版（静态资源无缓存标识）

- 发现日期：2026-10-16
- 问题与影响：详情面板区块顺序调整已发布，用户浏览器仍显示旧版式，误判为「服务器没生效/改动丢失」。根因：`frontend/index.html` 以无版本号的固定路径 `<script src="/static/app.js">`、`<link href="/static/app.css">` 引用资源，且 nginx 未下发 `Cache-Control`，浏览器沿用本地缓存的旧 `app.js`/`app.css`。影响所有后续前端发布：改动虽已上线，用户端可能长期看不到，且容易被误判成功能未交付。
- 证据：
  - HTTPS 实取字节与仓库/部署副本 sha256 一致（`bc5ac9c7d044e90d`），证明**服务端已是新代码**，问题在客户端缓存。
  - 修复前响应头无 `cache-control`，仅 `last-modified` + `etag`，静态资源 URL 无版本号。
- 处理方法：在 `fundlex/api.py` 的 `create_app` 中：
  - 新增 `_asset_version("app.css","app.js")`，按资源内容 sha256 生成 16 位版本标识，**每次发布自动变化**。
  - 入口 `/` 由 `FileResponse` 改为读取 `index.html` 文本并注入 `?v=<hash>` 后再返回，并下发 `Cache-Control: no-store, must-revalidate`。
  - 新增 HTTP 中间件：`/static/*` 下发 `public, max-age=31536000, immutable`（URL 带内容哈希，安全长期缓存）；`/`、`/index.html` 下发 `no-store`。
- 状态与验证：**已验证（生产）**。
  - 单元/接口：`TestClient` 校验 `/` 返回 `Cache-Control: no-store, must-revalidate` 且引用为 `app.css?v=a751d9b7f43c2426`、`app.js?v=a751d9b7f43c2426`；`/static/app.js|app.css` 返回 `public, max-age=31536000, immutable`。
  - 生产（`127.0.0.1:8010`/nginx）：首页实取含 `?v=a751d9b7f43c2426`、`no-store`；带版本号静态资源 `immutable`。
  - 真实浏览器（生产端点、真实登录）：16 条修订、目录 24 条 + 24 条链接、拒绝 1 条 + 接受 15 条 → 下载 `selected_final` 136235 字节、**残留修订 0**、**控制台错误 0**。
  - 全量回归 `611 passed / 6 skipped`（排除既有基线失败的 `test_rules_catalogue.py`）。
  - 提交 `64b0302`，已 `bash tools/deploy/publish_workspace.sh` 发布（api/worker active）。
- 后续：如后续仍出现页面未更新，先按「响应头 + URL 版本号 + 实取字节 sha」三步核对，再排查客户端。
- 变更记录：2026-10-16 新增。

## FL-D093 前端用遗留 ruleset 发布标志判断全局可用性，致 healthy 的 recall-first 交付显示「不可认定」

- 发现日期：2026-10-16
- 问题与影响：结果页「可直接使用」恒显示「不可认定」，用户据此怀疑功能未生效。根因：前端 `renderReport` 的 `usable` 四条件之一为 `state.cap.auto_write_enabled`，该字段来自**遗留 ruleset v1/v2 的 `release_policy`**（当前 `unreleased`），与用户实际使用的 recall-first（指引快照）路径**毫无关系**。同时 `downloadSection` 用 `!(kind==='final' && !usable)` 过滤，连「最终版 DOCX」按钮一并隐藏，用户误以为两处独立故障。
- 证据：
  - `frontend/app.js:289` `usable = auto_write_enabled && eligibility==='eligible' && (delivery∈complete[+exceptions]) && doc.downloads.final`；`:302` 的 final 过滤。
  - 生产 `/api/capabilities`：`auto_write_enabled=False`、`auto_write_count=0`、`ruleset_version='v1'`、`revision_ruleset_version='v2'`、`revision_mode='evaluation'`。
  - 生产任务分布：`engine_id='recall_first'` 212 个 vs `engine_id=''` 1 个；UI 永远传 `engine_id='recall_first'`（`app.js:137`），capabilities 的 `engine_id` 写死（`api.py:572`）。
- 处理方法：A/B 运行时下线（见 `docs/LEGACY_RULESET_RETIREMENT.md`）。发布门随 B 下线；「可直接使用」改按任务实际引擎路径判断，`usable` 去除所有 ruleset 字段。
- 状态与验证：**已实施并已验证**（2026-10-16）。生产 `GET /api/capabilities` 只返回 engine 契约；完整交付任务下真实浏览器「可直接使用」=「已通过交付校验」，最终版 DOCX 按钮可见，0 console error。前端 `usable` 已完全去除 ruleset 字段。
- 下一步：无（已完成）。
- 变更记录：2026-10-16 新增；同日方案确认并实施，生产端到端验证通过。

## FL-D094 A 规则集空壳载体拖垮 recall-first 建任务（无功能作用却可致 503）

- 发现日期：2026-10-16
- 问题与影响：建立 recall-first 任务时，`api.py:767` 执行 `carrier = load_ruleset("v1")`，仅为满足 `tasks.ruleset_version NOT NULL` 而加载遗留 A 规则集。该字段对 recall-first **没有任何业务作用**（真正生效的是 `guide_version_id` + `guide_rules_sha256`），但**若 A 加载失败（文件损坏、校验不通过、路径缺失），建任务直接 503，连带拖垮健康的 recall-first 路径**。生产 212 个 recall-first 任务全部携带这一无用的 `ruleset_version='v1'` 空壳值。
- 证据：`api.py:764-773`；`tasks.py:25`（`ruleset_version TEXT NOT NULL`）、`:57-79`；生产任务分布实测（`ruleset_version`：`v1` 212 / `v2` 1）。
- 处理方法：从建任务路径移除 A carrier 依赖；recall-first 任务写入空 `ruleset_version`/`ruleset_sha256`；保留列以兼容历史行。`tasks.create` 改为接受指引版本或 carrier（`_source_field` 兼容两者），运行时不再加载任何遗留规则集。
- 状态与验证：**已实施并已验证**（2026-10-16）。新增回归：monkeypatch 令 `load_ruleset`/`load_ruleset_v2` 抛错，recall-first 建任务仍返回 201；生产新任务实测 `ruleset_version=''`、`ruleset_sha256=''`。
- 下一步：无（已完成）。
- 变更记录：2026-10-16 新增；同日实施并通过回归与生产验证。

## FL-D095 遗留引擎任务行未标记 legacy，只读标注失效且仍暴露可操作入口

- 发现日期：2026-10-16
- 问题与影响：生产存在由已下线规则集引擎写入的**一等任务行**（`tasks.engine_id=''`、`ruleset_version='v2'`，如 `efce8a8eacf7491a844d838970c2158f`）。前端按 `state.task.legacy` 决定是否显示「遗留任务 · 只读」横幅，但 `legacy` 仅在 `task_id` 形如 `legacy-<batch_id>` 的合成镜像任务上为 `true`；这类真实任务行恒为 `false`。后果：列表芯片已显示「遗留任务 · 规则 v2」，详情页却不给只读提示；且 `recover-btn` 等入口仍按普通任务渲染（仅靠服务端 409 拦截），用户看到可点但会被拒。
- 证据：
  - `fundlex/tasks.py` `_summary(..., legacy=False)` 原实现只在 `_legacy()` 调用时传 `legacy=True`；`_snapshot()`（正常任务行）恒用默认值。
  - 生产实测：`GET /api/tasks/efce8a8eacf7491a844d838970c2158f` → `legacy: false`、`engine_id: ''`、`ruleset_version: 'v2'`；真实浏览器任务芯片显示「遗留任务 · 规则 v2」而详情无只读标注。
- 处理方法：`legacy` 改按引擎判定——`engine_id` 不等于当前引擎（`recall_first`）即为历史任务，与合成镜像任务的 `legacy=True` 取或。`RECALL_ENGINE_ID` 从 `fundlex/recall.py` 的 `ENGINE_ID` 复用，避免 `tasks.py` 反向导入 `api.py` 形成循环。
- 状态与验证：**已实施并已验证**（2026-10-16，提交 `012ba18`）。新增回归 `test_retired_engine_task_row_is_flagged_legacy`（植入带文档的遗留引擎任务行，断言 `legacy is True`）；`test_identity_isolation_capabilities_and_historical_mapping` 补充断言。真实浏览器（本地隔离实例，不污染生产）确认：`legacy: True`、详情页出现「遗留任务 · 只读」与「不能补传」、芯片「遗留任务 · 规则 v2」、0 console error。生产同型号任务（0 文档）芯片已正确显示遗留标注。
- 下一步：无（已完成）。
- 变更记录：2026-10-16 新增；同日实施并通过回归与真实浏览器验证。

## FL-D096 批次运行中重新发布导致引擎版本不匹配，整批作废（原编号 FL-D095，与他人条目冲突后改号）

- 发现日期：2026-10-16（P6 开发集 `round7` 首批）。
- 问题与影响：P6 批次运行期间执行 `publish_workspace.sh` 会更新 `engine_build()`。已在队列中的任务在**建任务时**已 pin 了旧 `engine_build`/`schema_version`，worker 取出时校验不符，直接 `ENGINE_SCHEMA_MISMATCH` 判 `job_status=failed` / `delivery_status=not_generated`（本批 D08 命中，D09 亦中断）。该批数据不可用于评分。
- 证据：`var/recall-first-evaluation/p6-dev-round7-01-invalid-publish-midrun/D08/result.json` → `error_code=ENGINE_SCHEMA_MISMATCH`；`fundlex/jobs.py:166` 的校验；`/tmp/opencode/p6-round7.log`。
- 处理方法（运维规程，已执行）：**批次运行期间禁止发布**。已将该批目录改名为 `…-invalid-publish-midrun` 留证，清空 trace 文件后以同一 run-id 重跑。
- 状态与验证：**已确认、已规避**（重跑进行中）。属 FL-D066「不要在飞批次期间干预」的同类，但触发原因是**发布**而非中断；补记于此以免重犯。
- **复发（2026-10-16，`p6-dev-round8-01`）**：本轮在飞期间**并行 agent 两次发布**（worker journal `13:37:57`、`14:47:48`），导致整批出现**三个不同 `engine_build`**（`2415dbab` → `45727220` → `5afe70c3`）。`D02`（pin `2415dbab`）与 `D17`（pin `45727220`）在 worker 取出时 `ENGINE_SCHEMA_MISMATCH`，`job_status=failed` / `delivery_status=not_generated`、**零模型调用**（trace 仅有 trace-open）。其余 18 例虽完成，但分属不同引擎修订，**整批不可用于评分**。已处置：目录改名 `p6-dev-round8-01-invalid-publish-midrun` 留证。
  - **加强措施（已实施）**：`tools/evaluation/p6_run.py` 现在在任一案例出现 `error_code == ENGINE_SCHEMA_MISMATCH` 时**立即中止批次**并打印 `BATCH_ABORTED`，避免继续在混合修订下跑完并误当合格数据；`batch.json` 记录 `aborted`/`aborted_at`。
  - **根因说明**：发布权在本机是共享的（并行 agent 亦会 `publish_workspace.sh`），单方「批次期间不发布」的约定不足以防止污染。故改为**按批自检并快速失败**。
- 变更记录：2026-10-16 新增；同日补记 round8 复发与中止加强。
- 变更记录：2026-10-16 新增；同日因编号与 FL-D095（遗留任务 legacy 标记）重号改为 FL-D096。

## FL-D097 评分器把多句引文的末句误当被删条款，已完成的删除被判 kept

- 发现日期：2026-10-16（P6 开发集 round7 重评，逐 delete 目标核对时发现）。
- 问题与影响：`p6_score._superseded_survives()` 用引文（`requirement` 中「」引号内文本）的三个特征片段 `[8:40]`、中段、`[-24:]` 判断「被删条款是否仍在终稿」。当引文**跨多句**时（D01/G17 引文为两句：「…服务费等。C类基金份额的销售服务费使用范围不包括…」），末句属于**相邻的另一条款**，引擎**有意保留**（终稿 p785 单独成段），却因 `[-24:]` 命中它而把**已完成的删除**判为 `kept`。
- 证据：`var/recall-first-evaluation/p6-dev-round7-01/D01/working_final` 中 D01/G17 的 `old_text`（`销售服务费主要用于支付销售机构佣金`）**已不存在**；终稿仅存相邻句 `销售服务费使用范围不包括基金募集期间的上述费用。`。修复前该目标判 `kept`。
- 处理方法（已实施）：仅当 `old_text` 锚点落在引文**最后一句**内时，才把 `[-24:]` 计入特征片段；引文跨句时锚点所在句即删除目标，后续句可能是被有意保留的相邻条款。中段片段判定保持不变，避免影响 D15 等「锚点是短片段、在别处出现」的正确 `kept` 语义（FL-D074）。
- 状态与验证：**已实施并验证**。开发集 **0.8602 → 0.8644**（236 目标 / completed 203→204，`kept` 32→31）。回归：`tests/test_p6_score_append.py` 11 项（新增「多句引文不要求末句」「单句引文仍能识别残留」两项）；全量 607 passed。反例核对：D17/G17 的 `old_text` **确实仍在终稿**，仍判 `kept`，未被误放。
- 变更记录：2026-10-16 新增。

## FL-D098 删除成功后原段落在终稿消失，评分器因找不到段落把已完成的删除判 kept

- 发现日期：2026-10-16（P6 开发集 round7 重评，按 `final_paragraph` 分布定位）。
- 问题与影响：`p6_score.score_target()` 的 `delete` 分支要求「能在终稿按内容定位到原段落」（`final_index >= 0`）**并且**该段落内不再含被删条款，两者同时成立才判 `completed`。但**删除正是让该段落消失的原因**：引擎删掉条款后原段落文本改变、内容匹配失败，`locate_paragraph()` 返回 `-1`，于是**已正确完成的删除被判 `kept`**（detail「deleted clause still in its region」）。开发集 round7 中 G17 一族 10 例 `kept` 有 5 例（D01/D03/D05/D11/D16）的真实原因是 `final_index = -1`，`old_text` 早已不在终稿。
- 证据：`/tmp/opencode/p6-round7-rescore3.json` 中这 5 例 `final_paragraph = -1` 且 `old_text` 全文不存在；D04/D08/D17/D19/D20 的 `final_index >= 0`（另因条款确实残留，属真实 `kept`，其中 D17/G17 核对终稿 p815 仍含原文，属引擎应改未改）。
- 处理方法（已实施）：`delete` 分支改为——`final_index < 0` 时判 `completed`（detail `deleted clause gone with its paragraph`）；`final_index >= 0` 且 `_superseded_survives()` 为假亦判 `completed`；仅当段落仍在且条款特征片段仍命中才判 `kept`。删除的判据是「条款在**全文**已不存在」，锚点消失即达标。
- 状态与验证：**已实施并验证**。开发集 **0.8644 → 0.9110**（236 目标 / completed 204→215，`kept` 31→20，`not_executed` 仍 1 例 D07/G16）。回归：`tests/test_p6_score_append.py` 12 项（新增「段落消失的删除判完成」并含「条款仍存则判 kept」反例）；全量 607 passed。反例核对：D17/G17 条款仍在终稿、仍判 `kept`，未被误放。
- 变更记录：2026-10-16 新增。

## FL-D099 replace 因一处措辞差异（多一个「基金」）被判未执行，引擎已正确替换却计 kept

- 发现日期：2026-10-16（P6 开发集 round7 重评，逐 `kept` 目标核对时发现）。
- 问题与影响：`p6_score.score_target()` 的 `replace` 分支用 `replacement[:24] in region` 判「新义务是否已出现」，`needle not in region` 判「旧措辞是否已消失」。G14 的政策句为「基金管理人可以适当调低基金申购费率和销售服务费率。」，实际合同交付为「…调低基金申购费率和**基金**销售服务费率。」——多一个「基金」，24 字前缀即分叉；同时标签的 `old_text`（`可以适当调低基金申购费率`）是**修正后句子的一部分**，于是「旧措辞仍在」成立，**引擎已正确替换却被判 `kept`**（D10/D14/D15）。
- 证据：`var/recall-first-evaluation/p6-dev-round7-01/{D10,D14,D15}/working_final` 对应段落实测为「…可以适当调低基金申购费率和基金销售服务费率。」，义务「调低销售服务费率」已落地；D11/G08 与 D11/G11 同因合同真实类别措辞（`A类、D类基金份额`）与模板（`A类基金份额`）不同而被前缀判定漏接，实际义务**已完整出现**于 p233/p234。
- 处理方法（已实施）：`replace` 分支新增 `_obligation_in_region()` 回退——先做规范化精确匹配，再做 `difflib.SequenceMatcher` 滑窗比对（窗口＝义务长度，逐字符步进，阈值 0.9），容忍少量插入/措辞噪声。仅作精确与前缀判定之后的**第三顺位**回退，阈值取高值以免放过真未执行的替换。
- 状态与验证：**已实施并验证**。开发集 **0.9110 → 0.9322**（236 目标 / completed 215→220，`kept` 20→15）。逐目标变更核对（对比复评 `p6-round7-rescore4.json` 基线）**仅 5 处** `kept→completed`，全部为上述已核实的正确替换，**无其他任何变化、无误放**。
  - 反例核对：**D12/G14 仍判 `kept`**——该段落原文「…调低基金申购费率、基金赎回费率、转换费率和销售服务费率。」**完全保留**，滑窗最佳比仅 0.76（低于 0.9 阈值）；引擎自身审计也一致（`status=unresolved`、`RECALL_EDIT_OVERLAP`、sweep `SW001 status=pending`、`edit_plan` 无 G14 条目），确认**属引擎真未执行**，评分器未误放。
- 变更记录：2026-10-16 新增。

## FL-D100 剩余 kept（G17 删除 / G18 替换）属引擎缺陷，且 P6 优化轮次已超协议上限、预算接近总额

- 发现日期：2026-10-16（P6 开发集 round7 评分收敛到 0.9322 后，逐 `kept` 目标定位根因）。
- 问题与影响（两件事，分列）：
  - **① 剩余 15 个 `kept` 全部是真实引擎缺陷，不再是评分器问题**。评分器三处误判（FL-D097/098/099）修完后，残余家族经逐例核对与**引擎自身审计**互为佐证：
    - **G17 删除 ×5**（D04/D08/D17/D19/D20）：引擎 ledger 记 `not_applicable`，理由为「本窗口未出现…条款」，但该条款**确实存在**（终稿 p977/825/815/806/830）。根因：指引 `old_text` 是**两句**且带 `C类基金份额的` 前缀（`…基金份额持有人服务费等。C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。`），实测合同为**无前缀**的单句（`销售服务费主要用于…`），第二句措辞亦不同（`销售服务费的使用范围不包括…` / `销售服务费不包括…`），**D04/D17 根本没有第二句**，D19 为 `持有人服务费`。逐句比对：指引两句在终稿均 **MISSING**，故模型盘点判 `absent`，管线沿用为 `not_applicable`。D17/D19 另有 survey 来源目标（`Y008`/`Y003`，`planned/replace`，审计判 completed），但条款仍存活于终稿。
    - **G18 替换 ×3**（D01/D11/D19）：ledger 为 `planned/replace`，**审计自称 completed**（`A类、D类基金份额和C类基金份额费用收取不同`），但该修正句出现在**别处**，原句在终稿 p1216/1232/1212 **原样保留**——属「替换未落地」。
  - **② 轮次与预算已越界**。`var/recall-first-evaluation/p6/protocol.json` 的 `ledger_policy` 明文「Optimisation rounds capped at 3」，`budget` 为 dev ≤2000 calls/≤$6、holdout ≤900/≤$3、**total ≤$10**。实际已执行 **baseline + 7 轮**（round1/round7 各含 1 个作废目录）；应用账本 `requests` 表累计 **charged $9.0593 / 10856 calls**（含 2026-10-14 起全部应用流量，非纯 P6）。**协议把 per-run 花费指向 `report.json` 的 model 段，但各 `p6-dev-*` 目录下并无 `report.json`，per-run 花费目前不可核验**。
- 证据：`var/recall-first-evaluation/p6-dev-round7-01/{D04,D08,D17,D19,D20}/report.json` 的 ledger/targets/audit；终稿 `final`/`working_final` 原始段落；`/tmp/opencode/dbg_g17_clause.py`、`dbg_g17g18.py`、`dbg_d12g14.py` 输出；`sudo -n sqlite3 /var/lib/fundlex/model_budget.sqlite` 汇总。
- 处理方法：
  - ① 待定：可行的方向是照 `append_applicability_targets`（FL-D060/090）的成例，为**删除类规则**增加「确定性适用性兜底」——用 `old_text` 的**特征核心**（如 `销售服务费主要用于支付销售机构佣金`）在文档中定位，命中即覆盖模型的 `absent`/`not_applicable`，并把锚点收敛到该条款所在句。**需评估误删风险**（该句在正文与摘要各出现一次）。G18 属「替换未落地」，需查 `_splice_fragment`/审计后回写链路，与删除兜底非同源。**尚未动手，未改任何引擎代码**。
  - ② 已处置：**停止继续开新批次**，把轮次/预算越界上报产品负责人决定是否继续（协议要求「dev 达标即冻结版本、随后只读留出」）。
- 状态与验证：①**已定位、未修复**（建议阶段）；②**已确认**（有账本与目录证据）。当前开发集 **0.9322**（236 目标 / completed 220 / `kept` 15 / `not_executed` 1），**未达 0.95**，故仍处「不得冻结、不得读留出」状态。
- 下一步：待产品负责人就轮次/预算给出意见后，再决定是否实施删除类确定性兜底并复测。
- 变更记录：2026-10-16 新增。

## FL-D101 模型盘点判「absent」的删除规则被 survey 跳过，删除义务静默丢弃（FL-D091 的删除类同源）

- 发现日期：2026-10-16（P6 开发集 round7 评分后按 `kept` 家族定位，D04/D08/D17/D19/D20 全中）。
- 问题与影响：G17 的指引 `old_text` 是**两句、带 `C类基金份额的` 前缀**（`C类基金份额的销售服务费主要用于…等。C类基金份额的销售服务费使用范围不包括…。`），实测合同为**无前缀**的单句、第二句措辞各异（`销售服务费的使用范围不包括…` / `销售服务费不包括…`），**D04/D17 无第二句**，D19 为 `持有人服务费`。因此模型盘点判 `absent`，其目标**恰好落在该条款所在段落**；`survey_targets()` 的 `existing` 集合含该 `(rule_id, location)`，把本应命中的 hit **静默跳过**，删除义务整条丢失。这与 FL-D091（append 被 `absent` 目标压制）是同一根因的不同规则类型。
  - 复现（离线重放）：G17 的 `operation_search_keys` 已包含有效定位键 `销售服务费主要用于支付销售机构佣金`（`_strip_class_lead` 剥离类前缀的产物），且该键在 D08 `p800` **命中**；但 `override_rules` 缺省时五例 G17 hits 均为 **0**。
- 证据：`/tmp/opencode/dbg_keys.py`、`/tmp/opencode/dbg_g17_pass.py` 输出——加 `override_rules={'G17'}` 后 D04 0→2、D08 0→1、D17 0→2、D19 0→2、D20 0→1 个 hit，全部 `operation=survey`、`ratio=1.000`（真实文档偏移，非臆造）。
- 处理方法（已实施）：
  1. `recall.survey_targets(..., override_rules=…)`——命中规则进入该集合时，`known` 中的既有目标不再压制 hit（与 FL-D091 的 `_survey_targets_from_hits(override_rules=…)` 同构）。
  2. 新增 `recall.is_delete_only_rule(rule, facts)`——判定「所有适用操作均为 delete」（`noop` 不计）。
  3. `recall_pipeline._run_survey()` 计算 `override_rules = 纯删除规则 － 已有 resolved needs_edit 目标的规则`，同时传入 `survey_targets` 与 `_survey_targets_from_hits`。**只覆盖模型判错（无 resolved needs_edit）的删除规则**，正在被正常编辑的规则不受影响。
- 状态与验证：**已实施、已发布**，真实批次 `p6-dev-round8-01` 复测进行中。离线重放证明五例目标恢复；单测 `tests/test_delete_applicability.py` 3 项（纯删除判定、absent 不压制、已 resolved 不被重复触发）；全量 613 passed / 6 skipped。
- 下一步：待 round8 评分确认 G17 五例由 `kept` 转 `completed`，再攻 G18「替换未落地」。
- 变更记录：2026-10-16 新增。

## FL-D102 交付包/工作台 ZIP 结构改造：结果总览 + 逐处改前改后对照（用户要求）

- 发现日期：2026-10-16（产品负责人给出目标结构：参考 `var/recall-first-evaluation/FundLex-合同修改结果-本次抽查-20261013/`）。
- 问题与影响：原「任务汇总.md」只列状态（上传/处理/资格/交付/原因码），看不出**每份合同改了几处、改了什么**；离线交付包与工作台「下载全部结果 ZIP」结构不一致，且最终版 word 与逐份说明混排，业务读者难以直接取用改后合同。
- 用户明确要求（四条）：
  1. 「任务汇总」改为「结果总览」，逐份写明**改了几处**；
  2. 保留「结果清单.csv」；
  3. **所有接受修订的最终版 word 单独放一个文件夹**；
  4. `修改说明.md` 详细写**对应的合同改了哪些地方、改之前改之后分别是什么**。
- 处理方法（已实施）：
  1. 新增 `fundlex/edit_summary.py`——编辑摘要的**唯一真源**：读取报告 `plan.edits`、指引规则标题/要求、审计 verdict，输出修改处数、涉及条款短标签、处理结果文案、`(改之前, 改之后)` 与 ZIP 归档路径（`archive_entry`）。工作台与离线工具共用，避免两处口径漂移。
  2. `fundlex/tasks.py` `TaskStore.report()`：标题改「# FundLex 合同修改结果总览」，新增「## 每份合同的修改情况」表（合同文件 / 交付完整性 / 修改处数 / 涉及条款），保留原状态表作为二级明细。
  3. `fundlex/api.py` `task_archive()`：ZIP 改为 `结果总览.md` + `结果清单.csv` + `最终版（接受修订后）/<合同>.docx` + `逐份修改说明/<合同>/`（含 `（修改痕迹版）.docx`、报告）。`final`/`working_final` 只进最终版文件夹，`redline` 与报告只进逐份文件夹；并对同名合同做去重（`name (2)`），修复同 stem 合同导致的 ZIP 重名（原先会产生重复条目）。
  4. `tools/evaluation/p6_package.py`：改用共享模块；`修改说明.md` 新增「逐处修改对照」表（序号/修改内容/位置/操作/修改前/修改后/校验）与「逐处修改详情」（含指引要求、逐处改前改后引用块）；「操作」列把「替换但 replacement 为空」正确标为**删除**；`修改前` 取自 `components[*].expected_old_text`（此前该字段未读取，导致改前栏为空）。
  5. 前端：按钮「↓ 下载任务汇总 .md」→「↓ 下载结果总览 .md」，下载文件名同步为 `<任务名>_结果总览.md`。
- 状态与验证：**已实施、已发布、已线上端到端验证**。
  - 生成器实跑 `p6-dev-round1-01`（20 例）产出目标结构；抽查「广发上海清算所…_20250319」修改说明含 17 处对照，改前/改后为真实原文（如赎回费归属、赎回金额表述、删除 7 日旧句），删除类显示「（删除该句）」。
  - 新增/调整单测：`tests/test_tasks_api.py::test_task_archive_groups_final_and_notes_by_folder`（ZIP 归档路径与重名去重）、`test_task_archive_authorization_names_and_integrity`（断言 `结果总览.md` 与「每份合同的修改情况」）、`tests/test_p6_package.py`（断言「逐处修改对照」「逐处修改详情」「修改前/后」）。
  - 全量测试 **630 passed / 6 skipped**，仅余已知基线失败 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（服务器缺 `references/`，与本次无关）。
  - **线上真实路径验证**（提交 `e235730` 发布后，走 `https`/本机 `127.0.0.1:8010` 密码登录 → `POST /api/tasks` → 上传 → seal → 真实 Worker+真实模型处理 → `GET /api/tasks/{id}/download/all`）：2 份真实合同任务 `completed`，交付统计 `{incomplete: 1, complete: 1}`；ZIP 641706 字节，**重复条目 0**，结构为 `结果总览.md` + `结果清单.csv` + `最终版（接受修订后）/<2 份合同>.docx` + `逐份修改说明/<合同>/{修改痕迹版.docx, report_md.md, report_json.json}`，与参考包一致；`结果总览.md` 逐份写明修改处数（17 / 18）与涉及条款。解压后最终版 DOCX 可正常打开（1338 / 1385 段），修订痕迹版含 `w:ins` 17/18 与对应 `w:del`，与总览所报处数一致。
- 待办：`修改说明.md` 仍按用户选择保持**节选截断**（160/200 字），完整上下文引导读者看「（修改痕迹版）」；离线 `FundLex-合同修改结果-P6开发集-20261015` 旧包如需同步新结构，可用新生成器重跑。
- 变更记录：2026-10-16 新增（用户四条要求 → 生成器 + 工作台两处实现）；同日完成发布与线上端到端验证。

## FL-D103 用户选择过修订的合同，交付包仍给引擎全量版本（方案A：改为交付所选版本）

- 发现日期：2026-10-16（产品负责人问「选择过修订的合同，<合同名>（修改痕迹版）.docx 是原版还是按用户想法的版本」后核实）。
- 问题与影响：工作台逐条接受/拒绝修订后，产物落成独立 artifact `selected_final`（`api.py:_apply_selection`），与引擎的 `redline` 互不覆盖。但 ZIP 打包只按 `final/working_final`、`redline/working_redline` 分派，**`selected_final` 不进「最终版（接受修订后）」**，所以只要用户选择过，交付包给的仍是引擎「全量接受修订」版本，与文件夹名含义不符，也与用户的意图不符。
- 用户决定：采用**方案A** —— ZIP 里最终版用 `selected_final`，并据此生成一致的痕迹版；未接受的修订不再出现在交付文件中。
- 处理过程与额外发现的真实缺陷：
  1. **配对被拆开的缺陷（已存在，非本次引入）**：`selective.apply_decisions()` 用 `_normalise_decisions()` 只看调用方传来的 id；前端只按 `del_id` 下发决策（`RevisionDecision` 仅含 `del_id`，`frontend/app.js` 亦然），于是配对的 `ins_id` 走默认 `ACCEPT` 被内联，**拒绝一条替换后原文与新文会同时留在文档里**（实测 p1191：拒绝 del_id=1 后旧句与新句并存）。只有同时下发 `del_id` 与 `ins_id` 才会正确拒绝。
     - 修复：新增 `selective._explicit_verdicts()`，把判定展开到整对修订（同一对的任一 id 被提及即整对生效），`apply_decisions` 与新的痕迹版生成共用。
  2. **新增 `selective.generate_selected_redline()`**：把源痕迹版重写为与选择一致的版本。**该函数的语义在首次实现后被产品负责人复核纠正过一次，见下方「语义纠正」。**
  3. `fundlex/store.py`：`SELECTED_KINDS` 增加 `selected_redline`；新增 `remove_selected_artifact()`（新痕迹版派生失败时删除过期的旧 `selected_redline`，避免与最新选择不一致而被误当可信产物；`selected_final` 不允许被该方法删除）。
  4. `fundlex/api.py`：决策后同时发布 `selected_redline`；下载白名单加入 `selected_redline`。派生失败只影响该痕迹版，不回滚已发布的 `selected_final`。
  5. `fundlex/edit_summary.py`：新增 `archive_kinds()` 与 `ARCHIVE_PREFERENCE` —— 最终版槽位取最优候选（`selected_final` > `final` > `working_final`）；修订痕迹槽位**保留引擎全量痕迹**（`redline` > `working_redline`），另设 `selected_redline` 槽位（见「语义纠正」）。报告类无竞争项照旧；`archive_entry()` 用 `（全量痕迹版）`/`（选择修订版）` 两个名字分别归档两份痕迹文件。
  6. `fundlex/tasks.py`：「结果总览」的「每份合同的修改情况」新增**版本**列（有 `selected_redline` 记「按人工选择」，否则「引擎全量」），并加说明文字解释两种值。
  7. `tools/evaluation/p6_package.py`：离线包同样优先取 `selected_final`，并同时归档 `（全量痕迹版）` 与 `（选择修订版）`。
- 语义纠正（2026-10-16，产品负责人复核后）：首次实现把**拒绝**的修订保留为痕迹，理由是「仍可复查」。
  这是错的，与最终版自相矛盾：最终版里该处是原文（拒绝已生效），痕迹版却标着「这里要改成新文」；
  而且「接受全部修订」会把用户已否决的改动再加回去，无法还原出最终版。
  - **正确语义**（已按此重写 `generate_selected_redline()` / `_keep_accepted_only()`）：痕迹版只保留**接受的**
    修订为痕迹；**拒绝的修订回到原文、不再留痕迹**。于是「接受痕迹版中的全部修订」即得到最终版，两份文件自洽。
  - **未表态的修订**：按**接受**处理（与 `apply_decisions()` 的默认一致）。前端下发的决策覆盖每条修订，
    正常不会出现未表态；用同一默认值可保证 `selected_redline` 与 `selected_final` 口径一致。
  - **产品负责人决定分两份痕迹文件**（避免丢失「引擎本来想改什么」的审计信息）：
    - `<合同名>（全量痕迹版）.docx` —— 引擎原始全量痕迹，不受选择影响；
    - `<合同名>（选择修订版）.docx` —— 审查后只含接受修订的痕迹；接受其全部修订即得到最终版。
    - **只在用户确实把某些修订从接受改成不接受时才生成第二份**；全部保持默认接受的合同与引擎结果一致，
      只发「（全量痕迹版）」以免重复。判定见 `api.py:_selection_overrides_default()`。
  - 相应改动：`archive_entry()` 采用两个名字（`（全量痕迹版）`/`（选择修订版）`）；`ARCHIVE_PREFERENCE` 让
    全量痕迹与选择痕迹各占一个槽位而不再互相覆盖；`tasks.report()` 的版本列改按 `selected_redline` 判定；
    前端下载按钮与文件名区分两份；`p6_package.py` 同步输出两份。
- 状态与验证：**已实施、已发布、已线上端到端验证通过**（第一次验证后按「语义纠正」重做，以下为纠正后的结果）。
  - 单测（纠正后）：`tests/test_selective.py` 19 项（含「拒绝的修订回到原文且不再留痕迹」「未表态的修订仍保留为痕迹」「选择修订版只留接受项且接受全部即得最终版」「须有 manifest」「不得覆盖源痕迹版」）；`tests/test_revision_api.py`（含「拒绝过则 `selected_redline` 与 `selected_final` 及引擎痕迹三者内容互不相同」「全部接受则不产生第二份痕迹文件」「accept-all 不发额外痕迹版」）；`tests/test_tasks_api.py`（含两份痕迹版命名、ZIP 槽位规则、总览版本列）。全量 **641 passed / 6 skipped**，仅余已知基线失败 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（服务器缺 `references/`，与本条无关）。
  - 离线复现配对缺陷：仅下发 `del_id=1: reject` 时，修复前 p1191 修订 id 为 `[]` 但旧句与新句并存；修复后旧句恢复、新句消失。
  - **线上真实路径验证**（发布后，密码登录 → 真实合同上传 → 真实模型处理 → 工作台取修订 → 按前端形式（仅 `del_id`）逐条决策 → 下载全部结果 ZIP）。两个场景各跑一个真实任务（任务 776b606…/e74ed69…）：
    - **拒绝 2 条（共 19 条）**：ZIP 的「逐份修改说明/<合同>/」同时出现 `（全量痕迹版）.docx`（19 条 `w:ins` + 19 条 `w:del`）与 `（选择修订版）.docx`（17 + 17）；「最终版（接受修订后）」为 `selected_final`；`结果总览.md` 版本列为「按人工选择」，处数 19。
    - **全部接受（共 18 条）**：ZIP 只出现 `（全量痕迹版）.docx`，**没有**第二份痕迹文件；「最终版」为引擎 `final`；总览版本列为「引擎全量」，处数 18。
  - 产物自洽核对（解压后实际读 XML，按 Word 语义模拟「接受全部修订」后逐段比对文本）：
    - **「选择修订版」接受全部修订后的文本与「最终版」完全一致（0 段差异）** —— 两份文件自洽；
    - 「全量痕迹版」接受全部修订后与「最终版」**有 2 段差异**，正是被拒绝的那 2 条修订 —— 符合「全量痕迹回答引擎本来想改什么，不代表最终交付」。
  - 三份 DOCX（最终版、全量痕迹版、选择修订版）均可正常打开（各 1385 段）。
- 下一步：无（用户决定的口径已全部实现并验证）。若后续希望把选择也计入引擎交付校验或让 `selected_final` 反哺评测口径，需另行确认，因为 `selected_final` 目前是**用户产物**，不参与引擎交付验证（`store.py:SELECTED_KINDS`）。另：旧交付包 `var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/` 仍是改动前的布局与旧文件名，尚未重新生成（尚未获得用户指示）。
- 变更记录：2026-10-16 新增（用户问询 → 核实 → 用户选方案A → 实施 → 线上验证通过）；同日产品负责人复核痕迹版语义后**纠正**（拒绝的应回原文而非留痕迹）、并决定分「（全量痕迹版）」与「（选择修订版）」两份、只在确有拒绝时发第二份 → 已重做并重新线上验证通过。

## FL-D104 全量合同 B 类（业务含义偏差）排查方法、发现与待裁决口径

- 发现日期：2026-10-17。
- 目标与范围：按产品负责人要求，找出合同与指引「同一件事但业务含义有出入」（B 类）的全部情形；范围为 `/home/opencode/data/funds_word` 下全部 **514** 份合同 DOCX。
- 方法（重要，供接续复用）：
  1. **取料（确定性，不耗模型）**：逐份解析段落，按规则家族抓「同主题」段落，落地为结构化 material JSON；**G02/G04 因类别字母为占位符、纯误报**，经确认后从模型判定中排除。
  2. **模型判定**：`deepseek-v4.1-flash`，**只问一个问题** —— 「这段文字的业务含义与指引条款是否不同？」；**不给预设分类、不给类别模板**，输出 `YES/NO/UNSURE` + 自由文本 `difference` + 引文 `quote`。
  3. **分拣**：剔除「段落逐字含规则 `old_text`」「段落是指引条款自身变体」「段落已含 `new_text`」等确定性误报；对**删除型规则（G15/G17）**额外剔除 `PURE_PRESENCE`（仅因「条款仍在」被判不同）。
- 结果数字：原始 YES **3459**；剔除删除型纯存在误判 **544**（G15 521 / G17 23）；判 `UNSURE` **61**；存活 **2915**；按 (合同, 规则) 去重后 **1638 行 / 覆盖 509 份合同**。分规则：G08 **404**、G11 **498**、G14 **306**、G15 **94**、G16 **319**、G17 **17**。
- 自然聚出的出入形态（由模型自由文本聚类得到，**非预设分类法**）：
  - G08 六族：缺 A/C 与渠道区分 377 / 多出 D·E·F·Y 类 43 / 范围大于指引 17 / 只写承担主体 4 / 其他 3 / 主题错位 2。
  - G11 六族：认购申购环节错位 455 / 只写承担主体 222 / 缺 A/C 与渠道区分 163 / 多出类别 30 / 范围更大 2 / 其他 1。
  - G14 四族：含赎回+转换+销售服务费 147 / 多调低赎回 100 / 多调低销售服务费 51 / 笼统「销售费率」8。
  - G16 三族：缺直销·其他机构区分与超一年返还 203 / 「每日计提」表述不同 127 / 缺直销返还 9。
  - G15 一族：支付时限/主体/路径不同 94。G17 一族：范围更大或少了募集期间费用排除 17。
- **提示词污染陷阱（已识别并处理）**：对**删除型规则**问模型「业务含义是否有出入」，模型会答「该条款仍在」，这**不是语义差异**。G15/G17 的 `PURE_PRESENCE` 误判（共 544 条）即由此产生，已从结果中剔除。
- 证据与产物（**均在仓库外，不入库**）：报告 `/home/opencode/B_CLASS_REPORT_FINAL.md`；数据 `/tmp/opencode/b_gap_findings_clean.csv`（1638 行）；分规则 CSV `/tmp/opencode/b_class_by_rule/*.csv`；逐条明细 `/tmp/opencode/report_full.txt`。
- 待办（需产品负责人**逐形态裁决**，报告第四节列 19 项），其中影响面最大的四项：
  - (a) 删除型规则下「段落仍在」是否不算 B 类（**已按此口径剔除，待确认**）；
  - (b) G11「认购 vs 申购环节错位」455 份是否算 B 类；
  - (c) G14「给管理人多留调低权限」是否算 B 类；
  - (d) G16 缺返还机制属 B 类偏差还是「指引新增机制」。
  - **裁定前不得据此改动引擎或评分。**
- 状态与验证：**已实施并已验证**（全量 514 份跑完、514/514，无异常错误）；结论**待产品负责人裁决**。方法上有一处经验教训须记：**首次 30 份小样本只暴露了 G14/G15 两类，主 agent 一度以该两类为模板做分类，属先入为主；已按用户要求改为「不预设分类、只找业务含义出入」重做。**
- 重要提醒：本条目只登记「发现与待决」，**不得据此宣称已修复或已达标**；P6 开发集指标与冻结/留出状态不受本条目影响。
- 下一步：等待产品负责人对报告第四节 19 项逐形态裁决；裁决后再决定是否调整引擎或评分口径。
- **产品负责人口径（2026-10-19，针对报告形态 G08-1、G08-2）**：
  - 两类形态均属**正常要替换**的目标：应改；不属于"表述不完整但非偏差"，也不按"规则缺口"另行处置（对报告第四节第 1、2 项的答复）。
  - 替换**不是字面替换**：需要语义理解，**按合同实际定义的份额类别及其收费性质实例化**；指引文本中的 A/C 是**占位举例**（原话："这种情况要基于基金的收费性质来判断，指引的 A/C 两类只是举例而已"），不得按字母照抄。
  - 与 FL-D105 Q2 的原则一致（按"是否收申购费 / 是否计提销售服务费"归类，而非按字母）；Q2 其余部分（迁移范围、货币基金等边界）仍待裁决。
  - **范围限制**：本口径只覆盖 G08-1、G08-2；G11 同族形态（报告第 6/7 项）等仍逐项待裁。
  - 实现状态：**未实施**——本条为已确认设计输入；引擎与评分未改动，不改变 P6 冻结/留出状态。
- 变更记录：
  - 2026-10-17 新增（全量 514 份 B 类排查完成，记录方法与待裁决口径）。
  - 2026-10-19 追加产品负责人对形态 G08-1/G08-2 的口径（正常替换；按收费性质实例化；A/C 为举例）。
  - 2026-10-19 产品负责人八项业务裁定（见 FL-D120 与计划文档 §39）：第 5 项 G11 认购/申购"错位"经全量核查**按材料/定位问题勘误**（不产生修改）；第 9/10 项 G14 与 138/40 类**直接改新表述**；第 12 项 G15 删除照常 + **标记"原合同可能有误"**；第 14 项"每日计算、逐日累计"**等同**"每日计提"；G11 同族形态**扩展确认**（按收费性质）。

## FL-D105 合同语料与《修改指引》结构性适配排查：类别模型 / 空格陷阱 / 删除型 old_text 对不上 / 模棱两可点

- 发现日期：2026-10-17
- 目标与范围：按产品负责人要求，排查 514 份合同（`/home/opencode/data/funds_word`）与指引（`guides/builtin_guide_v1.json`，22 规则组）之间的**不适配、特殊情况与模型易模棱两可处**。**确定性排查，未调用模型。**
- 方法：逐份解析段落，按规则主题锚点抓取同主题段落；关键是对文本做**去空白压缩**（含空格 / 全角空格 / U+200B）后再匹配，统计类别字母、类别集合、old_text / 变体命中、规则交叠与"已满足"情况。产物与脚本见 `/tmp/opencode/`（`guide_fit_probe2.json`、`clause_material.json`、`verify_findings.json`、`collect_clauses.py`、`verify.py` 等）；报告 `/home/opencode/GUIDE_CORPUS_FIT_REPORT.md`。
- 主要发现（**已实施并已验证的机械事实**）：
  1. **空格格式陷阱（H1）**：语料常写 `A 类`（字母与"类"间有空格/全角空格），指引写 `A类`。不做去空白归一化时 **386/514** 份合同被判为"零份额类别"；实际 367/514 存在该空格写法。任何类别识别 / 槽位替换 / old_text 匹配如未先归一化会整体失效。
  2. **真实类别远超 A/C（H2）**：存在 E(29)/F(19)/Y(19)/D(15)/B(9)/H(2) 六种额外类别，且**同字母含义因产品而异**（E 类有的属收费组、有的属服务费组）；B 类是货币基金专用（三类按不同销售服务费年费率，无 C 类、无 A/C 对立）。类别集合：A+C 291、**无任何字母 143**、A+C+E 18、A+C+F 14、A+Y 12、A+C+D 9 等。
  3. **删除型规则 old_text 大面积对不上**（逐字/变体命中的合同数）：G15 仅 **1/514**、G06 **2/514**、G17 **5/514**、G13 **19/514**（G05 514、G22 437 命中良好）。即指引给的是范本措辞，真实合同是同义异构写法；凡以"old_text 是否出现"决定规则适用性，这几条会大面积漏判（与 FL-D101 删除类静默丢弃同源）。
  4. **规则交叠 / 模棱两可点**：G05 与 G14 实测**同段交叠 = 0**（G05 命中 1092 段授权句、G14 命中 409 段促销句），但两者针对的句不同，混淆会误判适用对象；G14 真实原句有 300+ 种，其中**已含"销售服务费"**（138 份）与**带"全部或者部分份额类别"限定**（40 份）两类最易判错；`class_count`（1/multiple）在无字母/多类别产品上语义未定义。
  5. **已满足新机制的产品**：已含"通过直销机构…不收取申购费/认购费" **46/514**、已含"持有超一年返还" **41/514**。append 型（G01/G03/G16）若不识别"已满足"会重复新增。
  6. **货币基金（8 份）** 与 A/C 模型根本不兼容。
- 待产品负责人裁决口径（报告第四节 Q1–Q8）：Q1 old_text 对不上是否判"适用并改"；Q2 E/F/Y/D/B/H 是否纳入、按字母还是按收费属性归类；Q3 货币基金是否在范围内；Q4 已含销售服务费的 G14 原句是否仍需重写；Q5 带"全部或部分份额类别"限定算不算已满足；Q6 append 型"已满足"如何认定；Q7 无字母产品的 class_count 定义；Q8 G05 在已有"销售服务费"字样句上如何处理。**裁定前不得据此改动引擎或评分。**
- 状态与验证：**已实施并已验证**（确定性统计，514 份全覆盖，无异常）；结论待裁决。
- 重要提醒：本条目只登记"适配性发现与待决"，**不得据此宣称已修复、已达标或引擎确有缺陷**；P6 开发集指标与冻结/留出状态不受本条目影响。
- 变更记录：
  - 2026-10-17 新增。
  - 2026-10-17 按用户要求，将本适配性排查**并入 B 类总报告并明确分区**：`/home/opencode/B_CLASS_REPORT_FINAL.md` 现为**两部分**报告——第一部分（第一~五节）为 B 类合同语义偏差（模型判定，口径编号 1–19），第二部分（第六~八节）为本适配性排查（确定性统计，口径编号 **Q1–Q8**，用户要求"注意区分开"）。正文中本条目所述"报告第四节 Q1–Q8"在合并后位于**第二部分第七节**；独立副本 `/home/opencode/GUIDE_CORPUS_FIT_REPORT.md` 保留。两部分口径各自独立裁决，编号不通用。
  - 2026-10-19 产品负责人就 G08-1/G08-2 明确"按合同实际类别的收费性质实例化、A/C 为占位举例"（登记于 FL-D104 同日口径）；Q2 按此原则部分确认，其余细节（迁移范围、边界产品）仍待裁决。
  - 2026-10-19 八项业务裁定（FL-D120/计划文档 §39）：**Q2** 归基准 = "是否收申购费 / 是否计提销售服务费"（扩展 G11 及同类规则）；**Q3** 货币基金不在修改范围；**Q7** 按实际份额类别结构判定；**Q4/Q5** G14 相关原句直接替换为新表述。

## FL-D106 引擎把「规则是否适用」交给代码判断属设计错位：改为模型判、代码只兜硬事实

- **2026-10-28 再审计（未完成事项重开）**：当前归属并非“全部必须逐字old_text”，已有variants、0.35相似度、单适用operation及G02/G04等特例；但真实G17合法目标仍可被后置site词表否决，T3候选/quote检查比前置归属更严（合成G09前置通过，模型返回精确原文仍 `anchor_mismatch:quote_anchor_missing`），重定位复用该门禁不能根治。`compose_variant`仍在独立verify之前要求fixed_text逐字存在；`_verify_composed`会因“投资人→投资者”的保护词表差异在review调用前拒绝。**同日核对到本条2026-10-19已明确允许一个模型生成、另一个模型复核；这不是新的待业务决定，而是旧裁定未完整落地。** 对数字/主体含义应核对真实授权，不能把所有同义词形改动当经济条款改变，也不能因词义相近自动放行。`claimed_operations`是归属失败后转存的字段，不是独立已批准授权，不能简单恢复它就直接写入。状态：离线复现，统一语义绑定/独立效果仲裁尚未实施。证据见本轮审计报告/JSON。

- 发现日期：2026-10-17
- 背景与用户要求：产品负责人指出——**"适不适合"这类判断不应由代码来做，代码判不准**；要求**让模型多承担判断，只有确实更适合代码的才交给代码**；并**把"为什么用模型而不是用代码"的理由登记进本清单**。
- 问题定位（设计错位）：现有链路为「模型读事实 → 代码 `condition_matches()` 依 `class_count`/`has_service_fee` 判规则适不适用 → 代码用 old_text 逐字命中判是否命中」。模型的 INVENTORY 提示**本来就要求它判 `needs_edit`/`satisfied`/`absent` 并明确"措辞可与指引范本不同"**，但代码事后用**同样是语义判断**的确定性测试把模型结论推翻，导致"模型已看到、代码却丢弃"（FL-D091 ③、FL-D101 同源）。
- **为什么这些必须用模型、不能用代码（用户要求登记的核心理由）**：
  1. **判断答案不唯一**：同一份合同不同次跑、不同人判，结论会不同（如"给管理人多留调低赎回费的权限算不算要改"）。代码只能给一个固定答案，必然系统性判错。
  2. **不可逐字核验**：语义判断无法在原文指出唯一证据。"这段是不是在讲指引那件事"没有可核验的字面依据；而同义异构写法（"直销渠道"对"直销机构"、少一个"基金"、`A 类` 对 `A类`）无穷，代码锚点永远穷举不完（对应 FL-D105 的 6.2：G15 仅 1/514、G17 5/514 逐字命中）。
  3. **换种说法结论就变**：只要把"对不上措辞"当成"不适用"，换一种合法写法就会被误判——这正是漏判根因。
  4. **指引本身未定义的维度，代码无从判断**：`class_count` 只给 1/multiple，真实语料有 0 字母、A+C+D+E、货币基金 A/B/E 无 C 类等形态；"多类别"按字母还是按费率组、货币基金是否适用，**指引没定义，代码只能瞎猜**（对应 FL-D105 的 H2/M3/M6）。
- 判定边界（三问标准，**三问全"是"才交给代码**）：①答案唯一；②可逐字核验；③不需要理解。任一为"否"→ 交模型。
- **代码只兜"硬事实"（F1–F7）**：F1 某确切字符串在不在；F2 计数；F3 new_text 是否逐字已存在；F4 删除型相关词共现（`_delete_keyword_bag`）；F5 段落定位；F6 改后是否真的变了；F7 引文能否逐字核验。这些只用于**补充召回**与**硬否决**，不用于**软否决**。
- 处理方法（**已实施**）：
  1. 新增 `fundlex/recall.py::hard_fact_topic_absent(rule, document_compact)`——**唯一允许否决模型判断的硬事实**：合同全文**确无**该规则主题词（如 G15 无"销售服务费/支付"）才判不适用；主题词表 `_RULE_TOPIC_TOKENS` 为纯存在性测试，不含解释。
  2. 新增 `weak_rule_signals()`——把原先会**丢弃**目标的语义信号（`slot_group_missing`、`class_substitution_noop` 的语义分支、`fee_homogeneous_classes`）改为**标注待复核**，不再静默丢弃。
  3. 拆分 `class_substitution_noop`：新增 `class_substitution_letter_stable()` 承接其中的**硬事实**分支（实例化后 new_text **等于** old_text，即"改了等于没改"，F3 类），该分支**仍可合法丢弃**；`fee_homogeneous_classes` 分支改判为语义信号。
  4. `recall_pipeline._rule_already_satisfied()`：删除原 `class_substitution_noop`/`slot_group_missing` 的**软否决**；只保留硬事实分支与"逐字已满足"过滤。
  5. `recall_pipeline._rule_location_absent()`：原"段落不含任何参考文本"本身是语义判断，现**追加硬事实前提**——仅当"文档确无该规则主题词（`hard_fact_topic_absent`）且要求已满足"才判噪声，否则保留待复核。
  6. `recall.plan_target()`：原 `RECALL_RULE_NOT_APPLICABLE`（因缺类别组）改为**先查硬事实**；主题词仍在时**不整体判不适用**，改为按可用操作继续规划。
- 效果与实证：对 A/Y 产品（无 C 类）含"申购费用由"段落的真实合同（`广发上证科创板50成份ETF联接_20260924`）离线验证：G11 类规则由"被 `slot_group_missing` 丢弃"变为**保留**（`_rule_already_satisfied=False`、`_rule_location_absent=False`）。符合"可以错杀不能漏判"。
- 测试：新增 `tests/test_hard_fact_veto.py`（8 项，覆盖硬事实否决/语义不否决/字母稳定硬事实/弱信号标注）；`tests/test_recall_pipeline.py` 既有 FL-D052 用例（A+C 产品 G02 字母稳定=无改动）保持通过。**全量 `pytest tests`：649 passed / 6 skipped / 1 failed**，唯一失败为**既有无关项** `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（缺 `references/source/*.docx`，非本次引入）。
- 状态与验证：**已实施，单元与全量回归通过；真实批次效果待 P6 运行验证**（未经真实批次前不宣称指标改善）。
- 边界与风险：本次**未改** `condition_matches` 对 `class_count/has_service_fee` 的**选择**功能（它仍在多条分支里用于挑操作），只改"缺类别组即整体判不适用"的**整体否决**；类别模型（H2）、货币基金（M6）等未定义维度**仍需产品负责人按 FL-D105 Q2/Q3 定口径**，代码不得自行拍板。
- 证据：改动 `fundlex/recall.py`、`fundlex/recall_pipeline.py`、新增 `tests/test_hard_fact_veto.py`；说理来源 FL-D105 报告 `/home/opencode/GUIDE_CORPUS_FIT_REPORT.md` 及 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` FL-D091/D101。
- 变更记录：
  - 2026-10-17 新增。
  - 2026-10-19 讨论建议（**产品负责人同日部分推翻**：其中『政策文字保持逐字、不建议模型生成』部分不采纳，见下条裁定；其余判断/落位分工仍适用；背景：G08-1/G08-2 口径讨论与 FL-D119）：模型/代码职责边界——「**政策文字**」仍由代码逐字组装 + 类别槽位按实际收费性质实例化；缺类别组的"变通"=**从指引固定句中做选择**（丢弃不适用分句），不建议模型自由生成政策文本（不可逐字核验、不可复现、违背四条底线，且破坏"政策文字偏离=0"的审计与评分口径）；「该不该变通、保留/丢弃哪些固定句」属**判断**，可交模型做**选择式输出 + 依据**；「落位/衔接」由模型组合但受现有硬校验约束（固定文本逐字 `RECALL_COMPOSE_FIXED_TEXT_MISSING`、不得新增数字 `RECALL_COMPOSE_NEW_NUMBERS`），并按 FL-D119 补主题一致性守卫。状态：**建议，未实施**。
  - 2026-10-19 产品负责人裁定（**推翻上一条建议中的两项严格约束**）：`compose_variant` 的『固定政策文本必须逐字出现』（`RECALL_COMPOSE_FIXED_TEXT_MISSING`）与『不得新增数字』（`RECALL_COMPOSE_NEW_NUMBERS`）**可以推翻**；采用「**一个模型生成 + 另一个模型复核通过即可**」，不必如此严格。影响面（**待落地，未实施**）：① 内容接线 `_component_ok` 的 `composed` 分支（现要求 `fixed_text` 逐字出现在替换文中，否则 `RECALL_EDIT_CONTENT_UNVERIFIED`，只删 compose 约束不够）；② sweep 的 `required_text` 证据链（`_finding_evidence`/`_rule_required_text` 现按逐字判 `missing_new_text`）；③ 评分口径（属冻结范围，是否同步放宽需另行裁定）。复核模型（同模型独立调用／异模型）与复核不通过的处置待定。

## FL-D107 P6 第 9 轮（FL-D106 发布后）真实批次：结果对比、D09 崩溃归因、以及 sweep 输出截断这一既有脆弱点

- 发现日期：2026-10-17
- 背景：FL-D106（模型判适用/代码只兜硬事实）代码提交 `bd82207`、问题记录 `24f4d6b`、断点 `015fbaa` 后，按用户要求**发布并测试**。发布经 `tools/deploy/publish_workspace.sh` 完成，部署哈希与仓库一致（`recall.py` `1f898fe1…`、`recall_pipeline.py` `ccb2ff94…`），服务 `fundlex-recall-api`/`fundlex-recall-worker` 于 13:59:47 重启。
- 批次：`p6-dev-round9-01`，20 例开发集，20/20 完成、无 abort、成本 $0.5561。trace 已清空后独立采集并备份至 `/tmp/opencode/model-calls-round9.jsonl`。
- **结果对比（同一评分器 `tools/evaluation/p6_score.py`，同一 347 目标标签集）**：

| 批次 | 引擎 | completed | rate | kept | not_executed | delivery: reported/actually/false_complete |
| --- | --- | --- | --- | --- | --- | --- |
| round7-01 | 旧 | 220 | 0.6340 | 15 | 112 | 9 / 8 / 4 |
| round8-03 | 旧（含 FL-D101） | 211 | 0.6081 | 11 | 125 | 9 / 10 / 2 |
| **round9-01** | **新（FL-D106）** | **219** | **0.6311** | **9** | 119 | 10 / 11 / 3 |

- **2026-10-18 更正（FL-D116）**：上表 347 分母含 **111 个未运行的留出目标**；开发集实际为 **236 目标**。按 dev-only 复算：round7 **220/236 = 0.9322**、round8-03 **211/236 = 0.8941**、round9 **219/236 = 0.9280**。`not_executed` 中的 111 项是留出标签，不是引擎失败；相对比较仍成立，绝对率以 dev-only 为准。

- 结论：相对**紧接的** round8-03，completed **211 → 219（+8）**、`kept` **11 → 9（−2）**；相对 round7 为 220 → 219（−1，在噪声内）、`kept` **15 → 9（−6，明显改善）**。`kept` 是\"该删/该替换的原文仍在\"的直接指标，对应\"不能漏判\"，连续下降是本轮最实在的收益。
- 明确好转的目标（r7 → r9 判定变化，共 16 项变化里 9 项为改善）：**D04/D08/D17/D19 的 G17 删除型由 `kept` → `completed`**（FL-D101+FL-D106 主目标）、**D07 G16 由 `not_executed` → `completed`**、D12 G14 `kept` → `completed`、D19 G08 `kept` → `completed`。
- 明确回落的目标：**D09 的 7 个目标由 `completed` → `not_executed`**（原因见下，非本次逻辑缺陷）；D13 G05 `completed` → `kept`。
- **D09 崩溃归因（已查实，非 FL-D106 引入）**：
  - 现象：D09 报 `delivery_status=not_generated`、`error_code=PROCESSING_FAILED`、worker 日志 `fundlex.model.ModelError: MODEL_SCHEMA_INVALID`，发生在 `recall_sweep` 调用；单例重跑（`p6-dev-d09-check-01`）**可复现**。
  - 精确证据（`/tmp/opencode/model-calls-round9.jsonl`）：D09 的 `recall_sweep` 第 3 次调用 `finish_reason="length"`、`usage.output=4000`（**触到输出上限被截断**）、`output=None` → JSON 不完整 → schema 校验失败；同轮 D09 还有 1 次 `recall_inventory` `http_status=503` 后重试（provider 抖动）。
  - **全批次统计**：82 次 `recall_sweep` 中仅 **1 次** `finish_reason=length`（即 D09 该次），其余 81 次 `stop`；非 200 的 http 记录在 sweep 为 0；worker 日志全轮仅 4 次 `MODEL_SCHEMA_INVALID`（全部来自 D09 的重试）。
  - **排除 FL-D106 加重**：round8-03 sweep 调用/chunk **84**、round7 **80**、round9 **79** —— 发布后 sweep 工作量**反而减少**，FL-D106 并未加大 sweep 输入（sweep 上下文 `[GUIDE_REQUIREMENTS]+[FACTS]+[ARTIFACT_WINDOW]` 由代码构造，本次未改）。D09 合同（`广发悦享一年持有期混合型FOF`，1338 段）为密集长文，输出上限 4000 token 处被截断属**既有脆弱点**。
  - 配置线索：`fundlex/model.py` 的 `max_completion_tokens` 由环境变量 `FUNDLEX_MODEL_MAX_OUTPUT_TOKENS` 控制（`/etc/fundlex-recall.env` 中已设，值不记录），请求以 `max_tokens` 传入；生产实际为 4000。
- **另需说明（避免误读为失败）**：D02 本轮 `targets=0` 是正确的 `excluded_by_fund_type`（ETF 联接，`qualification.status=excluded_by_fund_type`）；round8-03 中 \"D01 crash\" 是**那一轮**的输出截断所致，D01 在 round9 正常 `complete`。
- 机制验证（改动确实生效）：round9 sweep 丢弃原因统计 `SWEEP_LOCATION_OUT_OF_SCOPE 362 / SWEEP_ALREADY_SATISFIED 172 / SWEEP_QUOTE_NOT_IN_WINDOW 74 / SWEEP_RULE_NOT_APPLICABLE 42 / SWEEP_FINDING_INVALID 124 / SWEEP_QUOTE_NOT_RESOLVED 6` —— 硬事实门控后的 `SWEEP_RULE_NOT_APPLICABLE` 仍工作，`SWEEP_ALREADY_SATISFIED` 逐字过滤仍工作。
- 处理方法：
  1. FL-D106 已发布并完成一轮真实批次验证（本条记录结果，**不宣称已达 0.9 目标**，集成完成度仍偏低）。
  2. D09 崩溃按\"既有输出截断脆弱点\"登记，**待定处理**（候选：sweep 输出上限提高 / 截断响应不做重试而是缩小该 chunk 重发 / 显式识别 `finish_reason=length` 并拆分重试）。**未实施**。
- 状态与验证：批次 `p6-dev-round9-01` 为有效批（无并发发布污染，发布发生在批次之前且已核对）；D09 失败已查实归因；指标对比基于同评分器同标签集，可比。**未做的**：未冻结版本、未跑留出 H01–H08、未生成评测结果文档、未打包。
- 证据：`var/recall-first-evaluation/p6-dev-round9-01/`、`/tmp/opencode/score-round7.json|score-round8.json|score-round9.json`、`/tmp/opencode/model-calls-round9.jsonl`、`/tmp/opencode/p6-round9.log`；对比表见 `docs/ACTIVE_HANDOFF.md`。
- 变更记录：2026-10-17 新增。

## FL-D108 sweep 响应触到输出上限被截断导致整份合同失败：改为「识别截断并把工作单元拆小」而非重试同一超长请求

- 发现日期：2026-10-17
- 背景：FL-D107 查实 P6 第 9 轮 D09 失败为 `recall_sweep` 响应 `finish_reason="length"`（输出 4000 token 上限被截断）→ JSON 不完整 → `MODEL_SCHEMA_INVALID` → 整份合同 `PROCESSING_FAILED`。用户要求**治本而非治标**。
- **根因（两层，均已定位）**：
  1. **截断被误判为"格式错误"**：`fundlex/model.py` 中，`jsonschema.ValidationError` / 解析异常一律记为 `MODEL_SCHEMA_INVALID`，且 `retry` 保持 False —— 既**不重试**，又没有区分"模型写了废话"与"模型还没写完就被截断"。
  2. **工作单元粒度与输出预算不匹配**：`_sweep_chunk_chars()` 只按**输入**上下文（4000 字符窗口）切块，而 sweep 的**输出**（findings 条数）与该窗口内违规点多寡成正比，与输入长度无关。合同越密集，单个窗口可能产出越多 findings，最终超出输出上限。**因此重试同一请求必然再次截断**——这正是"治标"的做法（也浪费预算）。
- **实测数据（说明治本点选对了）**：第 9 轮 82 次 `recall_sweep` 的输出 token 分布——`p50=146`、`p90=2874`、除截断外**最大值 3607**，仅 **1/82** 触及 4000 上限。故**不应全局提高上限**（90% 的调用用不到 3000，提上限只是多花钱），而应**把超限的那个窗口拆小**。D09 合同 1338 段、10 个窗口，其中含密集违规的窗口产出超长。
- 处理方法（**已实施**，符合"代码只兜硬事实、可核验"的边界——截断是 `finish_reason=length` 这一**逐字可核验的事实**，非语义判断）：
  1. `fundlex/model.py`：新增截断识别。当 `finish_reason == "length"` 时，`jsonschema.ValidationError` 与解析异常改记为 **`MODEL_OUTPUT_TRUNCATED`**（与 `MODEL_SCHEMA_INVALID` 明确区分）；`finish_reason` 在解析前已记录，判断可靠。
  2. `fundlex/recall_pipeline.py`：`_sweep_batch()` 改为**工作队列**。捕获 `MODEL_OUTPUT_TRUNCATED` 时调用新增的 `_split_chunk()` 将该窗口**按整段折半**，把两半压回队首继续 sweep；拆到**单段（或低于下限 `_SWEEP_MIN_SPLIT_CHARS=400`）无法再拆**时，记入 `ledger["truncated"]` 作为**诚实缺口**，不空转、不静默丢弃。拆分过程记入 `ledger["splits"]` 便于审计。
  3. `fundlex/recall_pipeline.py`：`MODEL_OUTPUT_TRUNCATED` 加入 `SOFT_STOP_CODES`，使**其他**任务遇到截断时按"可恢复暂停"处理，而非硬失败。
  4. 关键性质：`_split_chunk()` **保留原段落地址**（按 `[loc]` 行切分），故拆分后 quote 解析与 location 校验仍然有效。
- 验证：
  - 新增 `tests/test_sweep_truncation.py`（7 项）：拆分按整段且无损、单段窗口不变、下限保护、截断时拆成两个更小窗口并继续、单段窗口记诚实缺口且不空转、非截断错误原样抛出。
  - **真实合同验证**：对 D09 实际合同（`广发悦享一年持有期混合型FOF`，1338 段）实测——10 个窗口（7900–8000 字符）各拆一次均**无损**，子窗口地址**全部存在于文档**，quote/location 链路不受影响。
  - **全量回归 `pytest tests`：656 passed / 6 skipped / 1 failed**，唯一失败为**既有无关项** `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（缺 `references/source/*.docx`）。
- 状态与验证：**已实施，单元与全量回归通过，真实合同离线验证通过**；**真实批次效果待发布后验证**（未经批次前不宣称 D09 恢复或指标改善）。
- 边界与风险：未改动全局 `max_completion_tokens`（`FUNDLEX_MODEL_MAX_OUTPUT_TOKENS`）；拆分只发生在**确实截断**的窗口，其余窗口行为不变，故对第 9 轮 81/82 次正常调用无影响。
- 证据：改动 `fundlex/model.py`、`fundlex/recall_pipeline.py`、新增 `tests/test_sweep_truncation.py`；数据 `/tmp/opencode/model-calls-round9.jsonl`（输出分布）；前序 FL-D107。
- 变更记录：2026-10-17 新增。

## FL-D109 sweep 按字符全量切窗 + 向每个窗口灌全部规则：改为「章节对齐切窗 + 按窗口章节收敛规则」并保留硬兜底

- 发现日期：2026-10-17
- 背景：产品负责人指出"给模型看合同是按上下文长度拆分的，为什么不是按章节拆分"，并追问"符合（指规则）的时候是只符合涉及到的这一章节吗"。查证后确认**两个独立错配**，**均非原设计允许的"宽召回"那么简单**：
  1. **窗口切分**：`_artifact_chunks()` 纯按字符累加（`total + len(line) > max_chars`），**忽略章节边界**，一个窗口可横跨多个章节（实测 D08：1 个窗口覆盖 S03/S04/S07/S16/S17/S20/S26 共 7 节）。
  2. **规则分配**：`_sweep_requirements(rules)` 收到的是 `_guide_rules(guide_document)`——**全本指引的全部 22 条规则**，且**每个窗口都灌这一份全量**。故"符合涉及章节吗"的答案是**否**：窗口既非按章节切，规则也未按章节过滤。
- 影响：把"不该管的章节"交给模型判断，模型照答、代码再丢——round9 实测 `SWEEP_LOCATION_OUT_OF_SCOPE` **362** 次；requirements 文本按窗口数重复发送（D09 发 10 次）；密集章节堆叠导致 findings 爆长，是 **FL-D108 截断**的诱因之一。
- **更正前序结论**：本人先前称"现状违反设计 8.2"，措辞过强。设计 7.3/8.2 约束的是"候选判读限定在 action 声明章节内"，而 sweep 是**最终查漏**阶段，`SWEEP_LOCATION_OUT_OF_SCOPE` 的存在表明设计**允许** sweep 宽召回后再按 `rule_locations` 事后剔除。真正的问题是：**`rule_locations`（规则→章节映射）本已算出，却只用于事后丢弃，未用于切窗或收敛规则**——是实现错配，不是违反设计。
- 客观设计判断：切分与规则分配是**两个独立变量**，现状"字符 × 全量规则"是最差组合。**规则分配这一维改动更小、风险更低、收益更直接**（362 次丢弃主要由此产生），故先做（第一步），再做窗口切分（第二步）。
- 处理方法（**两步均已实施**）：
  - **第一步：规则按窗口章节收敛 + 硬兜底。** 新增 `_window_rule_scope()`：窗口覆盖的段落 → 所属 chapter 集合 → 仅取映射到这些 chapter 的规则；新增 `_sweep_requirements_for()` 只渲染该子集。**两道保险防止"收敛"变成"漏判"**：①`mandatory`（仍有 `needs_edit` 未完成目标的规则）强制进入其映射 chapter 所在窗口，**即便映射与实际不一致**；②**映射到任何窗口都覆盖不到的 chapter 的规则 → 回退为每个窗口都问**；③映射为空的 mandatory 规则 → 同样每个窗口都问。`_sweep_batch()` 新增 `requirements_by_chunk` / `scope_by_chunk`，并对越界 finding 记 `SWEEP_RULE_OUT_OF_WINDOW`。
  - **第二步：窗口按章节对齐 + 字符兜底。** 新增 `_section_aware_chunks()`：把**整节**打包进窗口直到预算将溢出（不切节）；单节自身超预算才在**节内**按字符拆；**不属于任何章节的段落**（`structure_index` 上限 80 节，尾部内容可能未分配）单独收集为窗口，**保证零覆盖损失**。以 `FUNDLEX_SWEEP_SECTION_WINDOWS=0` 可回退到字符切，便于同批对比。
- 验证（真实批次 + 离线，均为**同评分器/同 347 目标标签集**）：

| 批次 | 引擎 | completed | rate | kept | not_executed | 成本 |
| --- | --- | --- | --- | --- | --- | --- |
| round9-01 | FL-D106 | 219 | 0.6311 | 9 | 119 | $0.5561 |
| **round11-01** | **+FL-D109 第一步** | **225** | **0.6484** | 11 | 111 | $0.6769 |
| round12-01 | +FL-D109 第二步 | 219 | 0.6311 | 10 | 118 | $0.802 |
| round13-01 | +FL-D109 第二步（重复） | 222 | 0.6398 | 10 | 115 | $0.6487 |

  - 第一步实测（round11，20/20 完成、无 abort、无 not_generated、**零 `MODEL_*` 错误**，D09 亦恢复正常）：`SWEEP_LOCATION_OUT_OF_SCOPE` **362 → 146（−60%）**、`SWEEP_QUOTE_NOT_IN_WINDOW` **74 → 22（−70%）**、`SWEEP_FINDING_INVALID` **124 → 82**；`SWEEP_ALREADY_SATISFIED` 172 → 386（收敛后窗口**正确地**看到已满足条款，是该过滤器在起作用而非异常）。completed **+6**、rate **+0.0173**。
  - 离线验证（第一步）：12 份合同 requirements 文本量**下降 87.7%**，需问规则数由**每窗 22 条降至 mean 2.0–5.1 / max 8–11**，且**0 条规则不可达**（兜底未被触发但必要）。
  - 离线验证（第二步）：3 份真实合同窗口 19→26 / 18→25 / 20→27，**覆盖零损失**（1311/1311、1337/1337、1374/1374），**无窗口超预算**。
  - 单测：新增 `tests/test_sweep_rule_scope.py`（5 项：收敛、mandatory 强制、不可达回退、空映射 mandatory、子集渲染）与 `tests/test_sweep_section_windows.py`（6 项：章节对齐、预算受限分组、超长节内拆、未分配段落仍被扫、非可读区域排除、ID 稠密唯一）；`tests/test_sweep_truncation.py`（7 项，FL-D108）。
  - **全量 `pytest tests`：667 passed / 6 skipped / 1 failed**，唯一失败为既有无关项 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（缺 `references/source/*.docx`）。
- 状态与验证：**第一步经真实批次验证有效并已作为默认**（round11：completed 225 / rate 0.6484，优于 round9 的 219 / 0.6311）。**第二步经两次真实批次（round12 219、round13 222）测得无指标增益**，且 sweep 调用数上升（约 26 窗 vs 19 窗），故**默认关闭**（`FUNDLEX_SWEEP_SECTION_WINDOWS=0`），实现保留、留待后续在特定合同上再评估。**未宣称第二步有效**。
- 边界与风险：第一步的收敛依赖模型产出的 `rule_locations`，故设三道硬兜底。第二步经实测代价（调用数与成本上升）大于收益，保持关闭。两次 step-2 批次（219/222）与 step-1 单批（225）的差异落在**观测到的运行间噪声**内（D09 跨轮 spread 达 7；D04 为 12/11/13/13/9/13），故不宣称 step-2 有实质恶化，但同样**不宣称其有效**。两者均未改动规则语义、评分器或标签。
- 证据：改动 `fundlex/recall_pipeline.py`、新增 `tests/test_sweep_rule_scope.py`、`tests/test_sweep_section_windows.py`、`tools/evaluation/sweep_scope_probe.py`；数据 `/tmp/opencode/p6-round11.log`、`/tmp/opencode/score-round11.json`、`/tmp/opencode/sweep_scope_probe.json`、`/tmp/opencode/model-calls-round11.jsonl`。
- 变更记录（续）：2026-10-17 第二步实测无增益，改为默认关闭（opt-in）。
- 变更记录：2026-10-17 新增（两步同日实施；第一步已实测，第二步待 real batch）。

## FL-D110 引擎全链路复查：增量重扫与初次重扫不一致（已修）+ 审计/回绑三处语义缺陷（记录待决）

- 发现日期：2026-10-18
- 背景：产品负责人要求"对整个逻辑再进行检查看还有没有别的问题"。对 `fundlex/recall_pipeline.py`（2113 行）按阶段（inspect → facts → scope → inventory → survey → write → audit → sweep → deliver）逐段复查，并对 round11/12/13 三批真实产物做数据核对。
- 复查范围与已核实"无缺陷"的结论（避免后续重复排查）：
  - `_publish()` 只对 `temp_dir/final.docx` 做 `os.replace`，与审计读取的 `actual` 是同一文件对象，不存在"审计看 A、发布 B"；
  - 实测 round11–13 全部 **27 份 delivered `final` 产物 sha256 与报告 `output_validation.final_sha256` 逐一相符**（红本同理），报告哈希即产物哈希；
  - `_plan_and_generate()` 对"计划中有、但 `build_docx_edits` 未产出"的编辑回写 `RECALL_EDIT_NOT_EXECUTABLE` 并把 ledger 状态由 `planned` 改为 `unresolved`，该防线存在且有效（对应既有 `test_tampered_plan_not_generated`）。
- 缺陷 1（**已修，本次改动**）：增量重扫与初次重扫不一致。
  - 位置：`process_recall_first` sweep 段的增量重扫分支（原 `_artifact_chunks(actual, ...)` 硬编码 + `_sweep_batch(...)` 未传 `requirements_by_chunk` / `scope_by_chunk`）。
  - 问题：初次重扫在开关开启时用 `_section_aware_chunks`，增量重扫**始终**用 `_artifact_chunks`；且增量重扫**不带 FL-D109 的按窗口规则收敛**，即重新变回"给该窗灌全部 22 条规则且不校验越界"。同一轮 sweep 内两次扫描口径不同。
  - 影响规模（实测）：round11 有 **7/20** 个 case 触发增量重扫，round12 4/20，round13 4/20；D12 单案最多 3 轮。即约 **1/3 的 case 受影响**。后果：`changed` 判定（按 chunk 文本与 `swept_texts` 比对）在两次口径不同时会误判——未变窗口看似新增（浪费调用）、已变窗口看似未变（漏扫）；且增量重扫的 finding 未受窗口规则约束，`SWEEP_LOCATION_OUT_OF_SCOPE` 类噪声在重扫轮回升。
  - 处理：新增 `_sweep_chunks(actual, sections, *, max_chars)` 作为**唯一**切窗入口（初次与增量共用），增量重扫改用该入口，并对 changed 窗口重新执行 `_window_rule_scope()` 后传入 `requirements_by_chunk` / `scope_by_chunk`，与初次扫描完全同口径。
  - 验证：新增 `tests/test_sweep_rule_scope.py::test_sweep_chunks_are_the_same_for_initial_and_incremental_passes`（用 monkeypatch 断言两种开关下初次/增量派发一致）；`pytest tests/test_sweep_*.py tests/test_recall_pipeline.py tests/test_recall_integration.py` **50 passed**。**尚未跑真实批次确认指标**（见状态）。
- 缺陷 2（**记录待决，未改**）：`_target_identity` 截断 60 字导致审计结论可跨绑定存活。
  - 位置：`recall_pipeline.py:231`（`_compact(target.quote)[:60]`）、`_stale_rules()`（:876-888）、`_merge_audit_state()`（:834-849）。
  - 问题：若重扫/re-inventory 后同一 (rule, location) 的目标引文在**第 60 个压缩字符之后**才变化，`_target_identity` 不变 → `_stale_rules` 判定"不陈旧" → 旧的 `completed`+`evidence_verified` 结论**继续生效**，`_audit_issues` 不报错，交付门（:2054）可被满足。已用代码实测：`identity(quote='x'*100) == identity('x'*60+'TOTALLY DIFFERENT')` 为 `True`，且 `_stale_rules(state, [changed_target])` 返回 `set()`。
  - 可达性：需"引文 >60 字且前 60 字不变"才触发；round11–13 实测未观测到同案内真实触发（唯一一处 identity 相同者经核查为同案内 inventory/survey **重复目标**被正确去重，非缺陷）。故**实际风险低但机制真实**。
  - 建议方向（待产品负责人定夺，未实施）：identity 用 `quote` 的**哈希**而非前 60 字（或加长度），使任何引文变化都判为陈旧并触发重审。
- 缺陷 3（**记录待决，未改**）：复合(target)删除证据只检查第一个位置。
  - 位置：`recall_pipeline.py:752-754`，`for location in {target.location}`（单元素集合）；对照 `_target_locations(target)` 会返回全部复合位置。
  - 问题：模型对复合删除目标返回 `completed` 但未附可验证证据时，兜底逻辑只验证 `target.location`（锚点段）是否已空；若**续段（第二段）仍留有原文**，仍可判 `verified/deletion_evidence` 成立并清除该 issue。
  - 影响面收窄说明：`_audit_context()`（:650-654）在 [AFTER] 中**已包含全部复合位置**，模型通常能看到续段是否删除，故该兜底为**次要路径**；实测 round11–13 复合 needs_edit 目标 27 个、`deletion_evidence` 审计 **0 次**，尚未真实触发。
  - 建议方向（待定，未实施）：兜底改判 `all(_region_text(actual, loc, ...).strip()=="" for loc in _target_locations(target))`。
- 缺陷 4（**记录待决，未改，潜在**）：无 ledger 条目的编辑成分默认 `status="planned"`。
  - 位置：`recall_pipeline.py:215-217`（`_plan_by_target` 用 `setdefault(..., {"status": "planned"})`）、交付门 `:2027-2029`。
  - 问题：若某编辑成分的 `target_id` 无对应 ledger 记录，会被**默认判为 planned** 并计入交付门的"已解决"集合，且 `replacement` 为 `None`；正常路径 `plan_edits` 每目标必写一条 ledger，故当前不触发。实测 round11–13 未发现"报告 targets 中 status=planned 却无 ledger 条目"的情形。属**潜伏**缺陷。
  - 建议方向（待定，未实施）：默认状态改为 `unresolved` 或对"仅存在于 edits 成分、无 ledger"显式告警。
- 状态与验证：**缺陷 1 已实施并单测通过**（未跑真实批次）；缺陷 2/3/4 为**已确认机制、待产品负责人决定是否修改**，均未改动代码。本次未改动规则语义、评分器与标签。
- 边界与风险：缺陷 1 的修复使增量重扫口径与初次一致，预期降低重扫轮噪声与调用量，但也可能改变重扫轮 finding 集合，需真实批次确认不引入回归；缺陷 2/3/4 的修改涉及审计/交付门语义，按项目规定**须待产品负责人裁定 FL-D105 Q1–Q8 / FL-D104 1–19 后再动**。
- 证据：改动 `fundlex/recall_pipeline.py`（新增 `_sweep_chunks`、增量重扫复用收敛）、`tests/test_sweep_rule_scope.py`（+1 测试）；数据核对脚本基于 `var/recall-first-evaluation/p6-dev-round1[123]-01/*/report.json`。
- 变更记录：2026-10-18 新增（缺陷 1 已修并单测；缺陷 2/3/4 记录待决）。
- 变更记录（续）：2026-10-18 **缺陷 2/3/4 已实施**（commit `ebcd9de`）：身份键改为 `rule_id + location + sha256(start/end/全文 quote/composite)`，不再截断 60 字；复合删除证据新增 `_composite_parts_gone()`，逐 part 校验原切片已从各自段落消失；`_plan_by_target` 缺 ledger 改为 `unresolved` + `LEDGER_MISSING`。新增 5 项回归测试，全量 `pytest tests -q` → 680 passed / 6 skipped / 1 failed（既有 references 缺失项）。**待真实批次验证**。
- 变更记录（续 2）：2026-10-18 `p6-dev-round14-03`（DeepSeek 直连、**旧引擎**）基线：dev-only **218/236 = 0.9237**（kept 11 / not_executed 7），报 complete 6 / 实际 complete 10 / false_complete 1；1019 calls / **$0.7372**。原记录的 218/347 = 0.6282 是 FL-D116 的评分器分母问题（含 111 个未运行留出目标）。对照 round11 dev-only 225/236 = 0.9534；供应商切换是混杂因素。修正版（`ebcd9de`）已于 14:16 CST 发布，`round14-04` 运行中。

## FL-D111 Langfuse 追踪层吞掉引擎可恢复停止：暂停/续跑机制被破坏（已修）+ 上游周限额耗尽（外部阻塞）+ round14/14-02 批次作废

- 发现日期：2026-10-18
- 背景：产品负责人要求"对整个逻辑再进行检查看还有没有别的问题"；复查交付链路时，实测发现 `p6-dev-round14-01`（20/20 显示完成）与 `p6-dev-round14-02` 两个真实批次中，除 D01 外**全部 case 未做任何工作**（`not_generated`、targets=0、无模型调用），但批次日志显示 `completed: 20`。深挖后确认是**两个叠加问题**：一个代码缺陷（追踪层吞异常）+ 一个外部阻塞（上游周限额耗尽）。
- **缺陷 A（代码，已修）**：`observability.trace_document()` 用 `except Exception` 包住了 `yield`，把**被追踪主体抛出的异常**也一并吞掉，然后在 handler 里再次 `yield`。`contextlib` 语义下，generator 在 `throw()` 后再次 yield 会转为 **`RuntimeError("generator didn't stop after throw()")`**。
  - 后果：引擎设计中的**可恢复停止**（`RecallPipelineStop`：`MODEL_CIRCUIT_OPEN`、`MODEL_RETRY_EXHAUSTED`、预算类停止等）在到达 worker 前被替换为普通 `RuntimeError`，`Worker._is_recall_stop()` 判定失败 → 走通用失败分支 → `PROCESSING_FAILED`、`attempt=1`、**永久失败**，而设计规定的"暂停并在条件恢复后续跑"完全不生效。
  - 触发条件：Langfuse 凭据已配置（本机已配置）**且**主体抛异常；追踪关闭时该路径不经过，故此前未被发现。模块自身文档承诺"any import, configuration or network error degrades to tracing off … Observability must never turn a contract run into a failure"——该实现恰好在**最需要暂停续跑**（模型不可用）时把可恢复运行变成永久失败。
  - 生产证据：worker 日志出现 `langfuse trace failed for recall-first:inputs/<hash>.docx` 并附带 `RecallPipelineStop: MODEL_CIRCUIT_OPEN` 回溯；数据库中 round14/14-02 全部文档行为 `status=failed, attempt=1, error_code='PROCESSING_FAILED', delivery_status='not_generated'`（`attempt=1` 即终态，证明未走重试/暂停分支）。
  - 复现：新增 `tests/test_observability.py::test_body_exception_propagates_through_trace_document` 等 3 项测试，**在修复前实测复现 `RuntimeError: generator didn't stop after throw()`**（与生产一致）。
  - 处理：重写 `trace_document()`——**只吞追踪自身的建立/收尾错误**（建立失败则 `yield None` 降级为"无追踪"，主体照常执行）；主体异常原样向上传播；span 关闭放在 `finally` 且其自身错误只记日志、不替换主体结果。同时给 `trace_sink.trace_document()` 复核确认其用的是 `try/finally`，**无此问题**。
  - 验证：`tests/test_observability.py` **8 passed**（含 3 项新增）；全量 `pytest tests` → **671 passed / 6 skipped / 1 failed**，唯一失败仍为既有无关项 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（缺 `references/source/*.docx`）。
- **缺陷 B（评测工具，已修）**：`tools/evaluation/p6_run.py` 只有 `ENGINE_SCHEMA_MISMATCH` 一个中止条件。上游/预算整体不可用时，批次会继续跑完 20 个 case，每个都空跑失败，最终日志显示 `cases: 20, completed: 20`——**看起来是有效批次，评分却会读成"引擎灾难性回归"**（复盘时极易误判，本人此前一次误读即源于类似形态）。
  - 处理：新增 `ENVIRONMENT_BLOCKED_CODES`（模型/预算全局不可用类错误码），并增加"零调用 + 零目标 + not_generated"的兜底判定；命中即 `BATCH_ABORTED <code> at <case>` 并中止批次、提示 discard。
- **外部阻塞（非代码）**：上游模型服务返回 **HTTP 429 `GoUsageLimitError: Go usage limit exceeded`**，`metadata.limitName = weekly`，`retry-after: 70343` 秒（**≈19.5 小时**）。已用**独立账本**单次探测复现（避免污染生产 circuit 状态）：`UPSTREAM FAIL: ModelError MODEL_RETRY_EXHAUSTED`，账本内 `http_status=429`。
  - 影响：**当前无法进行任何真实模型批次**（含 FL-D110 的验证批次），直至上游周限额重置。此期间仍可做离线验证、单测与文档工作。
- **批次作废声明**：`p6-dev-round14-01` 与 `p6-dev-round14-02` **均不得用于评分或指标对比**——前者 19/20 个 case 空跑，后者 20/20 空跑；两者 `not_generated` 是环境所致，**与 FL-D110 改动无关**（空跑发生在 `facts` 阶段之前，根本没进入 sweep）。
- 状态与验证：**缺陷 A、B 均已实施、单测通过、已发布，并完成真实端到端验证**。真实验证方法：在上游限额耗尽（模型必然失败）的条件下，通过生产 API 提交一份真实合同任务（D01 类小合同），观察 job 结局。
  - **修复前（round14 生产数据）**：`status=failed, attempt=1, error_code=PROCESSING_FAILED, delivery_status=not_generated` —— 永久失败、真实停止码丢失。
  - **修复后（本次真实验证）**：`task status=paused`、`job_status=retry_wait`、`error_code=MODEL_CIRCUIT_OPEN`、`delivery_status=not_generated` —— **按设计暂停并保留真实停止码**，限额恢复后可由 resume 续跑。
  - 该验证任务（临时账号）批次处于 `paused`；`store.claim()` 仅从 `queued/running` 批次取件，故**不会自行续跑**，不会意外产生模型开销。
  - 上游限额仍为外部阻塞（需等待重置），重置后仍需重跑 round14 验证 FL-D110（该项**尚未验证**）。
- 边界与风险：缺陷 A 的修复恢复了"暂停/续跑"语义；修复后遇到上游限额，任务会按设计进入 `retry_wait`/暂停而不是永久失败（`attempt` 上限 3，暂停类错误码在 `store.retry()` 中会置批次为 `paused`）。未改动规则语义、评分器与标签。
- 证据：改动 `fundlex/observability.py`、`tools/evaluation/p6_run.py`、`tests/test_observability.py`（+3 测试）；日志 `sudo -n journalctl -u fundlex-recall-worker --since "2026-10-18 12:25:50" --until "2026-10-18 12:26:10"`；数据库行 `documents.status/attempt/error_code`；批次日志 `/tmp/opencode/p6-round14.log`、`/tmp/opencode/p6-round14b.log`。
- 变更记录：2026-10-18 新增（缺陷 A、B 已修并单测；上游周限额阻塞待重置）。
- 变更记录（续）：2026-10-18 缺陷 A 已发布并经**真实任务端到端验证**（暂停+真实停止码，详见上）；FL-D110 的真实批次验证仍待限额重置。
- 变更记录（续 2）：2026-10-18 13:26 CST 按用户指示**切换模型供应商**，绕过该周限额阻塞：`/etc/fundlex-recall.env`（备份 `…bak-20261018-132608`）改为 `LLM_PROVIDER=deepseek`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`；API key 仅存于该 env 文件（未写入仓库/文档）。`FUNDLEX_MODEL_REQUEST_OPTIONS_JSON` 保持 `thinking disabled`（实测 reasoning_tokens=0）；`FUNDLEX_MODEL_MAX_REQUESTS` 20000→40000（成本上限 $50 不变，切换前账本 17462 requests / charged **$14.4908**）。服务已重启，`/api/capabilities` 200，独立账本探测 `UPSTREAM OK`。**在用户明确指示前不切回原供应商**；原供应商周限额仍处于耗尽状态。
- 变更记录（续 3）：2026-10-19 **DeepSeek 直连账户余额耗尽**：`POST https://api.deepseek.com/chat/completions` 返回 **HTTP 402 `Insufficient Balance`**（用原 key 直连复现）；round14-06 在 D02 触发 `BATCH_ABORTED MODEL_CIRCUIT_OPEN`（FL-D111 守卫按设计中止），该批次**作废**（仅 2 例、无有效工作，不得评分）。旧供应商 OpenCodeGo 的周限额**已恢复**：带 `x-opencode-session` 的探测返回 200。按用户“等我告诉你再切回去”的指示**未自行切回**；等待用户决定“充值 DeepSeek / 允许切回 OpenCodeGo”。
- 变更记录（续 4）：2026-10-19 09:16 CST 按用户指示**切回 OpenCode Go 并更换新 key**（新 key 仅写入 `/etc/fundlex-recall.env`，未入库/文档/日志；切换前 env 备份 `…bak-20261019-091621`）：`LLM_PROVIDER=OpenCodeGo`、`LLM_BASE_URL=https://opencode.ai/inference/go/v1`、`LLM_MODEL=deepseek-v4.1-flash`；`thinking disabled`、`FUNDLEX_MODEL_MAX_REQUESTS=40000`、成本上限 $50 不变。服务已重启、capabilities 200、独立账本探测 `UPSTREAM OK`。`9ae799a`（FL-D118）已发布（部署 sha 与仓库一致）；**round14-07 运行中**。
- 变更记录（续 3）：2026-10-19 08:33 CST 用备份 `…bak-20261018-132608` 中的旧 OpenCode Go key 做最小探测（`POST https://opencode.ai/inference/go/v1/chat/completions`，`deepseek-v4.1-flash`，`max_tokens=1`）→ **HTTP 200**（usage 31 prompt / 1 completion）。结合 429 的 `retry-after: 70343s`（约 2026-10-19 07:57 CST 重置），判定**周限额已重置、key 可用**。项目供应商仍保持 DeepSeek 直连、未切回；同日 DeepSeek 直连返回 402，见 FL-D118。

## FL-D112 recall 生成内容复核闭包实际未生效（返回值被忽略）+ composite 分片坐标系不一致（已确认，未修）

- 发现日期：2026-10-18
- 问题与影响：
  - `docx.validate_edit_plan()` 对 `content_source=="generated"` 只执行 `content_check(edit)`，**不检查返回值**（`fundlex/docx.py:652-655`）；其函数契约（docstring）是“闭包必须 `raise DocxError`”。
  - recall 侧 `content_check_factory()` 的 `check()` 所有失败路径都是 `return False`（`fundlex/recall.py:2848-2872`），**从不抛出**；v2 侧 `build_content_check()` 是抛错实现（`fundlex/v2.py:1291-1305`），因此只有 recall-first 链路受影响。
  - 结果：recall 管线的生成内容复核（`_component_ok` 覆盖 `composite_delete/composite_replace`、`fragment_delete/fragment_replace`、`variant_*`、`composed/guide_text` 等）**在生产中不会拒绝任何 edit**，属于“校验存在但未接线”。
  - 关联缺陷：`_composite_part_slice()` 用 `display_text()` 的索引表解释 composite parts 的 whitespace-free 偏移（`fundlex/recall.py:2749-2752`），而 `plan_composite_target()` 明确按 `compact_offsets` 解释（`2118+`，注释 FL-D052）。两者在 slice 前存在空白时不一致：实测段落 `"本基金销售服务 费每日计提。"`，compact 偏移 `8` 被 display 表映射到 raw `7`（空格），正确应为 `8`。当前因返回值被忽略而未生效；一旦让校验生效，带空白锚点的 composite edit 会被**误拒**。
- 证据：
  - 离线探针 `/tmp/opencode/content_check_probe.py`：`validate_edit_plan(..., content_check=lambda e: False)` **接受** edit 并返回 plan sha；抛出 `DocxError` 的闭包会被拒绝（证明“必须 raise”的契约）。
  - 离线探针 `/tmp/opencode/review_checks.py` 第 1 项同样复现；坐标差异由 `compact_offsets` / `display_text` 对照实测。
  - 代码路径：`fundlex/recall_pipeline.py:605`（传入工厂）、`fundlex/docx.py:655`（忽略返回值）、`fundlex/recall.py:2823`（调用 `_composite_part_slice`）。
- 处理方法（建议，两处必须一起改）：
  1. 统一校验契约：`validate_edit_plan` 对 `content_check(edit) is False` 抛 `DocxError`（或让 recall 闭包抛错，二选一，建议前者，保持 v2 兼容）；
  2. `_composite_part_slice()` 改用 `compact_offsets(span.text)`，与 `plan_composite_target()` 同一坐标系；
  3. 补回归测试：篡改 composite/replace 必须被拒；带空白锚点的 composite 必须通过。
- 状态与验证：**已实施（2026-10-18，commit `ebcd9de`），待真实批次验证**。实现内容：
  - `validate_edit_plan` 对 `content_check(edit) is False` 抛 `DocxError("CONTENT_CHECK_FAILED")`；
  - recall 侧新增“逐条预检”：未通过内容校验的 edit 被丢弃，其 target 记为 `RECALL_EDIT_CONTENT_UNVERIFIED` → `unresolved`，其余 edit 继续生成，交付门因此只会给出 `incomplete`，不会把坏 edit 当完成；
  - `_composite_part_slice` 改用 `compact_offsets`；composite 校验改为按整段原文比较前缀/后缀（含 follower part），不再走“follower 直接放行”的旁路；
  - fragment 编辑记录 `fragments` 轨迹，内容校验用 `_replay_fragments` 从原文重放证明替换来源；`variant_delete`（`deleted_quote`）与 `target_span_delete` 增加确定性校验；`composite_replace` 记录 `fixed_text`；
  - `content_check_factory` 的查找键改为 target/location/span（composite 多个 part 共享 edit_id，旧键会让所有 part 只对最后一个校验）。
- 验证：`tests/test_docx.py` 新增 2 项（False 拒绝 / True 接受）、`tests/test_recall_core.py` 新增 2 项（省略号/跨段引文、带空白 composite 坐标与篡改拒绝）、`tests/test_recall_pipeline.py` 新增 5 项（identity 全文哈希、缺 ledger、盲窗回退、空 mandatory、复合删除逐段）；全量 `pytest tests -q` → **680 passed / 6 skipped / 1 failed**（唯一失败仍为既有 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`，缺 references 源文件）。
- 下一步：round14-03 基线完成后发布，跑 round14-04 对照；重点看 `RECALL_EDIT_CONTENT_UNVERIFIED` 数量、working/incomplete 比例与 kept 变化。
- 变更记录：2026-10-18 新增（外部模型复查核验时发现；该项不在其原清单内）。
- 变更记录（续）：2026-10-18 已实施并补测试，等待真实批次验证。

## FL-D113 sweep 规则范围为空的窗口：整窗 findings 被丢弃（已确认，未实施）

- 发现日期：2026-10-18
- 问题与影响：
  - `_window_rule_scope()` 只在“某规则在全文档任何窗口都不可达”时回退到全规则（`fundlex/recall_pipeline.py:1481-1488`）；若某个 sweep 窗口覆盖的 section 没有任何规则映射，该窗口 `ids=∅` → `requirements_by_chunk` 为空、`scope_by_chunk=∅`，窗口内模型上报的 findings 全部按 `SWEEP_RULE_OUT_OF_WINDOW` 丢弃（`1497+`）。确定性 survey 只覆盖可按 reference 文本命中的规则，**语义型条款在这些窗口完全不可见**。
  - 这是 FL-D109 step 1（按窗口收敛规则）留下的覆盖缺口：收益是砍掉跨章节噪声，代价是 scope_map 漏映射的 section 变成“盲窗”。
- 证据：
  - round11 离线重算（报告 round-0 chunk locations + `scope_mapping` + `structure_index`；mandatory 用 targets `needs_edit` 近似）：**80 个窗口里 14 个零规则**；D02 各窗规则数 `[14,0,8,4]`、D12 `[14,0,8,0]`、D16 `[14,0,8,0]`，每案 1–2 个盲窗。
  - section 级：round11 约 **69% 的 section 字符**所在 section 未被任何规则映射；其中含“基金合同内容摘要”等确实承载规则目标的 section（D10/D15/D19/D20 共有 43 处规则映射进摘要，说明模型是否映射摘要并不稳定）。
- 处理方法（建议）：空范围窗口回退——至少把 `mandatory` 规则并入，或整体回退全规则，并在报告中记录 `blind_windows` 以支持评测归因；任何回退都会提高噪声与调用量，需按 round11 口径做 A/B 后再定。
- 状态与验证：**已实施（2026-10-18，commit `61e210c`），待 A/B**：零规则窗口现在回退 **全部 guide 规则**（不再只给 mandatory），`blind_windows` 记录完整 fallback_rules；新增/更新的 2 项单测覆盖“有 mandatory / 无 mandatory 都回退全规则”；全量测试 686 passed / 6 skipped / 1 failed（既有）。
- 下一步：round14-06 对照 round14-04，重点看盲窗数量、sweep 调用量、`SWEEP_RULE_OUT_OF_WINDOW` 与 kept 变化；若噪声/成本上升明显再回退到 mandatory 或改为只记录观测。
- 变更记录：2026-10-18 新增。
- 变更记录（续）：2026-10-18 已实施观测 + **全规则**回退，等待 A/B。

## FL-D114 未核验 Facts 直接参与排除/分支决策（已确认，待裁定）

- 发现日期：2026-10-18
- 问题与影响：
  - `quotes_verified` 只写入报告（`fundlex/recall_pipeline.py:1849`），**不参与任何门控**；`facts.fund_type` 即使引文未核验也可触发 `excluded_by_fund_type` 并直接结束整份合同（`1846-1855`）；`condition_matches()` 用 `class_count/has_service_fee/floating_management_fee` 选择 operation，同样不看核验状态（`fundlex/recall.py:2032-2051`）。
  - 真实批次统计：round11/12/13 分别有 **3/4/6** 个 case 至少一个 `*_QUOTE_UNVERIFIED`（约 5–10%）；其中 `FUND_TYPE_QUOTE_UNVERIFIED` 每轮 1 例，三例 `fund_type` 均为 `open_regular`（未被排除）。
  - 抽查未核验引文（D06/D14 等）：`……` 省略号、跨段换行导致 `_verify_quote` 假阴性，**并非事实错误**。因此“未核验即阻断”会误伤正确事实；真正的高风险点是**未核验的 fund_type 触发整份排除**。
- 处理方法（建议）：
  1. 最小改动：`fund_type in excluded_types` 且引文未核验时，先做一次“重新取证/仲裁”调用（要求单段内逐字短引文）；仍不可核验则不排除、继续处理并在报告标注 `fund_type_unverified`；
  2. 中期：FactClaim 三态（verified/unknown/conflict）+ evidence，`condition_matches` 无 verified 时转语义裁定；
  3. 改进 `_verify_quote`：支持省略号分段校验与跨段拼接，降低假阴性。
- 状态与验证：**部分实施（2026-10-18，commit `ebcd9de`）**：`_verify_quote` 已支持省略号分段校验（每段必须逐字存在）与跨段落边界拼接（要求命中真正跨越边界）；**最小 hard-gate 保护已于 `61e210c` 实施**：`excluded_types` 且 `quotes_verified["fund_type"]` 为假时不再 `return excluded`，而是继续处理、qualification 记为 `eligible_fund_type_unverified`，并在交付门加入 `FUND_TYPE_UNVERIFIED` unresolved，禁止 complete。新增 1 项单测（未核验不排除 / 已核验排除 / 非排除类型）；全量测试 686 passed / 6 skipped / 1 failed（既有）。
- 下一步：`fund_type` 的严格证据协议（单一连续/同 section）与“重新取证/仲裁”仍待裁定；当前只是 fail-open + 不能 complete。
- 变更记录：2026-10-18 新增。
- 变更记录（续）：2026-10-18 引文核验改进 + 未核验排除保护已实施。

## FL-D115 sweep 以“重扫未再报”判定 finding resolved（已确认，待裁定）

- 发现日期：2026-10-18
- 问题与影响：
  - `_resolve_pending()` 对“被重扫窗口覆盖、且本轮未再报告同一 `(rule_id, location)`”的 pending finding 直接置为 `resolved`（`fundlex/recall_pipeline.py:1623-1636`），**不要求任何针对该 finding 的产物证据**（旧义务消失、新义务出现、锚点关系等）。
  - 模型重扫存在随机漏报；修复失败 + 下一轮漏报 → `resolved`，而 `resolved` 不进入 `pending_findings`，不阻塞 `complete`。
  - 真实批次：round11 `resolved=18 / pending=15 / unresolved=1`；round12 `8 / 19 / 0`；round13 `8 / 16 / 0`——多数 finding 走“静默 resolved”路径。
- 处理方法（建议）：finding 关闭改为**针对性证据校验**（delete：旧证据消失且保留内容仍在；replace：旧义务消失且新义务出现；append：必需条款存在于正确锚点关系）；模型未再报仅作为“候选 resolved”，需确定性证据确认。可先为 delete/replace/append 三类各加一条 evidence 规则，再评估 pending 清零率。
- 状态与验证：**已实施（2026-10-18，commit `61e210c`），待真实批次验证**：
  - `_resolve_pending()` 对 `residual_old_text` 要求引文已从产物段落消失；`missing_new_text` 要求规则的 required replacement/append 文本已出现；`wrong_text` 优先要求 required 文本出现、否则引文消失；`location_gone` 视为已消失；未知 issue 类型保留 `model_clean` 旧行为。
  - 模型“没再报”但证据不成立时，finding 保持 `pending`（`resolution=model_clean_but_evidence_missing`），继续阻塞 complete；已重新报告 → `unresolved`。
  - 新增 1 项单测覆盖 pending/resolved/unknown/still_reported 四类；全量测试 686 passed / 6 skipped / 1 failed（既有）。
- 下一步：round14-06 观察 pending/unresolved 与 complete 数量变化；若误伤过多（append 的 required 文本匹配过严），再细化 append 的证据匹配。
- 变更记录：2026-10-18 新增。
- 变更记录（续）：2026-10-18 已实施 evidence-gated closure（三类 issue），等待批次验证。

## FL-D116 P6 评分器把未运行的留出标签计入 not_executed：开发集绝对完成率被系统性低估（已修，已复算）

- 发现日期：2026-10-18
- 问题与影响：
  - `tools/evaluation/p6_score.py` 遍历 `labels.json` 的**全部 28 个 case**（dev 20 + holdout 8）；dev 批次目录里没有 H01–H08 的产物，评分器就把 **111 个留出目标全部判 `not_executed`**，与开发集的 236 个目标一起形成 **347** 的分母。
  - 结果：开发集真实完成率被稀释。round11 记录为 **225/347 = 64.84%**，实际开发集是 **225/236 = 95.34%**；round14-03 记录 218/347 = 62.82%，实际 **218/236 = 92.37%**。项目此前基于 347 口径得出的“离自动修订可靠还有明显距离”结论被显著夸大。
  - 该问题不改变同一轮内的相对比较（分子均为 dev），但所有绝对率、以及“not_executed 118”之类的读数都需要按 dev-only 重新解释。
- 证据（同一评分器修正后复算，均为 dev-only）：
  | 批次 | completed | rate | kept | not_executed | reported/actually/false_complete |
  | --- | --- | --- | --- | --- | --- |
  | round7-01 | 220 | 0.9322 | 15 | 1 | 9 / 8 / 4 |
  | round8-03 | 211 | 0.8941 | 11 | 14 | 9 / 10 / 2 |
  | round9-01 | 219 | 0.9280 | 9 | 8 | 10 / 11 / 3 |
  | **round11-01** | **225** | **0.9534** | 11 | 0 | 10 / 11 / 3 |
  | round12-01 | 219 | 0.9280 | 10 | 7 | 7 / 10 / 3 |
  | round13-01 | 222 | 0.9407 | 10 | 4 | 10 / 11 / 3 |
  | round14-03 | 218 | 0.9237 | 11 | 7 | 6 / 10 / 1 |
- 处理方法（已实施）：`p6_score.py` 新增 `--group {run,dev,holdout,all}`，默认 **`run`**——从 `batch.json` 的 `cases`/`results` 读取本次实际运行的 case，只评这些标签；`--group all` 仍可用于最终 dev+holdout 全量验收。输出新增 `cases_scored`/`groups` 并打印未评分标签数。
- 状态与验证：**已实施并复算**（commit 见变更记录）；新增 `tests/test_p6_score_append.py::test_score_selects_only_run_cases_by_default`，该文件 15 passed。修正后 round11 = 225/236、round14-03 = 218/236。
- 边界与影响：评分语义本身未变（每个目标的 verdict 规则不变），只修正分母；此前所有 347 口径的表按上表重新解释。留出验收必须在冻结版本后用 `--group holdout` 或 `--group all` 单独报告，不得再与 dev 混算。
- 下一步：round14-04 用修正后的评分器出 dev-only 指标；最终报告同时列 dev 与 holdout 两组分母。
- 变更记录：2026-10-18 新增并修复。

## FL-D117 satisfied 命中的规则级覆盖吞掉同段 delete operation 的 survey 补召回（delete 路径已修；模型 target 路径待 operation-aware 改造）

- 发现日期：2026-10-18
- 问题与影响：
  - `survey_targets()` 的覆盖率键是 `(rule_id, location)`。`satisfied_by_new_text()` 是**规则级**信号：它只证明 replace/append 的新文本已在段落中，对 delete operation 一无所知；命中后代码执行 `existing.add((rule_id, location))`，随后同一段里 `operation_search_keys()` 的 delete old_text 命中会被跳过。
  - 典型路径（G05）：同段 replace 已满足（“调低销售服务费率”已存在），但 delete 的“并报中国证监会备案”仍残留 → survey 不再补召回，planner 也没有 target 可执行该删除。
  - `override_rules` 只覆盖“delete-only 且未被 resolved needs_edit 覆盖”的规则；G05 是 replace+delete 混合规则，不在保护范围。
  - 第二个路径仍存在：模型 inventory 只报了同段一个 operation 的 target 时，`(rule, location)` 同样会压制其他 operation 的 survey 补召回——这需要 operation 级覆盖键，本轮未改。
- 证据：`fundlex/recall.py` `satisfied_by_new_text()`（约 925-970）、`survey_targets()`（约 1285-1292、1302）；新增 `tests/test_recall_core.py::test_satisfied_replace_does_not_suppress_delete_survey`（含“delete 仍残留 → 必须再出 hit”与“delete 已干净 → 不得重复 hit”两侧）。
- **残留路径（2026-10-18 复核确认）**：`_delete_operation_still_pending()` 只用**精确** `old_text in compact_body`，而 survey 的 `find_old_text_all()` 还有 fuzzy 路径（目标长度 ≥24、阈值 0.9）以及 fragment/keyword-bag 路径。离线复现：delete old_text 为“基金管理人应当在调整前及时公告并报中国证监会备案”，合同写作“基金管理人应当在调整前**事先**公告并报中国证监会备案”（difflib ratio 0.917）；当前 survey 只返回 satisfied hit；把该 helper 临时改为恒 True 后，survey 立即找到该 fuzzy delete hit。说明本修复只覆盖精确路径，fuzzy/变体仍会被 `(rule, location)` 压制；必须用 operation-aware 覆盖键根治。
- 处理方法（已实施，commit `61e210c`）：覆盖键升级为 `(rule_id, operation_key, location)`；`operation_search_key_pairs()` 给每个 search key 标注操作；`satisfied_operation_keys()` 只标记**自身新文本已存在**的 replace/append；`known_operations_from_targets()` 从 target 的显式 operations 或 span 内容计算覆盖；`_delete_operation_still_pending()` 已删除，不再逐个打补丁。
- 状态与验证：**已实施，单测通过**：精确 delete、fuzzy delete variant、模型 target 只覆盖 replace 时 delete 仍可补召回（新增 3 项测试）；全量 `pytest tests -q` → 686 passed / 6 skipped / 1 failed（既有 references 缺失项）。**待真实批次验证**（round14-06）。
- 下一步：round14-06 对照 14-04；观察 `kept`/`not_executed`、重复 target 与 sweep 调用量。之后才考虑把 operation 正式加入 Inventory schema / Target API。
- 变更记录：2026-10-18 新增并修 delete 路径。
- 变更记录（续 2）：2026-10-18 `p6-dev-round14-05`（仅 `c04d51a` 精确路径，Dev 20 例）dev-only **220/236 = 0.9322**（kept 10 / not_executed 6），reported complete **2** / actual 11 / false 1；**1240 calls / $0.9053**。目标完成率与 14-04 持平，但 survey 补出的 delete targets 使 unresolved 增多、complete 从 7 降到 2（交付更保守），调用/成本 +23%。结论：**精确补丁单独没有指标收益**；operation-aware 合并版见 `61e210c` / round14-06。
- 变更记录（续 3）：2026-10-18 `61e210c` 已发布（部署 sha 与仓库一致），round14-06 运行中。

## FL-D118 DeepSeek 直连余额耗尽（HTTP 402），真实模型批次再次受阻

- 发现日期：2026-10-19
- 问题与影响：2026-10-18 为绕开 OpenCode Go 周限额（FL-D111）把 `/etc/fundlex-recall.env` 切到 DeepSeek 直连；2026-10-19 08:32 CST 最小请求探测返回 **402 Insufficient Balance**。round14-06 及 FL-D110、FL-D112–D117 的真实批次验证再次无法继续；离线工作与 OpenCode 免费模型不受影响。
- 证据：`POST https://api.deepseek.com/chat/completions`（`LLM_MODEL=deepseek-flash`，`max_tokens=1`）→ HTTP 402，响应体 `{"error":{"message":"Insufficient Balance (request_id: 7fe02cf1-a4a3-4bac-8339-2e385f3ee987)","type":"unknown_error","code":"invalid_request_error"}}`。密钥仅存于 `/etc/fundlex-recall.env`，未打印。
- 处理方法：按外部余额阻塞处理，暂停真实模型批次并保留断点；不重置账本、不用替身结果冒充交付。需用户充值 DeepSeek 或提供可用 key/端点；切回 OpenCode Go 需用户明确指示（该 key 已于同日探测为 HTTP 200，见 FL-D111 续 3）。
- 状态与验证：**已实测确认**（2026-10-19，402 原始响应）；阻塞（外部余额）。
- 下一步：用户确认余额/新端点后，先做单次 `UPSTREAM OK` 探测，再续跑 round14-06。
- 变更记录：2026-10-19 新增。

## FL-D118 operation-aware 后续漏接四处：汇总二次吞并 / unknown 压制 / 交付门漏 coverage_gaps / D115 三边界（已修，未发布）

- 发现日期：2026-10-18（外部复查指出，2026-10-19 核实并修复）
- 缺陷 1（**P0**）：`_collect_targets()` 仍按 `(rule_id, location)` 去重，把 survey 为同位置**另一个 operation** 生成的 synthetic target 丢弃，直接抵消 operation-aware 改造。
  - 处理：只做**精确重复**去重（key = rule/location/operations/start/end/quote）；语义覆盖判断只保留在 survey 层。
- 缺陷 2（**P0/P1**）：`operations_cover_hit()` 对 `state is None`（target 存在但 operation 不可判定）返回 covered，会压制 specific operation hit。
  - 处理：`None` 对 specific operation **fail-open**（返回未覆盖）；wildcard hit 维持旧语义。为兼容旧调用方，`known` 传 `(rule, location)` 列表时用 `_LOCATION_WILDCARD` 哨兵，仍按位置覆盖压制。
- 缺陷 3（**P0**）：`complete` 条件逐项列举但漏了 `coverage_gaps`，报告可同时出现 `unresolved`（如 `SURVEY_QUOTE_UNRESOLVED`）与 `delivery_status=complete`。
  - 处理：新增 `_delivery_complete(unresolved)`，**最终 unresolved 非空即不得 complete**；报告与门禁同源。
- 缺陷 4（**P1**）：D115 三边界——`missing_new_text` 接受 `location_gone`（段落消失但 required 文本未出现也判 resolved）；`wrong_text` 在 required 已知时仅凭旧文消失即 resolved；`unaddressed_requirement` 落入 unknown → model-clean。
  - 处理：`location_gone` 只作为 `residual_old_text`（及无 required 的 `wrong_text`）的证据；`missing_new_text`/`unaddressed_requirement` 必须有 required 文本出现；`wrong_text` 有 required 时必须 required 出现；`unaddressed_requirement` 纳入 evidence-required 集合。
- 缺陷 5（**P0，2026-10-19**）：`_survey_targets_from_hits()` 在已有 target 的 operation 覆盖为 `None` 时执行 `known.setdefault((rule_id, location), set()).update(hit.operation_keys)` → `None.update` 抛 `AttributeError`；round14-07 的 D01 因此 `PROCESSING_FAILED`、批次作废。
  - 处理：改用 `_add_operation_coverage()`（把 unknown 状态替换为具体 key 集合，不 update None）；新增回归测试 `test_survey_targets_from_hits_handles_unknown_coverage`。
- 缺陷 6（**P0，2026-10-19，对缺陷 1 的修正**）：`_collect_targets` 的“只做精确重复去重”过宽——同位置重叠的 survey targets 大量进入 planner。round14-08 实测：`RECALL_EDIT_OVERLAP` **66**（round11 为 8）、plan conflicts **38**（5）、G17 完成 **2/11**（10/11）、dev **211/236 = 0.8941**（kept 20）。
  - 处理：`_collect_targets` 改为 **operation-aware + unknown 覆盖 fail-closed**：synthetic target 的 operation 在每个位置都已被覆盖（含 unknown）才丢弃；真正未覆盖的 operation（如 inventory 报 G05:0 时的 G05:1 delete）仍保留。`_collection_covered()` 与 survey 层的 fail-open 规则分开，避免重复编辑。
  - 验证：新增/更新测试 `test_collect_targets_keeps_different_operations_at_one_location`（未覆盖 delete 保留、covered duplicate 与 unknown duplicate 丢弃）；全量 **690 passed / 6 skipped / 1 failed**（既有）。
- 缺陷 7（**P0，2026-10-19**）：`_collect_targets` 的 unknown fail-closed 对 **wildcard synthetic（确定性 append）**过严：inventory 的 `absent` 目标把位置标成 unknown coverage，导致 append pass 已定位的 G01/G03 目标被丢弃（round14-09 中 D01/D19 的 G01/G03 共 4 个 `not_executed`，dev 221/236）。
  - 处理：wildcard synthetic 只在**所有位置**都有 `needs_edit` 或 `satisfied` inventory target 时丢弃；`absent` 判定不阻止（正是 append pass 要纠正的情形）。新增 satisfied/absent 两侧测试；全量 **691 passed / 6 skipped / 1 failed**（既有）。
- 证据与验证：新增/更新 7 项测试（`_collect_targets` 同位置双 operation、unknown fail-open、`_delivery_complete`、D115 六种 finding 场景、unknown-coverage survey hit）；全量 `pytest tests -q` → **691 passed / 6 skipped / 1 failed**（唯一失败仍为既有 references 缺失项）。
- 状态：**已实施（commits `9ae799a` + `03fbbfa` + `d6cc8ce` + `46afe2f`），单测通过；`46afe2f` 已发布（部署 sha 一致）；round14-10 运行中**（round14-06/14-07 作废；14-08 为重叠回归证据；14-09 为 append 丢失证据，均不作为有效提升）。
- 下一步：供应商恢复后发布并跑 round14-07（对照 round14-04 的 220/236 与 14-05 的保守交付）。
- 变更记录：2026-10-19 新增并修复。

## FL-D119（机制已离线复现）G08 把"赎回费率由基金管理人决定"句当申购参考命中并替换：假 satisfied 尾句 + survey 模糊阈值放行，14-08 由 fail-open 显现

- 发现日期：2026-10-19
- 问题与影响：round14-08（运行中；OpenCodeGo、engine commit `03fbbfa`）中 D01/D03/D06 出现 G08 目标落在**赎回**费率披露句（"本基金的赎回费率由基金管理人决定，并在招募说明书中列示。"，与 G08 参考"**申购**费率…"仅"申/赎"一字之差）。以 D01 为例：survey 生成 p227 目标、计划并落地替换，终稿把该赎回句覆盖为 G08 申购政策文本（原句丢失）；引擎 audit 已连标 `wrong`/`AUDIT_NOT_COMPLETED`/`AUDIT_MISSED_TARGET`，但按"复核只标记不回撤"仍落盘（交付 incomplete）。时间线：`p6-dev-round14-03/14-04/14-05` 的 D01 终稿均**保留**该赎回句，仅 14-08 丢失——与 FL-D118 缺陷 2（unknown 覆盖对 specific operation 改 fail-open）暴露此前被压制的潜伏误配一致。
- 机制（**已离线复现**，纯代码调用、未花模型预算）：
  1. `satisfied_by_new_text(G08, facts, p227)` 经 `_final_clause_candidates` 命中**通用尾句**"并在招募说明书中列示。"（该尾句同时也是旧句自身的结尾），误判 satisfied；`satisfied_operation_keys(...)` 返回**空集** → 覆盖记 `None`（unknown）。
  2. `find_old_text_all(..., threshold=SURVEY_FUZZY_THRESHOLD=0.9)` 对 28 字参考走模糊分支：赎回版与申购版 difflib 比值≈0.93 ≥0.9 → p227 产生 survey 命中；用 0.95 复跑无命中。
  3. `operations_cover_hit(None, specific)` 新版返回未覆盖（fail-open）→ 该命中不再被步骤 1 的 unknown 覆盖压制（结果上：14-03/04/05 终稿未发生该替换）。
  4. `plan_target`：`fuzzy_span_clause(threshold=VARIANT_MATCH_RATIO=0.95)` 不命中（0.93<0.95）→ 落 `compose_variant`（模型组合）→ 替换文本=G08 实例化政策原文 → 赎回句被改写为申购文本（主题替换）。
- 证据或复现线索：`var/recall-first-evaluation/p6-dev-round14-08/{D01,D03,D06}/report.json`（audit 段含上述标记与引文，`evidence_verified=true`；survey 记录含 `{"rule_id":"G08","operation":"survey","locations":["p227"],…}`）与 `D01/working_final` p227；对照 `p6-dev-round14-03/04/05/D01/working_final`。离线复现：D01 原文段落 + G08 参考，`find_old_text_all(...,0.9)` 命中 p227（0.95 不命中）；`satisfied_by_new_text` 返回"并在招募说明书中列示。"。
- 处理方法（**建议，均未实施**；涉及评分/交付语义的部分须先裁定）：① 收紧 `satisfied_by_new_text` 尾句通道——候选还需与规则参考文本有足够差异或含核心动作词，通用收尾句不得单独判 satisfied；② survey 模糊阈值 0.9 对"仅核心词不同"（申购/赎回等）的匹配加校验或提高门槛，避免主题翻转命中；③ 复核 `operations_cover_hit` fail-open 与 satisfied 空 keys 的组合边界；④ 是否加 compose 阶段主题一致性守卫（属交付校验语义，待裁定）。
- 状态与验证：**机制已离线复现并验证**（2026-10-19）；"是否为需修复缺陷、采用哪种修法"**待裁定**；未改任何代码，不宣称已修复。
- 下一步：round14-08 结束后复核结论是否一致；与 FL-D118 改动一并评估；裁定修法后再实施 + 单测 + 真实批次验证。
- 变更记录：2026-10-19 新增（机制离线复现已验证）。

## FL-D120 文本生成职责边界：产品负责人方案「确定性优先、模型补位」（Policy Compiler + Semantic Rewriter，讨论中）

- **2026-10-28 审计补充**：默认registry中G09只允许SPLICE，G06/G13/G15/G17只允许DELETE；专用/fragment/0.95 fuzzy路径耗尽后，即使compose_budget>0仍报 `RECALL_ROUTED_EXECUTOR_UNAVAILABLE`，不存在通用“让模型接手”出口（不等于应允许模型随意生成删除文本；应由模型判应删范围、代码执行）。另有G11契约不一致：合成原句“申购费用由投资人支付，不列入基金财产。”在模板成功生成后，Replay报 `CLAIM_OPERATION_SPAN_UNAUTHORIZED`，effect site另要求“承担”；不是每个阶段在用同一语义授权。状态：**离线行为已复现，未修复**；需统一语义批准记录贯通候选→归属→执行→证明，而非每层再写词表判一遍。证据 `docs/evidence/strictness-audit-20261028.json` 的G09/G13/G11。

- 发现日期：2026-10-19（产品负责人提出方案并征求意见；本条目记录方案、现状差距与评估，**未实施**）
- 方案要点（产品负责人）：
  1. 结构：**程序决定「改什么、必须包含什么、哪些内容不能丢」**；能确定性生成的文本由程序生成；只有「需结合合同原文重组语言」的场景才让模型生成，并同时经过**程序校验 + 独立模型复核**。
  2. 规则分三类：① 确定性修改（结果可由规则 + 已验证事实唯一算出，如 G14 集合式删除）→ 程序生成；② 参数化规则（模型只理解 Facts 分类——收费组/服务费组/直销豁免组等，正文由程序模板生成，如 G08/G11）→ 程序生成正文；③ 模型生成 + 强复核（只改原段一部分、其余必须保持合同原写法，如 G16）→ 三层验证。
  3. 三层验证（第三类专用）：第一层程序级硬校验（semantic invariants：must_add 组件齐全、protected literals 保留）；第二层 diff/preservation（未授权变化的数字/百分比/期限/主体/公式/公告条件一律拒绝，尽量代码完成）；第三层独立模型复核（semantic critic，**不作为最终安全门**）。
  4. 删除型（G15/G17）：语义定位后**程序删除**，不让模型写 replacement（除非目标 span 内含有必须保留内容）。
  5. 操作级 `generation_strategy` 元数据（如 template / model_compose / delete + required_components + preserve）。
  6. 原则：**代码能判的事不许交给复核模型**（如"类别是否全覆盖""0.40% 是否保留"必须代码校验）。
  7. 目标比例：约 **60–80% operation 确定性生成 / 20–40% 模型 compose**。
- 现状差距（我方核实；数据：`var/recall-first-evaluation/p6-dev-round14-05/{D01..D20}/report.json`，20 例共 **284** 条编辑的 `content_source`）：现状已是确定性级联，**最终文本由纯程序产出的 ≈56%（159/284）**、含确定性兜底 ≈64%（+`whole_paragraph_delete` 24）；**含模型产出 ≈36%**（`composed` 53、`merged` 30、`composed_delete` 18；`merged` 为机械合并、组件来源混合）。
  - 「本该确定性却全走模型」的最大两块：**G14 16/16 全 composed**、**G09 13/13 全 composed**（模板化这两个规则是把确定性占比抬到 70%+ 的最短路径）。
  - G08 7 composed / 7 fragment_replace、G11 4/9、G12 7/3；G05 已基本确定性（fragment 29）。
  - G15/G17 已基本「模型定位 + 程序删除」；其中 24 条整段删除是**先发起 compose（失败 `DELETE_NOT_SHRINKING`）再走确定性兜底**——可前置判断直接走确定性以省调用。
  - G16 现为 append 固定文本 + 合并写入（guide_text 7 + merged 15），**尚无「与合同原机制融合 + 保留」的生成机制**（第三类的典型新增项）。
  - 现有验证器已含部分硬校验（`_component_ok`、`RECALL_COMPOSE_NEW_NUMBERS`、preserved 回查），但**无「授权变更窗口外逐字不变」的 diff 校验**、无 must_add 组件级校验。
- 我方评估与补充（同日讨论）：方向**赞同**，与 FL-D106 同线（模型判、代码证明）；它本质是把现有「template → 最小化拼接 → compose」级联**显式化并补强**，不是推倒重来。补充三点：
  1. tier 应由**运行时前置条件**决定而非按规则静态归类（同一规则不同合同会落不同层：G08 干净整句 → 模板；G08「范围大于指引」段 → 最小编辑或 compose），级联顺序 template → minimal-splice → compose，并持续记录走层（`content_source` 现成）。
  2. 第二层 diff 里最强的一条门是**「授权窗口之外（去空白后）逐字不变」**，一条即可覆盖数字/期限/公式/公告条件的绝大部分，且与现有 `_splice_fragment` 语义同源；窗口内再校验 must_add/must_preserve 组件。这也是落实 FL-D106 2026-10-19 裁定（compose 两条硬约束可推翻）的安全方式。
  3. `generation_strategy` 建议放**代码侧注册表**（guide JSON 是编译产物，手工字段重编会丢），注册表需覆盖全部 22 条规则并加断言测试；FL-D119 的主题一致性守卫并入第二层校验设计。
- 拟分阶段（待确认后转实施计划）：① 策略注册表 + 观测指标（确定性占比）；② 验证器强化（授权 diff / protected literals / must_add 组件，可先旁路观测）；③ 模板生成器（G14、G09 优先）；④ 第三类 compose + 独立复核接线；⑤ 开发集验证与回归（受 FL-D118 供应商阻塞影响）。
- 状态与验证：**讨论中**（方向已评估赞同，细化项待产品负责人确认）；**未实施**、未改任何代码；评分/交付语义部分属冻结范围，需另行裁定。
- 变更记录：
  - 2026-10-19 新增。
  - 2026-10-19 实施计划文档已建：`docs/GENERATION_STRATEGY_PLAN_2026-10-19.md`（分阶段、含 5 项待裁；状态：**待批准**）。
  - 2026-10-19 **v2 并入**：产品负责人修订版方案（V3 失败改 unresolved、V2 精确授权窗口、UNKNOWN FACT ≠ tier3、Coverage Ledger 单一真相、成本三分、7-commit 顺序等）已并入计划文档；评审修正点 8 项列为文档**附录 A（待确认）**；v1 草稿被取代（差异见文档附录 B）。状态仍为**待批准、未实施**。
  - 2026-10-19 **八项业务裁定并入（v3）**：G11-1 认购/申购"错位"族经全量核查为**材料/定位问题**（454 行全量字段核查：368 行材料含真实申购目标句、85 行以场内 ETF 为主；按 B 报告勘误）；"按收费性质"归类基准确认（扩展 G11）；G14 四类费用句与"138 已含服务费 / 40 部分类别"**直接替换为新表述**；G15 删除照常 + 与指引参考有出入时**标记"原合同可能有误"**；"每日计算、逐日累计"≡"每日计提"；**货币基金不在修改范围**；class_count/无字母按**实际份额类别结构**。计划文档（v3）与映射文档已同步。
  - 2026-10-19 **二次工程评审并入（v4）**：V2 拆 **V2-A 边界门 / V2-B 变更解释门**（EXPLAINED / UNEXPLAINED_SOFT→V3 / UNEXPLAINED_HARD→FAIL 三级）；Coverage Ledger 先**只读视图**（Phase 1）；新增 **Phase 3 Facts 扩展 + 三态**（`share_class_structure` 替代裸 `class_count`）；**FL-D119 根因修复 + G11 定位回归**入 Phase 2；**Artifact Verification 升为 Claim Replay**（Phase 8）；`VERIFIED_EMPTY ≠ UNKNOWN`；阶段重排 **Phase 0–8**、commit 序 8 个。计划文档（v4）已同步，**附录 A 全部并入正文**。
  - 2026-10-19 B 类报告处理映射已建：`docs/B_CLASS_PROCESSING_MAP_2026-10-19.md`（逐形态 / 逐 Q 映射；收敛出仍待业务裁定 8 项、统计口径 4 项）。
  - 2026-10-19 **实施（Phase 0–8 代码完成）**：按 v4 计划完成全部 Phase 的代码与单测（registry/router/coverage 只读视图；V1/V2/A/B 影子验证；FL-D119 根因修复；Facts 三态；Tier1/Tier2 确定性生成；Tier3 V3 独立复核；Artifact Claim Replay 接线），全量 750 passed / 6 skipped / 1 failed（既有）；已发布并启用 `FUNDLEX_GENERATION_STRATEGY=registry`（env 备份 `.bak-genv4`），批次 `p6-dev-round14-11` 验收中。进度与证据：`docs/GENERATION_V4_PROGRESS.md`。

## FL-D121（已核实，未修复）成功操作提示在任务总览/任务详情/指引配置页不可见

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：`toast()` 的成功分支调用 `flash()`，后者只写 `#upload-message`（仅批量导入页存在），没有全局提示容器；`notice()` 的成功分支直接丢弃。`togglePause`、`exportResults`、`enableGuide`、`resetToBuiltinGuide`、`reparseGuide` 等在非导入页的成功反馈不可见；错误则进铃铛。用户会重复点击，误以为操作未生效。
- 证据：`frontend/app.js` 第 31–35 行 `notice`/`toast`/`flash`；`#upload-message` 只在 `#view-import`。`frontend/index.html` 第 35 行已有 `#toast` 元素，但上述函数未使用。
- 处理方法（**已实施，2026-10-19**）：新增全局 toast 栈组件，`toast(message, kind)` 使用 `#toast`，支持 success/error/info、自动消失、`aria-live` 与 8 秒内同文案去重；`flash()` 改为成功 toast，`errorNotice()` 同时进铃铛与错误 toast；导入页上传进度仍保留行内提示。状态：已实施；本地 dev 实例真实浏览器验证 25/25 通过（`/tmp/opencode/ui_smoke.py`）。
- 下一步：随第一批前端改动一起发布时复验生产页面；后台自动刷新不弹成功提示。

## FL-D122（已核实，未修复）消息中心仅内存态，不能作为持久消息中心使用

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：`notifications` 是页面内存数组；刷新/重新登录清空；`monitorTasks` 只在页面打开且轮询时检测状态变化，用户离线期间完成的任务不会产生消息；打开面板即全部标记已读，无单条已读/全部已读/查看全部；无消息类型字段。
- 证据：`frontend/app.js` 第 27–40 行；`resetWorkspace()` 清空 notifications。
- 处理方法（待决定）：A. 本地持久化（localStorage 按账号保存，启动时从近期任务派生完成/暂停事件）——快，但不能跨设备；B. 服务端 `notifications` 表 + `/api/notifications`（列表/单条已读/全部已读），任务状态变更时写入——真正的消息中心，需迁移与测试。建议 B；若本期只做 UI，则用 A 并明确限制。状态：待产品决定，未实施。
- 下一步：确认持久化范围后实现。

## FL-D123（已核实，未修复）任务总览“本月合同数/完成率/平均处理时长”缺少后端数据契约

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：当前 `/api/tasks` 只返回当前账号的任务分页；`_summary` 只有 `created_at`/`updated_at`，没有 `started_at`/`finished_at`，无法准确计算处理时长；前端若用当前页 20 条聚合会失真。`completed` 含 `failed`，完成率必须区分“进入终态”和“成功完成”；“异常”也未定义（failed/rejected/incomplete/excluded）。
- 证据：`fundlex/tasks.py` 的 `_summary`；`fundlex/api.py` 的 `GET /api/tasks`；`frontend/app.js` 的 `stats()`。
- 处理方法（建议）：新增服务端聚合接口（如 `GET /api/tasks/stats?month=YYYY-MM`），按账号和 `Asia/Shanghai` 时区聚合；增加 `started_at`/`finished_at` 或任务事件表并做迁移；先固定口径：本月创建合同数、成功完成/总数、平均单合同处理时长（开始处理到终态）、待处理（queued+processing+retry_wait）、异常（failed+rejected+delivery incomplete，excluded 单列）。
- 状态与验证：口径和实现均待确认，未改代码。
- 下一步：确认指标定义后做迁移、API 和测试。

## FL-D124（已核实，未实现）“重试选中异常”没有后端契约，现有 failed 为终态

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：API 没有 retry 端点；`TaskStore._summary` 的 failed 对应 `job_status=failed`；worker 内部只在临时故障时 `store.retry`，业务失败、资格失败、非合同、格式错误等不可重试。前端若直接对 failed 调 retry，可能重复计费、重复修订或对不可恢复错误无效。批量多选还需幂等、epoch 和预算控制。
- 处理方法（建议）：新增 `POST /api/tasks/{id}/documents/retry`（body 为 document_ids），服务端白名单只允许临时性错误（如 MODEL_NETWORK_ERROR、MODEL_RETRY_EXHAUSTED、TEMPORARY_STORAGE_FAILURE 及明确可重试的处理异常），排除资格/非合同/格式/权限/预算停止；保留原产物历史，生成新 attempt/version，记录操作人、时间和预算。前端只对可重试行启用，确认框说明会重新消耗模型额度。
- 状态与验证：建议，未实施；是否需要本期做待产品确认。
- 下一步：先定可重试错误白名单；不做则从方案移除或明确标“暂不支持”。

## FL-D125（已核实，未实现）任务级“完整审计日志”没有事件表/API

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：任务只有 `created_at`/`updated_at`，没有 stage/event 记录；报告里的 audit 是规则复核轮次，不是任务操作审计。可由任务/文档状态近似展示“创建→上传→封存→开始处理→处理中”的精简时间线，但“时间/操作人/操作”的完整日志无法从现有数据还原，历史任务尤其不可能。
- 处理方法（建议）：A. 本期只做派生精简时间线，不提供“完整审计日志”死入口；B. 新增 `task_events` 表，在创建/上传/封存/暂停/恢复/重试/完成等写入，提供 `GET /api/tasks/{id}/events`，历史任务标记“无事件记录”。建议 B，避免以后补历史。状态：待决定，未实施。
- 下一步：确认范围后建表和接线。

## FL-D126（已核实，未实现）指引“按建议修复”无后端，现有解析器已自动修复

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：`POST /api/guides/{id}/parse` 只是重新入队；`build_guide_document` 内部已有基于 validation/verification 的 repair 轮次，但没有按 issue id 定向修复的 API。`issues_detail` 的 errors/warnings 有 code/rule_id/detail，coverage_gaps 有段落号，但不总有结构化的“问题位置/修复建议”。前端若放“按建议修复”按钮只能触发重新解析，不能保证定向修复，属于误导。
- 处理方法（建议）：A. 本期把问题条目展开为“规则/段落/原因/建议（按错误码映射）”，按钮改为“重新解析（自动修复）”，并说明会重新调用模型、消耗预算；B. 后端新增结构化 issue（location/suggestion/repair_action）与定向修复端点（需防重复、预算与审计）。建议先 A，B 另立。
- 状态与验证：**UI 侧已实施（2026-10-19）**：问题条目改为可展开详情（问题位置/失败原因/修复建议），错误与核验发现默认展开，面板内新增“重新解析（自动修复）”按钮（内部仍调用 `POST /api/guides/{id}/parse`）；定向修复端点未实现。真实浏览器验证 10/10 通过（`/tmp/opencode/ui_guide_check.py`）。
- 下一步：若要真定向修复，另立后端契约；当前按钮文案已明确“自动修复”实际是重新解析。

## FL-D127（已核实，未实现）全局搜索与审查“上一份/下一份”受现有 API/分页限制

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：`/api/tasks?q=` 只搜任务名称；合同搜索必须带 task_id（`/api/tasks/{id}/documents?q=`）；没有跨任务合同名/全文搜索接口。`state.taskDocs` 只保存当前页（默认 20 条），审查页“上一份/下一份”只能在本页切换；`openReview` 每次重置 `chosen`，切换会丢未生成的勾选。
- 处理方法（建议）：全局搜索先做命令面板（页面导航 + 任务名搜索 + 当前任务合同搜索），或新增 `/api/search?q=`（owner 范围、任务/合同名、分页；全文检索需索引，另议）。审查切换按“当前筛选结果”跨页懒加载，切换前保存每份合同 decisions，跳过无修订合同；文件名/内容随 `showDetail` 更新。
- 状态与验证：**部分已实施（2026-10-19）**：修订审查新增“上一份/下一份”，按当前筛选结果懒加载跨页合同、跳过无修订合同，切换前保存每份合同的勾选；A/R 快捷键、点击定位与列表/文档联动均已实现并在本地真实浏览器验证 20/20 通过（`/tmp/opencode/ui_review_check.py`）。全局搜索仍未实施，待范围决策。
- 下一步：确认全局搜索范围（仅名称/当前任务，还是跨任务全文）后实施。

## FL-D128（设计冲突，待确认）批量导入“创建成功后自动跳转”与补传流程冲突

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：任务在创建时即存在，上传按组进行；部分文件被拒/未传时，当前页面保留补传清单和“导出待补传清单”。若创建成功立即跳任务详情，用户看不到上传进度/失败原因，也失去补传入口。现有代码只在 `seal` 后且本页文件全部接收时跳转。
- 处理方法（建议）：改为“封存且全部接收后自动跳转；存在 pending/rejected 时留在导入页并显示‘去任务详情’按钮”，或跳转后在任务详情保留补传卡片。建议前者，保留现有失败恢复能力。
- 状态与验证：**已按建议实施（2026-10-19）**：封存后仅在全部文件接收时自动跳转任务详情；存在待补传/接收失败时留在导入页，显示上传结束状态、待补传与接收失败数量，并保留补传清单。真实浏览器验证：全部接收 6/6、部分失败路径通过（`/tmp/opencode/ui_smoke.py`、`/tmp/opencode/ui_redirect_check.py`）。
- 下一步：无；随第一批前端改动发布。

## FL-D129（内容依赖，待确认）页脚“帮助中心/隐私/服务条款”缺少可发布内容与版本来源

- 发现日期：2026-10-19（前端改造方案评审）
- 问题与影响：`/api/capabilities` 未返回应用版本；仓库中没有可对外发布的帮助中心、隐私政策、服务条款文本。直接放链接会形成死链或未经审阅的法律文本。
- 处理方法（建议）：在 capabilities 增加 `app_version`/`build`（或使用静态资源内容哈希）；帮助中心先用应用内弹窗承载真实操作说明；隐私/服务条款需由产品/法务提供正式文本后再接入，未提供前不显示可点击链接。
- 状态与验证：**部分已实施（2026-10-19）**：`/api/capabilities` 新增 `app_version`（当前 0.1.0），页脚显示 © 广发基金 · FundLex 版本号 · 帮助中心；帮助中心为应用内弹窗（真实操作说明）；隐私政策/服务条款暂为不可点击占位（title 提示“正式文本待发布”）。真实浏览器验证通过（`/tmp/opencode/ui_smoke.py`）。
- 下一步：待产品/法务提供正式文本后再接入可点击链接。

## FL-D130（外部复查，2026-10-19）v4 生成策略落地复查：4 项 P0 未闭合 + 2 项 P1

- 发现日期：2026-10-19（另一 agent 对 GitHub HEAD `f19039a` 的代码复查；本条目为其结论与处理响应）。
- **P0-1 Router 未接入 planner（待修）**：`route_operation()` 与 Registry 目前属旁路设施；`recall.plan_target()` 仍自行按 condition+cascade 决定路径→"UNKNOWN FACT ≠ Tier3"尚未从架构上保证。处理：Router 成为生成路径唯一入口（fact 门→blocked→unresolved；记录 requested/actual tier）。状态：待修（下一有效批次前）。
- **P0-2 V3 按 default_tier 而非 actual tier 触发（已修）**：进入 `compose_variant` 即 actual tier = COMPOSE；原实现仅对 `default_tier==COMPOSE` 调用 V3，G08/G11/G14 的 fallback compose 会跳过复核。处理：删除 default_tier 门，composed 路径一律执行 V3（开关开启时）；新增 G08/G14 fallback-compose 测试替换原写死错误行为的测试。状态：**已实施（本提交）**。
- **P0-3 G16 Tier3 pilot 未按试点实现（待产品裁定）**：Guide G16 为 append，planner 在 append 分支直接 `guide_text` 返回，走不到 compose；Registry 写 COMPOSE 与执行不一致。两个方向：A=确定性 append + 智能 satisfied（推荐）；B=真正的组件融合（component extraction→compose→V1/V2/V3）。状态：**待裁定**（进度文档"Phase 0–8 代码完成"表述已订正）。
- **P0-4 Coverage Ledger 未接 Delivery Gate + operation 粒度回退（待修）**：`CoverageEntry` 缺 `operation_id`（FL-D117 operation-aware 成果未继承）；delivery 仍是 `_delivery_complete(unresolved)`，非 ledger 正向证明。处理：条目加 operation_id；gate 至少先读 ledger 投影（projection→proof），storage 统一仍后置。状态：待修。
- **P1-1 Tier 标签/遥测**：勘误——按计划 §19.1，干净整句即 Template 级，`tier1_template` 记录本身符合计划；`plan_policy_replacement` 的 docstring 误写 "Tier-2"，**已改为 §19.1 表述**；显式 `requested/actual tier` 字段随 P0-1 接入时补。状态：部分已修（docstring），字段待随 P0-1。
- **P1-2 VERIFIED_EMPTY 闭环未实现**：空 group 现一律 UNKNOWN（保守、不会误生成）；generation routing 尚未消费 VERIFIED_EMPTY。状态：待办（P1）。
- 其他：GitHub HEAD 无 CI 状态（建议加 Actions，非优先）；复查时段 HEAD=`f19039a`，其后已推进数据入库与停止确认两个提交。
- **第二份复查（源材料版，同日）**：阅读指引原文（68–88 段）+ 合同原文后提出 **6 项 P0 + 6 项 P1**（Facts 三态真接线 / 类别与币种模型 / `class_label` 叠字 / G15+G16+G17 业务闭环 / G16 组件级 coverage / G08-G11 组件级 drop / Router 唯一入口等）；关键代码断言经核对**全部属实**（证据行号见 `GENERATION_V4_PROGRESS.md`）。**处置：队列为 P0-A~D + P1，用户指示暂缓实施。**
- **ETF/同业存单范围裁定（2026-10-19 用户确认）**：**维持全局排除**（来源=C-R 设计文档 §9 默认 + 本次确认；后续按 policy override+依据 记录）。
- **REITs/封闭式商业不动产范围裁定（2026-10-20 用户确认）**：**REITs（基础设施 REITs 与封闭式商业不动产）同样不用修改**，纳入整份排除。默认集合由 `etf,money_market,interbank_cd` 扩为 **`etf,money_market,interbank_cd,reits`**（`fundlex/recall_pipeline.py::DEFAULT_EXCLUDED_TYPES`，2026-10-20 已改并新增排除回归测试；**未发布**）。合同自述口径：`广发成都高投产业园封闭式基础设施证券投资基金`（p43"本基金为基础设施基金"）与 `广发新城吾悦封闭式商业不动产证券投资基金`（p44"本基金为不动产投资信托基金（REITs）"）均归 `reits`。生产 env 未设 `FUNDLEX_RECALL_EXCLUDED_TYPES`，代码默认生效。
  - **真实模型核验（2026-10-20，临时账本，2 calls / $0.00514）**：两份合同均返回 `fund_type=reits`、`quotes_verified=true`；排除分支会在 facts 阶段结束后终止，不产生修改产物。注：成都高投的 `fund_type_quote` 取的是"存续期、封闭期…上市交易"句，虽可回查但未直接自述 REITs/基础设施基金；分类正确、证据指向性偏弱，后续可要求模型引用"本基金为基础设施基金"类自述句（**未实施**）。
  - **ETF 联接基金不属于 ETF**：用户 2026-10-20 进一步确认"ETF 联接基金正常修改"；只有 ETF 本身排除。确定性 feeder 判定与真实核验见 FL-D132。
  - 单测：`tests/test_recall_pipeline.py::test_excluded_reits_fund_type_report`（新增）与 `test_excluded_fund_type_report`（默认集合断言）通过；`tests/test_recall_pipeline.py + tests/test_recall_core.py` 76 passed（含 feeder 测试）。
- 关联：`docs/GENERATION_V4_PROGRESS.md`（外部复查响应节）、`docs/GENERATION_STRATEGY_PLAN_2026-10-19.md`。
- 变更记录：2026-10-19 新增（外部复查登记）；同日 P0-2 修复并加测试；同日追加第二份复查清单与 ETF 范围裁定；2026-10-20 追加 REITs/封闭式商业不动产排除裁定与代码/测试变更。
  - 2026-10-19 **实施 P0 批次**（commit 见 git log）：P0-A（`condition_status` 三值 + `plan_target` 入口 gate/route 记录）、P0-B 部分（`class_label` 保合同原文称谓、`service_group` 严格定义、两费皆真→CONFLICT）、P0-C（G16 组件级 satisfied、G15 `business_notices` 接线并去重）、P0-D（G08/G11 仅裁缺失组子句，registry）、P1 部分（G06/G13/G17 关键词签名、G14 扩展句补项、coverage `operation_keys` + delivery gate 读投影、claim replay 已接线）；另修 V3 的 `recall_verify` 未在网关白名单导致 `MODEL_TASK_UNSUPPORTED`。**全量 773 passed / 0 failed**。残余：币种维度拆分、semantic site anchor、per-operation claim replay、CI、红色盲核（FL-D131③）。

## FL-D131（用户澄清，待办）指引文件中的红色字并没有特殊含义

- 发现日期：2026-10-19（产品负责人澄清）。
- 问题与影响：此前多处把指引中的红色字当作有特殊含义——① `docs/CONTRACT_AND_GUIDE_READING_20261014.md` 的阅读记录写明"核对部分红色、加粗文字"；② 源文档 G18 的标题自带"，标红部分为变动内容"，编译产物 `guides/builtin_guide_v1.json` 的 G18 `title` 原样保留；③ 解析管线 `fundlex/guide.py` 把 `red_paragraphs`/`bold_paragraphs` 的段落索引列表作为源信息头（`_source_header`）喂给解析（`_parse_context`）与复核（`_verify_context`）模型——指令文本本身**未解释**红色含义，但模型可能自行将其读作"变动/重点内容"的暗示。**用户澄清：红色字没有特殊含义。**
- 影响盘点：**运行时引擎（识别/修改/验证/交付）完全不使用红色**（仅 `guide.py` 编译期引用；全仓 grep 确认）→ 对现网交付零影响。受影响面仅限：编译期提示的潜在偏置（未证实）、G18 标题尾缀（装饰性）、阅读记录的表述。
- 处理方法（建议，**未实施**）：① 从 `_source_header` 移除 `red_paragraphs`/`bold_paragraphs`（或保留提取但不传给模型，仅做统计）；② 清理 G18 `title` 的"标红部分为变动内容"尾缀（或其保留但注明为来源原文照抄）；③ 可选：对现有 22 组做一次"不看红色"的盲核（离线比对 `requirement`/`operations` 与源文本），确认现包未被红色暗示影响。
- 状态与验证：**部分已实施**（2026-10-19）：解析/复核上下文改为仅输出 red/bold **计数**（不再传段落索引）；G18 标题尾缀已清理。剩余可选项：不看红色的盲核。
- 下一步：随 P0 队列一并处理；若做盲核，结果记回本条目。
- 变更记录：2026-10-19 新增（用户澄清 + 影响盘点 + 处理建议）。

## FL-D132 ETF联接基金的 fund_type 判定不一致：同一引文既判 etf 又判 open_regular

- 发现日期：2026-10-19（核对合同样本类型时发现）。
- 问题与影响：D02《广发上证50交易型开放式指数证券投资基金发起式联接基金》与 D06《广发创业板交易型开放式指数证券投资基金发起式联接基金》都是 **ETF 联接基金**，`facts.fund_type_quote` 都是同一句 `ETF 联接基金` 且 `quotes_verified=true`；但 `p6-dev-round14-09` 中 **D02 判 `etf` → `excluded_by_fund_type`（整份排除、零修改）**，**D06 判 `open_regular` → 继续处理**（delivery=incomplete）。两份合同正文 p28/p29 均自述"…发起式联接基金由基金管理人…募集"，并非 ETF 本身。影响：① 同类产品因一次模型抽取差异被整份排除，属漏改；② 评分分母把排除项剔除后，该漏改不会体现在完成率里。
- 证据：`var/recall-first-evaluation/p6-dev-round14-09/D02/report.json`（`qualification.status=excluded_by_fund_type`、`fund_type=etf`、quote=`ETF 联接基金`）对比 `.../D06/report.json`（`status=eligible`、`fund_type=open_regular`、同一 quote）；合同原文 p28/p29（`funds_word/广发上证50…联接基金…20241113.docx`、`…创业板…联接基金…20250319.docx`）。
- 处理方法（**已实施**，2026-10-20）：① 用户裁定 **ETF 联接基金正常修改**，只有 ETF 本身排除；② `fundlex/recall.py` 新增 `_is_etf_feeder()`（封面/标题段同时含"联接基金"与"基金合同"即判为联接基金），`extract_facts()` 在模型返回 `etf` 且合同为联接基金时确定性改为 `open_regular`，`fund_type_basis=etf_feeder_is_open_regular`；③ facts prompt 升为 `recall_facts_v3`，明确"联接基金属普通开放式基金，不是 etf"。
- 状态与验证：**已实施/已验证（本地，未发布）**。`tests/test_recall_pipeline.py` 新增 `test_etf_feeder_is_eligible_and_revised`；`test_recall_pipeline.py + test_recall_core.py` **76 passed**。真实模型核验（临时账本，3 calls / $0.00650）：D02、D06 均 `open_regular`（`feeder=True`，引文回查通过）；对照真 ETF `广发中证全指食品ETF` → `etf`（`feeder=False`），排除逻辑未被放宽。
- 下一步：发布后跑下一有效开发集批次，确认 D02 不再 `excluded_by_fund_type`、D06 正常；与 FL-D130 的 REITs 排除一并观察。
- 变更记录：2026-10-19 新增；2026-10-20 用户确认"ETF 不用修改"；同日进一步确认 **"ETF 联接基金正常修改"**，据此实施确定性 feeder 判定 + prompt v3 + 回归测试与真实模型核验。

## 后续条目模板

### FL-Dxxx 问题名称

- 发现日期：
- 问题与影响：
- 证据：
- 处理方法：尚无方法时写明待分析。
- 状态与验证：注明建议/已确认/已实施/已验证及具体范围。
- 下一步：
- 变更记录：

## FL-D133 Obligation-first / 双模型 / Recovery 架构改造（2026-10-20）

- 发现日期：2026-10-20（用户提出最终改造方案后立项）。
- 目标与影响：把原有 Guide/Facts/Applicability/Target/Generation/Validator/Audit/Sweep/Claim Replay/Coverage/Delivery 统一为 obligation-first、evidence-backed、deterministic-first、model-assisted、fail-closed、recoverable 的链路；解决“UNKNOWN 静默当 FALSE/TRUE、模型 offset、Validator 只影子、Repair 叠加错误 artifact、Claim Replay 一次失败即终局、Review 与 Primary 不可独立配置”等结构性问题。
- 证据与实施（分支 `refactor/recovery-architecture`，commit `374440a..HEAD`）：
  - `/home/opencode/fundlex/fundlex/models/`：Primary/Review 独立配置、任务角色路由、独立调用记录、共享预算账本；允许同型号但角色/任务/prompt/上下文独立。
  - `/home/opencode/fundlex/fundlex/obligations.py` + `applicability.py`：ALL_OF/ONE_OF/BRANCH/INDEPENDENT、`G05:B1:O1` 身份与旧 `G05:1` alias、tri-state 适用性、UNKNOWN 不执行、applicable 无 target → OPEN_OBLIGATION、scope 遗漏规则 → `SCOPE_RULE_OMITTED` 而非静默不适用。
  - `/home/opencode/fundlex/fundlex/facts_recovery.py`：UNKNOWN/CONFLICT 聚焦重取、类别枚举句集合完整性、Review 仲裁、引文代码回查；恢复决定写入 `Facts.condition_overrides` 并进入 planning。
  - `/home/opencode/fundlex/fundlex/generation/validators.py` + `components.py` + `joint.py` + `claim_replay.py`：硬校验（必需项/边界/数字来源/受保护字面量/费用主题/组件×站点）、G16 四组件、Joint Compose 先 Validator 再 Review、claim replay 文档级与段内边界证明、重复列表序号不再误判为金额。
  - `/home/opencode/fundlex/fundlex/recovery/` + `delivery.py`：FailureClass、RecoveryAction、预算、历史、用户三态输出；Claim Replay 失败重建后重新 audit/sweep/replay。
  - `/home/opencode/fundlex/fundlex/targeting.py`：T3 模型定位只返回 quote/location，代码重新 `resolve_quote`/`containing_segment`；无目标规则的自动 T3 默认关闭（见限制 2）。
- 验证：
  - 全量 `pytest tests -q` → **878 passed / 6 skipped**。
  - 离线 `validator_shadow` 对 `p6-dev-round14-12`：19 例 / 222 段编辑 / **0 hard FAIL**；修复了 D03 列表序号 “4、” 被误判为受保护金额的 false positive。
  - 真实模型（临时账本，OpenCode Go）：D01 早期一版报 `complete_with_notices`（27 calls），但 Business Reviewer 复核 DOCX 发现 G17 p760 残句、G15 正文/摘要不一致，属 **false_complete**；新增 delete-only 逐句残留、重复副本一致性、G05/G06/G01/G03 目标锚点后，D01 被如实阻塞为 partial（96 calls / 约 $0.052）。D02（ETF 联接基金）`eligible/open_regular`，G05 compose 失败如实标记 partial；D03 G06 复合目标未解决 partial；D11 旧版 false_complete 被新门改为 partial（G15 误绑托管费、G09 第二处措辞缺失）。临时账本合计约 963 requests / $0.5792，未触碰生产账本。
  - 独立 Architecture Reviewer 发现并已修复：scope 遗漏被静默 NOT_APPLICABLE、plan `not_applicable` 覆盖 TRUE、Validator/Claim Replay 受 flag 开关、claim recovery 复用旧 audit/sweep、类别枚举前缀漏洞、审计一个 completed 掩盖另一个 wrong、Infrastructure stop 被吞。Business Reviewer 另发现并已部分修复：delete-only 短 span 残留、正文/摘要重复副本不一致、G05/G06 错误站点、中文数字时限通知、VERIFIED fact 被 applicability override 推翻、G02/G04/G08/G11 fee-group CONFLICT 未阻断、货币/描述性类别枚举、ONE_OF 残留变体。仍保留：无目标规则 T3 默认关闭、audit context 分批未实现、514 全量未跑、G05/G06/G15/G17 真实业务残留、尚未取得最新硬门下真实 complete。
- 生产发布与端到端（2026-10-20 20:37 CST，快照 `0fae88e`）：`publish_workspace.sh` 成功，API/Worker active；关键模块与部署副本 sha256 一致。真实工作台默认入口 D01：19 条修订、目录保留、14 页；拒绝 1/接受 18 → `selected_final` 136125 bytes、sha256 `efd9f20c…`、0 残留修订；accept-all 19 条成功；working 产物可下载；交付 `incomplete` 如实。任务 `db67ed71…`、文档 `9a0810a9…`。
- 子集回归（用户授权只跑部分，未跑 514）：D01 partial 93 calls/$0.0516；D02 partial 56/$0.0636；D11 partial 125/$0.0906；D16 partial 61/$0.0554。D11 旧版 false complete 被 blocked；D16 旧版 integrated complete 变 partial，需复核是否过度阻塞。
- 状态与验证范围：**已实施/已发布/真实工作台端到端通过**；但**未完成 §51 全量验收**。用户明确要求 agent 不自行跑全量，只跑子集；514 由用户运行。
- 下一步：① 修 G05/G06/G15/G17 目标/审计残留与 D16 过度阻塞；② 用户跑 514 全量/留出；③ 前端展示 `user_summary`/`failure_class`；④ 根据全量结果继续调优。
- 变更记录：2026-10-20 新增；同日发布并完成真实工作台 E2E；同日补子集回归。

## FL-D134（评估，未实施）任务总览改版（2026-10-20）的前端可改范围与后端缺口

- 发现日期：2026-10-20（产品负责人提出总览页改版需求后核对现有 API/前端）。
- 可**不动后端**完成：侧边栏「批量导入」改「新建任务」（图标不变）；右上角「角色 · 姓名」格式（`/api/auth/me` 有 `display_name`、`role`；但 `role` 仅 `admin/member`，见下）；保留面包屑；移除单任务卡片、替换为批量总览卡片的结构/文案/按钮（新建 `newTask()`、刷新 `refresh()` 均已有）；5 个指标卡的布局/文案/占位；「我的任务」标题、右侧新建按钮、「查看」文案、状态标签；任务名下方指引名称可用 `/api/guides` 的 `filename` 与任务 `guide_snapshot.version_id` 前端映射；通知铃铛与红点保持不动。
- **需取舍**：按指引名称筛选。`/api/tasks` 目前只支持 `q/status/sort/page`，没有 `guide_version_id` 参数；纯前端正确实现需拉取全部任务后本地筛选/分页（任务量小可行，量大不建议），或后端增加筛选参数。
- **必须后端或只能占位**：本月处理合同数、本月完成率、待处理合同、异常合同、平均处理时长、环比变化。现 `/api/tasks` 的任务摘要只有 `created_at`/`updated_at`，没有 `started_at`/`finished_at`，平均时长无法准确计算；也没有月度聚合/环比接口。按需求「数值后端渲染，前端只做占位结构」，本轮可先用 `—` 占位，真实值另立 `GET /api/tasks/stats?month=...`（含完成/待处理/异常/平均秒数/环比）并补时间戳或任务事件表。
- **批量导出**：描述文案可写；现有能力是单任务 ZIP（`/api/tasks/{id}/download/all`）与单任务 CSV，没有跨任务批量导出接口。若只是描述任务内批量导出，文案成立；若要做总览页跨任务导出，需后端。
- **角色名称**：当前用户字段只有 `role=admin/member`，没有「法务专员」等职务字段。可先前端映射 `member→法务专员`、`admin→管理员`；若要每个账号显示真实职务，需后端增加 `job_title`/`title` 字段。
- 状态与验证：**已实施（2026-10-20，方案 B），本地验证通过，未发布生产**。右上角用户区按产品负责人更正**未改**。
- **实施内容**：
  - 后端 `GET /api/tasks/stats?month=YYYY-MM`（owner 范围）：本月处理合同数（按 `finished_at`）、完成数/完成率、待处理、进行中任务数、异常合同、平均每份处理秒数（`started_at→finished_at`）、上月处理数及环比；月份按 `Asia/Shanghai`（固定 UTC+8）边界。
  - `documents` 表新增 `started_at`/`finished_at`：`claim` 首次领取写 `started_at`，`finish`/终态 `retry`/租约耗尽写 `finished_at`；迁移对历史终态行用 `created_at`/`updated_at` 回填近似值（新行精确）。
  - `GET /api/tasks` 新增 `guide_version_id` 筛选参数；`TaskStore.list` 在所有者任务范围内过滤。
  - 前端总览改版：侧栏「新建任务」；批量总览卡片（BATCH OVERVIEW、标题、描述、新建/刷新、本月完成率进度）；5 个指标卡（本月处理合同/完成率/待处理/平均时长/异常）；「我的任务」表格、按指引筛选、任务名下方指引名称、「查看」按钮；数值接入 stats 接口，加载/失败时保留 `—` 占位。
  - 样式复用现有 `.hero/.stat/.table/.badge/.progress-line`，仅新增局部作用域规则；未改配色、Logo、全局基础样式，未新增图表。
- 验证：全量 `pytest tests -q` → **875 passed / 6 skipped**；headless Chromium 对本地真实 API 验证 **23/23**（总览数字、5 卡片、指引名称/筛选、Chip、刷新、0 控制台错误），截图 `/tmp/opencode/ui-batch2/overview.png`。测试 seed 当前月 2 份处理（1 完成/1 异常）、待处理 1、平均 90 秒、上月 1 份；页面显示 50%/+100%/1 分 30 秒与 90 秒描述，与接口一致。
- 未发布原因：工作区存在另一 agent 未提交的 `fundlex/generation/template.py`、`fundlex/recall.py` 等引擎改动；此时执行 `publish_workspace.sh` 会把未协调改动一并带到生产，故本轮只提交本功能文件，待并行改动收敛后再发布。
- 下一步：并行引擎改动提交/发布后，执行统一发布并在生产真实登录页复验；若要跨任务批量导出，另立后端接口。

## FL-D135（已定位，生产已临时修复）自定义指引解析在 4000 输出 token 处被截断

- 发现日期：2026-10-20（用户反馈：指引配置页上传自有 DOCX 后显示“解析失败”）。
- 问题与影响：DOCX 本身可正常读取，失败发生在模型解析阶段。`fundlex/guide.py` 的 `parse_guide()` 要求模型一次返回完整 `groups` JSON；生产 Worker 的全局输出上限为 4000 token。本指引完整解析约需 5500–7800 completion token，三次尝试均在 4000 处收到 `finish_reason=length`，JSON 被截断。用尽 `MAX_GUIDE_JOB_ATTEMPTS=3` 后版本状态变为 `failed`；而 API 与前端只允许 `uploaded/parse_failed/parsed` 重新解析，导致“重新解析”按钮禁用，用户只能重复上传。
- 证据：
  - 源文件 `v4存量基金适用销售费用新规的基金合同修改指引.docx`（sha256 `9bc1ff24…`）可提取 107 段 / 105 非空段 / 6359 字符，非 DOCX 损坏。
  - 两个自定义版本 `08ac8c239c8d444a862edd0b7b0d8dfa`、`5f5392bbe48549d7badbbaa43c47586c` 为同一文件；最近版本 `issues_json = {"error_code":"GUIDE_MODEL_FAILED:MODEL_OUTPUT_TRUNCATED", "attempts":3}`。
  - 账本 `/var/lib/fundlex/model_budget.sqlite` 中最近 6 次 `guide_parse`：`completion_tokens=4000`、`finish_reason=length`、`content_chars=8763–9361`，错误为 `MODEL_OUTPUT_TRUNCATED`（旧代码记为 `MODEL_SCHEMA_INVALID`）。
  - 内置指引 `guides/builtin_guide_v1.json` 的模型事件显示历史解析 completion 为 6514 / 7798 / 7657 token；`tools/build_builtin_guide.py` 默认 `DEFAULT_MAX_COMPLETION_TOKENS=8000`，而生产环境变量为 4000，故内置指引可用、同规模自定义上传失败。
- 处理方法（生产临时修复，2026-10-20）：
  - 备份 `/etc/fundlex-recall.env` 为 `.bak-guide-output-*`，将 `FUNDLEX_MODEL_MAX_OUTPUT_TOKENS` 从 4000 调整为 8000，重启 `fundlex-recall-worker` 并核对进程环境。
  - 将版本 `08ac8c23…` 从 `failed` 置回 `parse_failed` 并重新入队；Worker 第 1 次即完成（completion 5712、`finish_reason=stop`），状态 `parsed`、15 个规则组、`coverage_gaps=0`。
  - 未改代码、未执行 `publish_workspace.sh`（工作区仍有其他 agent 未提交的引擎改动）。
- 状态与验证：**临时修复已验证**。产物解析成功且可启用；但版本仍报 1 个确定性错误 `GUIDE_SLOT_NOT_IN_TEXT`（G12，`C类基金份额` 未出现在任何 `new_text`）与 12 条独立核验 findings，属指引内容/模型理解问题，不是输出截断。该上传为非勘误版（15 组），与内置勘误版（22 组）不同。
- 下一步：① 给 `guide_parse` 增加专用输出上限（目标 8000）或分块解析，避免依赖全局 env；② 允许 `failed` 版本重新解析并同步 API/前端；③ 更新部署默认值与文档；④ 由用户决定启用该 15 组指引、改用勘误版，还是继续使用内置指引。
- 变更记录：2026-10-20 新增；同日完成临时配置修复、重新解析和证据登记。

## FL-D136 Recovery 架构收口：operation-level Claim Replay、统一恢复与 open obligation（2026-10-20）

- 发现日期：2026-10-20（产品负责人第二轮外部复查，要求以 `refactor/recovery-architecture` 最新 HEAD 为基线收口，不再扩张架构）。
- 问题与影响：
  1. `claim_replay` 的 `_authorization_for_group()` 按 paragraph 合并同一 location 下多个 operation 的授权，operation B 理论上可借用 sibling A 的删除或新增权限；段落级通过不能证明每个 obligation 各自的 span/授权/必需项。
  2. `RecoveryOrchestrator` 只在 claim replay 深度接入；audit/repair 仍主要依赖 `rounds_used → notes → reinventory → regenerate`，恢复决策没有统一 history，无法从报告看出某 obligation 为何 unresolved。
  3. `FUNDLEX_TARGET_LOCATOR_OPEN_RULES` 默认关闭，applicable obligation 被 inventory 完全漏掉时只能 partial，系统发现问题却不能安全恢复。
  4. G02/G04 同段多个相同 `A类基金份额`/`C类基金份额` 时，`resolve_quote(span, old_text)` 绑定第一个 occurrence，可能改错位置。
- 处理方法（分支 `refactor/recovery-architecture` 工作区，待提交）：
  - Claim Replay：按 edit/component 建立 operation unit；授权只取该 unit 的 target operation keys（无 keys 时由该 unit 的 old_text/new_text 反推），每个 unit 独立跑 `validate_edit`；新增 borrow 检测（append-only 操作吞掉既有文本 = `CLAIM_OPERATION_SPAN_UNAUTHORIZED`；替换段使用未选中 sibling 的 new_text = `CLAIM_OPERATION_EFFECT_MISSING`）；重叠 edit 进入显式 Joint 验证（union 授权 + 每个 unit 自身效果），不再用错误的 offset 逐条重建；返回 `operations[]`（rule/operation/obligation/target/location/span/scope/verdict/effect_errors）与 `obligations{}` 状态，一个 operation 失败则整组 FAIL。pipeline 传入 `targets_by_id` 与 `obligation_ledger`。
  - Recovery：`RecoveryOrchestrator` 的 VERIFICATION 分支支持 `metadata.route_class` 回到 TARGET/GENERATION/FACT 等根因层；audit/repair 每轮把 issue 分类为 `RecoveryContext` 并调用 `decide()`，未终局动作写入统一 `RecoveryHistory`，下一轮按 issue 数变化记录 succeeded/failed；`max_business_rounds` 仍是唯一全局断路器；报告保留 `recovery.business_rounds`。
  - Open obligation：新增确定性候选搜索（scope section + 规则 topic tokens + class tokens + delete keyword bag + reference fragments）；`FUNDLEX_TARGET_LOCATOR_OPEN_RULES` 默认改为 `auto`，无 anchor 证据不调用模型并保持 OPEN；locator 上下文只含候选段落，quote 必须唯一且通过 topic/class/keyword 复核，越界/歧义/不符即 rejected；同一 quote 在正文/摘要重复副本时创建受控 duplicate-copy target。
  - G02/G04：Target 新增 `site_candidates/occurrence_index/occurrence_anchor`；`resolve_occurrence()` 用 inventory quote 的上下文打分选择 occurrence，未命中或多候选无法区分时抛 `RECALL_TARGET_OCCURRENCE_AMBIGUOUS`（TARGET），不猜；Claim Replay 对带 occurrence 身份的 target 复核编辑 span 是否覆盖授权 occurrence（`CLAIM_OCCURRENCE_MISMATCH`）。
- 新增测试：`tests/test_claim_replay_operation_authorization.py`（6）、`tests/test_open_obligation_recovery.py`（5）、`tests/test_g02_g04_occurrence.py`（4）、`tests/test_recovery.py` 补 APPLICABILITY/EXECUTION/VERIFICATION 根因路由（3）。
- 状态与验证：**代码收口完成，待最终真实子集回归确认**；未发布生产。提交 `4ceaebe` + `a9d1501` + `db4c1c9`。
  - 全量 `pytest tests -q`：**929 passed / 6 skipped / 0 failed**（本轮新增/更新 52 条测试）。
  - 独立 Reviewer（Architecture/Test/Recovery）首轮发现并已修复：无 target/无法反推的 multi-op edit 仍走 rule-wide union；oversized delete、replace 借用删除、拼接 sibling 新增、缺失自身 new_text、component 绕过；overlap 分支不记录 unit 失败、any 判定、无边界证明；audit 恢复只记录不执行、pending 未赋值导致 history 为空、terminal 不终止、context 按 rule 合并/静默截断；RecoveryAttempt 无 obligation 身份、预算全局串扰；open locator 不过滤 quote 锚点/站点、duplicate clone 过宽、auto 对宽 topic 不安全、rebind 绕过 open 校验；G02 quote/offset 冲突未拒绝，Claim Replay 未复核 occurrence_anchor。
  - 首轮探索性真实子集（代码在运行中逐步变化，仅作参考，不作最终结论）：D01 incomplete 76 calls、D02 incomplete 43、D11 incomplete 93、D16 incomplete 87；四例均如实 partial，D11/D16 出现 `DUPLICATE_SITE_DIVERGED`（待最终批次复核是真实正文/摘要分歧还是过阻）。
  - 第二轮/第三轮 Reviewer 后追加修复：移除 single-op 绕过（单 operation 同样做 old/new/删除 residual 证明）；删除操作按 residual-text 而非 diff 片段证明（防止字符级对齐隐藏整句删除）；overlap 联合结果禁止未授权新增文本并保留 disjoint span 之间的 gap；occurrence 归一化空白（真实 DOCX "A 类基金份额"）并支持 index 0；G02/G04 增加 class-definition site guard；G02/G04 required terms 按整段复核；G14 分支按条件/替换文本归因；facts-aware slot 实例化（G01/G08/G02 等真实组别）；composed delete 仍保留删除所有权；open delete 规则可用 keyword bag 作为候选锚点；AUDIT_VERDICT_MISSING 增加 re-audit 预算。移除 legacy paragraph-scoped multi-op rule-wide union fallback（无 attribution 一律 `CLAIM_OPERATION_UNATTRIBUTED`）；composed edit 按 composer/validator 语义不强制逐字 guide new_text；delete operation 必须真正移除旧句；ONE_OF alternatives 授权与 unselected alternative 测试补齐；audit 预算身份加入 `site_id`；issue 成功判定改用稳定 `(code,rule,location,obligation)`；非执行类 decision 立即记 skipped；claim regeneration 后重新计算 target/audit/sweep unresolved 与 `report["audit"]`，`recovery.final` 在仍有 unresolved 时改为 `unresolved`；audit 修复体异常时保留已产生的 recovery history。
  - 第三轮 Business Reviewer 后又修复：replace 必须移除旧句（除非 new_text 保留）；composed replace/append 仍做 residual 所有权；G02/G04 required terms 改为整段缺失判定；artifact 级证明拒绝“未被计划的 sibling operation”；absent/out_of_scope target 不再视为 open recovery 已覆盖；G01/G03 append quote 需携带政策措辞；G02/G04 quote 需携带 class-definition site 措辞。
  - 真实子集重跑曾遇外部模型 503：`MODEL_RETRY_EXHAUSTED`（HTTP 503，两次 attempt），D01 首轮重试即 stopped；随后恢复。
  - 最终代码真实子集（临时账本，逐例对照 FL-D133 基线）：
    - D01：incomplete，25 targets / 16 edits / 79 calls / $0.0591（基线 93/$0.0516）。claim replay verified=true；残余 p135 重复副本上的 G05 overlap、G03 append 未插入、G06 delete 未删除、G05 备案句残留 + 2 条 audit + 1 条 OPEN_OBLIGATION。真实业务未完成 + duplicate-site/overlap 待解，不是 claim replay 误报。
    - D02：incomplete，50 targets / 18 edits / 135 calls / $0.0889（基线 56/$0.0636）。claim replay 拒绝 `CLAIM_OPERATION_NOT_PLANNED`（G05 适用删除操作在 artifact 中仍存活），另有 G05 p1162 compose fixed_text 缺失与 audit 未完成；真实业务未完成。
    - D11：incomplete，27 targets / 15 edits / 149 calls / $0.0946（基线 125/$0.0906）。G05/G14 p1109 target unresolved、G16/G17 sweep 残留、G05 删除未计划；真实业务未完成。
    - D16：incomplete，42 targets / 19 edits / 85 calls / $0.0483（基线 61/$0.0554）。G06 composite 两处未解（p431/p1169）、G13 p222 / G14 p224 / G15 p822 / G17 p822 残留、p822 正文/摘要副本分歧、G05 删除未计划、G16/G18 OPEN。旧版 complete 属 false complete（G15 旧支付机制与 G06 转换限制仍在、副本不一致），新版 partial 是正确阻塞，不是过度阻塞。
  - 调用数上升主要来自 open-obligation locator、audit re-audit 与重复副本/复合目标修复轮；成本仍在个例 $0.05–0.095。
- 下一步：模型服务恢复后用当前最终代码重跑 D01/D02/D11/D16（临时账本），对照 FL-D133 基线（D01 93/$0.0516、D02 56/$0.0636、D11 125/$0.0906、D16 61/$0.0554）；逐条解释 partial 原因；处理第二轮 Reviewer 残余；确认未降低 hard gate/delivery gate；再决定是否发布。
- 变更记录：2026-10-20 新增；同日补全量测试与首轮 Reviewer 修复记录。

## FL-D137 本机安装 cc-switch 管理 Codex 配置：glibc 版本不足需改用 musl 静态包（2026-10-21）

- 发现日期：2026-10-21（用户要求安装 ccswitch 用于设置 Codex 配置）。
- 环境事实（实测）：本机为无图形界面云服务器（`DISPLAY` 为空、无 `/tmp/.X11-unix`），OS `Alibaba Cloud Linux 3` / x86_64，glibc **2.32**；无 `node`/`npm`/`cargo`。外网访问经本机代理 `127.0.0.1:9981`（环境变量 `HTTP(S)_PROXY` 已设），`api.github.com` 因共享出口 IP 触发**限流 403**，但 `github.com` 网页与 release 下载正常。
- 问题与影响：
  1. 常见的 `farion1231/cc-switch` 是 Tauri **桌面 GUI**，本机无 X11/Wayland，装上也无法启动，不适合作为服务器侧 Codex 配置工具。
  2. `SaladDay/cc-switch-cli`（该 GUI 的 CLI fork，v5.11.2）`linux-x64` 包依赖 glibc ≥ 2.33，本机 2.32 报 `version 'GLIBC_2.33' not found`，二进制无法运行。
  3. GitHub API 限流会让按 API 取 release 资产的脚本返回空，改用 `releases/expanded_assets/<tag>` 网页列表获取资产名。
- 处理方法：
  - 下载 `cc-switch-cli-v5.11.2-linux-x64-musl.tar.gz`（static-pie，无 glibc 依赖），用 release 自带 `checksums.txt` 校验 sha256（`1d623ea8…53dc4bc`）后 `install -m 755` 到 `~/.local/bin/cc-switch`，`--version` 输出 `cc-switch 5.11.2`。
  - 首次运行在 `~/.cc-switch/` 生成 `cc-switch.db`、`settings.json`，并把现有 Codex 配置导入为 `default` 供应商（另有内置 `codex-official`）；**未改写** `~/.codex/config.toml`（安装前后内容一致）。
  - 未添加任何真实供应商、未写入任何 Key，未改动 `~/.codex/auth.json`。
- 状态与验证：**工具已安装并验证可运行**（`--app codex provider list/current` 正常）；Codex 供应商配置**尚未设置**，等待用户提供名称、Base URL、模型与 Key。
- 下一步：按用户给的供应商信息执行 `cc-switch --app codex provider add ...` 与 `provider switch`；切换前先备份 `~/.codex/config.toml`、`auth.json`；切换后重启 Codex 验证实际请求。
- 变更记录：2026-10-21 新增。

### FL-D137 追加：用户提供的 quanthatch 中转配置实测 401（2026-10-21）

- 用户提供的 `config.toml`：`model_provider = "OpenAI"` → `https://free.quanthatch.com/v1`，`wire_api = "responses"`，`requires_openai_auth = true`，`model/review_model = gpt-6.1-sol`，`model_catalog_url = .../v1/models`，`features.api_key_model_discovery/goals = true`。
- 实测结论：
  1. `codex doctor`：`config.toml parse ok`，默认 provider 为 `OpenAI`，端点可达；但 `disable_response_storage`、`network_access`、`windows_wsl_setup_acknowledged` 三项在 Codex 0.162.1 已被判为 **unrecognized / ignored**（3 条启动警告），属旧版或 Windows 专用键，无功能作用。
  2. 真实请求失败：`POST /v1/responses` → **401 `INVALID_API_KEY`**；用 `auth.json` 的 ChatGPT `access_token` 分别以 `Authorization: Bearer` 和 `x-api-key` 直接打 `GET /v1/models`，同样 401。说明该 relay **不接受本机 ChatGPT 登录态**，只接受它自己签发的 API Key；`requires_openai_auth = true` 在本机无法成立。
  3. 本机无 `OPENAI_API_KEY` / `CODEX_API_KEY` 环境变量，shell rc 中也无该域名相关配置，Key 无处可取。
  4. 附带噪声：`chatgpt.com/backend-api/ps/mcp` 连接失败导致 `rmcp` worker 反复重连（与主请求无关，但会刷 ERROR 日志）；`gpt-6.1-sol` 无内置模型元数据，提示会退化到 fallback。
- 处理方法：写入前已备份 `~/.codex/config.toml.bak-20261021-161752`；实测 401 后**立即回滚 live 配置**到备份，保证 Codex 仍可用 ChatGPT 登录态工作；把待启用配置暂存为 `~/.codex/config.quanthatch.toml`，等拿到 Key 再切换。
- 状态与验证：**阻塞在凭据**。配置结构已验证可加载，但端到端不可用；未向任何文档或日志写入 Key（本就没有 Key）。
- 下一步：① 向用户索取该 relay 的 API Key，改用 `requires_openai_auth = false` + `experimental_bearer_token`（或由 cc-switch 供应商写入 `experimental_bearer_token`）；② 或确认该 relay 是否本应支持 ChatGPT token（若是，则需排查账号/套餐或 relay 侧策略）；③ 拿到 Key 后先用 `GET /v1/models` 验 200，再跑一次最小 `codex exec`，最后决定是否长期启用。
- 变更记录：2026-10-21 追加。

### FL-D137 追加：quanthatch 接入 OpenCode 成功（2026-10-21）

- 用户提供该 relay 的 API Key 后，改为接入 **OpenCode**（原定 Codex 供应商配置暂缓）。
- 验证：`GET https://free.quanthatch.com/v1/models` 带 Bearer → **HTTP 200**，返回 59 个模型，含 `gpt-6.1-sol`、`gpt-6-sol`、`gpt-5.6-sol`、`deepseek-v4-flash`、`glm-5.2` 等。
- 处理方法（OpenCode V2 全局配置 `~/.config/opencode/opencode.json`）：
  - 新增 provider `quanthatch`，`package = "@opencode/ai/providers/openai-compatible"`，`settings.baseURL = https://free.quanthatch.com/v1`，`settings.apiKey = {file:~/.config/opencode/secrets/quanthatch.key}`，模型 `gpt-6.1-sol`。写法与同文件既有 `fundlex` provider 保持一致。
  - Key **不写入主配置**：单独存放 `~/.config/opencode/secrets/quanthatch.key`（目录 700、文件 600），通过 `{file:…}` 变量注入。
  - 修改前备份 `opencode.json.bak-20261021-162326`。
- 状态与验证：**已可用**。`opencode models` 列出 `quanthatch/gpt-6.1-sol`；`opencode run --model quanthatch/gpt-6.1-sol "Reply with exactly: OK"` 实际返回 `OK`，端到端打通。默认模型仍为 `fundlex/deepseek-v4.1-flash`，未改动。
- 备注：同一 Key 可复用于 Codex，但需改写 `requires_openai_auth = false` + `experimental_bearer_token`，并去掉 3 个已失效键；用户当前未要求在 Codex 侧启用。
- 变更记录：2026-10-21 追加。

### FL-D137 追加：OpenCode 扩到 12 个模型 + Codex 经 cc-switch 切换成功（2026-10-21）

- OpenCode：为 `quanthatch` provider 增加 12 个模型（`gpt-6.1-sol`/`gpt-6-sol`/`gpt-6`/`gpt-5.6-sol`/`gpt-5.5`/`gpt-5.4`/`gpt-5.3-codex-spark`/`gpt-5.2`/`deepseek-v4-flash`/`deepseek-v4-pro`/`glm-5.2`/`claude-sonnet-4-6`），`opencode models` 全部可列出；relay 实际共 59 个模型，其余未加入以免选择器过载。
- Codex：用 `cc-switch --app codex provider add --id quanthatch --api-format responses ...` 建供应商并 `use quanthatch`，cc-switch 生成的配置为 `model_provider = "custom"` + `requires_openai_auth = false` + `experimental_bearer_token`，**与手写方案一致**。真实 `codex exec` 返回 `OK`（234 tokens），`codex doctor` 解析正常、端点可达（`reachability mode: provider auth`）。
- 副作用与处理：
  1. 切到第三方供应商时 cc-switch **移除了 `~/.codex/auth.json`**，官方 ChatGPT 登录被暂存到 `~/.cc-switch/codex-login-stash.json`；`cc-switch --app codex use default` 可恢复。当前停留在 quanthatch，故 auth.json 不在位。
  2. cc-switch 每次切换都会重新写入 `disable_response_storage = true`，而 Codex 0.162.1 把它判为 unrecognized（每次启动 1 条警告）。`provider edit` 无脚本化参数、只能进 TUI 改，因此选择**在每次切换后 `sed` 删除该行**；已确认删除后 `codex doctor` 零警告且不影响请求。属**已知外观问题，未彻底根治**（根因在 cc-switch 模板）。
- 状态与验证：**OpenCode 与 Codex 两条链路均已真实打通**；备份 `~/.codex/config.toml.bak-quanthatch-*` 与原始 `config.toml.bak-20261021-161752` 保留。
- 变更记录：2026-10-21 追加。

## FL-D138 Operation Execution Closure：operation identity、final-plan ledger、全 obligation Claim Replay（2026-10-21）

- 发现日期：2026-10-21（用户要求基于 `refactor/recovery-architecture` 最新代码继续收口，不重设架构）。
- 问题与影响：真实 D01/D02/D11/D16 报告暴露了四层状态不一致：`operation TRUE` 可以没有 target；target 有但 sibling operation 未进入 plan；ledger 仍记 planned 但 final edit set 已丢弃该 component；Claim Replay 因 `edited_rules` gate 不检查未计划 operation；delete 已被 artifact 证明不存在时 Sweep 仍仅凭“没看到删除确认”阻塞。结果可能是 false complete，也可能是 sibling 消失后无人负责。
- 处理方法（本轮已实施）：
  - **Operation identity**：`obligations._target_covers_operation()` 不再把无 operation 的 location target 默认视为整条 rule 覆盖；`recall.assign_target_operations()` 统一给 `needs_edit` target 归属 operation，校验 operation 属于当前 rule、condition TRUE、并校验绑定 span 与 operation old_text/variant 有真实证据；无法归因时不进入 Planner，open/recovery 层再处理。
  - **Open recovery operation-first**：`targeting.targets_for_open_rules()` 改为 `covered_operations`/`seen_operations`，同一 rule 的 G05:0 不再覆盖 G05:2；新增 `_open_operation_candidates()`（P1 同 rule sibling site、P2 operation old_text、P3 variant/reference、P4 keyword bag/topic/site），append 规则（G01/G03/G16）按各自 site 语义找候选；G01/G03 的“直销/不收取/销售服务费”只作为最终 artifact 效果，不再要求出现在 source quote；G16 接受“每日计算/按月支付”等真实 payment site。
  - **Planner**：`PlannedEdit` 增加 `operation_keys`/`obligation_ids`；`_selected_operation_indices()` 只选择 target 归属 operation；G05 增加有界 `plan_g05_splice()`，支持“调低全部或者部分份额类别的赎回费率”，删除后仅做局部标点归一。
  - **Merge / ledger**：删除“同 rule 即 alternative”的旧逻辑；只有 `one_of_group` 相同才允许 alternative；同 rule 独立 operation 进入 conflict → Joint Compose；新增 `_reconcile_final_plan_ledger()`，从最终 edit set 与 component target ids 反推 planned/unresolved，冲突展开 `T1+T2` synthetic id；`RECALL_PLAN_COMPONENT_DROPPED` 不再被静默忽略。
  - **Claim Replay**：删除 `edited_rules` gate，检查所有 `applicability=TRUE` obligation；replace/append/delete 分别要求 artifact 新效果/旧效果消失/`VERIFIED_ABSENT`；delete residual 按 operation target/edit site 检查，避免把无关条款里的同短语误判；ONE_OF 只要求任一 source-present alternative 被处理，其余为 `ALTERNATIVE_NOT_SELECTED`；`verified` 改为“无 failure 且所有 required executable obligation 均 closure”。
  - **Projection**：`obligations.project()` 不再使用全局 `replayed`，必须读取 `replay["obligations"][obligation_id]` 的 own PASS；无记录时 `UNVERIFIED/UNRESOLVED`。
  - **Recovery / Sweep**：新增 `CLAIM_OPERATION_NOT_PLANNED`→TARGET、`CLAIM_PLANNED_EFFECT_MISSING`/`CLAIM_EXECUTION_EFFECT_MISSING`→EXECUTION、`RECOVERY_NO_PROGRESS`→EXECUTION；claim missing operation 创建 operation-specific target；每轮计算 target/plan/artifact/failure snapshot，连续无变化终止；Sweep finding 区分 `RESIDUAL_CONFIRMED` 与 `REMOVAL_UNCONFIRMED`，后者在有 obligation artifact proof 时 resolved；同 location 不同 rule/operation 不再按 location 去重；duplicate body/summary copy 增加 clone/repair。
  - **性能/并发**：`ModelGateway` 增加 state lock（calls/events/metrics），`RoleGateway.call()` 改用 `result.attempts == 0` 判断 checkpoint；audit 规则级 `ThreadPoolExecutor`，有效并发受 `ModelBudget.concurrency` 限制；audit 首次 full、后续 dirty-rule incremental；report 增加 `performance`（wall_ms、model_by_task、full/incremental audit、full sweep、inventory rerun、no-progress）。
- 新增测试：`tests/test_operation_execution_closure.py`（10 条）覆盖 location target 不覆盖整 rule、Planner 只执行 target operation、same-rule independent 不是 alternative、ONE_OF 仍为 alternative、final ledger reconciliation、无 edit applicable operation Claim FAIL、delete VERIFIED_ABSENT 接受 sweep removal unconfirmed、真实 residual 仍阻塞、no-progress snapshot、audit 并发/顺序。
- 最近真实子集（临时账本；均 `incomplete`，未发布生产）：
  - D01（D01f）：37 targets / 18 edits / 133 calls / $0.0806；Claim 仅 `G17 p760 RESIDUAL_OLD_TEXT`。之后又修 G17 span 阈值/duplicate repair，尚未重跑。
  - D02（D02b）：35 targets / 17 edits / 109 calls / $0.0831；Claim `G16 CLAIM_PLANNED_EFFECT_MISSING`、`G17 p823 RESIDUAL_OLD_TEXT`，另有 G05 satisfied-target residual 误报。之后修 G16 site/target recovery、scoped delete residual、duplicate repair，尚未重跑。
  - D02（D02c，提交 `21c7ae8` 后复跑）：35 targets / 18 edits / 84 calls / $0.0683 / 1464s；`incomplete`。首轮 `G16 CLAIM_PLANNED_EFFECT_MISSING`，missing-operation recovery 在 p1287 新增 R035 后 G16 artifact PASS；最终只剩 `p821/p1287 DUPLICATE_SITE_DIVERGED`，以及该 paragraph-level failure 被错误归因到 G15，导致 G15 自身 replay PASS 却在 obligation projection 中显示 UNRESOLVED。根因：p821 的旧 G16 目标是 `out_of_scope`，却仍被 `duplicate_copy_targets()` 当作“已存在”而抑制修复副本；`project()` 又把 `rule_id=""` 的 duplicate failure 按 location 匹配给所有同位置 obligation。已改为仅 active target 阻止 duplicate copy、复制时 supersede 旧 stale target，并只允许 replay failure 的 rule 标签包含该 obligation 的 rule 时影响它（merged edit 的 `G15+G16` 按成员匹配，`rule_id=""` 的 paragraph-integrity failure 仅由全局 delivery gate 阻塞）；新增 3 条单测。D02d 正在用该修复复跑，尚未完成，不能提前宣称通过。
  - D02（D02d，提交 `fee2cc5` 前复跑）：24 targets / 13 edits / 85 calls / $0.0669 / 1438s；`incomplete`。本次模型 scope/inventory 与 D02c 明显不同（window 变为 `S03_S04_S07_S16_S17_S20_S26`，少 11 个 target），因此不能与 D02c 做单点性能/完成率对比。暴露的新代码问题是：G16 由 open-obligation recovery 在 p821 新增，但该 target 在初次 duplicate-copy pass 之后才加入，未复制到 p1287，最终仍 `p821/p1287 DUPLICATE_SITE_DIVERGED`；已在 open targets 追加后再次执行 duplicate-copy 克隆（并 supersede stale target），D02e 正在复跑。其余同时出现的 G17 p1288 audit wrong、G14 p232 文本重复、G11 p228 重复句、G05 p138/G09 p227 sweep pending、G05:2 not planned、G09 unproven，均未宣称由本次修复解决。已定位其中两处为既有 target span/planner 问题而非本轮 duplicate 修改：G14 target quote 截断到“销售服务费”（缺尾部“率。”），`plan_fee_item_removal` 将它当作缺失项并用 `_rebuild` 拼出“基金销售服务费率…和销售服务费”；G11 target span 仅 12..31（`申购费用由投资人承担，不列入基金财产。`），整句模板替换后原 C 类句仍留在段尾形成重复。
  - D11：29 targets / 16 edits / 104 calls / $0.0936；Claim `G05:2 CLAIM_OPERATION_NOT_PLANNED`、`G16 missing`；同时 G22 audit `evidence_verified=false` 仍报 wrong。之后修 G05 unrelated-site scoped residual、G16 site，尚未重跑。
  - D16：40 targets / 20 edits / 78 calls / $0.0476；Claim `p822/p1306 DUPLICATE_SITE_DIVERGED`；G06 composite p431/p1169 仍 unresolved。之后加 duplicate repair，尚未重跑确认。
- 验证与状态：**代码实施基本完成；最终真实回归/Reviewer 未完成**。提交 `21c7ae8`、`fee2cc5` 已推送；`fee2cc5` 后全量 `pytest tests -q` 为 **942 passed / 6 skipped**（2026-10-21）。D02d 已完成但仍 `incomplete`，并暴露 open-target 晚加入导致 duplicate 未复制的新问题；修复后 D02e 正在复跑。未发布生产、未跑 514。模型服务在 2026-10-21 多次返回 HTTP 429；为完成真实调用临时加入 6–20s 节流和 30s 429 backoff，导致 wall time 明显高于基线（D11 单例约 47 分钟），不能把该 wall time 当作性能结论。
- 已知残余：G06 composite（D16 p431/p1169，按用户允许留专项）；G13/G14/G15/G17 真实业务残留；D11 G22 audit evidence unverified 但 wrong；`CLAIM_PLANNED_EFFECT_MISSING` 的 G16 恢复依赖 locator candidate；duplicate repair 的最终收敛待 D02d 验证；Sweep deterministic prefilter、rule artifact signature 复用、严格两次 Full Sweep 调度、5 类 Reviewer 尚未完成。
- 下一步：① 读取 D02e 与最新全量测试结果；② 若 duplicate 收敛，再评估 D01/D16（必要时 D11）；③ 补 REVIEW/性能表；④ 记录 D02e 结果并提交推送；⑤ 不发布生产、不跑 514。
- 变更记录：2026-10-21 新增。

## FL-D139 本机 systemd 服务状态与默认 API 端口可达性不一致（2026-10-21）

- 发现日期：2026-10-21。
- 问题与影响：本机 `systemctl is-active fundlex-recall-api fundlex-recall-worker` 返回 `active active`，但访问默认工作台/API 地址 `http://127.0.0.1:8000/api/health` 与 `/api/capabilities` 均返回 connection refused。当前不能据此确认工作台入口可用或完成运行态验收。
- 证据或复现线索：在 `/home/opencode/fundlex` 执行上述 systemd 状态检查及 `curl --max-time 5`；主机名 `iZf8zemhifedxdow1zefr0Z`，网卡地址为 `172.28.217.241`。本次检查未打印凭据，也未修改服务。
- 处理方法：暂登记为环境/入口核验问题；后续读取 FundLex 服务 unit 的实际监听地址、端口和日志，按部署配置核对反向代理或启动参数，再进行 `/api/health`、真实登录和用户端到端验证。
- 当前状态：入口误判已更正；原记录使用了错误的默认端口，不能作为服务故障证据。真实交付验收仍未由此完成。
- 验证结果：测试套件通过（939 passed、6 skipped）只证明代码测试，不证明当前服务端口可达。
- 下一步：核对 `fundlex-recall-api` unit、监听 socket 与部署环境变量；恢复可达后运行真实工作台路径并补充证据。
- 变更记录：2026-10-21 新增。

### FL-D139 更正（2026-10-21）

- `ACTIVE_HANDOFF.md` 已明确实际 API 为 `127.0.0.1:8010`，公网为 `https://fundlex.club`。匿名请求实际端口的 `/api/health` 返回 HTTP 401，证明监听及认证入口存在；8000 connection refused 是错误入口推断，并非服务故障。未更改服务，也未将 401 当作真实用户端到端验收。

## FL-D140 最终收口审计：认证、完整 Facts 与逐 operation/site 产物证明（2026-10-21）

- **2026-10-28 审计补充**：`evaluate_operation_effect()` 在无站点时可因guide字面旧文不存在返回 `PASS/VERIFIED_ABSENT`；G13“持续持有期少于7日→持有不足7日”、G17“主要用于→用于/使用范围→用途”的**未改合成原文**已复现这一局部结果。现有语义残留专用探针主要覆盖G06，不能用字面不存在证明所有规则语义已删除。**不是已证明所有整任务假complete**，上层可能有其他阻断；但与FL-D439真实景宁scope漏改共同表明：过严误拒和过松漏检并存，不能只删门禁。建议独立语义复核实际产物，并允许受控scope覆盖纠错。状态：局部离线复现、未修复。

- 发现日期：2026-10-21；任务起始 HEAD `00312e3bae7047c4ca04762d8f2739bd130894ed`，分支 `refactor/recovery-architecture`，起始工作区 clean。
- 问题与影响：runtime 没有 Certified Guide gate，内置 Guide 的历史 findings 裁定缺稳定身份和双 SHA；Primary Facts 只有类别值证据、没有完整集合证据；Applicability resolve 晚于目标发现；TRUE obligation 存在 target/scope absent→NOT_APPLICABLE 分支；Claim Replay 用全文替代 site 证据；merged component spans 串用；Audit 无证据负面意见仍触发恢复；planned-effect 缺失错误路由 TARGET；缺少冻结模型与阶段回放。
- 证据：逐层职责/输入输出/粒度/确定性/风险表见 `docs/RECOVERY_FINAL_AUDIT_20261021.md`；主要代码在 `guide.py`、`obligations.py`、`recall.py`、`recall_pipeline.py`、`generation/claim_replay.py`。内置实际为 22 rules/34 operations，旧统计 31；source SHA `b77be53c3439d785a9ffad0f09d8d03ba74f7722397576b999ae6f5dd6eef895`，旧文档自存 hash 与重新计算不一致。
- 处理方法：先认证 Guide/显式关系/TRUE invariant，再完整 Facts 与顺序，统一 OperationEffectEvaluator 和 root-cause recovery；新增 live/record/replay cassette 与 Stage Replay。保留全部 Validator、Claim Replay、residual 与 G02/G04 occurrence 边界。
- 当前状态：**实施中，尚未通过本轮回归，未部署**。已有 Guide/Projection/effects/Claim 接线改动；语法编译通过，初次针对性测试已暴露旧 fixture 和新证明接线不一致，待修复并分层验证。不得把这些改动当作最终完成。
- 验证与预算：本轮新 live 模型调用 0、费用 0；不跑 514、不反复 live E2E 调试。此前 942 passed 属旧版本，不作为当前验证。
- 下一步：完成 Primary class-set/依赖门、身份/站点证明及回放基础设施，运行针对性与全量离线回归；真实工作台最终交付仍须单独完成。
- 变更记录：2026-10-21 新增，保留 FL-D133/136/138 历史真实 incomplete 证据。

### FL-D140 实施补记（2026-10-21，进行中）

- 已完成一批针对性回归 146 passed（仅限当时 Guide/Facts/Claim/core/recovery 模块）；后续新改动仍在回归，不宣称整体完成。
- 新证据：Claim operation unit 仍有按文字和 single-operation fallback，merged component 可借父级 keys；Sweep repair 引用了前一 Audit loop 的 `reaudit_only`，无 Audit issues 时导致 UnboundLocalError。已去掉这些 fallback，并把 Claim Recovery 移至 Final Sweep 之前，待回归。
- 正在实施：Audit REVIEW_UNPROVEN 与确定性证明仲裁、相关站点签名、final executable edits 账本重算、四层 root-cause route、执行故障复用计划、Final Sweep 最多两轮。模型调用/新增费用仍 0，未部署。

### FL-D140 离线收口补记（2026-10-21，真实验收未完成）

- 新发现/影响：Audit missed-target 的 rule/location 去重会漏掉同址独立 operation；Sweep 按 rule 聚合 PASS 可跨 site 借证明；append 发现仍用全文政策和邻段关键词，正文已有政策可能掩盖摘要；Claim 用重叠 component spans 重建产物会重复应用；Joint Compose 同 rule 去重可能漏带后续独立 operation；residual repair 用第一个 delete index 和 location-level planned 判断可能修错 sibling。
- 已实施：去重和 residual repair 按 operation/site；Sweep 证明绑定 operation/obligation/site；append 仅在自身业务锚点检查政策并处理各 routed section；新增 `generation/atomic.py` 将独立 deterministic paragraph transforms 合成一个实际 edit、保留原 component 权限与 ledger；产物重建按 FINAL parent edit set；Joint Compose 汇总各 rule 全部显式 selected keys、无归因 fail closed；Claim Generation 用 `replan_sites` 保留未变 site 的最终计划，Execution 复用计划。
- Frozen Run/Stage Replay：model cassette 与 boundary/artifact 纳入 SHA manifest；六个阶段 CLI 支持修复 revision；无网络、无预算预留的回放测试通过，缺 cassette/输入/完整性失败均 fail closed。阶段为 facts/applicability/targets/obligations/plan/claim_replay；Facts 阶段为证据重认证，非重新请求事实模型。
- 测试迁移：旧 fixture 依赖 TRUE→NOT_APPLICABLE、无 site mock PASS、隐式 ONE_OF、章节末尾 append、文本推断 operation 等行为，已改为显式关系和实际 before/after site 证明；未修改业务规则数或评测 gold。新增 Scope correction、Audit 同址 sibling、duplicate/无关 delete residual、跨 site Sweep、atomic planning 和 dirty-site replan 回归。
- 验证：完整离线 **977 passed / 6 skipped / 2 warnings**（199.30s，`/tmp/fundlex-final-offline-3.txt`）；compileall/diff-check 通过。内置 Guide Gate 为 22 rules/34 operations，source/document SHA 见 ACTIVE_HANDOFF。
- 当前状态：**离线已验证，最终任务未完成、未提交/未部署**。本轮 live/费用 0；还需最终 diff/认证裁定审查、真实合同 Frozen run 与真实工作台交付，离线不能替代。保留所有历史 incomplete 分母，不能把现有通过数当业务 complete 证明。
- 下一步：在现有预算内做一次真实交付验收并录制；失败用 Frozen/Stage Replay 修复，禁止反复 live E2E 调试或提高预算/retry。

## FL-D141 Worker 停机时将正常退出误报为执行槽异常（2026-10-21）

- 发现日期：2026-10-21；本轮完整离线回归偶发复现。
- 问题与影响：`run_forever` 外层 wait 后、检查 consumer Future 之前，stop event 可被置位；consumer 正常返回却被报 `workflow slot stopped unexpectedly`，导致正常停机抛错。
- 证据/复现：`tests/test_tasks_api.py::test_multiple_tasks_really_execute_concurrently`；`/tmp/fundlex-final-offline-2.txt`（973 passed/1 failed/6 skipped），栈指向 `jobs.py` Future 完成判断。
- 处理方法：Future 正常完成后重新核对 stop event；stop 已置位即正常退出。Future 真异常仍通过 `future.result()` 抛出，不吞执行异常。
- 当前状态：**已实施并离线验证，未部署**；单独并发测试通过，随后完整回归 977 passed/6 skipped；适用当前未提交工作区。
- 下一步：随主分支工作统一发布后验证 systemd 正常停止；无新增模型调用/费用。

### FL-D140 推送前审查补记（2026-10-21）

- 发现剩余 Sweep rule-level satisfied 与 first-required-text 路径可独立关闭 finding；已移除，统一等待 operation/site artifact proof。静默 re-sweep 不再充当完成证据；Projection 未使用的旧 satisfaction helpers 一并删除。
- 针对性验证：`tests/test_recovery_final_invariants.py`、`tests/test_hard_fact_veto.py`、`tests/test_recall_pipeline.py` 合计 **77 passed / 22.59s**（`/tmp/fundlex-final-review-tests-2.txt`）；`git diff --check` 通过。中间误删 `_document_compact` 的回归已恢复；旧 `_finding_evidence` 为有意移除。审查补充后尚未重跑完整测试，不能沿用 977 项结果冒称当前全量已测。
- 用户随后明确只要求继续推送，故停止其他开发/真实验收/部署，将当前源码、测试与记录提交并推送。live 调用/费用仍为 0；真实工作台验收未完成，最终业务收口状态保持未验收。

## FL-D142 Exact-HEAD 最终验证发现运行录制/回放与 occurrence 缺陷（2026-10-21）

- 起始版本：`4f3229d901bda33332a8abee3d909b7550f07ff0`，`refactor/recovery-architecture`，fetch/checkout/pull 后 clean。全量离线实跑 976 passed / 0 failed / 6 skipped / 199.41s；compileall 通过。
- 实际证据：`docs/evidence/final-validation-20261021/`；D01 76 calls/$0.04448760，D02 3/$0.01303800，D11 3/$0.01213515，D16 5/$0.02031180；合计 87 calls/$0.08997255。四例均 `not_generated`，无最终 DOCX，artifact 安全指标为 UNVERIFIED，不能填写已验证的 0。原始四例 bundle 保留，不覆盖或用旧 SHA 产物补位。
- 已复现 root causes：record 相同完整请求再次 live 后遇不可覆写 cassette 冲突（D01）；失败响应在保存前抛出，D02/D11/D16 output truncation 无法 replay；无凭据 replay 在 role config 校验先失败；Inventory output truncation 未使用已有 bounded split；Stage Claim 缺 live target_rules/required_terms 参数、缺 boundary 仍宣称 replay；同段不同 G02 occurrence 被 location-level dedupe 隐藏，少改后 Claim 可 PASS（P0）；Audit missed-target 也缺 span identity；D16 `A 类/C 类` display labels 的 complete-set regex 漏识别 `A类`（false block）。独立 Architecture/Test/Recovery/Business 审查已分别确认。
- Recovery 额外 HIGH：Audit repair 分类后仍统一重跑 Inventory/Planner，Execution 不复用计划；Audit 无稳定状态 no-progress 阻断。
- 处理方法：仅针对上述 generic root causes 最小修复，新增回归；不改业务规则、Validator/Claim/safety，不加 retry/预算；修复后新 SHA 全量回归、独立新录制与零网络 Replay。当前状态：实施中，尚未验证修复、未部署，Gate FAIL；不运行 20/514。
- 预算：本轮预登记总上限 768 HTTP attempts/$2.40，每case 192/$0.60，后续必须扣除已用，不静默重置账本或增加额度。生产配置/数据库/账本未修改。
- 下一步：修复→完整离线→新 SHA四例record/replay→实际artifact独立复审→Gate；原始失败 cassette 缺失是历史证据缺口，不伪造补录。

### FL-D142 最小修复与离线复审补记（真实重录前）

- 已实施：Inventory按段有界拆分output-truncated窗口；record完整请求key与并发single-flight/首个outcome复用，失败错误码可零网络重放，legacy cassette只读兼容；replay role无需凭据；同段disjoint occurrences/同址sibling Audit identity分别保留；missed target按绑定span去重；A类display names正常集合验证；G05优先bounded token splice；G01/G03/G16拒绝在不完整跨段句中插入。
- Audit恢复最小接线：deterministic Claim证据逐operation判root cause；Execution复用final plan，Generation仅dirty site，Target才Inventory；真实fact/applicability变化使依赖计划失效；open targets保存在synthetic集合；稳定snapshot支持bound/unbound offsets，Audit无变化停止。没有更改Validator、业务适用性标准或预算。
- Stage必须有真实boundary；Claim与live使用相同components/required terms/target rules；返回recorded/replay HEAD与same_head，允许明确跨版本调试，不冒称exact-HEAD。多模型同一prompt的stage lookup仍可能ambiguous并fail closed（MEDIUM已知限制，当前四例单模型未触发）。
- 回归：中间完整989 passed/6 skipped（197.02s），之后又补Audit identity/None-offset/逐sibling rootcause与open-target持久化，故989不作为最终SHA证明。最终冻结后必须完整重跑。Architecture已确认原P0反例修复；Recovery复审95相关测试通过。实际artifact审查仍未完成。

### FL-D142 `22c15aa` 真实重录与独立产物复查（2026-10-21，未验收）

- 实际版本 `22c15aa4d8d736f2a2fc46a29bc3ed8611475f2f`；全量992 passed/0 failed/6 skipped/196.14s，compileall/diff-check通过。新bundle在 `docs/evidence/final-validation-20261021/revalidation-22c15aa/`，不覆盖4f3229d的失败录制。
- D01：53 calls/$0.04782000，24 TRUE，7 ARTIFACT_VERIFIED/6 ALREADY_SATISFIED/11 UNRESOLVED；D02：47/$0.04963680，24 TRUE，10/5/9；D11：51/$0.04332405，24 TRUE，11/5/8；D16：43/$0.04055925，24 TRUE，10/10/4。四例均incomplete且TRUE→NOT_APPLICABLE=0；这些中间proof数字存在下述缺陷，不能当业务成功指标。
- DOCX程序化对比：四例分别变更12/14/13/15段，final与final edit set重建文本0差异，final修订元素0。独立Business Reviewer核验接受redline=final、拒绝redline=original均0段落差异，未发现Writer丢失edit。
- 新可复现P0/HIGH：D16 G13跨段prefix p221被G12改写但p222续句仍在，Claim却VERIFIED_ABSENT；D01 G13/G15/G17与D02 G17存在真实旧文残留而operation proof PASS；G16只一份正文/摘要完成就PASS；D02 G11显式ONE_OF嵌套span在atomic阶段被重复应用；G22 fuzzy variant目标截断句尾，留下“配。”但该operation仍PASS。详见独立 `summaries/business-review.md`，原始产物保留。
- D16 G06 p431/p1169是通用业务规则调整条款，非不同份额类别不可互转禁令；G17 p822是G15支付机制，不是用途条款。两类模型错误attribution不应要求删除这些正确原文，正在增加通用site校验与回归。
- D16 full replay零HTTP但Inventory `MODEL_REPLAY_MISS`：`scope_map`用set建立dict，跨进程hash seed改变rule prompt顺序；已定位并改为Guide顺序，旧cassette保持不改，尚待最终SHA新录制/重放。
- 累计本轮真实HTTP 281次/$0.27131265；未增加每case192/$0.60总额度，下一轮必须继续扣除；未改生产配置/账本，未部署、未跑20/514。当前Gate仍FAIL。处理原则仍是最小通用修复、regression、全量重测、新SHA独立record/replay与四角色复审，不能通过降低proof或用旧SHA产物补位。

### FL-D142 后续最小修复与离线验证（2026-10-22，尚未冻结）

- 逐operation/site effect修复：真实source wording残留检测、跨段operation-reference continuation补证、精确原文正文/摘要duplicate独立site验证；同site合法新政策只接受已通过component证明的授权复用，不允许借另一site新文。对四例最终Claim boundary离线重算已挡住D01 G13/G15/G16/G17、D02 G16/G17、D16 G13 p222/G15 p822的虚假operation PASS；D11 G16无site仍OPEN。旧报告和artifact不重写为新结果。
- Planner最小修复：explicit ONE_OF重叠历史wording先交既有merge选择，避免atomic重复应用；whole-sentence fuzzy替换在同paragraph复核真实句界，最多延展12字符，无法证实则RECALL_VARIANT_CLAUSE_INCOMPLETE。D02冻结输入重算G11只保留1份policy、G22完整覆盖句尾；未更改G02/G04授权范围。
- site校验：composite也按绑定parts而非邻段检查业务site，阻止G06误绑通用业务规则；Sweep mapped candidate执行semantic site guard，未知wording保留有效业务锚点，Scope外候选仍需更强reference/variant证明。
- 独立Recovery发现：target重新编号会重置旧history预算；Sweep将Generation/Execution也统一Inventory且不留history。正在修复为stable operation/site预算、dirty-site/root-cause路由与Sweep history；无语义变化使用实际paragraph签名识别，避免DOCX ZIP时间戳触发多余工作。未增加任何retry/model预算。
- 真实negative Review quote即使可绑定，也不必然构成反证；正在按同operation/site已实例化授权新文、完整effect证明和hard findings仲裁。其它copy失败不能推翻本site确定性证明，但仍阻塞该obligation；真实残留和无证据缺口继续fail-closed。
- 工作区中间全量实跑1006 passed/0 failed/6 skipped/2 warnings/200.44s；此后仍有上述修复变更，所以该数字不作为最终SHA证明。compileall/diff-check通过；环境无node，未改frontend，`node --check frontend/app.js`未执行成功，须如实保留该工具缺失。最终冻结后完整重测。

### FL-D142 最终冻结前交叉复审（2026-10-22）

- Recovery最小修复已完成：budget按稳定operation/site/source span计数，target重新编号不重置；Sweep operation-first归因、按Target/Generation/Execution路由、复用dirty-site和统一history；语义artifact签名排除ZIP时间戳假进展。73项相关回归通过。
- 无证据Review仲裁修复完成：只使用同operation/site确定性PASS；授权新文被wrong_text引用时可标REVIEW_UNPROVEN，mixed旧文优先RESIDUAL_CONFIRMED；真实residual、其它copy失败、缺proof继续block。116项组合回归通过。
- Architecture交叉审查撤回G16 source anchor必须含新四组件的建议：旧支付机制是合法append锚点，四组件在artifact effect验证；也确认mixed paragraph旧文优先检查有效。源码编辑已停止，准备冻结。
- 全量首轮1018 passed/1 failed/6 skipped/202.43s；失败为Sweep proof_kind断言，实跑期间与最后issue guard修复交错。当前单测已通过，必须再完整重跑，不以局部结果替代。日志/tmp/fundlex-pytest-final-precommit.txt。

- 最终交叉审查新增CROSS-001（HIGH）：Compose replacement中的任意新句被当作授权fixed_text，可能把可验证语义矛盾意见错误标REVIEW_UNPROVEN。Architecture用通用G99原文/新文/矛盾追加句实际复现；由Test reviewer删除自授权fallback并补回归，修复后需再次完整测试及独立反例复审。中间完整1019 passed/6 skipped/199.89s不覆盖此末次修复。

- Architecture交叉复现CROSS-002（HIGH/P1）：Sweep已有target但matching Claim_OPERATION_NOT_PLANNED/UNPROVEN直接classify为TARGET，绕过已有claim root-cause helper，导致重复discovery。Recovery reviewer最小复用_claim_failure_context并补已有target/no-plan→GENERATION回归；其余stable retry identity、semantic no-progress交叉审查通过。
- 用户2026-10-22补充：本任务收口后继续多agent前后端/性能/准确完整修改，至少5份真实合同展示；先当前Gate，不以demo目标降低安全标准或改写失败分母。

### FL-D142 682e68a Exact-HEAD验证与新发现（2026-10-22）

- 冻结runtime682e68a5b3ef2a58feb77460af70afabdb314379，full1024passed/0failed/6skipped/200.45s，compileall/diff-check过。CROSS001/002独立反例复审关闭；新root final-validation-20261022。
- D01 record35HTTP/$0.02569695/158.46s not_generated：EDIT_OVERLAP_OR_ADJACENT阻断写出。零HTTP frozen replay复现；不是writer错误，replan_sites用可重编号target_id单遍扩dirty_ids，保留旧G08 T007@p226后又用新T010@p226追加相同edit，证据diagnostics/D01-overlap-root-cause.md。状态：已定位通用P1，待最小stable operation/site修复及回归。
- D02 record26/$0.02805225/127.21s incomplete，实际final/redline与FINAL_EDIT_SET零差异；独立Business新P0：absent占位heading p1036经claimed_operations进入Verified Site Set，多规则falseblock；G05:2/G06:0仅凭无关heading PASS VERIFIED_ABSENT。状态：真实复现，须排除absent/unattributed占位proof，TRUE无site继续OPEN，不改变业务适用性。
- D11 record25/$0.02588070/109.45s incomplete，D16同SHA record进行中。当前Gate FAIL，尚不可进入20-case或声称任何完美示范合同。

### FL-D142 接续修复（2026-10-22，未提交/未冻结）

- 发现于前序 agent 断线后的工作区：HEAD 仍为 `682e68a`，工作区有未提交修复与 `docs/evidence/final-validation-20261022/`。先保留全部证据，不重录、不覆盖旧 cassette。
- 已实施（未提交）：
  - Claim Replay 不再把 `state=absent`、`attribution_error` 或仅有 `claimed_operations` 的占位 target 当作 operation/site proof；这也移除 G05:2/G06 仅凭无关 heading 的 `VERIFIED_ABSENT` 假 PASS。
  - G02/G04 already-satisfied 判定按类别集合比较，接受真实合同常见的 `A类及D类`/`A类、D类` 分隔符差异；split 段落的份额类别定义允许由包含两类费用条款的报价证明站点，但仍拒绝只有 heading 的 p91 片段。
  - G05 effect/residual proof 绑定份额类别设置/费率调整站；持有人会议费用豁免条款（p138/p1109 等）不能证明 G05:2 已删除。
  - `replan_sites` 用稳定 operation/site 保留和重绑 old plan；保留 p758 G15 duplicate delete，修复 D01 `EDIT_OVERLAP_OR_ADJACENT` 与 `DUPLICATE_SITE_UNEDITED p758`。
  - G01/G03 split class-definition：段落没有句末标点时，若内容是完整 clause（末字非“的/和/与/及/、/：”），直接在段末追加并由 `append_separator` 补句号；只有真正的 open-ended heading 才转到下一段 continuation。D02 p93、D11 p91 的 G01 已能生成追加 edit。
  - G05 `absent` target 若在真实份额类别设置/费率调整段，允许用该段原文作为 site quote 证明独立 literal 已不存在；generic heading 仍拒绝，因此 D02 p1036/P0 不回归，D01 T007 p135 的 G05:2 可 VERIFIED_ABSENT。
  - G02/G04 split 段落重新分类：`assign_target_operations` 在 target 被前一轮标成 out_of_scope、但实际报价含完整费用组时清除误标；`plan_target` 在 selected class groups 全部已存在时标 satisfied，不再进入 occurrence ambiguity。
- 离线证据（当前工作区，未调用模型）：
  - D01 plan revision 2：19 edits、0 conflicts（G01 p92 追加、G15 p758/p1221 删除）；程序化 build/validate/generate 成功。用 live 等价的 assign+target mutation 重放时只剩 G06/G16 open，G01/G02/G05/G15 已关闭；冻结 stage 仍保留旧 target 状态，不能把 stage 的 G01/G02 失败当作新代码失败。
  - D02 claim replay failures 12→3（G02/G03/G04/G08/G09/G11/G12/G14/G22 false failure 转 PASS，G05:2 由真实 class-setup absent 证明；剩 G01/G06/G16）。
  - D11 claim replay：G02 分隔符 false failure 消失，G01 p91 现可生成追加 edit；claim 剩 G01/G06/G16（G05:2 已由 class-setup 证明）。
  - D16 claim replay：G05 会务条款 false failure 消失；剩 G01、G06、G12/G13、G16、G17 residual。
- 当前状态：**全量离线 1061 passed / 6 skipped / 2 warnings（219.40s）**；修复已提交到本地分支（未 push），Gate 仍 FAIL。D01 冻结 stage 的 target 旧状态导致 stage claim 仍报 G01/G02，live 等价模拟已验证关闭；BUS-FINAL-003（Audit 无证据负面意见）尚未处理。G06/G16 在四例中仍缺有效 site/target。未部署、未跑 20/514。
- 下一步：① 提交当前代码/测试/记录（未经用户要求不 push）；② 逐条处理 G06/G16 的 site/target 发现与 D16 G12/G13/G17 residual；③ 新 SHA 重新四例 record/replay 与独立业务复核；④ 之后再推进 ≥5 份真实合同，不降低 Gate。

### FL-D142 `ff4d749` exact-code revalidation（2026-10-22，未通过 20-case Gate）

- 验证代码：`ff4d7498b6c1aee72ba48686074d021fc7f84791`（纯证据 commit `387e334` 不计为 runtime）；证据根：`docs/evidence/final-validation-20261022/revalidation-ff4d7498/`，旧 `682e68a` bundle 保留未覆盖。runtime tree `7ad22dc0...`，Guide source/document SHA 与 index 一致。
- 离线：**1061 passed / 0 failed / 6 skipped / 2 warnings / 207.10s**；compileall、diff-check PASS。四例 live record 均为 exact code，artifact 均生成；calls 32/35/29/34，合计 130，cost $0.11742255，全部 incomplete，TRUE=24/例，TRUE→NOT_APPLICABLE=0。
- 四例零网络 full replay：0 HTTP/0 tokens/0 cost；`compare_frozen_replay` 14/14 项全 PASS，artifact 文本一致。D16 六 stage replay same_head=true、model_calls=0；base plan 与 revision 3 分别保存。
- 旧 finding：D02 absent 占位、D11 G02 分隔符、D16 G05 会务 site、D16 Audit B 类均关闭；D01 原 no-artifact/G08 overlap 已消失但 G17 same-operation duplicate 仍冲突，故 D01 overlap 只能标 PARTIAL/OPEN。
- 新/残留 BLOCKER：G16 四例全部未 append（G15 删除付款条款后留下空白）；D01/D16 G17 duplicate/subset target conflict；D02 G12/G13 joint edit 被 `replan_sites.bind_reference` 丢失（基线存在，属回归）；D11 G18 summary p1207 仍为旧文但 obligation 被 body p800 证明；D16 G12/G13 p221 仍 residual；G06 四例 absent literal 无 site proof；D01 G01/G02 split locator 与 B 类 false audit；D11 G05:2 false block。
- Safety：false delivery complete=0；obligation-level false completion=D11 G18；D02 audit false completion；unauthorized paragraph edit=0；cross-site/duplicate proof=D11 G18；unsupported VERIFIED_ABSENT=0；false Review block=D01 G02。
- 独立 Business/Architecture/Recovery/Test reviewer 均要求先修代码；Business BLOCK，Architecture 4 BLOCKER/6 HIGH，Recovery 4 BLOCKER/5 HIGH/8 MEDIUM，Test conditional（index/stage identity 已在证据中修正）。**Gate=DO_NOT_ENTER_20_CASE**。
- 本轮未改 runtime、未重录旧 SHA、未部署、未跑 20/514。下一步按 Architecture/Recovery 报告的最小通用修复顺序处理 G16/G17/G12-G13/G06/G01-G02，新增 regression、完整 pytest、新 code SHA 后重新四例 live + replay + 四 Reviewer 复审；不得把本 bundle 当验收通过。


## FL-D143 前后端交互与展示审查（2026-10-22）

- 发现日期：2026-10-22。范围为账号/任务/上传/筛选/指引/报告与修订审查界面；用户明确暂不检查目标发现与 DOCX 修改引擎。
- 问题与影响（已代码定位）：① 未进入 plan 的 needs_edit 目标也显示“已修改”，无产物的计划也可能当执行结果；组合编辑只显示首 component。② 修订节点配对使用字符串 `escaped+1`（1→11）导致插入正文不随拒绝状态变化，A/R 不更新复选框，点击插入节点不能对应清单，关闭面板后 review 仍存活；旧异步响应能覆盖新报告。③ 上传中的新建草稿可能被旧 POST/回执/seal 重新设置 recover、锁定任务名或错误跳转。④ 成功数使用 completed-failed，把 incomplete/正常排除计成成功；异常重复相加可能超过合同总数；统计把正常排除的 not_generated 当异常。⑤ “处理中”筛选发送 running，而 Worker 状态为 leased，结果漏项。⑥ 导入页提供评测/只读模式但实际始终提交 recall_first；平均秒数重复单位；总览只有选中任务运行时轮询，其他任务变化不更新。⑦ failed 指引不能显式重试；重复 parse 可产生多个任务且版本状态不立即更新，页面无法轮询。⑧ 登录过期消息被 showLogin 清空，身份切换后管理页/密码字段残留，hash 入口缺角色展示保护。
- 处理方法：已实施 UI 状态/请求隔离、真实交付口径与去重聚合、running→leased 兼容、单一真实模式、总览刷新、修订节点和控件同步、未交付文件如实标工作文件；failed 支持显式重试，活动解析任务复用原预算且新排队状态可见。改动只在工作区，不发布生产，不变更目标识别与写文件逻辑。
- 当前状态：**已修复并完成隔离验证；未部署生产**。
- 处理细节：`frontend/app.js` 增加请求 epoch/session 隔离，修订 ID 按 revision_ids 成对同步正文/复选框/键盘操作；未生成产物的计划显示“已规划/待修改”，工作文件显示为未完成；上传、报告、下载和账号操作忽略旧身份/旧草稿响应。`fundlex/tasks.py` 统一成功/异常去重口径并兼容 `leased` 筛选；`guide_store.py`/`api.py` 支持 failed 指引显式重试并复用活动解析任务；导入页只保留实际支持的合同修订模式。
- 验证/证据：主改动完成时离线全量 **1075 passed / 24 skipped / 2 warnings / 211.95s**；最后补充的前端修改之后，接口/认证/指引/修订 API 相关回归 **94 passed / 1 dependency deprecation warning / 30.48s**，中文字体环境下 Chromium 隔离 UI **29 passed / 38.03s**。覆盖 1440/768/390 宽度、统计和筛选、未执行条款展示、修订接受/拒绝和插入定位、旧异步响应、上传新草稿、失败指引重试、CSV/报告下载、登录过期和角色保护；`node --check frontend/app.js`、`compileall`、`git diff --check` 均通过。最新浏览器截图位于 `/tmp/fundlex-ui-browser-zh-verified/`，包含四个主页面以及报告/修订审查三种宽度，已经人工查看中文与布局；中文字体仅临时配置，不入库、不修改系统或产品字体。未调用真实模型、不作为项目最终端到端交付验收；生产行为未宣称修复。
- 2026-10-22 收尾补充（已实施并由上述 29 项浏览器回归验证）：正常排除的合同不再标红，进度条补齐排除分段；历史评测结果使用独立分段，不冒称正式交付完成；无终态结果时禁用整包下载；含例外交付保留下载但不显示“可直接使用”；展示服务端 `user_summary.issues`；评测合同隐藏不支持的正式修订审查；指引不可用时绑定提示/模式说明/提交禁用一致。生成选择版合同期间禁用控件，结束时恢复各自原有状态，避免误启用首份/末份导航。未修改目标发现与 DOCX 写入引擎。
- 下一步：发布前需按正常部署流程做一次生产静态资源与真实登录复验；本轮未部署、未修改查找目标和 DOCX 写入引擎。

## FL-D144 证据页只显示 G 编号、未说明修订版何处需要人工核对（2026-10-22）

- 发现日期：2026-10-22。用户在生产任务结果中看到 `G12/G18/G02/G04 · 该规则…`，但不知道内部规则编号含义；修订版中未修改的条款没有修订痕迹，用户无法定位核对。
- 原因：`fundlex/delivery.py` 的 `user_summary.issues` 只输出 `rule_id/location/business_reason`，未带指引组标题、章节、指引要求和原合同引文；前端证据页直接渲染内部编号。
- 处理：用户摘要增加 `title/section/requirement/quote/quote_exact_site/review_note`；前端“仍需人工核对”按“条款标题 + 章节 + 指引要求 + 原合同引文”展示，并明确说明未写入修订版的规则不会出现在修订痕迹中；技术编号/位置收进“技术信息（支持人员）”。对旧报告，前端从 `guide.groups`/`targets` 兼容推导标题和参考原文。
- 验证：`tests/test_delivery_summary.py`、`tests/test_tasks_api.py`、`tests/test_guide_api.py` 合计 41 passed；全量 **1075 passed / 35 skipped / 2 warnings / 207.89s**。浏览器测试需 `FUNDLEX_BROWSER_TESTS=1`，本机未运行；`node` 不在当前 PATH，未执行前端语法检查。
- 状态：代码已修复，待提交/部署后在生产任务上复验。未修改目标发现与 DOCX 写入引擎。

## FL-D145 D11 摘要副本漏改、D16 删除审计假阻断与陈旧 T3001（2026-10-22）

- 发现日期：2026-10-22，接续 `4090a22` 真实四例证据。D11 `G18` 正文 p800 已改、摘要 p1207 仍旧文，Claim 正确报 `CLAIM_OPERATION_NOT_PLANNED`；D16 G12/G13 的 24/24 obligation 已 PASS，但 G13 Audit 要求保留被 G12 授权替换掉的旧分配句，且 T3001 p219 仍以 `RECALL_TARGET_UNRESOLVED` 阻塞。
- 原因：① Claim 已证明 p1207 是必需出现点，但 recovery 只在“该 operation 没有任何 active target”时建 target，p800 的 active target 把它挡掉。② Audit 的负面意见只按字面 evidence 判断，没有把“同一业务站点已由另一 operation 授权并证明的新文本”与“本 delete operation 的真实残留”分开。③ Delivery 的 target 投影只排除 plan 状态，未在 obligation terminal PASS 后回收陈旧 candidate target。
- 处理（代码，未声称已 live 验证）：
  - `targeting.target_for_claim_site()`：对 Claim 已绑定的 occurrence 建 site-specific RepairTarget，要求真实 `operation_site_bound`，不扩大全文模糊 duplicate。
  - `recall.plan_edits(..., reuse_edits=...)`：同一 rule/operation/quote 的已验证替换可复用到 Claim 发现的副本；仅对非 append 生效，避免 append 复用产生 Claim 不可证明的 edit；`replan_sites` 从现有 plan 播种复用证据。
  - `recall_pipeline._delete_opinion_scope_unproven()` 与 `_site_record_quotes_expected_effect()`：delete 类 Audit 只有在本 operation 的 old_text 仍存在/被引用时才可阻塞；同站点 sibling 的授权新文不能当成本 operation 的漏删。仅在本 operation 有完整本地 effect proof 且无 artifact contradiction 时标 `REVIEW_UNPROVEN/OPERATION_SCOPED_DELETE_PROOF`。
  - missed-target 同样只有在引文属于同站点已证明的授权新效果时标 `EXPECTED_EFFECT_QUOTED_AS_MISSED`，否则继续阻塞。
  - `_reconcile_candidate_targets()`：target 的所有 operation 已有 terminal PASS 且不在 plan 中时标 `POST_PROOF_SUPERSEDED`/nonblocking；不再让 candidate target 高于已证明 obligation。
- 离线验证：
  - 全量 `pytest tests -q`：**1079 passed / 35 skipped / 2 warnings / 208.11s**；compileall、diff-check PASS。
  - 旧 cassette 零网络重放：D02 `complete`、D16 `complete`，均 0 HTTP/0 cost、Claim PASS、unresolved 0；D11 旧 cassette 已生成 p1207 `claim_site_reuse` edit 且 Claim PASS，但后续 sweep 上下文因新增站点变化，旧 cassette `MODEL_REPLAY_MISS`，只能作为引擎行为证据，不能当 exact-code 验收；必须新 live record。
  - 新增回归：`test_claim_site_repair_binds_a_non_exact_summary_copy`、`test_claim_site_reuse_plan_avoids_recomposing_the_summary_copy`、`test_delete_audit_opinion_must_quote_its_own_residual`、`test_post_proof_target_reconciliation_removes_stale_candidate`。
- 状态：代码已实施并通过离线/旧 cassette 行为验证；尚未提交、未部署、未用新 SHA 跑 D01/D02/D11/D16 live，也未做 Review DOCX 批注/高亮层。Gate 仍为 `DO_NOT_ENTER_20_CASE`。
- 下一步：提交新 runtime SHA → 建立新的、明确隔离的 validation budget（记录 calls/cost）→ 依次 live record D01/D02/D11/D16 → 四例零网络 replay/artifact review/独立复审 → 再评估 Gate。

### FL-D145 追加（D01 exact-code live 发现，2026-10-22）

- D01 在 `ebfe1de` live record：32 calls/$0.02791035，24 TRUE，14 artifact verified/8 already/2 unresolved，incomplete；G02 `R050` p91 报 occurrence ambiguous，Audit 又按虚构的 `A/B/C/D` 分组要求补 B 类，实际 certified facts 和合同 p91/p92 都是 A/C/D（A、D 收取申购费，C 收取销售服务费）。
- 根因：G02/G04 的 split definition 第一段是“基金份额类别…”标题，第二段才是 A/D、C 的收费分组。`target_site_ok` 只接受标题词，导致真实 p92 目标被标 `TARGET_SOURCE_MISMATCH`，recovery 反而去 p91 标题并报 ambiguous；Audit 的 B 类说法与 certified facts 冲突。
- 处理：`target_site_ok` 对 G02/G04 接受“至少两个类别标签 + 申购/认购费 + 销售服务费”的 split 费用段；仍拒绝无两类费用概念的普通费用句。新增回归 `test_g02_split_fee_group_paragraph_is_a_real_site`。certified facts 与 Audit 冲突的仲裁沿用现有 `_quote_confirms_class_facts`，待 D01 重跑确认。
- 状态：代码在本地继续修复，尚未提交/重跑；D01 仍未通过 Gate。

### FL-D145 追加 2（D01 第二次 exact-code 尝试）

- `b18a5c9` D01 live：36 calls/$0.0307719，incomplete；G02 已关闭，但 G04:1 因 satisfied 目标只带 G04:0 而缺 target；G15/G16 p758 与 p1221 相同副本在一次 recovery replan 后变成 `RECALL_PLAN_REFERENCE_UNBOUND`，只剩 p1221 联合编辑；G18 sweep 又把标题 p781 当业务站点。
- 处理：① `assign_target_operations` 对 satisfied 的 G02/G04 split 目标也按真实费用组扩展 operation keys；② `_plan_and_generate` 在 replan 出现 unbound 且当前仍有 live target 时回退到从全部 targets 重新 plan，避免丢失 p758 副本；③ `_TARGET_ANCHORS` 增加 G18 业务锚点，标题 p781 不再进入 sweep；④ 新增 G18 标题反例回归。
- 旧 cassette 重放（b18a5c9 cassette，新代码）已生成 p758 与 p1221 两份 G15+G16 联合编辑，T002 p130 operations 为 G04:0/G04:1；随后 Audit 上下文变化导致 `MODEL_REPLAY_MISS`，符合预期，需新 live record。
- 状态：尚未提交/重跑；D01 未通过。

### FL-D145 追加 3（D01 第三次 exact-code 尝试）

- `b6abf98` D01 live：29 calls/$0.02299395，24 TRUE 全部 terminal（14 VERIFIED/10 ALREADY/0 OPEN），Claim PASS，仅剩 1 条 sweep：G04 p130 被误报 wrong_text。实际 p130 已是 A/D 收费组 + C 服务费组；sweep 引文与 instantiated `A类、D类` 仅差“及/、”分隔符。
- 处理：`_quote_is_expected_effect` 对 G02/G04 使用 certified class-group 等价比对（`_class_group_equivalent`），不再把 `A类及D类` 误判为残留；新增正/反例回归，反例仍拒绝虚构 B 类。
- 状态：代码已修复，待提交后第四次 D01 live 确认。

### FL-D145 追加 4（D01 第三次证据的旧 cassette 行为重放）

- 新代码（未提交时）对 `80623e1` D01 frozen cassette 零网络重放：`delivery=complete`、errors=[]；p758 与 p1221 均生成相同的 `G15+G16 merged_delete_append`，G15 的 p758 副本通过 late duplicate-copy closure 被纳入。说明上一轮 D01 的 p758/p1221 分歧和 G04/G08/G11/G12/G13 sweep 误报已关闭。
- 仍不能替代 exact-code live：旧 cassette 的 audit/sweep 上下文来自旧代码；必须在新 SHA 重新 record。

### FL-D145 追加 5（D01 第四次 exact-code 尝试）

- `7bb9905` D01 live：32 calls/$0.0282417，24 TRUE 全部 terminal，Claim PASS，仅剩 1 条 sweep：G18 p1191 的最终类替换文本被误报 wrong_text；实际文本为 `A类、D类…和C类…费用收取不同`，是 G18 按 certified facts 加入 D 类后的正确结果。
- 处理：`_quote_is_expected_effect` 对 G18/G02/G04/G08/G11 增加“最终授权 edit replacement 的精确/包含匹配”，且仍要求本地 operation proof PASS；通用 G99 反例继续失败，避免把 compose contradiction 自我授权。新增 G18 D 类最终替换回归。
- 状态：待提交后再次 D01 live；若通过，再同 SHA 跑 D02/D11/D16。

### FL-D145 追加 6（D16 p222 重复整段，关键）

- `cf00116` 四例 live 均报 complete，D11 p1207 已改；但实际打开 D16 `final.docx` 发现 p222 被写成与 p221 相同的完整新条款，而不是删除 p222 的 7 日条款残片。Claim 却把 p222 判为 `VERIFIED_ABSENT`，属于 false PASS。
- 根因：G12/G13 两段复合目标在 p221 已合并为 `replace_covers_delete`，p222 只剩两个空 replacement 的删除；overlap resolver 又调用 Joint Compose，按 G12 政策文本重写了 p222，导致整段重复。
- 处理：overlap resolver 先检测所有冲突 edit 的 replacement 均为空，合并为单个 `joint_delete`（replacement=""），不再调用模型；新增回归 `test_overlapping_composite_deletes_merge_as_joint_delete`。
- 旧 cassette 行为：D16 plan 现在为 p221 `replace_covers_delete` + p222 `joint_delete ""`；需新 live 验证 p222 实际为空。
- 状态：关键修复，尚未提交；此前四例 complete 不能作为最终验收。

### FL-D145 追加 7（D16 p222 claim 与 D11 barrier）

- 修复 p222 joint_delete 后，Claim 又要求 G12:1 在 p222 出现完整 new_text，导致 `CLAIM_OPERATION_EFFECT_MISSING`；同时 D11 p129 G03+G05 合并编辑 end=177 超出唯一 TextSegment 0..176，写文件报 `EDIT_CROSSES_BARRIER`。
- 处理：① `_own_effect_errors`/`_joint_operation_effects` 对 composite tail（`composite_tail` 或 `part_index>0`）只要求删除旧文，不要求重复插入 new_text；② final merge 和 build 前把“仅尾随空白”超出的 end 夹到当前 TextSegment；③ ONE_OF 历史措辞替代项若其 old_text 在全文确实不存在且另一替代项已 PASS，标 `NOT_REQUIRED/one_of_alternative_absent`，不伪造站点。
- 旧 cassette D16 重放：delivery complete、Claim failures 0、unresolved 0，final p221 为正确新条款、p222 为空白；D11 plan 13 edits 无 barrier。需新 SHA live 四例复验。

### FL-D145 追加 8（D01 第四次 exact-code 后回退，已定位三处）

- `6fec3fc` D01 又出现 G05 p135 `RECALL_EDIT_CONTENT_UNVERIFIED`、G15 p758/p1221 diverge；D11 p129 barrier；D16 p222 已空但 G12:0/ONE_OF 未闭合。
- 处理：
  1. `_replay_fragments` 对 `g05_splice` 做句内终端词替换，不插入句号，修复 G05 content check。
  2. 在 `_plan_and_generate` 规划前再做一次最终 exact-copy closure，捕获 survey/rebind 晚到源 target（D01 p758）。
  3. D11 p129 等合并编辑仅在尾随空白超出 TextSegment 时夹到 segment end；D16 p222 composite tail 不要求重复 new_text，全部空 overlap 合并为 `joint_delete`。
  4. ONE_OF 历史替代项 old_text 全文确实不存在且另一项 PASS 时标 `NOT_REQUIRED`，不伪造站点。
- 旧 cassette 行为：D01 plan 已同时含 p135 G05、p758/p1221 两份 G15+G16；D16 frozen replay complete 且 p222 空；D11 stage plan 13 edits 无 barrier。需新 SHA 四例 live 复验。

### FL-D145 追加 9（D11 p129 content check 与 D01 G05/G15）

- `14bff5a` D11 p129 的 G03+G05 atomic 段因 target end 177 越过 TextSegment 176 被 content check 拒绝；同时 D01 G05 `g05_splice` 的 fragment replay 多插入句号，G15 p758 因晚到 survey target 未复制。
- 处理：G05 splice replay 不插句号；planning 前再做最终 exact-copy closure；尾随空白夹到 segment，并允许 atomic content check 忽略同段尾随空白；D16 composite tail/ONE_OF 修复保留。
- 当前离线：D11 stage plan 14 edits content check 全通过；D16 frozen replay complete p222 空；D01 plan p135 与 p758/p1221 均正确。需新 SHA 四例 live 复验。

### FL-D145 追加 10（Independent Reviewer 第一轮：BLOCKER/HIGH 修复）

- Reviewer 拒绝 `621d2c1` 的四项问题已处理：
  - D16 G13 `ALREADY_SATISFIED` 原为无站点 `document_literal_absent`；现在当目标已被 proof 后淘汰时，从实际 plan edit/site 重新绑定 G13 到 p221，Claim 记录 `sites:["p221"]` 和站点前后引文，不再只扫描原文。
  - Sweep `_sibling_expected_effect` 不再在 `residual_old_text` 分类之前放行，也不再接受“quote 包含 replacement 的超集”；旧文+新文引文保持 `RESIDUAL_CONFIRMED`。
  - `NOT_REQUIRED` ONE_OF 证据增加 `searched_literals/match_count/document_sha256`，`effect_proof_passed` 只接受可复核的 `alternative_wording_absent` 或 `certified_noop_branch`。
  - Claim 新增同段重复完整 new_text 检测 `CLAIM_DUPLICATE_EFFECT`，拒绝 p221 这类 R+R 双重插入。
  - API 完成计数排除 `out_of_scope` 的陈旧 target，不再在 complete 合同上显示“未完成 1”；report.md 每规则计数改读最终 target ledger，不再用 discovery coverage 冒充最终状态。
  - `tools/compare_frozen_replay.py` 按 report artifacts 映射选择 final/working_final，修复 complete 合同 `artifact_text:false` 的工具假阴性；四例旧 root 比较已 14/14 通过。
- 尚未提交/重跑四例；Gate 仍不能宣称通过。

### FL-D145 追加 11（66d9dc4 D16 live overlap 回归）

- `66d9dc4` D16 live 因 G13 p222 单段 target 与 Y007 复合 target 同时存在，planner 报 `RECALL_EDIT_OVERLAP`，尽管同版本 isolated plan 可干净合并。
- 处理：`dedupe_operation_targets` 在规划前把“同一 rule/operation、仅覆盖复合 target 某一段”的非复合 target 标为 `SUBSET_OF_COMPOSITE_TARGET`，不再与完整复合 target 竞争。D16 stage plan 复算为 p221 `G12:0+G13:0 replace_covers_delete`、p222 `joint_delete ""`、conflicts 0。
- 状态：待提交后再次四例 live。

### FL-D146 多通道召回、操作级覆盖与语义删除变体（2026-10-23，本轮）

- 发现与影响：真实 `funds_word` 合同中同一规则会在正文/摘要重复出现、跨段出现或采用措辞变体。旧 `find_old_text_all` 在首次 exact/split 命中后提前返回，且 fuzzy 仅在无 exact 命中时运行；这会漏掉第二处副本或同义写法。独立扫描还发现 514 份合同中至少 74 份存在 G06 的“暂不允许进行相互转换”等语义变体，canonical old_text 不出现时旧 absence proof 会误报 `VERIFIED_ABSENT`，形成 false completion。
- 证据：Recall Agent 对真实“广发品质回报”合同（1410 段）复现 G15 支付条款正文/摘要四处命中（含跨段 `p806`、`p807|p808`、`p1262`、`p1263|p1264`），G17 两处跨段副本与 G22 两处副本；Red Team 在“广发核心优选六个月持有期混合型基金中基金（FOF）”真实 DOCX 的 `p262` 复现 G06 变体。确定性补扫生成两个 G06 目标（`p130` canonical 变体、`p262` “暂不允许”变体）。
- 处理：`find_old_text_all` 现在保留 exact、split 与不重叠 fuzzy 命中，按当前段落计算 n-gram，并把 raw fuzzy span 正确映射到 compact offsets；`survey_targets` 对 mixed rule 的适用 delete operation 独立运行 keyword-bag fallback，并加入计提/计算、按月/次月、支付/划付等窄业务变体；`target_site_ok`/`ensure_delete_targets` 增加 G06 语义探针，保留真实位置和 operation identity。`evaluate_operation_effect` 在无 verified site 时先检查语义删除探针，命中则保持 OPEN/UNPROVEN，不产生 document-wide absence proof。新增 exact+variant、跨段、G06 语义变体和 keyword fallback 回归。
- 操作级覆盖：`CoverageEntry` obligation 路径现在保留 artifact evidence/site 与 operation key，artifact/site 同址去重，targetless unresolved finding 不再重复计数；报告 `operation_coverage` 输出完整 entries 与 counts。新增覆盖回归，验证同一 site 的 artifact+target 只计一次、open operation 不重复。
- 独立复核：`_run_audit`/`_audit_issues` 现在也审查 `satisfied` target，避免 inventory 误判 satisfied 后没有独立模型入口；新增 false-closure 回归。当前仍未建立独立 all-applicable-operation × 全文 omission-review 产物，作为后续 HIGH 保留。
- 修改失败策略：`generation.router` 增加失败分类与差异化 escalation helper（source/range/protected/requirement/duplicate/template/splice/compose/writeback/artifact），保证后续调用可按 DELETE→EXACT→NORMALIZED→FUZZY→TEMPLATE→SPLICE→COMPOSE 选择不同策略；当前 helper 尚未完全接入主 recovery 调用链，不能宣称 retry 闭环已完成。
- 验证：本轮 targeted 回归通过（召回、pipeline、coverage、generation、artifact regression 合计 145+ 项；后续全量回归待完成）。真实 DOCX 已实际生成 `/tmp/fundlex-real-e2e/g06-variant.final.docx` 与 `.redline.docx`，重新读取 `p262` 确认变体句已删除，段落数保持 1447，`unzip -t` 通过；该文件为确定性写入验收，不含真实模型调用。
- 当前状态：代码在工作区未提交、未部署线上；真实模型配置因本机 `/usr/bin/sudo` setuid/owner 异常无法安全读取，故本轮未新增 live model record，不能把离线及确定性 DOCX 验证冒称完整用户 E2E。下一步为修复/恢复安全配置读取后，用新 SHA 运行真实模型合同链路，补独立 omission review，完成全量回归并重新检查四例/至少五份真实合同。

## FL-D147 SSH 窗口关闭后 Codex 当前执行被标为 interrupted（2026-10-23）

- 发现日期：2026-10-23。用户明确反馈：通过 SSH 在云服务器命令行使用 Codex，关闭窗口后正在执行的任务变为 `interrupted` 并停止；同样使用 OpenCode 时未遇到该现象。问题是当前执行未持续运行，不只是聊天历史恢复。
- 影响与原因边界：部署在服务器上并不自动保证交互任务在客户端退出后继续运行。终端关闭可能导致 CLI 退出、连接断开或当前 turn 取消；本轮没有主动断开用户 SSH，未复现并区分具体触发机制，亦未确认 OpenCode 当时的后台运行方式。
- 证据与验证：本机 `codex --version` 为 `codex-cli 0.162.1`；`codex --help` 支持 `resume`、共享后台 app-server 及 `--no-daemon`，因此不能直接断言 Codex 没有后台服务。实际读取的 OpenAI 官方 CLI 文档将 `codex resume` 描述为重新打开已保存聊天（https://developers.openai.com/codex/cli/），这不等同于保证已取消的执行自动继续。工具进程视图处于隔离环境，不能据此认定宿主 SSH 的完整进程关系。
- 处理建议（未实施）：在独立的 `tmux` 会话内启动 Codex，使 SSH 断开时交互客户端及其终端保持运行；重新连接后 attach 同一会话。已经 `interrupted` 的执行需要恢复聊天并明确继续任务；不能把 `resume --last` 描述为撤销中断或自动保持执行。
- 处理方法（2026-10-23 已实施）：安装系统 `tmux 2.7`；新增 `tools/ops/codex_persistent.sh` 与安装器，并在 `~/.bashrc` 注入用户级 `codex()` 包装函数。交互式 Codex 自动进入按工作目录命名的独立 tmux server/session；显式使用 `--no-daemon`（本机为 standalone CLI，缺少完整 app-server package），并按用户“所有权限”要求加入 `--dangerously-bypass-approvals-and-sandbox`。非交互命令、管理子命令和已在 tmux 内的调用保持直接执行。
- 验证：配置写入前备份 `~/.codex/config.toml.bak-full-access-20261023-110532-742946`；当前 `config.toml` 解析成功，`approval_policy=never`、`default_permissions=:danger-full-access`，`codex doctor --json` 报 `approval policy=Never`、`filesystem sandbox=unrestricted`。专用 PTY 断线测试通过：终端 master 关闭后工作完成、tmux session 保持 detached、重新连接为同一进程（`pty_hangup=passed`、`work_completed_after_disconnect=true`、`reattached_same_process=true`）。真实 Codex `--no-daemon` 客户端也在 tmux 中保持运行；同一聊天的验证副本已关闭，避免并行打开。
- 当前状态与下一步：本机持久入口与用户级完整访问设置已实施；之后新 SSH shell 读取 `.bashrc` 后在相同目录输入 `codex`，自动创建或接回同一持久会话；也可用 `Ctrl-b` 后 `d` 主动分离。真实 Codex 测试客户端曾保持 detached 运行并识别出旧客户端持有当前聊天，显示“open in another app”；旧客户端结束后才可在新客户端恢复同一聊天，不能强抢写锁或把另一客户端仍在工作写成权限错误。11:22 已关闭 `client-diagnosis` 验证副本，同步最终启动器并复测 PTY 断线/同进程重连全部通过；临时测试 server 在 finally 中清理。已中断 turn 需要重新发出继续任务；本轮未进行真实模型调用，也未宣称已经断开用户实际 SSH 做过验证。

## FL-D148 用户要求 Codex 完整权限，但旧会话仍使用启动时沙箱（2026-10-23）

- 发现日期与影响：2026-10-23。用户明确要求“给你所有的权限”；本机 sudo 授权与 Codex 沙箱为两层，旧配置未指定默认 permissions，工具被 workspace-write、网络和受保护路径限制，导致写用户目录、创建 tmux socket及联网操作逐次请求执行权限。沙箱内 `/usr/bin/sudo` 显示 nobody owner 是隔离视图证据，不能据此断言宿主 sudo 安装损坏。
- 处理方法（已实施）：仅修改用户级 `~/.codex/config.toml` 两个顶层字段为 `approval_policy="never"`、`default_permissions=":danger-full-access"`，不与旧 `sandbox_mode` 混用；完整原件备份在同目录 `config.toml.bak-full-access-20261023-110532-742946`，权限 600。修改脚本对其余 TOML 数据做相等校验，未输出模型凭据。持久交互启动器同时显式传入 full-access flag，确保恢复聊天时采用用户授权的启动设置。
- 实际验证：`codex doctor --json` 的 `config.load` 为 ok，`sandbox.helpers` 显示 approval policy `Never`、filesystem sandbox `unrestricted`，配置文件权限 600。官方依据为 https://developers.openai.com/codex/permissions 与 https://developers.openai.com/codex/config-file/config-reference ，均实际读取。本轮 doctor 总体 warning 来自更新探测 HTTP 403，与权限配置无关；未为此更新 CLI。
- 状态与范围：用户默认配置已生效并由新 CLI invocation 验证；现有聊天不能通过改磁盘配置自行替换本轮 developer 注入的沙箱或审批策略，需要重新启动/恢复客户端会话。系统/组织强制限制仍不能由用户配置覆盖。项目凭据保护、部署边界和任务授权范围仍按 AGENTS.md 与用户任务执行。

## FL-D149 合同比较结果 JSON 需要长字段且上传必须完整校验（2026-10-23）

- 问题与影响：compare 结果包含每个差异的左右 span、文字和诊断，长度随合同变化。当前 Database 的 MySQL 兼容转换会把普通 `TEXT` 转为 `VARCHAR(255)`；若照旧表声明，会截断或拒绝长结果。另一个风险是只检查 ZIP 中是否存在 `document.xml` 会把伪 DOCX 入队，之后 Worker 才失败。
- 证据：`fundlex/db.py` 的 `_translate_text_columns` 对未列入长字段集合的 TEXT 使用 VARCHAR(255)；实际 compare API 结果包含 `left_spans/right_spans`，恶意或不完整 ZIP 可被基础成员检查误接受。
- 处理方法：`compare_pairs.result_json` 明确使用 `LONGTEXT`（SQLite 接受该声明，MySQL 保持长文本）；上传接口先调用现有 `_validate_upload`，再调用 compare parser 的完整 OOXML 包校验，失败返回 `COMPARE_INVALID_DOCX`/`COMPARE_UPLOAD_REJECTED`，不创建对象。结果对象写入后保存 SHA-256、大小和对象 key，查看前复核数据库、对象和源文件哈希。
- 状态与验证：已实施；`tests/test_compare_api.py`、`tests/test_compare_auth.py`、`tests/test_compare_batch.py` 覆盖伪 DOCX、恶意文本、跨用户访问、批量 pair 隔离和结果查看；本地 compare 全套 **32 passed**。真实 MySQL 服务变量未配置，MySQL 集成仍为 skip，故跨后端实际连接待验证。
- 下一步：在可用的 MySQL 测试库运行 compare schema/长结果和并发 claim 验证；继续保留结果 JSON 完整性检查。

## FL-D150 公开合同评测语料含已有 Word 修订痕迹（2026-10-23）

- 问题与影响：本次 compare 业务输入前提是不含已有审阅修订。公开 `funds_word` 库中至少存在带 `w:ins`/`w:del` 的文件；若把它们直接当作 identity 或 mutation base，会把输入前提问题误计为算法漏检或误报。
- 证据：`tools/evaluation/compare_fixture_builder.py` 的 `_supported_source` 对 `w:ins`、`w:del`、`w:moveFrom`、`w:moveTo` 做独立筛选；compare parser 对同类结构抛出 `EXISTING_REVISION_UNSUPPORTED`。首次 20 份均匀抽样语料发现至少一份不符合输入前提。
- 处理方法：语料构建只从无已有修订的源合同中选择，原件只读复制到临时 corpus；gold 由独立 OOXML 提取器冻结 block/offset/hash，不能修改原合同制造通过。含修订源文件应在上传时拒绝，并显示明确错误。
- 状态与验证：已实施筛选和 parser 拒绝；算法专项 **24 passed**，compare API/store 全套 **32 passed**。新过滤后的 20 份 dev/holdout mutation 评测正在生成，旧未过滤 corpus 不作为硬门证据。
- 下一步：完成过滤后 14 dev/6 holdout 的 recall、identity、modify、symmetry、determinism 和性能报告；若源合同不足 20 份，记录真实数量和外部阻塞。

## FL-D151 Compare parser 把 DrawingML moveTo 误认成已有修订（2026-10-23）

- 问题与影响：首次修订痕迹检测按 XML localname 匹配 `moveTo`，真实 DOCX 中的 DrawingML 路径元素 `a:moveTo` 被误判为 Word `w:moveTo` 修订，20-base corpus 的 B00 无法解析。此问题会拒绝本来符合 compare 输入前提的普通图形合同。
- 证据：`tests/test_compare_corpus.py::test_drawingml_move_to_is_not_word_revision` 复现；`fundlex/compare/parser.py` 原使用 `etree.QName(node).localname in REVISION_TAGS`。DrawingML 与 WordprocessingML 名称空间不同。
- 处理方法：修订检测使用 `Q("ins")/Q("del")/Q("moveFrom")/Q("moveTo")` 完整 QName。图形仍按不支持的可见内容产生 coverage 警告，不以已有修订错误代替。
- 状态与验证：已修复；`.venv/bin/python -m pytest tests/test_compare_*.py -q` **34 passed / 1 warning / 3.87s**。20 个真实 base、386 个 mutation 已冻结，gold SHA-256=`67b5b418492358aabcc3b9cfd04ad43889c69a474b9d5ec501b18d00570d2d9a`，dev 正在评测。

## FL-D152 Compare 对齐长合同耗时与重复/合并段落召回（2026-10-23）

- 问题与影响：局部 DP 对每个候选组重复运行 `SequenceMatcher`，真实长合同单 pair 曾约 1.6—6.5 秒；重复段落或删除段落相邻时，模糊 1:N/N:1 配对可能吞掉实际插入/删除，造成高召回评测漏检。
- 证据：冻结真实语料 B00/B05 的 duplicate/paragraph_delete 曾出现 0/1 覆盖；B07 merge 结构 fixture 的 gold 初始标记为零差异但可见字符流实际变化。复现路径为 `/tmp/fundlex-compare-corpus-v4/gold-sdt-v5.json` 与 compare evaluator 输出。
- 处理方法：`align._sim` 增加文本级缓存和长文本边界/长度快速评分；多块模糊组若左右存在相同完整 block，禁止将其合并，保留精确 block 与显式 insert/delete；gold extractor 仅在左右可见字符流（连续空白归一）确实相同才接受 structural zero-diff。
- 状态与验证：已实施。B00/B05/B07 反例复测通过；20 bases × 386 mutations（14 dev/6 holdout）重新评分：dev **272/272** mutation targets covered，identity false positives **0/14** zero-diff fixtures；holdout **114/114**，identity false positives **0/6**。modify classification dev **223/225=99.11%**，holdout **100%**。硬门 identity **20/20**、symmetry **20/20**、determinism **20/20**。dev median **0.620s**, P95 **0.897s**, max **2.096s**；holdout median **0.653s**, P95 **0.942s**, max **2.759s**。
- 下一步：继续保留真实合同中跨结构 text box/header/footer 等 coverage warning；如新增 corpus mutation，重新冻结 gold 后再比较指标。

### FL-D152 追加：结构变化伴随局部修改时的分类降级（2026-10-23）

- 发现与影响：独立算法复查发现，split/merge 结构变化中若同时包含局部文字修改，对齐在部分组合上会保守降级为整组 delete + insert，`modify=0`。字符级差异仍完整保留，但修改级定位不够细，影响 modify 分类统计与下游展示粒度。
- 证据：纯 `CompareDocument` 反例 `甲乙丙丁` → `甲 / 乙X / 丙 / 丁` 产生整组删除与插入；同轮四段 split/merge、表格 cell、重复段落/费率、唯一重排复查均未出现真实文字差异被归零。42 种分段组合的 1764 对比较中，字符流不同均未得到 0 diff；1500 组随机重排/修改攻击为 0 次零差异漏报、0 次双向不对称。
- 处理方法：当前保留 delete+insert 作为高召回保守回退，不以提高 modify 分类为代价吸收结构变化；后续若优化局部对齐，必须保持字符差异召回、方向对称和确定性硬门。
- 状态与验证：已确认范围内限制；当前不阻塞字符级召回与 identity/对称性硬门。独立算法复查报告源码未修改；现有 compare 测试仍为 54 passed / 4 skipped，待系统/前端收尾后的最终回归再次确认。
- 下一步：如产品需要更细 modify 展示，新增冻结 gold 与针对 split/merge+局部修改的分类指标后再单独优化；不得修改现有 gold 迎合分类结果。

### FL-D152 最终指标更正（2026-10-23，gold v7）

- 前文将 pair 数误作 operation 分母，且 zero/modify 分母填写错误；保留历史记录，本段为最终正确口径。20 bases 共386 mutation pairs，dev272 pairs/219 gold operations，回收219/219；holdout114 pairs/92 operations，回收92/92。modify 分类 dev112/113，holdout46/46。零差异 fixtures dev69/holdout30，误报均0；identity20/20，symmetry20/20 bases及60/60方向检查，determinism20/20 bases（每base identity与非零mutant各5次）。
- gold payload SHA-256 `45651ace97a78ec4d1d6e28d8b492f6ec090da55b62156ffae58ee6ca5779e04`，文件SHA `1a2afabe6bc09c182c107d9d608b5ea420dd08db57db855dbfe12ad914b63c3d`；manifest SHA `731a29bf9dbd199ca978e476313e1d6fa9d67239725e917ee3c93f6ddbe10e60`。独立gold读OOXML，不导入compare，但它仍属于程序化oracle，并非人工语义标签。
- dev耗时median0.7375s/P951.1651s/max3.1646s；holdout0.8944s/1.2950s/1.5384s。20对独立新Python进程性能：median1.1745s/P951.6512s/max4.0687s/peak RSS51,728,384bytes；未清OS页缓存。
- B14–B19 holdout此前已暴露，作为透明回归split，不冒称未见留出验收。B07历史merge声明零差异但可见文字流实际变化，v7独立更正；12个modify_percent是无目标百分比时的普通两字fallback，不冒称百分比语义样本。证据：`/tmp/opencode/compare-continuation/FINAL_SUMMARY.md`及同目录final-eval/final-hard-gates/final-benchmark文件。

## FL-D153 Compare 前端批量文件状态与异步结果竞态（2026-10-23）

- 问题与影响：重绘批量输入会清空浏览器 FileList；folder 自动配对原来静默跳过未配对文件；任务创建后未稳定进入结果页，异步轮询/快速切换可能以旧响应覆盖新 pair。
- 证据：独立 Playwright `/tmp/compare-e2e-review-2.json` 初始 15/16，`add_pair_preserves_existing_files` 复现已选文件在添加第二组后变为 0；刷新和快速 pair 切换可见旧结果覆盖风险。
- 处理方法：File 对象保存于 state，添加/删除 pair 采用增量 DOM；folder 显示未配对项供手工补齐；创建后刷新并打开任务；请求 token 丢弃过期异步响应；导航在 pane 内滚动，0 diff 重置计数；identity reset 清空视图。
- 状态与验证：已实施。`tools/evaluation/compare_e2e.py` 真实浏览器 **16/16 checks passed**，包含三类差异、XSS、虚拟 anchor、点击/上一处/下一处、SVG 端点 resize/scroll 误差≤2px、批量 pair 导航和身份切换；Node syntax check 通过。
- 下一步：部署前在目标环境再跑一次同一浏览器证据脚本；本轮未执行生产部署。
- 下一步：独立 parser/算法 Reviewer 攻击其他名称空间冲突；完成 dev 与未暴露 holdout 指标。

### FL-D153 最终前端补充验证（2026-10-23）

- 新发现及修复：新任务重用了上次state.inputs；目录枚举顺序导致E2E补错行；任务列表“差异”用了pair数；completed隐藏失败/覆盖不完整；failed pair错误写在隐藏viewer中。现已重置新任务输入、按文件名定位补配行、汇总实际summary.total、明确失败/不完整计数，并在可见pair卡片显示固定错误码。上传逐项核对accepted回执，切换pair先清旧viewer，零差异重置0/0及SVG。
- 当前源码浏览器验证：`/tmp/opencode/compare-e2e-current.json` **24/24 checks，9场景，全通过**。涵盖单modify、三组批量、25差异、三种类型、零差异、空侧anchor、folder补配、全失败、真实公开合同incomplete、XSS、导航与身份隔离；resize与独立scroll前后SVG端点最大误差均0px，无pageerror。截图目录`/tmp/opencode/compare-e2e-current-shots/`。该验证使用临时API/真实CompareWorker与项目dev身份入口，不接触生产或修订模型。
- 状态：开发环境前端验收通过，生产部署未执行。历史16/16等证据仅保留作先前轮次记录；最终使用当前24项证据。

## FL-D152 `codex` 默认进入旧 tmux 对话（2026-10-23）

- 问题与影响：为解决 SSH 断开后任务中断，前一版用户级 `codex()` wrapper 使用固定工作目录 session 名并执行 `new-session -A`；因此用户每次输入 `codex` 都会 attach 到仍存活的旧会话，跳过 Codex 初始页，造成“打开 Codex 就进入运行中的对话”。
- 证据：`tmux -L fundlex-codex list-sessions` 显示 `codex-d01396214ff5` 仍 attached；旧 `tools/ops/codex_persistent.sh` 使用 `session_name="codex-${digest}"` 与 `new-session -A`。
- 处理方法（已实施）：工作目录只作为 session 前缀；普通 `codex` 每次使用时间戳/PID 创建新 tmux session，进入初始页；`codex attach` 按该目录前缀选择最近 session 并 attach；`codex resume --last` 仍交给官方会话恢复命令。同步用户级启动器，保留显式 `--no-daemon` 与完整权限参数。
- 验证：`bash -n`、Python 编译、`git diff --check` 通过；PTY 断线测试 `pty_hangup=passed`、`work_completed_after_disconnect=true`、`reattached_same_process=true`；旧活动 session 未强制关闭，避免中断当前工作。新 SSH shell 读取更新后的 `.bashrc` 后，普通 `codex` 不再使用 `-A` 接旧 session。
- 当前状态与下一步：已解决。需要接回旧任务时使用 `codex attach`；需要恢复历史聊天时使用 `codex resume --last`。已有运行中的旧 session 会继续保留，用户可在确认无需其继续后手动退出。

## FL-D153 “优化 FundLex 合同修改闭环”被 stale writer lock 阻止切换（2026-10-23）

- 问题与影响：用户切换到会话 `01a16485-b7ba-7090-99cc-51cb1c5fa0ab`（标题“优化 FundLex 合同修改闭环”）时提示对话已在其他地方打开，无法继续。
- 证据：`session_index.jsonl` 将该 ID 映射到目标标题；进程表和两个当前 tmux pane 中均无该 ID 或其 `codex resume` 进程；唯一对应文件是空的 `~/.codex/thread-writer-locks/01a16485-b7ba-7090-99cc-51cb1c5fa0ab.lock`，mtime 为 2026-10-23 10:26:30 +0800，明显早于本次检查。
- 处理方法（已实施）：不停止当前两个活动 Codex 会话；将确认过期的空锁移到 `/tmp/fundlex-codex-stale-locks/01a16485-b7ba-7090-99cc-51cb1c5fa0ab.lock.20261023-134825` 保留证据，释放原锁路径。
- 验证与状态：原锁路径已不存在，目标没有活动进程；可重新切换/恢复该会话。若仍提示占用，应先退出其他设备上的同一会话客户端，再重试；不能删除有对应活动进程的锁。

### FL-D153 追加更正（2026-10-23 14:30）

- 更正：所谓“stale lock”判断错误。复核 `/proc/<pid>/fd` 发现 `01a16485-b7ba-7090-99cc-51cb1c5fa0ab.lock` 当时由 **pid 2152151**（tmux 会话 `codex-d01396214ff5` 内的活动 Codex TUI）持有，且同一进程同时持有 4 个 thread lock。`ps` 看不到 thread id、pane 里也看不到 `codex resume` 进程，不等于没有活动 writer。
- 影响：`rm` 锁文件只删掉路径名，原进程仍持有已删除 inode 的 flock；后续客户端会新建同名文件并误以为拿到锁，互斥被破坏。**任何情况下都不要删除 thread-writer-lock。**
- 正确处置：确认持有进程所在 tmux 会话，接回该会话或等其退出；锁随进程退出自动释放。

## FL-D154 Codex 对话锁的真正根因：多个 legacy TUI 各自持有 thread lock（2026-10-23）

- 问题与影响：用户切回历史对话时常提示 `This conversation is open in another app`。根因不是残留文件，而是每个 `--no-daemon` TUI 都是独立的 thread-store writer，旧 tmux 会话长期不退出，且一个 TUI 打开过的每个 thread 都会一直持有锁；新客户端 `resume` 同一 thread 即冲突。日志原文：`thread-store conflict: thread <id> already has an active writer`。
- 证据：`codex ls` 显示 4 个 detached legacy 会话；pid 2152151 持有 `01a16485…`、`01a16488-206d…`、`01a16488-8df7…`、`01a16663…` 四个锁；pid 2156308 持有另外三个；14:24:28 的 `thread/resume` 错误与 14:26 的锁提示可直接对应。
- 处理方法（已实施）：重写 `tools/ops/codex_persistent.sh` 并安装到 `~/.local/bin/codex-persistent`。`codex resume <id>` / `resume --last` 先用 `/proc/<pid>/fd` 找到真实 holder，再按 tty→tmux pane 映射到会话；若 holder 在 tmux 中则**接回原会话**，不再新开 writer；holder 不在 tmux 时报 pid/tty 并拒绝开第二个客户端。新增 `codex ls`（daemon 状态 + legacy 会话/运行状态/持有的 thread 标题）、`codex where <id>`、`codex attach`、`codex close`、`codex gc --hours N`。保留 daemon 不可用时的 tmux 兜底。
- 验证：`where 01a16485…` → `holder pid=2152151 tty=/dev/pts/0 tmux=codex-d01396214ff5`；dry-run `resume` → `attach codex-d01396214ff5`（正确接回而非新开）；`resume --last` → 按 `updated_at` 解析并接回对应会话；PTY 断线测试 `pty_hangup=passed / work_completed_after_disconnect=true / reattached_same_process=true`（0 模型调用）。
- 当前状态：已实施并验证路由逻辑。**未强制关闭用户正在使用的 legacy 会话**；这些会话持有的锁在其退出后自然释放。日常新会话走 FL-D155 的 daemon，不再产生新的 legacy 锁。

## FL-D155 SSH 关闭/终端退出后 Codex turn 中断：改用 app-server daemon 承载执行（2026-10-23）

- 问题与影响：standalone `--no-daemon` 把 turn 执行放在 TUI 进程内；TUI 退出（关终端、误按 Esc/Ctrl-C、tmux 会话被清理）会向自身 app-server 提交 `op=Interrupt`，turn 变为 `interrupted`。tmux 只能保住进程，保不住“客户端主动退出”这条路径，而且会累积持有锁的旧客户端。
- 证据：`logs_2.sqlite` 在 2026-10-23 14:26:04 记录 `submission ... operation="interrupt"`、`interrupt received: abort current task`，随后 `turn_aborted reason=interrupted`；同机 4 个 `--no-daemon` TUI 常驻且无人 attach。
- 处理方法（已实施）：
  1. 使用 Codex 官方完整包（`codex-package-x86_64-unknown-linux-musl.tar.gz`，0.162.1，bwrap sha256 与 FL-D076 记录一致）安装/启动 managed app-server daemon；daemon 随后自动升级到 **0.164.0**。
  2. 将 `~/.local/bin/codex` 改为指向 `~/.codex/packages/app-server-daemon/current/bin/codex`（0.164.0），旧 standalone 保留为 `~/.local/bin/codex-standalone-0.162.1` 可回滚；CLI 与 daemon 版本对齐。
  3. `~/.codex/app-server-daemon/settings.json` 增加 `"autoUpdateEnabled": false`、`"updateIntervalMinutes": 1440`，避免 daemon 单方面升级再次造成版本错配。
  4. `sudo loginctl enable-linger opencode`；新增 `~/.config/systemd/user/codex-app-server.service` + `.timer`（每 60s 健康探测 `codex-daemon-ensure`，socket 不通则 `daemon restart`；`KillMode=none` 保留 daemon）。daemon 与 updater 的 cgroup 已确认在 `user-1002.slice/user@1002.service/codex-app-server.service`，不再依赖某个 SSH session scope。
  5. `codex-persistent` 默认 daemon 模式（turn 在 daemon 中执行，TUI 只是客户端），daemon 不可用时才回退 tmux + `--no-daemon`。
- 验证：**SIGHUP 实测通过**——15:04:39 对 TUI 发送 SIGHUP（模拟 SSH 终端消失），daemon 内 `sleep 120` 继续执行，15:06:40 写出 `/tmp/opencode/sighup-ok.txt`，结果 `survived=true after=121s`；另外 TUI 在 turn 运行中收到 SIGKILL 后，daemon 仍继续写入 thread rollout（`01a16780…` 在客户端死亡后仍有 `task_started`/`custom_tool_call`/`token_count` 事件，无 `turn_aborted`）；`codex` 经 `.bashrc` 函数启动显示 `← for agents` 且不再新建 legacy tmux 会话；`codex doctor` 20 ok / 0 fail（唯一 warning 为既有的 `rollout_db_parity`）。
- 限制与下一步：SIGHUP 实测已证明 TUI 消失不会中断 daemon 内 turn；仍建议用户用自己的真实合同任务复验一次；测试 thread `01a16780…` 未删除（避免误删用户已打开的会话）。daemon 控制 socket 是 `/tmp` 下的符号链接；若 `/tmp` 被清理，timer 会在 60s 内重启。升级 Codex 时必须同时更新 CLI 与 daemon（完整包），不要只跑 `codex update`。用户现有 4 个 legacy 会话应在方便时退出，之后新会话全部走 daemon。

## FL-D156 opencode.service 每 3 秒重启一次（2026-10-23 发现）

- 问题与影响：`systemctl status opencode.service` 显示 `NRestarts=1768`、`MainPID=0`、`Result=success`，日志每 3 秒 `Started` → `Succeeded`。`ExecStart=/home/opencode/.opencode/bin/opencode serve --service` 在 fork 出常驻进程后以 0 退出，而 unit 配置 `Restart=always`，于是无限重启；只产生日志/启动开销，未观察到端口冲突。
- 状态：**已发现，未修复**（不在本次 Codex 稳定性范围内，避免影响用户当前 opencode 会话）。
- 建议：改为 `Type=forking` + 正确的 PIDFile，或 `Restart=on-failure` + `RemainAfterExit=yes`，或让 `serve --service` 前台运行（`Type=simple`）。修改前需确认 opencode 的 service 模式是否提供前台参数。

### FL-D154 追加：用户要求“全断”后清理结果（2026-10-23 15:13）

- 用户明确要求直接断开全部 Codex 会话，不再逐个确认。
- 操作：`tmux -L fundlex-codex kill-server` 关闭全部 6 个 legacy 会话；随后停止 daemon，确认 `thread-writer-locks/*.lock` 的 `/proc/<pid>/fd` 持有者为 0，删除全部 thread lock 文件（保留 `.coordination.lock`），移走 `loaded-threads.json` 备份到 `/tmp/opencode/`，再通过 systemd 服务重启 daemon。
- 结果：legacy tmux 会话 0 个；`~/.codex/thread-writer-locks/` 仅剩 `.coordination.lock`；daemon 0.164.0 running，cgroup 在 `user@1002.service/codex-app-server.service`，timer active；无活动 Codex 客户端。
- 影响：被关闭会话的进行中 turn 已中断（用户授权），聊天记录保存在 rollout，可用 `codex resume <id>` 或 `codex resume --last` 继续。

## FL-D157 删除关键词回退跨条款配对，G15 目标吞入 G17 段落（2026-10-23，核心引擎未提交改动）

- 发现：未提交改动中 `_delete_keyword_bag` 允许混合规则提取 delete 引用，`_KEYWORD_VARIANTS` 允许“次月/每月/月末”代替“按月”，且 `survey_targets` 的关键词回退不再受“本轮没有任何引用命中”限制。结果是：支付条款第二段以句号结束时，回退会把下一段（G17 用途条款）拼进同一个 G15 删除目标。
- 证据（真实合同 `funds_word/广发品质回报混合型证券投资基金基金合同_20230708.docx`）：
  - p806 `C 类基金份额的基金销售服务费每日计算，逐日累计至每月月末，按月支付，`
  - p807 `…于次月首日起5个工作日内从基金财产中一次性支付给基金管理人。…支付日期顺延。`
  - p808 `销售服务费主要用于支付销售机构佣金…`（属于 G17）
  - 当前工作区 `survey_targets` 产出 G15：`p806`、**`p807|p808`**、`p1262`、**`p1263|p1264`**；HEAD `a36acd2` 同样输入只产出 `p806`、`p1262`。G17 同时产出 `p808|p809`，p808 被 G15/G17 两个操作同时认领。
  - 100 份随机合同离线扫描：当前代码出现 6 处“G15 配对吞入下一段 G17 文本”（≥3 份合同）；按 HEAD 的精确关键词逻辑复算为 0 处。
  - FL-D146 记录曾把这 4 个 G15 命中当作“正文/摘要四处命中”的证据；实际正确跨段应为 `p806:0:35 + p807:0:89`（quality-return-12 已记录 `p806:0:34+p807:0:88`），`p807|p808` 是错误配对。
- 影响：G15 删除目标越过真实条款边界并覆盖 G17 文本；与 G17 目标重叠，可能触发 `RECALL_EDIT_OVERLAP`、错误删除或重复 Claim，站点证据不可信。即使最终 DOCX 表面正确，也不能证明操作级闭环。若模型 inventory 恰好把 p806/p807 作为复合目标覆盖，当前按 (rule, location) 的去重可能暂时掩盖该错误，但 recall-first 的正确性不应依赖模型先命中。
- 处理状态：**已修复（2026-10-23 晚，离线 + 真实模型单例验证）**。
  - `survey_targets` 关键词配对新增条件：上一段句末有 `。；;！？!?` 时不配对；follower 以 `销售服务费主要用于/使用范围` 开头时不配对；`in_self` 且段末为 `，、：` 时主动与下一段合并（修复半句目标）；`parts` 改用 `compact_text` 长度，避免空格导致 `RECALL_TARGET_COMPOSITE_UNRESOLVED`。
  - 回归：`tests/test_recall_core.py::test_keyword_delete_pair_stops_at_sentence_boundary`（含复合计划与 content check）通过；广发品质回报 survey 现在为 `p806|p807`、`p1262|p1263`，不再出现 `p807|p808`；100 份随机合同跨条款配对 **0 处**（修复前 6 处）。
- 验证/下一步：真实模型单例 `final1` 中 G15 四个段落均删除，G17 不再被 G15 认领；全量 pytest 1195 passed / 40 skipped / 0 failed。仍未 commit/deploy。

## FL-D158 append 摘要区路由把合同变更触发句当作份额类别定义锚点（2026-10-23，核心引擎未提交改动）

- 发现：`append_applicability_targets` 为所有 append 规则追加“所有 summary section”后，G01/G03 的 `append_site_ok` 只按“基金份额类别”等词匹配，命中摘要区的合同变更触发句，而不是份额类别定义句。
- 证据：30 份随机合同，当前工作区 **8 份 G01 + 8 份 G03** 命中类似 `基金推出新业务或服务，或调整基金份额类别设置；` / `调整基金份额类别设置及对基金份额分类办法、规则进行调整；`；HEAD `a36acd2` 同 30 份为 **0 份**。示例位置：广发品质回报 `p1138`、广发新城吾悦 `p1761`、其他合同 `p1208/p1111/p1093/p1186/p1178/p1160`。
- 影响：新增的份额类别/渠道费用条款会被插到“基金合同变更”触发事项列表中间；该插入通常可执行且不报错，存在静默错误交付/假完成风险；G01/G03 同址双插入还会造成重复。
- 状态：**已修复（2026-10-23 晚，离线 + 真实模型单例验证）**。
  - 新增 `_append_definition_anchor`：G01/G03 必须有定义标记（`份额类别：`/`基金份额类别定义`/`将基金份额分为`/`称为`），并排除 `调整基金份额类别设置`、`份额类别设置`、`增设新的份额类别`、`基金推出新业务`、`变更基金合同`、`终止基金合同`、`业务规则` 等变更触发句；支持 Word 拆分的定义续段。
  - `append_applicability_targets` 的成员筛选和 `append_site_ok` 都使用该门禁，模型 inventory 指向 `基金份额类别设置。` 的目标也不再被接受（FL-D163）。
  - 验证：30 份随机合同误锚点 **0**（修复前 8 G01 + 8 G03）；广发品质回报 append 目标为 G01 `p106`、G03 `p138`、G16 `p809/p1265`；真实单例 final1 中 G01/G03 政策各只出现一次，p137 未被插入。
- 下一步：随引擎改动一起 commit；仍只做单例真实验证，未跑 ≥5 份合同。

## FL-D159 核心引擎改动未提交、未做真实链路验证；G16 追加锚点仍在支付从句中间（2026-10-23）

- 范围：工作区未提交改动 `fundlex/recall.py`、`recall_pipeline.py`、`generation/coverage.py`、`generation/effects.py`、`generation/router.py`、`generation/__init__.py`、`recovery/{history,orchestrator,policies,types}.py` 及 8 个引擎测试文件（FL-D146）。
- 已完成的验证：`.venv/bin/python -m pytest tests -q` → **1166 passed / 39 skipped / 0 failed / 222.72s**；8 个引擎相关测试文件 247 passed；compileall、`git diff --check` 通过。HEAD 为 `a36acd2`，分支 `feat/contract-compare`（与 `origin/refactor/recovery-architecture` 同 SHA），改动未 commit/push。
- 未部署：`/opt/fundlex-recall-first/fundlex/{recall.py,recall_pipeline.py,generation/coverage.py}` 的 SHA-256 均与工作区不同，生产仍是旧版本。
- 未完成验证：无真实模型调用；上一 agent 记录的 `/usr/bin/sudo` setuid/owner 异常当前已不存在（`sudo -n true` 正常），但不能据此认定配置读取与真实链路已可用；尚未跑真实工作台端到端、未做 5 份真实合同验收。
- 既有问题（非本轮引入）：G16 append 锚点选在 `p806/p1262`（`…按月支付，` 句末逗号），`plan_target` 的从句保护会因下一段 `p807` 不满足 `append_site_ok` 抛 `RECALL_APPEND_CLAUSE_INCOMPLETE`，该目标无法执行；30 份随机合同有 5 份出现此类中间锚点。本轮摘要路由又把 p1262 副本加入，扩大了触发面。
- 影响：当前改动不能直接发布；在修复 FL-D157/FL-D158 并完成真实链路复验前，不得宣称引擎收敛或交付达标。
- **追加：G16 锚点已修复（2026-10-23 晚）**。`_g16_clause_end` 从支付句向后走到同一销售服务费条款的末段（p809/p1265，最多 6 段）；`append_site_ok` 接受条款末段和支付句的未完延续段；`_plan_and_generate` 对 append 规则改用 `append_site_ok` 归属，避免目标在规划前被 `TARGET_SOURCE_MISMATCH` 排除。回归 `test_g16_append_anchor_moves_to_the_end_of_the_fee_clause` 覆盖定位、`append_site_ok`、`target_site_ok` 与 `_plan_target_inner`。30 份随机合同中间锚点 **0**（修复前 5）。
- **真实模型单例（final1）**：43 calls / $0.02638 / 约 150s；G15 四个段落删除、G16 在 p809/p1265 各插入一次、G17 删除、G01 p106 与 G03 p138 各插入一次；obligation 13 ARTIFACT_VERIFIED + 9 ALREADY_SATISFIED + 10 NOT_APPLICABLE + 2 UNRESOLVED；剩余仅为既有 G08/G18（见 FL-D164）。
- 下一步：仍须 ≥5 份真实合同 + 工作台登录/上传/下载全链路验收；当前未 commit、未部署。

## FL-D160 Compare worker 过期租约清理可能覆盖并发终态（2026-10-23）

- 发现与影响：`CompareStore.claim()` 清理达到最大尝试次数的过期 `leased/running` pair 时，先读取普通快照，再用不带 fencing token、状态或当前租约条件的 UPDATE 写入 `failed`。在最后一次 Worker 持锁写入 `succeeded`、或续租成功与清理交错时，清理 UPDATE 可能等待行锁后覆盖新终态，破坏结果交付和任务计数。
- 证据：独立系统复核对临时 SQLite store 注入“过期 SELECT 后、清理 UPDATE 前终态提交”的交错，结果从成功被覆盖为 `failed / COMPARE_PROCESSING_FAILED`。MySQL 并发时序尚待补充真实复现；MySQL 的 `finish/retry` 本身已有锁读和 fencing 回归。
- 处理方法：待实施。过期清理应在 MySQL 使用 `FOR UPDATE`，并在 UPDATE 中绑定读到的 fencing token、`status IN ('leased','running')`、`lease_until<=now` 与 attempt 条件；只有 `rowcount=1` 才刷新 task。
- 状态与验证：待修复；不得把当前 compare 专项通过结果视为此并发边界已闭合。
- 下一步：补 SQLite 确定性交错和隔离 MySQL 并发回归，修复后重跑系统/Worker 专项及全量 pytest。

### FL-D160 修复与真实MySQL验证（2026-10-23）

- 已实施：MySQL清理采用当前锁读，UPDATE二次绑定token/status/expiry/attempt，rowcount1才刷新任务。初次FOR UPDATE范围锁导致双claim deadlock，后续锁策略修复；heartbeat回归不读取未对外暴露的lease_until，而直接查询测试库。
- 实际验证：独立临时MySQL8实例33155、隔离测试库中系统/worker集 **28 passed / 1 warning / 9.34s**，包括单claim winner、长JSON、stale finish/retry、upload/seal及耗尽清理/heartbeat竞态；关键并发回归另重复5轮，每轮2 passed。完整compare集启用同一临时MySQL为 **75 passed / 1 warning / 14.31s**。日志`/tmp/opencode/compare-mysql-latest.log`。没有操作生产库。
- 状态：已修复并验证，适用于当前 compare store/worker 实现。

## FL-D161 Compare 结果边界重解析的临时 I/O 被标为永久失败（2026-10-23）

- 发现与影响：`CompareStore.finish()` 为验证源 DOCX 重解析时把全部异常包装为 `COMPARE_RESULT_INVALID`。若底层读取暂时抛出 `OSError`，Worker 无法进入已有的有界 transient retry，pair 会被错误终结，造成可恢复任务丢失。
- 证据：独立复核在真实临时 store 中对 `parse_compare_document` 注入一次 `OSError`，第一次 Worker 运行得到 `failed / COMPARE_RESULT_INVALID`，而预期应为 `retry_wait`，第二次再成功。
- 处理方法：待实施。`OSError` 应向上保留为 transient；确定的解析、结构和契约错误仍映射为固定 `COMPARE_RESULT_INVALID`，不得泄露异常正文。
- 状态与验证：待修复；当前 compare 专项测试覆盖普通 Worker retry，但尚未覆盖 finish 边界重解析的临时读取故障。
- 下一步：增加一次重解析 OSError 后 retry 成功回归，并重跑隔离 MySQL 与完整回归。

### FL-D161 修复验证（2026-10-23）

- 已实施：finish重解析允许OSError/DocxError继续交由Worker分类；临时读取故障进入retry_wait后可恢复，确定性解析错误使用固定错误码。新增一次重解析OSError、解析错误分类及清理fencing回归。
- 实际验证：compare集本地 **70 passed / 5 skipped / 1 warning**；启用临时MySQL后完整 compare 集 **75 passed / 1 warning**；完整项目 **1195 passed / 40 skipped / 2 warnings / 247.79s**。Worker轮询基础设施故障也使用有限等待，避免进程退出或忙循环；任意异常正文不写入API错误码。
- 状态：已修复并验证，适用于当前 compare store/worker 实现。

## FL-D162 并行引擎兼容性回归：G16 site guard 对简化测试替身读取缺失 location（2026-10-23）

- 发现与影响：全量回归在 compare 并行修改期间出现 1 项既有引擎测试失败：G16 的简化 `SimpleNamespace(text=...)` 没有 `location`，新 site guard 直接读取属性导致 `AttributeError`。该失败与 compare 代码无关，但会阻断整仓库验收。
- 证据：`tests/test_ff4d749_gate_closure.py::test_g16_payment_site_rejects_rate_formula_and_usage`；修复前全量为 **1179 passed / 39 skipped / 1 failed**，失败栈指向 `fundlex/recall.py` 的 G16 `locations.index(span.location)`。补丁使用缺省 location 保护后，定向测试 **1 passed**。
- 处理方法：已实施：site guard 对没有 location 的简化对象直接返回 `False`，保留真实 Inspection 对象的定位逻辑。
- 状态与验证：已解决；定向测试1 passed，完整 `.venv/bin/python -m pytest tests -q` **1195 passed / 40 skipped / 2 warnings / 247.79s**。compare 文件未因此改动。
- 下一步：保留该兼容性保护，未来若删除简化替身需同步更新测试契约。

## FL-D163 复合目标第二段在内容校验时被静默丢弃（2026-10-23，已修复）

- 发现与影响：`plan_composite_target` 用 compact 偏移生成每段编辑，但整段删除时只映射到最后一个非空白字符，留下尾随空格；`_composite_part_slice` 又按 compact 偏移计算期望 replacement，两者不一致时 `content_check` 返回 False。`_plan_and_generate` 删除被拒绝的编辑后，`_reconcile_final_plan_ledger` 只检查 target/operation 是否“还有任一 component”，于是复合目标第一段保留、第二段丢失却仍记 `planned`。真实 G15 的 p807/p1263 就是这样在最终 DOCX 中保留支付条款后半句。
- 证据：final1 之前的批次中 G15 Y004 计划只有 p806；`report.plan.edits` 无 p807。离线复算 `plan_composite_target` 可产出两段，`_component_ok` 对 p807 返回 False。
- 处理：整段删除时 `plan_composite_target` 映射到 `len(span.text)`（含尾随空格）；`_composite_part_slice` 对 `start=0,end=compact_len` 的整段同样返回 `(0, len(span.text))`；新增复合两段 content-check 回归。
- 状态与验证：已修复；`test_keyword_delete_pair_stops_at_sentence_boundary` 断言两段 replacement 均为空且 `_component_ok` 全通过；final1 真实 DOCX 中 p806/p807/p1262/p1263 全部为空。
- 下一步：保持 composite 两段 content-check 回归；后续如新增跨段类型需同步该整段约定。

## FL-D164 out_of_scope/归属失败的模型目标仍压制确定性召回（2026-10-23，已修复）

- 发现与影响：`known_operations_from_targets` 不区分目标是否已 `out_of_scope` 或 `attribution_error`。真实 G15 p806 的模型复合目标因站点归属失败被标 out_of_scope，但仍占据 `(G15,p806)` 覆盖，导致 `survey_targets` 不再生成合法的 p806|p807 目标；该段支付条款整段未删。
- 证据：run3 中 G15 body 目标缺失、T016 out_of_scope；run5 同位置出现 `Y004` 后才规划成功。
- 处理：`known_operations_from_targets` 跳过 `out_of_scope` 与 `attribution_error` 目标；新增 `test_invalid_model_target_does_not_suppress_deterministic_survey`。
- 状态与验证：已修复；final1 中 Y004/Y005 正常生成并执行；全量 pytest 通过。
- 下一步：无；继续保证“无效模型判断不能关闭确定性召回”。

## FL-D165 删除与同段 append 合并时 Claim/Validator 误报（2026-10-23，已修复）

- 发现与影响：G15 删除 p807 的同时，G16 把新政策插入同一段（或 G17 删除的段落由 G16 承接），合并后段落不再为空。G15 的 per-edit unit validator 只看到自己的空 replacement，报 `CLAIM_VALIDATION_FAILED` / `CLAIM_PLANNED_EFFECT_MISSING`，即使最终文本完全符合联合计划且旧措辞已消失。
- 证据：run3/run5 的 G15 p807 覆盖率状态为 `CLAIM_VALIDATION_FAILED`；final1 中同一段实际已是 G16 授权文本。
- 处理：`evaluate_operation_effect` 增加 delete 分支：`planned_matches and own and not residual` 时判 PASS/VERIFIED_ABSENT（artifact 必须精确匹配包含兄弟操作的联合计划，且旧措辞已不存在）；新增 `test_delete_passes_when_another_operation_fills_the_empty_paragraph`。
- 状态与验证：已修复；final1 中 G15 四个段落均 PASS，G16 仍 PASS；全量 pytest 通过。
- 下一步：保留“联合计划精确匹配”前提，不得放宽为仅看旧文缺失。

## FL-D166 G03 模型目标落在“基金份额类别设置”句导致双插入（2026-10-23，已修复）

- 发现与影响：模型 inventory 把 G03 append 目标放在 `基金份额类别设置。` 的片段段（p137），确定性 append pass 又在真正的定义段（p138）生成目标，两处都执行，最终同一政策文本插入两次。
- 证据：run5 final DOCX p137 与 p138 各出现一次 G03 政策；`CLAIM_DUPLICATE_EFFECT` 在 run4 已出现。
- 处理：`append_site_ok` 对 G01/G03 先经过 `_append_definition_anchor`（定义标记 + 变更触发句排除 + 拆分续段），模型目标与 survey 目标使用同一门禁；新增回归断言 trigger 段不通过、定义段通过。
- 状态与验证：已修复；final1 中 p137 保持原文、p138 仅一次政策；全量 pytest 通过。
- 下一步：无；若后续出现其他“设置/调整”类定义变体，补充到排除/标记表。

## FL-D167 真实单例仍因 G08/G18 未完成（2026-10-23，未修复）

- 发现与影响：final1（43 calls / $0.02638）delivery_status=incomplete；obligation 计数 13 ARTIFACT_VERIFIED / 9 ALREADY_SATISFIED / 10 NOT_APPLICABLE / 2 UNRESOLVED。剩余为：
  - G08 p156 `RECALL_COMPOSE_FIXED_TEXT_MISSING` + `CLAIM_OPERATION_NOT_PLANNED`；
  - G18 无 verified site（`CLAIM_OPERATION_UNPROVEN`）。
- 证据：`/tmp/opencode/engine-live-20261023/final1/report.json`；最终 DOCX 的 G15/G16/G17/G01/G03 已按预期修改，G08/G18 未完成。
- **追加：已修复（2026-10-23 晚）**：
  - G08：`_selected_operation_indices` 增加 `_semantic_flip_only`/`_numeric_flip_only` 拒绝（认购费率 vs 申购费率），错误 p156 目标不再进入 compose；G08 只在 p223 申购费率条款执行。
  - G18：`satisfied_operation_keys` 对重排/改写后的费用差异句回退到单操作等价判定；`target_site_ok` 接受“由于基金费用的不同…分别计算基金份额净值”的等价站点；`operation_site_bound`/`evaluate_operation_effect`/`_quote_is_expected_effect` 接受政策等价文本，Claim 与 Audit 均判 ALREADY_SATISFIED。
  - 真实单例 final4：**27 calls / $0.02169 / 97s，delivery_status=complete、unresolved 0**；final/redline 哈希与报告一致，redline 19 ins / 19 del。
- 状态：**已解决（单例 + 5 份真实合同批次）**。这两项是 FL-D146 之前已存在的生成/适用性问题，不是 FL-D157/158 的回归。
- 下一步：保留 G08 认购/申购 flip 与 G18 等价句回归；继续 ≥5 份合同与工作台路径（见 FL-D174）。

### 本轮真实模型预算记录（2026-10-23）

- 临时账本（均在仓库外）：`/tmp/opencode/engine-live-20261023/ledger.sqlite`（263 calls / ≈$0.1439）、`ledger-final.sqlite`（74 / $0.03485）、`ledger-debug.sqlite`（85 / $0.04212）、`ledger-final2.sqlite`（43 / $0.02638）。合计 **465 calls / ≈$0.2473**。
- 未使用生产账本 `/var/lib/fundlex/model_budget.sqlite`；未打印或入库任何凭据；未部署、未跑 514 份。

## FL-D168 合同比较发布前缺少独立生产 Worker（2026-10-23，已解决）

- 发现与影响：compare API 和持久化代码已接入，但独立 `CompareWorker` 只存在于代码和 systemd 模板；若只发布工作区并重启原有 Recall Worker，用户可以创建和封存对比任务，却没有生产进程领取 pair，任务会长期停留在队列。
- 证据：发布前 `fundlex-recall-api.service` 与 `fundlex-recall-worker.service` active，`fundlex-compare-worker.service` 不存在；模板路径为 `tools/deploy/fundlex-compare-worker.service.template`。
- 处理方法：发布 compare 代码后，将模板安装为 `/etc/systemd/system/fundlex-compare-worker.service`，与 API 共用 `/etc/fundlex-recall.env`、`FUNDLEX_DATA_DIR` 和数据库，执行 daemon-reload、enable、start，并把三项服务纳入发布后的健康检查。
- 状态与验证：已解决。发布后以真实登录身份上传公开 DOCX、封存任务，由独立 compare Worker 实际处理；API 与浏览器结果页均成功，报告下载文件已核对。适用于 2026-10-23 发布版本。
- 下一步：未来 compare Worker 的代码、环境或 systemd 模板变化须重新执行同一生产用户路径验收。

## FL-D169 工作区快照发布会包含未提交文件（2026-10-23，需后续改进）

- 发现与影响：`tools/deploy/publish_workspace.sh` 按工作区目录打包同步 `fundlex`、`frontend`、`tools`、`docs`、`tests`，不按 Git 已提交文件筛选。因此本次发布虽然 compare 提交已单独创建并推送，发布快照也包含当时工作区中其他任务的未提交源码改动。
- 证据：发布前工作区存在 `fundlex/recall.py`、`fundlex/generation/*` 等未提交修改；发布脚本随后按目录复制并重启服务。生产服务已 active，compare 生产链路验收通过。
- 处理方法：本次保留已发布快照，不在生产上回滚其他任务，避免破坏用户要求的整体发布和当前运行任务。后续发布前应明确确认工作区快照范围，或改造发布脚本为接收明确的提交/文件清单，并在发布前输出源文件与目标文件哈希清单。
- 状态与验证：已发现，当前发布可用；发布脚本的范围控制仍待改进。compare 相关生产结果已实际验证，其他引擎改动的独立生产验收不属于本次 compare 验收。
- 下一步：下次发布前先检查工作区 dirty 文件，确认是否允许随快照发布；必要时建立干净发布 worktree。

## FL-D170 G06 语义探针把全文档尾部当成一个句子（2026-10-23，已修复）

- 发现与影响：`_semantic_delete_hits`/`_semantic_delete_sentences` 在按句切分后还把整段/整份文档作为 `tail` 再匹配一次。ETF 合同中前文的“基金份额类别”与后文的“不得…转换”相距数千字，仍被当成一个 G06 变体，导致 `semantic_delete_variant_present` 永久 OPEN（上海清算所 G06）。
- 处理：删除整段/整文档 tail 复扫；只保留按句切分结果（未终止的最后一节本身仍是一个 chunk）。
- 验证：新增 `test_semantic_delete_probe_does_not_join_distant_sentences`；上海清算所批次由 incomplete 转为 **complete**（35 calls / $0.0305）。
- 状态：已修复。

## FL-D171 跨三个段落的事实引文未通过核验（2026-10-23，已修复）

- 发现与影响：`_quote_present` 只拼接相邻两段；ETF 释义引文跨 p67/p68/p69 三段，`FUND_TYPE_QUOTE_UNVERIFIED` 使已可判定的 ETF 仍被当 eligible 处理，跑完整链路后 `not_generated`（91 calls）。
- 处理：按 2/3/4 段连续窗口拼接，并要求引文确实跨过至少一个段边界。
- 验证：新增三段引文回归；同一 ETF 合同现在识别为 `excluded`，12s / 39 calls 即停止，不再生成错误任务。
- 状态：已修复。

## FL-D172 模型目标只覆盖 G17 首句时漏掉第二段尾句（2026-10-23，已修复）

- 发现与影响：ESG 合同把 G17 的两句拆到 p813/p814。模型目标只绑 p813，`existing` 覆盖使 survey 跳过该规则；p814 的“销售服务费的使用范围不包括…”保留，sweep 正确报 residual，合同 incomplete。
- 处理：`_reference_tail_match` 识别 delete 参考文中的尾句（按句剥离类群前缀），survey 对未被覆盖的尾句段落生成独立目标；模型目标只覆盖首句时不再掩盖尾段。
- 验证：新增 `test_uncovered_delete_tail_sentence_gets_its_own_target`；ESG 由 incomplete 转为 **complete**（38 calls / $0.0261）。
- 状态：已修复。

## FL-D173 G17 delete + G16 append 联合校验误报（2026-10-23，已修复）

- 发现与影响：G16 政策插入 G17 删除的段落，合并 edit 的联合校验把实例化后的 G16 文本（C/F 类）判为 `CLAIM_JOINT_UNEXPLAINED_TEXT`，G16 也因 unit validator 只看到自身 replacement 而 `CLAIM_PLANNED_EFFECT_MISSING`；最终 DOCX 实际正确。
- 处理：联合校验的 `allowed_additions` 加入合并组件自身的 `replacement`/`evidence.fixed_text`（实例化文本），不再只依赖 guide 原始 new_text；`evaluate_operation_effect` 新增 append 分支：`planned_matches + expected_present + own` 判 PASS/EXPECTED_EFFECT_PRESENT。
- 验证：央企股东回报联接批次由 incomplete 转为 **complete**（72 calls / $0.0742）；G16/G17 联合站点通过。
- 状态：已修复。

## FL-D174 条件为 FALSE 的 satisfied 目标仍被审计为“应保持原文”（2026-10-23，已修复）

- 发现与影响：G20 仅适用于浮动管理费多类别产品；固定费率产品的 G20 satisfied 目标仍进入 Audit。相邻 G22 合法修改同一清算段后，审计把 G22 的“销售服务费（如有）”误判为 G20 的部分实现，合同 incomplete。
- 处理：`assign_target_operations` 对显式操作全部为 `condition_status=FALSE` 的目标标 `out_of_scope`（`TARGET_OPERATION_NOT_APPLICABLE`），Audit/覆盖率不再把它当作应保持原文的义务。
- 验证：新增 FALSE-branch 回归；央企创新驱动联接批次 **complete**（102 calls / $0.0892），G20 段落未被错误插入，G22 正常生效。
- 状态：已修复。

## FL-D175 真实合同批次与工作台路径验收（2026-10-23，阶段完成）

- **6 份不同真实合同 delivery_status=complete、unresolved 0、final/redline 均生成且哈希与报告一致**（临时账本）：

| 合同 | calls | cost USD | final SHA-256 前缀 | redline ins/del |
| --- | --- | --- | --- | --- |
| 广发品质回报混合 | 27 | 0.0217 | 785db513805f | 19/19 |
| 广发核心优选 FOF | 47 | 0.0305 | ade7f4ed4ffd | 19/19 |
| 广发上海清算所 0-4 年央企 80 债券 | 35 | 0.0305 | 33659eeaf416 | 21/21 |
| 广发 ESG 责任投资混合 | 38 | 0.0261 | 573bc64f74b0 | 16/16 |
| 广发中证国新央企股东回报 ETF 联接 | 72 | 0.0742 | ba90130db760 | — |
| 广发中证央企创新驱动 ETF 联接 | 102 | 0.0892 | 19ad7dad0838 | 18/18 |

- 额外：港股通央企红利 ETF 正确识别为 `excluded`（12s / 39 calls）；央企股东回报联接一次 `MODEL_SCHEMA_INVALID` 停止后已重跑成功，属模型输出偶发。
- **工作台真实路径（本地临时 API + Worker，非生产）**：`e2euser` 登录 → 创建任务 → 上传广发品质回报 DOCX → seal → Worker 真实模型处理 30 calls / $0.02243 / 101s → `delivery_status=complete` → 下载 `final`/`redline`/`report_json`/`report_md`；final SHA `0c1a5db56573…` 与报告一致，redline 19 ins / 19 del；G01/G03 政策各一次、G15/G16/G17 正确。
- **生产发布与真实用户路径（2026-10-23 晚）**：引擎提交 `11c3ae8` 已通过 `tools/deploy/publish_workspace.sh` 发布；部署 `recall.py`/`recall_pipeline.py`/`effects.py`/`claim_replay.py` 哈希与工作区逐项一致，`fundlex-recall-api`/`worker`/`compare-worker` 均 active。
- **生产域名 E2E（https://fundlex.club，admin 登录）**：创建任务 `19a5c76ec45d487caf11491f6294569e` → 上传广发品质回报 DOCX → seal → Worker 真实模型 **30 calls / $0.02247 / 115s** → `delivery_status=complete`、unresolved 0 → 下载 final/redline/report。final SHA `e48e0f781cd0…` 与报告一致；redline `aceb92896564…` 与报告一致、19 ins / 19 del；G01/G03 政策各一次，G15 p806/p807/p1262/p1263 删除，G16 p809/p1265 插入，G17 删除，G08 p223 正确、p156 未动，G18 p139 保持已满足。
- **浏览器 UI**：Chromium 登录成功（Bootstrap Administrator），任务页显示该生产任务，存在 3 个下载入口与“完整/最终/修订”文本；无 pageerror；仅有一条登录前 401 探测 console 记录，不影响流程。截图 `/tmp/opencode/engine-live-20261023/production-browser/task-page.png`。
- **生产批量 ≥5 份合同（2026-10-23 晚）**：在 https://fundlex.club 连续创建并处理 4 份合同，全部 `delivery_status=complete`、unresolved 0，final/redline 哈希与报告一致：

| 合同 | task | calls | cost USD | final SHA 前缀 | ins/del |
| --- | --- | --- | --- | --- | --- |
| 核心优选 FOF | `11ea3ca6…` | 32 | 0.0240 | df7cc5ec38d9 | 19/19 |
| 上海清算所债券 | `945d7fd4…` | 32 | 0.0249 | 892c709762e5 | 19/19 |
| ESG 混合 | `e37fceff…` | 29 | 0.0288 | e0ca96b68c16 | 17/17 |
| 央企创新驱动 ETF 联接 | `7c410185…` | 33 | 0.0252 | 8eb082c10aa9 | 18/18 |

- 加上此前的广发品质回报（`19a5c76e…`，30 calls / $0.02247），**生产共 5 份不同合同 complete**；G15/G17 旧条款均为 0 处，G16 新政策存在，未发现重复政策文本。
- **未做/边界**：生产验收任务未清理（无 DELETE 接口）；本轮生产模型调用记入生产账本。累计临时账本 **1129 calls / ≈$0.7999**，生产 5 份合计 **156 calls / ≈$0.1254**。
- 下一步：观察 compare/recall 三服务与生产账本；必要时由管理员清理验收任务。

## FL-D177 合同比较阅读器两栏不联动且视觉层级不足（2026-10-24，已修复）

- 发现与影响：生产版合同对比阅读器让原版和对比版分别滚动，用户无法保持两侧阅读位置；结果摘要、覆盖边界、正文标题和差异导航挤在同一层级，长合同核对时难以判断当前上下文。现有滚动监听只触发 `drawLines()`，不能实现阅读同步。
- 证据：`frontend/compare.js` 原先分别给两个 `.compare-pane` 绑定 `scroll` 事件且回调只有 `drawLines`；`frontend/compare.css` 原先两个 pane 都是独立 `overflow:auto`；生产截图 `/tmp/opencode/compare-production-ui-e2e/viewer.png` 可见正文区缺少明确的阅读器分区和同步提示。
- 处理方法：处理中。改为按两侧可滚动高度比例同步 `scrollTop`，用滚动来源锁避免递归回调；重新组织结果头、覆盖提示、双栏基准/修订标题、同步状态和差异导航层级，保留现有 API、连线、差异筛选、键盘定位和移动端单栏切换。
- 状态与验证：已修复并发布。`.venv/bin/python -m pytest tests/test_compare_*.py -q` → **70 passed / 5 skipped / 1 warning**；本地浏览器验收 `/tmp/opencode/compare-e2e-ui-v5.json` → **9 个场景全部通过**，包含正向/反向滚动比例和 SVG 连线检查；生产真实浏览器验收 `/tmp/opencode/compare-production-ui-e2e/report.json` → 注册/登录、公开 DOCX 上传、独立 Compare Worker、结果页、双向联动、移动端切换、键盘定位、报告下载全部通过，page error 为 0。生产联动比例误差分别为 `5.3e-6` 与 `2.6e-7`，结果 2772 处差异，报告 3189696 bytes。发布提交 `0f51d07` 已推送并通过 `tools/deploy/publish_workspace.sh` 发布，API、Recall Worker、Compare Worker 均 active。生产截图 `/tmp/opencode/compare-production-ui-e2e/viewer.png` 可见新的任务结果、方向提示、同步状态、基准/修订标题和差异导航层级。

## FL-D176 合同比较页面方向语义、恢复能力与长文阅读不足（2026-10-23，已修复）

- 发现与影响：原页面只写“左侧/右侧合同”，用户需要自行推断新增/删除方向；覆盖不完整时的空结果文案可能被理解为全文无差异；批量上传中断后不能从已完成位置继续；任务轮询会把当前查看的 pair 重置到第一组；移动端双栏过窄，差异类型筛选和正文标记键盘操作不足。
- 证据：三类只读评审分别定位到 `frontend/index.html` 的 compare DOM、`frontend/compare.js` 的 `openTask()`/上传流程和 `frontend/compare.css` 的移动端双栏规则；旧浏览器验收可复现轮询从第 2/3 组跳回第 1/3 组。
- 处理方法：创建与结果页统一使用“原版（基准）→ 对比版（修订）”语义；覆盖不完整时明确提示人工复核并改用“已覆盖范围内没有发现”；批量上传按组显示进度并保留可继续上传状态；轮询按 `selectedPairId` 保持当前 pair；差异列表增加类型筛选和章节信息；移动端切换为原版/对比版单栏阅读；正文差异标记增加焦点、Enter/Space 定位和可见状态。
- 状态与验证：已修复并发布。`.venv/bin/python -m pytest tests/test_compare_*.py -q` → **70 passed / 5 skipped**；`tools/evaluation/compare_e2e.py` → **9 个场景、全部检查通过**，新增方向语义、轮询保持当前组、差异筛选、键盘标记和移动端切换检查；证据 `/tmp/opencode/compare-e2e-ui-revision-v3.json`。生产浏览器回归 `/tmp/opencode/compare-production-ui-e2e/report.json` 通过：2772 处差异、修改 451、新增 1238、删除 1083，移动端左右切换成功，键盘计数 `1 / 2772`，报告下载 3189696 bytes，page error 为 0。
- 发布信息：UI 提交 `5d04271` 已推送到 `origin/feat/contract-compare`，通过 `tools/deploy/publish_workspace.sh` 同步生产；API、Recall Worker、Compare Worker 均 active，重启计数为 0。生产任务使用公开合同且 compare 不调用模型，费用为 `$0`。
- 下一步：覆盖完整性仍由 compare parser 支持范围决定，页面提示不能替代未支持结构的人工复核；后续 UI 或 Worker 改动须重复生产浏览器回归。

## FL-D178 Routed Policy Components 必须按当前 operation 验证（2026-10-24，已修复）

- 发现与影响：Registry 的完整 policy family 不能直接作为每个 sibling operation 的固定输出要求。G08/G11 某些 operation 只授权订阅费组，若把兄弟 operation 或完整 family 的所有组件硬套到当前输出，会把合法局部替换误报为 `RECALL_POLICY_COMPONENTS_UNVERIFIED`；G14 的授权替换还需要允许指引明确移除旧费率词；G16 则必须继续保留完整 Compose 组件硬门禁。错误边界会造成误阻断或放行未经授权的新文。
- 证据：`fundlex/recall.py::_validate_routed_policy` 现在从当前 operation 的 `new_text` 过滤 `must_add`，并用该 operation 自身 old/new 文本建立移除授权；`fundlex/generation/validators.py` 与 `tests/test_generation_validators.py` 覆盖 G08/G11 局部 fee group、G14 授权替换和 G16 完整组件语义。此前相关组合回归为 **142 passed**，更早闭环套件为 **217 passed**。
- 处理方法：Router 先按 operation 的 fact dependencies fail-closed；policy validator 仅验证当前 operation 固定文案声明的组件和当前 operation 的授权边界。兄弟 operation 不提供借权，G16 不因局部文案过滤而失去完整组件要求。
- 状态与验证：**已实施并定向验证**；当前工作区尚未以本条记录为依据宣称完整回归、冻结或生产发布。
- 下一步：随当前 operation identity/Registry patch 完成全量 pytest、compileall、diff check；然后重新冻结版本并按真实评测与工作台交付要求验收。

## FL-D179 Operation identity 必须贯穿 Registry、Planner 与 Claim Replay（2026-10-24，已修复）

- 发现与影响：同一 rule 下的 sibling operation 可能拥有不同 executor、条件、policy 和物理站点。若在 planner、replan、residual、coverage、obligation 或 Claim Replay 中重新派生 `RULE:index`，显式自定义 `operation_id` 会被错误当成兄弟别名，导致借权、重复站点合并或错误关闭 obligation。
- 证据：`fundlex/recall.py`、`fundlex/generation/claim_replay.py`、`fundlex/recall_pipeline.py`、`fundlex/targeting.py` 和 `fundlex/generation/registry.py` 统一优先读取 guide 声明的 `operation_id`；`tests/test_claim_replay_operation_authorization.py` 的自定义 identity 负向回归确认 `G99:CUSTOM_*` 不能借用 `G99:0`。同一 operation 的多个物理站点继续要求独立 occurrence identity，重复或缺失 occurrence fail-closed。
- 处理方法：released/fully annotated guide 必须使用显式 operation identity；部分标注抛出 `RECALL_OPERATION_ID_MISSING`；显式 operation 缺少 concrete Registry entry 抛出 `RECALL_OPERATION_REGISTRY_MISSING`。没有显式 identity 的旧低层 fixture 仅保留 legacy 兼容路径，不进入 routed Registry 执行。
- 状态与验证：**已实施并定向验证**。Registry、recall core 和 Claim Replay 组合当前 **104 passed**，其中新增 routed planner integration 回归直接验证缺失 Registry entry fail-closed；完整项目回归、真实合同重评测和生产验收尚待当前版本完成。
- 下一步：补齐 occurrence、canonical/legacy coverage fallback、replan/residual、delivery 回归并运行全量 pytest；之后重新冻结 build identity、发布并完成真实用户端到端交付。

## FL-D180 动态指引 operation 缺少 Registry entry 必须阻断发布执行（2026-10-24，已修复）

- 发现与影响：仅由 `operation_registry_coverage_gaps()` 报告动态指引缺口而继续 planner 执行，会使 operation identity 只成为 telemetry，运行时可能静默借用 rule-level fallback 或 sibling executor。
- 证据：对含 `operation_id=G99:CUSTOM_MISSING` 的 routed rule 直接调用 `plan_target()`，当前实现返回 `RECALL_OPERATION_REGISTRY_MISSING`，detail 同时保留 operation 和 rule；`tests/test_generation_registry.py::test_routed_planner_fails_closed_for_missing_custom_operation_registry_entry` 覆盖该路径。旧无显式 identity 的 low-level fixture 仍通过 legacy 分支。
- 处理方法：`_route_target_operations()` 在任何 routed operation 进入 Router 前检查 concrete `OPERATION_REGISTRY`；缺失即 fail-closed。动态 guide 只有在受控 publisher 显式提供 `OperationSpec` 并完成注册后才可执行。
- 状态与验证：**已实施并定向验证**；验证范围为本地测试，尚未证明动态指引发布流程或生产环境配置已完成。
- 下一步：将该门禁与 guide release/certification 及真实任务入口连测，保留失败证据，并在冻结版本后重新执行真实合同和工作台验收。

## FL-D181 Operation-aware targeting 回归破坏旧 fixture 的事实门顺序（2026-10-24，已修复）

- 发现与影响：把显式 operation identity 接入 `targets_for_open_rules()` 后，恢复循环在根据 `rule_id` 查找 rule 前读取 `rule`，旧低层 targeting fixture 触发 `UnboundLocalError`；同时 registry 模式的无显式 identity fixture 若直接进入目标解析，会把 `RECALL_TARGET_UNRESOLVED` 提前于应有的 `RECALL_FACT_UNVERIFIED`，破坏 UNKNOWN/CONFLICT fail-closed 契约。
- 证据：完整回归首次结果 **1241 passed / 8 failed / 42 skipped**；7 项失败栈定位到 `fundlex/targeting.py:682` 的局部变量，1 项失败为 `tests/test_condition_tri_state.py::test_route_blocked_facts_resolve_as_fact_unverified`。修复后 `tests/test_condition_tri_state.py tests/test_open_obligation_recovery.py tests/test_generation_registry.py` 为 **32 passed**。
- 处理方法：targeting recovery 先解析 rule/operation，再计算 declared identity；`plan_target()` 对未显式标注的 legacy fixture 保留兼容 executor，但在 registry 模式且 operation 有 concrete Registry entry 时先执行 Router fact gate，阻断 UNKNOWN/CONFLICT 后再进入目标/结构解析。
- 状态与验证：**已修复并验证**；定向回归 **32 passed**，随后完整 `.venv/bin/python -m pytest tests -q` 为 **1249 passed / 42 skipped / 2 warnings / 223.62s**，compileall 与 `git diff --check` 通过。真实合同与生产工作台仍未按当前工作区版本重验。
- 下一步：完成全量 pytest、compileall、diff check；检查 legacy fallback 与 routed operation 的覆盖回归，随后重新冻结并执行真实评测和端到端交付。

## FL-D182 React V2 smoke 将预期 API 404 与静态资源故障混为一类（2026-10-24，已修复）

- 发现与影响：不存在任务的 Review 深链会按设计请求任务范围内的合同、报告或修订接口并收到 404。浏览器 smoke 原先把所有 404 都放入静态资源缺失列表，同时 Chromium 将这些 API 404记录为通用 console error，导致正确的 API 行为被误报为 React 构建或资源损坏。
- 证据：修复前 `tests/browser/test_frontend_v2.py::test_react_routes_and_deep_links` 为 **1 passed / 1 failed**；失败中的 404 仅为 `/api/tasks/nonexistent/documents/doc/revisions`、`/api/tasks/nonexistent/documents?page=1&page_size=200` 和 `/api/tasks/nonexistent/documents/doc`，没有 JS、CSS 或 favicon 404。
- 处理方法：浏览器回调按 `/api/` 与静态资源分别收集 404；API 404 保留在诊断信息中，静态资源 404 继续失败；仅忽略 Chromium 对这些已分类 API 404 的固定通用 console 文案，其他 console/page error 仍失败。
- 状态与验证：**已修复并验证**。`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` → **3 passed**，包含真实任务/真实 DOCX 上传后的合同详情与 Review 深链；无 page error、无静态资源 404。组合运行曾暴露根节点可见性断言的导航时序竞争，已改为等待 `#root` visible，`tests/test_tasks_api.py tests/browser/test_frontend_v2.py` 组合回归为 **30 passed / 1 warning**。
- 下一步：发布 React V2 后在实际服务上重复入口、深链、缓存头和真实用户交付验收；本条不代表已部署。

## FL-D183 React V2 指引启用状态与后端契约漂移（2026-10-24，已修复）

- 发现与影响：前端 Guides 页将 `validated` 与 `parsed`、`released` 一起视为可启用状态，但当前后端 `guide_store.ENABLEABLE_STATUSES` 及 `/api/settings/guide` 仅允许 `parsed`、`released`。用户可能看到可点击的启用按钮并在提交后得到冲突，或者误以为验证态已经具备正式启用资格。
- 证据：`fundlex/guide_store.py` 的可启用集合为 `{"released", "parsed"}`；`fundlex/api.py` 的当前指引能力门也使用 `{"parsed", "released"}`；原前端 `frontend/src/pages/Guides/index.tsx` 使用 `['parsed', 'validated', 'released']`。
- 处理方法：前端可启用判断收敛为 `['parsed', 'released']`，继续显示其他状态但明确置为不可启用；后端仍是最终权限和状态裁决。
- 状态与验证：**已修复并验证**。前端 `npm run typecheck`、`npm run lint`、`npm run build` 均通过，后端任务 API 定向回归 **27 passed**，React V2 smoke **3 passed**。
- 下一步：发布后用配置页上传、解析、显式启用和恢复内置指引的真实账号路径复核状态展示与权限隔离。

## FL-D184 React V2 首次加载错误缺少页面级重试入口（2026-10-24，已修复）

- 发现与影响：任务列表、任务详情和指引列表/详情首次 API 请求失败时只能显示错误文本，用户需要刷新整个页面；这不满足工作台对临时网络故障和服务恢复的可恢复操作要求。
- 证据：`frontend/src/pages/Tasks/index.tsx` 的任务错误分支、`frontend/src/pages/TaskDetail/index.tsx` 的任务错误分支及 `frontend/src/pages/Guides/index.tsx` 的 Guides/GuideDetail 错误分支原先未传递 `refetch` 回调；`useQuery` 已提供独立的 `refetch`。
- 处理方法：扩展共享 `ErrorState` 支持可选重试按钮；任务列表、任务详情、指引列表、当前指引和指引详情错误状态接入对应查询的 `refetch`。保留已有的加载中、空结果和局部报告/修订重试状态。
- 状态与验证：**已修复并验证**。`npm run typecheck`、`npm run lint`、`npm run build` 通过；浏览器 smoke **3 passed**，包含真实任务合同详情和 Review 深链错误态；`git diff --check` 通过。
- 下一步：发布后在实际服务上补充网络恢复和 401 会话失效的浏览器回归，确认重试不会复用其他身份的缓存请求。

## FL-D185 React V2 发布快照与并行未提交工作区混杂（2026-10-24，阻塞）

- 发现与影响：当前 `feat/frontend-v2` 工作区同时包含 React V2、Compare、recall-first 引擎、evidence、运维脚本及其他未提交/未跟踪修改。现有 `/home/opencode/fundlex/tools/deploy/publish_workspace.sh` 通过 root-owned `/usr/local/sbin/fundlex-publish` 整体同步 `fundlex/`、`frontend/`、`guides/`、`rules/`、`tools/`、`docs/` 和 `tests/`，无法表达“仅发布本轮 V2 必要文件”。直接执行会把并行改动一起发布，无法形成可审阅的 V2 build identity。
- 证据：发布脚本固定 `SRC=/home/opencode/fundlex`、`DST=/opt/fundlex-recall-first`，并对上述目录逐个 `tar` 同步；当前 `git status --short` 仍同时列出 `fundlex/generation/*`、`fundlex/recall.py`、`docs/evidence/*`、`tools/ops/*`、Compare 文件和 React V2 文件。当前 8010 服务仍返回旧 hash 工作台 HTML，`GET /tasks` 为 404，说明本轮 V2 尚未发布。
- 处理方法：本轮不直接调用整仓库发布脚本，不移动、覆盖或回退并行工作；先保留当前源码和 `frontend/dist` 构建产物，后续建立只含 V2 及其必要后端契约的可审阅发布快照，或为发布工具增加经过审查的 source snapshot 参数，再重启服务并完成生产浏览器与真实合同交付验收。
- 状态与验证：**已解决（已按用户指示发布当前工作区快照）**。发布脚本已执行两次，API 与 Recall Worker active；本机与 `https://fundlex.club` 的 React 入口均返回 `/assets/index-CmYK9MZP.js`，`/tasks` 返回 200，未知 `/api/*` 返回 404；发布后服务时间为 2026-10-24 08:49:31 CST。当前工作区曾混合的并行改动已随用户明确的“发布”指示一并同步，后续需以新的部署快照重新审阅。
- 下一步：继续完成生产浏览器有效任务/合同/Review 深链、401 会话失效以及 Worker/模型/DOCX/报告/下载哈希的真实用户路径验收。

## FL-D186 React V2 正式入口的默认 favicon 请求返回 404（2026-10-24，已修复）

- 发现与影响：React HTML 已包含内联 favicon，但浏览器仍会按约定请求 `/favicon.ico`；服务的 React fallback 将带扩展名路径视为缺失静态资源并返回 404，导致正式浏览器控制台出现静态资源错误。
- 证据：发布后本机 `GET /favicon.ico` 返回 **404**；JS/CSS 均为 200，`/tasks` 深链和未知 `/api/*` 行为正常。
- 处理方法：在 React 静态入口路由旁增加固定 SVG favicon 响应，使用同一橙色图标并设置长期缓存；API 路径和其他缺失资源仍保持原有 404 边界。
- 状态与验证：**已修复并发布验证**。定向 API/浏览器回归 **30 passed / 1 warning**；发布后本机 `/favicon.ico`、JS、CSS 均 200，favicon 与哈希资源均为 `public, max-age=31536000, immutable`；React V2 浏览器 smoke **3 passed**；公网入口 `https://fundlex.club/` 返回 React V2 HTML，未再出现默认 favicon 404。
- 下一步：在公网真实用户浏览器路径中继续观察控制台和静态资源加载，并完成真实合同交付验收。

## FL-D188 当前 P6 标签继承过时资格口径且不足以证明多站点完整性（2026-10-24）

- 2026-10-24 target-16审核更正：临时复核脚本和聊天曾再次沿用D06旧excluded标签；现依FL-D132更正为正常修改。首次`target-16-g17-business-review.json`原样保留，更正版另存`target-16-g17-business-review-corrected.json`，补跨段句和同地址余文核验：D04源G17用途2处、剩1；D06源用途/排除合4处、剩用途2处，独立余文均保留，二者均FAIL。未修改旧labels/gold/scorer、未因此读取holdout。
- 问题与影响：本轮重生的 `p6-current/labels.json`（SHA `f120d38175c83cd1c973045d0414a69bacb9d837fc4bf24d40a8a762fe588841`）仍把 D02/D06 ETF 联接排除，与 FL-D132 用户确认冲突。`p6_label.py:301` 明示每合同每规则只取一个目标，append 没有独立站点定位；因此347目标的旧评分不能证明多个正文/摘要/occurrence 全部完成。先前“26可修改/2排除”的表述仅为旧标注器输出，不是已确认业务真值。
- 证据：`tools/evaluation/p6_label.py::fund_type_of/label_case`；D02/D06 原件标题与类别自述；既有 FL-D065/FL-D132 已记录相关限制。本轮尚未读取引擎新预测，发现来自原件/用户政策与标签实现核对。
- 处理：保留冻结标签及旧 scorer，不通过更改 gold/scorer 制造通过；保留旧标签指标但披露资格错误和单规则计数限制。补充独立原件逐站点核验与实际 DOCX/修订/报告对账；未完成该核验不得宣称全部业务正确。当前版本先隔离评测，取得发布条件再部署，修正 ACTIVE_HANDOFF 中先生产发布再评测的不当顺序。
- 状态：已确认，补充核验进行中；pilot-01 的 D01/D02 已真实运行，均 incomplete，失败文件及分母保留。原编号 FL-D186 与并行 favicon 条目冲突，本条改为 FL-D188，旧断点中的“FL-D186 标签问题”均指本条，favicon 的 FL-D186 保持不变。
- 下一步：冻结受控 engine-only 快照，在隔离 API/Worker 上先运行开发集；补齐资格、站点与未标注差异核验，达标后才运行留出并发布。
- 2026-10-24补充：新增 `tools/evaluation/build_revision_review_packet.py`，为20份 dev 生成仅原件阅读材料，并在 pilot-03 读取真实DOCX，保留每一个实际段落差异及来源/产物SHA。D01 19段、D02 18段与既有机械核验的改动地址和哈希完全一致；缺失产物明确unavailable。该工具不改labels/scorer、不输出业务分数，词法候选不能冒充独立gold；全部开发集逐站点业务复核仍待完成，状态不关闭。

## FL-D187 P6 runner 缺少隔离地址、原件校验与中途账本持久化（2026-10-24）

- 问题与影响：runner 硬编码8010、可覆盖旧 run、任务暂停时等至超时且继续提交、只在批末写 batch、下载无哈希；不适合本轮冻结版本隔离评测与故障保留。
- 处理：增加 `--base-url`、新 run 必须不存在、原件 SHA 校验、逐例持久 batch、暂停/超时停止提交及下载 SHA；不变更独立标签或 scorer。
- 状态：已实施并经隔离真实 API/Worker 集成验证。pilot-01 D01/D02 注册、上传、seal、持久 Worker、真实模型、报告及工作文件授权下载成功；两份均业务 incomplete，机械核验2/2通过。runner 的新下载扩展名修复晚于 pilot 快照，旧无扩展名文件由核验器兼容。该工具修复不构成合同业务验收通过。
- 下一步：运行开发集并保存 run_context、共享预算及实际文件，按真实结果补验证。

## FL-D189 G09 clean 路由选到未实现的 template executor（2026-10-24）

- 问题与影响：pilot-01 D01/D02 的 G09 p227 均返回 `RECALL_ROUTED_EXECUTOR_UNAVAILABLE`；Registry 声明允许 TEMPLATE，Router 对 clean 自动升级为 template，但 `_plan_tier1()` 的 G09 仅实现 splice。实际工作文件保留“扣除相应的费用”，Claim Replay 和 Delivery 正确阻断 complete。
- 处理：G09 的 allowed tiers 收敛为唯一已实现的 SPLICE；unsafe 且不能安全拼接时继续阻断，不增加 Compose 猜测。
- 验证：新增 routed `plan_target` → `generate_artifacts` → 重读 DOCX 回归，证明同时写入类别净值与“扣除或加上”两处变更，operation identity 为 G09:0、compose budget=0。Registry/最终核验相关 **106 passed / 7.47s**；扩大定向组合此前 **130 passed / 7.19s**。
- 状态：已实施并经 snapshot-02 pilot-02 双样本真实复测，G09 p227 均已实际修改且无 executor unavailable；snapshot-02 全量 **1221 passed /65 skipped /2 warnings /150.05s**。pilot-01 两份 incomplete 原结果保留，62 HTTP attempts / $0.0646734；pilot-02 61次/$0.06506505，两份仍因其他缺陷 incomplete，机械核验2/2通过，不能宣称业务完成。
- 2026-10-24补充证明收紧：legacy Claim Replay 不再把 `mode=g09_bounded_splice`、`fixed_text` 或 replacement 本身当作授权；从原始edit slice、G09 operation old/new_text（含事实实例化）重新计算 `splice_pairs`/bounded result，并要求与实际 replacement及旧报告fixed_text一致。旧报告无fixed_text仍可重放；伪造模式、替换结果、额外政策及借用另一operation的回归均被 `CLAIM_OPERATION_SPAN_UNAUTHORIZED` 阻断。新增G09 replay回归及相关定向 **56 passed**。尚未对真实合同重新运行。
- 2026-10-24补充验证：G09证明收紧后完整工作区回归 **1317 passed /44 skipped /2 warnings /238.34s**，日志`g09-proof-full-pytest.log`（收集早于后续G15新增测试）。真实target-07 D07原件与旧`working_final.docx`重放，G09:0 p226 `PASS/EXPECTED_EFFECT_PRESENT`，整合同仍`verified=false`且其他9项未证明未隐藏；证据`offline-d07-g09-proof-current/replay.json`。本次为0 HTTP旧产物重放，未新建真实任务或发布。
- 下一步：冻结新快照，先复测D01/D02，再开发集；通过前不宣称发布条件满足。

## FL-D190 Audit 指令要求读取 FACTS 但上下文未传入事实账本（2026-10-24）

- 问题与影响：D01 audit 将原件明确的 A/D 申购费组、C销售服务费组误判为C/D服务费组；`AUDIT_INSTRUCTION` 引用 `[FACTS]`，但 `_audit_context()` 只提供 BEFORE/AFTER/REQUIREMENTS/TARGET_LEDGER/OTHER_AUTHORIZED_EDITS，遗漏已核验事实，诱发按指引示例类别猜测。
- 处理：audit context 显式加入 `facts.as_ledger()`，原事实状态与证据均保留，纳入总字符限制；prompt version 升为 recall_audit_v2，使旧缓存失效。不将模型负面意见直接吞掉或自动判成功。
- 验证：新增穿过 `_run_audit()` 的回归捕获真实模型请求上下文，核对完整事实与两收费组，并验证超长上下文阻断；与FL-D189组合 **106 passed**。新真实评测待执行。
- 状态：已实施并经 snapshot-02 pilot-02 真实复测，D01 G02 audit 已按FACTS正确认可A/D申购费组与C服务费组；本轮无旧收费组错判。D01原sweep矛盾未复现，保留历史证据，不凭文案过滤绕过验证。两份其他未完成原因见FL-D191～193。
- 下一步：真实复测事实传递后的audit与sweep；仍有矛盾则走独立证据复核与可验证恢复。

## FL-D191 晚到的分段类别 target 扩展为相同 operation 但未再次对账（2026-10-24）

- 问题与影响：pilot-02 D01 G02 T3001/T3002 最初分别属于G02:0/1，经p91→p92分段重绑并按已正确类别扩展后都绑定两operation、相同quote与[0,80]，但早期dedupe已结束。Claim Replay按缺失occurrence正确阻断，形成5条unresolved。不能靠删除Claim门禁放行。
- 处理：最终 `_plan_and_generate` 在定位完成后再次dedupe；允许精确相同quote、geometry、composite且同状态的satisfied discoveries归并；显式不同occurrence index与不同物理位置继续独立，未知几何不归并。
- 验证：增加晚到split targets→assign→真实DOCX规划→Claim Replay回归，以及satisfied alias/显式不同occurrence正反例；相关组合 **174 passed /19.78s**。
- 状态：已实施并经 snapshot-03 pilot-03 双样本真实模型复测关闭。D01/D02 均 `completed`、`delivery_status=complete`、`unresolved=0`；真实 DOCX 逐站点补充核验均 **40/40**，下载机械核验 **2/2**。D01 G02 p92 两个 operation 已归并为同一 satisfied occurrence；D02 原本独立的 A/C operation 保持独立。pilot-03 共59次、约 `$0.062185`，原 pilot-02 incomplete 文件保留。
- 下一步：在同一 snapshot-03 和共享 ledger 上完成其余18份 dev，并检查是否有新的跨合同回归。

## FL-D192 G16 payment-head 与 clause-tail 被当作两个追加站点（2026-10-24）

- 问题与影响：pilot-02 D01实际下载DOCX p758/p760及p1221/p1223分别重复写入完整新销售服务费机制；inventory锚定payment head、survey锚定usage tail，paragraph identity不同，现有同段重复检查无法发现同一业务条款跨段重复。机械哈希/修订检查2/2通过不能证明业务正确。
- 处理：最终规划前按原件payment anchor和已有有界 `_g16_clause_end` 统一head/continuation/tail至同一条款尾位置，再按operation/geometry去重；正文摘要和不同支付机制保持独立地址。不得全合同只保留一个追加。
- 验证：新增两份费用条款的真实DOCX，输入每份head+tail四target，最终仅在两个tail各写一次完整机制；纳入 **174 passed**。真实模型结果待验证。
- 状态：已实施并经 pilot-03 真实模型复测关闭。D01 每个正文/摘要费用条款均只在统一条款尾写入一次 G16；D02 两个支付机制位置各写入一次。实际 DOCX 机械核验通过，补充站点核验通过；pilot-02 原重复文件保留，未发布。
- 下一步：其余 dev 与 holdout 继续按实际 DOCX 逐条款计数。
- 2026-10-24 target-07复发：snapshot-07 D18报告`complete/0 unresolved`、Claim Replay=True且四个G16 target均audit completed，但实际p775/p777及p1226/p1228分别出现完整相同新政策，正文/摘要各重复一次。原件p776/p1227以“若遇法定节假日、休息日或不可抗力…支付日期顺延。”开头，随后才是“销售服务费主要用于…”，不满足旧边界的用途段开头条件，导致head/tail未统一。证据：`/tmp/opencode/operation-validation-20261024/target-07/D18/report.json`、`target-07-review-packets/D18.json`。下载机械4/4通过仅证明本次四份文件与计划一致，未检出此业务错误。
- 当前状态：**重新打开，已确认错误complete，修复和验证进行中**；保留pilot-03历史关闭范围，不外推至D18。拟扩充有证据的支付顺延→用途续段边界、统一追加尾，并在Claim Replay按原件完整条款检查跨段重复；正文/摘要及独立支付机制保留独立地址。未达开发集门槛，不运行holdout、不发布。

## FL-D193 G05 planner站点门禁比effect proof宽，误改持有人大会权限条款（2026-10-24）

- 问题与影响：pilot-02 D01 p434/p1100原文“调低赎回费率、调低销售服务费率”被改为两个“调低销售服务费率”；D02 p1162同类“调低全部或者部分份额类别的赎回费率”又被audit要求修改。这些是持有人大会权限/豁免条款，非指引G05份额类别设置条款。effect proof已有窄门禁但planner仅匹配“调低”等宽关键词，导致执行与核验边界不一致。
- 处理：`target_site_ok(G05)` 收敛为份额类别具体设置或增加/增设/变更/停止类别的明确句，允许直接“调整基金份额类别”表述；与effect proof一致，匹配费率词本身不再构成授权。更新旧低层locator夹具补足合法类别设置语境，原gold/scorer不改。
- 验证：两类真实权限句在planner前site guard均拒绝，保留合法设置句与标点splice测试；相关 **174 passed**，`git diff --check`通过。
- 状态：已实施并经 pilot-03 真实模型复测关闭。D01 p434/p1100 与 D02 p1162 等权限/豁免条款在最终 DOCX 中逐字保留；D01/D02 补充站点核验均通过，audit 未再将这些位置作为 G05 必改。D01/D02 均 `unresolved=0`。
- 下一步：其余 dev 与 holdout 继续检查同类权限条款是否保持原文。

## FL-D197 旧 P6 scorer 对真实多类别 G18 使用过窄的冻结标签文本（2026-10-24）

- 问题与影响：snapshot-03 pilot-03 的 D01 真实合同有 A、C、D 三类；原文 G18 为“A类和D类不收取销售服务费，而C类收取销售服务费”，最终 DOCX 按事实改为“A类、D类基金份额和C类基金份额费用收取不同”。引擎 audit、operation effect 与逐站点检查均确认该结果正确，但冻结旧标签仍要求“A类基金份额和C类基金份额费用收取不同”，旧 `p6_score.py` 因此把 D01:G18 判为 `kept`，pilot-03 显示旧口径 13/14，并将完整交付标为 false_complete。该分数不能代表当前多类别业务完整性。
- 证据：pilot-03/D01/report.json 的 G18 audit evidence 已确认 A/D subscription、C service 与最终句；pilot-03/D01/final.docx p785、p1191 均实际为“A类、D类基金份额和C类基金份额费用收取不同”；`supplemental-site-review.json` D01 40/40；下载机械核验 final/redline、接受/拒绝修订、计划对账均通过。
- 处理方法：不修改冻结 `labels.json`、gold 或 scorer；保留原始 13/14 评分及其 SHA，另以实际事实、最终 DOCX、独立站点检查和 Claim/Delivery 证据报告当前版本结果。多类别替换应继续按事实实例化，不能强行回退为标签中的 A/C 文本。
- 状态与验证：**已确认是评测标签口径限制，不是当前 pilot-03 引擎失败**；适用范围为旧标签中要求固定 A/C 文本、而合同存在额外同组份额类别的目标。当前 dev/holdout 仍需同时保留旧 scorer 分数和逐合同业务核验。
- 下一步：开发集完成后在评测报告中分开披露冻结标签分数、实际 DOCX 业务复核结果与受限分母；不使用旧 scorer 13/14 作为发布批准依据。

## FL-D194 React V2 与独立 Compare 页面入口视觉不连续（2026-10-24，已处理待公网复验）

- 问题与影响：用户从 React V2 工作台进入 `/compare` 后会看到独立的旧式 Compare 页面；服务和首页并未回滚，但入口没有说明这是独立页面，容易被理解为整个工作台自动恢复旧版本。
- 证据：生产访问日志连续记录 `GET /` 及 V2 hashed assets 后访问 `GET /compare`，后者返回 `frontend/compare.html` 并加载 `/static/app.css`、`/static/compare.css`、`/static/app.js` 和 `/static/compare.js`；同一时段 `/`、`/tasks` 仍返回 React V2 entry。当前 `AppShell` 原导航仅显示“合同对比”。
- 处理方法：保留 Compare 的独立页面和现有真实对比流程，React V2 导航明确标注“合同对比（独立页）”；独立页面增加“独立合同对比工作台”说明和“返回新版修订工作台”入口，避免把页面差异误认为服务回滚。
- 状态与验证：已实施并完成公网静态入口复验；React smoke **3 passed**，Compare 专项 **70 passed / 5 skipped / 1 warning**，公网 `/` 加载 `index-DrDaSRVK.js`，`/compare` 返回说明、返回链接和 200 响应；工作区与部署文件哈希一致。真实 Worker/模型交付仍由本轮独立验收记录。
- 下一步：构建并受控同步仅包含本次前端静态变更的文件，执行公网浏览器入口复验；若产品要求统一壳层，再单独安排 Compare 迁移，不在本条中改变其业务实现。

## FL-D195 生产浏览器验收脚本的页面断言与任务路由匹配不稳定（2026-10-24，已修正并复验）

- 问题与影响：真实公网验收脚本先后把登录说明误当标题、用 `**/tasks/*` 把 `/tasks/new` 误当任务详情、再用任务详情页即时文案作为终态门槛，导致脚本在不同阶段提前退出。前两次退出均发生在可继续交付前，容易把自动化缺陷误报为产品故障；已创建的任务和账户证据必须保留，不能冒充完成验收。
- 证据：第一次脚本在登录页 `heading='登录合同修订工作台'` 断言失败；第二次 `task_url_after_submit` 为 `/tasks/new`，生产日志仅有注册而无任务创建；第三次及后续运行已真实记录 `POST /api/tasks 201`、上传 `200`、seal `200`，任务 `02418eb488a449a18d59cade45d773ed` 的详情 `GET 200`，但脚本随后在 `assert '任务状态' in body` 退出。任务页源码确有该标题，失败属于页面加载时序/文案耦合。
- 处理方法：登录只检查稳定的 `FundLex` heading；提交后用排除 `/tasks/new` 的具体任务路由正则，并从 URL 最后一段读取任务 ID；详情页只验证任务路由，任务终态由同一浏览器会话的 `/api/tasks/{id}` 和 `/documents` API 轮询决定；每次运行使用独立证据目录，不保存账号密码。
- 状态与验证：脚本已修正并由任务 `70e8148548ec4432a7d68457fd866fb1` 完成真实公网路径复验；登录、任务创建、上传、seal、Worker/model、详情、Review、报告和授权下载均通过。账号密码未写入证据。
- 下一步：完成新的公网临时账号路径，保存任务/文档状态、Review 页面、final/redline/working/report 下载，核对 DOCX ZIP、ins/del、源文件差异及报告哈希；失败或 incomplete 必须按真实结果登记。

## FL-D196 生产浏览器验收脚本自定义 API 请求遗漏 Bearer 会话（2026-10-24，已修复并复验）

- 问题与影响：React API client 会从 `sessionStorage['fundlex-auth-token']` 自动发送 `Authorization: Bearer`，验收脚本为轮询任务和下载文件而直接调用页面 `fetch`，没有复用该请求头，导致真实任务已创建并封存后，轮询收到 401，脚本无法继续到 Worker、Review 和产物核验。
- 证据：生产日志记录新任务 `5f24b5c441be4d0997e1ce5632b40884` 的注册、`POST /api/tasks 201`、上传 `200`、seal `200`；脚本紧随其后的 `GET /api/tasks/5f24b5c441be4d0997e1ce5632b40884` 返回 `401 Unauthorized`，同一时间 React 页面请求带会话的任务读取返回 `200`。此前运行输出为 `RuntimeError: task status HTTP 401`。
- 处理方法：自定义 `browser_json` 与 `browser_download` 从当前页面 sessionStorage 读取 `fundlex-auth-token`，同时保留 dev 模式的 `X-FundLex-User` 兼容头，再发起轮询、报告和下载请求；脚本编译检查通过。
- 状态与验证：已修复并由任务 `70e8148548ec4432a7d68457fd866fb1` 复验；同会话任务轮询、报告和下载均成功，账号密码未写入证据，任务和实际失败分母保留。
- 下一步：保留本次 `incomplete` 交付的 G09 p224 例外；引擎完成独立评测和发布后重新执行完整交付验收。

## FL-D198 生产浏览器验收脚本将详情/Review 页面文案当作加载完成条件（2026-10-24，已修正并复验）

- 问题与影响：真实任务 `15fe639652a0425eba26d6f012c6728f` 已由 Worker/model 完成，任务状态为 `completed`，文档为 `succeeded/incomplete`，详情页和 Review 所需的 `/revisions` API 均返回 200；脚本仍因瞬时页面正文没有出现“修订复核”而退出，阻断了后续报告和授权下载核验。详情页的“交付概览”断言也属于同一类异步文案耦合。
- 证据：本次保存结果 `/tmp/opencode/fundlex-production-v2-e2e-20261024/e2e-nwgc06n6cue0/result.json` 记录等待 203 秒、33 个目标完成 32 个、1 个未解决、详情页路由阶段已到达；生产日志记录文档读取、报告读取、文档列表和 `/revisions` 均为 200。失败栈为 `assert '修订复核' in page.locator('body').inner_text()`。
- 处理方法：详情和 Review 入口均改为验证 task/document scoped URL，并通过同会话认证请求文档、报告和 `/revisions` API 返回 200；Review API 还要求返回修订列表。页面文案只作为观察信息，不作为异步加载完成条件。
- 状态与验证：脚本已修正并通过 Python 编译检查；任务 `70e8148548ec4432a7d68457fd866fb1` 已完成详情路由、Review 路由与 revisions API、报告和授权下载核验。页面文案不再作为异步加载完成条件。
- 下一步：完成工作文件、报告下载，检查 DOCX ZIP/修订 XML、源到工作文件差异及报告 SHA；对 1 个未解决目标保留明确例外说明。
- 编号变更记录：本条最初与旧 P6 scorer 问题共用 FL-D197；2026-10-24 保留先登记的 scorer 为 FL-D197，将本条消歧为 FL-D198，历史聊天中的生产页面文案 FL-D197 均指本条。

## FL-D201 Review 文档呈现器把 HTML void 元素传入 children 导致 React #137（2026-10-24，已修复并公网复验）

- 问题与影响：生产 Review API 返回的安全合同 HTML 可能包含 `<hr>`。`DocumentViewer` 将所有允许标签统一通过 `createElement(tag, props, children)` 渲染；React 19 禁止 void 元素带 children，因此 Review 页面抛出 `Minified React error #137; args[]=hr`。API、报告和下载链路仍可成功，但正式复核页面存在真实渲染错误。
- 证据：旧任务 `85bddb11a5c64439b05bb5c103a63d75` 的保存结果 `/tmp/opencode/fundlex-production-v2-e2e-20261024/e2e-4688nid6dp6g/result.json` 记录 `review_api_ok=true`、`review_revision_count=18`，但 `page_errors` 含 React #137，参数为 `hr`；修复后的任务 `70e8148548ec4432a7d68457fd866fb1` 结果 `/tmp/opencode/fundlex-production-v2-e2e-20261024/e2e-12d1e3tfq98g/result.json` 记录 `page_errors=[]`、`console_errors=[]`。
- 处理方法：在 `frontend/src/components/document/DocumentViewer.tsx` 增加 HTML void tag 集合；对 `<hr>` 等元素只创建无 children 的 React element，同时保留安全属性过滤和 revision marker 处理。新增浏览器回归注入 `<p>…</p><hr><p><ins …>` 的真实 revisions 形态。
- 状态与验证：TypeScript、ESLint、Vite build 通过；React 浏览器 smoke **4 passed**；任务 API + 前端组合回归 **31 passed / 1 warning**；构建入口使用 `index-BUWdg2p2.js` / `index-BCmLwO6a.css`，工作区、部署目录和公网 JS SHA 一致。新前端公网真实路径已确认 `page_errors=[]`、`console_errors=[]`。
- 下一步：引擎 G09 未完成仍需按独立评测和发布门槛处理。

## FL-D202 生产任务只开放工作文件时验收脚本误报 final/redline 哈希失败（2026-10-24，已修复并脚本复验）

- 问题与影响：`delivery_status=incomplete` 时服务只开放 `working_final` 与 `working_redline`，报告仍以 `final_sha256`/`redline_sha256` 字段记录这两个工作文件的哈希。脚本只按下载 kind 查找 `final`/`redline`，把“授权文件不可用”误记为 `false`，掩盖了工作文件真实哈希一致。
- 证据：生产任务 `70e8148548ec4432a7d68457fd866fb1` 的报告 JSON/Markdown SHA 为 `a6d86a200eef81d82b55274047f5b4a79c19294b13a407c7e7a30064b172e16b` / `b86a864acd9d1d2665c7f5a4c8a47dfc863fc09b6d625fa303f27231b3db568f`；报告中的 `final_sha256`/`redline_sha256` 与下载的 `working_final`/`working_redline` 完全一致，独立 `verify_downloaded_artifacts.py` 机械检查通过。
- 处理方法：验收脚本按逻辑 final/redline 选择授权的 primary kind 或 incomplete 状态下的 working fallback，分别输出 `hash_checks` 和带 `matched/unavailable/mismatch` 状态的 `artifact_hash_checks`；同时保留未提供 final/redline 的事实，不把工作文件冒称最终合同。
- 状态与验证：代码已通过 Python 编译和 diff check；新公网运行的 `result.json` 确认 `hash_checks.final=true`、`hash_checks.redline=true`，且 `artifact_hash_checks` 明确记录实际下载类型为 `working_final`/`working_redline`、状态为 `matched`。当前真实业务仍为 `incomplete`，G09 p224 例外必须继续保留。
- 下一步：引擎完成正式发布后重新验证完整交付，并确认授权的 `final`/`redline` 文件出现；当前工作文件不冒称最终合同。

## FL-D199 删除残留恢复分支引用未绑定的 operation 变量（2026-10-24）

- 问题与影响：snapshot-03 在真实开发集 D03 的最终残留文本恢复阶段执行 `delete_indices` 的显式 operation 过滤时，列表推导使用了作用域外的 `operation` 名称，Worker 抛出 `NameError`，任务为 `PROCESSING_FAILED`、`delivery_status=not_generated`，整批 dev-03 在 D03 中止。该错误发生在已有真实模型调用之后的 Claim Replay 恢复路径，失败报告中的空计量不能据此理解为零次调用（见 FL-D200）。
- 证据：`dev-03/D03/report.json` 记录 `engine_build=515e0e08…`、错误阶段 `worker`、错误名 `NameError`；复制快照的 traceback 复现位置为 `fundlex/recall_pipeline.py:3888-3890`。使用 D03 已保存的 70 条成功 checkpoint 响应进行无网络回放，原 snapshot-03 在同一行稳定重现；回放未发出 HTTP 请求。
- 处理方法：新增 `_residual_delete_indices()`，在一次枚举中同时检查 `op=delete`、适用条件和声明的 `operation_id`；无 identity 的 legacy 残留只在唯一适用删除 operation 时继续，多个候选保持 fail-closed。恢复路径改用该 helper，避免引用未绑定循环变量及兄弟 operation 借权。
- 验证：新增 operation identity、条件、非 delete 和 legacy 唯一性回归；定向 **173 passed**，全量 **1266 passed /44 skipped /2 warnings**，`git diff --check`通过。修复快照无网络回放越过原 NameError；因原失败运行在 sweep 前结束，后续一个 sweep 请求没有保存响应，回放在该预期缺口处停止。
- 状态：**已实施并离线验证，待 snapshot-05/dev-05 真实 D01–D20 重跑确认**。snapshot-03 的失败批次、debug-d03 和成本记录保留，不覆盖。snapshot-05自身全量离线回归1234 passed /65 skipped /2 warnings /157.09秒；运行后源码manifest核对无变化。
- 下一步：以新 build 完整重跑20份 dev；若达标，再冻结 holdout 候选并运行8份留出。
- 变更记录：原 `snapshot-04/dev-04` 因冻结脚本从 HEAD 取回旧 API/tasks，实际 D01 已运行、D02 尚未完成后被主动停止；该批次保留但不计入单一版本评测。随后改为从已审查的 snapshot-03 显式继承并只覆盖 recall_pipeline，形成 snapshot-05。

## FL-D200 Worker 失败摘要覆盖了模型计量，导致单次运行成本需回到账本核对（2026-10-24）

- 问题与影响：Worker 捕获未分类异常时写入简化失败 `report.json`，只保留异常类型，不保留管线在异常前累计的 model metrics。D03 `result.json` 因此显示 `calls=null`、`cost=null`，而共享 ledger 实际从 216 次/$0.21015375 增至 248 次/$0.22743105；若只读失败报告，会低估真实预算和失败尝试。
- 证据：`dev-03/D03/result.json` 的 model 字段为空值；`debug-d03` 真实 Worker traceback 与共享 `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 汇总相互印证。该批次没有最终 DOCX，但 debug 重试产生的真实模型请求和成本仍计入总账。
- 处理方法：当前评测按共享 ledger 作为权威累计账本，保留每轮 run 目录和失败分母，不用 result.json 的 null 计量宣称零成本。后续应在 Worker/管线边界补充安全的失败计量落盘，不写入凭据或模型响应敏感内容。
- 状态：**已确认，计量修复尚未实施**；不阻断本轮继续评测，但阻断只依据单份失败报告计算预算或成本指标。
- 下一步：在 snapshot-05 真实重跑后，为失败路径补充不改变交付门禁的 model metrics 持久化回归，再重新核对总账；修改后须重新确认其对最终冻结build及评测资格的影响。
- 变更记录：snapshot-04 的无效批次在 D01/D02 中止时累计账本已纳入总账；后续使用 snapshot-05 和独立 data-05 继续，避免旧任务状态污染新批次。
- 2026-10-24实施：`process_recall_first()`在已分类/可恢复异常之后捕获普通未分类Exception，返回`PROCESSING_FAILED`/qualification failed并调用原失败产物门禁；finally保留model metrics、耗时和报告写入。异常只记录类型，不记录异常消息。新增`test_pipeline_failure_metering.py`的NameError/RuntimeError真实Worker持久化回归，检查实际授权report_json的HTTP/token/cost、failed状态、无正式产物和无异常私密内容；组合 **82 passed /1 warning /33.45s**。snapshot-07已包含修复，失败后保留计量的离线边界已验证；未模拟真实付费故障，不新增模型成本。

## FL-D203 评测快照从 HEAD 排除 API/tasks overlay 导致外围版本回退（2026-10-24）

- 问题与影响：临时构建脚本 `prepare()` 从HEAD archive起步，并将dirty `fundlex/api.py`、`fundlex/tasks.py` 排除在overlay之外。snapshot-03已经使用当前生产API/tasks，重建snapshot-04却带回旧版本，丢失task-scoped详情/Review/下载等契约；即使引擎修复正确，也无法代表现有生产工作台候选。
- 证据：`release-candidate-04.json`及03→04文件比对显示除预期recall_pipeline之外还变化API/tasks；snapshot-03、工作区与生产这两文件哈希一致，snapshot-04不同。dev-04已完成D01、D02未完成时主动停止；所有产物及费用保留，不计入dev-05资格分母。
- 处理方法：本轮用 `freeze_snapshot_05.py` 从已审查snapshot-03显式继承，仅overlay `fundlex/recall_pipeline.py` 和对应测试；断言唯一引擎源码变化为recall_pipeline且API/tasks与生产字节相同。新run_context-05保存完整manifest；独立data-05隔离遗留任务，共享原ledger。
- 状态与验证：**本轮快照已修正并验证，通用prepare构建器尚未产品化修复**。snapshot-05完整manifest核验无变化；API/tasks与生产一致；全量离线1234 passed /65 skipped /2 warnings。`release-candidate-05.json`只读差异为5个引擎文件，没有发布操作。
- 下一步：后续冻结继续使用显式父快照/overlay与生产契约断言，禁止再用旧prepare默认行为取得发布资格；待dev/holdout通过后按文件审查受控发布。

## FL-D204 G15 合同措辞变体被判不适用后，Sweep 残留未恢复为 operation target（2026-10-24）

- 问题与影响：D01 的 p758、p1221 均保留销售服务费支付机制。原始 G15 target 因合同使用“基金销售服务费每日计提，逐日累计至每月月末……”而不是 guide 的 `old_text`，被 inventory 标为 `not_applicable`；最终 Sweep 已在两个真实业务站点确认 `residual_old_text`，但 recovery 排除 `absent` target，随后把 finding 路由为 `SWEEP_TARGET_UNBOUND`，没有把已确认的变体绑定到 G15:0，最终产生 `CLAIM_OPERATION_NOT_PLANNED`。
- 证据：修复前 snapshot-05 的 `/tmp/opencode/operation-validation-20261024/dev-05/D01/report.json` 记录 G15 p758/p1221 target `state=absent`、`status=not_applicable`，Sweep `SW008`/`SW010` 为 `residual_old_text`，最终 delivery `incomplete`、8 unresolved；`/tmp/opencode/operation-validation-20261024/dev-05/supplemental-site-review.json` 记录 G15 两项失败，实际 DOCX 中仍分别存在完整变体条款。D01 下载产物独立机械核验通过，故问题是业务残留恢复与 operation attribution，不是 ZIP、哈希或修订文件损坏。
- 处理方法：`_absorb_sweep_findings()` 在 finding quote 已通过 source binding、且规则只有一个适用的 delete/replace operation 时，使用该唯一 operation identity；对同地点的 `absent/not_applicable` inventory target 保留原记录以供追溯，标记其被 sweep variant superseded，并创建 source-bound `needs_edit` synthetic target。多 operation 或无法唯一归属时继续 fail-closed。新增真实措辞形态的回归测试，验证 synthetic target 为 resolved 且绑定 `G15:0`。
- 状态与验证：修复已实施；相关 Sweep/Claim/最终校验定向 **109 passed**，新增边界回归后 Sweep/Claim/targeting 专项 **58 passed**、Sweep recovery **7 passed**，`py_compile` 与 `git diff --check` 通过。修复发生在 snapshot-05/dev-05 启动之后；修复后 `snapshot-06` build `e53c8585514470019ff2b7890aed1f407573f9574d00abe8b23a72d8a1b0a568` 全量离线回归 **1236 passed /65 skipped /2 warnings /148.62s**，但尚未运行真实合同，当前 dev-05 不能验证该修复；必须以 snapshot-06 重跑完整 20 份 dev。当前无生产发布。
- 下一步：待 dev-05 旧快照完成后保留其失败分母与费用，冻结包含 FL-D204 的新 build，完整重跑 D01–D20；对 D01/D03 及其他 G15 站点实际 DOCX 做业务复核，确认删除残留、G16 合并机制和报告/哈希一致后，才决定是否进入 holdout。
- 2026-10-24终态补充：dev-05全部20任务结束，本轮634 HTTP/$0.63333525，总账916 HTTP/$0.89509440；下载机械20/20。D01两处旧支付条款仍存（补充38/40），与修复前预期一致；snapshot-06尚未真实复测。

## FL-D205 G12多句替换缩为首句且残留核验漏掉旧政策，导致错误complete（2026-10-24）

- 问题与影响：dev-05 D17报告complete、unresolved=0，但实际p207在新“赎回费用全额计入基金财产。”后保留“赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示；”。新旧政策并存，不能交付最终合同。
- 证据：`/tmp/opencode/operation-validation-20261024/dev-05/D17/report.json`的G12:0 target quote覆盖两句，最终start/end却为0/40，仅首句被替换；G13:0独立删除74–122短期赎回费句。`dev-05-review-packets/D17.json`保存实际前后差异；audit错误将残留比例句归入G13授权内容。旧P6仍把D17算通过且false_complete=0，说明旧评分漏检。
- 处理方法：拟修定位在标点差异下过早逐句回退的问题，恢复operation自身完整授权范围；operation effect按实际原件与新文核查被替换的旧政策子句残留，不能只找完整old_text。补实际DOCX、Claim Replay、合法余文及G13不得借权回归，禁止用扩大到整段删除代替业务边界。
- 状态与验证：**已确认，修复中，未验证**；冻结snapshot-05原失败文件保留，生产未发布。尚不宣称D02/D16以外合同业务通过，整批仍未达留出门槛。
- 下一步：离线复现→局部修复/回归→重新冻结→真实定向及完整开发集；指标披露至少1份已确认错误complete，完整业务分母审核仍待完成。
- 2026-10-24实施：`resolve_quote()`在逐句回退前优先匹配仅末尾句号/分号不同的完整原文；Claim Replay和effect closure将该引文映射为真实原件标点。replace effect新增按原件确实存在、且不在自身new_text中的完整旧政策子句核查，避免首句替换后整段literal消失掩盖残留。新增`tests/test_replace_clause_closure.py`的9项真实DOCX回归，含合法计算余文和G13独立未删必须失败。组合**225 passed /20.79s**。20份dev-05真实下载产物0 HTTP离线Claim重读：D17由True→False，G12:0 p207明确`RESIDUAL_OLD_TEXT`；D02/D16通过保持，原失败均仍失败，证据`dev-05-clause-closure-replay.{json,log}`。全量离线测试运行中；真实模型修复后复测尚未进行，本条仍未关闭。
- 2026-10-24全量：FL-D205修复后工作区完整离线**1278 passed /44 skipped /2 warnings /236.07s**（`clause-closure-full-pytest.log`）。该全量先于后续FL-D207修改，须分开披露。

## FL-D206 G15正文摘要尾句及重复支付条款删除不一致（2026-10-24）

- 问题与影响：dev-05 D03 p1219仍保留“若遇法定节假日、公休日等，支付日期顺延。”，正文p751副本结果不同；D05原件p868/p1332完全相同，前者删空，后者保留自动扣划后核对句，均为incomplete。
- 证据：`dev-05/D03/report.json`、`dev-05/D05/report.json`及对应`dev-05-review-packets/*.json`；Claim Replay的RESIDUAL_OLD_TEXT/DUPLICATE_SITE_DIVERGED保留阻断，机械核验通过。
- 处理方法：待核对guide完整删除授权与跨句/跨段绑定，统一同一业务条款的完整删除范围，正文摘要保持各自站点；不关闭一致性门禁以制造通过。
- 状态与验证：**已确认，未修复**。2026-10-24尝试扩展survey句尾及parts后发现compact offsets不能直接作为原始DOCX地址；局部重建未产生G15 edit，不能作为修复证据，该轮G15试改已撤回。D03原件p751/p1219全文相同，原target分别覆盖133/113字符，后一处遗漏顺延句；D05原件p868/p1332全文相同，target分别覆盖139/102字符，差额为自动扣划后核对句。D05独立核对句删除授权尚需明确，不将其自动并入G15。
- 下一步：针对D03已绑定payment slice后的明确顺延尾句作原始地址内的有界补绑；D05保持OPEN，继续核对完整机制与独立核对句授权。修复后仍须真实Worker/模型与实际文件复测。
- 2026-10-24后续窄修复：保留前次survey/parts试改撤回结论；本次在`plan_target()`原始地址绑定后，仅对单个G15 delete、其自身old_text明确授权支付顺延、quote与实际slice一致、slice已包含销售服务费每日计提/计算和按月支付时，补绑定**紧邻一个完整“若遇…支付日期/时间顺延”句**。不跨独立核对句、管理费/赎回款顺延句，不把compact offset作为raw offset。新增`tests/test_g15_payment_delay_boundary.py`含真实DOCX双副本删除、句后核对保留、其他机制/自定义无顺延授权反例与零compose预算；相关**170 passed /32.90s**。
- D03实际原件局部重建：`offline-d03-g15-raw-current/`，只选择G15，复用dev-05真实targets及已记录facts，0模型请求；p751/p1219均生成0–133删除，其他段落逐段原样，Claim Replay `verified=true`；final SHA `70e67bb4cc9e5bf8d8011acf3744170a958a375b45c30b1218c8ecdba0087f93`、redline SHA `3a30c4653a0d167dfbbf323647546cd425180db00d9aefa18bdc564148a0d2b1`。属于**D03局部已实施、离线已验证**，D05删除核对句授权仍OPEN，整合同真实复测未完成；本条不关闭。
- 实际修订核验：`offline-d03-g15-raw-current/revision-checks.json`确认接受redline等于final、拒绝redline等于原件，两项均true。含D03窄修复与FL-D213全量已结束：**1325 passed /44 skipped /2 warnings /240.20s**（`g15-raw-boundary-full-pytest.log`）；该结果不覆盖随后D05收窄/`bounded_delete`修改。
- 2026-10-24 D05增量：新增`_g15_payment_clause_end()`识别支付顺延句末、将过宽target收窄至raw 102，`bounded_delete`保留102–139独立核对句。10项G15、相关组合**163 passed /33.54s**，compileall/diff check通过，尚未新全量。实际组合文件`offline-d05-g15-g17-current-proof/`确认p868/p1332核对句均保留、修订接受/拒绝等价；但p869/p1333 G17仍残留且Replay错误PASS，另登记FL-D214。该文件不是组合通过或正式交付，核对句保留方案尚待真实整合同复测与业务验收。
- 2026-10-24真实target-08验证：D03两处G15完整删除，D05 p868/p1332独立核对句均保留一次；下载机械均通过，D05定向18/18。此范围已真实验证；D18跨段残留另登记FL-D216，本条不能据D03/D05局部通过扩展为所有G15合同完成。

## FL-D207 跨段份额定义的append落在未完句中（2026-10-24）

- 问题与影响：dev-05 D07 p112原文停在“将基金份额分为 A”，续文位于下一段；实际在此插入“。投资者通过直销机构…”造成份额定义断裂。实际类别A/Y且无销售服务费，部分sweep的C类意见还需独立核对。
- 证据：`dev-05-review-packets/D07.json`中的p112前后文本与相邻原文，`dev-05/D07/report.json`记录44 unresolved。
- 处理方法：拟将完整逻辑定义跨段绑定后在定义末端追加，保留原类别及收费事实；无证据不套固定A/C或凭sweep意见改事实。
- 状态与验证：**已确认，未修复**；incomplete工作文件保留，不作为最终交付。
- 下一步：核对定义跨段全范围，补多类别/无服务费事实与实际DOCX追加回归并真实复测。
- 2026-10-24实施：新增有界`_split_definition_end()`，仅由真实定义锚点和字母→“类”等词法衔接启动，继续跨读未结束的类别账户限制句，最多6个后续段；`rebind_split_append_targets()`在最终规划/去重前及单目标planner中把G01/G03追加点移至同一定义尾，site guard继承原锚点。裸字母且无可信续文时保持`RECALL_APPEND_CLAUSE_INCOMPLETE`。新增5项回归，实际生成/重读final与redline，核对p0/p1原文和账户限制完整、追加只落p2、无关p3保留；**5 passed /1.93s**，规划/管线/闭环组合**220 passed /约42s**。真实模型复测尚未进行，本条未关闭。

## FL-D209 类别替换与固定措辞/语义变体核验仍存在业务范围或事实实例化缺口（2026-10-24）

- 问题与影响：dev-05 D06的G02/G04额外定位到申购费/销售服务费支付条款，D19的G02与G18在p1186重叠阻断；D04/D12的G09分别在扩展币种/“扣除其他相应费用”变体中未落实“或加上”；D10/D14/D15出现G01/G03/G08/G11/G14/G16站点或effect证明缺口。可能同时包含真实漏改、错误定位、固定A/C实例化及模型误拒，不能将unresolved直接等同全部真实漏改。
- 证据：`dev-05/D06/report.json`的G11:1 `LOST_PROTECTED_LITERAL`（E/F类别）、D19 p1186的`RECALL_EDIT_OVERLAP`；D04 p194/D12 p220 `CLAIM_OPERATION_EFFECT_MISSING`；相应原件和全部实际diff在`dev-05-review-packets/`。D10/D14 G16审计说只剩尾句，但该段未出现在actual_changes中，必须检查相邻段而不能直接采信该意见。
- 2026-10-24 target-17 D04 G12补证：p198模型compose输出逐字等于G12固定新政策，但program_check以`LOST_PROTECTED_LITERAL`拒绝删除原比例25%（原件还含7日/1.5%）。缓存`7d5db532eeb1ef26cf80f48cafeddcb62eb7f1466ea9942b602aafa31ff241e0.json`保留原输出；p198实际仅G13删除短期收费句，旧25%/登记手续费分配仍在。应按原件与G12自身operation独立证明合法比例变体，而非取消数字保护或让provenance自授权。尚未修复，仍计入完整目标分母；不把模型正确输出当实际完成。
- 处理方法：逐站点按guide、原件实际类别与完整条款重新审查，按operation自身授权校验；保持证据不足时fail-closed，不放宽门禁或修改gold制造通过。
- 状态与验证：**已登记，细分原因与业务复核中，未修复**。不能以214/236旧评分代替本条业务验收。
- 下一步：完成全20份原件候选/差异业务审查，分列真实误改漏改与误拒，再逐类修复和局部真实复测。
- 2026-10-24 D07复核更正：target-07 G04 p140两个quote分别为“A类不得对个人养老金账户销售”“Y类仅面向个人养老金账户销售”，是账户销售限制，不是收费组。原件并无C类，该目标的G04:1归属不成立；不能通过消除occurrence歧义把养老金限制替换成A/Y组。现将G02/G04规划与assign的site guard统一为须有收费语境，直接planner也拒绝该段；错误目标out_of_scope不等于G04 obligation完成，未有合法站点证据仍保持OPEN。另修`resolve_occurrence()`：唯一逐字引文内只有一个token时采用其原始地址，避免相邻token的24字窗口跨入同一引文导致误判平分；重复引文/多个token仍拒绝猜测。
- 同轮G05 p142：target只绑定“调低赎回费率”，遗漏自身operation授权的前导“、”，使确定性删除未匹配后落到compose，v3错误要求空AFTER保留段外余文。现在仅在G05合法类别设置站点、operation为delete、原始slice恰为去掉顿号的完整old_text时，绑定包含原slice的唯一完整literal；执行器保留段外文字，删除与独立备案operation分别归属。含真实DOCX及空格变体、会议条款保留的组合回归110 passed；全量运行中，尚无修复后真实模型复测。本轮渠道事实仍UNKNOWN，不据“可以豁免”推断收费现状。
- 2026-10-24真实target-08 D07：incomplete/18 unresolved，46 HTTP/$0.04773180。机械通过，账户限制保留、G05两删除及G09费用正负修改实际生效。原补充检查将p140整段“不变”作为要求是检查器错误，G03合法追加应允许原文前缀完整保留，已修正该开发辅助断言；未改冻结gold/labels/scorer。G01/G03 audit仍要求不存在的C类服务费文案，需要核对适用组件输入，不能据此补造C类。另发现facts用管理费0.90%/0.45%引文认证A/Y的subscription_fee=true，仅逐字引文存在不足以证明申购收费，待证据认证修复；渠道仍UNKNOWN。其余operation未证实仍保持阻断，不关闭本条。
- 2026-10-24审核输入修复已实施、待真实验证：`_audit_context()`保留完整原始REQUIREMENTS，同时按operation_id提供`APPLICABLE_POLICIES`（condition_status、policy_status、适用新文与issues）；仅认证了类别全集和收费组才可READY，UNKNOWN/CONFLICT不得把空组当不存在。audit提示升v3，明确按实际类别及已认证的组件省略审核，不能凭READY视为文件已执行。A/Y四规则、UNKNOWN/CONFLICT反例及相关组合162项通过，完整回归运行中。**管理费引文认证申购收费缺陷尚未修复**，不得仅凭本审核修复称D07完成；原件p225/p227/p229确有自身申购收费条款，但p229仅“可以豁免Y类”，不能认证当前渠道豁免。
- 2026-10-24收费事实入口已加证据校验（待完整回归与真实验证）：`facts_from_value()`调用既有`fee_evidence.fee_value()`独立核对每类quote中的申购/销售服务费极性，记录`fee_polarities`和`FEE_QUOTE_UNPROVEN/CONFLICT`；类别全集认证与收费值认证分离，管理费quote可以证明类别存在但收费组保持UNKNOWN。原始布尔值与引用保留供恢复，不把缺失值改成false，不把UNKNOWN当空组；明确反向证据保持CONFLICT，恢复合并携带证据结果。17项事实/恢复定向通过，当前全量日志`fee-evidence-current-full-pytest.log`运行中；此前1396 passed/44 skipped/2 warnings/283.59s只覆盖G01边界＋audit输入修复。
- 2026-10-24全20份旧回答重认证诊断（零模型、非真实交付）：`fee-facts-current-recertification.json`重读原件，D07/D10/D14/D16收费组从VERIFIED变UNKNOWN，其他原VERIFIED未降级；说明既有字面引文匹配曾过度认证。此文件不修改冻结标签、gold或scorer。**证据不足的错误认证入口已实施拦截，四份的正面补证恢复仍未完成**，不能把更严格拒绝当作召回和整合同完成。
- 2026-10-24补证接口完善：`ClassFact`与FACTS/恢复schema增加可选`subscription_quote`、`service_quote`，分别逐字回查并验证自身收费极性；原`quote`兼容保留，不拼接不同段落伪造连续证据。facts提示v5、恢复提示v2；既有`fee_evidence`补“认申购”缩写。157项相关回归通过，后续另加费率决定不能证明收费的反例、30项事实/audit回归通过。`fee-separate-positive-offline.json`在真实D10/D14分别补其已有两条原件引文、D16保留原引文后恢复收费组VERIFIED；均零模型，不能冒称真实重提取或任务交付。D07仍缺无服务费的正面证据，保持UNKNOWN，尚未真实复测。
- D07原件证据复核：p134“本基金具体认购费率按招募说明书的规定执行”、p142“变更现有基金份额类别的申购费率”只说明费率由外部文件/未来程序决定，不能证明当前A/Y收费布尔值；p140类别句只规定个人养老金销售限制，不能认证销售服务费不存在。该结论为原件业务证据边界，不是代码拒绝误报；待取得招募说明书或合同中的明确收费条款后再恢复，不凭空补证。
- 2026-10-24 D04/D12 G09证据更正：逐字复核`dev-05-review-packets/D04.json` p194实际after，已包含“当日该类基金份额的基金份额净值并扣除或加上相应的费用”，人民币元单位及前后费率、四舍五入/精度/损益余文完整，故本条首段把D04与D12并列描述为未落实“或加上”不准确；D04属于旧Claim证明/币种变体误拒线索，不是该处实际漏改。D12 p220实际仍“并扣除其他相应的费用”，仅修净值名词，属于确认的真实不完整。应分别处理证明误拒与缺少“其他相应”变体，保留历史文件和未完成分母。
- 2026-10-24完整旧产物Replay新增证据：`g09-d04-d12-readonly-full-replay.json`以完整plan重放，D04/D12整合同均false，但各自`G09:B1:O1`均PASS。D04实际正确；D12缺少“或加上”仍PASS，属于生成器部分splice与Replay共享不完整预期的缺口，另登记FL-D220。早期仅G09 edits对完整产物的诊断产生无关outside-span失败，不能作为本结论证据。

## FL-D220 G09仅完成净值名词替换却被Replay认证完整（2026-10-24）

- 问题与影响：D12 dev-05 p220原件“并扣除其他相应的费用”不匹配既有费用变体，`plan_g09_splice()`只改净值名词仍返回结果。Replay重算同一部分结果后认定EXPECTED_EFFECT_PRESENT，实际文件缺少政策要求的“或加上”。
- 证据：`/tmp/opencode/operation-validation-20261024/g09-d04-d12-readonly-full-replay.json`；D12实际working_final.docx与完整报告plan，G09 obligation错误PASS，整合同false。D04人民币元变体实际正确，不能并列为漏改。
- 处理方法：补原件费用变体，同时要求G09自身所有费用方向/净值效果完成后才返回确定性结果；Replay对旧部分输出必须拒绝，不能以可重现部分变更替代完整effect。
- 状态：**已确认，修复与验证待完成**。不改gold/labels/scorer，不删除旧失败。
- 下一步：真实旧文件反例、完整变体与余文保留回归→全量→新冻结真实复测。
- 2026-10-24 target-13真实验证：snapshot-13 D03使用修复版真实Worker/模型完成，37 HTTP、$0.03161985，40 targets/52 unresolved，机械下载1/1通过。原件p210实际已完整变为“当日该类基金份额的基金份额净值并扣除或加上相应的费用”，Claim Replay PASS；因此FL-D220的G09部分splice缺陷在该真实样本验证解决。final SHA `5810c37e6d3922ad0779682938782653637b068a0ed06dd4a324d28d49b1a06c`，redline SHA `214ea725352452d9df99b393e3d841066229f62f9970c32d735ed2d33083b3ea`。整合同仍因其他事实/目标失败，不能将该单点验证扩大为D03或开发集通过。
- 状态更新：**G09完整effect修复已真实验证，历史失败和整合同分母保留**。

## FL-D221 新收费证据认证在D03真实复测中未恢复明确收费组（2026-10-24）

- 问题与影响：snapshot-12 target-12 D03从旧complete退为incomplete/39 unresolved，52 HTTP/$0.05397930。A类subscription_quote未逐字匹配；C类service_quote的费率句也暴露了解析器对“的年费率”形式的缺口。
- 证据：`target-12.log`、`target-12/D03/report.json` facts.fee_polarities/quotes_verified，源p118/p211/p747。A类历史引文省略了原文p211开头的“4、”，严格来源校验拒绝是正确行为；C类原文明确为0.40%计提但旧解析结果为UNKNOWN。共享账本1319 HTTP/$1.25193945，无reserved，旧失败产物保留。
- 处理方法：保留逐字来源和缺失/相反证据UNKNOWN/CONFLICT门禁；补充“申购费用由投资人承担”正面极性和“销售服务费按…0.40%的年费率计提”解析，并加入重复类别主语/正反例回归。不把历史模型漏引文改成认证通过。
- 状态：**解析修复已实施，局部156项回归通过，真实复测待完成**；G01位置已由target-12实际文件核验，target-12不是完整交付。
- 下一步：全量回归、重新冻结和真实D03复测；新批次必须提供原件完整收费引文后才能判收费事实恢复。
- 2026-10-24 target-13真实验证：模型仍返回省略p211原文前缀“4、”的A类`subscription_quote`，严格来源校验继续将`subscription_fee_group`和`service_fee_group`判为UNKNOWN，G08/G11/G16/G22未执行，D03为incomplete。该结果证明门禁没有放宽；target-13 facts中C类0.40%服务费句已被当前解析器识别为正面，但整体收费组仍因A类引文不完整而未认证。新增来源驱动编号引文修复及DOCX回归已实施，当前定向147 passed，尚未经过真实Worker/模型复测。
- 状态更新：**旧解析缺口已修复并在target-13前的离线版本验证；编号引文恢复待完整回归及新真实批次验证**。

## FL-D222 G17删除与同一费用条款G16追加发生实际交付冲突（2026-10-24）

- 问题与影响：target-12 D03真实产物中，G17在p752/p753及摘要p1221删除原费用使用句，G16本应在同一费用条款追加销售服务费计提、直销返还、其他销售机构支付和持有期返还政策，却将p753/p1221整段删除。G16定向核验16处中14处通过，p751/p1219完整政策计数失败；报告仍为incomplete/39 unresolved。
- 证据：`target-12/D03/report.json`中G17 T018/T019、G16 T017/Y015，`target-12/D03/compared-to-target11.json`的p752/p753/p1221变化，`supplemental-target-sites.json`显示p751/p1219 `G16_COMPLETE_ONCE`失败。target-11曾保留G16完整追加，说明此次是实际模型/执行路径回退，不能用旧批次结果覆盖。
- 处理方法：保持G17删除自身授权范围，同时强制G16追加组件与G17删除组件在同一source clause闭合；删除不得吞掉应追加内容，Replay和实际DOCX审核都必须检查完整政策及原余文。
- 状态：**已确认，未修复**。FL-D220/221局部修复未覆盖该冲突；未修改gold/labels/scorer，target-12失败产物保留。
- 下一步：建立同site G16+G17组合反例和实际DOCX回归，修复组件排序/closure与Replay，完整回归后重新冻结并真实复测D03。
- 2026-10-24方案边界更正：曾尝试将“本基金的申购费率由基金管理人决定”作为共同收费证据，测试证明该句不等于明确收费且不证明无服务费，该尝试已撤回；未进入冻结版本/真实任务。当前测试包含该反例。无按文件特判、无gold/scorer变动。
- 2026-10-24 target-13真实验证：snapshot-13 D03中G17对p752/p753及p1220/p1221没有被单独删除；原用途/使用范围句保留，报告将G17标记为`CLAIM_OPERATION_NOT_PLANNED`/`G17_BLOCKED_G16_UNPLANNED`，G16仍因收费事实UNKNOWN而unresolved。机械下载1/1通过，未生成target-12式错误半成品；但同条款完整G16追加尚未交付，D03仍incomplete。
- 状态更新：**同site阻断已通过真实Worker/DOCX验证有效；合法G16+G17闭合在收费事实认证后仍需新批次验证**。
- 2026-10-24 target-14及原件复核：snapshot-14 D03收费组已VERIFIED，真实33 HTTP/$0.02573610，报告complete/34 targets/0 unresolved；机械1/1，G16正文/摘要均完整一次。原始模型审计仍报G15/G16 wrong。接续曾据此断言p751/p1219整段删除越界、p753/p1221必须保留原句；重新阅读指引原件第73/75–84/85–89段后，后一个判断已证伪：G17明确删除用途及使用范围排除句，G16追加本身不授予删除权，但允许与有独立授权的G17删除合并。G15支付变体删除及提示沿用既有用户裁定。不能为迎合错误审计恢复应删旧文；该审计冲突与Replay证据绕过另登记FL-D224。保留先前错误判断与更正，不以本次原件复核宣称全开发集或最终交付通过。
- 2026-10-24 target-17 D04复发：两处G17用途已窄删且独立费用余文逐字保留，但G16未规划。G16绑定p847/p1327是`_g16_clause_locations()`独立确认的真实费用条款尾，却被`append_site_ok()`仅检查尾段自身锚点误判`TARGET_SOURCE_MISMATCH`；guard又忽略out_of_scope G16，因此失去配套阻断。机械通过，整体incomplete/48 targets/15 unresolved，不能把G17局部通过视作完整条款。证据`target-17/D04/target-17-business-review.json`、snapshot-16完整Claim false/5 failures；拟统一source clause尾成员校验并让无效目标不抹去真实条款G16义务，再补失效目标与合法合并反例。当前仅已定位，尚未修复；D226全量运行期间不混入源码。

## FL-D210 G17删除后重复了前置支付顺延句（2026-10-24）

- 问题与影响：dev-05 D18 p776/p1227实际DOCX在用途条款删除后重复两次“若遇法定节假日、休息日或不可抗力致使无法按时支付等，支付日期顺延。”；audit阻断，Claim Replay自身仍通过。
- 证据：`dev-05-review-packets/D18.json`两处实际diff、`dev-05/D18/report.json`的G17 audit wrong；离线全20份重读仍显示D18 Claim=True，故不能把Claim通过理解为没有额外修改。
- 处理方法：待追踪组合delete的余文保留与replacement边界，按实际source slice保留一次；补非新政策重复文字的执行/授权回归，不能仅匹配固定new_text重复。
- 状态与验证：**已确认，未修复**；原incomplete文件和费用保留。
- 下一步：定位G17 planner/atomic composite重复来源，补DOCX回归并真实复测。
- 2026-10-24实施：`plan_composite_target()`原先以slice offsets执行，却把完整段外prefix/suffix放进replacement；改为delete返回空串，replace只返回该slice应插入的新文及必要分隔符，段外原文由执行器保留一次。`_component_ok()`验证相同切片/替换契约；Claim Replay增加delete replacement必须为自身source slice的子序列，阻断额外/重复文字。新增`test_composite_slice_delivery.py`实际final/redline生成及错误重复产物阻断回归；保留原测试但把断言改为检查执行后整段。完整离线 **1289 passed /44 skipped /2 warnings**。真实定向尚未完成，本条状态为**已实施、离线已验证、待真实复测**。
- 2026-10-24真实target-08：D18 p776/p1227旧顺延句各仅保留一次，原composite余文重复已消除，下载机械通过。**本重复缺陷在该真实样本验证解决**；该句自身应由G15删除却漏改是独立FL-D216，D18仍不能视为业务完整通过。

## FL-D211 份额定义段以跨段净值公式引导结尾导致追加被拒（2026-10-24）

- 问题与影响：dev-05 D11 p126已含完整A/C/D定义、代码和净值计算说明，但段尾“计算公式为：”连接p127公式；G03返回`RECALL_APPEND_CLAUSE_INCOMPLETE`而未追加。与D07字母分段不同，不能仅跳到下一段或插在公式中间。
- 证据：`dev-05-review-packets/D11.json` p126及next p127/p128，`dev-05/D11/report.json`中该错误和audit incomplete。
- 处理方法：待按完整业务条款或定义自身完句定位追加，保持计算公式原貌；FL-D207修复只覆盖定义词法/账户限制续文，不把本条写成已解决。
- 状态与验证：**已确认，未修复**。
- 下一步：核对guide追加范围，补定义/公式相邻的真实DOCX回归后复测。
- 2026-10-24实施：定义以“计算公式为：”结尾且紧邻段完整匹配净值等式时，`_split_definition_end()`将追加点绑定公式段末，原引导句及公式保持相邻、原样。不能认证的等式/无关后段继续阻断；G01/G03各有实际DOCX回归及两个反例，与FL-D207相关共9项通过。完整离线 **1289 passed /44 skipped /2 warnings**，真实定向尚未完成，本条状态为**已实施、离线已验证、待真实复测**。

## FL-D208 单类别合同缺少枚举句时收费画像长期UNKNOWN（2026-10-24）

- 问题与影响：dev-05 D09/D13实际单类别，facts class_count=1却无多类别枚举quote，share_class_structure/subscription_fee_group/service_fee_group均UNKNOWN，G07/G10/G14被RECALL_FACT_UNVERIFIED阻断，分别58/59 unresolved。
- 证据：`dev-05/D09/report.json`、`dev-05/D13/report.json`事实及恢复记录，原文候选在`dev-source-review-05/`。仅class_count=1或没有类别关键词本身不能当VERIFIED证据。
- 处理方法：待补单类别完整条款与收费正面证据的可追溯认证路径，保留UNKNOWN/CONFLICT fail-closed；不把默认值直接升级verified。
- 状态与验证：**已确认，未修复**。
- 下一步：独立核对两份原件费用/份额条款，设计有证据的单类别认证与反例回归，然后真实复测。
- 2026-10-24原件只读复核：`d09-single-class-evidence-review.json`、`d13-single-class-evidence-review.json`保留原facts与source候选。两者旧quote只有p214/p226“申购费用由投资人/者承担”，class_set_quote空。D09 p128–133、D13 p125–130无明确“仅一种”枚举；D13 p130只是未来可以增设/变更，不证明当前类别全集。D09 p740–766和D13 p766–788为自身完整费用列举/计提段，均无自身销售服务费机制；D09 FOF投资标的基金销售费用（p765/p830等）必须与本基金份额收费分开。后续可研究多区域完整性证书证明未命名单类别和自身费用缺项，尚未实施或验证，不能以无关键词直接放行。当前snapshot-12真实D03运行期间未改引擎。

## FL-D212 React V2 控件与原版工作台视觉体系不一致（2026-10-24）

- 问题与影响：新版任务工作台原先使用深橙色顶栏、独立的棕色 token、简化侧栏和浏览器原生下拉框，复选框、筛选表单、上传区、按钮组和移动端导航与原版 `frontend/app.css` / `frontend/index.html` 的浅灰画布、白色工作区、橙色强调和紧凑工具栏差异明显。用户在任务筛选、批量上传和修订复核中会感到页面像两套产品，原版的信息层级也不容易迁移。
- 证据：原版基线为 `--canvas:#f5f6f8`、`--paper:#fff`、`--accent:#b5471e`、252px 侧栏、64px 顶栏、分组导航、图标和多级筛选工具栏；V2 改造前为深橙顶栏、232px 侧栏和原生 `<select>`。差异已通过 Git 基线 `frontend/index.html` 与当前 V2 `frontend/src` 对照确认。
- 处理方法：新增共享 `Select` 包装控件，保留原生 select 的键盘和表单语义并提供统一箭头、焦点和 hover 状态；统一输入框、文件选择器、复选框、按钮组、筛选栏、上传拖放区、表格 hover、状态徽章和复核决策按钮的视觉状态；将 V2 顶栏、252px 分组侧栏、图标导航、移动端横向导航和页间距收回原版视觉尺度；任务总览补齐按指引筛选；恢复消息入口、帮助中心、修改密码入口和页脚信息；保留 V2 的 React 路由、持久任务、真实上传、复核和独立 Compare 入口。
- 状态与验证：**已实施，已发布并完成公网浏览器 smoke**。`npm run typecheck`、`npm run lint`、`npm run build` 和 `git diff --check` 均通过；前端浏览器定向回归通过；公网 smoke `/tmp/opencode/fundlex-public-v2-smoke-20261024/result.json` 已完成真实登录、`/tasks`、`/tasks/new`、`/guides`、`/settings`、消息、帮助和 1440px/390px 响应式检查，`page_errors=[]`、`console_errors=[]`、静态/API 404 均为0，页面 document/body 宽度无溢出，桌面侧栏计算宽度为252px。最终静态资源已按文件发布，备份为 `/tmp/opencode/fundlex-frontend-publish-20261024-131717-final-sidebar-fix/deployment-dist-before.tgz`。
- 下一步：如继续调整 V2 视觉或路由，必须重新构建并重复本地与公网浏览器验收；如修改 recall-first 引擎，继续按独立冻结版本、开发集真实 DOCX 审核和 holdout 条件推进，不与前端静态发布混发。若后续发现原版功能缺失，追加到本条变更记录或新建稳定编号。
- 变更记录：2026-10-24发布后公网 smoke 首次发现 390px `/tasks/new` 页面宽度 664px，根因是 `.shell-body` 在窄屏仍横向 flex，且横向导航内容未被侧栏容器承接；新增窄屏纵向 shell 和 `.sidebar { overflow-x: auto; }`，最终页面宽度收敛为 390px，公网 smoke 通过。前端-only 发布仅更新 `frontend/dist` 并重启 API，未发布引擎 dirty 改动。
- 2026-10-24追加发现：补测 768px 时 `/tasks` 页面 document/body 宽度为 998px，超出视口；当前 V2 的中等屏响应式仍未通过，前述发布后的 smoke 仅覆盖 1440px/390px，不能作为完整多视口验收。原因待结合原版 1180px 断点和 React 页面控件宽度矩阵修复。
- 2026-10-24用户再次明确验收原则：可以在原版基础上做细节优化，但**绝对不能丢失原版任何功能**。后续实现必须先建立原版功能/入口矩阵并逐项证明 React V2 等价可达；视觉优化、技术栈迁移和组件重构都不能删除、隐藏、改成绕路入口或降低原版能力。当前状态保持待修复，未重新发布。

## FL-D213 确定性整段删除被compose预算提前阻断并误扣预算（2026-10-24）

- 问题与影响：`recall.py::_plan_target_inner()`的`tier1_delete_pre_route`原在compose预算检查及递减之后；因此预算为0时根本无法执行，预算为正则未调用模型也扣一次compose名额。导致D03离线诊断`RECALL_COMPOSE_BUDGET_EXHAUSTED`，也可能让后续真实compose无可用名额。此处compose名额不是HTTP账本，不将其等同实际模型费用。
- 证据与复现：`probe_g15_raw.py`在registry模式、已正确raw绑定的D03 p751/p1219上，预算0失败、预算1返回`tier1_delete`且无模型调用；前次G15诊断因此同时混入了模式/预算因素，失败目录保留。
- 处理方法：把**原有**whole-paragraph quote/actual/source及keyword bag条件的确定性删除移到compose预算检查之前，并通过`finish()`保留operation身份与路由验证；没有扩大为任意部分段落删除。部分变体仍需要compose时保持预算0阻断。
- 状态与验证：**已实施，离线全量已验证，待真实任务验证**。`tests/test_g15_payment_delay_boundary.py`验证预算0/1均不调用模型、不改变预算，部分段落继续失败；与规划/Registry/管线组合**170 passed**。包含该修复的全量日志`g15-raw-boundary-full-pytest.log`为**1325 passed /44 skipped /2 warnings /240.20s**，不覆盖后续D05修改；D03原件局部DOCX/修订等价验证见FL-D206。无新增HTTP请求、未发布。
- 下一步：核对全量结果，冻结版本后真实复测；后续完整20份dev仍须审核，不以本条单点通过宣称整体完成。

## FL-D214 G17使用范围独立续段被过滤导致Claim Replay错误PASS（2026-10-24）

- 问题与影响：D05局部G15/G17组合中p869/p1333“销售服务费的使用范围不包括基金募集期间的上述费用。”未删除、plan ledger为unresolved，Replay却只要求p868/p1332并返回G17及整体PASS。不能以其他站点已完成掩盖同operation漏改。
- 证据：`/tmp/opencode/operation-validation-20261024/offline-d05-g15-g17-current-proof/offline-report.json`保留错误PASS；final SHA `5a337eed5cf65addc91020b0926374e46b94bc279ab0c97426fb7e5ff9e71c3a`。G17自身old_text第二句为“C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。”；实际多一个“的”。`operation_site_bound()`的literal/keyword/相似度未识别该句，target被静默过滤；同一关键词袋取首句“支付/佣金”，不能覆盖独立第二句。
- 处理方法：拟让planner与effect共用operation自身完整句的窄匹配（类别前缀与“销售服务费的使用范围”语法变体），保留明确主体、否定及募集期间语义；完整用途首句结束后，独立使用范围句仍须成为required site。无授权operation、不同费用/肯定句/其他时期不借权。
- 状态与验证：**已确认，修复实施并完成离线验证，待真实任务验证**。旧文件和报告保留，未修改gold/labels/scorer，未真实模型复测、未发布；本次及修复验证均0 HTTP。
- 下一步：实际DOCX反例先验证残留必须失败，修planner及site closure，再重建D05组合并核查全部四站点、修订等价和完整回归。
- 2026-10-24实施：新增`_g17_usage_exclusion_matches()`，只接受G17自身完整“销售服务费使用范围不包括基金募集期间的上述费用”语义，允许类别前缀及一个“的”变体；planner的确定性delete、`operation_site_bound()`和`_verified_site_closure()`共用该边界。结束的用途首句之后，紧邻独立续段被加入required sites；肯定、其他费用/期间、额外句及自定义仅首句授权均拒绝。新增G17实际DOCX/Replay回归与D05重建：旧产物重放明确p869/p1333 FAIL，当前重建四个G17 sites全部`PASS`，p868/p1332核对句保留，接受/拒绝修订分别匹配final/原件；0 HTTP，证据`offline-d05-g17-site-closure/`，final SHA `6fdc241ed53d54ff3da313aea86856fa721b24fd56b39ad9f196bc94689d0051`、redline SHA `46017ecbcf0d6c962aa253a8d77cf4857f8387b5d87ec61250131c5ce691ba8a`。同时G15 `bounded_delete` Replay改为重算自身授权和完整raw范围，新增伪造边界反例。**本条仍待完整全量及真实Worker/模型复测，未发布。**
- 2026-10-24全量验证：当前工作区完整回归 **1343 passed /44 skipped /2 warnings /245.29s**，日志`g17-closure-full-pytest.log`；包含G17续段站点闭环、D05实际重建回归及G15 `bounded_delete`授权重算。FL-D214的离线验证范围已完成，仍不能替代真实Worker/模型复测、20份dev业务审核或发布验收。
- 2026-10-24真实复测预登记：用户明确要求真实测试并按结果持续优化；本条与FL-D192/206/209共同纳入`snapshot-08/target-08` D03/D05/D07/D18真实任务，build `a829181de8e965b8c6f64f7d37dcd2e1e7ff5134230a258a584ea2ee59c8652b`，起点1028 HTTP/$0.99678030，共享cap2000/$2。当前仅完成冻结，真实结果尚待运行及文件复核；不得预先关闭本条。
- 2026-10-24真实target-08 D05结果：complete/0 unresolved，28 HTTP/$0.03210180，机械通过、定向18/18，G17四站点全部完成、G15核对句各一次、G16每条款完整一次。**本条G17独立使用范围续段缺陷在该真实样本已验证解决**；旧失败文件保留，不代表完整20份dev或生产验收。

## FL-D215 G08/G11完整政策替换吞掉原条款编号（2026-10-24）

- 问题与影响：真实`target-08` D03 p211原文以“4、A类基金份额的申购费用…”开头，G11 clean-clause template替换整个slice时仅返回新政策，导致“4、”编号丢失；报告complete、Claim PASS，政策文字正确但结构余文未保留。
- 证据：`/tmp/opencode/operation-validation-20261024/target-08/D03/review-packet.json`及`artifact-review.json`；final SHA `bd09136ba43f3c64feb265ab4de2e450045d3c89e9792d8d807838f02b7dc494`。真实模型33 HTTP/$0.02439705，机械通过不等于结构正确。
- 处理方法：clean-clause G08/G11从原slice提取有界、明确的条款编号前缀并逐字保留；Claim Replay独立从原slice核对编号，不依赖evidence自证。混合赎回/相邻正文仍拒绝整段模板，不将编号识别用作扩大授权。
- 状态与验证：**已确认，修复实施中，尚未验证**。新增实际DOCX、相邻条款保留、完整政策但删除/伪造编号必须FAIL的回归；未改gold/labels/scorer，未发布。`target-08`继续使用冻结修复前版本，后续必须冻结新版本并另建真实run复测D03。
- 下一步：必要回归→完整回归→新冻结版本真实任务→下载文件与全部差异复核，保留`target-08`失败文件。
- 2026-10-24验证更新：55项定向及完整 **1351 passed /44 skipped /2 warnings /256.56s**；修复版`snapshot-09` build `997329195f5699afd246bdb6ff5cca4fa28f5beaee440433e864e77c4f03d861`真实`target-09` D03已complete/0 unresolved，33 HTTP/$0.02420940。授权下载机械1/1、实际DOCX定向16/16通过，p211保留“4、”，完整政策、G15/G17/G16及相邻定义保持；final SHA `d04285613f9095a8b882daa92982d80a978fc5db04b1015252170595479ea226`，redline SHA `a1ab2c0bf5d32526d811c8d21b6243a39c168062495828e680687bfc895207d8`。**本编号缺陷在该真实样本已验证解决**；旧target-08失败证据保留，不代表全dev或生产验收完成。

## FL-D216 G15独立跨段支付顺延句漏删且Replay错误PASS（2026-10-24）

- 问题与影响：真实`target-08` D18 p775/p1226旧支付head已删除，p776/p1227首句“若遇法定节假日、休息日或不可抗力致使无法按时支付等，支付日期顺延。”仍留存；G17用途已删除、G16各完整一次，报告却complete/0 unresolved。定向12/14，两项失败均为该残留。
- 证据：`/tmp/opencode/operation-validation-20261024/target-08/D18/review-packet.json`及`supplemental-target-sites.json`；final SHA `126e63845e7baa27307618b49210b77dd20f2d1c174462343b4ff0ded1cf20a6`，redline SHA `49f63380eb8ee03fc11f984db6fd967d4a8c817ca6f1946073fcd1d8192be46c`。target-08四份机械4/4，140 HTTP/$0.12862980；机械通过不等于业务通过。
- 处理方法：拟由G15自身完整payment+delay删除授权，绑定紧邻已证实销售服务费支付段的完整下一段首句；planner和effect closure共用原件raw边界，Replay独立重算相邻source与授权。保留同段G17用途及核对句、其他费用机制；无head/无授权/跨无关段/其他机制不得删除。
- 状态：**已确认，修复中，未验证**。旧错误PASS产物保留；不改gold/labels/scorer，未发布。
- 下一步：实际DOCX/遗漏target/错误授权反例→旧产物Replay必须失败→完整回归→冻结新版本真实D18复测。
- 2026-10-24实施与离线验证：planner/effect共用`_g15_delay_continuation()`原件raw边界，新增自身operation的独立tail target；Replay从原件重算head/相邻句/授权，拒绝伪造evidence。相关82项通过，compileall/diff check通过。`offline-d18-cross-delay/offline-report.json`以真实target-08 D18旧产物重放从verified=true变false，p776/p1227明确FAIL；零模型局部重建两head删除及两tail各0–33删除，其他段落（含G17用途）逐段原样、接受/拒绝修订等价通过。首轮回归发现新增Replay参数未穿过`_operation_units`导致NameError，已补传并重跑通过；此错误未进入真实快照/生产。**状态为已实施、局部离线已验证，完整回归与真实D18复测待完成**。
- 2026-10-24全量及真实复测预登记：完整 **1363 passed /44 skipped /2 warnings /261.77s**（`g15-cross-paragraph-full-pytest.log`）。冻结snapshot-10 build `c3f8c6442b2b2880c82746e8b94e38e84127602da94053d5866d1b040f4638e8`，manifest已重验；API/tasks与生产一致，生产未发布。target-10仅D18，隔离data-10与API8013，真实身份/上传/持久Worker/模型/授权下载；账本起点1201 HTTP/$1.14961950，剩余799/$0.85038050，总cap2000/$2/并发1、单合同192不变，预计约35 HTTP/$0.03。新run不覆盖旧失败，结束检查两tail、完整G16各一次、G17、全差异、修订及哈希。
- 2026-10-24真实验证完成：snapshot-10 `target-10` D18 complete/0 unresolved，33 HTTP/$0.02434395；授权下载机械核验1/1，实际DOCX定向14/14。p776/p1227各删除原顺延首句，p775/p1226支付head已删，G16每条款完整一次，G17用途/独立其他机制保留；与target-08最终文件比较仅p776/p1227发生变化，未引入其他差异。final SHA `8ac72b7c83314f4b62230a2bfef4171f7a4f2d2d5def95c666472cb8fe34861`，redline SHA `788c9f1fba9c0fa02446b08b1735d65518cc958f1330f7b17f92092b83633e7b`，报告/实际变化已保存`target-10/D18/review-packet.json`、`compared-to-target08.json`。**FL-D216已在该真实样本验证解决**；不代表全20份dev或发布验收完成。

## FL-D217 G08完整新政策前保留旧同义免申购费子句造成重复（2026-10-24）

- 问题与影响：target-09 D03 p209在G08完整新政策之前仍保留“本基金C类基金份额不收取申购费，”，新政策紧接着又声明“C类基金份额不收取申购费用”。语义不冲突但重复，不能因编号缺陷修复或定向16/16而宣称完整业务文件无其他问题。
- 证据：`/tmp/opencode/operation-validation-20261024/target-09/D03/compared-to-target08.json`；同原件与target-08相比，除p211编号外仅p209此保留差异。target-09 final SHA `d04285613f9095a8b882daa92982d80a978fc5db04b1015252170595479ea226`；target-08没有该重复。真实模型run差异，不把snapshot-10的G15修复当作本问题已修复。
- 处理方法：待核对G08自身实际切片与完整source费率子句的边界和同义免申购费组件；仅在自身授权源句中收敛重复，保留计算公式与其他费用机制，不扩大到任意相邻段。
- 状态：**已确认，未修复**，FL-D215编号局部验证仍成立，D03整合同业务无缺陷声明不成立。历史文件/费用保留，未改gold/labels/scorer。
- 下一步：查看G08 target/compose/实际plan，补实际DOCX与未授权余文反例，修复后新真实D03复测。
- 2026-10-24修复与冻结：planner在G08完整同句政策已确定覆盖的情况下，将同句且同义的旧C类免申购费前缀纳入自身raw slice；仅接受逗号连接、当前类别、政策自身包含的申购免收费组件，并拒绝句号、其他收费主题、独立机制或跨句前缀。Replay从原件重算该扩展边界，旧target-09实际产物现报`CLAIM_DUPLICATE_EFFECT`；零模型实际D03局部重建p209 raw36–86，计算公式及其他段落保留，接受/拒绝修订等价通过，相关75项定向回归通过。
- 2026-10-24完整回归与真实复测：完整 **1370 passed /44 skipped /2 warnings /258.22s**；冻结`snapshot-11` build `92880a778ab4607b713cd26da56e8e061c9283e0d26021dfd121ad81298bdd5a`，manifest已重验，账本起点1234 HTTP/$1.17396345且无reserved。真实`target-11` D03已启动，尚未完成；FL-D217保持**修复已实施、离线已验证、真实验证进行中**，旧target-09重复产物及费用保留。
- 2026-10-24真实结果：target-11 D03 complete/0，33 HTTP/$0.02399670，机械1/1、定向15/16；p209旧同句C类免申购费前缀已消除，计算余文完整、p211编号保留。final SHA `82fbe05b4ffc261d546cc64f9a3a108949d6de005c4f939a45252b49dd6e4f0a`，redline SHA `0f3258ef066af20e61fb77fef3654c8d4f2467c2c6954e059151531380a20ce1`。**本重复缺陷在该真实样本已验证解决**；失败项为新FL-D218定义追加位置，不能称D03整合同业务通过。相对target-09仅p209（预期修复）和p92（新缺陷）不同。

## FL-D218 同段合并下一编号定义导致G01追加到错误条款之后（2026-10-24）

- 问题与影响：target-11 D03 G01 p92 inventory quote同时包含“基金份额类别”与下一“55、发起式基金”定义，planner在raw209追加新条款而非自身类别定义末raw130。实际没有删除余文，但政策附在错误定义之后，辅助检查15/16且报告仍complete/0、Replay通过。
- 证据：`/tmp/opencode/operation-validation-20261024/target-11/D03/report.json`、`compared-to-target09.json`、`supplemental-target-sites.json`；target-09同段quote只覆盖0–130且正确，target-11为0–209。不是FL-D217 G08回归，而是模型quote边界变化暴露已有G01边界验证缺口。
- 处理方法：待在原件raw地址识别自身类别定义之后的明确编号定义边界，限制append点；Replay独立重算边界阻断错误位置，保留下一定义全文及编号，不按文件/样本特判。
- 状态：**已确认，修复中，尚未验证**。旧target-11文件与真实33 HTTP/$0.02399670费用保留；累计账本1267 HTTP/$1.19796015、无reserved，余733/$0.80203985。
- 下一步：真实原件局部重建与错误位置Replay反例→完整回归→新冻结真实D03复测；D07审核输入改动仍在工作区待单独测试，不混作snapshot-11已验证实现。
- 2026-10-24实施与局部验证：`_definition_next_entry_start()`仅在完整类别定义结束后遇明确下一编号＋定义名＋冒号时给出raw边界；planner收窄append site，Replay从原件重算并拒绝错误位置。相关162项回归、compileall/diff check通过；`offline-d03-merged-definition/`对真实target-11旧产物Replay现false，G01 raw209被拒绝；零模型重建在raw130插入，下一编号定义和全部其他段落原样，接受/拒绝修订等价通过。**已实施、局部离线已验证、完整回归及真实复测待完成**。
- 2026-10-24完整回归阶段结果：G01边界＋audit_v3版本 **1396 passed /44 skipped /2 warnings /283.59s**（`merged-definition-audit-full-pytest.log`），随后新增收费事实入口认证，因此该统计不能代表当前完整工作区。当前全量`fee-evidence-current-full-pytest.log`后台运行，通过后冻结snapshot-12并启动target-12 D03；脚本`freeze_snapshot_12.py`已改为强制读取当前全量最终通过统计。
- 2026-10-24验证阶段更新：收费入口初版全量 **1400 passed /44 skipped /2 warnings /270.15s**，随后独立收费引文接口/认申购缩写追加，因此最终工作区全量另起`fee-separate-final-full-pytest.log`；启动前已保存完整fundlex/tests源码哈希与build `d441ec1706668bcdcafb0fcf7cfef9798d5879bb3a22871c1f9e84963c1fb16b`（`fee-separate-final-test-start.json`），冻结脚本强制与该源码一致，避免测试运行期间新代码混入冻结。`target-11/D03/business-diff-review.json`完整审核20处实际变化：19通过、p92失败；源级独立目标分母仍待审核。
- 2026-10-24最终回归与冻结校验：最终 **1404 passed /44 skipped /2 warnings /286.21s**。首次冻结在复制前因`tests/browser/test_frontend_v2.py`变化停止；核验全部fundlex/tests Python集合与哈希，仅该浏览器文件变化、引擎build未变。补验发现新增Compare入口测试漏点侧栏导航（FL-D219），修正后显式Chromium **5 passed /10.90s**；保留原全量与失败日志，`freeze12-supplement-evidence.json`记录独立补验哈希。冻结脚本只允许该精确补验差异，其余源码/文件集合/build继续严格一致。真实D03复测尚待启动。

## FL-D219 新增React清单浏览器测试误将Compare默认页当对比业务页（2026-10-24）

- 问题与影响：最终回归后并行增加的清单搜索/筛选/分页测试点击`/compare`入口，直接等待`#compare-new`可见；独立Compare页面默认任务总览，按钮所在业务section尚未打开，导致1失败/4通过并阻塞snapshot-12冻结。不是登录失败，初步聊天判断已更正。
- 证据：`frontend-freeze12-supplement.log`显示按钮存在但hidden；`frontend/app.js::go()`按hash切换section，`frontend/compare.html`默认`view-overview`。冻结前校验确认仅该浏览器Python文件变化，引擎build未变。
- 处理：保留新增清单交互测试，按已有用户路径点击侧栏`[data-nav="compare"]`后断言新建按钮；未改前端运行代码、引擎、gold或scorer。
- 状态与验证：**测试修正已验证**，初始补验 `FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q --tb=short` 为**5 passed /10.90s**，随后加入替换失败边界后当前专项为 **6 passed**；完整1404回归与前端补验分开记录。冻结脚本记录精确原/补验文件哈希，不放宽其他检查；不代表Compare真实任务或引擎最终交付完成。
- 下一步：冻结snapshot-12并继续FL-D218真实D03验证；前端后续变更继续按其功能基线验收。

## FL-D223 React上传清单替换失败时旧文件可能继续显示为可提交（2026-10-24）

- 问题与影响：React V2 新建任务页支持文件替换后，若替换文件不是 DOCX、为空、超过限制或与其他清单文件重名，旧文件仍可能留在 `files` 状态中，而异常只写入同名 `issues`；用户看到异常提示，但提交按钮仍可能按旧文件集合继续上传。另一个触发边界是点击“替换”后立即选择文件，异步 React 状态更新可能使回调读不到 `replaceName`。
- 证据：`frontend/src/pages/NewTask/index.tsx` 的 `replaceFile`、`files`、`issues` 状态；新增浏览器场景 `test_new_task_invalid_replacement_removes_old_upload_row` 曾在修复前观察到旧 `原合同.docx` 行仍显示为“已接收”，而新 `替换说明.txt` 异常行同时存在。
- 处理方法：替换目标同时保存到 `replaceTargetRef`；替换校验失败或新名称冲突时，从可提交 `files` 和 `clientIds` 删除旧行，仅保留异常文件行；成功替换清除旧异常并重置目标。追加文件保留同名保护，异常筛选按文件名合并展示。
- 状态与验证：**已实施，已验证**。`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` **6 passed**；TypeScript 类型检查、ESLint、Vite build 和 `git diff --check` 通过。验证范围为本机临时 FastAPI 服务和真实浏览器 DOCX/TXT 文件选择，不包含生产发布。
- 下一步：若后续继续修改上传清单或发布本候选，需重复上传、恢复补传、替换/移除/清空及七视口回归；生产真实合同交付仍按完整项目验收门槛单独执行。

## FL-D224 生产浏览器原地从桌面缩放到768px时主内容保留内容最小宽度（2026-10-24）

- 问题与影响：前端候选首次发布后，公网 smoke 在同一 Chromium 页面先以 1440px 访问路由，再调整到 768px 时，`.main-content` 作为 flex 子项保留内容最小宽度，页面 `document/body` 宽度扩大到 976px，导致中等视口横向溢出。独立新 context 直接以 768px 打开时未复现，因此原有七视口冷启动检查不足以覆盖浏览器原地缩放路径。
- 证据：发布后公网复现脚本 `/tmp/opencode/fundlex-public-v2-smoke-published.py` 在 medium 检查失败：`viewport=768, documentWidth=976, bodyWidth=976`；进一步检查显示 `.main-content` 从可用 550px 扩展到约 758px。首页、深链、API、JS/CSS 资源均正常，失败定位为布局尺寸。
- 处理方法：在 `frontend/src/styles/app.css` 的 `.main-content` 增加 `min-width: 0`，允许 flex 子项按中等视口收缩；新增 `test_shell_shrinks_when_viewport_changes_from_desktop_to_medium` 覆盖 1440px→768px 原地调整。
- 状态与验证：**已实施、已受控发布并已公网验证**。本机 `npm run typecheck`、`npm run lint`、`npm run build`、`git diff --check` 通过；React 浏览器专项 **7 passed**；公网 smoke `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json` 通过登录、消息/帮助、关键深链、1440/768/390 响应式及原地 1440→768 收缩，页面/控制台错误与静态/API 404均为0。最终资源哈希已登记在 `ACTIVE_HANDOFF.md`。
- 下一步：前端问题已关闭；继续完成当前版本真实合同的 Worker/model、DOCX、Review、报告、授权下载、修订和哈希验收。

## FL-D224 业务审核误读删除授权，且effect重建分支可绕过失败unit证明（2026-10-24）

- 问题与影响：target-14模型审计与报告complete冲突后，人工接续未先回查指引便把G17已授权的使用范围句删除误判为G16吞原句。指引原件85–89段要求删除两句，不能按该误判改回合同。同时`generation/effects.py`对delete/append存在`planned_matches`直接PASS分支，即使传入的operation unit为FAIL也可通过，可能把真正未授权删除误认证，不能用机械重建替代操作授权。
- 证据与复现：`/tmp/opencode/operation-validation-20261024/target-14/D03/report.json`、`report_md.md`及final/redline；p751/p1219为完整旧支付变体，p753/p1221为G17独立删除＋G16追加。指引`references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx`第73、75–89段（python-docx零基）；`tests/test_final_validation_regressions.py::test_delete_passes_when_another_operation_fills_the_empty_paragraph`明确给FAIL unit仍期望PASS，复现了effect绕过。
- 处理方法：以指引及operation身份核对删除与追加授权；收紧effect的merged重建分支，已有失败unit不能靠plan/artifact一致升级PASS；增加合法合并及伪造边界反例。审计引用真实丢失的原文时应核验BEFORE/AFTER，保留有据的越界结论；不能仅因引用新政策就覆盖真实余文损失。
- 状态：**原件授权误判已更正；代码缺口已定位，修复和验证待完成**。target-14历史报告、审计与费用全部保留；不改gold/labels/scorer、不运行holdout、不发布引擎。
- 下一步：操作级失败proof回归、合法G16/G17实际DOCX回归及target-14完整只读重放；按新发现收窄修复→定向/完整回归→必要的新冻结真实复测。共享账本1389 HTTP/$1.30929540，无reserved，上限2000/$2不变。
- 2026-10-24实施与定向验证：删除`effects.py`中delete/append凭`planned_matches`绕过失败unit的两个PASS分支；新增merged delete/append PASS/FAIL对照。G15 planner和Claim Replay均从自身operation重新计算支付范围，额外无关句不能通过伪造`expected_old_text`/`deleted_paragraph`自授权；最新定向**143 passed /16.14s**（包括四个新增G15反例）。target-14全计划/实际final只读重放`target-14-d224-source-scope-replay.json`为verified=true/0 failures，G15/G16/G17全部PASS，0 HTTP；此前strict-unit-replay也通过，但不含最新范围补丁，证据分开保留。
- 同日审计修复：提示词明确允许BEFORE引文证明丢失，旧`_run_audit()`却通常只接受AFTER（FACT/APPLICABILITY例外），可将真实丢失降为REVIEW_UNPROVEN。现分别记录`evidence_in_before/evidence_in_after`；BEFORE-only损失保持有据阻断，只有完整本地operation proof证明引文完全位于授权删除/替换范围时才可判审核意见未证明，G16追加不得替G17授权。新增实际DOCX合法G16+G17合并/无关核对句丢失反例，相关**124 passed /16.35s**；旧target-14审核只读重放`target-14-d224-audit-replay.json`为29 results/0 issues/0 artifact failures，0 HTTP。这是既有审核重放，不是新的独立业务审核。
- 当前状态：**代码已实施、定向及旧target-14只读重放通过；完整回归和修复后真实任务尚未完成**。完整回归后台`sh_16ce5d301001xtf0RCLtCjneLJ`，日志`/tmp/opencode/operation-validation-20261024/d224-full-pytest.log`，启动源码manifest`d224-full-test-start.json`，build `d7dc3484d26e637a37d44cec07e492b5c94872845a928f677698fea022bc9683`。通过且源码一致后方可冻结新版本、另建真实批次；不覆盖target-14。
- 全量首轮结果保留：**1 failed /1417 passed /46 skipped /2 warnings /272.88s**，唯一失败为`test_whole_paragraph_delete_when_wording_differs`：自定义G15指引只删除单句计提支付说明，合同合法单句变体被新门禁过度拒绝。已增加单句限定的source-bound支持；该短operation不能删除第二句或未授权顺延（新增两个反例），完整operation的多句范围仍逐句核验。相关**233 passed /30.25s**。最终全量重跑后台`sh_16cec1cb6001SVz0DMNrQuXjPC`，日志`d224-final-full-pytest.log`、manifest`d224-final-full-test-start.json`，build `9ed657267458d3fdd18a700a682576f7e5ec359e7535059799905648e01d6813`；首轮失败不抹去。
- target-14完整实际差异复核证据`target-14-d224-business-diff-review.json`：20个实际变化段均对照指引原件核对，其中G05原件21–22段、G08/G09/G11/G12/G14原件33/40/48/53/66段及G15–17原件73–89段；机械结果保持1/1。该复核发生在预测之后，不是独立冻结完整目标分母；全20份开发集门槛仍未通过。
- 2026-10-24最终全量结果：**1420 passed /46 skipped /2 warnings /271.52s**，`d224-final-full-pytest.log`与启动manifest逐文件哈希一致，结果另存`d224-final-full-test-result.json`。该版本不含FL-D225修复；不得以本全量证据冻结后续修改。

## FL-D225 G17整段删除可借伪造provenance吞掉独立余文（2026-10-24）

- 问题与影响：FL-D224收紧G15后，零模型对称探测发现G17仍可把“使用范围不包括…”与无关句合并成整段删除，将整段同时填入`expected_old_text`和`deleted_paragraph`后Claim Replay错误verified=true。G16/G17合法合并审核不能仅依赖这种自授权证明，否则BEFORE丢失引文可能被错误降级。
- 复现线索：使用builtin G17 operation，原文“销售服务费使用范围不包括基金募集期间的上述费用。投资者可以随时免责。”，`whole_paragraph_delete`、空replacement、operation_keys=G17:0、expected_old_text及evidence.deleted_paragraph均为完整原句，实际空段；直接`replay_claims`返回verified=true/0 failures（0 HTTP）。不涉及target-14真实原件；target-14尾段并无该无关句，不能将该对抗样例当作其实际缺陷。
- 处理方法：待从G17自身operation独立重算完整用途/排除句或合法跨段parts删除范围，拒绝额外无关句和篡改provenance；与合法G16/G17实际DOCX合并、反向语义及跨段余文正反例共同验证，不放宽门禁。
- 当前状态：**已确认、未修复**。FL-D224最终全量仍运行中，避免混入其源码版本；因此snapshot-15冻结及真实run应等待本缺口处理，不能照旧断点直接启动。
- 下一步：保存首个最终全量证据后修复G17源授权，定向/全量回归→更新snapshot-15启动manifest与预算→真实开发集复测。费用账本仍1389 HTTP/$1.30929540，reserved0，生产未发布、无holdout。
- 2026-10-24实施：`recall._g17_source_effect_owned()`按选定operation自己的完整句子、有限类别/基金前缀及“的使用范围”差异重读原件，独立映射完整句跨段覆盖范围；每个edit只能删除完整授权范围，切片内其余文字必须按原顺序保留。planner单段`_attach()`、composite planner和Claim Replay共同调用，不从`expected_old_text`、`deleted_paragraph`、`parts`或其他provenance取得删除权限。G17自定义replace操作沿用既有replace证明，本次修复针对delete。
- 定向验证：新增伪造多种provenance＋无关句、反向极性/费用主体/期间、planner整段fallback、句中拆段及篡改parts实际DOCX正反例；与合法单段、G16+G17合并及其他授权回归共**229 passed /30.52s**。首次定向1 failed/209 passed因新测试夹具缺少PlannedEdit.evidence，补全夹具后通过，不改业务预期。target-14全部计划与实际final只读Replay仍verified=true/0 failures（`target-14-d225-source-scope-replay.json`），0 HTTP。
- 当前状态：**已实施、定向与target-14只读Replay通过；完整回归和新真实任务待完成**。全量后台`sh_16cf55000001QvBoY3mtjs1yoV`，日志`d225-full-pytest.log`、启动manifest`d225-full-test-start.json`，build `27721a2f381b3fbcfbac37236f1058d1a3bcc004d6a613bfb95ca7181468742c`；启动后不混入源码。freeze_snapshot_15.py已绑定本轮日志/manifest，仍须待通过后再运行，保持D03预计40 HTTP/$0.04、最坏100/$0.12的已有预登记。
- 历史20份dev-05只读Replay（`dev-05-d225-replay.{json,log}`，0 HTTP、不重认证旧facts）发现：D04 p847/p1327旧composite把独立“上述费用实际支出…”整句吞掉；D06 p809/p1288吞掉独立管理人降费/促销权限句，新门禁均阻断；D18重复prefix旧缺陷保持失败。也发现当前窄匹配过拒合法表述：D02“佣金，及…”、D11/D19“持有人服务费”及D11“销售服务费不包括…”省略“使用范围”。应在本轮全量结束后按自身完整句有限措辞差异补充，另验反向极性/主体/期间和额外句拒绝，再重跑；**暂不直接冻结本轮版本**。旧D02曾complete但当前整体false含其他门禁，不能由本次新增G17范围失败倒推其全部原文删除错误。
- 首轮D225完整回归**1428 passed /46 skipped /2 warnings /271.62s**，源码manifest匹配，结果`d225-full-test-result.json`。随后补有限词汇/标点差异（“、以及/，及”“基金份额持有人/持有人”“使用范围”可省、句号/分号），保持主体/极性/期间及完整句边界；新增完整句通过＋独立降费句保留＋反向极性/主体拒绝反例，相关**226 passed /31.41s**。不按文件名/case_id分支，不改gold/labels/scorer。
- 最新最终全量后台`sh_16cfb1c5b0017gAN9i7cM35Ay7`，日志`d225-final-full-pytest.log`、manifest`d225-final-full-test-start.json`、build `4bbe0bd82928f338d4cdc87b786ca4dd39ced54aeea8bcdc2d9639c35709de00`；freeze_snapshot_15.py已绑定最终日志/manifest，勿用首轮全量冻结增量。历史20dev最终只读重放另后台`sh_16cfb1c5c001Pj0A1KHfwDu9XN`，输出`dev-05-d225-final-replay.{json,log}`，保留原轮所有失败证据。仍0新增HTTP、无真实Worker/holdout/引擎发布。
- 最终历史20dev重放已完成：D02/D11/D19的G17过拒消除，D04/D06独立余文损失及D18旧重复prefix仍失败。20份整体仍false（包含其他收费/目标/历史缺陷），不得将G17局部通过转为业务整合同通过。D04/D06真实原件G17完整句局部DOCX重建`offline-d225-real-source-slices-verified/result.json`：两份均proof=true，独立费用支出/降费权限余文逐字保留，只改四个目标段，接受/拒绝修订等价通过；0 HTTP，不是新正式任务。首次临时脚本未构造DOCX所需source/zone验证字段，执行器以SOURCE_HASH_MISMATCH拒绝且未产出文件；已使用正式build_docx_edits+content_check修正，失败目录保留。后续真实D04/D06应验证planner能恢复窄范围而非停在范围拒绝，不能用局部重建冒称召回问题已解决。
- 最终增量target-14只读完整产物/旧审核重放`target-14-D03-d225-final-replay.json`：verified=true/0 failures，29 results/0 issues/0 artifact failures，0 HTTP。全量仍运行，源码manifest保持一致，API/tasks与生产一致，预算足够既有D03预登记；暂不宣称新真实任务或FL-D225最终闭环完成。
- target-15 D03真实端到端已完成：snapshot-15 build `4bbe0bd82928f338d4cdc87b786ca4dd39ced54aeea8bcdc2d9639c35709de00`，真实登录、上传、seal、持久Worker/模型和授权下载均完成；`complete`，35 targets/0 unresolved，34 HTTP/$0.02907375。下载机械核验1/1：source/final/redline hash、接受修订=final、拒绝修订=原件、无残留修订、段落位置、plan/artifact全部通过；final SHA `66efdc0c6ceab948cd51a8745fc4236e275b7c7cb7a589cdadcd7afc401c8d2b`，redline SHA `302c9805930dbc3460e51a0c2670ad989899fad85db516879ae09559e5a1dc91`，修订20 ins/20 del。Claim Replay `verified=true/0 failures`；记录审计重放29 results/0 issues/0 artifact failures；实际变化20段与target-14已独立审核文本逐段相同，target-15业务复核20/20 PASS，证据`target-15/D03/{artifact-review.json,target-15-business-diff-review.json}`及`target-15-D03-d225-final-replay.json`。账本更新1423 HTTP/$1.33836915，reserved0。该结果仅是D03真实批次，不能替代20份dev完整独立目标分母、D04/D06真实复测或holdout。
- 已登记 target-16 D04/D06 真实复测：固定 snapshot-15、开发集、两份原件，不读取holdout；预计最多80 HTTP/$0.06，最坏200 HTTP/$0.24。按当前账本起点1423 HTTP/$1.33836915，最坏后仍不超过2000/$2。验收重点是实际planner/Worker是否分别只删除G17完整用途句，并保留D04“费用实际支出”余文、D06“下调/打折优惠”权限余文；另核对完整报告、Claim Replay、审计、final/redline、接受/拒绝修订和哈希。该登记不等于任务已完成。
- target-16实际终态：D04/D06均完成真实登录、上传、seal、持久Worker/模型及授权下载，但均`incomplete`（58 targets/33 unresolved、91 targets/37 unresolved）。机械核验2/2通过；D04 final SHA `96b3830e2d8afac21e0a874a03bfa2f25943f803ca323df4fde76b387b1c66c2`，17 ins/17 del；D06 final SHA `afbc9e41c5cacc4ca2880863714f35552e71e79c1e2e88e3a225e7dd97dce352`，13 ins/13 del。完整plan Claim重放分别false/8 failures、false/9 failures；脚本只重放最后artifact_recovery审计轮（0 results/27 issues、1/28），不能当作所有历史审核回答的重放。
- target-16定位：D04 survey Y006/Y007、D06 Y051/Y052将跨段用途句的follower整段纳入composite，吞入独立费用支出/管理人降费句，故被范围门禁正确拒绝。D04 DEL001仅恢复首副本p846/p847的0–32、0–20，独立余文保留，但p1326/p1327仍漏删；D06 p808/p809、p1287/p1288用途句均残留，p810/p1289排除句已合法删除并与G16合并。待从自身operation完整句重算窄parts，修复重复站点被宽目标覆盖/抑制；不能放宽Replay或伪造provenance授权。G12/G16/G15及其他未决独立保留。
- 费用更正：报告汇总50 HTTP/$0.05309895仅覆盖最终报告统计；共享账本由1423/$1.33836915增至1490/$1.40885745，真实增量67 requests/$0.07048830（65 completed/$0.06925320、2 failed/$0.00123510，reserved0）。17 requests/$0.01738935差额归因尚待对账，全部计入消耗，当前剩余510 requests/$0.59114255，cap2000/$2不变。未新增模型任务、未发布引擎、无holdout。
- 账本对账补充（更正早期把124次checkpoint复用误写成HTTP的计数）：D04/D06最终报告174个逻辑事件中124个为checkpoint复用，50个为非复用HTTP；后者按task/prompt/context/attempt/error字段与账本全部匹配、unmatched_report_events=0。17条账本差异为最终报告未保留的请求，按任务为facts 1、scope 1、inventory 3、locate 2、compose 2、verify 2、audit 6（其中audit失败2），合计`$0.01738935`。只读data-16/runs.sqlite3确认D04 attempt1、D06 attempt3，结合2条schema失败，证据指向D06重试前轮调用；`target-16-metering-reconciliation.json`保留逐请求哈希和费用。总消耗完整计入，最终报告未跨attempt汇总这一报告范围限制保留。
- FL-D225修复续：`_reference_continuation()`现在按G17 operation自身完整句、有限措辞/终止标点匹配 follower，只返回授权句的compact slice；`ensure_delete_targets()`对G17从源原件独立重算每个完整句的parts，宽composite与失败/过期target不能覆盖或抑制窄副本恢复。D04/D06真实原件零模型规划→DOCX结果各自Claim verified、独立余文逐字保留、接受/拒绝修订等价通过，D04 4 edits、D06 6 edits，0 HTTP，证据`offline-d225-planning-real/result.json`。定向相关130 passed（含新增真实D04/D06结构夹具），完整回归待当前后台结束；尚未冻结新snapshot或运行真实复测。
- 完整回归已完成**1436 passed/46 skipped/2 warnings/278.05s**，177个源文件manifest相同；日志`d225-planning-full-pytest.log`、结果`d225-planning-full-test-result.json`。`snapshot-16`已冻结、build `2858706c841ff88b1a75e394e1d4f225d0d6c8bcfa2ebfcb0b68252af7922889`，`run_context-16.json`保留全部manifest，API/tasks字节与生产相同。预登记另建target-17 D04/D06真实复测（data-17）：预计80 HTTP/$0.08、最坏200/$0.24，起点1490/$1.40885745/reserved0，仍受总cap2000/$2限制。须核对全部用途副本、独立余文、G15/G16/G12及完整产物，不把G17局部成功当整合同完成；无holdout/引擎发布。
- target-17已启动：后台shell `sh_16d2e31ec001l5FWpDOa8gSz01`，snapshot-16/data-17，D04/D06两份真实任务，结果待通知；不得重复提交。启动前manifest重验、独立target/data不存在及API端口空闲检查随启动运行。当前仅已实施/离线验证，不宣称新真实任务成功。
- target-17实际终态：D04/D06均完成真实登录/上传/seal/持久Worker/模型/授权下载，均incomplete（48 targets/15 unresolved、92/29）。G17业务局部通过：D04源2处、D06源4处全部删除、独立费用支出/降费权限余文逐字保留；机械2/2通过，final SHA分别`eb4986a6b3ec5d90dd50d7606cda2b305713566986b3943f864605dff50f4dba`、`200f897234af7afdb44144bb13ebcb3fd9eb95b3561450b11b4fcb5c51f31aa7`，18/17 ins和del。snapshot-16完整Claim分别false/5 failures、false/8；最后audit轮重放2 results/22 issues、1/29，不能代表全部历史审核。D04 G12/G16/G03及G17旧target身份冲突、D06 G11保护文字/G15等仍未完成。证据`target-17/{D04,D06}/{artifact-review.json,target-17-business-review.json}`及`target-17-{D04,D06}-snapshot16-replay.json`，真实产物为工作文件，不作为正式合同交付。
- target-17最终账本对账：新增62 HTTP/`$0.06612960`，与最终报告非checkpoint事件全部逐条匹配（missing0/unmatched0）；累计1552/`$1.47498705`/reserved0，剩448/`$0.52501295`，cap2000/$2不变。`target-17-metering-reconciliation.json`保存证据；无holdout/引擎发布。
- 审核更正：临时`review_target16_g17.py`曾误用旧D06排除标签且仅单段查找HEAD，首次输出保留但作废；依FL-D132/188，ETF联接D06正常修改，不能要求零修改。须补跨段读取、同站点余文逐字核验及全部原件用途句分母，另存更正版，旧labels/scorer保持不变。该审核失误续FL-D188。

## FL-D226 G15支付源范围检查过拒合法多类别前缀（2026-10-24）

- 问题与影响：target-16 D06 p807/p1286为C/E/F类完整支付与顺延安排，`_g15_payment_clause_end()`仅支持单类前缀，导致自身operation源授权检查false，阻止正常删除。D06属于可修改ETF联接，不能按旧排除标签忽略。
- 证据：原件`广发创业板交易型开放式指数证券投资基金发起式联接基金基金合同_20250319.docx`的上述两段，`_g15_payment_source_owned(text, builtin G15:0)`为false，仅去掉多类别前缀后为true；0 HTTP。target-17使用snapshot-16已启动，未混入本次修复。
- 处理：仅扩展支付头的有限类别枚举语法，支持重复“X类基金份额”及“X类、Y类基金份额”两种形式；继续逐句核验支付与顺延，不允许夹带独立政策句或核对责任。
- 状态：已实施，定向/真实原件及完整验证待完成。新增双副本实际DOCX与Claim验证、多类别前缀夹带政策及额外句反例。真实模型验证须待重新冻结，不以target-17或离线通过替代。
- 下一步：定向回归→真实D06原件零模型源范围与实际文件核验→完整回归及新快照→受预算约束的新真实开发集复测；holdout和发布仍阻断。
- 定向首轮2 failed/70 passed：源授权已修，但planner重复旧单类正则仍阻断合法双副本。删除该重复判断，统一依赖完整支付解析器后**72 passed/20.98s**。真实D06原件G15仅p807/p1286两处改动，均完整删除，其他段落原样，Claim verified、接受/拒绝修订等价通过，0 HTTP，证据`offline-d226-real/result.json`。完整回归后台`sh_16d32c3a3001uXM5zR7b6gvu5M`，启动manifest`d226-full-test-start.json`及`d226-full-pytest.log`；尚未冻结/真实复测此修复。
- D226完整回归结束**1443 passed/46 skipped/2 warnings/293.62s**，源码manifest相同，build `5cada9ddd46fc0dfe61f06a243dffb0bede48f5de3d2b39f6f9baf34c471820c`；结果`d226-full-test-result.json`。该结果不包含随后FL-D222复发/G03修复，不能拿来冻结后续增量。

## FL-D227 G03跨段“在投资｜者…”被误当作完整追加点（2026-10-24）

- 问题与影响：target-17 D04实际p82原文以“本基金根据申购费用收取方式的不同，将基金份额分为不同的类别。在投资”结束，p83续“者申购基金份额时…”。当前G03政策插在p82“类别。”之后、“在投资”之前，割裂同一定义条款；应在完整类别定义后追加。
- 证据：`target-17/D04/artifact-review.json`的p82实际变化，原件p83为完整A/C收费定义、p84为货币细分。现有词法延续识别只覆盖裸类字母等少量断点，未覆盖句中任意汉字拆分；机械plan一致不能证明追加点业务正确。
- 状态：已确认，尚未修复。真实批次保持incomplete，独立完整分母未完成；未修改labels/gold/scorer。
- 处理方向与下一步：按真实定义未闭合的句子与连续原文重算追加尾，不能从最后标点倒退到定义第一句后即当作完整条款；增加“在投资｜者…”实际DOCX与Claim反例及邻接独立条款边界，再做完整回归和新冻结真实复测。

## FL-D228 G12显式比例变体被保护字面量误拒（2026-10-24）

- 问题与影响：target-17 D04 p198的原件为“赎回费总额的25%应归基金财产，其余用于支付登记费和其他必要的手续费”，属于G12旧分配政策的明确比例变体；模型已生成指引固定新政策，但通用数字保护把25%及其分配句当作未授权删除，G12实际未修改，合同保持incomplete。G13相邻7日/1.5%句仍应由独立G13 operation处理，不能借G12授权删除。
- 证据：缓存模型输出`/tmp/opencode/operation-validation-20261024/data-17/checkpoints/7d5db532eeb1ef26cf80f48cafeddcb62eb7f1466ea9942b602aafa31ff241e0.json`；原件`/home/opencode/data/funds_word/广发亚太中高收益债券型证券投资基金基金合同_20230223.docx` p198；旧target-17报告G12 unresolved及Claim失败证据保持不变。
- 处理：增加窄范围`_g12_allocation_end()`，只识别G12自身replace operation的承接句、合法显式比例和登记/手续费尾；仅在G12源范围完整证明时使用确定性替换，并把该完整源片段加入同一operation的验证授权。未取消数字保护、未使用模型provenance自授权、未吞并独立后续句；补充实际比例变体零模型DOCX和Claim回归。
- 状态：已实施，定向回归及真实D04比例边界零模型验证通过：G12新政策写入、G13的7日/1.5%句保留、Claim与接受/拒绝修订等价均通过。FL-D228全量启动后又收窄了G12边界并追加了回归测试，故D228即使通过也不能作为包含最终源码/测试集合的冻结证据。
- D228中间全量随后结束为**1452 passed/46 skipped/2 warnings/284.20s**；但启动manifest与当前源码不一致，原因正是本条后续收窄G12边界并追加测试，故只作中间回归证据。最终manifest重跑尚未完成。
- 下一步：以完整最终源码/测试manifest重跑全量→重新冻结→重新登记预算并真实复测D04/D06；target-17旧产物不覆盖本修复，holdout、引擎发布及最终普通工作台E2E继续阻断。
- 最终回归已按最终manifest完成：**1453 passed/46 skipped/2 warnings/280.23s**，177个Python源文件manifest与启动时一致，build `e4ae767880625a3cf090fd500283facd28caab2f696e96c35551ab74b65dc172`；证据`final-full-test-start.json`、`final-full-pytest.log`、`final-full-test-result.json`。已冻结`/tmp/opencode/operation-validation-20261024/snapshot-17`，上下文`run_context-17.json`，生产API/tasks字节在冻结时一致。
- post-D228真实批次已预登记为target-18：snapshot-17、公开开发合同D04/D06、真实登录→上传/seal→持久Worker/model→授权下载，预计80 HTTP/$0.08，最坏200/$0.24，账本起点1552/$1.47498705/reserved0；仅开发集，不运行holdout。当前工作区发布到生产并完成服务/build核验后才能启动；target-17历史结果不得复用。
- 生产账本核对：`/var/lib/fundlex/model_budget.sqlite`当前为26919 requests/`$21.81123075`（completed26874、failed32、abandoned13），属于历史生产流量，不并入本轮隔离评测账本。target-18使用上述run_context登记的临时共享ledger，生产代码仅作为已发布快照一致性复核；两本账本均不重置。

## FL-D229 target-18验证包装器参数顺序错误（2026-10-24）

- 问题与影响：首次启动target-18时将包装器调用写成`run dev target-18 D04 D06`，而`fundlex-operation-validation.py`的实际接口是`dev <run-id> <case_id>...`（`run`仅是误传的group值）。`p6_run.py`在参数解析阶段以`--group run`退出，未启动合同任务、登录、上传、Worker或模型调用；不能计入真实评测结果，也不能消耗预算。
- 证据：shell命令`sh_16d542a77001GWC6jvid0LtxXr`，退出码1，错误`argument --group: invalid choice: 'run'`；隔离ledger仍为1552 requests/`$1.47498705`/reserved0，`target-18`目录不存在。
- 处理：保留本次零调用失败记录，按包装器实际接口重新执行`dev target-18 D04 D06`；不覆盖target-17，不修改selection、gold或历史结果。
- 状态：参数错误已定位，正确的target-18真实批次待执行；holdout、引擎正式发布和最终普通工作台E2E仍阻断。

## FL-D230 生产普通工作台验收脚本未跟随React V2表单契约（2026-10-24）

- 问题与影响：当前生产真实用户验收脚本先在登录页使用 `get_by_role('heading', name='FundLex')`，随后又沿用旧版提交按钮文案 `创建、上传并提交`，并遗漏 React V2 新建任务表单必填的任务名称；React V2 登录页按品牌结构使用 `<strong>FundLex</strong>`，新建任务按钮实际为 `创建任务并上传`。脚本分别在注册前、提交按钮定位和表单校验后等待路由阶段失败，不能据此判断生产页面、认证、上传或模型链路失败。
- 证据：`/tmp/opencode/fundlex-production-v2-e2e-20261024-rerun-d230/e2e-7db20hwbfitu/result.json` 显示已完成注册、登录、当前指引和新建任务页；数据库只读核对没有本次执行对应的新任务。源码 `frontend/src/pages/Auth/index.tsx` 明确显示登录页品牌为 `<strong>FundLex</strong>`；`frontend/src/pages/NewTask/index.tsx` 明确显示任务名称为必填、提交按钮为 `创建任务并上传`。本次没有发生模型调用。
- 处理方法：验收脚本改为精确文本选择器 `get_by_text('FundLex', exact=True)`，填写“任务名称”，按当前产品文案定位提交按钮，并继续使用独立输出目录，避免历史结果污染；不修改产品页面或认证行为。
- 状态与验证：**脚本问题已修正并验证**。d230c 已完成注册/登录、当前内置指引、公开 DOCX 上传、任务创建、seal、持久 Worker/model、任务详情、Review 页面/API、报告和授权下载；脚本断点已不再阻塞。合同交付结果另由 FL-D235 登记为 `incomplete`，不能把脚本修正等同合同交付通过。
- 下一步：保留 d230c 产物作为当前生产版本失败证据；引擎修复、完整回归、新快照和新的真实复测完成后，再按同一用户路径重验。

## FL-D235 d230c生产真实合同的G01/G15操作级证明失败导致交付不完整（2026-10-24）

- 问题与影响：当前生产工作台真实任务 `7aefa94ca9b64c83b64cc06f35941fff` 使用公开合同“广发品质回报混合型证券投资基金基金合同_20230708.docx”和内置指引 `builtin-v1` 完成了模型处理及DOCX生成，但最终交付门禁仍为 `incomplete`。报告的12个未决项集中在G01 p106追加和G15正文/摘要支付句（p806/p807、p1262/p1263）：G01报 `CLAIM_OPERATION_NOT_PLANNED`，目标location=p106但quote为p107的“指定媒介”定义，resolution=quote_not_found、最终not_applicable，G01没有形成编辑；G15四个站点报 `CLAIM_OPERATION_SPAN_UNAUTHORIZED`/`CLAIM_PLANNED_EFFECT_MISSING`。因此产物只能作为工作文件和失败证据，不能授权为最终合同。
- 证据：独立结果 `/tmp/opencode/fundlex-production-v2-e2e-20261024-rerun-d230c/e2e-gypkvi0ewhlz/result.json`；报告 JSON/Markdown `/tmp/opencode/fundlex-production-v2-e2e-20261024-rerun-d230c/e2e-gypkvi0ewhlz/report.json`、`report_md.md`；机械复核 `/tmp/opencode/fundlex-production-v2-e2e-20261024-rerun-d230c/e2e-gypkvi0ewhlz/artifact-review.json`。真实任务状态 `completed`，文档 `succeeded`、`eligibility=eligible`、`delivery_status=incomplete`，任务 `exceptions=1`；目标处理统计为31/31，但报告仍列12个最终未决项。模型报告记录29次 HTTP、147104 tokens、估算 `$0.025806`。Review 页面/API均返回成功并有18条修订记录；脚本未提交 Review 决策，因此不能声称用户已接受或拒绝全部修订。
- 产物与实际差异：授权下载成功，`working_final.docx` SHA-256 `cbbe28e31fedc5a36e80aa2638da10cf1dc07953c74ec9ef0ab184a07e0d4f6d`，`working_redline.docx` SHA-256 `5865fc9344a88fb0acb1752ac66ce7f2a26a58751a45a26dc9d3ef37df488815`；报告期望哈希与下载哈希均匹配。机械复核通过 source/final/redline 哈希、接受/拒绝修订等价、无残留修订、段落位置、计划与实际文件一致；准确XML解析为修订版18处插入/18处删除，终稿无残留修订，18个实际改变段落。逐站点确认终稿p106与原件相同，G01没有形成追加；G15四个正文/摘要支付段已删除，但其自身授权范围没有通过Claim Replay证明。
- 证据更正：初步全文检索发现直销政策，只能证明其他位置有新增政策，不能归因G01 p106；逐站点复核已推翻该归因。初步脚本使用`bytes.count(b'<w:ins')/b'<w:del'`统计得到28/46/57，会误计`w:instrText`、`w:insRsid`等标签/属性；按WordprocessingML命名空间准确解析得到终稿0/0、修订版18/18，以`artifact-review.json`为准，保留原始result.json不重写。
- 处理方法：保留全部真实任务、报告、Review/API和下载证据，不修改该任务报告，不把 `completed`、DOCX可读、哈希匹配或单纯实际差异当作交付完整。修复G01追加站点边界及G15自身operation的跨段/双副本授权范围后，必须完整回归、冻结新快照并以新任务复测；不得修改gold/labels以消除失败。
- 状态与验证：**已确认，当前版本未解决**。真实用户端到端链路已验证到授权下载，但合同完整交付失败，阻塞最终项目验收。证据显示问题属于引擎的目标/operation证明与交付门禁，非登录、上传、Worker、模型调用、DOCX打包或下载故障。
- 下一步：先完成FL-D231/FL-D232/FL-D233/FL-D234相关引擎修复及定向/完整回归；重新冻结版本后，再按公开合同开发集协议执行真实复测并核对G01/G15全文、Claim Replay、Review决策、报告、修订、接受/拒绝版本和哈希。

## FL-D236 生产任务目标统计与报告最终未决数口径不一致（2026-10-24）

- 问题与影响：d230c任务详情/API显示文档 `target_counts.total=31, completed=31, unresolved=0`，而同一文档报告显示 `delivery_status=incomplete`、`unresolved_count=12`，任务摘要还显示 `exceptions=1`。如果前端只展示目标计数，用户可能误以为合同已经完整交付；最终状态应以报告交付门禁和最终未决项为准。
- 证据：同一独立结果 `/tmp/opencode/fundlex-production-v2-e2e-20261024-rerun-d230c/e2e-gypkvi0ewhlz/result.json` 第15–39、53–206行，以及下载的 `report_md.md` 第7、51–66行。任务、文档、报告均来自同一个真实任务ID `7aefa94ca9b64c83b64cc06f35941fff`，不是跨任务拼接。
- 处理方法：当前验收按 `delivery_status=incomplete`、`report.unresolved` 和 Claim Replay失败判定，不以 `target_counts.unresolved=0`覆盖最终门禁；后续应统一任务摘要、文档目标统计和报告最终未决投影，或在UI明确区分“目标已处理”和“交付门禁未通过”。
- 状态与验证：**已确认，待产品/接口口径修复**。本条不改变d230c失败结论，也不修改历史报告或评测分母。
- 下一步：检查任务详情API与React V2展示字段的映射，补充含Claim Replay失败、报告incomplete和exceptions的真实回归；修复后用新真实任务验证显示和下载状态一致。

## FL-D231 target-18 D04 G12/G13 同段独立 operation 未形成原子变换（2026-10-24）

- 问题与影响：D04 p198 同时包含 G12 的赎回费分配句和独立 G13 的少于 7 日/1.5% 句。target-18 将 G12 绑定为 `T013`、G13 绑定为 `T014`，两者源范围相交；规划阶段报 `RECALL_EDIT_OVERLAP`，两个 operation 都没有进入最终 edit set，导致比例旧文和短持有期旧文均保留，合同交付不完整。
- 证据：`/tmp/opencode/operation-validation-20261024/target-18/D04/report.json` 中两个 target 的 `plan_reason` 均为 `RECALL_EDIT_OVERLAP`；原件 `/home/opencode/data/funds_word/广发亚太中高收益债券型证券投资基金基金合同_20230223.docx` p198 为“...25%应归基金财产...手续费。对于持续持有期少于 7 日...1.5%...”。
- 处理方法：保持 G12 的比例识别和 G13 的独立授权，规划时将重叠的 replace/delete 组件合成为一次有 operation keys、obligation ids 和各自源切片的原子 paragraph 变换；G12 只替换比例分配前缀，G13 只删除短持有期句，并保留独立尾部。Claim Replay 必须逐 component 证明两个 operation。
- 状态：**已确认，代码修复已实施，待完整回归及真实复测**。target-18 真实 Worker/model、DOCX 下载和机械校验已完成，但历史 Claim Replay 为 false，不能计入合同完成分母的通过项。当前源码已将 G12:1 与 G13:0 合并为一个带独立 operation keys、obligation ids 和源切片的原子 paragraph edit。
- 证据更新：`/tmp/opencode/operation-validation-20261024/offline-d231-d234-real-current/D04/result.json` 从 D04 原件零模型重建验证 `proof_verified=true`、G12/G13 两个 component 独立存在、比例旧文和短持有期旧文均删除；接受/拒绝修订分别与终稿/原件等价，`http_attempts=0`。该证据不改变 target-18 历史失败，也不替代新的真实模型任务。
- 下一步：完成最终源码全量回归和新快照后重新真实复测 D04，并核对完整合同业务门禁。

## FL-D232 target-18 D04 G12 stale target 在 G09 位置无法确定性重绑定（2026-10-24）

- 问题与影响：D04 报告产生 `T3001`，把 G12:0 错误候选绑定到 p194，同时 p194 的真实变更属于 G09。该 target 没有 quote、offset 或唯一候选，`RECALL_TARGET_UNRESOLVED` 使 G12:0 保持 OPEN，并污染 operation/site 覆盖判断。
- 证据：`target-18/D04/report.json` 的 `T3001` 为 `location=p194`、`quote=''`、`site_candidates=["p194","p199"]`、`operations=["G12:0"]`；同报告 p194 的 edit 为 G09:0。D04 原件 p194 不含 G12 赎回费分配旧文，p198 才是 G12 site。
- 处理方法：对 open operation 候选在 target 绑定前执行 operation 自身 source/reference 和业务 site 校验；候选不含该 operation 的旧文或唯一语义站点时拒绝重绑定并标记 stale/attribution error，不能把另一个 operation 的 edit 当作覆盖。若同 operation 已有确定的 p198 site，stale candidate 必须被 supersede，不产生新的可执行 target。
- 状态：**已确认，代码修复已实施，待完整回归及真实复测**。现有报告保留为历史证据；不得修改 gold、target-18 分母或把 G09 结果计作 G12 完成。当前恢复候选已加入 operation 自身 source/reference 和业务 site 校验，D04 stale `T3001` 不能借用 p194 的 G09 edit。
- 证据更新：新增 stale open-operation recovery 回归已通过；D04 当前离线重建未产生 G12:0 的错误 p194 绑定。证据目录为 `/tmp/opencode/operation-validation-20261024/offline-d231-d234-real-current/D04/`，`http_attempts=0`。该证据不改变 target-18 历史失败，也不替代新的真实模型任务。
- 下一步：完成最终源码全量回归和新快照后重新真实复测 D04，核对 G12:0/G12:1 的真实 source site 与 operation coverage 独立闭合。

## FL-D233 target-18 D06 G11 composite continuation 删除吞掉受保护 E/F 类文本（2026-10-24）

- **2026-10-28 授权边界补充（不静默推翻本条保留措施）**：指引零基段46的旧条款1包含承担句＋C类免收费句，47的条款2只含承担句，48要求直接替换完整新文；因此“G11永远只授权bearer句”不成立。D06 p228–229是否构成条款1的同义异构整体，须先由模型及独立复核按实际A/Y、C/E/F收费组判定，不能凭跨段、句号或当前planner切片先认定独立政策。完整授权条款替换不需再批；**确认在授权范围外的独立句仅为去重额外删除**才是窄业务新增授权。现有slice保留不因本次文档核查自动取消，后续应以统一语义授权和原件回查重新验证。

- 问题与影响：D06 p228/p229 的 G11 旧句跨段：p228 以“承担，”结束，p229 以“ 不列入基金财产。”完成旧句，随后同段还有独立的 C/E/F 类申购费政策。target-18 的 composite tail 删除把 p229 整段写空，丢失 `E类基金份额`、`F类基金份额` 等受保护业务字面量，形成 `LOST_PROTECTED_LITERAL` 风险。
- 证据：`target-18/D06/report.json` 与下载 DOCX 的独立复核显示 p229 源文为“ 不列入基金财产。本基金 C 类基金份额、E 类基金份额和 F 类基金份额不收取申购费。”，结果 p229 被替换为空；原件路径为 `/home/opencode/data/funds_word/广发创业板交易型开放式指数基金发起式联接基金基金合同_20250319.docx`（文件名以实际目录为准）。
- 处理方法：composite continuation 按 operation 自身 authorized slice 计算每个 part 的删除范围；p229 仅删除“ 不列入基金财产。”及其授权标点/空白，保留后续 C/E/F 句。任何 protected literal 丢失都必须使 plan/Claim 失败，不能由 joint_delete 的空 replacement 证明覆盖。
- 状态：**已确认，代码修复已实施，待完整回归及真实复测**。target-18 mechanical artifact verification 通过只证明文件可读和计划哈希一致，不证明受保护业务文本完整。当前 composite continuation 已按 G11 自身授权 slice 计算 p229 删除范围。
- 证据更新：`/tmp/opencode/operation-validation-20261024/offline-d231-d234-real-current/D06/result.json` 从 D06 原件零模型重建验证 `proof_verified=true`；p229 仅删除 continuation，C/E/F 类申购费句逐字内容（按紧凑文本）保留；接受/拒绝修订分别与终稿/原件等价，`http_attempts=0`。该证据不改变 target-18 历史失败，也不替代新的真实模型任务。
- 下一步：完成最终源码全量回归和新快照后重新真实复测 D06，核对完整合同业务门禁。

## FL-D234 target-18 多站点 operation attribution 与 coverage 聚合丢失独立 site（2026-10-24）

- 问题与影响：D06 Claim Replay 在 G02/G04/G08/G11 等多 site operation 上同时出现 PASS site 与 `CLAIM_OPERATION_NOT_PLANNED`/`CLAIM_OPERATION_UNPROVEN` site。当前部分聚合路径按 operation 或 location 汇总，导致已证明 site 被整体视为未计划，或失败 site 未能保持在 coverage/unresolved 中，无法准确表达“一个 operation 的每个业务 site 必须通过”。
- 证据：`/tmp/opencode/operation-validation-20261024/target-18-D06-r1-replay.json` 的 failures 与 `proof.obligations` 保留了 operation/site 级失败；D06 report 的 `coverage`、`unresolved` 与下载 artifact 复核之间存在 site attribution 不一致。具体 operation/site 证据以该 replay JSON 为准。
- 处理方法：以 `(operation_id, obligation_id, site_id/location[, occurrence])` 作为 coverage/effect 的最小身份；成功 site 单独保留，失败或缺证 site 单独保持 OPEN/FAIL。operation 只有在其全部 verified sites 通过且无缺失 site 时才可 PASS，不能用同 operation 的另一个 site 或 rule-level status 抵销。
- 状态：**已确认，代码修复已实施，待完整回归及真实复测**。不能用机械 DOCX 成功、单 site PASS 或 report complete 字段替代整合同交付 gate。当前 coverage/effects/Claim Replay 已按 operation、obligation、site/location 和 occurrence 保留独立 site。
- 证据更新：重复 site、部分 site 成功和缺失 occurrence proof 回归均已通过；D04/D06 当前离线重建的 operation-level Claim Replay 均通过，证据位于 `/tmp/opencode/operation-validation-20261024/offline-d231-d234-real-current/`，`http_attempts=0`。该离线证据不改变 target-18 历史失败，也不替代新的真实模型任务。
- 下一步：完成最终源码全量回归和新快照后，用新的真实 D04/D06 任务核对 coverage view、delivery gate、Claim Replay 与 DOCX 实际差异使用同一 site ledger。

## FL-D237 target-19 D06 G02/G04 已满足组成员被误判为 residual（2026-10-25）

- 问题与影响：D06 target-19 的 p231 已逐字包含完整 A/Y 与 C/E/F 收费分组，但 G02:1/G04:1 的 operation effect 把其中必然保留的 `C类基金份额` 成员标签当成旧单类残留，Claim Replay 分别报 `RESIDUAL_OLD_TEXT`/`CLAIM_OPERATION_NOT_PLANNED`，并使真实任务交付为 `incomplete`。p98、p131 同一类已满足站点则通过，说明是 residual/effect 的局部判定不一致。
- 证据：`/tmp/opencode/operation-validation-20261024/target-19/D06/report.json` 的 `artifact_claim_replay.obligations`；G02:B1:O2 和 G04:B1:O2 的 p231 site effect 失败，p98/p131 通过。p231 实际终稿文本由独立读取确认包含完整 C/E/F 组。旧任务产物和报告保持不变。
- 处理方法：G02/G04 的 replace operation 仅在旧文是单一 `[A-Z]类基金份额`、且最终段落在收费语境中包含完整实例化新组时，授权该旧标签作为组成员保留；普通 replace 不改变该例外。同步把 `_replaced_clause_residuals` 的 clause residual 过滤到同一 operation proof，避免字面残留层再次拒绝语义正确的组。新增 G02/G04 满足站点回归。
- 状态与验证：**代码已实施，待最终全量回归和新的真实 D06 任务验证**。新增定向回归此前为 161 passed；D04/D06 post-patch 零模型真实原件边界重建的关键检查全部通过，但不计真实模型分母。尚未证明新真实 Worker/model 产物已闭合。
- 下一步：全量回归通过后冻结新快照，重新部署与核对字节一致，再用剩余预算重新执行 D06；逐站点复核 G02/G04、p98 sweep、G06 人工未决、Claim Replay、报告和实际 DOCX。若 G06 单向转换仍无授权决策，保持未完成。

## FL-D238 target-19 D06 p98 G02 sweep scope quote 未被 operation proof 消解（2026-10-25）

- 问题与影响：target-19 p98 的 G02 sweep finding `SW002` 只引用同段开头的类别枚举，实际收费分组句紧随其后且已完整满足 G02。当前 `_quote_is_expected_effect` 的新增分支要求调用方同时传入完整 `actual_text` 与 operation proof；历史 report 的 finding 仍为 pending，不能直接改写为修复后结论。
- 证据：`target-19/D06/report.json` 的 `sweep.findings` 中 `SW002`；p98 target 已为 `satisfied`，quote 为“基金份额类别：本基金将基金份额分为…”，同段后续收费句含 A/Y、C/E/F 完整分组。旧 report 不能证明新分支已在真实管线中运行。
- 处理方法：保留 scope quote 与真实可编辑收费 site 的边界；只有同段完整 operation proof 通过，且 scope quote 本身没有费用词、同段 actual text 含完整认证组时，才把该 sweep finding 标记为 artifact-proof resolved。不能通过报告层直接删除 finding，也不能让一个不相关段落提供证明。
- 状态与验证：**代码已实施，待新真实 D06 任务验证**。本地 `_class_group_equivalent` 和 post-patch 零模型边界验证通过；target-19 历史 `SW002` 仍保持原始 pending 证据。新运行需确认 sweep finding 的最终状态和 delivery gate 一致。
- 下一步：新快照部署后读取新的 D06 report，独立检查 p98 finding、operation/site ledger 与实际段落；若仍 pending，登记新的根因并继续修复，不能以局部回放关闭本条。

## FL-D239 target-20 D06 独立业务复核脚本误报三项失败（2026-10-25）

- 问题与影响：target-20 D06 的第一次独立业务复核文件将三个证据口径误判为失败：G02/G04 只匹配带空格的 `A 类、Y 类` 与固定完整句，未接受实际 DOCX 中语义等价的紧凑写法；G11 要求所有 site 必须为 `ARTIFACT_VERIFIED`，错误排除了独立 `ALREADY_SATISFIED`；复核映射遗漏了 G17 明确授权删除的 p808、p809，导致 19 个实际变化段中两段被标为 `REVIEW_REQUIRED`。这些误报没有改写 target-20 report、DOCX、Claim Replay 或交付门禁。
- 证据：初始证据 `/tmp/opencode/operation-validation-20261024/target-20-D06-independent-business-review.json` 的 `failed_checks` 为 `g02_all_sites`、`g04_all_sites`、`g11_operation_coverage_protected`，并将 p808/p809 标为 `UNKNOWN/REVIEW_REQUIRED`；实际 p98/p131/p231 均包含完整 A/Y 与 C/E/F 收费组，operation coverage 中 G02/G04 三站点均为 `ALREADY_SATISFIED`，G11 p228 为 `ALREADY_SATISFIED`、p229 为 `ARTIFACT_VERIFIED`。
- 处理方法：独立复核改为先折叠空白再比较类别组，按语义组核对 A/Y 与 C/E/F；G11 site 允许 `ALREADY_SATISFIED` 或 `ARTIFACT_VERIFIED`；补入 p808/p809 的 G17 业务映射。保留初始失败 JSON 作为审计历史，另写 corrected 证据，不修改真实 report 或历史产物。
- 状态与验证：**已确认，复核证据已修正**。`/tmp/opencode/operation-validation-20261024/target-20-D06-independent-business-review-corrected.json` 显示 19/19 实际变化段通过、25/25 断言通过，结论为 `INCOMPLETE_G06_REVIEW_REQUIRED`。G06 的单向 Y 类转换语义变体仍被明确保留为人工业务未决，target-20 交付仍为 `incomplete`。
- 下一步：将 corrected 证据作为 target-20 D06 的独立业务复核依据；继续保持 G06、target-20 report 的 Claim Replay 失败和开发集门禁未决，不以修正复核脚本关闭真实业务阻塞。

## FL-D240 20份开发集闭环的当前快照证据与评测预算不足（2026-10-25）

- 问题与影响：target-20 D06 已完成 snapshot-19 的真实登录、上传、seal、持久 Worker/model、结果页和授权下载，但 G06 未决，不能计为完整合同交付。当前共享评测 ledger 已消耗 1701 requests、`$1.64408310`，reserved=0，仅余 299 requests、`$0.35591690`。D04 的最近真实通过证据属于 snapshot-18，D06 的最近真实复测属于 snapshot-19；其余开发合同的主要真实产物来自更早快照。因此现有证据不能构成同一冻结版本下 20 份开发集完整业务 gate，也不能据此进入 holdout、正式引擎发布或最终普通工作台 E2E。
- 证据：共享账本 `/tmp/opencode/operation-validation-20261024/ledger.sqlite`；target-19 D04 独立复核 `/tmp/opencode/operation-validation-20261024/target-19-D04-independent-business-review.json`；target-20 D06 report、artifact review、corrected 独立复核分别位于 `/tmp/opencode/operation-validation-20261024/target-20/D06/`、`/tmp/opencode/operation-validation-20261024/target-20/D06/artifact-review.json` 和 `/tmp/opencode/operation-validation-20261024/target-20-D06-independent-business-review-corrected.json`。账本按状态为 completed=1698、failed=2、abandoned=1、reserved=0。
- 处理方法：固定 20 dev + 8 holdout selection、labels、gold、scorer 和 ledger，不删除或重置历史失败，不把旧快照产物冒充 snapshot-19 结果。已完成的 target-19/20 真实任务、下载 DOCX、报告、operation/site coverage、Claim Replay、独立逐段复核和哈希证据分别保存；预算不足时停止扩大真实调用，并把未取得当前冻结版本证据的合同保持为未完成/待复测。
- 状态与验证：**外部预算阻塞，开发 gate 未通过**。target-20 D06 机械 artifact verification 为 1/1，19 个实际变化段独立复核 19/19 通过，但 Claim Replay 仍因 G06 为 false，delivery gate 的 `UNRESOLVED=1`、blocking_unresolved=2；不能用目标计数 `unresolved=0` 或机械通过覆盖交付门禁。
- 下一步：若要完成同一冻结版本的 20 份开发集闭环，需要新增或明确授权评测预算后，重新登记批次并从剩余开发合同中按固定分母继续真实工作台运行；在此之前保持 holdout、正式发布和最终普通用户 E2E 阻断，并如实交付当前工作文件及未决清单。

## FL-D241 D01-D20 固定分母对账显示当前 gate 为 0/20（2026-10-25）

- 问题与影响：需要把 D01-D20 的最新保留证据按同一当前快照、机械产物、Claim Replay、delivery gate 和独立整合同业务复核分别对账，避免把 dev-05 的旧快照产物、目标计数或段落级检查误算为当前开发 gate。对账结果为当前 snapshot-19 gate eligible **0/20**：仅 D06 有 snapshot-19 证据且仍因 G06 不完整；D04 的独立整合同通过属于 snapshot-18；其余 18 份主要证据来自更早的 dev-05，业务复核 pending。
- 证据：机器可读对账 `/home/opencode/fundlex/docs/evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.json`，明细 `/home/opencode/fundlex/docs/evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md`。对账固定引用 selection SHA `95fe8121d5f0aceb4febf9cc76a79fde78cf44f711e9a6f029b08eb6ee5643f3`、snapshot-19 build `e2ac0f14429de4fdd71e631d10c18b27f1366c8337e797b4c834b5adf6611229`、历史 dev-05 产物、target-19 D04 和 target-20 D06 证据。
- 处理方法：建立每份合同的证据来源、快照、delivery、机械核验、Claim Replay、delivery gate、独立业务复核和当前 gate eligibility 字段；保留历史文件，不改写 labels、gold、scorer、report 或 DOCX。按 dev-05 实际每合同模型消耗估算，保留当前 D06 并补跑其余 19 份需约 602 requests / `$0.60031875`；当前余量 299 requests / `$0.35591690`，最低基线缺口约 303 requests / `$0.24440185`，且不含重试和 G06 修复调用。
- 状态与验证：**已登记，开发 gate 仍阻塞**。对账脚本生成 JSON/Markdown 后，校验了 20 个固定 case、账本 1701 requests / `$1.64408310` / reserved 0、当前 gate eligible=0、模型调用增量为 0；历史 complete delivery 为 4/20，但独立整合同业务通过只有 target-19 D04 的 1/20，不能作为 snapshot-19 gate。
- 下一步：预算获得新增或明确授权后，冻结与 snapshot-19 一致的真实开发批次，补跑并独立复核 D01-D05、D07-D20，重新处理 D06 G06 决策；预算未到位前保持 holdout、正式发布和最终普通工作台 E2E 阻断。

## FL-D242 dev-05 历史产物独立整合同业务复核分类与同段 G12/G13 复核边界（2026-10-25）

- 问题与影响：固定分母对账初始把 dev-05 的所有合同都列为业务复核 pending。对可离线核验的 complete/replay 候选继续复核后，D02、D16、D17 的 snapshot-05 实际 DOCX 通过独立逐段、规则效果、operation coverage、Claim Replay 和 delivery gate 交叉核对；D18 明确因 G17 p776/p1227 重复/残留句、delivery gate 未完成而失败。若不更新分类，会低估已有历史证据；若将其视为当前通过，又会错误跨越 snapshot-19 固定 gate。
- 证据：`/tmp/opencode/operation-validation-20261024/dev-05-independent-business-reviews/D02-independent-business-review.json`、`D16-independent-business-review.json`、`D17-independent-business-review.json` 为 `PASS_FOR_HISTORICAL_INDEPENDENT_BUSINESS_REVIEW`；`D18-independent-business-review.json` 为 `FAIL_OR_REVIEW_REQUIRED`。机器可读固定分母对账已更新为 D01-D20：历史独立业务通过 4/20（含 target-19 D04）、pending 15/20、历史失败/未完成 1/20；当前 snapshot-19 gate 仍为 0/20。
- 处理方法：独立复核只把 D02/D16/D17 标为历史 snapshot-05 通过，并保留“当前 gate 不合格、必须 snapshot-19 重跑”的限制；D18 保持失败。D16 p221/p222 的 G12/G13 同段原子编辑按 operation/site 证据分别核对：G12 替换在 p221，p222 仅承担 G13 删除，不能因 p222 没有重复 G12 新句而误报。
- 状态与验证：**已完成历史证据分类并验证**。四份复核 JSON 的源文件哈希、实际变化段数量、段落变化、规则效果、机械产物、Claim Replay、delivery gate 和 final omission review 均已复核；D02/D16/D17 全部断言通过，D18 的失败断言与原报告未决项一致。未新增模型调用，未改写历史 report/DOCX。
- 下一步：当前 gate 仍需在 snapshot-19 重新运行 D01-D20；独立历史通过只作为审计证据，不能进入 holdout 或正式发布门禁。

## FL-D243 生产 API 端口与历史隔离评测端口不同（2026-10-25）

- 问题与影响：本机生产 `fundlex-recall-api.service` 监听 `127.0.0.1:8010`；历史真实评测使用过 `8013` 等隔离端口。若沿用旧评测端口做当前服务探测，会得到连接失败并误判 API 未运行，或把隔离评测入口当成正式服务入口。
- 证据：`systemctl status fundlex-recall-api fundlex-recall-worker` 显示生产 API/Worker 均 active；systemd 单元 `/etc/systemd/system/fundlex-recall-api.service` 的 `ExecStart` 明确为 `--host 127.0.0.1 --port 8010`；`ss -ltnp` 显示 8010 正在监听。当前只读核验中 8010 与 8013 的 `/api/capabilities` 均返回 200，但 8013 由独立 `fundlex-test-api.service`（工作目录 `/opt/fundlex-test`）提供，属于隔离测试服务，不是生产 API；本次没有修改服务或配置。
- 处理方法：生产服务验证以 systemd 单元和 8010 为准；隔离评测脚本必须显式使用其批次登记的端口、服务和数据目录，不能把 8013 的隔离服务响应写入生产健康结论。健康接口的未认证 401 要结合登录态验证，不能单独解释为服务失败。
- 状态与验证：**已登记并验证，当前无生产故障证据**。API/Worker active、8010 监听和 capabilities 200 均已核对；8013 当前是隔离测试服务，不能作为生产 API 证据。未新增模型调用，未改变部署文件。
- 下一步：后续真实工作台验收先确认 systemd/API 实际端口，再走登录、上传、Worker/model 和授权下载链路；将端口、认证状态和验证时间写入验收证据。

## FL-D246 `project_unresolved()` 诊断投影丢失全局 coverage 缺口类型（2026-10-25）

- 问题与影响：Ledger 成为唯一完成来源后，绑定 Claim Replay/obligation 证据应折叠到 canonical obligation 行；但没有 operation/site 身份的运行级 coverage 缺口（例如 `SWEEP_CHUNK_LIMIT`）不能绑定到某个 obligation。此前统一按未绑定证据转换为 `orphan_evidence`，导致报告丢失 `kind="coverage"`，用户和运维无法区分资源覆盖缺口与归属异常。
- 证据：`tests/test_recall_pipeline.py::test_sweep_chunk_limit_recorded_as_coverage_gap` 在修复前失败，报告只返回 `orphan_evidence`；同轮 `test_audit_failure_persists_incomplete_working_pair` 与 `test_tampered_plan_not_generated` 也用于确认绑定的高层 audit/plan 诊断仍需保留。修复后该三项为 **3 passed**，定向后端回归为 **286 passed**，完整 `tests` 为 **1467 passed / 47 skipped / 2 warnings / 289.47s**。
- 处理方法：`project_unresolved()` 仅将带 operation、obligation、target 或 rule+location 身份但无法绑定的证据转换为 `orphan_evidence`；无身份且原本为 `coverage` 的运行级诊断保留其 kind，并继续作为阻塞证据。绑定 Claim Replay/obligation 仍折叠到 Ledger 行，高层 audit、target、sweep、coverage 诊断保留。
- 状态与验证：**已解决，当前源码已实施并验证**。`compileall`、`git diff --check`、三项回归、286 项定向后端回归和完整测试均通过。完整测试的两个既有 warning 为 Starlette/httpx 弃用提示及测试构造的重复 DOCX ZIP 名称，不是本修复失败。
- 下一步：以当前源码重新生成精确测试 manifest 和候选 snapshot；由于当前工作区 `fundlex/api.py`、`fundlex/tasks.py` 与生产部署目录字节不一致，候选快照不能写成已发布版本。20 份开发集、发布和最终普通工作台 E2E 仍按 FL-D240–FL-D243 保持阻断。
- 变更记录：2026-10-25 新增；保留三项回归失败→修复→定向及完整回归通过链路。

## FL-D247 前端依赖安装与测试并发会产生无效缺失模块结果（2026-10-25）

- 问题与影响：前端 `npm ci` 会重建 `node_modules`。若与 Vitest、TypeScript 或 Vite 构建并发运行，测试进程可能在安装中途读取到不完整依赖树，报告 `debug/index.js` 或 TypeScript `lib.es2023.d.ts` 缺失。这会把环境操作竞态误报为代码回归，也会污染本轮验收证据。
- 证据：本轮并行执行 `npm ci --ignore-scripts --no-audit --no-fund` 与 `npm test`/`npm run typecheck` 时，Vitest 报 `Cannot find package .../node_modules/debug/index.js`，TypeScript 报 `lib.es2023.d.ts` 不存在；随后安装完成后串行重跑，Vitest 4 文件/9 项、typecheck、lint、build 全部通过。
- 处理方法：依赖安装完成后再开始测试、类型检查和构建；不采纳安装期间产生的失败作为代码证据。锁文件继续由 `npm ci` 校验。
- 状态与验证：**已解决（验证范围：2026-10-25 当前工作区）**。串行 `npm ci --ignore-scripts --no-audit --no-fund` 成功；其后前端 4 个 Vitest 文件/9 项、typecheck、lint、build、浏览器 7 项和后端聚焦 39 项均通过。
- 下一步：持续集成或交接脚本按串行安装→前端检查→浏览器/API 回归执行；若再次出现缺失模块，先核对安装进程和 `node_modules` 完整性，再判断代码失败。
- 变更记录：2026-10-25 新增；并行执行失败保留为环境竞态证据，不覆盖后续串行通过结果。

## FL-D248 React Compare 结果页缺少多组结果顺序导航与独立浏览器证据（2026-10-25）

- 问题与影响：旧版合同对比结果工具栏支持上一组/下一组；React Compare 迁移初版只提供差异内导航，用户在多组任务中必须返回分组卡片切换，且缺少结果视图在 390px 下的浏览器级验证。该缺口影响 Compare 功能等价审查和移动端结果阅读证据，但不改变后端差异计算。
- 证据：`frontend/src/pages/Compare/ComparePage.tsx` 初版结果工具栏只有“上一处/下一处”；`tests/browser/test_frontend_v2.py` 初版仅验证 `/compare` 空壳路由。Compare 旧实现 `frontend/compare.js` 的 `bind()` 同时注册 `compare-prev-pair` 和 `compare-next-pair`。
- 处理方法：React 结果工具栏加入当前组计数、上一组/下一组按钮，首尾组分别禁用；切组时重置移动阅读侧栏到原版。同步收紧帮助对话框关闭路径，避免关闭处理器和 `useEffect` 清理重复恢复焦点。浏览器测试使用独立 API 响应夹具验证两组结果切换、差异标记呈现、390px 双侧切换、横向尺寸约束及 page/console 错误。
- 状态与验证：**已解决（React/浏览器范围）**。`npm test -- --reporter=dot` 为 4 文件/9 项通过；`npm run typecheck`、`npm run lint`、`npm run build`、`git diff --check` 通过；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` 为 **8 passed**；`tests/test_compare_api.py`、`tests/test_compare_auth.py`、`tests/test_compare_worker.py` 为 **17 passed**。本条浏览器测试使用 API 夹具，不能证明真实 Compare Worker、真实模型或正式合同交付。
- 下一步：取得测试环境和预算后，在同一真实用户路径执行 Compare 多组 DOCX 上传→seal→持久 Compare Worker→结果页→下载报告，并将实际产物和报告核验结果登记；普通合同 D01–D20 门禁仍按 FL-D240–FL-D243 保持阻塞。
- 变更记录：2026-10-25 新增；初次浏览器测试出现一次结果工具栏异步渲染等待超时，改为等待“下一组”可见后重跑，完整 8 项通过。该一次性测试竞态不作为产品失败结论。

## FL-D249 React V2 前端候选受控发布与生产静态资源核验（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：React V2 候选在本地构建完成但未发布时，公网入口仍引用旧静态资源；若直接覆盖生产目录或重启整套服务，可能把未完成的引擎 dirty 改动混入发布，或丢失回滚依据。
- 证据：本次构建生成 `frontend/dist/index.html`、`assets/index-DYLFV7Bw.js`、`assets/index-BdkF_0-u.css`；候选与生产 SHA-256 逐文件一致，证据为 `/tmp/opencode/fundlex-frontend-publish-20261025-074321/deployment-evidence.json`。生产备份为 `/tmp/opencode/fundlex-frontend-publish-20261025-074321/deployment-dist-before.tgz`。发布后 API、Recall Worker、Compare Worker 均 active，Recall Worker PID 保持 `3107909`，公网首页 HTTP 200。
- 处理方法：只构建并同步 `frontend/dist`，发布前打包生产 `dist`，只重启 `fundlex-recall-api.service`；保留现有 Recall Worker 和引擎生产字节，不通过整仓发布器覆盖引擎候选。
- 状态与验证：**已解决（前端发布范围）**。生产静态文件、候选文件和公网资产 HTTP 200/字节哈希已核对；API/Worker 服务状态已核对。该条不等于召回引擎通过 D01–D20 或普通合同完整交付。
- 下一步：保留回滚备份；普通合同仍需沿真实登录、上传、Worker/model、Review、选择版和授权下载路径独立验收。
- 变更记录：2026-10-25 新增并完成受控发布验证。

## FL-D252 生产工作台视觉与响应式审查发现移动端信息密度问题（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：本轮对生产 `https://fundlex.club` 以 1440×900、768×1024 和 390×844 截图审查后，桌面端主要页面层级、卡片、表单和橙色状态体系一致；但移动端仍有几处桌面信息结构被压缩的问题。桌面顶栏的“消息”和“退出登录”按钮实际存在但继承了白色文字，在白色顶栏上几乎不可见，用户无法可靠发现这两个入口。指引配置的“可用版本”表格把长文件名压成极窄列，文件名按两三个字频繁换行；Compare 任务表的任务名和“结果”也逐字换行，阅读和扫描成本高。设置页运行能力使用原始内部值（如 `password`、`recall_first`、`formal`），且移动端标签和值的纵向排版关系不清晰。指引上传控件还显示浏览器原生英文 `Choose File / No file chosen`，与中文界面不一致。
- 证据：本次审查截图 `/tmp/opencode/fundlex-visual-audit-20261025/11-guides-mobile.png`、`13-settings-mobile.png`、`33-compare-mobile-overview.png`、`10-guides-desktop.png`；采集数据 `/tmp/opencode/fundlex-visual-audit-20261025/audit-data.json`。截图均在当前公网生产资产上重新生成，使用临时审查会话，审查结束已撤销会话；本轮未发起模型调用。
- 处理方法：修正顶栏按钮在浅色主题下的文字颜色并补充可见状态；移动端将长文件/任务数据改为卡片或定义明确的主次字段，长文件名允许自然截断并提供完整值查看；Compare 任务移动端优先显示任务名、状态、结果和查看操作，隐藏或折叠低优先级列；设置页将能力值映射为用户可理解的中文文案，并使用稳定的标签—值两列/分组布局；文件选择控件统一为中文包装控件或补充中文选择状态。
- 状态与验证：**已发布并完成公网基础回归，部分视觉项仍待复核**。本轮已修复浅色顶栏按钮可见性、统计卡间距、Compare 任务名/结果在移动端的最小宽度处理、设置页能力值中文映射和指引上传控件中文化；提交 `b78dc4a` 已推送，候选资产已同步生产。公网 smoke `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261025/result.json` 通过真实登录、关键路由、1440/768/390 三视口和零页面/控制台/404错误；针对性证据 `/tmp/opencode/fundlex-public-frontend-fix-20261025/result.json` 确认顶栏、设置、指引和帮助交互生效。指引可用版本表格的长文件名仍未在公网已有数据上单独复核，本条不等于整项视觉审查的全部建议已闭合。
- 下一步：如出现真实长文件名数据，在公网 390px 重拍指引表格并确认是否需要进一步调整信息层级。
- 变更记录：2026-10-25 新增；来源为生产页面多模态截图审查，不与此前移动导航宽度修复混为同一问题。
- 补充验证（2026-10-25，审查时点历史结论）：`followup-data.json` 确认消息/退出登录 computed color 和顶栏背景同为 `rgb(255,255,255)`（对比度 1:1）；`app.css:6` 的 `.topbar-actions .ui-button--quiet` 特异性高于后续通用 quiet 规则。统计卡首行第一张 y=179、其余 y=193，落差 14px，与 `.ui-card + .ui-card { margin-top:14px }` 作用于 grid 子项相符；390px 任务表起点 y≈1241，表格容器宽 324px、内容宽 667px；导航当时只有前五项可见。上述事实已在本轮源码处理中分别修正或保留为待公网复核项，详见本条后续“补充处理与验证”。
- 补充处理与验证（2026-10-25）：本轮源码在 `.topbar-actions .ui-button--quiet` 增加浅色顶栏覆盖规则，在 `.stats-grid > .ui-card` 清除相邻卡片上边距；Compare 任务表保留内部横向滚动并限制卡片/主内容宽度，设置页将 `password`、`recall_first`、`formal` 等内部值映射为中文，指引上传改为中文按钮并显示文件名。最新候选构建为 `frontend/dist`，资产 SHA-256：`index.html`=`8a1cb7f50066dca6450d4a77c080ca71a99caddaafb8818891993bf9cacca0c9`、`index-DgSYi7V7.js`=`a64f599ba6e405767e680f829c37a9db4e2e567bcc9611846787f7945d580091`、`index-CbzfypI-.css`=`4673c786f89d28f968725458e839088edf1d7026011964d0342f157339f22353`。本地三视口证据为 `/tmp/opencode/fundlex-ui-fix-visual-20261025/visual-data.json` 及对应截图；1440、768、390px 的 document/body 宽度均等于 viewport，帮助与 Compare 检查页面/控制台错误为 0。生产仍未同步本候选。

## FL-D253 帮助弹窗没有限制键盘焦点在对话框内（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：帮助中心打开后，关闭按钮获得初始焦点，按 `Shift+Tab` 即可把焦点移到背景页面的“帮助中心”触发按钮；焦点可以离开 `role="dialog" aria-modal="true"` 的弹窗。键盘用户可能在弹窗尚未关闭时操作背景控件，且视觉上看不到焦点所在位置。
- 证据：交互采集记录 `/tmp/opencode/fundlex-visual-audit-20261025/audit-data.json` 的 `help-dialog-shift-tab`：`insideDialog=false`，焦点落在 footer 的帮助中心按钮；`help-dialog-escape` 显示 Escape 可关闭且焦点恢复。相关截图为 `/tmp/opencode/fundlex-visual-audit-20261025/24-help-mobile.png`。实现位置为 `frontend/src/components/layout/AppShell.tsx:61-78,107`，当前 effect 只处理 Escape 和初始焦点，没有 Tab/Shift+Tab 循环。
- 处理方法：弹窗打开时收集弹窗内可聚焦元素，在 Tab 到首/尾元素时循环焦点；保留 Escape 关闭和关闭后恢复打开前焦点；必要时将背景内容设置为 inert，避免读屏和键盘同时访问背景。
- 状态与验证：**已发布并完成公网键盘回归**。AppShell 已增加 Tab/Shift+Tab 双向循环、Escape 关闭、关闭后恢复打开前焦点，并在弹窗打开期间将背景 shell 设置为 `inert`；Vitest 组件回归、三视口本地采集和公网针对性证据均通过。该验证不等于完整屏幕阅读器或无障碍合规认证。
- 下一步：继续保留屏幕阅读器语义审查作为独立验收项。
- 变更记录：2026-10-25 新增；由本轮生产键盘交互审查确认。

## FL-D254 合同详情例外列表出现重复事项，削弱人工核对信任（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：合同详情的“例外与人工核对 · 6 项”连续显示六条相同标题“基金费用与税收-3、基金销售服务费（有多个份额类别时适用）”。如果它们确实对应不同位置，界面没有展示位置、证据或编号来区分；如果是同一例外重复投影，则会夸大事项数量。用户难以判断需要核对几件独立问题和每件问题对应的原文位置。
- 证据：生产截图 `/tmp/opencode/fundlex-visual-audit-20261025/18-document-exceptions-desktop.png`、`20-document-downloads-desktop.png`；实现 `frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:84-90` 当前直接拼接 `report.exceptions` 与 `report.user_summary.issues`，未显示稳定 ID、位置，也未对重复项做可解释的归并。
- 处理方法：先确认报告中 `exceptions` 与 `user_summary.issues` 的数据契约，区分独立例外与摘要投影；前端显示规则/位置/证据摘要和稳定编号，只有确认语义完全相同的重复项才归并，并显示“涉及 N 个位置”。概览中的“仍需核对”与例外数量需要提供可解释的统计关系。
- 状态与验证：**展示修复已发布，业务归并仍待决定**。已读取 `/tmp/opencode/fundlex-visual-audit-20261025/document-report.json`，确认 `exceptions` 为空而 `user_summary.issues` 与 `unresolved` 各为 6 条，问题来自报告摘要事项的同类标题投影；不同条目包含不同诊断来源、规则和部分位置证据，不能直接合并。详情页现显示基于条目内容的稳定短 ID、规则、位置、诊断来源和证据，并明确“例外与人工核对”与“仍需核对”的统计口径不同；本轮公网 smoke 已确认生产资产更新，但当前账号未提供可复核的详情样本。
- 下一步：在有真实详情样本时重拍并核对所有条目的 ID、位置、规则、诊断来源和证据；如业务确认某些事项应归并，再以报告数据契约为依据另立变更，不在前端猜测合并。
- 变更记录：2026-10-25 新增；保留“视觉已确认、数据根因未确认”的边界。
- 补充验证（2026-10-25）：已读取并保存当前生产报告 `/tmp/opencode/fundlex-visual-audit-20261025/document-report.json`；`exceptions` 缺省为空，`user_summary.issues` 与 `unresolved` 均为 6 条，排除本样本的双来源拼接原因。六条同属 G15，但有 obligation、orphan evidence、final omission 等不同诊断来源，部分带 p807/p1263/p1262/p806，另外两条无位置；当前前端折叠标题均相同且未展示位置或诊断来源，造成六行看起来重复。**状态更新：前端区分信息缺失已确认、待实现；诊断是否应进一步业务归并仍待分析**。同时概览“仍需核对 26”来自 target 状态，例外“6 项”来自 user summary，应明确区分目标盘点与最终交付核验口径，避免用户误认为数字冲突；不能简单将其中一数覆盖另一数。

## FL-D255 Compare 移动端覆盖警告的长标识缺少断词处理（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：Compare 结果页的覆盖警告直接展示多个 `UNSUPPORTED_VISIBLE_CONTENT:...` 标识。390px 截图中长标识在警告框内连续延伸并接近/超出可读区域，用户难以阅读完整警告，也不容易分辨不同未覆盖内容。
- 证据：生产截图 `/tmp/opencode/fundlex-visual-audit-20261025/35-compare-mobile-right.png`、`40-compare-mobile-reader-controls.png`；补充数据 `/tmp/opencode/fundlex-visual-audit-20261025/followup-data.json` 记录警告容器宽度 330px、内容 scrollWidth 444px、`overflowWrap=normal`。样式 `frontend/src/styles/app.css:182` 的 `.compare-coverage.is-incomplete` 设置了 `line-height`，但没有 `overflow-wrap:anywhere` 或移动端警告分组规则；交互记录确认移动端左右面板切换成功，页面和控制台错误为 0。
- 处理方法：将覆盖项按列表或标签分组显示，长标识使用 `overflow-wrap:anywhere`，必要时显示用户文案并把内部代码放到可展开详情；保证警告在 390px 内完整换行，保留“不可据此确认全文无差异”的主提示。
- 状态与验证：**已发布；本地视觉验证通过，公网已有任务样本待复核**。覆盖警告已改为逐项列表，长内部标识使用 `overflow-wrap:anywhere`/断词规则；本地视觉数据 `/tmp/opencode/fundlex-ui-fix-visual-20261025/visual-data.json` 显示 390px 容器宽 320px、内容 `scrollWidth` 318px，768px 和 1440px 也无额外页面横向溢出，页面/控制台错误为 0。公网 smoke 已确认新资产和页面无横向溢出，但当前账号没有 Compare 任务，未新增任务验证真实覆盖警告。
- 下一步：在有真实 Compare 结果时于公网 390px 重拍，核对警告框逐项换行且不产生页面横向溢出。
- 变更记录：2026-10-25 新增；来源为生产 Compare 结果页截图审查。

## FL-D256 Compare 差异类型视觉颜色在生产结果中未按类型区分（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：Compare 阅读器中修改、新增、删除三类差异都呈亮黄色。用户无法仅凭颜色区分差异类型，必须同时阅读文字或差异清单；在 2,772 处差异的长文阅读中，视觉定位和快速扫描能力明显下降。
- 证据：生产截图 `/tmp/opencode/fundlex-visual-audit-20261025/31-compare-desktop-reader.png`、`41-compare-mobile-reader-original.png`、`42-compare-mobile-reader-comparison.png`；补充数据 `/tmp/opencode/fundlex-visual-audit-20261025/followup-data.json` 中前 8 个 `mark[data-diff-id]` 的 computed background 均为 `rgb(255, 255, 0)`，class 实际只有 `compare-diff`（活动项另有 `is-active`），尽管 `frontend/src/styles/app.css:200-203` 为 `.compare-diff.modify`、`.compare-diff.insert`、`.compare-diff.delete` 定义了不同背景色。源码根因已找到：`frontend/src/pages/Compare/ComparePage.tsx:55` 只识别 `compare-diff-(modify|insert|delete)`，而真实后端 `fundlex/compare/render.py:111` 输出 `class="compare-diff modify/insert/delete"`；fixture 使用了带连字符的类，未覆盖实际后端格式。
- 处理方法：先在当前生产构建中确认差异标记的最终 class、样式加载顺序和 computed style；确保修改/新增/删除具有足够对比且色彩盲用户也能区分的颜色或图标/文字标识，活动项保留独立焦点样式；移动端差异清单继续提供类型文字作为非颜色冗余信息。
- 状态与验证：**已发布；本地真实 renderer 验证通过，公网真实 Compare 样本待复核**。差异 class 解析现同时兼容 `modify/insert/delete`、`diff-modify/diff-insert/diff-delete` 和 `compare-diff-*` 形式；本地真实 renderer 形态与三类最小样例在 1440、768、390px 下分别得到修改 `rgb(255,240,182)`、新增 `rgb(217,241,223)`、删除 `rgb(247,216,216)`，并保留差异清单中的类型文字。候选资产已发布，公网 smoke 无错误，但当前账号没有 Compare 任务，因此未新增模型调用或真实结果页颜色采样。
- 下一步：在已有真实 Compare 结果或获得测试预算后，于公网重查三类 computed style、活动项焦点样式和移动端差异清单；长列表性能建议另按 FL-D256 相关阅读器建议评估。
- 变更记录：2026-10-25 新增；来源为补充生产 DOM 计算样式核验。
- 相关阅读器优化建议：本样本一次渲染 2,772 个差异按钮，桌面差异列表高约 148,616px 且 overflow=visible；大量连接线和非固定工具栏增加长文阅读负担。建议把差异列表放进有限高度/分页或虚拟滚动区，并提供固定导航和当前差异摘要。这是可用性/规模建议，未测得性能故障，不作响应时间不合格结论。

## FL-D260 Compare 阅读器差异导航与文档阅读布局不符合长文复核路径（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：多模态视觉复核确认 Compare 当前把可点击差异清单放在双栏文档之后，长文和 2,772 条差异会形成极长页面；用户无法同时看到文档与差异导航。当前点击差异使用两个 pane 的 `scrollIntoView()`，可能联动滚动外层页面；移动端隐藏一侧的差异目标无法可靠定位，筛选后内联差异与清单状态也可能不一致。视觉层级方面，正文当前为 13px/1.85，接近网页调试列表而非合同阅读；普通块和表格的 DOCX 样式信息不足，难以复刻 Word 页面。
- 证据：独立多模态审查报告及证据路径 `/tmp/opencode/fundlex-visual-audit-20261025/31-compare-desktop-reader.png`、`/tmp/opencode/fundlex-visual-audit-20261025/43-compare-mobile-diff-list.png`、`/tmp/opencode/compare-production-react-v2-e2e-20261025/report.json`；当前实现 `frontend/src/pages/Compare/ComparePage.tsx:118-153,224` 和 `frontend/src/styles/app.css:182-228`。生产结果包含 2,772 处差异，列表和文档阅读区均采用普通页面流。
- 处理方法：第一阶段将 Compare viewer 改为文档区加右侧独立差异 rail，rail 固定高度并独立滚动；以稳定 `data-diff-id` 建立目标定位，使用 pane 内相对坐标修改 `scrollTop`，移动端自动切换到包含目标的一侧，增加滚动同步锁和当前差异跟随。第二阶段再处理差异分组/空白噪声和虚拟滚动。Word 风格呈现需扩展 compare parser/renderer，保留段落、列表、表格、页边距和运行样式；不以 CSS 宣称已还原未输出的数据。
- 状态与验证：**代码已实施，定向验证通过，尚未发布**。右侧独立差异 rail、pane 内相对坐标定位、移动端目标侧自动切换、滚动同步锁、正文 15px 阅读基线和 DOCX 段落/run/编号/页边距/基础合并表格投影已完成；`PYTHONPATH=. .venv/bin/pytest -q tests/test_compare*.py` 为 73 passed、5 skipped，另有 1 个既有 Starlette/httpx deprecation warning；前端 typecheck、lint、9 项 Vitest、build、浏览器 8 项回归和 diff check 通过。浏览器夹具额外确认目标进入 pane 可视区且外层 `window.scrollY` 不变。新代码尚未生产发布，未新增模型调用；当前生产 Compare `incomplete` 状态和 header/footer/drawing 等覆盖缺口保持不变。
- 下一步：发布前仍需保留真实 renderer 的视觉截图并决定是否受控发布。后端完整 Word 还原仍需继续补齐复杂列宽/边框、header/footer、drawing/pict/AlternateContent 和真实分页等覆盖判断。
- 变更记录：2026-10-26 新增；来源为用户反馈和独立多模态视觉审查。该条与 FL-D256 的差异颜色问题关联，但范围扩展到长文导航、定位、布局和 Word-like 呈现，不合并为颜色问题。

## FL-D261 Compare 回归命令未显式设置仓库导入路径（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：直接运行 `.venv/bin/pytest -q tests/test_compare*.py` 时，`tests/test_compare_corpus.py` 在收集阶段因 `from tools.evaluation...` 找不到仓库根目录下的 `tools` 命名空间而失败；这会造成全量 Compare 回归被误判为代码失败。项目已有测试脚本依赖从仓库根目录导入 `tools`，当前环境的 pytest 启动方式没有自动把根目录加入 `sys.path`。
- 证据：直接命令报 `ModuleNotFoundError: No module named 'tools'`；同一工作区使用 `PYTHONPATH=. .venv/bin/pytest -q tests/test_compare_corpus.py` 为 8 passed，Compare 定向集合在显式 `PYTHONPATH=.` 下通过。未发现业务代码或生产服务错误。
- 处理方法：本轮验证采用 `PYTHONPATH=. .venv/bin/pytest ...`，保留测试代码和历史命名空间不变；后续可在统一测试入口或项目配置中声明仓库根目录导入路径，避免开发者漏设环境变量。
- 状态与验证：**已确认，当前通过显式环境变量规避**。该项属于测试运行环境细节，不影响 Compare 生产 API、Worker 或前端运行；尚未修改项目测试入口配置。
- 下一步：若将 Compare 全量回归纳入标准 CI/交接命令，应把 `PYTHONPATH=.` 固化到测试入口并保留本条记录，避免只记录一次性命令。
- 变更记录：2026-10-26 新增；来源为本轮全量 Compare 测试收集检查。

## FL-D250 React Compare 生产 Worker/DOCX 结果页与下载验收（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：React Compare 的隔离 API 夹具和本地 Worker 测试不能证明生产登录、真实 DOCX 上传、持久 Compare Worker、结果阅读、移动端切换及授权报告下载已经闭环。
- 证据：生产浏览器证据 `/tmp/opencode/compare-production-react-v2-e2e-20261025/report.json` 与下载文件 `/tmp/opencode/compare-production-react-v2-e2e-20261025/React Compare生产验收-20261025-差异报告.json`。真实公开合同为 `广发消费品精选混合型证券投资基金基金合同_20230708.docx` 与 `广发品质回报混合型证券投资基金基金合同_20230708.docx`；生产结果 2,772 处差异（modify 451、insert 1,238、delete 1,083），报告下载 3,189,696 bytes，SHA-256 `0f39d4d3655d773722dccaade57d9518fd2ed8f609d6ebf632f7433e85643bbc`。浏览器验证了差异导航、390px 左右面板切换和页面/控制台错误为 0。
- 处理方法：沿 HTTPS 普通登录入口注册测试账号，进入 React `/compare`，上传左右公开 DOCX、封存，等待生产 Compare Worker，读取结果并下载报告；对覆盖不完整状态保留明确人工复核提示及 header/footer/drawing 等警告。
- 状态与验证：**已验证（Compare 生产链路）；结果状态为 `incomplete`**。后端结果和前端下载内容均可读取，覆盖警告正确显示；`incomplete` 是当前结果的业务状态，不得解释为全文无差异或完整覆盖。
- 下一步：继续保留普通合同 D01–D20 gate 阻断；如需 Compare 全文可交付，需先补齐或明确处理未支持结构，再另行验收。
- 变更记录：2026-10-25 新增；当前 React V2 生产 Compare 证据已补齐。

## FL-D251 普通合同 Review 选择版生成存在异步可观测窗口（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：普通真实任务在 Review 页面批量接受 19 条修订并点击“生成选择版合同”后，界面可能先显示“正在生成选择版合同…”。验收脚本必须等待成功响应并轮询下载清单；在成功响应或明确错误出现前，不能证明 `selected_final` 已发布，也不能把生成请求受理当作选择版交付完成。
- 证据：首次真实任务 `8e3767e727344ecbbebc76ee95ad2b20`、文档 `2acd8583cea340fca1da964914ab39aa` 的证据 `/tmp/opencode/fundlex-production-v2-e2e-20261025/e2e-pp7khckdz8q2/result.json` 显示 `selected_artifact_generation_attempted=true`、`selected_generation_status=正在生成选择版合同…`，随后 `artifact_count=4` 且 downloads 未出现 selected artifact。补测真实任务 `add3f5e6d5f049eeb305c1e4a1ce81d9`、文档 `186228a5c3d645f188083f87f2095e26` 已完成登录、当前指引、真实 Worker/model、Review 读取（19 条修订），但 `/tmp/opencode/fundlex-production-v2-e2e-selected-20261025/e2e-3lopn3fjl7yl/result.json` 只记录到 Review；点击生成后 60 秒内未观察到“已生成选择版合同”，脚本 fail-closed 退出，未下载 selected artifact。两次任务的 delivery 均不能据此变为 complete，普通合同仍有 G15 claim/coverage 未决。
- 处理方法：保持服务端选择版生成的 fail-closed 行为；补充验收步骤，在生成响应后轮询文档/下载清单直到 `selected_final` 出现或明确返回错误，再核对 selected DOCX ZIP、实际修订、报告/来源哈希及授权下载。不能用按钮点击成功或短暂 status 文案代替产物存在。
- 状态与验证：**待验证，补测未闭合**。普通合同真实登录、上传、持久 Worker/model、Review 展示已通过；首次任务的 working 产物和报告哈希已通过。补测在成功状态观察阶段超时，未形成 selected DOCX、selected hash 或 selected 下载授权的证据，因此不能宣称选择版生成成功或失败。
- 下一步：保留两次真实任务及其失败时序证据；后续应捕获生成 mutation 的 HTTP 状态/错误正文，并在成功响应后轮询 `selected_final`，再核对 selected DOCX ZIP、实际修订、报告/来源哈希及授权下载。保持当前 G15 不完整状态，不扩大为 D01–D20 gate 通过。
- 变更记录：2026-10-25 新增；首次验证的立即读取竞态已确认，第二次补测改为等待成功文案但在 60 秒内超时，仍未取得 selected artifact 证据。

## FL-D263 operation Registry 门禁边界与 FALSE applicability edit 授权缺口（2026-10-25）

- 发现日期：2026-10-25。
- 问题与影响：本轮架构审计发现三类可跨规则复现的 fail-open 风险：Guide 的 operation registry 覆盖检查若只停留在低层 planner，parsed custom Guide 可在 enable 或 Worker 绑定时绕过；Claim Replay 若只投影 TRUE obligation，会让绑定到 FALSE/UNKNOWN operation 的 edit 在 artifact proof 中消失；审计 missed target 只保留 rule/location 会丢失 operation、obligation 和 target 归属。另发现 sibling 写入相同新文本时，普通 operation 可能被误判为 `ALREADY_SATISFIED`，但显式 `ONE_OF` 历史替代必须保留该语义。
- 证据：初次实现直接在 `validate_runtime_guide()` 加 operation registry 检查，破坏了自定义 Guide 的“先解析、后受控启用”契约；定向回归出现 `test_one_of_alternative_branch_can_close_when_sibling_was_applied` 和自定义 Guide certification 失败。完整回归第一轮为 1478 passed/48 skipped/3 failed，第二轮为 1479 passed/48 skipped/2 failed；失败均用于收紧兼容边界，未修改 gold、scorer、验证标准或固定分母。
- 处理方法：将 Registry coverage 门移到 `guide_store.set_current_guide()` 和 Worker `_bound_guide_document()`；显式 `operation_id` 的 custom/extension Guide 缺失 registry entry 时拒绝 enable/bind，未知 rule 即使没有显式 identity 也拒绝，已知内置 rule 的旧式无 identity fixture 保留兼容。Claim Replay 在 operation authorization 前拒绝 FALSE/UNKNOWN applicability edit；effects 仅在 operation 自身有 source policy 或通过自身 validated unit 时产生 `ALREADY_SATISFIED`，保留显式 `ONE_OF` alternative 的历史关闭语义；audit missed target 保留 operation/obligation/target 身份；Delivery Gate 在传入 Ledger 时检查 Ledger open obligations。
- 状态与验证：**修复不完整，当前仍可复现 sibling policy 错误关闭**。原有 FALSE applicability、custom operation enable、ONE_OF 兼容回归仍通过；但 2026-10-26 使用内置 G18 `INDEPENDENT` operation 和无关 synthetic `G100:0` sibling 的最小夹具重放时，`replay_claims()` 返回 `verified=true`，G18 被记为 `ALREADY_SATISFIED`、`edit_ids=[]`，Ledger `open_obligations=[]`，`_delivery_complete()` 最终返回 complete。根因是 `fundlex/generation/effects.py:584-623,688-689` 在当前 operation 没有自身 edit/source proof 时仍无条件使用 `_policy_phrase_equivalent()`，被 sibling 写入的最终文本关闭 G18。针对性回归为 4 passed，不能覆盖该 synthetic sibling 场景；未调用真实模型、未修改源码或真实生产产物。
- 下一步：收紧 `ALREADY_SATISFIED` 的证明来源，使独立 operation 只能由自身 source policy 或自身 validated unit 关闭；仅保留明确 `ONE_OF` 授权的 sibling 替代语义。为 independent sibling、ONE_OF sibling 和自身 satisfied 三类补 deterministic replay/ledger/delivery 回归，再按最终 clean candidate 运行 Frozen Replay、真实 Worker/model、D01-D20 固定分母和最终用户 E2E。G06 未授权语义、预算缺口及 selected artifact 观察窗口继续按 FL-D240–FL-D243、FL-D251 阻断。
- 变更记录：2026-10-25 新增并记录首轮兼容性边界；2026-10-26 修正状态：修订引擎离线最小夹具重新证明普通独立 sibling 仍可误关 obligation，原“已实施并验证”结论降级为“修复不完整”。

## FL-D257 G05 缺失替换分支被同站点删除分支错误覆盖（2026-10-25）

- 问题与影响：G05 在有销售服务费时要求将“调低赎回费率”替换为“调低销售服务费率”（G05:0），同时独立删除“并报中国证监会备案”（G05:2）。当真实份额类别设置段落只包含前者的业务上下文、两项旧文字均不存在时，旧的 absent coverage 按段落把所有缺失旧文都视为已处理，导致 G05:0 被错误关闭；G05:0 没有源文本或新政策证明时不得执行替换，也不能借用 G05:2 的 absent 证明。
- 证据：D19 原件 `/home/opencode/data/funds_word/广发聚源债券型证券投资基金（LOF）基金合同_20240920.docx` 的 p130 含份额类别设置和费率调整上下文，但不含“调低赎回费率”“调低销售服务费率”或“并报中国证监会备案”。历史真实报告和失败证据保留于 `/tmp/opencode/operation-validation-20261024/dev-21-full/D19/`；旧 `G05:0` target 为 `absent`，此前缺少可证明的替换站点。
- 处理方法：`targets_for_open_rules()` 的 absent coverage 改为只读取 target 自身明确的 operation；replace 只有在同一 operation 的新文本已存在且旧文本不存在时才可关闭。G05 的删除 operation 不再使用文档级缺失直接关闭，`resolve_absent_site_targets()` 仅在同一份额类别设置业务站点形成 operation-specific 的 G05:2 absent clone，并保留 G05:0 原 target 的 OPEN/UNPROVEN 状态。
- 状态与验证：**代码已实施并验证，尚未进行新真实 Worker/model 复测**。新增实际 DOCX 形态回归验证 G05:0 仍保持未证明、G05:2 生成独立 satisfied site；混合 operation target 拆分回归也通过，定向回归 141 passed，完整 `pytest tests` 为 **1476 passed / 48 skipped / 2 warnings**。snapshot-20 及历史 D19 报告不变。
- 下一步：在预算和发布条件满足后，以含本修复的新冻结版本重新执行受影响 D19，逐 operation 核对 G05:0/G05:2 的 source site、Claim Replay、报告和实际 DOCX；G05:0 无授权源文本时保持未完成。

## FL-D258 G16 支付段重复副本按字面复制导致不同 clause site 借权（2026-10-25）

- 问题与影响：D20 p804 与 p1259 的支付段文字相同，但 p804 后接 p805/p806 的销售服务费用途条款，G16 的 append site 应落在 body clause end p806；p1259 是没有该 continuation 的独立 summary site。若先按支付段字面做 duplicate-copy，再做 clause-end 重绑定，会把 p804/p1259 机械视为同一 operation site，产生错误 clone、错误 append 位置或错误 site coverage。
- 证据：D20 原件 `/home/opencode/data/funds_word/广发远见智选混合型证券投资基金基金合同_20230708.docx` 的 p804、p805、p806、p1259；p804 与 p1259 支付文本完全相同，实际 clause locations 为 `(p804,p805,p806)` 与 `(p1259,)`。历史 D20 真实报告、DOCX 和当前零 HTTP replay 保留于 `/tmp/opencode/operation-validation-20261024/dev-21-full/D20/` 及其对应 replay 文件。
- 处理方法：在 pipeline 的每次 duplicate-copy closure 前先执行 `rebind_g16_clause_targets()`；`duplicate_copy_targets()` 对 G16 增加 clause-end identity guard，仅当源和候选都是各自物理 clause 的末端才允许复制。无法建立真实 DOCX 结构索引的轻量测试替身退回原 exact-copy 行为，避免改变既有调用契约。
- 状态与验证：**代码已实施并验证，尚未进行新真实 Worker/model 复测**。实际 DOCX 回归确认 p804/p806 和 p1259 保持不同 operation site，不能互相机械克隆；定向回归 141 passed，完整 `pytest tests` 为 **1476 passed / 48 skipped / 2 warnings**。历史 D20 失败报告与产物没有被改写。
- 下一步：预算和发布条件满足后，以新冻结版本重新执行 D20，逐站点核对 G15/G16/G17 operation attribution、G16 append 位置、Claim Replay、修订版和接受/拒绝等价；不能以相同支付段字面证明不同 clause site 等价。

## FL-D259 G21 noop target 生命周期进入审计和 unresolved 投影（2026-10-25）

- 问题与影响：G21 只在“非浮动管理费且仅一个份额类别”时要求不替换。对多类别固定管理费产品，G21 target 属于 no-op 资格证明；如果 satisfied target 继续作为普通 auditable target，G22 可以合法修改同一清算段落时，审计会把 G21 的 unchanged 状态误判为冲突，且 target 可能继续污染 Claim Replay/unresolved projection。
- 证据：D20 相关清算段落同时存在 G21 noop 与 G22 同段替换边界；历史 D20 report 中 G21/G22 同段状态和旧 audit 误判保留在 `/tmp/opencode/operation-validation-20261024/dev-21-full/D20/`。此前仅归属阶段标记 no-op，后续审计仍可能重新接纳 satisfied target。
- 处理方法：`assign_target_operations()` 对适用 noop 的 satisfied target 标记 `out_of_scope` 并保留 `TARGET_OPERATION_NOT_APPLICABLE` 原因；`targets_for_open_rules()` 保留其 operation coverage，但不把该 target 作为可编辑或可审计站点。G22 同段 target 继续独立规划、审计、Claim Replay 和 unresolved 投影。
- 状态与验证：**代码已实施并验证，尚未进行新真实 Worker/model 复测**。新增同段 G21/G22 回归确认 G21 退出审计且 G22 不被隐藏；定向回归 141 passed，完整 `pytest tests` 为 **1476 passed / 48 skipped / 2 warnings**。未改写历史 report、labels、gold 或评测分母。
- 下一步：新冻结版本真实复测 D20 时，独立核对 G21 no-op ledger proof、G22 实际修改、audit、Claim Replay 和最终 unresolved projection；G21 不适用时不能成为可编辑 obligation。

## FL-D265 飞书 Draft 建表占位符数量错误导致附件事件进入 dead（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：`feishu_drafts` 插入语句列和值均为 15 项，但 `VALUES` 曾写成 16 个占位符。任何首次接收 DOCX 的事件都会在创建 Draft 时抛出 SQLite `OperationalError`，消息处理器随后将事件标记为 `dead`，用户看不到可继续添加附件的草稿卡片。
- 证据：新增 `tests/test_feishu_integration.py` 初次运行为 `4 failed`，日志记录 `OperationalError: 16 values for 15 columns`；修正后同一专项集合扩展并稳定为 `8 passed`。
- 处理方法：将 `feishu_drafts` INSERT 的占位符改为 15 个；新增真实 SQLite 持久层和 fake client 覆盖 Draft 创建、附件接收、提交和卡片路径。
- 状态与验证：**已解决（当前工作区已实施并验证）**。专项测试 `7 passed`；compileall 和 `git diff --check` 通过。尚未部署或进行真实飞书网络验收。
- 下一步：发布前重新执行全量回归，并在真实飞书用户路径核对首个附件事件、多个附件和卡片确认。
- 变更记录：2026-10-26 新增；保留初次失败证据和修复后专项验证结果。

## FL-D266 飞书卡片确认反馈曾与实际提交结果不一致（2026-10-26）

- 问题与影响：卡片 action 原先忽略 `submit_draft()` 的结果，任务中途失败时仍报告成功，无法指导重试。
- 证据与处理方法：`submit_draft()` 现返回 `submitted`、`busy`、`failed` 或 `missing`；卡片 action 按结果提示，并写入 `integration_events` 按 provider、event ID 和 payload hash 去重，payload 冲突 fail closed；卡片发送失败但正式任务已落库时仍返回已创建提示，durable outbox 负责补发状态卡片。
- 状态与验证：**已解决（当前工作区已实施并验证）**。上传失败、卡片失败、重复事件和 outbox 恢复专项断言通过；未进行真实 `message.patch` 网络验收。
- 下一步：真实飞书回调中核对确认、重复点击、过期按钮和消息 patch 返回行为。
- 变更记录：2026-10-26 新增。

## FL-D267 飞书任务提交中断后 Draft 不应失去重试能力（2026-10-26）

- 问题与影响：任务创建使用 Draft 幂等键，但上传、封存或发卡中断后原流程把 Draft 标为 `FAILED`，用户无法重试，可能留下未完成正式 Task。
- 证据与处理方法：异常分支现恢复为 `COLLECTING` 并记录 `last_error_code`，保留 staging 文件和原 submit idempotency key；重试复用正式 Task，成功后清除错误码。
- 状态与验证：**已解决（当前工作区已实施并验证）**。失败恢复、Task 幂等和最终 Draft 状态专项通过；真实 Worker/model 和飞书网络仍未验收。
- 下一步：生产验收覆盖中断后的恢复，并核对最终任务只创建一次。
- 变更记录：2026-10-26 新增。

## FL-D268 飞书绑定解绑后的历史身份行阻塞重新绑定，MySQL outbox 领取缺少数据库行锁（2026-10-26）

- 问题与影响：身份表保留 revoked 历史行；重新绑定可能被唯一键阻止。MySQL 下 outbox 领取原查询没有 `FOR UPDATE`，多个服务进程可能同时读取同一 pending 行。
- 证据与处理方法：消费绑定码现复用/更新 revoked 行，active 行仍对跨账号抢绑 fail closed；MySQL outbox 查询追加 `FOR UPDATE`，并检查领取 UPDATE 的 `rowcount`；发送完成仍携带 fencing token。SQLite 专项同时覆盖 stale fencing 和状态卡片发送失败恢复。
- 状态与验证：**代码已实施；SQLite 已验证，MySQL 待验证**。专项测试 `8 passed`；本轮无 `FUNDLEX_MYSQL_TEST_URL` 连接证据，也未部署飞书服务。

## FL-D269 完整 pytest 首次运行出现一次不可复现的 G15 顺序失败（2026-10-26）

- 问题与影响：本轮首次完整 `pytest` 在 G15 合法“支付头段与顺延句跨段”归属用例出现 1 次失败，可能造成把当前 dirty 工作区误判为回归；该用例单独运行和 G15 文件整体运行均通过。
- 证据：首次完整运行结果为 `1492 passed / 48 skipped / 1 failed`，失败为 `tests/test_g15_payment_delay_boundary.py::test_split_payment_head_is_attributed_before_delay_target_is_added`；随后单用例通过，G15 文件 `29 passed`，再次完整运行通过 `1493 passed / 48 skipped / 2 warnings`，最终源码复跑仍为 `1493 passed / 48 skipped / 2 warnings`。未发现共享环境变量未恢复或稳定复现路径。
- 处理方法：保留现有 G15 dirty 修改和测试，不以首次单次失败作为通过证据；串行重跑定向文件和完整套件确认结果。两次完整运行均使用 `PYTHONPATH=.`，未并行安装依赖。
- 状态与验证：**待观察，当前未复现**。最终完整套件结果为 `1493 passed / 48 skipped / 2 warnings / 307.62s`；warning 为既有 Starlette/httpx 弃用提示和重复 DOCX ZIP 测试构造。该条不改变引擎最终 candidate、D01–D20 gate 或生产发布结论。
- 下一步：若后续再次出现，按 pytest 收集顺序、随机种子、环境变量快照和最小失败集合继续定位；发布前至少保留当前完整回归证据。
- 变更记录：2026-10-26 新增；记录首次失败、定向复测和完整重跑通过，不修改历史报告或 gold。

## FL-D270 G15 跨段支付头在真实生产归因阶段被错误拒绝（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：真实 V1 生产任务的上传、封存、Worker 启动及模型调用均成功，但 G15 目标的支付头位于 `p806`、支付主体和顺延句位于 `p807`。盘点目标只覆盖 `p806` 时，归因门禁只看当前段与指引 `old_text` 的相似度，因而报 `RECALL_TARGET_OPERATION_UNATTRIBUTED` / `operation_span_mismatch`，任务以 `PROCESSING_FAILED` 结束且没有交付产物。
- 证据：任务 `91ab2940c62844f7a5cd75ca021c7c54`、文档 `2e8a8c9a2fd64c058d2bc6c4f2cd1401` 的脱敏报告 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-yarwc0ihqd68/report.json`；报告记录 3 次真实模型调用、`target_attribution` 为 G15 `T018`、`G15:0`、`operation_span_mismatch`，原件结构为 `p806` 支付头和 `p807` continuation/delay。生产失败任务和产物未被改写。
- 处理方法：`fundlex/recall.py` 增加 G15 限定归因路径：当前目标必须完整占据支付头段，下一物理段必须通过既有支付结构和顺延句解析；只允许 G15 完整支付删除 operation 使用该路径，不放宽其他规则或任意邻段借权。补充生产 p806/p807 形态回归及 Claim Replay 边界。
- 状态与验证：**代码已实施，工作区验证通过，生产发布与复跑待验证**。G15 定向集合为 `96 passed`；完整回归为 `1493 passed / 48 skipped / 2 warnings`；`py_compile` 和 `git diff --check` 通过。此前失败任务仍保持失败状态，不能作为修复后交付证据。
- 下一步：新备份后发布到生产 API/Worker；重新执行真实 V1 普通合同任务，核对报告、修订 DOCX、Review、selected artifact、哈希和授权下载；若仍有未完成目标，按报告保留 `incomplete`/`NO-GO`。
- 变更记录：2026-10-26 新增；修复限定为 G15 跨物理段支付头归因，未修改历史失败报告、gold 或固定分母门禁。

## FL-D271 V1 生产验收脚本把隐藏原生 select option 当作可见元素等待（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：任务已进入终态并写入真实生产数据库后，验收脚本在 `#task-select` 的原生 `<option>` 上使用默认可见性等待。原生 option 在浏览器中通常不可见，导致脚本在结果页前超时，未继续执行报告、Review、selected artifact 和 Compare 验收。
- 证据：最新脚本 `/home/opencode/fundlex/tools/evaluation/production_v1_e2e_20261026.py` 第 198 行原先对 `#task-select option[value=...]` 调用默认 `wait_for()`；失败结果 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-yarwc0ihqd68/result.json` 记录任务已完成但结果页自动化未完成。该问题不改变服务端任务状态。
- 处理方法：等待该 option `state="attached"`，确认选项已由 V1 页面填充后再调用 `select_option`；继续保留服务端轮询和产物门禁。
- 状态与验证：**代码已实施，待下一次真实生产复跑验证**。脚本静态编译和完整项目回归待随本轮最终编辑复核；在新的普通合同链路成功完成前，不把脚本修复视为生产验收完成。
- 下一步：发布 G15 修复后重新运行脚本；保留失败证据，完成后清理该次临时账号及所有精确关联数据和对象。
- 变更记录：2026-10-26 新增；与 FL-D270 分开记录，分别表示引擎归因缺陷和浏览器验收等待缺陷。

## FL-D272 V1 生产验收脚本使用 networkidle 与持续轮询页面不相容（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：G15 修复发布后的新验收脚本在首页加载阶段等待 Playwright `networkidle`，V1 页面启动后存在持续请求/轮询，导致浏览器在 60 秒内没有进入后续注册和任务步骤。此次没有创建用户、任务、模型调用或对象。
- 证据：运行结果 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-8j8alpwpr2j8/result.json`，错误为 `Page.goto: Timeout 60000ms exceeded`；同一时间直接请求 `https://fundlex.club/` 返回 HTTP 200，响应耗时约 0.03 秒，标题为 `FundLex合同修订工作台`。清理命令确认该临时用户名不存在。
- 处理方法：验收脚本导航统一改为 `wait_until="domcontentloaded"`，之后继续用具体控件、认证状态、API 轮询和结果元素作为业务就绪条件，不依赖网络空闲。
- 状态与验证：**代码已实施，待真实复跑验证**。本次失败不构成生产服务或引擎失败，也不能作为普通合同验收通过证据。
- 下一步：重新执行脚本；若成功完成真实普通合同和 Compare，再按报告和下载证据更新 FL-D270/FL-D271 状态；若业务路径仍失败，保留最新失败证据并继续 NO-GO。
- 变更记录：2026-10-26 新增；临时账号在注册前未产生数据库残留。

## FL-D273 `targets_for_open_rules` 局部导入遮蔽 `condition_status` 导致真实 Worker survey 阶段 NameError（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：`fundlex/targeting.py` 的 `targets_for_open_rules()` 在遍历 `satisfied` target 时先读取 `condition_status`；同一函数后面的 `if auto` 分支又局部导入同名符号，Python 因此把它判定为整个函数的局部变量。真实普通合同在事实、scope、inventory 三次模型调用后进入 `survey`，调用 `targets_for_open_rules` 时抛 `NameError`，任务以 `PROCESSING_FAILED` 结束，未生成 DOCX 交付物。
- 证据：任务 `c9e267272f7249e4a13d615cf0742dcd`、文档 `fdd5d355fdf1422dad0b2f60f4fdde22` 的报告 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-0hq1fi2tugpm/report.json` 记录 `stage: "survey"`、`message: "NameError"`；本机以同一公开 DOCX 和生产配置复现，异常为 `cannot access free variable 'condition_status' where it is not associated with a value in enclosing scope`，定位 `/home/opencode/fundlex/fundlex/targeting.py:648`。
- 处理方法：将 `condition_status` 与其他 recall helper 一起提升到 `targets_for_open_rules` 函数入口导入，删除后部同名局部导入，避免作用域遮蔽；增加 satisfied target 在 auto 分支前执行的回归，确保该状态读取可用。
- 状态与验证：**代码已实施，本地验证通过，生产发布待验证**。`tests/test_open_obligation_recovery.py`、G15 定向集合及跨段测试合计 `52 passed`；`py_compile` 和 `git diff --check` 通过。生产失败任务已清理 1 个用户、1 个会话、1 个任务、1 个批次、1 个文档及 3 个对象；本条修复尚未作为生产交付证据。
- 下一步：备份并发布 `fundlex/targeting.py`，核对 API/Worker active 后重新运行真实 V1 普通合同；继续核对 G15 attribution、完整报告、working/final/redline、Review、selected artifacts、哈希及授权下载，再执行独立 Compare。
- 变更记录：2026-10-26 新增；本条由 FL-D270 的生产复跑失败中发现，G15 修复本身尚未因该 NameError 被真实验证。

## FL-D274 V1 验收脚本在普通任务失败后继续点击 Compare，遮蔽主失败证据（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：普通合同 Worker 已写入 `PROCESSING_FAILED` 或 `delivery_status=not_generated` 后，脚本仍继续执行详情页后续动作；详情弹窗保持打开时，点击后台 Compare 按钮又产生 pointer interception 错误，使一次真实业务失败被后续 UI 错误混淆，也可能让人误以为 Compare 已开始验收。
- 证据：运行 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-0hq1fi2tugpm/result.json` 既记录普通文档报告的 `PROCESSING_FAILED`/`stage=survey`，又记录随后 `#compare-new` 被 `#detail-overlay` 遮挡的自动化异常；该次 Compare 没有创建任务。前端 `frontend/app.js` 的详情弹窗在打开期间将工作台设置为 inert。
- 处理方法：普通报告保存后，若任务失败、报告含错误码或交付状态为 `not_generated`/`incomplete`，验收脚本立即以明确的 ordinary failure 结束，不进入 Review/Compare；完整交付路径则在导航 Compare 前点击 `#close-detail` 并等待弹窗隐藏。
- 状态与验证：**代码已实施，待下一次真实运行验证**。脚本 `py_compile`、`git diff --check` 和 `node --check` 通过；此前真实失败账号及其关联数据已清理。本条不能替代普通合同或 Compare 成功验收。
- 下一步：以 FL-D273 修复后的新普通任务验证失败短路或完整交付分支；成功交付后独立核对 Compare 任务、阅读器、覆盖警告、报告下载和三视口证据。
- 变更记录：2026-10-26 新增；从 FL-D273 生产复跑中发现，和引擎 NameError 分开记录。

## FL-D275 G15 composite 首段 Claim Replay 未重算跨段支付授权、Review 父级 manifest 缺少原文（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：FL-D270 的归因修复生成了 `p806`/`p807` 和 `p1262`/`p1263` 两段 composite 删除，但 Claim Replay 对每个物理段按单段删除校验；支付头段本身不包含完整 payment clause，因而报 `CLAIM_OPERATION_SPAN_UNAUTHORIZED`，并继续产生 `CLAIM_PLANNED_EFFECT_MISSING`、`FINAL_OPERATION_UNPROVEN` 和 `FINAL_COVERAGE_UNRESOLVED`。同一批旧报告的 `atomic_paragraph` 父 edit 未保存 `expected_old_text`，Review 重建 redline manifest 时将 `p142` 原文误认为短 fragment，POST `/decisions` 返回 `REVISION_TEXT_MISMATCH`。
- 证据：原始真实报告 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-jeo9hsg813hd/report.json`；生产 G15 edit 为 `p806 (0,35)`、`p807 (0,89)`、`p1262 (0,35)`、`p1263 (0,91)`。修复前直接重放产生两个首段授权失败；修复后同报告以原始 DOCX 和 `working_final.docx` 重放为 `verified=true`、19 edits、0 failures。原 Review 失败通过正式 selected artifact 生成器复现为 `DocxError: REVISION_TEXT_MISMATCH`；补入已验证 source slice 后生成 `/tmp/opencode/selected-repro-after-d275.docx` 成功。
- 处理方法：`fundlex/recall.py` 仅在顺延句后没有可见文本时把尾随格式空白纳入 source-bound boundary；`fundlex/generation/claim_replay.py` 对 G15 composite 首段重新读取相邻 paragraph、验证完整 payment head、连续物理位置及 `_g15_delay_continuation()` 计算出的尾段边界，继续对尾段执行精确边界校验；`fundlex/recall_pipeline.py` 将 `validate_edit_plan()` 生成的父级 `expected_old_text`/`expected_old_hash` 写入 report plan，供 Review manifest 重建使用。新增 G15 composite Replay、尾随空白和 selected manifest 回归。
- 状态与验证：**代码已实施，工作区定向验证通过，生产发布与新真实 V1 复跑待验证**。G15/Claim Replay/selective 定向集合 `96 passed`，相关最终验证集合 `194 passed`；真实旧报告 Claim Replay 已通过，selected artifact 生成已通过；`py_compile`、`node --check` 和 `git diff --check` 通过。既有生产报告、账号和对象未被改写。
- 下一步：新备份后发布 `recall.py`、`recall_pipeline.py`、`generation/claim_replay.py` 及其依赖；核对部署 hash 和服务状态；运行新真实 V1 普通合同全交付与 Review selected artifact，再独立运行 Compare。所有 D01–D20、G06、普通合同完成和最终 GO 门禁继续按现状保持 NO-GO。
- 变更记录：2026-10-26 新增；保留修复前失败证据与修复后离线重放证据，不修改历史 report、gold 或固定分母。
- 下一步：使用一次性 MySQL 8 测试库运行 Feishu store/schema、并发绑定和 outbox 领取测试；真实验收前核对服务单元、共享数据目录和凭据变量存在性。
- 变更记录：2026-10-26 新增；明确区分 SQLite 与 MySQL/网络未验证边界。

## FL-D276 V1 真实普通交付通过、Compare 覆盖仍 incomplete（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：D275 发布后的真实 V1 普通公开合同路径已完整交付，但独立 Compare 路径虽然任务、阅读器和 view API 成功，结果 coverage 仍为 `incomplete`；未支持结构不能作为全文完整比较交付。
- 证据：普通任务 `6200b8ad71974c10b613622809fa52f5`、文档 `2adeaefc840b4df68e8be0d060cea16f`，证据目录 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-o9rfdisxoj2o/`。任务 `completed/succeeded/complete`，31/31 targets completed、unresolved=0、`artifact_claim_replay.verified=true`、19 edits；Review HTTP 200，19 条修订拒绝 1 条，`selected_final` 和 `selected_redline` 均成功下载。Compare 任务 `191b14f48e264212abe98de5828bcd29` 完成并可查看，1113 处差异（modify 313、insert 442、delete 358），但警告为 `UNSUPPORTED_VISIBLE_CONTENT:header`、`footer`、`AlternateContent`、`drawing`、`pict`，证据为 `compare-view.json` 和 `result.json`。
- 处理方法：普通交付证据按报告、Claim Replay、DOCX、哈希、Review 和授权下载逐项核验；Compare coverage 缺口保留为明确 `incomplete`，不提升为 complete，不修改结果或掩盖警告。
- 状态与验证：**普通 V1/D275 已验证；Compare 全文交付未通过，整体生产结论保持 NO-GO**。全量回归为 `1497 passed / 48 skipped / 2 warnings`；发布后 API/Worker active，部署关键文件哈希与工作区一致。
- 清理：临时账号 `e2e-v1-o9rfdisxoj2o` 已删除；清理脚本记录 1 user、1 session、1 task、1 batch、1 document、1 compare task、1 compare pair，删除关联对象 10 个；数据库复核用户名行数为 0。
- 下一步：补齐或明确处理 Compare 的 header/footer、AlternateContent、drawing、pict 等可见内容覆盖，再独立复验；D01–D20 固定分母、G06 授权及其他项目级门禁仍需完成。
- 变更记录：2026-10-26 新增；保留普通成功与 Compare incomplete 的同次真实用户路径证据。

## FL-D283 发布器文档仍宣称受限 sudo，但实际授权为全 root（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：用户已在 FL-D084 明确授予 `opencode` 本机 `NOPASSWD: ALL`，因此本条不把该授权定性为未经授权；但实际 `/etc/sudoers.d/fundlex-opencode-publish` 第 5 行的全 root 规则与第 1-3 行及发布器注释所描述的“仅受限发布”边界相反。工作区用户因此能够读取或修改生产环境密钥、数据库、对象文件、systemd/Nginx 配置及其他系统资源。若团队以发布器注释、历史文档或第 4 行为依据进行威胁建模，会低估主机接管和凭据暴露范围。严重级别：**严重（Critical）**。
- 证据：`/etc/sudoers.d/fundlex-opencode-publish:1-5` 的只读内容；第 4 行为受限发布规则，第 5 行为 `opencode ALL=(root) NOPASSWD: ALL`。`/home/opencode/fundlex/docs/DETAIL_ISSUES_AND_RESOLUTIONS.md:1072-1082` 的 FL-D084 已记录该用户授权背景；同次核验 `sudo -n true` 成功，未打印任何凭据值，也未利用该权限修改系统。
- 处理方法：由产品/运维明确选择并记录真实权限模型：若不需要全 root，应在备份后删除第 5 行，仅保留固定绝对路径发布命令，并用 `visudo -cf`、`sudo -n -l` 和发布器正向回归验证；若确需保留用户授权的全 root，则必须同步修正发布器注释、AGENTS/交接文档和安全边界说明，并把该能力作为主机级高风险控制单独审计，不能继续称为“受限 sudo”。
- 状态与验证：**待治理，未验证**。本轮只读取 sudoers 并确认授权范围，没有修改规则；FL-D084 的授权事实为已知历史事项，本条新增的是实际规则与“受限发布”安全声明不一致的治理风险。
- 下一步：由授权人确认最小权限目标；无论选择收紧还是保留，都要完成语法检查、授权枚举、发布器验证和凭据/对象/服务访问边界复核。
- 变更记录：2026-10-26 新增；与 FL-D084 合并关联，不把用户已授权的全 root 规则重复登记为未经授权漏洞。

## FL-D284 生产 API、Recall Worker 和 Compare Worker 缺少 systemd 沙箱限制（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：生产三个服务均以 `fundlex` 用户运行，但没有测试服务已有的 `NoNewPrivileges`、`PrivateTmp`、`ProtectHome`、`ProtectSystem`、`ReadWritePaths`、`RestrictAddressFamilies` 和严格 `UMask` 等约束。若 API、Worker、依赖库或处理 DOCX 的路径出现代码执行、路径写入或第三方组件缺陷，进程对主机文件系统、临时目录、用户 home、网络地址族和新权限获取的可达范围更大；生产服务之间也缺少明确的最小写入边界。严重级别：**高（High）**。
- 证据：生产单元 [`fundlex-recall-api.service`](/etc/systemd/system/fundlex-recall-api.service:6)、[`fundlex-recall-worker.service`](/etc/systemd/system/fundlex-recall-worker.service:6) 及 `/etc/systemd/system/fundlex-compare-worker.service:6` 仅配置 `User`、`Group`、`WorkingDirectory`、`EnvironmentFile`、`ExecStart` 和重启策略；`systemctl show` 显示 `NoNewPrivileges=no`、`PrivateTmp=no`、`ProtectHome=no`、`ProtectSystem=no`、`UMask=0022`。`systemd-analyze security` 对三个生产单元均给出 `9.1 UNSAFE`。测试单元 `/etc/systemd/system/fundlex-test-*.service:14-20` 已有相应限制，说明当前差异是生产配置缺口而非平台不支持。
- 处理方法：按服务实际需求迁移测试单元的基础沙箱设置，生产 API/Recall Worker/Compare Worker 至少加入 `NoNewPrivileges=true`、`PrivateTmp=true`、`ProtectHome=true`、`ProtectSystem=full`、明确的 `ReadWritePaths`、`RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6` 和 `UMask=0077`；再根据对象目录、MySQL、模型 endpoint 和 DOCX 工具链逐项验证写入与网络需求，必要时补充 capability、namespace 和 system call 限制。
- 状态与验证：**待修复，未验证**。本轮只读比较了实际生产与测试单元并运行 `systemd-analyze security`，未修改或重启服务；不能把测试单元的安全属性当作生产已具备。
- 下一步：为三个生产服务建立最小写入目录清单，先在隔离测试环境执行 `systemd-analyze verify`、健康检查、真实 Worker/Compare 处理和对象下载，再受控发布并复核生产服务状态与日志。
- 变更记录：2026-10-26 新增；与 FL-D243 的端口/环境隔离记录关联，但本条专门记录生产服务沙箱缺失。

## FL-D285 测试与生产复用相同 LLM API 密钥，削弱环境隔离（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：生产和测试虽然使用不同数据目录、认证数据库和服务端口，但 `/etc/fundlex-recall.env` 与 `/etc/fundlex-test.env` 中的 `LLM_API_KEY` 配置值相同，`LLM_MODEL` 也相同。测试环境中的代码、日志、调试路径或第三方依赖一旦被利用，可能直接消耗生产同一模型凭据的额度、触发生产供应商配额/审计关联，轮换或吊销凭据时也无法独立切断测试环境。严重级别：**高（High）**。
- 证据：生产服务使用 `/etc/systemd/system/fundlex-recall-api.service:10`、`fundlex-recall-worker.service:10` 和 Compare Worker 的 `EnvironmentFile=/etc/fundlex-recall.env`；测试服务使用 `/etc/systemd/system/fundlex-test-*.service:10` 的 `/etc/fundlex-test.env`。本轮仅比较变量行的脱敏 SHA-256，不读取或输出值：两文件 `LLM_API_KEY` 行哈希前缀均为 `7143fe7ed206`，`LLM_MODEL` 行哈希前缀均为 `1e089e630fd6`，并确认配置文件权限分别为 `root:root 640` 与 `root:fundlex 640`。密钥值未写入本记录。
- 处理方法：为测试环境配置独立、低权限、可单独限额和轮换的模型凭据；若供应商支持，进一步使用独立项目/组织、IP 或模型配额及审计标签。生产密钥只允许生产服务读取，测试发布和验收脚本不得从生产 env 文件继承。
- 状态与验证：**待修复，未验证**。本轮仅完成脱敏比较，没有轮换、吊销或真实供应商隔离验证；当前数据目录隔离不能抵消凭据级复用。
- 下一步：登记并创建测试专用密钥，验证测试模型调用、预算账本和 Langfuse/供应商审计均落入测试范围，再吊销旧的复用密钥并核对生产服务仍能调用。
- 变更记录：2026-10-26 新增；与 FL-D041 的额度/凭据可用性记录和 FL-D264 的测试发布隔离记录关联，但本条是实际密钥复用的新发现。

## FL-D286 Database repr 和数据库异常可能泄露连接凭据或内部信息（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：`Database.__repr__()` 原样插入 `self.target`，MySQL URL 通常包含用户名和密码；数据库连接错误也把底层异常正文包装进 `DatabaseError`。一旦对象进入调试日志、异常链、诊断输出或未预期的 repr 展示，连接密码可能被写入日志。另有多条 API 路径把 `str(exc)` 直接作为 HTTP 错误正文，数据库、文件系统、DOCX 和底层冲突信息可能暴露内部路径、表名、约束或实现细节。严重级别：**高（High，凭据泄露）；中（Medium，错误信息泄露）**。
- 证据：[`fundlex/db.py`](/home/opencode/fundlex/fundlex/db.py:247) 将解析出的 password 用于连接，`:253-263` 将驱动异常正文放入 `DatabaseError`，`:294-295` 的 `__repr__` 返回 `Database(..., self.target)`；本轮用脱敏测试 URL 验证 repr 会呈现 `mysql://user:password@...` 形式，未使用生产凭据。错误响应证据包括 [`fundlex/api.py`](/home/opencode/fundlex/fundlex/api.py:461-467、1015-1020、1090-1102) 和 [`fundlex/compare/api.py`](/home/opencode/fundlex/fundlex/compare/api.py:64-72、158-162)，其中多处 `HTTPException(..., str(exc))` 未统一过滤。
- 处理方法：`Database.__repr__()` 只显示 dialect、脱敏 host/database 或固定 `<redacted>`，永不显示 user/password/query；底层异常保留在受控服务端日志中时也应做凭据和路径脱敏。API 对外只返回稳定业务错误码/通用文案，使用异常类型到状态码的白名单映射；保留内部 correlation ID 供日志关联，禁止把 SQL、绝对路径、连接 URL 和驱动正文直接回传。
- 状态与验证：**待修复，未验证**。已完成脱敏 URL 的本地行为验证和源码审查，未修改代码，也未对生产日志进行凭据内容扫描；现有认证和 owner 隔离不能消除该输出渠道风险。
- 下一步：补充 repr/错误响应回归，覆盖 MySQL 认证失败、约束冲突、DOCX 解析失败、文件缺失和 Compare 结果损坏；对历史日志按变量名、URL 形态和密码模式做脱敏扫描，扫描结果不得记录秘密值。
- 变更记录：2026-10-26 新增；与 FL-D160 中“Compare API 不写异常正文”的既有处理结论关联，但本条扩展到通用数据库 repr 和多处 API 映射。

## FL-D287 标准发布器未重启 Compare Worker，可能造成 API/Worker 版本不一致（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：标准发布器同步 `fundlex/`、前端和工具后只重启 `fundlex-recall-api.service` 与 `fundlex-recall-worker.service`，没有重启独立的 `fundlex-compare-worker.service`。Compare 代码、解析器、结果契约或数据库迁移发生变化时，API 与 Compare Worker 可能运行不同版本，导致任务排队、结果解析、覆盖门禁或下载契约不一致；当前 Compare Worker 正常 active 不能证明后续发布会更新它。严重级别：**中高（High）**。
- 证据：[`tools/deploy/publish_workspace.sh`](/home/opencode/fundlex/tools/deploy/publish_workspace.sh:4-8) 只调用 root 发布器；[`/usr/local/sbin/fundlex-publish`](/usr/local/sbin/fundlex-publish:49-65) 的重启和健康检查集合只有 API/Recall Worker。生产实际存在并 active 的 `fundlex-compare-worker.service`，其单元使用相同部署目录和 env；该边界与 FL-D168 的 Compare Worker 生命周期问题、FL-D262 的测试发布边界相关。
- 处理方法：将 Compare Worker 纳入标准发布的同步、重启、active 检查和健康验收；发布前固定 API/Recall/Compare 三个服务应运行的 build/hash，发布后逐项核对。若采用独立 Compare 发布节奏，应把版本兼容契约、迁移顺序和明确的停止/排空策略写入发布流程。
- 状态与验证：**待修复，未验证**。本轮只读检查了脚本和服务状态，没有调用发布器，也没有重启服务；因此未声称当前生产版本已不一致，只确认发布流程存在覆盖缺口。
- 下一步：在隔离测试环境先做 Compare API→上传→seal→Worker→结果→报告下载回归，再更新 root 发布器及健康检查并执行一次受控发布；保留发布前备份和三服务 hash/状态证据。
- 变更记录：2026-10-26 新增；不覆盖 FL-D168 已解决的“Worker 是否安装/运行”历史结论，记录的是当前发布器未纳入该服务。

## FL-D288 multipart 上传在应用读取前缺少独立请求级资源门禁（2026-10-26）

- 发现日期：2026-10-26。
- 问题与影响：应用层已对单 DOCX 25 MiB、批次 50 MiB/20 文件、ZIP 单 part/解压总量/压缩比做限制，Nginx 也设置了 60 MiB 的请求体上限；但 FastAPI 路由接收 `list[UploadFile]` 后，应用才逐个 `read(MAX_UPLOAD_BYTES + 1)`，并将已读取的文件数据暂存在列表中。未见独立的请求并发、速率、超时、Content-Length 预检或 multipart 字段/part 总数门禁。攻击者可通过并发接近上限的 multipart 请求消耗代理缓冲、临时文件、Python 内存和 DOCX 解析 CPU；这是资源可用性风险，当前证据不足以断言已被远程利用。严重级别：**中（Medium，DoS/资源耗尽风险）**。
- 证据：[`/www/server/panel/vhost/nginx/fundlex.conf`](/www/server/panel/vhost/nginx/fundlex.conf:28) 设置 `client_max_body_size 60m`；[`fundlex/upload_validation.py`](/home/opencode/fundlex/fundlex/upload_validation.py:9-14、25-47) 的应用限制；普通上传 [`fundlex/api.py`](/home/opencode/fundlex/fundlex/api.py:911-941) 和 Compare 上传 [`fundlex/compare/api.py`](/home/opencode/fundlex/fundlex/compare/api.py:97-134) 在路由中读取并累计数据。已有大小和压缩限制是有效正向控制，不能替代请求级资源控制。
- 处理方法：在 Nginx/ASGI 层增加与应用预算一致的请求体和 multipart 限制，优先拒绝超出 `Content-Length` 的请求；为上传路由设置并发、读取速率、请求超时和每 IP/账号限流，限制 multipart part/header 数量，并让应用在累计预算超限后尽早停止且清理临时对象。继续保留 DOCX ZIP 安全验证，不以关闭压缩检查替代资源控制。
- 状态与验证：**待分析，未验证**。本轮完成源码与实际 Nginx 配置审查，未进行压力测试、并发实验或生产流量修改；现有 25/50 MiB 和 ZIP 限制应继续视为已实施控制。
- 下一步：在隔离测试环境以认证用户执行受控并发/慢上传/畸形 multipart 评测，记录内存、临时目录、CPU、响应时间和拒绝行为，基于结果确定 Nginx/ASGI/应用的最小门禁参数。
- 变更记录：2026-10-26 新增；区别于已有上传大小、DOCX 压缩炸弹和测试发布问题，本条只记录请求进入应用前及并发层面的剩余资源风险。

## FL-D289 普通文档 Worker 的完成/重试写入缺少最终 fencing 条件（2026-10-26）

- 发现日期：2026-10-26，多 agent 后端/API/Worker 只读审查。
- 问题与影响：`RunStore.finish()` 和 `RunStore.retry()` 先读取并检查 `fencing_token`、状态和租约，但最终状态更新仅使用 `WHERE id=?`。在旧 Worker 读取租约后暂停、租约过期、新 Worker 取得新 token 并完成、旧 Worker 恢复提交的交错中，旧 Worker 可能覆盖新 Worker 的状态、报告或产物指针。`claim()` 对达到最大尝试次数的过期清理也按文档 ID 更新，未绑定读取时的 token、状态、租约和 attempt，可能把新 Worker 的终态覆盖为失败。严重级别：**高（High）**。
- 证据：`fundlex/store.py:612-624` 的过期清理，`:697-722` 的 `finish()` 读取与最终更新，`:730-747` 的 `retry()` 读取与最终更新；`fundlex/db.py:287-290` 将 MySQL 的 `BEGIN IMMEDIATE` 转为普通事务。现有 `tests/test_api_store.py:98`、`tests/test_db_mysql.py:129,152` 只覆盖顺序旧 token 拒绝或双 Worker claim，不覆盖“旧 Worker 已读取后新 Worker 完成、旧 Worker 再提交”。
- 处理方法：MySQL 读取时使用锁读，或将 `fencing_token`、状态、未过期租约及必要的 attempt 纳入最终条件更新；过期清理绑定原 token、`status IN ('leased','running')`、`lease_until<=now` 和 attempt；所有关键更新检查 `rowcount == 1`，失败转为 stale lease。增加 SQLite 确定性交错测试和配置 MySQL 8 的并发回归。
- 状态与验证：**已确认代码时序风险，待修复、未实际并发复现**。本轮未运行真实 MySQL 并发测试，不能据此宣称已发生生产覆盖。
- 下一步：先补确定性交错测试，再在隔离 MySQL 8 上验证旧 Worker 的 finish/retry/过期清理均不能覆盖新 token；验证通过后再评估迁移和部署影响。
- 变更记录：2026-10-26 新增；与 FL-D160 的 Compare 过期清理问题同属 fencing 边界，但本条专门记录普通 `RunStore`。

## FL-D290 指引解析 Worker 缺少 fencing token，旧解析结果可覆盖新尝试（2026-10-26）

- 发现日期：2026-10-26，多 agent 后端/API/Worker/持久化只读审查。
- 问题与影响：`guide_jobs` 只有 attempts、lease_until 和状态，没有独立 fencing token。旧解析 Worker 的 `release_guide_job()` 或 `finish_guide_job()` 只按 job id 写入：租约过期后新 Worker 已重新领取时，旧 Worker 仍可能将新任务改回 queued/uploaded，或把旧 rules JSON、hash、解析状态写入当前版本。结果可能造成页面状态与规则内容不一致，并使绑定该指引的任务出现 `GUIDE_RULESET_HASH_MISMATCH`。严重级别：**高（High）**。
- 证据：`fundlex/guide_store.py:49-53` 的表结构，`:347-365` 的 claim，`:368-388` 的 release，`:391-431` 的 finish；`fundlex/jobs.py:303-309` 的 Worker 调用不携带租约校验。现有 `tests/test_guide_store.py:106` 覆盖顺序 claim/release/再次 claim/finish，未覆盖旧 Worker 与新 Worker 交错。
- 处理方法：为 `guide_jobs` 增加独立 fencing token，并由 release/finish 带 token 更新；或至少把读取到的 attempts、lease_until 和 leased 状态作为条件，同时检查 `rowcount`，失败时明确返回 stale lease。补旧解析 Worker 晚到 release、成功、失败三类交错测试。
- 状态与验证：**已确认代码时序风险，待修复、未实际并发复现**。本轮未运行真实模型或 MySQL 并发链路。
- 下一步：设计迁移兼容方案，先用 SQLite 交错夹具固定租约语义，再用 MySQL 8 验证行锁、重试和版本发布的一致性。
- 变更记录：2026-10-26 新增；不把普通文档 Worker 的 token 设计或顺序测试当作指引解析 job 已具备 fencing 的证明。

## FL-D291 并发提交修订选择可能发布不成对的 selected 产物（2026-10-26）

- 发现日期：2026-10-26，多 agent 后端/API/产物链只读审查。
- 问题与影响：`_apply_selection()` 先保存 `selected_final`，再按选择保存或删除 `selected_redline`；数据库按 `(document_id, kind)` 分别替换指针，没有 selection epoch、决策摘要或源 redline hash。两个不同选择并发提交时，最终可能出现 `selected_final-B` 与 `selected_redline-A` 的混合，下载者无法证明两份文件属于同一次选择。重复提交还可能留下已失去数据库指针的旧对象文件。严重级别：**高（High）**。
- 证据：`fundlex/api.py:496-524` 的分步发布逻辑；`fundlex/store.py:468-501` 的独立对象复制和 `INSERT OR REPLACE`；`:523-550` 的 selected 源完整性检查只验证源 redline 存在及自身完整性，不验证 final/redline 的选择版本一致。已有 `tests/test_selective.py:221`、`tests/test_revision_api.py:89` 覆盖顺序幂等和内容，不覆盖并发不同选择。
- 处理方法：引入 selection epoch 或决策 hash，把 final/redline 放入同一选择版本记录并原子切换；旧请求提交时若 epoch 已变更则返回冲突并清理临时对象；为替换后的旧对象建立清理策略。下载和报告同时返回并校验选择版本。
- 状态与验证：**已确认代码级并发风险，待修复、未实际并发复现**。本轮未修改业务代码，未启动真实任务。
- 下一步：增加两个并发请求的确定性测试，覆盖默认接受、部分拒绝、selected_redline 删除和失败回滚，再验证对象回收与下载配对。
- 变更记录：2026-10-26 新增；与 FL-D103 的选择产物交付设计关联，但 FL-D103 已有的顺序语义不能覆盖本条并发发布边界。

## FL-D292 损坏的 report_json 可使报告和任务列表接口返回 500（2026-10-26）

- 发现日期：2026-10-26，多 agent 后端/API/数据完整性只读审查。
- 问题与影响：部分指标路径会容忍损坏 JSON，但核心报告路径直接 `json.loads()`。一条损坏的 `report_json` 可能让单文档报告接口、任务文档列表的 reason 提取或任务报告流程抛出未处理异常，用户无法查看其余合同。严重级别：**中（Medium）**。
- 证据：`fundlex/store.py:460-466` 的 `get_report()` 直接解析，`fundlex/tasks.py:142-158` 的 `_reasons()` 直接解析；`fundlex/api.py:1073-1076` 的报告路由只捕获 `NotFound`。`tasks.py:161-166` 的 `_report_phase()` 已有局部容错，说明项目内处理口径不一致。
- 处理方法：统一把损坏报告转换为稳定错误码和 409/422 响应，保留文档状态和原始报告 artifact 供诊断；任务列表对单条坏记录返回受控 reason，不阻断其余合同；补充损坏 JSON 的 API 回归。
- 状态与验证：**已确认代码路径风险，待修复、未注入损坏数据验证**。本轮没有修改数据库或生产数据。
- 下一步：用 SQLite 夹具分别覆盖报告、任务详情、任务列表和下载路径，确认错误响应不泄露底层 JSON/路径，且其他文档仍可访问。
- 变更记录：2026-10-26 新增；与 FL-D286 的通用错误正文泄露问题相邻，但本条专门记录损坏报告导致的可用性和错误处理缺口。

## FL-D293 Compare 上传完成后使用旧闭包 refetch，可能把成功封存误报为中断（2026-10-26）

- 发现日期：2026-10-26，多 agent 前端只读审查。
- 问题与影响：`continueUpload()` 在 `setSelectedTaskId(draft.task.id)` 后调用闭包中的 `task.refetch()`。该闭包可能仍对应上传前的旧 `selectedTaskId`（包括 `undefined`），因此在任务已成功封存后仍可能请求旧任务或 `/api/compare/tasks/undefined`，并进入 catch 把成功提交显示成“上传中断”。已完成上传虽然保留，但用户可能误以为需要继续上传或重复操作。严重级别：**中（Medium）**。
- 证据：`frontend/src/pages/Compare/ComparePage.tsx:310-324`；`setSelectedTaskId` 是异步状态更新，随后立即使用的 `task` 来自旧 render。现有前端静态检查和壳层浏览器测试未覆盖首次创建后闭包更新与 refetch 错误路径。
- 处理方法：使用 `draft.task.id` 对应的显式查询 refetch/invalidate，或在状态更新后由 effect 按当前 id 触发查询；不要让旧闭包的 refetch 决定成功提交结果。补首次创建、全部上传、seal 成功以及旧查询失败的浏览器回归。
- 状态与验证：**已确认源码级竞态风险，待修复、未实际浏览器复现**。本轮未修改前端代码。
- 下一步：先检查 `useCompareTask`/query key 的 enabled 语义，再用隔离测试服务复现首次 Compare 创建和封存流程。
- 变更记录：2026-10-26 新增；与 FL-D153 的批量文件状态竞态、FL-D250 的 Compare 真实交付证据关联，但本条专门记录上传成功后的旧闭包查询。

## FL-D299 V2 任务失败筛选与后端 completed 状态口径不一致（2026-10-26）

- 发现日期：2026-10-26，多 agent 前后端交叉审查。
- 问题与影响：React V2 任务页提供 `failed` 状态筛选，但后端 `TasksService._summary()` 将文档 `succeeded` 和 `failed` 都计入 completed，并在全部终态时返回任务状态 `completed`。含失败合同的任务通常因此不会出现在 `failed` 筛选中，用户只能从异常计数或详情页发现失败。严重级别：**中（Medium）**。
- 证据：`frontend/src/pages/Tasks/index.tsx:49-52` 的 failed option；`fundlex/tasks.py:186-203` 的聚合状态；`fundlex/tasks.py` 同时单独返回 `exceptions`，说明失败事实存在但未映射到任务级筛选状态。后端审查确认这延续 FL-D123 的状态口径遗留，但前端 V2 的可见筛选使缺口重新暴露。
- 处理方法：明确任务级 failed 语义并统一 API、统计、筛选和状态徽章：若任一合同失败则任务状态为 failed，或改为明确的 completed-with-exceptions 状态并同步筛选项、文案和排序。补成功/失败混合、全失败和重试后的 API 与浏览器回归。
- 状态与验证：**已实施并完成本轮局部验证；项目级真实交付仍未闭合**。后端统一为全成功 `completed`、混合失败/异常 `completed_with_exceptions`、全失败 `failed`，并同步 API 筛选、统计 `failed_contracts`、V1/V2 状态徽章/通知/暂停按钮和 Feishu 状态卡片。定向后端回归包含任务状态、报告边界、Review、Feishu/OAuth 和 API 安全共 **59 passed / 1 warning**；浏览器 V1/V2 **40 passed**；尚未完成真实 MySQL 并发和完整用户交付验证。
- 下一步：在真实 MySQL 8 并发条件下验证任务状态聚合、筛选和 Feishu outbox 的一致性；继续用真实合同核对混合/全失败任务的结果页、报告和授权下载。项目级固定评测、Compare、OAuth 真实扫码回调和 D01–D20 gate 仍按既有记录阻断。
- 变更记录：2026-10-26 新增时误用已占用 FL-D294；本轮保留 FL-D294 的 Feishu 详情深链条目，将任务状态条目更正为 FL-D299。代码提交为 `59e9cf2`（后端契约）和 `cdf0699`（V1/V2/Feishu UI）；局部验证不代表项目 GO。

## FL-D295 React V2 根路径资源和 API 构造未覆盖 URL 前缀部署（2026-10-26）

- 发现日期：2026-10-26，多 agent 前端/部署交叉审查。
- 问题与影响：React V2 的 API client、登录页 logo 和 AppShell logo 使用根路径 `/api`、`/static`。若 V2 部署在 `/test/` 或其他 URL 前缀下，页面可能请求生产根 API 或返回静态资源 404，造成登录、能力探测和页面资源失败。当前 `/test/` 公网验收只覆盖 V1，不能证明 V2 前缀部署可用。严重级别：**中（Medium）**。
- 证据：`frontend/src/api/client.ts:45-70` 的 `assertApiPath()` 与 fetch，`frontend/src/pages/Auth/index.tsx:9` 和 `frontend/src/components/layout/AppShell.tsx:103-105` 的根路径静态资源；FL-D264 只验证了测试前缀下 V1 的 `/test/api` 和 `/test/static` 路径。
- 处理方法：统一从运行时注入的 frontend base path 构造 API、静态资源和下载地址，或让 Vite `base` 与服务端前缀契约一致；补 V2 在 `/test/` 下的登录、路由、资源和 API 404 浏览器验收。
- 状态与验证：**已确认源码级部署风险，待修复、未验证**。生产根路径 V2 的静态检查通过，不能外推到前缀部署。
- 下一步：先明确 V2 的正式部署前缀契约，再在隔离测试入口发布候选构建并完成真实登录 smoke；不以当前 V1 前缀证据代替 V2。
- 变更记录：2026-10-26 新增；与 FL-D264 的 V1 前缀资源修复关联，但本条保留 V2 独立路径构造问题。

## FL-D296 部署 smoke 未完成真实合同交付验收（2026-10-26）

- 发现日期：2026-10-26，多 agent 测试与交付证据只读审查。
- 问题与影响：`tools/deploy/cloud_verify.py` 创建临时账号、生成测试 DOCX、上传并封存后读取任务和文档快照，但不等待 Worker 最终成功，不下载或校验 final/redline/report，不核对修订内容、Claim Replay、产物哈希、Review selected artifact 或授权下载边界。若把该脚本作为发布后的合同验收，可能把 API/认证/上传基本可用误报为真实合同交付完成。严重级别：**高（High）**。
- 证据：`tools/deploy/cloud_verify.py:7-10` 的检查范围；完整生产 V1 交付所需的 Worker/model/DOCX、Review、selected artifact、下载和哈希证据已在 FL-D276 的 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-o9rfdisxoj2o/` 中单独核对。两者证据层级不同，smoke 不能替代正式 E2E。
- 处理方法：将部署验证拆为基础 smoke 和正式合同 E2E 两层；发布门禁使用默认工作台入口提交真实合同，等待实际 Worker/model 处理，核对 report、Claim Replay、final/redline、DOCX 内容与哈希，执行 Review accept/reject、selected artifact 和授权下载检查，并清理临时身份和对象。脚本输出应明确标记 smoke 或 delivery-e2e，不共享“成功”状态。
- 状态与验证：**已确认验收范围不足，待补齐**。现有一份生产 V1 普通合同真实交付已经通过，但不代表 `cloud_verify.py` 本身具备完整交付能力；本轮没有运行新的模型任务或修改脚本。
- 下一步：为正式发布建立可审计的 delivery E2E 命令和证据目录，保留 smoke 的快速健康检查用途；在预算、测试合同和清理策略明确后执行隔离环境及生产受控复验。
- 变更记录：2026-10-26 新增；与 FL-D024/FL-D025 的真实交付边界和 FL-D276 的单份生产 V1 证据关联，不把已有真实成功证据倒推为 smoke 脚本已覆盖。

## FL-D297 规则包发布状态与 README 自动写入描述直接冲突（2026-10-26）

- 发现日期：2026-10-26，多 agent 测试与交付证据只读审查。
- 问题与影响：当前 `rules/rules_v2.json` 明确为 `status: "unreleased"`、`auto_write_enabled: false`，而 `README.md:9-11` 仍保留“全部 22 个 action 已发布、正式交付自动写入可用”的历史描述。接续者或发布人员可能据 README 启用错误入口、误把未发布规则包当成正式能力，或把历史 v2 证据误用为当前 release gate。严重级别：**高（High）**。
- 证据：`rules/rules_v2.json:10-13`、`README.md:9-11`、`rules/release_v2.py:67-109`；发布脚本要求证据与当前引擎、规则、模型传输和 prompt context 完全匹配，并满足唯一文档数及实际修改门槛。FL-D278 已记录总体文档时态漂移，本条专门记录规则状态与正式写入描述的直接矛盾。
- 处理方法：建立唯一当前状态索引，明确当前源码、生产 recall-first 路径、未发布评测规则包、部署候选和历史 v2 证据；修正 README 的当前描述或将历史段落显式标日期与“已废止/不作为当前发布依据”标记。发布器、能力接口和文档应共享同一发布状态来源。
- 状态与验证：**已确认、待收敛**。本轮只读核对规则、README 和发布脚本，未修改规则包或文档，也未启用自动写入。
- 下一步：先确定当前正式产品入口和规则发布决策，再同步 README、实施计划、能力说明和发布证据；以当前候选重新运行 release gate，禁止用历史 v2 证据代替。
- 变更记录：2026-10-26 新增；与 FL-D278 合并关联但不覆盖其具体规则状态冲突。

## FL-D298 修订选择接口静默接受无效 ID，响应可能与实际 DOCX 不一致（2026-10-26）

- 发现日期：2026-10-26，多 agent 修订引擎/DOCX 只读审查。
- 问题与影响：选择接口将客户端决策直接交给生成器，没有根据当前 redline manifest 验证公开的修订 ID。未知 `del_id` 可能被静默忽略并返回 HTTP 200，用户提交的拒绝意图因此没有进入 `selected_final`；偶数 `ins_id` 也可能被接受，但响应的 `accepted`/`rejected` 按原始 verdict 计算，而实际文件按 `_explicit_verdicts()` 展开同一对 `del/ins`，导致 API 响应与下载 DOCX 的实际修改不一致。需要已认证用户提交无效或过期 ID，当前未发现越权影响。严重级别：**中（Medium）**。
- 证据：`fundlex/api.py:496-531` 的 `_apply_selection()` 直接传入决策并返回结果；`fundlex/selective.py:111` 的 `_normalise_decisions()` 保留未知输入之外的空映射，`:163` 的 `_explicit_verdicts()` 展开配对决策，`:197` 的 `apply_decisions()` 只处理 manifest 中已知修订，`:288-293` 的结果计算未把无效 ID 或实际展开 verdict 反映给 API。离线使用仓库历史 `working_redline` 夹具复现：提交不存在的 `del_id=9999` 返回 200、没有 rejected/absent，生成文件与全量接受版本相同；提交偶数 `ins_id=2` 返回 accepted/rejected 与实际 selected DOCX 文本不一致。现有 `tests/test_selective.py:299-307` 将未知 ID 返回空 absent 固定为预期，未覆盖 API 输入契约。
- 处理方法：API 层只接受当前 manifest 公开的有效 `del_id`，拒绝未知 ID、偶数 `ins_id`、重复或冲突决策及过期决策，返回稳定的 `REVISION_DECISION_ID_INVALID` 类 409/422 错误；选择生成器统一生成每个 revision pair 的最终 verdict，实际文件、accepted、rejected 和报告均使用同一结果。增加未知 ID、偶数 ID、混合有效/无效 ID、冲突提交和响应与 DOCX 文本一致性回归。
- 状态与验证：**已确认代码级输入校验与响应一致性缺陷，待修复、未在真实用户任务中复现**。定向选择/Review/DOCX 回归为 29 passed、1 个既有 Starlette/httpx warning；DOCX 结构、Claim Replay、交付门禁和 recall 集成定向回归为 131 passed、2 warnings。本轮未修改源码、未运行真实模型或部署。
- 下一步：先冻结有效 `del/ins` 公开 ID 和过期选择的 API 契约，再补输入拒绝及产物响应一致性测试；修复后核对 selected_final 下载内容、哈希和 Review 页面展示。该问题与 FL-D103 的有效配对语义、FL-D291 的并发产物混配风险相关，但分别属于输入校验/响应一致性和并发发布问题。
- 变更记录：2026-10-26 新增；原拟用 FL-D296，但该编号已用于部署 smoke 验收范围不足，按集中记录编号规则改用 FL-D298。

## FL-D400 飞书多任务接入：卡片路由、Compare、指引生成、诊断/评测（2026-10-28）

- 发现日期：2026-10-28，用户确认扩展飞书任务中心后实施。
- 问题与影响：原飞书入口只创建合同修订草稿；用户要求接入合同对比、法规指引生成、任务查询/结果回传和只读诊断/评测。若继续让任意文本默认创建修订草稿，或让卡片直接相信任务 ID，会造成任务类型混用、串文件、越权下载和状态卡无法分发。诊断/评测还涉及“跑完整流程但只回报告”的产物边界，不能只在飞书层伪造。
- 处理方法（已实施，当前工作区）：
  - `feishu_drafts` 增加 `task_type/step/metadata_json/target_id`，`feishu_draft_files` 增加 `side/kind/pair_index/revisions_accepted`，`task_channels` 增加 `task_type/last_external_status/last_progress_json`；保留旧任务默认值。
  - 新增任务中心卡、Compare 左右文件收集/交换/确认、指引 PDF/DOCX 接收/确认、任务列表卡、完成卡文件回传；卡片回调按 `tenant_key + open_id + chat_id + owner` 重新校验。
  - Compare 复用 `CompareStore.create/upload/seal`；指引生成复用新增的 `fundlex/guide_generation/service.py` 入队 helper；两者都通过统一 outbox 更新状态卡。
  - 任务后端增加 `tasks.mode` 和 `batches.mode`；诊断模式在交付校验通过后只发布报告类产物，评测模式发布 `evaluation_final/evaluation_redline` 且正式 `final/redline` 不可下载。
  - `FeishuClient` 增加 `send_file`；结果发送按 owner 重新读取任务/产物。
  - 新增 `tools/deploy/fundlex-guide-worker.service.template`，指引生成 run 需要独立 worker 消费。
- 状态与验证：**代码已实施并完成受控生产发布；Compare 真实飞书 E2E 通过；指引生成/诊断/评测真实模型 E2E 未完成**。完整 Python 回归 **1754 passed / 58 skipped / 3 warnings / 501.51s**；Feishu 专项 **19 passed**、tasks API **30 passed**；V1/V2 浏览器 **44 passed**，指引生成浏览器 **1 passed**；前端 typecheck/lint/Vitest **14 passed**/build 通过；`compileall`、`node --check`、`git diff --check` 通过。生产服务 `fundlex-recall-api/worker/compare-worker/feishu/guide-worker` 均 active；真实 Compare 任务 `4858ac14f16144309d70462ef5eb7b72` 完成（621 处差异、coverage incomplete），状态卡、报告文件回传和 `#compare?mode=detail&id=` 浏览器深链通过；指引 PDF 上传/确认卡/取消通过，未启动 model run；诊断/评测仅隔离测试，未调用真实模型。卡片按钮已改为 2.0 `behaviors.type=callback` 且卡片声明 `update_multi=true`；真实用户点击回调尚未由人工点击验证，已用等价 card action 事件验证 handler。详见 FL-D401–FL-D404。
- 下一步：按 `docs/FEISHU_MULTI_TASK_INTEGRATION_PLAN.md` 做受控发布；安装 guide worker；分别用真实飞书用户完成 Compare、指引生成、诊断、评测和结果回传路径，核对深链、文件哈希、owner 边界和 outbox 恢复。结果文件回传还要求飞书应用增加 tenant scope `im:resource` 并发布应用版本；当前生产应用版本尚未确认包含该权限。现有合同修订 `incomplete` 质量问题和项目级 NO-GO 不因本功能改变。
- 变更记录：2026-10-28 新增。

## FL-D401 飞书 2.0 卡片不再支持 action 交互模块，发送卡片报 200861（2026-10-28）

- 发现日期：2026-10-28，生产部署后首次发送任务中心卡。
- 问题与影响：`cards._actions()` 仍生成卡片 JSON 1.0 的 `{"tag":"action","actions":[...]}`。飞书返回 `FEISHU_API_230099`，`ErrCode 200861`，提示 `cards of schema V2 no longer support this capability; unsupported tag action`。所有带按钮的卡片（任务中心、Compare、指引、诊断、完成回传）都会发送失败。
- 证据：生产真实 `send_card` 返回上述错误；飞书 2.0 文档明确“2.0 结构已不支持交互模块（tag=action），按钮应直接放在 elements 或 column_set 中”。
- 处理方法：`_actions()` 改为 `column_set` + `column` + 直接 `button`，并在按钮 `behaviors` 中写入 `type=callback` 的 `value`；保留顶层 `value` 兼容旧客户端。生产重新发布 `cards.py` 后，任务中心卡、Compare 提示/完成卡、指引确认卡和任务列表卡均发送成功。
- 状态与验证：**已解决（生产真实卡片发送验证）**。Compare 全链路任务 `4858ac14f16144309d70462ef5eb7b72` 的卡片创建、状态更新、报告回传和浏览器深链均通过。
- 下一步：后续新增卡片必须使用 2.0 组件结构，不再生成 `tag=action`；在 `tests/test_feishu_integration.py` 中补充卡片结构断言，避免回归。
- 变更记录：2026-10-28 新增；与 FL-D400 同批部署发现。

## FL-D402 生产 guide worker 模板引用了不存在的 cli 模块（2026-10-28）

- 发现日期：2026-10-28，安装 `fundlex-guide-worker.service` 后服务反复重启。
- 问题与影响：模板使用 `python -m fundlex.guide_generation.cli worker --poll 5`，但生产 `/opt/fundlex-recall-first/fundlex/guide_generation/` 没有 `cli.py`，服务报 `No module named fundlex.guide_generation.cli`，指引生成 run 无法被消费。
- 处理方法：改用生产已存在的 `fundlex.guide_generation.worker` 模块（其 `__main__` 已实现 `run_forever`），更新 `tools/deploy/fundlex-guide-worker.service.template` 和已安装 unit；重启后 worker active。
- 状态与验证：**已解决（生产服务 active，空队列稳定运行）**。未创建真实 model run，因此未验证实际生成耗时/预算。
- 下一步：用一条经授权的真实法规生成 run 验证 worker 消费、状态回写和审核入口；不得把空队列 active 当作生成能力通过。
- 变更记录：2026-10-28 新增；与 FL-D400 指引生成接入相关。

## FL-D403 并发启动时 Feishu 表迁移 ALTER 竞争导致一次 DATABASE_OPERATION_FAILED（2026-10-28）

- 发现日期：2026-10-28，首次部署新飞书列后同时启动 API 与 Feishu 服务。
- 问题与影响：API 启动日志出现 `ALTER TABLE feishu_draft_files ...` 的 `DATABASE_OPERATION_FAILED`。两个进程同时执行 `ensure_schema` 的“检查列→ALTER”时，一个进程可能已加列而另一个仍执行 ALTER，造成服务启动失败/重试。发布器正常路径会先迁移 schema，但手工部署或并发重启仍可能触发。
- 处理方法：`IntegrationStore._add_column()` 捕获 ALTER 失败后重新读取列；列已存在则视为并发迁移成功，否则继续抛出。已部署到生产并重启 API/Feishu；重启后无 `DATABASE_OPERATION_FAILED`。
- 状态与验证：**已实施并完成生产启动验证**；未在 MySQL 8 并发压测中主动制造竞争。`tasks/batches` 的其他迁移仍依赖发布器先迁移或单进程启动。
- 下一步：如需彻底消除，给 TaskStore/RunStore 迁移统一加同样的幂等 ALTER 保护，并在发布器 migrate 阶段覆盖所有新列。
- 变更记录：2026-10-28 新增。

## FL-D404 飞书应用缺少 im:resource，结果文件回传被拒（2026-10-28）

- 发现日期：2026-10-28，Compare 报告回传首次尝试。
- 问题与影响：上传文件返回 `99991672`，提示需要 `im:resource:upload` 或 `im:resource`；没有该权限时“发送最终版/修订版/报告”全部不可用，而卡片和任务本身可以正常创建。
- 处理方法：通过应用配置 API 增加 tenant scope `im:resource` 并发布新应用版本；未记录任何 App Secret 或 token。随后同一上传接口返回 `code=0`，Compare 报告和修订任务报告均真实发送到飞书私聊。
- 状态与验证：**已解决（生产真实文件上传/发送验证）**。Compare 报告发送、既有修订任务报告发送均成功；未验证超大文件回退路径。
- 下一步：在应用发布检查中固定验证 `im:resource`，并补文件大小超限时的深链回退测试。
- 变更记录：2026-10-28 新增。

## FL-D405 飞书卡片不能内嵌文件上传，任务名称改为卡片表单、文件仍走消息（2026-10-28）

- 发现日期：2026-10-28，用户要求“点任务后在卡片里填写任务名和提交文件”。
- 问题与影响：飞书卡片 JSON 2.0 交互组件只有输入框、下拉、人员、日期、选择器等，**没有文件上传/附件选择组件**；文件只能作为聊天文件消息发送，或在网页端选择。若在卡片里伪造“上传”按钮，会造成用户误以为可以选文件。
- 处理方法：新增 `task_name_card` 表单卡：任务名称输入框 + “保存并继续”；保存后更新同一张卡片为文件提示，用户再发送 `.docx`/PDF 文件消息。表单按钮使用 `form_action_type=submit`，服务端从回调 `action.form_value.task_name` 读取名称；文本直接发送任务名仍兼容。文件流程、草稿类型和后续确认逻辑不变。
- 状态与验证：**已被 FL-D417 文件优先流程取代（2026-10-28）**。真实飞书发送任务名称卡、提交表单、卡片更新为文件提示、取消流程曾通过；隔离 Feishu 测试 **16 passed**。新草稿不再经过名称表单，旧表单仅兼容历史草稿。
- 下一步：若用户坚持卡片内选文件，需要改为飞书网页应用/小程序嵌入或打开 FundLex 网页上传；普通消息卡片无法实现。补真实点击表单和文件发送回归。
- 变更记录：2026-10-28 新增。

## FL-D406 文件收集卡与取消单批 20 个文件限制（2026-10-28）

- 发现日期：2026-10-28，用户确认文件上传规则后实施。
- 问题与影响：原飞书卡片只列文件、无移除/替换；网页端和飞书入口都存在 20 个文件上限；重复内容可被重复添加；取消草稿不会清理暂存对象；文件下载/校验失败可能只把事件标为 dead，用户看不到原因。
- 处理方法：
  - 飞书 `draft_card` 显示 accepted/rejected 文件，逐文件“移除”；Compare 支持“替换左侧/右侧”；指引支持“替换文件”；确认按钮仅在至少一个 accepted 文件时出现。
  - 同草稿相同 SHA-256 不重复添加；Compare 按侧去重；超过总字节上限/格式错误显示卡片错误；下载、暂存失败在卡片提示。
  - 取消草稿或提交成功后删除草稿暂存对象；提交后不会混入新任务。
  - 移除 `MAX_BATCH_DOCUMENTS` 与网页 20 文件校验；multipart 仍保留高安全上限和 50MB 总量限制；API capabilities 不再返回 `max_request_files`。
  - 飞书非文件消息（图片/语音等）提示改用文件消息。
- 状态与验证：**已实施并生产发布**。生产真实飞书文件收集卡、移除文件、取消清理通过；网页 API 25 文件单请求候选测试通过；Feishu 专项 **19 passed**（含表单、去重、移除/替换、取消清理）；`test_tasks_api.py` **30 passed**（含 25 文件单请求）；完整 Python **1754 passed / 58 skipped**。
- 下一步：用真实用户验证 Compare 替换左右、指引替换文件、超大/超总量错误提示；补 20 个以上文件的真实网页上传和飞书连续发送回归。
- 变更记录：2026-10-28 新增；与 FL-D405 任务名称卡同批。

## FL-D407 飞书表单提交按钮回传 name 非固定值，任务名保存无响应（2026-10-28）

- 发现日期：2026-10-28，用户真实点击任务名称卡后反馈“没有提醒提交文件”。
- 问题与影响：任务名称卡发出后，草稿停留在 `step=name`；用户点击“保存并继续”后没有出现文件提示。服务端原先要求回调 `action.name` 必须等于 `save_task_name` 才处理 `form_value`，但飞书对表单内按钮可能回传自动生成的 name（例如 `Button_...`），导致合法表单提交被当作未知按钮，用户无法进入文件收集步骤。
- 证据：`feishu_drafts` 中真实草稿 `bbd9d13d1b4c46afb785a0fe5da123fa` 长时间停留在 `step=name`；`integration_events` 有两次 `p2.card.action.trigger` processed，但草稿未更新。事件表只保存 payload hash，未保存原文；按飞书表单回调结构，`form_value` 是稳定字段，按钮 name 不应作为唯一判据。
- 处理方法：服务端改为只要回调含非空 `form_value` 且当前草稿处于 `step=name` 就保存任务名；额外兼容 `action_name=save_task_name`、`skip_name`（使用默认名称并继续）、以及客户端丢失 form_value 时的无 command 兜底，使用默认名称进入文件收集。日志只记录按钮 name 和字段名，不记录用户输入值。
- 状态与验证：**表单路径已被 FL-D417 取代（2026-10-28）**。曾用自动生成 button name 验证 `step name → collecting`；新流程不再创建名称表单，仅保留旧草稿兼容。Feishu 专项当前 **30 passed**。
- 下一步：用真实用户点击“保存并继续”确认卡片更新；如果仍无响应，记录日志中的 `action.name` 和 `form_value` 字段名（不记录值）继续排查。
- 变更记录：2026-10-28 新增；与 FL-D405 任务名称卡相关。

## FL-D415 飞书按钮后续卡片原地更新，用户只看到 toast 闪一下（2026-10-28）

- 发现日期：2026-10-28，用户真实点击任务中心按钮后反馈“闪出一个卡片但马上没有了，没有文件发送提醒”。
- 问题与影响：点击任务按钮时 `_start_flow` 优先 `update_card` 更新原菜单卡；如果菜单卡在会话上方或更新表现不稳定，用户只看到回调 toast，误以为没有进入下一步。若已有活跃草稿，点击同类型任务只会更新旧草稿卡，不会在会话底部出现新的文件提示。
- 证据：真实会话连续 5 次 `p2.card.action.trigger` processed，但草稿 `15e2ecd38326417a93885acc18024c7a` 的 `updated_at` 不变；用户看不到新的卡片。任务中心/草稿卡消息 ID 仍在数据库中。
- 处理方法：`_start_flow` 不再原地更新菜单卡，始终发送**新的**任务名称卡/当前草稿卡；已有同类型活跃草稿时在新消息中重新发送文件收集卡；`continue_draft` 也使用新消息；表单保存任务名后也改为发送**新的**文件收集卡，不再原地修改会被飞书表单提交状态影响的卡片。回调仍返回简短 toast，但下一步卡片是独立持久消息。
- 状态与验证：**已修复并生产发布**。已为卡住的真实草稿重新发送文件收集卡，并补发普通文本提示作为稳定锚点；Feishu 专项 **19 passed**。真实用户点击新卡仍需确认。
- 下一步：点击任务按钮后应在会话底部看到新卡；若仍只出现 toast，检查 `client.send_card` 是否被 Feishu 限流或卡片 schema 校验拒绝（日志只记录错误类型）。
- 变更记录：2026-10-28 新增（原误用 FL-D408，已改为 FL-D415）；与 FL-D407 表单回调问题连续出现，分别修复“保存无响应”和“下一步卡片不可见”。

## FL-D416 飞书任务中心需要用户主动发“菜单”，缺少常驻入口（2026-10-28）

- 发现日期：2026-10-28，用户要求不主动发菜单也能看到任务中心卡片。
- 问题与影响：任务中心卡只在绑定成功、发送“菜单”或收到未知文本时发送；用户进入会话时没有稳定入口，容易以为机器人没有功能。
- 处理方法：发送一张带“常驻任务中心”说明的干净菜单卡，并通过飞书 Pin API 置顶；移除旧的测试菜单 Pin，只保留当前任务中心卡。Pin 使用应用已有 `im:message.pins:write_only` 权限，真实生产调用返回 `code=0`。
- 状态与验证：**已解决（生产置顶卡已验证）**。会话 Pin 列表中保留 1 张当前任务中心卡；用户无需再发“菜单”即可从置顶卡进入。
- 下一步：如果产品希望“每次打开会话自动新发一张”，需要订阅 `im.chat.access_event.bot_p2p_chat_entered_v1` 并增加 access-event scope；但会产生重复卡片，建议继续用置顶卡。后续可在绑定成功/菜单重发时自动替换旧 Pin。
- 变更记录：2026-10-28 新增。

## FL-D417 强制“任务名称”表单阻断文件收集，是“保存并继续后闪退”的根因（2026-10-28）

- 发现日期：2026-10-28，用户连续两次反馈“点保存并继续后卡片闪一下就没，根本没有文件发送提醒”，要求按产品/用户体验全链路复核。
- 问题与影响：旧流程把“填写任务名称”放在文件之前，任务名称表单是必经门槛。飞书表单提交会重绘/替换原卡片，服务端再改发新卡时用户只看到 toast；一旦表单回调异常，整个任务无法进入文件收集。这不是单按钮 bug，而是首步设计把低价值命名放在高价值文件之前。用户目标始终是“发合同 → 拿结果”。
- 处理方法：改为**文件优先**。点击任务后直接显示“请发送 DOCX”，任务名在创建草稿时按当前时间生成（`<任务类型> YYYY-MM-DD HH:MM:SS`），不提供命名/改名入口（2026-10-28 用户决定见 FL-D428）。修订/诊断/评测/对比/指引全部采用；旧 `step=name` 草稿和表单卡仅保留兼容，新草稿不再创建。
- 状态与验证：**已修复并生产发布（2026-10-28）**。Feishu 专项新增“任务启动即文件提示、无 form”“时间命名且文件不改变任务名”“旧表单兜底”用例；当前 **32 passed**。真实用户尚未在新流程下完成一次完整文件收集。
- 下一步：生产发布后用真实用户点击任务、发送 DOCX、确认创建任务走完整链路；不再要求用户点“保存并继续”。
- 变更记录：2026-10-28 新增；取代 FL-D405 的“名称表单先行”设计，FL-D407 的表单回调兼容仅用于旧草稿。

## FL-D418 多张旧卡片仍可点击，用户分不清哪张是当前卡（2026-10-28）

- 发现日期：2026-10-28，代码复核与用户“旧卡片/测试卡很多”反馈。
- 问题与影响：任务卡、表单卡、重发卡同时存在，旧卡按钮仍指向同一草稿；用户点旧卡会触发“已处理/已过期”或重复提交，且旧卡内容不会随文件列表更新，形成事实错误。
- 处理方法：同一草稿只保留一张“活卡”。`_send_card_for_draft(new_message=True)` 先把旧 `card_message_id` patch 成“卡片已更新，请使用最新卡片”；草稿取消、任务提交成功也把输入卡 patch 成无按钮的失效卡；提交后状态卡是唯一可操作卡。
- 状态与验证：**已修复并生产发布**。新增旧卡失效逻辑；Feishu 专项 **30 passed**；生产历史旧卡不追溯回收，需用户忽略。
- 下一步：生产发布后观察是否还有旧卡可点击；如 Feishu 拒绝 patch 表单卡，日志只记录错误类型并继续发新卡。
- 变更记录：2026-10-28 新增；与 FL-D415 的“新消息”策略配套。

## FL-D419 “我的任务”的“下一页”按钮无效（2026-10-28）

- 发现日期：2026-10-28，代码复核 `_collect_tasks` / `_show_tasks`。
- 问题与影响：`_collect_tasks` 固定返回前 10 条并给出 `has_more`，`_show_tasks` 接收 `page` 却始终从第 1 条渲染；用户点“下一页”看到同一页，任务多时无法找到历史任务。
- 处理方法：聚合后不再截断，`_show_tasks` 按 `_TASK_PAGE_SIZE=6` 切片；任务卡增加“上一页/刷新/下一页”和真实页码；每页编号连续；各来源最多取 50 条后统一按时间排序。
- 状态与验证：**已修复并生产发布**。新增 8 条任务第 2 页用例，Feishu 专项 **30 passed**。
- 下一步：生产用“我的任务”真实翻页确认；超过 50 条时再考虑按时间游标分页。
- 变更记录：2026-10-28 新增。

## FL-D420 置顶任务中心依赖一次性人工 Pin，代码未保证常驻（2026-10-28）

- 发现日期：2026-10-28，用户要求“不要主动发菜单也能自动有卡片常驻”。
- 问题与影响：上一轮只手工调用 Pin API 置顶了一张菜单卡；新用户绑定、旧 Pin 失效或换卡后不会自动补充，常驻入口不可持续。
- 处理方法：`IntegrationStore` 新增 `integration_state` 保存每个私聊的菜单卡 message_id；绑定成功发送菜单卡后自动 Pin，并取消上一个 Pin；用户发送“菜单”时新菜单卡替换 Pin；创建/取消/提交草稿时原地刷新置顶卡内容（是否显示“继续当前草稿”）。
- 状态与验证：**已修复并生产发布**。新增绑定自动 Pin、状态持久化、Pinned 卡刷新逻辑；Feishu 专项 **30 passed**；生产现有 Pin 已写入 state，Pin 列表仍为 1。
- 下一步：生产当前 Pin `om_x100b61227c0f9cb8cfe2203ef9d572c` 已写入 state，Pin 列表实测 1；新用户绑定自动 Pin 仍需一位新用户验证。
- 变更记录：2026-10-28 新增；取代 FL-D416 的人工 Pin 方案。

## FL-D421 卡片回调同步执行重操作，可能超过飞书 3 秒响应窗口（2026-10-28）

- 发现日期：2026-10-28，代码复核 `build_event_handler.on_card_action`。
- 问题与影响：确认创建任务会同步上传全部草稿文件，发送结果文件会逐个上传；文件多/大时超过飞书卡片回调 3 秒窗口，用户看到“操作超时”，即使后台最终成功也会重复点击。
- 处理方法：卡片回调放入 4 线程池执行；最多等待 2 秒，超时立即返回“已开始处理，请稍候，下一步卡片会自动出现”，后台继续执行并发送状态卡；任务创建仍有草稿幂等键和原子 claim，重复点击不会重复建任务；异常通过 done callback 记录类型。
- 状态与验证：**已修复并生产发布**。Feishu 专项 **30 passed**；隔离测试未模拟 3 秒网络超时，生产需用多文件任务确认 toast 不再报超时。
- 下一步：生产用 5 个以上文件或大文件确认创建任务，观察 `journalctl -u fundlex-feishu` 无回调超时错误；如仍慢，把文件上传迁移到独立队列。
- 变更记录：2026-10-28 新增。

## FL-D422 卡片显示英文状态码、错误码和 bytes，缺少“下一步做什么”（2026-10-28）

- 发现日期：2026-10-28，逐卡复核 `cards.py`。
- 问题与影响：卡片显示 `queued/running/completed_with_exceptions`、`UPLOAD_REQUEST_SIZE_LIMIT`、`123456 bytes`、`{'complete': 1}`，用户无法判断任务是否正常、失败后该做什么；结果卡只给按钮，不说明交付限制。
- 处理方法：新增状态/阶段/交付/错误中文映射；文件大小格式化为 B/KB/MB；每张状态卡增加“下一步”提示（排队、处理中、部分完成、失败、评测非正式合同）；交付统计改为“最终版 1 · 修订版 1 · 报告 2”；草稿卡显示“单个 ≤25 MB、本批 ≤50 MB”。
- 状态与验证：**已修复并生产发布**。Feishu 专项 **30 passed**；未逐张截图核对生产。
- 下一步：生产逐类型截图核对卡片可读性；如文案仍偏技术化继续收口。
- 变更记录：2026-10-28 新增。

## FL-D423 结果发送忽略按钮 kind，且缺少“发送全部交付”（2026-10-28）

- 发现日期：2026-10-28，代码复核 `_send_result_file`。
- 问题与影响：指引卡的“发送指引草案”和“发送证据”两个按钮实际都发送两份文件；修订任务有最终版/修订版/报告时没有一键发送全部，用户要逐个点；`all` 还可能把 working 文件与正式文件一起发送。
- 处理方法：指引按 `kind` 只发对应 artifact；修订/诊断/评测支持 `kind=all`，按 final/redline/report 顺序发送，正式文件存在时跳过 working 文件；报告优先 Markdown，避免 md+json 重复；结果卡在可发送项大于 1 时显示“发送全部交付”。
- 状态与验证：**已修复并生产发布**。新增“发送全部跳过重复报告格式”用例，Feishu 专项 **30 passed**。
- 下一步：生产用真实完成任务点“发送全部交付”，核对文件数量、文件名和可下载性。
- 变更记录：2026-10-28 新增。

## FL-D424 合同对比卡首句要求先去工作台，与“飞书内办理”目标冲突（2026-10-28）

- 发现日期：2026-10-28，逐卡复核 `compare_prompt_card`。
- 问题与影响：对比卡第一句是“请先在 FundLex 工作台确认两份合同都是可编辑 DOCX”，用户会以为必须打开网页才能开始；文件大小显示 bytes，错误码直接显示英文。
- 处理方法：改为“第 1 步：发送左侧（原版）DOCX / 第 2 步：发送右侧（对比版）DOCX”，明确可交换左右；文件大小格式化；错误经 `friendly_error` 转为中文；完成后状态卡显示差异数和对比页深链。
- 状态与验证：**已修复并生产发布**。Compare 流程用例通过，Feishu 专项 **30 passed**。
- 下一步：生产真实两份 DOCX 走完对比，确认用户不需要先打开工作台即可创建任务。
- 变更记录：2026-10-28 新增。

## FL-D425 带修订痕迹的合同在交付任务中只得到 not_generated，上传前没有拦截（2026-10-28）

- 发现日期：2026-10-28，生产复盘用户真实任务 `3569d09b59f84851bd3253496e7cd375`（任务名“飞书合同任务2222”）。
- 问题与影响：合同 `广发恒阳一年持有期混合型证券投资基金基金合同20261022.docx` 上传后任务 `completed`，但 `delivery_status=not_generated`，仅生成 `report_md`/`report_json`，没有 final/redline；报告错误为 `EXISTING_REVISION_UNSUPPORTED`。用户在飞书只看到“任务结果/已完成/交付 not_generated”，没有明确原因和处理方法，容易误以为合同已处理成功。引擎本身拒绝已有修订痕迹的文档，但上传阶段没有提前告知。
- 证据：任务 `3569...`、文档 `10c9abba...`、`delivery_counts={'not_generated': 1}`、`report_md` 849 bytes；报告“错误：EXISTING_REVISION_UNSUPPORTED”。未记录合同正文。
- 处理方法：
  - `upload_validation.has_tracked_revisions()` 扫描 `word/*.xml` 的修订标签（ins/del/move/format change 等）。
  - 飞书修订/诊断/评测接收文件时先校验；命中则把文件标为 rejected，错误码 `EXISTING_REVISION_UNSUPPORTED`，卡片提示“先在 Word 接受/拒绝全部修订、关闭修订模式并另存后重发”，不创建任务。
  - Web 任务上传同样预检，命中写入 rejected error code，保持与飞书一致；Compare 仍允许既有修订，因为它会先归一化。
- 状态与验证：**已修复并生产发布**。新增 `has_tracked_revisions` 单测和飞书带修订 DOCX 拒绝用例；Feishu 专项 **30 passed**，tasks/API/store 定向 **53 passed**。用户既有任务不回滚，已把其状态卡改为橙色“任务未生成交付文件”，提供“发送报告”，并发送一张“合同未生成交付文件的原因”说明卡（接受/拒绝全部修订后重发）。
- 下一步：用带修订/受保护/正常 DOCX 各一份做生产上传验证；V1 前端 `app.js` 已补 `EXISTING_REVISION_UNSUPPORTED` 中文映射但未发布（生产前端基线仍是 `f4bb2b7`，避免从 dirty 工作区整树发布），V2 任务详情仍显示原始 error_code。
- 变更记录：2026-10-28 新增；由真实生产任务发现，不是隔离测试推测。

## FL-D426 任务已完成但未生成交付文件时，结果卡仍为绿色“任务结果”（2026-10-28）

- 发现日期：2026-10-28，与 FL-D425 同一真实任务。
- 问题与影响：`delivery_counts={'not_generated':1}` 未翻译；`result_card` 只按 `status=completed` 选绿色模板，并提示“可发送交付文件”，但实际没有 final/redline。用户无法区分“处理成功且有文件”与“处理结束但没有交付文件”。
- 处理方法：新增 `not_generated` 中文标签“未生成（需处理）”；结果卡检测 `not_generated>0` 且无 final/redline/working 文件时，标题改为“任务未生成交付文件”、橙色模板，说明常见原因（修订痕迹/受保护/规则不适用），并提供报告按钮；任务列表 detail 增加“未生成 N”。
- 状态与验证：**已修复并生产发布**。真实任务状态卡已更新为“任务未生成交付文件/橙色”，新增卡片单测，Feishu 专项 **30 passed**。
- 下一步：生产再触发一次 not_generated 结果（可用带修订 DOCX 的旧任务或隔离任务）确认卡片文案；不要用颜色代替原因，后续可把 `reason_codes` 透出到任务摘要。
- 变更记录：2026-10-28 新增。

## FL-D427 取消草稿后不返回任务中心，用户无法开始新任务（2026-10-28）

- 发现日期：2026-10-28，用户真实点击“取消”后反馈“不会给我发新的 FundLex 任务中心卡片，导致我没办法开始新的任务”。
- 问题与影响：`_cancel_draft` 原来只发送一条“已取消”文本卡，没有重新发送任务中心。置顶卡虽然仍在，但用户在当前消息流里看不到入口，尤其旧卡被失效后，不知道下一步去哪。
- 处理方法：取消成功后先把草稿输入卡 patch 为失效卡，再调用 `_show_menu` 发送一张新的任务中心卡，并把这张卡设为当前 Pin；卡片说明“本次任务草稿已取消，暂存文件已清理，请重新选择任务”。`switch_task` 取消后直接进入新任务，不额外发菜单，避免重复。
- 状态与验证：**已修复并生产发布**。新增“取消后最后一条消息是任务中心卡、Pin state 指向新卡”用例；Feishu 专项 **32 passed**。已为用户补发一张任务中心卡并更新 Pin（当前 Pin 列表 1）；真实用户点击取消仍需确认新卡位置。
- 下一步：用户点击取消后确认会话底部出现任务中心卡；如果仍看不到，检查 `send_card` 返回和 Pin API 日志（只记录错误类型）。
- 变更记录：2026-10-28 新增；与 FL-D416/420 的常驻入口配套。

## FL-D428 取消命名/改名功能，任务统一按创建时间命名（2026-10-28）

- 发现日期：2026-10-28，用户明确要求“还是不要命名的功能了吧，就按照时间命名吧”。
- 问题与影响：上一版默认用首份文件名、并提供“命名”按钮；用户认为任务命名不是必要功能，名称应稳定、可预期，避免用户维护名称。文件收集卡上的“命名”按钮和 `改名` 文本命令增加认知负担。
- 处理方法：新草稿创建时统一生成 `<任务类型> YYYY-MM-DD HH:MM:SS`（例如 `合同修订 2026-10-28 12:45:30`）；移除文件收集卡/对比卡/指引确认卡的“命名”按钮、`rename_prompt` 回调和 `改名` 文本命令；文件到达后不再修改任务名。旧 `step=name` 草稿和旧表单仅保留兼容。
- 状态与验证：**已修复，工作区 Feishu 专项 31 passed**；时间命名用例覆盖修订/对比，明确断言文件名不会覆盖任务名、卡片无“命名”按钮。生产发布后需再用真实点击确认。
- 下一步：生产发布并重启 Feishu；用户从任务中心新建任务，确认任务名是创建时间且卡片没有命名入口；`我的任务` 中按时间区分任务。
- 变更记录：2026-10-28 新增；取代 FL-D417 中“首文件自动命名/可改名”的部分，FL-D417 的“文件优先”保留。

## FL-D429 外围前后端审查复核与分阶段整改计划（2026-10-28）

- 发现日期：2026-10-28，复核另一 agent 针对 GitHub 默认分支 `codex/fundlex-recall-first`（a2905ac，2026-10-19）的外围审查结论；当前工作区 `codex/semantic-engine-remediation-20261028`（f2e318e）领先 110 个提交且未推送。
- 问题与影响：
  - P0-1 **仍部分成立**：`incomplete` 合同的 `working_redline` 仍可进入修订审查并生成 `selected_final`；API/`publish_selected_artifacts` 没有交付门，`tests/test_revision_api.py` 用 `incomplete` fixture 固化 accept-all 成功。当前分支 ZIP 已把 working/incomplete selected 归入“工作文件（未完成）”，但 V1 下载文件名仍可能显示“最终版（按人工选择）”。
  - P0-2 在默认分支成立（前端两模式、payload 无 mode、后端无 mode）；当前分支已修：`TaskSubmission.mode` 已持久化，前端只保留正式修订。
  - P0-3 **仍成立**：`PARSEABLE_STATUSES` 含 `parsed`，`finish_guide_job` 原地更新同一 version；实测同 id、rules hash `bf77397b…` → `b0e6410c…`，排队任务会 `GUIDE_RULESET_HASH_MISMATCH`。
  - 指引 parse job 连续 release 后 `queued + attempts=3` 不可 claim 也不被标 failed；已用隔离 store 复现。当前 `enqueue_parse` 已复用 active job，但未修 release 预算。
  - `engine_build()` 当前哈希 `fundlex/**/*.py`（129 个文件，含 `api.py`）；修 API/auth 会使排队任务 `ENGINE_SCHEMA_MISMATCH`。当前修复本身也会触发该问题，必须先拆分。
  - 其他确认：分页仍全量+Python 切片+N+1；V1/V2 仍有多条 5 秒轮询；`complete_with_exceptions` 汇总已修；Database repr 已脱敏；上传 500MB 已被 multipart/ASGI guard 缓解；last-admin 无保护；生产注册开放且登录无限流（产品已接受）；HTML 仍宣称 Word 保真；selected/attempt GC 仍不完整；默认分支无 CI，当前 CI push 只覆盖 main/master。
- 已锁定产品决定：当前工作区为基线、完成后再合并默认分支；`incomplete` 人工审查后允许生成选择版但仍按工作文件标注；重新解析采用“新建 V2、V1 不可变”的方案 A；不再提供只读诊断入口；不关闭注册、不加登录限流。
- 处理方法（计划，未完成）：按 `docs/PERIPHERAL_REMEDIATION_PLAN_20261028.md` 分 Phase 0–4 多 agent 实施；Phase 1 先做交付状态机、指引版本/parse job、engine_build 拆分，Phase 2 做分页/轮询/last-admin/GC/文案，Phase 3 前端一致性，Phase 4 全量/迁移/发布/真实 E2E。
- 状态与验证：**计划已保存，代码未完成、未发布**。当前存在 P0-3 未完成 WIP；`tests/test_guide_api.py::test_guide_parse_endpoint_requeues_owner_versions_only` 仍有一条断言未更新。WIP 补丁 `/tmp/opencode/fundlex-outer-remediation-wip-20261028.patch`（sha256 `90831114487dd5690e3d62e8a47f5cfa96ecb0b1751598303ccdaa2d885fd769`）。
- 下一步：用户确认计划；Phase 0 决定 WIP 去留、创建 worktree、登记接口契约；未确认前不继续改代码、不发布。
- 变更记录：2026-10-28 新增。
