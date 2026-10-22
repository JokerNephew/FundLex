# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：2f2f7a36000af8135feb625c0c7d6f9f3e8b291d1628f0879993d6987e2d278d
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 3（A类、C类、D类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 25，已符合 3，不适用 2；计划修改 14
- 审计轮次：2；未决问题 6
- 查漏：块 4，发现 2，未解决 0，缺口 0
- 模型调用：39；估算费用：0.023543399999999996

## 每规则处置

- G01：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S03']
- G02：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S03']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S04']
- G04：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S04']
- G05：覆盖 targets_found；目标 3（应改 2 / 已符合 0 / 不适用 1）；审计完成 1/2；章节 ['S04']
- G06：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S04']
- G07：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G10：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G11：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/2；章节 ['S07']
- G12：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S07']
- G13：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G15：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S16']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16']
- G17：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/4；章节 ['S16']
- G18：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17']
- G19：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 13，结论 21，另报 0，丢弃 0，问题 6
- 第 1 轮（incremental）：规则 2，结论 6，另报 0，丢弃 0，问题 6

## 查漏轮次

- 第 0 轮：块 4，发现 2，丢弃 7
  - SW001：G22 p934 wrong_text → resolved
  - SW002：G22 p1299 wrong_text → resolved

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p758：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1221：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G17", "target_id": "Y006", "location": "p759", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "Y007", "location": "p1222", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "DEL001", "location": "p760", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "DEL002", "location": "p1223", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G02", "target_id": "T3001", "location": "p91", "reason": "RECALL_TARGET_OCCURRENCE_AMBIGUOUS", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G12", "target_id": "T3004", "location": "p227", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "Y006", "location": "p759", "verdict": "wrong", "reason": "G17 requires deleting the sales-service-fee clause; the AFTER text at p759 still contains the full clause unchanged, so the deletion was not performed.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除销售服务费用途条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "Y007", "location": "p1222", "verdict": "wrong", "reason": "G17 requires deleting the sales-service-fee clause; the AFTER text at p1222 still contains the full clause unchanged, so the deletion was not performed.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除销售服务费用途条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "DEL001", "location": "p760", "verdict": "wrong", "reason": "G17 requires deleting the residual sentence about the scope excluding募集期间费用; the AFTER text at p760 still contains it unchanged.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除销售服务费使用范围排除募集期间费用的条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "DEL002", "location": "p1223", "verdict": "wrong", "reason": "G17 requires deleting the residual sentence about the scope excluding募集期间费用; the AFTER text at p1223 still contains it unchanged.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除销售服务费使用范围排除募集期间费用的条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G02", "target_id": "T3001", "location": "p91", "verdict": "incomplete", "reason": "G02:0 requires replacing 'A类基金份额' with all classes that charge subscription/purchase fees and no sales service fee, i.e. 'A类、B类基金份额'. The AFTER text still lists only 'A 类、C 类和 D 类' and does not add B类, so the required grouping replacement was not performed.", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "基金份额类别分组（A类、B类为收取认购申购费且不计提销售服务费的类别）", "affected_obligation": "G02:0 将A类基金份额替换为实际适用该规则的全部份额类别（A类、B类）"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G02", "operation_id": "G02:0", "obligation_id": "G02:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G06", "operation_id": "G06:0", "obligation_id": "G06:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p759", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p759", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p760", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p1222", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p1223", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "failure_class": "GENERATION"}

**交付状态：incomplete**
