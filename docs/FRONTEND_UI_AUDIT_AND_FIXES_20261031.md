# 前端全面整改：全页面体检清单与逐项修复记录（2026-10-31，qa-frontend 线）

- 派单：产品负责人六条（结果页杂乱/模型配置丑/列表与字体按钮不一致/技术内容泄露/小字冗余/整体优化）+ 主线补充 FL-D721（导出包 409 新语义与「下载全部结果」禁用旧口径）。
- 范围：V1（`frontend/app.*`、`workspace.js`、`compare.*`、`guide_generation.*`、`compare.html`）与 V2 React（`frontend/src/**`）。不动 CSV/MD 导出内容（qa-export 线）、不动 API 与 review/pin 选择语义（FL-D565/662/663）。
- 编号段位：FL-D710..719 + FL-D721。

## 一、统一设计 token 层（整改基准）

| Token 组 | 值 |
| --- | --- |
| 品牌 | `--brand:#b5471e` / `--brand-dark:#8e3213`(hover) / `--brand-soft:#fff1e9` / `--brand-soft-strong:#f8dfd1` |
| 文字 | `--ink:#20252b` / `--muted:#68717c` |
| 表面 | `--surface:#fff` / `--surface-subtle:#f7f9fa` / 页面底 `#f5f6f8` |
| 边框 | `--border:#dfe3e8` / `--border-strong:#cfd5db` |
| 语义 | success `#2f7653/#e8f4ec`，warning `#8a5b14/#fff5dc`，danger `#a13b35/#fbeceb` |
| 字号阶梯 | 12 注释 / 13 表格·次要 / 14 正文基准 / 16 / 20 / 24；小徽章 11；禁半像素 |
| 间距 | 4 / 8 / 12 / 16 / 24 / 32 |
| 圆角 | 6 / 10 / 999(pill) |
| 按钮 | primary 橙底白字 hover 深橙；默认白底灰边；danger；quiet 无框 |
| 表格 | th 12px muted；cell padding 10px 12px；行高统一 |
| 徽章/标签 | pill 圆角、soft 底 + 纯色字 |

V1 历史包袱：第一调色板 `--accent:#b5471e` 本与 V2 `--brand` 一致，但后并入的 `--fx-*` 蓝色系（`#2f5b83`）形成双品牌；整改采用**保留变量名、翻转变量值**策略收敛，避免上百处规则级联。
整改前 V1 字号实测 27 种（含 9/10.5/11.5/12.5/13.5/14.5px 半像素），padding 约 40 种组合；V2 `app.css` 存在 `.data-table th`、`.form-stack label` 同名重复定义且值不一致。

## 二、全页面体检清单（技术泄露点 / 风格不一致点 / 冗余文案点 / 信息架构问题）

### V1（app.js / compare.html / compare.js / guide_generation.js）

| # | 页面 | 问题 | 类别 |
| --- | --- | --- | --- |
| V1-1 | 任务详情逐合同行 | `title="引擎阶段：${doc.phase}"` 内部阶段原值悬停；无 phase 回显引擎营销名「召回优先修订」 | 技术泄露 |
| V1-2 | 合同结果·条款对照 | 未知 `row.reason` 直接回显英文原始码 | 技术泄露 |
| V1-3 | 我的指引 | 完整版本 UUID、`规则哈希`(sha256 前12位+title 全值)、`基于 {parent}`、列表行 item.id | 技术泄露 |
| V1-4 | 指引解析错误 | `<code>${error_code}</code>` 原始错误码直显 | 技术泄露 |
| V1-5 | 合同结果下载区 | 「JSON 报告」直供普通用户下载 | 技术泄露 |
| V1-6 | 比对选择与事件线 | artifact 完整 SHA-256 行直显；「差异报告」= JSON.stringify dump；statusLabel 未知回显英文 | 技术泄露 |
| V1-7 | 指引生成管理页 | 候选版本/父版本 UUID `<code>` 直显；`error.raw+code` 直拼；下载项名含「完整证据 JSON」「引擎兼容报告 JSON」 | 技术泄露 |
| V1-8 | 任务详情页 | 下载操作散落在 6 按钮操作排；进度文案三处重复（subtitle 计数 + task-percent/overall-label + mini-kpi title 长提示）；图例硬编码色 | 信息架构+冗余 |
| V1-9 | 「下载全部结果」禁用 | ready() 用 completed>0 旧口径：全失败任务后端可下载解释包但 UI 禁用；download-hint 仍旧 409 语义（FL-D721） | 功能+文案 |
| V1-10 | 模型设置 | 双 fieldset 上下堆叠视觉重复、信息密度低；每控件一条 subnote；config_error 原文；legacy 旧模型名直显 | 造型+泄露 |
| V1-11 | 全局 | 重试话术 ≥9 种变体 26 处；状态标签表 4 份重复维护（app.js labels/GUIDE_STATUSES、workspace.js phases、compare.js statusLabel） | 冗余+不一致 |
| V1-12 | 登录态切换 | `.app.inert` 切换与 V2 登录页视觉不一致（双品牌残留） | V1/V2 协调 |
| V1-13 | compare.html | 23 处 inline style；theme-color 第三色值 #8E3213 | 风格不一致 |

### V2 React（src/）

| # | 页面 | 问题 | 类别 |
| --- | --- | --- | --- |
| V2-1 | 全局 StatusBadge | 未知状态 fallback 回显英文原值 | 技术泄露 |
| V2-2 | 任务总览 | 任务 UUID 显示在名称下；指引版本哈希/版本号直出；术语「Worker」；「均来自服务端」开发视角句 | 技术泄露+冗余 |
| V2-3 | 任务详情 | 指引快照 version_id 裸哈希；「服务端 phase 字段」句；error_code/reason_codes 原始英文直出；高级筛选占位符示范内部码 | 技术泄露+冗余 |
| V2-4 | 合同详情（DocumentDetail） | 下载区在页面最末（首屏看不到）；原件 SHA-256 整列展示；指引版本 UUID；EX-${hash} 自造例外号；目标条目 rule_id/status 裸值；「统计口径不同」开发解释；verification_blocked 等散落 | 信息架构+泄露+冗余 |
| V2-5 | 修订复核 Review | 进度三处重复（页头/面板/footer）；快捷键小字与按钮重复 | 冗余 |
| V2-6 | 我的指引 | 「来源哈希」列；「版本 {UUID}」「基于 {parent}」；资格状态英值；操作统计英文 key 直出；两处 JSON.stringify `<pre>` dump；「（不使用模型）」实现口径形容 | 技术泄露+冗余 |
| V2-7 | 对比页 | statusLabel 未知回显英文；「差异报告」JSON dump 下载；每条 diff 前置 `<small>FundLex 对比</small>` | 技术泄露+冗余 |
| V2-8 | 模型配置 | 系统模型 provider_model 字符串直显；config_error 拼接原文；legacy_model/system_model 显示；「仅影响新建任务」同义句 ×3 | 泄露+冗余+造型 |
| V2-9 | 设置页 | 全站唯一 inline style（二维码容器色 #d9d9d9 与 token 不一致） | 风格 |
| V2-10 | 全局 | tokens.css 只有颜色，字号/间距/圆角全硬编码于 app.css；hover 三套近似色；`TaskDetailIndexPage` 与 `Tasks` 表格近乎复制 | 风格不一致 |

## 三、逐项修复记录

### V2 React（frontend/src/**，18 文件；自验 tsc 0 错 / vitest 24 绿 / vite build 过）

| 体检项 | 处理方式 |
| --- | --- |
| token 缺口 | `tokens.css` 扩展全 token 层（字号阶梯/间距/圆角/行高/表格密度/工具类 `.meta-line` `.advanced-details` `.stat-card` `.ui-tag`），保留全部旧变量名值 |
| 风格重复定义 | `app.css` 合并 `.data-table th`×2、`.form-stack label`×2；hover 三色收敛 `--brand-soft`/`--surface-subtle`；`.error-state`/`.fundlex-error` → danger 语义变量；半像素字号 sed 批归一 |
| V2-1 StatusBadge | 未知值 fallback →「未知状态」（中文文案透传不误伤），补 pending/blocked/partial/eligible/retry_wait 等映射 |
| V2-2 任务总览 | 删 UUID 行；指引列值 →「修改指引已锁定」；Worker→处理服务；删服务端来源句 |
| V2-3 任务详情 | `issueCodeLabels` 8 码中文映射 + 未知→「处理未通过，详见报告」；version_id 移 `.advanced-details`；删 phase 字段句；筛选占位符改「按提示关键词筛选」 |
| V2-4 合同详情重构 | 块序：页头→概要→**交付文件区上移**→条款改动汇总（Target+Compare 合并按条款归并，`.ui-tag` 动作标签）→verification_blocked→异常点（EX-hash →「例外 N」）→业务依据→高级详情（SHA-256 全值/version_id/report_json/evaluation_* 下载）；Summary 删两行哈希；删统计口径解释；review/pin API 语义未动 |
| V2-5 Review | 三重进度 → 仅 RevisionPanel 一处；快捷键+生成语义合并一句；`rule_id` 显示「规则 {id}」pill |
| V2-6 我的指引 | 删来源哈希列；版本 UUID → 当前使用/历史版本标签；`qualificationStatusText`、`guideOperationLabel` 中文化；两处 JSON `<pre>` 进高级详情；删「（不使用模型）」 |
| V2-7 对比页 | statusLabel fallback →「处理中」；**删 JSON dump「差异报告」下载**；删 diff 前置「FundLex 对比」赘标 |
| V2-8 模型配置 | 系统模型串 →「由管理员统一配置」；config_error → 中文泛化；legacy 警告一句且不含字段值；「仅影响新建任务」3→1；保留「验证连接」+ role=status |
| V2-9 设置页 | 唯一 inline style → `.settings-oauth/.settings-qr-frame`（token 边框/圆角） |
| V2-10 其他 | NewTask 字节 → KB/MB（formatSize）；侧栏重复 note 改品牌短句；Users 16 行压缩 JSX 格式化+admin/member 中文化；TaskDetailIndexPage 与 Tasks 同表口径 |
| Button 组件 | 新增 `className` 透传（向后兼容） |

### V1（app.js/app.css/compare.*/guide_generation.*/compare.html + 新建 status_labels.js）

| 体检项 | 处理方式 |
| --- | --- |
| 双品牌调色板 | `--fx-*` 蓝系变量值整体翻为 canonical 橙系/中性系（变量名保留规避级联）；compare.html `theme-color` 移除第三色值 |
| 字号/padding 碎片化 | 半像素与 1px 级噪声批量归一：app.css px 种数 25→18、compare.css 18→10、guide_generation.css 9→8；token 变量（--fs-*/--sp-*）入 `:root`；inline style 23 处提类 |
| V1-1 引擎 phase | title 删除；「召回优先修订」→「合同修订」 |
| V1-2 reason 原文 | 未知 reason →「其他调整」映射 |
| V1-3/4 指引 UUID/哈希/错误码 | 「版本编号/规则哈希」移入 `details.action-evidence`（高级详情）；解析错误码中文映射 +「已尝试 N 次」保留 |
| V1-5 JSON 报告 | 合同结果弹层下载区移出，进「高级详情」 |
| V1-6 比对 SHA/JSON dump | artifact SHA-256 行删除；「差异报告」JSON dump 下载删除（compare.js handler 一并移除）；statusLabel fallback「—」 |
| V1-7 指引生成 UUID | 版本链编号入「高级详情」；error_code 中文映射；下载项改名「解析证据（JSON）」「兼容性检查（JSON/HTML）」 |
| V1-8 任务详情 IA | 独立「交付文件」卡（下载全部结果 ZIP/结果清单 CSV/结果总览 .md 集中，download-hint 同卡）；三处进度文案合并为 KPI+进度条一处 |
| V1-9 FL-D721 | ready 条件 = `(completed>0 \|\| failed>0)`（含全失败；处理中不开放）；disabled title 改新语义；hint 文案改「任何已接收的合同都会进入结果包；未通过处理的合同会在包内给出原因说明。」 |
| V1-10 模型设置 | `.model-roles-grid` 双列卡片（窄屏纵排）；页级说明一句；subnote 收敛为两条；config_error 中文泛化；legacy 一句不含字段值 |
| V1-11 重试/状态表 | 重试统一「请稍后重试。」；新建 `status_labels.js` 共享状态标签（`window.FUNDLEX_STATUS_LABELS`），app.js/workspace.js/compare.js 引用 |
| 规则编号呈现 | 修订条目 `<span class="rule">` 显示「规则 G01」pill（与 V2 `.ui-tag` 对齐） |
| 结果弹层块序 | 结论→交付文件→审阅修订→人工核对（技术信息折叠摘要改「高级详情」）→未修改条款→条款对照→依据 details；「修订痕迹中不会出现本处」重复句合并 |

> V1 施工线未及跑的浏览器整批由主线回归统一执行（结果见第四节）。

## 四、测试与构建

| 验证 | 命令 | 结果 |
| --- | --- | --- |
| TS 类型 | `frontend && npx tsc -b --noEmit` | 0 错误 |
| 单元 | `frontend && npx vitest run` | 6 文件 24 用例全绿（基线 24 绿，零退化） |
| 构建 | `frontend && npm run build` | ✓ built（dist 产物与浏览器套件一致） |
| JS 语法 | `node --check` ×5（app/workspace/compare/guide_generation/status_labels） | 全过 |
| CSS 完整性 | 大括号配对 ×3 | 876/661/142 全平衡 |
| 锚点核对 | vitest 断言清单 + python 浏览器测试 40+ id/文案 | 全部保留（「指引配置」「最终版 DOCX」「上传并解析」等） |
| 浏览器 V2 | `test_frontend_v2.py` + `test_frontend_fixes.py`（FUNDLEX_BROWSER_TESTS=1） | 全绿 |
| 浏览器 V1 | `test_v1_frontend_remediation.py` + `test_workbench.py` + `test_tracked_upload.py` + `test_guide_generation.py` | 全绿 |
| 浏览器整批 | 上述 6 文件合跑 | **96 passed / 1 failed**（0:19:50）；唯一失败 `test_real_task_document_deep_links_use_task_scoped_api`（:264 深链合同名可见性）在本次批量前 2 次单跑、批量后 1 次单跑均通过，且整批内相邻两次全跑失败者轮换（prefixed_entry→deep_links）——多线并行 pytest 高负载下的环境抖动，非本线回归 |

diff 统计（前后对比）：V1 调色板 2 套→1 套；字号 px 种数 app.css 25→18、compare.css 18→10、guide_generation.css 9→8；任务详情下载操作 6 按钮混排→独立「交付文件」卡；V2 合同详情下载区由页面最末移至首屏块序第 2；技术泄露点 20+ 处清零（删除或入「高级详情」）；重试话术 9+ 变体→统一；状态标签表 4 份→共享 1 份。

## 五、遗留与交接

- FL-D710..716、FL-D721 已登记；FL-D716 已关闭（验证完成）。观察项（不阻塞）：V2 reason_codes 兜底文案偏强（建议后端返中文 label 根治）；`.hash-value` 死样式低优先清理；Guides 多版本区分度（建议后端列表返 created_at 展示）。
- 下一波建议：①以本 token 层为准出一份轻量设计规范（README 或 tokens.css 注释）；②真实工作台一轮人工走查（本线验证均为自动化，视觉密度未截屏核对）；③合同结果页 review 入口常显化评估（目前需有 redline 才可用，属既有语义未动）。

