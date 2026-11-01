# V2 前端三禁令/文案/布局只读审计（2026-11-01）

审计范围：`frontend/src/pages/**`、`frontend/src/components/**`（全部 28 个 tsx）。
审计口径：三禁令（删≠藏）、FL-D816 文案人话化、FL-D817 布局观察；「Secret 加密保存」类安全说明保留；结果页地图喂 FL-D818。
路径均以仓库根为基准；行号为当前 worktree 实际行号（多数 JSX 被压成单行，长行内多处问题共用一个行号时注明序号）。

---

## 表 1 · 三禁令·待删信息表

| 位置 (file:line) | 内容摘要 | 类别 | 建议(删/平铺) | 理由 |
|---|---|---|---|---|
| frontend/src/pages/Guides/index.tsx:330-331 | `<details><summary>查看人读详情`：规则 requirement + operations 正文被整体折叠，页面上规则只剩 rule_id + 标题 | 禁令③（藏信息）+ 造词 | **平铺**，把规则正文直接显示为表格第二行内容 | 用户点名双重违禁；规则内容正是用户来这页要看的东西 |
| frontend/src/pages/TaskDetail/index.tsx:100 | 8 阶段流水线（结构读取/事实理解/范围映射/目标盘点/规划/写入/复核/交付）+ 图例「已完成阶段/待处理阶段/当前处理服务：…」+ `<details>高级详情`（指引版本 version_id） | 禁令①③；内部引擎口径 | 8 阶段轨道删；「高级详情」整块删（或仅保留 phase 一行进度） | 用户只关心排队/处理中/完成/失败；阶段名是引擎内部术语 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:153 | `<summary>高级详情</summary>`：原件 SHA-256、指引版本 ID、report_json/evaluation 下载入口 | 禁令③；技术字段外露 | 删 SHA/版本 ID；**报告与评测文件下载入口平铺**到「交付文件」区 | 下载产物是用户核心动作，不能藏折叠；哈希属内部核验字段（留否主线裁决） |
| frontend/src/pages/Guides/index.tsx:294 | `<summary>高级详情</summary>`：版本 ID、基于版本 ID、规则哈希 sha256 | 禁令③；技术字段外露 | 删整块（或只留「基于上一版」人话） | 内部口径外露，用户读不懂 |
| frontend/src/pages/Guides/index.tsx:287 | needs_review 时 `<summary>高级详情</summary>` + JSON.stringify 原文 dump | 禁令③；原始 JSON | 删折叠；如必须保留，渲染成人话列表 | 直接把原始 JSON 扔给用户 |
| frontend/src/pages/Guides/index.tsx:351 | 解析问题：issues_detail 整块 JSON dump（`<pre>`，且默认 open=false 隐藏真问题，无问题时显示一句「没有记录解析问题。」反而可见） | 禁令③；原始 JSON | 删 JSON；有问题时列问题文本列表 | 同上 |
| frontend/src/pages/Guides/CompareCard.tsx:125-126 | 每条修改规则被收进 `<details>`（「规则X · N 个字段有变化」），old→new 对照藏在折叠里 | 禁令③ | 平铺字段对照 | 「规则差异」本来就是本区的主体内容，折叠=藏主体 |
| frontend/src/pages/Compare/ComparePage.tsx:449 | `<details class="compare-coverage-chip">覆盖不完整 · N 项未覆盖</summary>`，未覆盖清单与人工复核警示藏折叠 | 禁令③（藏风险提示） | 平铺为常驻警示条 | 安全/准确性提示不应默认收起（与「安全说明保留」同类） |
| frontend/src/pages/Settings/index.tsx:123-124 | `<details class="system-state"><summary>系统状态 · 运行参数（管理员）`：登录方式/处理引擎/交付模式/正式写入/单文件上限 | 禁令③；信息归属 | 平铺成普通卡片管理员可见（或归入用户管理页） | 折叠藏管理员参数；内容本身可留（主线裁决），形式违禁 |
| frontend/src/pages/TaskDetail/index.tsx:102（行内高级筛选 form） | 「高级筛选」按钮 + 处理/交付/上传三组 Select + 异常代码输入（placeholder 按提示关键词筛选） | 禁令③味/低频堆控件 | 主线裁决：简化为一个状态筛选或删除 | 与 Tab 行（处理中/资格通过/交付完成…）功能重叠 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:127 | 异常点内「诊断来源：规则义务核对/覆盖检查/人工复核提示/交付核验」（来源判断见 :68-73） | 内部口径外露 | 删该字段，只留 位置+原因+引文 | 「覆盖检查」「交付核验」是管线内部名词 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:184 | 「暂无独立证据引文。」meta-line | 解释性小字 | 删 | 空态占位废话 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:173 | 「处理所需的验证记录或模型额度暂不可用。」 | 内部原因外露 | 改为「处理暂时暂停，恢复后自动继续验证」（删技术归因） | 用户不需要知道模型额度/验证记录 |
| frontend/src/pages/TaskDetail/index.tsx:100（行内 StatusDimension） | 「上传」维度 detail 「任务调度状态」（:100 `current.pause_reason || '任务调度状态'`） | 占位废话 | 删 detail 或留空 | 无信息量小字 |
| frontend/src/pages/TaskDetail/index.tsx:94（行内 exportResults） | 导出 CSV 表头含「原始原因码」列 | 内部口径外露 | 删该列或改「原因」并映射人话 | 导出物面向用户 |
| frontend/src/pages/TaskDetail/index.tsx:101 | Card 说明「整包下载入口；单份合同的修改情况请在下方列表打开。」 | 解释性废话 | 删 | 按钮自明 |
| frontend/src/pages/TaskDetail/index.tsx:102 | 「点击合同名称查看修改情况与下载文件。」 | 解释性废话 | 删 | 链接自明 |
| frontend/src/pages/TaskDetail/TaskDetailIndexPage.tsx:12 | 「选择任务查看处理进度、合同交付与下载入口。」 | 解释性废话 | 删 | 与「任务」页重复简介 |
| frontend/src/pages/Tasks/index.tsx:60 | 页头「先处理暂停、失败和待交付任务，再查看已完成结果。」 | 说教 | 删 | 用户不是傻子 |
| frontend/src/pages/Tasks/index.tsx:47/66 | 「服务已连接」/「暂无统计」连接状态行 | 技术状态外露 | 删常态行；仅在读取失败时显示错误+重试 | 「服务已连接」对业务用户无意义 |
| frontend/src/pages/Tasks/index.tsx:62 | 「暂无处理统计——创建第一个任务后，这里会显示进行中、待处理与异常合同概况。」 | 解释性废话 | 删整段，空态直接不渲染统计区 | 解说什么会显示，而不是显示 |
| frontend/src/pages/Tasks/index.tsx:68 + TaskDetailIndexPage.tsx:15 | 列表「指引快照」列全部恒显「修改指引已锁定」 | 恒值列 | 删此列 | 每行同值 = 无信息；「锁定」还是内部口径 |
| frontend/src/pages/NewTask/index.tsx:195 | 副标题「上传合同后将按当前修改指引逐份检查并生成修订，可随时回到任务页查看进度。」 | 解释性废话 | 删或砍到 10 字内 | 流程解说 |
| frontend/src/pages/NewTask/index.tsx:196 | 「任务创建后会固定这个指引版本，补传不会切换任务指引。」 | 解释性小字 | 主线裁决（有一丁点实体信息：快照固定） | 可并入卡片一句「本任务将使用上面这个指引版本」 |
| frontend/src/pages/Guides/index.tsx:83 | 「管理自己的指引版本、启停规则组…任务会保存创建时的指引快照。」 | 目录句+机制解释 | 删 | 页头自我介绍 |
| frontend/src/pages/Guides/index.tsx:92 | 「新建任务默认使用这一版；运行中的任务不受后续切换影响。」 | 解释性小字 | 主线裁决 | 同上，属弱提示 |
| frontend/src/pages/Guides/index.tsx:109 | 「上传后的版本先解析；解析完成不代表已启用，请在列表里明确启用。」 | 解释性小字 | 删；状态字段本身已表达（已解析/已发布） | 流程解说重复出现两次（另见 :151） |
| frontend/src/pages/Guides/index.tsx:151 | 「支持与内置指引同结构的 DOCX。上传后会先解析；解析完成不代表已启用。」 | 解释性小字 | 留格式一句，删流程句 | 重复废话 |
| frontend/src/pages/Guides/index.tsx:225 | 「默认对比当前版本与上一版本；…全部在服务器本地计算，不调用模型。」 | 实现细节外露 | 前半句删；「本地计算不调模型」主线裁决 | 用户不关心调不调模型 |
| frontend/src/pages/Guides/index.tsx:301 | 「关闭的规则不会在之后新建的任务中执行，并会在报告里列为“用户关闭的规则”。至少保留一条启用规则。」 | 解释性小字 | 「至少保留一条」并入保存按钮 disabled 提示；其余删 | 与 :307-308 title 重复 |
| frontend/src/pages/Guides/CompareCard.tsx:102 | 「校验：干净→有遗留（发现 3→2）。」 | 自造词（干净/有遗留） | 删或改人话 | 完全读不懂 |
| frontend/src/pages/Guides/CompareCard.tsx:99-101 | 「分组变化：新增 X / 删除 Y / 顺序有变化；元信息变化 N 项（解析器版本、结构版本…）」 | 内部字段堆砌 | 只留「规则 12 → 15 条（+3）」级聚合 | 元信息字段名直接外抛 |
| frontend/src/pages/Settings/ModelSettings.tsx:93 | 「验证连接会向供应商发送一条简短请求，可能产生少量费用；不会发送合同内容。」 | 重复提示 | 删本文；:49 的 confirm 里已有全文 | 同一句话两处说 |
| frontend/src/pages/Settings/ModelSettings.tsx:73 | 「理解合同、定位条款并生成修改内容。」/「核验修改结果，检查错误和遗漏；可以使用不同的供应商和模型。」 | 职能解说 | 各砍到一句（「负责改合同的模型」/「负责复查的模型」） | 用户已知自己在配什么 |
| frontend/src/pages/Settings/ModelSettings.tsx:81 | 「建议名称并不保证账户可用，请向供应商确认。」 | 解释性小字 | 删 | 免责声明式废话 |
| frontend/src/pages/Settings/ModelSettings.tsx:82 | 「由供应商提供，仅其他兼容服务需要填写。」 | 解释性小字 | 删 | 字段见名字即懂 |
| frontend/src/pages/Settings/ModelSettings.tsx:84 | 「由管理员统一配置；需要自定义时选择「使用自己的模型」。」 | 教学 | 删 | 选择框就是答案 |
| frontend/src/pages/Settings/ModelSettings.tsx:183 | 「检查模型将改用与执行模型相同的供应商、模型与访问密钥，保存后立即生效于新建任务。」 | 重复确认 | 删；:150 confirm 已问 | 整卡只有一句话+一个按钮（见布局表） |
| frontend/src/pages/Settings/index.tsx:137 | 「扫码或在飞书与 FundLex 机器人私聊发送一次性绑定码；绑定只关联当前账号。」 | 操作说明 | 简化为「在飞书私聊里发送绑定码，仅绑定当前账号」（扫码走 :145 已有提示） | 与二维码提示重复 |
| frontend/src/pages/Settings/index.tsx:161 | 「账号管理与业务指引配置分开控制。」+「打开用户管理」按钮卡 | 解释+重复导航 | 整卡删（顶部 :119 已有「用户管理」按钮） | 重复入口 |
| frontend/src/pages/Users/index.tsx:72 | 「仅管理员可查看和管理账号状态。」 | 解释性废话 | 删 | 能看到此页的就是管理员 |
| frontend/src/pages/Review/ReviewPage.tsx:199 | 工具条文案「快捷键 A 接受 / R 拒绝 / ↑ ↓ 定位；选择版按每条修订的接受或拒绝结果生成，待处理项不会写入。」 | 混合说明 | 拆：快捷键提示可留（小字），后半句删，由生成按钮 disabled 提示承载 | 行为说明与快捷键混在一起 |
| frontend/src/pages/Compare/ComparePage.tsx:439 | 「按“原版 → 对比版”阅读两份 DOCX 的正文与普通表格差异，结果只代表已覆盖内容。」 | 教学+免责 | 删前半句；「结果只代表已覆盖内容」并入覆盖警示条 | 与 :443 方向卡重复 |
| frontend/src/pages/Compare/ComparePage.tsx:441 | 「多组任务会分别展示处理状态，失败或覆盖不完整的分组保留人工复核提示。」 | 解释性废话 | 删 | 状态列自明 |
| frontend/src/pages/Compare/ComparePage.tsx:442 | 「先选择原版（基准文本），再选择对比版（修订文本）。」+ PairInput 标签「原版（基准）」「对比版（修订）」（:127） | 重复教学 | 删说明句；输入标签保留 | 同一信息两处 |
| frontend/src/pages/Compare/ComparePage.tsx:232 | 「当前为移动端单文档视图；切换上方标签查看源文档。」 | 教学 | 删 | 移动端切换按钮自明 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:147 | 「文件会在处理服务完成并通过复核后开放；不完整结果请先查看下方异常点。」 | 指引导读 | 后半句主线裁决；「处理服务」改「处理完成」 | 「处理服务」「异常点」内部词 |
| frontend/src/components/layout/AppShell.tsx:133 | 帮助中心 5 步长文 ol | 大块解释文本 | 主线裁决：整体精简或删（页面改人话后大量内容将重复） | 帮助中心意义依赖用户不会在界面里迷路 |

**注**：Tasks/index.tsx:29 注释提到「全站唯一分页规格（FL-D806）句式与 V1 一致」，分页文案不在本审计建议修改范围（有既有规格约束）。

---

## 表 2 · 文案修改清单

| 位置 | 原文 | 建议新文（人话） | 理由 |
|---|---|---|---|
| frontend/src/pages/Guides/index.tsx:331 | 查看人读详情 | （删除，内容平铺；若必须保留标签）查看规则内容 | FL-D816 用户点名；「人读」自造词 |
| frontend/src/pages/Guides/index.tsx:127 | 冒烟复核提示：消费质量疑有下降，请查看详情 | 这版指引解析质量可疑，建议先查看再启用 | 「冒烟」「消费质量」内部词 |
| frontend/src/pages/Guides/index.tsx:286 | 冒烟复核提示：该版本消费质量疑有下降（不阻断启用，请人工确认）。 | 这版解析质量较前版下降，可启用但建议先人工确认 | 同上 |
| frontend/src/pages/Guides/index.tsx:127-128 | 解析质量未通过认证，不能启用 / 解析未完成或已失败（enableBlockReasonText :25-26） | 质量检查没过，暂时不能启用 / 还没解析完（或解析失败） | 认证书面腔 |
| frontend/src/pages/Guides/index.tsx:31 | 已通过认证 / 内置（免认证）/ 待解析认证 / 未通过认证 | 可用 / 内置默认 / 待解析 / 质量未通过 | 认证口径对用户无感 |
| frontend/src/pages/Guides/index.tsx:97, :130, :280 | 「规则组 X」「规则组」表头 | 「规则条数」表头→「规则」；值改「X 条」 | groups 实为计数，组名歧义 |
| frontend/src/pages/Guides/index.tsx:126 | {guide.issues} 个问题 | {guide.issues} 条解析问题 | 表意更准 |
| frontend/src/pages/TaskDetail/index.tsx:10-13 | phases 结构读取/事实理解/范围映射/目标盘点/规划/写入/复核/交付；「等待处理服务更新」 | 删或改：「处理中（进度第 N/8 步）」「等待开始」 | 引擎内部名词（主线裁决是否整删） |
| frontend/src/pages/TaskDetail/index.tsx:100 | 当前处理服务：{phaseLabel} | 删除（见表 1） | 同 left |
| frontend/src/pages/TaskDetail/index.tsx:44 | 处理未通过，详见报告 | 这份合同没处理成功，打开看详情 | 公文腔 |
| frontend/src/pages/TaskDetail/index.tsx:85? / DocumentRow :77 | 操作列按钮「修订」 | 逐条复核 | 「修订」动名混淆，入口实为 review 页 |
| frontend/src/pages/TaskDetail/index.tsx:63 | 工作文件（选择版） | 选择版（未完成，供人工继续） | 括号嵌套，先看懂再点 |
| frontend/src/pages/TaskDetail/index.tsx:66 | 最终版（含例外） | 最终版（有 X 处未改完） | 「例外」内部词 |
| frontend/src/pages/TaskDetail/index.tsx:68 | 工作文件（未完成） | 半成品（未改完，仅供参考） | 「工作文件」行话；felt to 主线裁决措辞 |
| frontend/src/pages/TaskDetail/index.tsx:151? → NewTask 关联 :204? — TaskDetail/index.tsx:101 | 补传未接收文件 | 补传没传成功的文件 | 口语化 |
| frontend/src/pages/TaskDetail/index.tsx:98 | 创建于 {date} · 修改指引已锁定 · 已关闭规则 N 条 | 创建于 {date} · 指引版本已固定 · 已跳过 N 条规则 | 「锁定/关闭规则」行话 |
| frontend/src/pages/TaskDetail/index.tsx:102（详情键列） | 表头「资格」 | 是否可处理 | 资格二字不解 |
| frontend/src/components/ui/StatusBadge.tsx:9 | eligible: 资格通过 / ineligible: 资格不通过 | 可以处理 / 不能直接处理 | 同上 |
| frontend/src/components/ui/StatusBadge.tsx:2-12 | completed_with_exceptions: 已完成（含异常）；complete_with_exceptions: 交付完成（含例外）；incomplete: 结果不完整 | 已完成（有待人工核对）；已完成（有未改完项）；没改完 | 「异常/例外」混用且不直观（已/未区分见主线裁决统一表） |
| frontend/src/components/ui/StatusBadge.tsx:4 | diagnosed: 诊断完成 | 只做了诊断，未改合同 | badge 需自带解释否则误导 |
| frontend/src/pages/Users/index.tsx:98 | StatusBadge '已接收'（accepted）用作账号状态 | 使用中 / 已停用 | 上传徽章复用到账号状态，语义错位 |
| frontend/src/pages/Tasks/index.tsx:67 | 已完成（含异常）/ 失败（含失败合同） | 已完成（有待核对）/ 失败 | 括号套括号 |
| frontend/src/pages/Tasks/index.tsx:23-24 | N 份合同需要关注未完成项。 | 还有 N 份没改完，要人工核一眼 | 人话 |
| frontend/src/pages/Tasks/index.tsx:20-21 | 处理失败，请打开任务查看原因。/ 任务已暂停，可从详情页恢复处理。 | 处理失败，点进去看哪份出了问题 / 已暂停，点进去恢复 | 同上 |
| frontend/src/pages/TaskDetail/TaskDetailIndexPage.tsx:15 | 指引快照列值「修改指引已锁定」 | 删列（见表 1）；若留改「已固定」 | 「快照/锁定」行话 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:41-48 | 工作文件（人工选择，未完成）/ 工作文件修订痕迹（人工选择，未完成）/ 评测修改版合同 / 评测修订痕迹 | 选择版（未完成）/ 选择版-带修订痕迹（未完成）/ 评测版（非正式）/ 评测版-带修订痕迹 | 拆词减少认知负担；「修订痕迹」可统一为「带修改标记」（主线裁决） |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:168 | 打开修订复核 | 逐条确认修改 | 动名词混杂 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:56-60 | 诊断完成→「只读诊断完成，仅提供报告，未交付修改后的合同」；evaluation→「评测结果，不能作为正式合同」 | 只生成了报告，没有改后的合同 / 这是评测产物，不是正式合同 | 去「只读」「交付」行话 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:91 | 表 dt「交付说明」「目标完成」「仍需核对」 | 说明 / 已改 N/M / 待人工核对 N | 栏目名一致口语 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:116-118 | 条款改动 · N 项；该目标没有逐段对照，处理结果见右上标记。 | 改了哪些条款 · N 处 / 这条没有前后对照，状态见标签 | 「目标」引擎词 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:117 | dt「目标原文」 | 合同原文 | 同上 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:127 | 异常点 · N 项 / 例外 {index + 1} | 待人工核对 · N 处 / 第 N 处 | 「异常点/例外」行话 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:184 | 暂无独立证据引文。 | 删（表 1）；若留：没有更多原文依据 | 同上 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:181-184 H2 | 业务依据 | 为什么判定可处理 | 「业务依据」律腔 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:153 | dt「原件 SHA-256」「指引版本」 | 原件指纹 / 使用的指引版本 | 若保留（主线裁决），至少不写 SHA |
| frontend/src/pages/Review/ReviewPage.tsx:140 | 还有 N 条修订处于“待处理”，请逐条决定或使用批量接受/拒绝。 | 还有 N 条没决定怎么办，接受或拒绝后再生成 | 「批量接受/拒绝」是按钮名，引用口语化 |
| frontend/src/pages/Review/ReviewPage.tsx:152 | 已生成选择版合同：接受 X 条，拒绝 Y 条。 | 已生成新合同：采用了 X 处修改，放弃 Y 处 | 「选择版」回合行话 |
| frontend/src/pages/Review/ReviewPage.tsx:157 | 选择版本已变化，已重新读取当前修订；请核对后再次生成。 | 修订内容更新过，已重新加载，请再看一眼再生成 | 口径软化 |
| frontend/src/pages/Review/ReviewPage.tsx:196 / RevisionPanel.tsx:43 | 生成选择版合同 / 修订清单 共 N 条 · 待处理 X · 接受 Y · 拒绝 Z | 生成确认后的合同 / 改动清单（X 待决定 · Y 要 · Z 不要） | 「待处理/接受/拒绝」偏工单 |
| frontend/src/components/review/RevisionCard.tsx:6 | 待处理 / 接受 / 拒绝 | 待定 / 要 / 不要（或 保持原样） | 人话；保持按钮短小 |
| frontend/src/components/review/RevisionCard.tsx:27 | 规则 {rule_id} | 指引第 X 条（若无更可读标题） | rule_id 外抛（主线裁决是否展示 id） |
| frontend/src/pages/Users/index.tsx:99 | 启用账号 / 停用账号 | 恢复登录 / 禁止登录 | 「停用账号」歧义 |
| frontend/src/pages/Users/index.tsx:84-86 | 成员 / 管理员 | 普通用户 / 管理员 | 成员行政腔 |
| frontend/src/pages/Settings/ModelSettings.tsx:169/174/169? → :169-174 | 执行模型 / 检查模型 | 修改合同的模型 / 复查修改的模型 | 用户点名「执行模型」生硬 |
| frontend/src/pages/Settings/ModelSettings.tsx:150,153,182 | 将执行模型配置复制给检查模型并保存？ | 复查用和修改一样的配置吗？ | 人机对话口吻 |
| frontend/src/pages/Settings/ModelSettings.tsx:140 | 配置已保存；保存不代表已验证连接，仅用于新建合同修改任务。 | 已保存；保存不等于连得上，点「验证连接」试一下 | 免责声明改写 |
| frontend/src/pages/Settings/ModelSettings.tsx:166 | 检测到旧保存设置，保存后切换到新配置。 | 这是旧版配置，再存一次就升级 | 「legacy」概念外露 |
| frontend/src/pages/Settings/index.tsx:127 | 召回优先修订引擎（recall_first） | 现行修订引擎 | 引擎代号外露 |
| frontend/src/pages/Settings/index.tsx:128-129 | 正式交付模式 / 评测模式；正式写入 已启用/当前不可用 | 模式：正式 / 评测；改名：可以产出正式合同 / 暂不能产出正式合同 | 语义不清 |
| frontend/src/pages/Compare/ComparePage.tsx:173-175, 197, 205-210 | 原文档 / 修订的文档 / 比较的文档 | 原合同 / 改后的合同 / 对照结果 | Word 教条腔 |
| frontend/src/pages/Compare/ComparePage.tsx:186 | 显示标记：所有标记 / 简单标记 / 最终状态 | 显示：全部修改痕迹 / 只标位置 / 最终样子 | 术语翻译 |
| frontend/src/pages/Compare/ComparePage.tsx:193 | 已覆盖范围内没有发现文字差异，无法确认全文无差异。 | 已比对的部分没发现不同，但没比对到的部分不敢说一样 | 官腔软化（safe to keep 属准确声明，措辞改） |
| frontend/src/pages/Compare/ComparePage.tsx:218, 226, :700s? — :124, :233 等 | 双栏对照 子文案「双栏联动阅读，拖动中间分隔线可调整宽度」 | 删后半句（自明） | 教学句 |
| frontend/src/pages/Compare/ComparePage.tsx:390 | 已按相对路径配对 X 组；Y 个文件未配对。 | 配成了 X 对，还有 Y 个文件配不上对 | 人话 |
| frontend/src/pages/Compare/ComparePage.tsx:402 | 第 N 组上传未完成。 | 第 N 对还没上传完 | 同上 |
| frontend/src/pages/Compare/ComparePage.tsx:407 | 上传中断：…已完成的文件已保留，可继续上传。 | 上传断了，传好的没丢，继续点上传就行 | 同上 |
| frontend/src/pages/NewTask/index.tsx:110 | 当前指引不可用，请先在指引配置中完成解析或启用。 | 还没可用的修改指引，先去「修改指引」页传一份或启用一份 | 内部词 |
| frontend/src/pages/NewTask/index.tsx:150 | N 个文件未接收。请修正后重新选择文件，再从此页补传。 | 有 N 个文件没传上去，改好文件名/内容后重新选 | 人话 |
| frontend/src/pages/NewTask/index.tsx:22-25 | 只支持 DOCX 文件。/ 空文件无法上传。/ 文件超过 X MB 限制。/ 同一批次中存在同名文件。 | 只收 DOCX / 这个文件是空的 / 这个文件超过 X MB / 这次选的文件里有重名的 | 逐项缩短 |
| frontend/src/pages/Guides/index.tsx:290-291 | 下载原始 DOCX / 下载规则 JSON | 下载指引原件 / 下载规则清单（JSON） | JSON 仅开发者懂，至少括注 |
| frontend/src/pages/Guides/index.tsx:349 | 解析结果未通过质量通道（确定性校验或独立验证有遗留），版本已标记为失败，不能启用。 | 解析质量没过关，这一版不能启用 | 「质量通道/确定性校验/遗留」内部三连 |
| frontend/src/pages/Guides/index.tsx:333 | 详细修改见条规条款。 | 详细修改以指引原文为准 | 错别字级口语错误（条规条款） |
| frontend/src/pages/Guides/index.tsx:25? — Guides/index.tsx:118 'GUIDE_NOT_PARSED' | （映射文案见上） | — | 同上 |
| frontend/src/pages/TaskDetail/index.tsx:151? → 见 DocumentRow :74 | 「等待接收」 | 还没传上来 | 口语 |
| frontend/src/pages/TaskDetail/index.tsx:151? → :94 CSV 表头 | 「资格」「业务提示」「原始原因码」 | 「可以处理」「说明」（删原始原因码列，见表 1） | 内部口径 |
| frontend/src/pages/Tasks/index.tsx:12 LoadingCard | 加载中（Spinner label） | （删除或不动声色） | 细枝末节，主线裁决 |
| frontend/src/pages/Auth/index.tsx:13 | 当前环境为开发身份模式，无需账号密码… | 本环境免登录 | 「开发身份」面向运维 |

---

## 表 3 · 布局观察清单

| 位置 | 问题 | 建议 | 理由 |
|---|---|---|---|
| frontend/src/pages/TaskDetail/index.tsx:97-102 | 页头状态行 + 「任务状态」卡（4 格 stats + 8 阶段轨道）+「结果与交付」卡（4 按钮 + 6 Tab）+「合同列表」卡（两排筛选 + 表），首屏三卡堆叠，Tab 与高级筛选、四格 stats 与表头状态重复表达同一状态 | 合并「结果与交付」对「合同列表」（按钮所剩无几）；状态卡只留一枚总badge + 一句进度；删阶段轨道 | 同一信息 3 处出现，卡片切分没有回答任何问题 |
| frontend/src/pages/TaskDetail/index.tsx:74-77 | DocumentRow 单元格：合同列内再压 muted 阶段行、状态列挂 form-error 行、「交付/目标」列塞 badge + 目标 x/y + 未完成提示 + incomplete 红字，行高约 120px 的密集堆字 | 每列只保留 badge + 一个主导词；数字进「待核对」列；错误归入 hover/详情页 | 用户点名「字密密麻麻堆在一起」的直接出处之一 |
| frontend/src/pages/TaskDetail/TaskDetailIndexPage.tsx:12-16 vs frontend/src/pages/Tasks/index.tsx:68 | 「任务」（TasksPage 列表）与 AppShell 导航「任务详情」（/tasks/detail 列出的还是任务列表）两张几乎同构的表 | 合并成一个任务列表页 | 导航嵌套关系错乱：详情入口却先是一张列表 |
| frontend/src/components/layout/AppShell.tsx:8-18 | 工作区分组同时列「任务总览/新建任务/任务详情」；前两是操作，第三个是列表跳转，概念不对齐 | 导航改：任务 / 新建任务 / 合同对比 | 同上 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:167-178 | 6 个全宽 Card 顺序纵列：概览(6字段dl)→交付文件(下载按钮列)→条款改动(N 个全 folded details 原文引用块)→(偶发验证中断卡)→异常点(N 个 folded details)→业务依据→高级详情，全页无锚点/无分栏 | 首屏：状态一句 + 下载按钮组 + 「改了什么 / 待核对」两列分区；条款对照与原文证据降权（点开才看） | 即用户点名重构对象；四个核心问题要靠滚动+逐条展开才能回答，见表 4 |
| frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx:116-118 | 条款改动每条 `<details>`：摘要行只有标题+badge，全部原始引用段落（blockquote）+「修改前/修改后」双栏全文随条款数线性铺开 | 摘要行内展示「条款名 + 一句改了什么 + badge」；前后对照全部进展开区 | 现状默认全收起=用户改的内容不可见；全展开又爆屏 |
| frontend/src/pages/Review/ReviewPage.tsx:196-208 + frontend/src/components/review/RevisionPanel.tsx:44-50 | 头部动作条 + 工具条（快捷键说明）+ 面板头含「上一条/下一条/全部接受/全部拒绝/全部待处理」+ 页脚再「批量接受/批量拒绝」，批量按钮出现两次、单条导航按钮与键盘快捷键并存 | 保留面板头一处批量操作；页脚删除；快捷键提示收成 one-line | 交互冗余 |
| frontend/src/pages/Review/ReviewPage.tsx:201-204 | SplitPane 左右面板各有一条 toolbar（左「合同原文与修订 点击高亮内容可定位右侧修订」/移动标签「合同呈现/修订清单」），说明文字与标签名不统一 | 统一叫法（左：合同 · 修改标记 / 右：改动清单） | 术语漂移 |
| frontend/src/pages/Compare/ComparePage.tsx:439-443 | 单页内顺序：任务列表卡 → （条件）新建任务卡 → 选中任务详情卡 → 全屏 viewer；四段状态机全靠滚动堆叠 | 新建任务放弹层或独立区块锚点；任务详情与列表用上下分页/tab | 层级过深，创建流程与浏览流程混在一页 |
| frontend/src/pages/Compare/ComparePage.tsx:177-199 | CompareReader：toolbar（视图模式/修订计数/显示源文档/显示标记）+ aside 修订 rail 头（上一处/下一处/筛选）+ 文档区 pane-head（三处）+ 图例插标，共 4 层头部装饰 | 合并 toolbar 与 rail 头；源文档开关进视图模式 | 装饰比内容多 |
| frontend/src/pages/Compare/ComparePage.tsx:219 | 双栏对照模式头部三行：「合同正文 双栏联动阅读…」+ A/合同A→B/合同B 徽章行 + 移动端切换行 | 合并为一行 | 重复标题 |
| frontend/src/pages/Guides/index.tsx:88-157 | 顺序：当前指引 → 我的指引（表）→ CompareCard（版本对比，含 tab 规则差异/原文比对）→ 上传新指引 | 「上传新指引」上提到当前指引后；版本对比整块降到详情页或折叠区（主线裁决：本身可能是重功能，见 Table1） | 主流程被次要功能截断 |
| frontend/src/pages/Guides/index.tsx:312-341 | 规则表：每规则两行（主行 + colSpan=4 的 detail-row 折叠）+ 分组行 colSpan，结构复杂而正文仍被藏 | 单行表格显示：勾选 / 规则标题 / 章节 / requirement 直接展示（截断可滚动）| 与「平铺」互锁 |
| frontend/src/pages/Guides/CompareCard.tsx:104-140 | 新增/删除/修改三栏 guide-diff-grid，修改栏内每条再 details | 三栏保留，详情平铺 | （部分已在表 1 给出） |
| frontend/src/pages/Settings/index.tsx:116-162 | 管理员看到：系统状态（折叠）→ 飞书绑定 → 修改密码 → 管理员卡（重复导航按钮） | 删管理员卡（表 1）；系统状态平铺成小 dl 列表 | 重复入口 + 藏信息 |
| frontend/src/pages/Settings/ModelSettings.tsx:181-187 | 「将执行模型配置复制给检查模型」独立整卡，仅一句说明 + 一个按钮 | 并入检查模型卡内的 action-row | 卡片裁得过碎 |
| frontend/src/pages/Settings/ModelSettings.tsx:81-84 | 每个表单字段下各跟一条 muted 帮助句（4 条） | 合并为一张表单下面一句总注（或删，见表 1 各行） | 堆小字 |
| frontend/src/pages/NewTask/index.tsx:197-205 | 单卡内：名称 → 大 dropzone(158px) → 文件清单（KPI×4 + 搜索 + 筛选 + 表 + 自带分页）→ 服务端接收结果 ul → 补传 CSV 行 → 进度 → 错误 → 提交按钮；一个卡承担 8 个职责 | 拆 stepper 或至少把「服务端接收结果」并入文件表状态列 | 单卡信息密度爆表 |
| frontend/src/pages/Users/index.tsx:67-104 | 创建用户 form 占一张卡（5 控件横排 action-row 折行）；账号列表另卡，布局尚可 | 创建表单改 form-grid 两列 | 控件横排换行难看（全局 action-row 通病：见 TaskDetail:101 一堆按钮折行） |
| frontend/src/components/layout/AppShell.tsx:127 | 侧栏底部「FundLex · 广发基金合同修订工作台」note + 顶栏 brand + 页脚©行三重品牌 | 保留其一 | 品牌重复 |
| frontend/src/pages/TaskDetail/index.tsx:101 | action-row 内「下载汇总/导出结果 CSV/下载全部 ZIP/补传未接收文件」+ 6 个 Tab 按钮同一行，视口一窄就换行错位 | 下载组与 tab 组分行 | 控件拥挤 |

---

## 表 4 · 结果页地图（FL-D818 重构输入）

**目标页面**：合同修改结果页 = `frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx`，路由（`frontend/src/app/App.tsx:33-34`）：
`/tasks/:taskId/documents/:documentId/report` 与 `/detail` 双别名。相邻结果面板：
任务级结果在 `TaskDetail/index.tsx`（结果与交付+合同列表），修订复核在 `pages/Review/ReviewPage.tsx`。
本表只详尽描述 **DocumentDetailPage**。

### 组件树 / DOM 区块（按渲染顺序，DocumentDetailPage.tsx:156-179）

```
DocumentDetailPage (div.fundlex-document-detail)
├─ header.page-heading (L168)
│   ├─ 「← 返回任务」链接 → /tasks/:taskId
│   ├─ H1 = 合同文件名；副文「修改与交付结果」
│   └─ 动作区: [打开修订复核] (primary, working_redline/redline 缺失则 disabled) + StatusBadge(delivery_status)
├─ Card「交付概览」 Summary (L86-92 → L169)
│   dl.fundlex-detail-grid 六对 dt/dd:
│     资格(StatusBadge) / 处理状态(StatusBadge) / 交付(StatusBadge) /
│     交付说明(detailStatus L55-62 人话句) / 目标完成 x/y / 仍需核对 n
├─ Card「交付文件」 DownloadSection (L144-148 → L170)
│   ├─ 标题 H2「交付文件」
│   ├─ DownloadButtons (L130-142): kinds = downloads 中排除 report_* 与 evaluation_*
│   │   → final(final 或 selected_final 用 primary 变体) ; 可能含 redline /
│   │     selected_final / selected_redline / working_final / working_redline
│   │     按钮文案 = downloadLabel (L40-49)
│   ├─ 空态: 「当前没有可下载文件。」+ muted「文件会在处理服务完成并通过复核后开放…」
│   └─ 条件警示: incomplete/not_generated 时「当前交付状态为“…”，工作文件不能直接视为最终合同。」(L147)
├─ Card「条款改动 · N 项」 ClauseChangeSection (L100-120 → L172)   [report 已生成时]
│   ├─ targets: 每条 <details.fundlex-target>(默认闭合):
│   │    summary = 规则标题/rule_id + StatusBadge(条款状态)
│   │    内: dl 位置 + 目标原文(Evidence blockquote)
│   │        + EditRows：「修改前」p / 「修改后」p（可多条 component）
│   │        无对照时 meta-line「该目标没有逐段对照，处理结果见右上标记。」
│   └─ rest edits（report.plan.edits 未匹配 target 的）: <details> 规则id · 位置 + 操作 tag，
│        内为 EditRows
│   (空: 「报告没有返回条款改动明细。」 L119)
├─ [条件] Card「验证暂未完成，等待恢复处理」 (L173, verification_blocked)
│   文案含「验证记录或模型额度暂不可用」内部归因
├─ Card「异常点 · N 项」 ExceptionSection (L122-128 → L174)
│   每条 <details.fundlex-exception>(默认闭合):
│     summary = 「例外 N · 标题 + 小字位置」
│     内: dl 位置 + 诊断来源(规则义务核对/覆盖检查/人工复核提示/交付核验)
│         + 原因段落 + Evidence(引文 blockquote)
│   (空: 「没有登记异常点。」)
├─ Card「业务依据」 EvidenceSection (L181-185 → L175)
│   资格依据一段文字 + fund_type_quote 引文 + qualification evidence 列表
│   (空: 「暂无独立证据引文。」/「报告未提供资格说明。」)
└─ <details.advanced-details>「高级详情」 AdvancedSection (L150-154 → L177)
    dl: 原件 SHA-256 / 指引版本(version_id)
    + DownloadButtons(report_* 与 evaluation_* 全集合：Markdown 报告/JSON 报告/评测版…)
```

不在 result 页但与之构成闭环的入口：
- 任务行「修订」按钮 (`TaskDetail/index.tsx:77`) → `/review` 逐条复核页（DocumentViewer 左 + RevisionPanel 右，`components/document/*` + `components/review/*`）。
- 报告 JSON/MD = 表 1 所指藏进「高级详情」的下载项。

### 各区块回答什么问题

| 区块 | 回答的问题 | 现状密度评价 |
|---|---|---|
| header (L168) | 我是谁（文件名）、总状态（badge）、去复核 | OK；只有「打开修订复核」文案需改 |
| 交付概览 (L86-92) | 处理/交付状态汇总；目标 x/y；仍需核对 n | 6 字段 dl 可读，但与后文 badge/警示重复 |
| 交付文件 (L144-148) | 产物在哪、怎么下载 | 主下载区——但报告类被拆到「高级详情」（见下）；按钮文案冗长（downloadLabel 行话） |
| 条款改动 (L100-120) | 我的合同改了什么 | **核心内容默认全部折叠**；每条含 位置+引文+前后对照全文，N 条款展开即长文砌块，字密密麻麻的直接出处 |
| 验证中断卡 (L173) | 为什么还没完 | 文案带内部归因，可并入交付概览 |
| 异常点 (L122-128) | 没改完/要人工核什么 | 同样全折叠；「诊断来源」内部词；位置小字塞 summary |
| 业务依据 (L181-185) | 为何判定可处理 | 次要信息，排位却在下载之后条款之前的同等深度 |
| 高级详情 (L150-154) | 哈希/版本 ID + 报告/评测下载 | 技术字段 + **被藏的真正下载物**，双重问题 |

### 可砍 / 可分层 / 密集堆叠判定

- **可砍**：原件 SHA-256、version_id（或移到极小字脚注——主线裁决）；「诊断来源」字段；「验证中断卡」的技术归因句；空态解释小字（见表 1 各行）。
- **可分层**（放次级）：整段 Evidence blockquote（引文摘要到 hover/展开才看）；「业务依据」整卡降为资质说明一行（仅 ineligible/diagnosed 时显示）。
- **必须升层的**：条款改动摘要（现在是折叠的；应做成每行：条款名 + 一句「改了什么」+ 状态），报告/评测下载（汇入交付文件区分组），「仍需人工核对」从数字升级为同条款改动并列的可见列表。
- **密集堆叠重灾区**：`fundlex-target` 详情体（dl+blockquote+双栏对照）与 task-level DocumentRow 单元格（表 3 行 2）。

### 用户四个核心问题 → 现状由谁回答

| 核心问题 | 现页面回答区块 | 结果评级 |
|---|---|---|
| ① 我的合同改了什么 | 条款改动卡 (L100-120)：全部 details 默认闭合，须逐条展开才见前后对照；可视修订需跳去 /review 页 | **基本未直接回答**（埋在三屏外的折叠里）；修订对照在另一页 |
| ② 还有哪些没改完要人工核 | 交付概览「仍需核对」数字 (L91) + 异常点卡 (L122-128，默认闭合) + header badge「结果不完整」 | 分散三处且两处折叠；入口不强 |
| ③ 产物在哪 | 交付文件卡 (L144-148)：主产物齐全；但 报告(MD/JSON)/评测产物被计入「高级详情」折叠 (L150-154)；incomplete 时按钮名与警示不一眼对应 | 一半可见一半被藏 |
| ④ 怎么下载 | DownloadButtons (L130-142)：按钮齐备，文案冗长行话（「工作文件修订痕迹（人工选择，未完成）」）；任务级另有「下载全部 ZIP/汇总/CSV」(TaskDetail/index.tsx:101) | 能完成但认知成本高 |

> 任务级（合同列表）下载入口另见 TaskDetail/index.tsx:77 行内 `修订 / 选择版… / 报告` 按钮组，命名与 DocumentDetail downloadLabel (L40-49) 不一致（任务行用「报告」指 JSON 报告，详情页叫「JSON 报告」），建议 FL-D818 统一一份下载命名表。

---

*审计性质：只读；除本文档外未改动任何代码。所有「主线裁决」为不确定项，交由主 agent 按 FL-D816/817/818 裁决。*
