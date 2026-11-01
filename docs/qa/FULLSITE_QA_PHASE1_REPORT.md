# 走查线阶段一完工报告（FULLSITE_QA PHASE-1 REPORT）

线别：qa-fullsite-qa ｜ 日期：2026-11-01 ｜ commits：`93c0dc2`（v1.0 主体）+ `ac1811d`（双盲复查整改 v1.1）
交付物：`docs/qa/FULLSITE_CHECKLIST.md` v1.1、`tools/qa/fullsite/{shots.py, manifest.json, perf_budget.json, README.md}`

## A. 用户原话→断言自拍表（强制）

> 原话：「所有开发完之后，要对所有的链路进行检查，我说的是所有，你不要之后又跟我说你有页面没有检查到，绝对不能出现任务bug以及非常卡顿的情况。以及要对所有的页面及子页面截图检查，我说的是所有」
> 说明：A1/A2/A3/A4 是**阶段二执行判定基准**，已写入检查单卷首；本表断言的是**阶段一交付是否足以支撑这四条在阶段二可机械执行、无主观空间**。

| # | 断言 | 判定 | 证据（可当场重放） |
| --- | --- | --- | --- |
| A1 | 全站每个页面/子页面/状态都有唯一编号与截图位，不漏 | ✅ | 检查单 103 行 ↔ manifest 103 条程序化双空集核验：`doc: 103 manifest: 103 对称差: []`；V1 11 视图与 `app.js:170 VIEW_TITLES`(11 key)+`compare.html` 11 个 `id="view-*"` section 逐一吻合；V2 20 条 Route 与 `App.tsx:29-48` 吻合；双盲复查反向虚构项抽查=0 |
| A1b | 覆盖枚举本身经过独立复核 | ✅ | 质检子agent（双盲）发现 2 处实质漏项（V2 CompareCard、V2 补传 `?taskId=`），已修：FS-V2-21/22 入行入册（`Guides/index.tsx:147`、`NewTask/index.tsx:50-54` 代码实证） |
| A2 | 每条链路有起止与判据 | ✅ | 检查单 §5 LC-01~08（覆盖原话「登录→上传→解析→修订→比对→下载」六步+指引生成+错误权限），每条含通过判据列 |
| A3 | 「卡顿」有冻结级量化阈值，杜绝主观 | ✅ | 检查单 §2 阈值表（A/B/C 三页级 × 6 指标 × warn/fail，median of 3，移动×1.5 取整百位）+ `perf_budget.json` 程序化逐格核验「无差异（含 B/C heavy 格）」；measure_click 超时=❌；ready 超时=❌；反馈 500ms 死线。**待主线审定后冻结**（本线唯一待办） |
| A4 | 工具链跑出真实截图+性能数，不是纸面骨架 | ✅ | 三轮真实冒烟：`/tmp/opencode/qa/fullsite/20261101-212143`（v1.0，3条目）、`20261101-214034`（v1.1，4条目×2样本，warm）：FS-V1-71 五条 307 断言全✅、FS-V1-72 logic-demo 实渲截图已目检、FS-V1-25 登录墙 ⛔+P-READY ❌ 正确标定、coverage_ok=true |
| 纪律① | 只在自己工作树施工，主线树禁写 | ✅ | 工作树 `/home/opencode/.local/share/opencode/worktree/29a9a9/qa-fullsite-qa`；`cd /tmp/opencode/qa-base && git status --short` 输出为空（本线零写入） |
| 纪律② | 增量 commit | ✅ | 93c0dc2 → ac1811d；状态文件断点更新 `/tmp/opencode/qa/status/qa-fullsite-qa.md` |
| 纪律③ | 新发现问题先申请 FL 号段再登记 | ✅ | 阶段一零问题登记（质检发现的均为本线自身交付物缺陷，直接修复不占用 FL） |
| 纪律④ | 凭据不落盘 | ✅ | shots.py 只读 env（FUNDLEX_QA_TOKEN/USER/PASSWORD/SEED_*）；v1.1 起 token 仅同源 localStorage 注入、不发请求头（断第三方泄露路径）；交付物 grep 无凭据值 |
| 纪律⑤ | 前端/后端测试 | ✅ N/A | 本批改动 0 行业务代码（docs+tools 纯新增）；shots.py 自身三轮真实执行=功能测试 |
| 预算 | 真实模型调用账本 | 0 次 | 阶段一为静态枚举+基建，无真实模型调用（质检子agent 走完查平台推理，非项目模型 API） |

## B. 双盲质检记录（强制，缺则驳回）

- 质检子agent：`ses_e68b7d0b8ffeTWMobx3Xi16BQ1`（general，未接触实现意图；获 diff+四文件+独立代码实证授权）。
- 结论摘录：「V1 域相当扎实…**V2 域两处实质性功能遗漏直接命中红线**；shots.py 1×P0+6×P1，当前形态不能作为 A1/A3 验收依据」。
- 处置映射（全部认领）：

| 复查发现 | 级别 | 处置（commit ac1811d） |
| --- | --- | --- |
| P0-1 v1_form_login 死代码、未登录静默失真 | P0 | `auth_bootstrap()` 接线：token→注入/user,pw→表单引导；拿不到登录态→exit 3 整 run 中止；每页登录墙探测→`_auth=⛔`；`--no-auth` 仅未登录态条目可用 |
| P1-1 actions goto 相对路径崩+307 无断言 | P1 | urljoin 修复 + page.on("response") 收集 3xx + `expect_redirects` 断言（FS-V1-71 五条实测全✅） |
| P1-2 verdict 取末样本冒充中位数 | P1 | 聚合改按 metrics_median 用 verdict() 重算 |
| P1-3 P-READY 超时静默吞 | P1 | ready_timeout→P-READY=❌ 且聚合保留计数 |
| P1-4 冷缓存与 §2 warm 口径矛盾 | P1 | 默认 warm（同 URL 预载再测第二次），`--cold` 分口径，records 带 cache_mode |
| P1-5 就绪选择器容器偷跑 | P1 | ready_any：行级优先、容器回落，记录命中支（FS-V1-01/04/11/13/61 等已改） |
| P1-6 三数相等定义矛盾 | P1 | 重定义=manifest 条目数==检查单编号数==covered_ids；截图按 id×视口×样本另计；counts.coverage_ok 硬输出（exit 4 非零） |
| P1-7 V2 CompareCard 漏检 | P1 | 新增 FS-V2-21（检查单+manifest） |
| P1-8 V2 补传 `?taskId=` 深链漏检 | P1 | 新增 FS-V2-22（检查单+manifest） |
| P1-9 B 类 P-CLICK-HEAVY 缺格 | P1 | perf_budget.json 补 [800,2000]，程序化核验通过 |
| P2-3 Bearer 头跨域泄露风险 | P2→修 | 去掉 header 注入，仅 localStorage 同源注入 |
| P2（移动取整/截图样本覆盖/url_template/LTASK 窗口/click 超时炸行/15→16 计数/V2-20 粒度/环境口径/LCP,INP/Suspense 时机） | P2 | 均修复或明记：取整百位已实现；截图带 `-s样本` 不覆盖；种子 env 替换已实现（缺失=⛔）；LTASK 改 READY 时刻 5s 窗；click 超时记❌；§4 计数与 V2-20 子态展开已改；环境口径写入 §2+notes；LCP/INP 与 Suspense 捕获列入阶段二待补（README #4/#5、检查单 U6） |

## C. 报主线审定/知会事项

1. **请审定冻结**：检查单 §2 性能阈值表 + perf_budget.json（冻结后二者同步改动守纪律）。
2. **请知会口径**：U4——生产 V2 未上线（fundlex-test-api 显式 pin v1，systemd 实证），V2 走查基线暂取本地构建；阶段二开始前请主线给定 V2 基线（本地 dist 或届时生产 URL）。
3. 观察项两条（不自封 FL 号段，供主线判断）：①生产主实例（:8010）`/api/capabilities` 报 `registration_open:true` 而 test 实例为 false，是否有意；②默认 server 块下 `/v2/` 307 落到 `/test/#overview`（命中 V1 catch-all），生产 fundlex.club/v2/ 亦 307 回 V1——若 V2 未来上生产，该路径需先清障。
4. 阶段二待命：听主线令全量执行（103 行截图+LC 8 链+性能全量，证据落 `/tmp/opencode/qa/fullsite/<run-id>/`）。
