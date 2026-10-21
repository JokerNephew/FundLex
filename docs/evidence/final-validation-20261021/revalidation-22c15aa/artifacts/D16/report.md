# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：8beacaba3446f7e7e6db1d8cdd3036f0eb086139d6e89a9d27e3552ec658e45d
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=False）
- 事实：份额类别 2（A类、C类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 27，已符合 8，不适用 3；计划修改 15
- 审计轮次：3；未决问题 4
- 查漏：块 7，发现 10，未解决 7，缺口 0
- 模型调用：51；估算费用：0.04055925000000002

## 每规则处置

- G01：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/1；章节 ['S03']
- G02：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S03']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S04']
- G04：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S04']
- G05：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S04']
- G06：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/4；章节 ['S04']
- G07：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G10：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07']
- G11：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G12：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S07']
- G13：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S07']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G15：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S16']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16']
- G17：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 3/3；章节 ['S16']
- G18：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17']
- G19：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20']
- G20：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 0/1；章节 ['S20']
- G21：覆盖 targets_found；目标 1（应改 0 / 已符合 1 / 不适用 0）；审计完成 0/0；章节 ['S20']
- G22：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20']

## 审计轮次

- 第 0 轮（full）：规则 14，结论 24，另报 0，丢弃 0，问题 9
- 第 1 轮（incremental）：规则 4，结论 9，另报 0，丢弃 0，问题 9
- 第 2 轮（sweep_repair）：规则 14，结论 21，另报 0，丢弃 1，问题 4

## 查漏轮次

- 第 0 轮：块 4，发现 4，丢弃 4
- 第 2 轮：块 3，发现 6，丢弃 3
  - SW001：G01 p91 missing_new_text → unresolved
  - SW002：G06 p133 residual_old_text → resolved
  - SW003：G17 p823 residual_old_text → resolved
  - SW004：G17 p824 residual_old_text → resolved
  - SW005：G01 p91 missing_new_text → pending
  - SW006：G05 p133 residual_old_text → pending
  - SW007：G13 p222 residual_old_text → pending
  - SW008：G15 p822 residual_old_text → pending
  - SW009：G16 p822 missing_new_text → pending
  - SW010：G17 p822 unaddressed_requirement → pending

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p822：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1306：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [target] {"kind": "target", "rule_id": "G13", "target_id": "Y007", "location": "p221", "reason": "RECALL_TARGET_OPERATION_UNATTRIBUTED", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G12", "target_id": "T3001", "location": "p219", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G06", "target_id": "Y019", "location": "p431", "reason": "RECALL_TARGET_COMPOSITE_UNRESOLVED", "failure_class": "TARGET"}
- [target] {"kind": "target", "rule_id": "G06", "target_id": "Y020", "location": "p1169", "reason": "RECALL_TARGET_COMPOSITE_UNRESOLVED", "failure_class": "TARGET"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "verdict": "incomplete", "reason": "AFTER 与 BEFORE 完全相同，未在基金份额类别定义后追加 G01 要求的新条款（直销机构申购A类不收取认购/申购费用、直销机构申购C类不收取销售服务费、其他销售机构申购C类持续持有超过一年不再收取销售服务费）。", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G01:0 追加直销机构/其他销售机构费用豁免条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G13", "target_id": "Y007", "location": "p221", "verdict": "wrong", "reason": "G13 requires deleting the sentence about charging a redemption fee of no less than 1.50% for investors holding fewer than 7 days and including that fee fully in fund assets. The AFTER text instead rewrites the fee-allocation clause to say the redemption fee is fully included in fund assets, which contradicts the requirement and drops the required content (the original proportional-allocation language and the 7-day/1.50% sentence). The change matches the G12 authorized edit, not G13.", "evidence_verified": true, "failure_class": "TARGET", "affected_fact": "", "affected_obligation": "G13:0 delete the 7-day/1.50% redemption fee sentence"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G06", "target_id": "Y019", "location": "p431", "verdict": "wrong", "reason": "G06 requires deleting the clause '除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。' The AFTER text at p431 still contains the original business-rule adjustment clause and the required deletion was not performed; the target location is unchanged from BEFORE.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "G06:0 delete 除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G06", "target_id": "Y020", "location": "p1169", "verdict": "wrong", "reason": "G06 requires deleting the clause '除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。' The AFTER text at p1169 still contains the original business-rule adjustment clause and the required deletion was not performed; the target location is unchanged from BEFORE.", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "G06:0 delete 除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。"}
- [sweep] {"kind": "sweep", "finding_id": "SW001", "rule_id": "G01", "location": "p91", "source_location": "p91", "quote": "基金份额类别：本基金将基金份额分为 A 类和 C 类不同的类别。在投资者认购、申购基金份额时收取认购、申购费用而不计提销售服务费的，称为 A 类基金份额；在投资者认购、申购基金份额时不收取认购、申购费用而是从本类别基金资产中计提销售服务费的，称为 C 类基金份额", "issue": "missing_new_text", "reason": "释义的基金份额类别定义条款后未增加关于通过直销机构申购A类不收取认购/申购费用、通过直销机构申购C类不收取销售服务费、通过其他销售机构申购C类持续持有超过一年不再收取销售服务费的新条款。", "artifact_start": 0, "artifact_end": 131, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW006", "rule_id": "G05", "location": "p133", "source_location": "p133", "quote": "根据基金销售情况，在符合法律法规且不损害已有基金份额持有人权益的情况下，基金管理人在履行适当程序后可以增加新的基金份额类别、或者在法律法规和基金合同规定的范围内变更现有基金份额类别的申购费率、调低销售服务费率或变更收费方式、或者停止现有基金份额类别的销售等，调整前基金管理人需及时公告。", "issue": "residual_old_text", "reason": "原条款中“并报中国证监会备案”未被删除（该句仍以“调整前基金管理人需及时公告”形式保留原结构，但要求删除的“并报中国证监会备案”文本未处理）；且该条款未按G05删除“并报中国证监会备案”。", "artifact_start": 34, "artifact_end": 177, "chunk": "C001", "round": 2, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW007", "rule_id": "G13", "location": "p222", "source_location": "p222", "quote": "7 日的投资者收取不低于 1.5%的赎回费，并全额计入基金财产。", "issue": "residual_old_text", "reason": "G13要求删除“本基金对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并将上述赎回费全额计入基金财产。”，但该句残片仍保留在p222，未被删除。", "artifact_start": 0, "artifact_end": 32, "chunk": "C001", "round": 2, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW008", "rule_id": "G15", "location": "p822", "source_location": "p822", "quote": "基金销售服务费每日计提，逐日累计至每月月末，按月支付，经基金管理人与基金托管人核对一致后，由基金托管人于次月前 5 个工作日内按照指定的账户路径从基金财产中一次性支付，管理人无需再出具资金划拨指令。若遇法定节假日、公休日等，支付日期顺延。费用自动扣划后，管理人应进行核对，如发现数据不符，及时联系托管人协商解决。", "issue": "residual_old_text", "reason": "G15要求删除原C类销售服务费“每日计提，按月支付……由基金管理人向基金托管人发送基金销售服务费划付指令……支付日期顺延”的旧支付条款；p822仍保留按月支付、托管人支付、顺延等旧销售服务费支付安排，未按G16替换为直销机构返还及其他销售机构按月支付/持有超一年返还的新内容。", "artifact_start": 0, "artifact_end": 156, "chunk": "C003", "round": 2, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [sweep] {"kind": "sweep", "finding_id": "SW009", "rule_id": "G16", "location": "p822", "source_location": "p822", "quote": "基金销售服务费每日计提，逐日累计至每月月末，按月支付，经基金管理人与基金托管人核对一致后，由基金托管人于次月前 5 个工作日内按照指定的账户路径从基金财产中一次性支付，管理人无需再出具资金划拨指令。若遇法定节假日、公休日等，支付日期顺延。费用自动扣划后，管理人应进行核对，如发现数据不符，及时联系托管人协商解决。", "issue": "missing_new_text", "reason": "G16要求在原条款最后增加销售服务费每日计提、直销机构返还、其他销售机构按月支付及持有超过一年后返还等内容；p822没有直销机构赎回/终止时随赎回款返还、其他销售机构按月支付、持有超过一年后继续计提部分返还等新增内容。", "artifact_start": 0, "artifact_end": 156, "chunk": "C003", "round": 2, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW010", "rule_id": "G17", "location": "p822", "source_location": "p822", "quote": "基金销售服务费每日计提，逐日累计至每月月末，按月支付，经基金管理人与基金托管人核对一致后，由基金托管人于次月前 5 个工作日内按照指定的账户路径从基金财产中一次性支付，管理人无需再出具资金划拨指令。若遇法定节假日、公休日等，支付日期顺延。费用自动扣划后，管理人应进行核对，如发现数据不符，及时联系托管人协商解决。", "issue": "unaddressed_requirement", "reason": "G17要求删除原条款中关于C类销售服务费主要用于支付销售机构佣金、行销广告费、促销活动费、持有人服务费等使用范围的旧表述；该使用范围条款在p822附近仍未见删除或替换，销售服务费条款仍保留旧支付/使用安排，未落实G17的删除要求。", "artifact_start": 0, "artifact_end": 156, "chunk": "C003", "round": 2, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p822", "code": "DUPLICATE_SITE_UNEDITED", "reason": "an identical clause copy was left unedited", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "p91", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G05", "operation_id": "G05:0", "obligation_id": "G05:B1:O1", "location": "p427", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G15", "operation_id": "G15:0", "obligation_id": "G15:B1:O1", "location": "p822", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "若遇法定节假日、公休日等，支付日期顺延。", "failure_class": "GENERATION"}

**交付状态：incomplete**
