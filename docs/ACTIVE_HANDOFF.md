# ACTIVE_HANDOFF — qa-feat-recall 线（2026-10-31 17:40）

## 目标
dev20 v2 闭环：修复循环直到 §7 门槛（无已确证严重错误、无错误 complete、正常可编辑全完成）→ 留出 8 份同 freeze 验收 → 更新 docs/REAL_REVISION_EVALUATION_RESULTS.md。

## 用户约束要点
- pytest 必须本 tree：`.venv/bin/python -m pytest`；工具脚本 `python -m`（FL-D581）。
- 只提交自己改的文件；不 push、不动 qa-base；段位 FL-D580..589（含 589 尚未用）。
- guide 不得回退 20bc6677 系；labels `61a2c514` 冻结；QA-F2 带痕迹功能排除在评测口径外；费用无 cap 仅观测（FL-D445），账本分段。
- 状态落 `/tmp/opencode/qa/status/qa-feat-recall.md`。

## 分支/HEAD
- 分支 `qa-feat-recall-20261031` @ `d55702b`（工作树 `/home/opencode/.local/share/opencode/worktree/29a9a9/qa-feat-recall`，freeze 时 clean）。
- 已合并：主线 af15149 + qa-feat-guide 修复批（FL-D606×5/607×3/644/645）+ 自修 f2a16a0（FL-D584/585/587）。

## 已完成
- v2 正式轮 2a416f8：315/390(80.8%)、14/20、false_complete 2（B01/B03）→ 门槛未达。FL-D576 数据登记。
- 修复（全带测试+mutation+真实复验 B01/B03/B10 全 complete）：FL-D584 G18 kernel 排序、FL-D585 replace 吞除闭合、FL-D587 G08 变体残目标。
- 登记 FL-D576/584/585/586/587/588（586/588 open）。
- 宽面 763 绿；冻结面待回归结果。

## 在途（后台进程）
1. dev20 第 3 轮：`qa-wave1-dev-v2-20261031-d55702b/run-dev.log`（~75min）。
2. 全量回归：`/tmp/opencode/qa/qa-feat-recall-full-freeze-d55702b.log`（~60min）。

## 下一步（可执行顺序）
1. 回归绿 + dev20 完 → `WAVE=qa-wave1-dev-v2-20261031-d55702b bash var/.../$WAVE/run_v2_post_dev.sh`（评分+对 v1 对比）。
2. 门槛评估：false_complete=0 且无可编辑未完成 → 达标；否则归因→修复→再循环。
3. 达标 → 留出 8 份 `GROUP=holdout` 同 freeze 跑 + scorer --group holdout + 分列报告。
4. 更新 docs/REAL_REVISION_EVALUATION_RESULTS.md（v1/v2loop1/v2loop2、dev/holdout 分列、费用耗时、局限）。
5. 更新 FL-D586/588/644 条目状态；状态文件收尾。

## 关键路径
- 正式 v2(loop1): `var/recall-first-evaluation/qa-wave1-dev-v2-20261031-2a416f8/`（compare-v1-vs-v2.md）
- loop2 冻结： `var/recall-first-evaluation/qa-wave1-dev-v2-20261031-d55702b/freeze.json`（guide 前移 5335e401，deviation_flag 已留主线否决口）
- 复验现场： `/tmp/opencode/qa/reverify/`（b01/b03/b10 + ledgers）
- v1 基线： `/tmp/opencode/qa-base/var/recall-first-evaluation/qa-wave1-dev-20261031-0b1a813/`
- 留出输入： `var/recall-first-evaluation/v2-staging/holdout_inputs_flat/`（28/28 sha 已验）

## 外部阻塞
- 无。磁盘 `/` ~1.9G 留意。
- guide sha 前移待主线事后确认（已 flag）。
