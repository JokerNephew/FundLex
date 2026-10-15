# FundLex 当前断点（ACTIVE_HANDOFF）

> ## ⚠️ 机器身份（先读这一段，禁止凭内网地址判断机器）
>
> **当前工作机 = 云服务器**，即本仓库所在处：
>
> | 项 | 值 |
> | --- | --- |
> | 主机名 | `iZf8zemhifedxdow1zefr0Z` |
> | 公网出口 IP | `8.155.130.168` |
> | 内网网卡 IP | `172.28.217.241`（**同一台机器**，不是另一台开发机） |
> | 区域 / 实例 | `cn-heyuan` / `i-f8zemhifedxdow1zefr0` |
> | 工作区 | `/home/opencode/fundlex`（专用用户 `opencode`） |
> | 应用部署 | `/opt/fundlex-recall-first`（systemd `fundlex-recall-api`/`fundlex-recall-worker`，API `127.0.0.1:8010`） |
> | 公网 HTTPS 入口 | **`https://fundlex.club`**（`www.fundlex.club` 同；Let's Encrypt 证书，nginx/宝塔反代 `127.0.0.1:8010`，80→443 跳转） |
>
> **本文其余部分的“本机 / 笔记本”一律指已停用的 Windows 开发机，绝不是当前工作机。**
> 接续 agent 开工前先跑一次身份采集：`hostname`、`ip -4 addr`、`curl ifconfig.me`、
> `curl http://100.100.100.200/latest/meta-data/instance-id`，用事实确认自己所在的机器。
> （本机器块为 FL-D061 的处置结果，见集中问题记录。）

更新：2026-10-15（服务器开发主副本 `/home/opencode/fundlex`，接续 agent **第 5 轮**：修 qr-local-12 的 12 项未解决，FL-D052；三轮真实链路复验后 FL-D052 全部收敛，quality-return-12 单份合同完整交付）。规则：50% 整理、60% 前完成压缩/交接；本文只记状态与下一动作，不写密码。

> **编号更正（FL-D077，2026-10-15）**：集中问题记录曾有 5 组编号重号，已把后出现者改为新编号（保留首次出现的原编号）：
> `FL-D057→FL-D072`（sweep 误报 G02/G04）、`FL-D058→FL-D073`（无服务费结论）、`FL-D068→FL-D074`（评分器短锚误判）、
> `FL-D069→FL-D075`（G17 跨段删除）、`FL-D066→FL-D076`（Codex bwrap）。
> **注意**：本文下文第 5/6 轮的历史叙述写于更正之前，个别处仍写旧编号，含义以更正后为准；新增条目一律先查重再编号。

## 当前断点（第 8 轮，2026-10-15，接续请从此处读）

- **本轮已完成的非批次工作（第 8 轮）**：① 修正集中问题记录的 5 组**编号冲突**（FL-D077），并同步修正 `tools/evaluation/p6_score.py` 与断点/计划文档的引用（后出现的重复项改为 FL-D072/073/074/075/076，保留首次出现编号之一义）；② 全量测试 **562 passed / 1 expected / 6 skipped**（与更正前一致，说明只动注释与文档）。**未 commit、未 push、未发布。**
- **正在运行**：P6 开发集优化第 1 轮的**第 3 次重跑** `p6-dev-round1-01`（后台，日志 `/tmp/opencode/p6-dev-round1-01.log`，`var/recall-first-evaluation/p6-dev-round1-01/`，`--timeout 1800`，构建 `fundlex/recall.py` `07b39288b87dfa14…`）。已完成 D01 `incomplete`（4 未解决）、D02 `incomplete`（10 未解决，ETF 排除集）、D03 `incomplete`（4 未解决）。**一次跑 20 例约 2 小时**；**不要 kill 在途任务**（见 FL-D066）。
- **跑完后**：`bash -lc '.venv/bin/python -X utf8 -m tools.evaluation.p6_score --run-id p6-dev-round1-01'`（产物默认写 `/tmp/opencode/`，与基线/第 2 次对比：基线 0.754、第 2 次 0.792）。
- **P6 关键文件（仓库外）**：`/home/opencode/data/funds_word/`、`/home/opencode/data/MANIFEST.sha256`；仓库内 `var/recall-first-evaluation/p6/`（selection/labels/protocol/freeze）。
- **账本（仓库外，勿入库）**：应用调用记 `/var/lib/fundlex/model_budget.sqlite`（root 只读，opencode 读不到；数字取自各 `report.json` 的 `model` 段）。基线 581 调用/$0.5624；第 2 次 677/$0.5738。**agent 自用 0 次**。
- **禁止**：commit、push、把资料/样本/密钥入库。发布只能用 `bash tools/deploy/publish_workspace.sh`。
- **下一步（按序）**：① 等批次结束并评分，对比基线/第 1 轮，统计 G01/G03/G16（FL-D060 无条件 append 漏加）、G17（FL-D075）等残留；② 修 FL-D060 后只在**开发集**再跑 1—2 轮（≤3 轮），直到 dev 达标（0.95 / 整合 0.9）并冻结；③ 冻结版跑 8 留出例（`--group holdout`）；④ 写 `docs/REAL_REVISION_EVALUATION_RESULTS.md`；⑤ P7 浏览器端到端、断点续跑、双身份隔离、指引切换、MySQL 备份/恢复。

## 第 7 轮进度（服务器，2026-10-15）：用户 8 项 UX/修改问题 + P6 第 1 轮评分

任务计划文档：`docs/TASK_PLAN_UX_AND_APPEND_20261015.md`（该文档写于编号更正 FL-D077 之前，文中 FL-D068/069 指现在的前端互斥与 fragment 拼接两义，见本文顶部更正块）。

- **T2 引擎（问题 5，无标点拼接）已修复**：`_splice_fragment`（`fundlex/recall.py`，`fragment_replace` 路径）遗漏分隔符 → 已加 `append_separator`；`plan_composite_target` 同步加固。新增 2 回归测试。→ **FL-D068**
- **T1 后端并发核实（问题 1）**：后端本就支持多任务并行（`tasks.create` 无限制、`POST /api/tasks` 无守卫、worker 公平 claim）；互斥纯在**前端**。→ **FL-D069**
- **T3 前端 8 项 UX（问题 1–8）已实施**（`frontend/index.html|app.js|app.css`）：多任务并行、证据侧栏改「章节+改之前/改成了什么」、精简小字、结果页 ZIP 按钮置首、删顶部横幅+铃铛只收重要消息、总进度指标单行、导入 KPI 并入筛选栏。→ **FL-D071**。验证：`node --check` 通过、120 个 id 引用完整、`#2` 用真实报告核对 22 行可读无技术字段。**未做浏览器端点击验收。**
- **P6 第 1 轮评分（FL-D070）**：`p6-dev-round1-01` 20/20 完成，677 调用，$0.5738。**开发集 236 目标：基线 178（0.7542）→ 187（0.7924，+3.8pt）**；G15 +9、G05 +2、G17 −2；`applicability_conflicts` 29→13；**假完成仍 12**。评分产物 `/tmp/opencode/p6-round1-score.json`。**仍未达阈值（0.95/0.9）**。
- 测试：`.venv/bin/python -m pytest tests -q` → **561 passed / 1 expected（references/）/ 6 skipped**。
- **已提交（本地，10 个逻辑提交 `cc558ab..3a3f524`），push 被凭据阻塞**：工作树干净；`origin` 为私有仓库 `github.com/JokerNephew/FundLex`，本机无 HTTPS 凭据/SSH 私钥/`gh`，`git ls-remote` 报 `could not read Username`，SSH 报 `Permission denied (publickey)`。已配置仓库级代理 `http.proxy=http://127.0.0.1:9981`（GitHub 直连可达但走代理更稳）。→ **FL-D072**
- **未发布**：部署副本 `/opt/fundlex-recall-first` 仍为上一版。
- **预览服务（临时）**：`FUNDLEX_DATA_DIR=/tmp/opencode/fundlex-preview FUNDLEX_AUTH_MODE=dev .venv/bin/uvicorn fundlex.api:app --host 127.0.0.1 --port 8020`，供浏览器（经 SSH `-L 8020:127.0.0.1:8020` 转发）查看新代码；验证完应停掉。
- 下一动作：① 用户提供 GitHub 凭据后 `git push -u origin codex/fundlex-recall-first`（或新分支/PR）；② 浏览器端验收前端问题 1/2/4/6/7/8；③ 经确认后 `bash tools/deploy/publish_workspace.sh` 发布；④ 继续修 P6 开发集 `not_executed`（17，G01/G03/G16）+ `kept`（32，G17/G15/G14/G11/G08/G18）。

## 第 5 轮进度（服务器，2026-10-15）

- 基线复核：`uname` Linux x86_64；`.venv` Python 3.11.13；`/home/opencode/data/MANIFEST.sha256` 538/538 OK；`fundlex-recall-api`/`fundlex-recall-worker` active；`/api/capabilities` 200。
- 基线测试：`.venv/bin/python -m pytest tests -q` → **530 passed / 1 failed / 6 skipped**（唯一失败=`test_rules_catalogue`，references 未随迁移，预期）。
- 已修四类真实缺陷（**FL-D052**，见集中问题记录；代码在 `fundlex/recall.py`、`fundlex/recall_pipeline.py`）：
  1. survey 引文切片 compact→raw 偏移错误（`compact_offsets`；`survey_targets`/`plan_composite_target` 改用）；
  2. 跨段盘点目标未重绑定（`_rebind_unresolved_targets`，盘点后+每轮修复后执行，报告新增 `rebind` 段）；
  3. 同段多操作被首个命中短路（`plan_target` 累积 delete+replace，新增 `fragment_mixed`）；
  4. 查漏位置误报与“已满足”漏判（`_rule_mapped_locations`+`_sweep_batch(rule_locations=…)`→`SWEEP_LOCATION_OUT_OF_SCOPE`；`_rule_location_absent`→`SWEEP_LOCATION_NOT_RULE`；`satisfied_by_new_text` 同政策异语序等价；裸尾片段需上下文佐证 `bare_tail_keys`/`rule_context_anchors`）；并新增确定性审计确认 `_confirm_merged_append`（G03 p141、G16 p809 的 append+兄弟删除合并误判）。
- 新增单测 7 项；全量 **537 passed / 1 failed（预期）/ 6 skipped**。
- qr-local-12 12 项逐条结论：G05 p142=真实缺陷（已修）；G15 p806/p1262=跨段（已修）；G03 p141、G16 p809=审计误判（已加确定性确认）；G05 p760、G16 p227、G18 p139/p829/p1217、G22 p142=误报（已加过滤）；另修正 FL-D047 遗留判断：G05 真实目标只有 p142，p954/p1332 是“基金合同变更”条款非费用类别调整句。
- **已发布**：`tools/deploy/publish_workspace.sh` 成功（拷贝到 `/opt/fundlex-recall-first`、重启服务、capabilities 200）；部署代码已含全部 FL-D052 修复。
- **真实链路复验 quality-return-10**（应用链路：register→login→tasks→uploads→seal→轮询→下载；真实模型）：`task_status=completed`、`job_status=succeeded`、**64 调用 / $0.0461 / 230431 tokens / 358s / delivery=incomplete**；**targets 28 / completed 27 / unresolved 1**（对比 qr-local-12：30/14/12）；`rebind=[]`；`output_validation` 有 working_final/working_redline sha256。产物在 `var/cloud-runs/quality-return-10/`（report.json/working_final/working_redline/report_md）。
  - 已验证：G05 p142 同一目标同时 replace（调低销售服务费率）+ delete，`fragment_mixed` 生效；G03 p141 审计 completed；G16 p809 审计 completed（`_confirm_merged_append` 生效）；跨段 G15 p806/p1262 已解决；G18 p139/p829/p1217、G22 p142、G16 p227 误报消失（sweep dropped 记录 `SWEEP_LOCATION_OUT_OF_SCOPE`/`SWEEP_LOCATION_NOT_RULE`/`SWEEP_ALREADY_SATISFIED`）。
  - **残留 4 项未解决**（3 类原因）：① **G17 p808** `RECALL_COMPOSE_DELETE_NOT_SHRINKING`（审计 wrong）——规则 `old_text` 是 p808+p809 两句拼接，而 T018 目标只含 p808 一句，`_splice_fragment`/`variant_delete` 均无法匹配整段参考，落到 compose-delete 后被模型原样返回；② **G02 p106 sweep 误报**、③ **G04 p138 sweep 误报**——`class_substitution` 规则的 `new_text`（`A类、B类基金份额`）是指引示例，本产品只有 A/C 类，盘点已正确判 `satisfied`，但 sweep 模型把示例当真需求；④（第④项为 ①②③ 的审计/sweep 派生条目）。
- **第 5 轮第二轮修复（同属 FL-D052）**：
  1. `recall.class_substitution_noop`（新）：`class_substitution` 规则若各适用操作的实例化 `new_text` 与其 `old_text` 相等（产品实际类别已就是规则要的分组），则该规则无需修改；`recall_pipeline._rule_already_satisfied` 前置调用 → sweep finding 记 `SWEEP_ALREADY_SATISFIED`（修 ②③）。
  2. `recall.plan_target` 新增“删除整段目标”确定性分支：delete-only 规则、目标引文（compact）等于目标 span 且是规则 delete 参考文的子串时，整段 `replacement=""`（`variant_delete`），不再走 compose-delete（修 ①）。
  - 新增单测 3 项（core 2 + pipeline 1）；全量 **539 passed / 1 failed（预期）/ 6 skipped**。
- **未做**：quality-return-11 复验进行中、P6 评测。**本工作区未 commit、未 push**。
- 本轮模型调用：**0 次**（全部为离线单测与对既有 report.json 的离线核对）；应用账本 `/var/lib/fundlex/model_budget.sqlite` 的调用来自 quality-return-10/11 的应用任务，非 agent 自用（自用 0 次）。
- **第 5 轮第三轮修复（同属 FL-D052，已通过真实链路验证）**：quality-return-11 暴露两处新问题 →（a）G15 p806 因合同把支付条款拆成 p806+p807 两段、且指引措辞与合同不同，盘点把目标绑成单段 `…按月支付，`，删除无法覆盖续段 → 落 compose-delete 失败；（b）G16 p809 审计随之误判。修复：`_rebind_unresolved_targets` 新增 `extend_resolved`（仅跨段 composite 可替换已解析单段绑定）+ `_clause_continuation_binding`（整段覆盖 + 段末逗号 + 删除/替换规则 → 并入紧随一段）。新增单测 `test_rebind_extends_resolved_target_to_clause_continuation`。
- **quality-return-12 真实链路结果（已通过）**：`delivery_status=complete`、unresolved 0、targets 27/27、sweep_findings 0、**25 调用 / $0.0236 / 127s**；G15 重绑定 `p806:0:34+p807:0:88`。产物 `var/cloud-runs/quality-return-12/`；`final`/`redline` 哈希与报告一致（`862548a7…` / `2e586002…`），redline 含 16 `w:ins`+16 `w:del`；p806/p807/p808 删除、p809 保留+追加、p142 replace+delete 均在真实 DOCX 中核对通过。**FL-D052 全部收敛。**
- 全量测试：`.venv/bin/python -m pytest tests -q` → **540 passed / 1 failed（预期，references 未迁移）/ 6 skipped**。
- **待用户协助**：~~quality-return-10/11/12 的临时账号（`cloud-run-*`）与任务~~ **已于 2026-10-15 清理完毕（FL-D053 已解决）**：用户提供 3307 应用账号凭据，按 cloud_verify 顺序删除 3 账号及其任务/批次/文档/产物/会话；`admin` 与 `cloud-eval-*` 未动。
- **下一步**：P6 真实修改评测（28 份：20 开发 + 8 留出）。

## 第 6 轮（P6 真实修改评测，2026-10-15 续）

- **目标**：按 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` 执行 P6：28 份合同（20 开发 D01–D20 + 8 留出 H01–H08）走真实应用链路（`recall_first` 引擎、真实模型），对**实际 DOCX** 与**先冻结的独立标签**计分，据结果优化；留出集在冻结版之前只读一次。
- **样本选择**：`tools/evaluation/p6_select.py`（新）按分层确定式抽取（active/qdii/fof/likely_excluded/other 目标 16/3/4/3/2，stride 填充，dev/holdout 交错）；输出 `var/recall-first-evaluation/p6/selection.json`（`a7ed2519…`）。范围=514 份 `funds_word`，hash 引用 `/home/opencode/data/MANIFEST.sha256`。
- **独立标签**：`tools/evaluation/p6_label.py`（新，**盲于引擎输出**，只读指引 + 原件）。确定性推导事实（基金类别、份额类别与费用规则、浮动费）与逐规则义务；`old_text` 按合同实际措辞定位，删/替义务源句缺失记 `not_applicable`。规模：**347 目标 / 26 可改合同 / 2 排除**。修正过份额类别与费用事实推导（跨段、术语式定义、A/Y 按账户分类、否定式“不收取申购费/不从…中计提销售服务费”），旧/新 hash 均记录在 `freeze.json`（`label_corrections`）。
- **协议与冻结**：`protocol.json`（预算：dev ≤2000 调用 / ≤$6；holdout ≤900 / ≤$3；单任务 ≤$1；账本在仓库外）、`freeze.json`（三份 hash + 已知局限）。`labels.json` `230b5be4…`。
- **运行器/评分器**：`tools/evaluation/p6_run.py`（单账号、每合同一个 `POST /api/tasks`、下载 final/redline/report）、`tools/evaluation/p6_score.py`（重读实际 DOCX 计分；引擎判 `not_applicable/satisfied` 而标签仍要求改动的，单列 `applicability_conflicts`，不静默计为漏改）。
- **本轮修复的真实缺陷**（均记入集中问题文档）：
  - **FL-D054**：长合同 sweep 阶段 `MODEL_CONTEXT_LIMIT` 整单不产出 → `_sweep_chunk_chars` 扣减 `facts_text` 与固定开销。D01(1363 段) 复验不再触发。
  - **FL-D055**：审计把份额类别占位符展开误判为无依据新增 → `AUDIT_INSTRUCTION` 增补通用总则。
  - **FL-D056/FL-D058**：无销售服务费类别产品被误判 `RECALL_SLOT_UNRESOLVED` → `slot_group_missing`（服务组为空或费用同质）+ class_substitution 规则整体判不适用 + `Target.out_of_scope` 统一审计/未解决统计 + `unresolved_targets` 排除 `not_applicable`。D07 由 26 项降到 0，真实链路 `complete`。
  - **FL-D052 补充**：整段删除在合同措辞与指引不同、composer 报 `DELETE_NOT_SHRINKING` 时，整段 `replacement=""`（`whole_paragraph_delete`）。D01 真实链路 `complete`。
  - **FL-D072**（未完全解决）：sweep 偶发误报 G02/G04 分组替换未完成（残留旧标签句）。已加确定性过滤，偶发一次；规划侧正确。
- **测试**：`.venv/bin/python -m pytest tests -q` → **544 passed / 1 failed（预期，references 未迁移）/ 6 skipped**。新增单测 5 项（sweep 预算 2、服务费组不适用 1、整段删除 1、费用组反向 1）。
- **已发布**：`tools/deploy/publish_workspace.sh` 成功；部署 `fundlex/recall.py` `ef600a1e…` 与工作区一致（前次 `87407fe1…`/`2a0df932…`/`7136d6ad…` 为迭代中间态）。
- **基线批次已完成**：`p6-dev-baseline-01`（20 开发集，修复前部署 `ef600a1e…`，日志 `/tmp/opencode/p6-dev-baseline-01.log`）：**20/20 完成，581 调用，$0.5624**；报告内部 `delivery_complete=13`（D01/D04/D05/D08/D09/D10/D13/D14/D15/D16/D18/D19/D20），D02 `excluded`，D03/D06/D07/D11/D12/D17 `incomplete`。
- **基线评分（实际 DOCX vs 冻结标签）**：以**较正后**的 `/tmp/opencode/p6-baseline-full2.json`（`scored_at 08:26`）为准：**开发集口径（剔除未跑的 8 留出与 D02 excluded）236 标签目标 / completed 178 / 率 0.7542**；`kept 41`；**integrated-complete 0/18**；**13 份假完成**；**applicability_conflicts 29**。（较早的 `/tmp/opencode/p6-baseline-full.json` 给 168/0.712，已被 full2 取代。）全量口径 347 目标 / 178 / 0.513（含未跑的 8 留出）。**远低于阈值（目标 0.95 / 整合 0.9）**。
- **优化第 1 轮结果（`p6-dev-round1-01`，已完成并评分，见 FL-D070）**：20/20 完成，677 调用，**$0.5738**；**开发集 236 目标 / completed 187 / 率 0.7924（较基线 +9 目标，+3.8pt）**；规则层 **G15 +9（0/15→9/15）、G05 +2、G17 −2**；`kept 32`；`applicability_conflicts 13`；**假完成 12（actually_complete 1）**。评分产物 `/tmp/opencode/p6-round1-score.json`（sha256 `07fb0112…`）。**仍未达阈值**，不满足正式交付条件。
- **基线漏改归因**：`not_executed` 主要为 G01(5)+G03(5)+G16(3)（无条件 append 漏加，FL-D060）；`kept` 主要为 G15(7)+G17(4)（删除句变体漏删，FL-D059/FL-D062）。
- **本轮（发布前）修复并发布**：FL-D059（`_strip_class_lead` 短锚，G17 11/11）、FL-D052 整段删除兜底、FL-D062 通用结构化删除兜底（`_delete_keyword_bag`+`_keyword_bag_in_clause`，G15 28/28 精确 2 处、零误报）、FL-D054/D055/D056/D058。测试 **546 passed / 1 expected / 6 skipped**。
- **已发布**：`bash tools/deploy/publish_workspace.sh` → 部署 `fundlex/recall.py` `3bccf52788cb5bbc…` 与工作区一致；`fundlex-recall-api`/`worker` active，`/api/capabilities` 200。
- **进行中（第二轮=优化第 1 轮，第 3 次重跑）**：`p6-dev-round1-01`（20 开发集，最新构建 `fundlex/recall.py` `07b39288b87dfa14…`，日志 `/tmp/opencode/p6-dev-round1-01.log`，`--timeout 1800`）。前两次尝试见下。
- **第 2 次尝试结果（构建 `6340b6618745af32…`，已归档 `p6-dev-round1-01-prev`）**：20/20 完成，677 调用，$0.5738。评分（`/tmp/opencode/p6-round1b.json`）：开发集 **236 标签目标 / completed 187 / 率 0.792**（基线 0.712）；`applicability_conflicts` 38→13。**剩余主因**：G01/G03/G16 无条件 append 漏加（7/7/3）；G17 跨段删除次段残留（10）；G15 短锚误判（6，FL-D074 已修）。据此新增 FL-D074（评分器短锚误判）、FL-D075（G17 跨段删除）。
- **本轮新增修复（已发布，`07b39288b87dfa14…`）**：FL-D063（删除 span 延伸到引用所跨句数 + 句首回退避开公式行 + 词袋配对防误并 + `target_span_delete`）、FL-D064、FL-D062、FL-D065、FL-D067、FL-D074（评分器按引号内整条条款判删除）、FL-D075（G17 跨段删除合并）。全量 **562 passed / 1 expected / 6 skipped**。
- **本轮新增修复（已发布，`6340b6618745af32…`）**：FL-D063（删除 span 延伸到引用所跨句数 + 句首回退并避开公式行；G17 半删 / G15 空删修复）、FL-D064（survey 兜底补 `.with_parts()`）、FL-D062（G15 结构化删除兜底）、评测器 `appendix_present` 归一化（FL-D065 边界）、FL-D067（遗留 append 测试按当前 API 重写）。全量 **559 passed / 1 expected / 6 skipped**。
- **环境问题（FL-D066）**：中止批次遗留的模型账本 `reserved` 预留会阻塞后续任务（`MODEL_CONCURRENCY_LIMIT`，`concurrency=1`）；经重启 worker 缓解。**规程更新：不在任务在途中 kill 批次；中止后先重启服务。**
- **本轮新增修复（已发布）**：FL-D063（短锚点删除延伸到句末，修 G17 半删 / G15 空删）、FL-D064（survey 兜底命中补 `.with_parts()`，修 `IndexError`）、FL-D062（G15 通用结构化删除兜底）、评测器 `appendix_present` 归一化（FL-D065 边界：真漏加仍判 not_executed）。
- **环境问题（FL-D066）**：中止批次遗留的模型账本 `reserved` 预留会阻塞后续任务（`MODEL_CONCURRENCY_LIMIT`，`concurrency=1`）；经重启 worker 缓解。**规程更新：不在任务在途中 kill 批次。**
- **评分器**：`tools/evaluation/p6_score.py` 已实现并校准——按标签 `compact_start` 定位原段落，再按内容在最终文件中找回同一段落（段落索引会因增删而位移），在该**区域**内判断旧措辞是否消除/新义务是否到位。避免两类假信号：短锚点同时出现在无关条款；替换文本以旧措辞为前缀。
- **基线首轮已定位的漏改类别**（见集中问题文档）：
  - **FL-D059**：删规则合同措辞变体未进 survey → G15/G17 被判 not_applicable、应删条款保留（D01 两处×2）。**已实施修复**（`_strip_class_lead` 短锚点），独立验证命中。
  - **FL-D060**：无条件 append 规则在原文该条款缺失时被盘点判 not_applicable，导致漏加（D01 的 G01/G03）。**未解决**，待全量统计。
  - 评分器首轮还暴露出：D01 G05 在多处“费用调整”条款中只改了一处（标签冻结单点）、G18 替换未落实；D03 G08 引擎超规划到无源条款位置报 `RECALL_TARGET_UNRESOLVED`（非标签目标，属执行质量问题）。
- **本轮模型调用**：应用账本计 smoke-01..08 共 ≈ 600 调用 / ≈$0.5；开发集基线单独计费（见 `protocol.json` 预算）。**agent 自用 0 次**。
- **本工作区未 commit、未 push**。

## 0. 迁移决定与执行记录（2026-10-15，用户指令）

- **开发主副本迁移到云服务器**：`/home/opencode/fundlex`（专用用户 `opencode`，OpenCode v2.0.29 systemd 常驻，仅监听 127.0.0.1:49374）。
- 迁移内容：整个工作区（含 `.git`、`docs`、全部未提交改动）；排除 `var/`、`funds/`、`funds_word/`、`references/`、`.venv`、缓存与同步残留。
- **资料迁移（`/home/opencode/data`，与工作区分离）**：`funds_word/`（514 份合同）与 `references/`（24 份原件）已迁移，`chown -R opencode:opencode`、目录 750、文件 640；服务器生成 `MANIFEST.sha256`（每行 `sha256  相对路径  字节数`，注释行记录 538 文件 / 82361614 字节 / 生成时间 / 主机）；逐文件与本地比对 0 不一致（FL-D050）。**资料不进工作区、不进 git**；后续评测抽样引用该清单。`funds/`（历史 PDF）与 `.venv`、缓存不迁移。
- **执行记录（`tools/deploy/migrate_workspace.py` 等）**：
  - 打包 824 文件 / 283MB → 上传 → 解包覆盖 `/home/opencode/fundlex`（staging 校验 `layout-ok`）→ `chown -R opencode:opencode` → 保留可执行位；
  - 核对：远程文件数 824 = 本地包内文件数；11 个关键文件 sha256 全部一致（`fundlex/*.py`、`frontend/*`、`guides/builtin_guide_v1.json`、`docs/*.md`、`pyproject.toml` 等，见 `tools/deploy/migrate_verify.py`）；
  - git：远程 HEAD `3ed4e96146a04d3092de6c57138289bdffeca526`、分支 `codex/fundlex-recall-first`，与本机一致；工作区状态 55 项（本机 56 项，差一个未迁移的 `references/`）；
  - 服务器仓库设置 `core.autocrlf=input`、`core.quotepath=false`（修 CRLF 状态噪声与中文路径显示，FL-D049）；
  - 迁移后补传的文档/脚本哈希逐项一致（`tools/deploy/migrate_fixup.py` 复验）；
  - 服务器环境：`/usr/bin/python3.11 -m venv .venv` + `pip install -e '.[test]'`（pytest 9.1.1 / Python 3.11.13）；**基线测试 530 passed / 1 failed / 6 skipped**，唯一失败是 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`——该用例校验 `references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx` 的来源哈希，而 `references/` 按迁移约定不带去服务器（本机为标准 531 passed）。
  - 最终状态：源码文件 229（不含 `.git`/`.venv`/缓存）+ `.git` 对象 606 + `.venv` 4074；`git status` 55 项（11 个已跟踪修改 + 44 个未跟踪，与本机一致，仅缺未迁移的 `references/`）。
- 迁移后核对：74/74 关键文件哈希一致（`fundlex/*.py`、`frontend/*`、`guides/*.json`、`docs/*.md`、`tools/deploy/publish_workspace.sh`），远程 HEAD `3ed4e96…`。
- 迁移后：**服务器工作区是开发主副本；本机（笔记本）副本转为只读备份**。不要两边同时改同一份代码。
- 应用部署 `/opt/fundlex-recall-first` 不动；发布走 `/home/opencode/fundlex/tools/deploy/publish_workspace.sh`（内部调 root 的 `/usr/local/sbin/fundlex-publish`）。
- 不 push（未经用户要求）；不改应用部署，除非已按项目规定完成真实验证与问题登记。
- 模型账本：应用调用记 `/var/lib/fundlex/model_budget.sqlite`；常驻 agent 自身调用不记入该账本，用量单列跟踪。

## 目标与用户约束（摘要）

- 完成 FundLex 整个项目交付：前端、后端、召回优先修订引擎、指引配置、账号、持久任务、MySQL、云部署、真实用户端到端验收、20—30 份真实合同评测与优化闭环。
- 召回优先：模型负责业务判断/映射/盘点/联合修改/复核；代码负责结构地址/来源核对/执行/可靠性。不按关键词或旧文相等拒绝真实目标；已有命中仍查漏。
- 默认内置指引；自定义同结构 DOCX 指引仅在配置页上传/查看/启用/恢复默认；任务页只上传合同；任务绑定不可变指引版本。
- 每轮从原件重生成；复核发现问题自动补证/修复/仲裁，未解决才记未完成。
- 细节问题集中登记 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`；上下文 60% 前压缩或交接。
- 最终验收必须走真实用户端到端路径（工作台登录→上传真实合同→真实模型→DOCX 修改→复核→下载），见 AGENTS.md。

## 仓库状态（本机，迁移前）

- 分支：`codex/fundlex-recall-first`；HEAD：`3ed4e96`（仍未提交 commit；全部为工作区改动）。
- 已跟踪修改（5 个）：`IMPLEMENTATION_PLAN.md`、`README.md`、`docs/RECALL_FIRST_DESIGN.md`、`frontend/app.css|app.js|index.html`、`fundlex/api.py|jobs.py|model.py|store.py|tasks.py`。
- 未跟踪新增（节选，全部随迁移带上）：`AGENTS.md`、`fundlex/recall.py|recall_pipeline.py|recall_prompts.py|guide.py|guide_store.py`、`guides/builtin_guide_v1.json`、`tests/test_recall_*.py|test_guide*.py`、`tools/deploy/`、`tools/evaluation/recall_run.py|replay_checkpoints.py`、`docs/*.md`（含本文件、集中问题记录、实施计划、交接文档）。
- 明确不迁移：`var/`（产物与账本）、`funds_word/`（真实合同原件）、`references/`（指引原件）、`.venv/`、`__pycache__`、`.pytest_cache`。

## 已完成（有证据）

1. **内置指引**：22 组 / 34 操作，确定性校验干净，独立核验逐条处置（FL-D040）；哈希冻结。
2. **引擎核心 + 编排**：事实/映射/盘点/规划/写入/审计/修复/最终查漏/交付裁决；确定性优先；working_final/working_redline 门禁。
3. **第 4 轮新增确定性覆盖与跨段能力**（FL-D047）：`survey_targets` 在全部段落按规则参考旧文补扫（摘要第二处、变更章节残留）；`find_old_text_all` 边界/引导语约束；`plan_composite_target` 跨段删除/替换按段落精确执行；`satisfied_by_new_text` 已满足识别；`_absorb_sweep_findings` 重绑定（含跨段）；审计上下文覆盖 composite 段落；`recall_inventory_v2` / `recall_sweep_v2` 指令。
4. **FL-D048 修复**：条件不适用记 `not_applicable`（不再当未解决）；STOP_CODES 的 ModelError 直接暂停（`RecallPipelineStop`）；账本 reserve/finish 瞬时 readonly/locked 重试 3 次；`recall_run.py` 把 `--max-calls` 同时写入 `FUNDLEX_MODEL_MAX_REQUESTS`；`SOFT_STOP_CODES`（schema/quote/evidence 类）也按可恢复暂停处理。
5. **持久化/API/前端**：指引版本与配置、任务绑定快照、下载白名单、指引配置页、提交页只读显示当前指引。
6. **云端部署**（8.155.130.168）：`/opt/fundlex-recall-first`（8010，systemd `fundlex-recall-api`/`fundlex-recall-worker`，nginx 已切）；MySQL 127.0.0.1:3307/fundlex；公网 `http://8.155.130.168` 已实测 200。
7. **真实云端运行**：quality-return-01…09（产物在 `var/cloud-runs/`）；最新 09：69 调用 / $0.046 / 350s、delivery=incomplete、findings 8（其中 8 条经阅读为真实线索，FL-D047 已针对其治理）。
8. **全量测试**：`pytest tests -q` → **531 passed / 6 skipped**（MySQL 用例需 FUNDLEX_MYSQL_TEST_URL）。

## 本机真实运行证据（第 4 轮）

- `var/recall-runs/qr-local-01`：旧代码，48 calls / $0.029，`not_generated`；暴露 G07/G10 `RECALL_NO_APPLICABLE_OPERATION` 与账本 readonly 停止（催生 FL-D048）。
- `var/recall-runs/qr-local-11`：修复后，48 calls / $0.0284 / 198s，`not_generated`；survey 找到摘要 G22 p1357；sweep findings 0；仍有 G15 `RECALL_TARGET_UNRESOLVED`（跨段参考文与合同变体不匹配）与 G05 一处 `RECALL_COMPOSE_FIXED_TEXT_MISSING`。已针对这两类再改：非等价旧文先归一化再拆分（`_normalized_operation_text`）、`_operation_fingerprints` 逐级降级匹配、停止码细分。
- `var/recall-runs/qr-local-12`：上述再改后的运行完成（143 calls / $0.0748 / 512s，`incomplete`，targets 30 / edits 14 / rounds 5）。剩余未解决 12 项，下一条动作的输入：
  1. **G15 跨段目标未解析**（`RECALL_TARGET_UNRESOLVED`，p806；盘点引文与合同变体文不一致，sweep 本轮未报该规则，故 composite 重绑定没触发）→ 需要在“盘点/审计给出的目标本身引文未解析”时也走 `_operation_fingerprints` 降级匹配（不只是 sweep finding）；
  2. **G05 p760 假阳性**（survey 生成 `Y003`，plan 落 compose 后 `RECALL_COMPOSE_FIXED_TEXT_MISSING`，审计已判 wrong）→ 两处待查：① `_survey_targets_from_hits` 的引文切片疑似偏移一位（记录 quote 为“人并报中国证监会备”，实际应为“并报中国证监会备案”，导致 `_splice_fragment` 失配而走 compose）；② p760 是基金资产估值差错更正条款，与费用类别调整无关，需在 survey/规划入口按上下文过滤或交由审计裁决后不再进未解决。
  3. **审计未通过 4 项**：G03 p141（wrong）、G05 p142（incomplete）、G15 p806（incomplete）、G16 p809（wrong）→ 逐条读审计理由与产物片段核对（如属模型误判需按证据回驳，如属真实缺陷则修）；
  4. **sweep findings 5 条**：G16 p227、G18 p139/p829/p1217、G22 p142 —— G18 三条对应 FL-D047 里“已满足判定”的适用问题（p139 变体未被识别为已满足；p829/p1217 是摘要对应位置的追索），G22 p142 疑似位置错配（p142 是类别调整句，真实清算条款在 p978/p1357 已改），G16 p227 是摘要对应位置的追加缺失。
  以上均为“开发中真实缺陷”，不是评测或替身：修复后应在云端 quality-return-10 复验。

## 外部阻塞

- ~~**公网 HTTPS 未配置**（无域名）~~ **已于 2026-10-15 解决**：用户提供域名 `fundlex.club`，A 记录指向 `8.155.130.168`；已配 nginx + Let's Encrypt（acme.sh，自动续期），**`https://fundlex.club` 公网实测 200、证书有效、http 301 跳转 https**。详见集中问题记录 FL-D044。宝塔面板若重写站点 SSL 设置可能覆盖配置，旧版备份为 `fundlex.conf.pre-ssl-*`。
- **本机账本限制**（已登记 FL-D048）：本机 `var/` 目录被同工作区其他 agent 会话持续占用，SQLite 稳定 readonly；本机运行账本必须放项目目录之外（`%TEMP%` 或 `%LOCALAPPDATA%`）。迁移后本机仅作只读备份，此限制不再影响主开发。
- 评测额度：服务器账本 cap 20000 次 / $50（示例配置）。评测 28 份预计 $5—15，需用户确认额度或沿用服务器凭据。

## 模型账本与预算（预登记）

- 价格：input $0.15/M、output $0.60/M（OpenCodeGo deepseek-v4.1-flash）。
- 本轮（第 4 轮）已用：本机开发运行合计约 106 次调用 / ≈$0.06（qr-local-01 约 10 次、qr-local-11 48 次、qr-local-12 进行中；口径以各运行 report_json 的 `model` 段为准）。均在 P3—P5 预登记额度（≤1500 次 / ≤$8）内。
- 迁移后：开发验证默认走服务器应用链路，调用记 `/var/lib/fundlex/model_budget.sqlite`；常驻 agent 自身调用单列跟踪、不混入。
- 每次真实批量运行前写 `protocol.json`（样本/版本/预算/最坏调用上限），见实施计划 §5。

## 运行中的进程 / agent（迁移时）

- 本机：`qr-local-12` 开发运行（账本在 `%TEMP%\ledger-qr-local12.sqlite`）仍在执行；其产物在 `var/recall-runs/qr-local-12/`，不影响迁移（`var/` 不打包）。
- 本工作区另有其他 agent 会话在活动（`docs/RESIDENT_AGENT_SETUP.md` 等新文件非本轮所写）；迁移前已核对本文件与集中问题记录无冲突。
- 云端：`fundlex-recall-api`/`fundlex-recall-worker` 常驻（systemd）；`opencode.service` 常驻（127.0.0.1:49374）。

## 下一条可执行动作（服务器工作区，第 5 轮后）

1. ~~发布~~、~~quality-return-10/11/12 真实链路复验~~ 已完成；FL-D052 四类缺陷全部收敛，quality-return-12 `delivery_status=complete`、unresolved 0。
2. **P6 评测**：28 份（20 开发 + 8 留出），引用 `/home/opencode/data/MANIFEST.sha256` 冻结样本，写 `protocol.json`，独立标签冻结、评分读实际 DOCX；结果落 `docs/REAL_REVISION_EVALUATION_RESULTS.md`。预登记预算（≤相应调用/费用上限，ledger 放项目外）。
3. **FL-D053 清理**：请用户协助清理 quality-return-10/11/12 的临时账号与任务（无 DELETE 接口、DB 需 root 凭据）。
4. **P7**：浏览器端到端、服务重启续跑、双身份隔离、指引切换、MySQL 备份恢复演练。**正式入口 `https://fundlex.club` 已上线（FL-D044 已解决）**，P7 浏览器验收可直接走该 HTTPS 域名。

## 关键命令

- 服务器工作区测试：`cd /home/opencode/fundlex && .venv/bin/python -m pytest tests -q`（或只读用 `/opt/fundlex-recall-first/.venv/bin/python`）。
- 发布：`/home/opencode/fundlex/tools/deploy/publish_workspace.sh`。
- 云端真实运行：`python -X utf8 -m tools.deploy.cloud_task_run --contract "..." --output var/cloud-runs/<run> --timeout-min 30`。
- 资料目录（与工作区分离）：`/home/opencode/data/{funds_word,references}`；清单核对：
  `cd /home/opencode/data && awk '!/^###/ {print $1"  "$2}' MANIFEST.sha256 | sha256sum -c -`
- 本机（只读备份）真实运行：账本放 `%TEMP%`，命令见 `tools/evaluation/recall_run.py` 顶部说明；资料迁移脚本 `tools/deploy/migrate_data.py` / 工作区迁移脚本 `tools/deploy/migrate_workspace.py`。
