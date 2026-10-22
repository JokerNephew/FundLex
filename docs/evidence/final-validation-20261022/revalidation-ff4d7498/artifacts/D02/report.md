# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：c02ae5a04ffbb1a8c63a7408fb3c69fab4f54cd60ff44575f42031ab00e1289b
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 2（A、C）；销售服务费类别：C；浮动管理费：否
- 目标计数：应改 23，已符合 12，不适用 7；计划修改 16
- 审计轮次：4；未决问题 0
- 查漏：块 4，发现 4，未解决 2，缺口 0
- 模型调用：35；估算费用：0.03701984999999999

## 每规则处置

- G01：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S03', 'S25']
- G02：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S03', 'S25']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S04', 'S25']
- G04：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S04', 'S25']
- G05：覆盖 targets_found；目标 3（应改 2 / 已符合 0 / 不适用 1）；审计完成 1/2；章节 ['S04', 'S25']
- G06：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S04', 'S25']
- G07：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07', 'S25']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G10：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07', 'S25']
- G11：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S07', 'S25']
- G12：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G13：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G15：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S16', 'S25']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16', 'S25']
- G17：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 4/4；章节 ['S16', 'S25']
- G18：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17', 'S25']
- G19：覆盖 targets_found；目标 2（应改 0 / 已符合 1 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 targets_found；目标 2（应改 0 / 已符合 1 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 3（应改 2 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 13，结论 20，另报 1，丢弃 0，问题 3
- 第 1 轮（incremental）：规则 2，结论 6，另报 0，丢弃 0，问题 1
- 第 2 轮（incremental）：规则 1，结论 1，另报 0，丢弃 0，问题 1
- 第 3 轮（incremental）：规则 1，结论 1，另报 0，丢弃 0，问题 0

## 查漏轮次

- 第 0 轮：块 4，发现 4，丢弃 7
  - SW001：G05 p138 residual_old_text → resolved
  - SW002：G12 p229 residual_old_text → pending
  - SW003：G13 p229 residual_old_text → pending
  - SW004：G18 p848 wrong_text → resolved

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p821：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1287：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G12", "target_id": "S03_S04_S07_S16_S17_S20#1:T016", "location": "p229", "reason": "RECALL_PLAN_COMPONENT_DROPPED", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G13", "target_id": "S03_S04_S07_S16_S17_S20#1:T017", "location": "p229", "reason": "RECALL_PLAN_COMPONENT_DROPPED", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G15", "target_id": "Y012", "location": "p821", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [sweep] {"kind": "sweep", "finding_id": "SW002", "rule_id": "G12", "location": "p229", "source_location": "p229", "quote": "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用归入基金财产的比例依照相关法律法规设定，具体见招募说明书的规定，未归入基金财产的部分用于支付登记费和其他必要的手续费。其中，对持续持有期少于 7 日的投资者收取不低于 1.5% 的赎回费，并全额计入基金财产。", "issue": "residual_old_text", "reason": "G12 requires replacing this clause with “赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用全额计入基金财产。”. The old text survives: it still says “赎回费用归入基金财产的比例依照相关法律法规设定，具体见招募说明书的规定，未归入基金财产的部分用于支付登记费和其他必要的手续费。其中，对持续持有期少于 7 日的投资者收取不低于 1.5% 的赎回费，并全额计入基金财产。” instead of the required full-inclusion wording.", "artifact_start": 0, "artifact_end": 147, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [sweep] {"kind": "sweep", "finding_id": "SW003", "rule_id": "G13", "location": "p229", "source_location": "p229", "quote": "其中，对持续持有期少于 7 日的投资者收取不低于 1.5% 的赎回费，并全额计入基金财产。", "issue": "residual_old_text", "reason": "G13 requires deleting “本基金对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并将上述赎回费全额计入基金财产。”. The equivalent short-holding-period redemption fee sentence still survives in the clause (“对持续持有期少于 7 日的投资者收取不低于 1.5% 的赎回费，并全额计入基金财产”), so the required deletion has not been carried out.", "artifact_start": 103, "artifact_end": 147, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G06", "operation_id": "G06:0", "obligation_id": "G06:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G12", "operation_id": "G12:0", "obligation_id": "G12:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G12", "operation_id": "G12:1", "obligation_id": "G12:B1:O2", "location": "p229", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G13", "operation_id": "G13:0", "obligation_id": "G13:B1:O1", "location": "p229", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}

**交付状态：incomplete**
