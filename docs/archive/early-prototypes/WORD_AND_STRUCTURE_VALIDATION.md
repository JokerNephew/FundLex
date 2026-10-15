# Word 与 DOCX 结构独立验收

日期：2026-10-13。依据《FundLex_技术方案_详细设计_v1》§7、§11。仅本地 DOCX；无 PDF、历史转换、模型调用、规则修改或 Git 提交。

## 可复现命令

在 `D:\Desktop\FundLex` 的 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/corpus_audit.py --census-only --output var/evaluation/structure_census.json
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/corpus_audit.py
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/corpus_audit.py --metadata-only
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/word_fixture.py
pwsh -NoProfile -File tools/evaluation/word_acceptance.ps1
```

## 514 份原始 DOCX 独立普查

使用 ZIP 只读读取与 namespace-aware XML 查询独立枚举，并逐文件保存读取前后 SHA-256。首轮普查 27.87 秒，514/514 原文件 hash 未变。

|特征|文件数|次数|
|---|---:|---:|
|TOC 域代码|501|501|
|目录标签（可含标签内部空白）|509|509|
|表格|50|196|
|含费用关键词的表格|20|60|
|文本框|7|304|

历史 501/20/7 全部重现。费用表定义：连接表格后代 `w:t` 并移除空白，命中申购费、赎回费、销售服务费、管理费、费率任一；普通和嵌套表格均枚举，文件只计一次。这是结构命中数量，不代表表格可写或目标规则可适用。

持久证据：`var/evaluation/structure_census.json` 包含全部文件名、原文件前后 hash 及逐文件特征计数。`--census-only` 明确不执行生产 parser，`NOT_RUN_CENSUS_ONLY` 表示未运行，不能解释为 parser 失败。

完整生产 parser 专项于同日完成，514/514 `inspect_docx(full=True)` 通过，错误 0，耗时 445.16 秒，514/514 源文件前后 SHA-256 相同。独立 XML 扫描先枚举复杂 `fldChar` 开始/结束域区间、`fldSimple`/`sdt` 后代文字、目录标签和文本框后代文字；再解析生产 parser 的每个可写 segment 的 `node_paths` 回到原 XML，检查实际节点祖先及域范围。文本框、目录、域或内容控件的越界可写命中均为 0。全部 20 个费用表格文件及 7 个文本框文件均包含于该全量结果。

早期完整审计记录 `has_toc_field=true` 为 513 份，当时该标志把静态目录标签也计入；独立 XML 的真实 TOC 域计数始终为 501。随后核心修正该元数据，仅实际 TOC 域产生 `has_toc_field=true`，静态目录仍只读保护。冻结核心后，使用 `--metadata-only` 重新核验早期误报的全部 12 份静态目录合同和 2 份真实 TOC 域合同：12/12 静态目录返回 false，2/2 真域返回 true，14/14 源 hash 不变且区域分类计数与完整审计相同。固定 Word 夹具含真实 TOC 域，仍返回 true，源 hash 为 `b3d868fb17943974cf5d4be479f03b3c72ea67f4d135b6d621a3c63f934e87ab`，与 Word 自动验收输入记录相同。

补充证据在 `var/evaluation/toc_metadata_revalidation.json`；没有重新执行全量结构审计，也不把早期 513 当作当前字段计数。完整逐文件结构保护结果保留于 `var/evaluation/structure_audit.json`。此处的解析通过不代表所有段落可写，unsupported 区域继续只读。

## 固定模板编辑夹具及 Word 自动验证

夹具由独立脚本生成，未复用核心测试夹具或任何模型输出。源文件、固定模板、5 个 edit manifest、修订版、最终版及 Word 接受修订版均保存在 `var/evaluation/word_fixture/`。覆盖跨 run（相邻粗体/斜体）、普通表格、正文、摘要、TOC 只读拒绝、保留原生换行并插入模板换行、append 零宽追加；保留非目标重复文本、表格另一 cell、附录、页眉与页脚。

生产编辑器包校验、修订校验、最终版等价、非目标与固定模板文本断言全部通过。独立 XML 比对 8 个非目标段落 canonical XML 相同，所有非主文档部件字节相同；源 hash 未变。TOC 修改请求明确以 `REGION_NOT_EDITABLE` 拒绝，跨原生换行替换以 `EDIT_CROSSES_BARRIER` 拒绝，输出 `toc_update_status=not_updated`。

本机 Microsoft Word COM `Version=16.0`、`Build=16.0.14334` 隐藏打开 source/redline/final 成功。源文件及最终版均 0 条 Word revisions；修订版 9 条，作者均为 `FundLexAcceptance`，接受后 0 条。manifest 5 个 edit 对应 10 个 OOXML 修订节点；零宽 append 的空删除节点在 Word 中不计为可见 revision，故 Word 9 条与 manifest 不矛盾。

接受本次修订后 `Document.Content.Text` 与最终版逐字相同；`StoryRanges` 的全部 7 个故事实例（1:0、7:0、9:0、12:0、13:0、15:0、16:0）逐字相同；非主故事与源文件相同。所有非目标 token 校验通过。source/accepted/final 的 Word TOC 数均为 1，未更新目录。Word 自动验收前后 source/redline/final 三份输入文件 SHA-256 均保持相同。性能修复后的生产编辑器已重新生成夹具并重新运行上述 Word 验收。

持久结果：`fixture.json`、`word_acceptance.json`、`word_accepted_stories.json`、`word_final_stories.json`、`word_accepted.docx`。此自动验证证实 Word 打开及接受修订文本兼容性；`manual_visual_inspection=false`，未执行人工视觉抽检，不能据此声称页面布局、表格视觉或字体外观人工验收通过。
