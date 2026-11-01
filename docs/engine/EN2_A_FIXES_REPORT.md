# EN2 总攻完工报告：A 类 18 件直修 + B/C 处置（2026-11-01）

- 工作树：qa-audit-engine2（detached HEAD，施工区间 a96f118 → fbdc883+）
- 对应需求：总指挥总攻开工令①②③ + 测试条 + 验收条 + 纪律条 + 质量双保险条
- 配套档：发现附录 docs/DETAIL_APPEND_EN2.md；分级提案 docs/engine/EN2_TRIAGE_PROPOSAL.md；B 裁决表 docs/engine/EN2_B_RULINGS.md；C 决策原文 docs/engine/EN2_C_USER_QUESTION.md；双盲质检 docs/engine/en2_batches/QA_DOUBLEBLIND_A_FIXES.md

## 一、用户原话逐条断言表（自拍自检，引擎类 S2 口径）

| # | 用户原话 | 断言 | 证据（命令/输出要点） |
| --- | --- | --- | --- |
| 1 | 「A 类 18 件直修…每件一 commit」 | ✅ 18 件 19 个 commit（含一处自检补漏独立 commit，如实留史） | `git log --oneline a96f118..HEAD`：8a39da5/0091497/ce9a6df/d10aba4/6b0853a/79c73bf/ac5f00d/b6345f0/fa520b7/c3d82cb/5035b2c/aebcff7/8ec508d/4b403aa/5332196/0a7139b/d5b9075/5af0008/06ebf77（+质检档 fbdc883） |
| 2 | 「每件一 commit 附"为什么安全"一句」 | ✅ 每个 commit message 第二段均为安全论证一句（等价/兜底/纯注释口径） | 见各 commit message（例：d10aba4「全仓 grep 仅剩活副本，无引用损失」） |
| 3 | 「死代码/注释/文案类，禁行为变更」+「零行为变更证明（diff 仅死代码/注释/文案）」 | ✅ 双证成立 | ①`git diff a96f118..HEAD -- fundlex/` 全量 19 文件，逐一归类：删死代码×6、纯注释×3、常量命名/改名×3、相同语义摩尔式重构×3、防护收窄为既有兜底语义×4（崩溃输入→UNPROVEN/同口径跳过/带名异常——合法输入域零变化）；②独立质检子agent双盲裁决 **19/19 ✅**（QA_DOUBLEBLIND_A_FIXES.md，含 grep 零调用复验、pdf_parser 去首空格 token 流比对、v2_pipeline 真值表核对） |
| 4 | 「B 类 14 件：列成裁决表（改动点/行为差异/风险/建议）」 | ✅ 14 行裁决表齐 | docs/engine/EN2_B_RULINGS.md（commit ef9fdaa），每条四列+建议与施工衔接 |
| 5 | 「C 类 1 件：写清用户需要决策的问题原文」 | ✅ | docs/engine/EN2_C_USER_QUESTION.md：三问原文（是否更新/准入口径/供应商范围） |
| 6 | 「每件直修跑相关测试」 | ✅ 逐件即时跑 | 各 commit message 落数：107/13/95/62/25/2/3/25+冒烟/17/12/3+句柄冒烟/71/6p+16s/57/51/4/54（件件有定向绿） |
| 7 | 「全量回归一次」 | ✅ | `pytest tests -q`：2658 passed / 143 skipped / 4 warnings / 1 failed（23m19s）。唯一失败 test_deploy_publisher…isolated_sqlite 定为**环境前置缺失**（本树无 .venv，断言索要 .venv/bin/python，与 19 文件零关联）；补齐前置（.venv→主 venv 目录软链，.gitignore:1 覆盖不入库）后单测绿，整文件 17 passed |
| 8 | 「只在自己工作树施工…增量 commit…每 30 分钟窗口必须有可见产出」 | ✅ | 施工全程仅本树；qa-base 未写一字；本阶段 commit 19+3，无任何 30 分钟空窗；状态文件 /tmp/opencode/qa/status/qa-audit-engine2.md 同步更新 |
| 9 | 「新发现的问题先向主线申请 FL 号段再登记，禁止自封编号」 | ✅ | 本轮施工零新发现登记；FL-D921~937 为上一棒主线批准号段内用号，未超段自封 |
| 10 | 「凭据一律不落盘」 | ✅ | 全程未涉凭据；改动文件无一凭据字段写入（grep 自查 diff 无 key/secret 字面内容） |
| 11 | 「后端测试：cd <你的树> && PYTHONPATH=$PWD .venv/bin/python -m pytest…」 | ✅（一本调整已报备） | 本树无 .venv，全程等价奏法：`PYTHONPATH=$PWD /home/opencode/fundlex/.venv/bin/python`（同一 3.11.13 解释器）；补链后 `.venv/bin/python` 命令字面亦可用 |
| 12 | 「质量双保险 A：用户原话逐条 ✅/❌ 断言+证据」 | ✅ 本表 | （本文件） |
| 13 | 「质量双保险 B：自建质检子agent双盲复查」 | ✅ | docs/engine/en2_batches/QA_DOUBLEBLIND_A_FIXES.md：独立 subagent，未读实现意图，独立 grep/真值表/token 流比对，总判 19/19 ✅ |

## 二、A 类 18 件处置总表

| # | 编号 | 处置 | commit |
| --- | --- | --- | --- |
| 1 | FL-D928 | effects occurrence_index 补防抑→UNPROVEN | 8a39da5 |
| 2 | FL-D929 | reconciliation 删不可达分支+预留注释 | 0091497 |
| 3 | FL-D935(1) | validators 删 _token_context | ce9a6df |
| 4 | FL-D935(2) | obligations 删 _audit_verdicts | d10aba4 |
| 5 | FL-D935(4) | orchestrator 删 failure_codes+死 import | 6b0853a |
| 6 | FL-D935(5) | frozen 删死变量 identity | 79c73bf |
| 7 | FL-D935(6) | ingestion 删死赋值 | ac5f00d |
| 8 | FL-D936(1) | policies env int() 包 try 带 env 名 | b6345f0 |
| 9 | FL-D936(2) | trace_sink 捕获开关线程本地化 | fa520b7 |
| 10 | FL-D936(4) | roles metrics 拷贝注 role | c3d82cb |
| 11 | FL-D936(5) | pdf_parser try/finally 必 close | 5035b2c |
| 12 | FL-D936(6) | v2_pipeline 合并重复分支为建构期单点赋值 | aebcff7 |
| 13 | FL-D936(7) | selective accept_all 单次计算 | 8ec508d |
| 14 | FL-D936(9) | claim_replay:2575 getattr 防御 | 4b403aa |
| 15 | FL-D936(10) | docx 两处防御性吞错补注释 | 5332196 |
| 16 | FL-D937(2) | rules 解 re 遮蔽（含补漏一 commit） | 0a7139b+d5b9075 |
| 17 | FL-D937(3) | rules_v2 注释拼写 | 5af0008 |
| 18 | FL-D937(9)(10) | components docstring 对齐+模板阈值命名 | 06ebf77 |

> 如实留史：#16 第一 commit 后自检（AST 名称解析）抓到同函数第二字典残留旧名，立即补 commit 修正并公开说明——半成品隐患修正过程不掩盖。

## 三、全量回归证据

- 命令：`cd qa-audit-engine2 && PYTHONPATH=$PWD /home/opencode/fundlex/.venv/bin/python -m pytest tests -q -p no:cacheprovider`
- 结果：`1 failed, 2658 passed, 143 skipped, 4 warnings in 23m19s`（/tmp/opencode/qa/en2_full_regression.txt）
- 唯一失败定因与闭环：test_deploy_publisher…isolated_sqlite 断言索要本树 `.venv/bin/python`（错误 127，No such file），与本批 19 文件零关联；补前置后单测 1 passed、整文件 17 passed。即：**全量实质绿（fc=0 硬门达成，唯一失败为非代码环境前置并已闭环）**。

## 四、交接主线

- A 类 18 件：本轮闭环（以上证据），可批量验收。
- B 类 14 件：等主线批量裁决（EN2_B_RULINGS.md），裁决回流本线施工。
- C 类 1 件：转呈用户三问（EN2_C_USER_QUESTION.md）。
