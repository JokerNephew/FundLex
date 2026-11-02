# EN3·外来修订稳健性：全路径审计 + 测试矩阵覆盖断言表（2026-11-02）

用户亲令（2026-11-02）：「合同修订对带修订痕迹的合同也要能稳健的修改，这个要充分的测试检验和优化」「这是最新版的合同样本，要重点测试，不只是针对这两个任务，是全局的要求」
用户裁决（2026-11-02 落地）：策略锁死 **B（保留原痕叠加）**——原产品部修订红字与我方修订红字两层并存、各自可独立接受/拒绝；**产品面不暴露开关**（锁死单一行为，accept-first 生产默认已废除）。

## 〇、锁死 B 的生产接线（新增，随裁决落地）

- `recall_pipeline` 任务输入的「先接受拍平」规整化**已拆除**（废除 2026-10-31 产品决定）：带痕合同直接进入 overlay 通道
  （`inspect/validate/generate(allow_existing_revisions=True)` 本就在场），原始痕迹字节级进交付；
  overlay 不能诚实承载的形状（move 系列/trPr 行标记）在摄入即 typed fail-closed（语料 0 命中）。
- 报告迹：`tracked_input_strategy="preserve_overlay"` + 外来清单（count/authors/items）；`base_had_tracked_changes`
  不再置真（selective 历史拍平报告兼容分支保留）；`source_revision_manifest` 由生成校验自带的
  外来清单下落（既有接线 :6554 未动）。上传侧 `has_tracked_revisions` 仍为纯探测。
- 双层隔离锚点（写手自证 + 独立复核）：我方 `w:id` 从全包（含页眉/脚注/批注）最大 id 向上取奇起步，
  奇 del/偶 ins+1 成对，与外来 id 空间不相交；清单按 (part,kind,id,author,date,content_sha256) 六元组绑定。
- 受影响测试已按新契约跟进：`test_docx_tracked_input.py` 管道 E2E 三例改写（保留双层、锚点不落外来节点、
  reject-all 恢复+原痕不动、selected-final 与 final c14n 全等）；`test_docx_overlay_contract.py` 契约同批。

## 〇.一、锚点语义硬实证（用户承诺口径，产品部 32 份逐格）

工具 `tools/en3/anchor_semantics_report.py`（独立推导，非引擎自评）；证据
`docs/engine/en3/evidence/anchor_semantics_20261102.json`：**PASS 30/30 + 2 份 documentProtection 边界**。

| 检查项（每格逐份通过数/30） | 语义 | 结果 |
|---|---|---|
| anchor_accept_view_coords | 锚点按接受原痕后文本视图定位：plain[s:e]==expected_old（`_accepted_offsets` 显式换算）| 30/30 |
| anchor_outside_foreign_nodes | 我方 del/ins 直接挂段落、无任何外来修订祖先——绝不插在原 w:ins/w:del 节点中间 | 30/30 |
| final_pure | 接受全部后成品零修订标记 | 30/30 |
| accept_all_equals_final_c14n | accept-all(redline) 与 final 逐 part c14n 全等（引擎外靠 `compare.revisions._accept_revisions` 独立复算）| 30/30 |
| final_text_equals_reference | final 全文 == 源接受视图全文 + 编辑施加（全文拼接序独立再推导；结构已由前格锁死）| 30/30 |
| layer_reject_restores_foreign_intact | selective 全部拒绝我方 → 我方成对消失+原文恢复+外来六元组清单逐项不变 | 30/30 |
| layer_default_equals_final_c14n | selective 默认（全接受我方）→ selected_final 与 final c14n 全等 | 30/30 |
| id_namespace_isolated | w:id 命名空间隔离：我方⊥外来、奇偶成对、全文唯一 | 30/30 |
基线：FL-D924 已修（`_pair_revisions` 以 manifest 为准，commit 6afc165 在主线 qa 树就位，本树 HEAD=1b18847 含之），不重复开挖奇偶配对。

## 一、全路径审计（DOCX 摄入 → 段落 span → 编辑落点 → 输出写回）

### 0. 双轨现状（实测事实）

| 轨 | 入口 | 外来修订去向 | 产品部 32 份实测（修复前） |
|---|---|---|---|
| A 保留原痕+叠痕（overlay） | `inspect_docx/validate_edit_plan/generate_artifacts(allow_existing_revisions=True)` | 原样保留在 redline，final 全接受 | **摄入 1/32 通过**（nested-revision / paragraph-or-row-mark 整机拒入）|
| B 先接受再改（任务规整化） | `normalize_tracked_base`（recall_pipeline 主链） | 全部接受拍平，产物仅我方修订 | 30/32 通过（2 份 DOCUMENT_PROTECTED 正当拒入）|
| C 先拒绝再改 | **能力缺失**（docstring 明示"intentionally not offered"）| — | — |

处置策略三格中两格残缺：A 轨在真实语料上基本不可用（31/32 拒），C 轨无实现。

### 1. 语料事实（references/source/产品部修改后，32 份，glob 需 recursive——目录嵌套一层）

- document.xml 合计 w:ins=2775 / w:del=1044；台账锚定值已固化为测试断言。
- 形状分布（Full XPath 父链统计）：**pPr/rPr/ins 873 处、pPr/rPr/del 231 处（31/32 文件）**；**嵌套修订仅 ins>del 一种形状 45 处**；rPrChange 47 / pPrChange 8（其中 5 个快照内含标记）；move/range/cell 标记 0；trPr 行标记 0；非主 story（页眉页脚）修订 0；sectPr+删段标冲突 0。
- 2 份带 documentProtection（广发恒裕、广发稳信）——通用防护守卫正当拒入，编入边界行。

### 2. 发现与处置（全部机制面，无一处样本特判）

| 编号 | 发现 | 根因 | 处置 | 反例/验证 |
|---|---|---|---|---|
| FL-D1003 | A 轨摄入对 Word 合法形状整机拒入（31/32） | `_validate_overlay_structure` 把段落标记修订与嵌套 ins>del 一律按"拓扑变化"拒绝 | **opaque-region 放宽**：段落标记（pPr/rPr 祖父链）与嵌套 ins/del 视为不可入编辑的元数据区；trPr 行标记与 move 仍 fail-closed（语料 0 命中，边界写明）。投影天然已正确（ins 计文字禁写/del 占零坐标），清单哈希覆盖外层即覆盖内层 | `tests/test_docx_overlay_contract.py` 两条旧策略断言改写为新契约（含 trPr/move 仍拒的反突变断言）；语料 32/32 摄入 |
| FL-D1004 | C 策略（先拒绝）能力缺失 | 仅 accept 投影实现 | `compare/revisions._reject_revisions`（accept 的单点镜像：ins/moveTo 摘子树、del 解包+delText→t、段落标插入=合并（与接受删除同构复用 `_join_marked_paragraphs`）、行/单元格插入摘行、属性变更从快照回滚+快照内陈旧标记剥离、cellMerge fail-closed）；`normalize_tracked_base(disposition=)`，生产主链默认 accept 不变 | 合成四形状 accept/reject 镜像断言 + **语料 32 份与独立参照实现全文字流全等比对**（非子串抽查） |
| FL-D1005 | 拒绝视图 mutation 网 | — | 后置 `_validate_package(full=True)` 天然捕获任何残留标记 | mutation 测试：`_reject_revisions` 变异为空操作 → normalize 必须抛（已入套件） |
| FL-D1006 | 跨区编辑（跨越外来 del）在 validate 期被吞（except DocxError: pass），`generate_artifacts` 才整机爆——逐编辑归罪机制 `_drop_unvalidatable_edits` 对几何类失效**结构性失灵**（一次模型越界 → 整份合同陪葬） | `validate_edit_plan` 959-965 故意吞几何错误，与自身 docstring「同一几何实现，双方同判」矛盾；写手与验证实际同谓词，吞错只换挡不挡事 | 移除吞错，验证期即抛原码（书签配对检查保持）| 跨区格测试断言 validate 期 fail-closed；既有 200 项相关测试 0 回归；`_drop_unvalidatable_edits` 既有行为不依赖被吞错误（其归罪用例即为自己 validate 抛错路径）|
| FL-D1007 | A 轨写回整体验证坐标系坍塌：外来**段落标删除**在 accepted 树里物理合并段落，`p{n}` 键整体位移；生成校验用 plan 的原树 location 键查 accepted 树 → NON_TARGET_STRUCTURE_CHANGED/FINAL 系误报，凡编辑点位于任一删段标之后必炸（修复前语料 22/32 写回失败） | 生成校验骨架/非目标/文本/格式四套检查以 accepted 树承载原树坐标 | **原树锚定**：写手已证明不改拓扑（manifest+非目标双重断言），所有 location 键检查改锚原树（original vs redline 原树 c14n/文本/格式三方对拍）；final 与 accept-all(redline) 的 c14n 全等检查不动，结构/文本保证沿等式传导；格式检查在「仅沉降我方 id」的克隆上恢复 run 级断言（外来 wrapper 由清单 c14n 防篡）| 语料 32 份写回 33 格全绿；合成同形状回归（clean/flush-adjacent-del/header）|

### 3. 如实记录的残余边界（非缺陷，fail-closed 或明示降级）

- 段落含外来 ins 文字的**同段格式断言**降级为空等（双侧 revision 区 segments 抽成 None 恒等）；外来内容本体由 inventory c14n 防篡，我方替换文本格式由 manifest REVISION_TEXT_MISMATCH + 干净段 format 断言共同覆盖。
- trPr 行标记、move 系列、cellMerge 拒绝视图回滚仍拒入/拒平（语料 0 命中）；sectPr 段落标合并沿用既有 `REVISION_PARAGRAPH_MERGE_UNSUPPORTED`。
- 2 份 documentProtection 合同全策略拒入（守卫正确）。
- 生产主链策略（2026-11-02 用户裁决，锁死）：**B 保留原痕叠加**为唯一生产行为，无产品面开关；引擎层
  `normalize_tracked_base(disposition=accept|reject)` 能力保留供测试/评测/未来裁决使用，不接线生产。

## 二、矩阵覆盖断言表（83 项测试 ≡ 83 格；✅=测试函数 ↔ 格一一对应）

### 输入形状 × 摄入（test_intake_*）

| 形状 | 摄入(overlay) | 取舍断言 |
|---|---|---|
| 段落标 ins（pPr/rPr） | ✅ `test_intake_admits_word_native_shapes[para_mark_ins]` | 无旗标仍整机拒（同测试内）|
| 段落标 del | ✅ `[para_mark_del]` | 同上 |
| 嵌套 ins>del | ✅ `[nested_ins_del]` | 文字投影=「保留的插入」|
| 相邻 ins+del | ✅ `[adjacent]` | — |
| 跨段落删除（文本 del×2 + 段落标 del） | ✅ `test_intake_cross_paragraph_deletion` | — |
| 页眉 story 外来修订 | ✅ `test_header_part_foreign_marks_writeback` | 写回后页眉字节含原痕 |
| move/range/trPr（反突变边界） | ✅ overlay_contract 两测试内嵌拒断言 | 放宽不得过界 |

### 处置策略（test_strategy_*）

| 形状 | 先接受 | 先拒绝 | 镜像语义 |
|---|---|---|---|
| 段落标 ins/del、嵌套、相邻 | ✅ `test_strategy_accept_and_reject_are_mirrors` ×4 | ✅ 同 | 插入现/隐、删除隐/复原文 |
| 跨段落删除 | ✅ `test_strategy_cross_paragraph_deletion` | ✅ 同 | 接受=合并；拒绝=分段+原文恢复（含原文断言）|
| 属性变更 | ✅ `test_strategy_property_change_reject_restores_snapshot` | ✅ 同 | 接受=新值 240；拒绝=快照回滚 120 |
| 干净输入 | ✅ `test_strategy_clean_input_identity` 双 disposition 字节恒等 | — | 异常 disposition 抛 ValueError |
| 语料 30/32（2 份防护除外） | ✅ `test_corpus_intake_and_strategies` ×30 | ✅ ×30 | **与独立参照实现全文全等**；零件残留清零断言；防护 2 份按文档自声明推导 DOCUMENT_PROTECTED |

### 修改落点 × 输出完备性（test_location_* / battery）

| 落点 | 判定 | 输出完备性电池（10 项：python-docx 重开×2、part 集合相等、delText 必有 del 祖先、我方 id 奇 del/偶 ins、与外来 id 不相交、全文唯一、外来清单 c14n 保全、selective 单对拒后原痕不减、final 零修订、写回确定性字节一致）|
|---|---|---|
| 干净区 | ✅ `test_location_clean_region_full_battery` | 全项 |
| 修订区内（外来 ins 内） | ✅ `test_location_inside_foreign_insertion_fails_closed` | 码族 fail-closed |
| 跨区（跨越外来 del） | ✅ `test_location_spanning_foreign_region_fails_closed` | F4 后验证期即拦 |
| 紧邻外来 del（坐标映射） | ✅ `test_location_flush_after_foreign_del_maps_offsets` | 全项 + 替换后文字精确断言 |
| 语料 30 份写回 | ✅ `test_corpus_writeback_with_stacked_marks` ×30（2 防护 skip） | 全项逐份 |

### mutation 反例

| 变异 | 期望 | 测试 |
|---|---|---|
| 摄入守卫被拔除（伪造跨区 segment 直攻 `_edit_region`） | 写路径外来祖先防护仍必须 fail-closed（纵深不依赖单点）| ✅ `test_mutation_intake_guard_neutered_depth_guards_still_fire` |
| `_reject_revisions` 退化为空操作 | 后校验网捕获残留标记 | ✅ `test_mutation_noop_reject_implementation_caught_by_net` |
| selective 裁决落到外来 id（manifest 错位） | SELECTION_UNKNOWN_REVISION | ✅ `test_mutation_foreign_identity_cannot_be_hijacked` |
| 摄入放宽过界（move/trPr 混入） | 仍 EXISTING_REVISION_STRUCTURE_UNSUPPORTED | ✅ overlay_contract 新契约内嵌 |

### 真实语料事实锚 + 真实模型验证

| 项 | 断言/留证 |
|---|---|
| 语料事实锚 | ✅ `test_corpus_inventory_matches_dispatch_facts`：32 份、ins 2775 / del 1044 |
| 真实模型（FL-D445，无上限） | `tools/en3/real_model_probe.py` 对 ESG(97 外来痕)+中证A50(111 外来痕) 各一次真实 `generate_clause` → 模型文本经 content_source=generated 验证 → 生成 → 全电池 + selective 拒回 + 两视图规范化：**双 PASS**。账本：`docs/engine/en3/evidence/real_model_probe_20261102.json`（2 calls / 2397 tokens / $0.0009549，观测非门禁）|

## 三、出厂口径（S2）

- fc=0：矩阵 83 格 0 失败（2 skip=防护边界，防护判定由文档自声明推导而非名单）；完工前以定版全量回归读数为准（见状态文件）。
- 读实际产物：battery 全部以 python-docx 真读 DOCX + zip part 级断言；final 与 accept-all(redline) c14n 全等即「Word 打开无修复提示」的结构保证（python-docx 双开为零修复代理）。
- 机制面证明：四处改动均落在通用抽象层（摄入白名单谓词、规范化镜像、验证吞错移除、校验锚定坐标系）；无任何按文件名/费率文本/样本条件的分支。
- 留史：本文件 + evidence JSON + 状态文件 `/tmp/opencode/qa/status/qa-engine-tracked.md`。
- 编号说明：发现已由总指挥 2026-11-02 派定正式号段 **FL-D1003~FL-D1007**（映射顺序 EN3-F1..F5；FL-D1007=坐标错位根级缺陷，标最高危）；集中册登记见 [DETAIL_APPEND_EN3](../DETAIL_APPEND_EN3.md)。施工版本 cbcf3cc 起；完工=矩阵 83 格全绿 + 定版全量回归 **2802 passed / 145 skipped / 0 failed** + 真实语料 32 份过机证据 + 真实模型双 PASS。
