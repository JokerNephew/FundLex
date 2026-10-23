# 合同对比设计

合同对比是独立的只读流水线，入口是工作台的「合同对比」，与现有合同修订任务、指引、模型和 DOCX 写入链路分开。输入仅为 DOCX；后端把每个左右文件对作为显式 `compare_pair` 保存，正文和普通表格文字经 OOXML 解析后比较。比较源头是确定性代码，不调用大模型。

## 解析与对齐

`fundlex.compare.parser` 直接读取 `word/document.xml`，输出 `CompareDocument` 和 `CompareBlock`。每个 block 同时保留 `raw_text`、仅用于配对的 `match_text` 和用于差异的 `diff_text`，并带稳定 block id、正文/表格位置、章节路径和源文件 SHA-256。解析器复用既有 DOCX ZIP/XML 安全边界，但不复用修订引擎的可编辑区域过滤。Hyperlink、普通 content control、正文段落和普通表格单元格纳入；文本框、嵌套表格等可见但未支持结构会产生 `coverage=incomplete` 警告。已有 Word 修订痕迹明确拒绝。

`align.py` 先使用唯一精确 anchor 和 LIS 保持顺序，再对 anchor 间窗口做有限动态规划，允许 1:1、1:N、N:1 和小组 N:N。相似度只决定配对；配对后仍执行字符/token diff，不能把相似当作相同。无法可靠配对时保留删除和新增以保证召回。分组不跨表格单元格。

`text_diff.py` 用保留 offset 的 tokenizer 识别中文字符、英文词、数字、百分号和标点。连续水平空白数量变化按约定忽略；数字、标点、大小写、否定词和百分比变化保留。结果按阅读顺序生成稳定 `D0001`… ID，每项包含左右 block、offset、文字、虚拟 anchor 和可选跨 block spans。

## 持久化、API 与 Worker

`CompareStore` 沿用现有 Database 和对象存储，但使用独立的 `compare_tasks`、`compare_pairs`、`compare_pair_files`、`compare_artifacts` 表；DOCX 正文不放入数据库。结果 JSON 用 `LONGTEXT` 以兼容 MySQL 的长差异列表，SQLite 同样可用。上传前复用完整 DOCX 包校验，入库后按源 SHA-256、对象大小和对象哈希复核。任务有 owner 隔离、Idempotency-Key、显式 left/right、租约和 fencing token；批量 pair 独立失败。

路由：

```text
POST /api/compare/tasks
GET  /api/compare/tasks
GET  /api/compare/tasks/{task_id}
GET  /api/compare/tasks/{task_id}/pairs
POST /api/compare/tasks/{task_id}/uploads
POST /api/compare/tasks/{task_id}/seal
GET  /api/compare/pairs/{pair_id}
GET  /api/compare/pairs/{pair_id}/view
```

`CompareWorker` 独立于 Recall Worker，可用 `.venv/bin/python -m fundlex.compare.worker` 启动，或用 `--once` 处理一个 pair。普通处理异常只关闭当前 pair；结果覆盖不完整时状态为 `incomplete`，不会伪装成完整对比。

部署模板位于 `tools/deploy/fundlex-compare-worker.service.template`。生产发布时安装为 `fundlex-compare-worker.service`，与 compare API 共用同一个 `FUNDLEX_DATA_DIR`、数据库连接和对象存储；发布后与 API、Recall Worker 一起检查状态。Worker 对对象读取和数据库临时故障使用有限重试，租约由 fencing token 保护，过期 Worker 不能提交结果；解析、输入完整性和结果结构错误使用固定错误码并按 pair 隔离。

## HTML 与前端

`render.py` 对所有合同文本先 HTML escape，后端提供稳定 `data-block-id` 和 `data-diff-id`，插入/删除一侧使用虚拟 anchor。`frontend/compare.js` 使用原生 DOM，与现有工作台只共享认证 JSON adapter；双栏独立滚动，差异列表支持点击、上一处/下一处，批量 pair 支持上一组/下一组。SVG 线条由浏览器实际 `getBoundingClientRect()` 计算，在 scroll、resize、ResizeObserver 和 requestAnimationFrame 时重算。文件夹配对按相对路径精确匹配，未配对文件不猜测。

## 测试与已知范围

算法、API、认证、对象完整性、批量失败隔离、恶意文本、确定性、对称性和真实合同 mutation 评测分别测试。冻结语料为20份公开合同、386个 mutation pair（14 dev / 6 holdout）；gold 独立读取 OOXML，不能作为 compare 输出的自证。最终证据保存在 `/tmp/opencode/compare-continuation/`，holdout 中 B14–B19 曾在前一轮暴露，按回归 split 披露。第一版不比较字体、字号、颜色、粗体、行距、页边距、分页、header/footer、footnote、endnote、comment、embedded file 和未支持的 text box；后者会在 coverage 中明确告警。

当前已知分类限制：split/merge 结构变化伴随局部文字修改时，部分对齐会保守退化为整组 delete + insert，字符差异仍保留但 `modify` 粒度下降；该限制记录在 FL-D152，不能用分类优化削弱差异召回。生产部署和正式工作台交付验收本轮未执行。
