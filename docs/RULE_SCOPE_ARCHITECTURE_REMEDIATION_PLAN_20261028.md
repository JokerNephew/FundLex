# 规则作用域架构修复计划（2026-10-28）

> **最新实施方案替代本文件冲突约束**：[修订引擎多阶段执行方案](SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md)。旧版scope接入及测试作为历史基线保留；单叶子first-match、摘要默认排除、把G14/G18笼统挂业务待定等不再作为后续要求。新方案同时保证规则范围内完整覆盖和范围外不改，支持多agent自主执行到真实用户交付。

> **2026-10-28 严格性再审计更正**：下文“景宁可交付／只剩业务适用性”等为历史程序状态，不代表业务完整性。景宁p155实际为正文而非摘要，scope只选第一个叶子漏改，历史complete撤回为业务验收证据（FL-D439）；G14表述2/3已获指引授权，QDII是绑定缺陷而非业务待定（FL-D399）。范围守卫应保留，但范围建立不能由固定标题/编号及first-match独断，查漏必须能指出scope漏选；整改见 [严格性审计](STRICTNESS_DESIGN_AUDIT_20261028.md)。本次只审计，未修复或重新验收。

## 实施状态（2026-10-28 收尾）

- Phase 1–3 已完成：`fundlex/rule_scope.py`、管线全路径接入、Claim Replay/effect/delete residual 接入、scope_audit、规划门禁、G12 相邻 ONE_OF 修复、假 complete 门禁修复。
- D06 真实链路 `/tmp/opencode/d06-rule-scope3-20261028`：`complete`，39 targets / 15 edits / 27 calls / 约 `$0.0295`，Claim Replay verified、open obligations 0、final omission PASS。
- 全量回归 **1803 passed / 13 skipped**；`tests/test_rule_scope.py` 覆盖 D06/QDII/景宁真实 scope。
- Phase 4 第一批 3 份 smoke（同一最终代码、各自新账本）：价值优选 `complete`（`/tmp/opencode/smoke5-fix-value-20261028`）；景宁纯债 `complete`（`/tmp/opencode/smoke5-fix-20261028`）；QDII 仍 `incomplete`，但只剩 G14:3/4/5（“转换费率”，BIZ-02）与 G18（缺少旧 A/C 表述，BIZ-03）4 个业务适用性 open obligation，G15/G16/G17 已 `ARTIFACT_VERIFIED`。三份中 2 份可交付、1 份待业务决定，不是 3/3。
- 未部署生产；固定 D01–D20/holdout、独立 labels/gold、候选冻结仍未完成，项目继续 NO-GO。

## 目标

消除“规则找到不该找的章节/段落”这一类问题，而不是继续为 G06 等单条规则加特判。完成后必须满足：

1. 每条规则只能在自己的**物理叶子小节**内产生候选；模型、survey、append、semantic delete、sweep 全部共用同一作用域。
2. 任何进入规划的 target/edit 都带 `scope_id`，可回溯到 `rule_id → leaf_section → location`。
3. 越界候选必须被丢弃并记录 `OUT_OF_RULE_SCOPE`，不能静默消失。
4. 摘要副本按显式 `copy_key`/`include_summary_copies` 处理，不能按摘要标题猜。
5. D06 p280 必须被排除；G06 只接受 p130–p137；景宁 G04 不得把 p148 费率调整段当作类别定义段。
6. 全量聚焦回归、D06 真实链路、第一批 3 份 smoke 通过；业务适用性问题（G14/G18）仍按业务决定处理，不用 scope 修复掩盖。

## 非目标

- 不解决 G14“转换费率”、G18“无旧表述”等业务适用性问题；这些仍由业务决定。
- 不改固定 D01–D20/holdout manifest、不重写历史 report/labels/gold。
- 不部署生产；生产发布另行按候选冻结和验收流程执行。

## 当前基础与缺口

已有：

- `g06_scope_locations()`：G06 的物理小节特判（p130–p137）。
- `expand_class_definition_scope()`：G04 在基金基本情况没有完整定义时补入释义定义段。
- `rule_locations_for_window()` / `rule_scope_locations()`：inventory/survey/append 的规则级 location 过滤。
- `source_parts_contiguous()` / `_target_source_body()`：复合目标边界。

缺口：

- 没有通用的叶子小节树；`Section` 仍只到“第三部分基金的基本情况”这种大章节。
- G06 仍是专用函数；G15/G16/G17/G18/G19–G22 没有显式摘要副本策略。
- scope 解析没有审计输出；越界候选没有统一 `OUT_OF_RULE_SCOPE` 记录。
- inventory/sweep/audit/coverage 的 scope 传递仍不完全一致。

## 架构

### 1. 叶子小节树

新增 `fundlex/rule_scope.py`：

```python
@dataclass(frozen=True)
class LeafSection:
    id: str
    parent_section_id: str
    title: str
    zone: str                  # body | summary
    heading_level: int
    locations: tuple[str, ...]
    summary_of: str = ""       # summary leaf -> body section identity
    copy_key: str = ""         # normalized clause identity for duplicate copies
```

`build_leaf_sections(inspection, sections)`：

- 遍历 `inspection.paragraphs`，按 `section_path` 和编号标题/大纲样式识别叶子小节。
- 标题识别：中文编号（一、二、……；1、2、……）、短标题、样式/大纲级别；识别不唯一时保留父 section，不猜测。
- 每个段落只归属一个叶子；空段跟随所在叶子。
- 摘要区标记 `zone=summary`；用规范化标题/条款锚点建立 `summary_of` 和 `copy_key`。

### 2. RuleScope

```python
@dataclass(frozen=True)
class RuleScope:
    rule_id: str
    leaf_ids: frozenset[str]
    locations: frozenset[str]
    zone: str
    include_summary_copies: bool
    copy_keys: frozenset[str]
    resolution: str            # resolved | fallback_exact | unresolved
    evidence: tuple[str, ...]
    def contains(self, location: str) -> bool: ...
```

`resolve_rule_scopes(rules, sections, inspection, mapping)`：

- 输入仍用现有 `scope_map` 的 section 级 mapping，但解析到叶子小节。
- 解析优先级：
  1. 显式规则策略（见下）。
  2. `section_hint` 与叶子标题的规范化匹配。
  3. 规则 old_text/requirement 的业务锚点匹配。
  4. 无法唯一解析 → `resolution="unresolved"`，不生成候选。
- 不允许回退到整章/全文；G06 旧 fallback 仅保留精确句子 + 基本情况章节的兼容路径。

显式策略（第一版）：

| 规则 | 叶子范围 | 摘要副本 |
|---|---|---|
| G01/G02 | 释义中的“基金份额类别”定义段 | 默认不包含 |
| G03/G04/G05 | 基金的基本情况中的“份额类别设置”小节 | 默认不包含 |
| G06 | 基金的基本情况中的“份额类别设置”小节；精确 fallback 仅限该章节 | 默认不包含 |
| G07–G14 | 基金份额的申购与赎回中的“申购和赎回的价格、费用及其用途”小节 | 默认不包含 |
| G15/G16/G17 | 基金费用与税收中的“基金销售服务费”小节 | 仅当摘要段落 `copy_key` 与正文条款匹配且 `include_summary_copies=True` |
| G18 | 基金的收益与分配中的收益分配原则段 | 仅当 `copy_key` 匹配 |
| G19–G22 | 基金财产的清算中的“清算剩余资产分配”段 | 仅当 `copy_key` 匹配 |

`copy_key` 由规范化后的业务锚点/旧文生成，不使用章节标题。摘要标题与正文不同不影响 `copy_key`；只有条款 identity 匹配才可作为副本。

### 3. 统一 ScopeGuard

在 `fundlex/recall.py`/`recall_pipeline.py` 中：

- `scope_locations_for_window(window, scopes)`：替换 `rule_locations_for_window` 的 section 级计算。
- `scope_locations(scopes)`：替换 `rule_scope_locations`。
- inventory：模型返回的每个 target 先过 `scope.contains(location)`；越界项写入 `scope_audit.dropped`。
- survey/append recovery：`allowed_locations` 使用 `scope_locations`。
- semantic delete/ensure_delete：只扫描 `scope.locations`。
- sweep：`rule_locations` 使用 scope；sweep finding 的 location 不在 scope 内直接丢弃。
- audit/coverage：只审计 scope 内的 target；越界 target 不能成为 unresolved 证据。
- 规划前最终门禁：`target.scope_id` 必须存在且 `scope.contains(target.location)`；否则 `RECALL_TARGET_OUT_OF_SCOPE`。

### 4. Scope 审计

报告新增：

```json
"scope_audit": {
  "rules": [
    {"rule_id": "G06", "leaf_sections": ["S04:11"],
     "locations": ["p130", "..."], "resolution": "resolved",
     "accepted": 2, "dropped": [{"location": "p280", "reason": "OUT_OF_RULE_SCOPE"}]}
  ],
  "unresolved_rules": []
}
```

门禁：

- `resolution="unresolved"` 的规则不得产生计划编辑。
- 任何 edit 无 `scope_id` 或 location 越界 → 失败关闭。
- 报告/结果页显示 scope 解析和越界丢弃摘要，便于业务复核。

## 阶段与工作流

### Phase 0：基线（主 agent）

- 记录当前 HEAD、dirty 状态、现有 scope 函数和测试基线。
- 建立本计划、证据目录、预算（如需真实 smoke）。

### Phase 1：核心 RuleScope（Agent A）

- 新增 `fundlex/rule_scope.py`、`tests/test_rule_scope.py`。
- 不改 `recall.py`/`recall_pipeline.py`。
- 交付：LeafSection、RuleScope、resolver、显式策略、单元测试。
- 验收：p280 在 G06 范围外；p130–p137 在范围内；摘要 copy_key 正反例；G04 释义/基本情况选择。

### Phase 2：管线集成（Agent B）

- 在 `fundlex/recall.py`/`recall_pipeline.py` 接入 `RuleScope`。
- 替换 `rule_locations_for_window`/`rule_scope_locations` 的 section 级路径。
- 加 scope_audit、越界丢弃、规划前门禁。
- 保留旧函数兼容包装，避免一次性删除公共 API。
- 交付：集成代码、定向测试、报告字段。

### Phase 3：回归与边界（Agent C）

- 新增 `tests/test_rule_scope_integration.py`：
  - D06 p280 越界丢弃，G06 p130–p137 接受。
  - 景宁 G04 p148 不接受；p120 仅在策略允许时接受，否则 unresolved。
  - 摘要 p1286–p1289：copy_key 匹配才接受；标题不同不自动接受。
  - 近似关键词跨章节（p280）不进入候选。
  - inventory/survey/append/sweep 四条路径一致。
- 运行聚焦套件和完整回归。

### Phase 4：真实链路与交付（主 agent + Agent D）

- 用新账本/证据目录跑 D06 真实模型链路；核对 scope_audit、final/redline、Claim Replay、报告/哈希。
- 跑第一批 3 份 smoke；确认不再出现“正确正文目标不可编辑”或“越界章节候选”。
- 更新 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`、`docs/ACTIVE_HANDOFF.md`、`docs/BUSINESS_ISSUES_FROM_TESTS.md`。
- 交付：代码、测试、真实运行证据、业务问题状态；不宣称业务适用性问题已解决。

## Agent 分工

- **Explore Agent**：只读梳理所有 scope 调用点和报告字段，返回精确文件/函数/行号。
- **Agent A（general）**：核心 `rule_scope.py` + 单元测试；只改新文件。
- **Agent B（general）**：管线集成；在 A 完成后串行执行，避免与 A 冲突。
- **Agent C（general）**：集成回归测试；在 B 完成后执行。
- **Agent D（general）**：文档/业务问题/交接更新；在测试结果后执行。
- **主 agent**：计划、审查、合并、冲突处理、完整回归、真实 smoke、最终交付。

## 验收标准

1. `pytest` 聚焦套件全通过；新增 scope 测试覆盖越界、摘要副本、G04 双位置、四条召回路径。
2. D06 scope_audit 显示 p280 `OUT_OF_RULE_SCOPE`，G06 只含 p130–p137。
3. 景宁 G04 不再把 p148 当作类别定义；无正确叶子时 `RULE_SCOPE_UNRESOLVED`。
4. 摘要副本只有 copy_key 匹配才进入 target；否则丢弃并记录。
5. 真实 D06 `delivery_status=complete` 或明确列出非 scope 的业务/执行问题；不能把越界目标算作 unresolved 业务证据。
6. 第一批 3 份 smoke 不再出现“正文目标因 bookmark/章节误配不可编辑”；剩余问题分类为业务/执行。
7. 文档登记 FL-D 编号、计划、证据路径和当前 NO-GO 边界。

## 风险与约束

- 指南 `section_hint` 较粗，叶子标题识别可能不唯一；解析失败必须 fail-closed，不能回退全文。
- 摘要标题与正文标题可能不同；copy_key 必须基于业务条款 identity，不能基于标题。
- 修改共享文件时只允许 Agent B 串行编辑；A/C/D 使用新文件或只读。
- 不改变固定 D01–D20/holdout manifest；不重写历史 labels/gold。
- 真实 smoke 需要新账本和预登记 cap；历史账本不能复用。
