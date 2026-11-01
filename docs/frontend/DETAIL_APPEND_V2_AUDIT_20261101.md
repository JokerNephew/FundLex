# FL-D899 附录·登记项明细（qa-frontend-v2 树，2026-11-01）

主条目见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` FL-D899；普查全文见 `docs/frontend/V2_AUDIT_20261101.md`（逐页四关+证据图编号）。本附录承载本批**登记不动工**项，供主线/裁决线消费。

## 登记-裁决

1. **令牌档案增补档位**：`.brand` 20px、`.compare-viewer-title strong` 19px、`.stat-value` 等大字号现裸值；建议 `DESIGN_TOKENS_20261101.md` 增补 `--text-display`（19–20px 档）后统一收编，避免本批就近套 16/24 令牌引视觉漂移。证据：app.css 字号扫描。
2. **app.css 其余直色值收编**：全文直色值扫描 153 处，本批已收编 UI chrome 点（`.identity/.nav-group/.sidebar-note/.compare-pair-number/.compare-summary-stat/.compare-sync-note/.compare-reader-label/.compare-side-badge`、移动端导航 10px→`--text-2xs`）。其余集中于 compare 内部分区底色/语义色（如 `.compare-direction-note #fff8f3/#ead8ca/#684a35`、`.compare-coverage.is-incomplete #fff9e8/#e5c774/#73520d`、`.compare-columns #f7f8f9` 等）与 compare-word 文书区（按设计不动）。需审计归并为语义令牌族（surface-warm/warning-soft 等）后统一收编，本批不一刀切。
3. **CompareCard 元信息字段名**：META_LABELS 含 `parser_version→解析器版本`、`schema_version→结构版本`、`source_sha256→原件摘要`，字面已汉化但「解析器/结构版本」仍偏技术；是否整体隐去元信息变化清单待主线裁决（默认保留，有信息价值）。证据：Guides/CompareCard.tsx:19-24,96-102。

## 登记-IA（归 FL-D891/896 统筹，不动工）

4. **任务入口双轨**：`/tasks`（任务总览）与 `/tasks/detail`（任务详情索引）双列表内容高度重叠，导航「工作区」分组下并列；建议合并为单入口+页内视图切换。
5. **导航分组错配**：「合同对比」在工作区组，「修改指引/模型配置/设置」在配置组，与用户使用频率/心智（先指引后任务）存在错配；归信息架构重构统筹。

## 验证口径说明（本批直接修的验证）

- tsc --noEmit 0 错；vitest 6 文件 24 项全绿；vite build 成功。
- after 截图 `/tmp/opencode/qa/shots-v2-after/`（01/03/04 列表修复实证；22/23 查看器 kicker）对比 `/tmp/opencode/qa/shots-v2-audit/` before。
- python 浏览器全套回归（FUNDLEX_BROWSER_TESTS=1, FUNDLEX_AUTH_MODE=dev）结果待补录于主条目。
- V2 frontend tests 与 python 浏览器测试对本批改动字符串（资格/目标/服务已连接/指引快照/干净/遗留/比较的文档）无锚点；`stats-connection/stats-empty` data-testid 无引用，文案已改、结构保留。
