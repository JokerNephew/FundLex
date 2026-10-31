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
