# 多对话并行协调看板（主 agent 维护，2026-10-31）

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
