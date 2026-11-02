# 细节问题与处理记录·EN3 附录（修订痕迹轨）

> 本附录为 EN3 线自有登记册，编号 FL-D1003~1007 由总指挥 2026-11-02 派定（映射 EN3-F1..F5，
> 其中坐标错位根级缺陷=FL-D1007，标最高危）。主线合并集中册时按并集并入，本附录不删历史。
> 详见审计与矩阵断言表：[EN3_FOREIGN_REVISIONS_20261102.md](engine/EN3_FOREIGN_REVISIONS_20261102.md)；
> 施工版本：`qa-engine-tracked-20261102`（cbcf3cc 起）。

## FL-D1003 外来修订摄入对 Word 合法形状整机拒入（overlay 轨真实可用性）

- 发现：2026-11-02。影响：A 轨（保留原痕+我方叠痕）对产品部人工修订语料基本不可用。
- 证据：`inspect_docx(allow_existing_revisions=True)` 对 references/source/产品部修改后 32 份实测 31 份抛
  EXISTING_REVISION_STRUCTURE_UNSUPPORTED（nested-revision / paragraph-or-row-mark），仅 1 份通过；
  形状普查：段落标修订 pPr/rPr/ins 873、del 231（31/32 文件），嵌套 ins>del 45 处。
- 处理：`_validate_overlay_structure` 改 opaque-region 白名单——段落标修订（rPr 祖父链=pPr）与嵌套
  ins/del 视为不可入编辑的元数据区；trPr 行标记与 move 系列维持 fail-closed（语料 0 命中，边界写明）。
- 状态：**已修复已验证**。验证：语料摄入 1/32 → 32/32；overlay_contract 两条旧策略断言按新契约改写
  （内嵌 move/trPr 仍拒的反突变断言）；定版全量回归 2802/0。
- 下一步：收口线并入主线时抽查 overlay_contract 两测试的新旧断言差异。

## FL-D1004 「先拒绝再改」规范化能力缺失

- 发现：2026-11-02。影响：处置策略三格缺一；docstring 明示 rejected-view「intentionally not offered」。
- 处理：`fundlex/compare/revisions._reject_revisions`（accept 单点镜像：ins/moveTo 摘子树、
  del 解包+delText→t/delInstrText→instrText、段落标插入合并复用通用化 `_join_marked_paragraphs`、
  行/单元格插入摘行、属性变更从快照回滚+快照内陈旧标记剥离、cellMerge fail-closed）；
  `normalize_tracked_base(disposition=accept|reject)`，生产主链默认 accept 未动。
- 状态：**已修复已验证**。验证：合成四形状镜像断言；跨段删接受=合并/拒绝=分段+原文恢复；属性快照
  回滚 240→120；语料 30/30 两视图与独立参照实现全文全等；2 份 documentProtection 正当拒入。
- 变更记录（2026-11-02 用户裁决落地）：**生产锁死 B（保留原痕叠加）**，无产品面开关；recall 主链
  废除「先接受拍平」输入规整化，带痕合同直接进 overlay 通道；`disposition` 能力层保留不接生产线。
  锚点语义 32 份硬实证 PASS 30/30（docs/engine/en3/evidence/anchor_semantics_20261102.json）。
- 下一步：收口线并入；监督线验收界面双层呈现可读性（html_view 已按 FL-D924 配对）。

## FL-D1005 拒绝视图正确性此前无独立验证网

- 发现：2026-11-02。影响：新增拒绝镜像若无独立断言，退化即静默错文。
- 处理：测试层独立参照实现（对源 document.xml 施加极简变换）与引擎输出**全文流全等比对**，
  覆盖嵌套/标记全形状；后置 `_validate_package(full=True)` 作为残留标记捕获网；
  mutation 反例：`_reject_revisions` 变异为空操作时 normalize 必须抛 DocxError（已入套件）。
- 状态：**已修复已验证**（随 FL-D1004 同批：test_strategy_* / test_mutation_noop_reject_implementation_caught_by_net /
  test_corpus_intake_and_strategies ×32）。
- 下一步：无；后续拒绝语义扩展（move/cellMerge）沿用同一验证网。

## FL-D1006 validate 吞几何错误导致逐编辑归罪机制对几何类失效结构性失灵

- 发现：2026-11-02。影响：模型编辑跨越外来修订区时，`validate_edit_plan` 旧实现吞 DocxError
  放行，`generate_artifacts` 生成期才整机爆——一次越界编辑整份合同陪葬，
  既有 `_drop_unvalidatable_edits` 降级对几何类失效永远不触发。
- 根因：validate 内 try/except DocxError: pass（原注释「几何错误留到生成期」），与该函数自身
  docstring「同一几何实现，验证与写手双方同判」矛盾；写手与验证实为同一 `_edit_region` 谓词，
  吞错不产生任何可通过的编辑，只换挡。
- 处理：移除吞错，验证期即抛原码（书签配对检查置后保持）；recall 管线的逐编辑归罪恢复设计意图。
- 状态：**已修复已验证**。验证：跨区格断言 validate 期 fail-closed；既有 FL-D112/D568 归罪测试、
  docx/selective/overlay 定向 200 项 0 回归；鑫裕书签残半案实测归罪生效（候选落点跳过错开）。
- 下一步：无。

## FL-D1007 写回校验坐标系坍塌：段落标删除致 accepted 树 p{n} 全位移（根级，最高危）

- 发现：2026-11-02。影响：**凡编辑点位于任一外来段落标删除之后，overlay 写回必炸**
  NON_TARGET_STRUCTURE_CHANGED（前置触发）/FINAL 系误报尾随——产品部语料 22/32 写回失败，
  即「带痕合同无法稳健修改」的工程根因。
- 根因：外来 pPr/rPr/del 在 accepted 树物理合并段落，段落序号整体位移；`generate_artifacts`
  的骨架/非目标/文本/格式四套检查用 plan 的原树 location 键查 accepted 树，坐标错位。
- 处理：校验改**原树锚定**——写手保拓扑已有 manifest+非目标双重断言，全部 location 键检查锚
  original↔redline 原树（c14n/文本/格式三方对拍）；final 与 accept-all(redline) 的 c14n 全等检查不动，
  结构/文本正确性沿等式传导；格式检查在「仅沉降我方 id（外来 wrapper 不动）」的段内克隆上恢复
  run 级具体断言。
- 如实边界：含外来 ins 文字的同段格式断言降级为空等（双侧 revision 区恒等）；外来内容本体由
  inventory c14n 防篡、我方替换由 manifest REVISION_TEXT_MISMATCH + 干净段格式断言覆盖。
- 状态：**已修复已验证**。验证：语料写回 30/30 全格绿（修复前 22/32 失败）；合成 clean/紧邻 del/
  页眉回归；真实模型 ESG(97 外来痕)+中证A50(111 外来痕) 双 PASS（账本
  docs/engine/en3/evidence/real_model_probe_20261102.json，2 calls/2397 tok/$0.0009549，FL-D445 观测口径）。
- 下一步：主线 S2 抽验重点格=test_corpus_writeback_with_stacked_marks 任抽 3 份重放
  （树内 references/source 语料经符号链接就位，主线树实物目录下本测试自动全量执行）。
