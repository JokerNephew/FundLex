# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：c02ae5a04ffbb1a8c63a7408fb3c69fab4f54cd60ff44575f42031ab00e1289b
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 2（A类、C类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 23，已符合 13，不适用 23；计划修改 18
- 审计轮次：1；未决问题 0
- 查漏：块 4，发现 2，未解决 1，缺口 0
- 模型调用：25；估算费用：0.028159800000000002

## 每规则处置

- G01：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S03', 'S04', 'S25']
- G02：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S03', 'S04', 'S25']
- G03：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S04', 'S25']
- G04：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S04', 'S25']
- G05：覆盖 targets_found；目标 5（应改 1 / 已符合 2 / 不适用 2）；审计完成 1/1；章节 ['S04', 'S25']
- G06：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S04', 'S25']
- G07：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G08：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G09：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G10：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G11：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S07', 'S25']
- G12：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G13：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G14：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G15：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S16', 'S25']
- G16：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/4；章节 ['S16', 'S25']
- G17：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 3/3；章节 ['S16', 'S25']
- G18：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17', 'S25']
- G19：覆盖 targets_found；目标 2（应改 0 / 已符合 1 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 targets_found；目标 2（应改 0 / 已符合 1 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 3（应改 2 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 14，结论 21，另报 0，丢弃 2，问题 0

## 查漏轮次

- 第 0 轮：块 4，发现 2，丢弃 2
  - SW001：G05 p138 residual_old_text → resolved
  - SW002：G05 p1162 residual_old_text → pending

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1287：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p821：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G15", "target_id": "Y005", "location": "p821", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [sweep] {"kind": "sweep", "finding_id": "SW002", "rule_id": "G05", "location": "p1162", "source_location": "p1162", "quote": "在法律法规和《基金合同》规定的范围内调整本基金全部或者部分份额类别的申购费率、调低全部或者部分份额类别的赎回费率、调低销售服务费率或变更收费方式；", "issue": "residual_old_text", "reason": "G05 requires deleting '、调低赎回费率' (since a service-fee class exists, it should be changed to '调低销售服务费率'), but the old text '调低全部或者部分份额类别的赎回费率' survives alongside the new '调低销售服务费率'.", "artifact_start": 0, "artifact_end": 73, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [obligation] {"kind": "obligation", "code": "OPEN_OBLIGATION", "rule_id": "G06", "obligation_id": "G06:B1:O1", "operation_id": "G06:0", "branch_id": "B1", "applicability": "TRUE", "failure_class": "TARGET", "reason": "CLAIM_REPLAY_UNPROVEN", "expected_site": "基金的基本情况"}

**交付状态：incomplete**
