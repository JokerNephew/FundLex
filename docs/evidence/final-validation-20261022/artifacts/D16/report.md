# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：8beacaba3446f7e7e6db1d8cdd3036f0eb086139d6e89a9d27e3552ec658e45d
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 2（A、C）；销售服务费类别：C；浮动管理费：否
- 目标计数：应改 30，已符合 6，不适用 0；计划修改 12
- 审计轮次：3；未决问题 12
- 查漏：块 8，发现 16，未解决 13，缺口 0
- 模型调用：47；估算费用：0.034974899999999996

## 每规则处置

- G01：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/1；章节 ['S03']
- G02：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S03']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S04']
- G04：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S04']
- G05：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S04']
- G06：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S04']
- G07：覆盖 targets_found；目标 1（应改 0 / 已符合 1 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G10：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G11：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G12：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S07']
- G13：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S07']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G15：覆盖 targets_found；目标 1（应改 0 / 已符合 1 / 不适用 0）；审计完成 1/2；章节 ['S16']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16']
- G17：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/3；章节 ['S16']
- G18：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17']
- G19：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20']
- G20：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20']
- G21：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20']
- G22：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20']

## 审计轮次

- 第 0 轮（full）：规则 15，结论 27，另报 0，丢弃 1，问题 14
- 第 1 轮（incremental）：规则 6，结论 14，另报 0，丢弃 1，问题 14
- 第 2 轮（sweep_repair）：规则 4，结论 8，另报 0，丢弃 2，问题 5

## 查漏轮次

- 第 0 轮：块 4，发现 10，丢弃 4
- 第 2 轮：块 4，发现 6，丢弃 6
  - SW001：G01 p91 missing_new_text → unresolved
  - SW002：G03 p129 missing_new_text → resolved
  - SW003：G05 p133 residual_old_text → resolved
  - SW004：G12 p221 wrong_text → unresolved
  - SW005：G13 p221 residual_old_text → unresolved
  - SW006：G15 p823 residual_old_text → pending
  - SW007：G17 p823 residual_old_text → pending
  - SW008：G17 p824 residual_old_text → pending
  - SW009：G17 p1307 residual_old_text → unresolved
  - SW010：G17 p1308 residual_old_text → unresolved
  - SW011：G01 p91 missing_new_text → pending
  - SW012：G05 p133 residual_old_text → resolved
  - SW013：G12 p221 wrong_text → pending
  - SW014：G13 p221 residual_old_text → pending
  - SW015：G17 p1307 residual_old_text → pending
  - SW016：G17 p1308 residual_old_text → pending

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1306：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p822：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [target] {"kind": "target", "rule_id": "G12", "target_id": "S03_S04_S07_S16_S17_S20#1:T013", "location": "p221", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G13", "target_id": "S03_S04_S07_S16_S17_S20#1:T014", "location": "p222", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "S03_S04_S07_S16_S17_S20#1:T018", "location": "p823", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G13", "target_id": "Y007", "location": "p221", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "Y011", "location": "p1307", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G12", "target_id": "T3001", "location": "p219", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "verdict": "incomplete", "reason": "AFTER at p91 is identical to BEFORE; the required appended clause about direct-sales A-class fee waiver, direct-sales C-class sales-service-fee waiver, and other-agency C-class fee cessation after one year is entirely missing.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "G01:0 append 直销机构申购A类不收认购/申购费、直销机构申购C类不收销售服务费、其他销售机构申购C类持有超一年不再收取销售服务费"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G02", "target_id": "S03_S04_S07_S16_S17_S20#1:T002", "location": "p91", "verdict": "incomplete", "reason": "G02 requires replacing 'A类基金份额' with all actual share classes that charge subscription/purchase fees and do not accrue sales service fees. AFTER still reads '称为 A 类基金份额' unchanged, so the required grouping replacement was not applied.", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G02:0 replace A类基金份额 with the actual classes applying the front-load/no-service-fee rule"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G04", "target_id": "S03_S04_S07_S16_S17_S20#1:T005", "location": "p129", "verdict": "incomplete", "reason": "G04 requires replacing 'A类基金份额' with all actual classes applying the '收取认购、申购费用且不计提销售服务费' rule (A类、B类基金份额 per the rule). AFTER still reads '称为 A 类基金份额' with no B类 added, so the grouping replacement was not performed.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "A类、B类基金份额", "affected_obligation": "G04:0 replace A类基金份额 -> A类、B类基金份额"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G12", "target_id": "S03_S04_S07_S16_S17_S20#1:T013", "location": "p221", "verdict": "wrong", "reason": "The requirement replaces the redemption-fee clause with '赎回费用全额计入基金财产。' AFTER still retains the old proportional-allocation wording and the 7-day/1.5% sentence, so the required replacement was not made.", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G12: replace redemption fee clause with '赎回费用全额计入基金财产。'"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G13", "target_id": "S03_S04_S07_S16_S17_S20#1:T014", "location": "p222", "verdict": "wrong", "reason": "G13 requires deleting the sentence about charging ≥1.5% redemption fee for holders under 7 days and including it fully in fund assets. The AFTER text at p222 still contains this content unchanged, so the deletion was not performed.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除对持续持有期少于7日投资者收取不低于1.50%赎回费并全额计入基金财产的表述"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "S03_S04_S07_S16_S17_S20#1:T018", "location": "p823", "verdict": "wrong", "reason": "G17 requires deleting the sales service fee clause, but the AFTER text at p823 still contains the full clause unchanged.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除销售服务费用途条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G13", "target_id": "Y007", "location": "p221", "verdict": "wrong", "reason": "The ledger marks p221 as needing replacement, but the AFTER text is identical to BEFORE and still contains the clause continuation about holders with holding period less than (7 days). No edit was applied.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除对持续持有期少于7日投资者收取不低于1.50%赎回费并全额计入基金财产的表述"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "Y011", "location": "p1307", "verdict": "wrong", "reason": "The clause at p1307 was to be removed per G17, but it remains verbatim in AFTER.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除销售服务费用途条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G12", "target_id": "T3001", "location": "p219", "verdict": "incomplete", "reason": "The ledger target at p219 is unresolved with no operation; AFTER only shows the G09-authorized change to '扣除或加上相应的费用' and '该类基金份额的基金份额净值', with no G12 redemption-fee replacement applied at this location.", "evidence_verified": true, "failure_class": "TARGET", "affected_fact": "", "affected_obligation": "G12: redemption fee clause replacement"}
- [sweep] {"kind": "sweep", "finding_id": "SW001", "rule_id": "G01", "location": "p91", "source_location": "p91", "quote": "基金份额类别：本基金将基金份额分为 A 类和 C 类不同的类别。在投资者认购、申购基金份额时收取认购、申购费用而不计提销售服务费的，称为 A 类基金份额；在投资者认购、申购基金份额时不收取认购、申购费用而是从本类别基金资产中计提销售服务费的，称为 C 类基金份额", "issue": "missing_new_text", "reason": "释义的基金份额类别定义条款后未增加关于直销机构申购A类不收认购/申购费、直销机构申购C类不收销售服务费、其他销售机构申购C类持续持有超过一年不再收取销售服务费的新条款。", "artifact_start": 0, "artifact_end": 131, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW004", "rule_id": "G12", "location": "p221", "source_location": "p221", "quote": "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用应根据法律法规规定的比例归入基金财产，未计入基金财产的部分用于支付登记费和其他必要的手续费。其中，对持续持有期少于", "issue": "wrong_text", "reason": "未按G12替换为“赎回费用全额计入基金财产”，仍保留“赎回费用应根据法律法规规定的比例归入基金财产，未计入基金财产的部分用于支付登记费和其他必要的手续费”的旧表述。", "artifact_start": 0, "artifact_end": 101, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "RESIDUAL_CONFIRMED", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW005", "rule_id": "G13", "location": "p221", "source_location": "p221", "quote": "其中，对持续持有期少于", "issue": "residual_old_text", "reason": "应删除的“本基金对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并将上述赎回费全额计入基金财产。”旧文本仍残留（p221-p222连续表述“其中，对持续持有期少于7日的投资者收取不低于1.5%的赎回费，并全额计入基金财产。”）。", "artifact_start": 90, "artifact_end": 101, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW006", "rule_id": "G15", "location": "p823", "source_location": "p823", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "issue": "residual_old_text", "reason": "G15要求删除原条款中关于C类基金份额销售服务费每日计提、按月支付、划付指令及支付日期顺延的整段文字。该段旧文本（含“C类基金份额的销售服务费每日计提，按月支付……若遇法定节假日、公休日等，支付日期顺延。”）在p823处仍以“销售服务费主要用于支付销售机构佣金……”的形式残留，未被删除或替换，属于应删除而未删除的旧条款。", "artifact_start": 0, "artifact_end": 52, "chunk": "C003", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW007", "rule_id": "G17", "location": "p823", "source_location": "p823", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "issue": "residual_old_text", "reason": "G17要求删除原条款“C类基金份额的销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。”。p823仍保留“销售服务费主要用于支付销售机构佣金……”的旧文本，p824仍保留“销售服务费使用范围不包括基金募集期间的上述费用。”，两处旧条款均未删除。", "artifact_start": 0, "artifact_end": 52, "chunk": "C003", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW008", "rule_id": "G17", "location": "p824", "source_location": "p824", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "issue": "residual_old_text", "reason": "G17明确要求删除“C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。”这一旧条款。p824仍完整保留该句（仅省略了“C类基金份额的”前缀），属于应删除而未删除的残留旧文本。", "artifact_start": 0, "artifact_end": 24, "chunk": "C003", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW009", "rule_id": "G17", "location": "p1307", "source_location": "p1307", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "issue": "residual_old_text", "reason": "G17要求删除“C类基金份额的销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。”，但该段旧文本仍保留在[p1307]-[p1308]。", "artifact_start": 0, "artifact_end": 52, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "SCOPE_CORRECTION_TARGET", "status": "unresolved", "proof_kind": "RESIDUAL_CONFIRMED", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW010", "rule_id": "G17", "location": "p1308", "source_location": "p1308", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "issue": "residual_old_text", "reason": "G17明确要求删除“C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。”，该旧条款仍存活于[p1308]。", "artifact_start": 0, "artifact_end": 24, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "SCOPE_CORRECTION_TARGET", "status": "unresolved", "proof_kind": "RESIDUAL_CONFIRMED", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW013", "rule_id": "G12", "location": "p221", "source_location": "p221", "quote": "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用应根据法律法规规定的比例归入基金财产，未计入基金财产的部分用于支付登记费和其他必要的手续费。其中，对持续持有期少于", "issue": "wrong_text", "reason": "G12要求替换为“赎回费用全额计入基金财产”，但该条款仍保留“赎回费用应根据法律法规规定的比例归入基金财产，未计入基金财产的部分用于支付登记费和其他必要的手续费”，未改为全额计入基金财产。", "artifact_start": 0, "artifact_end": 101, "chunk": "C001", "round": 2, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [sweep] {"kind": "sweep", "finding_id": "SW014", "rule_id": "G13", "location": "p221", "source_location": "p221", "quote": "其中，对持续持有期少于", "issue": "residual_old_text", "reason": "G13要求删除“本基金对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并将上述赎回费全额计入基金财产。”，但该条款仍保留对持续持有期少于7日收取不低于1.5%赎回费并全额计入基金财产的旧文本（跨p221-p222）。", "artifact_start": 90, "artifact_end": 101, "chunk": "C001", "round": 2, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW015", "rule_id": "G17", "location": "p1307", "source_location": "p1307", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "issue": "residual_old_text", "reason": "G17要求删除“C类基金份额的销售服务费主要用于支付销售机构佣金……基金份额持有人服务费等。C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。”，但p1307仍保留该用途描述（仅删去“C类基金份额的”前缀），旧条款实质残留。", "artifact_start": 0, "artifact_end": 52, "chunk": "C004", "round": 2, "failure_class": "TARGET", "routing_status": "SCOPE_CORRECTION_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [sweep] {"kind": "sweep", "finding_id": "SW016", "rule_id": "G17", "location": "p1308", "source_location": "p1308", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "issue": "residual_old_text", "reason": "G17明确要求删除“使用范围不包括基金募集期间的上述费用”一句，但p1308仍完整保留该句。", "artifact_start": 0, "artifact_end": 24, "chunk": "C004", "round": 2, "failure_class": "TARGET", "routing_status": "SCOPE_CORRECTION_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "p91", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G05", "operation_id": "G05:0", "obligation_id": "G05:B1:O1", "location": "p427", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G06", "operation_id": "G06:0", "obligation_id": "G06:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G12", "operation_id": "G12:0", "obligation_id": "G12:B1:O1", "location": "p221", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G12", "operation_id": "G12:1", "obligation_id": "G12:B1:O2", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G13", "operation_id": "G13:0", "obligation_id": "G13:B1:O1", "location": "p221", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p823", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p823", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p1307", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p824", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "semantic_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p1308", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "semantic_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "failure_class": "GENERATION"}

**交付状态：incomplete**
