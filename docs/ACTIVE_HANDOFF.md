# FundLex 当前断点（ACTIVE_HANDOFF）

> **用户测试语料指令（2026-10-27）**：后续新增测试/评测统一使用 `/home/opencode/fundlex/funds_word/基金合同第一批`。该目录 18 份含修订文件已拒绝全部修订并替换，原件备份在 `funds_word/基金合同第一批_修订原件备份_20261027/`，清理副本/清单在 `funds_word/基金合同第一批_拒绝修订_20261027/`；当前 27/28 `parse_ok`，唯一失败 `广发稳信` 仅受保护且无修订。固定 D01–D20/holdout manifest 不变。业务问题汇总见 [`BUSINESS_ISSUES_FROM_TESTS.md`](BUSINESS_ISSUES_FROM_TESTS.md)。
>
> **章节口径更正（2026-10-28）**：D06 p280 实际位于“第六部分基金份额的申购与赎回”，不在 G06 的“基金的基本情况—份额类别设置”；G06 只覆盖 p130–p137。p280 的 Y 类单向转换不是 G06 业务问题，BIZ-01 已从业务问题清单排除；如要处理应另立规则/业务决定。

## 最新断点（2026-10-28，新需求：带既有修订的DOCX叠加修订，设计已保存）

- 用户新要求：上传件可能带其他部门的Word修订痕迹，需在其上叠加FundLex修订并区分；本轮只要求先思考方案，**未实现、未改行为、未部署**。
- 设计文档：`docs/TRACKED_CHANGES_OVERLAY_DESIGN_20261028.md`；集中记录FL-D446。核心：双视图投影（接受视图供模型、原始视图供写回）、字符级修订上下文、作者/ID区分、嵌套修订优先且不支持时阻断、三向等价校验（接受全部=final、只拒绝我方=对方接受稿、拒绝全部=原始基线）、既有修订清单与报告分离。
- 现状：`inspect_docx` 仍拒绝 `EXISTING_REVISION_UNSUPPORTED`，`_project` 把修订当屏障；`compare/revisions.py` 的接受逻辑可复用为校验参照，但不能直接改写输入。
- 待验证：嵌套ins/del的Word/WPS往返、段落标记修订、同名作者、ID冲突、表格/页眉页脚、已含FundLex修订的幂等。
- 下一步：R1双视图投影+合成fixture，再验证嵌套修订与三向等价，之后接上传/前端与真实带修订合同E2E。预算已不阻塞（FL-D445）。

## 历史断点（2026-10-28，真实模型已开跑；用户取消预算限制）

- **用户授权（2026-10-28）**：“想调模型就调，不用管预算，以后都不要管这预算了”。后续真实模型调用不再受费用/calls cap 阻塞，账本仅作观测；不得再以预算为由暂停或NO-GO。详见FL-D445。仍不泄露密钥、不绕过业务/权限/文件安全。
- 真实弘利运行（第一批原件，独立新账本 `/tmp/opencode/real-smoke-remediation-20261028/ledger.sqlite`）：最新 `hongli5` 为 29 targets / 10 edits / 24 calls / 约$0.0262，`incomplete`。`hongli3`（修复前）46 calls/$0.0466、25 targets/9 edits。两次均为真实模型+真实DOCX，有working_final/redline。
- 真实运行确认并已修：G11:0/G11:1 同一段落两种历史措辞导致 `RECALL_EDIT_OVERLAP` 全部未执行 → 同规则包含式编辑现在吸收为covered（commit `abcf3f0`）。G14:4/G14:5 同段冲突仍在（single/multi类别操作选择问题）。
- 真实运行仍阻断交付的失败（`hongli5`，17 claim failures / 39 unresolved）：G02/G04/G05 satisfied目标仍 `CLAIM_OPERATION_UNPROVEN`（G04目标被site guard标out_of_scope、G05:0无对应批准）；G06/G13/G17 `EFFECT_SITE_UNPROVEN`（旧句确实不存在，需要“无目标”证据路径）；G14 `EFFECT_MISSING/PLANNED_EFFECT_MISSING`、G15 `SPAN_UNAUTHORIZED`、G18 `NOT_PLANNED`。**这些都是真实待修工程项，不是业务待定。**
- 下一步：实现“无目标/已满足”证据路径（用模型判定+scope覆盖证据，而非字面缺失直接PASS）；修G14 single/multi操作选择与G15 span授权；再跑弘利/景宁/QDII，直至真实complete；随后独立标签、全批、发布、用户E2E。预算不再阻塞。
- 本轮提交：`f2e318e`、`2953a87`、`102435a`、`af2acd7`、`e9ce4f6`、`d1f966e`、`c5d5ab5`、`abcf3f0` 及文档提交。项目仍NO-GO，但已进入真实模型迭代。

## 历史断点（2026-10-28，整改已开工：S0–S1完成，S2/S3/S4/S5/S6/S7首批落地）

- 执行分支 `codex/semantic-engine-remediation-20261028`（从 `99a5dad` 带dirty树创建）。**代码未提交Git**：目标文件在本任务前已有约2873行未提交改动，直接提交会混入无关工作；S0基线分离仍待完成。可恢复快照：`/tmp/opencode/semantic-remediation-baseline-20261028-150805/`（tracked/index patch、untracked code tar、合同sha256）与本批代码 `/tmp/opencode/semantic-remediation-slice-20261028-162300/`。
- 新增 `fundlex/semantic_evidence.py`：版本化 `EvidenceRef`（源hash+精确quote+offset+occurrence）、`SemanticApproval`（guide身份/operation/scope/状态机/assessment）、`ApprovalBook`、`CoverageRecord`、`guide_fingerprint`。`Target.approval_id`；`approval_book_for()` 从代码已核验的target确定性生成批准，production与frozen replay一致。
- 语义误拒：`plan_target`/`_plan_target_inner` 在有效批准下不再被另一套site词表二次否决；新增 `approved_span_delete`（模型已选精确句子+代码核验quote/operation/scope时，程序精确删除该span，0模型调用）。真实弘利G17 p784“可用于…”由`TARGET_SOURCE_MISMATCH`变为精确删除该句。
- 范围漏改：`rule_scope.py` 支持同类多叶子；景宁G05现同时含p148/p155（均body），G04仍只取定义叶；费用章节标题接受“基金费用”等词族，销售服务费叶子不再要求固定前缀；copy_key按标题词族生成。
- 证明方向：`effects.py` 无站点+guide字面缺失不再PASS，默认`EFFECT_SITE_UNPROVEN`，需显式覆盖证据；G13/G17同义旧义残留探针；`claim_replay` 重复效果按operation/授权站点收敛。
- 容量/重试：`structure_index` 默认全量（85/85可达）；`compose_variant` delete重试每次attempt独立校验（二次正确不再被首次错误污染）。
- 离线验证：全量 `1871 passed / 13 skipped`（commit `c5d5ab5`）；真实原件探针 `docs/evidence/remediation-probe-20261028.json`（景宁p148+p155、弘利G17 0调用精确删除、G14绑定、85节索引、effect fail-closed），`model_calls=0`。均为离线证据，不是真实模型/生产/用户E2E验收。
- 本轮提交：`f2e318e`、`2953a87`、`102435a`、`af2acd7`、`e9ce4f6`、`d1f966e`、`84d9a73`、`474c608`、`c5d5ab5`、`d51dc34`。未提交的既有frontend/compare/feishu等dirty工作保持原状。
- 第二批（commit `2953a87` 及后续未提交改动）：T3 locator 消费批准（窗口内真实quote+有效批准可越过词袋，越界/伪造/过期仍拒）；候选发现可分页；事实按申购费/销售服务费分别推导；replay/residual 到40返回 truncated/remaining/next_cursor；`ensure_delete_targets` 支持 cursor/page_info 且 pipeline 循环取页；`EFFECT_SITE_UNPROVEN` 等新码归为阻断；有有效批准才允许受控 compose fallback（无批准仍 fail-closed）。
- 第四批（commit `e9ce4f6`、`d1f966e`）：截断的残留扫描计入未完成；`facts_context` 遇超长段落改为跳过并标记，不再屏蔽后续短证据。
- 第三批（commit `102435a`）：确定性执行器无法表达变体时，有有效批准才允许受控 compose fallback（无批准仍fail-closed）；集合枚举接受“现有/设/包括”（仍要求标签集合精确一致）；收费证据识别“实行/适用…%年费率”。
- 未完成：S4独立语义复核/事实依赖进一步拆分；S6 `absent_coverage_by_operation` 接线与完整artifact语义复核；S8真实前端集成；S9独立标签/真实模型评测；S10发布/用户E2E。**真实模型预算阻塞**：FL-D306 记录新预算授权未解决，`p6_run.py` 需冻结protocol+authorization，当前无新cap，未开跑付费批次；不以新账本绕过。
- 下一条动作：继续S4/S6离线实现与回归；真实模型阶段先解决预算授权；S10发布前必须完成S0基线分离与干净候选。

## 历史断点（2026-10-28，用户指定引擎缺陷的多步骤整改方案已保存，待其他模型执行）

- 用户本轮只要求制订保存方案，后续交其他模型执行；明确授权其创建多agent合作开发/测试，中途不询问，自主掌握进度和版本管理，完成端到端交付。用户补充确切对象是已列语义门禁、标题/scope、上限、结构、审计/交付及后续已核实补充缺陷，**不是再做业务分类**。
- 主方案：[`SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md`](SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md)，含R01–R17与S0–S11、统一版本化证据/语义批准/re-quote、scope独立覆盖、事实/恢复/产物证明、分页/结构/前后端、真实评测/生产E2E及Git/预算/回滚门槛。
- 交给下一模型的入口：[`NEXT_AGENT_SEMANTIC_ENGINE_EXECUTION_PROMPT_20261028.md`](NEXT_AGENT_SEMANTIC_ENGINE_EXECUTION_PROMPT_20261028.md)；执行进度表：[`SEMANTIC_ENGINE_REMEDIATION_PROGRESS_20261028.md`](SEMANTIC_ENGINE_REMEDIATION_PROGRESS_20261028.md)。任务从S0起，未开始工程整改，不把本轮规划当完成。
- 约束已明确：规则对应业务范围之外不改；不得用代码漏选范围冒充业务范围；不能信失败转存claimed_operations、移除物理安全边界或降级抹未完成。新增测试用第一批，固定manifest/hash/分母/旧gold不改；第一批历史预测不能冒称新独立留出，来源冲突只追加映射并如实报告。
- 两名只读方案审阅agent均完成，主agent已整合。重要发布陷阱已亲自只读核对：root发布器固定SRC为主工作区且拒绝所有参数，换worktree运行无效；UNITS缺正在active的guide-worker。详见FL-D303补充；生产分叉FL-D382须合并为干净候选后受控发布。
- 当前工作区branch/HEAD仍 `codex/regulation-guide-generation` / `99a5dad27aa68e73362851d136bd0955944707ea`，大量既有dirty保留。本轮新增上述三份文档并更新交接/集中记录/旧入口提示，**无引擎或合同修改、无新真实模型调用/费用、未部署、未重启**。源码/生产/用户E2E依然NO-GO。
- 下一条动作：接续模型读本方案和最新裁定，按AGENTS核对机器/Git/生产，保护tracked差异与相关untracked依赖，建立可恢复任务基线和ownership，再自主并行S1契约与独立回归。未核实当前预算授权不得付费开跑，不能以新账本重置历史额度。

## 历史断点（2026-10-28，用户确认规则对应范围之外不改）

- 用户原话：“不在规则对应的范围之内就不要改”。范围外不改，不为去重额外删除、顺带润色或补写；BIZ-09/10原保留的窄授权问题已决定为不改，不再等待用户拍板。
- 范围依指引和完整条款语义确定，不等同代码当前可能漏选的scope/短切片；合法范围内目标仍须完整处理，不能用本裁定为景宁正文漏改或实际摘要目标排除开脱。D06 p229先核实完整授权条款归属，确认范围外则保留原文。
- 已更新业务目录与FL-D443；本次只记录裁定，未改引擎、合同、gold/manifest或历史report，未调用真实模型/部署。工程整改、独立验证及用户端到端仍待完成。
- 下一动作：后续语义绑定/scope覆盖整改同时验证“规则范围内完整修改、范围外原文保留”，不再提供范围外去重删除选项。

## 历史断点（2026-10-28，待定业务事项逐项原件重核完成；窄授权项已由上方用户裁定关闭）

- 用户要求检查此前待确定事项哪些真是业务问题；主agent＋两名只读agent对照指引原件、实际合同及已有裁定完成核实。结果集中在 [`BUSINESS_ISSUES_FROM_TESTS.md`](BUSINESS_ISSUES_FROM_TESTS.md) 的“最新核实结论”，集中记录FL-D443及FL-D397/398/399/434/356/233补充。
- **撤回笼统业务待定**：G14含转换费率已有指引表述2/3；G18缺旧原因句是替换目标/适用性核对，不应无授权强制新增，也不能假称已满足；D06中性费用差异句已有完整新意；G15旧例10日/新机制5日及自动支付变体已有删除照常＋差异仅提示裁定；实际摘要对应目标分别盘点/关联语义一致是既有要求；QDII/FOF按事实逐规则判、单类别补证及独立标签属于既定工作，不为错误另造业务档或改分母。
- **补充结构证据更正**：D06 p1256原件已有“四、与基金财产管理、运作有关费用的提取、支付方式与比例”，p1269“（三）销售服务费”。p1286 inspection.section_path仍停在“三、基金的收益与分配”是元数据错误，不是真实标题冲突，不能作为排除摘要或再次业务审批依据。该结构/scope缺陷仍未修复。
- **真正保留的窄条件项**：只有确认重复句位于全部授权替换/删除范围之外后，若还要仅为去重额外删除，才需新授权。G11指引46旧条款1本就包含承担句＋C类免收费，47条款2只含承担句，48完整新文含免收费；D06 p228–229必须先做完整逻辑条款语义复核，不能按当前planner切片预判p229必为授权外独立句，也不因本轮审计擅自撤销FL-D233保留措施。
- 另提“无对应旧句也强制新增G18”、按QDII/FOF整体豁免、新期限或改冻结门槛/分母才是范围/政策变更，当前未提出，不包装成必须用户先回答的阻塞。
- 本轮仅阅读原件/历史证据、更新文档；**未改引擎、合同、历史report、gold或固定manifest；未调用真实模型，新增费用0，未部署**。两名只读agent均完成，无本轮运行任务。分支/HEAD仍 `codex/regulation-guide-generation` / `99a5dad27aa68e73362851d136bd0955944707ea`，保留全部既有dirty工作。项目仍NO-GO，业务归因更正不代表工程修复/验收完成。
- 下一动作：按已明确指引和裁定实现统一语义批准/完整条款绑定、scope覆盖/摘要关系与无目标义务闭环；优先处理G14匹配、景宁正文漏改、弘利G17误拒及G18无目标，不再把这些工作等同等用户拍板。

## 最新断点（2026-10-28，严格性审计完成，撤回部分业务归因/完成结论）

- 当前用户任务：核实此前所有“限制过严”的说法并继续找遗漏，不是授权直接删安全门禁。审计已完成，**未实施本轮引擎整改、未部署、未调用真实模型**。
- 结果见 [`STRICTNESS_DESIGN_AUDIT_20261028.md`](STRICTNESS_DESIGN_AUDIT_20261028.md)；证据 `docs/evidence/strictness-audit-20261028.json`；复跑 `.venv/bin/python tools/evaluation/strictness_audit_20261028.py --output docs/evidence/strictness-audit-20261028.json`。包含真实原件/历史产物复核、9项scope/事实探针、容量/结构探针、脚本模型门禁探针、28份第一批只读上下文检查，源码/样本SHA随证据保存。
- **必须更正**：G14“转换费率”本就在指引表述2/3，BIZ-02不是业务待定。原件零基段59–66及guide G14:1/4、:2/5已覆盖；QDII p263只是重复“基金”，属代码匹配/绑定问题。此前工作区已有局部归一化尝试，**不等于统一SemanticMatch/requote/语义仲裁方案已实施或真实验收**。
- **真实漏改（FL-D439）**：景宁p155是body正文、与p148同章，非摘要。G05 scope只选第一个叶子，实际final p148已改，p155仍有旧费率及备案句，历史report却complete/Claim verified/遗漏PASS。撤回此前“景宁可交付、三份只剩QDII业务问题”的结论；历史report不改。独立查漏与scope共用同一漏选范围，存在自证通过。
- **真实误拒（更新FL-D394）**：弘利p784“销售服务费可用于……”在G17 scope内，精确quote/合法operation归属通过，site词表仍在模型调用前硬拒。另确认registry禁止部分失败executor升级、T3比初次归属更严、G11模板接受/Replay拒同一源文、模型review前保护词/固定文字否决、事实语法及依赖耦合、删除重试旧错误残留（FL-D442）。详见FL-D106/120/140/440。
- 容量/结构更正（FL-D441）：普通表格可读可写、full参数非摘要/全文、32k/4k可配置且已有拆窗；80节索引/12候选/20删除/40失败仍有局部截断和缺少分页问题。composite不得跨无关非空段/不同section属于应保留的物理安全边界。第一批27份可解析合同在28500字符探针下未丢所检索的正文销售服务费段，不虚报潜在上下文缺陷已影响全批。
- 验证：主agent持久探针重跑成功；定向离线测试 **95 passed**（含8项子agent行为复现），不替代修复/全量/业务验收。预算：真实模型新增调用0、费用0；两名审计子agent均完成，无本轮运行中的服务/脚本任务。
- branch/HEAD：`codex/regulation-guide-generation` / `99a5dad27aa68e73362851d136bd0955944707ea`；工作区仍大量dirty，不reset/覆盖其他工作。本轮新增审计脚本、报告、JSON，修改集中记录/业务文档/本断点；没有新增引擎源码变更。项目继续 **NO-GO**。
- 下一动作：按审计P0将“语义批准→精确绑定→规划→Replay”建立统一契约，并让独立scope覆盖检查能提出合法第二叶子；优先修景宁正文漏改、弘利用途句误拒、G14绑定与G11证明分歧，随后处理事实仲裁和分页。不得只加G14“基金”正则、信任失败转存的claimed_operations、或跳过Claim Replay制造complete。

## 最新断点（2026-10-28，Compare 修订版输入已提交并生产发布）

- 目标：Compare 上传带 Word 修订痕迹的 DOCX 时自动接受既有修订，原始文件不覆盖，审计字段与清理后对象绑定。
- 代码：创建分支 `codex/compare-tracked-revisions`（基于生产 Compare 后端基线 `f4bb2b7`），提交 `019a1cf`（新增 `fundlex/compare/revisions.py`、`ingest.py`，修改 API/store/docx 与测试）和 `a86f238`（发布记录）；已推送 `origin`。
- 生产：受控逐文件发布 `revisions.py`（新增）、`docx.py`、`compare/store.py` 与生产 `compare/api.py` 上传补丁；生产原有 `compare/ingest.py` 与发布版本同哈希。重启 `fundlex-recall-api`/`fundlex-compare-worker`/`fundlex-feishu`，均 active、capabilities 200；`compare_pair_files` 新增 4 个审计字段。发布前代码备份 `code-before/`、DB 备份 `db-before.sql.gz`、部署 SHA 均在 `/tmp/opencode/fundlex-compare-revisions-20261028/`。
- 真实验证：修订原件 208 处，原始 `bbe61101...`/138,515 字节，清理后 `80f72ef8...`/129,391 字节，45 处差异，view 双侧正常，未授权 401/403，原始字节未改；证据 `/tmp/opencode/fundlex-compare-revisions-e2e-20261028/production-e2e.json`。候选树既有 Compare 48 passed、新增修订测试 35 passed。
- 边界：生产 V1 `frontend/compare.js` 未显示“已自动接受 N 处”提示；飞书 Compare 复用同一 `ingest` 且服务已重启，但未做飞书端真实上传 E2E；交付引擎（Recall-first）仍要求上传前接受/拒绝全部修订，本次不改其策略。
- Compare 选择版生产 API 小样本 E2E（2026-10-28）：两处**分离**修改段可逐项采用左右并生成 `selected_final`/`selected_redline`/选择报告 JSON/Markdown；实测第一处采用右侧、第二处保持左侧，final 文本正确、修订版 1 处 `w:ins` + 1 处 `w:del`、final 无残留修订。**连续两个修改段的 FL-D441 已修复并生产验证**：分支 `codex/compare-selection-group-fix` 提交 `426892d`，生产 `selection_writer.py` SHA `53c6cfd1...`；连续修改混合选择 final `0.30%`/`0.10%`、修订 1+1，全部采用右侧 final `0.30%`/`0.08%`、修订 2+2，四类产物均下载成功，证据 `/tmp/opencode/fundlex-compare-selection-e2e-20261028/`。临时账号/任务/对象已清理。随后完成真实合同路径：1,417 段 ESG 合同、两处连续修改、header/footer 覆盖警告，修复 FL-D442 后全部采用右侧生成成功（final p831/p832 `1.00%`、段落数与页眉保持、redline 2+2、final 无残留修订、报告列出 header/footer 例外）；生产浏览器登录→上传→全部采用 B→保存→预览→生成→下载 final/redline 全链路通过，1440 视口 0 页面/控制台错误。Compare 全套 **106 passed / 6 skipped**。空侧 insert/delete、跨段、合并单元格仍按设计阻断。
- 工作区仍 dirty（大量既有修改未提交）；本任务只提交/推送上述独立分支，未改动主工作区 HEAD，未整树发布。集中记录 FL-D371 已更新。

## 最新断点（2026-10-28，RuleScope 统一作用域 + D06 真 complete）

- 目标：消除“规则找到不该找的章节/段落”这类错配，不再为 G06 等单条规则加特判。已把物理叶子小节作用域做成一等公民：新增 `fundlex/rule_scope.py`（`LeafSection`/`RuleScope`/`resolve_rule_scopes`），inventory、survey、append recovery、semantic delete、sweep、audit、coverage、规划前门禁、Claim Replay、effect proof、delete residual 全部使用同一 scope；越界记录 `OUT_OF_RULE_SCOPE`，规划目标带 `scope_id`，无 scope/越界失败关闭。方案见 [`RULE_SCOPE_ARCHITECTURE_REMEDIATION_PLAN_20261028.md`](RULE_SCOPE_ARCHITECTURE_REMEDIATION_PLAN_20261028.md)。
- D06 真实链路 `/tmp/opencode/d06-rule-scope3-20261028`：**真 complete**，39 targets / 15 edits / 27 calls / 约 `$0.0295`，`artifact_claim_replay.verified=true`，`open_obligations=0`，`final_omission_review.status=PASS`，final/redline 哈希 `2eed1752...` / `72c2fcb3...`。p230 G12+G13 只写一次“赎回费用全额计入基金财产”，7 日旧句已删除。
- scope 审计：G06 仅 p130–p137，`sweep:OUT_OF_RULE_SCOPE:G06:p280`；G15–G17 摘要 p1286–p1289 默认排除；G19–G22 的 p982“对基金财产进行分配。”引导句被 `inventory:OUT_OF_RULE_SCOPE` 丢弃；景宁 G04 p148 不再作为类别定义，p151 为完整 basics 定义，p120 仅在无 basics 定义时使用。无模型 scope 审计与真实报告一致。
- 两个非 scope 通用缺陷同批修复：FL-D436 G12 相邻 ONE_OF 历史措辞被拼接成重复整句（`merge_edits` 现吸收等价替代、不同政策失败关闭）；FL-D437 review_assisted 假 complete（Claim Replay 失败、证明型 final omission、含 `CLAIM_` 证据的 open obligation 一律阻断；审计未完成/sweep 上限/事实未核验仍为人工复核或业务待定）。
- 回归：全量 **1803 passed / 13 skipped**（120 个测试文件分两批跑完）；`tests/test_rule_scope.py` 覆盖 D06/QDII/景宁真实 scope，`tests/test_rule_scope_integration.py` 覆盖 gate/sweep/delete/Claim Replay；新增 G12 相邻替代、交付门禁、QDII 类前缀费用标题、景宁 G03 scope 回归。
- 第一批 3 份 smoke5 `/tmp/opencode/first-batch-smoke5-20261028`（新账本，240 calls / $1.00 上限）：价值优选 `complete`；QDII 全球稳健 `incomplete`；景宁纯债 `incomplete`。两份失败的 scope/恢复缺陷已由 FL-D432/FL-D433 修复：QDII 类前缀费用标题现解析到 `S17:L04`（p969–p971，排除摘要 p1151）；景宁 G03 改用 p151 完整类别定义，缺失操作恢复受 RuleScope 约束。用 `/tmp/opencode/smoke5-fix-20261028` 新账本重跑两份：**景宁纯债 `complete`**（36 targets / 15 edits / 26 calls / 约 `$0.0267`，Claim Replay verified、open 0、final omission PASS）；**QDII 仍 `incomplete`，但只剩 G14:3/4/5（“转换费率”，BIZ-02）和 G18（缺少旧 A/C 表述，BIZ-03）4 个业务适用性 open obligation**，G15/G16/G17 已 `ARTIFACT_VERIFIED`（p969/p970 实际修改），不再有 `RULE_SCOPE_UNRESOLVED`。价值优选也在同一最终代码上用新账本复跑 `/tmp/opencode/smoke5-fix-value-20261028`：**`complete`**（31 targets / 15 edits / 27 calls / 约 `$0.0266`）。因此同一最终代码下三份代表性样本为 **2 份可交付（价值优选、景宁）、1 份待业务决定（QDII G14/G18）**，不是 3/3。
- 未完成/边界：未建独立 labels/gold，未做固定 D01–D20/holdout 重跑、候选冻结或生产部署；业务待定仍为 BIZ-02（G14 转换费率）、BIZ-03/04（G18 QDII/中性句）、BIZ-06（G15 5 vs 10 工作日）、BIZ-07（G15–G17 摘要副本是否必须同步）、BIZ-09（G11 C/E/F 重复）。项目整体仍 **NO-GO**。
- 工作区仍 dirty，分支 `codex/regulation-guide-generation`，HEAD `99a5dad`；RuleScope/Claim Replay/G12/门禁修改未 commit、未 push。

## 最新断点（2026-10-28，飞书多任务卡片已生产发布）

- 用户确认扩展飞书：合同对比、法规指引生成、任务查询/结果回传、只读诊断/评测。已确认口径：指引生成对全部绑定用户开放；只读诊断跑完整修订流程但只回报告。
- 已实施（FL-D400；方案见 [`FEISHU_MULTI_TASK_INTEGRATION_PLAN.md`](FEISHU_MULTI_TASK_INTEGRATION_PLAN.md)）：
  - 任务中心卡与文本命令；`feishu_drafts` 增加 `task_type/step/metadata_json/target_id`，草稿文件增加 `side/kind/pair_index/revisions_accepted`，`task_channels` 增加 `task_type/last_external_status/last_progress_json`。
  - Compare 双文件草稿、交换/替换/确认、CompareStore 创建/上传/封存、状态卡和 `#compare?mode=detail&id=` 深链。
  - 法规 PDF/DOCX 接收、`create_guide_run` 共享 helper、run 状态卡和 `#generation?mode=detail&id=` 深链；新增 `fundlex-guide-worker.service.template`。
  - 我的任务聚合卡；完成卡发送 final/redline/report、对比 JSON、指引草案/证据；`FeishuClient.send_file`。
  - `tasks.mode` / `batches.mode` 贯通；诊断仅发布报告（`diagnosed`），评测发布 `evaluation_final/evaluation_redline`；`validate_delivery`/`finish`/`get_artifact` 增加对应门禁。
- 验证：完整 Python 回归 **1754 passed / 58 skipped / 3 warnings / 501.51s**；Feishu 专项 **19 passed**、tasks API **30 passed**；V1/V2 浏览器 **44 passed**，指引生成浏览器 **1 passed**；前端 typecheck/lint/Vitest **14 passed**/build 通过；`compileall`、`node --check`、`git diff --check` 通过。未调用真实模型创建新任务；已完成生产 Feishu Compare/卡片/文件回传/深链 E2E，指引真实 model run 和诊断/评测真实 E2E 未做。
- 生产发布已完成（2026-10-28，受控逐文件发布）：`fundlex-recall-api/worker/compare-worker/feishu/guide-worker` 均 active；生产 16 个候选文件 SHA 与 `/tmp/opencode/fundlex-candidate-20261028` 一致。代码备份 `/tmp/opencode/fundlex-code-before-20261028.tgz`，DB 备份 `/tmp/opencode/fundlex-db-before-20261028.sql.gz`，逐文件回滚备份 `/tmp/opencode/fundlex-deploy-individual-20261028/`、`/tmp/opencode/fundlex-deploy-fileux-20261028/`；部署 SHA 清单 `/tmp/opencode/fundlex-feishu-multitask-20261028/deployed-sha256.txt`。
- 生产真实 Feishu E2E：任务中心卡和任务名称表单卡发送/提交/更新成功；Compare 任务 `4858ac14f16144309d70462ef5eb7b72` 用两份公开 DOCX 完成，621 处差异、coverage incomplete，状态卡、报告文件回传（`im:resource`）和 `#compare?mode=detail&id=` 浏览器深链通过（1440，页面/控制台错误 0；截图 `/tmp/opencode/feishu-compare-deeplink-20261028.png`）；既有修订任务报告文件回传成功；指引 PDF 上传、确认卡、取消通过，未确认/未启动真实 model run。诊断/评测仅隔离测试；任务名可在卡片填写，文件仍以消息发送（飞书卡片无文件上传组件）；文件卡支持移除/替换、SHA 去重、错误提示，取消/提交后清理暂存。网页与飞书均取消单批 20 个文件限制。卡片按钮使用 2.0 `behaviors.type=callback` 和 `config.update_multi=true`；真实用户点击回调尚未由人工点击验证，已用等价回调事件验证 handler。
- 生产问题已修复：表单提交按钮 name 非固定值导致任务名保存无响应（FL-D407）；任务中心卡已 Pin 置顶作为常驻入口（FL-D416）；任务按钮后续卡片改为新消息，避免只看到 toast（FL-D415）；卡片 2.0 `action` 模块改为 `column_set`（FL-D401）；guide worker 改用 `-m fundlex.guide_generation.worker`（FL-D402）；Feishu 迁移并发 ALTER 加幂等保护（FL-D403）；飞书应用增加 `im:resource` 并发布版本（FL-D404）。
- 2026-10-28 飞书交互按产品/UX 复核重构（FL-D417–FL-D424）：改为**文件优先**（取消必经的任务名称表单，任务名按创建时间生成，不再提供命名/改名入口）；旧卡自动失效；绑定自动 Pin 并持久化；任务列表真实分页；卡片回调 2 秒超时保护；状态/阶段/错误/文件大小中文化；结果卡“发送全部交付”；Compare 卡不再要求先开工作台。飞书产品/UX 复核与目标流程见 [`FEISHU_UX_REVIEW_20261028.md`](FEISHU_UX_REVIEW_20261028.md)。Feishu 专项 **31 passed**（时间命名、取消后重发任务中心），tasks/API/store 定向 **53 passed**，完整 Python 回归 **1801 passed / 58 skipped / 3 warnings / 575.85s**；已受控发布 `fundlex-feishu`（cards/service/events/client/store）、`upload_validation.py` 和 `api.py` 并重启 Feishu/API，Pin 列表仍为 1。发布前备份与 SHA 清单：`/tmp/opencode/fundlex-deploy-feishu-ux-20261028/`、`/tmp/opencode/fundlex-feishu-ux-20261028/deployed-sha256.txt`。生产 health 当前 pending/outbox 0、Pin 1；取消草稿现在会重发任务中心并更新 Pin（FL-D427）；任务名改为创建时间，命名/改名入口已移除（FL-D428）；`integration_events` 有 9 条历史 dead（均为 2026-10-28 早些时候 E2E/旧代码 `RuntimeError`，非本轮新增，未清理）。
- 2026-10-28 生产真实发现（FL-D425/426）：用户任务 `3569d09b59f84851bd3253496e7cd375` 的合同带有未处理修订痕迹，引擎返回 `EXISTING_REVISION_UNSUPPORTED`，任务 `completed` 但 `delivery_counts={'not_generated':1}`，飞书旧卡显示绿色“任务结果”。已补上传前修订预检（飞书+Web，Compare 仍允许），并把该任务卡更新为橙色“任务未生成交付文件”，说明原因并提供“发送报告”；`not_generated` 增加中文标签。
- 未完成：真实用户从置顶卡用一份**无修订痕迹**的 DOCX 完成“发送文件 → 确认 → Worker → 最终版/修订版/报告回传”全链路；指引生成真实 model run（预算/耗时未授权）、诊断/评测真实 model E2E、MySQL 8 并发 outbox/状态卡压测、真实用户逐类型点击验收；V2 前端修订错误码中文映射、生产 V1 `app.js` 映射发布；工作区仍 dirty，分支 `codex/regulation-guide-generation`，HEAD `99a5dad`，未 commit/push。项目整体仍 **NO-GO**。

## 最新断点（2026-10-27，第一批清理样本 3 份真实 smoke）

- 用清理后的 `基金合同第一批` 选 3 份代表性合同（价值优选、景宁纯债、全球稳健 QDII）走真实模型/当前管线；最新目录 `/tmp/opencode/first-batch-smoke4-20261027`，新账本，240 calls / $1.00 上限。smoke3 曾为 1/3 complete；smoke4 在 G04 scope/G05 审计修复后仍 **0/3 complete**，说明模型/窗口变化会暴露新的副本与无操作站点问题。
- FL-D381 已修复：TOC bookmark 不再只读、`lastRenderedPageBreak`/`proofErr` 不再切段，writer 支持单文本 run 带良性标记；聚焦套件 **372 passed**。G04 已补入释义中的类别定义 section；G05 已用审计证据覆盖自相矛盾的 incomplete verdict。
- smoke4 剩余：价值优选 G15 p1258 摘要片段 `TARGET_SOURCE_MISMATCH`，最终仍残留“销售服务费每日计提，按月支付。”；QDII G05 p1331 已满足、p481 无目标，Claim Replay 报 `CLAIM_OPERATION_NOT_PLANNED`；QDII G14/G18 仍是业务措辞/适用性；景宁 G04 p148 被模型判 satisfied/no replacement，但无站点证明，最终 `verified site missing`。
- 这些剩余项登记为 FL-D384：重复摘要副本覆盖、短片段绑定、no-op 站点证明，另有 G14/G18 业务决定。不能把 372 项离线回归或 G04/G05 两项修复当成整批通过。
- G16 append 站点修复（FL-D391）已验证：7 份“只差 G16”的定向 smoke **6 complete / 1 incomplete**，202 calls / 约 `$0.2310`；ESG、品质优选、恒昌、恒阳、恒隆、招利通过，恒裕剩 G17 p888 残句/G15 `LEDGER_EVIDENCE_UNBOUND`。聚焦套件 **385 passed**。按最新一次运行，24 份中 10 份 complete（4 原有 + 6 个 G16 簇），恒裕等 14 份仍 incomplete；3 份 smoke4 仍 0。
- 2026-10-28 又修 5 个代码缺口（均未跑真实批次，只做了真实 report/artifact 离线复算）：FL-D392 absent 目标压制删除目标（恒裕 G17 p888）；FL-D393 ASCII 引号 orphan evidence（恒裕 G15 SW002）；FL-D394 G17 单句用途条款整段删除（生物科技/美国房地产/道琼斯等 5 份）；FL-D395 G05 协调费率列表已满足证明（QDII p1331）；FL-D396 G02/G04 已满足定义站点（景宁 p148→p151）。聚焦回归当前 **418 passed**（1 个与本次无关的 Feishu `status_card` ImportError 被 deselect）。
- 2026-10-28 交付策略改为 **review_assisted**（FL-D408）：未证明站点/审计缺口/查漏缺口/orphan evidence 降级为人工复核清单，不再阻断交付；旧句残留、编辑未生效、写入/模型失败仍阻断；事实未核验/适用性未知与 G14/G18 一起归入业务待定，不自动修改。`FUNDLEX_DELIVERY_POLICY=strict` 可恢复旧行为。
- 2026-10-28 重写逐份 `report.md`（FL-D409）：逐处列出规则标题、位置、操作、指引要求、修改前原文、修改后原文、Claim Replay 证明状态；另有“已符合、无需修改”“业务待定”“阻断项”“人工复核清单”章节。
- 业务待定（旧口径，已被下方 2026-10-28 结果替代）：FL-D397/398/399。
- 历史（2026-10-27，已被下方 2026-10-28 结果替代）：27 份可解析样本已全部跑过（3 份 smoke4 + 24 份 remaining），当时观察约 **10/27 complete**，但这是不同真实运行的逐份状态，不是正式准确率；未建立独立 labels/gold、未做 candidate freeze 或生产部署，项目继续 **NO-GO**。
- 2026-10-28 全量 28 份真实批次（`/tmp/opencode/first-batch-full-20261028`，801 calls / 约 `$0.9275`）：严格口径 **14 complete / 13 incomplete / 1 not_generated（受保护）**；按 review_assisted 离线重分类 **23 complete / 4 incomplete / 1 not_generated**。仍 incomplete：QDII 全球稳健（G12 p260 旧句残留）、纳斯达克生物科技/美国房地产/道琼斯石油（各 2 处旧句残留）。重分类报告在 `reclassified/<合同>/report.md`。
- 2026-10-28 新链路 3 份 smoke（价值优选、QDII、景宁，`/tmp/opencode/new-policy-smoke-20261028`，82 calls / 约 `$0.0948`）：**3/3 complete**，report.md 含“逐处修改/已符合/业务待定/阻断项/人工复核”五节，逐处有指引要求与修改前后原文；QDII 的 G14/G18 进入业务待定，景宁 G04 已满足定义站点闭合。
- 2026-10-28 最终代码全量 v2（`/tmp/opencode/first-batch-v2-20261028`，827 calls / 约 `$0.9553`）：**23 complete / 4 incomplete / 1 not_generated（受保护）**，与 v1 重分类一致。4 份 incomplete 均为真实旧句残留：QDII 全球稳健 G12 p260（已由 FL-D410 修复，单跑后 complete）、纳斯达克生物科技/美国房地产/道琼斯石油各 2 处 G17 残句（facts 未核验→G16 未追加→G17 保护性阻断）。
- 2026-10-28 再修 3 个 QDII 缺口：FL-D411（多币种类别事实核验：币种后缀/封顶申购费率/方括号净值费率/基础类别归并）、FL-D412（G04 scope 不再重复编辑 G02 的释义定义）、FL-D413（claim-site 修复目标必须落在规则 scope 内）。三份原 incomplete 单跑均 **complete**（纳斯达克/美国房地产/道琼斯），聚焦套件 **443 passed**、fee evidence **87 passed**。
- 2026-10-28 v3 全量 28 份（`/tmp/opencode/first-batch-v3-20261028`，817 calls / 约 `$0.9284`）：**25 complete / 2 incomplete / 1 受保护**。2 份回归：品质优选 G12/G13 在 p231 `RECALL_EDIT_OVERLAP`（G12 短持有期扩展覆盖了 G13 句子）、弘利 G11:0/G11:1 在 p218 重叠。修复后再发布。
- 2026-10-28 生产任务 `96779cbd...` 4 份全部 `not_generated`：ESG/富信 FOF 为 `EXISTING_REVISION_UNSUPPORTED`（文件含修订痕迹），港股通/道琼斯为旧引擎 `RECALL_TARGET_STRUCTURE`。生产 `/opt/fundlex-recall-first` 仍是 10-26 构建，缺 FL-D391..413 与 review_assisted；API 重启未更新代码。
- 2026-10-28 FL-D414：新增统一 `failure_reason()`，文件/目标/重叠/模型/版本/残留/claim/audit/coverage 等失败场景都有简要中文原因；report.md 头部显示“失败原因”，user_summary 对 not_generated 显示“未生成修改文件：<原因>”。旧部署任务不会自动获得该提示。
- 2026-10-28 磁盘清理（用户授权“可安全释放的删掉”）：杀掉残留 headless Chrome（释放 325MB 已删除文件）、`journalctl --vacuum-size=50M`（136MB）、logrotate messages（约 58MB）、`git gc`（32MB）、删除 `frontend/node_modules`（285MB，构建前需 `npm ci`）。根分区可用从约 **586MB 提升到约 1.5GB**。
- 2026-10-28 快照压缩归档（用户 2026-10-28 授权）：保留 `snapshot-20` 完整树与 `data*/target*/ledger`，其余 21 个 snapshot 生成差异补丁（`patches/*.patch` + `*.tree.sha256`，共 14MB）后删除整树拷贝；删除前逐一 dry-run，`snapshot-03` 完整重建 diff=0，`snapshot-19` 删除后重建哈希完全一致。`operation-validation-20261024` 从 **5.6GB 降到 830MB**，根分区可用提升到 **6.2GB**。记录见 `docs/evidence/operation-validation-20261024-compaction-20261028.md`。
- 未动：playwright 缓存 681MB、旧评测 494MB、`docs/evidence` 172MB、MySQL 907MB。
- 2026-10-28 第二轮清理（用户“继续检查”）：删除 `/tmp/gg-pipe-*`（91MB 测试运行库）、`fundlex-no-dist-qa`（125MB）、`dnf clean all`（213MB）、`npm cache clean`（60MB）、6 个 worktree 的 `frontend/node_modules`（994MB）。根分区可用提升到 **7.7GB（80%）**。两个有未提交改动的 worktree（`fix-compare`、`incomplete-engine`）已把 diff 保存到 `docs/evidence/worktree-diffs-20261028/`（52KB）。
- 2026-10-28 worktree 清理（用户确认）：删除 21 个无会话/干净 worktree（18 个在 `~/.local/share/opencode/worktree`，3 个在 `/home/opencode/fundlex-*`），保留 5 个（`full-stack-test-environment`、`fix-d292`、`fix-d294` 有会话；`fix-compare`、`incomplete-engine` 有未提交改动）及生产基线 `fundlex-prod-f4bb2b7`。删除前为 21 个 HEAD 建立 `refs/worktree-archive/*`（commit 仍可达），两个 dirty worktree 的 diff 已存 `docs/evidence/worktree-diffs-20261028/`。worktree 目录 6.0GB → 1.3GB，根分区可用 **7.7GB → 13GB（66%）**。另 prune 了 2 个指向旧 Windows 机器的失效 worktree 条目。
- 业务待定：FL-D397（G15 2023 自动划付式支付条款变体，当前模型显式命中即删除，需确认）、FL-D398（QDII/FOF/指数/养老目标合同适用档与验收分母）、FL-D399（G14 多“转换费率”、G18 QDII 适用性）。
- 历史（2026-10-27）：24 份未测可解析合同批次已完成，目录 `/tmp/opencode/first-batch-remaining-20261027`，新账本，实际 **772 calls / 约 `$0.9016`**，77 分钟；**4 complete / 20 incomplete**，12 次失败请求（含 429/schema）。通过：广发富信优选 FOF、广发沪深300指数增强、广发沪港深精选、广发聚安混合；其余 20 份 incomplete。连同刚才 3 份 smoke4 的 0 complete，当前代码在这 27 份中合计仅 **4 份 complete**。
- 24 份批次未闭合规则计数：G17 62、G14 60、G16 52、G02 33、G04 33、G05 27、G22 26、G11 25、G01 19、G03 18、G09 17、G15 16 等；unresolved code 以 `OPEN_OBLIGATION` 139、`FINAL_COVERAGE_UNRESOLVED` 136、`FINAL_OPERATION_UNPROVEN` 46、`LEDGER_EVIDENCE_UNBOUND` 40、`FINAL_MODEL_SWEEP_FINDING` 21 为主。证据汇总 `/tmp/opencode/first-batch-remaining-20261027/batch-analysis.json`。这是管线 smoke，不是有独立 labels 的正式评测；不能当准确率或整批通过。

## 最新断点（2026-10-27，V1 Compare 可调双栏已生产发布）

- 当前仍在 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`；工作区继续 dirty，包含既有并行修改和 Compare 可调双栏修改，未 reset、未 checkout、未 commit。
- **生产前端基线是 `f4bb2b7`，不是当前工作区 HEAD**：生产 `workspace.js`/`compare.html`/`compare.js`/`compare.css`/`app.js`/`app.css` 与 `f4bb2b7` 完全一致；工作区 `compare.html`/`compare.js`/`compare.css` 是另一套较早实现。整树 `publish_workspace.sh` 会回退生产 UI，禁止从当前 dirty 工作区直接执行，详见 FL-D382。
- 已按用户要求覆盖默认 V1 与 React V2：V2 使用 `antd@^6.6.8` 的 `antd/es/splitter`；V1 使用原生可聚焦分隔条，支持指针拖动、方向键、Shift 加速、Home/End、Enter/Space 或双击恢复 50/50，比例持久化并同步 A/B 栏头。V1 拖动期间只移动 `#compare-split-preview` 预览线，松手才一次性应用宽度并重绘 SVG；差异标记 Map 缓存，≤760px 均保留单栏切换。V1 差异栏已收窄为 `200–240px`，批量/单项按钮改为“全部采用 A/B”“采用 A/B”；V2 差异栏为 `220–280px`。
- V2 工作区验证：`npm run typecheck`、`npm run lint`、Vitest **14 passed**、`npm run build` 通过（主包 410.28 kB，Compare 分包 117.49 kB）；完整工作区浏览器套件 **45 passed / 117.53s**；差异栏收窄后 V2 Compare 浏览器用例 **1 passed**。
- V1 生产发布：在 detached `f4bb2b7` worktree `/tmp/opencode/fundlex-prod-f4bb2b7` 上仅移植 V1 Splitter；生产同源 Compare 选择版浏览器套件 **14 passed**（含临时拖动/键盘/复位验证和紧凑栏检查）。首次发布备份 `/tmp/opencode/fundlex-compare-splitter-20261027/`；性能优化前版本备份 `/tmp/opencode/fundlex-compare-splitter-lazy-20261027/`；紧凑栏前版本备份 `/tmp/opencode/fundlex-compare-compact-20261027/`；仅替换生产 `frontend/compare.html`、`compare.css`、`compare.js` 并重启 `fundlex-recall-api`。当前哈希：`compare.html` `18b5924c...`、`compare.css` `13c211d4...`、`compare.js` `22bb6be8...`；API active、capabilities 200，公网首页 200、资源版本 `adb3032a1052f46f`，1440/390 无页面错误/控制台错误/404，1440 分隔条可见、差异栏实测 230.39px，390 分隔条隐藏。
- 拖动性能：1200 处差异基准优化前 `longCount=2`/`longMax=65ms`/平均帧 21.10ms；改为预览线 + 松手应用 + 缓存标记后拖动期间 `longCount=0`/`longMax=0`/平均帧 16.84ms，详见 FL-D383。
- 未发布：React V2、`frontend/dist`、antd 依赖、工作区其他 dirty 引擎/法规/前端修改。未创建真实合同任务、未调用真实模型。项目整体继续 **NO-GO**。
- 已知限制：V1 拖动时显示预览线，栏宽在松手后应用，以保证长合同 60fps；V2 antd 拖拽条当前没有 tabIndex，键盘用户不能直接调整，V2 栏头仍按固定中缝布局，拖动后与面板边界有轻微偏差。
- 下一条动作：下次正式候选发布前先合并/重建唯一 clean candidate，解决 FL-D382 的 `f4bb2b7` 与工作区分叉；如需 V2 完整键盘可调，补外层可聚焦重置/键盘入口。定向发布不能替代完整候选、真实用户路径或 D01–D20/holdout 验收。

## 最新断点（2026-10-27，D06 隔离正式工作台与浏览器用户路径通过）

- 当前仍在 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`，工作区保留既有 dirty 修改；未 reset、未 checkout、未部署。当前 guide 文件 SHA `20bc6677...`、`document_sha256=7b68793d...`，22 条规则/34 个操作。根分区约 1.3 GB 可用；Chromium 已安装，Worker 256 MB 保留阈值仍满足。
- **用户测试语料指令（2026-10-27）**：后续新增测试/评测统一使用 `/home/opencode/fundlex/funds_word/基金合同第一批` 中的样本；`tools/evaluation/sample_corpus.py`、`recall_run.py`、`sample_corpus_audit.py` 已默认该目录。固定 D01–D20 与既有 holdout manifest 保持原路径、哈希和分母不变。当前目录 28 份：18 份含修订文件已拒绝全部修订并替换，原件备份在 `funds_word/基金合同第一批_修订原件备份_20261027`，清理副本与清单在 `funds_word/基金合同第一批_拒绝修订_20261027`；当前 27 份 `parse_ok`，1 份 `广发稳信...` 仅受保护且无修订。解析拒绝样本不静默修复、不转换、不计入真实修改分母。
- 隔离正式 API/Worker 路径 `/tmp/opencode/d06-delivery-real-20261027b` 通过：密码登录、guide 绑定、上传、持久任务、真实 Worker/模型、final/redline、报告/Claim Replay、下载、修订选择和授权检查。27 HTTP / 约 `$0.03283635`，`delivery_status=complete`、19 edits、0 unresolved、Claim Replay verified（19/22）、gate 0 open、final SHA `387759e0...`、redline SHA `1ab117a2...`；19 个段落变化、19 条修订、未授权 401、跨用户 404。
- 隔离真实浏览器 V1 路径 `/tmp/opencode/d06-browser-real-20261027b` 通过：注册登录、指引页、上传、真实 Worker/模型、结果详情页、final/redline/report 下载。任务/文档 `complete`、49 targets/0 unresolved、Claim Replay verified、最终遗漏 PASS、19 个段落变化、final SHA `0b25951e...`、redline SHA `d52faf32...`；结果页显示“可直接使用/已通过交付校验/最终版 DOCX/修订版 DOCX”，未授权下载 401。独立 `browser-verification.json` 的 12 项检查全部通过。
- 首轮浏览器运行曾因 FL-D378 失败：G09 `SW004` 引用带源前缀的完整最终句，reason 写“G09 已满足”，但 `_quote_is_expected_effect()` 未识别“引文以完整 new_text 结尾”，将其留为 `SEMANTIC_UNCERTAIN`，最终遗漏 `FAIL`、`OPEN_OBLIGATION`，交付 `incomplete`。已增加有界兼容（引文在最终 artifact 中且以完整实例化策略结尾；调用方仍要求同 operation/site 的 effect proof），新增回归；聚焦套件 **306 passed**，`py_compile`/`git diff --check` 通过，失败 artifact 离线复算后 `SW004 resolved`、最终遗漏 `PASS`。
- 浏览器重跑临时脚本在下载后的 `docx_check` 字段名上误取 `sha256`，原始 `result.json` 仍为 failed；独立 `browser-verification.json` 对保留证据逐项复核通过，原始失败记录不覆盖。该问题属于验收脚本，不属于引擎交付缺陷。
- D06 当前代码已在隔离 V1 工作台完成真实用户路径；**生产部署、生产/普通工作台 E2E、固定 D01–D20/holdout、独立标签和 candidate freeze 仍未完成，项目继续 NO-GO**。不能用本次单合同通过替代整批评测或生产交付。
- 下一条动作：继续固定 D01–D20/holdout 的真实修改评测与独立标签，冻结候选后再做部署验证和普通工作台 E2E；同时保持 FL-D378 回归和已通过的 D06 证据不变。

## 最新断点（2026-10-27，D06 当前代码真实运行与严格零网络回放）

- 当前仍在 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`，工作区保留既有 dirty 修改；未 reset、未 checkout、未部署。当前认证 guide 文件 SHA `20bc6677...`、`document_sha256=7b68793d...`，22 条规则/34 个操作。
- 历史 D06 checkpoint 对当前代码的精确回放被正确阻断：第 5 次请求为 `recall_inventory_v2`、context SHA `56cdd238...`、6145 字符，不在历史 30 个 checkpoint 中；严格回放以 `PROCESSING_FAILED` 停止，未发网络请求。原因是 scope 收紧改变 inventory 上下文，不能伪造响应补齐。
- 已在 `/tmp/opencode/d06-current-real-20261027` 用当前代码、当前 guide 和 D06 原件完成真实模型库级运行：独立新账本，预登记 120 calls / $2.00，实际 28 HTTP / 29 logical、约 `$0.0319953`、158.4 秒；`delivery_status=complete`、46 targets、25 needs_edit、19 edits、0 unresolved、Claim Replay verified（19/22）、delivery gate 0 open、final omission PASS、audit issues 0、sweep gaps 0。
- 实际 `final.docx` SHA `9283b432...`、`redline.docx` SHA `141e8a2f...` 与报告一致；源到 final 仅 19 个段落变化，全部在计划站点内。G06 `p135` 错站点目标被排除；`p280` 位于第六部分申购与赎回，不属于 G06 目标，未删除是正确范围行为；G11 `p228→p229`、G17 `p808→p809`/`p1287→p1288` 复合目标、G16/G17 原子替换、G18 `p831/p1245` 均按预期闭合。
- 已用上述 28 个真实响应在 `/tmp/opencode/d06-current-strict-replay-20261027` 做零网络回放：29 次调用全部命中、0 HTTP、0 缺失；plan/Claim Replay/gate/scope/attribution 与真实运行一致；final 的 `word/document.xml`、`docProps/core.xml` 和 1,411 个段落文本一致，redline 仅修订 `w:date` 不同（归一化一致）。容器哈希差异来自 ZIP/修订时间戳，真实运行哈希为正式证据。
- 该运行仍是 `execution_mode=evaluation` 的库级真实模型运行，**不是正式 Workbench/API/Worker 用户路径**；结果页审阅、授权下载、持久任务、生产部署和固定 D01–D20/holdout 仍未完成。项目继续 **NO-GO**。
- 下一条动作：在新的证据目录和独立账本中，通过正式工作台身份入口提交 D06，核对持久任务、Worker 真实模型、最终/修订 DOCX、Claim Replay、报告/哈希、结果页和授权下载；随后继续固定 D01–D20/holdout、独立标签、candidate freeze、部署验证和普通工作台 E2E。

## 最新断点（2026-10-27，通用定位边界与引文 fail-closed 修复）

- 当前仍在 `codex/regulation-guide-generation`，HEAD 未变，工作区保留既有 dirty 修改；本轮继续修改 `fundlex/recall.py`、`fundlex/recall_pipeline.py`、`tests/test_recall_core.py`、`tests/test_operation_execution_closure.py` 及本断点/集中问题文档，未 reset、未 checkout、未部署。
- 已确认并修复 FL-D370：窗口字符切分后 section IDs 只记录实际 chunk；inventory 和 sweep 重盘点按规则 scope 过滤；survey 与 append recovery 使用映射 section 的物理 location；完整多句引文无法绑定时不再缩窄到最长句；复合 target attribution 只读取目标切片并拒绝跨非空段、section 或 zone。
- 新增回归覆盖：缺失多句引文保持 unresolved、chunk section IDs 不泄漏、survey sibling section 排除、复合目标跨独立物理段 fail-closed。聚焦套件 **266 passed**（包含原有 G06/G15/G18、operation closure、final validation、Replay、append 回归）；`py_compile`、`git diff --check` 通过。
- 尚未完成真实 Worker/model 重跑、实际 DOCX 修改、Claim Replay、正式 final/redline、报告/哈希核对、结果页审阅及授权下载。根分区此前约 165–585 MB 可用，历史 `/tmp/opencode/operation-validation-20261024` 仍按 FL-D367 原地保留，不能删除或复用其超 cap ledger。项目继续 **NO-GO**。
- 下一条动作：在新的 evidence directory 使用当前 workspace 代码重放 D06 checkpoint，核对真实 scope mapping、重复站点、复合目标和 Claim Replay；资源恢复后完成真实 D06 Worker/model → DOCX → Claim Replay → 结果页 → 授权下载验收，再继续固定 D01–D20、dev/holdout、candidate freeze、部署和普通工作台 E2E。

## 最新断点（2026-10-27，法规指引 P1–P10 修复完成，smoke19 待验证）

- 当前阶段快照：`codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`；工作区 dirty（保留既有 Compare/召回/前端修改）。本轮新增/修改集中在 `fundlex/guide_generation/`、`fundlex/generation/effects.py`、`fundlex/model.py`、`tests/test_guide_generation*.py`；未 commit、未 push、未部署。
- 已修复：FL-D368（批次/schema/Residual 稳定键）、D372（并发错配）、D373（G06 探针）、D374（finalize quality 门禁）、D375（req review v5）、D376（要求 findings 入库）、D377（双证据任一匹配）、D379（覆盖审计分批+全量索引）、D380（yes/无文案合并中止）、D383（Residual 指引全量可见）、D384（主题判定+补写）、D385（两轮修复）、D386（uncertain 批次逐要求裁决）。
- 最新离线：法规六套件 **77 passed**；最终全量回归 **1720 passed / 58 skipped / 0 failed**（451.83s，`/tmp/opencode/full_pytest_final9_20261027.log`）。smoke18 在 P10 前启动已中止（$0.0238）；smoke19 已启动。
- 外部阻塞：FL-D382，现有 API key 对其他模型 403，独立复核身份无法由代码关闭。
- smoke19 已完成（run `3b4543d0ecda4feeaff169d30b894716`，1800 calls / $24）：748 次逻辑调用 **0 error**；85 requirements、784 impacts、101 items；finalize `complete_with_unresolved / candidate_with_findings`，gaps **0**、unresolved **2**、latest uncertain **0**、critical_quality **1**（regulation_fidelity）、quality `fail`；critical 合计 101（多数 superseded，最终 open 约 4 个）；Residual **8/3/5** 未饱和；实际计费约 **$0.641711**。latest uncertain 115→0、unresolved 10→2、Residual 56/29/22→8/3/5。
- FL-D387 已修复：smoke19 的 10 个 coverage-topic Impact 未产出 item；现在模型无候选时生成 `regulation_verbatim` 兜底候选（仍需质量复核），pipeline **10 passed**。
- FL-D388 已修复：repair 覆盖 item 后未重新应用直销渠道边界，重新引入 critical；现在 repair 后强制重跑 `_normalise_direct_sale_candidate`。
- FL-D389/390 已修复：重试成功后不再保留 model_error evidence；覆盖按批次 requirement 窗口 + resolver 逐要求结果计算。法规测试 **28 passed**（test_guide_generation.py）。
- smoke20 已完成（run `85a131677d2c4992b4194acc4090509f`）：latest uncertain **41**（2 个 model_error 旧 evidence 所致）、unresolved **4**、critical_quality **1**、Residual **5/2/5**、费用 $0.688562；仍 `candidate_with_findings`。最新全量回归 **1725 passed / 58 skipped / 0 failed**（466.10s）；smoke21 已完成（`gg-real-smoke21`、run `37a22d0df6684cbbaf543ea158a7e985`）：latest uncertain **101**（窗口缺口，非模型错误）、unresolved 10、critical_quality **6**、Residual **6/3/2**、费用 $0.80198；仍 `candidate_with_findings`。FL-D391（轮转窗口+resolver 全批次）与 FL-D392（施行/废止条款 out_of_contract_scope）已修复；最新全量回归 **1739 passed / 58 skipped / 0 failed**（525.32s）；smoke22 首次运行在 RESIDUAL_MINING 被工具 2 小时时限终止（1110 次调用），随后用 `resume_guide_smoke22.py` 从同一 run/账本续跑完成。最终 `complete_with_unresolved / candidate_with_findings`：latest uncertain **0**，但 unresolved **24**、critical_quality **6**、missing_topics 7、Residual 第一轮 5 个新影响后两轮因共享账本 2000 requests 上限记为 blocked；`guide_merge` 20 次逻辑 schema 失败；实际计费约 $1.446136。该运行**不是资格证据**（FL-D393）。已实施 FL-D393 修正：单窗口（8 相关+轮转至 12）、merge cluster 12 + 字段自检、smoke23 预算 3000/$36（运行 2400/$32、并发 2）。**FL-D394 已解除**：磁盘恢复至约 **13GB 可用（67%）**；`full_pytest_final14` 的 F/E 确认由 ENOSPC 污染、无效。**FL-D382 已解决**：补上 `x-opencode-session`/User-Agent 后 `glm-5.3-flash` 返回 200；真实 quality review schema 探测通过，`independent_model_review_status=qualified`，reviewer 与 author 不同。smoke23 已配置 glm reviewer；最终全量回归 **1757 passed / 58 skipped / 0 failed**（516.30s），smoke23 已完成（run `9f7872b1fd1041d499c46c30b4123a7c`）：**独立 reviewer=glm-5.3-flash 已合格**，critical_quality **0**、gaps 0、unresolved 3；但 latest uncertain **58**（轮转窗口只取切片前 4 条）、Residual 10/4/1、quality fail（11 semantic_coverage + 1 contract_coverage open）、glm quality review **47 次截断**，费用 $0.960993。已修轮转游标/循环上界、glm 简洁输出、topic 等价判定；最终全量回归 **1802 passed / 58 skipped / 0 failed**（504.90s）；smoke24 已完成（run `520a39742a4c47af8c1c15da65490d96`）：**quality `pass_with_findings`、critical_quality 0、gaps 0、unresolved 3、independent_model_review_status=qualified**；但 latest uncertain **44**（42 个“该要求未被语义扫描覆盖”，窗口按合同混合分配）、Residual 五轮全部 `blocked`（`MODEL_CIRCUIT_OPEN`，0 次实际调用），费用 $1.141186。未达资格。已登记 FL-D396；FL-D397（按合同 coverage tail，所有条款批次补扫缺失要求）与 FL-D398（residual circuit 等待 130s 重试一次）已实施，法规两套件 31+52 passed；全量回归 **1848 passed / 58 skipped / 0 failed**（552.26s）；smoke25 已启动（`gg-real-smoke25`、新账本、run `462f25deebf1452f87ca21fb7201047d`、3000/$36、2400/$32、并发 2、path_b_max_calls=150、Residual 5 轮）。只跑这一次。
- 最新全量回归 **1721 passed / 58 skipped / 0 failed**（436.27s）；smoke20 已启动（`gg-real-smoke20`、新账本、run `85a131677d2c4992b4194acc4090509f`、1800 calls / $24），包含 FL-D387/388。
- 下一条动作：全量回归通过后启动 smoke20，核对补写是否产出 item、剩余 semantic_coverage/regulation_fidelity critical、Residual 是否饱和；独立模型仍为外部阻塞 FL-D382。

- 已制订 [`GUIDE_GENERATION_REMEDIATION_PLAN_20261027.md`](GUIDE_GENERATION_REMEDIATION_PLAN_20261027.md)；根因、已实施处理与离线验证登记在 FL-D368。
- P1 已实施：`path_b_max_requirements=12` 配置贯穿 Pipeline→DiscoveryConfig；合同扫描每批只携带与条款有证据关联的至多 12 条要求，schema `requirement_ids.maxItems` 同步收紧；模型返回空/超限/越界绑定时整批 `INVALID_REQUIREMENT_BINDINGS` fail closed 并一次有界重试；多要求 finding 按每个要求生成独立 Impact。
- P1 已实施：`QUALITY_SCHEMA` 显式声明 `evidence_quote_2`，quality review 记录 `evidence_quotes` 与 `evidence_matched_quote_indexes`；任一引文精确匹配即可验证，避免第二引文把真实 critical 降级（FL-D377）；未知字段继续由严格 schema 拒绝。
- P2 已实施：Residual 模式键改为“合同版本 + 物理 clause 地址 + 规范化 requirement IDs”；已有 Impact 的物理模式预置为 seen；Residual 按条款批次裁剪要求并拒绝越界绑定；模型错误/无效绑定/其他审计 finding 的轮次为 `blocked`，清零 clean streak，不冒充 saturated。
- FL-D372 已实施：smoke13 的 702 次逻辑调用中 120 次失败，119 次为 `MODEL_CONCURRENCY_LIMIT`（阶段 worker 默认 4、共享账本并发 1，等待约 30 秒后超时）。`GuideModelRouter` 现按预算并发上限加进程内 `BoundedSemaphore`，阶段调用排队而不是失败；离线 3 线程用例断言最大并发为 1。
- 离线验证：最新冻结代码完整 `PYTHONPATH=. pytest -q` 为 **1701 passed / 57 skipped / 0 failed**（479.58s，`/tmp/opencode/full_pytest_final2_20261027.log`）；法规生成六套件（不含 browser）**67 passed**；`compileall`、`git diff --check` 通过。历史首轮 1688 passed / 1 failed 为 G06 探针，已由 FL-D373 修复。
- FL-D373 已修复：当前工作树曾把“Y类单向外转”从句子里排除出 `_semantic_delete_hits()` 探针，导致探针返回空、G06 操作可能从 OPEN 误变可关闭；已恢复探针命中，自动删除排除仍保留在 `_semantic_delete_sentences()`/review 路径。`test_recovery_final_invariants.py + test_recall_core.py` **101 passed**；修复后完整回归 **1698 passed / 57 skipped / 0 failed**。
- FL-D374 已修复：`stage_finalize()` 原来只统计三类文本 critical，未纳入 `quality.run_status`，要求复核失败或覆盖 critical 存在时仍可能 `candidate_ready`（fail-open）。现在 `quality_gate_passed = quality.run_status != "fail"` 纳入 `complete`，finalize 记录 `quality_run_status` 与 checklist。`tests/test_guide_generation_pipeline.py` **7 passed**（新增 critical quality 阻断 candidate_ready 用例）。smoke14 在此修复前启动，其结果必须按新口径重算，不能直接作为资格证据。
- FL-D376 已修复：要求抽取/复核的 `requirement_coverage`、`REQ_REVIEW_FAILED` 等 findings 原来只写 evidence，未进入 `gg_findings`，质量与最终门禁看不到。`stage_extract()` 现同时 `_merge_findings(result.findings)`；新增 `guide_req_review` 全失败用例，断言 critical findings 入库、quality=fail、最终 `candidate_with_findings`、`quality_gate_passed=false`。
- FL-D375 已处理：smoke14 的 `guide_req_review` 在 `article_assessment.4` 因缺少 `reason` 触发严格 schema 失败；保留必填字段，提示词明确每个对象必须提供 reason，版本提升为 `guide_req_review_v5`，待 smoke15 验证。
- smoke14（v4 基线）已完成：目录 `/tmp/opencode/gg-real-smoke14`、新账本、run `390677df707040d68839708c4f9e38c2`。614 次逻辑调用 **0 error**（smoke13 为 120 error，119 次并发）；`guide_impact_sweep` 19 次调用 0 失败。结果 76 requirements、843 impacts、90 items、545 findings；finalize `complete_with_unresolved / candidate_with_findings`，gaps **0**、unresolved **7**、critical_quality_findings **0**，但 quality `fail`（36 critical：31 semantic_coverage、2 draft_text_fidelity、2 regulation_fidelity、1 contract_coverage），latest uncertain **88**，Residual 新增 **24/19/5** 未饱和。实际计费约 **$0.479236**。完整登记见 FL-D378。
- smoke15 已中止并登记为非资格尝试：启动后发现 FL-D379 覆盖审计截断缺陷，smoke15 不含该修复；停止时 31 次逻辑调用、账本 32 requests、实际计费约 $0.0533，目录/账本保留，不改写。smoke16 已中止并登记为非资格尝试：run `68af3fbbe3fb43d4b598e92eea7d98cd`，在 MERGE_AND_GENERALIZE 因 `LOCAL_CANDIDATE_NOT_IN_FAMILY:LG-50b95879a1a1bea62fcc` 中止（yes 但 new_text 为空；388 requests、约 $0.2347），目录/账本保留。已修复为 FL-D380：yes 无文案降级为 uncertain，Impact 保持 unresolved；pipeline 回归 **8 passed**。smoke17 已完成（`gg-real-smoke17`、新账本、run `fd1084ed48284cc5998ffd270a936ab5`）：766 次逻辑调用 **0 error**，无中止；100 requirements、1094 impacts、100 items、679 findings；finalize `complete_with_unresolved / candidate_with_findings`，gaps **0**、unresolved **10**、latest uncertain **115**、critical_quality **9**（draft 4 + regulation 5）、quality `fail`；critical 合计 106（semantic_coverage **78**、draft 14、regulation 13、contract 1）；Residual **56/29/22** 未饱和；实际计费约 **$0.576609**。含全部修复的最新全量回归 **1711 passed / 58 skipped / 0 failed**（442.25s）。完整登记见 FL-D381。
- FL-D379 已修复（smoke15 启动后）：覆盖审计原先单请求 24000 字符截断，smoke14 的 90 个 GuideItem 只有 59 个可见，剩余 31 个被误报为 missing topics，恰好对应 31 个 `semantic_coverage` critical。现改为每 16 条要求分批 + `[ALL_GUIDE_ITEM_INDEX]` 全量索引 + 跨批主题过滤，`COVERAGE_VERSION=guide_coverage_audit_v3`；新增 40/40 分批回归。含该修复的最新全量回归 **1709 passed / 57 skipped / 0 failed**（466.29s）。
- 独立模型复核仍为 `OpenCodeGo/deepseek-v4.1-flash` 同模型，`independent_model_review_status=independent_model_review_not_qualified`；质量/覆盖/Residual 未闭合或独立身份未合格前，项目继续 **NO-GO**，不得宣称 `candidate_ready`、启动 Blind Benchmark 或发布。
- FL-D377 已修复：双证据校验由“全部匹配”改为“任一精确匹配”，并记录匹配索引；真实 critical 不再因第二引文近义而降级。`test_guide_generation.py + pipeline` **26 passed**。
- P5 已实施（FL-D384）：覆盖审计返回结构化 missing topics；`guide_topic_coverage` 严格判定已有指引是否覆盖，只有真实未覆盖主题保留 critical；`stage_supplement()` 对有 requirement/合同锚点的主题创建 coverage-topic Impact，进入 authoring→quality→coverage 复审，最多 2 轮；复审计前 supersede 旧 coverage findings，避免 critical 累积。
- P6 已实施（FL-D383）：Residual 上下文由 6000 字符摘要改为全量 `[ALL_GUIDE_ITEM_INDEX]` + 本批相关明细，避免约 20/100 条可见导致的假新影响；`RESIDUAL_VERSION=guide_residual_sweep_v2`。
- P7 已实施（FL-D385）：`repair_rounds=2`，每轮只修复最新 open critical 并复审，不降低 severity。
- 定向验证：法规六套件 **76 passed**（含 24 guide + 10 pipeline 新增用例）；`guide_topic_coverage` 已注册到 ModelGateway 任务白名单；authoring impact 上下文携带 `impact_reason`；最新全量回归 **1719 passed / 58 skipped / 0 failed**（455.14s）。
- FL-D382 外部阻塞：现有 API key 对 `minimax-m3.1-flash`、`glm-5.3-flash`、`qwen3.8-flash` 探测均返回 **HTTP 403**，无法配置第二模型；独立复核仍为 `independent_model_review_not_qualified`，需用户/运维提供可用第二模型凭据。
- smoke18 已中止并登记为非资格尝试：P10 分批裁决在启动后加入，smoke18 不含该修复；停止时 12 次逻辑调用、账本 14 requests、约 $0.0238，目录/账本保留。P10（FL-D386）新增 uncertain 批次逐要求裁决，仅全窗口明确 not_affected 才关闭，affected 生成 Impact，遗漏/uncertain 保持 open；`guide_batch_resolve` 已注册，法规测试 **25 passed**。
- smoke19 待启动（`gg-real-smoke19`、新账本、1800 calls / $24），包含 P5–P10 全部修复；需最新全量回归通过后执行。
- 下一条动作：等待 smoke18 完成，核对主题级误报是否减少、真实缺口是否补写、Residual 是否收敛、文本 critical 是否下降；独立模型未合格前资格不能关闭。

## 最新断点（2026-10-27，历史评测目录保留边界）

- `/tmp/opencode/operation-validation-20261024` 已确认不是当前应用运行时默认依赖，也没有活动评测进程使用；但它仍是历史 D01–D20、D06 独立复核、超 cap 账本和回放 provenance 的外部证据根。当前不删除、不改写、不重置其中内容，项目仍继续 **NO-GO**。
- 已生成只读分类清单 [`docs/evidence/operation-validation-20261024-retention-manifest.json`](evidence/operation-validation-20261024-retention-manifest.json)，记录 13 项权威证据、117 项支持性材料、98 项诊断/派生物和 107 项潜在清理候选；清单 `deletion_authorized=false`，SHA-256 为 `386392788de44fd554f299ae2aa290905ad40dd35489fd3ff5783e9946b694fe`。目录约 5.6 GB，未发生文件删除或内容修改。
- 历史隔离账本 `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 当前为 2,293 requests、约 `$2.32384410`，已超过历史登记的 2,000/$2 cap；它只能作为保留的历史事实，不能作为下一轮预算依据。后续真实评测必须新建运行目录、新登记预算和新账本。
- 下一条动作：先完成最小权威证据集的耐久归档、提取哈希复核和显式 archived evidence root 对账支持；在引用迁移和负责人明确决定前不清理候选文件。资源恢复后再处理 FL-D362/FL-D364、独立模型资格和真实 D06 链路，不能把历史回放或目录清理当作当前资格证据。

## 最新断点（2026-10-27，G06 小节边界与第一批样本准入）

- G06 代码逻辑缺陷已修复：真实 D06 的物理范围为 `p130–p137`，`p280` 已排除；第一批可解析沪深 300 合同的范围为 `p157–p162`，后续 `p817`、`p903` 不进入 G06。Y 类单向转换继续 review/fail-closed。
- 当前定向验证：G06/语义删除/范围/operation closure **36 passed**；Worker 恢复 **2 passed**；占位目标 **12 passed**；G15/G18/Claim Replay/交付相关 **14 passed**。JSON、`py_compile`、`git diff --check` 通过。集中记录见 FL-D365。
- 用户指定第一批目录已完成只读准入审计：28 份中 9 份 `parse_ok`，18 份 `EXISTING_REVISION_UNSUPPORTED`，1 份 `DOCUMENT_PROTECTED`。证据 `/tmp/opencode/sample-corpus-first-batch.json`，集中记录见 FL-D366。后续新评测入口默认使用该目录；既有 D01–D20/holdout 固定 manifest 不改。
- 新增入口默认路径：`tools/evaluation/sample_corpus.py` 被 recall run、controlled regression、unseen sampling、scope probe、corpus audit、real contract E2E 和 delivery E2E 使用。准入审计脚本为 `tools/evaluation/sample_corpus_audit.py`。
- 当前阻塞：根分区仅约 165 MB 可用空间，Worker 默认保留阈值为 256 MB；正式模型/Worker 运行不能据此宣称完成。D06 最新真实重跑、正式 final/redline、Claim Replay、结果页和授权下载仍未完成。项目继续 **NO-GO**。
- 下一条动作：在恢复足够磁盘空间且模型配置可用后，重新执行 D06 完整真实链路；随后用 9 份可解析第一批合同建立独立标签和 dev/holdout 选择，不把解析失败样本或转换文件计入真实修改分母。

## 最新断点（2026-10-27，smoke13 已完成，向量派生层实施中）

- smoke9 已完成真实模型运行：run `a9f78342dc674524bf8c79fd77f47544`，目录 `/tmp/opencode/gg-real-smoke9/`，独立账本 `/tmp/opencode/gg-real-smoke9/ledger.sqlite`，退出码 0。最终为 `complete_with_unresolved / candidate_with_findings`，69 requirements、681 impacts、628 local candidates、71 families、59 guide items、264 findings、536 model calls；quality `fail`，coverage 有 111 unresolved impacts、59 latest contract uncertain、1 requirement gap，Residual `max_rounds_reached/saturated=false`。没有 candidate-ready 资格，未运行 blind benchmark。
- 根因补充见 FL-D357：覆盖审计原来一次处理全部未闭合影响，真实 HTTP 200 响应多次超过 schema `maxItems`。当前代码已改为要求级审计 + 每批 40 个未绑定影响的独立审计，prompt version 为 `guide_coverage_audit_v2`；已有 GuideItem 未被明确绑定时，审计不能凭空关闭影响为 covered。
- 定向验证：模型、法规生成、pipeline、API 套件 **52 passed / 1 warning**；新增覆盖批处理、要求复核分批和输出截断分类回归使法规主套件 **37 passed**；`py_compile`、`git diff --check` 通过。schema 失败现在只记录 validator、bounded JSON path 和截断 message，不保存模型响应正文。
- smoke10 启动无效：`/tmp/opencode/gg-real-smoke10/data/runs.sqlite3` 只有 `QUEUED` run，`gg_steps=0`、`gg_model_calls=0`，模型账本无请求，且没有存活进程或退出码；不计入真实模型失败分母。随后 smoke11 run `e37e4b0deb4b4dd58830b2226347dfb1` 已正式完成，退出码 0、15 个阶段完成，最终 57 requirements、589 impacts、618 local candidates、50 families、45 guide items、353 findings、587 model calls；quality `fail`，coverage 有 68 unresolved impacts、19 latest contract uncertain、3 requirement gaps，Residual 为 3 轮 `new_uncovered`、`max_rounds_reached/saturated=false`，状态 `complete_with_unresolved`、资格 `candidate_with_findings`。账本中的旧版 429、截断和 local candidate schema 失败已登记 FL-D358/FL-D359。
- 所有法规角色仍为 `OpenCodeGo/deepseek-v4.1-flash`，`independent_model_review_status=independent_model_review_not_qualified`。项目继续 **NO-GO**；smoke11 完成后仍须满足质量、覆盖、Residual 和独立复核身份条件，才可执行生成后 blind benchmark。
- smoke11 旧代码运行期间发现 FL-D358：要求复核一次性完整上下文在 HTTP 429 后重试为 HTTP 200，但 `finish_reason=length`，账本记录 `MODEL_OUTPUT_TRUNCATED`；当前代码已改为 `guide_req_review_v3` 按约 6000 字符法规批次复核，尚未真实重跑验证。
- smoke11 旧代码运行期间另发现 FL-D359：`guide_local_candidate` HTTP 200/`finish_reason=stop` 但 `schema_error_path=candidates.1`、`schema_failure=required`；当前代码已改为 `guide_local_candidate_v3` 增加逐对象字段自检提示，尚未真实重跑验证。
- smoke12 run `8d2ea4c4fd41480f846a9c1138525f3b` 已正式完成，退出码 0、15 个阶段完成，最终 53 requirements、545 impacts、581 local candidates、63 families、56 guide items、437 findings、523 model calls；quality `fail`，coverage 有 87 unresolved impacts、45 latest contract uncertain、9 requirement gaps，Residual 为 3 轮 `new_uncovered`、`max_rounds_reached/saturated=false`，状态 `complete_with_unresolved`、资格 `candidate_with_findings`。账本 427 条请求中 7 条失败：5 条 requirement extraction `maxItems`、1 条 requirement review truncation、1 条 local candidate `requirement_ids` 缺失；完整登记见 FL-D360。
- smoke13 已完成，run `266823af9f9c474fb87a11e7a90c7fd2`，退出码 0，状态 `complete_with_unresolved / candidate_with_findings`；最终 88 requirements、835 impacts、858 local candidates、88 families、77 guide items、467 findings、702 model calls。质量 `fail`（436 findings、4 critical），覆盖有 88 unresolved impacts、86 latest contract uncertain、4 requirement gaps，Residual 三轮分别新增 54/72/82 个未覆盖影响，`max_rounds_reached/saturated=false`。独立账本 586 条请求中 4 条失败：2 条 `guide_impact_sweep`（`requirement_ids.maxItems`、输出截断）、1 条 residual HTTP 429 重试耗尽、1 条 quality review additionalProperties；最终证据见 FL-D362、FL-D364。所有法规角色仍使用 `OpenCodeGo/deepseek-v4.1-flash`，`independent_model_review_status=independent_model_review_not_qualified`。
- 当前代码定向回归仍为 **53 passed / 1 warning**；smoke13 不能作为资格或 blind benchmark 输入，项目继续 NO-GO。
- 向量派生层已实施：SQLite 关系库仍是 ClauseUnit 权威源，新增版本化 embedding manifest、provenance、原子激活/回滚和可注入 embedding provider；discovery 已接入词法+向量并集，新增无需 Python 客户端的 Qdrant REST 后端。23 项向量/法规聚焦回归通过；真实 embedding/Qdrant 尚未验证。当前根分区仅约 350 MB 可用，真实后端启动登记为 FL-D365，向量配置保持关闭并回退词法。
- 下一条动作：完成 Qdrant/本地派生后端边界与 discovery 词法+向量并集接入，补充重建/回滚/证据回查测试；随后修复 FL-D362/FL-D364 的真实批次问题，用全新账本重跑资格门禁。只有质量、覆盖、Residual 和独立模型身份条件全部满足，才可运行生成后 blind benchmark。

## 历史断点（2026-10-27，D06 当前代码离线重放；smoke9 后续已完成）

- D06 已用最新代码对真实运行 checkpoint、原件和 working artifact 完成完整 `offline_checkpoint_replay`：目录 `/tmp/opencode/recall-runs/d06-current-full-replay/001-d06/`，31 个缓存模型响应、0 个 task fallback，无新增真实模型请求。
- 当前重放结果：`delivery_status=incomplete`、`artifact_claim_replay.verified=false`、`delivery_gate.open_obligations=1`、`blocking_unresolved=2`。唯一未闭合 operation 是 G06：p280 的 Y 类单向转换限制进入 `semantic_delete_review_required`，保留人工业务 review/fail-closed；不得自动删除。
- G15/G18 当前代码证据已闭合：G15 p810 sweep 为 `resolved / sibling_authorized_effect`，同站点 G16 新支付机制通过 operation/site proof；G15 p807/p1286 为 `ARTIFACT_VERIFIED`。G18 p1245 和 p831 为 `ALREADY_SATISFIED`，均有 `source_operation_policy_equivalent` 物理站点证据；p132 未分组类别句仍未被接受。完整登记见 FL-D356。
- 重放目录只有 `working_final.docx`、`working_redline.docx` 和报告，没有正式 `final.docx`/`redline.docx` 或授权下载交付；离线重放不能替代真实 Worker/真实模型重跑。项目继续 **NO-GO**。
- 当时等待的 smoke9 已在后续完成，最终未达资格；完整证据见上方当前断点和 FL-D355。该历史段落保留 D06 重放时的上下文，不能作为当前运行状态。
- 下一条动作：等待 smoke9 进程结束并按 FL-D355 核对最终阶段/资格/盲评；模型服务稳定后真实重跑修复后的 D06，先取得 G06 p280 业务适用性决定，再完成正式 final/redline、Claim Replay、残留、哈希和授权下载门禁。

## 最新断点（2026-10-27，smoke8 上游限流与 smoke9 重跑）

- 当前受保护配置 `OpenCodeGo / deepseek-v4.1-flash` 的最小真实请求已恢复；配置只通过保留 `/etc/fundlex-recall.env` 原始 RHS 的当前进程注入，凭据未写入仓库、账本或文档。所有法规指引角色仍使用同一模型，`independent_model_review_status=independent_model_review_not_qualified`。
- 全新 smoke8 已完成真实模型调用：run `9bf46661ec8444479a8451ddad6eb248`，目录 `/tmp/opencode/gg-real-smoke8`，53 requirements、252 impacts、277 model-call records；前三次要求抽取 HTTP 200，随后 `guide_req_review` 连续三次 HTTP 429，账本熔断后其余调用返回 `MODEL_CIRCUIT_OPEN`。结果为 `complete_with_unresolved / candidate_with_findings`，252 impacts 均 `possible/unresolved`、0 families、0 guide items、21 requirement gaps，未达到资格。详见 FL-D354。
- 两次全新账本的单请求探测均成功：完整 `guide_req_review` 约 47 秒、单条 `guide_intent` 约 23 秒；随后同一新账本连续 3 次 intent 加 1 次完整 review 均 HTTP 200，无错误。该证据支持“短时间上游限流窗口”判断，不能把 smoke8 的 unresolved 结果归因于法规抽取或 schema 代码。
- smoke9 已启动，使用全新 `/tmp/opencode/gg-real-smoke9` 数据目录、独立账本和同一真实法规/2 份合同输入；运行时 guide retries 从 2 提高到 4，保持单并发、原有质量与覆盖门禁不变。命令输出暂存于 `/tmp/opencode/smoke9.out`，完成后才进行生成后 blind benchmark。
- 项目继续 **NO-GO**：smoke8 未资格，D01–D20 固定分母、500+ corpus、holdout、候选冻结/runtime 导入、部署及普通工作台完整真实 E2E 仍未闭合。下一条动作是等待 smoke9 完成，按 FL-D354 核对真实阶段结果并决定是否执行 blind benchmark。

## 最新断点（2026-10-27，OpenCode workspace region 阻塞）

- 按用户要求，仅更新 `/etc/fundlex-recall.env` 的 `LLM_API_KEY`，保留 OpenCode endpoint `https://opencode.ai/inference/go/v1`、模型 `deepseek-v4.1-flash`、原有请求选项和其他配置；旧配置备份为 `/etc/fundlex-recall.env.bak-20261027-100547`。
- 新 key 的认证已通过，但最小真实请求均返回 HTTP 400，上游明确提示：`This Go model requires Global regions. Select Global in your workspace's Privacy settings to use it.` 带请求选项、去掉请求选项和最小请求三种形态结果一致。
- 因此当前阻塞是 OpenCode workspace 的 Privacy/region 设置，不是 FundLex 代码或 API key 认证问题。尚未产生 D06 合同产物、Claim Replay 或授权下载文件，项目继续 **NO-GO**。集中记录见 FL-D353。
- 下一条动作：将 OpenCode workspace region 设为 Global 后，重新运行最小 schema smoke；成功后重跑 D06 修复版真实流水线。

## 最新断点（2026-10-27，D06 修复后真实评测的认证阻塞）

- D06 修复后的首次启动 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06-fixed-600/` 因直接 `source /etc/fundlex-recall.env` 破坏 JSON 引号，在网关构造前失败；该问题登记为 FL-D351，没有模型请求或合同产物。
- 用保留原始 `name=value` RHS 的安全环境传递方式重新启动 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06-fixed-600b/`，实际进入 runner，但本机 env 配置的 `deepseek-v4.1-flash` 在 `https://opencode.ai/inference/go/v1` 首个 `recall_facts` 请求返回 HTTP 402，summary 为 `STOP:MODEL_HTTP_ERROR`，targets=0。
- 仅在当前进程覆盖到既定 `https://free.quanthatch.com/v1`、`gpt-6-luna`、`{"reasoning_effort":"high"}`，继续使用同一受保护 key 做最小真实 smoke，返回 HTTP 401；账本为 `/tmp/opencode/gpt6luna-smoke-20261027.sqlite`。因此当前 key 不能证明可认证既定评测端点，详见 FL-D352。
- 代码层 D06/G05/G06/G11/G18 定向回归已达到 **339 passed**，`py_compile` 和 `git diff --check` 通过；这些结果不能替代真实模型、Worker、DOCX 和授权下载验收。
- D06 修复后真实合同尚未生成，D01–D20 固定分母、holdout、候选冻结、部署和普通工作台真实 E2E 仍未闭合；项目继续 **NO-GO**。
- 下一条动作：取得能认证既定端点的 `gpt-6-luna` key，或由用户明确指定当前 key 对应的正式模型路径后先完成最小 schema smoke，再重跑 D06。

## 最新断点（2026-10-27，gpt-6-luna 真实网关与 D06/D09/D13 复测）

- 用户要求直接使用现有 `gpt-6-luna` 凭据继续真实调用；凭据仅作为当前进程环境变量传入，没有写入仓库、服务环境、日志或文档。配置为 `LLM_BASE_URL=https://free.quanthatch.com/v1`、`LLM_MODEL=gpt-6-luna`、`FUNDLEX_MODEL_REQUEST_OPTIONS_JSON={"reasoning_effort":"high"}`。
- FundLex `ModelGateway` schema smoke 已通过：实际模型 `gpt-6-luna`，合法 JSON，1 HTTP request，无错误，约 2.34 秒；账本 `/tmp/opencode/gpt6luna-gateway-schema-20261027.sqlite`。
- 评测输出均放在 `/tmp/opencode/recall-runs/`，因为工作区 `var/recall-runs/` 为 root-owned，不修改历史目录。D09 首次错误使用了不存在的 `D09-` 文件名前缀，生成 `ZIP_INVALID` 空结果且无模型调用；已用正确原件 `funds_word/广发悦享一年持有期混合型基金中基金（FOF）基金合同_20230708.docx`（SHA `48e4b5b8...f898f`）重新运行。
- 正确 D09 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d09/`：`incomplete`，13 HTTP、10 targets、4 edits、约 `$0.0367`，有 working final/redline，但交付门禁未通过。
- D13 180 秒运行 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d13/` 和 D06 180 秒运行 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06/`：均在 `recall_inventory` 两次 `MODEL_NETWORK_ERROR` 后 `not_generated`，分别约 `$0.0197`/`$0.0217`，无正式 DOCX。600 秒上限重跑后：D13 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d13-600/` 为 `incomplete`（16 HTTP、13 targets、5 edits、约 `$0.0451`）；D06 `/tmp/opencode/recall-runs/real-20261027-gpt6luna-d06-600/` 为 `incomplete`（32 HTTP、80 targets、17 edits、约 `$0.0886`）。两份均有 working final/redline 和实际哈希，但没有正式 final/redline 交付。
- D13 主要残留：9 个 operation `verified site missing`，G10 保留原申购费用条款，G12 保留按比例计入/未计入部分用途旧内容；D06 主要残留：G05/G11 站点缺失、G06 `semantic_delete_variant_present`，G18 两处实际 A/Y 与 C/E/F 类别分组未实例化。详见 FL-D350。
- `tools/evaluation/recall_run.py` 已修复新摘要传播 model event 首个 `error_code`；详见 FL-D349。未回写 D06/D13 历史摘要，不改变固定失败分母。
- 项目结论继续 **NO-GO**：真实模型虽可用但长上下文性能不稳定，D06/D09/D13 仍未 complete；D01–D20 固定分母、holdout、候选冻结、部署和普通工作台真实 E2E 均未闭合。
- 下一条动作：先运行评测摘要定向回归；随后按 FL-D350 优先修 D13 G10/G12 与 D06 G05/G06/G11/G18 执行/站点闭环，必要时以 600 秒上限独立账本复测，再决定是否整批复跑。

## 最新断点（2026-10-27，free.quanthatch DeepSeek 服务探测）

- 用户提供的 `https://free.quanthatch.com/v1` API key 已完成最小探测；凭据只在当前进程使用，没有写入仓库、文档、环境文件、日志或评测账本。
- `/v1/models` 认证请求返回 HTTP 200，并列出 `deepseek-v4-flash`、`deepseek-v4-flash-ascend`、`deepseek-v4-pro`。实际 `/v1/chat/completions`：Ascend/Pro 模型立即返回 HTTP 502 `Upstream service temporarily unavailable`，基础 Flash 模型在 90 秒最小请求后超时。
- 结论：该端点当前只能证明模型目录可访问，不能证明 DeepSeek 对话调用可用，不能替代 D09/D13/D06 的真实模型验收。集中记录见 FL-D348。
- 由于 API key 已在聊天中出现，正式评测前必须先撤销并轮换；新 key 只能通过受保护的本机环境变量注入。服务恢复后先用 FundLex 实际网关配置完成最小对话请求，再继续真实合同评测。

## 最新断点（2026-10-27，法规 source supplement 与直销收费候选隔离）

- 当前机器仍为规定的 Linux 云服务器；分支 `codex/regulation-guide-generation`，工作区 dirty，既有 Compare、Feishu、前端、引擎和法规指引生成修改均保留，未 reset、未 commit、未 push、未部署。
- 本轮新增 FL-D347：`fundlex/guide_generation/requirements.py` 现在在模型抽取、repair 和 challenger 后补建“模型已引用但 source quote 未完整覆盖”的 source-backed requirement，并恢复 source quote 中显式 `对于/除……外` 条件和例外；完全未被模型引用的 block 不由该 supplement 伪造。`authoring.py` 在 Local Candidate/Family 后隔离基金管理人直销禁收费与 A/D/C 历史收费结构，`quality.py` 对残留无渠道边界冲突保持 critical。
- 新增回归：源块部分跨度与未引用边界、直销收费候选边界、quality fail-closed；法规/指引主套件 **15 passed**，浏览器法规套件 **1 skipped**；完整 Python 回归 **1655 passed / 56 skipped / 3 warnings / 423.84s**；`compileall`、`py_compile`、`git diff --check` 通过。Fake pipeline 恢复 `complete/candidate_ready`。
- 尚未重新调用真实模型，未改变账本、未部署。smoke7 历史 run `3c694aebc9bd4579aec1996bf8dac9df` 仍是关键要求召回 75.0%、条件覆盖 58.33%、6 条关键 fidelity findings、Residual 未饱和的未达资格基线；必须在模型服务恢复后独立账本真实重跑核对，不能用离线回归替代。
- 下一条动作：先完成更广法规/质量定向回归及完整 Python 回归，更新 FL-D343 状态；模型服务恢复后重跑 smoke7，核对 G-R02/G-R11/G-R12、第八条费率主题和直销渠道文案，再决定是否进入 500+ corpus、D01–D20、holdout 和候选冻结。

## 最新断点（2026-10-27，单类事实、D06 survey 与模型服务阻塞）

- 当前机器仍为规定的 Linux 云服务器；分支 `codex/regulation-guide-generation`，工作区 dirty，既有 Compare、Feishu、前端、引擎和法规指引生成修改均保留，未 reset、未 commit、未 push、未部署。
- 单类事实修复已实施：无字母/货币类别且无多类枚举的合同可由源文结构确认 `SINGLE`；模型“默认份额类别”归一为 `__single__`；单类费用事实只在合同申购费用引文和限定范围内无当前销售服务费条款时闭合。集中记录见 FL-D344。
- 定向验证：单类、费用证据、条件状态、Replay、survey/operation closure 相关套件 **177 passed**；`py_compile`、`git diff --check` 通过。此前完整 Python 回归的 FL-D343 顺序失败尚未通过第二次完整长跑定性，不能宣称全量回归通过。
- D09 检查点重放确认事实输出 `classes=[('__single__', True, False)]`、规则映射 22/22；随后 inventory 因事实账本上下文改变产生 `MODEL_REPLAY_MISS`，属于离线重放边界，不能作为真实模型合同结果。
- 新 D09 真实复测 `var/recall-runs/real-20261027-d09a/` 在事实提取首请求收到 HTTP 402，summary 为 stopped、targets=0、无合同产物。D13 仍未取得修复后真实结果。集中记录见 FL-D346；不得把 stopped/checkpoint replay 当作 complete。
- D06 原始报告的 5 条 G02 `SURVEY_QUOTE_UNRESOLVED` 已定位为短引文无法在重复类别标签中绑定完整物理段；已增加只针对 G02/G04 satisfied 证据的完整段绑定兜底，并有合成回归。D06 旧检查点重放同样在 inventory 因 `MODEL_REPLAY_MISS` 停止，真实 D06 仍需复跑。G06 的单向 Y 类转换限制继续 fail-closed，见 FL-D345。
- 当前开发集仍不能冻结：D06/D07/D08/D09/D10/D12/D13/D14/D19/D20 仍需真实模型复测或逐份产物复核；固定 D01–D20 分母、holdout、候选冻结、部署和普通工作台真实 E2E 均未闭合。项目级结论继续 **NO-GO**。
- 下一条动作：模型服务恢复后分别真实重跑 D09、D13、D06；随后按 D01–D20 固定分母逐份核对实际 DOCX、Claim Replay、残留、报告/哈希和授权下载，再进行整批复跑、holdout、候选冻结与用户端到端验收。

## 最新断点（2026-10-27，法规 smoke7 盲评与完整回归复核）

- 已确认当前机器为规定的 Linux 云服务器，分支 `codex/regulation-guide-generation`，工作区 dirty；既有 Compare、Feishu、前端、引擎和法规指引生成修改均保留，未 reset、未 commit、未 push、未部署。
- smoke7 原始运行 `/tmp/opencode/gg-real-smoke7/` 已完成：run `3c694aebc9bd4579aec1996bf8dac9df`，47 requirements、352 impacts、237 local candidates、50 families、45 guide items、108 findings、302 model calls，状态 `complete_with_unresolved` / qualification `candidate_with_findings`。盲评原始目录重跑成功：关键要求召回 **75.0%**、已知合同条款覆盖 **100%**、条件覆盖 **58.33%**、关键 fidelity findings **6**、false-positive rate **6.7%**、人工复核负担 **45**、Residual `max_rounds_reached` 且 `saturated=false`。结果文件为 [`benchmarks/sales_fee_regulation_2025/results/3c694aebc9bd4579aec1996bf8dac9df.json`](../benchmarks/sales_fee_regulation_2025/results/3c694aebc9bd4579aec1996bf8dac9df.json)。该结果未达到 qualification，不能扩展为正式 500+ corpus。
- 修复 FL-D342：benchmark CLI 使用 `RunStore(read_only=True)` 与只读法规 Store，不建表、迁移或切换 WAL；原始 root-owned 数据库评分成功。只读边界/法规套件 **18 passed**，法规/浏览器法规套件 **22 passed / 1 skipped**，compile/Node/diff check 通过。
- 完整 Python 回归后续复跑：**1652 passed / 56 skipped / 3 warnings / 439.35s**。FL-D343 中记录的 `test_unnamed_single_class_normalizes_model_default_and_verifies_no_service_fee` 未复现；该测试单独 **1 passed**、所属文件 **23 passed**，因此按疑似顺序/环境 flake 保留，不能据此宣称根因已证明消失。此前全量的 V2 失败已在单独和成组回归中通过（V2/Store/Worker **44 passed / 1 skipped**）。
- 法规指引、法规 API/流水线、模型和 recall 组合定向回归当前为 **102 passed / 1 warning**；法规浏览器链路 **22 passed / 1 skipped / 1 warning**。未新增真实模型调用，未改变账本，未部署。
- 下一步：保留 FL-D343 的一次失败证据，继续修复 smoke7 的 75% 关键要求召回、6 条关键 fidelity findings、11 unresolved impacts 和未饱和 Residual；资格门通过前不启动 500+ corpus 和正式 holdout。
- 项目级结论继续 **NO-GO**：D01–D20 固定分母/holdout、正式候选冻结与 runtime import、Engine Compatibility、真实 OAuth 回调、MySQL 8 并发、Compare 完整 coverage、部署和完整普通工作台最终交付仍未全部闭合。

## 最新断点（2026-10-26，D01/D04 真实合同闭环与 D01–D20 批量）

- 用户已明确：不再受原模型预算限制，也不再等待生产授权，预算“该用就用”。本轮已真实调用模型，使用生产账本的独立副本 `/tmp/opencode/eval-ledger-20261026-d04.sqlite`，起始 28,328 requests / $23.380108；当前约 28,558 requests / $23.64。未把副本余额冒充生产账本；原生产账本由在线服务单独记账。
- 当前代码已验证：
  - D04 `var/recall-runs/real-20261026-d04h/`：**complete**，44 targets、18 edits、28 calls、$0.0312、145 秒；Claim Replay `verified=true`（18 edits/22 units）；final SHA `5bffa2e7d8637ab9ecc8b0d6ec3e54ef8624cf28a025c4746d05c3aa4403de21`、redline SHA `03b37d0367990df4c65692dd8fd39153d3ea8ff97defd947c0781cbe76965fff`；实际 p83/p194 正确。
  - D01 `var/recall-runs/real-20261026-d01c/`：**complete**，27 targets、19 edits、28 calls、$0.0269、149 秒；Claim Replay `verified=true`（19/21）；final SHA `c4c2bbdbe056ec1151b1b400225549dba6a9edc523ac2b5c6b720895c3c86587`、redline SHA `874d7a29e7901e88a90250a207ac35ad38b2d1f93136e43c9714b51e7f81da2a`；p229/p760 正确。
- 本轮修复（详见 FL-D340/FL-D341）：G04 跨段引文前缀裁剪与 target 重绑；G12 ONE_OF 源文变体选择；G17 复合站点重复 target 去重；sweep orphan 引用旧条款不存在时确定性反证；G09“人民币元→元”变体；共享账本并发等待有界（30 秒）与 429 Retry-After/指数退避；`MODEL_CONCURRENCY_LIMIT`/`MODEL_RESERVATION_EXPIRED` 进入 stop 路径。
- 完整 Python 回归：**1644 passed / 56 skipped / 3 warnings / 414.87s**；定向回归 179 passed；未重新跑完整浏览器/前端构建（代码改动在后端，发布前必须重跑）。
- D01–D20 开发集批量已跑完：`var/recall-runs/real-20261026-dev20/`，**5 complete / 14 incomplete / 1 stopped**（D15 `MODEL_SCHEMA_INVALID`），587 calls / 约 $0.675。批量 D01 仅 1 条 G13 orphan 误报，单独 D01c 为 complete；sweep 输出有波动，不能只凭一次结果。
- 批量后已修复并定向验证：G06 确定性删除（D03/D08/D18）；G02/G04 类别 operation 重绑（D03/D05 等）；G16 尾句重分类和完整替换（D14 的 G16 已不再阻塞）；非截断 schema 错误重试。D03 定向复跑 **complete**（35 targets/20 edits/$0.0273/166s），D05/D18 定向 **complete**；D14 仍有 G01/G03/G08/G14 open。
- 当前保守完成：D01（单独）/D02/D03/D04/D05/D11/D16/D17/D18；其余 D06/D07/D08/D09/D10/D12/D13/D14/D19/D20 仍有阻塞。完整 Python 回归 **1649 passed / 56 skipped / 3 warnings / 411.35s**。
- 剩余共性热点：G01/G03 append、G08/G11/G14 多操作/类组、D20 G16+G17 合并保留原文、D09/D13 单类 FOF/债基 class structure、D06 survey 短引文 orphan、D07/D12 大范围 audit/coverage。下一轮先修共性再整批复跑。
- 隔离账本累计约 **29,400 requests / $24.60**（起始 28,328 / $23.380108）；生产在线账本另计。当前分支 `codex/regulation-guide-generation`，工作区 dirty，未 commit、未 push、未部署；并行法规/Feishu/Compare 修改保留，不得 reset/checkout。
- 下一步：继续修 G01/G03/G08/G11/G14/G16 与单类结构；整批复跑后冻结候选；完整前端/浏览器/MySQL/真实 DOCX 复核；备份并发布；普通工作台真实上传→Worker/模型→DOCX→结果页→授权下载；真实 OAuth 和 Compare 覆盖缺口继续跟踪。项目整体仍 **NO-GO**。

## 2026-10-26 法规候选链路收敛断点

- 当前分支仍为 `codex/regulation-guide-generation`，工作区 dirty；保留既有 Engine、Replay、Feishu、Compare、前端和文档修改，未 reset、未部署、未调用真实模型。法规新增/修改文件包括 `fundlex/regulatory/`、`fundlex/guide_generation/`、`frontend/guide_generation.{html,js,css}`、`tests/test_guide_generation*.py` 和相关依赖/文档。
- 已完成并验证：法规 DOCX/PDF、候选流水线、`/api/guide-generation/*` 路由、专用 Worker、SQLite Store、owner 隔离、人工编辑、Evidence/DOCX 导出、不可变候选版本、`candidate_ready → human_draft → approved → published` 状态链、发布后编辑拒绝、前端带认证头下载和候选审批/发布按钮。
- 候选版本现在在 `gg_candidate_versions.payload_json` 绑定 GuideItem 快照及 artifact key/SHA/size；人工编辑使用候选锁、expected current version 和唯一文件名。候选发布明确返回 `runtime_guide_import=not_requested`，不会自动调用现有 runtime `guide_store.set_current_guide()`。
- 实际验证：法规套件及新增候选版本/Worker 边界覆盖 = **21 passed / 1 warning**；覆盖不可变版本快照、旧版本冲突、artifact SHA/size 对账和 Worker fencing。`FUNDLEX_BROWSER_TESTS=1 PYTHONPATH=. .venv/bin/pytest -q tests/browser/test_guide_generation.py` = **1 passed / 9.01s**，临时密码账号完成法规上传、候选 Worker、人工编辑、批准、发布和认证 DOCX 下载；无认证下载返回 401。`compileall`、`py_compile`、`node --check frontend/guide_generation.js`、`git diff --check` 通过；全模块 import 通过；`sudo -n true` 通过。
- `.venv/bin/uv lock --check` 已通过；使用 `/tmp/opencode/fundlex-uv-clean-env` 做 Python 3.11 clean sync，锁定 PyMuPDF 1.28.2 安装及 `pymupdf`/候选 API/pipeline import 已通过。集中记录 FL-D337 已更新为已验证，FL-D338 已补入真实密码浏览器证据；FL-D336 保持已解决。
- 当前下一步：候选链路的离线/密码浏览器验收已闭合；在预算、labels/gold 和正式候选发布条件满足前，不启动真实模型资格评测或生产部署。条件满足后，完成真实模型/正式候选发布、独立 runtime 指引导入门禁和完整用户交付。候选发布不等于 runtime 指引发布。
- 项目级结论仍为 **NO-GO**：真实模型预算和 qualification、D01–D20/holdout、G06 授权、MySQL 8 并发、OAuth callback、Compare coverage、runtime publication 和完整真实用户交付仍未闭合。

## 最新断点（2026-10-26，V1 Compare 选择版阶段三/四完成）

- 当前分支 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`；本轮修改尚未 commit、push 或部署。工作区仍包含 Compare、法规指引生成、Feishu、source proof/Worker 等并行 dirty 内容，不得 reset/checkout 清理。
- Compare 选择版已补齐阶段三/四：
  - 持久化：`compare_selection_drafts`、`compare_selection_artifacts`；草稿 epoch、decision hash、result/左右源哈希绑定；选择变化将旧生成版本标记 stale，旧文件仍可追溯下载。
  - API：`GET/PUT /api/compare/pairs/{id}/selection`、`POST .../preview`、`POST .../generate`、`GET .../selection-artifacts/{version}/{kind}`；所有查询/下载校验 owner；epoch/result/source 冲突返回稳定错误；增量保存合并草稿；同一 epoch/decision 重复生成幂等。
  - V1：逐差异“采用原版/采用对比版”radio、进度、全部左右、清除、保存、预览、生成、版本/过期标记、选择报告和授权 DOCX 下载；390px/768px/1440px 无横向溢出。
- 验证证据：Compare + selection 定向 **91 passed / 5 skipped / 1 warning**；完整 Python **1637 passed / 56 skipped / 3 warnings / 413.76s**；完整浏览器 `FUNDLEX_BROWSER_TESTS=1` **43 passed / 90.79s**；一次性真实 MySQL 8.0.46 套件（数据库适配、RunStore 租约、Compare 并发、选择版事务）**27 passed / 23.48s**；前端 build/typecheck/lint/Vitest **14 passed**；`node --check`、`py_compile`、`git diff --check` 通过。
- 并行法规指引测试新增同名文件导致 pytest 收集冲突；通过新增 `tests/browser/__init__.py` 包标记解决，未修改并行测试内容，登记 FL-D339。该文件属于测试基础设施，不改变产品行为。
- 当前未完成：Compare 选择版生产真实用户路径（登录→上传→Worker→选择→生成→实际 DOCX/哈希/授权下载）、候选冻结与部署。结构新增/删除（空侧段落级）、跨段联合操作仍按设计 fail closed；header/footer/AlternateContent 等 Compare 覆盖缺口仍存在。
- 本轮未调用真实模型、未改变账本、未部署。项目整体继续 **NO-GO**；下一步需要用户给出生产发布/真实模型预算/D06 业务 gold 的授权，才能继续 D01–D20、候选发布和正式端到端验收。

## 最新验证断点（2026-10-26，source proof/Worker/前端收尾）

- 当前分支 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`；工作区仍 dirty，未 commit、未 push、未部署，既有 Compare、法规指引生成、Feishu、前端和引擎修改均保留。
- 固定源码/构建验证快照：`/tmp/opencode/source-proof-validation-pfsxw_go/`，2908 个文件，manifest SHA-256 `551a2c2edaa0b10cf852f220bd0fbfdc3b7d03f5eb885f775f1d304d414149b8`。快照后并行法规指引生成工作更新了 `frontend/guide_generation.js`、`fundlex/guide_generation/api.py`；这两项另经 9 个指引生成测试和 JS/Python 编译检查，未纳入核心 source proof/Worker/浏览器全量数字。
- 最终离线验证：完整 Python **1632 passed / 53 skipped / 3 warnings / 428.35s**；任务/存储/API 定向 **77 passed / 1 skipped / 1 warning**；完整浏览器 `FUNDLEX_BROWSER_TESTS=1 PYTHONPATH=. .venv/bin/pytest -q tests/browser` **41 passed / 82.63s**；前端 build、typecheck、lint、Vitest **14 passed**，Node/Python 编译和 diff check 通过。
- 浏览器与 Vite build 并行时曾出现一次资源目录竞态，独立重跑及 build 完成后的完整浏览器回归均通过，已登记 FL-D335。后续验收必须先完成 build 和 manifest 固定，再运行浏览器，不得并行清空同一 `frontend/dist`。
- 本轮未调用真实模型、未改变账本、未部署。项目继续 **NO-GO**；真实预算授权、D01–D20、labels/gold、正式候选发布、真实 OAuth/MySQL 并发和完整用户交付仍是阻塞项。
- 下一步：在预算、labels/gold 和候选发布条件满足后，使用冻结候选重新执行真实 D01/D04；核对普通工作台登录、指引、上传、Worker/model、DOCX 修改、Claim Replay、最终/修订版/报告哈希、结果页和授权下载。条件未闭合前不启动新的真实模型调用或部署。

## 当前工作区快照（2026-10-26，G03/G18 站点归因修复与离线重放接续）

- 当前分支 `refactor/backend-engine-finalization`，HEAD `18093fa`，相对 `origin/refactor/backend-engine-finalization` ahead 35。工作区仍 dirty，保留既有用户修改及本轮未提交文件：`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`、`frontend/app.css`、`frontend/app.js`、`frontend/src/pages/Settings/index.tsx`、`frontend/src/types/api.ts`、`fundlex/api.py`、`fundlex/generation/claim_replay.py`、`fundlex/generation/effects.py`、`fundlex/integrations/feishu/oauth.py`、`fundlex/recall.py`、`fundlex/recall_pipeline.py`、`tests/test_append_applicability.py`、`tests/test_feishu_oauth_api.py`、`tests/test_final_validation_regressions.py`、`tests/test_operation_execution_closure.py`、`tests/test_replay_site_provenance.py`。本轮未回退或覆盖既有 dirty 修改，尚未 commit、push 或部署。
- 当前候选已包含 Engine `165dbdf/a872628`、Replay `4fa137d`、Delivery `18b4183`、发布器 `224c4e3`、发布器回归 `13a3380`、预算 guard `da0562c/690c352`、P6 接入 `95a6836`。仓库发布脚本、root publisher、部署脚本 SHA-256 均为 `a873e4b4961207a6fabdb5caf01f8d809c500b6a430ce9c80af8dad114de0338`；四个生产服务最近核对均 active。正式候选尚未执行完整 staging 发布或生产发布。
- 本轮新增定向验证：预算 guard **12 passed**、P6 拒绝顺序 **1 passed**；P6 模拟 ledger 超限返回 2，未构造 HTTP client、账号凭据、运行目录或 manifest。`p6_run.py` 已把 protocol、selection、labels、build、ledger、model mode 和 role snapshot 的 admission 置于账号注册和上传之前。
- 本次 HEAD 工作区完整 Python 回归为 **1599 passed / 52 skipped / 3 warnings / 381.29s**；G03/G18、Replay/site、append、operation closure 相关定向套件为 **167 passed**；`.venv/bin/python -m py_compile` 和 `git diff --check` 通过。前端 typecheck/lint/build、Vitest **14 passed**、V1/V2 浏览器 **40 passed / 81.21s** 是既有候选证据，本轮未因后端改动重新宣称为新的前端验收。
- D06 两次独立盲读均为 `eligible`、A/C/E/F/Y，A/Y 申购费组、C/E/F 服务费组，13 个规则组需改、3 个已满足、6 个不适用。对账证据 `/tmp/opencode/incomplete-remediation-20261026/d06-label-amendment-draft-20261026/review-reconciliation.json`，SHA `18d8d7cc3a45b07449f18870e66bff66ac8ff6c3939b0f1acb47c96a5e92497e`。17 个实际业务位置与 13 个需改规则组仍并列保存，待业务口径批准；gold 未冻结。
- D01/D04 当前候选离线重放位于 `/tmp/opencode/incomplete-remediation-20261026/offline-engine-d01-production/current-replay/` 和 `offline-engine-d04-production/current-replay/`：均为 `offline_checkpoint_replay/incomplete`，只有 working 文件；D01 `open_obligations=5 / blocking_unresolved=11`，D04 `2 / 6`。D01 工作版 Claim Replay 19/19 通过但仍有真实 G11 旧句 `本基金 C 类基金份额不收取申购费。`；D04 工作版 Claim Replay 19/19 通过，G03 只绑定真实定义结束位置 p83，G18 satisfied site 已补真实 source offsets。两份 strict checkpoint replay 仍分别因缺少新上下文响应停止：D01 `recall_inventory` context SHA `9a513a03fc8cbc455246cf14d74b76ac6faa18ef30e11efecddc5b5dc1aa7773`，D04 `recall_audit` context SHA `bedbe9797d768a8ffea4253b7418ab2074c6719aee24a11c820cb3c18148382c`。离线重放不计真实 Worker/model 复测或正式交付。
- 新增真实模型消费为 0。隔离 ledger `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 仍为 2293 requests / `$2.32384410`，超过历史 2000/$2 cap；生产历史账本 27327 requests / 约 `$22.2562593` 只是消费快照，不是新授权。预算与 labels 门继续阻断 qualification/dev/holdout。
- 本轮未新增真实模型请求，隔离 ledger `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 仍为 2293 requests / `$2.32384410`，超过历史登记的 2000/$2 cap；生产历史账本约 27327 requests / `$22.2562593` 只是消费快照，不是新授权。项目继续 **NO-GO**：固定 D01–D20 gate 0/20、D06 gold、规则发布、正式候选发布、普通默认入口真实 E2E、真实 OAuth 回调、MySQL 并发和 Compare coverage 尚未闭合。以下旧时间线保留历史状态，不代表当前快照。

## V1 Compare 左右选择功能实施断点（2026-10-26）

- 用户已明确要求：在 V1 Compare 差异阅读器逐处选择采用左侧或右侧，并依据选择生成一版 DOCX；用户要求后续自行把控进度和版本管理，方案必须落文件，后续无业务待确认点时不暂停询问。
- 持久化方案见 [`docs/V1_COMPARE_SELECTION_IMPLEMENTATION_PLAN_20261026.md`](V1_COMPARE_SELECTION_IMPLEMENTATION_PLAN_20261026.md)，交互和文档边界见 [`docs/V1_COMPARE_SELECTION_DESIGN_20261026.md`](V1_COMPARE_SELECTION_DESIGN_20261026.md)。关联问题 FL-D328–FL-D331 已登记；本功能仍只纳入 V1，不纳入 React V2。
- 当前源码状态：分支 `refactor/backend-engine-finalization`，HEAD `18093fa`，工作区保留既有 dirty 修改；本轮新建方案文档，尚未创建功能分支、尚未提交、尚未改 Compare 运行代码，未部署、未调用真实模型。
- 实施约束：每处差异初始 `pending`，不默认替用户选择；生成绑定 source/result hash 与 selection epoch；实际 DOCX OOXML 写入、重新读取和授权下载是完成门槛。先实现选择契约，再实现 DOCX writer、持久化/API、V1 阅读器和分层/真实用户验证；阶段提交只纳入本功能文件。
- 下一条可执行动作：创建 `codex/v1-compare-selection` 功能分支，提交方案文档（不混入既有 dirty 文件），随后开始阶段一的 selection contract 和纯逻辑测试。若发生上下文压缩，先读本条、实施方案、选择设计和集中问题记录再继续。

## V1 Compare 阶段一选择契约断点（2026-10-26）

- 已创建功能分支 `codex/v1-compare-selection`；阶段 0 方案提交为 `dd52a1d`，只包含 Compare 设计与实施方案文档。既有 dirty 文件均保留，未重置、未部署、未调用真实模型。
- 阶段一已实现 `fundlex/compare/selection.py` 与 `tests/test_compare_selection.py`，并从 `fundlex/compare/__init__.py` 导出契约。支持 `pending/left/right`、三类差异的左右语义、未知/重复/冲突决策拒绝、canonical decision hash、source/result/epoch binding hash，以及跨块/重叠差异阻断。
- 实际验证：`.venv/bin/pytest -q tests/test_compare_selection.py tests/test_compare_algorithm.py tests/test_compare_api.py` 为 **34 passed / 1 warning**；尚未运行完整项目回归，尚未实现 DOCX 写入、持久化/API、V1 控件或下载。
- 当前未提交文件中的 Compare 阶段变更为 `fundlex/compare/selection.py`、`fundlex/compare/__init__.py`、`tests/test_compare_selection.py` 以及实施方案状态更新；集中记录和本断点文件仍含其他历史 dirty 内容，提交时需局部暂存。
- 下一条可执行动作：执行 `git diff --check`、Python 编译和阶段一定向测试，提交 `feat(compare): add selection contract`；随后实现阶段二安全 OOXML 写入器。若压缩，先读本条、实施方案、选择设计和集中问题记录。

## V1 Compare 阶段二安全 DOCX writer 断点（2026-10-26）

- 阶段一提交为 `b8987e1`；阶段二新增 `fundlex/compare/selection_writer.py`、`tests/test_compare_selection_writer.py`，并从 `fundlex/compare/__init__.py` 导出 writer。尚未提交阶段二；既有非 Compare dirty 修改继续保留。
- writer 以左侧 DOCX 为结构基底，绑定左右源 hash、result hash 和 selection epoch；当前只支持单段内 `modify`、普通表格单元格内单段 modify 和多个不重叠操作，生成人工选择版及选择修订痕迹版。生成后重新读取实际 DOCX，校验包成员/非文档部件、最终文本、修订接受等价和选择 manifest。
- 空侧 `insert/delete`、跨段、整段结构、合并单元格、嵌套表格、header/footer/drawing/field/content control 等当前明确返回结构阻断；不把空侧导航 anchor 当成写入地址。后续如支持段落级结构操作，必须新增独立地址和验证，不放宽现有门禁。
- 实际验证：`.venv/bin/pytest -q tests/test_compare_selection_writer.py` 为 **6 passed**；阶段一/原有 Compare 合并定向为 **40 passed / 1 warning**（34 + 6，尚未完整回归）。未部署、未调用真实模型、未通过真实用户下载交付。
- 下一条可执行动作：运行阶段二合并回归、静态检查并提交 `feat(compare): generate selected docx`；随后实现阶段三 Compare selection draft、epoch、artifact、报告和鉴权下载 API。

### 本轮实现与下一断点

- G01/G03 跨段定义追加先归并到真实定义结束段；Claim Replay superseded-site recovery 只接受当前 operation 自己的 edit/component key，缺少 component provenance 时保持 OPEN。G18 satisfied survey target 重新解析真实 source quote，写入 `start/end`、`resolution`、`segment_ok`；无法绑定时登记 coverage gap。effect proof 和 sweep proof 均按 physical site 与 operation identity 归因，sibling operation 不能借站点。
- 集中问题记录已补录 FL-D309/FL-D310 的本轮变更；详细证据和当前状态见 [`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`](DETAIL_ISSUES_AND_RESOLUTIONS.md)。Engine 独立复核交接见 `/home/opencode/.local/share/opencode/worktree/29a9a9/incomplete-engine/docs/ENGINE_INCOMPLETE_ANALYSIS_20261026.md`。
- 下一条可执行动作：预算、labels/gold 和候选发布条件满足后，以冻结候选重新执行真实 D04，核对 G03 p83、G18 物理站点、实际 DOCX、Claim Replay、独立业务复核、授权下载及报告/哈希；先处理 D01 G11 residual，再按 D01–D20 固定分母和普通默认入口完整验收。条件未闭合前保持 NO-GO，不启动新的真实模型调用。

### 2026-10-26 source proof 与验证阻塞修复断点

- 已修复严格 source quote 的轻量 fixture 兼容和短 survey excerpt 绑定：真实 `DocumentInspection` 仍强制唯一物理段、句末边界、未跨 barrier、单一可编辑 segment；重复 occurrence、句中 prefix、受保护段和跨 segment fail closed。Claim Replay/effects/final-validation 及 site 回归恢复，扩大定向套件 **393 passed / 1 warning**。
- Worker retry 现在保留 `verification_blocked` 报告及阻塞阶段/上下文信息；`MODEL_REPLAY_MISS`、`MODEL_CHECKPOINT_UNAVAILABLE`、`MODEL_CASSETTE_UNAVAILABLE` 会暂停任务，仍不进入正式 `complete`。新增 Worker 持久化回归；任务/存储套件 **64 passed / 7 skipped / 1 warning**。
- 已执行 `.venv/bin/python -m py_compile` 和 `git diff --check`；本轮未调用真实模型、未部署、未改变账本。集中记录新增 FL-D332、FL-D333。
- 当前 dirty 文件包含既有 Compare、Feishu、前端及文档修改，以及本轮 `fundlex/recall.py`、`fundlex/recall_pipeline.py`、`fundlex/jobs.py`、`fundlex/store.py`、`fundlex/delivery.py`、`tools/evaluation/replay_checkpoints.py` 和相关测试；不得 reset/checkout 清理。下一步先跑完整 Python 回归，随后按预算/labels/gold/发布条件决定真实 D01/D04 复验；项目继续 NO-GO。

## 历史快照（2026-10-26，incomplete 修复初始与合并过程）

- 当前分支为 `refactor/backend-engine-finalization`，HEAD `1131a8cd74b9b228bef103fcb0dbd6668a907133`；工作区保留既有 dirty 修改和 `docs/INCOMPLETE_REMEDIATION_PLAN_20261026.md`，尚未 push。P0 基线快照保存在 `/tmp/opencode/incomplete-remediation-20261026/`，包含 dirty patch、部署哈希、服务状态和模型账本摘要。
- 本轮只从该 HEAD 创建独立 worktree：Engine、Replay、Evaluation、Delivery 四条审查线并行工作；主工作区不回退既有修改，集中问题记录由主 agent 统一维护。当前尚未合并 agent 代码、部署本轮候选或新增真实模型调用。
- 本轮验证：完整 Python 回归 **1542 passed / 52 skipped / 3 warnings / 358.46s**；后端 OAuth/Feishu/API 定向 **60 passed / 1 warning**；V1/V2 浏览器 **40 passed**；前端锁文件重建后 Vitest **4.1.12，14 passed**，typecheck、lint、build 和 `npm audit`（0 vulnerabilities）通过；`.venv/bin/python -m compileall -q fundlex`、`node --check frontend/app.js`、`node --check frontend/compare.js`、`git diff --check` 通过。系统 `python3` 为 3.6，不能用于本项目编译结论。
- OAuth 当前实现：state 仅保存 SHA-256、默认 10 分钟、成功/拒绝回调均一次性消费；成功回调的真实飞书扫码仍未验证。回归补充了拒绝后 state replay 失败；未调用生产真实模型、未部署本轮 dirty 工作区。
- 集中记录：原 FL-D294 保留为 Feishu 详情深链；任务状态条目已更正为 FL-D299。集中记录仍存在更早历史标题重复，未在本轮擅自重排旧编号；新增编号必须先全文查重。
- 项目结论继续为 **NO-GO**：D01–D20 固定评测 gate、holdout、G06 授权、Compare 复杂结构、真实 MySQL 8 并发、真实 OAuth 回调及完整用户端到端交付尚未闭合。下一步是以当前 clean HEAD 重新核对候选快照和部署边界，再继续 Compare/评测/真实验收；未经授权不部署或调用生产真实模型。
- `incomplete` 修复执行计划见 [`INCOMPLETE_REMEDIATION_PLAN_20261026.md`](INCOMPLETE_REMEDIATION_PLAN_20261026.md)。基线账本摘要为 27,327 requests、约 `$22.2562593`、reserved 0；后续真实调用必须继续使用共享生产账本并登记运行证据。
- 已处理 FL-D303：仓库规范发布脚本已安装到 `/usr/local/sbin/fundlex-publish`，安装前备份位于 `/tmp/opencode/incomplete-remediation-20261026/`；root 发布器与仓库脚本 SHA-256 均为 `1ebe1b52...`，`bash -n` 通过；源/部署 `fundlex.api` 导入预检使用临时数据目录并移除生产数据库环境变量，已实际通过。未因该操作重启或发布业务代码，候选发布仍需执行三服务、构建哈希和 capabilities 验证。
- incomplete 修复基线回归：operation 闭环、Claim Replay 授权边界、复合切片、交付摘要和 Review 门禁共 **97 passed / 1 warning**；这是离线防错证据，不能替代真实模型、实际合同、业务复核和授权下载。评测线另确认当前固定 D01–D20 gate 仍 0/20，账本超历史 cap（FL-D304），D06 冻结标签错误（FL-D305）。
- 本轮已合入 Engine overlap（`165dbdf`、`a872628`）、Replay/ledger projection（`4fa137d`）和 Delivery incomplete 展示（`18b4183`）；各线均未调用真实模型。Replay 全量回归为 **1532 passed / 80 skipped / 3 warnings**，Delivery 定向后端 **65 passed**、前端 14 tests/build 通过；主线合并后的完整回归仍待执行。
- 合并后主线完整 Python 回归：**1564 passed / 52 skipped / 3 warnings / 370.31s**；前端 typecheck、lint、Vitest **14 passed**、production build 通过；compileall、Node `--check`、shell `bash -n`、`git diff --check` 通过。该结果只证明代码回归，不替代真实模型合同评测或用户交付。
- 合并候选浏览器回归：V1/V2 **40 passed / 81.21s**。该套件使用项目浏览器测试环境，证明页面/状态契约回归，不替代真实模型和正式云端交付。
- 发布器 staging 事务与回滚隔离测试：**7 passed**；root 发布器与部署目录脚本 SHA-256 均为 `a873e4b4...`，四服务 active。发布器测试没有执行真实同步或重启。
- 当前生产运行态：API、Recall Worker、Compare Worker、Feishu 均 active；Compare 曾在 13:23:51 因并发 schema migration 重启失败、13:23:55 恢复，登记 FL-D308。误执行截断发布器片段导致 dirty 快照短暂部署，登记 FL-D307；该部署不计正式候选证据。
- 2026-10-26 生产库诊断：MySQL 中共有 666 份合同，335 份（50.3%）为 `succeeded/incomplete`；595 个含合同任务中 318 个至少含一份 incomplete、307 个全部 incomplete。每份合同首要阻塞原因：目标定位/规划/生成执行 212、独立业务复核 86、Claim Replay 25、其他 12。详见集中记录 FL-D301。诊断期间曾有生产数据库连接串旧密码出现在 shell 输出，已按 FL-D302 轮换；配置备份为 `/etc/fundlex-recall.env.bak-20261026-db-rotation`，API/Worker 重启后 active，未记录新密码。

## FL-D291 设置入口修复、飞书主链路与 OAuth 扫码（2026-10-26 11:30）

- 已修复生产 password 用户点击 V1“设置”被 `auth_mode==='dev'` 守卫拦截的问题：移除设置导航守卫，V1 侧栏/顶栏/面包屑统一改为“设置”，保留 `#dev-settings-panel` 密码模式隐藏、`#users` 管理员限制和 `/api/admin/*` 管理员权限。集中记录见 FL-D291，旧浏览器断言 FL-D279 已同步修正。
- 验证：前端 typecheck、lint、Vitest 9 项、build、`node --check`、`git diff --check` 通过；V1+V2 浏览器回归 **37 passed**。真实生产 member 注册/登录后 `#view-settings` 可见、开发面板隐藏、飞书绑定按钮可见、UI 生成 12 位绑定码、binding-code API 200、`/api/admin/users` 404 fail-closed，页面错误 0。
- 生产仅发布 `frontend/app.js` 与 `frontend/compare.html` 并重启 `fundlex-recall-api.service`；工作区与部署 SHA 分别为 `9a6ad9e43cfccce90431ce484d436c6b7085972207cfad903d78005dc7e5b134` 和 `42505246214d3be174c5ecb918fe41d0aae388df11023eee76ffaf9c8b6558a0`。备份：`/tmp/opencode/fundlex-settings-fix-20261026-095645/production-frontend-before.tgz`。证据：`/tmp/opencode/fundlex-prod-settings-e2e-20261026/ui-evidence.json` 与截图（绑定码未入图）。临时账号凭据和 60 分钟绑定码只在同目录 `credentials.json`（`0600`）。
- 飞书应用已补发版本 `0.0.2`（增加 user token 的 `im:message.send_as_user`、`im:message`、`im:chat:readonly`）与 `0.0.3`（增加 tenant `im:message:readonly`，修复 DOCX 资源下载）。真实用户李嘉伟（`ou_f5c9422295f601e1d2826345609fd411`）已完成 CLI 设备授权；先由机器人发起私聊取得 `chat_id`，再由用户发送绑定消息，`/api/integrations/feishu/binding` 已返回 `bound=true`。详见 FL-D290、FL-D292、FL-D293。
- 已发送两份公开 DOCX 原件 D01 141,078 bytes、D02 162,609 bytes，SHA-256 前缀分别为 `2f2f7a36000af813`、`c02ae5a04ffbb1a8`；两份均被飞书机器人接收为 `accepted`，用户发送“确认”后创建任务 `0a1122e359a94cbebf17d2782cfc0969`，文档 `06a49aa462074c98987fd16bdaee0054`、`c29054299d39474baa7d68e79c4a0959`。真实模型调用使用 `deepseek-v4.1-flash`，8 次调用（7 completed / 1 reserved）、约 `$0.02616`；任务已终态但两份均 `incomplete`。
- 飞书卡片已实测发送 `uploading`、`running` 状态并带 FundLex 深链。发现 `/tasks/<id>` 原只回任务总览，已修复为 `/?task=<id>#task` 并让 V1 自动选中任务；生产深链验证通过。详见 FL-D294。发布备份 `/tmp/opencode/fundlex-deeplink-20261026-102313/production-before.tgz`，生产 API/Worker/Feishu 均 active。
- 第一个飞书任务 `0a1122e359a94cbebf17d2782cfc0969` 已终态：2/2 succeeded，但两份 delivery 均为 `incomplete`，只有 `working_final`/`working_redline`/report，没有 final/redline；D01 未完成 G08/G11/G12，D02 也有未完成目标。已下载并保存产物到 `/tmp/opencode/feishu-e2e-20261026/artifacts/`，核验结果 `/tmp/opencode/feishu-e2e-20261026/verification.json`；未授权下载返回 401。**不能把这两份工作文件当最终合同。**
- 由于 D01/D02 不满足完整交付，已用 D04（亚太中高收益债券，SHA `dd176283...`）和 D17（睿毅领先混合，SHA `3b4a3615...`）创建第二个飞书任务 `8da0ef68f2c8465986917a66e7835bf0`；D17 完整、D04 因 G03 Claim Replay 不完整。详见下方第二任务结果。
- 已实现并生产发布个人 OAuth 扫码绑定（FL-D295）：V1/V2 设置页可生成个人二维码，回调绑定当前 FundLex 账号；应用版本 `0.0.6`，OAuth 重定向 URL 已写入，飞书可用范围已改为全员（`is_visible_to_all=1`）。首次二维码等待 10 分钟未扫码：OAuth state 未消费并已过期，API 日志无 callback 请求，真实回调仍未验证；测试账号已用绑定码恢复绑定。另用新的未绑定临时账号完成生产 V1 UI 检查：按钮可见、SVG 112,472 bytes、10 分钟提示和 Feishu 链接正常、页面错误 0；临时账号、会话和未消费 state 已精确删除，未留下可用链接。二维码和 state 只保存在 `/tmp/opencode/feishu-oauth-e2e-20261026/`（`0600`），不得写入仓库/文档。
- 第二个飞书任务 `8da0ef68f2c8465986917a66e7835bf0` 已终态：D17 **complete**，D04 **incomplete**。D17 final SHA `f320b61c3fc42cb41c3c0fc489f85850c04a6ba597c387179f505bc29caf2b87`、redline `e136a0da32bd94977e7869dc90a6371fa96b9a27e9be2b780aa578db91060e24`、report `2930610c96b786a09c463e26ff50c4fd9cd6933736aedc7696e9bf9be4b9a8c0`；16 edits、16 insertions/16 deletions，Claim Replay true，delivery gate unresolved 0；浏览器登录后深链打开任务并下载 final/redline/report，哈希与 API/报告一致。D04 因 G03 `CLAIM_REPLAY_FAILED` 为 incomplete，只有 working 文件。证据 `verification-task2.json`、`browser-verification.json`、`task2-detail.png`。
- 飞书完成卡片已实测：任务 1 `incomplete:2`，任务 2 `incomplete:1 / complete:1`，均带深链。第一个任务 D01/D02 两份均 incomplete，不能当最终合同。整体结论仍为 **NO-GO**，飞书主链路通过不等于引擎全部合同通过。
- 全量回归首次为 **1 failed / 1518 passed / 49 skipped / 3 warnings / 401.37s**，唯一失败 `test_app_rejects_oversized_content_length_before_multipart_parse` 单独运行通过（413），记录为 FL-D297；同源码第二次全量为 **1519 passed / 50 skipped / 3 warnings / 497.31s**，首次失败未复现，按顺序/环境 flake 记录。浏览器套件另修正一处 `time.sleep` 阻塞 route 事件的测试竞态（FL-D298），最终 V1+V2 为 **39 passed / 68.00s**。产品代码未因这两个测试问题改动。
- 二维码“糊”已修复（FL-D300）：根因是 65×65 模块被 240px SVG + 抗锯齿缩放；现生产页面 SVG 为 **325×325**（5px/模块）、`shape-rendering="crispEdges"`，容器 351px；另有 650×650 PNG 回退（约 1.5KB）。真实生产页面检查页面错误/控制台错误 0；临时检查账号/state 已清理。旧页面需强制刷新以加载新 app.js/CSS。
- **FL-D299 发布事故已恢复**：选择性部署工作区 `api.py` 时带入未发布的 `manifest_fingerprint` 导入，与生产旧 `selective.py` 不匹配，API 两个 worker 启动失败约数分钟；已从 `/tmp/opencode/fundlex-qr-sharp-20261026-121725/production-before.tgz` 恢复 API，只补 `qr_png`。当前生产 `api.py` SHA `8048c11d54a896a75d8edb70ac43e1dc220e8a2e1ae3ed392cd9a71f7daf1fbf`，工作区 `api.py` SHA `81bb09ef...`，生产/工作区 `selective.py` 也不一致。**下一次发布前必须先对齐 api.py/selective.py 依赖并整仓验证，禁止再只复制 api.py。** 当前 API/Worker/Feishu 均 active。
- 工作区仍 dirty，HEAD 为 `7cb25d4e27c0cc62408cf92587956fd4150d4d79`；本轮新增修改为 `fundlex/api.py`、`fundlex/integrations/store.py`、`fundlex/integrations/feishu/oauth.py`、`frontend/app.js`、`frontend/app.css`、`frontend/compare.html`、V2 设置/类型/API、测试及文档。未 commit/push。飞书 OAuth 真实回调仍未验证；D17 完整交付已验证，但 D04/D01/D02 不完整，整体 FL-D290 仍不能标记为全量验收通过。

## FL-D290 飞书应用服务器准备断点（2026-10-26）

- 用户已创建飞书企业自建应用。旧 App Secret（曾在聊天中出现）按已暴露处理并废弃；用户已完成轮换，新 Secret 已注入服务器环境文件，未写入仓库/文档/日志。
- 本机已完成服务器侧准备：`/etc/fundlex-recall.env` 已写入 App ID、新 App Secret 和 `FUNDLEX_PUBLIC_BASE_URL=https://fundlex.club`（`640 root:root`）；备份为 `/etc/fundlex-recall.env.bak-20261026-084101`（注入前另备份 `.bak-20261026-085808`）；API 与 Worker 已重启并验证环境变量生效，飞书 `tenant_access_token` 接口返回 `code=0`；`/etc/systemd/system/fundlex-feishu.service` 已安装并于 09:08 enable/active。
- 生产虚拟环境此前缺少锁定的 `lark-oapi==1.7.5`，已安装并验证可导入；systemd 模板通过 `systemd-analyze verify`。该依赖安装是部署目录运维变更，后续发布流程需确保不会丢失。
- 平台配置已通过官方 `lark-cli 1.0.98` 完成：机器人能力已开启；版本 `0.0.1` 已发布；已保留 `im.message.receive_v1`，加入 `im:message.p2p_msg:readonly`、`im:message:send_as_bot`，并写入 WebSocket 模式和新版 `card.action.trigger` 回调。
- 官方 `lark-cli 1.0.98` 已通过 stdin 绑定当前 App ID/Secret，`lark-cli whoami` 显示 bot token ready；09:08 及重启后服务日志显示已连接 Feishu WebSocket；应用管理 scope 已验证有效。
- 下一条动作：真实 FundLex 用户登录设置页生成一次性绑定码，在飞书私聊发送绑定消息；随后发送多个公开 DOCX、点击确认创建任务，完成真实 Worker/模型、产物、状态回传、详情和授权下载验收。真实闭环完成前继续保持未验收状态。

## FL-D276 生产真实验收结果（2026-10-26）

- D275 候选全量回归为 **1497 passed / 48 skipped / 2 warnings / 324.62s**；发布前备份为 `/tmp/opencode/fundlex-production-d275-backup-20261026/pre-publish-opt-fundlex-recall-first.tgz`，SHA-256 `85723301d210de32ee95463cbd503ebe4f1cd0bf43417b32fae2b6083a30cdd1`。发布后 API/Worker active，`/api/capabilities` HTTP 200，四个关键运行时文件部署哈希与工作区一致。
- 新真实 V1 普通路径证据 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-o9rfdisxoj2o/`：任务 `6200b8ad71974c10b613622809fa52f5` / 文档 `2adeaefc840b4df68e8be0d060cea16f` 为 `completed/succeeded/complete`，31/31 targets completed、unresolved=0、19 edits、`artifact_claim_replay.verified=true`。final/redline 与报告哈希一致；Review HTTP 200，19 条中拒绝 1 条，`selected_final`/`selected_redline` 均成功生成、下载和 DOCX 校验通过。
- 独立 Compare 任务 `191b14f48e264212abe98de5828bcd29` 已创建、完成、阅读器与 view API HTTP 200，1113 处差异；coverage 为 `incomplete`，警告为 header/footer/AlternateContent/drawing/pict 未支持，证据为同目录 `compare-view.json`。Compare 全文交付门禁失败。
- 临时账号 `e2e-v1-o9rfdisxoj2o` 已精确清理：1 user、1 session、1 task、1 batch、1 document、1 compare task、1 compare pair，关联对象 10 个；数据库复核用户名行数为 0。
- 当前结论：普通 V1 与 FL-D275 修复真实验收通过；整体生产结论继续 **NO-GO**，因为 Compare coverage incomplete，且 D01–D20 固定分母、G06 授权和其他项目级门禁尚未全部通过。

## FL-D275 G15 composite Replay 与 Review manifest 修复（2026-10-26）

- 真实生产报告 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-jeo9hsg813hd/report.json` 已在工作区修复后离线重放通过：19 个计划 edit、`verified=true`、0 个 Claim Replay failure。修复前的两个 G15 composite 首段失败对应 `p806`/`p1262`，尾段 `p807`/`p1263` 的 source-bound 尾随空白边界也已纳入校验。
- Review 的 `REVISION_TEXT_MISMATCH` 已用真实 `working_redline.docx` 重现；将 `validate_edit_plan()` 生成的父级 `expected_old_text`/`expected_old_hash` 写回 report plan 后，正式 selected artifact 生成器成功生成 `/tmp/opencode/selected-repro-after-d275.docx`。
- `fundlex/generation/claim_replay.py` 已增加仅针对 G15 composite 首段的相邻物理段、完整 payment head、source 重算 delay boundary 校验；`fundlex/recall.py` 仅在顺延句后没有可见文本时保留尾随格式空白；`fundlex/recall_pipeline.py` 持久化已验证 parent manifest 原文。新增 composite Replay 和尾随空白回归。
- 当前定向回归为 `97 passed`；`py_compile`、`node --check`、`git diff --check` 通过。完整回归正在执行，尚未计入本断点；本轮代码尚未发布。
- 本轮工作区仍 dirty，HEAD 为 `7cb25d4e27c0cc62408cf92587956fd4150d4d79`，未提交、未 push。下一步：完整回归通过后创建生产备份，发布 `recall.py`、`recall_pipeline.py`、`generation/claim_replay.py` 及相关当前候选，核对部署 hash 和服务状态。
- 发布后必须执行新的真实 V1 普通公开合同路径，完成 Claim Replay、working/final/redline、Review accept/reject、`selected_final`、`selected_redline`、报告/哈希/授权下载；随后独立完成 Compare、覆盖警告、报告下载、404/页面错误和 1440/768/390 三视口检查。任何 incomplete、selected artifact 缺口、D01–D20 或 G06 缺口继续保持 **NO-GO**。

## FL-D270–FL-D274 G15 生产归因修复与 V1 验收脚本修正（2026-10-26）

- 真实 V1 任务 `91ab2940c62844f7a5cd75ca021c7c54` / 文档 `2e8a8c9a2fd64c058d2bc6c4f2cd1401` 曾完成注册、登录、指引加载、任务创建、DOCX 上传、封存、持久 Worker 和 3 次真实模型调用，但因 G15 `p806` 支付头与 `p807` continuation/delay 跨段归因报 `operation_span_mismatch` 而失败；证据保留在 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-yarwc0ihqd68/`。
- `fundlex/recall.py` 已增加限定的 G15 跨段支付头归因：当前目标必须完整占据支付头段，下一段必须通过支付结构与顺延句校验；不放宽其他规则。新增回归覆盖生产 p806/p807 形态和 Claim Replay。G15 定向 `96 passed`，完整 `1493 passed / 48 skipped / 2 warnings`，`py_compile` 与 `git diff --check` 通过。
- `tools/evaluation/production_v1_e2e_20261026.py` 已将原生 `<option>` 等待改为 `state="attached"`，避免结果页因隐藏 option 可见性超时；`/tmp/opencode/cleanup_fundlex_e2e_user.py` 已按 MySQL schema 增加 Feishu Draft 文件、outbox 和安全对象根目录检查。
- 集中记录已新增 FL-D270–FL-D274。G15 修复已受控发布，备份与哈希证据在 `/tmp/opencode/fundlex-production-g15-20261026-022742/`，生产 API/Worker active，候选 `recall.py` 与部署文件 SHA 均为 `9c6fc3ae6705060d161c6bcf35be967c5c4e0132514b3962c42687ccace62b44`。`targeting.py` 的 NameError 修复也已发布，备份与哈希证据在 `/tmp/opencode/fundlex-production-nameerror-20261026-024021/`，API/Worker active。普通验收脚本已增加失败短路并在成功分支关闭详情弹窗，记录 FL-D274；第三次真实普通合同运行仍待终态。当前普通合同和 Compare 均未完成正式验收；后续必须完成报告、working/final/redline、Review、selected artifact、hash、授权下载、Compare reader/report 和三视口检查，再精确清理最新临时账号和全部关联对象。任何 incomplete 或 selected artifact 缺口都保持 NO-GO。
- 当前工作区仍 dirty，HEAD 为 `7cb25d4e27c0cc62408cf92587956fd4150d4d79`；本次未提交、未 push。生产发布前须记录新备份路径、部署 build 和服务状态；发布后所有结论以新真实证据为准。

## FL-D265–FL-D268 飞书接入专项测试与部署模板（2026-10-26）

- 本轮继续完成飞书私聊接入：修正 `feishu_drafts` INSERT 占位符错误；卡片 action 按事件 ID/payload hash 去重并返回实际提交结果；任务提交中途失败时 Draft 保留为 `COLLECTING`，使用原 idempotency key 恢复；解绑后的身份可复用 revoked 行；MySQL outbox 领取增加 `FOR UPDATE` 和 rowcount 检查。
- 新增 [`tests/test_feishu_integration.py`](../tests/test_feishu_integration.py)，覆盖一次性绑定码、解绑重绑、event payload conflict、重复附件、多个 DOCX、提交恢复、卡片重复 action、卡片发送失败后的 durable outbox、outbox fencing 和 chat/owner scope。专项结果：`PYTHONPATH=. .venv/bin/pytest -q tests/test_feishu_integration.py` = **8 passed**；`compileall` 和 `git diff --check` 通过。
- 新增 [`docs/FEISHU_INTEGRATION.md`](FEISHU_INTEGRATION.md) 和 [`tools/deploy/fundlex-feishu.service.template`](../tools/deploy/fundlex-feishu.service.template)，`.env.example` 只增加凭据变量名和公开 base URL 空值。凭据值未写入仓库、文档、测试或日志。
- 集中问题已登记 FL-D265–FL-D269。FL-D265–FL-D267 已在 SQLite/fake client 范围解决并验证；FL-D268 的 MySQL 8 实际并发锁行为、systemd 安装和真实飞书网络仍待验证。FL-D269 记录一次未复现的首次全量 G15 顺序失败。当前没有安装/启用 `fundlex-feishu.service`，没有发布生产，没有真实飞书任务或新增模型调用。
- 当前工作区继续 dirty，包含本轮 Feishu 文件以及既有 Compare/V1/引擎/文档修改；未提交、未 push。下一条动作：运行 Feishu API/入口回归和完整 pytest，若发现新细节先更新集中记录，再按真实 MySQL 条件执行 store 验证；之后才评估服务安装和真实飞书端到端验收。
- 本轮后续验证：Feishu 专项最终为 **8 passed**；API/入口/任务回归 **60 passed / 1 warning**；数据库回归 **2 passed / 6 skipped**（未配置 `FUNDLEX_MYSQL_TEST_URL`）；完整 `PYTHONPATH=. .venv/bin/pytest -q` 最终为 **1493 passed / 48 skipped / 2 warnings / 307.62s**；前端 typecheck、lint、Vitest **9 passed**、build、V1 `node --check` 和 diff check 通过。首次完整运行有一次未复现的 G15 顺序失败，已登记 FL-D269。
- 运维静态检查：模板复制为 `/tmp/opencode/fundlex-feishu.service` 后 `systemd-analyze verify` 通过；`fundlex.integrations.feishu.service_main` 可导入；`lark-oapi` 为 `1.7.5`。本机 shell 和 `/etc/fundlex-recall.env` 均未发现 `FUNDLEX_FEISHU_APP_ID`、`FUNDLEX_FEISHU_APP_SECRET` 或 `FUNDLEX_PUBLIC_BASE_URL` 的有效值，`/etc/systemd/system/fundlex-feishu.service` 不存在，故真实飞书网络 E2E、MySQL 实连和服务安装仍保持未完成。

## FL-D264 V1 默认工作台恢复与隔离测试发布（2026-10-26）

- 用户最新要求为恢复 V1；已将 `fundlex/api.py` 默认前端入口切回 `frontend/compare.html`，保留 Vite/React V2，并通过 `FUNDLEX_FRONTEND_VERSION=v2` 显式启用。V1 `/compare`、`/tasks`、`/tasks/new`、`/guides`、`/settings`、`/users` 深链映射到原 hash 页面；`frontend/compare.html` 标题恢复为合同修订工作台并移除独立 Compare 横幅。
- 为隔离测试路径增加 `FUNDLEX_FRONTEND_BASE_PATH`；测试服务 drop-in `/etc/systemd/system/fundlex-test-api.service.d/frontend-v1.conf` 当前设置 `FUNDLEX_FRONTEND_VERSION=v1`、`FUNDLEX_FRONTEND_BASE_PATH=/test`。V1 `frontend/app.js` 对 API fetch/XHR 使用该前缀，测试环境既有 `api.py` 的 `/test/static`、健康检查和运行隔离改动已保留。
- 本地验证：入口/Compare/修订 API `13 passed / 1 warning`；V1+V2 浏览器回归 `37 passed`；`git diff --check`、`node --check frontend/app.js` 通过。公网证据 `/tmp/opencode/fundlex-v1-public-smoke-20261026/browser-smoke.json`：测试域名 `/test/` 登录、任务总览、新建任务、指引配置、Compare 均通过；1440/768/390px 无横向溢出，静态/API 404 和页面错误为 0。登录前 Compare 的 401 为预期未认证请求。
- 已受控发布至 `/opt/fundlex-test` 并只重启 `fundlex-test-api`；测试 API、普通 Worker、Compare Worker 和生产 API/Worker 均 active。发布前备份为 `/tmp/opencode/fundlex-v1-restore-20261026/test-frontend-before.tgz`。未调用生产发布器、未修改 `/opt/fundlex-recall-first`、未创建合同任务或新增模型调用；临时 smoke 账号、会话和本地凭据文件已清理。
- 当前工作区仍 dirty：`fundlex/api.py`、`frontend/app.js`、`frontend/compare.html`、`tests/browser/test_workbench.py`、`tests/browser/test_frontend_v2.py`、`tests/test_frontend_entry.py`，以及既有 Compare/后端/文档修改。当前 HEAD：`7cb25d4e27c0cc62408cf92587956fd4150d4d79`。尚未 commit/push。
- 当前剩余动作：审核并提交本轮 V1 恢复文件；如需继续部署，先保留测试服务 drop-in 的 `/test` 前缀。普通合同真实 Worker/model/DOCX、D01–D20、G06、selected artifact 仍按 FL-D263、FL-D251 等记录保持未完成，不因 V1 页面验收改变状态。

## FL-D263 后端安全边界修复与当前验证断点（2026-10-25）

- 已实施后端通用修复：operation Registry 覆盖门移至 Guide enable 与 Worker binding；显式 custom operation 未登记时 fail-closed；Claim Replay 拒绝绑定 FALSE/UNKNOWN applicability 的 edit；普通 sibling 同文不再单独关闭 operation，显式 ONE_OF 历史替代保留；audit missed target 保留 operation/obligation/target 身份；Delivery Gate 接入传入 Obligation Ledger 的 open-record 检查。
- 新增回归：FALSE applicability edit、未登记 custom operation enable；Registry legacy identity 兼容边界已修正。错误码归类修复后，完整当前 dirty 工作区回归：`PYTHONPATH=. .venv/bin/pytest -q` = **1481 passed / 48 skipped / 2 warnings / 288.79s**；`.venv/bin/python -m compileall -q fundlex` 与 `git diff --check` 通过。最终验证时间：2026-10-25T18:48:54+08:00。
- 当前精确 Git HEAD 仍为 `4bad293302e77c859bf6036237142fb382dac6e0`，工作区 dirty。除既有 Compare/前端/文档修改外，本轮后端修改文件为 `fundlex/generation/claim_replay.py`、`fundlex/generation/effects.py`、`fundlex/generation/registry.py`、`fundlex/guide.py`、`fundlex/guide_store.py`、`fundlex/jobs.py`、`fundlex/recall_pipeline.py` 及两项测试文件；未部署生产引擎、未新增真实模型调用。
- 本轮后端文件 SHA-256：`guide.py` `52213bf99cc3e6c394c69519b8caf9d6926793169ffb61d790b05a1dfd239a6c`；`guide_store.py` `019fc5c022ecbaf5813dc8ca5ce7da89914c5dbe34ea52bdd46f2a3d922b915a`；`jobs.py` `22fb4e7f690634c28b342ade09423c82ee1838cac922f1cdb0eb45a627c2bcaa`；`claim_replay.py` `44377f84622bdeb481ea3b80bc780c76b37ec86647573cf658560006ac8c32aa`；`effects.py` `f3343b0a4575f5de0c6029c3d6de3d0dcbba57dba36a1cde0d6f2563a6c93946`；`registry.py` `4563c001408915f8dd4b226a8886a69da5f7b65b3cb75872b3af3e1eba2f9004`；`recall_pipeline.py` `38f6ab8f904282a805c0d88afec9f23a74b9643887b15b514ca45b03723f3927`。当前 dirty engine build：`63401714832f88277194e2005bc6a21b5365d30b56e49ee59d91c8f78b028edc`。
- 不能把本轮 dirty 回归计为最终发布证据。下一条依赖动作：审核 Compare dirty 修改边界并形成唯一 clean candidate；随后以最终 HEAD 重新冻结/生成 build 和 artifact hash，运行 Frozen Replay、真实 Worker/model、D01-D20 固定分母、holdout 及普通工作台最终 E2E。当前结论仍为 **NO-GO**：D01-D20 current gate 0/20、G06 业务授权未决、评测预算不足、selected artifact 仍无闭合证据。

## FL-D262 Compare 候选已发布到隔离测试环境（2026-10-25）

- 已将当前工作区候选发布到隔离测试目录 `/opt/fundlex-test`，覆盖 `fundlex/`、`frontend/`、`guides/`、`rules/`、`tools/`、`docs/`、`tests/` 和必要项目文件；未调用生产发布器，未写入 `/opt/fundlex-recall-first`，未修改生产配置或数据库。
- 发布前备份：`/tmp/opencode/fundlex-test-publish-20261025-150535/test-deployment-before.tgz`。发布证据和哈希文件位于同目录，包括 `after-sha256.txt`、`source-deployed-hash-check.txt`、`browser-smoke.json`、`before-sha256.txt` 和 `before-size.txt`。
- 已重启并核验 `fundlex-test-api.service`、`fundlex-test-worker.service`、`fundlex-test-compare-worker.service`，三项均为 `active`；测试 API 监听 `127.0.0.1:8110`。测试 API `/api/capabilities` 未登录返回 200；密码模式下 `/api/health` 与 `/api/auth/me` 未登录返回预期 401，不能把未认证健康接口 401 误判为服务故障。
 - 工作区与测试部署的 Compare Python 文件及当前入口静态资源 SHA-256 一致：`models.py` `13b36e48669eabd303ee2ef192f886692c81c5757f74fe120ace64be9be5370c`、`parser.py` `e49be4a2aa5d42777336752290db3cee74693927232d9159ce1666b1bd20429b`、`presentation.py` `3ced9d82bf6bfdd0e2e6597dc853aaa7a2b92341a9722749da9cb8d155f9c6fa`、`render.py` `f69d553587e08aedbc7d63f7e6982e2be354694e6aa4fbf96f37c32a9d1a9614`、`index.html` `131e6c718b3732b77431cb53b3ea6357a5657f1dafb8baac1d3a8ed53864f932`、JS `597d4cee45f13670e3f888d0ba2bdc609709b8870665b6704570f34dd48cf1d8`、CSS `3891a1846348a419486ffeb581476bad8c8c273f7b75eb21f3e7e896ae9c4cae`。
- 资源与页面验收通过：`/`、当前 HTML 引用的 JS/CSS 均 HTTP 200；真实测试账号登录后访问 `/compare`，390px 和 1440px 视口均无横向溢出，标题和“新建对比任务”入口可见，页面错误、控制台错误、静态 404、API 404 均为 0。证据：`/tmp/opencode/fundlex-test-publish-20261025-150535/browser-smoke.json`。
- 浏览器验收使用的临时 `compare-test-*` 账号及其会话已删除，数据库复核残留数为 0。未创建 Compare 任务，未新增模型调用。测试目录保留旧 Vite 哈希静态文件是增量同步的结果，首页只引用当前构建的 `index-GU2uu_zT.js` 和 `index-BSExzTi5.css`。
- 生产隔离复核通过：生产 API/Worker 仍 active，生产 8010 仍监听；生产 Compare renderer 文件时间和 PID 未因本次测试发布变化。本条只证明隔离测试环境发布与页面入口验收，不替代真实测试合同的 Worker/model/DOCX 交付验收。

## Frontend visual remediation checkpoint (2026-10-25, published and publicly verified)

## FL-D260 Compare reader implementation checkpoint (2026-10-26, local only)

- 已实施未发布：`frontend/src/pages/Compare/ComparePage.tsx` 将文档区与差异导航拆为桌面右侧独立 rail；rail 自身滚动，正文左右 pane 保持独立滚动。差异点击通过 `data-diff-id` 和目标相对 pane 坐标更新 `scrollTop`，不再使用 `scrollIntoView()`；移动端在目标仅存在另一侧时自动切换，双栏滚动加入锁避免递归联动。
- 已实施未发布：`frontend/src/styles/app.css` 调整 Compare 正文字号至 15px，增加中文合同字体、段落段后距、标题层级、列表、表格、页边距和 1440/768/390 布局；`fundlex/compare/presentation.py`、`fundlex/compare/parser.py`、`fundlex/compare/models.py`、`fundlex/compare/render.py` 现在解析并投影 DOCX 段落缩进/对齐/间距/页边距、编号、run 粗体/斜体/下划线/删除线/字号/颜色/字体/上下标，并保持差异坐标不变。当前能力仍是 Word-like 连续阅读投影，不代表完整 Word 分页还原。
- 验证：前端 `npm run typecheck`、`npm run lint`、`npm run test -- --run`（4 files / 9 passed）、`npm run build` 和 `git diff --check` 通过；`PYTHONPATH=. .venv/bin/pytest -q tests/test_compare*.py` 为 73 passed、5 skipped、1 个现有 Starlette/httpx deprecation warning；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/pytest -q tests/browser/test_frontend_v2.py` 为 8 passed，包含长文 pane 内定位、目标进入可视区、外层 `window.scrollY` 保持不变和移动端单侧差异自动切换夹具。
- 当前工作区：未提交文件为 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`、`docs/ACTIVE_HANDOFF.md`、`frontend/src/pages/Compare/ComparePage.tsx`、`frontend/src/styles/app.css`、`fundlex/compare/models.py`、`fundlex/compare/parser.py`、`fundlex/compare/presentation.py`、`fundlex/compare/render.py`、`tests/browser/test_frontend_v2.py` 和 `tests/test_compare_render.py`；生产静态资源仍为上一轮 `b78dc4a`/`4bad293` 发布版本，未发布本轮改动。
- 下一动作：保留本轮本地证据，继续补充真实 renderer 视觉截图和复杂表格/页眉页脚覆盖判断后，再进行受控发布决定；真实公网 Compare 新任务尚未创建，未新增模型调用。

- 本轮针对 FL-D252–FL-D256 的源码修复已提交为 `b78dc4a59e0b8be4c5c3c7b4979484e7a6a50a5a`，推送到 `origin/refactor/backend-engine-finalization`，并已完成前端静态资源受控发布。涉及文件：`frontend/src/components/layout/AppShell.tsx`、`frontend/src/pages/Compare/ComparePage.tsx`、`frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx`、`frontend/src/pages/Guides/index.tsx`、`frontend/src/pages/Settings/index.tsx`、`frontend/src/styles/app.css` 和 `frontend/tests/components.test.tsx`；既有其他工作区改动未回退。
- 已实施：浅色顶栏消息/退出按钮可见性、统计卡相邻 margin 隔离、Compare 三种后端差异 class 解析、差异类型颜色、覆盖警告逐项列表和长标识断行、Compare 任务表移动端宽度隔离、帮助弹窗 Tab/Shift+Tab 焦点循环、Escape 关闭与焦点恢复、背景 `inert`、合同例外稳定短 ID/规则/位置/诊断来源/证据展示、设置能力值中文映射和指引上传中文文件控件。
- 候选构建已发布：`frontend/dist` 与 `/opt/fundlex-recall-first/frontend/dist` 的资产 SHA-256 一致：`index.html`=`8a1cb7f50066dca6450d4a77c080ca71a99caddaafb8818891993bf9cacca0c9`、`assets/index-DgSYi7V7.js`=`a64f599ba6e405767e680f829c37a9db4e2e567bcc9611846787f7945d580091`、`assets/index-CbzfypI-.css`=`4673c786f89d28f968725458e839088edf1d7026011964d0342f157339f22353`。生产备份为 `/tmp/opencode/fundlex-frontend-publish-20261025-121730/deployment-dist-before.tgz`，发布证据为 `/tmp/opencode/fundlex-frontend-publish-20261025-121730/deployment-evidence.json`。
- 验证已完成：`npm test -- --reporter=dot` 为 4 个文件/9 项通过；`npm run typecheck`、`npm run lint`（零 warning）、`npm run build`、`git diff --check` 通过；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` 为 8 项通过。浏览器回归覆盖真实 renderer 的 `modify/insert/delete` 形态、三类差异颜色、Compare 覆盖警告、帮助弹窗焦点循环和背景 inert。
- 三视口本地视觉证据在 `/tmp/opencode/fundlex-ui-fix-visual-20261025/`：`visual-data.json` 记录 1440、768、390px 的 document/body 宽度分别等于 viewport；覆盖警告在 390px 容器宽 320px、内容 `scrollWidth` 318px；差异 computed background 分别为修改 `rgb(255, 240, 182)`、新增 `rgb(217, 241, 223)`、删除 `rgb(247, 216, 216)`；帮助弹窗 Shift+Tab 到“知道了”、Tab 回到关闭按钮、Escape 后恢复“帮助中心”焦点。截图包括 `compare-{desktop,tablet,mobile}.png` 与 `help-{desktop,tablet,mobile}.png`。
- 公网验证已完成：`/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261025/result.json` 通过真实登录、消息、帮助、`/tasks`、`/tasks/new`、`/guides`、`/settings`，1440/768/390 三视口无横向溢出，页面错误、控制台错误、静态/API 404 均为 0。针对性证据 `/tmp/opencode/fundlex-public-frontend-fix-20261025/result.json` 确认白色顶栏按钮为品牌深色，设置能力值和指引上传中文控件生效，帮助 Shift+Tab/Tab、背景 inert、Escape 后焦点恢复均通过。当前公网账号没有 Compare 任务，因此没有为本轮新建任务或新增模型调用。
- 当前边界：D252 的指引可用版本长文件名尚未在公网已有数据上单独复核；D254 的事项是否应业务归并仍需产品/报告数据契约决定；屏幕阅读器合规和 Compare 超长差异清单性能建议尚未验收。普通合同 D01–D20、G15 和选择版产物问题继续按 FL-D240–FL-D243 阻断。
- 下一条可执行动作：保留本次发布备份和公网证据；如需验证 Compare 本轮类型颜色，使用既有生产 Compare 真实链路证据或在获得明确测试预算后创建新任务，不在本轮追加模型调用。

## Frontend V2 continuation checkpoint (2026-10-25, post-publish real acceptance)

- The current React V2 candidate was published as a frontend-only release at 2026-10-25 07:43 CST. Production backup: `/tmp/opencode/fundlex-frontend-publish-20261025-074321/deployment-dist-before.tgz`; byte evidence: `/tmp/opencode/fundlex-frontend-publish-20261025-074321/deployment-evidence.json`. Candidate and production SHA-256 match for `index.html` (`1a61614146d2c0d37e45e92876ab2d5f97b2641ace883a68b15118bd658c1518`), `assets/index-DYLFV7Bw.js` (`172d6479b38f5c5ae3c505df94a81922e52d0ce4847c84a0ea457d8749bbcacd`) and `assets/index-BdkF_0-u.css` (`15ce316f6e92f992cb8712da29093aab08cbf76cc811d23f986f18f00fcbe5ea`). API was restarted; Recall Worker PID stayed `3107909`, and API/Recall Worker/Compare Worker were active after publication.
- Real production React Compare acceptance completed through HTTPS login → DOCX upload → seal → persistent Compare Worker → result viewer → report download. Evidence: `/tmp/opencode/compare-production-react-v2-e2e-20261025/report.json` and the downloaded report in the same directory. The result contained 2,772 differences (451 modify / 1,238 insert / 1,083 delete), status `incomplete` with explicit unsupported header/footer/drawing coverage warnings, 390px left/right pane switching, next-difference navigation and a 3,189,696-byte report download whose SHA-256 is `0f39d4d3655d773722dccaade57d9518fd2ed8f609d6ebf632f7433e85643bbc`; page and console errors were zero.
- A real ordinary contract acceptance also completed against the published frontend and persistent production Worker/model. The current run is task `8e3767e727344ecbbebc76ee95ad2b20`, document `2acd8583cea340fca1da964914ab39aa`; task status is `completed`, job status `succeeded`, but delivery remains `incomplete` with 6 unresolved G15 verification items. It used 27 model HTTP attempts and estimated `$0.02525925`; `working_final` SHA is `d823a5c6a8a9d3eb4c85b66530513121b9525644429ec277f699a16b9a0b2e7d` and `working_redline` SHA is `3e7fb5f140fab1d1dfd4aed007bc98e90146f8e609abb5fbbd675e898b0b8e99`, both matching report hashes. The DOCX packages were valid and changed from the source; Review exposed 19 revisions and no page/API 404s. A follow-up task `add3f5e6d5f049eeb305c1e4a1ce81d9` / document `186228a5c3d645f188083f87f2095e26` also reached Review with 19 revisions, but its selection generation did not show `已生成选择版合同` within 60 seconds and produced no selected download. Selected-artifact availability remains unverified; evidence is `/tmp/opencode/fundlex-production-v2-e2e-selected-20261025/e2e-3lopn3fjl7yl/result.json`.

- React Compare parity review added previous/next pair navigation to `frontend/src/pages/Compare/ComparePage.tsx`; first/last pair buttons are disabled and switching resets the mobile reader to the original side. AppShell help-dialog close no longer performs duplicate focus restoration; the close handler remains the single restoration path.
- Browser evidence now includes the 390px Review flow and fixture-backed Compare result view. `FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q`: **8 passed**. The Compare case verifies two result pairs, diff markup, mobile side switching, pair navigation, viewport bounds, page errors and console errors.
- Serial frontend checks pass: `npm test -- --reporter=dot` (**4 files / 9 passed**), `npm run typecheck`, `npm run lint`, `npm run build`; Compare API/Auth/Worker focused tests **17 passed**; `git diff --check` passes. The first Compare browser attempt had an async rendering wait race and was corrected to wait for the visible pair-navigation button before the final 8-test run; recorded as FL-D248 and not treated as a product failure.
- The published frontend is now the current candidate. The isolated browser Compare result and focused tests remain regression evidence only; the real Compare Worker/DOCX evidence above is production acceptance evidence for this release. Ordinary D01–D20 and final ordinary-user delivery remain blocked under FL-D240–FL-D243.
- Next executable action: on a future authorized real run, capture the selection mutation HTTP status/error body and, after a successful response, poll and download `selected_final`; preserve the explicit G15 incomplete state and do not change the fixed D01–D20 gate.

## Production visual audit checkpoint (2026-10-25)

- Completed a screenshot-first audit of `https://fundlex.club` using Playwright Chromium with the temporary Chinese font configuration `/tmp/fundlex-ui-fontconfig/fonts.conf`. Captured 43 current production screenshots at 1440×900, 768×1024 and 390×844 covering login/register, tasks, new task, guides, settings, task/document detail, notifications/help, Review and Compare. Audit data and screenshots are under `/tmp/opencode/fundlex-visual-audit-20261025/`; existing E2E sessions were scoped for the run and revoked afterward; no model calls were made.
- Interaction evidence recorded 14 primary checks plus read-only follow-up DOM checks with zero page errors and zero console errors. Confirmed Review pending generation guard, bulk decision persistence after reload, mobile tabs/back navigation, Compare difference navigation, mobile side switching, empty upload validation and paired-pane scroll behavior. The help dialog closes on Escape and restores focus, but Shift+Tab moves focus outside the dialog; this is recorded as FL-D253.
- Visual findings are recorded as FL-D252–FL-D256: invisible topbar actions, mobile information density and statistics-card spacing (FL-D252), missing dialog focus trap (FL-D253), visually duplicated/unexplained exception rows with report-level source now verified (FL-D254), long unsupported-content identifiers in the 390px Compare warning (FL-D255), and Compare difference types losing their class and falling back to one yellow mark color because the frontend parser expects `compare-diff-*` while the real renderer emits `compare-diff modify/insert/delete` (FL-D256). These are audit findings only; no application code was changed or deployed in this audit.
- The audit uses the current published frontend and preserves the existing incomplete contract/Compare states. It does not establish accessibility compliance, fix the findings, or change the ordinary D01–D20 delivery gate.

## 当前源码候选快照断点（2026-10-25）

### 2026-10-25 G05/G16/G21 边界修复续接点

- 本轮在工作区继续完成三类 operation/site 生命周期修复：G05 absent coverage 仅按自身 operation 计入；G05:0 替换在旧文和新文均缺失时保持未证明，G05:2 仅在同一份额类别设置业务站点形成独立 absent proof；G16 duplicate-copy 先 clause-end rebinding，再按物理 clause 末端判断是否可复制；G21 适用 noop 的 satisfied target 从可审计/可编辑目标退出，同时保留 operation coverage，G22 同段 operation 独立继续。
- 新增回归覆盖实际 DOCX 形态：D19 p130 的 G05:0/G05:2、D20 p804-p806 与 p1259 的 G16 站点边界、G21/G22 同段审计生命周期。定向回归 **141 passed**；完整 `PYTHONPATH=/home/opencode/fundlex .venv/bin/pytest -q` 为 **1476 passed / 48 skipped / 2 warnings / 296.41s**。`compileall` 与 `git diff --check` 通过。
- 证据和问题登记：FL-D257、FL-D258、FL-D259 已追加到 [`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`](DETAIL_ISSUES_AND_RESOLUTIONS.md)。历史 D19/D20 report、DOCX、Replay、labels、gold、scorer 和评测账本均未改写。
- 本轮修复仍只存在于 dirty 工作区，未重新冻结、未发布、未重启生产服务、未新增真实模型请求；snapshot-20 build `06ef07cc...` 仍不包含本轮修复。D01-D20 当前固定分母 gate 仍为 0/20，G06 未授权语义和评测预算缺口仍按 FL-D240–FL-D243 阻断。
- 下一条：在预算与发布条件满足后，先以包含本轮修复的新候选受控冻结/发布，再真实复测受影响 D19/D20；逐 operation 核对 source site、实际 DOCX、Claim Replay、audit、报告、修订接受/拒绝等价和授权下载。不能把本轮零 HTTP/回归证据计为新的真实 Worker/model 交付。

- FL-D246 已修复并验证：`project_unresolved()` 对无 operation/site 身份的运行级 coverage 缺口保留原 `kind="coverage"`；有身份但无法绑定的证据仍转换为 `orphan_evidence` 并 fail closed。三项直接回归 **3 passed**，定向后端回归 **286 passed**，完整 `tests` 两次均通过：**1467 passed / 47 skipped / 2 warnings**，分别为 289.47s 和 284.79s。
- 当前精确候选已冻结于 `/tmp/opencode/operation-validation-20261024/snapshot-20`，build `06ef07cc443a61ebb50009d7e8ce8c0280d08d70d0190d350e8d92a02f78f75b`；178 个 `fundlex/` 与 `tests/` Python 源文件的启动 manifest 与测试后哈希一致。启动 manifest 为 `/tmp/opencode/operation-validation-20261024/current-candidate-full-test-start.json`，结果为 `/tmp/opencode/operation-validation-20261024/current-candidate-full-test-result.json`，上下文为 `/tmp/opencode/operation-validation-20261024/run_context-20.json`。
- snapshot-20 是**未发布候选**：工作区 `fundlex/api.py` SHA `c0459fd16573a2d2084be900156dc10ae8df65414eda298046f5935df04b0c98`、`fundlex/tasks.py` SHA `028e858c0706d15392c4eba5ec33dd3ade438fde00ecd44889d6105587bb546b`；生产目录对应 SHA 为 `8cdd1507fcccacf2b1ec596a4bfdf69daf623e35ea75bca2ba8c000c85416191`、`3e7162fdbcee2daa8bb0e45506f71d41f20990cc9350aae2ed6b1882b7de6063`。未部署、未重启服务、未新增模型调用。
- snapshot-20 冻结时共享 ledger 为 **1701 requests / `$1.64408310` / reserved 0**；当前仍有 299 requests / `$0.35591690`，但不足以按固定分母完成剩余开发集的估算需求。20 份开发集、holdout、正式发布和最终普通工作台 E2E 继续按 FL-D240–FL-D243 阻断。
- 当前下一条：若取得新增预算及发布授权，先对候选 API/tasks 做受控发布并核对生产字节，再按 snapshot-20 固定源码执行 D01–D20 真实登录→上传→seal→持久 Worker/model→DOCX→Review→授权下载和独立业务复核；未取得前不启动无法完成固定分母的真实批次。

## 当前 target-20 对账断点（2026-10-25）

- target-20 D06 已完成真实登录→上传→seal→持久 Worker/model→结果页→授权下载；snapshot-19 build `e2ac0f14429de4fdd71e631d10c18b27f1366c8337e797b4c834b5adf6611229`，82 targets 已处理，delivery 为 `incomplete`。机械下载核验 1/1 通过；final SHA `7503c5e61cf1602240b9c3843d5e7ebd7c9b29029d969b2e04485fcd97a5e7bd`，redline SHA `01de404f1fdc36c1a74e1a8fb0d3eb6b00613ffd4463b178e4f8e70bda2fedeb`。
- target-20 D06 的 corrected 独立业务复核 `/tmp/opencode/operation-validation-20261024/target-20-D06-independent-business-review-corrected.json` 已通过 25/25 断言，19/19 实际变化段通过。初始误报证据保留在 `/tmp/opencode/operation-validation-20261024/target-20-D06-independent-business-review.json`，对应 FL-D239；未修改真实 report、artifact 或历史失败文件。
- G02/G04 p98、p131、p231 的 operation/site coverage 均为 `ALREADY_SATISFIED`；G11 p228 为 `ALREADY_SATISFIED`、p229 为 `ARTIFACT_VERIFIED`。G12/G13、G15/G16/G17、G22 和 sweep findings 已由实际 DOCX、operation ledger 与 Claim Replay 逐项复核。G06 仍因 p280 的单向 Y 类转换语义变体保持 `CLAIM_OPERATION_UNPROVEN` / `semantic_delete_variant_present`，delivery gate `UNRESOLVED=1`、blocking_unresolved=2。
- 共享 ledger 当前为 **1701 requests / `$1.64408310` / reserved 0**，按状态 completed=1698、failed=2、abandoned=1，剩余 **299 requests / `$0.35591690`**。target-19 D04 的最近独立通过证据属于 snapshot-18，target-20 D06 属于 snapshot-19；其余开发集主要证据来自更早快照，尚未形成同一冻结版本的 20 合同 gate。按 FL-D240 保持 holdout、正式引擎发布和最终普通工作台 E2E 阻断；不得因目标计数 `unresolved=0` 或 mechanical pass 宣称交付完整。
- 当前下一条：在不新增预算授权前，不再启动无法完成固定分母的随机真实批次；先保存本断点和集中问题记录，若预算获授权则冻结新的、与 snapshot-19 一致的开发复测批次，按固定 20 合同分母继续真实运行并逐合同独立业务复核。
- 当前服务只读核验：`fundlex-recall-api.service` 与 `fundlex-recall-worker.service` 均为 active；生产 API 由 systemd 配置监听 `127.0.0.1:8010`，`GET /api/capabilities` 返回 200。当前 8013 由独立 `fundlex-test-api.service`（工作目录 `/opt/fundlex-test`）提供隔离测试服务响应，不能作为生产 API 证据；生产健康和真实验收仍以 8010/公网入口为准。该端口细节登记 FL-D243。
- D01-D20 固定分母对账已保存于 [`docs/evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md`](evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md) 和同目录 JSON；当前 snapshot-19 gate eligible 为 **0/20**。已有 snapshot-19 证据仅 D06，D04 独立通过是 snapshot-18；历史 snapshot-05 复核中 D02、D16、D17 通过，D18 失败，其余 15 份仍 pending。保留 D06 并补跑其余 19 份的历史消耗基线为约 602 requests / `$0.60031875`，相对当前余量缺口约 303 requests / `$0.24440185`，不含重试和 G06 修复调用；对应 FL-D241/FL-D242。

## 最新引擎验证断点（2026-10-25）

- FL-D237/FL-D238 已实施：G02/G04 完整收费组中的旧单类成员不再被 residual 门禁误判；p98 同段类别枚举 sweep 只有在同一段完整收费组 operation proof 通过时才可由 artifact proof 消解。新增回归与最终全量均已通过：**1459 passed / 47 skipped / 2 warnings / 291.27s**，`git diff --check` 通过。
- snapshot-19 已冻结于 `/tmp/opencode/operation-validation-20261024/snapshot-19`，build `e2ac0f14429de4fdd71e631d10c18b27f1366c8337e797b4c834b5adf6611229`，测试 manifest 为 `g02-g04-postpatch-full-test-start.json`，178 个 Python 源文件一致。已受控发布到 `/opt/fundlex-recall-first`，API/Worker active；工作区、snapshot-19 和部署目录的 `api.py`、`tasks.py`、`effects.py`、`recall_pipeline.py` 字节一致。

- FL-D231–FL-D234 修复后的最终源码回归已通过：**1458 passed / 47 skipped / 2 warnings / 288.47s**；`git diff --check` 通过。当前修复版 snapshot-18 已冻结于 `/tmp/opencode/operation-validation-20261024/snapshot-18`，build `e42254705a296954284d7fd3831543c38db1894ec1966bf3d7462cf85be3c39a`，上下文 `run_context-18.json`，源码 manifest 与最终回归启动 manifest 一致。
- snapshot-18 冻结时评测 ledger 为 1621 requests / `$1.54847790` / reserved 0；target-19 已完成 D04/D06 真实任务，使用独立 `data-19`，不复用 target-18。D04 complete，D06 incomplete；当前总账以本文件顶部 target-20 对账断点为准。
- snapshot-18 已通过受控发布同步到 `/opt/fundlex-recall-first`，API 与 Worker 均 active；工作区与部署目录 `fundlex/api.py`、`fundlex/tasks.py` SHA 一致，`/api/health` 返回 200。`/api/capabilities` 未认证请求返回 404，属于当前身份门禁行为；尚未以此接口结论替代登录验收。
- D04/D06 当前源码零模型真实原件重建已通过：`/tmp/opencode/operation-validation-20261024/offline-d231-d234-real-current/result.json`；D04 G12:1/G13:0 原子 component、D06 G11 p229 窄 continuation、Claim Replay、接受/拒绝修订等价均通过。该证据不替代 target-19 真实 Worker/model 交付。
- target-18 历史真实产物、报告和失败 Replay 保持不变；holdout、正式发布结论和最终普通工作台 E2E 仍受 20 份开发集完整业务门禁阻断。
- target-19 已完成：后台 shell `sh_16ead959c001MZSAUWU9cVPMyW` 使用 snapshot-18、独立 `data-19` 和共享 ledger，真实 D04/D06 登录→上传→seal→持久 Worker/model→结果页/Review→授权下载路径均已核验。D04 complete；D06 incomplete，报告和历史产物保持不变。
- target-20 已完成：使用 snapshot-19、独立 `data-20` 和共享 ledger，仅 D06；真实链路、机械核验、账本、Claim Replay/audit、p98 sweep、G02/G04/G06 逐站点实际差异及接受/拒绝修订/hash 均已核对。G06 单向 Y 类转换没有业务授权，继续保持未完成。

- 前端最终候选已完成受控公网发布并通过复验：只同步 `frontend/dist/index.html`、`index-BkJEWrna.js`、`index-ko73k-L5.css` 到 `/opt/fundlex-recall-first/frontend/dist`，只重启 `fundlex-recall-api.service`，Recall Worker 保持运行。工作区、部署目录和公网引用的 SHA-256 分别为 `6019229d8c9df8bd3e9e8b55fbfe4a4f8f0a46201fbc612088acbd4418c4b5c2`、`bc87d8701dc0bfaaaca00c121528942975253ac77a83c46a3b26fa03cf709ae3`、`a7f472e4b4dd426cb4cd2f8e91ca656a6d4528dd333930783274e08dcfc7167a`。备份为 `/tmp/opencode/fundlex-frontend-publish-20261024-180136-responsive-fix/deployment-dist-before.tgz`。
- 最终公网 smoke `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json` 已通过：真实登录、消息、帮助、`/tasks`、`/tasks/new`、`/guides`、`/settings`、1440/768/390 响应式、原地 1440→768 收缩、页面/控制台错误和静态/API 404 均通过或为0。该 smoke 只证明当前前端壳层与现有 API 可用，仍不能替代下面的真实合同模型交付验收。

- FL-D227全量已结束，结果为 **1 failed / 1451 passed / 46 skipped / 2 warnings / 288.10s**；源码manifest匹配，唯一失败是`tests/test_append_applicability.py`的FakeParagraph缺少真实段落结构字段。已补齐替身并登记FL-D228。
- FL-D228全量已启动，日志`/tmp/opencode/operation-validation-20261024/d228-full-pytest.log`，启动manifest`d228-full-test-start.json`，build为当前源码build。该运行启动后又完成G12边界收窄和新增回归，因此无论结果如何都必须按最终源码/测试manifest重跑完整回归。
- D228中间结果已结束：**1452 passed/46 skipped/2 warnings/284.20s**；启动manifest与当前源码不一致（启动后收窄G12边界并追加测试），不能冻结。最终manifest重跑已进入下一步。
- FL-D228增量定向回归通过：G12/Claim/append相关62 passed；真实D04 p198零模型流程`/tmp/opencode/operation-validation-20261024/offline-d228-g12-real/result.json`通过，G12固定政策写入、G13 7日/1.5%句保留、Claim与接受/拒绝修订等价均通过；D227 G03/G16真实D04零模型结果`offline-d227-real/result.json`通过。无HTTP。
- 当前源码仍未冻结、未运行新的真实任务。target-17历史产物保持不变；holdout、引擎发布和最终普通工作台E2E继续阻断。D228结束后下一步：记录结果→按最终manifest重跑全量→冻结新snapshot并核验API/tasks与生产字节一致→重新登记预算后真实复测D04/D06。
- 最终manifest重跑已通过：**1453 passed/46 skipped/2 warnings/280.23s**；177个Python源文件manifest与启动时一致，build `e4ae767880625a3cf090fd500283facd28caab2f696e96c35551ab74b65dc172`。已冻结`/tmp/opencode/operation-validation-20261024/snapshot-17`，上下文`run_context-17.json`；冻结时API/tasks与生产一致。
- target-18已预登记：D04/D06开发集真实普通工作台路径，预计80 HTTP/$0.08、最坏200/$0.24，账本起点1552/$1.47498705/reserved0，剩余448/$0.52501295。发布新快照后才启动；target-17不得复用，holdout/正式发布/最终普通工作台E2E继续阻断。
- 生产账本只读核对为26919 requests/`$21.81123075`（completed26874、failed32、abandoned13），与本轮隔离ledger不同；target-18沿既有评测协议使用`/tmp/opencode/operation-validation-20261024/ledger.sqlite`，不混算、不重置。
- FL-D229：首次target-18启动参数误传为`run dev target-18 D04 D06`，包装器在`p6_run`参数解析阶段退出，未创建任务、未登录、未上传、未调用Worker/model；shell `sh_16d542a77001GWC6jvid0LtxXr`，ledger仍1552/$1.47498705/reserved0，target-18目录不存在。下一步使用正确接口`dev target-18 D04 D06`重新启动。
- FL-D230：生产普通工作台验收脚本曾错误要求登录页品牌具有 heading 角色；React V2 登录页实际使用品牌 `<strong>`，该失败发生在注册前，不能作为产品或模型链路失败。已登记并从独立输出目录重新执行生产真实合同验收，等待新任务结果。

## 最新前端发布与公网验收（2026-10-24）

- **最新用户硬性要求**：允许在原版基础上做细节优化，但绝对不能丢失原版任何功能。React V2 后续必须先完成原版功能/入口/品牌资源/响应式基线矩阵，逐项证明等价可达；优化不得删除、隐藏、改成绕路入口或降低原版能力。矩阵未完成、任一硬性功能缺失或多视口不可用时，不得进入下一阶段或发布。

- 按用户“发布”要求完成 React V2 **前端静态文件受控发布**。标准整仓发布器未使用，避免将未完成的 recall-first 引擎、评测、测试和文档 dirty 改动同步到生产；仅更新 `/opt/fundlex-recall-first/frontend/dist/index.html` 和当前 Vite hashed assets，并只重启 `fundlex-recall-api.service`，Recall Worker 未重启。
- 最终备份：`/tmp/opencode/fundlex-frontend-publish-20261024-180136-responsive-fix/deployment-dist-before.tgz`。最终工作区、部署目录和公网入口引用一致：`index.html` SHA `6019229d8c9df8bd3e9e8b55fbfe4a4f8f0a46201fbc612088acbd4418c4b5c2`，`index-BkJEWrna.js` SHA `bc87d8701dc0bfaaaca00c121528942975253ac77a83c46a3b26fa03cf709ae3`，`index-ko73k-L5.css` SHA `a7f472e4b4dd426cb4cd2f8e91ca656a6d4528dd333930783274e08dcfc7167a`。
- 公网浏览器 smoke `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json` 已通过：真实登录、`/tasks`、`/tasks/new`、`/guides`、`/settings`、消息面板、帮助中心；1440px、768px、390px以及1440→768原地缩放均无页面横向溢出；`page_errors=[]`、`console_errors=[]`、静态 404 和 API 404 均为 0。公网入口和新 JS/CSS 均 HTTP 200，API 服务 active，Worker 保持 active。
- Smoke 首次发现移动端 V2 侧栏导航使页面宽度扩展至 664px；已通过窄屏纵向 shell 布局和侧栏横向滚动容器修复，重新执行 typecheck、lint、build、diff check 与公网 smoke 后通过。截图保留在 `/tmp/opencode/fundlex-public-v2-smoke-20261024/tasks-wide.png`、`new-task-mobile.png`。
- 本次仅证明前端页面与现有生产 API 的公网可用性；没有创建新的生产任务、没有新增模型调用，也不改变 recall-first 引擎发布门槛。Recall-first engine 仍受 dev-05 真实合同业务缺陷、开发集复测和 holdout 条件约束。

## 当前接续断点（2026-10-24，operation Registry/Router 当前版本）

- **正在运行，勿重复提交（2026-10-24）**：target-17 D04/D06已通过后台shell `sh_16d2e31ec001l5FWpDOa8gSz01`启动，冻结snapshot-16、独立data-17、共享ledger；等待完成通知，不轮询。日志`target-17-api.log`、`target-17-worker.log`及shell输出。下面“下一条启动”已执行，不得再跑。当前源码只在`fundlex/recall.py`和`tests/test_composite_slice_delivery.py`增加本轮G17窄parts修复，其他dirty属于既有工作；全量及冻结哈希相同。后续先`PYTHONPATH=/home/opencode/fundlex .venv/bin/python tools/evaluation/verify_downloaded_artifacts.py /tmp/opencode/operation-validation-20261024/target-17 --selection var/recall-first-evaluation/p6-current/selection.json`，再`replay_saved_case.py target-17 D04 d225planning`和D06同样（最后轮audit限制仍在），另建跨段G17业务复核与全部diff，独立账本增量对账。预算尚以run前1490/$1.40885745为基线，不把运行中值当最终。没有子agent；保留target-16旧失败和首次错误业务输出、冻结labels/scorer不改。上下文已分阶段持久保存；若压缩后先读本条、集中FL-D225/188、run_context-16再继续，勿重做真实调用或把离线通过当正式交付。总体20dev/holdout/发布/最终E2E尚未完成。
- **最新可执行动作**：G17规划修复完整回归1436 passed/46 skipped/2 warnings/278.05s，177源文件manifest匹配；已冻结snapshot-16/build `2858706c841ff88b1a75e394e1d4f225d0d6c8bcfa2ebfcb0b68252af7922889`、`run_context-16.json`，API/tasks与生产相同。另建target-17 D04/D06/data-17预算已登记：预计80 HTTP/$0.08、最坏200/$0.24，起点1490/$1.40885745/reserved0，总cap2000/$2不变。下一条启动命令`FUNDLEX_VALIDATION_SNAPSHOT=/tmp/opencode/operation-validation-20261024/snapshot-16 FUNDLEX_VALIDATION_DATA_DIR=/tmp/opencode/operation-validation-20261024/data-17 .venv/bin/python /tmp/opencode/fundlex-operation-validation.py dev target-17 D04 D06`；不要prepare/复用target-16。完成后机械下载核验、全计划Claim/audit、逐站点业务与全部diff；旧review_target16_g17.py已修正跨段及D06口径但输出固定target-16，更正版不会覆盖首次错误证据。D04 G12/G16、D06 G15及其他未决仍待独立处理；20dev完整独立分母/D07/单类别认证尚未完成。无holdout/发布、无子agent、未commit/push，工作区dirty保留。新快照不是整项目验收。
- **最新target-16终态，优先于下方历史**：D04/D06真实任务及下载结束，均incomplete（58/33、91/37 targets/unresolved），机械2/2；完整Claim false/8、false/9。G17宽survey composite被独立范围门禁拒绝，D04首副本DEL001窄删/余文保留但第二副本漏，D06两用途句漏删；排除句已合法删。已实施源operation窄parts恢复：D04/D06真实原件零模型规划各自Claim、余文保留、接受/拒绝修订等价通过，4/6 edits，证据`offline-d225-planning-real/result.json`；定向相关130 passed。下一步等待完整回归通知，核对源码manifest后冻结新snapshot，再登记预算并启动真实D04/D06复测；不放松Replay。临时业务脚本跨段漏检与D06旧排除口径已更正并保留首次输出；FL-D132/188确认ETF联接应正常修改。账本1490 requests/$1.40885745/reserved0，target-16增量67/$0.07048830（17/$0.01738935已对账为最终报告未保留的前轮请求），余510/$0.59114255，总cap2000/$2。无运行中的真实任务/子agent；未发布引擎/无holdout。分支feat/frontend-v2、HEAD fc8424aaae46e46d209ec7aa3834502136f692f8，所有已有dirty保留，无commit/push。
- **target-15 D03已完成真实交付**：真实登录→上传→seal→持久Worker/模型→结果页/授权下载完成，complete/35 targets/0 unresolved，34 HTTP/$0.02907375。机械核验1/1，final `66efdc0c6ceab948cd51a8745fc4236e275b7c7cb7a589cdadcd7afc401c8d2b`、redline `302c9805930dbc3460e51a0c2670ad989899fad85db516879ae09559e5a1dc91`，20 ins/20 del；Claim true/0 failures，audit replay 29/0/0，target-15实际diff 20/20 PASS。证据`target-15/D03/artifact-review.json`、`target-15/D03/target-15-business-diff-review.json`、`target-15-D03-d225-final-replay.json`。账本1423 HTTP/$1.33836915/reserved0，剩余577/$0.66163085。D03单合同已完成，20dev独立完整分母仍pending；下一步应登记新的D04/D06真实窄范围复测预算，验证G17 planner自动恢复独立用途句且保留D04费用支出/D06降费权限余文，再继续D07/D09/D13和完整dev审核。holdout、引擎发布、普通用户最终E2E仍被开发门槛阻断。
- **target-16 D04/D06 已登记并即将启动**：snapshot-15/data-16，预计80 HTTP/$0.06，最坏200/$0.24；预算余量足够。两份任务必须走真实登录、上传、seal、持久Worker/模型、结果页和授权下载，再逐文件核对G17窄范围、D04费用实际支出余文、D06下调/打折权限余文、报告/Claim/audit/修订/hash。run前账本1423/$1.33836915/reserved0；仍无holdout、无生产发布，D03单合同成功不能替代20dev门槛。
- **当前待通知与可直接执行动作**：唯一仍运行进程为D225最终完整tests后台`sh_16cfb1c5b0017gAN9i7cM35Ay7`，不是模型；20dev最终离线Replay已结束。最终target-14实际+旧audit重放`target-14-D03-d225-final-replay.json`为verified=true/0 failures、29 results/0 issues/0 artifact failures。启动manifest与源码再次核对相同，API/tasks字节仍等于生产，账本1389 HTTP/$1.30929540/reserved0，snapshot-15/data-15/target-15均不存在。等待通知后读`d225-final-full-pytest.log`保存结果、核对`d225-final-full-test-start.json`，通过才运行`.venv/bin/python /tmp/opencode/operation-validation-20261024/freeze_snapshot_15.py`；重验run_context-15.json文件manifest、预算及build，再`FUNDLEX_VALIDATION_SNAPSHOT=/tmp/opencode/operation-validation-20261024/snapshot-15 FUNDLEX_VALIDATION_DATA_DIR=/tmp/opencode/operation-validation-20261024/data-15 .venv/bin/python /tmp/opencode/fundlex-operation-validation.py dev target-15 D03`。勿调用prepare，不发布引擎、不跑holdout。结束后`review_target15.py`实际文件核验和`replay_saved_case.py target-15 D03 d225`（两者需PYTHONPATH=/home/opencode/fundlex）。review_target15.py仅同原件+同实际文本的target-14已审核段可复用结论，其余REVIEW_REQUIRED必须逐项读原件/指引；独立完整目标分母仍pending。branch feat/frontend-v2，HEAD fc8424aaae46e46d209ec7aa3834502136f692f8，所有并行dirty保留，尚未commit/push。无子agent。D03真实预算沿用40 HTTP/$0.04预估、100/$0.12最坏，余611/$0.69070460。下一阶段应完成D04/D06真实窄范围恢复、D07费用证书、D09/D13单类别认证和20dev独立分母/完整业务审核，达门槛才留出/发布/普通用户最终E2E。上下文已分阶段保存；不要因本轮工具通知把目标替换为单纯报告测试结果。
- **等待最终全量期间新增证据**：最终20dev只读重放已结束，D02/D11/D19合法G17措辞过拒消除；D04/D06独立余文损失、D18重复prefix保持失败。D04/D06原件窄切片DOCX重建`offline-d225-real-source-slices-verified/result.json`两份proof/余文保留/仅目标改变/接受拒绝修订等价全部通过，0 HTTP；仍非新真实任务。最终全量继续等待`sh_16cfb1c5b0017gAN9i7cM35Ay7`通知；源码未在测试期间修改，freeze/run按下一条。target-15后还要真实D04/D06验证规划召回能恢复窄边界，不以拒绝替代完整修改。临时重建脚本首次source绑定失败目录保留，已通过正式build_docx_edits修正。
- **D225最终增量全量运行中（优先于以下历史）**：首轮1428 passed/46 skipped/2 warnings/271.62s，manifest匹配，结果d225-full-test-result.json。随后已补有限措辞等价（佣金连接词/持有人简称/省略使用范围/分号），226项定向通过，反向语义和独立余文仍拒绝。最新全量后台`sh_16cfb1c5b0017gAN9i7cM35Ay7`，日志`d225-final-full-pytest.log`、manifest`d225-final-full-test-start.json`，build `4bbe0bd82928f338d4cdc87b786ca4dd39ced54aeea8bcdc2d9639c35709de00`；历史20dev只读重放后台`sh_16cfb1c5c001Pj0A1KHfwDu9XN`→`dev-05-d225-final-replay.{json,log}`。等待通知，勿轮询/改源码。通过后保存结果/核对manifest→freeze_snapshot_15.py（已绑定最终日志）→重验manifest/API/tasks/账本→真实target-15 D03（现snapshot-15/data-15/target-15均不存在），预计40 HTTP/$0.04、最坏100/$0.12，账本1389/$1.30929540、reserved0/cap2000/$2。实际下载后执行`PYTHONPATH=/home/opencode/fundlex .venv/bin/python /tmp/opencode/operation-validation-20261024/review_target15.py`（会机械校验并与target-14逐段相同原文/实际文本的已审核diff比对，未相同项保持REVIEW_REQUIRED），再全计划Claim与audit核验。此脚本及最终重放脚本在/tmp不参与引擎全量源码manifest。其余开发集独立完整分母、D07及单类别认证仍未完成，生产未发布本轮引擎/无holdout。
- **D225全量等待期间发现合法措辞过拒，暂停直接freeze**：20份dev-05只读Replay已结束（`dev-05-d225-replay.{json,log}`），D04独立费用支出句/D06独立降费权限句越界删除被阻断；D02佣金“，及”、D11/D19“持有人服务费”、D11省略“使用范围”需支持有限同义差异。等当前D225全量通知，保存当前结果/source manifest，再补合法差异与反例并重跑全量；不要立刻按下条freeze/run。target-14审核旧回答重放29 results/0 issues/0 artifact failures（`target-14-d225-audit-replay.json`）；0 HTTP。当前源码未在全量中修改。
- **FL-D225修复后全量运行中（优先于以下历史）**：G17单段/composite planner与Claim Replay均从原件及自身operation完整句独立核验删除范围，跨段parts/expected_old_text等不能自授权；合法G16/G17合并保留。新增伪造provenance/parts、反向语义与实际跨段DOCX反例，229项定向通过；target-14只读完整Replay true/0 failures，`target-14-d225-source-scope-replay.json`。当前全量后台`sh_16cf55000001QvBoY3mtjs1yoV`、日志`d225-full-pytest.log`、manifest`d225-full-test-start.json`、build `27721a2f381b3fbcfbac37236f1058d1a3bcc004d6a613bfb95ca7181468742c`。勿轮询/改源码；完成后保存统计/核对manifest→freeze_snapshot_15.py（已改绑定D225）→核验账本/API/tasks→另建真实D03 target-15→实际diff/修订/hash/audit。D224最终全量1420 passed/46 skipped/2 warnings/271.52s，源manifest匹配，结果`d224-final-full-test-result.json`，该全量不含D225。账本仍1389 HTTP/$1.30929540、reserved0、cap2000/$2；新真实D03预计40/$0.04、最坏100/$0.12，未发布引擎、无holdout、无子agent/真实Worker。其余20份开发集审核/收费认证未完成，branch/HEAD与并行dirty保持。
- **最新发现FL-D225，暂停原snapshot-15启动动作**：零HTTP探测G17整段删除+伪造expected_old_text/deleted_paragraph可吞掉独立无关句，Replay错误true。target-14无该余文，不应把对抗样例当作其实际错误。当前FL-D224最终全量继续等待通知、勿改源码；结束后需先补G17独立源授权（自身完整用途/排除句及合法跨段parts）和反例，再重新全量/manifest，不能按下面旧下一动作立刻freeze/run。集中记录已登记FL-D225未修复。
- **FL-D224最终全量重跑（优先于下一条）**：首轮完整回归1 failed/1417 passed/46 skipped，失败为合法自定义单句G15支付变体被过拒；新增单句source-bound支持与额外第二句/顺延不授权反例，相关233 passed。当前最终全量后台`sh_16cec1cb6001SVz0DMNrQuXjPC`、日志`d224-final-full-pytest.log`、启动manifest`d224-final-full-test-start.json`，build `9ed657267458d3fdd18a700a682576f7e5ec359e7535059799905648e01d6813`。不要轮询或修改源码；通过后运行`/tmp/opencode/operation-validation-20261024/freeze_snapshot_15.py`（强制源码哈希与该最终全量一致），重验manifest/账本→`FUNDLEX_VALIDATION_SNAPSHOT=.../snapshot-15 FUNDLEX_VALIDATION_DATA_DIR=.../data-15 .venv/bin/python /tmp/opencode/fundlex-operation-validation.py dev target-15 D03`另建真实复测。已预登记D03预计40 HTTP/$0.04、最坏100/$0.12，共享cap2000/$2。实际target-14全部20变化段复核已落`target-14-d224-business-diff-review.json`，为预测后开发审核；独立完整分母未完成。其余预算/无holdout/不发布约束不变。
- **FL-D224最新断点，优先于下列历史**：merged effect绕过FAIL unit已移除；G15 planner/Replay从operation独立重算删除范围；143项定向通过。audit接受BEFORE-only丢失引文，但经本地独立授权证明的合法G17删除仍可闭合，新增实际DOCX G16/G17合并与丢失核对句反例，124项相关通过。target-14只读完整Replay及既有audit重放均0 failures/issues，证据`target-14-d224-source-scope-replay.json`、`target-14-d224-audit-replay.json`；0新增HTTP，不代表新真实任务或独立业务审核。当前完整`tests`后台`sh_16ce5d301001xtf0RCLtCjneLJ`运行中，日志`d224-full-pytest.log`、启动manifest`d224-full-test-start.json`，build `d7dc3484d26e637a37d44cec07e492b5c94872845a928f677698fea022bc9683`；勿轮询或改源码混入该测试版本。通过后先核验源码哈希/预算，再冻结snapshot-15并另建真实D03及受影响G15样本。共享账本1389 HTTP/$1.30929540、reserved0、cap2000/$2；无真实Worker/子agent、无holdout、未发布引擎、所有并行dirty保留。branch/HEAD为feat/frontend-v2/fc8424a。FL-D208单类别、D07收费补证及全20份独立分母/实际DOCX审核仍待完成。
- **当前接续，优先于下列历史**：target-14已真实结束，snapshot-14 build `0f4fd6e2f3f701d1209900b4cc712470a108650f4694b6e0e2db37eb36d61117`，33 HTTP/$0.02573610、报告complete/34 targets/0 unresolved，机械1/1；共享账本1389 HTTP/$1.30929540，无reserved。接续重新读指引73/75–89段，纠正“p753/p1221必须保留使用范围句”误判：G17明确授权删除该句，G16可以与该独立删除合并，不能按错误审核恢复旧文。FL-D224登记审核误读及effect的planned_matches绕过FAIL unit缺口；下一动作是收紧merged effect证明并补实际DOCX正反例、完整target-14重放。当前无新真实批次/子agent、未发布引擎、无holdout，所有并行dirty保留；分支/HEAD仍feat/frontend-v2/fc8424a。此轮尚未改代码、尚未新增HTTP；不得把纠正审核等同全20份开发集通过。
- **最新snapshot-12/target-12（优先于下列历史）**：最终引擎全量 **1404 passed /44 skipped /2 warnings /286.21s**。冻结首次因唯一变化`tests/browser/test_frontend_v2.py`停在复制前；补验修正新增Compare测试漏点侧栏（FL-D219），显式Chromium **5 passed /10.90s**。`freeze12-supplement-evidence.json`记录精确差异及日志哈希，原1404全量证据保留，其余fundlex/tests文件集合及哈希未变。snapshot-12已冻结，build `d441ec1706668bcdcafb0fcf7cfef9798d5879bb3a22871c1f9e84963c1fb16b`，2418文件manifest重验、API/tasks与生产一致。真实`target-12` D03已启动，独立`data-12`，日志`target-12.log`，后台shell `sh_16ca07d6c001B2H2c12uth4Xap`；等待通知，勿轮询/重复提交。预算起点1267 HTTP/$1.19796015，无reserved，cap2000/$2/并发1、每合同192保持，预计33–40 HTTP/$0.03。完成后机械核验、p92 raw130插入/55号原文、p209无重复/p211编号、全部diff、G15/G16/G17及修订/report/hash核验。未发布引擎、无holdout、无子agent，保留全部并行dirty。
- **target-12 D03终态更新**：真实任务已完成但`incomplete`，42 targets/39 unresolved，52 HTTP/$0.05397930；共享ledger为1319 HTTP/$1.25193945、无reserved。下载机械核验1/1通过：final SHA `c593ea2a3b6cdefabed2ec8a031743abba0475ee61380c324286cb7fb592e7b3`、redline SHA `496b8ad8af0c75bde59d9c15b27dd3e8d2a744d683cf066bdd07287cca4e136b`，接受/拒绝修订、无残留修订和plan一致。实际业务复核相对target-11新增p92/p121/p209/p211/p752/p753/p925/p1221/p1318，target-11的G01 raw130/55号原文仍被验证；但新模型结果删除G16内容、回退G05语义、G22未完成，不能沿用旧审核通过。G16定向检查14/16，p751/p1219的完整政策计数失败。FL-D220已登记：D12 G09部分splice/Replay错误PASS；FL-D221已登记：D03收费引文认证部分仍UNKNOWN。局部G09/收费回归当前100 passed；源码已继续变更，snapshot-12不能作为修复后快照，未发布/无holdout。
- **FL-D220/221修复后回归**：`template.plan_g09_splice()`和G09 Replay现在要求净值与“扣除或加上相应的费用”两个完整效果，并支持`并扣除其他相应的费用`变体；`fee_evidence`支持“申购费用由投资人承担”和“的年费率计提”。定向156 passed；完整`tests`回归后台`sh_16caffd59001essR5lR6mEcfYO`，日志`post-d220-d221-full-pytest.log`，完成通知前勿重复运行。通过后需重新计算build/源码manifest、冻结新快照并另建真实D03；target-12仍是修复前真实证据。
- **FL-D222修复后回归**：同一G16费用条款若G16没有可执行计划，`guard_g17_deletes_against_g16()`会撤回G17删除并将其记为unresolved，避免删除应追加内容的源段；合法G16+G17合并与阻断反例受影响回归184 passed。完整`tests`回归后台`sh_16cba2c780012UvdfT6JwxpV8z`，日志`post-d222-full-pytest.log`，完成通知前勿重复运行。通过后重新冻结、再做真实D03；target-12仍保留为修复前证据。
- **target-13 D03终态**：snapshot-13真实Worker/模型、登录/上传/持久任务/授权下载已完成，`incomplete`，40 targets/52 unresolved，37 HTTP、$0.03161985；共享ledger现为1356 HTTP/$1.28355930，无reserved。下载机械核验1/1通过，final SHA `5810c37e6d3922ad0779682938782653637b068a0ed06dd4a324d28d49b1a06c`、redline SHA `214ea725352452d9df99b393e3d841066229f62f9970c32d735ed2d33083b3ea`。实际改变12段：G09 p210完整效果通过，G01/G03、G05、G06、G12/G13、G14、G15、G18实际修改与plan一致；收费A类引文仍省略原件p211“4、”，严格门禁保持UNKNOWN，G08/G11/G22未交付。FL-D222阻断真实生效：p752/p753、p1220/p1221的G17未单独删除，原文保留并标为`G17_BLOCKED_G16_UNPLANNED`/`CLAIM_OPERATION_NOT_PLANNED`，避免target-12错误半成品。target-13不是完整D03或开发集通过。
- **FL-D221来源驱动引文修复（当前未冻结）**：`facts_from_value()`新增窄范围source-bound修复，仅当模型引文以“本基金”开头、原件同一收费条款存在编号前缀、修复片段独立证明预期极性时补回原件完整引文；其他情况继续UNKNOWN/CONFLICT。新增编号收费条款DOCX回归，定向147 passed；受影响/完整回归待运行。target-13不能代表该修复，必须重新冻结并启动新真实批次。
- **最新动作已完成**：FL-D216完整回归 **1363 passed /44 skipped /2 warnings /261.77s**；snapshot-10 `target-10`真实D18 complete/0，33 HTTP/$0.02434395，机械1/1、定向14/14，仅p776/p1227相对target-08删除旧顺延句。final SHA `8ac72b7c83314f4b62230a2bfef4171f7a4f2d2d5def95c666472cb8fe34861b`，redline SHA `788c9f1fba9c0fa02446b08b1735d65518cc958f1330f7b17f92092b83633e7b`。FL-D216真实样本验证解决。共享账本1234 HTTP/$1.17396345，无reserved，剩余766/$0.82603655；未发布引擎、无holdout。下文“回归运行中/快照待冻结”为历史。
- **FL-D217真实复测进行中**：G08同句边界修复完整回归 **1370 passed /44 skipped /2 warnings /258.22s**（`g08-same-sentence-full-pytest.log`）。`snapshot-11`已冻结并重验manifest，build `92880a778ab4607b713cd26da56e8e061c9283e0d26021dfd121ad81298bdd5a`，API/tasks与生产一致，账本起点1234 HTTP/$1.17396345、无reserved，隔离`data-11`。真实`target-11` D03已启动（`target-11.log`、后台shell `sh_16c873a1a0012gDhh3Sv0vxp6J`）；结束后必须核对p209同义重复消失、p211“4、”保留、全部实际差异、报告/修订/授权下载哈希。未发布、无holdout。
- **target-11终态（覆盖上一条运行中）**：D03 complete/0，33 HTTP/$0.02399670，机械1/1、定向15/16。FL-D217 p209同义重复已真实修复，p211编号保持；新增FL-D218 p92 G01错误追加在同段下一“55、发起式基金”之后，不能判D03整合同通过。相对target-09仅p92/p209两处不同。累计1267 HTTP/$1.19796015、无reserved，余733/$0.80203985，不重复启动target-11。
- **FL-D218正在离线验证**：已实现`_definition_next_entry_start()`原件raw边界及Replay错误插入位置阻断；162项相关回归、compileall/diff check通过。真实旧target-11重放现G01 `CLAIM_OPERATION_SPAN_UNAUTHORIZED`，`offline-d03-merged-definition/`零模型重建仅在p92 raw130插入，下一定义原样、其他段落原样、接受/拒绝修订等价。完整回归后台`sh_16c8c95e6001anpIpG7qqz3rIh`，日志`merged-definition-audit-full-pytest.log`；等通知，勿轮询。该工作区同时含D07审核适用政策输入与audit_v3提示修复（UNKNOWN/CONFLICT不生成READY），尚未真实验证；D07收费事实认证仍未修复。
- **最新全量与事实入口（覆盖上一条）**：G01/audit版本已1396 passed/44 skipped/2 warnings/283.59s；随后`facts_from_value()`新增逐类申购/服务费quote极性核验与`fee_polarities`，缺失证据收费组UNKNOWN、反向证据CONFLICT，不改变原始布尔值。17项事实/恢复回归通过，当前完整回归后台`sh_16c91c85c001ZMbww6vst82T8Q`、日志`fee-evidence-current-full-pytest.log`，勿轮询/重启。20份旧回答原件重认证`fee-facts-current-recertification.json`确认D07/D10/D14/D16旧VERIFIED降UNKNOWN，这四份补证恢复尚未完成。待当前全量通过→`freeze_snapshot_12.py`→重验manifest/预算→真实target-12 D03→全部实际差异/G01/G08/编号/修订/hash审核。无真实批次运行，账本仍1267/$1.19796015，未发布/无holdout。
- **最终候选当前断点（优先于以上历史）**：收费入口初版1400 passed/44 skipped/2 warnings/270.15s；现支持每类独立`subscription_quote/service_quote`逐字证据（FACTS v5、恢复v2）、认申购缩写，157项相关回归通过；真实D10/D14/D16零模型补证可恢复VERIFIED（`fee-separate-positive-offline.json`），D07无服务费仍UNKNOWN。最终全量后台`sh_16c96ea870018j6h1FKOSs1igu`，日志`fee-separate-final-full-pytest.log`，启动源码哈希`fee-separate-final-test-start.json`/build `d441ec1706668bcdcafb0fcf7cfef9798d5879bb3a22871c1f9e84963c1fb16b`。**不要继续改源码混入测试版本**；等通知→读统计→运行freeze_snapshot_12.py（会强制源码哈希一致）→重验manifest/账本→target-12 D03真实复测。原target-11全部20处diff审核19通过、p92失败，证据`business-diff-review.json`。当前无真实Worker，账本1267/$1.19796015、剩733/$0.80203985。所有源码/前端/compare/外围dirty保留，未commit/push/发布，无子agent、无holdout；分支feat/frontend-v2，HEAD fc8424aaae46e46d209ec7aa3834502136f692f8。
- **最新真实终态，优先于下文历史**：target-08四份全部结束，140 HTTP/$0.12862980，机械4/4；D03 complete但编号丢失15/16（FL-D215），D05 complete且定向18/18，D07 incomplete/18 unresolved且修正辅助检查后33/33（不能替代业务完整审核），D18错误complete且12/14（FL-D216两处跨段顺延残留）。target-09 D03已完成，33 HTTP/$0.02420940，机械1/1、定向16/16，FL-D215该真实样本验证解决。D03相对target-08只变p209/p211，前者需细看语义差异，后者编号保留。target-09 final SHA `d04285613f9095a8b882daa92982d80a978fc5db04b1015252170595479ea226`。截至该轮账本1201 HTTP/$1.14961950，无reserved，剩余799/$0.85038050；无真实批次运行，不重复启动target-09。
- **FL-D216正在修复验证**：`recall.py`共用`_g15_delay_continuation()`，为已绑定G15支付head补紧邻完整顺延首句target；effect closure不依赖tail target也要求该site，Replay从原件独立重算授权与raw边界。新`tests/test_g15_cross_paragraph_delay.py`及相关82项通过；compileall/diff check通过。真实target-08 D18旧文件Replay现false，两tail FAIL；`offline-d18-cross-delay/`零模型局部重建只改p775/p1226 head及p776/p1227各0–33首句，G17用途/全部其他段落保留，修订等价通过。完整回归后台`sh_16c7b5248001q6uBCmnNuKAQuo`，日志`g15-cross-paragraph-full-pytest.log`，等完成通知，勿轮询/重复启动。待通过后冻结snapshot-10并另建target-10真实D18复测（脚本`freeze_snapshot_10.py`已备）。生产未发布、无子agent、所有前端/compare/其他dirty保留；branch/HEAD仍feat/frontend-v2/fc8424a。
- **后续未做**：D07收费facts引用管理费不能认证申购收费、audit适用组件口径仍待修；FL-D208单类别正面认证、FL-D209其余dev、全20份独立目标分母和完整实际文件审核待完成；达开发门槛才holdout、发布和最终普通工作台真实交付。不要把局部复测通过写成整项目完成。先完成FL-D216新真实任务闭环，再按这些缺口继续。
- **新发现FL-D217**：target-09 D03 p209比target-08多保留旧“本基金C类基金份额不收取申购费，”前缀，G08完整新政策再次声明C类免申购费，造成同义重复；编号FL-D215已解决不等于D03完整业务无缺陷。证据`target-09/D03/compared-to-target08.json`，待修G08源边界/重复，再新真实复测。snapshot-10已冻结（尚未启动真实），build `c3f8c6442b2b2880c82746e8b94e38e84127602da94053d5866d1b040f4638e8`，manifest `run_context-10.json`；先等当前完整回归通知，通过且manifest一致才启动target-10 D18。
- FL-D217定位证据：target-08 G08 p209 quote覆盖raw36–86（完整C类不收费＋A类费率同一句），target-09仅raw54–86（A类费率），二者均clean template，导致后一轮保留raw36–54旧C类前缀。应仅按自身完整政策覆盖的同句收费事实收敛边界，并让Replay检测相同来源政策重复，不盲吞相邻计算余文。尚未实施。

- **当前真实测试（覆盖下文旧下一动作）**：用户已再次授权真实测试、根据测试结果优化并继续真实复测；冻结`snapshot-08` build `a829181de8e965b8c6f64f7d37dcd2e1e7ff5134230a258a584ea2ee59c8652b`，manifest `run_context-08.json`。引擎与1343项完整回归工作区字节一致，API/tasks与生产一致，未发布。`target-08` dev D03/D05/D07/D18 已启动，隔离`data-08`、API8013、真实Worker/模型/授权下载；D03/D05已完成complete（D03 33 HTTP/$0.02439705，D05 费用报告$0.03210180），D07/D18仍运行，日志`/tmp/opencode/operation-validation-20261024/target-08.log`。预算起点1028 HTTP/$0.99678030，共享cap2000/$2/并发1；结果后立即做实际DOCX业务和机械复核，发现缺陷登记并优化，优化后继续新真实run，不能停在离线。D03已发现FL-D215编号吞掉，修复已通过55项定向回归，target-08保留修复前失败证据；无holdout、无子agent，生产前端发布与其他dirty改动保留。
- **FL-D215真实复测已冻结待启动**：修复版`snapshot-09` build `997329195f5699afd246bdb6ff5cca4fa28f5beaee440433e864e77c4f03d861`，manifest `run_context-09.json`，隔离`data-09`，仅真实复测D03；冻结时共享账本1137 HTTP/$1.108932，剩余863 HTTP/$0.891068。须等待`target-08` D07/D18终态后启动，避免两个隔离Worker争用共享并发；target-08旧D03失败证据保留。

- **最新终态（覆盖下文运行中历史信息）**：dev-05 D01–D20 已全部结束，不要重启或等待；D02/D16/D17报告complete，其余17份incomplete。真实634 HTTP / $0.63333525，共享ledger累计916 HTTP / $0.89509440，上限2000/$2不变。下载机械20/20通过，旧P6为214/236（90.68%，kept14/not_executed8），score SHA `5de8689c9d751c4b74e38f97ec2eeb1e7226599ee0128f052b2d9673d3f87afd`；旧口径存在已知限制，不能作为业务通过率。
- **最新修复与证据（覆盖下文历史）**：FL-D205已修完整引用标点定位和旧政策子句残留；dev-05实际产物0 HTTP离线重读，D17 G12 p207明确阻断，D02/D16状态保持。FL-D207跨段类别定义追加、FL-D210 composite切片外余文重复、FL-D211定义后净值公式追加及FL-D200异常计量修复已实施；相关82项Worker/管线/DOCX回归通过。完整离线回归 **1289 passed /44 skipped /2 warnings /242.46s**（`slice-formula-full-pytest.log`），该回归收集发生在新增FL-D200两项测试之前；FL-D200另外有上述组合验证。
- **2026-10-24最新工作区增量**：D07边界完整回归1308通过；后续G09 replay重算证明完整回归 **1317 passed /44 skipped /2 warnings /238.34s**（`g09-proof-full-pytest.log`）。真实target-07 D07原件/旧`working_final.docx`在`offline-d07-g09-proof-current/`重放：G09 PASS，整合同仍false。G15早先survey/parts试改已撤回；本次采用新的raw地址窄修复，仅补紧邻明确顺延句，D03真实原件p751/p1219均0–133删除，其他段落原样、Claim verified=true、接受/拒绝redline分别等于final/原件，证据`offline-d03-g15-raw-current/`。FL-D213把现有整段确定性删除移到compose预算检查之前，零模型/不扣compose名额；新测试`test_g15_payment_delay_boundary.py`及相关 **170 passed**。D05核对句授权仍OPEN，尚无新真实模型任务、未发布。
- **冻结候选为历史snapshot-07，不能代表当前工作区**：`/tmp/opencode/operation-validation-20261024/snapshot-07`，build `ac51034291840615ab22ee62c2453e2bc26cd456d51e0e9f550af4e3b2d001ad`，manifest `run_context-07.json`。它缺少最新G16/D07/G09/G15修复及新增测试；需重新显式冻结，保留当前API/tasks和其他并行外围，不复用旧快照冒充新构建。
- **target-07终态（覆盖上文预登记）**：四份已结束，禁止重复启动。D07 incomplete/40 unresolved，D11/D17/D18报告complete/0；112 HTTP/$0.10168590，累计1028 HTTP/$0.99678030，剩余972 HTTP/$1.00321970。机械4/4通过，D17旧比例句、D11公式末追加、D18顺延句局部复核符合预期；但D18在p775/p777及p1226/p1228重复完整G16且错误complete，FL-D192重新打开。证据`target-07/artifact-reviews.json`、`target-07-review-packets/`。
- 当前下一动作（2026-10-24更新）：D03/FL-D213旧全量为**1325 passed /44 skipped /2 warnings /240.20s**；随后D05 G15收窄/`bounded_delete`及G17 site closure已通过68项定向回归，D05实际重建`offline-d05-g17-site-closure/`四个G17 sites全部通过、两处核对句保留、修订等价通过。当前工作区最新完整回归为**1343 passed /44 skipped /2 warnings /245.29s**，日志`g17-closure-full-pytest.log`。FL-D214旧错误PASS已保留为失败证据，离线修复已验证，尚未真实Worker/模型复测。继续FL-D206授权审查、FL-D208单类别正面认证及FL-D209其余dev缺陷，再完成20份独立目标分母/实际DOCX业务审核。未达开发集门槛不跑holdout、不发布。无后台真实批次、无子agent，所有并行dirty内容保留；共享账本1028 HTTP/$0.99678030，总cap2000/$2，剩余972 HTTP/$1.00321970，本次全部离线。
- 目标：完成当前未提交 operation-level Registry/Router、Policy Components、canonical obligation、Claim Replay、coverage、Delivery Gate patch 的 build identity 冻结、真实合同评测、受控生产发布及当前版本工作台真实端到端交付验收。
- 用户/项目约束：不得整仓库 add/reset/覆盖并行前端、compare、evidence、运维改动；真实模型、实际 DOCX、报告和下载哈希必须核验；历史 FL-D175 证据不能证明当前版本；问题必须登记本文件与 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`；凭据只允许从受保护环境读取，不写入仓库、文档、日志或命令输出。
- 环境：hostname `iZf8zemhifedxdow1zefr0Z`，内网 `172.28.217.241`，工作区 `/home/opencode/fundlex`，Python `.venv/bin/python`。当前分支 `feat/frontend-v2`，HEAD `fc8424a`。系统 `python3` 为3.6，所有项目命令必须使用 `.venv/bin/python`。
- 工作区：引擎相关修改仍未提交；并行 dirty/untracked 文件同时存在。除此前引擎文件，本轮新增 `recall_prompts.py` audit v2、`tools/evaluation/{p6_run,verify_downloaded_artifacts}.py` 与相关测试。API/tasks/前端属于并行工作，保留其最新生产版本，不整仓库覆盖。
- 已完成：operation identity 已贯穿 Registry、Router、planner/replan/residual、targeting、obligation、coverage、Claim Replay、Delivery；UNKNOWN/CONFLICT、缺失显式 Registry、重复/缺失 occurrence 和兄弟 operation 借权均 fail-closed；G08/G11/G14/G16 policy component 规则已接入。定向回归 **142 passed / 1 warning**；完整离线回归 `.venv/bin/python -m pytest tests -q` **1249 passed / 43 skipped / 2 warnings / 235.11s**；`git diff --check` 通过。
- 当前版本评测冻结：`var/recall-first-evaluation/p6-current/selection.json` 为20 dev + 8 holdout，原件 manifest/hash 已校验；labels SHA `f120d38175c83cd1c973045d0414a69bacb9d837fc4bf24d40a8a762fe588841`。原标签347目标、26可改/2排除仅为旧标注器输出，存在ETF联接 D02/D06错排及单规则单目标限制（**FL-D188**，原误编号FL-D186与favicon冲突已消歧），不能作为完整业务真值。原gold/scorer不改；holdout新预测未读。
- 冻结快照：`/tmp/opencode/operation-validation-20261024/snapshot` build `41de9fcb36fe028457255cbb282ccc3e02ea3ef478f520dd6ef2b14e30fd3d97`，全量 **1216 passed / 65 skipped / 2 warnings /156.97s**。pilot-01 D01/D02 真实模型62次/$0.0646734，均 incomplete；下载机械检查2/2通过，旧scorer13/14目标通过（D02被旧标签错误排除，不能宣传92.86%为完整口径）。失败文件保留。
- 缺陷修复：FL-D189 G09 clean自动选template但只有splice实现，改为仅允许SPLICE，unsafe继续阻断；FL-D190 audit指令引用FACTS却未传账本，补完整facts.as_ledger、计入context cap并升级audit v2。新增routed planner→真实DOCX回归及audit调用上下文回归，相关 **106 passed /7.47s**。
- 当前新冻结：`snapshot-02` build `1a34319a91df99e389fbd403d419f09d21ae010db078244acd66bcaa48732cb9`，`run_context-02.json`记录源码hash/范围；继承原快照、只加上述两修复与最新生产API/tasks（保留React V2外围）。并行前端已发布生产，现build `dbfc3951b3e2ac46430a32086b1ade538950fb570bf93bce33f6c62f23cc84b2`，与snapshot-01仅API/tasks不同；本agent未发布新修复，后续先隔离评测，达发布条件才部署。
- 共享预算：`/tmp/opencode/operation-validation-20261024/ledger.sqlite`，本轮所有尝试共用，2000 HTTP/$2/并发1/每合同192调用上限；不得重置。harness只从受保护生产环境读模型配置到内存；隔离数据`data/`、API8013；结束自动终止隔离API/Worker。
- 最新结果：snapshot-02全量 **1221 passed /65 skipped /2 warnings /150.05s**；pilot-02 D01/D02均incomplete，61次/$0.06506505。G09及audit事实修复实际生效；机械核验2/2通过。D01 G02重复T3 target阻断Claim（FL-D191），实际DOCX G16在同一条款head/tail重复写入（FL-D192），G05误改权限条款（FL-D193）；D02业务站点补充40/40但G05权限句被audit误拒，不能称整合同通过。前两轮累计123次/$0.12973845。
- 新修复：`recall.py` 规划前精确对账satisfied aliases（显式不同occurrence保留）；`rebind_g16_clause_targets` 将同一费用条款head/tail绑定至统一尾位置再dedupe，正文摘要保持各一；G05在assign阶段所有状态及planner采用窄业务site guard，`generation/effects.py`同步允许直接“调整基金份额类别”。`recall_pipeline.py::_plan_and_generate` 调用重绑和最终dedupe。更新低层测试夹具补合法类别语境；原gold/scorer不改。相关174项通过，扩大组合后仅旧低层fixture需加类别语境，修复后最后组合104 passed/8.34s，diff check通过。
- 当前冻结改为 `snapshot-03`，build `515e0e08accf04172609422acf08f25120144e5fcd2da642e1c9199b9987ae12`，hash见`run_context-03.json`；继承snapshot-02仅新增上述FL-D191～193修复及测试。源站点审查脚本`/tmp/opencode/operation-validation-20261024/review_pilot_sites.py`是开发补充核验，不是独立gold；检查guide完整新文、费组、公式余文、旧机制删除、同条款G16次数和权限句保留。pilot-02 D01 36/40、D02 40/40，文件`pilot-02/supplemental-site-review.json`。
- snapshot-03完整测试已结束：**1226 passed /65 skipped /2 warnings /150.73s**。`replay_pilot_plan.py offline-plan-03`用pilot-02真实target、不调模型重建局部产物，D01/D02 G16 count均2（各正文摘要一次）；因其他生成/复用路径缺少模型与最终edit上下文，replay全量Claim未通过（D01有5类failure/7unresolved、D02有2类/4unresolved），只作局部重复修复证据，不可计正式交付或另一个真实样本。
- pilot-03 已完成：D01/D02 均 `completed`、`delivery_status=complete`、`unresolved=0`，真实模型 59 次、约 `$0.062185`；`verify_downloaded_artifacts.py` 机械核验 **2/2**，`review_pilot_sites.py` 实际 DOCX 逐站点检查 **D01 40/40、D02 40/40**。最终 SHA：D01 final `a682e23b6dada80dddd1ae0662a7a9a0277cdfc63bffe08ab6b565ab08ca94b3`、redline `fe5120b139ff86d1fb54d547f870940d8eb5c8291928cba43bb09603e0cb2b45`；D02 final `8f25c7470b8a99d3ebd6043452e96d33af00798e10c5326f72d05f848e4edd6e`、redline `cd292a7a2ab2f9ddfea16456866f156b1486ada480f6e733472da5aa3bf5d371`。FL-D191～193 已在这两个真实样本关闭；pilot-02 原失败证据保留。
- 仍未完成：受控发布；最终快照20份真实 dev 修改与实际 DOCX/report/hash 评分；按开发结果登记缺陷并局部复测；冻结后 holdout/blind 8份；生产域名真实登录→上传→持久任务→真实 Worker/模型→DOCX 修改→复核→结果页→final/redline/report 授权下载及哈希/修订核验；更新集中问题记录、最终交付说明和本断点。
- 运行状态：无子agent；旧 `dev-03` 在 D03 因 FL-D199 中止，D04–D20 未运行，其失败证据保留。`debug-d03` 已用保存 checkpoint 无网络稳定复现原 NameError，修复后越过该点；snapshot-05 冻结快照全量回归 **1234 passed /65 skipped /2 warnings /157.09s**。共享 ledger 仍须作为真实模型费用权威，失败报告中的 null 不能计为零成本。当前 `dev-05` 使用 snapshot-05、独立 `data-05` 和共享 ledger 正在运行，已完成 D01–D06：D01 `incomplete`/8 unresolved，D02 `complete`/0 unresolved，D03 `incomplete`/6 unresolved，D04 `incomplete`/16 unresolved，D05 `incomplete`/2 unresolved，D06 `incomplete`/30 unresolved；D07–D20 尚未完成。D01–D06 的下载 DOCX 机械核验均通过；D01 supplemental site review 为 **38/40**，失败为 G15 p758/p1221 变体残留。当前工作区已加入 FL-D204 的最小变体恢复修复及回归测试，但 dev-05 使用的是修复前 snapshot-05，不能把该批次结果当作修复后结论。
- 最新冻结与运行：`snapshot-04` build **`efc893de06f8476d4123a27cb1c467d4eb637c5f5cd297628d23590f27745edd`**，源码上下文已保存为 `run_context-04.json`（prepare 原始输出名为 `run_context.json`）。后台 **dev-04 完整 D01–D20**，shell `sh_16b94e96c0011udYlV17dBCfjC`；等待完成通知，不重复启动/轮询。启动后一次账本快照 **258 HTTP / $0.24256935**，总 cap 2000/$2不变。全量工作区离线验证 **1266 passed /44 skipped /2 warnings /242.79s**，快照 compileall通过。生产未发布。下一动作是完成通知后读取 `dev-04.log` 和 `dev-04/batch.json`，运行下载机械核验、旧scorer、实际DOCX逐合同业务复核；有已知缺陷不能凭complete状态直接进holdout。
- `snapshot-04/dev-04` 已判废并保留：其冻结脚本从 HEAD 取回旧 API/tasks，虽 D01 已完成，但 D02 尚未完成即停止；不作为单一版本评测。新冻结 `snapshot-05` 从 snapshot-03 显式继承并只覆盖 `fundlex/recall_pipeline.py`，build **`5b04e5ea2ed2aadddca51ddca4ed66c1d65f33461f435445f394b5e34cd953c2`**，`run_context-05.json` 已保存，API/tasks 与生产一致。后台 **dev-05 D01–D20** 使用独立 `data-05`、共享 ledger；启动前总账 **282 HTTP / $0.26175915**。dev-04 的 D01 产物保留，不并入 dev-05 分母。
- 接续补充：dev-05后台shell **`sh_16b98cf3b001YCPBttGsvCxaPI`**，父进程2645668、隔离API2645673、Worker2645674、runner2645684（仅作本轮识别，操作前重新核实）；D01已真实写入checkpoint，租约正常，尚无全批终态。最新一次总账快照 **316 HTTP / $0.30515715**；不要重置、重复提交或据此当作最终费用。等待完成通知后读取dev-05.log/batch.json再分析。
- snapshot-05自身完整离线测试已完成：**1234 passed /65 skipped /2 warnings /157.09秒**，日志`/tmp/opencode/operation-validation-20261024/snapshot-05-pytest.log`，与工作区1266项分开披露；完整冻结文件manifest无变化。无子agent、未改生产。
- 新增`tools/evaluation/build_revision_review_packet.py`（仅评测辅助，未写入冻结引擎），20 dev原件材料在`dev-source-review-05/`，pilot-03实际diff材料在`pilot-03-review-packets/`：D01 19段/D02 18段与机械复核地址及哈希完全对账，工具不赋业务分数，不读holdout产物。FL-D188保留未关闭，冻结labels SHA未变。已新建`docs/REAL_REVISION_EVALUATION_RESULTS.md`记录证据边界与后续动作。
- 只读`release-candidate-05.json`确认候选相对生产5文件不同：generation/effects.py、generation/registry.py、recall.py、recall_pipeline.py、recall_prompts.py；API/tasks相同。旧构建回退另登记FL-D203，本轮用显式继承修正，通用prepare未修。dev-05 运行期间新增 FL-D204 G15 变体恢复修复：Sweep 在唯一适用 delete/replace operation 且 finding 已 source-bind 时，能将原 `absent/not_applicable` target 转为 operation-specific synthetic `needs_edit` target；多 operation 继续 fail-closed。回归测试已通过。基于 snapshot-05 创建修复后候选 `snapshot-06`，build **`e53c8585514470019ff2b7890aed1f407573f9574d00abe8b23a72d8a1b0a568`**，`run_context-06.json` 已保存，唯一引擎源码 overlay 为 `fundlex/recall_pipeline.py`，API/tasks 与部署版本一致；snapshot-06 全量离线回归已完成 **1236 passed /65 skipped /2 warnings /148.62s**，日志为 `snapshot-06-pytest.log`，未发布、未调用真实模型。dev-05 仍继续使用修复前 snapshot-05。当前下一动作：dev-05完成后运行`verify_downloaded_artifacts.py`、旧p6_score、全dev实际DOCX阅读材料生成与逐站点业务复核；未达条件不跑holdout、不发布、不宣称最终交付。

## React V2 前端回归收口（2026-10-24，当前）

- 本轮按用户要求完成 React V2 控件与原版视觉体系对齐，登记 FL-D212：新增共享 `Select` 控件，统一输入/下拉/复选框/文件选择器/按钮组/筛选栏/拖放区/表格和 Review 决策状态；V2 顶栏改为原版浅色 64px，侧栏恢复 252px 分组图标导航，移动端保留横向导航；任务总览补齐按指引筛选，并恢复消息、帮助中心、修改密码入口和页脚信息。任务、批量上传、指引、设置、用户和 Review 路由/API 未改变，独立 Compare 入口保留。发布后的移动端侧栏溢出修复已追加验证，详见本文最新发布段。
- 当前验证：`PATH=/tmp/opencode/node-v20.18.0-linux-x64/bin:$PATH npm run typecheck`、`npm run lint`、`npm run build`、`git diff --check` 均通过；前端浏览器定向回归 **7 passed**；公网 smoke 已覆盖登录、关键路由、消息/帮助入口、1440px/768px/390px响应式宽度、1440→768原地缩放、页面错误、控制台错误和 404，证据见 `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json`。最终构建资源为 `frontend/dist/assets/index-BkJEWrna.js` 与 `frontend/dist/assets/index-ko73k-L5.css`，已完成前端-only 生产发布。

- 当前工作区仍为 branch `feat/frontend-v2`、HEAD `fc8424a`，同时保留前端、Compare、evidence、运维和 recall-first 引擎的并行未提交/未跟踪改动；不得整仓库 add/reset/覆盖。主机已核实为 `iZf8zemhifedxdow1zefr0Z`，内网 `172.28.217.241`，使用 `.venv/bin/python`。
- 本轮修复并登记 `FL-D182`、`FL-D183`、`FL-D184`：React smoke 将 API 404 与静态资源 404 分离；Guides 启用状态只允许后端支持的 `parsed`/`released`；任务列表、任务详情、指引列表/详情首次加载失败增加页面级重试。
- 新增浏览器覆盖：真实临时 FastAPI 任务入口创建任务、上传真实 DOCX，并打开 task-scoped 合同详情和 Review 深链，检查报告/修订错误态、请求路径和 page error。
- 当前验证：`PATH=/tmp/opencode/node-v20.18.0-linux-x64/bin:$PATH npm run typecheck` 通过；`npm run lint` 通过；`npm run build` 通过，最新 JS 为 `frontend/dist/assets/index-CmYK9MZP.js`，CSS 为 `frontend/dist/assets/index-BCmLwO6a.css`；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` → **3 passed**；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/test_tasks_api.py tests/browser/test_frontend_v2.py -q` → **30 passed / 1 warning**；`git diff --check` 通过。

### React V2 parity 候选更新（2026-10-24，未发布）

- 矩阵见 [`docs/FRONTEND_V2_PARITY_MATRIX.md`](FRONTEND_V2_PARITY_MATRIX.md)。本轮补齐并核验任务总览统计卡、上传清单搜索/状态筛选/分页/重复名称保护、替换/移除/清空，以及替换失败时旧文件不能继续提交的状态边界；集中记录新增前端问题 FL-D223。矩阵中的 Compare 独立入口问题沿用 FL-D219，已修正专项浏览器脚本默认页与业务页的导航断言。
- 当前前端候选构建资源：`frontend/dist/assets/index-B75utm89.css`、`frontend/dist/assets/index-jR7FF1CT.js`。`index.html`、CSS、JS SHA-256 分别为 `06e141e0edefd822bff92194e2f1c75115af292f8657029073f54fc461c25cc9`、`6e2be4855eafc59c43153cf2b1f58efa3c02b0a5452bc75b473d66f0e4d1664b`、`bc87d8701dc0bfaaaca00c121528942975253ac77a83c46a3b26fa03cf709ae3`。`npm run typecheck`、`npm run lint`、`npm run build`、`git diff --check` 通过。
- 当前本机浏览器证据：React V2 定向回归 **6 passed**，React/API 组合 **33 passed / 1 warning**；Compare 单测 **70 passed / 5 skipped / 1 warning**；`tools/evaluation/compare_e2e.py` 现访问 `/compare#compare`，独立 Compare **9/9 场景通过**，证据 `/tmp/opencode/compare-e2e-final.json`；1440/1180/1000/768/760/420/390 七视口均无 document/body 横向溢出。
- 本轮未发布候选，也没有新的生产模型调用。公网仍是此前已发布版本；任何后续发布都必须只同步前端静态候选并重新完成公网入口、深链、响应式和真实用户交付核验。
- 发布前公网复验发现 FL-D224：旧候选在同一浏览器从 1440px 原地调整到 768px 时 `document/body=976px`，已用 `.main-content { min-width: 0 }` 修复；本机浏览器专项 **7 passed**，最终候选已受控同步并完成公网复验，详见上方最新发布记录。
- React V2 已按用户“发布”指示完成前端-only 静态同步到 `/opt/fundlex-recall-first/frontend/dist` 并重启 API；本次没有重启 Recall Worker，Compare Worker 保持原状态。发布后公网 `/`、关键 V2 路由、新 hashed JS/CSS 均可用，具体资源哈希与浏览器证据见本文最新发布段。`FL-D185` 发布阻塞已解决，`FL-D186` favicon 404 已修复并验证。
- 发布后本地前端 typecheck、lint、Vite build、浏览器定向回归和公网 smoke 均通过；最新 smoke 已补充移动端页面宽度回归。此前的临时 API smoke 仍保留为开发证据，不能替代最终真实登录→当前指引→上传→seal→Worker/模型→DOCX 修改→Review→授权下载与哈希核验。
- 生产工作台的完整真实用户路径此前已有任务 `70e8148548ec4432a7d68457fd866fb1` 证据，但本次前端-only 发布没有重新创建任务或调用模型；当前版本仍需完成本轮生产真实合同的 Worker/model、DOCX、Review、报告、授权下载、修订和哈希核验，不能据此宣称完整项目交付完成。

## React V2 / Compare 入口说明（2026-10-24）

- 用户看到“恢复原版本”的原因已确认是访问 `/compare`：该路径按设计继续提供独立 Compare 页面，生产首页、`/tasks` 和 V2 hashed assets 未回滚。问题登记为 FL-D194。
- 已更新 React V2 导航为“合同对比（独立页）”；Compare 页面增加独立页面说明和返回 `/` 的“返回新版修订工作台”链接。Compare 业务链路保持不变。
- 本次前端静态变更已按文件发布并完成公网入口复验，新资源为 `index-BUWdg2p2.js` / `index-BCmLwO6a.css`，工作区、部署目录和公网 JS SHA 一致。最新生产任务 `70e8148548ec4432a7d68457fd866fb1` 已真实登录、当前指引快照、上传、seal、Worker/model、详情、Review、报告和授权下载完成：任务 `completed`，文档 `succeeded/incomplete`，32 targets 中31完成、1未解决；G09 p224 仍未执行。结果文件 `/tmp/opencode/fundlex-production-v2-e2e-20261024/e2e-12d1e3tfq98g/result.json` 确认 `page_errors=[]`、`console_errors=[]`、静态/API 404均为0；`working_final` SHA `c2becfdc024efc171b79ae2d409f25c8f079d65e40de67198ebbbbd0a4c1923e`、`working_redline` SHA `811425c8c14d87972098adbb7a179530e36ce958db0b0f9ec88b39b815ad8469`，报告 JSON/Markdown SHA 分别为 `a6d86a200eef81d82b55274047f5b4a79c19294b13a407c7e7a30064b172e16b` / `b86a864acd9d1d2665c7f5a4c8a47dfc863fc09b6d625fa303f27231b3db568f`。页面/路由误断言登记 FL-D195，自定义 fetch 漏带 Bearer 登记 FL-D196，详情/Review 文案登记 FL-D198；Review `<hr>` React #137 登记 FL-D201，工作文件哈希误报登记 FL-D202。引擎发布仍受 snapshot-05 dev 结果约束。

## Recall-first operation Registry/Router 收口断点（2026-10-24，当前优先）

- 当前工作区：branch `feat/frontend-v2`，HEAD `fc8424a`；工作区同时保留前端、compare、evidence、运维和其他并行未提交/未跟踪改动，禁止整仓库 add/reset/覆盖。当前主机已核实为生产/工作同机 `iZf8zemhifedxdow1zefr0Z`，内网 `172.28.217.241`；Python 使用 `.venv/bin/python`。
- 本轮继续收口 recall-first 的 operation-level Registry/Router、Policy Components、canonical obligation、Claim Replay、coverage 和 Delivery Gate。显式 guide `operation_id` 优先贯穿 planner、replan/residual、targeting、obligation、coverage 与 replay；部分标注、显式 operation 缺 Registry entry、UNKNOWN/CONFLICT fact 和未解析 occurrence 均 fail-closed。旧无显式 identity 的低层 fixture 只走 legacy 兼容路径。
- 已实施并登记集中问题 `FL-D178`、`FL-D179`、`FL-D180`：当前 operation policy 文案按自身组件验证；G08/G11 局部 fee group、G14 授权替换、G16 完整 Compose 语义分别处理；动态 operation 缺 concrete Registry 时 planner 返回 `RECALL_OPERATION_REGISTRY_MISSING`。
- 新增回归：`tests/test_generation_registry.py::test_routed_planner_fails_closed_for_missing_custom_operation_registry_entry`，直接穿过 `plan_target()` 验证缺失注册阻断；自定义 operation 不能借用 `RULE:index` 别名。
- 当前离线验证：Registry/recall core/Claim Replay 组合 **104 passed**；Registry/validators/coverage/obligations/delivery **89 passed**；Claim/targeting/pipeline **77 passed**；首次全量曾暴露并已修复 FL-D181，最终 `.venv/bin/python -m pytest tests -q` **1249 passed / 42 skipped / 2 warnings / 223.62s**；compileall 与 `git diff --check` 通过。真实合同重新评测、build identity 冻结、生产发布和当前版本工作台 E2E 尚未完成。
- 下一步：先运行完整 `.venv/bin/python -m pytest tests -q`，保存真实结果；再补 occurrence 0/1、重复 occurrence、canonical/legacy coverage fallback、replan/residual/delivery 的缺口；随后只整理引擎相关文件冻结版本，按 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` 重新执行真实合同开发集/历史失败样本/holdout-blind，并重新完成生产工作台真实上传、Worker/模型、DOCX、复核和下载哈希核验。旧 `FL-D175` 证据属于此前版本，不能替代本轮冻结版本验收。

## 合同比较阅读器联动滚动与视觉重构已发布（2026-10-24）

- 本轮完成 `frontend/index.html`、`frontend/compare.js`、`frontend/compare.css` 和 `tools/evaluation/compare_e2e.py`；集中问题记录新增并关闭 FL-D177。其他引擎、evidence、`tools/ops/` 等未提交改动仍保留，不能整仓库 add/reset。
- 已实施：双 pane 按可滚动高度比例联动，滚轮/连续事件使用 `requestAnimationFrame` 合并且有来源锁防递归；结果摘要、覆盖边界、方向提示、基准/修订标题、同步状态、差异导航和移动端结构重新分层；保留连线、筛选、键盘定位、pair 轮询和移动端切换。
- 验证：`.venv/bin/python -m pytest tests/test_compare_*.py -q` → **70 passed / 5 skipped / 1 warning**；本地 `/tmp/opencode/compare-e2e-ui-v5.json` → **9 场景全部通过**，正向/反向同步比例与 SVG 几何均通过；生产 `/tmp/opencode/compare-production-ui-e2e/report.json` → 真实注册/登录、上传公开合同、Compare Worker、结果查看、双向联动、移动切换、键盘定位、报告下载通过，page error 0，联动比例误差 `5.3e-6` / `2.6e-7`，报告 3189696 bytes。
- 发布：提交 `0f51d07` 已推送到 `origin/feat/contract-compare`，通过 `tools/deploy/publish_workspace.sh` 发布；`fundlex-recall-api`、`fundlex-recall-worker`、`fundlex-compare-worker` 均 active。生产截图 `/tmp/opencode/compare-production-ui-e2e/viewer.png`。
- 下一步：如继续调整 compare 视觉或滚动行为，必须重新运行 compare 专项、浏览器验收和生产真实用户路径；不要将当前截图中的 headless 环境中文字体缺失现象误判为合同文本内容问题，正式浏览器应按客户端字体渲染复核。

## 合同比较页面改版已发布（2026-10-24）

- 本轮依据产品、UI、前端三类只读评审修改 `frontend/index.html`、`frontend/compare.js`、`frontend/compare.css`，并扩展 `tools/evaluation/compare_e2e.py`。其他引擎、evidence、`tools/ops/` 等未提交改动仍保留，不能整仓库 add/reset。
- 已实施：原版→对比版方向语义、覆盖不完整人工复核提示、批量上传中断后继续上传、轮询保持选中 pair、差异类型筛选/章节显示、移动端单栏侧切换、正文差异标记键盘定位与焦点可达。
- 验证：compare 专项 **70 passed / 5 skipped**；本地浏览器验收 `/tmp/opencode/compare-e2e-ui-revision-v3.json` 为 **9 个场景全部通过**；生产浏览器验收 `/tmp/opencode/compare-production-ui-e2e/report.json` 通过，覆盖方向说明、incomplete warning、移动端单栏切换、修改筛选、键盘定位和报告下载，无 page error。
- 发布：UI 提交 `5d04271` 已推送并通过 `tools/deploy/publish_workspace.sh` 发布；三个服务均 active、重启计数 0。生产结果为 2772 处差异，报告下载 SHA-256 `d1607d77f3b0fe8487c8c1a8b4c2c287599e5283eb7d207b447ce0ca719716e3`。compare 不调用模型，费用 `$0`。
- 下一动作：后续 UI 或 Worker 改动必须重复生产浏览器回归；其他引擎、evidence、`tools/ops/` 等未提交改动仍保留，不能整仓库 add/reset。

## 引擎真实合同与工作台验收断点（2026-10-23 21:00，优先）

- 本轮完成 FL-D157~FL-D175：多通道召回、append/G16 锚点、复合目标 content-check、G06 语义探针、跨段事实引文、G17 尾句、G08 认购/申购 flip、G18 等价句、G20 FALSE 分支审计、delete+append 联合校验、重复 append 目标去重均已修复并有回归。
- **真实合同：6 份不同合同 delivery_status=complete、unresolved 0、final/redline 哈希与报告一致**（广发品质回报、核心优选 FOF、上海清算所债券、ESG 混合、央企股东回报 ETF 联接、央企创新驱动 ETF 联接）；港股通红利 ETF 正确 excluded。明细/哈希/费用见集中问题 FL-D175。
- **工作台真实路径（本地临时 API+Worker，非生产域名）**：登录 → 建任务 → 上传 → seal → 真实模型 30 calls/$0.02243 → complete → 下载 final/redline/report；final 哈希与报告一致，redline 19/19。脚本 `/tmp/opencode/engine-live-20261023/workbench_e2e.py`。
- 全量测试：**1203 passed / 40 skipped / 0 failed / 222.50s**；compileall/diff check 通过。
- 临时模型账本合计 **1129 calls / ≈$0.7999**，全部在 `/tmp/opencode/engine-live-*`，未用生产账本；未打印凭据。
- **生产发布已完成**：引擎提交 `11c3ae8` 已本地提交并通过 `publish_workspace.sh` 发布；部署 `recall.py`/`recall_pipeline.py`/`effects.py`/`claim_replay.py` 哈希与工作区一致，api/recall-worker/compare-worker 均 active。
- **生产域名 E2E 已通过**（https://fundlex.club，admin）：任务 `19a5c76e…`，上传广发品质回报 → Worker 真实模型 **30 calls / $0.02247 / 115s** → complete、unresolved 0；final SHA `e48e0f78…` 与报告一致，redline `aceb9289…` 与报告一致且 19/19；关键段落已核对。Chromium 登录/任务页/3 个下载入口正常，无 pageerror（仅登录前 401 探测）。
- **生产批量已通过（5 份不同合同 complete）**：广发品质回报 + FOF/上海清算所债券/ESG/央企创新驱动 ETF 联接；4 份批量任务均 unresolved 0、final/redline 哈希与报告一致、redline 17~19 处修订、G15/G17 旧条款 0 处、G16 新政策存在。明细见 FL-D175。生产 5 份合计 156 calls / ≈$0.1254。
- **未做**：生产验收任务未清理（无 DELETE 接口）；浏览器截图 `/tmp/opencode/engine-live-20261023/production-browser/task-page.png`；最终交付说明尚未汇总。
- 下一步：① 观察三服务与生产账本；② 清理/登记验收任务；③ 更新最终交付说明与 README；④ 如需回滚，使用 `11c3ae8` 前的部署快照（如有）。

## 合同比较已推送并部署（2026-10-23）

- Compare 发布提交为 `eba2b3a`，已推送到 `origin/feat/contract-compare`。工作区其他任务的未提交改动仍保留，未整仓库提交。
- 已执行 `tools/deploy/publish_workspace.sh`；API 与 Recall Worker active。随后安装、enable 并启动 `fundlex-compare-worker.service`，三项服务均 active，重启计数均为 0。
- 生产真实用户链路已通过：工作台注册/登录 → 合同对比 → 上传两份公开 DOCX → 封存 → 独立 Worker → 结果页 → 双栏导航 → 报告下载。结果为 2772 处差异，coverage 明确标记暂不支持的页眉/页脚/绘图结构；浏览器 page error 为 0。证据见 `/tmp/opencode/compare-production-e2e/` 和 `/tmp/opencode/compare-production-browser-e2e/`。
- 本轮 compare 模型调用 0、费用 `$0`；未修改 nginx 或生产数据库结构。后续若修改 compare 代码或 Worker 模板，需重新发布并重复生产链路验收。

## 核心引擎层审查与修复断点（2026-10-23 18:00，历史；最新见上）

- 用户问题：检查核心引擎层修改情况；前一个负责 agent 已失联。**本轮已完成审查、修复、回归与 1 份真实模型单例验证；未 commit、未部署、未跑 ≥5 份合同、未做工作台 E2E。**
- 现场：branch `feat/contract-compare`，HEAD `a36acd2`（与 `origin/refactor/recovery-architecture` 同 SHA）。引擎改动仍未提交：`fundlex/recall.py`、`recall_pipeline.py`、`generation/{coverage,effects,router,__init__}.py`、`recovery/{history,orchestrator,policies,types}.py` + 测试。compare/前端未提交工作保留，未整仓库 add。
- 全量回归：`.venv/bin/python -m pytest tests -q` → **1195 passed / 40 skipped / 0 failed / 230.16s**；compileall、`git diff --check` 通过。compare agent 同时登记 FL-D160~FL-D162（其 MySQL/worker 修复与 G16 site guard 兼容性），本段不覆盖。
- **已修复（集中问题记录 FL-D157~FL-D166）**：
  - FL-D157 G15 关键词配对跨条款：加入句末终止符/新主题/半句合并门禁，复合 parts 改 compact 偏移；100 份扫描 0 误配对（原 6）。
  - FL-D158 append 摘要误锚定变更触发句：新增 `_append_definition_anchor` 定义句门禁；30 份扫描 0 误锚点（原 16）。FL-D166 同时修复模型目标落在“基金份额类别设置”导致 G03 双插入。
  - FL-D159 G16 锚点在支付从句中间：`_g16_clause_end` 走到条款末段（p809/p1265），append site/归属/planning 使用同一 guard；30 份扫描 0 中间锚点（原 5）。
  - FL-D163 复合目标第二段被 content-check 静默丢弃：整段删除映射到 `len(span.text)`，`_composite_part_slice` 同步；G15 p807/p1263 不再残留。
  - FL-D164 out_of_scope 模型目标仍压制 survey：`known_operations_from_targets` 跳过无效目标。
  - FL-D165 删除与同段 append 合并时 Claim/Validator 误报：delete 在“联合计划精确匹配 + 旧文不存在”时判 PASS。
- **真实模型单例（`/tmp/opencode/engine-live-20261023/final1/`）**：广发品质回报，43 calls / $0.02638 / 约 150s，`delivery_status=incomplete`；G01 p106、G03 p138 各插入一次，G15 p806/p807/p1262/p1263 全部删除，G17 p808/p1264 删除，G16 p809/p1265 各插入一次；无重复政策文本。obligation：13 ARTIFACT_VERIFIED / 9 ALREADY_SATISFIED / 10 NOT_APPLICABLE / 2 UNRESOLVED。
- **剩余未完成（FL-D167）**：G08 p156 `RECALL_COMPOSE_FIXED_TEXT_MISSING` + `CLAIM_OPERATION_NOT_PLANNED`；G18 无 verified site。两者是 FL-D146 之前已有的生成/适用性问题，不是本轮 FL-D157/158 回归，但不能宣称合同完整。
- 预算：本轮真实模型合计 465 calls / ≈$0.2473（临时账本均在 `/tmp/opencode/engine-live-20261023/`，未用生产账本、未打印凭据）。无遗留 live 进程。
- **已本地提交 `f3791df`（未 push）**：20 个引擎/测试/文档文件；compare、前端、api.py 的未提交工作未纳入。生产仍是旧版本，未部署。
- 下一步：① 修 G08/G18 并重跑本单例；② ≥5 份真实合同；③ 工作台登录→上传→真实模型→DOCX→下载全链路；④ 发布与生产复核。当前生产仍是旧版本，未部署。

## 核心引擎层改动审查原始发现（2026-10-23 16:10，已由上一段修复）

- 原审查发现 FL-D157（G15 配对吞入 G17 p808）、FL-D158（G01/G03 摘要误锚定变更触发句）、FL-D159（G16 支付从句中间锚点）均已在 2026-10-23 晚修复并验证，详见集中问题记录与上一段。

## Codex SSH 稳定性修复断点（2026-10-23 15:00，优先）

- 用户问题：关闭 SSH 后 Codex 任务仍中断；历史对话频繁提示“open in another app”。OpenCode 侧正常。
- 已定位：① legacy `--no-daemon` TUI 把 turn 放在自身进程内，TUI 退出即 `op=Interrupt`；② 每个 TUI 都是独立 thread-store writer，旧 detached tmux 会话永久持有多个 thread lock；FL-D153 的“stale lock 删除”是误判，已更正。
- 已实施：官方完整包启用 managed app-server daemon（0.164.0），`~/.local/bin/codex` 指向 managed `current/bin/codex`（旧 0.162.1 保留为 `codex-standalone-0.162.1`）；daemon auto-update 关闭；`loginctl enable-linger opencode`；`codex-app-server.service` + 60s timer（`codex-daemon-ensure` 健康探测），cgroup 在 `user@1002.service`；`codex-persistent` 改为 daemon-first + tmux fallback，并新增 `resume` 锁路由、`ls/where/attach/close/gc`。
- 已验证：`where 01a16485…` 指向 pid 2152151 / `codex-d01396214ff5`；dry-run resume 正确 attach 而非新开；PTY 断线测试通过（0 模型调用）；TUI SIGKILL 后 daemon 仍写 rollout；`codex` 经 `.bashrc` 启动显示 `← for agents` 且不新建 legacy 会话；`codex doctor` 0 fail。
- 未完成/下一步：① 用户现有 4 个 legacy 会话仍在跑，未强杀；完成后退出，之后新会话走 daemon；② SIGHUP 实测已通过（TUI 收到 SIGHUP 后 daemon 内 sleep 120 仍于 121s 后完成并写出文件）；仍建议用户用真实任务复验；③ `01a16780…` 测试 thread 未删除；④ opencode.service 每 3s 重启 1768 次，已记 FL-D156，未修。
- 文件：`tools/ops/codex_persistent.sh`、`tools/ops/verify_codex_persistence.py`、`tools/ops/install_codex_persistence.py`、`~/.local/bin/codex-persistent`、`~/.local/bin/codex-daemon-ensure`、`~/.config/systemd/user/codex-app-server.{service,timer}`、`~/.codex/app-server-daemon/settings.json`。

## 合同双版本对比开发断点（2026-10-23，当前任务优先）

- 目标：独立确定性 compare pipeline、DOCX 文字高召回、前后端/持久任务/worker、20真实base 14dev6holdout mutation评测、独立review、浏览器验收。禁止生产部署；LLM调用0/费用0。
- 环境已核实：hostname iZf8zemhifedxdow1zefr0Z，instance i-f8zemhifedxdow1zefr0，同机172.28.217.241；Python必须 `.venv/bin/python`（系统python3.6不可用）。branch feat/contract-compare，HEAD a36acd2。当前compare代码全未提交；用户已有recall/generation/旧测试/运维和evidence改动不得覆盖/清理，禁止整仓库add。
- 已实现：fundlex/compare 全套 models/normalize/parser/align/text_diff/render/store/service/api/worker；frontend/compare.js/css + index nav/页面 + app.js 小adapter；api.py最小接入；设计文档；tests/test_compare_*；tools/evaluation/compare_fixture_builder/gold/evaluate/benchmark/e2e。
- Baseline全量：1103 passed/35 skipped/1 failed（test_append_applicability::test_g16_summary_business_anchor_is_considered_under_generic_heading），log `/tmp/fundlex-compare-evidence/baseline-pytest.log`。
- 最近compare suite：41 passed/4 skipped（MySQL opt-in），修gold structural zero后已通过corpus4。system reviewer隔离真实MySQL 8.0曾11pass，修finish/retry stale CAS与upload/seal锁，fixtures已改真DOCX。MySQL实例由reviewer管理，未碰生产。
- 实际发现修复：FL-D149/150/151 已记录；align长文本快速评分+cache；multi-block fuzzy不能吸收exact constituent；重复paragraph插入/删除真实漏覆盖已修；renderer已改offset准确virtual anchor、空docfallback、真正table结构、无silent overlap discard；parser新增递归nested/cell SDT（待reviewer回归），unknown可见结构应warning。frontend File refs保存且add/remove增量DOM；folder未配对显示、token隔离、创建后轮询、pane内滚动。
- Corpus `/tmp/fundlex-compare-corpus-v4`，20bases386mutation；初gold-v5 a8ba42...，v6修错误structural zero（B07 merge实际挪heading）hash58390e...。刚进一步修zero检查使用去空白可见字符流避免正常split被误取消expected_zero，需再冻结v7并最终跑全指标。不能修改gold迎合算法；原v5/v6保留。
- v6实际指标：dev272pairs，gold operations219/219，modify112/113，zero fixtures69；holdout114pairs，ops92/92，modify46/46，zero30；median0.620/0.653s，P95 0.897/0.942s，max2.096/2.759s。硬门 identity20/20，symmetry20/20，determinism20bases各5次20/20。注意集中FL-D152里分母刚写错（pair误作target，modify也写错），收尾必须更正为实际最终报告。
- 浏览器旧工具16/16通过 `/tmp/compare-e2e-review-final2.json`；仍需扩展到单组exact1modify、3组、20+diff、空侧、folder未配对、真实corpus页面上传worker。agent independent_frontend_review 正独占 tools/evaluation/compare_e2e.py 增补，root改frontend/render互不冲突。
- 活跃agents：algorithm_final_review 独立算法攻击/新增 tests/test_compare_review.py（已发现nested/cellSDT漏文本，root刚修parser）；independent_system_review 汇报MySQL/并发最终复查；independent_frontend_review 扩展E2E。无生产部署，无模型进程。
- 全量pytest正在 session16478，output `/tmp/fundlex-compare-evidence/final-pytest.log`，2026-10-23约13:5x启动，轮询工具write_stdin；最终当前代码若再修需合理重跑。
- 下一步：完成review发现修复和局部tests；v7 gold冻结+dev/holdout/hardgates，真实20pair benchmark（冷cache）含大小/blocks/peakmem；扩展browser；全量回归；集中问题登记/设计与最终证据报告；只commit compare相关文件，保留用户未提交代码。生产部署NOT PERFORMED。

## 合同比较最终收尾断点（2026-10-23 17:45，未提交/未部署）

- 当前分支 `feat/contract-compare`，HEAD `a36acd23d810aef2d8338e06698ed76c3e6b3c59`；工作区同时保留其他 agent 的引擎、旧测试、运维和 evidence 改动，禁止整仓库 add、reset 或覆盖。Compare 全套仍为未提交文件；本轮没有 commit、push、生产部署、服务重启、nginx/生产DB迁移或真实模型调用。
- 已完成实现：独立 `fundlex/compare` parser/normalize/align/text_diff/render/store/service/api/worker；工作台 `frontend/compare.js/css` 与导航接入；上传完整DOCX校验、对象/结果SHA、LONGTEXT、owner/idempotency、批量pair隔离、lease/fencing、严格span与renderer边界校验、bounded transient retry、固定错误码；worker systemd模板仅新增文档模板，未安装启用。
- 最新 compare 专项：`.venv/bin/python -m pytest tests/test_compare_*.py -q` → **70 passed / 5 skipped / 1 warning**；隔离MySQL8 port33155：`FUNDLEX_COMPARE_MYSQL_TEST_URL=... .venv/bin/python -m pytest tests/test_compare_system_review.py tests/test_compare_worker.py -q` → **28 passed / 1 warning**。Node `/tmp/opencode/node-v20.18.0-linux-x64/bin/node --check frontend/compare.js`、py_compile、compileall、git diff --check通过。
- 最新浏览器开发验收：`/tmp/opencode/compare-e2e-current.json` → **24/24 checks、9场景、全通过**；真实临时FastAPI+CompareWorker，单modify/0 diff/三组导航/25差异/insert-delete-modify/空侧anchor/folder手工补配/全失败/公开合同incomplete/XSS/身份隔离/SVG resize+独立滚动均覆盖；SVG三次误差均0px，无pageerror。截图 `/tmp/opencode/compare-e2e-current-shots/`。
- 冻结算法证据保持有效：compare算法及独立gold/evaluator源哈希与 `/tmp/opencode/compare-continuation/source-freeze-final.json` 一致；20 bases、386 mutation，dev 219/219 operations，holdout 92/92，identity20/20，symmetry60/60 directional，determinism20/20；dev modify112/113，holdout46/46。最终数字、gold与暴露holdout说明见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 的 FL-D152 最终指标更正与 `/tmp/opencode/compare-continuation/FINAL_SUMMARY.md`。
- 独立算法复查：42种分段的1764对、1500组随机重排/修改攻击无零差异漏报、无双向不对称；已知限制是结构变化伴随局部修改时可能保守降级为整组delete+insert，已补FL-D152。系统复查发现的FL-D160过期清理覆盖终态、FL-D161重解析临时I/O已修并用临时MySQL验证。
- 本轮并行引擎兼容性修复：`fundlex/recall.py` 的 G16 site guard 对无 `location` 的简化测试替身返回 False；定向测试与完整回归均通过。最终 `.venv/bin/python -m pytest tests -q` → **1195 passed / 40 skipped / 2 warnings / 247.79s**，日志 `/tmp/opencode/compare-final-pytest-2.log`；FL-D162 已解决并更新集中记录。
- 最终收尾验证：启用隔离临时MySQL8（port33155）跑完整 compare → **75 passed / 1 warning / 14.31s**；本地 compare → **70 passed / 5 skipped / 1 warning**；最新浏览器 `/tmp/opencode/compare-e2e-final-current.json` → **24/24 checks、9场景、全通过**；Node/py_compile/compileall/diff-check通过。系统/worker关键并发回归额外重复5轮，每轮2 passed。
- 下一动作：只整理报告和供用户审阅的文件清单；当前默认不提交，保留所有未相关改动。最终回复必须明确 `Production deployment: NOT PERFORMED`、模型调用0/费用0，以及真实生产用户链路未执行。若后续用户要求提交，必须只选择compare相关文件，不能整仓库add。

## SSH 持久运行与权限配置（2026-10-23，FL-D147/FL-D148）

- 当前用户任务：解决关闭 SSH 后 Codex turn interrupted，并明确授权 Codex 完整本机权限；不涉及产品引擎修改或生产部署。分支 `refactor/recovery-architecture`，本轮读到 HEAD `a36acd23d810aef2d8338e06698ed76c3e6b3c59`；保留其他会话的引擎、测试和证据未提交修改。
- 已做：安装 tmux 2.7；安装 `~/.local/bin/codex-persistent`、`~/.config/fundlex/codex-tmux.conf` 与 `.bashrc` 的交互 `codex()` 函数；备份 `.bashrc`。用户 `~/.codex/config.toml` 设置 `approval_policy=never`、`default_permissions=:danger-full-access`，备份 `config.toml.bak-full-access-20261023-110532-742946`（600）。doctor 确认 Never/unrestricted；现有会话仍保留启动时权限，需要重开。
- 验证：`tools/ops/verify_codex_persistence.py` 真实 PTY 关闭后 worker 继续完成、重连接回相同进程，0 模型调用。Codex standalone 默认 app-server 启动失败（缺完整 package），加 `--no-daemon` 后真实客户端在 tmux 保持运行；同一聊天显示另一客户端写锁，未强抢。
- 收尾状态：`tools/ops/` 源码未提交；11:22 已同步最终 wrapper（含 `--no-daemon` 和显式 full-access flag），关闭 `client-diagnosis` 副本，最终 PTY 断线与同进程重连复验通过，syntax/compile/diff-check 通过。复现 `.venv/bin/python tools/ops/install_codex_persistence.py` 和 `.venv/bin/python tools/ops/verify_codex_persistence.py`，需宿主执行环境；当前旧沙箱已批准对应脚本前缀。新权限由新 invocation 验证，当前聊天仍受其原启动策略限制；用户应结束旧客户端后，新开 SSH、进入项目并运行 `codex resume --last`，之后同目录 `codex` 自动接回持久会话。
- 不改生产服务/SSH 守护配置，不打印/入库凭据；本轮无子 agent，无真实模型消费。新 shell 中同目录输入 `codex` 自动接入持久会话；旧聊天接续用 `codex resume <session-id>`，原客户端应先退出以释放锁。

## Codex 初始页与显式接回（2026-10-23，FL-D152）

- 用户反馈普通 `codex` 自动进入旧运行对话；原因是上一版 wrapper 固定 session + `new-session -A`。已改为普通 `codex` 每次新建 tmux session，`codex attach` 才按工作目录前缀接回最近旧 session，`codex resume --last` 继续官方历史聊天恢复。
- 已同步 `/home/opencode/.local/bin/codex-persistent`；旧活动 session `codex-d01396214ff5` 保留，未强制关闭。最终 PTY 持久测试通过：断线后完成、detached、attach 同一进程；syntax/compile/diff-check 通过。

## 目标合同闭环对话 stale lock（2026-10-23，FL-D153）

- 目标会话：`01a16485-b7ba-7090-99cc-51cb1c5fa0ab`，标题“优化 FundLex 合同修改闭环”。确认无对应运行进程，仅存在 10:26 的空 writer lock。
- 已将锁保留移至 `/tmp/fundlex-codex-stale-locks/01a16485-b7ba-7090-99cc-51cb1c5fa0ab.lock.20261023-134825`，释放原路径；当前两个活动 Codex 会话未停止。用户可重新切换该会话；若有其他客户端同时打开，需先关闭它。

## 当前前后端审查断点（2026-10-22，FL-D143）

- 最新用户要求：检查前后端交互与前端设计，暂不检查查找修改点及写 DOCX 引擎。当前不做真实模型调用或生产部署。
- 分支 refactor/recovery-architecture；收尾读到 HEAD `943830a33d41dccd7250bdcc36eae43da6d63c7a`（现场有其他会话推进证据提交，继续前重查）；本轮没有提交/推送，不覆盖他人引擎与证据内容。
- 本轮未提交文件：frontend/app.js/index.html/app.css、fundlex/api.py/tasks.py/guide_store.py、tests/test_tasks_api.py/test_guide_api.py、新增 tests/browser/test_workbench.py，以及本文和集中问题记录。详见 FL-D143。
- 已实施并隔离验证：未执行条款误标已修改；revision 字符串 ID 配对/checkbox/旧 review 响应；upload 草稿被旧请求污染；成功/异常去重统计、running/leased 筛选；单一支持模式、重复单位、总览轮询；failed 指引显式重试/去重；过期提示/身份展示残留。收尾增加排除/历史评测进度、含例外交付不可直接使用、业务问题摘要、无结果下载禁用、不可用指引说明、生成后恢复导航禁用状态。
- 验证：主改动后全量 `.venv/bin/python -m pytest -q` **1075 passed / 24 skipped / 2 warnings / 211.95s**；最后前端补充后相关 API/认证/指引/修订回归 **94 passed / 30.48s**，中文字体环境下 Chromium **29 passed / 38.03s**；Node syntax、compileall、diff-check PASS。前后端流程与报告/修订审查在 1440/768/390 无横向溢出、无 pageerror，中文截图人工复核。
- 复现浏览器：`FONTCONFIG_FILE=/tmp/fundlex-ui-fontconfig/fonts.conf FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_workbench.py -q --basetemp=/tmp/fundlex-ui-browser-zh-verified`；字体在 `/tmp/fundlex-ui-fonts/`，截图在 `/tmp/fundlex-ui-browser-zh-verified/`。这些仅是 UI fixture/临时 SQLite API 测试，不启动 Worker/真实模型。
- 预算/进程：本轮真实模型 0 calls/$0，不消耗前序引擎账本；无子 agent，无遗留测试服务。工作区修复已验证，生产未部署，查找目标和 DOCX 写入引擎未修改。保留他人 `docs/evidence/final-validation-20261022/` 的未跟踪材料。
- 下一步：如发布本轮改动，先核对并行引擎变更的冻结/发布状态，再按正常部署流程复核生产资源和真实登录路径。本轮不宣称项目最终真实合同验收完成。



## ff4d749 exact-code Gate 断点（2026-10-22，优先）

- **code_head=`ff4d7498b6c1aee72ba48686074d021fc7f84791`；evidence base=`387e334`（docs-only）。** 新证据根 `docs/evidence/final-validation-20261022/revalidation-ff4d7498/`；旧 682e68a bundle 未覆盖。
- 离线 1061 passed/0 failed/6 skipped/207.10s，compileall/diff-check PASS。四例 live record exact code：calls 32/35/29/34（合计130），cost $0.11742255；全部 incomplete，TRUE 24/例，TRUE→NOT_APPLICABLE=0；四例 working_final/redline 均生成，plan→artifact 0 mismatch；四例 replay 0 HTTP/0 tokens/0 cost 且 14/14 语义检查 PASS。D16 六 stage same_head=true、model_calls=0。
- 旧 finding：D02 absent、D11 G02、D16 G05、D16 Audit B 关闭；D01 overlap 仅 PARTIAL（artifact 已生成，但 G17 same-operation conflict 仍在）。
- **Gate=DO_NOT_ENTER_20_CASE**。剩余 root cause：G16 四例未 append；D01/D16 G17 duplicate/subset conflict；D02 G12/G13 joint edit 被 replan 丢失（回归）；D11 G18 summary p1207 false proof；D16 G12/G13 residual；G06 四例 absent literal 无 site proof；D01 G01/G02 split+B false audit；D11 G05:2 false block。
- 独立 Reviewer：Business BLOCK；Architecture 4 BLOCKER/6 HIGH；Recovery 4 BLOCKER/5 HIGH/8 MEDIUM；Test conditional（index/stage identity 已在证据修正）。本轮未改 runtime、未部署、未跑 20/514。
- 下一动作：按 `summaries/architecture-review-ff4d749.md`/`recovery-review-ff4d749.md` 的最小通用修复顺序修 G16/G17/G12-G13/G06/G01-G02；每项 regression；完整 pytest；新 code SHA 后重新四例 live+replay+四 Reviewer；不得用本 bundle 冒充验收通过。

## 接续断点（2026-10-22 07:00，前序 agent 断开后）

- **当前版本**：HEAD `682e68a5b3ef2a58feb77460af70afabdb314379`，分支 `refactor/recovery-architecture`，ahead 2（`22c15aa`、`682e68a`），未 push。工作区有未提交修复，涉及 `fundlex/recall.py`、`recall_pipeline.py`、`generation/claim_replay.py`、`generation/effects.py`、两个验证测试文件及未跟踪的 `docs/evidence/final-validation-20261022/`。
- **上一冻结证据**：exact-HEAD `682e68a` 全量 1024 passed/0 failed/6 skipped；四例 record 均完成但 Gate FAIL：D01 `not_generated`（EDIT_OVERLAP_OR_ADJACENT，无 DOCX），D02/D11/D16 `incomplete`，业务复核 5 项 BLOCKER/HIGH（absent 占位 proof、G02 分隔符、G05 会务条款误绑、Audit 无证据意见、D01 重叠）。D02/D11/D16 final/redline 与 FINAL_EDIT_SET 程序化零差异。
- **已实施未提交的最小修复**：
  1. Claim Replay 排除 `state=absent`、`attribution_error` 和 `claimed_operations` 作为 operation/site proof；避免无关 heading 产生 VERIFIED_ABSENT 或 falseblock。
  2. G02/G04 already-satisfied proof 按类别集合等价，接受 `A类及D类` 与 `A类、D类`；split 段落允许由含两类费用条款的报价证明 site，但仍拒绝 heading。
  3. G05 residual/effect proof 绑定份额类别设置/费率调整业务站，拒绝持有人会议费用豁免条款。
  4. `replan_sites` 改为按稳定 operation/site（而非会重编号的 target_id）保留/重绑；保留旧计划中合法的 p758 G15 duplicate delete，避免 duplicate-site 未编辑和 EDIT_OVERLAP。
- **离线验证（当前工作区，无模型调用）**：
  - D01 plan revision 2：18 edits / 0 conflicts；`build_docx_edits`→validate→generate 成功，G15 p758/p1221 均删除。Claim 仍剩 G01 p91、G02 p91/p92、G05:2、G06、G16；不是本轮 duplicate/overlap 误报。
  - D02 claim replay：12→4 failures；G02/G03/G04/G08/G09/G11/G12/G14/G22 已由 false failure 转 PASS；G05:2/G06/G16 继续 OPEN，G01 p93 真实 missing。
  - D11 claim replay：G02 delimiter false failure 消失；剩 G01 p91、G05:2、G06、G16。
  - D16 claim replay：G05 会务条款 false failure 消失；剩 G01、G06、G12/G13、G16、G17 真实 residual/缺失。
- **当前验证**：工作区全量离线 **1061 passed / 6 skipped / 2 warnings，219.40s**；修复已提交到本地分支，用户未要求 push，默认不 push。D01 split class-definition 的 G02 site 归属与 G01 append 已由 live 等价模拟关闭；G06/G16 仍缺有效 site/target；D16 G12/G13/G17 residual、BUS-FINAL-003 Audit 无证据意见仍待处理。之后新 SHA 重新四例 record/replay 与 ≥5 份真实合同验收。未部署、未跑 20/514，Gate 仍 FAIL。

## 新SHA四例record断点（2026-10-22，优先于以下）

- runtime冻结682e68a5b3ef2a58feb77460af70afabdb314379（ahead2，未push）。exact SHA完整1024passed/0failed/6skipped/200.45s；compileall/diff-check过。新证据docs/evidence/final-validation-20261022，原root20261021保留。
- D01新record35calls/$0.02569695/158.46s，not_generated EDIT_OVERLAP_OR_ADJACENT stage audit，无DOCX。Recovery agent零HTTP full replay复现，定位replan_sites单遍dirty_ids依赖target重新编号，旧G08 T007被保留+新T010 G08重复规划。diagnostics/D01-overlap-root-cause.md及capture/trace均保存。最小修复待D16当前record结束后实施，不重构writer。
- D02新record26calls/$0.02805225/127.21s，incomplete，24TRUE=7verified/5already/12unresolved。真实final/redline存在；programmatic source+finaledit→actual零差异，接受redline=final/拒绝=source。Business发现P0：state=absent占位heading p1036通过claimed_operations进入Claim verified site；导致falseblock以及G05:2/G06:0无关site VERIFIED_ABSENT。须排除absent/rejected/unattributed占位为proof，TRUE保持OPEN。Business reviewer继续只读，未修。
- D11新record25calls/$0.02588070/109.45s，incomplete，24TRUE=12verified/8already/4unresolved，artifact待business review。
- D16新record正在exec session23552，已22completed+1reserved（以实际状态为准），不要重启。完成前不改runtime，以保四例SHA一致。
- 活跃agents recovery_final_review只读诊断D01+absent入口；test_review只读stage/failclosed验证（D01sixstage缺Claim/obligation边界正确failclosed，D02全stage待结果）；business_final_review直接读新DOCX。Architecture上一轮CROSS001/002复审已0BLOCKER/HIGH，但新P0/P1尚未修，Gate FAIL。
- 预算原每case192/$0.60不变，已用累计：D01 164/$0.11800455余28calls；D02 76/$0.09072705余116；D11 79/$0.08133990余113；D16此前48/$0.06087105+当前未完。凭据仅进程内，ledger /tmp/opencode/final-validation-20261022，不改生产。
- 下一动作：D16完成→保存四例此SHA完整record/replay与business failure baseline→最小修复D01稳定op/site dirty closure与Claim absent proof gate+regression→新full freeze。不要旧cassette冒新record；D01剩余28不足一整轮平均calls，必须如实标预算限制，不增加预算。最新用户要求后续≥5完美合同+全前后端+性能，不能因此放松验证或伪称完成。

## 最新用户补充（2026-10-22）

- 当前最终验证任务完成后，用户要求继续组织多个agent自行推进后续修复/前后端逻辑检查，中途不自停/不询问，目标至少5份真实合同准确完整修改且单份耗时合理，为次日展示准备。不得放松原Gate、验证标准、预算/retry或伪称完美；先当前Gate再推进后续。
- 当前runtime编辑未冻结：Test agent正在修Architecture复现CROSS-001（compose任意replacement子串自授权负面review），Recovery agent正在修CROSS-002（Sweep已有target/no-plan被classify送TARGET）。Architecture只读反例交叉验证。完整1019pass/6skip是两条HIGH修复前，修后须完整实跑。

## 最终冻结准备（2026-10-22，优先于以下历史）

- 再次fetch/checkout/pull，HEAD22c15aa，remote4f3229d，ahead1；所有已有改动/证据保留。机器身份符合AGENTS规定。
- Architecture/Test/Recovery源码修复结束，正在完整重跑pytest；第一次1018passed/1failed/6skipped为末次编辑竞态，当前单项已通过；最终全量日志/tmp/fundlex-pytest-final.txt，exec session54854（查询实际状态）。compileall/diff-check通过。
- 未冻结/未push，未新live。接下来完整通过→commit runtime→新独立root四例record/replay，剩余预算继续扣：D01 63HTTP/$0.5076924，D02 142/$0.5373252，D11 138/$0.5445408，D16 144/$0.53912895。
- 当前Gate仍FAIL/PENDING，Business旧artifact问题已通用修复，但需最终新SHA artifact/四Reviewer验收；不得替换旧cassette。

## 最终证据收口接续（2026-10-22，优先于以下历史）

- 当前分支refactor/recovery-architecture；HEAD 22c15aa（未push）；fetch→checkout→pull已再次完成，remote仍4f3229d。本轮开始工作区已有ACTIVE_HANDOFF/runner修改和untracked全部evidence，已保留。
- 四例22c15aa live record均完成：D01 53/$0.04782，D02 47/$0.0496368，D11 51/$0.04332405，D16 43/$0.04055925；均incomplete、24 TRUE、TRUE→NOT_APPLICABLE=0。含旧4f3229d失败录制累计281HTTP/$0.27131265；每case192/$0.60总限额不增加。新录制前须继续扣除D01累计129、D02 50、D11 54、D16 48。
- 四例实际DOCX全部存在；programmatic source+FINAL EDIT SET→final零差异，final零修订；Business独立确认redline接受=final/拒绝=original均0差异。现有4例artifact可用作failure regression，不能证明后续新SHA。
- Business审查 `docs/evidence/final-validation-20261021/revalidation-22c15aa/summaries/business-review.md/json` 报BLOCKER1/HIGH3：delete residual虚假PASS与G16 duplicate只证一份、G11 explicit ONE_OF nested重复写、G22目标截尾留下“配。”、unsupported audit/sweep falseblock。细节FL-D142已更新。
- 主agent已修scope_map用set导致跨进程rule order变化/Inventory cassette miss，保Guide顺序。3个不同PYTHONHASHSEED context SHA一致已独立验证。新增tools/compare_frozen_replay.py比较facts/scope/targets/attribution/obligations/plan/replay/delivery/recovery和实际DOCX文本，检查0HTTP。
- 活跃agent：architecture_review负责effects.py/Claim跨段residual、原文duplicates独立siteproof，continuation regression先失败（joint绑定后单段语义再次False），现agent报告已修并在跑全组和四例Claim stage；test_review负责recall.py/recall_pipeline.py的G06 composite site guard、G17 sweep semantic、G11 ONE_OF绕过atomic先merge、G22 fuzzy同段句尾重绑定（最多12 chars且句界证据），新tests已82passed/1deselected（唯一失败属architecture正在修）；recovery_final_review独立审查真实history与源码，未交报告；business_review完成并idle，最终新SHA四例待复审。不要并行编辑同一agent所管源码/集中记录。
- 未完成：effects全组/四例旧artifact当前Claim离线重算；BR004其余G02/G04/G18错误facts意见/G05无备案证据仲裁；完整pytest（最终代码必须重跑）；冻结提交新SHA；以剩余额度新根目录四例record（不要旧cassette补位）→全replay0HTTP+semantic比较→D16六stage/revision selection→四Reviewer复审→Gate→证据提交push。不部署，不跑20/514，当前Gate FAIL。
- 运行中没有live任务；最新pytest运行已退出。系统Python3.6不可用，所有命令用.venv/bin/python。凭据只从sudo读取env到record进程内存，不输出/入库。现证据目录约40MB，安全模式扫描未见API key/Bearer；实际提交前再查。
- 当前运行代码未提交（git status为准），targeted回归仅局部，不可用992passed旧SHA当新证明。本环境无手动context压缩工具，已持久化本断点，接续优先读本段+FL-D142。

## 冻结版本与真实重录（2026-10-21，进行中）

- 运行代码已提交 `22c15aa4d8d736f2a2fc46a29bc3ed8611475f2f`，未push/未部署。该SHA完整实跑992 passed/0 failed/6 skipped/196.14s，compileall/diff-check通过；日志 `/tmp/fundlex-pytest-22c15aa.txt` 和 revalidation目录logs。
- 两处P0 occurrence、Audit同址sibling identity、record/error replay、class-set display、G05标点、incomplete append anchor、Audit dirty-site/no-progress已修，有新增regression；Architecture/Recovery复审代码范围BLOCKER0/HIGH0，业务实际artifact待验证。
- 新证据 `docs/evidence/final-validation-20261021/revalidation-22c15aa/`，index绑定SHA和剩余额度。旧四例保留原位。runner `tools/validate_frozen_case.py <case> record|replay --root <directory>`。当前外层exec session **68057** 顺序D16→D01→D02→D11 record（须用write_stdin轮询，不用functions.wait）；进程是否仍运行以ps为准。未增加模型并发/retry/总预算。
- 每case后续限额已扣首轮：D01 116 attempts/$0.5555124；D02 189/$0.586962；D11 189/$0.58786485；D16 187/$0.5796882。真实模型deepseek-v4.1-flash/上下文32000/output8000继承配置，凭据只内存。
- 增加evidence `review_artifacts.py` 可独立逐段对比source→final plan→DOCX并生成TRUE obligation证据表（无模型）；实际结果尚待。下一步：等待record、artifact复核、四例零网络full replay与D16六stage/revision selection、四Reviewer实际证据复审→Gate→提交push。不得旧bundle补齐或将无artifact填0安全错误。

## 最终验证接续（2026-10-21；优先于以下历史）

- 用户最新任务是最终验证、证据收口、最小修复、独立审查、Gate、提交 push；不是旧“只push”任务。起始 HEAD `4f3229d901bda33332a8abee3d909b7550f07ff0`，branch `refactor/recovery-architecture`，已fetch/checkout/pull，起始clean。
- 全量fresh离线 976 passed / 0 failed / 6 skipped / 199.41s；compileall通过。日志/四例真实证据 `docs/evidence/final-validation-20261021/`。
- 四例record首试均not_generated，无最终DOCX：D01 cassette conflict；D02/D11/D16 inventory output truncated。87 calls / $0.08997255；本轮总预登记768/$2.40、每case192/$0.60，后续扣除已用，不加预算。未部署、未改生产配置/账本、未跑20/514。
- FL-D142登记全部发现。主agent正在做bounded truncation split、cassette full-request复用/错误录制、无凭据replay、Stage参数/边界、occurrence dedupe、class-set label最小修复。源码未提交，`git status --short`为准；新tests fixture尚待通过；必须修后全量重跑。
- 三位独立Architecture/Recovery/Test reviewer已完成初审并发现BLOCKER/HIGH；Business Reviewer运行中，后续实际artifact需复审。没有运行中的record进程。
- 下一动作：完成小修/回归→提交代码冻结新SHA→以剩余预算独立录制四例（保留首试）→full/stage零网络replay→DOCX逐operation证据审查→四Reviewer复审→Gate→证据提交push。不能用历史artifact替代，不把缺验证当0缺陷。
- 无手动压缩工具；断点已持久化。所有凭据只在进程内读取，不打印/入库。


## 最新状态（2026-10-21，按用户要求仅提交和推送）

- 用户最新指示：“我只是让你继续推送而已，不用做别的”。本次停止其余开发、真实模型验收与部署，仅提交并推送当前 `refactor/recovery-architecture` 工作区。
- 推送前基线 HEAD `00312e3bae7047c4ca04762d8f2739bd130894ed`；fetch → checkout → pull 已再次完成，origin 未变化；工作区包含本轮最终收口改动。
- 本次审查补充：移除 Sweep 的旧 rule-level satisfied/first-required-text 关闭路径，统一由 operation/site artifact proof 仲裁；静默 re-sweep 不再单独关闭 finding；删除 Projection 未使用的旧 satisfaction helpers。针对性回归 **77 passed / 22.59s**，输出 `/tmp/fundlex-final-review-tests-2.txt`；`git diff --check` 通过。
- 历史完整离线回归 **977 passed / 6 skipped** 适用于上述审查补充之前；补充后未重新跑完整回归。中间误删 `_document_compact` 引发 NameError，已恢复并由 77 项回归验证；`_finding_evidence` 是本次有意移除的旧独立判断路径。
- 本次 live 调用/费用 0，未部署。真实合同 Frozen record 与真实工作台交付仍未完成，不能将推送或离线验证宣称业务验收完成。
- 源码、测试与集中问题记录随同一次提交；实际提交 SHA 以 `git log -1` 为准。


## 最新接续断点（2026-10-21，离线回归通过；最终收口尚未验收）

此段优先于下方历史断点；下方 883/59、90/4 等结果只保留历史，不代表当前工作区。

- 目标/约束：完成用户 1—40 项整链路收口；不降低 Validator/Claim/G02/G04、不忽略 residual、不加 retry/模型预算。用户末尾只写了 Stage Replay 标题，因此现有接口按冻结阶段输入实现，不杜撰额外规格。
- branch `refactor/recovery-architecture`；HEAD `00312e3bae7047c4ca04762d8f2739bd130894ed`。起始 fetch→checkout→pull 已完成且当时 clean；本轮继续时已重读 HEAD/status。全部工作区改动未提交、未推送、未部署，`git status --short` 为准。
- 最新完整离线测试：`.venv/bin/python -m pytest tests -q` → **977 passed / 6 skipped / 2 warnings / 199.30s**，输出 `/tmp/fundlex-final-offline-3.txt`。`compileall`、`git diff --check` 通过。第二轮曾 973 passed/1 failed（Worker 停机竞态），已修复并完整重测。针对性 dirty-site/Frozen 测试 33 passed，主链路 99 passed。
- 完成并验证：Guide Gate/显式历史 ONE_OF、TRUE completion invariant、Primary class-set completeness、排除双认证、Applicability 前置、site-scoped OperationEffectEvaluator/Claim/Projection、Audit 无证据意见仲裁、final ledger 重算、四层 Claim root-cause 路由、Final Sweep 至多两轮、相关站点签名复用与冻结回放。
- 本次新增实质修复：Audit missed-target 按 operation/site 去重；Sweep 不借其它 site 的 proof；delete residual site-first + 无关邻段反例；append 不再借用全文政策证明或邻段锚点，摘要独立发现；同段 deterministic edits 合为 atomic paragraph 并保留 component 账本；Claim 按 FINAL parent edits 重建实际产物；Joint Compose 同 rule 独立 operations 全部保留；Claim generation recovery 只重算 dirty sites，execution 复用原计划。见 FL-D140。
- 新文件：`fundlex/fact_evidence.py`、`qualification.py`、`frozen.py`、`stage_replay.py`、`generation/effects.py`、`generation/atomic.py`、`tools/replay_stage.py` 与两组新增测试。已迁移旧测试中的隐式 ONE_OF/无证据关闭/章节末尾 append/缺少 operation identity 等断言；未改独立评测 gold。
- Guide 运行门实测：source `b77be53c3439d785a9ffad0f09d8d03ba74f7722397576b999ae6f5dd6eef895`，document `45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7`，22 rules/34 operations。
- 模型/预算：本轮 live 请求 **0**、费用 **0**，无新生产任务、无子 agent、无运行中的本轮进程；未改 `/etc/fundlex-recall.env` 或生产账本，未跑 514。机器主机名/实例/内网均已核实，curl ifconfig.me 返回 IPv6 出口，不把内网当其它机器。
- **仍未完成**：最终变更审查（尤其认证裁定来源、真实 wording/duplicate 完整覆盖、Audit/Sweep 共用 evaluator 的剩余旧 helper）、真实合同 Frozen record/replay 验收、真实工作台登录→上传→Worker/模型→修改 DOCX→结果页→授权下载→实际文件/红线/报告哈希核验；没有真实 complete 验收，不能宣称总体完成。
- 下一条动作：先审阅当前 diff 与 `docs/RECOVERY_FINAL_AUDIT_20261021.md`/FL-D140；确认冻结回放目录与现有预算账本，在现有授权/预算内安排一次真实工作台验收并录制 cassette。失败时从冻结阶段回放定位修复，不重复 live 调试；若预算/服务阻塞，如实登记，勿增加预算或绕过发布门。
- 上下文：本环境没有可调用的手动压缩工具；已持久保存源码/测试/断点，下一上下文从本段继续，不重复审计或旧真实调用。


## 本轮实施补充断点（2026-10-21，未完成/未部署）

- HEAD 仍为 `00312e3bae7047c4ca04762d8f2739bd130894ed`；全部最终收口改动未提交，`git status --short` 可核对。无子 agent，live 调用 0/费用 0。
- 已完成针对性一批 146 passed；后续 pipeline 37 passed/2 failed 属旧 fixture（缺 operation metadata、故意漏 D 类），已迁移为认证 IR 与不完整集合阻塞测试。该结果不代表当前全部代码通过。
- 新增/接线：Guide certification、Primary class-set proof、exclusion 独立认证、Applicability 前置、site-scoped effects/Claim/Projection、final ledger components、模型 cassette 与 Stage Replay。
- 最新正在验证：消除 Claim 的文字/单 operation 归因 fallback；Audit 无引文意见用 operation proof 仲裁；audit site signature；Claim 四层 root-cause 路由；执行故障复用计划；Sweep 移至 Claim Recovery 之后，最多两轮；FINAL_EDIT 过滤后重新 reconcile。
- 当前测试：`/tmp/fundlex-proof-recovery-tests-2.txt`（运行状态需核实）；前一轮 90 passed/4 failed，包含已发现 Sweep 引用旧 reaudit_only 和旧断言，尚待再次核对。
- 未完成：site-first delete residual、Audit missed operation 去重、显式 Guide schema/业务批准边界核查、Frozen 完整 boundary serialization/阶段实际回放、dirty recovery/no-progress 全链路和完整回归，以及最终真实工作台交付。
- 下一动作：查看当前测试文件并修复；为四层 recovery/ledger same-operation 不同 site/Scope correction/回放零网络增加实质性回归。禁止把离线通过或历史真实 incomplete 当作最终交付。

## 最新任务（2026-10-21，最终收口，进行中）

- 用户最新指令：完成整条 Guide→Facts→Applicability→Target→Plan→Artifact→Audit/Claim/Sweep→Recovery→Delivery 收口；先完整审计后实施。详细审计/分批实施账本：`docs/RECOVERY_FINAL_AUDIT_20261021.md`。用户消息末尾为“40. 新增 Stage Replay”（未附具体阶段接口）；按冻结输入+确定性阶段 CLI 实施，不虚构额外要求。
- 起始同步已完成：`git fetch`→`git checkout refactor/recovery-architecture`→`git pull`；HEAD `00312e3bae7047c4ca04762d8f2739bd130894ed`，branch `refactor/recovery-architecture`，working tree clean。
- 硬约束：不降低 Validator/Claim、不中断 G02/G04 occurrence safety、不把 failure 降 warning、不忽略 residual、不减少规则、不增 retry/预算。不用反复 live E2E debug。后续最终端到端仍须真实路径验证，不宣称离线替代。
- 已做：全链路审计表已保存；未启动新 live 模型调用；未部署。上轮理解项目时测试 939 passed/6 skipped 属旧 HEAD，当前基线历史记录为 942 passed/6 skipped，不挪用为新改动验收。
- 发现：内置 Guide 10 findings 的历史裁定缺 finding_id/approved/双 SHA，内置 document_sha 与实际 payload 不一致；Primary Facts 没有完整 class_set；Projection 仍多处 TRUE→NOT_APPLICABLE；Claim append/replace 用 after_full 跨 site 借证据；Applicability resolve 晚于 Inventory。
- 运行环境：同台 Linux 云服务器，API `127.0.0.1:8010`，公网 `https://fundlex.club`；本次 health 返回 401，匿名不可用是认证行为，不是监听失败。FL-D139 待更正。
- 预算/账本：本轮 live 请求 0，费用 0；不改生产 `/etc/fundlex-recall.env` 或 `/var/lib/fundlex/`。不自行跑 514。
- 下一动作：实现 certified guide + 显式 group semantics + TRUE invariant；继而 facts set completeness、统一 operation/site effects 与 frozen replay。每批保存 tests/剩余项；上下文不可观测，保守分段接续，不虚构压缩完成。
- 进程/agent：本轮无子 agent；既有 D02e 后台若仍运行属于前序会话，不重启或重复花费。

> ## ⚠️ 机器身份（先读这一段，禁止凭内网地址判断机器）
>
> **当前工作机 = 云服务器**，即本仓库所在处：
>
> | 项 | 值 |
> | --- | --- |
> | 主机名 | `iZf8zemhifedxdow1zefr0Z` |
> | 公网出口 IP | `8.155.130.168` |
> | 内网网卡 IP | `172.28.217.241`（**同一台机器**，不是另一台开发机） |
> | 区域 / 实例 | `cn-heyuan` / `i-f8zemhifedxdow1zefr0` |
> | 工作区 | `/home/opencode/fundlex`（专用用户 `opencode`） |
> | 应用部署 | `/opt/fundlex-recall-first`（systemd `fundlex-recall-api`/`fundlex-recall-worker`，API `127.0.0.1:8010`） |
> | 公网 HTTPS 入口 | **`https://fundlex.club`**（`www.fundlex.club` 同；Let's Encrypt 证书，nginx/宝塔反代 `127.0.0.1:8010`，80→443 跳转） |
>
> **本文其余部分的“本机 / 笔记本”一律指已停用的 Windows 开发机，绝不是当前工作机。**
> 接续 agent 开工前先跑一次身份采集：`hostname`、`ip -4 addr`、`curl ifconfig.me`、
> `curl http://100.100.100.200/latest/meta-data/instance-id`，用事实确认自己所在的机器。
> （本机器块为 FL-D061 的处置结果，见集中问题记录。）

更新：2026-10-16（服务器开发主副本 `/home/opencode/fundlex`，接续 agent **第 12 轮**：A/B 遗留规则集退出运行时，能力接口收敛为 engine 契约，交付语义改由指引版本状态决定，FL-D093/FL-D094/FL-D095，生产端到端验收通过）。规则：50% 整理、60% 前完成压缩/交接；本文只记状态与下一动作，不写密码。

> **第 12 轮要点（A/B 下线）**：见 [`docs/LEGACY_RULESET_RETIREMENT.md`](LEGACY_RULESET_RETIREMENT.md)。
> 运行时仅服务指引绑定的 recall-first；`capabilities` 只返回 `engine` 对象；`/api/tasks` 只接受 `engine_id`（传 `ruleset_version` → 422 `RULESET_RETIRED`）；`/api/batches` 创建 → 410；遗留任务只读且标记 `legacy`。
> A/B 代码与规则文件**保留**（测试与离线评测直接导入管线），但不再被运行时引用。
> 相关提交：`5615609`（方案）→ `beee73e`（后端收敛）→ `2b32e40`（测试）→ `93196d9`/`012ba18`（前端与遗留标注）→ `67410b3`（收尾）。部署副本与仓库一致，服务 active。

> **编号更正（FL-D077，2026-10-15）**：集中问题记录曾有 5 组编号重号，已把后出现者改为新编号（保留首次出现的原编号）：
> `FL-D057→FL-D072`（sweep 误报 G02/G04）、`FL-D058→FL-D073`（无服务费结论）、`FL-D068→FL-D074`（评分器短锚误判）、
> `FL-D069→FL-D075`（G17 跨段删除）、`FL-D066→FL-D076`（Codex bwrap）。
> **注意**：本文下文第 5/6 轮的历史叙述写于更正之前，个别处仍写旧编号，含义以更正后为准；新增条目一律先查重再编号。

## 当前断点（2026-10-20，Recovery 架构改造，本地已验证/未发布）

- **分支**：`refactor/recovery-architecture`（基于 `a2905ac` + REITs/ETF feeder 提交 `374440a`）。本轮架构提交：`f98d95c` 模型角色、`69a6a24` Obligation IR、`3e257f0` Validator 硬门、`c6bbf1d` Recovery、`838c9a6` 管线接线；文档提交待补。
- **完成内容**：`docs/RECOVERY_ARCHITECTURE.md` 与集中问题 **FL-D133**。核心为 obligation-first ledger、Primary/Review 独立角色、tri-state applicability、focused fact recovery、T3 locator、Joint Compose、Validator hard gate、claim replay 边界证明、统一 Recovery/FailureClass、用户三态交付摘要。
- **测试**：全量 `pytest tests -q` → **872 passed / 6 skipped**。离线 validator shadow（round14-12）：19 例 / 222 段 / **0 hard FAIL**。
- **真实模型（临时账本 `/tmp/opencode/realcheck.sqlite`，未触碰生产账本）**：
  - **D01 曾出现 false_complete，已修复门禁**：早期一版报 `complete_with_notices`（27 calls），独立 Business Reviewer 复核最终 DOCX 发现 G17 第二句仍留在 p760、G15 正文/摘要处理不一致。新增 delete-only 逐句残留检测、重复条款副本一致性、G05/G06/G01/G03 目标锚点后，D01 被如实阻塞为 partial（96 calls / 约 $0.052；audit 另发现 G09 第二处措辞缺失、G01 追加位置错误、G11 变体残留）。
  - **D02**（ETF 联接基金）：`eligible/open_regular`；116 calls / $0.0615；G05 compose 固定文本缺失 → partial（诚实失败）。
  - **D03**：32 calls / $0.0222；G06 复合目标未解决 → partial。
  - **D11**：99 calls / $0.0658；旧版 false_complete 被新门改为 partial（G15 误绑托管费、G09 第二处措辞缺失）。
  - 临时账本合计约 **963 requests / $0.5792**；以上为 agent 真实调用，生产账本未动。
  - **结论**：新架构已能发现旧版 false_complete，但尚未取得“最新硬门下真实合同 complete”的验收样例。Final Architecture Reviewer 的 G05 satisfied-target 隐藏 delete、G11 ONE_OF 被新文误判残留两个 blocker 已在 `039519f` 修复并有回归测试。
- **独立审查**：Architecture Reviewer 提出 5 个 BLOCKER + 5 个 HIGH；已修复 scope 遗漏静默、plan not_applicable 覆盖 TRUE、Validator/Replay flag 开关、claim recovery 旧 audit/sweep、类别枚举前缀、单 completed 掩盖 siblings、infra stop 吞咽。保留限制见 `RECOVERY_ARCHITECTURE.md` §10：无目标规则 T3 默认关闭、audit context 分批未实现、514 全量未跑、G09/G15 业务残留、前端未展示新字段。
- **已发布（2026-10-20 20:37 CST，快照 commit `0fae88e`）**：`bash tools/deploy/publish_workspace.sh` 成功；`fundlex-recall-api` / `fundlex-recall-worker` active；`/opt/fundlex-recall-first` 与仓库 `obligations.py` / `recovery/orchestrator.py` / `models/roles.py` / `recall.py` / `recall_pipeline.py` / `frontend/app.js` sha256 一致；`/api/capabilities` 200。生产 env：`FUNDLEX_GENERATION_STRATEGY=registry`、`FUNDLEX_MODEL_MAX_OUTPUT_TOKENS=8000`。
- **真实工作台端到端（已通过）**：默认入口 `POST /api/tasks`（`engine_id=recall_first`）→ 上传 D01 → seal → 真实 Worker/模型 → `/revisions` 19 条全部映射、目录保留、14 页 → 拒绝第 1 条 + 接受其余 18 条 → 下载 `selected_final` **136125 bytes / sha256 `efd9f20c59fddb96224876782e9b73f5c0670201440947aeeac4e90f62faeb1f`**，残留修订 0，被拒条目恢复原文，接受条目保留替换；`accept-all` 19 条成功；`working_final`/`working_redline` 仍可下载。任务 `db67ed71…`、文档 `9a0810a9…`、批次 `b72d9b42…`；交付状态 `incomplete`（如实，不冒充 complete）。
- **子集回归（最终代码，用户授权只跑部分，不跑全量）**：
  - D01：partial；93 calls / $0.0516；claim replay 17/17 verified；残留问题集中在 G05/G01/G08 审计与 G06/G15/G17 查漏（具体见任务报告）。
  - D02（ETF 联接基金）：partial；56 calls / $0.0636；claim verified 17 段；TARGET 7 / GENERATION 1。
  - D11：partial；125 calls / $0.0906；claim 失败集中在重复正文/摘要副本（DUPLICATE_SITE_UNEDITED）与 G15/G17 残留。
  - D16：partial；61 calls / $0.0554；G06 复合目标、G14/G16/G18/G22 audit pending 等。
  - 对照 round14-12：D02 原先可能被排除，现正确进入处理；D11 旧版报 complete 但属 false_complete，现 blocked；D16 旧版 integrated complete，现因更严格 target/audit 门 partial（需人工复核是否为过度阻塞）。
- **下一动作**：① 用户自行跑全量 514（agent 不自行跑）；② 修 G05/G06/G15/G17 目标与审计残留、D16 过度阻塞复核；③ 用子集结果调优后再发布；④ 全量/留出验收与最终报告。
- **预算/账本**：生产账本 `/var/lib/fundlex/model_budget.sqlite` 本轮未读写；agent 使用临时账本 `/tmp/opencode/realcheck.sqlite`（约 $0.45）。

## 当前断点（2026-10-19，前端改造第一批，已本地验证并发布）

- **范围**：全局 Toast（修复 FL-D121 成功提示不可见）、面包屑、页脚 + 版本号（`capabilities.app_version`）与帮助弹窗、筛选 Chip、任务列表“合同份数/成功异常/进度”、任务详情统计条与异常行高亮、批量导入进度条/异常标红/替换/条件跳转、修订审查 A/R + Toast + 上一份/下一份、指引问题展开 + “重新解析（自动修复）”。
- **文件**：`frontend/index.html|app.js|app.css`、`fundlex/api.py`（仅 `app_version`）、`tests/test_tasks_api.py`；问题状态见 FL-D121 / FL-D126 / FL-D127 / FL-D128 / FL-D129。
- **验证**：全量 `pytest tests -q` → **752 passed / 6 skipped**；本地 dev 实例真实浏览器四组：`ui_smoke` 25/25、`ui_review` 20/20、`ui_guide` 10/10、`ui_redirect` 6/6，0 页面/控制台错误。
- **已发布（2026-10-19，commit `c2851a8` 快照）**：`bash tools/deploy/publish_workspace.sh` 成功，api/worker active；`frontend/index.html|app.js|app.css`、`fundlex/api.py` 与部署副本 sha256 一致；`https://fundlex.club/api/capabilities` 返回 `app_version=0.1.0`；首页资源版本已变化（`app.js?v=35788dcc…`）；生产匿名页真实 Chromium 检查 0 页面/控制台错误。发布快照同时包含并行 agent 的引擎提交 `839ffe0`（其自测全量通过；如该引擎变更需单独批次验证，由对应 agent 继续）。
- 下一动作：用户在真实登录环境复验第一批交互；第二批待拍板项（月度统计/消息持久化/全局搜索/重试/审计）见集中问题记录 FL-D122～FL-D125。

## 当前断点（2026-10-20，任务总览改版方案 B，本地验证；**未发布**）

- **需求**：侧栏「批量导入」→「新建任务」；右上角用户区**不改**（产品负责人更正）；批量总览头部卡片（BATCH OVERVIEW、本月累计处理/平均秒数、完成率进度、新建/刷新）；5 个指标卡（本月处理合同/完成率/待处理/平均时长/异常）；「我的任务」表格 + 指引名称/筛选 + 「查看」；不改配色/Logo/全局基础样式/不新增图表。
- **后端**：`GET /api/tasks/stats?month=YYYY-MM`（owner 范围，CST 月边界；处理数/完成率/待处理/进行中任务/异常/平均秒数/环比）；`documents.started_at|finished_at` 迁移与 claim/finish/terminal retry 写入；`GET /api/tasks?guide_version_id=...` 筛选。
- **前端**：`frontend/index.html|app.js|app.css` 总览重构；用户区未改；指引名称由 `/api/guides` + `guide_snapshot.version_id` 映射；数值接 stats 接口，加载中 `—`。
- **验证**：全量 `pytest tests -q` → **875 passed / 6 skipped**；本地 dev 真实浏览器 **23/23**（总览数字、5 卡片、指引筛选、Chip、刷新、0 控制台错误），截图 `/tmp/opencode/ui-batch2/overview.png`。
- **未发布**：工作区仍有另一 agent 未提交的 `fundlex/generation/template.py`、`fundlex/recall.py`、`tests/test_recall_core.py` 等引擎改动；现在执行 `publish_workspace.sh` 会把未协调改动一并带入生产，故本轮只提交本功能文件，待并行改动收敛后统一发布。
- **下一步**：并行引擎改动提交/发布后统一发布，并在生产真实登录页复验总览；如需要跨任务批量导出，另立后端接口。

## 当前断点（2026-10-18，模型供应商切换 + 外部模型复查核验）

- **供应商切换（按用户指示，先不切回）**：原 `OpenCodeGo` 周限额耗尽（429 `GoUsageLimitError`，retry-after ≈19.5h，见 FL-D111）。已改为 **DeepSeek 直连**：
  - `/etc/fundlex-recall.env`（备份 `/etc/fundlex-recall.env.bak-20261018-132608`）：`LLM_PROVIDER=deepseek`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`；API key 只在 env 文件，不写仓库/文档/聊天记录。
  - 请求选项保持 `{"thinking":{"type":"disabled"}}`（实测该端点接受且 `reasoning_tokens=0`）；`FUNDLEX_MODEL_MAX_REQUESTS` 20000→40000，`FUNDLEX_MODEL_MAX_COST_USD=50` 不变；单价按目录价输入 $0.15/M、输出 $0.60/M。
  - 2026-10-18 13:26 CST 重启 `fundlex-recall-api` / `fundlex-recall-worker`；`/api/capabilities` 200；独立账本探测（`/tmp/opencode/upstream_probe2.py`）`UPSTREAM OK: {"ok": true}`。
  - 账本（切换前）：`17462` requests / charged **$14.4908**（上限 40000 / $50）。**用户明确指示前不切回原供应商。**
- **外部模型复查核验（已完成，未改引擎）**：对另一模型对核心链路的分析逐条对照当前代码与真实批次，新增 4 条记录（FL-D112～FL-D115）：
  - **FL-D112（新，最高价值）**：recall 生成内容复核闭包返回 bool 且 `validate_edit_plan` **忽略返回值** → 所有 `_component_ok` 复核（composite/fragment/variant）实际未生效；同时 `_composite_part_slice` 用 `display_text` 解释 compact 偏移，一旦校验生效会误拒带空白锚点的 composite。两处需一起修，属交付校验语义变更，待裁定。
  - **FL-D113（新）**：sweep 的按窗口规则范围在“该窗口 section 无任何规则映射”时为空 → 整窗 findings 被丢弃；round11 实测 14/80 个窗口零规则（D02/D12/D16 等每案 1–2 个盲窗）；约 69% section 字符所在 section 未被规则映射（含部分摘要）。待裁定 + A/B。
  - **FL-D114（新）**：未核验 Facts 仍参与 `excluded_by_fund_type`（整份结束）与 `condition_matches` 分支；round11/12/13 有 3/4/6 个案例含未核验引文，多为省略号/跨段导致的验证假阴性，`FUND_TYPE_QUOTE_UNVERIFIED` 每轮 1 例但均为 `open_regular`（未排除）。待裁定。
  - **FL-D115（新）**：sweep finding 以“重扫未再报”判 `resolved`，无针对性产物证据；round11 resolved 18 / pending 15，round12 8 / 19，round13 8 / 16。待裁定。
  - **复查中被证伪/夸大的项**：`structure_index` 80 段上限在 514 份语料中**不可达**（groups 中位 26、p90 30、最大 34，0 份超 80）；`facts_context` 的 `break` 在 29500 字符预算下抽样 120 份 **0 份截断**；target identity/复合删除/无 ledger 默认 planned 三点**已在 FL-D110 记录待决**，非新问题。
- **本轮已实施（2026-10-18，commit `ebcd9de`，尚未发布）**：按 [`REVISION_PLAN_2026-10-18.md`](REVISION_PLAN_2026-10-18.md) 完成 FL-D112 / FL-D113 / FL-D114（引文核验部分）与 FL-D110 缺陷 2/3/4：
  - 内容校验真正接线（False → 拒绝；坏 edit 丢弃并记 `RECALL_EDIT_CONTENT_UNVERIFIED`，其余继续）；composite 坐标改用 `compact_offsets` 并按整段校验，follower 不再走旁路；fragment 记录并重放 `fragments` 轨迹；variant/span-delete/composite_replace 证据与生产者对齐；`content_check_factory` 查找键加入 span。
  - target 身份改为全文 span hash；复合删除逐 part 校验；缺 ledger → `unresolved/LEDGER_MISSING`。
  - sweep 新增 `blind_windows` 记录 + 空范围窗口回退 mandatory 规则。
  - `_verify_quote` 支持省略号分段与跨段边界（fund_type 排除策略未改）。
  - 测试：新增 9 项；全量 **680 passed / 6 skipped / 1 failed**（唯一失败为既有 references 缺失项）。
- **下一动作**：
  1. **`p6-dev-round14-03` 基线已完成**（DeepSeek 直连、旧引擎）：dev-only **218/236 = 0.9237**（kept 11 / not_executed 7），6 报 complete / 10 实际 complete / 1 false_complete；1019 calls / $0.7372。对照 round11 dev-only 225/236 = 0.9534（旧供应商）。**注意 FL-D116**：此前 218/347 = 0.6282 与 225/347 = 0.6484 是评分器把 111 个未运行留出目标计入分母导致的低估；`p6_score.py` 已改为默认只评本次批次实际运行的 case（`--group run`），并支持 `--group dev|holdout|all`。
  2. 修正版 `ebcd9de` 已于 2026-10-18 14:16 CST 发布（部署文件 sha 与仓库一致，服务 active）；**`p6-dev-round14-04` 已完成**：dev-only **220/236 = 0.9322**（kept 10 / not_executed 6），7 报 complete / 11 实际 complete / 1 false_complete；1008 calls / $0.7536。对照 14-03（同供应商、旧引擎）218/236 = 0.9237：**+2 目标，无回归**；`RECALL_EDIT_CONTENT_UNVERIFIED` 两轮均为 **0**（校验接线未造成拒绝），14-04 记录 **16 个 blind_windows**。
  3. 已修 FL-D117 的 delete 路径（satisfied replace 不再压制仍残留的 delete survey），单测通过；待发布后跑下一批验证。模型 target 的 operation 粒度覆盖仍待改造。
  3a. **2026-10-18 追加（commit `61e210c`，已发布）**：operation-aware 覆盖键 `(rule_id, operation_key, location)`（含模型 target 与 fuzzy delete）、D115 evidence-gated finding closure、unverified `fund_type` 不排除且禁止 complete、零规则 blind window 回退全规则；全量 `pytest tests -q` → 686 passed / 6 skipped / 1 failed（既有）。发布后跑 **round14-06** 对照 round14-04（220/236）。
  3b. **2026-10-18 更新**：round14-05（仅 FL-D117 精确补丁）dev-only **220/236 = 0.9322**（kept 10 / not_executed 6），reported complete 2 / actual 11 / false 1；1240 calls / $0.9053——目标率持平、complete 更保守、成本 +23%。`61e210c` 已发布（部署 sha 一致）。
  3c. **2026-10-19 更新（外部阻塞 + P0 修复）**：DeepSeek 直连账户 **HTTP 402 `Insufficient Balance`**（直连复现）；round14-06 在 D02 触发 `BATCH_ABORTED MODEL_CIRCUIT_OPEN`，**批次作废、不得评分**。旧供应商 OpenCodeGo 周额度**已恢复**（带 session 头探测 200）；按用户“等指示再切回”的约定**未自行切回**，等待“充值 DeepSeek / 允许切回 OpenCodeGo”的决定。外部复查指出的 4 处漏接已修（commit `9ae799a`）：`_collect_targets` 只做精确去重、unknown operation fail-open、`_delivery_complete(unresolved)` 纳入 `coverage_gaps`、D115 三边界（`location_gone`、`wrong_text` required、`unaddressed_requirement`）；全量 **689 passed / 6 skipped / 1 failed**（既有）。**尚未发布**；供应商恢复后发布并跑 round14-07 对照 14-04/14-05。
  3d. **2026-10-19 09:16 CST 已切回 OpenCode Go**（新 key 仅在 `/etc/fundlex-recall.env`，未入库/文档；env 备份 `…bak-20261019-091621`）；`9ae799a` 已发布（部署 sha 一致）、capabilities 200、独立账本探测 `UPSTREAM OK`；**round14-07 运行中**。
  3e. **2026-10-19 更新**：round14-07 在 D01 触发 `PROCESSING_FAILED`（`AttributeError`，`_survey_targets_from_hits` 对 unknown 覆盖 update None）——**批次作废**；已修并发布 `03fbbfa`（改用 `_add_operation_coverage` + 回归测试），全量 **690 passed / 6 skipped / 1 failed**（既有）；**round14-08 运行中**。
  3f. **2026-10-19 更新**：round14-08（FL-D118 缺陷 1–5，同供应商）dev-only **211/236 = 0.8941**（kept 20 / not_executed 5），`RECALL_EDIT_OVERLAP` **66**（round11 为 8）、plan conflicts 38、G17 完成 2/11、reported complete 1/actual 4/false 1；1305 calls / $0.9074 —— 判定收集层去重过宽（缺陷 6）。已修并发布 `d6cc8ce`（operation-aware + unknown fail-closed），全量 690 passed；**round14-09 运行中**。
  3g. **2026-10-19 更新**：round14-09（`d6cc8ce`）dev-only **221/236 = 0.9364**（kept 11 / not_executed 4），overlaps 回到 **8**、conflicts 5、findings 11 resolved（evidence=required_text_present）/16 pending/1 unresolved；891 calls / $0.7435。剩余差距集中在 D01/D19 的 G01/G03 append（被 `absent` inventory 目标经 unknown fail-closed 丢弃）——已修并发布 `46afe2f`（wildcard synthetic 仅在 needs_edit/satisfied 位置被抑制），全量 691 passed；**round14-10 运行中**。
  3h. **2026-10-19 用户指示停止批次**：`p6-dev-round14-10` 在 D11 后被终止（runner 已 kill；最多一个在途 case 会由 worker 收尾）。**该批次作废、不得评分**；当前无运行中的评测批次，等待后续指示。
  4. 对照重点：`RECALL_EDIT_CONTENT_UNVERIFIED` 数量、`blind_windows`/`SWEEP_RULE_OUT_OF_WINDOW`、working/incomplete 比例、kept 变化；供应商切换与修正合并，作为混杂因素注明。
  5. 结果稳定后再冻结版本 → 留出 H01–H08 → 评测报告 → 打包。
- **预算/账本**：真实运行前在批次说明预登记；账本 `/var/lib/fundlex/model_budget.sqlite`（切换前 requests=17462，charged=$14.4908；上限 40000 / $50）。
- **约束**：FL-D105 Q1–Q8、FL-D104 1–19 未裁定前不改规则适用性/评分语义；合同可入库/出境（公开资料），凭据不入库/不入文档。
- **2026-10-19 追加（文档侧，均未改引擎）**：产品负责人裁定 G08-1/G08-2 属"正常替换、按合同实际类别的收费性质实例化"（登记于 FL-D104 变更记录）；裁定 `compose` 两条硬约束（固定文本逐字、不新增数字）可推翻、改由"生成+独立复核"接管（登记于 FL-D106）；同日**八项业务裁定**并入生成方案（v3：G11-1 勘误、收费性质归类、G14 直接替换、G15 删除+疑似合同有误标记、同义等同、货币基金排除、class_count 按实际类别）并更新映射文档 `B_CLASS_PROCESSING_MAP_2026-10-19.md`；新增 **FL-D119**（G08 把"赎回费率"句误当"申购"参考命中：机制已离线复现）与 **FL-D120**（"确定性优先、模型补位"方案）及其实施计划 [`GENERATION_STRATEGY_PLAN_2026-10-19.md`](GENERATION_STRATEGY_PLAN_2026-10-19.md)（v4：八项裁定 + 二次工程评审已并入）。
- **2026-10-19 实施启动（v4 Phase 0–2 完成）**：按 [`GENERATION_STRATEGY_PLAN_2026-10-19.md`](GENERATION_STRATEGY_PLAN_2026-10-19.md)（v4，已批准/实施中）完成 **Phase 0–2**，进度与验收见 [`GENERATION_V4_PROGRESS.md`](GENERATION_V4_PROGRESS.md)：`53b6d0f` registry/router/coverage 只读视图/mix 工具（flag 默认 legacy）；`a6d7e60` V1/V2-A/V2-B 影子验证器 + **FL-D119 根因修复**（模糊命中加主题翻转守卫、satisfied 尾句通道收紧）+ G11 定位回归 + 离线回放工具（round14-09：155 段校验仅 1 FAIL，待复核；`D01/p227` fixture 被正确抓为硬失败）。全量 **722 passed / 6 skipped / 1 failed**（既有）。**下一动作：Phase 3（Facts 扩展 + 三态证据），随后 Phase 4 Tier1（G14/G09/G15/G17）。**
- **2026-10-19 继续实施（v4 Phase 3–8 代码完成 + 发布；批次被用户停止）**：按产品负责人指示连续实施：`f492701` Facts 三态；`24e39d6`/`9b0fdb0` Tier1（G14 收敛/重建、G15/G17 删除前置、G09 splice）；`287be26` Tier2（G08/G11 干净整句政策替换）；`1ecd93c` Tier3 V3 独立复核 + **Artifact Claim Replay 接线**（对已写入 DOCX 重放，失败阻塞 complete）；预登记与本地真实验证见 [`GENERATION_V4_PROGRESS.md`](GENERATION_V4_PROGRESS.md)（D01 claim replay 17/17 通过；D16 composed 归零）。全量 **750 passed / 6 skipped / 1 failed**（既有）。已 `publish_workspace.sh` 发布并在 `/etc/fundlex-recall.env` 增加 `FUNDLEX_GENERATION_STRATEGY=registry`（备份 `.bak-genv4`）后重启；**批次 `p6-dev-round14-11` 经用户指示停止、作废不得评分**（runner 与守候脚本已终止；D01 在飞任务自然结束后无运行批次）；env 开关**当前仍为 registry，未回滚**（回滚=还原 `.bak-genv4` 并重启）。
- **2026-10-19 外部复查 P0 批次实施（`66265f7` + `1dd68b4`，已发布）**：按第二份源材料复查实施：**P0-A** `condition_status` 三值 + `plan_target` 入口 fact gate/Router 决策记录；**P0-B（部分）** `class_label` 保合同原文称谓（修叠字）、`service_group` 严格定义、两费皆真→CONFLICT；**P0-C** G16 组件级 satisfied（不再因"每日计提"首句误判）、**G15 `business_notices`**（"原合同可能有误"，不影响交付）接线并去重；**P0-D** G08/G11 仅裁缺失服务组子句（registry）；**P1 部分** G06/G13/G17 关键词签名、G14 扩展句补项、coverage `operation_keys` + delivery gate 读投影、claim replay 已有；另修 V3 `recall_verify` 未在网关白名单（`MODEL_TASK_UNSUPPORTED`）。全量 **773 passed / 0 failed**（references 随语料入库后既有失败亦消失）。已发布；**`p6-dev-round14-12`（dev 20 例）运行中**，完成后自动评分与分析。残余：币种维度拆分、semantic site anchor、per-operation claim replay、CI、红色盲核。

## 当前断点（第 12 轮，2026-10-16，P6 开发集真实修改评测收敛到 0.8602）

- **本轮任务**：用户指示「做二和三」——(三) Langfuse 退化为**本地 JSONL trace 兜底**，(二) 用它帮助 P6 评测优化。
- **(三) 已完成**：`fundlex/trace_sink.py`（FL-D088）。纯标准库、无网络、`FUNDLEX_TRACE_JSONL` 未设即 no-op；一合同一 trace（确定 seed）、一次调用一 generation、一条评测 score；活动文档 id 走 thread-local，引擎深处模型调用自动归入正确 trace。接线于 `model.py:_trace_attempt` + `jobs.py:_document_trace`（与 Langfuse 并列，可同开）。生产落点 `/var/lib/fundlex/traces/model-calls.jsonl`（env 备份 `…env.bak-tracesink`）。真实 20 例验证：1085 行、单条 25KB 含合同原文、19/20 trace 匹配、0 错误。分析器 `tools/evaluation/p6_trace_report.py` 把 trace 与评分按 trace_id 关联，直接产出「按规则/按阶段」失败画像。单测 `tests/test_trace_sink.py`。
- **(二) 已完成 — 用 trace 定位并修掉 3 个真实缺陷**：
  - **FL-D089 评分器误判**（commit `64dab0c`）：`appendix_present()` 因份额类别枚举差异把**已正确追加**的政策句判 `not_executed`。改为折叠枚举 + 模糊兜底逐字符步进。0.7892 → 0.8161，无引擎改动。
  - **FL-D091 append 家族缺陷**（commits `fc08350`/`c6c00aa`/`8331233`/`b78c26e`）：三层叠加——①措辞变体致盘点判 `not_applicable`；②缺 class group 时 append 被整体判不适用；③hit 被既有 `absent`/未解析目标压制。新增 `append_applicability_targets()` 确定性兜底 + 收窄 class-substitution 门限 + `override_rules`。
  - **FL-D091 类别名渲染缺陷**（commit `d900fb2`）：终稿出现 `default类基金份额`、`A类份额类基金份额`。修正 `class_label()` 剥离份额变体并丢弃占位名。
  - **FL-D089 补充**（commit `48fe3ca`）：单类别合同只应追加适用分句，评分器不再索要不存在的 C 类分句。
- **当前指标（开发集 20 例 / 236 目标）**：**0.9322**（completed 220 / kept 15 / `not_executed` **1**），目标 0.95。唯一残留 `not_executed` 是 **D07/G16**——该合同 `基金费用与税收` 章节**确无销售服务费条款**，引擎判不适用属正确。整合完成 `actually_complete` 5→8，目标 0.9（`kept` 15 为主要来源）。
- **评分器又修两处误判（同源：把「引擎做对了」读成没做）**：
  - **FL-D097**（commit `c68434d`）：删除规则的引文**跨多句**时，`_superseded_survives()` 的末句片段属于**相邻的、引擎有意保留**的条款，命中它就把已完成的删除判 `kept`。改为仅当锚点落在引文末句才计末句片段。
  - **FL-D098**（commit `1b478b2`）：删除成功后**原段落在终稿消失**，`locate_paragraph()` 返回 `-1`，而 `delete` 分支要求定位成功，于是**正确删除被判 `kept`**。改为「条款在全文已不存在即达标」。
  - **FL-D099**（本轮）：`replace` 的「新义务是否出现」用 24 字前缀精确判定，一处措辞差异（多一个「基金」、或合同真实类别 `A类、D类`）即分叉；同时标签 `old_text` 恰是修正后句子的子串，于是**正确替换被判 `kept`**。新增 `_obligation_in_region()`（规范化＋`difflib` 滑窗，阈值 0.9）作第三顺位回退。
  - 三处合计：0.8602 → **0.9322**（`kept` 32 → 15，`not_executed` 恒为 1）。逐目标核对确认**仅预期目标翻转、无误放**，并以**引擎自身审计**为独立佐证（D12/G14 仍判 `kept`，引擎审计同判未执行）。
- **剩余 `kept` 15 = 真实引擎缺陷（非评分器问题）**：G17 删除 ×5、G18 替换 ×3、G08 ×2、G11 ×2、G05 ×2、G14 ×1（D12 `RECALL_EDIT_OVERLAP`）。引擎 ledger 显示多为 `not_applicable`（作用域判定与终稿残留矛盾）或 `planned` 但未落地。
- **预算**：round2–round7 累计约 **$3.7**（单批 ~$0.52–0.70）；协议预算 dev ≤2000 calls/≤$6。
- **运维教训（FL-D096）**：**批次运行期间禁止 `publish_workspace.sh`**。已在飞批次的任务 pin 了旧 `engine_build`，重发布后 worker 校验失败 → 整批 `ENGINE_SCHEMA_MISMATCH`。round7 首批已作废留证并重跑。
- **并行协作**：另一 agent 同期推进前端（FL-D092 缓存、FL-D093/094 A/B 遗留规则集下线、HTML 呈现 + 逐条审查）。共享文档编号曾两次冲突（我的条目被并入 FL-D091、FL-D096），**改共享文档前先看 mtime，只做追加**。
- **下一动作**：① 就「优化轮次已达 baseline+7，超协议 3 轮上限；应用账本 charged $9.06 / 协议 total $10」请产品负责人定夺是否继续；② 若继续，按 `append_applicability_targets` 成例为**删除类规则**加确定性适用性兜底（FL-D100①），并单独排查 G18「替换未落地」；③ 达标前**不得冻结、不得读留出 H01–H08**。
- **预算与轮次（须如实上报）**：`protocol.json` 明文 optimisation rounds ≤3、total ≤$10；实际 baseline+7 轮；账本 charged **$9.0593**。协议指定的 per-run 来源 `report.json`（model 段）在各 `p6-dev-*` 目录下**不存在**，per-run 花费当前不可核验（FL-D100②）。

## 当前断点（第 11 轮，2026-10-16，静态资源缓存失效修复，**已生产验证**）

- **本轮任务**：用户反馈「我这里看着还是没变」——区块顺序调整已发布但页面仍旧版。
- **根因（FL-D092）**：`index.html` 以**无版本号固定路径**引用 `/static/app.js`、`/static/app.css`，nginx 也不下发 `Cache-Control`，浏览器沿用旧缓存。HTTPS 实取字节 sha 与仓库/部署一致（`bc5ac9c7d044e90d`），证明**服务端早已是新代码**，问题在客户端缓存。
- **修复（commit `64b0302`）**：`fundlex/api.py`
  - `_asset_version("app.css","app.js")` 按资源内容 sha256 生成 16 位版本标识，**每次发布自动变化**。
  - 入口 `/` 改为读 `index.html` 文本并注入 `?v=<hash>`，下发 `Cache-Control: no-store, must-revalidate`。
  - 新增 HTTP 中间件：`/static/*` → `public, max-age=31536000, immutable`（URL 带哈希，安全长期缓存）；`/`、`/index.html` → `no-store`。
- **验证证据**：
  - `TestClient`：`/` 返回 `no-store` 且引用 `app.js?v=a751d9b7f43c2426`；`/static/app.js|app.css` 返回 `immutable`。
  - 生产（nginx/`127.0.0.1:8010`）：首页含 `?v=a751d9b7f43c2426` + `no-store`；带版本静态资源 `immutable`。
  - **真实浏览器（生产、真实登录）**：16 条修订、目录 24 条 + 24 链接、拒绝 1 + 接受 15 → 下载 `selected_final` 136235 字节、**残留修订 0**、**控制台错误 0**。
  - 回归 `611 passed / 6 skipped`（排除既有基线失败 `test_rules_catalogue.py`）。
  - 已 `bash tools/deploy/publish_workspace.sh` 发布，api/worker active。
- **易错点**：若再遇「页面没变」，按「响应头 → URL 版本号 → HTTPS 实取字节 sha」三步先判定是客户端还是服务端，勿直接改代码或重发。
- **下一动作**：无阻塞。用户如仍见旧版，请**硬刷新（Ctrl+Shift+R）**一次即可清掉历史缓存；此后发布自动带新版本号，不再需要手动清缓存。

## 当前断点（第 10 轮，2026-10-16，前端逐条审查修订 + HTML 呈现，**已完整端到端交付**）

- **本轮任务**：用户选定 **A 服务端 HTML 方案**，要求：用户在结果页看到合同的 Word 呈现、**逐条勾选接受/拒绝修订**（与 Word 一致，任意组合自由）、据此生成**独立最终版产物**、支持一键接受全部；并指出 A 页**目录丢失**，要求排查是否还有其他丢失；指定全链路改造 + 进度管控 + 版本管理 + **完整端到端交付**，中途不得停下。
- **目录丢失根因（FL-D087，已查明并修复）**：demo 转换器只遍历 `body` 顶层 `w:p`/`w:tbl`，**整份目录位于唯一 `w:sdt`（20806 字符）内被静默丢弃**。完整丢失清单：目录 sdt（24 超链接 + 23 PAGEREF + 24 bookmark + 24 个 TOC1 段）、75 个 fldChar / 29 个 instrText 域、超链接不输出 `<a href>`、`w:tab` 硬编码、`sectPr` 分页信息。原文档 1363 个 `w:p` vs A 页 1252 个 `doc-p`。
- **方案规格与进度台账**：`docs/HTML_PRESENTATION_PLAN.md`（P0–P6 全部 ✅）。
- **实施（5 个 commit，全部已 push 到本地分支，未 push 远程）**：
  - `da86401` P1 投影层 `fundlex/html_view.py`（新增，只读）：通用块级遍历（含 `w:sdt`/表格）、`w:hyperlink`→真实 `<a href>`（经 rels 解析，协议白名单）、域代码隐藏仅留缓存结果、`w:bookmarkStart`→锚点、`w:tab`/`w:br type=page`/`sectPr` 投影；修订锚点直接取 OOXML `w:id`（**零文本匹配**）。
  - `40c53da` P2 选择性写入 `fundlex/selective.py`（新增）：`accept` 提升 `w:ins` 并删除 `w:del`；`reject` 删除 `w:ins` 并把 `w:delText` 还原为 `w:t`；未托管修订 id 只报告不改写；产物独立重开校验无残留。
  - `b9ff52a` P3 新 kind `selected_final` + 端点 `GET /revisions`、`POST /decisions`、`POST /accept-all`；`store.save_selected_artifact`（用户产物存 `selected/`，与 worker 产物隔离；`finish()` 白名单**故意不含** `selected_final`）。
  - `e9e51ac` P4 前端审查面板（单滚动容器 + 点清单 `scrollIntoView` 定位，**不做双栏同步滚动**——已实测两侧高度差 22% 无解）。
  - `b938a21` P6 文档与问题登记。
- **验证证据（全部真实、可复现）**：
  - 单元/集成：新增 19 项测试（`tests/test_selective.py`、`tests/test_revision_api.py`）；全套 **596 passed**（唯一失败 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation` 经 `git stash` 对照确认为**既有基线失败**，与本次无关）。
  - P2 关键正确性：全部接受输出与引擎自身 `working_final` **逐段一致**（1363/1363，0 差异）；全部拒绝恢复每一条 `expected_old_text`；单条拒绝只影响其所在段落（p1191）；纯删除型拒绝恢复被删文本。
  - **真实云端端到端（默认工作台入口，非遗留 `/api/batches`，未改任何发布标志）**：`POST /api/auth/login` → `POST /api/tasks`（`engine_id=recall_first`）→ `/uploads` → `/seal` → 真实 Worker + 真实模型 → `/revisions` → `/decisions` → 下载 `selected_final`。输入为干净原件 D01（sha256 `2f2f7a36…`，0 条既有修订）。结果：17 条修订全部映射、`has_toc True`、14 页；拒绝第 1 条 + 接受其余 → 下载文件 **0 条残留修订**、被拒条目还原原文、被接受条目保留替换文本、**目录 sdt 完整保留**、1338 个顶层段落结构未变；一键接受全部成功；引擎原有产物仍可下载未被替换。**incomplete 交付情形同样通过**（16 条修订 / `working_*` 产物）。
  - **真实浏览器（生产端点 127.0.0.1:8010，真实密码登录）**：17/16 条修订、目录 24 条 + 24 链接、勾选联动、点清单精确定位、生成与下载成功、**0 控制台错误**。脚本 `/tmp/opencode/browser_prod.py`。
- **验证中修复的真实缺陷（FL-D088）**：① 存储产物保留原始上传名无 `.docx` 后缀，`_read_parts` 以上传防护拒读 → `/revisions`、`/decisions` 对真实任务一律 422（真实路径才会暴露）；已改为经临时 `.docx` 副本读取，包限制不减。② 前端 `pathDoc` 用 `doc.id`，实际字段是 `document_id` → 请求 `/documents/undefined/revisions` 404；已修正。
- **易错点（接续必读）**：
  - 端到端验证**必须**用默认入口 `POST /api/tasks` + `engine_id=recall_first`（FL-D089）。遗留 `/api/batches` 建的批次 `engine_id` 为空 → 走遗留 ruleset-only 路径 → 报告 `guide groups 0 / targets 0`，**会误判成"引擎找不到条款"**。
  - 任务 `id` 与上传回执的 `batch_id` **不是同一个值**；文档/报告/产物端点用 `batch_id`。
  - ruleset v1 处于 `unreleased`（`auto_write_enabled: false`）只关门 ruleset 路径；recall-first 引擎走绑定指引快照，**不受该门限制**，实测正常交付（FL-D090）。不得为"制造交付"手改发布标志。
  - 引擎在真实模型下**非确定**：同一份合同不同批次可能得 17 条（complete）或 16/17 条（incomplete，如 `RECALL_EDIT_OVERLAP`）。incomplete 时产物是 `working_final`/`working_redline`，`final`/`redline` 会 404，属**正确行为**。
- **部署状态**：`bash tools/deploy/publish_workspace.sh` 已执行；`/opt/fundlex-recall-first` 与仓库**逐文件 sha256 一致**（html_view/selective/api/store/app.js/app.css 全部 SAME）；`fundlex-recall-api`/`fundlex-recall-worker` 均 active，`/api/capabilities` 200。
- **下一动作**：功能已按用户要求完整端到端交付，无待办阻塞。可选后续：① 若要求修订审查的**确定性交付**，需先解决引擎 `RECALL_EDIT_OVERLAP`（属引擎既有议题，非本功能）；② 合并到主分支/推送远程需用户明确要求（本轮**未 push**）。

## 当前断点（第 9 轮，2026-10-15，前端合并「处理进度/合同结果」）

- **本轮任务**：用户提出前端「处理进度」与「合同结果」两页几乎一样，要求合并。用户**明确选定**方案：**一张表 + 全部列常显**（明确否决"视图切换"方案）。
- **合并依据（代码证据）**：两页消费**同一接口** `GET /api/tasks/{id}/documents`（`fundlex/api.py:720`），共用 `loadDocuments()`、任务选择器循环、`showDetail`、分页；差异仅列/筛选/页头按钮。→ 同一实体，非两个功能。
- **已实施**（仅 3 个前端文件，**无后端/数据库/引擎改动**，单 commit 可 revert）：
  - `frontend/index.html`：`#view-progress` + `#view-results` → 单个 `#view-task`；侧边栏两项 → 一项「任务详情」(`data-nav="task"`)，总览页英雄区两按钮 → 一个；固定 7 列表头常显（合同文件/上传状态/资格/交付完整性/处理状态/业务提示/操作）；工具栏 7 个筛选控件（`doc-search`/`doc-upload-filter`/`doc-qualification-filter`/`doc-completeness-filter`/`doc-status-filter`/`doc-reason-filter`/`doc-sort`）；两组统计 `#overall-counts`+`#result-counts` 常显；页头运行态+交付态按钮并列。顺带删掉无人引用的死标记 `release-notice`。
  - `frontend/app.js`：`state` 的 `progressPage/resultPage/progressSize/resultSize/progressDocs/resultDocs` → 单一 `docPage/docSize/taskDocs`；`VIEW_TITLES`/`go()` 支持 `task`；`renderTask`/`deliveryCounts`/`updateDeliveryNote`/`selectTask`/`loadDocuments`/`refresh`/`seal`/`exportResults`/`resetWorkspace`/`data-detail`/分页/`changed`/事件绑定全部改到 `doc-*`；`renderTask` 里失效的 `selected-task-ruleset` 已移除。
  - `frontend/app.css`：`#result-scope-note`→`#doc-scope-note`、`#result-rows`→`#doc-rows`（行置灰规则随合并变为常显）。
- **关键坑（勿再错改）**：分页名**必须**用 `name='doc'`。`pagination()` 按 `name` 推导 `state[`${name}Page`]`，而 `taskPage/taskSize` 已被**任务列表**占用，若沿用会把两处分页串在一起。`data-detail` 统一 `doc:i` 并统一读 `state.taskDocs`。
- **顺带修复**：原 `emptyRow(cols)` 列数与真实表头不符（progress 传 5 / results 传 7 / reset 传 6、5）→ 统一 7，空态 `colspan=7`，列错位消除。
- **真实浏览器验证（已做，非静态检查）**：装了 Playwright + Chromium（`dnf install atk gtk3 …` 补系统库）驱动**真实页面 + 真实 API**。脚本 `/tmp/opencode/browser_accept.py`、`/tmp/opencode/browser_accept2.py`。结果：**0 页面/控制台报错**；`#view-task` 唯一，旧两页已无；导航只剩一个「任务详情」；表头 7 列全部可见；数据行 7 单元格；`data-detail="doc:0"`；空态 `colspan=7`；筛选真实下发（`upload_status=pending`）；分页 `data-page='doc'`；`#overall-counts`/`#result-counts` 正常填充；刷新后一致。另：`app.js` 过 modern JS 引擎语法校验；HTML 结构闭合 0 错；118 个 JS 引用 id 全部存在。
- **测试**：572 passed / 6 skipped / 1 failed；该 1 失败经 `git stash` 对照确认是**既有环境问题**（缺 `references/source/…文案勘误版.docx`），**与本改动无关**。
- **已登记**：`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` **FL-D086**（两页重复 + `emptyRow` 列数缺陷，含验证证据）。
- **已发布到线上（已完成）**：`bash tools/deploy/publish_workspace.sh` → `api/worker` 均 active，`/api/capabilities` 200。公网 `https://fundlex.club` 已复核（真实 Chromium）：`#view-task` 唯一、旧两页不存在、导航只剩一个「任务详情」、0 报错。脚本 `/tmp/opencode/live_check.py`。
- **git**：commit `3f4d8cf`（前端合并）已推送 origin（`341be2b..3f4d8cf`）。注：FL-D086 文档条目被并行 agent 的 `341be2b` 一并提交，内容完整。
- **下一步**：① 前端合并已完成并上线，如需可让用户在线上点一遍确认交互手感；② 回到第 8 轮主线：修 **FL-D060**（无条件 append 漏加 G01/G03/G16）→ 开发集再跑 1—2 轮 → 冻结 → 留出 8 例 → `docs/REAL_REVISION_EVALUATION_RESULTS.md`。

## 当前断点（第 8 轮，2026-10-15，接续请从此处读）

- **本轮已完成的非批次工作（第 8 轮）**：① 修正集中问题记录的 5 组**编号冲突**（FL-D077），并同步修正 `tools/evaluation/p6_score.py` 与断点/计划文档的引用（后出现的重复项改为 FL-D072/073/074/075/076，保留首次出现编号之一义）；② **新增交付包工具 `tools/evaluation/p6_package.py`**（把 P6 运行目录打成业务读者可读的「结果总览.md + 最终版（接受修订后）/ + 逐份修改说明/<合同>/{修改说明.md,修改明细.json,（修改痕迹版）.docx}」，结构对齐参考包 `FundLex-合同修改结果-本次抽查-20261013`），已用它生成 **`var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/`**（20 份合同，81 文件）；③ 复核交付包时发现并修复**真实缺陷 FL-D079**（变体模糊匹配 span 停在句中，留下“…（如有）。配。”碎片）→ 新增 `fuzzy_span_clause()` 句边界吸附，`variant_replace/variant_delete/审计复核`三处统一；④ 新增测试 `tests/test_p6_package.py`（3 项）与 `test_fuzzy_span_clause_snaps_to_sentence_boundary`；⑤ 全量测试 **566 passed / 1 expected（references/）/ 6 skipped**。
- **P6 第 1 轮（第 3 次重跑）已完成**：`p6-dev-round1-01` 20/20、604 调用、$0.5533；评分 `.venv/bin/python -X utf8 -m tools.evaluation.p6_score --run var/recall-first-evaluation/p6-dev-round1-01 --output /tmp/opencode/p6-round1-final.json` → 全量 347 目标/184 完成/0.5303；**开发集口径 236 目标/184 完成/0.7797**（基线 0.754、第 2 次 0.792）；integrated_complete 0/20；applicability_conflicts 19。产物 `var/recall-first-evaluation/p6-dev-round1-01/`。
- **P6 关键文件（仓库外）**：`/home/opencode/data/funds_word/`、`/home/opencode/data/MANIFEST.sha256`；仓库内 `var/recall-first-evaluation/p6/`（selection/labels/protocol/freeze）。
- **账本（仓库外，勿入库）**：应用调用记 `/var/lib/fundlex/model_budget.sqlite`（root 只读，opencode 读不到；数字取自各 `report.json` 的 `model` 段）。基线 581 调用/$0.5624；第 2 次 677/$0.5738。**agent 自用 0 次**。
- **禁止**：把**密钥/凭据**入库。发布只能用 `bash tools/deploy/publish_workspace.sh`。（**更新**：用户已授权自行判断 git 提交/推送；**推送统一用 `bash tools/deploy/push_with_token.sh`**，token 存仓库外 `/home/opencode/.github_token`（600），不打印/不入库。**合同资料政策更新（用户 2026-10-15）**：合同为公开资料，**可入库、可出服务器**（含 Langfuse Cloud）；「不入库/不出服务器」的旧底线**仅对凭据仍然有效**。）
- **本轮已推送**：`e37aa21`（交付包工具 + FL-D079）、`99509fb`（push 助手）、`dcc715e`（FL-D080）；远端 `origin/codex/fundlex-recall-first` 与本地一致（HEAD `dcc715e`）。
- **交付包已含根目录 `结果清单.csv`（FL-D081，用户要求）**：`tools/evaluation/p6_package.py` 复刻工作台「导出结果清单」的格式（BOM+CRLF、列 `序号,文件名,资格,处理状态,交付完整性,业务提示,原始原因码`、末列仅短机器码）；`结果总览.md` 保持不变。重出包：`var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/`（根目录 3 项 + 最终版 20 份 + 逐份说明 20 组）。
- **Langfuse 可观测性（FL-D081，已推送 `f5be16f`）**：接入 **Langfuse Cloud**（本机无 Docker/无 Postgres+ClickHouse+Redis+MinIO，自托管不可行）。代码：`fundlex/observability.py`（唯一收口，**无 key 纯 no-op**）、`fundlex/model.py` 的 `_trace_attempt`（每次调用一个 generation span）、`fundlex/jobs.py` 的 `_document_trace`（**一个合同一个 trace**，document_id 为确定性 seed）、`tools/evaluation/p6_langfuse_sync.py`（把 P6 verdict 作为 score 回写同一 trace）。开关：`FUNDLEX_LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST`（两个 key 都设才启用）+ `FUNDLEX_LANGFUSE_CAPTURE_TEXT`。已用本地 OTLP 桩验证真实发射（根 span 与 generation trace id 一致、带 usage/cost/version；score 带完整 metadata）；`tests/test_observability.py` 5 项通过；全量 **568 passed / 6 skipped**。详见 `docs/LANGFUSE_OBSERVABILITY.md`。**真实云端凭据已配置并验证**（FL-D083：`jp.cloud.langfuse.com`，`auth_check=True`，冒烟 trace `b1648f73…`）。
- **root 写权限（FL-D084，全部 agent 须知）**：用户已授予 `opencode` 本机 sudo `ALL`（`/etc/sudoers.d/fundlex-agent`）。`sudo -n` 可用；已用它备份并追加 `FUNDLEX_LANGFUSE_*` 到 `/etc/fundlex-recall.env`（备份 `…env.bak-langfuse`）。**边界**：仅 FundLex 部署/配置/服务/验证；凭据值不入库/文档/日志。**部署侧待办**：`/opt/fundlex-recall-first` 缺 `observability.py` 且 venv 未装 `langfuse` → 需 `sudo -n …/pip install langfuse` + `bash tools/deploy/publish_workspace.sh`（重启 api/worker）后生产 worker 才会发真实 trace。
- **合同资料政策更新（用户 2026-10-15）**：合同为公开资料，**可入库、可出服务器**；旧「不入库/不出服务器」约束**仅对凭据仍有效**（见 `AGENTS.md`）。
- **本地 JSONL trace 兜底（FL-D088，2026-10-16，已发布并验证）**：Langfuse 两区均丢 payload（FL-D085），用户指示退化到本地 JSONL。新增 `fundlex/trace_sink.py`（纯标准库；`FUNDLEX_TRACE_JSONL` 未设即 no-op；一个合同一 trace + 一次调用一 generation + 一条 score；活动文档 id 走 thread-local），接线于 `model.py`/`jobs.py`，配套分析器 `tools/evaluation/p6_trace_report.py`，单测 `tests/test_trace_sink.py`。生产落点 `/var/lib/fundlex/traces/model-calls.jsonl`（`/etc/fundlex-recall.env` 已加变量，备份 `.bak-tracesink`）。**真实 20 例已验证：1085 行、单条 25KB 含合同原文、19/20 trace 匹配、0 错误。**
- **评分器 append 误判已修（FL-D089，2026-10-16）**：`appendix_present()` 现折叠份额类别枚举（`A类、D类` ≡ `A类`）+ 模糊兜底逐字符步进。**开发集 0.7892 → 0.8161**（无引擎改动）。回归测试 `tests/test_p6_score_append.py`。
- **剩余主力缺陷（FL-D090，未修）**：开发集剩余 `not_executed` 11 例**全是 G01/G03/G16 append**（D07 真漏改——原件用「直销渠道」措辞致模型盘点判 `not_applicable`；D09/D13 属原件已含相近义务）。修法方向：`appendix` 规则增确定性适用性兜底 + 直销措辞归一化。
- **当前指标（2026-10-16，开发集 20 例 / 223 目标）**：**0.8161**，目标 0.95；整合完成 0/20，目标 0.9。`kept` 30 例（G17×8/G14×5/G11×4/G18×3/G15×3/G08×3/G13×2/G05×2）。
- **下一步（按序）**：① 修 FL-D090（append 适用性兜底）；② 开发集再跑 1 轮验证；③ 达标后冻结 → 跑留出 H01–H08；④ 出交付包 + `docs/REAL_REVISION_EVALUATION_RESULTS.md`；⑤ Langfuse 云端若报障有结论再回填 score 通道。
- **下一步（按序）**：①（可选）发布 FL-D079 修复后用 D01 等含 G22 变体的样本复跑，确认终稿无“……（如有）。配。”碎片；② 修 FL-D060（无条件 append 漏加 G01/G03/G16）后只在**开发集**再跑 1—2 轮（≤3 轮），直到 dev 达标（0.95 / 整合 0.9）并冻结；③ 冻结版跑 8 留出例（`--group holdout`）；④ 写 `docs/REAL_REVISION_EVALUATION_RESULTS.md`（用 `tools/evaluation/p6_package.py` 出交付包）；⑤ P7 浏览器端到端、断点续跑、双身份隔离、指引切换、MySQL 备份/恢复。

## 第 7 轮进度（服务器，2026-10-15）：用户 8 项 UX/修改问题 + P6 第 1 轮评分

任务计划文档：`docs/TASK_PLAN_UX_AND_APPEND_20261015.md`（该文档写于编号更正 FL-D077 之前，文中 FL-D068/069 指现在的前端互斥与 fragment 拼接两义，见本文顶部更正块）。

- **T2 引擎（问题 5，无标点拼接）已修复**：`_splice_fragment`（`fundlex/recall.py`，`fragment_replace` 路径）遗漏分隔符 → 已加 `append_separator`；`plan_composite_target` 同步加固。新增 2 回归测试。→ **FL-D068**
- **T1 后端并发核实（问题 1）**：后端本就支持多任务并行（`tasks.create` 无限制、`POST /api/tasks` 无守卫、worker 公平 claim）；互斥纯在**前端**。→ **FL-D069**
- **T3 前端 8 项 UX（问题 1–8）已实施**（`frontend/index.html|app.js|app.css`）：多任务并行、证据侧栏改「章节+改之前/改成了什么」、精简小字、结果页 ZIP 按钮置首、删顶部横幅+铃铛只收重要消息、总进度指标单行、导入 KPI 并入筛选栏。→ **FL-D071**。验证：`node --check` 通过、120 个 id 引用完整、`#2` 用真实报告核对 22 行可读无技术字段。**未做浏览器端点击验收。**
- **P6 第 1 轮评分（FL-D070）**：`p6-dev-round1-01` 20/20 完成，677 调用，$0.5738。**开发集 236 目标：基线 178（0.7542）→ 187（0.7924，+3.8pt）**；G15 +9、G05 +2、G17 −2；`applicability_conflicts` 29→13；**假完成仍 12**。评分产物 `/tmp/opencode/p6-round1-score.json`。**仍未达阈值（0.95/0.9）**。
- 测试：`.venv/bin/python -m pytest tests -q` → **561 passed / 1 expected（references/）/ 6 skipped**。
- **已提交并已推送（第 7 轮，11 个逻辑提交 `cc558ab..05fc90f`）**：工作树干净；`origin` 为私有仓库 `github.com/JokerNephew/FundLex`，分支 `codex/fundlex-recall-first`（新建 + upstream）。凭据为用户提供的 OAuth token（`gho_…`，经临时文件 + `GIT_ASKPASS` 使用，未入仓库/日志，用后即删；**用户应撤销该 token**）。仓库级代理 `http.proxy=http://127.0.0.1:9981`。详见 `docs/HANDOFF_ROUND7_UX_AND_GIT_20261015.md`。→ **FL-D078**（原 FL-D072，编号冲突后更正）。
- **未发布**：部署副本 `/opt/fundlex-recall-first` 仍为上一版。
- **预览服务（临时）**：`FUNDLEX_DATA_DIR=/tmp/opencode/fundlex-preview FUNDLEX_AUTH_MODE=dev .venv/bin/uvicorn fundlex.api:app --host 127.0.0.1 --port 8020`，供浏览器（经 SSH `-L 8020:127.0.0.1:8020` 转发）查看新代码；验证完应停掉。
- 下一动作：① 用户提供 GitHub 凭据后 `git push -u origin codex/fundlex-recall-first`（或新分支/PR）；② 浏览器端验收前端问题 1/2/4/6/7/8；③ 经确认后 `bash tools/deploy/publish_workspace.sh` 发布；④ 继续修 P6 开发集 `not_executed`（17，G01/G03/G16）+ `kept`（32，G17/G15/G14/G11/G08/G18）。

## 第 5 轮进度（服务器，2026-10-15）

- 基线复核：`uname` Linux x86_64；`.venv` Python 3.11.13；`/home/opencode/data/MANIFEST.sha256` 538/538 OK；`fundlex-recall-api`/`fundlex-recall-worker` active；`/api/capabilities` 200。
- 基线测试：`.venv/bin/python -m pytest tests -q` → **530 passed / 1 failed / 6 skipped**（唯一失败=`test_rules_catalogue`，references 未随迁移，预期）。
- 已修四类真实缺陷（**FL-D052**，见集中问题记录；代码在 `fundlex/recall.py`、`fundlex/recall_pipeline.py`）：
  1. survey 引文切片 compact→raw 偏移错误（`compact_offsets`；`survey_targets`/`plan_composite_target` 改用）；
  2. 跨段盘点目标未重绑定（`_rebind_unresolved_targets`，盘点后+每轮修复后执行，报告新增 `rebind` 段）；
  3. 同段多操作被首个命中短路（`plan_target` 累积 delete+replace，新增 `fragment_mixed`）；
  4. 查漏位置误报与“已满足”漏判（`_rule_mapped_locations`+`_sweep_batch(rule_locations=…)`→`SWEEP_LOCATION_OUT_OF_SCOPE`；`_rule_location_absent`→`SWEEP_LOCATION_NOT_RULE`；`satisfied_by_new_text` 同政策异语序等价；裸尾片段需上下文佐证 `bare_tail_keys`/`rule_context_anchors`）；并新增确定性审计确认 `_confirm_merged_append`（G03 p141、G16 p809 的 append+兄弟删除合并误判）。
- 新增单测 7 项；全量 **537 passed / 1 failed（预期）/ 6 skipped**。
- qr-local-12 12 项逐条结论：G05 p142=真实缺陷（已修）；G15 p806/p1262=跨段（已修）；G03 p141、G16 p809=审计误判（已加确定性确认）；G05 p760、G16 p227、G18 p139/p829/p1217、G22 p142=误报（已加过滤）；另修正 FL-D047 遗留判断：G05 真实目标只有 p142，p954/p1332 是“基金合同变更”条款非费用类别调整句。
- **已发布**：`tools/deploy/publish_workspace.sh` 成功（拷贝到 `/opt/fundlex-recall-first`、重启服务、capabilities 200）；部署代码已含全部 FL-D052 修复。
- **真实链路复验 quality-return-10**（应用链路：register→login→tasks→uploads→seal→轮询→下载；真实模型）：`task_status=completed`、`job_status=succeeded`、**64 调用 / $0.0461 / 230431 tokens / 358s / delivery=incomplete**；**targets 28 / completed 27 / unresolved 1**（对比 qr-local-12：30/14/12）；`rebind=[]`；`output_validation` 有 working_final/working_redline sha256。产物在 `var/cloud-runs/quality-return-10/`（report.json/working_final/working_redline/report_md）。
  - 已验证：G05 p142 同一目标同时 replace（调低销售服务费率）+ delete，`fragment_mixed` 生效；G03 p141 审计 completed；G16 p809 审计 completed（`_confirm_merged_append` 生效）；跨段 G15 p806/p1262 已解决；G18 p139/p829/p1217、G22 p142、G16 p227 误报消失（sweep dropped 记录 `SWEEP_LOCATION_OUT_OF_SCOPE`/`SWEEP_LOCATION_NOT_RULE`/`SWEEP_ALREADY_SATISFIED`）。
  - **残留 4 项未解决**（3 类原因）：① **G17 p808** `RECALL_COMPOSE_DELETE_NOT_SHRINKING`（审计 wrong）——规则 `old_text` 是 p808+p809 两句拼接，而 T018 目标只含 p808 一句，`_splice_fragment`/`variant_delete` 均无法匹配整段参考，落到 compose-delete 后被模型原样返回；② **G02 p106 sweep 误报**、③ **G04 p138 sweep 误报**——`class_substitution` 规则的 `new_text`（`A类、B类基金份额`）是指引示例，本产品只有 A/C 类，盘点已正确判 `satisfied`，但 sweep 模型把示例当真需求；④（第④项为 ①②③ 的审计/sweep 派生条目）。
- **第 5 轮第二轮修复（同属 FL-D052）**：
  1. `recall.class_substitution_noop`（新）：`class_substitution` 规则若各适用操作的实例化 `new_text` 与其 `old_text` 相等（产品实际类别已就是规则要的分组），则该规则无需修改；`recall_pipeline._rule_already_satisfied` 前置调用 → sweep finding 记 `SWEEP_ALREADY_SATISFIED`（修 ②③）。
  2. `recall.plan_target` 新增“删除整段目标”确定性分支：delete-only 规则、目标引文（compact）等于目标 span 且是规则 delete 参考文的子串时，整段 `replacement=""`（`variant_delete`），不再走 compose-delete（修 ①）。
  - 新增单测 3 项（core 2 + pipeline 1）；全量 **539 passed / 1 failed（预期）/ 6 skipped**。
- **未做**：quality-return-11 复验进行中、P6 评测。**本工作区未 commit、未 push**。
- 本轮模型调用：**0 次**（全部为离线单测与对既有 report.json 的离线核对）；应用账本 `/var/lib/fundlex/model_budget.sqlite` 的调用来自 quality-return-10/11 的应用任务，非 agent 自用（自用 0 次）。
- **第 5 轮第三轮修复（同属 FL-D052，已通过真实链路验证）**：quality-return-11 暴露两处新问题 →（a）G15 p806 因合同把支付条款拆成 p806+p807 两段、且指引措辞与合同不同，盘点把目标绑成单段 `…按月支付，`，删除无法覆盖续段 → 落 compose-delete 失败；（b）G16 p809 审计随之误判。修复：`_rebind_unresolved_targets` 新增 `extend_resolved`（仅跨段 composite 可替换已解析单段绑定）+ `_clause_continuation_binding`（整段覆盖 + 段末逗号 + 删除/替换规则 → 并入紧随一段）。新增单测 `test_rebind_extends_resolved_target_to_clause_continuation`。
- **quality-return-12 真实链路结果（已通过）**：`delivery_status=complete`、unresolved 0、targets 27/27、sweep_findings 0、**25 调用 / $0.0236 / 127s**；G15 重绑定 `p806:0:34+p807:0:88`。产物 `var/cloud-runs/quality-return-12/`；`final`/`redline` 哈希与报告一致（`862548a7…` / `2e586002…`），redline 含 16 `w:ins`+16 `w:del`；p806/p807/p808 删除、p809 保留+追加、p142 replace+delete 均在真实 DOCX 中核对通过。**FL-D052 全部收敛。**
- 全量测试：`.venv/bin/python -m pytest tests -q` → **540 passed / 1 failed（预期，references 未迁移）/ 6 skipped**。
- **待用户协助**：~~quality-return-10/11/12 的临时账号（`cloud-run-*`）与任务~~ **已于 2026-10-15 清理完毕（FL-D053 已解决）**：用户提供 3307 应用账号凭据，按 cloud_verify 顺序删除 3 账号及其任务/批次/文档/产物/会话；`admin` 与 `cloud-eval-*` 未动。
- **下一步**：P6 真实修改评测（28 份：20 开发 + 8 留出）。

## 第 6 轮（P6 真实修改评测，2026-10-15 续）

- **目标**：按 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` 执行 P6：28 份合同（20 开发 D01–D20 + 8 留出 H01–H08）走真实应用链路（`recall_first` 引擎、真实模型），对**实际 DOCX** 与**先冻结的独立标签**计分，据结果优化；留出集在冻结版之前只读一次。
- **样本选择**：`tools/evaluation/p6_select.py`（新）按分层确定式抽取（active/qdii/fof/likely_excluded/other 目标 16/3/4/3/2，stride 填充，dev/holdout 交错）；输出 `var/recall-first-evaluation/p6/selection.json`（`a7ed2519…`）。范围=514 份 `funds_word`，hash 引用 `/home/opencode/data/MANIFEST.sha256`。
- **独立标签**：`tools/evaluation/p6_label.py`（新，**盲于引擎输出**，只读指引 + 原件）。确定性推导事实（基金类别、份额类别与费用规则、浮动费）与逐规则义务；`old_text` 按合同实际措辞定位，删/替义务源句缺失记 `not_applicable`。规模：**347 目标 / 26 可改合同 / 2 排除**。修正过份额类别与费用事实推导（跨段、术语式定义、A/Y 按账户分类、否定式“不收取申购费/不从…中计提销售服务费”），旧/新 hash 均记录在 `freeze.json`（`label_corrections`）。
- **协议与冻结**：`protocol.json`（预算：dev ≤2000 调用 / ≤$6；holdout ≤900 / ≤$3；单任务 ≤$1；账本在仓库外）、`freeze.json`（三份 hash + 已知局限）。`labels.json` `230b5be4…`。
- **运行器/评分器**：`tools/evaluation/p6_run.py`（单账号、每合同一个 `POST /api/tasks`、下载 final/redline/report）、`tools/evaluation/p6_score.py`（重读实际 DOCX 计分；引擎判 `not_applicable/satisfied` 而标签仍要求改动的，单列 `applicability_conflicts`，不静默计为漏改）。
- **本轮修复的真实缺陷**（均记入集中问题文档）：
  - **FL-D054**：长合同 sweep 阶段 `MODEL_CONTEXT_LIMIT` 整单不产出 → `_sweep_chunk_chars` 扣减 `facts_text` 与固定开销。D01(1363 段) 复验不再触发。
  - **FL-D055**：审计把份额类别占位符展开误判为无依据新增 → `AUDIT_INSTRUCTION` 增补通用总则。
  - **FL-D056/FL-D058**：无销售服务费类别产品被误判 `RECALL_SLOT_UNRESOLVED` → `slot_group_missing`（服务组为空或费用同质）+ class_substitution 规则整体判不适用 + `Target.out_of_scope` 统一审计/未解决统计 + `unresolved_targets` 排除 `not_applicable`。D07 由 26 项降到 0，真实链路 `complete`。
  - **FL-D052 补充**：整段删除在合同措辞与指引不同、composer 报 `DELETE_NOT_SHRINKING` 时，整段 `replacement=""`（`whole_paragraph_delete`）。D01 真实链路 `complete`。
  - **FL-D072**（未完全解决）：sweep 偶发误报 G02/G04 分组替换未完成（残留旧标签句）。已加确定性过滤，偶发一次；规划侧正确。
- **测试**：`.venv/bin/python -m pytest tests -q` → **544 passed / 1 failed（预期，references 未迁移）/ 6 skipped**。新增单测 5 项（sweep 预算 2、服务费组不适用 1、整段删除 1、费用组反向 1）。
- **已发布**：`tools/deploy/publish_workspace.sh` 成功；部署 `fundlex/recall.py` `ef600a1e…` 与工作区一致（前次 `87407fe1…`/`2a0df932…`/`7136d6ad…` 为迭代中间态）。
- **基线批次已完成**：`p6-dev-baseline-01`（20 开发集，修复前部署 `ef600a1e…`，日志 `/tmp/opencode/p6-dev-baseline-01.log`）：**20/20 完成，581 调用，$0.5624**；报告内部 `delivery_complete=13`（D01/D04/D05/D08/D09/D10/D13/D14/D15/D16/D18/D19/D20），D02 `excluded`，D03/D06/D07/D11/D12/D17 `incomplete`。
- **基线评分（实际 DOCX vs 冻结标签）**：以**较正后**的 `/tmp/opencode/p6-baseline-full2.json`（`scored_at 08:26`）为准：**开发集口径（剔除未跑的 8 留出与 D02 excluded）236 标签目标 / completed 178 / 率 0.7542**；`kept 41`；**integrated-complete 0/18**；**13 份假完成**；**applicability_conflicts 29**。（较早的 `/tmp/opencode/p6-baseline-full.json` 给 168/0.712，已被 full2 取代。）全量口径 347 目标 / 178 / 0.513（含未跑的 8 留出）。**远低于阈值（目标 0.95 / 整合 0.9）**。
- **优化第 1 轮结果（`p6-dev-round1-01`，已完成并评分，见 FL-D070）**：20/20 完成，677 调用，**$0.5738**；**开发集 236 目标 / completed 187 / 率 0.7924（较基线 +9 目标，+3.8pt）**；规则层 **G15 +9（0/15→9/15）、G05 +2、G17 −2**；`kept 32`；`applicability_conflicts 13`；**假完成 12（actually_complete 1）**。评分产物 `/tmp/opencode/p6-round1-score.json`（sha256 `07fb0112…`）。**仍未达阈值**，不满足正式交付条件。
- **基线漏改归因**：`not_executed` 主要为 G01(5)+G03(5)+G16(3)（无条件 append 漏加，FL-D060）；`kept` 主要为 G15(7)+G17(4)（删除句变体漏删，FL-D059/FL-D062）。
- **本轮（发布前）修复并发布**：FL-D059（`_strip_class_lead` 短锚，G17 11/11）、FL-D052 整段删除兜底、FL-D062 通用结构化删除兜底（`_delete_keyword_bag`+`_keyword_bag_in_clause`，G15 28/28 精确 2 处、零误报）、FL-D054/D055/D056/D058。测试 **546 passed / 1 expected / 6 skipped**。
- **已发布**：`bash tools/deploy/publish_workspace.sh` → 部署 `fundlex/recall.py` `3bccf52788cb5bbc…` 与工作区一致；`fundlex-recall-api`/`worker` active，`/api/capabilities` 200。
- **进行中（第二轮=优化第 1 轮，第 3 次重跑）**：`p6-dev-round1-01`（20 开发集，最新构建 `fundlex/recall.py` `07b39288b87dfa14…`，日志 `/tmp/opencode/p6-dev-round1-01.log`，`--timeout 1800`）。前两次尝试见下。
- **第 2 次尝试结果（构建 `6340b6618745af32…`，已归档 `p6-dev-round1-01-prev`）**：20/20 完成，677 调用，$0.5738。评分（`/tmp/opencode/p6-round1b.json`）：开发集 **236 标签目标 / completed 187 / 率 0.792**（基线 0.712）；`applicability_conflicts` 38→13。**剩余主因**：G01/G03/G16 无条件 append 漏加（7/7/3）；G17 跨段删除次段残留（10）；G15 短锚误判（6，FL-D074 已修）。据此新增 FL-D074（评分器短锚误判）、FL-D075（G17 跨段删除）。
- **本轮新增修复（已发布，`07b39288b87dfa14…`）**：FL-D063（删除 span 延伸到引用所跨句数 + 句首回退避开公式行 + 词袋配对防误并 + `target_span_delete`）、FL-D064、FL-D062、FL-D065、FL-D067、FL-D074（评分器按引号内整条条款判删除）、FL-D075（G17 跨段删除合并）。全量 **562 passed / 1 expected / 6 skipped**。
- **本轮新增修复（已发布，`6340b6618745af32…`）**：FL-D063（删除 span 延伸到引用所跨句数 + 句首回退并避开公式行；G17 半删 / G15 空删修复）、FL-D064（survey 兜底补 `.with_parts()`）、FL-D062（G15 结构化删除兜底）、评测器 `appendix_present` 归一化（FL-D065 边界）、FL-D067（遗留 append 测试按当前 API 重写）。全量 **559 passed / 1 expected / 6 skipped**。
- **环境问题（FL-D066）**：中止批次遗留的模型账本 `reserved` 预留会阻塞后续任务（`MODEL_CONCURRENCY_LIMIT`，`concurrency=1`）；经重启 worker 缓解。**规程更新：不在任务在途中 kill 批次；中止后先重启服务。**
- **本轮新增修复（已发布）**：FL-D063（短锚点删除延伸到句末，修 G17 半删 / G15 空删）、FL-D064（survey 兜底命中补 `.with_parts()`，修 `IndexError`）、FL-D062（G15 通用结构化删除兜底）、评测器 `appendix_present` 归一化（FL-D065 边界：真漏加仍判 not_executed）。
- **环境问题（FL-D066）**：中止批次遗留的模型账本 `reserved` 预留会阻塞后续任务（`MODEL_CONCURRENCY_LIMIT`，`concurrency=1`）；经重启 worker 缓解。**规程更新：不在任务在途中 kill 批次。**
- **评分器**：`tools/evaluation/p6_score.py` 已实现并校准——按标签 `compact_start` 定位原段落，再按内容在最终文件中找回同一段落（段落索引会因增删而位移），在该**区域**内判断旧措辞是否消除/新义务是否到位。避免两类假信号：短锚点同时出现在无关条款；替换文本以旧措辞为前缀。
- **基线首轮已定位的漏改类别**（见集中问题文档）：
  - **FL-D059**：删规则合同措辞变体未进 survey → G15/G17 被判 not_applicable、应删条款保留（D01 两处×2）。**已实施修复**（`_strip_class_lead` 短锚点），独立验证命中。
  - **FL-D060**：无条件 append 规则在原文该条款缺失时被盘点判 not_applicable，导致漏加（D01 的 G01/G03）。**未解决**，待全量统计。
  - 评分器首轮还暴露出：D01 G05 在多处“费用调整”条款中只改了一处（标签冻结单点）、G18 替换未落实；D03 G08 引擎超规划到无源条款位置报 `RECALL_TARGET_UNRESOLVED`（非标签目标，属执行质量问题）。
- **本轮模型调用**：应用账本计 smoke-01..08 共 ≈ 600 调用 / ≈$0.5；开发集基线单独计费（见 `protocol.json` 预算）。**agent 自用 0 次**。
- **本工作区未 commit、未 push**。

## 0. 迁移决定与执行记录（2026-10-15，用户指令）

- **开发主副本迁移到云服务器**：`/home/opencode/fundlex`（专用用户 `opencode`，OpenCode v2.0.29 systemd 常驻，仅监听 127.0.0.1:49374）。
- 迁移内容：整个工作区（含 `.git`、`docs`、全部未提交改动）；排除 `var/`、`funds/`、`funds_word/`、`references/`、`.venv`、缓存与同步残留。
- **资料迁移（`/home/opencode/data`，与工作区分离）**：`funds_word/`（514 份合同）与 `references/`（24 份原件）已迁移，`chown -R opencode:opencode`、目录 750、文件 640；服务器生成 `MANIFEST.sha256`（每行 `sha256  相对路径  字节数`，注释行记录 538 文件 / 82361614 字节 / 生成时间 / 主机）；逐文件与本地比对 0 不一致（FL-D050）。**资料不进工作区、不进 git**；后续评测抽样引用该清单。`funds/`（历史 PDF）与 `.venv`、缓存不迁移。
- **执行记录（`tools/deploy/migrate_workspace.py` 等）**：
  - 打包 824 文件 / 283MB → 上传 → 解包覆盖 `/home/opencode/fundlex`（staging 校验 `layout-ok`）→ `chown -R opencode:opencode` → 保留可执行位；
  - 核对：远程文件数 824 = 本地包内文件数；11 个关键文件 sha256 全部一致（`fundlex/*.py`、`frontend/*`、`guides/builtin_guide_v1.json`、`docs/*.md`、`pyproject.toml` 等，见 `tools/deploy/migrate_verify.py`）；
  - git：远程 HEAD `3ed4e96146a04d3092de6c57138289bdffeca526`、分支 `codex/fundlex-recall-first`，与本机一致；工作区状态 55 项（本机 56 项，差一个未迁移的 `references/`）；
  - 服务器仓库设置 `core.autocrlf=input`、`core.quotepath=false`（修 CRLF 状态噪声与中文路径显示，FL-D049）；
  - 迁移后补传的文档/脚本哈希逐项一致（`tools/deploy/migrate_fixup.py` 复验）；
  - 服务器环境：`/usr/bin/python3.11 -m venv .venv` + `pip install -e '.[test]'`（pytest 9.1.1 / Python 3.11.13）；**基线测试 530 passed / 1 failed / 6 skipped**，唯一失败是 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`——该用例校验 `references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx` 的来源哈希，而 `references/` 按迁移约定不带去服务器（本机为标准 531 passed）。
  - 最终状态：源码文件 229（不含 `.git`/`.venv`/缓存）+ `.git` 对象 606 + `.venv` 4074；`git status` 55 项（11 个已跟踪修改 + 44 个未跟踪，与本机一致，仅缺未迁移的 `references/`）。
- 迁移后核对：74/74 关键文件哈希一致（`fundlex/*.py`、`frontend/*`、`guides/*.json`、`docs/*.md`、`tools/deploy/publish_workspace.sh`），远程 HEAD `3ed4e96…`。
- 迁移后：**服务器工作区是开发主副本；本机（笔记本）副本转为只读备份**。不要两边同时改同一份代码。
- 应用部署 `/opt/fundlex-recall-first` 不动；发布走 `/home/opencode/fundlex/tools/deploy/publish_workspace.sh`（内部调 root 的 `/usr/local/sbin/fundlex-publish`）。
- 不 push（未经用户要求）；不改应用部署，除非已按项目规定完成真实验证与问题登记。
- 模型账本：应用调用记 `/var/lib/fundlex/model_budget.sqlite`；常驻 agent 自身调用不记入该账本，用量单列跟踪。

## 目标与用户约束（摘要）

- 完成 FundLex 整个项目交付：前端、后端、召回优先修订引擎、指引配置、账号、持久任务、MySQL、云部署、真实用户端到端验收、20—30 份真实合同评测与优化闭环。
- 召回优先：模型负责业务判断/映射/盘点/联合修改/复核；代码负责结构地址/来源核对/执行/可靠性。不按关键词或旧文相等拒绝真实目标；已有命中仍查漏。
- 默认内置指引；自定义同结构 DOCX 指引仅在配置页上传/查看/启用/恢复默认；任务页只上传合同；任务绑定不可变指引版本。
- 每轮从原件重生成；复核发现问题自动补证/修复/仲裁，未解决才记未完成。
- 细节问题集中登记 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`；上下文 60% 前压缩或交接。
- 最终验收必须走真实用户端到端路径（工作台登录→上传真实合同→真实模型→DOCX 修改→复核→下载），见 AGENTS.md。

## 仓库状态（本机，迁移前）

- 分支：`codex/fundlex-recall-first`；HEAD：`3ed4e96`（仍未提交 commit；全部为工作区改动）。
- 已跟踪修改（5 个）：`IMPLEMENTATION_PLAN.md`、`README.md`、`docs/RECALL_FIRST_DESIGN.md`、`frontend/app.css|app.js|index.html`、`fundlex/api.py|jobs.py|model.py|store.py|tasks.py`。
- 未跟踪新增（节选，全部随迁移带上）：`AGENTS.md`、`fundlex/recall.py|recall_pipeline.py|recall_prompts.py|guide.py|guide_store.py`、`guides/builtin_guide_v1.json`、`tests/test_recall_*.py|test_guide*.py`、`tools/deploy/`、`tools/evaluation/recall_run.py|replay_checkpoints.py`、`docs/*.md`（含本文件、集中问题记录、实施计划、交接文档）。
- 明确不迁移：`var/`（产物与账本）、`funds_word/`（真实合同原件）、`references/`（指引原件）、`.venv/`、`__pycache__`、`.pytest_cache`。

## 已完成（有证据）

1. **内置指引**：22 组 / 34 操作，确定性校验干净，独立核验逐条处置（FL-D040）；哈希冻结。
2. **引擎核心 + 编排**：事实/映射/盘点/规划/写入/审计/修复/最终查漏/交付裁决；确定性优先；working_final/working_redline 门禁。
3. **第 4 轮新增确定性覆盖与跨段能力**（FL-D047）：`survey_targets` 在全部段落按规则参考旧文补扫（摘要第二处、变更章节残留）；`find_old_text_all` 边界/引导语约束；`plan_composite_target` 跨段删除/替换按段落精确执行；`satisfied_by_new_text` 已满足识别；`_absorb_sweep_findings` 重绑定（含跨段）；审计上下文覆盖 composite 段落；`recall_inventory_v2` / `recall_sweep_v2` 指令。
4. **FL-D048 修复**：条件不适用记 `not_applicable`（不再当未解决）；STOP_CODES 的 ModelError 直接暂停（`RecallPipelineStop`）；账本 reserve/finish 瞬时 readonly/locked 重试 3 次；`recall_run.py` 把 `--max-calls` 同时写入 `FUNDLEX_MODEL_MAX_REQUESTS`；`SOFT_STOP_CODES`（schema/quote/evidence 类）也按可恢复暂停处理。
5. **持久化/API/前端**：指引版本与配置、任务绑定快照、下载白名单、指引配置页、提交页只读显示当前指引。
6. **云端部署**（8.155.130.168）：`/opt/fundlex-recall-first`（8010，systemd `fundlex-recall-api`/`fundlex-recall-worker`，nginx 已切）；MySQL 127.0.0.1:3307/fundlex；公网 `http://8.155.130.168` 已实测 200。
7. **真实云端运行**：quality-return-01…09（产物在 `var/cloud-runs/`）；最新 09：69 调用 / $0.046 / 350s、delivery=incomplete、findings 8（其中 8 条经阅读为真实线索，FL-D047 已针对其治理）。
8. **全量测试**：`pytest tests -q` → **531 passed / 6 skipped**（MySQL 用例需 FUNDLEX_MYSQL_TEST_URL）。

## 本机真实运行证据（第 4 轮）

- `var/recall-runs/qr-local-01`：旧代码，48 calls / $0.029，`not_generated`；暴露 G07/G10 `RECALL_NO_APPLICABLE_OPERATION` 与账本 readonly 停止（催生 FL-D048）。
- `var/recall-runs/qr-local-11`：修复后，48 calls / $0.0284 / 198s，`not_generated`；survey 找到摘要 G22 p1357；sweep findings 0；仍有 G15 `RECALL_TARGET_UNRESOLVED`（跨段参考文与合同变体不匹配）与 G05 一处 `RECALL_COMPOSE_FIXED_TEXT_MISSING`。已针对这两类再改：非等价旧文先归一化再拆分（`_normalized_operation_text`）、`_operation_fingerprints` 逐级降级匹配、停止码细分。
- `var/recall-runs/qr-local-12`：上述再改后的运行完成（143 calls / $0.0748 / 512s，`incomplete`，targets 30 / edits 14 / rounds 5）。剩余未解决 12 项，下一条动作的输入：
  1. **G15 跨段目标未解析**（`RECALL_TARGET_UNRESOLVED`，p806；盘点引文与合同变体文不一致，sweep 本轮未报该规则，故 composite 重绑定没触发）→ 需要在“盘点/审计给出的目标本身引文未解析”时也走 `_operation_fingerprints` 降级匹配（不只是 sweep finding）；
  2. **G05 p760 假阳性**（survey 生成 `Y003`，plan 落 compose 后 `RECALL_COMPOSE_FIXED_TEXT_MISSING`，审计已判 wrong）→ 两处待查：① `_survey_targets_from_hits` 的引文切片疑似偏移一位（记录 quote 为“人并报中国证监会备”，实际应为“并报中国证监会备案”，导致 `_splice_fragment` 失配而走 compose）；② p760 是基金资产估值差错更正条款，与费用类别调整无关，需在 survey/规划入口按上下文过滤或交由审计裁决后不再进未解决。
  3. **审计未通过 4 项**：G03 p141（wrong）、G05 p142（incomplete）、G15 p806（incomplete）、G16 p809（wrong）→ 逐条读审计理由与产物片段核对（如属模型误判需按证据回驳，如属真实缺陷则修）；
  4. **sweep findings 5 条**：G16 p227、G18 p139/p829/p1217、G22 p142 —— G18 三条对应 FL-D047 里“已满足判定”的适用问题（p139 变体未被识别为已满足；p829/p1217 是摘要对应位置的追索），G22 p142 疑似位置错配（p142 是类别调整句，真实清算条款在 p978/p1357 已改），G16 p227 是摘要对应位置的追加缺失。
  以上均为“开发中真实缺陷”，不是评测或替身：修复后应在云端 quality-return-10 复验。

## 外部阻塞

- ~~**公网 HTTPS 未配置**（无域名）~~ **已于 2026-10-15 解决**：用户提供域名 `fundlex.club`，A 记录指向 `8.155.130.168`；已配 nginx + Let's Encrypt（acme.sh，自动续期），**`https://fundlex.club` 公网实测 200、证书有效、http 301 跳转 https**。详见集中问题记录 FL-D044。宝塔面板若重写站点 SSL 设置可能覆盖配置，旧版备份为 `fundlex.conf.pre-ssl-*`。
- **本机账本限制**（已登记 FL-D048）：本机 `var/` 目录被同工作区其他 agent 会话持续占用，SQLite 稳定 readonly；本机运行账本必须放项目目录之外（`%TEMP%` 或 `%LOCALAPPDATA%`）。迁移后本机仅作只读备份，此限制不再影响主开发。
- 评测额度：服务器账本 cap 20000 次 / $50（示例配置）。评测 28 份预计 $5—15，需用户确认额度或沿用服务器凭据。

## 模型账本与预算（预登记）

- 价格：input $0.15/M、output $0.60/M（OpenCodeGo deepseek-v4.1-flash）。
- 本轮（第 4 轮）已用：本机开发运行合计约 106 次调用 / ≈$0.06（qr-local-01 约 10 次、qr-local-11 48 次、qr-local-12 进行中；口径以各运行 report_json 的 `model` 段为准）。均在 P3—P5 预登记额度（≤1500 次 / ≤$8）内。
- 迁移后：开发验证默认走服务器应用链路，调用记 `/var/lib/fundlex/model_budget.sqlite`；常驻 agent 自身调用单列跟踪、不混入。
- 每次真实批量运行前写 `protocol.json`（样本/版本/预算/最坏调用上限），见实施计划 §5。

## 运行中的进程 / agent（迁移时）

- 本机：`qr-local-12` 开发运行（账本在 `%TEMP%\ledger-qr-local12.sqlite`）仍在执行；其产物在 `var/recall-runs/qr-local-12/`，不影响迁移（`var/` 不打包）。
- 本工作区另有其他 agent 会话在活动（`docs/RESIDENT_AGENT_SETUP.md` 等新文件非本轮所写）；迁移前已核对本文件与集中问题记录无冲突。
- 云端：`fundlex-recall-api`/`fundlex-recall-worker` 常驻（systemd）；`opencode.service` 常驻（127.0.0.1:49374）。

## 下一条可执行动作（服务器工作区，第 5 轮后）

1. ~~发布~~、~~quality-return-10/11/12 真实链路复验~~ 已完成；FL-D052 四类缺陷全部收敛，quality-return-12 `delivery_status=complete`、unresolved 0。
2. **P6 评测**：28 份（20 开发 + 8 留出），引用 `/home/opencode/data/MANIFEST.sha256` 冻结样本，写 `protocol.json`，独立标签冻结、评分读实际 DOCX；结果落 `docs/REAL_REVISION_EVALUATION_RESULTS.md`。预登记预算（≤相应调用/费用上限，ledger 放项目外）。
3. **FL-D053 清理**：请用户协助清理 quality-return-10/11/12 的临时账号与任务（无 DELETE 接口、DB 需 root 凭据）。
4. **P7**：浏览器端到端、服务重启续跑、双身份隔离、指引切换、MySQL 备份恢复演练。**正式入口 `https://fundlex.club` 已上线（FL-D044 已解决）**，P7 浏览器验收可直接走该 HTTPS 域名。

## 关键命令

- 服务器工作区测试：`cd /home/opencode/fundlex && .venv/bin/python -m pytest tests -q`（或只读用 `/opt/fundlex-recall-first/.venv/bin/python`）。
- 发布：`/home/opencode/fundlex/tools/deploy/publish_workspace.sh`。
- 云端真实运行：`python -X utf8 -m tools.deploy.cloud_task_run --contract "..." --output var/cloud-runs/<run> --timeout-min 30`。
- 资料目录（与工作区分离）：`/home/opencode/data/{funds_word,references}`；清单核对：
  `cd /home/opencode/data && awk '!/^###/ {print $1"  "$2}' MANIFEST.sha256 | sha256sum -c -`
- 本机（只读备份）真实运行：账本放 `%TEMP%`，命令见 `tools/evaluation/recall_run.py` 顶部说明；资料迁移脚本 `tools/deploy/migrate_data.py` / 工作区迁移脚本 `tools/deploy/migrate_workspace.py`。

## 本轮新增断点（2026-10-17，B 类全量排查 + 指引适配排查）

- **FL-D104**（已提交 `e780202`，未推送）：514 份全量 B 类（业务含义偏差）排查。报告 `/home/opencode/B_CLASS_REPORT_FINAL.md`，数据 `/tmp/opencode/b_gap_findings_clean.csv`（1638 行 / 509 份），分规则 CSV `/tmp/opencode/b_class_by_rule/*.csv`。**19 项口径待产品负责人裁决**，裁定前不得据以改动引擎/评分。
- **FL-D105**（已提交 `5fc3d70`，未推送）：合同语料 × 指引**结构性适配排查**（确定性、无模型）。报告 `/home/opencode/GUIDE_CORPUS_FIT_REPORT.md`，产物 `/tmp/opencode/{guide_fit_probe2,clause_material,verify_findings}.json`。核心：空格陷阱 386/514、真实类别超 A/C（E/F/Y/D/B/H）、删除型 old_text 大面积对不上（G15 1/514、G17 5/514）、已满足新机制 46/41 份、货币基金 8 份不兼容；**Q1–Q8 待裁决**。
- 两项均只登记"发现与待决"，未改动代码、未发布、未宣称达标。P6 开发集冻结/留出状态不受影响。

## FL-D106 代码改动断点（2026-10-17）

- **已发布并完成一轮真实批次验证**：发布哈希 `recall.py 1f898fe1…` / `recall_pipeline.py ccb2ff94…`，服务 13:59:47 重启；批次 `p6-dev-round9-01`（20/20 完成，$0.5561，无 abort）。
- **指标（同一评分器/标签集，347 目标）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；**round9 219/0.6311/kept9**。相对紧邻的 round8-03：completed **+8**、kept **−2**；相对 round7：kept **15→9**。明显改善：D04/D08/D17/D19 的 G17 删除型 kept→completed、D07 G16 not_executed→completed、D12 G14、D19 G08。
- **D09 崩溃为非本次引入**：82 次 sweep 中仅 1 次 `finish_reason=length`（输出 4000 上限截断）→ `MODEL_SCHEMA_INVALID`；sweep 工作量 84→79 反而下降。属既有输出截断脆弱点（FL-D107），待定处理。
- **未做**：未冻结版本、未跑留出 H01–H08、未写评测结果文档、未打包；未宣称达成 0.9。
- 详见集中问题记录 FL-D106、**FL-D107**。

## FL-D108 / FL-D109 断点（2026-10-17，sweep 输出截断 + 切窗与规则收敛）

- **当前生产状态（已发布并核对）**：`recall_pipeline.py db2ad9d1…` / `model.py 4d66f856…` 与仓库逐字节一致；服务于 **23:23:21** 重启，`/api/capabilities` 200。
- **FL-D108（已实施并生效）**：sweep 响应触到输出上限（`finish_reason=length`）时识别为 `MODEL_OUTPUT_TRUNCATED`，并**把该窗口按整段折半重扫**，而非重试同一超长请求；单段无法再拆则记诚实缺口。（根因实测：82 次 sweep 仅 1 次触顶，p50 输出仅 146 token，故不提高全局上限。）
- **FL-D109 第一步（已实施、已发布、已实测有效，为默认）**：sweep 规则**按窗口覆盖章节收敛**（含 mandatory 强制、不可达回退、空映射回退三道硬兜底），并对越界 finding 记 `SWEEP_RULE_OUT_OF_WINDOW`。round11：completed **225 / rate 0.6484**（round9 为 219 / 0.6311），`SWEEP_LOCATION_OUT_OF_SCOPE` **362→146**、`QUOTE_NOT_IN_WINDOW` 74→22；离线 requirements 文本量 **−87.7%**，每窗规则数 22 → mean 2.0–5.1。
- **FL-D109 第二步（已实施但默认关闭，opt-in）**：章节对齐切窗 + 未分配段落字符兜底，由 `FUNDLEX_SWEEP_SECTION_WINDOWS=1` 开启（当前未设置=关闭，部署已核对）。两次真实批次（round12 219 / round13 222）**无指标增益**且窗口数升至约 26（调用与成本上升），故不改默认。
- **指标台账（同评分器/同 347 标签）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；round9 219/0.6311/kept9；**round11 225/0.6484/kept11**；round12 219/0.6311/kept10；round13 222/0.6398/kept10。观测到显著运行间噪声（D09 跨轮 completed 7/7/0/7/4/4）。
- **全量测试**：`pytest tests` → **667 passed / 6 skipped / 1 failed**，唯一失败为既有无关项 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（缺 `references/source/*.docx`）。
- **未做**：未冻结版本、未跑留出 H01–H08、未写 `docs/REAL_REVISION_EVALUATION_RESULTS.md`、未打包；未宣称达成 0.9。
- 待推送提交：`157aba6`、`e88b64e`（代码）与 `ef76bce`、`e85e08c`（文档），以及更早的 `3946bdf`、`84402c3`、`bd82207`、`24f4d6b`、`b4039a1`、`a36e64f`、`767cbd0`、`5fc3d70`、`d5aae21`、`e780202`。

## FL-D110 / FL-D111 断点（2026-10-18，全链路复查 + 上游周限额阻塞）【当前断点】

- **本段为最新断点，接续请从此处开始。**
- **产品负责人指示**：先推送代码（已完成）。其后仍需：等上游限额重置后重跑 round14 验证 FL-D110；再收尾冻结/留出/打包。
- **FL-D110（已提交、已发布、单测通过；真实批次待补）**：增量重扫（sweep 第二轮）原来与初次重扫**口径不同**——用 `_artifact_chunks` 而非同一入口，且**未传** `requirements_by_chunk`/`scope_by_chunk`（即绕过 FL-D109 的按窗口规则收敛）。实测约 **1/3 的 case** 触发增量重扫（round11 7/20、round12 4/20、round13 4/20），D12 单案最多 3 轮。已新增唯一入口 `_sweep_chunks()` 并让增量重扫重新执行 `_window_rule_scope()`。另记录 3 项待决机制缺陷（`_target_identity` 60 字截断致旧审计结论可存活；复合删除证据只查锚点段；无 ledger 条目默认 `planned`）。
- **FL-D111（已提交、已发布、单测通过）**：`observability.trace_document()` 把被追踪主体的异常一并吞掉并再次 `yield`，导致 contextlib 抛 `RuntimeError("generator didn't stop after throw()")`——引擎的**可恢复停止**（`RecallPipelineStop`）被降级为普通 `RuntimeError`，worker 判不出停止 → `PROCESSING_FAILED`、`attempt=1`、**永久失败**，"暂停/续跑"设计完全失效。已重写为"只吞追踪自身错误、主体异常原样传播、span 关闭只记日志"。生产证据：worker 日志 `langfuse trace failed …` + `RecallPipelineStop: MODEL_CIRCUIT_OPEN`；DB 中 round14 全部 `attempt=1, PROCESSING_FAILED`。同时 `tools/evaluation/p6_run.py` 增加 `ENVIRONMENT_BLOCKED_CODES` 与"零调用零目标"兜底中止，避免再出现"`completed 20/20` 实际全空跑"的假批次。
- **外部阻塞（当前最重要）**：上游模型服务返回 **HTTP 429 `GoUsageLimitError`（weekly 限额）**，`retry-after: 70343s`（≈**19.5 小时**，自 2026-10-18 12:25 观测起算）。**在此之前无法运行任何真实模型批次**。可用独立账本探测命令模式：读 worker 的 `/proc/<pid>/environ` 构造 `ModelGateway.from_env()`，并把 `FUNDLEX_MODEL_LEDGER` 指向临时文件（勿污染生产 circuit）。
- **round14/14-02 作废**：`p6-dev-round14-01`（19/20 空跑）、`p6-dev-round14-02`（20/20 空跑）**不得用于评分**；空跑发生在 `facts` 阶段之前，与 FL-D110 无关。
- **已推送状态（2026-10-18 12:xx 核对）**：`origin/codex/fundlex-recall-first == HEAD`，ahead=0/behind=0；推送用 `bash tools/deploy/push_with_token.sh`（token 来自 `/home/opencode/.github_token`，不打印）。
- **全量测试**：`pytest tests` → **671 passed / 6 skipped / 1 failed**（唯一失败为既有无关项 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`，缺 `references/source/*.docx`）。
- **指标台账（同评分器/同 347 标签）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；round9 219/0.6311/kept9；**round11 225/0.6484/kept11（当前最好，FL-D109 第一步）**；round12 219/0.6311/kept10；round13 222/0.6398/kept10。round14/14-02 无效不计。
- **限额重置后的下一步（按序）**：(1) 直接重跑 `p6-dev-round14-03`（无需再发布，代码已发布）验证 FL-D110；(2) 与 round11/13 对比指标；(3) 若通过则继续冻结版本 → 跑留出 H01–H08 → 写 `docs/REAL_REVISION_EVALUATION_RESULTS.md` → `tools/evaluation/p6_package.py` 打包。
- **待决定/待决（未实施）**：FL-D110 记录的 3 项机制缺陷；FL-D105 Q1–Q8 与 FL-D104 1–19 仍待产品负责人裁定。
- **待推送提交**：无（已全部推送；此后新增提交需再次运行 `bash tools/deploy/push_with_token.sh`）。
- **安全提示**：2026-10-18 复查期间，读取服务环境时曾有一处命令未能完整脱敏，导致 `FUNDLEX_DATABASE_URL` 中的数据库口令出现在会话输出中。已停止再读该行；如需可评估轮换该口令。

## 当前断点（2026-10-21，Operation Execution Closure）

- **任务**：按用户方案完成 operation identity、final-plan ledger reconciliation、全 applicable obligation Claim Replay、G05 bounded splice、sweep/delete artifact proof、missing-operation recovery、dirty audit/并发/性能。
- **代码**：工作区已修改（未提交）：`fundlex/obligations.py`、`recall.py`、`targeting.py`、`recall_pipeline.py`、`generation/claim_replay.py`、`recovery/types.py`、`model.py`、`models/roles.py`；新增 `tests/test_operation_execution_closure.py`。
- **测试**：最近一次全量 `pytest tests -q` = 939 passed / 6 skipped；最后几处 target/duplicate/site 修复后需重跑。
- **真实子集（临时账本，均 incomplete）**：
  - D01f 37 targets / 18 edits / 133 calls / $0.0806；仅 G17 p760 残句。
  - D02b 35 / 17 / 109 / $0.0831；G16 missing + G17 p823 + G05 residual。
  - D11 29 / 16 / 104 / $0.0936；G05:2 + G16 + G22 audit。
  - D16 40 / 20 / 78 / $0.0476；p822/p1306 duplicate + G06 composite。
- **待完成**：D02c 后台结果；D01/D11/D16 用最后修复重跑；全量 pytest；5 类 Reviewer；文档/证据包；按逻辑 commit 提交推送。
- **明确未做**：未发布生产、未跑 514。

## 本轮实现断点（2026-10-21，未完成）

- 当前 HEAD 仍为 `00312e3bae7047c4ca04762d8f2739bd130894ed`，分支 `refactor/recovery-architecture`；未提交改动包含 Guide certification、Facts class-set、qualification review、site-scoped effects、frozen cassette/run/stage replay、Claim Replay 与 recovery 路由调整。
- 新增 `fundlex/fact_evidence.py`、`fundlex/qualification.py`、`fundlex/frozen.py`、`fundlex/stage_replay.py`、`tools/replay_stage.py`，并新增 `tests/test_recovery_final_invariants.py`。
- 内置 Guide runtime gate 实测通过：source SHA `b77be53c...`, guide SHA `45dd7746...`, 22 rules / 34 operations；未部署。
- 语法编译和 diff check 通过。旧全量测试在新硬不变量下为 883 passed / 59 failed / 6 skipped；失败混合旧测试预期（TRUE→NOT_APPLICABLE、隐式 ONE_OF、未认证 synthetic guide）和实际接线缺陷，不能作为最终验收。新增 invariant 测试尚未单独通过。
- 已修复：`CLAIM_PLANNED_EFFECT_MISSING` 路由至 generation；Audit evidence 按目标 site 验证；append fallback 要求 rule-specific site anchor；ModelGateway 支持 `FUNDLEX_MODEL_MODE=live|record|replay`；frozen run manifest 与 stage replay 均 fail closed。
- 待做：修复新增测试与事实解析边界；审查 all TRUE replay universe、delete residual site-first、scope correction、final sweep 次数与 no-progress hash；更新 Worker `GUIDE_NOT_CERTIFIED` 错误映射；运行针对性测试并记录结果；不进行 live E2E/部署。

## 当前断点（2026-10-28，外围前后端整改计划）

- 用户要求先停止改代码，先制定可多 agent 协作的分阶段计划。计划已保存：`docs/PERIPHERAL_REMEDIATION_PLAN_20261028.md`。
- 已锁定的产品决定：以当前工作区 `codex/semantic-engine-remediation-20261028` 为基线，完成后再合并/推送默认分支；`incomplete` 人工审查后允许生成选择版但仍按工作文件标注；指引重新解析采用“新建 V2、V1 不可变”的方案 A；不再提供只读诊断入口；不关闭注册、不加登录限流。
- 用户已批准继续，当前集成分支 `codex/outer-remediation-20261028`，已提交 P0-3 不可变指引、parse job release 预算、P0-1 工作文件标签、engine_build/service_build 拆分、部署双哈希、last-admin 保护、对象 GC、HTML 文案、CI 分支、前端轮询降频和 SQL 分页/N+1 移除。
- 最终验证：干净 worktree `/home/opencode/.local/share/opencode/worktree/29a9a9/outer-integration` 全量 pytest **1782 passed / 85 skipped**（`/tmp/opencode/outer-full-pytest-final2.log`）；V1 浏览器 **34 passed**，V2 浏览器 **10 passed**；前端 typecheck/lint/Vitest/build 通过。
- 未做：未发布生产、未跑真实模型 E2E。`engine_build()` 一次性变更要求发布前清空/暂停队列；分页仍有 `reason_options` 全量报告解析、error_code 回退 Python、legacy 分页和 MySQL 未实跑等保留项。
- 下一步：用户验收；发布前按计划完成迁移/队列/回滚演练并登记真实 E2E 预算，不能把自动化测试冒充真实合同交付验收。
