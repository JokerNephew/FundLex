# Compare 选择版真实合同与浏览器路径验收（2026-10-28）

## 范围

完成 Compare 选择版的剩余验收：

1. 真实合同选择路径：完整 ESG 基金合同（1,417 段），正文两处连续修改。
2. 生产浏览器路径：登录 → 新建比对 → 上传左右 DOCX → 全部采用 B → 保存 → 预览 → 生成 → 下载 final/redline。
3. 修复真实合同因 header/footer 覆盖警告被整体阻断的问题（FL-D442）。

## FL-D442 修复

`selection_writer.generate_selection_artifacts()` 原先要求左右 coverage 均为 `complete`，真实合同通常有非空页眉/页脚，因此直接返回 `SELECTION_COVERAGE_INCOMPLETE`。现在：

- 不再因全局 coverage 警告整体拒绝；
- 警告保留为 artifact `limitations`，写入选择报告；
- 每个选择仍逐操作校验单块 body/table paragraph、run/field/drawing/合并单元格/content control 等结构；
- final/redline 重新读取并核对文本与修订接受等价；
- 报告明确列出 header/footer 未覆盖，不宣称全文完整。

## 真实合同验收

- 左：`funds_word/基金合同第一批/广发ESG责任投资混合型证券投资基金基金合同.docx`（128,805 字节，1,417 段）
- 右：同合同复制件，正文 p831/p832 连续两处 `1.20%` → `1.00%`
- Compare：2 处 `modify`，同一 `G0599`，coverage `incomplete`（header/footer）
- 选择：两处均采用右侧
- 生成结果：
  - final p831/p832 为 `1.00%`
  - final 段落数 1,417，与原合同一致；页眉保留
  - redline 2 处 `w:ins` + 2 处 `w:del`
  - final 0 处残留修订
  - 报告包含 header/footer 警告
- 证据：`/tmp/opencode/fundlex-compare-real-contract-20261028/production-real-contract-e2e.json`
- 文件：同目录 `selected_final.docx`、`selected_redline.docx`、`selection_report.md`

## 生产浏览器验收

- 视口 1440×900，Chromium headless
- 登录 → `#compare` → 新建任务 → 上传真实合同左右文件 → 等待 Worker → 全部采用 B → 自动保存 → 预览 → 生成 v1 → 下载
- 页面错误 0、控制台错误 0
- 下载 final：1,417 段，p831/p832 为 `1.00%`，页眉保留，0 残留修订
- 下载 redline：2 处 `w:ins` + 2 处 `w:del`
- 证据：`/tmp/opencode/fundlex-compare-browser-20261028/browser-e2e.json` 与 `browser-selected-final.docx`、`browser-selected-redline.docx`、7 张截图

## 测试与发布

- Compare 全套：**106 passed / 6 skipped**
- 分支：`codex/compare-selection-group-fix`
- 提交：`426892d`（连续修改组）、`85c8e42`（coverage 警告）
- 生产 `selection_writer.py` SHA-256：`4b62a0601a4554b09338d794473d2d1ecd663e4fb60e0ef1c3a789cf453360ba`
- 发布备份：`/tmp/opencode/fundlex-compare-selection-fix-20261028/`、`/tmp/opencode/fundlex-compare-selection-coverage-20261028/`
- 已重启 `fundlex-recall-api`，active、capabilities 200
- 临时账号、任务、对象和凭据文件已清理

## 仍未支持

- 一侧为空的 insert/delete
- 跨段联合修改
- 合并单元格等复杂结构
- header/footer 内容本身纳入比较（当前只作为覆盖例外保留）
