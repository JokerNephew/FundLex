# 《泛化假设清单》——EN5 / B4 引擎泛化审查（2026-11-02）

> 性质：只审查+提案，未改任何业务代码。工作树 `codex/comprehensive-remediation-20261028`，HEAD `158475f`。
> 审查入口：`guides/builtin_guide_v1.json` schema 反查消费点；范围 `fundlex/`（规则执行与解析消费侧）+ `fundlex/guide.py` + `fundlex/guide_generation/`。
> 既有相关记录：FL-D439（内置 G 编号策略绑架自定义指引）、FL-D538（配置化能力缺口，docs/CONFIGURABILITY_ANALYSIS_20261030.md）、FL-D131（红/粗体无语义，仅计数）。
> 新发现条目统一用 `EN5-xx` 占位编号，报主线派 FL-D 正式号。
> 风险级：**高**＝新指引直接走错逻辑/静默漏改；**中**＝需人工适配或触发安全关门（fail-closed）阻断；**低**＝注释/展示/诊断层面。

## 假想新指引形态（审查基线）

新指引与 v1 不同：①主题不是份额类别/费用（如信息披露、流动性风险）；②rule_id 可能是自定义顺序但非 `Gnn`；③篇目名不再是释义/基金费用与税收 等；④可能不用红/粗体字、或反而用颜色表达强制语义；⑤条件体系不再是 class_count/has_service_fee/is_floating_fee；⑥operation 结构不变（append/replace/delete/noop 通用）但数量/比例不同；⑦可能通过 guide_generation 产出或人工编写入库。

---

## A. fundlex/guide.py（解析与认证侧，主线自审）

### A-1【高】rule_id 必须是顺序 G01..Gnn，写死在确定性校验
- 锚点：`fundlex/guide.py:275-288`（`expected_id = f"G{position+1:02d}"`，`re.fullmatch(r"G\d{2}", rule_id)`，非顺序即 `GUIDE_RULE_ID_INVALID`）；L391 `rule_id is sequential: G01, G02, ...`。
- 假设：一切指引的规则编号就是 G+两位顺序号。
- 断裂：新指引（含人工编写）若想用语义编号（如 DISC-01）或与原文条款号对齐，连解析校验都过不去。
- 修法：校验只要求唯一性/非空/稳定格式（如 `[A-Za-z0-9._:-]+`），顺序号策略下沉为"解析器默认生成器"，可由指引发布 sidecar 覆写。
- 风险级：高（且连带 operation_id `rule_id:index` 与 registry 键空间）。

### A-2【高】CONDITION_KINDS 与值域 = v1 份额类别/费用条件体系
- 锚点：`fundlex/guide.py:37`（`CONDITION_KINDS = ("none","class_count","has_service_fee","is_floating_fee","compound")`）；L230-244 值域校验（class_count 仅 1/"multiple"）；L444-450 JSON Schema 中 `integer enum [1]`、`string enum ["multiple"]`。
- 假设：指引分支条件只可能有"份额数量/有无销售服务费/是否浮动费"三类事实。
- 断裂：新主题的条件（如"是否指数基金""是否开放期"）无 kind 可表示；`has_service_fee` 之类也无对应事实提取器（引擎侧 fact_status 键同样写死，见 B 段）。
- 修法：condition kind 改为注册表+schema 可扩展点，v1 三种 kind 仅是内置注册项；解析 instruction 里的条件说明按指引域注入。
- 风险级：高。

### A-3【高】section_hint 篇目名硬编码 v1 业务域（且两处篇目清单互相不一致）
- 锚点：`fundlex/guide.py:44-46`（`GUIDE_DOMAINS` **8 项**：释义、基金的基本情况、基金份额的申购与赎回、基金费用与税收、基金合同的变更、基金合同、基金的收益与分配、基金财产清算）；L395-396 `_PARSE_INSTRUCTION` 给模型的篇目枚举却只有 **6 项**（"section_hint names the business domain, one of 释义, 基金的基本情况, 基金份额的申购与赎回, 基金费用与税收, 基金的收益与分配, 基金财产的清算"）；`guide_generation/scope.py` 的 `DEFAULT_GUIDE_SCOPE` 又是另一套措辞（"基金财产清算" 无"的"）。质检确认三处清单两两不一致。
- 假设：每份指引的篇目域就是 v1 这套名字；且三套硬编码清单本应一致。
- 断裂：新指引篇目名不同 → 模型被指示往旧域上套，section_hint 失真，下游 `rule_scope.py`/section mapping 全域失配；v1 内部措辞漂移已导致生成侧 scope 与引擎 parser 对不上（见 E-13）。
- 修法：域清单从指引源文（自动归纳）或 sidecar 提供，instruction 模板化注入。
- 风险级：高。

### A-4【中】解析指令内嵌 v1 业务语义（share class / A类基金份额 / 15-group 字样）
- 锚点：`fundlex/guide.py:404-406`（slot_tokens 举例 "A类基金份额， C类基金份额"、class_substitution 释义绑定 share-class）；L409-411（条件说明点名单一/多份额类别、销售服务费、浮动费）；L415（"The 15-group human reading of this guide is a reference only"）；L432-434 `_VERIFY_INSTRUCTION` 同样点名 share classes / sales service fee / floating management fee。
- 假设：指引永远谈份额类别费用（"15-group"更是直接把 v1 的人工分组读法写进通用解析器）。
- 断裂：新指引解析时模型被 v1 语境污染；class_substitution/slot_tokens 字段对非份额类别指引是死的或被迫硬套。
- 修法：解析/验证 instruction 不含任何具体指引业务词，条件与 slot 语义从域配置注入；"15-group"等 v1 专属句子移入 builtin 专用 profile。
- 风险级：中（模型侧偏置，不硬失败，但拉低解析质量与独立性）。

### A-5【中】颜色/粗体假设：红=弱绿蓝阈值 + 多数票判定，且语义被 FL-D131 归零
- 锚点：`fundlex/guide.py:80-88`（`_hex_red` red≥0xB0、green/blue≤0x60）；L139-142（`counts*2>total` 多数票）；L368-381 stats 只计 red_paragraphs/bold_paragraphs 数量；L546-558 `_source_header` 只给计数不给清单（FL-D131 决定红粗体无语义）。
- 假设：①指引若强调文本必是"红/粗"两种形态；②强调无语义、仅诊断。
- 断裂：新指引若用颜色表达"必须改/禁止改"语义，引擎完全无视；若用其他颜色（蓝/高亮）也识别不了。
- 修法：强调语义显式化——解析 schema 增加 `emphasis_policy`（none/red_mandatory/…），由发布侧按 per-guide 声明，解析层照传原文样式而非硬判定。
- 风险级：中。

### A-6【低】配套硬阈值/上限
- 锚点：`fundlex/guide.py:252`（`_heading_only` ≤64 字判标题段）；L477-492（operations≤12、old_text_variants≤12、slot_tokens≤12、references≤8、source_paragraphs≤60、groups≤40）；L666/671/679 repair context 截断 40/10/20 条；L583-584 requirement 截断 200 字。
- 假设：指引体量与形态与 v1 同量级（107 段、22 组、34 op）。
- 断裂：超大指引（>40 组或单组 >12 op）直接被 schema 拒。
- 修法：上限参数化（域配置/环境变量），默认值保持 v1 行为。
- 风险级：低。

### A-7【低】op 必写字段与 noop/text 结构固定
- 锚点：`fundlex/guide.py:327-328`（append=new_text、replace=old_text+new_text、delete=old_text、noop=text）；L38 `OPERATIONS` 四值；L321-326 group_kind/one_of_group 硬结构。
- 假设：操作代数就是这四元组；新指引若需"move/renumber/annotate"类操作无法表达。
- 修法：OPERATIONS 注册化，未知 op 在解析期 fail-closed 并给出扩展点。
- 风险级：低。

### A-8【中】noop 语义占位、`one_of` 仅允许"历史同义 replace 变体"
- 锚点：`fundlex/guide.py:888-897`（ONE_OF 校验：必须 ≥2 条、全部 replace、condition 完全一致、new_text 完全一致）；registry.py:85-87 G21 noop。
- 假设：分支形态只有"历史表述变体"一种；新指引若 ONE_OF 表示"二选一执行"会被判 `one_of_not_historical_alternatives`。
- 修法：ONE_OF 语义拆分为 `historical_variant` / `conditional_choice` 两类，后一类延迟到执行期按 condition 取分支。
- 风险级：中。

## B. fundlex/generation/（执行策略层，主线自审 + 直接证据）

### B-1【高】StrategySpec 全表按 v1 G01..G22 逐条写死（含业务文案 note）
- 锚点：`fundlex/generation/registry.py:23-89`（22 条 StrategySpec，mode/allowed_tiers/required_fact_status/required_components/preserve_policy 全部 per-rule 硬编码；note 中文版位如 L40「调低赎回费率→调低销售服务费率」）；L143-163 `_OPERATION_OVERRIDES`（G05:0/1/2、G11、G12、G20 键名与形态绑定）；L170-176 `counts` 每规则 operation 数量写死（G14:6、G05:3 等，正是 v1 的 34 op 形态）。
- 假设：指引=22 组/34 op、编号 G01..G22、每条规则的执行策略是代码常量。
- 断裂：新指引 rule_id 不在表内 → `strategy_for` 落 `_UNKNOWN_SPEC`（L188-191，COMPOSE+全链验证的安全默认）；执行面上层若按标号查策略即错位。既有 FL-D439 已记"策略绑架"风险，本条为其根源锚点。
- 修法：策略元数据迁移到指引版本 sidecar（per-guide、可校验、随同认证哈希绑定），registry 退化为"未提供 sidecar 且 rule_id 在 v1 白名单"时的兼容层。
- 风险级：高。**报主线派号（建议并入 FL-D439 或新条目）**。

### B-2【高】`policy_components_for_operation` / required_components 键绑 G 编号
- 锚点：`fundlex/generation/components.py:17-24` 注释绑 G15/G16/G17、G01/G03、G08/G11；L114-132 规则→组件硬映射（`"G01": ("direct_sales_fee_exemption",)`、`"G16": ("daily_accrual","direct_refund","non_direct_sales_policy","over_one_year_refund")`）。
- 假设：政策组件集合是 v1 费用机制的固定词表。
- 断裂：新指引无对应组件键，compose/validate 层退化或借用错误保护集。
- 修法：组件词表迁移到指引域 profile；registry 只引用 profile 注入的键。
- 风险级：高。

### B-3【高】effects.py 大量 per-G 正则与站点逻辑（句型硬编码典型灾区）
- 锚点（部分）：`fundlex/generation/effects.py:125`（G02/G04 门控）、L139-155（`"G06"`/`"G13"`/`"G17"` 各挂专属 `re.compile`）、L415-440（G08/G11/G12/G13/G06/G15 分支）、L448-491（G02/G04/G05 站点与 G01/G03/G16 append 名单）、L582-592（G15/G17 邻接规则）、L652-688（G06 专项）、L727（G05 absent coverage）。
- 假设：每条规则的"效果如何判定已完成"由硬编码中文句型/规则编号分支决定。
- 断裂：新指引全部走不到这些分支→效果判定回到通用兜底，既有 22 规则专用护栏（防误删/越界）对新指引不存在，反之若新指引误用 G 编号会错套用 v1 护栏。
- 修法：把"删除目标语义正则/append 锚点/邻接借用"声明为 per-rule sidecar 元数据；引擎只执行声明。
- 风险级：高。**报主线派号**。

### B-4【中】`preserve_original_qualifiers=(rule.rule_id not in {"G14"})` 单点特判
- 锚点：`fundlex/generation/registry.py:117,122`。
- 假设：只有 G14 一条规则例外；新指引同类需求无处声明。
- 修法：移入 sidecar per-rule 字段。
- 风险级：中。

### B-5【中】operation_id 形态 `RULE:idx` 与 `_normalize` 大写化假设
- 锚点：`fundlex/generation/registry.py:194-196`（`split(":",1)` + `.upper()`）；L217-228 合成索引。
- 假设：规则编号可安全大写化且不含冒号以外语义；对大小写敏感体系（或自定义 id 含 `:`）会冲突。
- 修法：id 规范化策略由指引 profile 声明；禁止大写折叠或改为显式原始比较。
- 风险级：中。

### B-6【中】edit_summary 展示层 G01..G22 中文标签表
- 锚点：`fundlex/edit_summary.py:20-40`（22 条硬标签，G21 缺位）、L78 composite `G12+G13` 拼接口径。
- 断裂：新指引条目在报告/前端展示落无标签兜底或英文原 id。
- 修法：标签从指引文档 title 字段动态派生，写死表仅作 v1 内置展示优化。
- 风险级：低-中（展示层）。

## C. recall.py / recall_pipeline.py（召回与执行层，子 agent 审计，33 条）

> 体量提示：这两文件是全库绑定最深处（recall.py 代码行内引用 G 编号 **267 处**、注释 105 行；recall_pipeline.py 代码行内 33 处、注释 34 行）。下表按风险排序，高风险前三条是"静默路径"，新指引不报错但全错。

### C-1【高】`_RULE_TOPIC_TOKENS` 22 组主题词 veto 表 + fail-open
- 锚点：`fundlex/recall.py:5844-5867`（表）、`5870-5889`（查不到 id `return False`）。
- 断法：新指引 id 不在表 → "合同确无该主题"硬事实防线整体失效，主题防误改护栏静默消失。
- 修法：topic_tokens 由 guide 每组声明（入 sidecar 字段），未知 id 显式告警。
### C-2【高】satisfied 证明的逐规则原文判别句
- 锚点：`recall.py:1999-2010`（G02/G04 集合、G09 "扣除或加上相应的费用"、G11 "通过直销机构" 字面值豁免）。
- 断法：新规则无分支 → 全走通用路径，suffix/重序证明系统性误判。
- 修法：豁免条件声明在 operation 元数据。
### C-3【高】单函数内 5 规则行级特判的证明/归一化
- 锚点：`recall.py:2776/2848/2885/2890`（G14 费率归一化）、`2902/2905/2914/2920/2926`（G17/G15/G22/G08 专属 effect 证明）。
- 断法：新指引删除/替换语义无人接管 → 残留/越权裁决错误。
- 修法：per-rule 证明策略外置为声明。
### C-4【高】扫描/合并阶段 G 号特权
- 锚点：`recall.py:3023/3041/3058`（G16 satisfied、G02/G04 去重特权）。
### C-5【高】整段 G05 专属 target 克隆补召
- 锚点：`recall.py:3121-3178`（`rules_by_id.get("G05")` 克隆 + 伪造 records）。
- 断法：新指引需要等价确定性补召时无入口 → 漏召。
- 修法：声明式 per-rule expansion pass。
### C-6【高】composite 归并白名单
- 锚点：`recall.py:3374-3380/3440-3443`（G01/G03 append、G17 delete 归并）。
### C-7【高】G16 append + G17 delete 同址责任移交
- 锚点：`recall.py:4478/4530/4570-4585/4610-4749`（composite "…+G16"/"G17" 接管逻辑写死）。
- 断法：任意兄弟规则共享站点场景（新指引普遍存在）无对应机制 → 证明丢链或重复改。
- 修法：站点归属/移交关系入 guide 声明。
### C-8【高】G15 支付条款专属处理器 + 跨规则直调 G08 政策文本
- 锚点：`recall.py:5367-5433` + `_g15_*` 系列（5219/5268/5276/5303/5334/8251/8312）+ 5413 `instantiate_policy_text("G08", …)`。
### C-9【高】审计 replan 按 G 号走"费率调整"专用路径
- 锚点：`recall.py:6287/6353-6359/6397-6468`（含 "申购费率由基金管理人决定" 锚）/6681-6705。
### C-10【高】composer/audit 形状路由散弹区（40+ 处）
- 锚点：`recall.py:6897-7797`（如 6897/6949/7152/7204/7305/7547/7797 `if rule_id == "G12" and mode == "replace"`）。
- 断法：新编号 100% 落通用分支 → 为 v1 修的 FL-D 系列保护全部失效（最大面积损失）。
- 修法：strategy 由 operation 形状推导或 guide 显式声明。
### C-11【高】事实抽取 hints/keywords = 费用领域词表
- 锚点：`recall.py:728-729`（`_FACTS_SECTION_HINTS=("释义","基金的基本情况","费用","税收","申购","赎回","清算","收益")`、`_FACTS_KEYWORDS=("份额类别","销售服务费","申购费",…)`）。
- 断法：新主题事实段落全灭 → Facts UNKNOWN → 条件链崩塌。
### C-12【高】condition kind 封闭集 + 未识别 kind 静默 FALSE（五静默路径之首）
- 锚点：`recall.py:5952-5967`（`_condition_fact_names` 仅识三种）、`5985-6012`（`condition_matches` fallthrough `return False`）、`6015-6057`（`condition_status` 同构 UNKNOWN）。
- 断法：新指引条件全判 FALSE → 带条件 operation 零实例化且不报错（静默漏改的最典型形态）。
- 修法：kind 注册表 + 未识别 kind 显式抛错。
### C-13【高】Facts dataclass 本身=销售费用新规领域模型
- 锚点：`recall.py:540-660`（subscription_group/service_group/direct_sales_exempt_group/floating_management_fee/has_service_fee…）、723-724 channel、1086/1167。
- 断法：新主题前置事实无字段承载（中高端层绑定，非 if 可解）。
- 修法：Facts schema 由 guide profile 驱动生成。
### C-14【高】槽实例化只认字面 A/C 类（slot_tokens 仅作证据/提示，未驱动实例化）
- 锚点：`recall.py:5612-5615/5629-5638/5653-5668`（`instantiate_slots` 用字面 `"A类基金份额"`/`"C类基金份额"` 替换）；`recall.py:7440/7455/7844`（slot_tokens 确有 3 处消费，但仅写入证据 `slots` 与 compose prompt 提示，**未参与替换驱动**）；`recall_pipeline.py:1984-1989`（`("A类基金份额","subscription_fee_group"),("C类基金份额","service_fee_group")`）。
- 断法：schema 提供的槽词无法左右实例化 → 新指引槽词（如"普通投资者"）→ SUBSCRIPTION_GROUP_EMPTY 或未实例化文本写入合同。
- 修法：用 guide slot_tokens 驱动槽替换（质检修正：非"零消费"，而是"消费面在旁路不在主驱动"）。
### C-15【高】`_delete_keyword_bag` 费用词袋服务**所有**规则的 delete 召回
- 锚点：`recall.py:5462-5481`（销售服务费/申购费/赎回费/认购费/管理费/托管费/份额类别…），调用点 4070、7648。
- 断法：非费用主题删除条款几乎必漏召。
- 修法：词袋由 rule old_text 自动派生。
### C-16【高】G06 物理 scope 与删除对象正则写死
- 锚点：`recall.py:1232-1319`（`_G06_SUBSECTION_RE`、g06_scope_locations、1313 兜底整句 "不同基金份额类别之间不得互相转换。"）、5105-5112 `_G06_PROHIBITION`。
- 断法：新指引无"基本情况+份额类别设置"小节 → scope 恒空（fail-closed 零召回）。
### C-17【高】G16 append 机制词与落点锚 = v1 句型
- 锚点：`recall.py:4204-4226`（直销/返还/365）、4233-4242（`_APPEND_DEFINITION_MARKERS` "份额类别：" 等）、4376-4459 `_g16_payment_anchor`（"每日计提"+"按月支付"）。
### C-18【高】G12/G13 数字写进引擎（7日、1.5%、全额计入基金财产）
- 锚点：`recall.py:5036-5069`（"少于7日" 在 5040/5043）、5146-5147（"1.5%" 首现）、5191-5212（四联 token，两词俱在 5206-5210）。（质检修正：行号区间按实校准。）
- 断法：新指引数值/表述不同 → 确定性匹配静默不命中。
- 修法：数值/标记入 operation 声明。
### C-19【高】G05 splice 缝合词对写死
- 锚点：`recall.py:6131/6134-6163`（`调低[^。；;]*?赎回费率`、terminal/new_terminal 词对）。
### C-20【高】站点守卫锚表逐 G 号中文锚
- 锚点：`recall.py:9398-9408`（`_TARGET_ANCHORS`）+ 9412-9563 `append_site_ok/target_site_ok`。
### C-21【高】合成补召 pass 与单叶 scope 兜底只存在于 v1 具体规则
- 锚点：`recall.py:9623/9626-9659`（`_G08_ACTUAL_RATE` 字面值、`G08V*` target 注入）、9662-9686/9709（`_G22_ORDERED_ITEM`）；`recall_pipeline.py:994/1027-1036`（`_FEE_SCOPE_RULES=frozenset({"G15","G16","G17"})` 单叶兜底）、2115-2162（G02/G04/G08/G11/G18 门控链）、4635-4662（三注入点）。
#### 中风险（C-22~C-32，管线层特判，需逐条入 guide 或删除特例）
- C-22 `recall_pipeline.py:3729` `_BUSINESS_PENDING_RULES={"G14","G18"}`（待定/阻断分类错配）。
- C-23 `recall_pipeline.py:3558` scope 校正免证白名单 `{"G01","G03","G16"}`。
- C-24 `recall_pipeline.py:4037-4043` G15 兄弟站点销残。
- C-25 `recall_pipeline.py:5231` 必含分组标签仅 G02/G04。
- C-26 `recall.py:2410-2413` `_CONFUSABLE_SWAPS` 申购/赎回/托管费封闭对偶（新主题 fuzzy 假阳性）。
- C-27 `recall.py:1482-1492` 释义定义锚+A/C 类别计数+费用词。
- C-28 `recall.py:930-954` 份额类别计数、申购费 ±12 段邻域窗口。
- C-29 `recall.py:8312-8320` `"G15" in edit.rule_id.split("+")` 通知门槛。
- C-30 `recall_pipeline.py:1148/1207/1367/1790`（G18/G22 normalized-copy、G22 scope_id 字面值 "G22:ordered_list"、G02/G04 证明绑定、G16_PARTIAL_CLAUSE 例外）。
- C-31 `recall.py:2613-2635` operation_key "RULE:index"、id 一律 `.upper()`（非大写编号体系撞名）。
- C-32 `recall_pipeline.py:4664-4668` `FUNDLEX_SEMANTIC_V2_RULES` 默认 `"G09"`。
#### 低风险（C-33）
- C-33 `recall_pipeline.py:4265-4267` + `recall.py:9653` 展示文案/字面值命名（G08V、G22:ordered_list 等）；recall.py 注释 G 编号 105 行 / pipeline 34 行（溯源用，低）。

## D. 其余消费点（子 agent 审计，32 条，含发布链路三重门）

> 核心判断：approve/certification 是**三重 fail-closed**（解析层 guide.py 校验 → 启用层 guide_store registry gaps → 运行前 jobs.py `_bound_guide_document` 再验 gaps+certification）；带 findings 的指引**无在线 disposition 通道**（`certify_guide_document` 只收调用方预给的 dispositions，全仓仅测试调用）→ findings 非空的指引永远卡 GUIDE_NOT_CERTIFIED。更危险的是 "id 撞号"：新指引 rule_id 必然复用 G01..Gnn 空间（A-1 强制发号所致），所有按 id 查表的部件会按 v1 业务含义解释新指引。

### D-1【高】rule_scope 按 G 编号派发 scope 家族
- 锚点：`fundlex/rule_scope.py:1139-1156`（`{"G01","G02"}→释义`、`{"G15","G16","G17"}→费用税` …）。
- 断法：撞号新规则被解析到错误业务章节 leaf，静默错范围/漏改。
- 修法：派发依据从 id 改为 guide 自带的语义类别字段（section_hint 或新增 category）。
### D-2【高】targeting 候选分类器硬编码内置文本锚
- 锚点：`fundlex/targeting.py:258-289`（G12 "赎回费用由"、G13 "1.5%/少于7日"、append 需 "销售服务费" in text）、236/399（`_RULE_TOPIC_TOKENS` 查表）、486-511（G16 站点特判、G02/G04 class-site）、1040-1294（恢复通路继承同一锚点）。
### D-3【高】Facts schema / 恢复 / 费用证据全绑定 v1 领域
- 锚点：`fundlex/recall_prompts.py:28-115`（FACTS_SCHEMA：classes.subscription_fee/service_fee/direct_sales_exempt/floating_management_fee…）；`fundlex/facts_recovery.py:16-90`；`fundlex/fee_evidence.py:7-128`（销售服务费极性、直销特殊语法）。
- 断法：新主题事实无处安放 → 条件评估全 UNKNOWN → 分支义务静默不执行。
### D-4【高】condition kind → 事实名硬映射
- 锚点：`fundlex/obligations.py:219-223`（`_CONDITION_FACTS`）；266/307 `strategy_for(rule_id)` 取默认 `_UNKNOWN_SPEC`（Tier3 COMPOSE 安全侧默认，遇撞号 v1 成分要求——直销豁免等——会走错且不报错）。
### D-5【高】条件词表封闭（与 A-2 同一根因，消费侧锚点另列）
- 锚点：除 guide.py:37 外，消费点在 obligations/recall_prompts 全链；新 kind 连校验都过不去（修理轮耗尽 → 指引无法 clean）。
#### 中风险（D-6~D-19，发布链路与结构性门禁）
- D-6 `guide_store.py:262-269` `set_current_guide` 调 `operation_registry_coverage_gaps` → 非内置 id 指引永远 `GUIDE_OPERATION_REGISTRY_MISSING`，无法启用。
- D-7 `jobs.py:419-426` `_bound_guide_document` 同卡 + `validate_runtime_guide` → 任务直接 PROCESSING_FAILED。
- D-8 guide.py GUIDE_DOMAINS heading-only 豁免（A-3 已记；此处补消费点 366-367）：新指引标题段全计 coverage_gap → clean=False → 永不自动认证。
- D-9 `validate_runtime_guide`/`certify_guide_document`（guide.py:793-912/932-950）：findings dispositions 无运行时在审通道 → 新指引 approve 只能离线。
- D-10 `semantic_contract.py:17` `DEFAULT_POLICY_PATH=guides/semantic_policies_v1.json`（policy 只覆盖 G02/G03/G04/G05/G09/G16/G18/G22）+338：新指引无语义策略静默跳过该通路。
- D-11 `rule_scope.py:101-305` `_KNOWN_TITLES`/`copy_key` 词表 + 683-948 费用/基本情况/释义族 leaf 策略：新主题退 `_resolve_default` 失去 leaf 精度与"正文↔摘要"联动修复。
- D-12 `tasks.py:51-53`、`jobs.py:326-335`：新指引错误正确落库但表现为"任务处理失败"而非可配置的"指引不支持"。
- D-13 `rules.py:394/444-447/528-530/568/594-595/676-701`（退休引擎，七日 1.5% 正则等，RULESET_RETIRED）：常驻且可被离线误启用。
- D-14 `rules_v2.py:38-51/176/187` + v2.py + v2_pipeline.py（同为退休路径，SLOT_GROUPS/recognition_kind 全内置主题；质检补点：`v2.py:560-563` 类别定义锚硬编码费用词组、`v2.py:919-928` 直销收费判定句型 `"直销机构"+"不收取…"`/`"不再（继续）收取销售服务费"`）。
- D-15 `qualification.py:14-20` `_SIGNATURES`（ETF/货币/QDII/REITs 排除集）+ recall_prompts.py:26 FUND_TYPES：排除资格隐含 v1 适用范围。
- D-16 `qualification_evidence.py` `_NUMBERED_FIELD`/`_VALUE` 锁基金模板字段。
- D-17 `applicability.py:26-51` 通用三态评估提示混入 "share class, fee or branch"、"A class…sales-service fee" 主题引导词。
#### 低风险（D-18~D-21）
- D-18 `edit_summary.py`（见 B-6；消费面=tasks 工作台概览 + tools p6 交付包；撞号时展示内置业务标签误导）。
- D-19 `delivery.py:19/45-46` 用户文案费用主题措辞；`docx.py:540-547` 合同章名白名单与 v1 篇目名部分重合（多为通用合同章名，弱信号，仅注明不整改）。
- D-20 `recall_prompts.py:296-301/344-358` 审计/巡检 prompt 示例主题偏向。
- D-21 `guide_store.py:28-29` BUILTIN_GUIDE_PATH 加载点（结构正常）；185/189 `frozen_builtin` 仅作用于内置行。
#### 已确认无内置假设（正面结论，抽查+全文 grep 通过）
`frozen.py`、`selective.py`、`db.py`、`config.py`、`workspace.py`（gg_* 属生成域）、`models/`、`application/task_service.py`、`compare/`、`regulatory/`、`recovery/`、`checkpoints.py`、`artifact_review.py`、`api.py`（规则总览数据驱动）、`html_view.py`、`docx.py` 等；`semantic_evidence.py:721-728` 按整份规则 hash 区分同 rule_id 的两份指引（正确防御）；guide.py 红/粗体仅计数无语义（A-5 的另一面：现行为合规点，但新指引若赋颜色语义则成缺口）。

## E. fundlex/guide_generation/（子 agent 审计，44 条核心 19 条高/中高）

> 核心判断：生成管线**没有**任何"22 组/34 op"固定数量断言；v1 绑定集中在**主题词表、篇目集合、scope 来源**三处。store/eligibility/vector/model_router/api/worker/human/corpus_catalog/export 为正面结论。

### E-1【高】scope 默认从 builtin v1 section_hint 派生
- 锚点：`fundlex/guide_generation/scope.py:16-26`（fallback 硬编码 v1 篇目）；`pipeline.py:161`（`config.guide_scope_sections or load_builtin_guide_scope()`，贯穿 discovery/authoring/coverage/residual 四阶段）；`coverage.py:294/333/390`（范围外章节静默 out_of_scope 移出覆盖分母）。
- 断法：新指引篇目之外的要求/影响全链路静默不算缺口 → 静默漏法。
- 修法：scope 变为 run 创建时必填声明（`service.py:49/97-107` 的 `guide_scope_sections` 是唯一松绑口，提升为正式引导参数）。
### E-2【高】disposition 推断词表 = v1 分界词
- 锚点：`requirements.py:44-50`（直销服务平台/客户维护费/销售费用信息披露/基金销售协议 OUT_OF_SCOPE 正则）；33-34/615-624（`_CONTRACT_FEE_TERMS` 豁免施行条款）；178-181/253-281（`_FEE_CONTRACT_TOPIC`、域标签恒 "费用条款"、"前端/后端收费方式" 注入）。
### E-3【高】authoring/quality/repair 三处的直销守卫句型注入
- 锚点：`authoring.py:32-42/85`（直销禁止收费四正则 + 兜底直引 v1 法条原文 "不得收取认（申）购费、销售服务费。"）；96-106（条件/例外/适用性三句 v1 渠道分界措辞）；`quality.py:33-42/139-152`（质量门内置直销×份额渠道边界 critical 判定）；`repair.py:97-111`（修复无条件重套直销守卫）。
- 断法：新主题下正则误命中即把销售费用新规条文注入候选文案。
- 修法：守卫改为法规 profile 插件，默认关闭。
### E-4【高】engine_compat 兼容词表 = v1 词表，且只标注不阻断
- 锚点：`engine_compat.py:19-28`（supported/unsupported 两词表全为份额类别/A类/C类/销售服务费/浮动管理费/直销…）；50-52/61（DSL 白名单 {append,replace,delete,noop} + v1 CONDITION_KINDS，缺口仅标注）。
- 断法：新指引条件大面积假 ENGINE_CAPABILITY_GAP（报告失真）；反向：不可执行指引可能经 human 路径进引擎后执行失败。
- 修法：判定从引擎 DSL 能力清单单源导出；eligibility 增"DSL 可表达率"硬门。
### E-5【高】prompt 硬编码费率档示例
- 锚点：`prompts.py:341-344`（LOCAL_CANDIDATE_INSTRUCTION "0.4% stock/mixed、0.2% index/bond、0.15% money market"）。
### E-6【高】lexical 域词表与篇目别名 = v1
- 锚点：`lexical.py:26-36/137`（DOMAIN_TERMS ~60 词全销售费用域，权重 0.35 vs 2.0）；38-46（SECTION_HINTS 对齐 v1 篇目）。
- 断法：新主题召回排序失真。
#### 中风险（E-7~E-16）
- E-7 `discovery.py:46-49` DIMENSION_TERMS v1 词表死代码（误导）；62/480-483 + prompts.py:225（sweep 窗口 8/12、max_requirements=12 与 schema maxItems 耦合，按 v1 调优）。
- E-8 `coverage.py:187/247/558/588/104-145` 批大小 6/3/16/40 与 `_audit_context` 24000 字上限按 v1 规模写死（代码注释自承曾隐藏 31/90 条 → 假缺口）。
- E-9 `prompts.py:86` + `requirements.py:82/426/521`（每批 maxItems 18 / 1500 字批联动）。
- E-10 `prompts.py:61-70` applicable_scope schema 固定 fund_types/channels/share_classes/investor_types。
- E-11 `prompts.py:439-441/665` 放行/修复示例引用 A/C/D 份额与费率下限（先验偏置）。
- E-12 `quality.py:117-126/236-258` 下限保护只认 "不低于 X%" 百分比句型；285-286 severity 降级 scope_markers 写死 a/b/c/d/货币市场。
- E-13 `scope.py:43-56` `normalise_section` 子串匹配，且与引擎 parser 六篇目措辞不一致（"基金的收益与分配/基金财产的清算" vs "基金的收益与分配/基金财产清算"）→ 新篇目误/漏匹配。
- E-14 `pipeline.py:83-87` + `service.py:40-43` 轮数默认 2、上界 10/20（大指引可能不足）。
- E-15 `residual.py:34-39/117-119/198-205` 负样本 8、30k 截断按 v1 语料调。
- E-16 `guide_store.py:28-29`（引擎）与生成侧未联通：「生成→选装发布→注册策略」release 协议缺一环，registry `register_guide_operations` 需 publisher 显式 specs（无集成验证）。
#### 低风险/正面结论（E-17~E-20）
- E-17 `authoring.py:503` `guide_item_id="G-"+hash` 与引擎 Gnn 易混淆（换前缀）。
- E-18 schema_version 字符串五处独立写死（export.py:127/human.py:140/pipeline.py:983/engine_compat.py:116/service.py:174/pipeline.py:1165）→ 收敛 models.py 常量。
- E-19 `corpus_segmenter.py:30-39/248` 章条号正则是基金合同通用格式（合同域不变则不断）；`benchmark.py` gold 需 per-regulation 另备（by design）。
- E-20 正面结论：store.py/eligibility.py/vector.py/model_router.py/api.py/worker.py/human.py/corpus_catalog.py 无 v1 形态依赖。

---

## 汇总：五大静默路径（新指引接入时不报错但全错）

1. 未知 condition kind 静默 FALSE（recall.py:5996-6012 fallthrough）。
2. `_FEE_SCOPE_RULES` 单叶兜底只服务 G15-G17（recall_pipeline.py:994-1036）。
3. `_RULE_TOPIC_TOKENS` 对未知 id fail-open（recall.py:5870-5889）。
4. `_delete_keyword_bag` 费用词袋给**所有** delete 规则召回（recall.py:5462-5481）。
5. 合成补召 pass（G05 克隆/G08V/G22 ordered list/class-noop）只对本指引规则存在（recall.py:3121/9626/9686；pipeline:4635-4662）。

## 统一修法方向（建议级，未实施）

把散弹收拢为 **guide 文档 sidecar 元数据**（per-guide、随认证哈希绑定）：topic_tokens、site/append 锚、易混词对、condition kind 注册表+fact 绑定、slot→fact 映射、synthetic-target 补召策略、策略/tier 表、豁免/移交关系；引擎只保留通用机制，未知 kind/rule **一律显式抛错**，消灭 fallthrough False/UNKNOWN 与 `_UNKNOWN_SPEC` 安全侧默认。生成侧引入"法规 profile"（主题词表+scope 章节+守卫插件开关）。与 FL-D538 §11 的 sidecar 建议一致，FL-D439 为其根源。

---

## 附录 1：报主线派号清单（占位编号 EN5-xx，待派 FL-D）

> 既有记录已覆盖者不重复申请：FL-D439（G 编号策略绑架）、FL-D538（配置化缺口）、FL-D131（红粗体无语义）。

| 占位号 | 主题 | 等级 |
|---|---|---|
| EN5-01 | rule_id G\d{2} 顺序发号硬校验 + 新指引 id 与内置命名空间撞号风险（guide.py:275-288 → rule_scope/targeting/generation/edit_summary 全链错位解释） | 高 |
| EN5-02 | condition kind 封闭集 + 未知 kind fallthrough 静默 FALSE/UNKNOWN（guide.py:37；recall.py:5985-6057；obligations.py:219-223） | 高 |
| EN5-03 | 引擎忽略 guide schema 已有字段 slot_tokens，槽实例化只认字面 A/C 类（recall.py:5612-5668；pipeline:1984-1989） | 高 |
| EN5-04 | generation registry/effects/components 按位置 G 号绑 v1 策略与条数（与 FL-D439 互补的操作级证据：registry.py:143-176、effects.py 全表） | 高（并入 FL-D439 或立新条目） |
| EN5-05 | recall 五大静默路径（fallthrough FALSE、_FEE_SCOPE_RULES 单叶、topic tokens fail-open、delete 词袋泛用、合成补召无入口） | 高 |
| EN5-06 | `_PARSE_INSTRUCTION` 内嵌 v1 业务语义与 "The 15-group human reading of this guide" 字样（guide.py:388-417、426-439） | 中 |
| EN5-07 | 认证链路无在线 findings disposition 通道，新指引 approve 只能离线（guide.py:932-950；guide_store.py:262-269；jobs.py:419-426 三重门） | 中 |
| EN5-08 | guide_generation scope 默认派生自 builtin v1，范围外静默 out_of_scope（scope.py/pipeline.py:161/coverage.py） | 高 |
| EN5-09 | guide_generation 直销守卫/质量门硬编码 v1 句型并可向任意主题注入 v1 法条（authoring.py:32-106；quality.py:33-152；repair.py:97-111） | 高 |
| EN5-10 | engine_compat 兼容判定用 v1 词表且只标注不阻断（engine_compat.py:19-61） | 高 |
| EN5-11 | 生成侧→引擎「选装发布→注册策略」协议缺环，无集成验证（guide_store.py:28-29；registry.register_guide_operations；guide_generation/service.py） | 中 |
| EN5-12 | 通用 prompt/评估混入 v1 主题词（applicability.py:26-51；recall_prompts.py:26/296-358；prompts.py:341-344/439-665） | 中 |
| EN5-13 | schema 上限阈值按 v1 体量写死（guide.py:477-492 groups≤40 等；guide_generation 批大小/截断多处） | 低 |
| EN5-14 | 退休引擎（rules.py/rules_v2.py/v2*.py）常驻且含 v1 词表，存在离线误启用面 | 低 |
| EN5-15 | rule_scope._KNOWN_TITLES/族派发、targeting 锚表依赖内置篇目与文本锚，新主题退 _resolve_default 失 leaf 精度（rule_scope.py:101-305/683-948/1139-1156；targeting.py:236-511） | 高 |

## 附录 2：任务要求逐项自检断言表（双保险 A）

| 序号 | 任务要求 | 结果 | 证据 |
|---|---|---|---|
| 1 | 入口=fundlex 引擎包规则执行与解析消费侧+fundlex/guide.py+guide_generation/ | ✅ | A/B/C/D/E 五段全覆盖；消费面确认清单见 D 正面结论 |
| 2 | 从 builtin_guide_v1.json schema 反查消费点 | ✅ | 开工先 dump schema（groups/operations/validation/certification 全字段），再按字段/值域反查 grep |
| 3 | 覆盖硬编码句型 | ✅ | C-2/C-16/C-17/C-18/C-19/C-20、D-2、E-3、E-5 |
| 4 | 覆盖编号结构假设 | ✅ | A-1、B-5、D-1、C-31、E-17 |
| 5 | 覆盖阈值 | ✅ | A-5/A-6、E-8、E-9、E-13、C-32；registry counts 170-176 |
| 6 | 覆盖「15-group」类语境 | ✅ | guide.py:415（A-4，字面 "15-group"）+ 解析先验偏置 E-14 轮数类 |
| 7 | 覆盖 G 族编号假设 | ✅ | A-1、B-1、C-1~C-21、D-1~D-5 主灾区全列 |
| 8 | 每条含 文件：行锚/假设/断法/修法/风险级 | ✅ | A/B 段精确行号；C/D/E 段含子 agent 复核过的行锚 |
| 9 | 只审查+提案，不动业务代码 | ✅ | 仅新增本文档 + /tmp 状态文件；`git status` 业务代码零改动 |
| 10 | 30 分钟可见产出 | ✅ | 开工后先写状态文件断点，再持续增量写报告 |
| 11 | 状态文件 qa-engine-b4.md 维护 | ✅ | /tmp/opencode/qa/status/qa-engine-b4.md 持续更新 |
| 12 | 新发现报主线派号 | ✅ | 附录 1，EN5-01~15（已知 FL-D439/538/131 不重复申请） |
| 13 | 真实模型账本 | ✅ | 本任务纯静态审查，真实模型调用 0 次、token 0、费用 $0（FL-D445 口径，无上限但无需调用） |
| 14 | 双保险 A：证据+逐条 ✅/❌ 断言表 | ✅ | 本表 |
| 15 | 双保险 B：自建子 agent 双盲质检 | ⏳ | 质检进行中，结论附本报告附录 3 |
| 16 | 服务自测（uvicorn+sqlite+dev auth+playwright） | ✅不适用 | 本次为只读审查零代码变更，无运行面变化；不走 live 自测（如需可后补） |

## 附录 3：双盲质检记录（双保险 B）

- 质检员：独立子 agent（session ses_e658c36e5ffeov4g5FqiupvU3m），盲审（未先读报告结论，直接核锚点）。
- 方法：抽 20 个关键锚点逐一回源核验 + 任选 3 个范围外文件（v2.py、rules.py、docx.py）独立抽查漏项。
- 结果：**命中 17 / 偏差 3 / 不存在 0**。
  - 偏差 1（已修）：A-3 原写"GUIDE_DOMAINS 六项"，实际 **8 项**，且与解析指令 6 项、scope.py 6 项三处措辞两两不一致——已重写 A-3 并交叉 E-13。
  - 偏差 2（已修）：C-14 原写"slot_tokens 无任何消费"，实际 recall.py:7440/7455/7844 有 3 处旁路消费（证据与 compose prompt），但实例化驱动仍是字面 A/C——已改为准确表述。
  - 偏差 3（已修）：C-18 行号区间——"少于7日"在 5036-5069，"1.5%" 首现 5146-5147，5191-5212 四联 token 两词俱在 5206-5210——已校准。
- 范围外新发现（已并入 D-14/D-19）：`v2.py:560-563` 费用词组锚、`v2.py:919-928` 直销句型（退休 v2 路径）；`rules.py` 一处（D-13 已覆盖概念，质检确认）；`docx.py:540-547` 章名白名单弱信号（仅注明）。
- 质检判定：原判"局部返工"；上述 3 处修正与 3 处补录完成后，质检员认定的全部可证伪错误已清零，**定稿**。
- 未改动任何业务代码；质检全程只读。
