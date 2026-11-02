# 多对话并行协调看板（主 agent 维护；【INT 合并台账】小节归 INT 收口线追加，其余区域只读，2026-10-31）

## 指挥通道（2026-10-31 建立）

- 主线可对任意线发令：`opencode api post /api/session/<id>/prompt --data '{"text":"…"}'`；读进度 `opencode api get /api/session/<id>/message`（正文取最后 assistant text）；列表 `opencode api get /api/session`。
- 会话映射：`ses_e7055fdb…`=guide-history；`ses_e7072d88…`=feat-recall；`ses_e708617…`=b13；`ses_e7053f1f…`=compare-tracked；`ses_e708687a…`=labels-wave2；`ses_e7071ecc…`=feat-guide；`ses_e7054415…`=recall-tracked；`ses_e70721e0…`=feat-compare。
- 2026-10-31 已对 8 线发出阶段指令（feat-guide 第二阶段：merge+FL-D608+复验 v2；feat-recall v2 四前置；其余线收尾/推进+状态文件）。各线回报落 `/tmp/opencode/qa/status/<线名>.md`，主线轮询收敛。
- **看门狗**：`/tmp/fundlex-watchdog.sh`（nohup，每 45min 向主线会话投递巡线 prompt）；全链路交付后由主线 `touch /tmp/fundlex-watchdog.stop` 停止。本会话服务为 opencode serve v2.1.4（无 schedule 路由，直连 API 需走 `opencode api` 鉴权）。

共 9 个对话：本对话（主线 qa-base）+ 8 条线。各线**只动自己的文件/自己的段位**；完成后将状态写入 `/tmp/opencode/qa/status/<线名>.md`（自由格式，共享目录无 git 冲突），主线每轮收齐合并。

## 一、线的清单与段位

| 线 | 分支 / 工作区 | FL 段位 | 状态（主线最近核实） |
|---|---|---|---|
| 主线（协调+收口） | `qa/full-audit-20261031` @ `/tmp/opencode/qa-base` | 574-579 | 本文件 |
| 第二波 100 份标签 | qa-base | FL-D670..679 | ✅ 100 份冻结（labels 423c6944/problems=0/1254 目标）+ 运行脚手架 8a10295 就绪，**等 dev20 v2 门槛放行令** |
| B13 性能治理 | qa-base | FL-D640 | ✅ 全线收口（f83462b/977c054；FL-D574 关闭=测试陈旧定责；全量 2375/0 绿） |
| qa-feat-recall | `qa-feat-recall-20261031` | 580-589 | 🔥 dev20 v2 正式轮运行中（冻结 2a416f8；abort 轮已作废标记；评分→对比→FL-D576→留出 8 份 流程） |
| qa-feat-compare | `qa-feat-compare-20261031` | 590-599 | 代码完成（b7ca4c2/ac44e1d，175 绿）；**FL-D590 语料冒烟运行中**（完成后主线先收它再收 compare-tracked） |
| qa-feat-guide | `qa-feat-guide-20261031` | 600-609 + 650-659 | 第一批（D608双层/601/602）已并主线；FL-D644/645/606/607 修复批在途（报验后统一 merge+复核）；smoke28 复验 v2 与 B15 降级归因待办 |
| qa-f2-recall-tracked | `qa-f2-recall-tracked-20261031` | 610-619 | ✅ 已完成并并入主线（38c0727+f7ccbb5 合并进 qa-base） |
| qa-f2-compare-tracked | `qa-f2-compare-tracked-20261031` | 620-629 | ✅ 完成（185d5e6，含 merge 主线），**待 feat-compare 先收后按序并入主线** |
| qa-f2-guide-history | `qa-f2-guide-history-20261031` | 630-639 + 660-669 | ✅ 全范围完成并入主线（94ad5ed）：diff API+认证门槛+生命周期质量通道+引擎对齐冒烟 PASS+浏览器；留 FL-D648 解析粒度开放项 |

## 二、冻结与发布门槛（谁先谁后，铁律）

1. **dev20 v2 冻结重跑（qa-feat-recall 执行）前置**：①merge 主线至 ≥ `0a89e7d`（含 FL-D571/572/573 全部 + fe4803f 测试）；②guide sha 固定为 `30c2625d…`（G13 variant 重认证版，不得回退 20bc6677）；③FL-D608 若影响 dev20 样本则须先修（由 qa-feat-guide 判定并给信号）；④重跑须对比 v1 阻断/交付率并登记 FL-D576。
2. **smoke28 复验 v2（qa-feat-guide 执行）前置**：merge 主线（拿到 FL-D572 G08）+ FL-D608 归因修复。v1 复验（3b6da2a2）已存证：B16 23/23 恢复（FL-D568 真实路径证据）。
3. **留出发货验收**：dev20 v2 达标（门槛同 smoke28 四项）后方可动留出 8 份；禁止把历史运行冒充留出。
4. **merge 回主线顺序（主线执行）**：qa-feat-compare → qa-f2-compare-tracked（后到者复用接受视图公共函数，主线验收）；qa-feat-guide 与 qa-f2-guide-history 都碰 api.py，分别合并、邻近 hunk 主线手工对；qa-f2-recall-tracked 与 qa-feat-recall 在 recall/pipeline 邻近，主线对。功能线全部合入前**不做受控发布**。
5. **qa-f2 新功能不进入 dev20 v2 冻结口径**（冻结时以 commit 清单显式排除）。

## 三、qa-base 在途文件归属表（勿越权 commit）

- B13 线：`fundlex/api.py`（投影缓存）、`frontend/app.js`（渲染索引）、`tests/test_review_render_index.py`、`tests/test_revision_view_cache.py`（新）；`tests/test_v2_evaluation.py`、`tests/test_v2_workbench.py`、`tests/test_v3_delivery_review_gate.py`（FL-D574 夹具改造，定责=测试陈旧方向）。
- 标签线：`docs/evidence/selection-second-batch-20261031.json`、`tools/evaluation/select_second_batch_20261031.py`、`tools/evaluation/verify_second_batch_labels_20261031.py`。

## 四、纪律重申

- 测试纪律：`cd <对应工作区> && .venv/bin/python -m pytest`（.venv 为 symlink，cwd 决定 import）。
- 提交纪律：只 `git add` 自有文件，提交前 `git status` 核对（986c1eb 打包竞态与 ac697a4 卷入 recall.py 在途均为教训）。
- 任何子 agent 汇报引用的规则/FL 编号须回源核实（FL-D575 注记的虚构编号教训）。
- 合同/指引为公开资料可入库可传出；凭据（值）永不落盘。
- 细节问题一律进 docs/DETAIL_ISSUES_AND_RESOLUTIONS.md 自己段位；状态变化在本段位加变更记录行。

## 编号候补池（2026-10-31 起）

- FL-D640+ 为跨线候补池：任何「读尾部顺延」的线（B13、标签线及后续）一律用 640 起的下一空闲号，禁止复用各线段位号。首例：B13 的浏览器 V2 失败条目已由 FL-D610（撞 recall-tracked 段位）改派为 **FL-D640**。

## 2026-11-01 会场二收口进度（主线维护）

- ✅ **qa-recall-miss（原 LzndoPec/feat-guide 线）**：五机制 FL-D652~659 交付，主线复核 PASS → 已并入主线（`6961c77`）
- ✅ **qa-feat-recall（CBU8V6tg）**：FL-D690 B02 根治 + FL-D692 量具归一 → 已并入主线（`9538d6c`，de18ec1 本就曾在主线）
- ⏳ **qa-guide-parse（lnYRv7RA）**：等全套件终绿 → 并入；之后派 frontend（l8yCbACU）接 upload-spec + canary/parse_report 渲染
- ⏳ merge 序：recall-miss ✅ → feat-recall ✅ → guide-parse → feat-compare → compare-tracked（EFtQKeLE 等其前置）
- loop-4 冻结门：合并树新 HEAD 全量回归绿 → 向 CBU8V6tg 发冻结令 + dev20 评分 → false_complete=0 → 留出 8 份首验 → 第二波 100 份放行（kvvQwuiB）

## 2026-11-01 会场三：用户十项新需求下派（档案 docs/USER_REQUIREMENTS_20261101_SESSION2.md）

| 对话 | 新任务 | 编号段 |
| --- | --- | --- |
| l8yCbACU（前端主线） | 项4 列表统一规范+项3 规则可见+项1 设计总负责 | 730-749 |
| ivRkf1jH（V1 worker） | 项1 V1 + 项4 V1 实施（worktree qa-v1-s2） | 750-759 |
| 81FirpsQ（V2 worker） | 项1 V2 ModelSettings + 项4 V2（worktree qa-v2-s2） | 760-769 |
| esIJeEvN（guide-diff） | 项2 指引版本比对（文件diff+规则diff；worktree qa-guide-diff） | 770-779 |
| TGWE0lhi（feishu-onboarding） | 项5 飞书跨企业自建应用一站式向导（worktree qa-feishu-onboarding） | 780-789 |

时序：项1-5 验收上线 → **存档一版（tag+发布）** → 项9 前端整体二次优化 → 项10 用户视角终审。
磁盘治理（附项A）已完成首轮：codex 1.4G 卸载 + 废弃树 1.2G 清除（可用 4.8→7.8G）；发布留存事务保留 mXk9ve/HSmFwd 作诊断，其余已清。

### 会场三收口进度（01-02:4x 更新）

- ✅ guide-parse → 并入主线 `73cb7a6`（定向 220 绿）
- ✅ guide-diff（用户项2）→ 主线复核 PASS（确定性零模型/复用合同比对链/权限不泄露）并入 `fe47f9f`（api 12 绿/vitest 24/tsc 0）
- ⏳ feishu-onboarding：实现完成未提交，全套件回归在跑（已纠错：不等用户确认）
- ⏳ V2 worker：已纠错（不等"用户确认"），commit+验收申请流程纠正
- ⏳ V1 worker：等前端主线规格单（规格冻结 commit 69779d8 已出在 qa-v2-s2 枝上）
- ⏳ loop-4：feat-recall dev20 在跑（~2h，冻结 6339a06）

### 2026-11-01 06:5x 收口进度

- ✅ 项9 批4 → 302280a（项9 施工全量收口；FL-D757 结案=dist 前置环境约定）
- ✅ recall-miss r3 → 9efe827（FL-D695/696 机制修复）；loop-6 冻结令已发 feat-recall
- ✅ compare-tracked → 30cf69e（修订痕迹接受视图；worker/store 双特性共存）——compare 域全部线收口
- 在跑：loop-6 dev20；项9 已完；留 compare 性能复测（低噪窗口）

### 2026-11-01 09:5x 收口进度（巡线29）
- ✅ recall-miss r4 → ada83eb（FL-D697 容器校验/FL-D698 satisfied 消歧/FL-D695 残渣；24 测绿）；loop-7 冻结令已发 feat-recall
- ✅ 前端第三轮规划过目通过 → 批0/批1 动工令（FL-D803~815 入册；验收=并排对照非 token）
- 在跑：loop-7 dev20；前端设计收敛批0/批1

### 2026-11-01 10:4x 会话映射补充
- **A4vO9d5**=guide-generation 专项（ses_e6b1fb214ffe9UIKWT7A4vO9d5，worktree qa-gg-audit）：FL-D820 后续全面检查/守门补强/错误人读化；号段 FL-D820~829
- 第三轮需求追加 5 项已发前端主线合并施工

### 2026-11-01 12:1x 会话映射补充
- **HOKfnt**=compare-ux 线（ses_e6acc8f6effe1JmCR2hnHOKfnt，worktree qa-compare-ux）：比对滚动丝滑+比对链路重设计；号段 FL-D840~859；与前端主线 compare 文件域错峰约定
- gg-audit（A4vO9d5）扩权：审计→补完开发+充分测试（用户第 17 点）

### 2026-11-01 12:4x 收口进度（巡线32）
- ✅ recall-miss r5 → aa30eaf（FL-D699 恒等类替换坍缩；21 测绿）；loop-8 冻结令已发
- ✅ 前端第三轮全量 → 4173dec（设计令牌/输入下拉/动效/三禁令/列表统一/文案人话化/FL-D818 结果页重构；主线复验 vitest24/build/浏览器80 全绿+并排对照亲验）
- 在跑：loop-8 dev20；gg-audit（扩权后观察中）；compare-ux 方案阶段

### 2026-11-01 13:0x 会话映射勘误（FL-D860）
- ~~A4vO9d5 / nHOKfnt~~（僵尸，deepseek-flash 空转）→ 重建：**XMWmAw4**=gg-audit、**OhgIvj8**=compare-ux（均钉 hon-maas/kimi-k3#high，已见产出）
- 调度 SOP：API 建会话必须显式钉模型（Model.Ref 对象）

### 2026-11-01 13:5x 收口进度（巡线34，里程碑）
- 🎯 **loop-8 = 100.0%（390/390）八波首达——dev20 冻结门槛全项达成**；留出 8 份首验令已发 feat-recall；第二波 100 份标签准备激活 kvvQwuiB
- ✅ compare-ux A 阶段 → 滚动丝滑化并入（rAF 同步+splitter 重对齐+双视图；perf 新测绿）
- FL-D861 B01 悬空残句带标交付形态登记（观察项）；recall 新池 FL-D862~869

### 2026-11-01 14:4x 巡线35（评测转折）
- 留出首验 51.4%（57/111，3/8，fc=0守住）：分布外新家族 FL-D862/863/864——**第二波不放行**，修复令发 recall-miss（禁样本特判；留出首轮如实留史，二轮待修复）
- compare-ux B 方案过目通过 → FL-D843~848 动工（P1/P2/P3 两级嵌套去 dialog）
- gg-audit 节奏催收（85min 不可见）

### 2026-11-01 15:xx 既往十项复验令（用户第五轮指令）
- 前端线：FL-D890~893（模型配置页重构/版本比对完整性/规则选择人话化/既往全量自证）与 FL-D880~887 同一交付
- 比对线：COMPARE_SCROLL_REUSE_NOTES.md 复用说明（供 FL-D891）
- 飞书线：项5 盘点+操作成本优化清单+真实验证脚本
- 评测线：项7/8 作证报告（机制面自证+扩样台账）
- gg-audit：盘点追加指引 diff 后端能力问题
- 发布#5 门槛：FL-D880~887 与 FL-D890~893 全部销号 + 主线生产逐页亲验

### 2026-11-01 15:2x 第六轮派工（用户"派给空闲的对话"）
- recall-miss：FL-D897 修订流程大修授权（失效模式总图 REVISION_FAILURE_MODES.md）
- gg-audit：FL-D898 新指引解析质量门（可检验标准+多形态测试矩阵+变量名外泄根治）
- 前端主线：+FL-D894 技术外泄清扫 / FL-D895 小字复查 / FL-D896 合同修改页面群整体设计（方案先过目）
- V2线（81FirpsQ）复出：FL-D899 V2 全站四关普查
- 发布#5 总门槛更新：FL-D880~887 + 890~896 + 899 全销号 + 主线逐页亲验

### 2026-11-01 16:3x 全覆盖矩阵 + 两条新审计线（用户最后通牒后）
- docs/COVERAGE_MATRIX_20261101.md：549 文件+21 页面域逐格成指派，零漏项；销号=逐格签认
- 新线：**Kdvq1x**=EN2 引擎审计2（generation/docx/guide*/delivery 等，FL-D921~939）；**czGpu**=PL2 平台审计（tools 97+tests 全量，FL-D940~959）；总会话 10 条
- 九线总则追加令已发（用户铁律原文逐字置头）
- FL-D920：简化需求=大忌，最后通牒级登记

### 2026-11-01 16:5x 监督线设立 + 两合并完成
- **监督线 qa-overseer（会话 WO4MKd 尾）**：用户亲令设立，独立树 qa-overseer；追溯+产出侧+常驻三审计，驳回权；发现号段 FL-D960~979；工单留档制 /tmp/opencode/qa/dispatch-log/（API 窗口仅找回 6 份历史工单，产出侧审计补足）
- recall 修复回归 2659/0 绿 → **留出第二轮令已发**（新引擎冻结 05c3ef1）
- compare-ux B 阶段（FL-D843~848 链路重设计）并入 7b95c38（vitest24/build/浏览器 12 绿）

### 2026-11-01 17:5x 三并收口（GG/CX/V2）
- GG 并入 7931390（FL-D898 质量门+16测+27文件签认+parse-2/prompt-v2 有意升级，两处测试断言跟进 38997a5/续）
- CX 并入 92aa408（FL-D853~860 签认修复；事故：主线误 reset 后已按 reflog 无损重建历史）
- V2 并入（FL-D899 普查+直修；冲突裁决：app.css 取比对新形态/ComparePage.tsx 尊重 B 重设计删除/DETAIL 并集）→ vitest24/build/浏览器12 全绿
- 工单留档制落地：dispatch-log/MAINLINE-2026-11-01.md（监督线常驻审计料）

### 2026-11-01 19:5x 用户八点指摘改道（巡线42）
- 用户生产巡检八连（FL-D987~995）：FL-D987 比对/修订审查全屏回退（B案方向作废）、988 指引生成风格、989 飞书独立页、990 去红标删「已锁定」、991 下拉框换组件（V2做）、992 三列表统一+状态溢出、993 规则开关子页删除、994 删冗余文案。FE 八点令已发（首发sessionID错误已补发）；FL-D890/896 暂缓并入待返工。
- 验收口径更新：监督线 S1 增「方向确认」硬条款（用户原话方向词逐字转断言）。
- 号段事故：CX 发现二次撞号（先撞 EN1 FL-D981/982、再撞 EVAL FL-D983/984）→ 主线裁决定 FL-D996/997。**新纪律：各线新发现一律先在看板申请号段再引用，禁止自封。**
- GG 实战验证 69min 零产出已排障；W2 三次催办45min最后期限，逾期主线接管。

### 2026-11-01 20:5x 巡线43（r3门票收口）
- **留出 r3=92.8%（103/111）门槛全过**：fc=0/wrong=0、BH01回摆消除（FL-D981实证）、BH07天花板如实交代（G02/G04清零，残G14 MISS_TARGET_RESOLUTION列第二波观测项）、无新回摆/家族。账本段13 $0.2124/168c。**第二波门票到手，唯一缺口=W2标签停滞。**
- EN2分级提案（A直修18/B主线14/C用户1）、PL2分级提案（P0×4/P1×7/P2×9+发布守门地基缺陷节）并入。
- 前端六工单仍冻结待用户批；W2逾期未交（标签接管等用户定）；GG实战验证二次排障；磁盘救回1.6G。

### 2026-11-01 21:1x 总攻开工（用户全清单批准）
- 用户批准全任务清单并定五条铁规：拆细多开会话/工单详细交底（禁一句话）且交底过程须子agent监督/完工后所有链路+所有页面及子页面截图检查/单会话不过载/总指挥仍总负责但须建子agent监督主线+不许让各线久等批复；端到端交付前不擅自停。
- 新线：W3（标签接管，W2 转复核）、QA 全站走查线（两阶段：先全站检查单+性能阈值表，后全量扫荡）。
- 15 工单先发子agent审查：判 9 合格/6 补强（2 硬伤：S3 未定义、PL1 无验收段）——全部修订后发送，审查底稿 dispatch-drafts-20261101-total.md。
- 监督线三责升级：审查主线工单完整性（驳回权）+验收执行+终局全站扫荡牵头。
- 主线 SLA 承诺：完工报告 30 分钟内验收或驳回。

### 2026-11-01 22:0x 第二波放行+三并（巡线45）
- **第二波 100 份 GO**：r3门票+W3标签重验双闭合；冻结=229f030/labels 423c6944/scorer p6-score-4；F-3裁决保留分母+货币市场单列；EVAL 执行中。
- W3 重验=战役最高质量交付（独立重验+1254金标零缺陷+四段提前）；派号 FL-D998~1000；W2 沉冤更正（本体早已冻结，停滞的是交付纪律）→转复核 sample-pack 12 案。
- 并入：EN2 A类18件（裁决备注 claim_replay 属崩溃路径加固；回归抽验 55 绿）、W3 自树件、QA 检查单+阈值表冻结。
- 监督线收验收批1（V2·FE-C·QA阶段一）；V2 SLA 首破（50min）致歉加速。

### 2026-11-01 22:4x INT 整合收口线设立（用户亲定分工建议落地）
- 用户指示：「不一定要你收口，你可以安排别的对话专门负责收口，但他们得充分了解任务要求」→ 设 INT 线（唯一授权写主线树的副官），章程经子agent两轮审查（一审抓3越权通道+1 AGENTS冲突+1撞车+命令错误，全部补丁后V2发送）。
- 分工终版：裁决/派号/GO=总指挥；界面验收=监督线；合并/验证/合并侧台账=INT；监督线对 INT 合并有抽审权。

## 【INT 合并台账】（本小节归 INT 收口线追加维护，其余区域只读）

- 2026-11-01 23:0x 就任首批收口（详情 /tmp/opencode/qa/dispatch-log/INT-LOG.md #1~#3）：
  - ✅ `4672773` EN1(qa-recall-miss) 总攻文档 3 件摘收（纯 docs 通道，FETCH_HEAD bda16b4…）
  - ✅ `2b0cb28` GG(qa-gg-audit) 总攻文档 13 件摘收（纯 docs；DETAIL_APPEND_GG_AUDIT 冲突 1 处按并集先例解决）
  - ✅ `fabff06` EVAL(qa-feat-recall) A2/A3 文档 6 件摘收（纯 docs；剔除碰治理档 3 commit 已上报）
  - ⏳ 阻塞：qa-frontend-v2（D991 已过验收，但增量含 DETAIL_ISSUES/package.json/package-lock.json 治理+lock 三件套，待总指挥逐件明示）；qa-frontend-c（待 ACCEPT-FL-D990/994 + node_modules 软链回潮需该线先清）；qa-audit-platform（PL2 待放行条）
  - ✅ `1ce3014` V2·FL-D991 并入（放行令①；vitest 35/35+build 绿；治理三件套随令知情并入；集中册冲突并集先例×1）
  - ✅ `80c2234` FE-C·FL-D989 并入（放行令②，仅 D989 粒度；990/992/994 排除；node_modules 软链回潮按质检 P1 删除意图剔除）
  - 📒 INT-LOG #5 含一则工作树事故诚实留痕（untracked 依赖目录误删→npm ci 重建复绿；零 git 跟踪内容损失）
  - ⏳ 余阻塞：PL2 放行条仍缺；D990/992/994、D992 比对列表侧（CX）待验收

### 2026-11-02 01:4x 新三轨+全局样本令（用户亲令）
- 用户补三任务（专轨化）：①带修订痕迹合同稳健修改=**EN3 新线**（FL-D924 已修为基线，外推输出写回路径）②模型读所有合同章节找特殊情况喂指引解析=**CA1（四目录重点）+CA2（funds_word 500+ 分层）双线**，现象目录 schema=S-XXX，CA1 唯一 owner ③开发完后所有页面所有逻辑全检查=QA 阶段二加「逻辑完备性」维度+届时再派 2-3 分域线（终局牵头仍监督线）。
- 全局测试重心：/home/opencode/fundlex/references/source/{2026-10-26基金合同修改后(33),产品部修改后(32全带修订,嵌套层),原始文件,基金合同第一批} + 最新指引V2.docx。排序锁：EVAL B3 冷启动先跑冻结→GG A6 方可压测 V2。fee-rule-v2 与四目录关系核实唯一 owner=W3。
- 会话映射新增：EN3=wLZQPE CA1=k6dCXj9k CA2=Rz0GCde7Q。工单经子agent二审（8补丁：阻断2/治理1/验收3/事实2）。
  - ✅ `f676b78` EN2 B类14件（ACK①；合并正式说明=INT-LOG #6：2719/0 全量+2冲突先例+凭据副本；备注=该 commit 由主线会话在 INT 验证期抢跑提交，内容核验无损）
  - ✅ `84e06b4` EN1·FL-D1001 注册回流（ACK②+拆分裁决：guide_store.py 回炉/form_matrix 随 harness 批；全量 2727/0）
  - ⚠ `59721b8` FL-D987 部分落袋（D987b 审查 overlay 已复原；查看器 dialog 回退链+V2 三件因 B 期结构分叉中止，重组装/裁决请求见 INT-LOG #10）
  - ✅ `d734855` EN1·FL-D1002 双族修复链（裁决②；冻结小刀有亲验凭；测试文件并集携带未授权 7a92027 三测已精摘除；全量 2732/0）
  - ⛔ FL-D1001 enable 面回炉件二回中止（同两红；根因切片=finish-canary 先行拒收，嫁接点应挪 finish 评估前，INT-LOG #11）
  - 🔧 PRE 干跑：R5 候选树 /tmp/opencode/release-20261102-r5-pre @ fd019ea，构建✓/发布脚本 dry-run✓/全量 pytest 后台流——产出《R5 预组装验证单》(/tmp/opencode/qa/R5_PREASSEMBLY_VERIFICATION_20261102.md)
  - ✅ `7491177` V2·F2 Guides 三案（D988/992/993，ACCEPT 通过并入；vitest 32/32+build+tsc 0；N1 条件已入册候补派号；验收后追加 refactor 01b551b 未摘已上报）
