# W3 交付物独立质检记录（双盲复查）

- 质检员身份：独立 QA subagent（不采信施工方结论，全部自行复核后比对）
- 日期：2026-11-01
- 施工树：`/home/opencode/.local/share/opencode/worktree/29a9a9/qa-wave2-labels2`（分支 qa-wave2-labels2-20261101）
- 被检对象：W3 独立重验交付物（`tools/evaluation/w3_reverify_second_batch_labels_20261101.py`、`docs/evidence/w3-reverify/{batch-1..5,summary}.json`、`defect-diffs.md`、`sample-pack.{md,json}`、`docs/DETAIL_APPEND_W3.md`）
- 纪律遵守：除本文件外未写施工树任何文件；QA 脚本置于 `/tmp/opencode/qa-inspect/`；未运行引擎、未调用模型（所有核对为本地 python-docx/哈希/文本比对）。Python 用 `/home/opencode/fundlex/.venv/bin/python`（系统 python3=3.6 不可用，按 AGENTS.md）。
- 结论：**PASS-WITH-NOTES**

---

## 1. 声明 sha256 vs 实测

命令：`sha256sum docs/evidence/labels-second-batch-20261031-v1.json`

- 实测：`423c6944687a6006d493d3f8dff4b4cb32593cc6acc26c2e2b3fb423622a88f5`
- 施工方 summary.json 声明：同值。
- **一致 ✔**

## 2. 随机 3 案独立抽验（QA 自选案，非施工方 sample）

选案方法：`random.Random(2026110199).sample(100案ID, 3)`，得 **W2D04、W2D45、W2D46**（均不在施工方 sample-pack 案清单 W2D30/W2D43/W2H01/W2H13/W2H25 内）。
QA 独立脚本 `/tmp/opencode/qa-inspect/indep_check.py`：仅用 python-docx 逐段抽取，对每条 target 核对 ① old_text 去空白后是否逐字落在 `paragraph_index` 所指段内（append 特例同样核其锚段与哈希）② `paragraph_text_sha256 == sha256(python-docx 段落 raw text)` ③ `old_text_sha256 == sha256(去空白 old_text)` ④ 源文件字节 sha256 与 paragraph_count。

结果摘要：

- **W2D04**（广发中证1000ETF，index/single-class）：源 sha 一致、段落数 1300 一致；targets=0（零目标案）。与施工方 batch-1.json 一致（该案无任何 problem/warning）。✔
- **W2D45**（广发招泰混合，long/hybrid/multi-class）：targets=20，20/20 条全部 `old_text 逐字在段内=是、pos_hash=True、old_hash=True`，含 3 条 append 特例（G01/G03 pi=88/118，G16 pi=830/1283）锚段真实；源 sha、段数 1406 均一致。batch-3.json 对该案零 problem。✔
- **W2D46**（广发招瑞 FOF，maybe-satisfied 层）：targets=1（G05 replace pi=138），哈希与原文三验全过；该案大量 G 规则为 satisfied 判定而非 target。batch-3.json 零 problem。✔

比对结论：3 案 QA 独立实测与施工方 batch-1/batch-3 结论完全一致，未发现施工方漏报。

## 3. defect-diffs.md 三条“实伤”亲自回原文核对

QA 脚本 `/tmp/opencode/qa-inspect/defect_check.py`，抽取标签 evidence_quote 与 python-docx 原文段落逐字比对：

1. **W2D11 G05 pi=135（声称：实质掺入）**——核对为真。引文含「、基金合同的约定」「经与基金托管人协商一致」，原文段落该两处均不存在（QA 布尔核对 引文 True/原文 False×2）；QA 自算 opcode 与 defect-diffs 记载差异点逐条吻合（两处 delete 一致）。✔ 掺入属实。
2. **W2D51 G15 pi=1312（声称：未带省略号跳读）**——核对为真。标签引文原样在「…由注册登记机构代收，按」处截断，原文为「…代收，**注册登记机构收到后**按…」；QA 唯一 opcode=`insert '注册登记机构收到后'`，即跳读且未带省略号属实。（QA 中字串布尔核对显示 False 系因引文恰在“按”字截断所致，不影响结论。）✔
3. **W2H25 G14 pi=234（声称：单字脱落）**——核对为真。引文「基金赎回**费**和基金销售服务费率」，原文为「基金赎回**费率**和基金销售服务费」；布尔核对 引文含脱落版=True、原文仅含“率”版。✔ 脱落属实。

比对结论：3/3 条实伤记录如实，施工方未夸大也未淡化（其 ratio 与 QA 全段比对基数不同，方向一致）。

## 4. 施工方脚本“选择性放行”审查（静态审计 + 只读复算）

通读 `w3_reverify_second_batch_labels_20261101.py` 全文，并做只读复算：

- **未见放水证据**：施工方自己检出的 10 条 evidence_quote 实伤全部进 `problems`（非 warnings），summary 账实一致（QA 只读复算：targets=1254、coverage=4350、有目标案=84、uncertain=31、零目标案=16 与 boundary 清单一致，与 summary.counts 完全相符）；脚本在 problems 非空时退出码=1，未把自伤降级或隐瞒；DETAIL_APPEND_W3.md 如实登记为观察项 F-1，并如实说明“金标层零伤、引文层局部夸大”。✔
- **发现的校验覆盖盲区（注记，非放水）**：`fragments()` 丢弃 `<10` 字片段（`w3_reverify…py:111`），而复算显示 **116/1254 条非 append target 的 old_text 短于 10 字**（典型为「调低赎回费率」6 字）。对这部分 target，脚本不执行内容级原文查真；`old_text_sha256` 仅为标签字段间自洽校验、`paragraph_text_sha256` 只锚定段落本身，均不锚定“old_text 在原文在场” ⇒ 短 old_text 的“在场真实性”无硬校验。但 QA 对抽中案的短 old_text（如 W2D45 T003「调低赎回费率」）做了独立验证均在原文在场；且该盲区对**所有**标注方产物一视同仁，不构成对施工方自身缺陷类目的选择性放行。
- 次要观察：哈希字段非必填（`TARGET_REQUIRED` 不含 `old_text_sha256`/`paragraph_text_sha256`，缺失即跳过），但只读复算 1254/1254 条均实际携带两哈希，现状无影响。

## 5. 结论

**PASS-WITH-NOTES**

1. 冻结声明 sha 与实测一致。✔
2. QA 自选 3 案（W2D04/W2D45/W2D46）独立抽验，targets/append 特例/paragraph_index 位置真实性全部属实，与施工方 batch 结论一致。✔
3. 抽 3 条 defect-diffs 实伤回原文核对，3/3 如实。✔
4. 脚本无选择性放行；注记两条：(a) `<10 字` 短引文/old_text（116 条）内容级查真盲区，建议后续校验器把 `old_text` 直接做整串在场断言（代价极低）；(b) 10 条 evidence_quote 引文层实伤为真实数据瑕疵（施工方已诚实登记 DETAIL F-1），位于评分不消费的辅助层，不影响金标层与分母，但下游引用引文层时须知情。

证据脚本：`/tmp/opencode/qa-inspect/indep_check.py`、`/tmp/opencode/qa-inspect/defect_check.py`（只读，不落施工树）。
