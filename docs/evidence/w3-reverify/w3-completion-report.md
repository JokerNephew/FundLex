# W3 标签接管线 — 完工报告（2026-11-01）

线名：W3（总攻令）；树：`qa-wave2-labels2`（branch `qa-wave2-labels2-20261101`，基点 6d4d966）；
HEAD `3f17223`（共 9 commit，全部自树自有文件，主线树/共享文档零触碰）。
模型调用账本：**0 次 / $0**（全程确定性脚本；FL-D445 口径）。

## 〇、裁定摘要

W2「停滞」= 状态/证据链交付停滞，标签本体**真实已冻结并在主线 HEAD**。
W3 以接管-核验-补证为纲完成：独立重验（零代码共享）+ 分批校验输出 + 抽验备料 + 缺陷入册。
**金标层 1254 条 target 零缺陷；辅助引文层 10 处保真瑕疵（不影响分母/评分），3 项发现待主线派 FL 号。**

## 一、用户原话断言表（质量双保险 A）

| # | 原话（总攻令/纪律） | 断言 | 证据 |
|---|--------------------|------|------|
| 1 | 读本线交接料（扩波口径/r1~r3 报告/W2 边界声明） | ✅ | 本报告§〇引用 r2(74.8%)/r3(92.8%) 数据；labels-wave2.md 边界口径逐项核对（§二） |
| 2 | 对第二波 100 份合同按 selection manifest 做义务标签 | ✅ 冻结物真在 | labels sha 实测=`423c6944…`；100 case 与 selection 逐案 case_id/group/file/sha256/bytes 一致（summary.json envelope_problems=[]） |
| 3 | 不侵分母边界（不可解析/受保护单列） | ✅ | boundary 三清单=空 经复算；保护扫描 100 份 w:documentProtection 全 false 与 labels 一致；货币市场 3 案按「保留分母」口径与 boundary explicit_exclusion 清单逐案一致；零目标 16 案复算=boundary 清单 |
| 4 | 标签 schema 沿用第一波 | ✅+注记 | envelope schema=`fundlex-independent-labels-v1`（与第一波 v2 同名同构）；F-2 记字段漂移（provenance 文档有/实现无） |
| 5 | 分波冻结：每 20 份一冻结 commit，不憋全量 | ✅ | da569fe(B1)/09d09fb(B2)/a6d8e89(B3)/5196c82(B4)/af9bdc8(B5)+bbd2e0e(summary) |
| 6 | 标签只 add 自己树自有文件，共享文档禁改 | ✅ | `git show --name-only` 9 commit 仅含 `tools/evaluation/w3_*`、`docs/evidence/w3-reverify/*`、`docs/DETAIL_APPEND_W3.md` |
| 7 | 不运行引擎、不评分 | ✅ | 全程纯解析/哈希；无 gate 变量、无 var 运行目录写入 |
| 8 | references/fee-rule-v2 黄金对不混入标签分母 | ✅ | 校验器硬断言 relative 无 references/ 前缀，100/100 通过，零命中 |
| 9 | 标签自校验脚本（格式/必填字段/分母一致性）+每冻结批附校验输出 | ✅ | `tools/evaluation/w3_reverify_second_batch_labels_20261101.py` + batch-1..5.json + summary.json |
| 10 | 开工即回计划表+逐小时进度 | ✅ | 本会话首回即计划表；`/tmp/opencode/qa/status/w3-labels.md` 断点更新 |
| 11 | 主线抽验≥10 份 | ✅ 备料 | sample-pack 12 案（分层确定性）150 条 target 逐字+双哈希现场重算 bad=0 |
| 12 | 只在自己工作树施工，qa-base 禁写 | ✅ | qa-base 零写入（只读 sha 复核/报告阅读） |
| 13 | 新发现问题先申请 FL 号段再登记，禁止自封编号 | ✅ | `docs/DETAIL_APPEND_W3.md` 3 项全部【拟请派号】 |
| 14 | 凭据一律不落盘 | ✅ | 全产物 grep 无凭据形态（纯 JSON/MD/PY） |
| 15 | 后端测试命令 | N/A | 未改后端代码；校验脚本实跑输出即证据（下方） |
| 16 | 质量双保险 B：子agent 双盲复查 | ✅ | `inspection-record.md`：PASS-WITH-NOTES（sha✔/独立抽 3 案✔/实伤回核 3/3 如实/无选择性放水）；其指出的 <10 字 old_text 盲区已当场修复复跑仍 0 伤（3f17223） |

## 二、独立重验结果（与 W2 verifier 零代码共享）

- 四件套 sha 全部=登记值：labels `423c6944…`、verification `3d71bd33…`、selection `32b36f02…`、boundary `17037021…`。
- 总账重算 = 冻结 verification 全一致：targets=1254、coverage=4350、有目标案 84/100、
  uncertain=31、rule_target_totals 逐规则一致、review=completed 100/100、group 75/25。
- **金标层（targets，1254 条）零缺陷**：
  分句原子查真 + `old_text_sha256`（去空白哈希）+ `paragraph_text_sha256`（位置哈希）逐条复核，
  并被质检子agent 的独立抽案复核通过；质检指出的短 old_text 盲区修复后复跑仍 0 伤。
- **辅助引文层（coverage evidence_quote，4350 条）实伤 10 处（0.23%）**：
  G05×3（W2D11/W2D74/W2H15）模板混入「经与基金托管人协商一致」；
  G09×3（W2D33/W2D41/W2D66）掺入「对应份额类别的」；
  W2D39 指定/规定媒介；W2D43「（2）」编号+索引错位；W2D51 无省略号跳读；W2H25 单字脱落。
  逐条 diff：`defect-diffs.md`。评分不消费引文层 → **分母/gold 不受影响，不必重冻**；
  已按纪律待主线派号登记，并建议第三波标注器加引文查真收尾。
- 观察：货币市场 3 案 eligible 被盲读翻转=true 并带 10/7/8 目标——与「明确排除类型」分层存在
  语义张力，引擎运行令发出前建议主线指定裁决口径（DETAIL F-3）。

## 三、关键证据命令输出（摘录）

```
$ sha256sum docs/evidence/{labels,selection,boundary}*20261031*.json docs/evidence/labels-second-batch-20261031-v1-verification.json
423c6944…a88f5 labels-v1.json | 32b36f02…87d9 selection | 17037021…ef1d boundary | 3d71bd33…db07 verification
$ for b in 1 2 3 4 5 all; do .venv/bin/python tools/evaluation/w3_reverify_second_batch_labels_20261101.py --batch $b; done
batch-1: cases=20 targets=223 problems=1 warnings=1   # 全部 problem=辅助引文层
batch-2: cases=20 targets=263 problems=2 warnings=0
batch-3: cases=20 targets=285 problems=3 warnings=0
batch-4: cases=20 targets=269 problems=2 warnings=0
batch-5: cases=20 targets=214 problems=2 warnings=1
summary: cases=100 targets=1254 problems=10 warnings=2  # 10=引文层实伤，金标层 0
$ .venv/bin/python tools/evaluation/w3_build_sample_pack_20261101.py
sample-pack: 12 cases, 150 targets, bad=0
```

## 四、计划表实绩对照

| 阶段 | 承诺 | 实绩 | 判定 |
|------|------|------|------|
| P0 交接核验 | 21:05 | 21:05 | 按时 |
| P1-B1..B5 分批校验+commit | 21:20→22:00 | 21:20 起六批连发，~21:45 全结 | **提前** |
| P2 盲抽对照包 | 22:20 | 22:0x（commit aba6d14） | 提前 |
| P3 双保险+完工报告 | 22:40 | 质检 PASS-WITH-NOTES+盲区修复复跑，~22:30 | 按时 |
| P4 报主线验收 | 22:50 | 本报告 | 提前 |

## 五、请主线裁定事项
1. 抽验：≥10 份请从 sample-pack（12 案）或全量 labels 任选，字段对照格式见 sample-pack.md。
2. 派号：DETAIL_APPEND_W3 三项（F-1 引文保真×10、F-2 字段漂移、F-3 货币市场口径）。
3. 运行令前置：F-3 的 eligible 翻转裁决口径建议在运行令中明文。
