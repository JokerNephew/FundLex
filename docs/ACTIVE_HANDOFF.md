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

更新：2026-10-16（服务器开发主副本 `/home/opencode/fundlex`，接续 agent **第 12 轮**：A/B 遗留规则集退出运行时，能力接口收敛为 engine 契约，交付语义改由指引版本状态决定，FL-D093/FL-D094/FL-D095，生产端到端验收通过）。规则：50% 整理、60% 前完成压缩/交接；本文只记状态与下一动作，不写密码。

> **第 12 轮要点（A/B 下线）**：见 [`docs/LEGACY_RULESET_RETIREMENT.md`](LEGACY_RULESET_RETIREMENT.md)。
> 运行时仅服务指引绑定的 recall-first；`capabilities` 只返回 `engine` 对象；`/api/tasks` 只接受 `engine_id`（传 `ruleset_version` → 422 `RULESET_RETIRED`）；`/api/batches` 创建 → 410；遗留任务只读且标记 `legacy`。
> A/B 代码与规则文件**保留**（测试与离线评测直接导入管线），但不再被运行时引用。
> 相关提交：`5615609`（方案）→ `beee73e`（后端收敛）→ `2b32e40`（测试）→ `93196d9`/`012ba18`（前端与遗留标注）→ `67410b3`（收尾）。部署副本与仓库一致，服务 active。

> **编号更正（FL-D077，2026-10-15）**：集中问题记录曾有 5 组编号重号，已把后出现者改为新编号（保留首次出现的原编号）：
> `FL-D057→FL-D072`（sweep 误报 G02/G04）、`FL-D058→FL-D073`（无服务费结论）、`FL-D068→FL-D074`（评分器短锚误判）、
> `FL-D069→FL-D075`（G17 跨段删除）、`FL-D066→FL-D076`（Codex bwrap）。
> **注意**：本文下文第 5/6 轮的历史叙述写于更正之前，个别处仍写旧编号，含义以更正后为准；新增条目一律先查重再编号。

## 当前断点（2026-10-18，模型供应商切换 + 外部模型复查核验）

- **供应商切换（按用户指示，先不切回）**：原 `OpenCodeGo` 周限额耗尽（429 `GoUsageLimitError`，retry-after ≈19.5h，见 FL-D111）。已改为 **DeepSeek 直连**：
  - `/etc/fundlex-recall.env`（备份 `/etc/fundlex-recall.env.bak-20261018-132608`）：`LLM_PROVIDER=deepseek`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`；API key 只在 env 文件，不写仓库/文档/聊天记录。
  - 请求选项保持 `{"thinking":{"type":"disabled"}}`（实测该端点接受且 `reasoning_tokens=0`）；`FUNDLEX_MODEL_MAX_REQUESTS` 20000→40000，`FUNDLEX_MODEL_MAX_COST_USD=50` 不变；单价按目录价输入 $0.15/M、输出 $0.60/M。
  - 2026-10-18 13:26 CST 重启 `fundlex-recall-api` / `fundlex-recall-worker`；`/api/capabilities` 200；独立账本探测（`/tmp/opencode/upstream_probe2.py`）`UPSTREAM OK: {"ok": true}`。
  - 账本（切换前）：`17462` requests / charged **$14.4908**（上限 40000 / $50）。**用户明确指示前不切回原供应商。**
- **外部模型复查核验（已完成，未改引擎）**：对另一模型对核心链路的分析逐条对照当前代码与真实批次，新增 4 条记录（FL-D112～FL-D115）：
  - **FL-D112（新，最高价值）**：recall 生成内容复核闭包返回 bool 且 `validate_edit_plan` **忽略返回值** → 所有 `_component_ok` 复核（composite/fragment/variant）实际未生效；同时 `_composite_part_slice` 用 `display_text` 解释 compact 偏移，一旦校验生效会误拒带空白锚点的 composite。两处需一起修，属交付校验语义变更，待裁定。
  - **FL-D113（新）**：sweep 的按窗口规则范围在“该窗口 section 无任何规则映射”时为空 → 整窗 findings 被丢弃；round11 实测 14/80 个窗口零规则（D02/D12/D16 等每案 1–2 个盲窗）；约 69% section 字符所在 section 未被规则映射（含部分摘要）。待裁定 + A/B。
  - **FL-D114（新）**：未核验 Facts 仍参与 `excluded_by_fund_type`（整份结束）与 `condition_matches` 分支；round11/12/13 有 3/4/6 个案例含未核验引文，多为省略号/跨段导致的验证假阴性，`FUND_TYPE_QUOTE_UNVERIFIED` 每轮 1 例但均为 `open_regular`（未排除）。待裁定。
  - **FL-D115（新）**：sweep finding 以“重扫未再报”判 `resolved`，无针对性产物证据；round11 resolved 18 / pending 15，round12 8 / 19，round13 8 / 16。待裁定。
  - **复查中被证伪/夸大的项**：`structure_index` 80 段上限在 514 份语料中**不可达**（groups 中位 26、p90 30、最大 34，0 份超 80）；`facts_context` 的 `break` 在 29500 字符预算下抽样 120 份 **0 份截断**；target identity/复合删除/无 ledger 默认 planned 三点**已在 FL-D110 记录待决**，非新问题。
- **本轮已实施（2026-10-18，commit `ebcd9de`，尚未发布）**：按 [`REVISION_PLAN_2026-10-18.md`](REVISION_PLAN_2026-10-18.md) 完成 FL-D112 / FL-D113 / FL-D114（引文核验部分）与 FL-D110 缺陷 2/3/4：
  - 内容校验真正接线（False → 拒绝；坏 edit 丢弃并记 `RECALL_EDIT_CONTENT_UNVERIFIED`，其余继续）；composite 坐标改用 `compact_offsets` 并按整段校验，follower 不再走旁路；fragment 记录并重放 `fragments` 轨迹；variant/span-delete/composite_replace 证据与生产者对齐；`content_check_factory` 查找键加入 span。
  - target 身份改为全文 span hash；复合删除逐 part 校验；缺 ledger → `unresolved/LEDGER_MISSING`。
  - sweep 新增 `blind_windows` 记录 + 空范围窗口回退 mandatory 规则。
  - `_verify_quote` 支持省略号分段与跨段边界（fund_type 排除策略未改）。
  - 测试：新增 9 项；全量 **680 passed / 6 skipped / 1 failed**（唯一失败为既有 references 缺失项）。
- **下一动作**：
  1. **`p6-dev-round14-03` 基线已完成**（DeepSeek 直连、旧引擎）：dev-only **218/236 = 0.9237**（kept 11 / not_executed 7），6 报 complete / 10 实际 complete / 1 false_complete；1019 calls / $0.7372。对照 round11 dev-only 225/236 = 0.9534（旧供应商）。**注意 FL-D116**：此前 218/347 = 0.6282 与 225/347 = 0.6484 是评分器把 111 个未运行留出目标计入分母导致的低估；`p6_score.py` 已改为默认只评本次批次实际运行的 case（`--group run`），并支持 `--group dev|holdout|all`。
  2. 修正版 `ebcd9de` 已于 2026-10-18 14:16 CST 发布（部署文件 sha 与仓库一致，服务 active）；**`p6-dev-round14-04` 已完成**：dev-only **220/236 = 0.9322**（kept 10 / not_executed 6），7 报 complete / 11 实际 complete / 1 false_complete；1008 calls / $0.7536。对照 14-03（同供应商、旧引擎）218/236 = 0.9237：**+2 目标，无回归**；`RECALL_EDIT_CONTENT_UNVERIFIED` 两轮均为 **0**（校验接线未造成拒绝），14-04 记录 **16 个 blind_windows**。
  3. 已修 FL-D117 的 delete 路径（satisfied replace 不再压制仍残留的 delete survey），单测通过；待发布后跑下一批验证。模型 target 的 operation 粒度覆盖仍待改造。
  3a. **2026-10-18 追加（commit `61e210c`，已发布）**：operation-aware 覆盖键 `(rule_id, operation_key, location)`（含模型 target 与 fuzzy delete）、D115 evidence-gated finding closure、unverified `fund_type` 不排除且禁止 complete、零规则 blind window 回退全规则；全量 `pytest tests -q` → 686 passed / 6 skipped / 1 failed（既有）。发布后跑 **round14-06** 对照 round14-04（220/236）。
  3b. **2026-10-18 更新**：round14-05（仅 FL-D117 精确补丁）dev-only **220/236 = 0.9322**（kept 10 / not_executed 6），reported complete 2 / actual 11 / false 1；1240 calls / $0.9053——目标率持平、complete 更保守、成本 +23%。`61e210c` 已发布（部署 sha 一致）。
  3c. **2026-10-19 更新（外部阻塞 + P0 修复）**：DeepSeek 直连账户 **HTTP 402 `Insufficient Balance`**（直连复现）；round14-06 在 D02 触发 `BATCH_ABORTED MODEL_CIRCUIT_OPEN`，**批次作废、不得评分**。旧供应商 OpenCodeGo 周额度**已恢复**（带 session 头探测 200）；按用户“等指示再切回”的约定**未自行切回**，等待“充值 DeepSeek / 允许切回 OpenCodeGo”的决定。外部复查指出的 4 处漏接已修（commit `9ae799a`）：`_collect_targets` 只做精确去重、unknown operation fail-open、`_delivery_complete(unresolved)` 纳入 `coverage_gaps`、D115 三边界（`location_gone`、`wrong_text` required、`unaddressed_requirement`）；全量 **689 passed / 6 skipped / 1 failed**（既有）。**尚未发布**；供应商恢复后发布并跑 round14-07 对照 14-04/14-05。
  3d. **2026-10-19 09:16 CST 已切回 OpenCode Go**（新 key 仅在 `/etc/fundlex-recall.env`，未入库/文档；env 备份 `…bak-20261019-091621`）；`9ae799a` 已发布（部署 sha 一致）、capabilities 200、独立账本探测 `UPSTREAM OK`；**round14-07 运行中**。
  3e. **2026-10-19 更新**：round14-07 在 D01 触发 `PROCESSING_FAILED`（`AttributeError`，`_survey_targets_from_hits` 对 unknown 覆盖 update None）——**批次作废**；已修并发布 `03fbbfa`（改用 `_add_operation_coverage` + 回归测试），全量 **690 passed / 6 skipped / 1 failed**（既有）；**round14-08 运行中**。
  4. 对照重点：`RECALL_EDIT_CONTENT_UNVERIFIED` 数量、`blind_windows`/`SWEEP_RULE_OUT_OF_WINDOW`、working/incomplete 比例、kept 变化；供应商切换与修正合并，作为混杂因素注明。
  5. 结果稳定后再冻结版本 → 留出 H01–H08 → 评测报告 → 打包。
- **预算/账本**：真实运行前在批次说明预登记；账本 `/var/lib/fundlex/model_budget.sqlite`（切换前 requests=17462，charged=$14.4908；上限 40000 / $50）。
- **约束**：FL-D105 Q1–Q8、FL-D104 1–19 未裁定前不改规则适用性/评分语义；合同可入库/出境（公开资料），凭据不入库/不入文档。
- **2026-10-19 追加（文档侧，均未改引擎）**：产品负责人裁定 G08-1/G08-2 属"正常替换、按合同实际类别的收费性质实例化"（登记于 FL-D104 变更记录）；裁定 `compose` 两条硬约束（固定文本逐字、不新增数字）可推翻、改由"生成+独立复核"接管（登记于 FL-D106）；新增 **FL-D119**（G08 把"赎回费率"句误当"申购"参考命中：机制已离线复现，14-08 在飞批次显现，待裁定修法）与 **FL-D120**（"确定性优先、模型补位"方案）及其实施计划 [`GENERATION_STRATEGY_PLAN_2026-10-19.md`](GENERATION_STRATEGY_PLAN_2026-10-19.md)（**v2 已并入（产品负责人修订版）；评审修正点 8 项与 §39 待裁；待批准、未实施**）。

## 当前断点（第 12 轮，2026-10-16，P6 开发集真实修改评测收敛到 0.8602）

- **本轮任务**：用户指示「做二和三」——(三) Langfuse 退化为**本地 JSONL trace 兜底**，(二) 用它帮助 P6 评测优化。
- **(三) 已完成**：`fundlex/trace_sink.py`（FL-D088）。纯标准库、无网络、`FUNDLEX_TRACE_JSONL` 未设即 no-op；一合同一 trace（确定 seed）、一次调用一 generation、一条评测 score；活动文档 id 走 thread-local，引擎深处模型调用自动归入正确 trace。接线于 `model.py:_trace_attempt` + `jobs.py:_document_trace`（与 Langfuse 并列，可同开）。生产落点 `/var/lib/fundlex/traces/model-calls.jsonl`（env 备份 `…env.bak-tracesink`）。真实 20 例验证：1085 行、单条 25KB 含合同原文、19/20 trace 匹配、0 错误。分析器 `tools/evaluation/p6_trace_report.py` 把 trace 与评分按 trace_id 关联，直接产出「按规则/按阶段」失败画像。单测 `tests/test_trace_sink.py`。
- **(二) 已完成 — 用 trace 定位并修掉 3 个真实缺陷**：
  - **FL-D089 评分器误判**（commit `64dab0c`）：`appendix_present()` 因份额类别枚举差异把**已正确追加**的政策句判 `not_executed`。改为折叠枚举 + 模糊兜底逐字符步进。0.7892 → 0.8161，无引擎改动。
  - **FL-D091 append 家族缺陷**（commits `fc08350`/`c6c00aa`/`8331233`/`b78c26e`）：三层叠加——①措辞变体致盘点判 `not_applicable`；②缺 class group 时 append 被整体判不适用；③hit 被既有 `absent`/未解析目标压制。新增 `append_applicability_targets()` 确定性兜底 + 收窄 class-substitution 门限 + `override_rules`。
  - **FL-D091 类别名渲染缺陷**（commit `d900fb2`）：终稿出现 `default类基金份额`、`A类份额类基金份额`。修正 `class_label()` 剥离份额变体并丢弃占位名。
  - **FL-D089 补充**（commit `48fe3ca`）：单类别合同只应追加适用分句，评分器不再索要不存在的 C 类分句。
- **当前指标（开发集 20 例 / 236 目标）**：**0.9322**（completed 220 / kept 15 / `not_executed` **1**），目标 0.95。唯一残留 `not_executed` 是 **D07/G16**——该合同 `基金费用与税收` 章节**确无销售服务费条款**，引擎判不适用属正确。整合完成 `actually_complete` 5→8，目标 0.9（`kept` 15 为主要来源）。
- **评分器又修两处误判（同源：把「引擎做对了」读成没做）**：
  - **FL-D097**（commit `c68434d`）：删除规则的引文**跨多句**时，`_superseded_survives()` 的末句片段属于**相邻的、引擎有意保留**的条款，命中它就把已完成的删除判 `kept`。改为仅当锚点落在引文末句才计末句片段。
  - **FL-D098**（commit `1b478b2`）：删除成功后**原段落在终稿消失**，`locate_paragraph()` 返回 `-1`，而 `delete` 分支要求定位成功，于是**正确删除被判 `kept`**。改为「条款在全文已不存在即达标」。
  - **FL-D099**（本轮）：`replace` 的「新义务是否出现」用 24 字前缀精确判定，一处措辞差异（多一个「基金」、或合同真实类别 `A类、D类`）即分叉；同时标签 `old_text` 恰是修正后句子的子串，于是**正确替换被判 `kept`**。新增 `_obligation_in_region()`（规范化＋`difflib` 滑窗，阈值 0.9）作第三顺位回退。
  - 三处合计：0.8602 → **0.9322**（`kept` 32 → 15，`not_executed` 恒为 1）。逐目标核对确认**仅预期目标翻转、无误放**，并以**引擎自身审计**为独立佐证（D12/G14 仍判 `kept`，引擎审计同判未执行）。
- **剩余 `kept` 15 = 真实引擎缺陷（非评分器问题）**：G17 删除 ×5、G18 替换 ×3、G08 ×2、G11 ×2、G05 ×2、G14 ×1（D12 `RECALL_EDIT_OVERLAP`）。引擎 ledger 显示多为 `not_applicable`（作用域判定与终稿残留矛盾）或 `planned` 但未落地。
- **预算**：round2–round7 累计约 **$3.7**（单批 ~$0.52–0.70）；协议预算 dev ≤2000 calls/≤$6。
- **运维教训（FL-D096）**：**批次运行期间禁止 `publish_workspace.sh`**。已在飞批次的任务 pin 了旧 `engine_build`，重发布后 worker 校验失败 → 整批 `ENGINE_SCHEMA_MISMATCH`。round7 首批已作废留证并重跑。
- **并行协作**：另一 agent 同期推进前端（FL-D092 缓存、FL-D093/094 A/B 遗留规则集下线、HTML 呈现 + 逐条审查）。共享文档编号曾两次冲突（我的条目被并入 FL-D091、FL-D096），**改共享文档前先看 mtime，只做追加**。
- **下一动作**：① 就「优化轮次已达 baseline+7，超协议 3 轮上限；应用账本 charged $9.06 / 协议 total $10」请产品负责人定夺是否继续；② 若继续，按 `append_applicability_targets` 成例为**删除类规则**加确定性适用性兜底（FL-D100①），并单独排查 G18「替换未落地」；③ 达标前**不得冻结、不得读留出 H01–H08**。
- **预算与轮次（须如实上报）**：`protocol.json` 明文 optimisation rounds ≤3、total ≤$10；实际 baseline+7 轮；账本 charged **$9.0593**。协议指定的 per-run 来源 `report.json`（model 段）在各 `p6-dev-*` 目录下**不存在**，per-run 花费当前不可核验（FL-D100②）。

## 当前断点（第 11 轮，2026-10-16，静态资源缓存失效修复，**已生产验证**）

- **本轮任务**：用户反馈「我这里看着还是没变」——区块顺序调整已发布但页面仍旧版。
- **根因（FL-D092）**：`index.html` 以**无版本号固定路径**引用 `/static/app.js`、`/static/app.css`，nginx 也不下发 `Cache-Control`，浏览器沿用旧缓存。HTTPS 实取字节 sha 与仓库/部署一致（`bc5ac9c7d044e90d`），证明**服务端早已是新代码**，问题在客户端缓存。
- **修复（commit `64b0302`）**：`fundlex/api.py`
  - `_asset_version("app.css","app.js")` 按资源内容 sha256 生成 16 位版本标识，**每次发布自动变化**。
  - 入口 `/` 改为读 `index.html` 文本并注入 `?v=<hash>`，下发 `Cache-Control: no-store, must-revalidate`。
  - 新增 HTTP 中间件：`/static/*` → `public, max-age=31536000, immutable`（URL 带哈希，安全长期缓存）；`/`、`/index.html` → `no-store`。
- **验证证据**：
  - `TestClient`：`/` 返回 `no-store` 且引用 `app.js?v=a751d9b7f43c2426`；`/static/app.js|app.css` 返回 `immutable`。
  - 生产（nginx/`127.0.0.1:8010`）：首页含 `?v=a751d9b7f43c2426` + `no-store`；带版本静态资源 `immutable`。
  - **真实浏览器（生产、真实登录）**：16 条修订、目录 24 条 + 24 链接、拒绝 1 + 接受 15 → 下载 `selected_final` 136235 字节、**残留修订 0**、**控制台错误 0**。
  - 回归 `611 passed / 6 skipped`（排除既有基线失败 `test_rules_catalogue.py`）。
  - 已 `bash tools/deploy/publish_workspace.sh` 发布，api/worker active。
- **易错点**：若再遇「页面没变」，按「响应头 → URL 版本号 → HTTPS 实取字节 sha」三步先判定是客户端还是服务端，勿直接改代码或重发。
- **下一动作**：无阻塞。用户如仍见旧版，请**硬刷新（Ctrl+Shift+R）**一次即可清掉历史缓存；此后发布自动带新版本号，不再需要手动清缓存。

## 当前断点（第 10 轮，2026-10-16，前端逐条审查修订 + HTML 呈现，**已完整端到端交付**）

- **本轮任务**：用户选定 **A 服务端 HTML 方案**，要求：用户在结果页看到合同的 Word 呈现、**逐条勾选接受/拒绝修订**（与 Word 一致，任意组合自由）、据此生成**独立最终版产物**、支持一键接受全部；并指出 A 页**目录丢失**，要求排查是否还有其他丢失；指定全链路改造 + 进度管控 + 版本管理 + **完整端到端交付**，中途不得停下。
- **目录丢失根因（FL-D087，已查明并修复）**：demo 转换器只遍历 `body` 顶层 `w:p`/`w:tbl`，**整份目录位于唯一 `w:sdt`（20806 字符）内被静默丢弃**。完整丢失清单：目录 sdt（24 超链接 + 23 PAGEREF + 24 bookmark + 24 个 TOC1 段）、75 个 fldChar / 29 个 instrText 域、超链接不输出 `<a href>`、`w:tab` 硬编码、`sectPr` 分页信息。原文档 1363 个 `w:p` vs A 页 1252 个 `doc-p`。
- **方案规格与进度台账**：`docs/HTML_PRESENTATION_PLAN.md`（P0–P6 全部 ✅）。
- **实施（5 个 commit，全部已 push 到本地分支，未 push 远程）**：
  - `da86401` P1 投影层 `fundlex/html_view.py`（新增，只读）：通用块级遍历（含 `w:sdt`/表格）、`w:hyperlink`→真实 `<a href>`（经 rels 解析，协议白名单）、域代码隐藏仅留缓存结果、`w:bookmarkStart`→锚点、`w:tab`/`w:br type=page`/`sectPr` 投影；修订锚点直接取 OOXML `w:id`（**零文本匹配**）。
  - `40c53da` P2 选择性写入 `fundlex/selective.py`（新增）：`accept` 提升 `w:ins` 并删除 `w:del`；`reject` 删除 `w:ins` 并把 `w:delText` 还原为 `w:t`；未托管修订 id 只报告不改写；产物独立重开校验无残留。
  - `b9ff52a` P3 新 kind `selected_final` + 端点 `GET /revisions`、`POST /decisions`、`POST /accept-all`；`store.save_selected_artifact`（用户产物存 `selected/`，与 worker 产物隔离；`finish()` 白名单**故意不含** `selected_final`）。
  - `e9e51ac` P4 前端审查面板（单滚动容器 + 点清单 `scrollIntoView` 定位，**不做双栏同步滚动**——已实测两侧高度差 22% 无解）。
  - `b938a21` P6 文档与问题登记。
- **验证证据（全部真实、可复现）**：
  - 单元/集成：新增 19 项测试（`tests/test_selective.py`、`tests/test_revision_api.py`）；全套 **596 passed**（唯一失败 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation` 经 `git stash` 对照确认为**既有基线失败**，与本次无关）。
  - P2 关键正确性：全部接受输出与引擎自身 `working_final` **逐段一致**（1363/1363，0 差异）；全部拒绝恢复每一条 `expected_old_text`；单条拒绝只影响其所在段落（p1191）；纯删除型拒绝恢复被删文本。
  - **真实云端端到端（默认工作台入口，非遗留 `/api/batches`，未改任何发布标志）**：`POST /api/auth/login` → `POST /api/tasks`（`engine_id=recall_first`）→ `/uploads` → `/seal` → 真实 Worker + 真实模型 → `/revisions` → `/decisions` → 下载 `selected_final`。输入为干净原件 D01（sha256 `2f2f7a36…`，0 条既有修订）。结果：17 条修订全部映射、`has_toc True`、14 页；拒绝第 1 条 + 接受其余 → 下载文件 **0 条残留修订**、被拒条目还原原文、被接受条目保留替换文本、**目录 sdt 完整保留**、1338 个顶层段落结构未变；一键接受全部成功；引擎原有产物仍可下载未被替换。**incomplete 交付情形同样通过**（16 条修订 / `working_*` 产物）。
  - **真实浏览器（生产端点 127.0.0.1:8010，真实密码登录）**：17/16 条修订、目录 24 条 + 24 链接、勾选联动、点清单精确定位、生成与下载成功、**0 控制台错误**。脚本 `/tmp/opencode/browser_prod.py`。
- **验证中修复的真实缺陷（FL-D088）**：① 存储产物保留原始上传名无 `.docx` 后缀，`_read_parts` 以上传防护拒读 → `/revisions`、`/decisions` 对真实任务一律 422（真实路径才会暴露）；已改为经临时 `.docx` 副本读取，包限制不减。② 前端 `pathDoc` 用 `doc.id`，实际字段是 `document_id` → 请求 `/documents/undefined/revisions` 404；已修正。
- **易错点（接续必读）**：
  - 端到端验证**必须**用默认入口 `POST /api/tasks` + `engine_id=recall_first`（FL-D089）。遗留 `/api/batches` 建的批次 `engine_id` 为空 → 走遗留 ruleset-only 路径 → 报告 `guide groups 0 / targets 0`，**会误判成"引擎找不到条款"**。
  - 任务 `id` 与上传回执的 `batch_id` **不是同一个值**；文档/报告/产物端点用 `batch_id`。
  - ruleset v1 处于 `unreleased`（`auto_write_enabled: false`）只关门 ruleset 路径；recall-first 引擎走绑定指引快照，**不受该门限制**，实测正常交付（FL-D090）。不得为"制造交付"手改发布标志。
  - 引擎在真实模型下**非确定**：同一份合同不同批次可能得 17 条（complete）或 16/17 条（incomplete，如 `RECALL_EDIT_OVERLAP`）。incomplete 时产物是 `working_final`/`working_redline`，`final`/`redline` 会 404，属**正确行为**。
- **部署状态**：`bash tools/deploy/publish_workspace.sh` 已执行；`/opt/fundlex-recall-first` 与仓库**逐文件 sha256 一致**（html_view/selective/api/store/app.js/app.css 全部 SAME）；`fundlex-recall-api`/`fundlex-recall-worker` 均 active，`/api/capabilities` 200。
- **下一动作**：功能已按用户要求完整端到端交付，无待办阻塞。可选后续：① 若要求修订审查的**确定性交付**，需先解决引擎 `RECALL_EDIT_OVERLAP`（属引擎既有议题，非本功能）；② 合并到主分支/推送远程需用户明确要求（本轮**未 push**）。

## 当前断点（第 9 轮，2026-10-15，前端合并「处理进度/合同结果」）

- **本轮任务**：用户提出前端「处理进度」与「合同结果」两页几乎一样，要求合并。用户**明确选定**方案：**一张表 + 全部列常显**（明确否决"视图切换"方案）。
- **合并依据（代码证据）**：两页消费**同一接口** `GET /api/tasks/{id}/documents`（`fundlex/api.py:720`），共用 `loadDocuments()`、任务选择器循环、`showDetail`、分页；差异仅列/筛选/页头按钮。→ 同一实体，非两个功能。
- **已实施**（仅 3 个前端文件，**无后端/数据库/引擎改动**，单 commit 可 revert）：
  - `frontend/index.html`：`#view-progress` + `#view-results` → 单个 `#view-task`；侧边栏两项 → 一项「任务详情」(`data-nav="task"`)，总览页英雄区两按钮 → 一个；固定 7 列表头常显（合同文件/上传状态/资格/交付完整性/处理状态/业务提示/操作）；工具栏 7 个筛选控件（`doc-search`/`doc-upload-filter`/`doc-qualification-filter`/`doc-completeness-filter`/`doc-status-filter`/`doc-reason-filter`/`doc-sort`）；两组统计 `#overall-counts`+`#result-counts` 常显；页头运行态+交付态按钮并列。顺带删掉无人引用的死标记 `release-notice`。
  - `frontend/app.js`：`state` 的 `progressPage/resultPage/progressSize/resultSize/progressDocs/resultDocs` → 单一 `docPage/docSize/taskDocs`；`VIEW_TITLES`/`go()` 支持 `task`；`renderTask`/`deliveryCounts`/`updateDeliveryNote`/`selectTask`/`loadDocuments`/`refresh`/`seal`/`exportResults`/`resetWorkspace`/`data-detail`/分页/`changed`/事件绑定全部改到 `doc-*`；`renderTask` 里失效的 `selected-task-ruleset` 已移除。
  - `frontend/app.css`：`#result-scope-note`→`#doc-scope-note`、`#result-rows`→`#doc-rows`（行置灰规则随合并变为常显）。
- **关键坑（勿再错改）**：分页名**必须**用 `name='doc'`。`pagination()` 按 `name` 推导 `state[`${name}Page`]`，而 `taskPage/taskSize` 已被**任务列表**占用，若沿用会把两处分页串在一起。`data-detail` 统一 `doc:i` 并统一读 `state.taskDocs`。
- **顺带修复**：原 `emptyRow(cols)` 列数与真实表头不符（progress 传 5 / results 传 7 / reset 传 6、5）→ 统一 7，空态 `colspan=7`，列错位消除。
- **真实浏览器验证（已做，非静态检查）**：装了 Playwright + Chromium（`dnf install atk gtk3 …` 补系统库）驱动**真实页面 + 真实 API**。脚本 `/tmp/opencode/browser_accept.py`、`/tmp/opencode/browser_accept2.py`。结果：**0 页面/控制台报错**；`#view-task` 唯一，旧两页已无；导航只剩一个「任务详情」；表头 7 列全部可见；数据行 7 单元格；`data-detail="doc:0"`；空态 `colspan=7`；筛选真实下发（`upload_status=pending`）；分页 `data-page='doc'`；`#overall-counts`/`#result-counts` 正常填充；刷新后一致。另：`app.js` 过 modern JS 引擎语法校验；HTML 结构闭合 0 错；118 个 JS 引用 id 全部存在。
- **测试**：572 passed / 6 skipped / 1 failed；该 1 失败经 `git stash` 对照确认是**既有环境问题**（缺 `references/source/…文案勘误版.docx`），**与本改动无关**。
- **已登记**：`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` **FL-D086**（两页重复 + `emptyRow` 列数缺陷，含验证证据）。
- **已发布到线上（已完成）**：`bash tools/deploy/publish_workspace.sh` → `api/worker` 均 active，`/api/capabilities` 200。公网 `https://fundlex.club` 已复核（真实 Chromium）：`#view-task` 唯一、旧两页不存在、导航只剩一个「任务详情」、0 报错。脚本 `/tmp/opencode/live_check.py`。
- **git**：commit `3f4d8cf`（前端合并）已推送 origin（`341be2b..3f4d8cf`）。注：FL-D086 文档条目被并行 agent 的 `341be2b` 一并提交，内容完整。
- **下一步**：① 前端合并已完成并上线，如需可让用户在线上点一遍确认交互手感；② 回到第 8 轮主线：修 **FL-D060**（无条件 append 漏加 G01/G03/G16）→ 开发集再跑 1—2 轮 → 冻结 → 留出 8 例 → `docs/REAL_REVISION_EVALUATION_RESULTS.md`。

## 当前断点（第 8 轮，2026-10-15，接续请从此处读）

- **本轮已完成的非批次工作（第 8 轮）**：① 修正集中问题记录的 5 组**编号冲突**（FL-D077），并同步修正 `tools/evaluation/p6_score.py` 与断点/计划文档的引用（后出现的重复项改为 FL-D072/073/074/075/076，保留首次出现编号之一义）；② **新增交付包工具 `tools/evaluation/p6_package.py`**（把 P6 运行目录打成业务读者可读的「结果总览.md + 最终版（接受修订后）/ + 逐份修改说明/<合同>/{修改说明.md,修改明细.json,（修改痕迹版）.docx}」，结构对齐参考包 `FundLex-合同修改结果-本次抽查-20261013`），已用它生成 **`var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/`**（20 份合同，81 文件）；③ 复核交付包时发现并修复**真实缺陷 FL-D079**（变体模糊匹配 span 停在句中，留下“…（如有）。配。”碎片）→ 新增 `fuzzy_span_clause()` 句边界吸附，`variant_replace/variant_delete/审计复核`三处统一；④ 新增测试 `tests/test_p6_package.py`（3 项）与 `test_fuzzy_span_clause_snaps_to_sentence_boundary`；⑤ 全量测试 **566 passed / 1 expected（references/）/ 6 skipped**。
- **P6 第 1 轮（第 3 次重跑）已完成**：`p6-dev-round1-01` 20/20、604 调用、$0.5533；评分 `.venv/bin/python -X utf8 -m tools.evaluation.p6_score --run var/recall-first-evaluation/p6-dev-round1-01 --output /tmp/opencode/p6-round1-final.json` → 全量 347 目标/184 完成/0.5303；**开发集口径 236 目标/184 完成/0.7797**（基线 0.754、第 2 次 0.792）；integrated_complete 0/20；applicability_conflicts 19。产物 `var/recall-first-evaluation/p6-dev-round1-01/`。
- **P6 关键文件（仓库外）**：`/home/opencode/data/funds_word/`、`/home/opencode/data/MANIFEST.sha256`；仓库内 `var/recall-first-evaluation/p6/`（selection/labels/protocol/freeze）。
- **账本（仓库外，勿入库）**：应用调用记 `/var/lib/fundlex/model_budget.sqlite`（root 只读，opencode 读不到；数字取自各 `report.json` 的 `model` 段）。基线 581 调用/$0.5624；第 2 次 677/$0.5738。**agent 自用 0 次**。
- **禁止**：把**密钥/凭据**入库。发布只能用 `bash tools/deploy/publish_workspace.sh`。（**更新**：用户已授权自行判断 git 提交/推送；**推送统一用 `bash tools/deploy/push_with_token.sh`**，token 存仓库外 `/home/opencode/.github_token`（600），不打印/不入库。**合同资料政策更新（用户 2026-10-15）**：合同为公开资料，**可入库、可出服务器**（含 Langfuse Cloud）；「不入库/不出服务器」的旧底线**仅对凭据仍然有效**。）
- **本轮已推送**：`e37aa21`（交付包工具 + FL-D079）、`99509fb`（push 助手）、`dcc715e`（FL-D080）；远端 `origin/codex/fundlex-recall-first` 与本地一致（HEAD `dcc715e`）。
- **交付包已含根目录 `结果清单.csv`（FL-D081，用户要求）**：`tools/evaluation/p6_package.py` 复刻工作台「导出结果清单」的格式（BOM+CRLF、列 `序号,文件名,资格,处理状态,交付完整性,业务提示,原始原因码`、末列仅短机器码）；`结果总览.md` 保持不变。重出包：`var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/`（根目录 3 项 + 最终版 20 份 + 逐份说明 20 组）。
- **Langfuse 可观测性（FL-D081，已推送 `f5be16f`）**：接入 **Langfuse Cloud**（本机无 Docker/无 Postgres+ClickHouse+Redis+MinIO，自托管不可行）。代码：`fundlex/observability.py`（唯一收口，**无 key 纯 no-op**）、`fundlex/model.py` 的 `_trace_attempt`（每次调用一个 generation span）、`fundlex/jobs.py` 的 `_document_trace`（**一个合同一个 trace**，document_id 为确定性 seed）、`tools/evaluation/p6_langfuse_sync.py`（把 P6 verdict 作为 score 回写同一 trace）。开关：`FUNDLEX_LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST`（两个 key 都设才启用）+ `FUNDLEX_LANGFUSE_CAPTURE_TEXT`。已用本地 OTLP 桩验证真实发射（根 span 与 generation trace id 一致、带 usage/cost/version；score 带完整 metadata）；`tests/test_observability.py` 5 项通过；全量 **568 passed / 6 skipped**。详见 `docs/LANGFUSE_OBSERVABILITY.md`。**真实云端凭据已配置并验证**（FL-D083：`jp.cloud.langfuse.com`，`auth_check=True`，冒烟 trace `b1648f73…`）。
- **root 写权限（FL-D084，全部 agent 须知）**：用户已授予 `opencode` 本机 sudo `ALL`（`/etc/sudoers.d/fundlex-agent`）。`sudo -n` 可用；已用它备份并追加 `FUNDLEX_LANGFUSE_*` 到 `/etc/fundlex-recall.env`（备份 `…env.bak-langfuse`）。**边界**：仅 FundLex 部署/配置/服务/验证；凭据值不入库/文档/日志。**部署侧待办**：`/opt/fundlex-recall-first` 缺 `observability.py` 且 venv 未装 `langfuse` → 需 `sudo -n …/pip install langfuse` + `bash tools/deploy/publish_workspace.sh`（重启 api/worker）后生产 worker 才会发真实 trace。
- **合同资料政策更新（用户 2026-10-15）**：合同为公开资料，**可入库、可出服务器**；旧「不入库/不出服务器」约束**仅对凭据仍有效**（见 `AGENTS.md`）。
- **本地 JSONL trace 兜底（FL-D088，2026-10-16，已发布并验证）**：Langfuse 两区均丢 payload（FL-D085），用户指示退化到本地 JSONL。新增 `fundlex/trace_sink.py`（纯标准库；`FUNDLEX_TRACE_JSONL` 未设即 no-op；一个合同一 trace + 一次调用一 generation + 一条 score；活动文档 id 走 thread-local），接线于 `model.py`/`jobs.py`，配套分析器 `tools/evaluation/p6_trace_report.py`，单测 `tests/test_trace_sink.py`。生产落点 `/var/lib/fundlex/traces/model-calls.jsonl`（`/etc/fundlex-recall.env` 已加变量，备份 `.bak-tracesink`）。**真实 20 例已验证：1085 行、单条 25KB 含合同原文、19/20 trace 匹配、0 错误。**
- **评分器 append 误判已修（FL-D089，2026-10-16）**：`appendix_present()` 现折叠份额类别枚举（`A类、D类` ≡ `A类`）+ 模糊兜底逐字符步进。**开发集 0.7892 → 0.8161**（无引擎改动）。回归测试 `tests/test_p6_score_append.py`。
- **剩余主力缺陷（FL-D090，未修）**：开发集剩余 `not_executed` 11 例**全是 G01/G03/G16 append**（D07 真漏改——原件用「直销渠道」措辞致模型盘点判 `not_applicable`；D09/D13 属原件已含相近义务）。修法方向：`appendix` 规则增确定性适用性兜底 + 直销措辞归一化。
- **当前指标（2026-10-16，开发集 20 例 / 223 目标）**：**0.8161**，目标 0.95；整合完成 0/20，目标 0.9。`kept` 30 例（G17×8/G14×5/G11×4/G18×3/G15×3/G08×3/G13×2/G05×2）。
- **下一步（按序）**：① 修 FL-D090（append 适用性兜底）；② 开发集再跑 1 轮验证；③ 达标后冻结 → 跑留出 H01–H08；④ 出交付包 + `docs/REAL_REVISION_EVALUATION_RESULTS.md`；⑤ Langfuse 云端若报障有结论再回填 score 通道。
- **下一步（按序）**：①（可选）发布 FL-D079 修复后用 D01 等含 G22 变体的样本复跑，确认终稿无“……（如有）。配。”碎片；② 修 FL-D060（无条件 append 漏加 G01/G03/G16）后只在**开发集**再跑 1—2 轮（≤3 轮），直到 dev 达标（0.95 / 整合 0.9）并冻结；③ 冻结版跑 8 留出例（`--group holdout`）；④ 写 `docs/REAL_REVISION_EVALUATION_RESULTS.md`（用 `tools/evaluation/p6_package.py` 出交付包）；⑤ P7 浏览器端到端、断点续跑、双身份隔离、指引切换、MySQL 备份/恢复。

## 第 7 轮进度（服务器，2026-10-15）：用户 8 项 UX/修改问题 + P6 第 1 轮评分

任务计划文档：`docs/TASK_PLAN_UX_AND_APPEND_20261015.md`（该文档写于编号更正 FL-D077 之前，文中 FL-D068/069 指现在的前端互斥与 fragment 拼接两义，见本文顶部更正块）。

- **T2 引擎（问题 5，无标点拼接）已修复**：`_splice_fragment`（`fundlex/recall.py`，`fragment_replace` 路径）遗漏分隔符 → 已加 `append_separator`；`plan_composite_target` 同步加固。新增 2 回归测试。→ **FL-D068**
- **T1 后端并发核实（问题 1）**：后端本就支持多任务并行（`tasks.create` 无限制、`POST /api/tasks` 无守卫、worker 公平 claim）；互斥纯在**前端**。→ **FL-D069**
- **T3 前端 8 项 UX（问题 1–8）已实施**（`frontend/index.html|app.js|app.css`）：多任务并行、证据侧栏改「章节+改之前/改成了什么」、精简小字、结果页 ZIP 按钮置首、删顶部横幅+铃铛只收重要消息、总进度指标单行、导入 KPI 并入筛选栏。→ **FL-D071**。验证：`node --check` 通过、120 个 id 引用完整、`#2` 用真实报告核对 22 行可读无技术字段。**未做浏览器端点击验收。**
- **P6 第 1 轮评分（FL-D070）**：`p6-dev-round1-01` 20/20 完成，677 调用，$0.5738。**开发集 236 目标：基线 178（0.7542）→ 187（0.7924，+3.8pt）**；G15 +9、G05 +2、G17 −2；`applicability_conflicts` 29→13；**假完成仍 12**。评分产物 `/tmp/opencode/p6-round1-score.json`。**仍未达阈值（0.95/0.9）**。
- 测试：`.venv/bin/python -m pytest tests -q` → **561 passed / 1 expected（references/）/ 6 skipped**。
- **已提交并已推送（第 7 轮，11 个逻辑提交 `cc558ab..05fc90f`）**：工作树干净；`origin` 为私有仓库 `github.com/JokerNephew/FundLex`，分支 `codex/fundlex-recall-first`（新建 + upstream）。凭据为用户提供的 OAuth token（`gho_…`，经临时文件 + `GIT_ASKPASS` 使用，未入仓库/日志，用后即删；**用户应撤销该 token**）。仓库级代理 `http.proxy=http://127.0.0.1:9981`。详见 `docs/HANDOFF_ROUND7_UX_AND_GIT_20261015.md`。→ **FL-D078**（原 FL-D072，编号冲突后更正）。
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

## 本轮新增断点（2026-10-17，B 类全量排查 + 指引适配排查）

- **FL-D104**（已提交 `e780202`，未推送）：514 份全量 B 类（业务含义偏差）排查。报告 `/home/opencode/B_CLASS_REPORT_FINAL.md`，数据 `/tmp/opencode/b_gap_findings_clean.csv`（1638 行 / 509 份），分规则 CSV `/tmp/opencode/b_class_by_rule/*.csv`。**19 项口径待产品负责人裁决**，裁定前不得据以改动引擎/评分。
- **FL-D105**（已提交 `5fc3d70`，未推送）：合同语料 × 指引**结构性适配排查**（确定性、无模型）。报告 `/home/opencode/GUIDE_CORPUS_FIT_REPORT.md`，产物 `/tmp/opencode/{guide_fit_probe2,clause_material,verify_findings}.json`。核心：空格陷阱 386/514、真实类别超 A/C（E/F/Y/D/B/H）、删除型 old_text 大面积对不上（G15 1/514、G17 5/514）、已满足新机制 46/41 份、货币基金 8 份不兼容；**Q1–Q8 待裁决**。
- 两项均只登记"发现与待决"，未改动代码、未发布、未宣称达标。P6 开发集冻结/留出状态不受影响。

## FL-D106 代码改动断点（2026-10-17）

- **已发布并完成一轮真实批次验证**：发布哈希 `recall.py 1f898fe1…` / `recall_pipeline.py ccb2ff94…`，服务 13:59:47 重启；批次 `p6-dev-round9-01`（20/20 完成，$0.5561，无 abort）。
- **指标（同一评分器/标签集，347 目标）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；**round9 219/0.6311/kept9**。相对紧邻的 round8-03：completed **+8**、kept **−2**；相对 round7：kept **15→9**。明显改善：D04/D08/D17/D19 的 G17 删除型 kept→completed、D07 G16 not_executed→completed、D12 G14、D19 G08。
- **D09 崩溃为非本次引入**：82 次 sweep 中仅 1 次 `finish_reason=length`（输出 4000 上限截断）→ `MODEL_SCHEMA_INVALID`；sweep 工作量 84→79 反而下降。属既有输出截断脆弱点（FL-D107），待定处理。
- **未做**：未冻结版本、未跑留出 H01–H08、未写评测结果文档、未打包；未宣称达成 0.9。
- 详见集中问题记录 FL-D106、**FL-D107**。

## FL-D108 / FL-D109 断点（2026-10-17，sweep 输出截断 + 切窗与规则收敛）

- **当前生产状态（已发布并核对）**：`recall_pipeline.py db2ad9d1…` / `model.py 4d66f856…` 与仓库逐字节一致；服务于 **23:23:21** 重启，`/api/capabilities` 200。
- **FL-D108（已实施并生效）**：sweep 响应触到输出上限（`finish_reason=length`）时识别为 `MODEL_OUTPUT_TRUNCATED`，并**把该窗口按整段折半重扫**，而非重试同一超长请求；单段无法再拆则记诚实缺口。（根因实测：82 次 sweep 仅 1 次触顶，p50 输出仅 146 token，故不提高全局上限。）
- **FL-D109 第一步（已实施、已发布、已实测有效，为默认）**：sweep 规则**按窗口覆盖章节收敛**（含 mandatory 强制、不可达回退、空映射回退三道硬兜底），并对越界 finding 记 `SWEEP_RULE_OUT_OF_WINDOW`。round11：completed **225 / rate 0.6484**（round9 为 219 / 0.6311），`SWEEP_LOCATION_OUT_OF_SCOPE` **362→146**、`QUOTE_NOT_IN_WINDOW` 74→22；离线 requirements 文本量 **−87.7%**，每窗规则数 22 → mean 2.0–5.1。
- **FL-D109 第二步（已实施但默认关闭，opt-in）**：章节对齐切窗 + 未分配段落字符兜底，由 `FUNDLEX_SWEEP_SECTION_WINDOWS=1` 开启（当前未设置=关闭，部署已核对）。两次真实批次（round12 219 / round13 222）**无指标增益**且窗口数升至约 26（调用与成本上升），故不改默认。
- **指标台账（同评分器/同 347 标签）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；round9 219/0.6311/kept9；**round11 225/0.6484/kept11**；round12 219/0.6311/kept10；round13 222/0.6398/kept10。观测到显著运行间噪声（D09 跨轮 completed 7/7/0/7/4/4）。
- **全量测试**：`pytest tests` → **667 passed / 6 skipped / 1 failed**，唯一失败为既有无关项 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（缺 `references/source/*.docx`）。
- **未做**：未冻结版本、未跑留出 H01–H08、未写 `docs/REAL_REVISION_EVALUATION_RESULTS.md`、未打包；未宣称达成 0.9。
- 待推送提交：`157aba6`、`e88b64e`（代码）与 `ef76bce`、`e85e08c`（文档），以及更早的 `3946bdf`、`84402c3`、`bd82207`、`24f4d6b`、`b4039a1`、`a36e64f`、`767cbd0`、`5fc3d70`、`d5aae21`、`e780202`。

## FL-D110 / FL-D111 断点（2026-10-18，全链路复查 + 上游周限额阻塞）【当前断点】

- **本段为最新断点，接续请从此处开始。**
- **产品负责人指示**：先推送代码（已完成）。其后仍需：等上游限额重置后重跑 round14 验证 FL-D110；再收尾冻结/留出/打包。
- **FL-D110（已提交、已发布、单测通过；真实批次待补）**：增量重扫（sweep 第二轮）原来与初次重扫**口径不同**——用 `_artifact_chunks` 而非同一入口，且**未传** `requirements_by_chunk`/`scope_by_chunk`（即绕过 FL-D109 的按窗口规则收敛）。实测约 **1/3 的 case** 触发增量重扫（round11 7/20、round12 4/20、round13 4/20），D12 单案最多 3 轮。已新增唯一入口 `_sweep_chunks()` 并让增量重扫重新执行 `_window_rule_scope()`。另记录 3 项待决机制缺陷（`_target_identity` 60 字截断致旧审计结论可存活；复合删除证据只查锚点段；无 ledger 条目默认 `planned`）。
- **FL-D111（已提交、已发布、单测通过）**：`observability.trace_document()` 把被追踪主体的异常一并吞掉并再次 `yield`，导致 contextlib 抛 `RuntimeError("generator didn't stop after throw()")`——引擎的**可恢复停止**（`RecallPipelineStop`）被降级为普通 `RuntimeError`，worker 判不出停止 → `PROCESSING_FAILED`、`attempt=1`、**永久失败**，"暂停/续跑"设计完全失效。已重写为"只吞追踪自身错误、主体异常原样传播、span 关闭只记日志"。生产证据：worker 日志 `langfuse trace failed …` + `RecallPipelineStop: MODEL_CIRCUIT_OPEN`；DB 中 round14 全部 `attempt=1, PROCESSING_FAILED`。同时 `tools/evaluation/p6_run.py` 增加 `ENVIRONMENT_BLOCKED_CODES` 与"零调用零目标"兜底中止，避免再出现"`completed 20/20` 实际全空跑"的假批次。
- **外部阻塞（当前最重要）**：上游模型服务返回 **HTTP 429 `GoUsageLimitError`（weekly 限额）**，`retry-after: 70343s`（≈**19.5 小时**，自 2026-10-18 12:25 观测起算）。**在此之前无法运行任何真实模型批次**。可用独立账本探测命令模式：读 worker 的 `/proc/<pid>/environ` 构造 `ModelGateway.from_env()`，并把 `FUNDLEX_MODEL_LEDGER` 指向临时文件（勿污染生产 circuit）。
- **round14/14-02 作废**：`p6-dev-round14-01`（19/20 空跑）、`p6-dev-round14-02`（20/20 空跑）**不得用于评分**；空跑发生在 `facts` 阶段之前，与 FL-D110 无关。
- **已推送状态（2026-10-18 12:xx 核对）**：`origin/codex/fundlex-recall-first == HEAD`，ahead=0/behind=0；推送用 `bash tools/deploy/push_with_token.sh`（token 来自 `/home/opencode/.github_token`，不打印）。
- **全量测试**：`pytest tests` → **671 passed / 6 skipped / 1 failed**（唯一失败为既有无关项 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`，缺 `references/source/*.docx`）。
- **指标台账（同评分器/同 347 标签）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；round9 219/0.6311/kept9；**round11 225/0.6484/kept11（当前最好，FL-D109 第一步）**；round12 219/0.6311/kept10；round13 222/0.6398/kept10。round14/14-02 无效不计。
- **限额重置后的下一步（按序）**：(1) 直接重跑 `p6-dev-round14-03`（无需再发布，代码已发布）验证 FL-D110；(2) 与 round11/13 对比指标；(3) 若通过则继续冻结版本 → 跑留出 H01–H08 → 写 `docs/REAL_REVISION_EVALUATION_RESULTS.md` → `tools/evaluation/p6_package.py` 打包。
- **待决定/待决（未实施）**：FL-D110 记录的 3 项机制缺陷；FL-D105 Q1–Q8 与 FL-D104 1–19 仍待产品负责人裁定。
- **待推送提交**：无（已全部推送；此后新增提交需再次运行 `bash tools/deploy/push_with_token.sh`）。
- **安全提示**：2026-10-18 复查期间，读取服务环境时曾有一处命令未能完整脱敏，导致 `FUNDLEX_DATABASE_URL` 中的数据库口令出现在会话输出中。已停止再读该行；如需可评估轮换该口令。
