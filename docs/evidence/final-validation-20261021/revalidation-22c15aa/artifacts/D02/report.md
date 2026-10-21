# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：c02ae5a04ffbb1a8c63a7408fb3c69fab4f54cd60ff44575f42031ab00e1289b
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 2（A类、C类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 26，已符合 11，不适用 5；计划修改 14
- 审计轮次：3；未决问题 6
- 查漏：块 7，发现 16，未解决 12，缺口 0
- 模型调用：59；估算费用：0.0496368

## 每规则处置

- G01：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 0/1；章节 ['S03', 'S25']
- G02：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S03', 'S25']
- G03：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S04', 'S25']
- G04：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S04', 'S25']
- G05：覆盖 targets_found；目标 4（应改 4 / 已符合 0 / 不适用 0）；审计完成 1/3；章节 ['S04', 'S25']
- G06：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S04', 'S25']
- G07：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G08：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G09：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G10：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G11：覆盖 targets_found；目标 3（应改 2 / 已符合 0 / 不适用 1）；审计完成 0/2；章节 ['S07', 'S25']
- G12：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G13：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G14：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S07', 'S25']
- G15：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 3/4；章节 ['S16', 'S25']
- G16：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 1/3；章节 ['S16', 'S25']
- G17：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 2/3；章节 ['S16', 'S25']
- G18：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17', 'S25']
- G19：覆盖 targets_found；目标 3（应改 1 / 已符合 0 / 不适用 2）；审计完成 0/1；章节 ['S20', 'S26']
- G20：覆盖 targets_found；目标 3（应改 0 / 已符合 1 / 不适用 2）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 targets_found；目标 3（应改 0 / 已符合 3 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 14，结论 23，另报 0，丢弃 0，问题 9
- 第 1 轮（incremental）：规则 4，结论 10，另报 0，丢弃 0，问题 9
- 第 2 轮（sweep_repair）：规则 13，结论 19，另报 1，丢弃 0，问题 6

## 查漏轮次

- 第 0 轮：块 4，发现 10，丢弃 3
- 第 2 轮：块 3，发现 6，丢弃 3
  - SW001：G01 p93 missing_new_text → unresolved
  - SW002：G05 p138 residual_old_text → resolved
  - SW003：G08 p226 wrong_text → pending
  - SW004：G11 p228 wrong_text → unresolved
  - SW005：G12 p229 wrong_text → pending
  - SW006：G14 p232 wrong_text → unresolved
  - SW007：G16 p821 residual_old_text → resolved
  - SW008：G15 p1288 residual_old_text → pending
  - SW009：G17 p1289 residual_old_text → pending
  - SW010：G05 p1162 residual_old_text → pending
  - SW011：G01 p93 missing_new_text → pending
  - SW012：G05 p138 residual_old_text → resolved
  - SW013：G06 p138 residual_old_text → pending
  - SW014：G14 p232 wrong_text → pending
  - SW015：G11 p228 wrong_text → pending
  - SW016：G15 p821 residual_old_text → resolved

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1287：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p821：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p93", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "S25_S26#1:T003", "location": "p1289", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [target] {"kind": "target", "rule_id": "G17", "target_id": "Y007", "location": "p1288", "reason": "RECALL_EDIT_OVERLAP", "failure_class": "GENERATION"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p93", "verdict": "incomplete", "reason": "AFTER 与 BEFORE 完全相同；G01 要求的新条款（直销机构申购A类不收认购/申购费、直销机构申购C类不收销售服务费、其他销售机构申购C类持有超过一年不再收取销售服务费）未追加，整条要求缺失。", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G01:0 追加直销机构/其他销售机构费用安排条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G11", "target_id": "S03_S04_S07_S16_S17_S20#1:T012", "location": "p228", "verdict": "wrong", "reason": "AFTER contains a duplicated/garbled fragment ('通过直销机构申购本基金A类基金份额的通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担') and repeats the C类 sentence twice, so the replacement is not the clean required clause and adds duplicated content.", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G11:0 replace with clean clause: 通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G17", "target_id": "Y007", "location": "p1288", "verdict": "wrong", "reason": "G17要求删除销售服务费用途条款，但p1288的该句在AFTER中仍完整保留，未删除。", "evidence_verified": true, "failure_class": "EXECUTION", "affected_fact": "", "affected_obligation": "删除原销售服务费用途条款"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G22", "target_id": "Y008", "location": "p1371", "verdict": "wrong", "reason": "p1371 虽已替换为要求文本，但末尾残留了原文片段“配。”，形成重复/残缺文字，属于生成错误，需清理。", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G22 替换条款文本完整性"}
- [audit] {"kind": "audit", "code": "AUDIT_MISSED_TARGET", "rule_id": "G17", "location": "p1289", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "reason": "该残留旧文本仍存在于AFTER中，需按G17删除。", "failure_class": "VERIFICATION"}
- [sweep] {"kind": "sweep", "finding_id": "SW001", "rule_id": "G01", "location": "p93", "source_location": "p93", "quote": "基金份额类别：本基金将基金份额分为 A 类和 C 类不同的类别。在投资者认购、申购基金份额时收取认购、申购费用，不计提销售服务费的，称为 A 类基金份额；在投资者认购、申购基金份额时不收取认购、申购费用，而是从本类别基金资产中计提销售服务费的，称为 C 类基金份额", "issue": "missing_new_text", "reason": "释义的基金份额类别定义条款后未增加关于直销机构申购A类不收认购/申购费、直销机构申购C类不收销售服务费、其他销售机构申购C类持续持有超过一年不再收取销售服务费的新条款。", "artifact_start": 0, "artifact_end": 132, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW003", "rule_id": "G08", "location": "p226", "source_location": "p226", "quote": "本基金A类基金份额在申购时收取申购费用，C类基金份额不收取申购费用。通过直销机构申购本基金A类基金份额不收取申购费。通过直销机构以外的其他销售机构申购本基金的申购费率由基金管理人决定，并在招募说明书中列示。", "issue": "wrong_text", "reason": "G08要求将“本基金的申购费率由基金管理人决定，并在招募说明书中列示。”替换为包含“本基金A类基金份额在申购时收取申购费用，C类基金份额不收取申购费用。通过直销机构申购本基金A类基金份额不收取申购费。通过直销机构以外的其他销售机构申购本基金的申购费率由基金管理人决定，并在招募说明书中列示。”的完整表述，但该条款仅部分替换，未完整包含“本基金A类基金份额在申购时收取申购费用，C类基金份额不收取申购费用。”的完整语义（实际已包含，但缺少“通过直销机构以外的其他销售机构申购本基金的申购费率由基金管理人决定，并在招募说明书中列示。”的完整表述？需核对：原文已包含该句，但缺少“本基金A类基金份额在申购时收取申购费用，C类基金份额不收取申购费用。”的完整表述？实际已包含。但G08要求替换的是“本基金的申购费率由基金管理人决定，并在招募说明书中列示。”，而该条款中该句仍存在，未按G08替换为完整新句。", "artifact_start": 36, "artifact_end": 139, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW004", "rule_id": "G11", "location": "p228", "source_location": "p228", "quote": "通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。本基金C类基金份额不收取申购费用。", "issue": "wrong_text", "reason": "G11要求将原条款替换为“通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。”，但该条款存在重复和错乱文本（“通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担”），且“本基金C类基金份额不收取申购费用。”重复出现，未按G11正确替换。", "artifact_start": 0, "artifact_end": 141, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "RESIDUAL_CONFIRMED", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW005", "rule_id": "G12", "location": "p229", "source_location": "p229", "quote": "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用全额计入基金财产。", "issue": "wrong_text", "reason": "G12要求将原条款替换为“赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用全额计入基金财产。”，但该条款已符合G12要求，不应报告。", "artifact_start": 0, "artifact_end": 53, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW006", "rule_id": "G14", "location": "p232", "source_location": "p232", "quote": "基金管理人可以适当调低基金申购费率和销售服务费率。", "issue": "wrong_text", "reason": "G14要求产品有多个份额类别时将“基金管理人可以适当调低基金申购费率和赎回费率。”变更为“基金管理人可以适当调低基金申购费率和销售服务费率。”，但该条款已符合G14要求，不应报告。", "artifact_start": 112, "artifact_end": 137, "chunk": "C001", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "unresolved", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "still_reported"}
- [sweep] {"kind": "sweep", "finding_id": "SW008", "rule_id": "G15", "location": "p1288", "source_location": "p1288", "quote": "销售服务费主要用于支付销售机构佣金，及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。", "issue": "residual_old_text", "reason": "G15 requires deleting the old C类销售服务费 payment/usage clause; the old usage-scope text survives (and p1289 continues it), so the deletion was not carried out.", "artifact_start": 0, "artifact_end": 51, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW009", "rule_id": "G17", "location": "p1289", "source_location": "p1289", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "issue": "residual_old_text", "reason": "G17 requires deleting the old clause 'C类基金份额的销售服务费主要用于支付销售机构佣金...使用范围不包括基金募集期间的上述费用。'; this surviving sentence is part of that old text and was not deleted.", "artifact_start": 0, "artifact_end": 24, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW010", "rule_id": "G05", "location": "p1162", "source_location": "p1162", "quote": "在法律法规和《基金合同》规定的范围内调整本基金全部或者部分份额类别的申购费率、调低全部或者部分份额类别的赎回费率、调低销售服务费率或变更收费方式；", "issue": "residual_old_text", "reason": "G05 requires replacing '调低赎回费率' with '调低销售服务费率' (since the product has a service-fee class); the old '调低全部或者部分份额类别的赎回费率' survives.", "artifact_start": 0, "artifact_end": 73, "chunk": "C004", "round": 0, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN", "resolution": "model_clean_but_evidence_missing"}
- [sweep] {"kind": "sweep", "finding_id": "SW011", "rule_id": "G01", "location": "p93", "source_location": "p93", "quote": "基金份额类别：本基金将基金份额分为 A 类和 C 类不同的类别。在投资者认购、申购基金份额时收取认购、申购费用，不计提销售服务费的，称为 A 类基金份额；在投资者认购、申购基金份额时不收取认购、申购费用，而是从本类别基金资产中计提销售服务费的，称为 C 类基金份额", "issue": "missing_new_text", "reason": "释义的基金份额类别定义条款后未增加关于直销机构申购A类不收认购/申购费、直销机构申购C类不收销售服务费、其他销售机构申购C类持有超一年不再收取销售服务费的新条款。", "artifact_start": 0, "artifact_end": 132, "chunk": "C001", "round": 2, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW013", "rule_id": "G06", "location": "p138", "source_location": "p138", "quote": "根据基金销售情况，在符合法律法规且不损害已有基金份额持有人权益的情况下，基金管理人在履行适当程序后可以增加新的基金份额类别、或者在法律法规和基金合同规定的范围内变更现有基金份额类别的申购费率、调低销售服务费率或变更收费方式，或者停止现有基金份额类别的销售等。调整前，基金管理人需履行适当程序并及时公告。", "issue": "residual_old_text", "reason": "G06要求删除“除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。”该句在p138中未出现，故不成立。不报告。", "artifact_start": 39, "artifact_end": 190, "chunk": "C001", "round": 2, "failure_class": "VERIFICATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW014", "rule_id": "G14", "location": "p232", "source_location": "p232", "quote": "基金管理人可以在不违反法律法规规定及基金合同约定并对基金份额持有人利益无实质性不利影响的情形下根据市场情况制定基金促销计划。针对基金投资者定期和不定期地开展基金促销活动。在基金促销活动期间，按相关监管部门要求履行必要手续后，基金管理人可以适当调低基金申购费率、基金赎回费率、转换费率和销售服务费率。", "issue": "wrong_text", "reason": "产品有多个份额类别，G14要求将“基金管理人可以适当调低基金申购费率、赎回费率、转换费率和销售服务费率。”变更为“基金管理人可以适当调低基金申购费率和销售服务费率。”，但该条仍保留“基金赎回费率、转换费率”等旧表述，未按要求替换。", "artifact_start": 0, "artifact_end": 149, "chunk": "C001", "round": 2, "failure_class": "TARGET", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [sweep] {"kind": "sweep", "finding_id": "SW015", "rule_id": "G11", "location": "p228", "source_location": "p228", "quote": "通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。本基金C类基金份额不收取申购费用。", "issue": "wrong_text", "reason": "该条出现重复拼接错误：“通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的”重复出现，且“本基金C类基金份额不收取申购费用。”重复两次，未形成G11要求的干净替换文本。", "artifact_start": 0, "artifact_end": 141, "chunk": "C001", "round": 2, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "RESIDUAL_CONFIRMED"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p1288", "code": "DUPLICATE_SITE_UNEDITED", "reason": "an identical clause copy was left unedited", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p1289", "code": "DUPLICATE_SITE_UNEDITED", "reason": "an identical clause copy was left unedited", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p821", "locations": ["p821", "p1287"], "code": "DUPLICATE_SITE_DIVERGED", "reason": "identical clause copies were edited to different content", "failure_class": "VERIFICATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "", "location": "p1001", "locations": ["p1001", "p1371"], "code": "DUPLICATE_SITE_DIVERGED", "reason": "identical clause copies were edited to different content", "failure_class": "VERIFICATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G11", "location": "p228", "code": "CLAIM_JOINT_UNEXPLAINED_TEXT", "joint": true, "reason": "joint result introduced text not authorized by any selected operation", "failure_class": "VERIFICATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G11", "location": "p228", "code": "CLAIM_JOINT_VALIDATION_FAILED", "joint": true, "reason": "UNEXPLAINED_CHANGE", "validator": {"verdict": "PASS", "findings": [], "changes": [{"kind": "insert", "before": "", "after": "通过直销机构申购", "explanation": "EXPLAINED", "reason": "must_add"}, {"kind": "delete", "before": " ", "after": "", "explanation": "EXPLAINED", "reason": "authorized_replace"}, {"kind": "replace", "before": " ", "after": "类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A", "explanation": "UNEXPLAINED_SOFT", "reason": "unexplained_paraphrase"}, {"kind": "delete", "before": " ", "after": "", "explanation": "EXPLAINED", "reason": "authorized_replace"}, {"kind": "replace", "before": " ", "after": "类基金份额不收取申购费用。本基金C", "explanation": "UNEXPLAINED_SOFT", "reason": "unexplained_paraphrase"}]}, "failure_class": "VERIFICATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "p93", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G05", "operation_id": "G05:2", "obligation_id": "G05:B3:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G06", "operation_id": "G06:0", "obligation_id": "G06:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G11", "operation_id": "G11:0", "obligation_id": "G11:B1:O1", "location": "p228", "code": "CLAIM_PLANNED_EFFECT_MISSING", "reason": "operation effect is not proven at every verified site", "failure_class": "GENERATION"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G14", "operation_id": "G14:3", "obligation_id": "G14:B2:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G14", "operation_id": "G14:5", "obligation_id": "G14:B2:O3", "location": "p232", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G17", "operation_id": "G17:0", "obligation_id": "G17:B1:O1", "location": "p1289", "code": "RESIDUAL_OLD_TEXT", "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site", "reason": "exact old effect survives at this operation's business site", "quote": "销售服务费使用范围不包括基金募集期间的上述费用。", "failure_class": "GENERATION"}

**交付状态：incomplete**
