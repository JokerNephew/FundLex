# EN2 · D2 守门地基修复完工报告（2026-11-02）

- 基座：主线 `45d7d07`（FL-D1012 事故登记处；qa-audit-platform 树全灭后守门地基重起点）
- 施工区间：db6014f..HEAD（8 commit）
- 依据：PL2 修复卡（卡原文 PL2 事故前已通读+抽验复跑，卡内容上下文完整留底）+ GG《RELEASE_GATE_PROPOSAL》四层守门 + 施工序（本线 EN2_D2_REVIEW_AND_PLAN.md，主线已收编）

## 一、判词/卡逐条断言表

| # | 卡/判词 | 施工 | 证据 |
| --- | --- | --- | --- |
| FL-D950 | drift 方向警示（守门实装序①，收益/风险最高） | ✅ `486cf4f` | rc=3 疑似反向同步+--ack 放行；tests/test_drift_reverse_sync.py 6/6；生产现跑 rc=0 |
| FL-D940（P0-①） | 旧部署器覆写生产 | ✅ `6f489b1` | 模块顶 SystemExit，python -m/import 均 rc=1 只打阻断语无凭据（SystemExit 不被 except Exception 捕获、无 import 方） |
| FL-D948（P0-②） | GC 引据不全可误删交付物 | ✅ `e82684e` | referenced_keys 补 compare_pair_files/compare_artifacts/compare_selection_artifacts/gg_artifacts；tests/test_object_gc.py 双反例（四处注册存活件过龄 --apply 仍存活）2/2 绿 |
| FL-D954（P0-③） | 27 用例 gitignored fixture 静默 skip | ✅ `8a3697b` | tests/fixtures/evaluation/p6-dev-round1-01/D01 入库（diff -rq 与 var/ 源逐字节一致）；REAL 改 __file__ 锚定；两文件 34 passed / 0 skipped |
| FL-D953（P0-④） | fakes 与真实 ModelRouter 漂移 | ✅ `744a18f` | identity 逐 role 对齐真实 10 字段 + `_value` 兜底 AssertionError + 3 个新任务类 stub；8 个引用文件 118 passed + 1 skipped |
| FL-D941（守门实装②） | cleanup 删表不全+p6-% 模糊 | ✅ `8398cee` + 质检回流 `82c1175` | 级联覆盖 compare 三级+gg 全 run 挂点 20 表+集成/飞书/guide_jobs+历史面；p6-% 默认排除须 --include-broad-p6；差集断言双段（账号域+gg 子表域）rc=3；sqlite 副本演练账号清零、非白名单/admin 无损、21 表清零 |
| FL-D951（守门实装③） | browser 10s 硬等待 | ✅ `d162b4b` | 三循环改 expect_request（12s 上限非步进）；FUNDLEX_BROWSER_TESTS=1 双参数绿；卡写 expect_response 但拦截状态下 response 事件不自洽，按语义落 request 锚（如实判词口径在 commit 里注明） |
| FL-D946（守门实装④） | cloud_verify 断言陈旧+清理静默 | ✅ `3ac6a8c` + 质检回流 `82c1175`（代码面） | ①前缀 cloud-run-verify-（入白名单）②清理失败 rc=2 ③隧道改 capabilities JSON（engine.id），不过 rc=1 门禁 ④dir() 死代码删 ⑤tmp 带 pid ⑥seal 后 3 分钟终态铃、未终态不删行（skipped 留现场） |

## 二、验收证据（S2 口径）

- **全量回归**：`tests/ -q` = 2787 passed / 104 skipped / **0 failed**（30m42s，质检回流前状态树；回流两件仅动 shell 与嵌入串，已分别 bash -n / ast compile 复核，pytest 覆盖面无涉）。
- **定向复核**：171 passed + 1 skipped（deploy_publisher/GC/revision_api/selective/guide 全线）+ expect_request 浏览器双参数绿。
- **双盲质检**：独立 subagent（总判"一审通过 conditional"），抓到 cleanup 级联盲区（gg 无 FK 子表）+cloud_verify 三微瑕，全部在 `82c1175` 闭环；同 commit 入选要求无超卡顺手改动确认成立。
- **事故善后**：C1/D2/D4 三 commit 已被主线并入（事故前），本线真实损失（P0 四卡代码）已在基座上一卡一卡重做并登记入史。

## 三、如实留口（不越权线）

1. **FL-D941 生产 --apply** 与 **FL-D946 全链路实地验证** 属部署线维护窗口执行（写型验证超审计线授权，施工卡原判词同口径）；代码面齐全随时可跑。
2. **批 E 移交回收**（test_compare_polling_gate.py:12 / test_review_render_index.py:15）在 d2a9bc5 属主线，须回收确认——D2 序中本线已列入回收行，等属主报账。
3. **GG 四层守门启用** 须等上面 1-2 复票+P2 排期（EN2_D2_REVIEW_AND_PLAN.md §二）——不建议在漏底前启用。
