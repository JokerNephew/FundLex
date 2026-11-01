# FL-D899 附录·登记项明细（qa-frontend-v2 树，2026-11-01）

主条目见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` FL-D899；普查全文见 `docs/frontend/V2_AUDIT_20261101.md`（逐页四关+证据图编号）。本附录承载本批**登记不动工**项，供主线/裁决线消费。

## 登记-裁决

1. **令牌档案增补档位**：`.brand` 20px、`.compare-viewer-title strong` 19px、`.stat-value` 等大字号现裸值；建议 `DESIGN_TOKENS_20261101.md` 增补 `--text-display`（19–20px 档）后统一收编，避免本批就近套 16/24 令牌引视觉漂移。证据：app.css 字号扫描。
2. **app.css 其余直色值收编**：全文直色值扫描 153 处，本批已收编 UI chrome 点（`.identity/.nav-group/.sidebar-note/.compare-pair-number/.compare-summary-stat/.compare-sync-note/.compare-reader-label/.compare-side-badge`、移动端导航 10px→`--text-2xs`）。其余集中于 compare 内部分区底色/语义色（如 `.compare-direction-note #fff8f3/#ead8ca/#684a35`、`.compare-coverage.is-incomplete #fff9e8/#e5c774/#73520d`、`.compare-columns #f7f8f9` 等）与 compare-word 文书区（按设计不动）。需审计归并为语义令牌族（surface-warm/warning-soft 等）后统一收编，本批不一刀切。
3. **CompareCard 元信息字段名**：META_LABELS 含 `parser_version→解析器版本`、`schema_version→结构版本`、`source_sha256→原件摘要`，字面已汉化但「解析器/结构版本」仍偏技术；是否整体隐去元信息变化清单待主线裁决（默认保留，有信息价值）。证据：Guides/CompareCard.tsx:19-24,96-102。

## 登记-IA（归 FL-D891/896 统筹，不动工）

4. **任务入口双轨**：`/tasks`（任务总览）与 `/tasks/detail`（任务详情索引）双列表内容高度重叠，导航「工作区」分组下并列；建议合并为单入口+页内视图切换。
5. **导航分组错配**：「合同对比」在工作区组，「修改指引/模型配置/设置」在配置组，与用户使用频率/心智（先指引后任务）存在错配；归信息架构重构统筹。

## 第二轮（2026-11-01 全覆盖令·只读复审计）

- 产出：`docs/frontend/V2_COVERAGE_SIGNOFF_20261101.md`——按 `docs/COVERAGE_MATRIX_20261101.md` 对 V2 10 页面域 + 50 文件（矩阵 49 + 自产 lib/issueText.ts）逐项签认，零遗漏。
- 新发现 18 项编号 V2M-01～V2M-18（裁决级 3 / 直接修建议级 7 / 登记观察级 8），全文见签认表第三节；本轮只读未改代码，修复待下轮令。

## 第三轮（2026-11-01 第二棒：矩阵签认 + V1/V2 双标清查）

- **矩阵签认**：主线 `docs/COVERAGE_MATRIX_20261101.md` A 节 V2 10 域 + B 节 49 文件行全部 ☐→✅+发现编号（ComparePage.tsx 行标注主线重构去向，继任 4 文件逐行补签）。
- **双标清查**：FL-D880~896 口径逐项对标（分页/徽标/外泄/小字/验证文案/系统状态/结果页/下载词典/查看器词典/行内操作），结论与证据见签认表 4.2；**V2 无「V1 已修而 V2 落后」硬伤**，跨线提示 V1 侧 3 项欠债（CSV 原始原因码列/下载词典自相矛盾/compare.html kicker 未扫）。
- **本轮修复（令牌级/词典级，全绿）**：V2M-02 `--accent*`→`--brand*` 6 处、V2M-03 两处 10px→`--text-2xs`、V2M-19 kicker 词典统一（对照结果/原合同/改后的合同）、V2M-10 CompareListPage 徽章传原始码。tsc 0 / vitest 24/24 / build ✓ / 浏览器对比查看器用例 PASS。
- **新登记**：V2M-19（已修）、V2M-20（sanjin 表1 解释句残留 5 处，待裁决）、V2M-21（shared.tsx 两处未映射码原文回显，V2M-01 同族）。

## 第四轮（2026-11-01 晚：FL-D991 下拉框组件替换）

- **选型**：联网调研（npm registry 实据）@headlessui/react 2.2.10（依赖 5）vs @radix-ui/react-select 2.4.1（依赖 ~20）vs @floating-ui/react（仅定位）vs antd 6.6.8（死依赖零引用）→ Headless UI Listbox，理由一句话已报主线备案，对比与体积代价（gzip +33.4 kB）记入 API 文档。
- **实施**：新组件 `components/ui/Listbox.tsx`（泛型 value 直传/键盘可达/表单安全/无匹配首项兜底）；`.ui-listbox*` 并入控件令牌矩阵（app.css 状态矩阵收编 button，新增 `--shadow-overlay` 令牌）；16 处用法全量替换（Tasks 4/TaskDetail 4/Users 1/NewTask 1/shared 2/CompareCard 2/ModelSettings 2），旧 `Select.tsx` 删除、`.ui-select*`/`.control-select` 死样式清零（grep 实证零残留）。
- **测试**：vitest +8 项（tests/listbox.test.tsx）；浏览器锚点 2 处随 FL-D991 有意升级（`select_option` → button+option，选项面板 Portal 到 body 需 page 级定位）。
- **四闸**：tsc 0 / vitest 32 项全绿 / build ✓ / 浏览器 3 用例 PASS。
- **交接**：`docs/frontend/LISTBOX_COMPONENT_API_20261101.md`（API + 样式契约 + V1 集成说明，V1 集成归 FE 线）；集中册立 FL-D991 条目。

## 第五轮（2026-11-01 夜：FL-D991 总攻收口——语义补强+前后对照截图+完工报告）

- **语义补强**（commit 825cd36）：vitest +3 项（aria 矩阵 haspopup/expanded/selected+焦点落 listbox、label 包裹命名=「状态」（与原生 select 语义等同，修初稿断言）、axe.run 零违规），vitest 35/35。
- **license 联网核实**：headlessui/radix-select/floating-ui 全 MIT（npm registry 实据），兼容性无碍。
- **前后对照截图**：`c03af74` 独立 worktree+同 node_modules 构建 pre-dist，同机同服务同视口拍摄，证据 9 张存 `docs/frontend/evidence/listbox-20261101/`（桌面 tasks/models 前后、打开面板、键盘焦点、移动 390px 前后+打开）。拍摄坑位：pre 版原生 select 的 option 文本为 hidden 需 `state="attached"`；label 包裹场景 button 可访问名=「状态」非值文本。
- **完工报告**：`FL_D991_COMPLETION_REPORT_20261101.md`（U1/U2 用户原话断言表+T1~T4/W1~W3 工单要求断言，全 ✅）。
- **无新发现问题**，无需申请 FL 号段；**质检子agent 环境无工具可派**（如实申报，已申请主线补派，见报告 §3）。

## 验证口径说明（本批直接修的验证）

- tsc --noEmit 0 错；vitest 6 文件 24 项全绿；vite build 成功。
- after 截图 `/tmp/opencode/qa/shots-v2-after/`（01/03/04 列表修复实证；22/23 查看器 kicker）对比 `/tmp/opencode/qa/shots-v2-audit/` before。
- python 浏览器全套回归（FUNDLEX_BROWSER_TESTS=1, FUNDLEX_AUTH_MODE=dev）结果待补录于主条目。
- V2 frontend tests 与 python 浏览器测试对本批改动字符串（资格/目标/服务已连接/指引快照/干净/遗留/比较的文档）无锚点；`stats-connection/stats-empty` data-testid 无引用，文案已改、结构保留。
