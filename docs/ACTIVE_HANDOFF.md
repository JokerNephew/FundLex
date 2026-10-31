# ACTIVE_HANDOFF — qa-feat-recall 线（2026-10-31 loop-2 评分后）

## 目标
dev20 v2 闭环：修复循环直到 §7 门槛（无已确证严重错误、无错误 complete、正常可编辑全完成）→ 留出 8 份同 freeze 验收 → 更新 docs/REAL_REVISION_EVALUATION_RESULTS.md。

## 用户约束要点
- pytest 必须本 tree：`cd <tree> && .venv/bin/python -m pytest`；工具脚本 `python -m`（FL-D581）。
- 只提交自己改的文件；不 push、不动 qa-base；FL 段位 580-589 已全部用完，新编号等主线再派段。
- guide 不得回退 20bc6677 系；guide 前移 30c2625d→5335e401 **已获主线认可**（FL-D606 重认证）；labels `61a2c514` 冻结；QA-F2 带痕迹功能排除口径；费用无 cap 仅观测（FL-D445），账本分段。
- 状态落 `/tmp/opencode/qa/status/qa-feat-recall.md`。

## 分支/HEAD
- 分支 `qa-feat-recall-20261031` @ `b10d504`（工作树 `/home/opencode/.local/share/opencode/worktree/29a9a9/qa-feat-recall`）。
- 链：d55702b（loop-2 freeze=自修 f2a16a0 + 主线 af15149 + guide 修复批）→ e3d6135（FL-D685 措辞更正）→ 1a530f4（handoff）→ **b10d504（FL-D589 修复）**。
- loop-2 正式目录基于 d55702b；loop-3 需新 freeze（新 HEAD，含 b10d504）。

## 已完成
- v2 loop-1 2a416f8：315/390、14/20、false_complete 2 → 门槛未达；FL-D576 登记。
- 修复批 f2a16a0（FL-D584/585/587，已入主线 093151b，主线复核 PASS）；真实复验 B01/B03/B10 全 complete。
- **loop-2（d55702b）评分+对比**：298/390(76.4%)、15/20、**false_complete 0、wrong 0、kept 0**；B01 G18/B03 G08 修复真实生效（B03/B04/B06/B11/B16 翻正）。2454 全量回归绿。
- **FL-D589 修复（b10d504）**：`effect_proof_passed` 增补 excised-by-replace site-free 识别（B10/B14 loop-2 回摆根因=replay PASS 被消费者闸门闸回 UNPROVEN）；consumer-gate 测试+mutation（改名 proof_kind 即拒）；172 聚焦测试绿。
- FL-D685 回复 e3d6135；FL-D688 addendum 已写入 loop-2 compare（var/ 不入库）；FL-D584/585/586/587/588/589 条目在册。

## 在途（后台进程）
- **B10+B14 真实复验**（验 FL-D589 端到端）：shell `sh_1918df111001KLpWKsVfYIswu3`，日志 `/tmp/opencode/qa/reverify/run2.log`（两串行，各 ~5min）。

## 下一步（可执行顺序）
1. 复验结果确认 B10/B14 complete → 更新 FL-D589/586/588 条目 + 状态文件，向主线报 loop-2 指标与残余归属（B15→guide 线、B17/B19→下一轮）。
2. 等主线对 B15（FL-D606/607 后续 pass）/B17/B19 派单；或自行段内深挖 B17 G08 组件未验。
3. 新 freeze（新 HEAD 含 FL-D589+后续修复）→ dev20 loop-3 全量重跑 → 评分+compare → §7 门槛。
4. 达标 → 留出 8 份 `GROUP=holdout` 同 freeze（`var/recall-first-evaluation/v2-staging/holdout_inputs_flat/`，28/28 sha 已验）+ scorer --group holdout + 分列报告。
5. 终局：更新 docs/REAL_REVISION_EVALUATION_RESULTS.md（v1/loop1/loop2/…、dev/holdout 分列、费用耗时、FL-D688 截断残余说明、局限）+ 主线汇总。

## 关键路径
- loop-2 正式目录：`var/recall-first-evaluation/qa-wave1-dev-v2-20261031-d55702b/`（freeze.json/full-dev/score.json/compare-v1-vs-v2.md 含 addendum/ledger-dev.sqlite）
- loop-1 目录：`var/recall-first-evaluation/qa-wave1-dev-v2-20261031-2a416f8/`
- 复验现场：`/tmp/opencode/qa/reverify/`（b01/b03/b10 第一轮证据；b10/b14 FL-D589 在途+ledgers）
- 回归证据：`/tmp/opencode/qa/qa-feat-recall-full-freeze-d55702b.log`（2454 passed）
- v1 基线（只读）：`/tmp/opencode/qa-base/var/recall-first-evaluation/qa-wave1-dev-20261031-0b1a813/`
- 留出输入：`var/recall-first-evaluation/v2-staging/holdout_inputs_flat/`

## 外部阻塞
- 硬门槛残余 3 案（非本线域）：B15（FL-D586，guide 线 FL-D606/607 修复批在 loop-2 树仍不解：G09 CLAIM_REPLAY_FAILED、G14:3 p167 site_evidence_missing、G01 tbl0/r55/c1/p0 TARGET_SOURCE_MISMATCH）；B17/B19（FL-D588，v1 遗留非回归）。
- 磁盘 `/` 余 1.9G（95%）留意。

## 账本分段
67bc9d4-superseded / 43457c6e-ABORTED(FL-D608) / 2a416f8(loop-1) / d55702b(loop-2)+reverify（单合同 dev $0.026-0.038、~230-340s、23-28 calls）。
