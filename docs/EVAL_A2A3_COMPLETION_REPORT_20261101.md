# A2/A3 完工报告（中断点版，2026-11-01，qa-feat-recall EVAL 轨）

> 状态定性：**核心可交付段完工**（schema+种子黄金集+G 层三冻结+评分器+三路基线+重大发现入册）；**忠实未竟清单**在 §4（受主线裁决/上游依赖阻塞）。质检双保险 A/B 均完成。

## A. 用户原话逐条断言表（总攻令 EVAL 轨①② + 通用纪律）

| 用户原话 | 判定 | 证据 |
| --- | --- | --- |
| A2「以 references/fee-rule-v2 33 份为种子」 | ✅ | manifest 33 对全核验 sha16 前缀；O 层 17 对 derived/1058 edits（独立 QC 抽查 fee-v2-02/05 非空复核通过）；16 边界（14 .doc+1 protected+1 OPC）如实留分母，QC 复验三类边界真实（protect/OPC 生产通道复抛实证） |
| A2「按 GG 形态清单扩充」 | ◐ 未完成（如实） | taxonomy 已兼容并记录（勘误/条文/附条件/定义引用实测四族）；8 族扩充依赖 GG A1《GUIDE_MORPHOLOGY》定稿（上游未交付），列 §4 |
| A2「标签先行冻结（纪律同合同标签）」 | ✅ | 三件 rules-gold 均先冻结（sha 链 manifest+freeze）后出评分；v2 G 层经盲读双遍（QC 独立重算 labels_sha256 吻合）；v4-errata derived 口径+盲读草案交叉验证隔离存档 |
| A2「schema 文档化」 | ✅ | docs/EVAL_PARSE_GOLDEN_SET_SCHEMA_20261101.md（防循环铁律 §6，QC 核验 L90 禁令原文） |
| A3「规则召回率/结构正确率/直接可用率」 | ✅ 三指标齐备 | score-g：召回/分支召回/结构正确；直接可用率 gate 口径（如实 0）；O 层 score-o 为第三层全形态（§4 待裁决项） |
| A3「基线分全量跑出并留史」 | ✅ G 层三路全量 | 三路真实模型 parse 归档+三件 score-g 报告（QC 独立复跑 v4 byte-identical）；var/parse-eval/PARSE_BASELINE_REPORT_20261101.md 留史；账本 16c/$0.3513 独立段 |
| 验收 S2「如实留史」 | ✅ | 量具自证段：5 处量具修正全留痕并单测锁死（6 绿）；两次 py3.6 事故自承；QC 驳回的字面失实已修正并入变更记录 |
| 纪律③「新发现先请赐号」 | ✅ | 注册链路断路写 DETAIL_APPEND_EVAL_PARSE_EVAL.md（请赐号，不自封） |
| 纪律②「30 分钟窗口可见产出」 | ✅ | 本令 15 commits（af1ac34..HEAD 含中间 failed-fix 诚实链） |

## B. 质检子 agent 双盲复查记录（QC ses_e689cfe95f…，10/10 声称核验）

- **结论：9/10 PASS**；唯一部分 PASS（声称7）为我方文档字面失实——`tests/test_generation_registry.py:124` 存在单测 caller（090cc5c 既有祖先件）；**已按 QC 意见修正 DETAIL_APPEND 措辞**（「tests/ 均无 caller」→「生产链路零调用」，变更记录自承）。核心结论（注册链路断路）QC 独立 grep 复核**成立**。
- QC 副产两处口径备注已采纳：labels_sha256 归属（manifest/文件内 vs freeze 记文件 sha）与 document.groups 嵌套层级描述，均不构成伪造但已在对答中明示。
- QC 独立验证硬证据：freeze.sha 链闭合、7 段勘误 diff 独立复核成立、score-g 独立复跑 v4 三件 byte-identical、33 对 stats Counter 复核、pytest 6 绿、commit 范围清洁（builtin/DETAIL 零触碰）。

## 交付物索引

- schema：docs/EVAL_PARSE_GOLDEN_SET_SCHEMA_20261101.md
- 黄金集：docs/evidence/parse-golden-v1/（manifest/freeze/checks；三指引 G 金；33 对 O 金）
- 工具：tools/evaluation/parse_golden_o_tier.py / parse_golden_g_finalize{,_v4,_v4errata}.py / parse_score.py；单测 tests/test_parse_score_metrics.py（6 绿）
- 基线：var/parse-eval/（runs ×3、score-g ×3、PARSE_BASELINE_REPORT_20261101.md v2、ledger-parse.sqlite）
- 附册：docs/DETAIL_APPEND_EVAL_PARSE_EVAL.md（注册断路请赐号件，QC 修正版）

## §4 忠实未竟清单（阻塞归属明示）

| 件 | 阻塞 | 下一动作 |
| --- | --- | --- |
| A3 score-o 直接可用率双口径 | **注册断路（请赐号在档）**：gate 未修跑引擎=绕口径造假分 | 主线裁决后：gate 口径+注册回流口径补测 17 对 |
| A2 片4 形态 8 族扩充 | GG A1《GUIDE_MORPHOLOGY》未交付（其线任务②） | 上游定稿后按族收集/构造、逐批冻结 |
| `.doc` 14/33 种子 | 工具链 docx-only | 报主线裁决抽取设施（已三处登记）后 O 层补全 |
| 保护/OPC 2 对 | 生产通道 fail-closed | 报主线裁决只读通道后补 |
| B1 第二波 100 | W3 标签冻结（观察哨在哨） | 标签到位即跑，G14 观测并入 |
