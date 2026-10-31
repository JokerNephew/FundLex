# 多对话并行协调看板（主 agent 维护，2026-10-31）

## 指挥通道（2026-10-31 建立）

- 主线可对任意线发令：`opencode api post /api/session/<id>/prompt --data '{"text":"…"}'`；读进度 `opencode api get /api/session/<id>/message`（正文取最后 assistant text）；列表 `opencode api get /api/session`。
- 会话映射：`ses_e7055fdb…`=guide-history；`ses_e7072d88…`=feat-recall；`ses_e708617…`=b13；`ses_e7053f1f…`=compare-tracked；`ses_e708687a…`=labels-wave2；`ses_e7071ecc…`=feat-guide；`ses_e7054415…`=recall-tracked；`ses_e70721e0…`=feat-compare。
- 2026-10-31 已对 8 线发出阶段指令（feat-guide 第二阶段：merge+FL-D608+复验 v2；feat-recall v2 四前置；其余线收尾/推进+状态文件）。各线回报落 `/tmp/opencode/qa/status/<线名>.md`，主线轮询收敛。

共 9 个对话：本对话（主线 qa-base）+ 8 条线。各线**只动自己的文件/自己的段位**；完成后将状态写入 `/tmp/opencode/qa/status/<线名>.md`（自由格式，共享目录无 git 冲突），主线每轮收齐合并。

## 一、线的清单与段位

| 线 | 分支 / 工作区 | FL 段位 | 状态（主线最近核实） |
|---|---|---|---|
| 主线（协调+收口） | `qa/full-audit-20261031` @ `/tmp/opencode/qa-base` | 574-579 | 本文件 |
| 第二波 100 份标签 | 直接在 qa-base 作业 | 读尾部顺延 | 在途：selection-second-batch json+2 py 未提交 |
| B13 性能治理 | 直接在 qa-base 作业 | 读尾部顺延（FL-D557 等） | 在途：api.py 投影缓存 F3④、app.js 渲染索引 F8、2 新 pin 测试；疑似同时认领 FL-D574 陈旧测试修复（3 个测试文件中 mode=evaluation 夹具改造） |
| qa-feat-recall | `qa-feat-recall-20261031` | 580-589 | 已提交 wave-compare 工具、FL-D582 闭环；**待 dev20 v2 冻结重跑（门槛见下）** |
| qa-feat-compare | `qa-feat-compare-20261031` | 590-599 | compare 引擎能力恢复在途（selection_writer/store/worker/compare.js 未提交） |
| qa-feat-guide | `qa-feat-guide-20261031` | 600-609 | FL-D601/602 已修（068fe94）；smoke28 复验 FL-D609=NO-GO（B05 false_complete 依旧，因 FL-D608 append not_executed 未归因、且复验时 FL-D572 尚未并入）；**下一步：merge 主线（含 ac697a4 FL-D572）→ 归因修复 FL-D608 → smoke28 复验 v2** |
| qa-f2-recall-tracked | `qa-f2-recall-tracked-20261031` | 610-619 | 带痕迹输入支持在途（docx/delivery/selective/recall_pipeline 未提交） |
| qa-f2-compare-tracked | `qa-f2-compare-tracked-20261031` | 620-629 | 已提交 92c6b93（accept-all 基线元数据+矩阵测试），推进中 |
| qa-f2-guide-history | `qa-f2-guide-history-20261031` | 630-639 | 指引生命周期在途（guide_store/api.py/React Guides 页未提交）；**测试输入可用 references/fee-rule-v2/ 与 references/source/…指引V2.docx（主线已备）** |

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
