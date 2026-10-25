# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：74920e09c398f086091ca2b522c5d3bb0ed574d8ccd8c6e00ecf416b508ba93a
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 3（A、C、D）；销售服务费类别：C；浮动管理费：否
- 目标计数：应改 22，已符合 7，不适用 5；计划修改 14
- 审计轮次：1；未决问题 0
- 查漏：块 4，发现 2，未解决 1，缺口 0
- 模型调用：29；估算费用：0.0258165

## 每规则处置

- G01：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S03', 'S25']
- G02：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S03', 'S25']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S04', 'S25']
- G04：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S04', 'S25']
- G05：覆盖 targets_found；目标 2（应改 1 / 已符合 1 / 不适用 0）；审计完成 1/1；章节 ['S04', 'S25']
- G06：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S04', 'S25']
- G07：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07', 'S25']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G10：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07', 'S25']
- G11：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/2；章节 ['S07', 'S25']
- G12：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S07', 'S25']
- G13：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G15：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S16', 'S25']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/4；章节 ['S16', 'S25']
- G17：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S16', 'S25']
- G18：覆盖 targets_found；目标 2（应改 1 / 已符合 1 / 不适用 0）；审计完成 1/1；章节 ['S17', 'S25']
- G19：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 targets_found；目标 1（应改 0 / 已符合 1 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 14，结论 19，另报 0，丢弃 0，问题 0

## 查漏轮次

- 第 0 轮：块 4，发现 2，丢弃 3
  - SW001：G18 p800 wrong_text → resolved
  - SW002：G18 p1207 residual_old_text → pending

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p772：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1247：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）

## 未完成清单

- [sweep] {"kind": "sweep", "finding_id": "SW002", "rule_id": "G18", "location": "p1207", "source_location": "p1207", "quote": "由于本基金 A 类基金份额和 D 类基金份额不收取销售服务费，而 C 类基金份额收取销售服务费，各基金份额类别对应的可分配收益将有所不同。", "issue": "residual_old_text", "reason": "G18 requires replacing the fee-difference wording with '由于本基金A类基金份额和C类基金份额费用收取不同'. The old clause still enumerates A/D not charging and C charging sales service fee; the required replacement text is absent.", "artifact_start": 0, "artifact_end": 69, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G18", "operation_id": "G18:0", "obligation_id": "G18:B1:O1", "location": "p1207", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [obligation] {"kind": "obligation", "code": "OPEN_OBLIGATION", "rule_id": "G06", "obligation_id": "G06:B1:O1", "operation_id": "G06:0", "branch_id": "B1", "applicability": "TRUE", "failure_class": "TARGET", "reason": "CLAIM_REPLAY_UNPROVEN", "expected_site": "基金的基本情况"}

**交付状态：incomplete**
