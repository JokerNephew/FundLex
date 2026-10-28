# Compare 选择版连续修改段修复（2026-10-28）

## 问题

Compare 选择版在用户逐项采用 A/B 后生成新 DOCX。两份文档有连续多个修改段落时，对齐会把多个 `modify` 放入同一个 alignment group（例如 `G0001` 含 2 个左块、2 个右块）。`selection_writer` 原先要求每个 `modify` 的组形状为 `(1,1)`，因此生成返回 `409 SELECTION_STRUCTURAL_DIFF_UNSUPPORTED`，用户无法生成选择版/修订版。

## 修复

`fundlex/compare/selection_writer.py` 新增 `_modify_group_compatible()`：

- 允许左右块数相等且块序号一一对应的 `modify` 组（覆盖 2 个、3 个连续修改段）。
- 每个 diff 仍必须落在单个块内，不能跨段。
- 左右块数不等、跨序号映射、多块 span、`insert`/`delete` 仍失败关闭，不放开结构修改。
- 同一段的多个不重叠修改继续由现有 overlap 检查约束。

新增回归：连续两个修改段混合选择、同一组两个修改都采用右侧。

## 验证

- `tests/test_compare_selection_writer.py` **8 passed**
- selection 套件 **20 passed / 1 skipped**
- Compare algorithm/API **37 passed**
- 生产 API 小样本真实路径（连续两个修改段）：
  - 第一处采用右、第二处采用左：final `0.30%` / `0.10%`，redline 1 处 `w:ins` + 1 处 `w:del`，final 无残留修订；
  - 两处都采用右：final `0.30%` / `0.08%`，redline 2 + 2，final 无残留修订；
  - 四类产物（selected_final、selected_redline、选择报告 JSON/Markdown）均下载成功。
- 证据：`/tmp/opencode/fundlex-compare-selection-e2e-20261028/production-selection-e2e.json`、`production-selection-e2e-all-right.json`
- 发布备份/SHA：`/tmp/opencode/fundlex-compare-selection-fix-20261028/`

## 发布

- 分支：`codex/compare-selection-group-fix`
- 提交：`426892d fix(compare): support consecutive modify selections`
- 生产文件：`/opt/fundlex-recall-first/fundlex/compare/selection_writer.py`
- 生产 SHA-256：`53c6cfd1339119989911917c202bbff13964ec0deab572a1eff8e5426c320e6c`
- 重启：`fundlex-recall-api.service`（active，capabilities 200）

## 后续

- 浏览器点击路径和真实合同选择路径已于 2026-10-28 完成，见 [`COMPARE_SELECTION_REAL_CONTRACT_20261028.md`](COMPARE_SELECTION_REAL_CONTRACT_20261028.md)。
- 空侧 `insert`/`delete`、跨段联合修改、合并单元格等结构差异仍按设计阻断。
