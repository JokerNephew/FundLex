# W3 接管线 DETAIL 附录（待主线派号）

纪律：新发现的问题**先向主线申请 FL 号段再登记**，本附录不自封编号。
申请对象：主线。下文每条附【拟请派号】。

关联冻结物：labels `423c6944…` / verification `3d71bd33…` / selection `32b36f02…` / boundary `17037021…`。
证据目录：`docs/evidence/w3-reverify/`（batch-1..5.json、summary.json、defect-diffs.md、sample-pack.*）。

## F-1【拟请派号】第二波标签辅助引文层 10 处保真瑕疵（9 组，金标层零伤）

- 层级：`rule_coverage[].evidence_quote`（解释/证据辅助层，评分不消费；targets 层 1254 条经
  分句原子查真 + `old_text_sha256` + `paragraph_text_sha256` 双重哈希复验**零缺陷**）。
- 清单（逐条 diff 见 defect-diffs.md）：
  1. W2D11/W2D74/W2H15 G05（3 案，target 覆盖条）：引文模板混入「、基金合同的约定」+「，经与基金托管人协商一致」，
     合同原文无此语（ratio≈0.87）。**实质掺入**。
  2. W2D33/W2D41/W2D66 G09（3 案，target 覆盖条）：引文「当日**对应份额类别的**基金份额净值」，
     原文为「当日该类/当日基金份额净值」（ratio≈0.86-0.88）。**实质掺入**（疑指引模板回流）。
  3. W2D39 G13（satisfied 覆盖条）：「在**指定**媒介上公告」vs 原文「在**规定**媒介上公告」，一词之差。
  4. W2D43 G16（satisfied 覆盖条）：引文带「（2）」编号前缀（不在文本层）且 paragraph_index=858 指向无关段。
  5. W2D51 G15（target 覆盖条）：「代收，**按**相关合同规定」未带省略号跳读（原文「代收，**注**册登记机构收到后按…」）。
  6. W2H25 G14（target 覆盖条）：「基金份额赎回**费**和」vs 原文「赎回费**率**和」，单字脱落。
- 影响判定：分母/金标/评分零影响（三案 G05 的 target old_text 本身逐字验证通过，站点真实存在）；
  但「evidence_quote 保真」口径被局部夸大，下游若消费引文层（如 review、对外证据引用）需知。
- 建议：第二波引擎运行前不必重冻 labels（金标无修）；瑕疵按观察项入册，第三波标注器 prompt 加
  「引文禁止改写/编号层文字」禁令 + 收尾器对 evidence_quote 跑同款分句原子查真。
- 检出方式：W3 独立重验（工具与 W2 verifier 零共享），5 批输出 + summary 在本树。

## F-2【拟请派号】schema 口径文档与实现的字段漂移（观察项）

- `docs/evidence/labels-schema-second-batch-20261031-v1.md` §3 列 targets 含 `provenance` 字段，
  实测 1254 条 target 无此字段（模型/收尾来源以 finalize 惯例清单与 review 记录承载）。文档漂移，非数据缺陷。
- 建议：主线统一修文档或登记口径注记。

## F-3【备查】货币市场 3 案（W2D52/W2D67/W2D71）裁 eligible=true 的计费含义

- 盲读裁「本指引适用范围」并给出 10/7/8 条目标（W2D52/W2D67/W2D71；与 boundary explicit_exclusion 清单一致）。
- 与选样 stratum「exclusion-money-market（明确排除类型）」存在语义张力：排除类型样本被盲读翻转为应改。
- 本线不裁决业务对错，仅揭示：评分时若引擎按排除处理，将与此三案标签冲突——**建议主线在运行令中指定裁决口径**。
  （口径文档已述「不预先剔出分母」，但 eligible 翻转后的预期目标计数处理未见明文。）
