# 带既有修订痕迹 DOCX 的叠加修订设计（2026-10-28）

状态：**核心垂直切片已实现（投影/写入/最终接受/上传放行），嵌套修订与前端/真实E2E未完成**。作者默认值按用户 2026-10-28 指示改为“资金清算部”。

## 1. 需求与不变量

上传的 DOCX 可能已由其他部门留下 Word 修订痕迹（`w:ins`/`w:del` 等）。要求：

1. **保留**原有修订痕迹，不擅自接受、拒绝或抹掉；
2. 在其当前状态之上**叠加** FundLex 的修订；
3. 两类修订**可区分**（作者、界面筛选、报告清单）；
4. 原有文件字节不变，产物可复核、可回滚；
5. 规则范围外不改、不借叠加扩权（延续既有业务边界）。

必须同时成立的三向等价：

| 检查 | 期望 |
|---|---|
| 接受 redline 的全部修订 | 等于 `final.docx` |
| 只拒绝 FundLex 作者的修订 | 等于“接受输入中全部既有修订”后的视图（即对方部门当前稿） |
| 拒绝 redline 的全部修订 | 等于输入文件的原始基线（对方修订前） |
| 输入文件 | 字节级未修改，SHA-256 与上传一致 |

第三条与第二条不同：输入带修订时，“分析基线”是对方接受后的视图，而“原始基线”是拒绝后的视图，不能混用。

## 2. 现状与差距

- `fundlex/docx.py::inspect_docx` 默认 `allow_existing_revisions=False`，遇到 `REVISION_TAGS` 直接 `EXISTING_REVISION_UNSUPPORTED`。
- `_project()` 把修订内容视为屏障：`revision_content`、不可写、段落 `zone=revision`，因此既有修订文本既不进入模型分析，也不能编辑。
- `_apply_one()` 只处理普通 `<w:r>`，删除包 `<w:del>`、插入包 `<w:ins>`，作者/日期/ID 由本次运行生成；尚无“避开既有修订节点”或“在既有插入内部再修订”的能力。
- `_accept_our_revisions()`/`_validate_revision_manifest()` 已能只接受“我们 manifest 中的 ID”，这是三向校验的良好基础。
- `fundlex/compare/revisions.py` 已有“接受全部既有修订”的成熟实现（含表格、段落标记、move、属性变更），可复用其语义作为分析基线与校验参照，但**不能直接把输入改写成已接受文件**，否则丢失原有痕迹。

## 3. 核心设计

### 3.1 双视图投影

扩展 `_project()`（新增 revision-aware 模式）同时产出：

| 视图 | 规则 | 用途 |
|---|---|---|
| `accepted_text` | 包含 `w:ins`/`w:moveTo` 内容，排除 `w:del`/`w:moveFrom`/`w:delText` | 模型分析、目标定位、偏移量 |
| `base_text` | 排除 `w:ins`/`w:moveTo`，包含 `w:del` 原内容 | 写回时定位原始 XML、构造拒绝视图 |

每个 `accepted_text` 字符带一个 `RevisionContext`：

```text
node_path, run_kind(normal|foreign_ins|our_ins|foreign_del|move_to|move_from),
author, revision_id, editable(bool), barrier_reason
```

约束：

- `foreign_del` 不进入 `accepted_text`，因此模型不会把已删除内容当作现行条款；
- `our_ins` 表示上次 FundLex 已改过，默认**拒绝再次处理**（见 3.5 幂等）；
- 段落标记本身被修订（`w:pPr/w:rPr/w:del`）时，接受视图会合并段落；投影必须按“接受后”的段落边界重建 location，同时保留原始物理地址映射，否则跨段偏移会错位；
- 表格单元格、页眉页脚、文本框按现有结构能力分别标记可见/可写；不可写的既有修订只进入清单，不进入编辑。

### 3.2 编辑映射与作者区分

`_apply_one()` 增加 revision-aware 分支：

1. 目标区间全部落在 `normal` 文本：沿用现有做法，`<w:del>` + `<w:ins>`，作者为 FundLex。
2. 目标区间包含 `foreign_ins` 文本：
   - 首选：在对方 `<w:ins>` 内部放我们的 `<w:del>`（嵌套修订），实现“我们删除/改写对方新增的内容”，接受后消失、拒绝对方修订后回到原始基线；
   - 若 Word/WPS 往返验证不通过，或结构不允许嵌套：**不静默展平**，该目标标为 `FOREIGN_INSERTION_EDIT_UNSUPPORTED`，交付为未完成并列出位置，等待人工处理；
   - 绝不把对方 `<w:ins>` 直接改成普通文本后冒充“无冲突”。
3. 目标区间落在 `foreign_del`：不可见，不产生目标；若模型误报，按越界拒绝。
4. 目标跨越 `normal` 与 `foreign_ins` 边界：拆成多个物理操作，但作为一个业务修改单元审批；每段保留各自作者上下文。
5. 目标落在 `moveTo`/`moveFrom`、属性变更、域、SDT 等结构：沿用现有结构边界；能读不能写的明确报告，不静默跳过。

作者与标识：

- 作者名按用户指示默认 **“资金清算部”**，可配置；若与输入中既有作者同名，自动追加运行标识，保证 Word“特定人员”筛选可区分。
- 日期使用本次运行时间；`w:id` 从输入中现有最大值之后分配，避免与既有修订冲突。
- 报告中同时记录作者、日期、修订 ID，支持按作者筛选。

### 3.3 产物定义

| 产物 | 内容 | 说明 |
|---|---|---|
| `final.docx` | 接受**全部**修订（既有 + FundLex） | 等于“对方当前稿 + 我们的修改” |
| `redline.docx` | 保留既有修订，叠加 FundLex 修订 | 两类作者可区分；不修改既有节点 |
| `report` | 既有修订清单 + FundLex 修改清单 + 冲突/未完成项 | 既有修订不冒充我们的修改 |
| 原输入 | 不覆盖、不改字节 | 下载/复核均以原件哈希为准 |

如业务还需要“仅 FundLex 修改的干净稿”，可另加 `final_ours_only.docx`（接受我们的、保留对方的），但默认不增加产物数量，避免混淆。

### 3.4 校验

在现有包级/结构级校验之外新增：

1. 接受全部 → `final` 文本与结构等价；
2. 仅拒绝 FundLex 作者 → 与 `accept_all(输入)` 等价（用 compare/revisions 的接受逻辑作参照）；
3. 拒绝全部 → 与输入原始基线等价；
4. 既有修订节点：作者/ID/日期/内容与输入一致（未被改写）；数量与清单一致；
5. 我们的修订：作者唯一、ID 不冲突、只出现在批准范围内；
6. 范围外文本（含对方修订）守恒；
7. 表格/页眉页脚/特殊结构：接受/拒绝往返一致，或明确列为不支持。

### 3.5 幂等与重跑

- 输入已含 FundLex 作者修订：默认拒绝并提示“该文件已由 FundLex 修订”，避免叠加两层我们的痕迹；管理员可显式允许“继续修订”，此时以“接受我们的旧修订 + 保留对方修订”为新基线，并记录来源。
- 同一任务重跑从**原始上传件**重新生成，不在上次 redline 上叠加。
- 断点恢复必须绑定输入哈希、作者、修订 ID 区间，避免重复分配 ID。

## 4. 接口与数据

新增/扩展字段（目标契约，名称可调整）：

```text
DocumentInspection.revision_mode = none | foreign | mixed | ours
DocumentInspection.revisions = [{revision_id, kind, author, date, location, accepted_text}]
Target.revision_context = normal | foreign_ins | mixed | unsupported
EditPlan.author, revision_id_range, foreign_overlap
ArtifactValidation.three_way_equivalence, foreign_revisions_preserved, author_separation
```

上传/API：

- 默认接受带既有修订的 DOCX，不再返回 `EXISTING_REVISION_UNSUPPORTED`；
- 响应中返回既有修订数量、作者列表、可处理性预检（是否有不可写结构/同名作者/已含 FundLex 修订）；
- 前端在任务详情显示“检测到 N 处既有修订（作者：…），FundLex 修订将以‘…’作者叠加”，下载页区分 final/redline/report；
- 受保护文档、数字签名、严格 OOXML 仍拒绝，不因本需求放宽。

## 5. 分阶段实施

| 阶段 | 内容 | 退出条件 |
|---|---|---|
| R1 投影 | revision-aware `_project`，双视图 + 字符级上下文；接受后段落边界 | 单元测试：既有 ins/del、段落标记、表格、跨段 |
| R2 写入 | 作者/ID 分配、嵌套修订、边界拆分、unsupported 报告 | 往返测试：接受/拒绝三向等价 |
| R3 校验/报告 | 三向等价、既有修订守恒、作者分离、清单 | 合成 fixture 全绿 |
| R4 上传/前端 | 解除拒绝、预检、提示与下载标签 | API + 页面测试 |
| R5 真实样例 | 用真实“带修订合同”跑通，Word/WPS 打开核对 | 实际产物复核，不以 report 代替 |
| R6 回归 | 无修订合同全部旧测试、全量回归、真实 E2E | 不回归现有交付 |

## 6. 风险与待验证点

1. **嵌套修订的 Word/WPS 兼容性**：`<w:ins>` 内嵌 `<w:del>` 的渲染与接受/拒绝行为需真实 Word 与 WPS 双端验证；不通过则走“明确未完成”，不静默降级。
2. **段落标记修订**：删除段落标记会合并段落，location/offset 映射必须按接受后视图重建，否则 Claim Replay 会错位。
3. **同名作者**：对方作者可能也叫 FundLex；必须自动区分，不能只靠作者名判断“我们的修订”。
4. **既有修订 ID 冲突**：必须扫描全包最大 ID，跨 part 统一分配。
5. **表格/页眉页脚/文本框**：现有结构能力有限，先保证“可见 + 明确不可写”，不承诺全部可编辑。
6. **性能**：双视图与字符级上下文会增加内存；长合同需按段落增量构建，不复制整包 XML。
7. **验收口径**：三向等价必须基于实际 DOCX 重读，不能只看 report；接受/拒绝后的文本与结构都要比对。

## 7. 建议的默认业务口径（待确认）

- `final` = 接受全部修订；`redline` = 双方修订并存；不额外生成“仅我方”版本（需要时再加）。
- 对方插入内容被我们改写时：优先嵌套修订；不支持则**阻断该目标并报告**，不静默接受对方插入。
- 已含 FundLex 修订的输入默认拒绝重跑；管理员显式允许时才继续。
- 既有修订只作为“当前状态”，不重新判定其业务对错；我们的规则仍按指引判断，范围外不动。

以上为设计，不含实现。下一步应先做 R1 投影与合成 fixture，验证双视图和段落标记，再决定嵌套修订是否可作为默认路径。
