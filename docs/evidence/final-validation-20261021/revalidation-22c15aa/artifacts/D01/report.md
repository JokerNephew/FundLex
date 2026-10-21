# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：2f2f7a36000af8135feb625c0c7d6f9f3e8b291d1628f0879993d6987e2d278d
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 3（A类、C类、D类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 25，已符合 5，不适用 7；计划修改 12
- 审计轮次：4；未决问题 6
- 查漏：块 4，发现 10，未解决 8，缺口 0
- 模型调用：64；估算费用：0.047819999999999994

## 每规则处置

- G01：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S03']
- G02：覆盖 targets_found；目标 1（应改 0 / 已符合 1 / 不适用 0）；审计完成 0/1；章节 ['S03']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/1；章节 ['S04']
- G04：覆盖 targets_found；目标 1（应改 0 / 已符合 1 / 不适用 0）；审计完成 0/1；章节 ['S04']
- G05：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/2；章节 ['S04']
- G06：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S04']
- G07：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G10：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G11：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/2；章节 ['S07']
- G12：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S07']
- G13：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G15：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S16']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/2；章节 ['S16']
- G17：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/3；章节 ['S16']
- G18：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17']
- G19：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 16，结论 25，另报 0，丢弃 0，问题 7
- 第 1 轮（incremental）：规则 5，结论 8，另报 0，丢弃 2，问题 10
- 第 2 轮（incremental）：规则 7，结论 12，另报 0，丢弃 1，问题 6
- 第 3 轮（incremental）：规则 3，结论 6，另报 0，丢弃 1，问题 6

## 查漏轮次

- 第 0 轮：块 4，发现 10，丢弃 3
  - SW001：G03 p130 missing_new_text → pending
  - SW002：G13 p230 residual_old_text → resolved
  - SW003：G14 p231 wrong_text → pending
  - SW004：G15 p758 residual_old_text → resolved
  - SW005：G16 p758 missing_new_text → pending
  - SW006：G17 p759 residual_old_text → pending
  - SW007：G18 p782 unaddressed_requirement → pending
  - SW008：G18 p785 wrong_text → pending
  - SW009：G22 p934 wrong_text → pending
  - SW010：G22 p1299 missing_new_text → pending

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1221：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T001", "location": "p92", "reason": "TARGET_SOURCE_MISMATCH", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G03", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T004", "location": "p135", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T019", "location": "p759", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G18", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T021", "location": "p785", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G22", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T025", "location": "p934", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G22", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T026", "location": "p1299", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G01", "target_id": "Y008", "location": "p91", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [target] {"kind": "target", "rule_id": "G02", "target_id": "T3001", "location": "p91", "reason": "RECALL_TARGET_OCCURRENCE_AMBIGUOUS", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G12", "target_id": "T3004", "location": "p227", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T001", "location": "p92", "verdict": "incomplete", "reason": "AFTER 在 p92 处与 BEFORE 完全相同，未增加 G01 要求的新条款（直销机构申购A类不收取认购/申购费用、直销C类不收销售服务费、其他销售机构C类持有超一年不再收取销售服务费）。", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "在释义基金份额类别定义后增加直销/其他销售机构费用安排的新条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G03", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T004", "location": "p135", "verdict": "incomplete", "reason": "G03 requires appending a new clause after the share-class setup clause specifying that direct-sales A类 subscriptions charge no subscription fee, direct-sales C类 charge no sales service fee, and other-agency C类 held over one year stop incurring sales service fee. AFTER only contains the original clause (with an unrelated G05 fee-rate wording change) and no appended clause.", "evidence_verified": true, "failure_class": "TARGET", "affected_fact": "", "affected_obligation": "G03:0 append 直销机构申购A类不收取认购/申购费用、直销C类不收取销售服务费、其他销售机构C类持有超一年不再收取销售服务费的新条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "S03_S04_S07_S16_S17_S20_S26#1:T019", "location": "p759", "verdict": "wrong", "reason": "G17 requires deleting the sales service fee clause, but p759 still retains the full clause unchanged.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除销售服务费用途条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "Y008", "location": "p91", "verdict": "incomplete", "reason": "AFTER 在 p91 处与 BEFORE 完全相同，未按 G01 在该基金份额类别定义条款后追加新条款。", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "在释义基金份额类别定义原条款后增加新条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G02", "target_id": "T3001", "location": "p91", "verdict": "incomplete", "reason": "G02 requires the share-class definition to be regrouped per actual fee rules: the A类 group must be replaced with all classes that charge subscription/purchase fees and no sales service fee (A类、B类), and the C类 group with all classes that charge no subscription/purchase fee but accrue sales service fee (C类、D类). AFTER still reads the original 'A 类、C 类和 D 类三种不同的' — the B类 class is missing from the first group and the grouping replacement was not performed.", "evidence_verified": true, "failure_class": "FACT", "affected_fact": "基金份额类别分组：A类、B类为收取认购/申购费且不计提销售服务费的类别；C类、D类为不收取认购/申购费且计提销售服务费的类别", "affected_obligation": "G02 释义-基金份额类别定义按实际收费规则分组替换"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G04", "target_id": "T3002", "location": "p130", "verdict": "wrong", "reason": "G04 要求按实际收费规则对份额类别分组替换：收取申购费且不计提销售服务费的类别应替换为实际适用该规则的全部类别（A类、B类），不收取申购费且计提销售服务费的类别应替换为实际适用该规则的全部类别（C类、D类）。AFTER 仍保留原分组，把 D 类归入收取申购费且不计提销售服务费的一组，与 G04:1 要求的 C类、D类 分组相矛盾，未完成替换。", "evidence_verified": true, "failure_class": "FACT", "affected_fact": "D类基金份额的收费规则（应不收取申购费用并计提销售服务费，而非收取申购费用且不计提销售服务费）", "affected_obligation": "G04: 按实际收费规则对份额类别进行分组替换（A类基金份额->A类、B类基金份额；C类基金份额->C类、D类基金份额）"}
- [sweep] {"kind": "sweep", "finding_id": "SW001", "rule_id": "G03", "location": "p130", "source_location": "p130", "quote": "本基金将基金份额分为 A 类、C 类和 D 类三种不同的类别。在投资者申购 A 类及 D 类基金份额时收取申购费用，不计提销售服务费；在投资者申购 C 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费。", "issue": "missing_new_text", "reason": "基金的基本情况份额类别设置条款后未增加关于直销机构申购A类不收取认购/申购费用、直销机构申购C类不收取销售服务费、其他销售机构申购C类持续持有超过一年不再收取销售服务费的新条款。", "artifact_start": 0, "artifact_end": 108, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW003", "rule_id": "G14", "location": "p231", "source_location": "p231", "quote": "基金管理人可以适当调低基金销售服务费率、基金申购费率和基金赎回费率。", "issue": "wrong_text", "reason": "G14要求多份额类别时将“基金管理人可以适当调低基金申购费率和赎回费率。”变更为“基金管理人可以适当调低基金申购费率和销售服务费率。”，但此处仍保留“基金赎回费率”且未按目标表述改写为仅调低申购费率和销售服务费率。", "artifact_start": 112, "artifact_end": 146, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW005", "rule_id": "G16", "location": "p758", "source_location": "p758", "quote": "基金销售服务费每日计提，逐日累计至每月月末，按月支付，经基金管理人与基金托管人核对一致后，由基金托管人于次月前 5 个工作日内从基金财产中一次性划出，由基金管理人代收，基金管理人收到后按相关合同规定支付给基金销售机构等。若遇法定节假日、公休假或不可抗力等，支付日期顺延。", "issue": "missing_new_text", "reason": "G16 requires appending the new sales-service-fee content: 直销机构返还机制（赎回或合同终止时随赎回款/清算款返还）、直销机构以外的其他销售机构按月支付（次月首日起5个工作日内）、以及持有超过一年后继续计提的销售服务费在赎回或合同终止时返还。None of these direct-sales return / over-one-year return provisions appear.", "artifact_start": 0, "artifact_end": 135, "chunk": "C002", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW006", "rule_id": "G17", "location": "p759", "source_location": "p759", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "issue": "residual_old_text", "reason": "G17 requires deleting the old clause stating the sales service fee is mainly used to pay sales agency commissions, marketing/advertising, promotion and holder service fees. This old usage-scope clause survives and should have been deleted.", "artifact_start": 0, "artifact_end": 52, "chunk": "C002", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [sweep] {"kind": "sweep", "finding_id": "SW007", "rule_id": "G18", "location": "p782", "source_location": "p782", "quote": "在符合有关基金分红条件的前提下，本基金收益每季度最少分配 1 次，每年收益分配次数最多为 12 次，每份基金份额每次收益分配比例不得低于收益分配基准日每份基金份额可供分配利润的 10%，若《基金合同》生效不满 3 个月可不进行收益分配；", "issue": "unaddressed_requirement", "reason": "G18 requires changing the收益分配 principle wording from '由于本基金A类基金份额不收取销售服务费，而C类基金份额收取销售服务费' to '由于本基金A类基金份额和C类基金份额费用收取不同'. The收益与分配 section in this chunk contains no such revised wording; the required replacement text is absent.", "artifact_start": 0, "artifact_end": 118, "chunk": "C002", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW008", "rule_id": "G18", "location": "p785", "source_location": "p785", "quote": "由于本基金A类、D类基金份额和C类基金份额费用收取不同，各基金份额类别对应的可分配收益将有所不同。", "issue": "wrong_text", "reason": "G18 requires the clause to read “由于本基金A类基金份额和C类基金份额费用收取不同”. The rewritten text instead enumerates “A类、D类基金份额和C类基金份额费用收取不同”, which does not match the required wording; the required replacement text is not present.", "artifact_start": 0, "artifact_end": 49, "chunk": "C003", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW009", "rule_id": "G22", "location": "p934", "source_location": "p934", "quote": "依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用、交纳所欠税款并清偿基金债务后，按基金份额持有人持有的基金份额比例进行分配，并加上返还基金份额持有人的销售服务费（如有）。", "issue": "wrong_text", "reason": "FACTS show the product is not a floating-fee product (is_floating_fee=false) and has a service-fee class (C类), so G22 applies and requires the liquidation residual distribution clause to add “并加上返还基金份额持有人的销售服务费（如有）”. The clause at p934 already contains that exact added text, so the requirement is met and must not be reported.", "artifact_start": 0, "artifact_end": 100, "chunk": "C003", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW010", "rule_id": "G22", "location": "p1299", "source_location": "p1299", "quote": "依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用、交纳所欠税款并清偿基金债务后，按基金份额持有人持有的各类基金份额比例进行分配。", "issue": "missing_new_text", "reason": "本基金不是浮动管理费产品（管理费为固定0.15%年费率），且收取销售服务费（C类计提销售服务费），因此适用G22：清算剩余资产分配条款应替换为在按比例分配后“并加上返还基金份额持有人的销售服务费（如有）”。当前条款仅写到“按基金份额持有人持有的各类基金份额比例进行分配。”，缺少销售服务费返还的表述。", "artifact_start": 0, "artifact_end": 79, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p758", "code": "DUPLICATE_SITE_UNEDITED", "reason": "an identical clause copy was left unedited", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p759", "code": "DUPLICATE_SITE_UNEDITED", "reason": "an identical clause copy was left unedited", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p1299", "code": "DUPLICATE_SITE_UNEDITED", "reason": "an identical clause copy was left unedited", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "p92", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G02", "operation_id": "G02:0", "obligation_id": "G02:B1:O1", "location": "p92", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G02", "operation_id": "G02:1", "obligation_id": "G02:B1:O2", "location": "p91", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G03", "operation_id": "G03:0", "obligation_id": "G03:B1:O1", "location": "p135", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G04", "operation_id": "G04:0", "obligation_id": "G04:B1:O1", "location": "p130", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G05", "operation_id": "G05:0", "obligation_id": "G05:B1:O1", "location": "p434", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G14", "operation_id": "G14:3", "obligation_id": "G14:B2:O1", "location": "p231", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G14", "operation_id": "G14:4", "obligation_id": "G14:B2:O2", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G22", "operation_id": "G22:0", "obligation_id": "G22:B1:O1", "location": "p1299", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p759", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "failure_class": "GENERATION"}

**交付状态：incomplete**
