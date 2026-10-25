# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：8beacaba3446f7e7e6db1d8cdd3036f0eb086139d6e89a9d27e3552ec658e45d
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 2（A类、C类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 27，已符合 8，不适用 2；计划修改 18
- 审计轮次：2；未决问题 0
- 查漏：块 4，发现 2，未解决 0，缺口 0
- 模型调用：34；估算费用：0.027286650000000003

## 每规则处置

- G01：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S03', 'S04']
- G02：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S03', 'S04']
- G03：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S04', 'S03']
- G04：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S04', 'S03']
- G05：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S04']
- G06：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/4；章节 ['S04']
- G07：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G08：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G09：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G10：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S07']
- G11：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G12：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S07']
- G13：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/2；章节 ['S07']
- G14：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 1/1；章节 ['S07']
- G15：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S16']
- G16：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/3；章节 ['S16']
- G17：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 3/3；章节 ['S16']
- G18：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17']
- G19：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20']
- G20：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20']
- G21：覆盖 no_target_found；目标 0（应改 0 / 已符合 0 / 不适用 0）；审计完成 0/0；章节 ['S20']
- G22：覆盖 targets_found；目标 1（应改 1 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20']

## 审计轮次

- 第 0 轮（full）：规则 14，结论 23，另报 1，丢弃 1，问题 5
- 第 1 轮（incremental）：规则 2，结论 3，另报 0，丢弃 0，问题 0

## 查漏轮次

- 第 0 轮：块 4，发现 2，丢弃 3
  - SW001：G05 p133 residual_old_text → resolved
  - SW002：G15 p822 residual_old_text → resolved

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p822：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1306：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G12", "target_id": "T3001", "location": "p219", "reason": "RECALL_TARGET_UNRESOLVED", "failure_class": "TARGET"}
- [obligation] {"kind": "obligation", "code": "OPEN_OBLIGATION", "rule_id": "G06", "obligation_id": "G06:B1:O1", "operation_id": "G06:0", "branch_id": "B1", "applicability": "TRUE", "failure_class": "TARGET", "reason": "CLAIM_REPLAY_UNPROVEN", "expected_site": "基金的基本情况"}

**交付状态：incomplete**
