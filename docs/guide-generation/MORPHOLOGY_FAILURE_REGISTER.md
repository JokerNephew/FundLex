# 形态压测失败族登记册（2026-11-01，总攻 A6 收官）

> 口径：两轮真实模型全链路（生产 API 上传→解析 worker→质量门→（certified 者）引擎直驱），
> 产物 `/tmp/opencode/qa/guide-stress/stress-report.json`；账本
> `guide-stress-ledger.sqlite`。入册条目以占位号待主线核拨（申请段 FL-D998~）。
> FF=失败族；「已修」均指本树机制修复（非单件特判），主线未并。

## FF-1 脚注规则族：**已修复（guide-parse-3）**
- 样本：T5_footnote_rules（正文「见脚注①」，规则实文在 word/footnotes.xml）。
- 一轮（parse-2）：版本 **failed**。提取层不读 footnotes.xml——规则全文不可见；模型保守
  noop+notes 注明悬空，验证器中文诊断「指南第[1]段要求按脚注①口径执行，但脚注①的具体
  内容未包含在指南文本中」（kind_zh=引用未解析），三轮修复不收敛，fail-closed 正确。
- 修复（FL-GGAPPLY-01，commit e36548e）：提取层读取脚注（separators 跳过、序号标记
  「脚注<n>：」、malformed 容错、正文索引不变+mutation 反例）；PARSER_VERSION=guide-parse-3。
- 复验（parse-3）：**certified（1 规则）**，引擎直驱在两份冻结合同上**真实定位目标
  T3001**——链路打通；执行计划轮未为该义务生成计划（MISS_PLAN_GAP）交付 honest_hold，
  未伪装完成（执行侧缺口另行观察，见「遗留观察-1」）。

## FF-2 条文型「替换无旧文」族：**守门正确拦下，机制摩擦面登记**
- 样本：T2_article_only（纯第X条，无领域标题/无旧文引用）。
- 两轮一致：版本 **failed**，GUIDE_VALIDATION_UNCLEAN；确定性门报
  「该规则第 1 个操作的「替换」操作缺少原条款文本」（生产级中文原文引用）。
- 判定：条文型指引本身不给旧条款全文时，模型倾向造无旧文 replace；门 fail-closed 正确、
  诊断达标。模型修复轮三轮未收敛属摩擦面——提示词层是否加「条文形态须先旧文后新文」
  引导属主线提示词工程议题（禁单件特判原则下本线不动）。

## FF-3 勘误型「新文案非逐字」族：**门正确拦下+模型可自愈+空锚点同族**
- 样本：T6_errata_ab（「将『1.5%』更正为『1.2%』」）。
- 一轮：失败 GUIDE_TEXT_NOT_VERBATIM（新文案系模型改写合成而非指引原文）——门+中文诊断
  达标；二轮：模型自愈逐字产出，**certified**。
- 但 certified 后直驱 0 目标：replace 操作 old_text_variant=null（FL-D927 空锚点族，
  已在前批入册，编号 FL-D927 正式）——门内声明：本族的真实可用性缺陷归属 FL-D927 处置。

## FF-4 语义垃圾误诊族：**已修复（A7 双修因诊断）**
- 样本：N3_garbage_semantic（菜谱/天气/纪要合法 DOCX）。
- 一轮：parse_failed GUIDE_MODEL_FAILED:MODEL_SCHEMA_INVALID，诊断「多为服务暂不可用
  或限流，稍后重试」——**事实性误诊**（内容不是指引，重试永无效）。
- 修复（FL-GGAPPLY-02，e36548e+d584602）：说明文案改为「模型未能解析该内容（码）；
  请确认上传文件确为修订指引…；若确认是指引仍失败，多为服务暂不可用或限流…」——
  双修因、通用、无单件特判；钉测在案。复验 N3 同码失败+新文案生效。

## FF-5 附条件适用「generated 第二分支」族：**入册待主线裁定（FL-GGAPPLY-03）**
- 样本：T7_conditional（如果…则…否则…）。
- 两轮一致：parsed（validation 全绿）但 **needs_review**：canary
  GUIDE_CANARY_OP_UNREGISTERED=G01:1。深层取证证实**三层谓词不一**：jobs admission
  （registry.py，generated+STRATEGY 跳过）放宽、运行时执行仍 fail-closed、启用门
  canary 与执行一致（保护性正确）。曾误判方向修 canary、深挖后整体回退并改钉测试
  （7d131f4，如实留史）——admission 缝隙待主线二选一裁定。

## 负向对照（非缺陷，正确行为证据）
- N1_empty：parse_failed GUIDE_SOURCE_EMPTY（issues 稳定码；中文映射在 api_content
  引导规范，渲染归前端线）。
- N2_corrupt：上传即 422 UNSUPPORTED_FILE，不入解析。

## 遗留观察
- 遗留观察-1：T5 脚注形态修复后，规则可 certified、引擎可定位目标（T3001），但计划轮
  OPEN_OBLIGATION/CLAIM_REPLAY_FAILED（MISS_PLAN_GAP）诚实扣件——执行层对「无章节
  信号+脚注来源规则」的计划生成缺口，待主线单独立项（本线样本量 1 形态，不宜过度推论）。
- 与上一批入册的重合面：replace/delete 空锚点（FL-D927）、admission 缝隙（FL-GGAPPLY-03）
  已分别独立条目，本册只做族级索引。
