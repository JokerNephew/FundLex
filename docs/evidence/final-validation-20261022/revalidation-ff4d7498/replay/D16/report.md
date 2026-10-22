# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：8beacaba3446f7e7e6db1d8cdd3036f0eb086139d6e89a9d27e3552ec658e45d
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 2（A类、C类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 26，已符合 13，不适用 0；计划修改 14
- 审计轮次：4；未决问题 5
- 查漏：块 4，发现 3，未解决 2，缺口 0
- 模型调用：45；估算费用：0

## 每规则处置

- G01：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/1；章节 ['S03']
- G02：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S03']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S04']
- G04：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S04']
- G05：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S04']
- G06：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/4；章节 ['S04']
- G07：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G10：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07']
- G11：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G12：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/2；章节 ['S07']
- G13：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/2；章节 ['S07']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G15：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S16']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16']
- G17：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 1/3；章节 ['S16']
- G18：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17']
- G19：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20']
- G20：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20']
- G21：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20']
- G22：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20']

## 审计轮次

- 第 0 轮（full）：规则 13，结论 21，另报 0，丢弃 2，问题 7
- 第 1 轮（incremental）：规则 3，结论 6，另报 0，丢弃 1，问题 3
- 第 2 轮（incremental）：规则 2，结论 3，另报 1，丢弃 1，问题 5
- 第 3 轮（incremental）：规则 3，结论 6，另报 0，丢弃 2，问题 5

## 查漏轮次

- 第 0 轮：块 4，发现 3，丢弃 3
  - SW001：G05 p133 residual_old_text → resolved
  - SW002：G12 p221 wrong_text → pending
  - SW003：G13 p221 residual_old_text → pending

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1306：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p822：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G12", "target_id": "S03_S04_S07_S16_S17_S20#1:T014", "location": "p221", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "S03_S04_S07_S16_S17_S20#1:T019", "location": "p823", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G13", "target_id": "Y007", "location": "p221", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G12", "target_id": "T3001", "location": "p219", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [audit] {"kind": "audit", "code": "AUDIT_VERDICT_MISSING", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "failure_class": "VERIFICATION"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G12", "target_id": "S03_S04_S07_S16_S17_S20#1:T014", "location": "p221", "verdict": "wrong", "reason": "The p221 clause was not replaced; the old proportional-allocation and registration-fee wording remains, contradicting the requirement to replace it with '赎回费用全额计入基金财产'.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "G12: replace redemption fee clause with full inclusion in fund property"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "S03_S04_S07_S16_S17_S20#1:T019", "location": "p823", "verdict": "wrong", "reason": "G17 requires deleting the sales service fee usage clause at p823-p824, but AFTER still contains the full clause unchanged.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "G17:0 delete sales service fee usage clause"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G13", "target_id": "Y007", "location": "p221", "verdict": "wrong", "reason": "G13 requires deleting the sentence about charging a redemption fee of no less than 1.50% for holders with a continuous holding period of less than 7 days and including it fully in fund assets. The AFTER text still contains this clause verbatim (split across p221/p222), so the deletion was not performed.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除“本基金对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并将上述赎回费全额计入基金财产。”"}
- [sweep] {"kind": "sweep", "finding_id": "SW002", "rule_id": "G12", "location": "p221", "source_location": "p221", "quote": "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用应根据法律法规规定的比例归入基金财产，未计入基金财产的部分用于支付登记费和其他必要的手续费。", "issue": "wrong_text", "reason": "G12 requires replacing the old clause with “赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用全额计入基金财产。” The rewritten clause still keeps the old proportional-allocation language (“应根据法律法规规定的比例归入基金财产，未计入基金财产的部分用于支付登记费和其他必要的手续费”) instead of the required “赎回费用全额计入基金财产。”", "artifact_start": 0, "artifact_end": 90, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [sweep] {"kind": "sweep", "finding_id": "SW003", "rule_id": "G13", "location": "p221", "source_location": "p221", "quote": "其中，对持续持有期少于", "issue": "residual_old_text", "reason": "G13 requires deleting “本基金对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并将上述赎回费全额计入基金财产。” The old short-holding-period redemption-fee sentence survives (split across p221–p222: “其中，对持续持有期少于 7 日的投资者收取不低于 1.5% 的赎回费，并全额计入基金财产。”) and was not deleted.", "artifact_start": 90, "artifact_end": 101, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p823", "code": "DUPLICATE_SITE_UNEDITED", "reason": "an identical clause copy was left unedited", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G06", "operation_id": "G06:0", "obligation_id": "G06:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G12", "operation_id": "G12:0", "obligation_id": "G12:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G12", "operation_id": "G12:1", "obligation_id": "G12:B1:O2", "location": "p221", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G13", "operation_id": "G13:0", "obligation_id": "G13:B1:O1", "location": "p221", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p823", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p823", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p824", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "semantic_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "failure_class": "GENERATION"}

**交付状态：incomplete**
