# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：74920e09c398f086091ca2b522c5d3bb0ed574d8ccd8c6e00ecf416b508ba93a
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 3（A类、C类、D类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 21，已符合 6，不适用 2；计划修改 13
- 审计轮次：3；未决问题 3
- 查漏：块 5，发现 7，未解决 6，缺口 0
- 模型调用：54；估算费用：0.04332404999999999

## 每规则处置

- G01：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 0/1；章节 ['S03', 'S04', 'S25']
- G02：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S03', 'S04', 'S25']
- G03：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S04', 'S25']
- G04：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S04', 'S25']
- G05：覆盖 targets_found；目标 3（应改 3 / 已符合 0 / 不适用 0）；审计完成 0/1；章节 ['S04', 'S25']
- G06：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S04', 'S25']
- G07：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G08：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G09：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G10：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G11：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/2；章节 ['S07', 'S25']
- G12：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S07', 'S25']
- G13：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G14：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07', 'S25']
- G15：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S16', 'S25']
- G16：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16', 'S25']
- G17：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S16', 'S25']
- G18：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17', 'S25']
- G19：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 13，结论 17，另报 0，丢弃 0，问题 1
- 第 1 轮（incremental）：规则 1，结论 1，另报 0，丢弃 0，问题 1
- 第 2 轮（sweep_repair）：规则 13，结论 19，另报 0，丢弃 0，问题 3

## 查漏轮次

- 第 0 轮：块 4，发现 4，丢弃 8
- 第 2 轮：块 1，发现 3，丢弃 1
  - SW001：G01 p91 missing_new_text → pending
  - SW002：G05 p129 wrong_text → unresolved
  - SW003：G18 p800 wrong_text → pending
  - SW004：G16 p1246 missing_new_text → pending
  - SW005：G05 p129 residual_old_text → pending
  - SW006：G05 p129 residual_old_text → pending
  - SW007：G06 p129 unaddressed_requirement → resolved

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p772：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1247：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [target] {"kind": "target", "rule_id": "G05", "target_id": "S03_S04_S07_S16_S17_S20#1:T005", "location": "p129", "reason": "RECALL_EDIT_CONTENT_UNVERIFIED", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G11", "target_id": "S03_S04_S07_S16_S17_S20#1:T011", "location": "p211", "reason": "RECALL_COMPOSE_UNVERIFIED", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G12", "target_id": "S03_S04_S07_S16_S17_S20#1:T013", "location": "p210", "reason": "RECALL_COMPOSE_UNVERIFIED", "failure_class": "GENERATION"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "verdict": "incomplete", "reason": "AFTER 与 BEFORE 完全相同，未在基金份额类别定义条款后增加 G01 要求的新条款（直销机构申购A类不收取认购/申购费用、直销机构申购C类不收取销售服务费、其他销售机构申购C类持续持有超过一年不再收取销售服务费），要求内容整体缺失。", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G01:0 在释义基金份额类别定义后追加直销机构/其他销售机构申购费用与销售服务费豁免条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G05", "target_id": "S03_S04_S07_S16_S17_S20#1:T005", "location": "p129", "verdict": "wrong", "reason": "The requirement (G05) states that because the fund has a share class charging a sales service fee (C类), “调低赎回费率” must be changed to “调低销售服务费率”. The AFTER text still reads “调低赎回费率”, so the required replacement was not made and the original wording remains unchanged.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "本基金有收取销售服务费的C类份额，应调低销售服务费率", "affected_obligation": "将“调低赎回费率”改为“调低销售服务费率”"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G11", "target_id": "S03_S04_S07_S16_S17_S20#1:T011", "location": "p211", "verdict": "wrong", "reason": "The p211 clause still states that A类 and D类 收取申购费用 and only C类 不收取申购费; it was not replaced with the required direct-sales/other-sales A类 (and D类) no-fee / investor-borne fee wording. The text contradicts the requirement.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "G11 replace 申购费用承担条款为直销机构申购A类不收取申购费、其他销售机构申购A类费用由投资人承担、C类不收取申购费用"}
- [sweep] {"kind": "sweep", "finding_id": "SW001", "rule_id": "G01", "location": "p91", "source_location": "p91", "quote": "基金份额类别：本基金将基金份额分为 A 类、C 类和 D 类三种不同的类别。在投资者申购 A 类及 D 类基金份额时收取申购费用，不计提销售服务费；在投资者申购 C 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费", "issue": "missing_new_text", "reason": "释义的基金份额类别定义条款后未增加关于直销机构申购A类（及D类）不收取认购/申购费用、直销机构申购C类不收取销售服务费、其他销售机构申购C类持续持有超过一年不再收取销售服务费的新条款。", "artifact_start": 0, "artifact_end": 114, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW002", "rule_id": "G05", "location": "p129", "source_location": "p129", "quote": "在法律法规和基金合同规定的范围内变更现有基金份额类别的申购费率、调低销售服务费率或变更收费方式", "issue": "wrong_text", "reason": "该条款已含“调低销售服务费率”，但G05要求删除“并报中国证监会备案”，而本段末尾仍保留“调整前基金管理人需及时公告”前的原表述结构；需核对是否残留“并报中国证监会备案”。实际p129未见该残留，但G05的删除项在p418处仍存在“调低赎回费率”。", "artifact_start": 98, "artifact_end": 145, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW003", "rule_id": "G18", "location": "p800", "source_location": "p800", "quote": "由于本基金A类、D类基金份额和C类基金份额费用收取不同，各基金份额类别对应的可分配收益将有所不同。", "issue": "wrong_text", "reason": "G18 requires the phrase to read '由于本基金A类基金份额和C类基金份额费用收取不同'; the rewritten clause still enumerates 'A类、D类基金份额和C类基金份额' rather than the required wording, so the required replacement text is not present.", "artifact_start": 0, "artifact_end": 49, "chunk": "C003", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW004", "rule_id": "G16", "location": "p1246", "source_location": "p1246", "quote": "E为C类基金份额前一日基金资产净值", "issue": "missing_new_text", "reason": "G16要求在销售服务费条款最后增加“销售服务费每日计提。（1）直销机构……（2）直销机构以外的其他销售机构……”的完整段落，但该段落在计提公式后缺失，未补充直销机构返还及其他销售机构按月支付、持有超过一年返还的内容。", "artifact_start": 0, "artifact_end": 17, "chunk": "C004", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW005", "rule_id": "G05", "location": "p129", "source_location": "p129", "quote": "在法律法规和基金合同规定的范围内变更现有基金份额类别的申购费率、调低赎回费率或变更收费方式", "issue": "residual_old_text", "reason": "G05 requires that where a class charges a service fee, '调低赎回费率' be changed to '调低销售服务费率' (and '并报中国证监会备案' deleted). The old text '调低赎回费率' survives unchanged in the 基金份额的类别 clause.", "artifact_start": 98, "artifact_end": 143, "chunk": "C001", "round": 2, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW006", "rule_id": "G05", "location": "p129", "source_location": "p129", "quote": "调整前基金管理人需及时公告。", "issue": "residual_old_text", "reason": "G05 requires deletion of '并报中国证监会备案'; the clause still retains the old pre-announcement/备案 regime wording rather than the required deletion-adjusted text.", "artifact_start": 161, "artifact_end": 175, "chunk": "C001", "round": 2, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "p91", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G02", "operation_id": "G02:0", "obligation_id": "G02:B1:O1", "location": "p91", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G02", "operation_id": "G02:1", "obligation_id": "G02:B1:O2", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G04", "operation_id": "G04:0", "obligation_id": "G04:B1:O1", "location": "p126", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G04", "operation_id": "G04:1", "obligation_id": "G04:B1:O2", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G05", "operation_id": "G05:0", "obligation_id": "G05:B1:O1", "location": "p129", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G11", "operation_id": "G11:0", "obligation_id": "G11:B1:O1", "location": "p211", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}

**交付状态：incomplete**
