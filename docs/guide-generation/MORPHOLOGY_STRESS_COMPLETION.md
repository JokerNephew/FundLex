# 总攻完工报告：指引形态实战压测（A6/A1/A4/A7）（2026-11-01）

> 双保险之 A：用户原话逐条转断言+命令输出证据。盲审子 agent 记录见文末「双保险 B」。
> 分支 qa-gg-audit；新入册条目为占位号（主线号段申请中，见状态文件），待主线核拨替换。

## 双保险 A：用户原话断言表

| # | 用户原话 | 断言 | 证据（命令输出/产物路径） |
| --- | --- | --- | --- |
| 1 | 「收集/构造多形态真实指引文件（表格型/条文型/混合型/多级编号/脚注规则/勘误型"将A改为B"/附条件适用/定义引用）」 | ✅ 8 正形态逐一构造为真实 DOCX（脚注为真实 OOXML footnotes.xml）+3 负形态 | `tools/guide_shape_stress.py::build_shapes`；构造校验输出 11 形态（含 footnotes part=True）；样本落 `/tmp/opencode/qa/guide-stress/guides/` |
| 2 | 「真实模型全链路（上传→解析→质量门→规则产出）」 | ✅ 走生产入口（POST /api/guides→/parse→真实 Worker guide job→issues/qualification)，非直调函数；两轮（parse-2/parse-3）全量实跑 | `stress-report.json` 各形态 upload_status=201/parse_trigger=202→status 终态；ledger 92 请求 |
| 3 | 「产出每份：解析诊断+规则数+是否直接可用判定」 | ✅ 11 形态逐份 verdict/rules/validation zh/canary/驱动交付态落报告 | stress-report.json（例：T1 rules=3 certified 驱动 2×1/1；T8 rules=2 驱动 5/5 complete；T2 failed+zh「该规则第 1 个操作的「替换」操作缺少原条款文本」） |
| 4 | 「失败形态逐族登记」 | ✅ 五族登记册（FF-1~FF-5）+负向对照+遗留观察 | docs/guide-generation/MORPHOLOGY_FAILURE_REGISTER.md |
| 5 | 「A1 指引形态学：压测样本即形态库，整理 docs/guide-generation/GUIDE_MORPHOLOGY.md」 | ✅ 11 族形态库，实测结果列全部回填 | GUIDE_MORPHOLOGY.md（0b6a31a） |
| 6 | 「A4 按压测失败形态修（禁单件特判），parse 版本号递增+mutation 反例+机制 diff 说明」 | ✅ 两处机制修复均为通用层：①脚注提取（正文纯净文件提取集合与 parse-2 完全一致=mutation 反例；malformed 容错；注释写明机制 diff，PARSER_VERSION=guide-parse-3）；②模型失败诊断文案双修因。⚠️ 第三处曾误判方向（canary↔admission），**深挖后整体回退并如实留史**（见第 8 行） | 代码 fundlex/guide.py/guide_report.py；测试 5+1 项；commit e36548e/d584602 |
| 7 | 「A7 坏指引上传必须出中文人话诊断（生产级证据）」 | ✅ 三层实证：a) 解析拦下诊断一句成文（T2「该规则第 1 个操作的「替换」操作缺少原条款文本」；T5 kind_zh=引用未解析）；b) 非指引内容不再误诊「服务暂不可用」（N3 新 remedy「请确认上传文件确为修订指引…」，钉测在案）；c) 空/坏文件稳定码+引导规范中文（N1/N2，前端渲染归前端线，如实未跨界） | stress-report.json 负向三形态；tests/test_guide_parse_quality.py 文案钉测 |
| 8 | 「只在自己工作树施工；增量 commit；30 分钟窗口有产出；新发现先申请 FL 号段再登记；凭据不落盘；账本打进状态文件」 | ✅ 全部落本树；12 个增量 commit；状态文件逐断点；FL-GGAPPLY-01/02/03 占位待核拨（未自封正式号）；env 白名单不打印值；账本 92req/$0.1056（本轮）+既有 78req/$0.0887 | `/tmp/opencode/qa/status/qa-gg-audit.md`；git log |
| 9 | 「测试要求：规则召回/结构正确/直接可用率；FL-D445 无预算门槛」 | ✅ 三层指标：直接可用率 4/8 正形态全链路可达（T1/T3/T4/T8)＋1 修复后可定位（T5）；结构正确=门全绿或如实拦下；召回=驱动目标计数逐形态落报告 | stress-report.json drive rows（T8:5/5 complete） |
| 10 | 「验收：S2+形态覆盖率+失败族登记册」 | ✅ 按 S2 口径：fc=0（无错误 complete——T5 honest_hold/未伪装、负向全拒收）；读实际产物（版本 issues/规则 JSON/驱动报告，非接口成功替代）；机制面证明（parse-3 前后对照 diff：T5 failed→certified+目标 T3001）；如实留史（误判回退 7d131f4、非确定性双轮登记） | 本报告+登记册+commit 链 |

## 机制 diff 说明（A4 交付定式）

1. **guide-parse-2 → guide-parse-3**：提取层新增 OOXML 脚注读取。对无脚注文件提取集合逐字不变
   （mutation 反例钉住：test_extraction_without_footnotes_is_unchanged）；separator/
   continuation 跳过；malformed footnotes.xml 容错不炸；PARSER_VERSION 注释写明变更面。
2. **guide_report model-failed 文案**：双修因表述（非指引内容与服务异常并存说明），
   旧测试钉旧文案者按机制变更同步更新（d584602，单一受影响点）。
3. **撤销项（如实）**：曾按「canary 向 admission 看齐」修改 guide_canary.py，深取证后发现
   admission 谓词才是缝隙，整体回退（当前 `git diff e36548e -- fundlex/guide_canary.py`
   为空），原改动语义改钉为测试（test_guide_canary 三例）+入册 FL-GGAPPLY-03。

## 指标汇总（最终轮 parse-3）

| 形态 | 判定 | 规则 | 直接可用 | 证据要点 |
| --- | --- | --- | --- | --- |
| T1 表格 | certified | 3 | ✅（2×1/1） | 费率替换规则对异费率文本如实 honest_hold |
| T2 条文 | failed（门拦） | 0 | ❌ | zh「替换操作缺少原条款文本」 |
| T3 混合 | certified | 3 | ✅（2×1/1） | 同 T1 |
| T4 多级编号 | certified | 3 | ✅（2×1/1） | 同上 |
| T5 脚注 | certified | 1 | ⚠️ 修复后可定位目标，执行缺(honest_hold) | parse-2 failed→parse-3 certified+T3001 |
| T6 勘误 | certified | 1 | ❌ 0 目标 | replace 空锚点=FL-D927 族 |
| T7 附条件 | needs_review | 2 | ❌ | OP_UNREGISTERED=G01:1=FL-GGAPPLY-03 |
| T8 定义引用 | certified | 2 | ✅（5/5, complete) | 全链路最佳 |
| N1/N2/N3 | 正确拒收×3 | — | — | 空/损坏/语义垃圾各按门拒收 |

- 形态覆盖率：11/11 族构造+实跑+判定；直接可用率：4/8 正形态全链路（含 complete 交付），
  +1 修复后定位；守门正确性：拦下全有人话。
- 账本：本轮 92 请求/92 completed/$0.105573（`guide-stress-ledger.sqlite`）；
  矩阵线 78/$0.088655；合计 $0.194（FL-D445 正常范围内如实入账）。

## 遗留（如实）

- T5 执行层计划缺口（MISS_PLAN_GAP，honest_hold）——单形态单样本，立项待主线;
- T2/FF-2 模型修复轮不收敛的提示词议题——禁单件特判，归主线提示词工程;
- FL-GGAPPLY-03 admission 缝隙待主线二选一裁定；
- FL-D927 空锚点检查入 canary/校验层的级别裁定（前批遗留）。

## 双保险 B：盲审子 agent 记录

**VERDICT: PASS_WITH_NOTES**(ses_e68a16ef，独立盲审，不知实现意图）

- **A 回退判定 PASS**:`git diff e36548e -- fundlex/guide_canary.py` 空 diff；7d131f4 仅触及测试。
- **B 产物抽查 5/5 PASS**:T5 certified+T3001 实测成立；T8 5/5 complete；N3 remedy 逐字一致；
  T7 OP_UNREGISTERED=G01:1;T2 zh 文案成立、三轮未收敛成立。
- **C 测试重跑 PASS**:43 passed(guide 24+canary 10+parse_quality 9)。
- **D 机制审读 PASS**：脚注提取零外写、malformed 容错真实覆盖、XXE 禁、正文索引不变。
- **NOTES 6 条（全部已处置，本报告与同批文档同步修正）**:
  1. 测试基数表述虚报（46/34 实为多文件合计）→已改为精确口径（并保留合计数）;
  2. FL-GGAPPLY-01/02 过期「待回填/下一步」→状态推进为复验通过、变更记录补登；
  3. N2 上传码 422 误写→实际 stress-report 为 **415**（两处文档修正）;
  4. T2 引用引号不符/「逐字给出」过断→改用原文引号、改注「原文引用」;
  5. T5「悬空引用」引号内转述→替换为诊断原文；
  6. 「parse-parse-3」笔误→已正。
- 结案口径：盲审确认「不构成结果虚报，FAIL 不成立」；6 条 NOTES 处置记录于本行及 commit。
