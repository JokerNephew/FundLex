# Recall-first 真实修改评测进展（2026-10-25）

当前最新已发布候选为 snapshot-19，build `e2ac0f14429de4fdd71e631d10c18b27f1366c8337e797b4c834b5adf6611229`。FL-D237/FL-D238 的源码修复已实施，最终全量回归为 **1459 passed / 47 skipped / 2 warnings / 291.27s**，178 个 Python 源文件 manifest 一致；snapshot-19 已受控发布到本机部署目录，API/Worker active，关键引擎文件与工作区/snapshot 字节一致。FL-D231–FL-D234 修复前一版本 snapshot-18 的回归为 **1458 passed / 47 skipped / 2 warnings / 288.47s**。D04/D06 零模型真实原件重建 `offline-d231-d234-real-current/result.json` 已验证 D04 G12/G13 原子变换和 D06 G11 protected-literal 边界；postpatch 重建位于 `offline-d231-d234-real-postpatch/`，均不计入真实模型分母。

## 当前对账结论

- target-19 D04 已完成 snapshot-18 的真实普通工作台链路和独立业务复核：19 个实际变化段 19/19 通过，证据为 `/tmp/opencode/operation-validation-20261024/target-19-D04-independent-business-review.json`。target-19 D06 的历史报告和产物保留为 incomplete 证据，不被改写。
- target-20 D06 已完成 snapshot-19 的真实普通工作台链路。机械 artifact verification 为 1/1；final SHA `7503c5e61cf1602240b9c3843d5e7ebd7c9b29029d969b2e04485fcd97a5e7bd`，redline SHA `01de404f1fdc36c1a74e1a8fb0d3eb6b00613ffd4463b178e4f8e70bda2fedeb`。corrected 独立业务复核为 19/19 段、25/25 断言通过，但 G06 单向 Y 类转换语义变体仍使 Claim Replay false、delivery `incomplete`。
- target-20 D06 report 的 operation ledger 已核对：G02/G04 在 p98、p131、p231 均为 `ALREADY_SATISFIED`；G11 p228 为 `ALREADY_SATISFIED`、p229 为 `ARTIFACT_VERIFIED`；G12/G13、G15/G16/G17、G22 和两项 sweep finding 已由实际 DOCX 复核。初始独立复核的三个脚本误报已按 FL-D239 更正，初始 JSON 继续保留。
- 共享评测 ledger `/tmp/opencode/operation-validation-20261024/ledger.sqlite` 当前为 **1701 requests / `$1.64408310` / reserved 0**（completed=1698、failed=2、abandoned=1），剩余 **299 requests / `$0.35591690`**。D04 最近证据属于 snapshot-18，D06 最近证据属于 snapshot-19，其余开发集主要真实产物属于更早快照；因此尚未取得同一冻结版本的 20 份开发集完整业务 gate。
- 当前状态仍为 **开发集 gate 未通过**。holdout、正式引擎发布和最终普通工作台 E2E 继续阻断；不能以 target_counts、任务 completed、机械文件通过或离线重建替代独立 whole-contract business approval。预算不足的状态与下一步已登记 FL-D240。

## 固定分母对账

机器可读与可读版对账分别为 [`docs/evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.json`](evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.json) 和 [`docs/evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md`](evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md)。它固定核对 D01-D20，不改历史 report、labels、gold、scorer 或 DOCX。当前 snapshot-19 gate eligible 为 **0/20**：仅 D06 有当前快照证据且 G06 未决；D04 的独立通过属于 snapshot-18；历史 snapshot-05 复核中 D02、D16、D17 通过，D18 失败，其余 15 份 pending。按 dev-05 实际消耗，保留 D06 并补跑其余 19 份至少约需 602 requests / `$0.60031875`，相对当前余量缺口约 303 requests / `$0.24440185`，不含重试和 G06 修复调用。该对账结果登记为 FL-D241，历史复核分类登记为 FL-D242。

target-19 已按 snapshot-18、独立 data-19 完成 D04/D06 真实普通工作台路径，后台 shell `sh_16ead959c001MZSAUWU9cVPMyW`；target-18 历史失败证据不覆盖、不重写。D04 complete，D06 incomplete；真实下载文件、Claim Replay、audit、逐站点实际差异、Review 接受/拒绝修订和哈希均已核对。holdout、正式引擎发布结论和最终普通工作台 E2E 继续阻断，直到开发集完整业务门禁通过。

target-20 已按 snapshot-19 完成 D06 真实普通工作台路径，独立 `data-20`；target-19 的 D04/D06 报告和产物保持历史证据，不被覆盖。当前账本与 target-20 结果见“当前对账结论”和 FL-D240。

当前状态：**开发集 gate 未通过，尚未满足本轮发布和最终交付验收条件**。本文件记录当前冻结版本及真实复测证据范围；历史成功样本、离线测试或任务 complete 状态均不能替代20份开发集、8份留出及发布后的真实工作台验收。

最新target-17（snapshot-16）：D04/D06真实任务与授权下载均结束，incomplete，48/15、92/29 targets/unresolved。机械2/2；G17源2/4处全部删除、独立余文逐字保留，局部通过。完整Claim false/5和false/8，D04 G12/G16/G03及旧target身份、D06 G11/G15等未完成，不能视作整合同通过。新增62 HTTP/$0.06612960，逐请求与最终报告对账一致；累计1552/$1.47498705/reserved0、余448/$0.52501295。FL-D226合法多类别G15过拒修复已1443 passed/46 skipped，真实D06原件零模型2处完整删除及修订等价通过；FL-D222复发/G03跨段修复继续验证，新版尚未冻结或运行真实任务。无holdout/引擎发布。

FL-D227/228当前增量：真实D04原件零模型验证确认G16两处各追加一次且保留独立费用余文，G03追加至完整p83定义末端；G12显式25%比例变体可在自身旧分配句范围内确定性替换，G13短期收费句边界保留。相关定向回归通过；D227全量曾1 failed/1451 passed/46 skipped，唯一失败是测试替身缺少真实段落结构字段，已修正。D228全量启动后又追加G12回归测试，因此即使其结果通过仍需按最终manifest重跑，尚未冻结或真实复测。

最终manifest已重跑通过：**1453 passed/46 skipped/2 warnings/280.23s**，177个Python源文件manifest一致，build `e4ae767880625a3cf090fd500283facd28caab2f696e96c35551ab74b65dc172`；证据`/tmp/opencode/operation-validation-20261024/final-full-test-start.json`、`final-full-pytest.log`、`final-full-test-result.json`。snapshot-17已冻结，仍未取得任何新的真实合同交付结果。下一批target-18预登记D04/D06，预计80 HTTP/$0.08、最坏200/$0.24，账本起点1552/$1.47498705/reserved0；holdout、引擎正式发布和最终普通工作台E2E继续阻断，直至开发集门槛完成。

生产账本只读核对为26919 requests/`$21.81123075`（completed26874、failed32、abandoned13），为历史生产流量；target-18沿隔离评测ledger运行，生产与评测账本不混算。

target-18首次启动因评测包装器参数顺序错误在解析阶段退出（FL-D229），未产生真实任务或模型调用，账本仍1552/$1.47498705/reserved0；该次不计入开发集结果，待按正确参数重新执行。

target-16 D04/D06已完成真实任务及授权下载，均incomplete（58 targets/33 unresolved、91/37）。下载机械2/2、完整Claim false/8和false/9；D04首G17用途副本窄删且费用余文保留，第二副本残留，D06两用途句残留而排除句已删。宽survey/composite带入独立余文，被范围门禁正确拒绝，召回恢复仍未完成（FL-D225）。D06属可改ETF联接，首次临时业务脚本沿用旧排除标签和单段HEAD查找的结论作废，旧labels/scorer不改（FL-D188）。报告50 HTTP/$0.05309895，账本实际67 requests/$0.07048830，累计1490/$1.40885745/reserved0；差额全部计费、归因待核。实际产物为工作文件，不能宣称业务通过；无holdout/引擎发布。

target-16费用已完成对账：17条账本请求/$0.01738935未出现在两份最终报告事件中，属于报告仅保留最终attempt造成的统计差异；最终报告的50条非checkpoint重用HTTP事件全部与账本metadata匹配，另124条是checkpoint复用（更正早期将124误记成HTTP的表述）。D04数据库attempt1、D06 attempt3与schema失败重试相符。对账证据`target-16-metering-reconciliation.json`，实际总消耗仍1490/$1.40885745/reserved0。

FL-D225源operation窄parts修复已完成定向验证：`_reference_continuation()`不再把跨段follower整段纳入删除，`ensure_delete_targets()`从G17自身完整句为全部副本恢复窄目标。D04/D06真实原件零模型规划共4/6 edits，Claim、余文保留及接受/拒绝修订等价均通过，证据`offline-d225-planning-real/result.json`；这是离线规划证据，不是新的真实模型任务。完整回归通过并重新冻结前，仍不得运行真实复测、holdout或发布。

该增量完整回归已1436 passed/46 skipped/2 warnings/278.05s，源码manifest匹配；snapshot-16已冻结build `2858706c841ff88b1a75e394e1d4f225d0d6c8bcfa2ebfcb0b68252af7922889`、API/tasks与生产相同。预登记target-17 D04/D06真实复测预计80 HTTP/$0.08、最坏200/$0.24，账本起点1490/$1.40885745/reserved0，预算上限不变；本轮开发集仍未达holdout或发布条件。

最新target-14（snapshot-14，build `0f4fd6e2f3f701d1209900b4cc712470a108650f4694b6e0e2db37eb36d61117`）真实登录/上传/持久Worker/模型/授权下载已结束：complete/34 targets/0 unresolved、33 HTTP/$0.02573610；机械1/1，final SHA `3e73446d8ee1f8dc235bd22895b69e9e18b045cec5f059f0cfbe137b277529cb`、redline SHA `4962c8d2f6942eb82c660fa3f8693a5fc8134f079d7751ef2a7e0a231dce1e3c`。收费引文恢复后两收费组VERIFIED。模型G15/G16审计仍wrong；先前人工据此判p753/p1221应保留原句，经指引原件85–89段复核已更正：G17本身要求删除该使用范围句，G16独立新增与其合并不能直接视为越界。FL-D282保留该审核失误及effect重建绕过失败unit的实际代码缺口；当前不宣称D03或开发集最终业务通过，先收紧证明并重放完整产物。累计1389 HTTP/$1.30929540，无reserved；保留target-12/13/14全部原始证据，无holdout、未发布引擎。

FL-D282后续：target-14完整实际DOCX与plan重放verified=true/0 failures、既有audit重放29 results/0 issues/0 artifact failures，全部20个实际变化段按指引原件复核通过（`target-14-d224-{source-scope-replay,audit-replay,business-diff-review}.json`）；这些均0 HTTP、属于旧产物的开发验证，不补作独立冻结标签或新真实批次。G15范围、effect失败unit及BEFORE丢失引文修复已实施；第一轮全量1 failed/1417 passed/46 skipped，随后修复单句支付变体过拒、233项相关通过，最终全量仍运行中。真实新版本验证尚待冻结snapshot-15后另建target-15，不覆盖旧证据。

2026-10-24后续结果：FL-D282最终全量1420 passed/46 skipped/2 warnings/271.52s，源码manifest匹配；FL-D225发现并修复G17 provenance扩大删除权限，首轮全量1428 passed/46 skipped/2 warnings/271.62s。target-14在新证明下仍完整Replay true/0 failures、旧审核重放29 results/0 issues/0 artifact failures（`target-14-d225-{source-scope-replay,audit-replay}.json`）。历史20dev只读Replay识别D04独立费用支出句、D06独立降费权限句的越界删除，不能沿用旧complete；同时有限措辞差异过拒已修、226项相关通过，最终全量和最终20dev只读重放运行中。本轮全部0 HTTP，真实target-15待最终全量/冻结；不是全开发集业务通过。

target-15 D03在snapshot-15上完成真实端到端：`complete`/35 targets/0 unresolved，34 HTTP/$0.02907375；机械核验1/1，final SHA `66efdc0c6ceab948cd51a8745fc4236e275b7c7cb7a589cdadcd7afc401c8d2b`、redline SHA `302c9805930dbc3460e51a0c2670ad989899fad85db516879ae09559e5a1dc91`，20 ins/20 del，接受/拒绝修订与哈希一致。新引擎Claim Replay true/0 failures，旧审计重放29/0/0，20个实际变化段与target-14已审核结果逐段一致并20/20 PASS。共享账本1423 HTTP/$1.33836915，无reserved；D03这一个真实合同完成，仍未完成20dev独立目标分母或发布/holdout门槛。

最新snapshot-12：最终 **1404 passed /44 skipped /2 warnings /286.21s**，引擎build `d441ec1706668bcdcafb0fcf7cfef9798d5879bb3a22871c1f9e84963c1fb16b`。全量启动后唯一变化的前端浏览器模块另以显式Chromium补验 **5 passed /10.90s**（FL-D219，精确补验哈希独立保存）；其余源码一致。已冻结并重验2418文件manifest，API/tasks与生产一致；`target-12`仅D03，隔离data-12真实登录/上传/持久Worker/模型/授权下载正在运行，预算起点1267 HTTP/$1.19796015、无reserved、总cap2000/$2。完成后复核G01原件raw130位置、下一定义原文、G08一次、编号、全部实际变化与修订/report/hash；当前尚不能关闭FL-D218或判D03整合同完成。D07/D10/D14/D16旧事实回答曾过度认证收费组，现有证据认证入口已拦截；独立收费引文接口已支持D10/D14与D16原件零模型正面补证，仍非真实重提取结果。

target-12 D03已完成真实Worker/模型和授权下载：`incomplete`，42 targets、39 unresolved，52 HTTP、$0.05397930；共享账本1319 HTTP/$1.25193945，无reserved。机械下载核验1/1通过，final SHA `c593ea2a3b6cdefabed2ec8a031743abba0475ee61380c324286cb7fb592e7b3`，redline SHA `496b8ad8af0c75bde59d9c15b27dd3e8d2a744d683cf066bdd07287cca4e136b`。target-12相对target-11发生9处段落变化；p92 G01 raw130插入、55号定义原文保留通过，但新结果的p121 G05回退、p752/p753及p1221删除G16应追加内容、p925/p1318未完成G22，故不能沿用target-11的20处审核结论。G16补充核验14/16；全开发集独立目标分母仍未完成。源码在target-12之后已修复G09完整effect和收费费率解析，新增100项局部回归通过，必须重新全量、冻结并真实复测。

target-13 D03已完成修复后真实Worker/模型与授权下载：`incomplete`，40 targets、52 unresolved，37 HTTP、$0.03161985；共享账本1356 HTTP/$1.28355930，无reserved。机械下载核验1/1通过，final SHA `5810c37e6d3922ad0779682938782653637b068a0ed06dd4a324d28d49b1a06c`，redline SHA `214ea725352452d9df99b393e3d841066229f62f9970c32d735ed2d33083b3ea`。实际DOCX改变12段：G09 p210同时含“当日该类基金份额的基金份额净值”和“扣除或加上相应的费用”，Replay PASS；G01/G03、G05/G06、G12/G13、G14、G15、G18与plan一致。收费事实仍因模型省略p211原文编号“4、”而UNKNOWN，G08/G11/G16/G22未交付。FL-D222阻断已在真实文件中生效：p752/p753、p1220/p1221原用途条款未被G17单独删除，并以`G17_BLOCKED_G16_UNPLANNED`/`CLAIM_OPERATION_NOT_PLANNED`保持失败闭环。该批次不能判D03或开发集通过；target-12失败证据继续保留。target-13之后新增source-bound编号引文修复，不能复用target-13作为修复后版本。

2026-10-24最新终态（优先于下文历史）：target-08四份已全部结束，140 HTTP/$0.12862980，下载机械4/4；D03业务15/16（FL-D215编号）、D05 18/18、D07修正辅助检查器的合法追加断言后33/33但仍incomplete/18 unresolved、D18 12/14且错误complete（FL-D216跨段顺延两处残留）。snapshot-09 target-09 D03已真实完成complete/0，33 HTTP/$0.02420940，机械1/1、定向16/16，原“4、”保留，FL-D215在该真实样本解决；最新完整离线为1351 passed/44 skipped/2 warnings/256.56s。共享账本1201 HTTP/$1.14961950，无reserved，余799 HTTP/$0.85038050，原2000/$2上限不变。

FL-D216已实施原件授权的紧邻跨段站点闭环，相关82项回归及D18真实旧文件Replay反例/局部重建/修订等价通过；完整回归运行中，之后需snapshot-10/target-10 D18真实任务复测，当前不能宣称修复真实验证完成。所有旧失败与费用保留；无holdout、未发布引擎。

`target-10`已完成真实D18复测：complete/0 unresolved，33 HTTP/$0.02434395；下载机械1/1、定向14/14、修订接受/拒绝及哈希一致。相对target-08 D18仅p776/p1227删除两处旧顺延句，其他差异未新增。FL-D216从“已实施、待真实验证”更新为**真实样本已验证解决**；D18历史target-08错误complete文件仍保留为失败证据。

target-09全部文件差异复核新增FL-D217：D03 p209在完整G08新政策之前保留旧C类免申购费短句，造成同义重复。该项不在原16项补充断言中，不能用16/16代替全差异审核；编号FL-D215局部验证通过仍成立，D03整合同完整业务通过尚不成立。证据`target-09/D03/compared-to-target08.json`，待修复并再真实复测。

FL-D217修复后的完整回归为 **1370 passed /44 skipped /2 warnings /258.22s**。已冻结`snapshot-11`（build `92880a778ab4607b713cd26da56e8e061c9283e0d26021dfd121ad81298bdd5a`），账本起点1234 HTTP/$1.17396345、无reserved；`target-11` D03真实登录、上传、持久任务、Worker/模型和授权下载链路正在运行，结果未出前不关闭本问题或扩展为开发集通过。

`target-11`终态：D03 complete/0，33 HTTP/$0.02399670，机械1/1、定向15/16；p209 G08重复已解决、编号保留。全差异发现新FL-D218：G01追加点落在同段下一编号定义之后；因此D03仍未业务完整通过。账本累计1267 HTTP/$1.19796015、无reserved，余733/$0.80203985。FL-D218已补源边界和Replay阻断，相关162项离线回归及真实原件零模型重建/修订等价通过；完整回归与下一真实D03复测尚待完成。旧target-11错误complete文件保留，不重写历史失败。

2026-10-24用户再次明确要求真实测试→按结果优化→优化后继续真实测试。本轮预登记`target-08`：dev D03/D05/D07/D18，真实身份入口→默认配置→上传/持久任务→实际Worker/模型→授权下载；逐份复核实际DOCX、修订等价、报告/哈希和全部未完成项。冻结`snapshot-08` build `a829181de8e965b8c6f64f7d37dcd2e1e7ff5134230a258a584ea2ee59c8652b`，完整fundlex源码与1343项测试工作区一致，API/tasks与生产一致；manifest `run_context-08.json`。隔离`data-08`、API8013，不修改生产。共享ledger起点1028 HTTP/$0.99678030，总cap2000/$2/并发1不变；预计约120 HTTP/$0.12，四份最坏各192次且受共享总预算阻断。修复后必须另建新run真实复测，不能以离线重放代替；本轮不运行holdout。

`target-08`当前进度：D03、D05已真实完成complete，D03实际模型33 HTTP/$0.02439705，D05报告估计$0.03210180；D07、D18仍运行。D03下载文件机械核验已通过，实际业务复核发现G11 p211原有“4、”编号被clean template吞掉，登记FL-D215；编号保留修复已通过55项定向回归，尚未进入真实复测快照。D05报告与实际DOCX待批次完成后统一核验，不能根据complete状态直接判业务通过。

为验证FL-D215，已冻结新`snapshot-09` build `997329195f5699afd246bdb6ff5cca4fa28f5beaee440433e864e77c4f03d861`，父版本`snapshot-08`，manifest `run_context-09.json`；与当前工作区引擎字节一致，API/tasks仍与生产一致，生产未修改。共享账本冻结时为1137 HTTP/$1.108932，剩余863 HTTP/$0.891068；新真实`target-09`仅复测D03，使用隔离`data-09`，不覆盖`target-08`失败证据，不运行holdout。

最新增量：D03 G15/FL-D213旧全量为 **1325 passed /44 skipped /2 warnings /240.20s**，早于后续D05修改。FL-D214已实施G17完整续段站点闭环，相关G15/G17定向**68 passed**；D05实际重建四个G17 sites全部通过，p868/p1332核对句保留，修订等价通过，旧错误PASS的p869/p1333残留证据仍保留。当前工作区最新完整回归为 **1343 passed /44 skipped /2 warnings /245.29s**（`g17-closure-full-pytest.log`）。无新增模型费用、无后台真实批次，开发集/留出/发布条件仍未通过。

2026-10-24最新工作区增量验证：G09旧报告重放证明收紧后完整回归 **1317 passed /44 skipped /2 warnings /238.34s**（`g09-proof-full-pytest.log`），真实D07旧产物G09 PASS且整合同仍false。早先G15 survey/parts试改撤回；新raw地址紧邻顺延句窄修复已在D03原件局部DOCX验证：p751/p1219均0–133删除，其他段落原样，Claim通过，接受/拒绝redline与final/原件一致（`offline-d03-g15-raw-current/`）。确定性删除的compose预算误扣修复登记FL-D213；相关 **170 passed**，包含新修复的全量运行中。D05核对句授权仍OPEN，以上均为离线验证，新增HTTP为0，不能代替正式整合同真实模型复测。

最新候选为`snapshot-07`，build `ac51034291840615ab22ee62c2453e2bc26cd456d51e0e9f550af4e3b2d001ad`：从snapshot-03继承并显式overlay19个引擎文件，API/tasks与生产一致，manifest `run_context-07.json`；不覆盖下文snapshot-05/dev-05历史证据。当前工作区FL-D205/207/210/211后的全量为 **1289 passed /44 skipped /2 warnings /242.46s**，FL-D200安全失败计量的后续组合为 **82 passed /1 warning**。快照不含新增测试，须另用当前测试验证冻结源码。

`target-07`四份真实定向复测已结束：D07 `incomplete/40 unresolved`，D11/D17/D18报告`complete/0 unresolved`；112 HTTP / $0.10168590，各份费用依次为$0.02498685/$0.02931180/$0.02309205/$0.02429520。机械检查4/4通过（`target-07/artifact-reviews.json`），D17 p207旧比例句清除、D11追加在净值公式之后、D18 p776/p1227支付顺延句各保留一次。但D18实际p775/p777及p1226/p1228各含完整G16政策，**同一条款重复且错误complete，FL-D192重新打开**；局部修复不能代表整合同业务通过。实际差异证据在`target-07-review-packets/`。D07收费事实正面认证、缺失服务费组的期望统一及多个漏改仍待处理，不能仅因模板写A而断言Y越权。

## 冻结范围

- 当前候选：`/tmp/opencode/operation-validation-20261024/snapshot-05`。
- Engine build：`5b04e5ea2ed2aadddca51ddca4ed66c1d65f33461f435445f394b5e34cd953c2`。
- 从已审查的 snapshot-03 继承，仅覆盖 `fundlex/recall_pipeline.py` 的 FL-D199 修复；测试文件同时保留。`run_context-05.json` 保存完整文件哈希，运行期间复核无不一致。
- 样本：`var/recall-first-evaluation/p6-current/selection.json`，20 dev + 8 holdout；SHA-256 `95fe8121d5f0aceb4febf9cc76a79fde78cf44f711e9a6f029b08eb6ee5643f3`。
- 冻结 labels SHA-256：`f120d38175c83cd1c973045d0414a69bacb9d837fc4bf24d40a8a762fe588841`，未修改 gold/labels/scorer。
- 当前版本留出新预测未读取、未运行；仍须开发集达到门槛后执行。

## 已取得证据及边界

| 证据 | 结果 | 适用范围 |
| --- | --- | --- |
| 工作区完整离线测试 | 1266 passed / 44 skipped / 2 warnings | 工作区含并行外围测试，不等于冻结快照结果 |
| snapshot-05 完整离线测试 | 1234 passed / 65 skipped / 2 warnings，157.09秒 | 日志 `snapshot-05-pytest.log`；不调用真实模型 |
| snapshot-06 修复后完整离线测试 | 1236 passed / 65 skipped / 2 warnings，148.62秒 | 日志 `snapshot-06-pytest.log`；包含 FL-D204 修复及 2 个变体/fail-closed 回归，不调用真实模型 |
| FL-D199 原版本精确响应回放 | 70次保存响应，0 HTTP，同一处 NameError | snapshot-03 D03 运行时缺陷重现 |
| FL-D199 修复版本精确响应回放 | 越过原异常；后续 sweep 无历史响应而停止 | 局部修复证据，不能记为完整 D03 交付 |
| snapshot-03 pilot-03 D01/D02 | 两份 complete、unresolved=0；机械检查2/2、开发补充站点检查各40/40 | 历史版本两份开发样本；不能并入 dev-05 分母 |
| snapshot-05 dev-05 | 20/20任务结束；D02/D16/D17报告complete，其余17份incomplete；实际D17存在错误complete（FL-D205） | 下载机械20/20通过；业务全站点复核未完成，未达发布门槛 |
| snapshot-06 修复后候选 | build `e53c8585514470019ff2b7890aed1f407573f9574d00abe8b23a72d8a1b0a568`，从 snapshot-05 继承，仅覆盖 `fundlex/recall_pipeline.py` 及 Sweep 回归测试；离线1236 passed /65 skipped | 尚未运行真实合同，不能替代 dev-05 或取得发布资格 |
| 新版本生产发布与公网端到端 | 尚未完成 | 不使用旧生产引擎结果替代 |

旧 P6 标签存在 ETF 联接资格错误及单规则单站点限制（FL-D188），多类别 G18 固定文本限制见 FL-D197。保留其原始分数，不能把该分数当成全部业务目标分母或发布依据。新一轮发现召回、正确完成、整合同完成、误改/漏改和错误 complete 的业务指标均待实际文件及独立站点复核，当前不填通过率。

dev-05旧P6原始评分214/236（90.68%），completed214、kept14、not_executed8；score SHA `5de8689c9d751c4b74e38f97ec2eeb1e7226599ee0128f052b2d9673d3f87afd`。其false_complete=0漏掉了实际D17的旧比例残留，因此该项不能作为真实错误complete结论。补充站点D01 38/40（G15两处漏删），D02 40/40。完整20份实际差异在`dev-05-review-packets/`，待逐项复核。已确认D17 G12错误complete、D03 G15尾句残留、D05相同支付条款删除不同、D07跨段定义插断；D09/D13单类别事实无法认证，详见FL-D204～208。

## 实际文件复核材料

1. `tools/evaluation/verify_downloaded_artifacts.py`：读取下载 final/redline 或明确的工作文件，对账源 SHA、报告 SHA、接受/拒绝修订、实际段落与计划，机械通过不等于政策业务通过。
2. `tools/evaluation/p6_score.py`：保持原冻结旧口径，输出原始分数并披露 FL-D188/FL-D197 限制。
3. `tools/evaluation/build_revision_review_packet.py`：仅从原件和实际 DOCX 生成复核材料，完整保留所有实际段落差异；词法候选只是阅读线索，不自动成为 gold 或业务分母，不输出业务通过分数。
4. `review_pilot_sites.py`：仅覆盖 D01/D02 的开发补充逐站点检查；其余合同不能沿用该脚本宣称已复核。

源文材料已保存于 `/tmp/opencode/operation-validation-20261024/dev-source-review-05/`（20份，仅 dev），补充工具在 `pilot-03-review-packets/` 与既有机械复核对账。dev-05 历史产物的独立复核已补充：D02、D16、D17 通过，D18 因 G17 重复/残留文本失败，其他 15 份仍 pending；这些结果均属于 snapshot-05，不能替代 snapshot-19 当前 gate。

## 失败批次与预算

- snapshot-03/dev-03 在 D03 因 FL-D199 中止，失败、debug及无网络回放证据均保留。
- snapshot-04/dev-04 因构建脚本带回 HEAD 中旧 API/tasks 判废，运行到 D01、D02未完成即停止；不并入 dev-05，但真实请求/费用仍记总账。构建问题见 FL-D203。
- 唯一共享账本：`/tmp/opencode/operation-validation-20261024/ledger.sqlite`；上限2000次HTTP、估计费用$2、模型并发1、单合同调用上限192。不得重置。
- dev-05 启动前总账282次 / $0.26175915；本批634 HTTP / $0.63333525，终态累计916 HTTP / $0.89509440，含所有失败/调试尝试。不可重置；后续预登记须从此累计继续。
- target-07在以上累计基础上新增112 HTTP / $0.10168590；共享账本累计**1028 HTTP / $0.99678030**，剩余972 HTTP / $1.00321970；首次误传`run`在argparse退出，零HTTP，不能重复运行已结束批次。
- FL-D200未分类异常失败报告丢失模型计量已实施修复并通过离线Worker/管线组合验证；旧失败报告中的null不表示零成本，真实请求与费用仍以共享账本核算。

## 发布候选与下一步

只读差异清单 `release-candidate-05.json` 显示相对当前生产仅以下5个引擎文件不同：`fundlex/generation/effects.py`、`fundlex/generation/registry.py`、`fundlex/recall.py`、`fundlex/recall_pipeline.py`、`fundlex/recall_prompts.py`。API/tasks与生产一致；本轮未修改生产。发布前须再次核对并行生产变化及完整 build，保留 React V2、Compare、evidence 和运维工作。

下一步：接收 dev-05 完成结果 → 全批下载机械核验和冻结旧评分 → 对全部原件站点与实际差异做业务复核并保留失败分母 → 按结果修复/局部复测及冻结完整dev回归 → 达标后8份独立留出 → 受控发布 → 生产公网真实登录、当前指引、上传、seal、Worker/模型、Review、结果页和授权下载，核对最终版/修订版/报告与哈希。未完成部分持续记录于 [当前断点](ACTIVE_HANDOFF.md) 与 [集中问题记录](DETAIL_ISSUES_AND_RESOLUTIONS.md)。
