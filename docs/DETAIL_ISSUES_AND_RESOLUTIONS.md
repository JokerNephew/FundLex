# FundLex 细节问题与处理记录

本文件是项目细节问题与处理方法的唯一集中记录，依据根目录 `AGENTS.md` 持续维护。创建于 2026-10-14。

本次补录来自原件阅读、用户讨论及三 agent 交叉审查。除明确说明外，下列处理方法属于设计结论或建议，尚未实施、评测或发布。记录不是问题已解决的证明，也不替代专题报告。

## 记录约定

- 稳定编号：`FL-D001` 起递增，不改号、不复用。
- 状态：待分析、待确认、待实现、待验证、阻塞、已解决。是否获用户确认单独写明。
- 条目字段：发现日期、问题与影响、证据、处理方法、状态与验证、下一步、变更记录。
- 同一问题更新原条目；重大结论变化注明日期和原因，不覆盖历史。
- 原件段落编号 `p` 为本次阅读提取器从0开始的序号，非Word页码、非应用内部地址。

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
- 状态与验证：**已实施并验证**。`grep -oP "^## FL-D\K[0-9]+" | sort | uniq -d` 输出为空（75 条编号全部唯一）；`grep -rn "FL-D068\|FL-D069"` 确认其余引用（TASK_PLAN/archive README/ACTIVE_HANDOFF）指向的正是保留原编号的那一层含义，故无需改动。**未 commit、未 push**。
- 复发（同日）：规范化提交轮次又新增一条占用 FL-D072 的条目（「工作区长期未提交、版本管理缺失」）→ 已按同一规则改号为 **FL-D078**，冲突清零。
- 下一步：后续新增条目必须先在全文搜 `^## FL-D` 确认编号未被占用；编号更正一律"保留旧条目 + 新增一行变更记录"，禁止原地重排。
- 变更记录：2026-10-15 新增。

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

## 后续条目模板

### FL-Dxxx 问题名称

- 发现日期：
- 问题与影响：
- 证据：
- 处理方法：尚无方法时写明待分析。
- 状态与验证：注明建议/已确认/已实施/已验证及具体范围。
- 下一步：
- 变更记录：
