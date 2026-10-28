# 修订引擎语义误拒、范围漏改与证明闭环：多阶段执行方案

日期：2026-10-28。状态：**方案已保存，尚未执行本方案的工程整改/真实评测/生产交付**。

配套入口：[接续模型执行 Prompt](NEXT_AGENT_SEMANTIC_ENGINE_EXECUTION_PROMPT_20261028.md)；[执行进度表](SEMANTIC_ENGINE_REMEDIATION_PROGRESS_20261028.md)。

## 1. 本次任务的确切范围

用户要修复的是此前列出的五类引擎问题：语义硬门禁、固定标题/规则作用域、容量与静默截断、结构能力、交付/审计误拒及漏检，并包含后续已复现的事实依赖、执行器恢复、重试污染和自定义指引编号问题。**不是再写业务分类报告，也不是重建无关Compare/飞书功能。** 周边前后端、持久任务、配置和部署只做完成本次整改交付所必需的集成及回归。

用户已授权接续模型：组织多agent合作开发和测试；中途不反复询问；自行掌握进度、版本、整合与发布；完成真实端到端交付。本轮主agent只制订和保存方案，开发由后续模型执行。

### 1.1 不可改变的业务边界

1. 用户最新裁定：**“不在规则对应的范围之内就不要改”**。范围外不删、不润色、不补写、不为去重顺带处理，不再询问是否允许范围外去重。
2. 范围来自指引、适用条件和完整逻辑条款，不等于当前代码可能漏选的scope。范围内多叶子、正文重复条款及真实摘要对应目标不能漏掉；物理写入必须先获得对应规则授权。
3. G14三种旧表述已获指引授权；QDII重复“基金”属于绑定缺陷。G18是条件性替换，无对应旧义时不强制新增，不把无目标冒称已满足。D06完整费用差异→可分配收益差异句按语义判已满足。
4. G15旧例10日不是新要求；新机制是5日。旧支付安排变体按既有裁定处理，实质差异只作不阻交付的提示，不另行整改旧机制。不得把自动支付/无需指令当作无授权。
5. G11原件条款1包含承担句及免收费句，条款2仅含承担句；先判完整授权范围。范围内按规则处理，确属范围外的独立句即使重复也保留。
6. 实际正文/摘要对应目标分别盘点、保持语义一致；无实际摘要目标且指引无新增义务，不机械复制。QDII/FOF按事实逐规则判断，不以失败多为由整份降配或改分母。

### 1.2 阅读顺序、当前事实与优先级

- 阅读 `AGENTS.md` → `docs/ACTIVE_HANDOFF.md` 最新条目 → 本方案 → `docs/BUSINESS_ISSUES_FROM_TESTS.md` 最新裁定 → `docs/STRICTNESS_DESIGN_AUDIT_20261028.md` → 集中问题相关条目 → 完整交接与评测计划。
- 最新用户指示/项目规定优先；旧scope计划中的“只选一个叶子、摘要默认排除、只剩业务待定”等不得继续作设计依据。
- 当前工作/部署是同一台Linux云服务器；工作区 `/home/opencode/fundlex`，Python `.venv/bin/python`，应用目录 `/opt/fundlex-recall-first`。按AGENTS执行身份核验，不沿用旧Windows操作。
- 本方案保存时工作分支 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`；**大量已修改/未跟踪代码是真实依赖，不能从HEAD直接新建干净worktree就以为拿到了现有实现**。执行前重新核对，不假定仍是这个版本。
- 样本使用 `funds_word/基金合同第一批/`；现有记录为27/28可解析，保护合同“广发稳信”失败，须重新核实。固定D01–D20/holdout清单、哈希、旧gold、历史产物和分母不可篡改。
- 指引原件：`references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx`，SHA-256 `b77be53c3439d785a9ffad0f09d8d03ba74f7722397576b999ae6f5dd6eef895`。

## 2. 缺陷—整改—验收追踪表

“确认”指审计已复现局部行为，不自动等于每份真实任务都受影响；“待复核”须先复现再决定修改。真实段号仅是证据，不得进入运行时样本特判。

| ID / 来源 | 证据状态与问题 | 必须采取的处理 | 首要验收 |
|---|---|---|---|
| R01 / FL-D106、394 | 确认：弘利G17 p784正确scope＋精确quote＋合法操作仍被site词表拒 | target_site_ok/append_site_ok等词形检查改为快速路径或有依据的疑点，不作为最终语义裁判；进入统一批准链 | 同义合法目标通过；相同词出现在无关条款仍拒 |
| R02 / FL-D106、399 | 确认归属已有variants/fuzzy，非全精确；G14仍存在绑定失败 | `_selected_operation_indices`、`target_operation_keys`与执行共用语义批准身份；不得直接恢复claimed_operations就写 | G14重复“基金”、其他语义变体；错误operation/过期quote不能通过 |
| R03 / FL-D106 | 确认T3候选/quote检查比初次归属更严；原文复制仍anchor拒绝 | 确定性候选为快速路径，范围内模型提名/重取原文作为完整恢复路径 | 同一合法目标在初次/恢复入口判定一致；复制范围外文本不得写 |
| R04 / FL-D439 | 真实景宁p148/p155均为正文，first-leaf漏p155；历史complete假完整 | 多叶子scope、完整逻辑条款、独立scope覆盖审查；禁止各阶段共享漏选后自证完成 | 实际两处应改义务均完成；规则外段落不动；旧final复核应识别漏改 |
| R05 / FL-D434、443 | 固定标题、费用必须含税收、copy_key及摘要默认排除；D06摘要section_path错误 | 标题词典只作导航；模型有界选叶子/确认对应关系；修元数据与scope来源 | “基金费用”等改标题、D06 p1256/p1269费用标题及p1286后续目标正确识别 |
| R06 / FL-D439 | 确认同内容换G编号会改变scope策略 | 规则策略绑定guide身份/来源语义/版本，不按裸G号绑架自定义规则 | 同内容重编号语义一致；两个guide相同ID不串授权 |
| R07 / FL-D120 | 确认registry确定性executor失败后无语义补救出口 | 有界升级为模型重判范围/生成或重规划；删除仍优先代码按批准span执行 | G09同义句、G13“持有不足7日”；错误/无授权改写不被升级放行 |
| R08 / FL-D120、233 | 确认G11模板接受而Replay/effect不接受同源变体 | 模板、splicing、compose、effects、Replay共享同一操作/授权span及政策组件契约 | “由投资人支付”完整政策；跨段合法范围；范围外C/E/F句保留；无多余重复添加 |
| R09 / FL-D106 | 确认fixed_text与保护词在review前否决同义表达 | 区分指引要求逐字的固定文与允许语义生成；词形变化可进入独立复核，数字/主体含义仍必须保真 | 投资人/投资者同义通过；费率、渠道、期限、否定关系变错必须失败 |
| R10 / FL-D440 | 确认集合/收费固定语法及事实组状态耦合 | 源引文验证与语义证据验证分离，独立事实状态和依赖，仲裁不重走唯一regex门 | “现有A/C”“实行0.5%年费率”；服务费未知不抹掉已验证申购费事实 |
| R11 / FL-D442 | 确认delete-compose二次正确仍沿用首次错误 | 每次尝试独立校验状态，失败历史与当前候选分离，成功后独立verify | 首次错误/二次正确通过；二次仍错不通过；不回退粗暴整段删除 |
| R12 / FL-D140、399 | 确认无站点时范本字面缺失可误判VERIFIED_ABSENT | 区分无替换目标、已满足、已删除、未发现、未验证；语义残留复核和独立覆盖证据 | G13/G17同义旧义未改不能PASS；QDII G18真无目标不强制新增 |
| R13 / 原清单重复/审计项 | CLAIM_DUPLICATE_EFFECT范围、audit引文失败、分类器新错误码：具体误杀范围待复核 | 重复按operation＋授权站点＋对象/组件判断；统一artifact重取引文；有类型失败分类，不按未知字符串猜成功 | 同政策不同类别/正文摘要合法；同站点重复追加阻断；unknown错误不能默认complete |
| R14 / FL-D441 | 确认80节索引、12候选、20删除、40失败存在处理截断 | 全量索引＋可续跑分页；触顶含remaining/cursor/coverage，报告展示截断与真实未完成 | 85+章节、25+候选/删除、45+失败，尾部可到达；重启无重做/遗漏 |
| R15 / 原清单预算/恢复项 | 预算可配置、已有split/retry；sweep40/round3、短于8字、0.84/0.8限制需逐路径核查 | 区分资源上限/展示上限/候选阈值；段内offset分窗、输出分页、耗尽显式暂停；短quote歧义由地址补证 | 超长段及预算边界、末页、短删除句、低字面相似合法句；无静默漏内容 |
| R16 / 结构项 | 普通表格已读写；特殊结构可见性/可写性不同；full非全文开关 | 建立全包结构能力与读取缺口清单；最小安全增量支持有真实目标的结构；不无证解包 | 普通表格不回退；SDT/域/文本框/页眉页脚/合并嵌套表格各有明确状态与证据 |
| R17 / FL-D437及交付项 | 严格证明、最终查漏、失败分类须一致；不能靠降级抹未完成 | 完成状态由物理＋语义＋覆盖＋授权全部证据决定；前后端/持久任务一致 | 有遗漏、未遍历、过期证明、预算暂停不能complete；正常用例默认入口真实交付 |

### 2.1 不照抄原建议的部分

- **不实施“claim＋scope＋quote存在就无条件执行”**：仍须证明该operation确实获指引授权且适用于该对象，源版本正确、修改范围有边界。模型原始claim与批准记录分开。
- **不信任claimed_operations作为批准凭证**：现字段是归属失败后的存储，应保留审计历史，另建有效批准。
- **不把strict定义成仅认字面代码证明**：strict要求全部证据闭合；有来源、独立审核的语义等价可成为正式证明。审核失败仍未完成。review_assisted不得把漏改降成可交付complete。
- 不降低精确来源核验：模型意译引文先re-quote，不能直接把意译当真实源文。
- 不重写已经可读写的普通表格、不把full当全文开关、不把单一fuzzy阈值当全链路开关。
- 不放开跨不相关非空段的composite拼接；合法跨章/多站点修改建多个批准操作，不能虚构连续源文。

原清单的逐函数检查入口也须保留在任务卡：`_KNOWN_TITLES/_is_class_definition/_resolve_fee_tax/_copy_key/_is_fee_tax_section/_is_liquidation_section/_summary_enabled`归R05；`_READABLE_ZONES`归R16；`_apply_scope_gate`及composite归R04/R03；`find_old_text_all/find_fuzzy`的最小长度/阈值和`sweep_chunks/business_rounds`归R15，先复核调用链与补救而非直接删阈值；`_classify_delivery_items/final_omission_review/CLAIM_DUPLICATE_EFFECT`归R13/R17。短句/低相似本身不证明应改，模型仍须基于规则范围和真实地址复核。

## 3. 目标契约与数据流（字段可调整，含义不可丢）

以下为**待实现的目标契约，不是现有接口承诺**。优先复用仓库已有类型，避免再造平行引擎。

### 3.1 不可变证据对象

| 对象 | 最低字段与语义 |
|---|---|
| `RuleIdentity` | guide_id/source_hash/compiled_hash/version、rule_id、operation_id、来源段落、授权操作/条件/政策组件；ID必须在guide命名空间内 |
| `ScopeResolution` | source_hash、rule_identity、scope_version、多个leaf/block/span、正文摘要关系、候选/批准/排除理由；`unresolved`不等于空范围已完成 |
| `SourceBinding` | part、location、start/end、精确quote、source_hash；跨段parts逐一绑定，保持原段落和offset |
| `SemanticApproval` | 原claim引用、对应规则/对象/条件、绑定、scope_version、允许改动及必须保留、来源依据、独立复核记录、批准/拒绝/未决状态、模型/提示版本 |
| `FactEvidence` | 字段/对象/值、精确来源、quote存在状态、语义支持状态、UNKNOWN/CONFLICT、适用条件和依赖版本；不把未找到当FALSE |
| `ArtifactProof` | source/plan/artifact hash、operation/approval/site身份、实际artifact精确quote、技术验证、语义复核、覆盖状态与未解决项 |
| `CoverageLedger` | 文档block/窗口总量与已读、rule/scope/operation/site覆盖、分页cursor、未读/不可写/触顶/未复核原因、剩余量 |
| `Failure/RecoveryRecord` | 类型、可重试性、影响完成与否、已试动作、新证据、剩余预算/cursor；未知故障显式未分类并阻止虚假完成 |

源文、指引、事实、scope或计划版本变化，失效相关批准/证明/缓存，按依赖重新验证。不能拿旧批准配新span，不能把语义批准的任意ID伪装成代码执行授权。

实际切入点：`recall.Target`已有operations/claimed_operations/composite/scope_id，`generation/types.py`已有OperationSpec/PolicyComponents/RouteDecision，`generation/validators.py`已有Authorization，`RuleScope`容器已有leaf_ids/locations集合。优先扩展这些对象并抽出共享证据模块（例如`fundlex/semantic_evidence.py`），问题在解析/批准/消费契约，不是缺一个多叶子list容器；不要把巨型pipeline再复制一套。现有raw与compact offset有不同用途，必须集中转换回原始字符位置。

### 3.2 唯一业务判断链

1. 指引＋原件 → 事实/业务范围候选 → 完整条款提名。
2. 确定性快速匹配成功可复用；失败进入有界模型判断，不在后置阶段用另一词表再次推翻已经核实的等价语义。
3. 统一re-quote返回精确`SourceBinding`，独立确认授权/条件/保留事项，形成`SemanticApproval`。
4. 模板/拼接/compose/代码删除都消费批准，不改变范围。需要更大范围先重新批准，不隐式扩写。
5. 从不可变原件重生成完整计划与产物，复核实际文件，物理证明和语义证明共同形成`ArtifactProof`。
6. 独立覆盖检查有只读的更宽父章节/全文轻扫视野，可提出漏选候选；候选须重新映射到指引对应范围并批准后才能写。**全局可发现不等于全局可编辑。**

### 3.3 统一re-quote服务

inventory、survey、append、rebind、缺失操作恢复、事实补证、audit/artifact review均调用同一能力；源文和产物分别带版本，不能混用。

- 输入：document_version、规则来源/已批准业务范围、候选location/cursor、语义目标、上次失败、预算。
- 模型只能从提供的真实候选复制，返回location/quote/parts或not_found/need_more_context，不返回杜撰原文。
- 代码验证quote在相应part/段落中真实存在并计算offset；归一化匹配须保留到真实字符的可逆映射，不能用compact offset写入。
- 多处同文靠地址和对象消歧，不按quote文本去重。短引文允许结合地址/邻文核验，不全文盲删。
- 找不到可按cursor读取下一批，疑似scope遗漏提交独立范围复核，不直接扩大写入；同失败无新证据不得无限重试。

## 4. 多agent组织与进度管理

### 4.1 角色和文件所有权

主agent负责架构契约、计划、共享集中记录、预算、合并、候选冻结和发布；最多同时安排3–4名子agent，模型调用并发依据实际配额，不能等同agent数量。

| 角色 | 主要工作 / 推荐文件归属 | 不能自行做 |
|---|---|---|
| A 范围与绑定 | scope/structure/re-quote类型和测试；`rule_scope.py`及新增绑定模块 | 改别人的pipeline核心段、单独扩大规则范围 |
| B 规划与证明 | operation/registry/template/effects/claim_replay契约及测试 | 信任失败claim、跳过Replay、范围外去重 |
| C 事实与容量 | fact_evidence/fee_evidence/facts_recovery、分页/预算覆盖 | 修改冻结标签/分母、独立开新付费账本绕cap |
| D 独立测试与交付 | 盲标签/实际DOCX评分、故障/负例、前端API、E2E与发布核验 | 让被测输出决定gold，编造通过证据 |
| 主agent/集成agent | `recall.py`、`recall_pipeline.py`、targeting共享接入，API/store/schema及前端状态，集中记录 | 覆盖他人dirty工作、未审阅整树发布 |

`recall.py`/`recall_pipeline.py`冲突最高，默认单写者。子agent通过新模块/窄patch或分支提交契约接入；必须修改共享文件时先转移ownership，不让多个agent并发写同一文件。审查者不自审自己实现的语义边界，独立测试先保存预期再看实现。

每个任务卡记录：任务ID、R编号、依赖、owner、文件范围、输入/输出契约、验收测试、commit、状态、证据路径、下一步。主agent合并集中记录，避免重复编号；历史FL-D441有编号碰撞，引用时带标题。

### 4.2 自主推进和阻塞处理

- 常规选型、接口、调试、提交、重试、回归与受控发布由主agent自行决定，不问“是否继续/是否用多agent”。根据本方案验收门槛推进，不以固定耗时保证完成。
- 新语义疑点先读完整指引/原件/已有裁定、独立复核；范围外保持不改。仍无法解决的个别合同如实未完成，继续其他可推进任务，不发明授权。
- 无有效凭据、余额/授权cap、外部服务故障、无法安全发布等：记录具体阻塞、已尝试办法和恢复动作，继续离线/其他独立工作；确实无路时保存断点并给非提问式阻塞报告，状态NO-GO。**不询问不等于无限费用、绕过权限或伪造成功。**
- 依AGENTS在可观测约50%上下文时开始整理、60%前完成接续。不可观测时按阶段保守落盘。更新进度表、ACTIVE_HANDOFF、集中记录及运行账本，写清运行agent/进程，不虚构压缩指令。

## 5. 分阶段实施步骤与门槛

状态流：`planned → implementing → unit_verified → integrated → real_qualified → released → user_e2e_verified`；失败/阻塞单列。任何阶段不能凭测试数量跳过后面的真实交付。

### S0：保护工作区、冻结可恢复起点（主agent）

1. 按AGENTS验证机器；核对当前branch/HEAD、tracked/untracked、现有worktree、运行服务与磁盘。不要读取打印密钥值。
2. 安全保存tracked补丁/索引差异、相关untracked源码/测试/文档清单与哈希、当前依赖锁定信息。受保护快照位于 `/tmp/opencode/semantic-remediation-<timestamp>/` 或项目授权持久证据目录，检查无凭据；不能只保存`git diff`而漏untracked的`rule_scope.py`等。
3. 划分引擎整改依赖与Compare/飞书/指引生成等无关dirty工作。逐文件/逐hunk建立相关集成基线提交或可审阅补丁；保留其他未提交状态，不`reset/checkout --/clean/stash`抹掉。
4. 创建执行分支（建议`codex/semantic-engine-remediation-20261028`），记录真实起点。若用worktree，必须基于包含本任务相关dirty依赖的可恢复基线；不能只从旧HEAD启动。所有worktree标识基线commit及与生产差异。
5. 复跑离线审计，输出**新目录**，不覆盖历史 `docs/evidence/strictness-audit-20261028.json`。记录原失败特征及当前测试基线。新增的语义能力可能让历史characterisation断言不再成立，应保留原审计并新增正向验收，不能删除证据掩盖。

**退出门槛**：快照能验证/恢复；每个已有相关改动有归属；无secret入Git；基线、生产差异、任务owner和执行进度落盘。建议checkpoint：`chore(engine): capture reviewed remediation baseline`（不混入无关变化）。

### S1：固定契约与失败/成功反例（A/B/D，主agent整合）

1. 落实§3版本化契约、序列化、依赖失效、approved与raw_claim分离；最小贯通一条完整operation。
2. D独立建立R01–R17测试矩阵：每个正例配错误operation、范围外邻文、错误数字/渠道、未确定事实等负例；真实位置只用于fixture断言。
3. 先写失败回归：景宁正文两处、弘利用途句、G14重复基金、G11模板/Replay同源分歧、G18无目标及同义旧义残留、delete二次正确。
4. 添加版本过期/跨guide同ID/伪造批准/原文存在但与规则无关等安全反例，冻结期望依据与指引段号。
5. 为API/report/schema兼容制定迁移：旧任务保留旧engine/schema版本和历史结论，不能升级报告伪称新验证。旧checkpoint缺批准证据须重建/重验，不反序列化成默认approved。

**退出门槛**：契约和负例独立评审通过，测试在旧行为上能捕获已确认缺陷；主agent记录接口冻结版本。建议commit：`feat(engine): define versioned semantic evidence contracts`。

### S2：业务scope、多叶子与独立覆盖纠错（A）

1. 结构索引遍历完整文档，保留part、地址、段序、标题候选与可信度；修D06摘要嵌套标题未更新，不只硬编码p1256。
2. 固定标题/词表保留快速匹配；失败或多候选时把父章节/候选块交模型，按指引业务功能选**一组**合法叶子，返回证据。别只取first-match；别用候选个数>1当歧义拒绝。
3. 规则策略绑定guide/version/来源语义，不按裸G01等编号调用内置策略。内置兼容策略显式标明适用guide哈希，custom不误用。
4. 正文、正文重复条款与摘要真实对应关系分别建site；copy_key为关联提示不是准入词表，摘要身份/缺省开关不能删掉实际目标。
5. 建立只读独立覆盖扫描：能看到未被scope选中的块及父业务上下文，提出遗漏候选；核实归属、生成新scope_version并使受影响证明失效后，才允许执行。
6. 禁止一旦unresolved就回退全文写入。实际不属于该规则范围的候选记录排除证据、保留原文，不留成必改义务。

**退出门槛**：景宁G05两处正文均被覆盖；D06 G06 p280仍不被此规则处理；费用改标题/无常规标题/多个合法叶子/摘要缺目标负例通过；无规则外写入。建议commit：`fix(scope): resolve semantic multi-site scopes with independent coverage`。

### S3：统一重取引文、站点和operation批准（A＋主agent）

1. 实现统一re-quote，源文/产物分域，物理quote/offset/hash验证保留。长候选分页，短quote用地址/邻文消歧；连续跨段parts与不相关跳段分别处理。
2. 将inventory/rebind/survey/append/T3/audit所有入口接入同一契约；一次批准在后续阶段不再被另一组“承担/主要用于/类定义”词表重判。
3. 改造target_site_ok、append_site_ok、selected_operation、target_operation_keys：返回快速证据/疑点，语义不确定进入有来源独立核实。需要拒绝时给具体授权/条件原因，不只给词袋不命中。
4. 原模型operations原样留审计；失败转存的claimed_operations不得升为approved；合法operation的选择包含guide身份和对应对象/条件，不能只看quote存在。
5. 全链路统一not_found/needs_more_context/out_of_scope/invalid_quote/invalid_operation/unknown_condition，不把找不到混写为不适用。

**退出门槛**：弘利G17、G14变体、G01/G03同义定义与T3恢复均能到达合法规划；精确quote但错误规则/伪造source/范围外仍阻止写入。建议commit：`fix(binding): share requote and semantic operation approvals`。

### S4：事实抽取、适用性及无目标义务（C＋B）

1. Regex保留高置信快速路径，quote客观存在与语义支持分成两个状态；模型＋独立复核可以基于完整证据确认集合/收费语义，不再要求最后绕回相同语法。
2. 集合完整性与单个成员、申购费与服务费、渠道与期限等分别维护依赖。缺一项只使真正依赖它的操作未决，防止服务费UNKNOWN污染全部申购费组。
3. 模型判适用性的事实也必须有来源；不以UNKNOWN猜FALSE/空集/单类别，不根据投资标的费用推本基金收费。
4. 义务状态区分：适用待执行、已满足、已修改并证明、无对应替换对象、不适用、未验证/未完成；明确“无目标”的搜索覆盖和独立复核依据。
5. 实现G18缺对应原因句的闭环；不得用QDII p169净值条款证明收益分配站点满足，不凭guide字面不存在就关闭旧义残留。

**退出门槛**：事实语法/依赖正负例通过；QDII G18不新增、完整收益语义已满足与无目标状态分开；正常单/多类别/QDII/FOF不靠产品名豁免。建议commit：`fix(facts): separate evidence semantics and obligation applicability`。

### S5：执行器升级、联合规划和重试（B＋主agent）

1. 模板/拼接是低成本执行策略，不是限制业务可处理范围的白名单。确定性失败须暴露原因，进入有界重定位/范围重判/compose或联合重规划，受批准与预算约束。
2. DELETE优先模型确认应删span、代码执行；需要重写混合条款时明确批准保留/删除组件，不能生成任意replacement或整段兜底吞邻文。
3. G11完整原条款绑定、G08组件、G12/G13互斥旧表达和相邻操作统一联合计划，避免重复整句与错误去重；范围外独立句不处理。
4. 每次compose retry清空候选局部错误，保留attempt历史；有效候选必须进入当前独立校验。无新证据同样报错则停止该循环进入明确失败/其他恢复。
5. 固定政策中明确逐字部分继续保来源，允许语义生成部分进入独立复核；保护词改为含义/事实保护，未经证据的数值/对象/否定关系变化仍拒。
6. 每次修复更新完整计划、从原始合同重生成；不在旧final上叠改，不让旧批次结果污染新计划。

**退出门槛**：G09/G13失败能受控恢复；G11生成和下一阶段证明一致；二次正确重试通过；重要余文/公式/费率保留；重复执行幂等。建议commit：`fix(planner): recover authorized variants without widening edits`。

### S6：实际产物证明、语义残留与交付分类（B/D＋主agent）

1. Replay保留实际DOCX、edit计划、批准身份、地址/结构/hash的物理核验，不以report.replacement当产物证据。
2. 纯字面effect不确定时，独立模型在实际产物中提名精确quote并说明新义落实/旧义消除/对象范围，代码回查，再按统一证据政策批准或失败；不得只有模型verdict无artifact绑定。
3. 删除证明核对全部已确认站点及独立范围覆盖，同义旧义仍在不能靠范本文字不存在PASS。无目标需覆盖证据，不是旧句检索0次的别名。
   删除后的空quote不能单独证明成功：必须联合源站点、实际diff、产物邻文/位置映射、范围外保留及语义残留核查，不能为满足quote字段虚构一段已删除的产物原文。
4. 重复效果按operation、授权site、对象/类别、政策组件及执行幂等判断；两个类别/正文摘要合法重复不误阻，同一站点重复追加仍失败。范围外原句保留不当作必删残留。
5. audit意译引文先重取实际原文；无效证据不自动接受，也不重复抛无修复机会的quote错误。
6. 建立有类型失败及恢复表，未知错误码进入显式未分类未完成；最终查漏、open obligation、Replay、下载门禁使用同一完成契约。
7. strict与review_assisted都不能把未完成必需目标、未检查窗口、过期证明改名为complete。允许语义正式证明不等于放弃strict，未验证必须如实保留。

**退出门槛**：历史景宁final被识别漏改；新实际文件覆盖全部目标；同义等价不误拒，旧义同义残留不误放；新失败码/模型不可用不能虚假完成。建议commit：`fix(proof): bind semantic reviews to actual artifacts and coverage`。

### S7：分页、资源上限、长段与恢复持久化（C＋主agent）

1. 把80章节等处理上限改为全遍历或分页批量；12候选/20删除/40失败独立计量，不能只是提高常数。
2. 模型输出schema目标数/映射数、sweep窗口、恢复轮次、事实context均记录输入/输出是否完整，`has_more/remaining/next_cursor`可续跑。无exact remaining时给unknown和遍历边界，不伪造计数。
3. 长单段按原始地址/字符映射拆成重叠证据窗，业务条款跨窗待合并完成，不把半段当完整目标；源引用映射仍精确。
4. 核对真实完整请求token/输出预算，沿用已有scope/inventory/sweep拆分、网络/schema retry，补缺失路径而非重造传输。token统计与字符限制分别记录。
5. 资源/费用上限耗尽明确`LIMIT_REACHED`/`TRUNCATED`/`paused`与未完成证据，写入DB/checkpoint/UI；共享预算不因新分页、新agent、重启或换目录归零。
6. 检验源/guide/事实/scope变更后cursor和缓存失效，恢复无重复执行/费用重复记账；有进展才安排下一轮，无新证据不能无限业务轮转。

**退出门槛**：85+节、25+候选/删除、45+失败及多页输出全部可遍历；末尾应改目标到达；强制中断/重启能续跑；cap耗尽诚实未完成。建议commit：`fix(runtime): paginate coverage and persist bounded recovery`。

### S8：文档结构能力及前后端集成（A/D＋主agent）

1. 普通表格现有读写作为必须保留的正例。为合并/嵌套表格、inline/block SDT、超链接、域、文本框、页眉页脚分别记录能否看见/核引/写入/修订往返，不用统一unsupported隐藏。
2. 包级发现清单包括未进入正文窗口的部件；范围内可能有业务目标但不可写时，报告具体part/位置、影响和未完成，不静默当不存在。
3. 优先支持评测中真实规则目标需要且能安全实现的结构，逐种增加结构守恒与接受/拒绝修订测试；不假定任何结构都可无损解包。未支持结构明确限制，不报全部结构支持完成。
4. 实际运行的前端先核实是原生JS还是V2路由，不仅修改未发布前端。展示真实阶段、范围依据、语义核实、分页/暂停/恢复、未完成与业务提示，支持查看源/新文、报告及授权下载。
5. API/worker/store/checkpoint/交付schema、数据库迁移与旧任务读取一起验证；原始source不可变，用户/任务/文件隔离保留。指引只在配置页管理，普通提交只上传合同并绑定当前有效版本。
6. Compare、飞书与指引生成的生产能力做共享模块回归，不顺带重设计它们。新失败必须查明为本改动还是基线既有问题，不能默默忽略。

**退出门槛**：正常可编辑真实用例链路可走；结构边界透明无假complete；状态前后端一致；旧任务可读/恢复安全；共享功能无新回归。建议commit：`feat(workbench): expose evidence coverage and truthful delivery states`。

### S9：独立标签、真实修改与优化回归（D，主agent控制付费）

1. 先做离线全量回归和模块交叉审查，再开展真实模型；具体测试命令由当前pyproject/脚本`--help`核实，禁止虚构参数。
2. 按§6冻结样本映射、独立标签、评分口径、版本及预算。首轮用开发集代表合同打通，不将小样本烟测当全量验收。
3. 至少覆盖景宁、弘利、全球稳健QDII、价值优选、恒裕及第一批对应多收费类别/跨段/正文摘要合同，真实修改并重读下载DOCX评分。D06历史位置用于理解，新增真实运行只用第一批实际文件并记录新hash/location。
4. 按错误类别修复，不按合同名/编号/固定段号特判；先失败局部复测，再冻结新版本做完整开发集回归，所有尝试计费计时，旧产物保留。
5. 在既有授权cap内执行计划内优化，达到门槛再冻结候选、跑holdout。任何留出反馈用于调优后即记污染，按评测计划如实报告历史留出回归，不另偷换样本。
6. candidate的代码、guide、prompts、模型配置、依赖和schema全部版本绑定；评分数据属于最终候选，不能用早期好结果拼成“最终全通过”。

**退出门槛**：满足§6全部质量门槛，未通过不进入正式发布。独立评审签字式记录R01–R17状态与证据，不以“本地测试全绿”替代。建议commit：`test(engine): qualify frozen candidate on actual contract artifacts`。

### S10：受控发布与真实用户端到端（主agent＋D）

1. 盘点生产当前代码/服务、数据库schema、前端资源、guide发布状态和配置变量名；与候选作逐文件哈希差异。生产包含另分支Compare/飞书发布，不能用旧HEAD整树覆盖。
2. 按§7制作可回滚的干净release目录/清单；执行只影响FundLex的部署，配置/DB迁移前备份。默认不重启无关服务，不用开发开关绕过guide资格验证。
3. 先满足真实资格验证及指引发布条件，再从默认任务入口执行真实用户流程。不要手改released/auto_write等标志来制造交付。
4. 浏览器登录或项目支持的真实身份入口 → 配置页当前有效指引 → 普通合同上传提交 → 实际队列/Worker/真实模型 → 结果页查看 → 授权下载final/redline/报告；检查实际文件差异与证据，非脚本直调替代。
5. 正常应改用例必须有真实改动；至少复验景宁双正文目标、弘利变体、QDII无G18新增，并覆盖长合同、已满足、排除、不可完成/保护输入、预算暂停/重启续跑、身份隔离、指引切换。
6. 逐一核对final不含未接受修订、redline含真实Word修订、接受redline语义/结构等价final、拒绝redline恢复source；产物hash与API/报告/下载一致、范围外内容守恒。ZIP字节可能因合法元数据不同而不同，等价规则明确；交付文件本身sha必须精确一致。
7. 浏览器/网络证据留存脱敏，验证401/403未授权不可下载；临时账号/测试任务按受控清单清理，不删用户任务。

**退出门槛**：默认入口已交付正常合同、真实文件复核通过、生产版本可追溯、范围外不改、质量/安全无回归。失败须修复并复验或安全回滚，不能以任务结束代替业务正确。

### S11：收尾交付与接续材料（主agent）

- 完成阶段提交、版本/部署哈希、验证报告、实际访问入口与使用说明、升级/备份/恢复步骤。
- 结果包括最终版、修订版、改动/例外报告；失败合同只交明确工作文件或原因，不把原样/不完整文件叫最终合同。
- 更新进度、ACTIVE_HANDOFF、集中记录、评测结果及预算摘要；区分已实施/离线通过/真实资格通过/生产用户E2E通过。未解决R项和结构边界逐项保留。
- 若仍有必需用例失败、错误complete、未经批准改文或真实链路阻塞，最终结论NO-GO并附可执行断点，不写“全部完成”。

## 6. 评测、预算与验收细则

### 6.1 样本与冻结分母

继续执行 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` 的20–30份真实合同、独立标签和开发/留出隔离要求；固定D01–D20/holdout manifest、source hash、分母不改。

“后续新增运行用第一批”与历史固定清单可能并非逐字同一文件：S0建立**只追加的来源映射/冲突表**（固定case/hash → 第一批文件/hash → 是否完全一致/仅可比较/缺失），不修改原manifest或假装不同hash为同一原件。相同字节可映射运行路径；不同字节作为独立新证据单列，不替代固定case成绩。无法在当前资料和既有授权内满足两套约束时记录未完成，不偷偷换分母或扩样；不为此反复询问用户。

已知历史固定选择入口包括 `var/recall-first-evaluation/p6/selection.json`、`p6-current/selection.json`，记录源根与当前第一批不同，执行时须验证存在性/哈希。**第一批28份已有历史批量预测，不得重新随机划8份就称从未见过的独立留出**。盲读重建独立标签可改进真值，不能消除样本选择/预测泄漏；结果明确区分固定历史回归、第一批真实修改、真正独立留出。没有符合现有约束的独立留出时，该验收项保持未闭合、报告局限，不虚构证据或扩大授权取新样本。

独立标签先读原件/指引，不能看被测预测；本轮已讨论合同视作开发/缺陷回归，不能再冒称未见留出。新标签另存版本并锁定hash，旧gold/scorer/报告保留。文件不可解析、结构不能修改、服务失败、未取得可信真值的样本都透明列明，不在结果出来后消失。

### 6.2 质量门槛（运行前写入run_context）

- 已确认正常可编辑必需用例：范围内应改目标全部正确完成、范围外未授权语义修改为0、重要费率/公式/对象/否定关系错误为0、错误complete为0；不能用平均95%掩盖已知漏改。
- 所有必需目标进入指标分母，包括误排/未发现/未执行/结构失败；分别报告目标发现召回率、目标正确完成率、整合同全部完成率、按规则完成率、修改正确率、额外变化、审计误拒/漏检、真实下载一致性、性能/费用。
- 无目标/已满足/不适用正确区分；合法正文摘要重复与同site误追加分开；不可写结构/受保护输入/故障边界必须真实未完成，不伪称覆盖全部文档结构。
- 实际DOCX评分，不只读plan、report.applied或模型自评。逐个未标注diff核对是否有规则依据，范围外即不能算合理优化。
- 单测、性质测试、集成、API/数据库、浏览器、真实模型、真实DOCX、生产入口分别留证据。Mock仅用于开发回归，不能算真实交付。

### 6.3 预算纪律：不询问，但不扩权

1. 真实调用前查现有授权范围、账本、价格/模型配置和可用cap，仅记录变量名/额度和安全路径，不输出凭据。旧smoke的240 calls/$1是历史上限，不是这次新额度。
2. 主agent在一个共享账本预登记：原件/标签/批量/复核/E2E各阶段calls、HTTP尝试、token、费用估计、最坏重试预留、全批cap、并发。标签模型和审查模型同样计入，不能子agent各开新账本。
3. 批量先估计单份成本再预留开发回归、留出和生产复验；并发预约/扣账要原子、失败/重试仍记账。不得将用户“自主执行”解释为自动补充资金。
4. 没有可核实付费授权或余额时暂停付费阶段，推进离线与可做事项，记录budget_blocked及恢复条件；不以问句中断常规工作，不隐瞒阻塞、不重置计数或降低审计冒充完成。

### 6.4 现有工具的真实边界（执行前重新核对`--help`与源码）

| 入口 | 可以证明什么 | 不可以冒称什么 |
|---|---|---|
| `tools/evaluation/strictness_audit_20261028.py --output <新路径>` | 零网络现状探针，源码/样本指纹与局部行为 | 不证明修复、业务全完成或E2E |
| `tools/evaluation/controlled_regression.py` | 旧v1只读诊断，要求写门关闭，断言无修改文件 | **不能作真实DOCX修改runner** |
| `tools/evaluation/recall_run.py --input … --output … --guide … --ledger … --max-calls … --max-cost-usd …` | 库级真实评测；上下文/输出/轮次/窗口可配置 | 非浏览器/登录/持久Worker E2E；resume仅跳已有report，必须额外核对freeze，防混版本 |
| `tools/evaluation/real_contract_e2e_20261023.py --output … --ledger … FILE…` | 库级真实smoke，内部直接调处理流程 | 名字含E2E也不是生产用户路径；默认600 requests/$2不构成本轮预算授权 |
| `tools/evaluation/budget_preflight.py`、`BUDGET_PREFLIGHT.md`、`p6_run.py` | 复用既有付费准入；p6_run要求protocol及hash、manifest、labels、requests/cost-per-case，支持selection/group/run-id/base-url等 | 本地预检不代表真实服务已采用同一build/model/ledger/cap，服务侧须核验；其他runner需同等准入 |
| `tools/evaluation/p6_score.py --labels … --run … --output …` | 读取实际DOCX的机械评分基础 | 字面/fuzzy/类别归一化不能替代独立语义、范围外diff、摘要关系核对 |
| `tools/evaluation/verify_downloaded_artifacts.py RUN --selection … --data-root …` | 文件hash、接受/拒绝修订、真实改动等机械证据 | 明确不评业务完整，不能据此判合同complete |
| `tools/evaluation/delivery_e2e.py --source … --evidence-dir … --model-mode real --allow-real-model` | 显式real参数可跑真实模型/Worker隔离链路；默认fixture，dry-run零模型 | TestClient隔离链路不是生产浏览器E2E；禁止默认fixture计作真实调用 |
| `tests/browser/test_workbench.py` / `test_frontend_v2.py` / `test_guide_generation.py` | 前端/隔离状态与交互回归，需相应browser测试开关 | 现有dev身份/fixture套件不等于实际Worker和模型交付 |
| `frontend/package.json` 的typecheck/lint/test/build | 用npm ci与实际脚本验证候选前端构建 | V2构建通过不代表生产默认V1已更新 |

省略号是待执行者填写的已冻结路径/额度，不是可直接复制的shell命令；未核对预算不得自动执行真实runner。模型配置需安全注入，Linux runner不会必然自动读取生产env，不打印整份环境或带密码DB URL。

## 7. Git、整合、发布与回滚

- 每阶段最少一个可审查、可测试的逻辑提交，提交正文关联R编号/FL标题及测试证据；定向`git add`，避免`git add .`混入原件、大型证据、无关dirty或secret。阶段commit建议只是命名，不规定必须套用英文。
- 主agent维护integration分支；子agent基于共同包含dirty依赖的reviewed baseline创建任务分支/worktree，完成后审查diff再cherry-pick/merge。不要同时切换共享工作目录分支影响其他agent。
- 用户授权自主版本管理，允许本任务本地建分支/提交/冻结release；**未额外明确远端发布时不push**，不得force-push或替用户合并无关分支。文档/证据持久化不以push为前提。
- 候选冻结记录code tree/commit、dirty应为任务清单内已处理状态、guide/提示/schema/依赖/model role配置哈希、测试结果及预算摘要；禁止带未审阅dirty正式发布。
- 审阅 `tools/deploy/publish_workspace.sh` 和实际 `/usr/local/sbin/fundlex-publish` 行为再执行。该路径可能复制整个工作目录并重启服务；**若会夹带无关dirty，则不得从当前工作区直接跑**。用包含完整必要依赖的干净release worktree/受控发布清单并验证发布源；部署方案变化也需备份和证据，不临时覆盖生产共享文件。
- **2026-10-28只读实查的发布器陷阱**：wrapper仅转发root脚本；root与仓库脚本固定`SRC=/home/opencode/fundlex`，root第282行拒绝所有参数。**在其他worktree执行wrapper不会改变发布源；目前没有可用的`--source/--commit/--dry-run`参数**。S10前先实现并隔离测试“显式候选根＋冻结版本校验”的受控能力，或选择有同等证据的发布方式；不能为迁就固定SRC覆盖原dirty树，也不能执行截断脚本片段。
- 同次实查API/Recall/Compare/Feishu/Guide五个服务均active，但发布脚本`UNITS`只含前四个，缺`fundlex-guide-worker`。共享代码/schema替换前须核对并纳入适用服务的停启/排空与build验证，不能让Guide Worker继续持有旧代码。本轮只读发现登记至FL-D303，未修改服务或发布器；执行时重查真实状态。
- 本机`sudo -n`仅用于FundLex部署配置/服务验证；配置和数据库迁移前备份，迁移优先向后兼容。rollback清单覆盖代码、前端资源、配置、schema兼容、Worker/checkpoint版本，不能回滚后读坏新任务。
- 逐文件核对生产Compare/飞书/指引生成既有修复是否被保留，旧主分支并不一定代表完整生产版本。前后端和worker同一契约发布，必要时排空/暂停领取任务，不能让混版本worker使用旧批准。
- smoke/E2E失败按记录回滚到已知版本；不`git reset --hard`当前dirty树，不用DB整体旧备份覆盖生产新增用户数据。不可逆迁移有预案再发布，不能靠猜。

## 8. 必交付文件与完成声明

执行中新增/更新（路径可在S0按现有目录调整，须留映射）：

1. `docs/SEMANTIC_ENGINE_REMEDIATION_PROGRESS_20261028.md`：阶段/任务/owner/commit/测试/阻塞/下一步。
2. `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`：已有问题更新；新问题稳定编号，写证据、状态、实际验证范围，不重复造号。
3. `docs/ACTIVE_HANDOFF.md`：当前任务、版本、未提交文件、预算/账本、运行agent与下一条动作；历史保留。
4. 新run目录中的版本freeze、样本映射、独立labels、metric配置、各尝试账本、原始模型/源引用证据（不含密钥）、plan、实际产物/hash、scores、未标注diff与错误分析。
5. 候选审查/生产发布清单、备份和回滚路径、服务/前端版本hash、浏览器E2E/下载鉴权/修订等价证据；`docs/REAL_REVISION_EVALUATION_RESULTS.md`追加版本结果，不覆盖历史。

最终答复先说真实交付结果，列版本、访问入口、实际下载产物、验收证据及仍存在的限制。只有S0–S11适用门槛全部满足才能宣称本次整改交付完成；不能以“方案完成”“代理报告通过”“单测很多”“状态complete”代替。

## 9. 本次规划审阅记录（不是开发验证）

- 两名只读agent分别审查实际语义契约/模块接口，以及测试工具/预算/生产基线/发布路径；主agent统一整合，无并行修改共享文档。
- 主agent只读复核了root/仓库发布器固定SRC、拒绝参数和UNITS列表，以及五个服务active事实；没有调用真实模型、改配置、重启服务或部署。
- 本方案已覆盖R01–R17及用户原清单的待核实项，刻意保留正确的物理/预算/授权边界，并纠正“信claimed_operations”“普通表格全只读”“strict只认字面”等不准确建议。
- 文件校验及链接核对只证明方案可接续；真实工程状态仍是未执行。接续模型必须从S0重新核对版本/资源，不用本节取代开发测试。
