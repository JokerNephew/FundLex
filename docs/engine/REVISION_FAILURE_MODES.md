# 修订流程失效模式总图（FL-D897）

> 上位框架：用户原话「合同修改还是会出现该修改但修改失败的地方……你可以在修改流程上进行大修，但不要针对某个规则去改，因为用户是会上传新指引文件的」。
> 本文是后续所有波次的**路线图**：把修订流程逐环节展开，列出每一环已实证出现过的「该改未改 / 改失败」失效模式、该模式已有的防呆机制、仍然存在的缺口。所有条目以集中问题记录 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 的 FL-D 编号为证据，不虚构。

**维护规则**：每波修复新增家族时，先查本图所属环节；新模式追加到对应环节，旧模式状态迁移（MATERIAL → CLOSED）必须带真实复验证据编号。本图与集中问题记录互相引用，但不可替代集中记录的单条登记义务。

---

## 0. 全流程一图

```
①解析            ②指引解析/义务识别      ③站点定位            ④前提适用性          ⑤缺席证明          ⑥生成             ⑦核验/交付门
DOCX inspect   guide JSON → records    scope + targeting +  facts → applicability  absent / satisfied plan/compose         Claim Replay
structure index  applicability 承载      recovery / 补扫     required_facts 门      -noop / 恒等完结    instantiate/merge   audit / worst-of
────────────   ───────────────────    ───────────────────  ───────────────────   ───────────────── ─────────────────   ─────────────
FM-01 保护边界   FM-05 标题适用性不机器化  FM-09 双 scope 分歧   FM-07 极性链不完备    FM-13 缺位无证     FM-16 余文丢失      FM-24 否决站点混入
FM-02 标题规约   FM-06 条件桩饿死       FM-10 先选一叶漏改     FM-08 空组无完结      FM-14 假站点       FM-17 重试黏错      FM-26 外层PASS
FM-03 跨段站点   ②' 指南重认证纪律      FM-11 scope 过界       ④' 业务适用档待定     FM-15 absent冒称   FM-18 首标签残留    FM-27 绕过scope
FM-04 短引文                          FM-12 摘要区排除                                              FM-19 自由compose   FM-28 历史双并
                                      ③' 探针过严/过宽                                              FM-20 schema无再试  FM-29 同址双计
                                                                                                  FM-21 恒等扣件      FM-30 判定摇摆
                                                                                                  FM-22 重叠未联划    FM-31 重盘毁证
                                                                                                  FM-23 replay判原文
```

**总防线（贯穿各环，已存在）**：缺证即拒（fail-closed UNKNOWN 永不静默升级）、Claim Replay CLOSED_REPLAY 必闭合、miss_classification 分类账、audit worst-of-sites、作用域 containment、受保护词检查、证书+sha 绑定（指引/评测/发布三级）、诚实 incomplete（hold 优于错交）。

**总破口（本图消灭目标）**：某类义务的「完结代数」缺成员——edited / already-satisfied / absent-certified / satisfied-noop / N/A-by-applicability / honest-hold 六态里缺一个，该类合同就**系统性**扣件。holder 不是缺陷，缺通道才是。

---

## 1. 失效模式分类账（FM-xx 编号稳定，新家族追加）

| 编号 | 失效模式 | 环节 | 首证 | 状态 |
|---|---|---|---|---|
| FM-01 | 受保护文档解析拒入（边界案） | ① | FL-D865（BH06） | CLOSED（边界隔离，不侵分母） |
| FM-02 | 标题规约假设：非范式小节标题无法解析 scope | ①③ | FL-D432（QDII「3、C类…」）、FL-D365 | 部分CLOSED（物理边界修复）/ LOF 形态见 FM-09 |
| FM-03 | 跨段引文/复合站点/ONE_OF 变体绑定失败 | ①③ | FL-D340（D01/D04） | CLOSED |
| FM-04 | 类别替换 survey 短引文无法绑定完整物理站点 | ①⑥ | FL-D345 | CLOSED |
| FM-05 | **指引适用性只写在标题**：operation condition=none，不适配合同跑全套义务 | ② | FL-D863（BH04 八连饿死） | CLOSED（条件词表机器化承载+重认证） |
| FM-06 | **条件桩饿死**：中性 facts 桩使全部条件化规则 UNKNOWN，恢复通路静默失效 | ②④ | FL-D863 后续（summary_copy_targets stub） | CLOSED（生产两通路接真实 facts） |
| FM-07 | **极性链不完备**：无字母归属句/豁免句式/零绑定证明缺环 → 前提 UNKNOWN 连发 | ④ | FL-D862（BH07 22 连发） | CLOSED（三补环+抽取开工闸） |
| FM-08 | **空组无完结通道**：组级缺位已证但绑定操作无 satisfied-noop 归宿 | ⑤ | FL-D869（BH07 二阶残余 4 holds） | **CLOSED**（ad70cd6+877383b；BH07-v3 实跑 complete：empty_group_noop×2） |
| FM-09 | **双 scope 分歧**：门/probe 独立标题扫描 ≠ 调用方已解析 RuleScope，形态差异即饿死 | ③ | FL-D866（BH05 LOF g06_subsection_scope_missing） | CLOSED（回退调用方边界，绝不全域） |
| FM-10 | scope 先选一个叶子漏改正文同类条款；误写摘要 | ③ | FL-D439（景宁 p155） | CLOSED |
| FM-11 | scope 过界：扩展到释义区与兄弟规则同段 overlap；修复目标不查 scope | ③ | FL-D412（G04/G02）、FL-D413 | CLOSED |
| FM-12 | 摘要区/副本排除：摘要中的义务站点不进 scope 或被 residual 加回 | ③⑦ | FL-D509、FL-D435、FL-D384/434/443 | CLOSED（真副本建目标通道） |
| FM-13 | **缺席无证书**：义务指向对象本就不存在，但无 scoped absence 证明通道 → 永 OPEN | ⑤ | FL-D488（G06/G13/G17 三连）、FL-D494（G05） | CLOSED（absent_delete_coverage + replace_noop） |
| FM-14 | 合成 ABSENT 目标被 replay 当真实物理站点判 MISSING_EFFECT | ⑤⑦ | FL-D507、FL-D493 | CLOSED |
| FM-15 | absent 判定冒称覆盖以压制确定性目标 | ⑤ | FL-D392（恒裕 G17 p888） | CLOSED（反证闸） |
| FM-16 | 片段级替换/删除路由到自由 compose，余文丢失 | ⑥ | FL-D045 | CLOSED（片段操作禁 compose） |
| FM-17 | compose 重试沿用首次错误结果 | ⑥ | FL-D442 | CLOSED |
| FM-18 | 协调类别组只替换首标签，残留「或E类基金份额」 | ⑥ | FL-D498 | CLOSED |
| FM-19 | 自由 compose 遗漏实际类别/触发受保护词检查失败 | ⑥ | FL-D499（G18 E类） | CLOSED（受保护词门） |
| FM-20 | compose MODEL_SCHEMA_INVALID 连续 → 计划级 unresolved，无业务级再试 | ⑥ | FL-D793/794（B15 G11 双连） | OPEN（观察项，业务级重试待裁决） |
| FM-21 | **恒等替换被当活**：实例化结果与现文一致仍计划编辑/永久扣件 | ⑥ | FL-D699（B05 G02）、FL-D697 同根 | CLOSED（恒等⇒satisfied-noop） |
| FM-22 | 传递重叠编辑未按连通分量联合规划 | ⑥ | FL-D309 | CLOSED |
| FM-23 | replay 用原文判断产物、占位污染站点、sibling 借站点 | ⑥⑦ | FL-D310 | CLOSED |
| FM-24 | 计划阶段已否决的站点主张混入 Replay 闭合必需集，worst-of-sites 翻 OPEN | ⑦ | FL-D696（B12 G16 三站点） | CLOSED |
| FM-25 | SemanticApproval 可搬用到其他物理站点 | ⑦ | FL-D457 | CLOSED |
| FM-26 | 语义审计只改外层 PASS，站点仍 FAIL → 合法已满足无法完成 | ⑦ | FL-D458 | CLOSED |
| FM-27 | Claim Replay/delete residual 绕过 RuleScope 把摘要副本加回必改站点 | ⑦ | FL-D435 | CLOSED |
| FM-28 | 相邻 ONE_OF 历史措辞同时合并，p230 重复整句 | ⑥⑦ | FL-D436（G12） | CLOSED |
| FM-29 | 同址 satisfied 双计伪造 occurrence 歧义 | ⑦ | FL-D698（B12 G05:2@p162） | CLOSED |
| FM-30 | 单轮 inventory absent 判定摇摆把可执行义务变全案无产物 | ⑤⑦ | FL-D695（B15 G09@p159） | CLOSED（变体证据反证闸） |
| FM-31 | 业务轮重盘整体替换冲掉反证+已执行目标 | ⑤ | FL-D695 loop-6 残余 | CLOSED（重盘后反证闸二次挂点） |
| FM-32 | **纯枚举句缺位无证书**：类别句为枚举形态（非费制分组原型句），替换会造损坏文本，无任何完结通道 | ⑤⑥ | FL-D869（BH07 二阶） | **CLOSED**（enumerated_absence 证书；BH07-v3 实跑 complete；费义素句在场仍 fail-closed，消费端 mutation 在案） |
| FM-33 | 合成遗漏：义务站点从未入计划（p244 合成遗漏） | ③ | FL-D791/696 loop-5（B12 G12+G13） | CLOSED |
| FM-34 | append 被 approval 绕过结构站点，在无关段落重复插入 | ⑥⑦ | FL-D510 | CLOSED |
| FM-35 | P6 评分器把缺失义务/残留删除句判为完成（评测侧假绿） | ⑦评 | FL-D450 | CLOSED（评分口径修正） |
| FM-36 | 语义探针过严排除单向外转句 / 过宽收录非目标句 | ③ | FL-D373、FL-D504、FL-D511 | CLOSED（探针双向收口+scope 内守） |

CLOSED = 有真实复验证据收口；MATERIAL = 仅作证机制存在；OPEN = 缺口未闭。

---

## 2. 逐环节失效模式与防呆

### ① 解析（DOCX inspect / structure index）

**失效模式**
- FM-01 受保护文档：inspect 阶段拒入，整案 0 目标。属**边界隔离**而非缺陷——标签 0 目标不侵分母（留出 BH06 口径已定）。
- FM-02 标题规约：scope 解析假设范式小节标题；QDII「3、C类基金份额的销售服务费」编号形态解析失败（FL-D432）。
- FM-03 物理站点形态：跨段引文、ONE_OF 变体、复合站点（FL-D340 三形态同波暴露）。
- FM-04 短引文：类别替换 survey 的短引文绑不到完整物理段落（FL-D345）。

**已有防呆**：保护文档 fail-closed 拒入+边界口径；物理小节边界修复（FL-D365）；复合站点 composite 表达；短引文绑定扩张。

**缺口**：模板多样性（短版式合同如 BH04 纯债）的解析覆盖仍随新模板暴露；语料 500+ 剖析（主线在做）将量化覆盖面。

### ② 指引解析与义务识别（guide JSON → obligation records）

**失效模式**
- FM-05 **标题适用性不机器化**（最重缺口，已修）：指引作者把「多类别时适用 / 有销售服务费时适用」只写在标题，operation condition=none。单类无服务费合同 8 条不适用义务杀入 scope/replay 双双饿死 → 全案扣件（BH04）。**修法是通用的**：用指引自带条件词表（class_count / has_service_fee，G05/G08/G11/G19/G22 先例）补全 G01-G04/G15-G18，按 FL-D572 先例重认证。对任何新指引成立的前提是**指引通道本身保留条件词表**——这是指引 schema 的硬约束，不是本合同特判。
- FM-06 **条件桩饿死**（修复级联暴露）：`summary_copy_targets` 用中性 facts 桩探测候选，13+ 条条件化规则在 UNKNOWN 下被 `condition_status != "TRUE"` 静默饿死——**恢复通路在结构正确时也不产目标**。教训：凡以 facts 探测条件的代码通路，生产路径必须接真实 facts，桩只能出现在注明「结构锚与事实无关」且经条件化规则清单审计的测试旁。
- ②' 指引重认证纪律：改动 guide JSON 必须重算 document_sha256、重指 certification/dispositions 摘要——validation.findings 内的 guide_document_sha256 属 finding 载荷，**禁止改**（改动破坏 finding_id → finding_uncertified 连发）。本轮已实证此坑。

**已有防呆**：operation 编译计数校验（34 不变）、validate_runtime_guide GUIDE_NOT_CERTIFIED 拒载、certification sha 绑定。

**缺口**：用户新指引上传后，条件词表的覆盖率校验尚无门禁——「标题注适用条件但 operation 未承载」在未来指引上**可复发**。建议后续波次增加指引质量门：标题含条件词而 condition=none 的操作发 warning（登记，不阻断）。

### ③ 站点定位（scope / targeting / recovery）

**失效模式**
- FM-09 **双 scope 分歧**（本轮新证）：G06 门用自己的标题扫描，与调用方已解析的 RuleScope 互不知晓；LOF 合同无精确小节标题 → `g06_subsection_scope_missing` 饿死（BH05）。**原则：同一义务的作用域只能解析一次并由单一来源分发**；次级通路回退调用方边界，绝不独立全域扫描。
- FM-10 先选一叶子漏改同类条款；误把正文当摘要写（FL-D439）。
- FM-11 scope 过界：扩展到释义区与兄弟规则同段 → RECALL_EDIT_OVERLAP（FL-D412）；claim-site 修复目标不查规则 scope 在兄弟段落重建目标（FL-D413）。
- FM-12 摘要区排除双相：摘要副本不进 scope（FL-D509）；residual 把摘要副本加回（FL-D435）。修法：真副本经结构锚（summary_of/copy_key）建目标通道（FL-D384/434/443），不逐字不抛光。
- FM-33 合成遗漏：义务站点从未入计划（B12 p244）。
- FM-36 探针双向错位：单向外转句被误排除（FL-D373）/ 非目标句被收录 / scope 外禁令漏删（FL-D511）。

**已有防呆**：RuleScope resolution 显式化（resolved/…）、scope.contains 门禁、absent 探针全限 scope 内、恢复通路归因（target_attribution 记 origin）。

**缺口**：scope 解析对「非范式标题模板」的覆盖 vs 防呆闸的张力仍未量化——500+ 语料剖析的形态清单将决定是否需要通用标题正则层。

### ④ 前提适用性（facts → applicability）

**失效模式**
- FM-07 **极性链不完备**（本轮三补环）：(a) 无字母默认费句「申购费用由投资人承担」此前不证类级极性——修法收窄为**归属句式**（费用由…承担），裁量句「费率由…决定」明确不证（test_fee_fact_evidence 双守护用例是不可破闸门）；(b) 豁免句式「可以豁免Y类…申购费用」以默认费存在为前提证正极性；(c) 多类零绑定扫描证空销服组，但**仅当每个 current 类已解析出申购极性**（抽取确已开工）才升级——静默合同保持 UNKNOWN。
- FM-08 **空组无完结通道**：见 ⑤。
- ④' 业务适用档：QDII/FOF/指数/养老目标合同的规则适用档与验收分母（FL-D398/399）——**业务裁决项**，引擎只负责暴露分母口径。

**已有防呆**：required_facts 门（apply_facts UNKNOWN 拒 TRUE）、applicability status 显式（TRUE/N/A）、fee guard 双用例、事实组 VERIFIED 才可实例化（FL-D864 证书门槛）。

**缺口**：空组完结（FM-08/32）实施后，「组级缺位证明」需固化为通用代数成员（任意多类指引规则可复用，不只费制）。

### ⑤ 缺席证明（absence / satisfied-noop 完结代数）

**失效模式**
- FM-13 缺席无证书（历史最大面积 FAIL 源）：B 系三波大面积「原文不存在」未闭环（FL-D488）；G05 replace scope 内旧文缺失仍不闭（FL-D494）。已建 `absent_delete_coverage`：delete 类 probe_backed（G05/G06/G13/G17）+ replace_noop（G05/G14/G02/G04/G18），scope 内扫描、变体与 review 候选阻断、任何存活措辞阻断证书。
- FM-14 合成目标被当真实站点（FL-D507）；清算标题被当 absent 业务站点产孤儿证据（FL-D493）。
- FM-15 absent 判定冒称 operation 覆盖压制确定性目标（FL-D392 G17@p888）→ 变体证据反证闸。
- FM-30 判定摇摆：单轮 absent/needs_edit 翻转把可执行义务变全案无产物（FL-D695）。
- FM-31 重盘毁证：业务轮重盘整体替换冲掉反证+已执行目标 → 反证闸二次挂点（重盘后重放）。
- FM-32 **纯枚举句缺位无证书**（OPEN）：BH07 类别句「分为A类基金份额和Y类基金份额」是纯枚举形态，非费制分组原型句；G02:1/G04:1 按原型句假设替换会造「分为A类、Y类基金份额和Y类基金份额」损坏文本——计划面 fail-closed 正确地拒了，但**代数里没有它的完结项**。已定设计：scope 内无费制分组原型句 ⇒ 缺位证书（枚举句不阻断已枚举目标的完结；真原型句存活则 fail-closed 不证）。配合 FM-08 空组绑定 satisfied-noop（instantiate_slots SERVICE_GROUP_EMPTY ⇒ satisfied-noop，复用 FL-D699/FL-D090 `_drop_empty_group_operations`/`_append_without_missing_group` 哲学）。两机制对任意多类指引成立。

**已有防呆**：证书门槛（VERIFIED 事实组、实例化 old_text 一并搜索、scope 内存活提及阻断——FL-D864 G18 三件套）；判定性质必须明示（ALREADY_SATISFIED vs N/A，FL-D052/FL-D106 先例）。

### ⑥ 生成（plan / instantiate / compose / merge）

**失效模式**
- FM-16 片段级操作路由到自由 compose → 余文丢失（FL-D045）。规矩：片段替换/删除禁 compose。
- FM-17 重试黏错（FL-D442）。
- FM-18 协调组只替首标签（FL-D498）；协调列表已满足证明不识别「调低A和B」（FL-D395）。
- FM-19 自由 compose 遗类/触受保护词门（FL-D499）；local candidate yes 但无 new_text → 合并门禁中止整运行（FL-D380）。
- FM-20 MODEL_SCHEMA_INVALID 连续双连，无业务级再试（FL-D793/794，OPEN 观察项）。
- FM-21 **恒等扣件**：实例化恒等仍计划编辑（FL-D697 复合引用整段替换崩塌同根）；恒等⇒satisfied-noop（FL-D699，B05 收官，全波 390/390）。
- FM-22 传递重叠未联合规划（FL-D309）；FM-23 replay 判原文/占位污染/sibling 借站点（FL-D310）；FM-28 相邻 ONE_OF 历史双并（FL-D436）；FM-34 append 绕结构站点重复插入（FL-D510）。

**已有防呆**：compose 仅整句级、受保护词检查、merge 门禁、重叠连通分量、恒等坍缩。

**缺口**：compose 类错误唯一的归宿是诚实 incomplete，缺业务级限次重试（FL-D794 待裁决——注意与 FL-D445「有限技术重试」政策的边界）。

### ⑦ 核验与交付门（Claim Replay / audit / merge 核验 / 交付）

**失效模式**
- FM-24 已否决站点主张混入闭合必需集，worst-of-sites 把已完成义务翻 OPEN（FL-D696 B12 三站点）。
- FM-25 SemanticApproval 可搬站（FL-D457）；FM-26 外层 PASS 站点 FAIL（FL-D458）。
- FM-27 residual 绕 scope 加回（FL-D435）。
- FM-29 同址 satisfied 双计伪造 occurrence 歧义（FL-D698）。
- FM-35 评测侧假绿：评分器把缺失义务/残留删除句判完成（FL-D450）——**评测口径与引擎口径必须同源**，否则优化目标失真。
- ⑦' sweep 带源前缀的已满足句误判 SEMANTIC_UNCERTAIN（FL-D378）；site guard 判残留删除目标 out_of_scope 致旧支付句保留（FL-D486）；尾部旧句误判「新政策已存在」（FL-D492）。

**已有防呆**：miss_classification 分类账（CLOSED_REPLAY / MISS_*）、final_omission 复核、诚实 incomplete 交付门（hold 优于错交，FL-D501 网络错误亦不交付）。

**缺口**：交付门的 hold  taxonomy（FL-? 待统一）——「机制 hold vs 外部阻塞 hold vs 边界 hold」三分已在留出报告实践，引擎侧 enumeration 未固化。

---

## 3. 机制设计原则（大修后的架构红线）

1. **完结代数完备**：每类义务必须可归入 edited / already-satisfied / absent-certified / satisfied-noop / N/A-by-applicability / honest-hold 六态之一；缺态即系统性扣件，属引擎缺陷，不属个案。
2. **作用域单一来源**：同一义务的 scope 只解析一次、单一来源分发；次级通路回退调用方边界，禁独立全域扫描（FM-09）。
3. **条件必须机器化承载**：适用性写在散文/标题即不存在；指引 schema 的条件词表是硬约束（FM-05/06）。
4. **缺证即拒，证必有凭**：UNKNOWN 永不静默升级；证书门槛（VERIFIED 事实+实例化搜索+存活提及阻断）是标准三件套；判定性质（satisfied vs N/A）必须明示。
5. **恒等与空组是合法终态**，不是失败：instantiate 恒等⇒satisfied-noop、空组绑定⇒satisfied-noop（FM-21/08）。
6. **禁样本特判**：所有机制对任意新指引、任意模板形态成立；证据可以来自个案，修法必须一般化，dev/留出双复验防回摆。
7. **防呆缺口登记制**：每波新家族先入集中问题记录+本图，后谈优化；状态迁移必须带真实复验证据编号。

## 4. 已知缺口与路线图（按优先级）

| # | 缺口 | 编号 | 下一步 |
|---|---|---|---|
| R1 | BH07 二阶：空组绑定完结 + 枚举句缺位证书 | FL-D869（**CLOSED**） | ad70cd6 机制+5 mutation；v2 实跑暴露第三阶接线断裂（生产端产出 verdict、消费端 kind 白名单拒收）；877383b 接线修复+2 消费端测试；**BH07-v3 实跑 complete 0-hold 闭环**。教训已录：机制修复必须含『生产→消费』端到端 acceptance 测试，单边 mutation 会造全绿假象 |
| R2 | 指引质量门：标题含条件词而 condition=none 发 warning | FM-05 复发防呆 | 待主线裁决是否入 build_guide 通道 |
| R3 | compose 业务级限次重试 | FL-D794 | 待裁决（FL-D445 政策边界） |
| R4 | 非范式标题模板的 scope 覆盖量化 | FM-02/09 | 等 500+ 语料剖析矩阵，定通用标题正则层是否有必要 |
| R5 | 交付门 hold 三分 taxonomy 固化 | ⑦' | 留出报告实践已有，引擎侧待固化 |
| R6 | 语料交叉验证：本图各 FM 在 500+ 合同中的覆盖面 | 全部 | 主线剖析产物到位后回填本表「覆盖面」列；**语料里高频而本图未画的形态，一律追加新 FM 编号** |

*FL-D897 登记：本文件即大修框架交付物之一；FL-D866~869 为留出首验四家族的机制修复与残余登记（详见集中问题记录）。*

---

**FM-38 机制生产-消费接线断裂**（2026-11-01 补，BH07-v2 实跑暴露，FL-D869 第三阶）：修复机制在上游正确产出证据（离线探针可复现），但下游消费白名单/契约未同步接入 → 真实路径静默回落旧失败，单边 mutation 全绿。规则：凡新增证据 kind/状态/代码，必须同提交接入所有消费端白名单并配『生产→消费』acceptance 测试；真实复跑为最终验收，mutation 绿不作数。

## 5. 语料交叉验证回填（2026-11-01，主线 542 合同类型学剖析 CORPUS_TYPOLOGY_20261101.md，R6 收口）

| 总图条目 | 语料覆盖面（批外 514） | 结论 |
|---|---|---|
| FM-07（FL-D862 极性链，已修） | FOF 45（批外 41），且 FOF 服务费词次 3~45 分布宽、表述可在释义/费用表/正文三处 | 修复罩 41 份；**残余风险**：FOF 需向下穿透被投基金表述一层的形态未证（语料建议 1），留观察 |
| FM-05（FL-D863a 条件承载，已修） | 短版式低部件 16（批外 15） | 罩 15 份 |
| FM-09（FL-D863b 双 scope，已修） | LOF 12（批外 10），编号体系特殊 | 罩 10 份；语料建议子节匹配正则族参数化（（一）/1./一、/无编号），ETF 附加章节 149 份同族收益——并入 R4 |
| FM-13（FL-D864 缺位证书，已修） | QDII 15（批外 13）；单义务连坐为通用门语义放大器 | 罩 13 份 + 全语料防连坐 |
| FM-01（FL-D865 保护边界） | 全语料仅 2 份带 protection 标签；BH06 `enforcement="0"` | 边界极低频；引擎「在场即拒」疑似过宽（语料建议 6：enforcement=0 应视为未启用）——移交主线 FL-D865 条目 |
| **新候选 FM-37** | **无字母类 386 份（75%）** | 「不分类」合同的费率新规适用/改写形态波一几乎未测；适用义务密度远低于波一，**资格分流正确性**成主战场；【OPEN，候波次验证，勿当作已修】 |
| FL-D921（审计新证：字母示例写死 _EXAMPLE_GROUP_PATTERNS） | 非 A/C 字母 Y/E/F/B/D 批外 43 份 | 字母泛化映射层（类字母集合求交+全集为空退化路径）需求被语料实证；与 FL-D921 架构治理直接联动 |
| 评测分母（非 FM） | 批内 96% 多字母类 vs 批外 17%；578 物理=542 唯一（36 副本） | 第三波门槛口径必须按「适用密度×类型」分层，NOT_APPLICABLE 闭合计正确；selection 先 sha256/文件名去重 |

**路线图更新**：R4 量化=低部件 15+LOF 10+ETF 149（罩量 174）；新增 R7=FL-D921 指引元数据注入架构（EN1 审计实证 + 语料字母泛化 43 份佐证），R5 后移。布外最大不确定面：股票/货币/其他 38 份批内零覆盖 + ETF 149 份 + 无字母类 386 份 —— 第三波首验必须含这些形态的分层观察指标。
