# V2 全覆盖签认表（2026-11-01 第七轮·全覆盖令）

> 用户铁律：「对所有的代码、所有的各个页面挨个检查，不要有任何遗漏」「简化我的要求是绝对的大忌」。
> 指派依据：`docs/COVERAGE_MATRIX_20261101.md`（主线 3cab25b，本树自 git show 抽取至 /tmp/opencode/qa/COVERAGE_MATRIX_20261101.md）A 节 V2 10 页面域 + B 节 49 个 V2 文件。
> 基线：qa-frontend-v2 @ **3fce104**（含 FL-D899 直接修批；矩阵 49 文件与工作树逐一比对零差异，另 +1 自产文件 `lib/issueText.ts`（FL-D899 新建）一并签认，共 **50 文件**）。
> 纪律遵守：本轮**只读代码、未改任何源码**；全部发现登记于本文「V2M 登记表」，编号 V2M-xx（不占集中册 FL-D 号段）；主条目挂 FL-D899 变更记录。
> 口径：四关（①技术内容外泄 ②小字/啰嗦 ③与全站令牌不一致 ④组件丑/信息层级混乱）+ 状态覆盖（空/加载/失败态）。

## 一、页面域签认（A 节 V2 全 10 域 + 子路由/状态）

状态实证沿用 FL-D899 浏览器回归（同一 HEAD 3fce104，代码未变）：python 浏览器 101/101 通过；before/after 截图 `/tmp/opencode/qa/shots-v2-audit/`、`/tmp/opencode/qa/shots-v2-after/`；逐页四关记录见 `docs/frontend/V2_AUDIT_20261101.md`。本轮在此基础上逐页复查源码。

| 页面域 | 子路由/状态覆盖 | 签认 | 发现编号 |
| --- | --- | --- | --- |
| Auth | /login（密码态）、dev 身份态、登录/注册错误态、初始化失败兜底 | ✅ | V2M-01（波及）、V2M-07（初始化兜底文案） |
| Compare | 列表（空/有数据）、新建（逐组/文件夹配对/续传）、任务详情（进行中/完成/失败组/覆盖不完整）、查看器（word/双栏/移动态，shot22） | ✅ | V2M-10、V2M-17、V2M-02、V2M-03、V2M-01（波及） |
| DocumentDetail | 正常态/失败态/加载态（批4 结构干净） | ✅ | V2M-01（波及），无页面独立发现 |
| Guides | 列表（空/当前/历史/不可启用）、详情（解析结果/规则开关/解析问题）、版本对比（规则/原文） | ✅ | V2M-11、V2M-16、V2M-12、V2M-14；已登记-裁决3 |
| NewTask | 新建/补传双态、拖拽、文件校验、清单筛选、上传进度、部分拒绝态 | ✅ | V2M-01（波及），无页面独立发现 |
| Review | 逐条复核（种子态实证 FL-D899）、空清单、未知操作码 | ✅ | V2M-09、V2M-01（波及） |
| Settings | 系统状态（管理员）、飞书绑定（码/扫码/已绑）、改密码（成功/失败） | ✅ | V2M-13、V2M-01（波及） |
| TaskDetail | 任务状态四卡、结果与交付、合同列表（搜索/排序/高级筛选/分页）、下载/补传/暂停恢复 | ✅ | V2M-05、V2M-06、V2M-18、V2M-01（波及） |
| Tasks | 总览（空/加载/失败/分页，已修-3fce104 噪音列删除实证 shot03/04） | ✅ | 无页面独立发现（ErrorState 为 V2M-01 载体） |
| Users | 403 诚实态（已修-3fce104）、创建/停用（LAST_ADMIN_REQUIRED 人话） | ✅ | V2M-01（波及），无页面独立发现 |

## 二、文件签认（B 节 49 文件 + 自产 1 = 50，逐文件）

| 文件 | 签认 | 发现编号 |
| --- | --- | --- |
| api/client.ts | ✅ | V2M-01（源头） |
| api/endpoints.ts | ✅ | 无发现 |
| api/hooks.ts | ✅ | 无发现 |
| api/index.ts | ✅ | 无发现 |
| api/queryClient.ts | ✅ | 无发现 |
| app/App.tsx | ✅ | V2M-07 |
| app/index.ts | ✅ | 无发现 |
| components/document/DocumentAnchor.tsx | ✅ | 无发现 |
| components/document/DocumentMarker.tsx | ✅ | 无发现 |
| components/document/DocumentNavigator.tsx | ✅ | 无发现 |
| components/document/DocumentViewer.tsx | ✅ | 无发现（消毒白名单正确，为 V2M-12 之正例对照） |
| components/document/SplitPane.tsx | ✅ | 无发现 |
| components/document/index.ts | ✅ | 无发现 |
| components/layout/AppShell.tsx | ✅ | V2M-08 |
| components/layout/index.ts | ✅ | 无发现 |
| components/review/RevisionCard.tsx | ✅ | V2M-09 |
| components/review/RevisionPanel.tsx | ✅ | 无发现 |
| components/review/RevisionTypes.ts | ✅ | 无发现 |
| components/review/index.ts | ✅ | 无发现 |
| components/ui/Button.tsx | ✅ | 无发现 |
| components/ui/Card.tsx | ✅ | 无发现 |
| components/ui/Select.tsx | ✅ | 无发现 |
| components/ui/Spinner.tsx | ✅ | 无发现 |
| components/ui/StatusBadge.tsx | ✅ | 无发现（中文直通设计正确；tone 丢失在调用方 V2M-10） |
| components/ui/index.ts | ✅ | 无发现 |
| lib/issueText.ts（自产，矩阵外+1） | ✅ | 无发现 |
| main.tsx | ✅ | 无发现 |
| pages/Auth/index.tsx | ✅ | V2M-01（波及） |
| pages/Compare/ComparePage.tsx | ✅ | V2M-10、V2M-17、V2M-01（波及） |
| pages/DocumentDetail/DocumentDetailPage.tsx | ✅ | V2M-01（波及） |
| pages/DocumentDetail/index.ts | ✅ | 无发现 |
| pages/Guides/CompareCard.tsx | ✅ | V2M-12、V2M-14；已登记-裁决3 |
| pages/Guides/index.tsx | ✅ | V2M-11、V2M-14、V2M-16 |
| pages/NewTask/index.tsx | ✅ | V2M-01（波及） |
| pages/Review/ReviewPage.tsx | ✅ | V2M-01（波及） |
| pages/Review/index.ts | ✅ | 无发现 |
| pages/Settings/ModelSettings.tsx | ✅ | V2M-15、V2M-01（波及） |
| pages/Settings/index.tsx | ✅ | V2M-13、V2M-01（波及） |
| pages/TaskDetail/TaskDetailIndexPage.tsx | ✅ | 无发现 |
| pages/TaskDetail/index.tsx | ✅ | V2M-05、V2M-06、V2M-18、V2M-01（波及） |
| pages/Tasks/index.tsx | ✅ | V2M-01（ErrorState 载体），无独立发现 |
| pages/Users/index.tsx | ✅ | V2M-01（波及，非 403 分支） |
| stores/auth.ts | ✅ | 无发现 |
| stores/index.ts | ✅ | 无发现 |
| stores/workspace.ts | ✅ | 无发现 |
| styles/app.css | ✅ | V2M-02、V2M-03、V2M-04（与已登记-裁决1/2 同族补充） |
| styles/index.css | ✅ | 无发现 |
| styles/tokens.css | ✅ | 无发现 |
| types/api.ts | ✅ | 无发现 |
| types/index.ts | ✅ | 无发现 |

**无遗漏核对**：矩阵 49 项全部签认 + 自产 1 项；无「矩阵有实际无」、无「实际有矩阵无而未审」（差集核对记录于状态文件）。

## 三、V2M 登记表（本轮发现，登记不动工；修复待下轮令）

### 裁决级（建议主线裁决口径后统一修）

- **V2M-01 · ApiError 裸错误码冒泡**（高）。`api/client.ts:16-17` 构造器把响应体 `detail` 原文当 `code`，`:97-98` parseError 把 detail 当 `message`；后端 raise_api_error detail=错误码（实证 compare 422 `{detail:"INVALID_REQUEST"}`），导致顶层 `ErrorState`（Tasks/index.tsx:7-9，message 直出）、App.tsx auth 初始化失败、ReviewPage ErrorState、NewTask catch、ComparePage `messageOf`、Settings 绑定/改密、ModelSettings 连接测试、Guides/Users 非特判分支全部可能把英文错误码原样显示给用户。建议：client 层统一把「纯大写下划线码」走 `issueCodeText` 同族映射或回退通用人话，页面不再直吃 message。
- **V2M-02 · `--accent*` 死引用 6 处**（中）。app.css:440/442/446/486/490/562 引用 V2 未定义的 `--accent/--accent-dark/--accent-soft` 且无回退值 → 「x 处修订」计数、checkbox accent、差异列表激活竖条、移动切换激活态品牌色全部失效（shot22 实证：931 处修订未呈品牌色）。语义等价 1:1 映射已验证：`--accent*→--brand*`（DESIGN_TOKENS 档案声明同名同值）。注：:710 有回退值无碍。
- **V2M-07 · 路由与初始化兜底**（中）。App.tsx：①无 404 路由，`*` 静默跳 /tasks（用户打错地址无反馈）；②`/tasks/:id/documents/:docId/report` 与 `/revisions` 双路由挂同组件（IA 同族，见已登记-IA4）；③auth 初始化失败兜底仅「请求失败（500）」式通用错误，不引导重试/重登。

### 直接修建议级（令牌级 1:1 或文案微调，无交互变更）

- **V2M-03 · 查看器 10px 小字残留两处**。app.css:465 `.compare-word-pane-kicker`、:530 `.compare-word-legend` 为 10px，低于令牌最小档 `--text-2xs: 11px`（FL-D899 G2 漏网）。
- **V2M-04 · 直色/裸字号漏网（补登记-裁决1/2）**。app.css:172 `.app-footer` #89919b、:284/286 `.footer-link` #6b7681/#a9b0b6 直色；:103 `.nav-link` 15px 裸字号（令牌无 15px 档）；`.stat-value` 25/23px、`.compare-viewer-title strong` 19px 随登记-裁决1 收编。
- **V2M-05 · TaskDetail 导出 CSV 英文原始码**。pages/TaskDetail/index.tsx `exportResults` 内联：`document.eligibility || '未判定'`、`job_status`、`delivery_status` 裸值直接入「能否处理/处理状态/交付」三列（页面表格同位置是中文 StatusBadge），用户得到的 CSV 出现 `eligible/complete_with_exceptions` 等码。建议复用 StatusBadge 标签表抽出共享 helper 后导出中文。
- **V2M-06 · TaskDetail「任务」卡明细同义反复**。`StatusDimension title="任务" detail={current.pause_reason || '当前状态'}`：非暂停态恒显「当前状态」，零信息量噪音。
- **V2M-10 · Compare 列表徽章 tone 丢失**。ComparePage.tsx:442 `<StatusBadge value={statusLabel(item.status)} />` 二次中文化后tone 逻辑以英文码匹配（`includes('fail')` 等），中文值恒落 neutral → 失败任务灰显非红。建议直接传英文码（StatusBadge 自映射），删除 statusLabel 在徽章处的使用（文本处保留）。
- **V2M-11 · Guides qualificationStatusText 未知值原文回显**。Guides/index.tsx:31 `... || status || '—'`，后端新增资格码将原文外泄；建议同 StatusBadge 策略回退「未知状态」。
- **V2M-13 · Settings capabilityLabel 未知 key 原文回显**。Settings/index.tsx:12 `labels[key] || key || '—'`；系统状态卡（admin-only）遇新 engine/delivery 值将原文外泄英文技术词。

### 登记观察级（minor / 一致性与 IA）

- **V2M-08 · AppShell 导航小疵**。①「模型配置」「设置」共用 `settings` 图标，辨识度低；②帮助弹层「评测文件」为内部词外显（普通用户无此概念）。
- **V2M-09 · RevisionCard 未知 operation 原文回显**。`operationLabels[op] || op`：后端新增操作码将原文外泄；建议回退「调整」。
- **V2M-12 · CompareCard 原文比对未消毒**。Guides/CompareCard.tsx:174-179 `dangerouslySetInnerHTML` 直接渲染 text_diff HTML，未走 DocumentViewer/SafeCompareDocument 的白名单消毒（同站两处对比渲染均消毒，此处口径不一致）。指引 DOCX 为用户上传内容，保留观察。
- **V2M-14 · operation 文案三套不一致**。同一组操作码三套标签：CompareCard `OP_LABELS`（追加/替换为/不改）、Guides `guideOperationLabel`（修改/删除/新增/无需调整）、RevisionCard `operationLabels`。建议统一收敛至单一映射表。
- **V2M-15 · 原生 confirm 弹窗**。ModelSettings.tsx:49/143/150 三处 `window.confirm`，与全站组件化风格不一致；次要不阻塞。
- **V2M-16 · Guides「解析问题」卡静默空卡**。Guides/index.tsx:344-350 仅处理 `GUIDE_VALIDATION_UNCLEAN` 一种 error_code，issues_detail 含其他键时卡内无任何内容且不显示「没有记录解析问题」。
- **V2M-17 · Compare 视图术语不一致**。classic 视图「合同A/合同B」（:218-228）与 word 视图/创建表单「原版/对比版」混用；建议统一「原版/对比版」。
- **V2M-18 · 高级筛选提示词失准**。TaskDetail 高级筛选「异常提示」placeholder「按提示关键词筛选」，实际入参 `error_code` 为精确码匹配，用户按自然语言关键词搜不到。

## 四、与既有登记的关系

- FL-D899 直接修 7 项已在 3fce104 生效（本表基线内，不重列）；「已登记-裁决1/2/3」「已登记-IA4/5」继续有效，本表 V2M-04 为裁决1/2 的漏网补充、V2M-07②/… 与 IA4 同族不重复占号。
- V2M-xx 不占用集中册 FL-D 号段；待下轮令裁决/修复后，由主条目 FL-D899 变更记录汇总消化并入集中册。
