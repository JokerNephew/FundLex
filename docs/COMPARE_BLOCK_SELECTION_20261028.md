# Compare 选择版：空侧 insert/delete 与跨段修改（2026-10-28）

## 范围

- 正文普通段落的整段插入/删除
- 正文普通段落的跨段拆分/合并/替换
- 表格单元格内普通段落的插入/删除/跨段修改
- 同一锚点多个插入保持文档顺序

仍失败关闭：

- 整表/整行插入删除
- 合并单元格
- content control、域、drawing、文本框
- header/footer 内容比较

## 实现

- `fundlex/compare/selection.py`：多块差异不再在预览阶段整体阻断，改为非阻塞提示，由 writer 做真实结构校验。
- `fundlex/compare/selection_writer.py`：
  - `_BlockOperation` 描述 block range / anchor；
  - `_build_plan()` 区分 inline modify/insert/delete 与 block insert/delete/replace；
  - `_apply_block_operations()` 在 final 中增删/替换段落，在 redline 中生成段落标记和 run 级 `w:ins`/`w:del`；
  - `_accept_revisions_copy()` 接受修订时处理段落标记，校验“接受全部修订 = final”；
  - `_validate_block_references()` 校验克隆段落引用的 style/rStyle/numId 在左侧包存在，不要求 styles.xml 字节完全相同；
  - 跨段替换允许部分 span，但同一块有其它 diff 时返回 `SELECTION_BLOCK_OVERLAP`。

## 验证

- Compare 全套 **112 passed / 6 skipped**
- 生产 API 小样本三组：
  - 整段插入：final `前文 / 新增整段 / 尾部`，redline 2 处 `w:ins`
  - 整段删除：final `前文 / 尾部`，redline 2 处 `w:del`
  - 跨段拆分：final `abcdX / Yefgh`，redline 4 处 `w:ins` + 2 处 `w:del`
- 生产真实合同：1,417 段 ESG 合同、正文插入 1 段，final 1,418 段、p836 为新增文本、redline 2 处 `w:ins`、final 无残留修订
- 生产浏览器：跨段拆分对，登录→上传→全部采用 B→保存→预览→生成→下载，final `abcdX / Yefgh`，0 页面/控制台错误
- 证据：`/tmp/opencode/fundlex-compare-block-e2e-20261028/`、`/tmp/opencode/fundlex-compare-block-browser-20261028/`

## 发布

- 分支：`codex/compare-selection-group-fix`
- 提交：`429f1bf`（块级支持）、`38861f4`（style 引用校验）
- 生产 SHA-256：
  - `fundlex/compare/selection.py` `3a5a6d393a0ca30f2ffddd8a25d6cde1a8e70ac220142a2f49c8e6261da827e9`
  - `fundlex/compare/selection_writer.py` `2898dcb83420b0bab93cb66057939815bb02afba7c777e16092e319f47642195`
- 重启 `fundlex-recall-api`，active、capabilities 200
- 备份：`/tmp/opencode/fundlex-compare-block-selection-20261028/`

## 后续

整表/整行、合并单元格、content control、域/drawing 和 header/footer 仍不在本次范围；需要另行设计。
