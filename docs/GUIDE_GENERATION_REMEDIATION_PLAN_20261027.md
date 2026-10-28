# 法规指引生成修复与验证计划（2026-10-27）

## 目标

让真实法规与合同输入在严格证据门禁下稳定产生可审查候选。`candidate_ready` 只能在要求、影响、质量、覆盖和 Residual 全部闭合，且独立模型复核身份合格后产生；离线 fake/replay 结果只用于开发验证。

## 已确认根因

1. 合同影响扫描把全部法规要求放进每个合同批次，模型容易为一个 finding 绑定超过 schema 上限的要求 ID；当前批次按字符限制，但没有按输出容量限制。
2. 质量复核 schema 对证据字段的版本约束不完整，真实模型返回第二条证据时整批被拒绝。
3. Residual 的模式键包含不稳定的模型描述和整段证据文本；同一合同位置在不同轮次换一种描述会被算成新模式，且批次状态未随覆盖结果刷新，造成不收敛的重复扫描。
4. 法规生成阶段默认 4 个并行 worker，但共享账本并发上限为 1；smoke13 的 702 次逻辑调用中有 119 次 `MODEL_CONCURRENCY_LIMIT`，导致批次被丢弃、裁决被跳过、质量复核被记为失败（FL-D372）。

## 实施阶段与出口

### P1：契约与批次边界

- 影响扫描按可关联要求裁剪上下文，并把单个 finding 的要求 ID 上限降到更保守的值；提示明确要求不要枚举无关要求。
- 保留严格 schema；对已确认有业务意义的第二证据字段显式建模并校验，不放宽为任意额外字段。
- 增加真实模型输出形状的回归夹具：超长 requirement_ids、`evidence_quote_2`、截断和未知字段均有明确结果。

出口：离线回归能证明批次不会主动制造超限上下文，合法双证据可保存，未知字段仍 fail closed。

当前状态：**已实施并通过离线回归**。`path_b_max_requirements=12` 贯穿 Pipeline→DiscoveryConfig；每个条款批次只携带与该批条款有证据关联的至多 12 条要求，schema `requirement_ids.maxItems=12`；空/超限/越界绑定整批 `INVALID_REQUIREMENT_BINDINGS` fail closed 并一次有界重试；多要求 finding 按每个要求生成独立 Impact；`evidence_quote_2` 显式建模，任一引文精确匹配即可验证并记录匹配索引（FL-D377）。新增回归覆盖未知/超限绑定、多要求拆分、双证据、部分匹配与未知字段。真实效果待 P4。

### P2：Residual 收敛

- 模式键使用合同版本、物理 clause 地址、规范化 requirement IDs 和稳定语义字段；不使用模型自由描述作为唯一身份。
- 同一位置已在本轮发现后，后续轮次只能作为复核，不重复新增 impact；保留不同 requirement 或不同物理位置的独立缺口。
- 保留两轮 clean 才能 saturated；模型失败、未绑定证据和覆盖不确定继续阻断。

出口：夹具中同一位置换描述会收敛，不同位置/要求不会被错误合并；Residual 不能靠重复扫描伪造饱和。

当前状态：**已实施并通过离线回归**。模式键为“合同版本 + 物理 clause 地址 + 规范化 requirement IDs”；已有 Impact 物理模式预置为 seen；模型错误/无效绑定/其他审计 finding 记为 `blocked` 并清零 clean streak。新增回归证明同一位置换描述两轮 clean、saturated=true，且不新增 Impact。真实收敛效果待 P4。

### P1b：并发与账本一致性（FL-D372）

- `GuideModelRouter` 按共享预算 `concurrency` 加进程内 `BoundedSemaphore`，阶段 worker 在路由层排队而不是等待预算槽位后失败。
- 离线 3 线程用例断言最大并发为 1、无调用失败、调用记录完整。

出口：真实运行中 `MODEL_CONCURRENCY_LIMIT` 逻辑失败显著下降；跨进程竞争若仍存在需另行登记。

当前状态：**已验证**。smoke14 的 614 次逻辑调用 0 error，`MODEL_CONCURRENCY_LIMIT` 从 119 次降为 0；剩余为 attempt 级 1 条 schema + 3 条 retry exhausted，未形成逻辑失败。

### P2b：最终资格门禁聚合（FL-D374）

- `stage_finalize()` 纳入 `quality.run_status != "fail"`，避免要求复核失败或覆盖 critical 存在时仍产生 `candidate_ready`。
- 新增 critical quality finding + 其余门禁闭合的流水线回归。

出口：质量门禁为 fail 时，最终必须为 `complete_with_unresolved / candidate_with_findings`。

当前状态：**已实施并通过离线回归**。`tests/test_guide_generation_pipeline.py` **6 passed**。smoke14 在修复前启动，其结果需按新口径重算。

### P2c：要求复核字段契约（FL-D375）

- 保留 `article_assessment.reason` 必填，补充提示词明确每个对象（含 covered）都必须提供 reason，prompt 版本提升到 `guide_req_review_v5`。
- smoke14 的 v4 失败作为基线；v5 需在新账本真实复测。

### P3：局部与完整离线验证

- 运行法规生成定向测试、完整 Python 测试、编译和 diff check。
- 检查 pipeline 的 `complete` 仍由真实门禁决定，不能因修复 schema 或 dedup 降低质量/覆盖要求。

出口：代码回归通过；真实 smoke 尚不自动宣称通过。

当前状态：法规生成六套件 **67 passed**；`compileall` 与 `git diff --check` 通过。完整 `PYTHONPATH=. pytest -q` 首轮 **1688 passed / 57 skipped / 1 failed**（G06 探针，FL-D373）；修复 G06 后 **1698 passed / 0 failed**；纳入 FL-D374/376/377 的最新冻结代码最终为 **1701 passed / 57 skipped / 0 failed**（479.58s）。定向与全量回归通过，但真实资格仍待 smoke14/15。

### P4：全新账本真实复测

- 磁盘、模型配置和预算满足后，使用新运行目录、新账本和冻结 manifest 重跑 smoke。
- 核对 schema failures、quality、coverage、Residual、模型身份和费用；只在全部门禁通过后进入 Blind Benchmark。

当前状态：**smoke14 与 smoke17 均已完成，均未达资格**。smoke14（`390677df707040d68839708c4f9e38c2`）614 次逻辑调用 0 error，76 requirements/843 impacts/90 items/545 findings，gaps 0、unresolved 7、critical_quality 0，但 quality fail（31 semantic_coverage 等）、latest uncertain 88、Residual 24/19/5 未饱和，费用 $0.479236。smoke17（`fd1084ed48284cc5998ffd270a936ab5`，含 FL-D379/380）766 次逻辑调用 0 error、无中止；100 requirements/1094 impacts/100 items/679 findings，gaps 0、unresolved 10、latest uncertain 115、critical_quality 9、quality fail，critical 合计 106（semantic_coverage 78），Residual 56/29/22 未饱和，费用 $0.576609。smoke15/smoke16 为中止的非资格尝试（$0.0533/$0.2347），目录与账本保留。smoke9–13 与历史账本保持只读。独立模型复核仍为同一模型，即使其余门禁通过也不能宣称资格闭合。

### P2d：覆盖审计可见性（FL-D379）

- 要求覆盖审计按 16 条要求分批，每批显示绑定指引明细 + 全量 `[ALL_GUIDE_ITEM_INDEX]`；只接受本批 requirement_ids 的结果/主题；`COVERAGE_VERSION=guide_coverage_audit_v3`。
- 背景：smoke14 的 90 个 GuideItem 只有 59 个可见，31 个不可见条目被误报为 missing topics，恰好对应 31 个 `semantic_coverage` critical。

当前状态：**已实施并通过离线回归**。新增 40 requirements/40 items 用例断言 3 批、全部 ID 可见、每个上下文 ≤ 24000；法规套件 **20 + 49 passed**。smoke15 在修复前启动，已中止并登记为非资格尝试（31 calls / $0.0533）；smoke16 将验证该修复。

### P2e：local candidate 合并完整性（FL-D380）

- `stage_authoring()` 把“needs_modification=yes 但 new_text 为空”的 local 降级为 `uncertain`，对应 Impact 保持 unresolved，由覆盖门禁阻断；不伪造文案、不放宽 merge marker。
- 新增流水线用例覆盖 yes/empty，断言不再中止且最终仍非候选就绪。

当前状态：**已实施并通过离线回归**。`tests/test_guide_generation_pipeline.py` **8 passed**；smoke16 因该缺陷中止（388 requests / $0.2347，非资格尝试），smoke17 待验证。

### P5：覆盖缺口回写闭环（计划中，尚未实施）

- smoke14 的 31 个 `semantic_coverage` critical 中相当一部分由 FL-D379 的上下文截断造成（90 个 GuideItem 仅 59 个可见）；修复 P2d 后仍需用 smoke16 判断剩余哪些是真实法规主题缺口。当前覆盖审计只把真实缺口记为 finding，没有回写到要求抽取或补写候选。
- 计划：覆盖审计返回的 `missing_topics` 经严格证据校验后绑定到法规 block/quote，生成补充要求（`discovery_pass=B`、`adjudication_status=supplemented_by_coverage`），再经锚点→authoring→quality→coverage 复审；有界轮次，未闭合主题继续阻断。
- 出口：missing topics 能进入候选并复审闭合；不得用放宽审计、删除 critical 或增加无限轮次冒充覆盖。实施前需新增 schema、store 字段和回归，当前 smoke15 不包含 P5。

## 第二阶段（smoke17 后，2026-10-27）

### P6：Residual 全量指引可见性（已实施）

- 问题：Residual 上下文只截取 6000 字符指引摘要（约 20/100 条），已覆盖模式被反复当作新影响，导致 56/29/22 不收敛。
- 处理：`[ALL_GUIDE_ITEM_INDEX]` 全量紧凑索引 + 本批相关指引明细；`RESIDUAL_VERSION=guide_residual_sweep_v2`。
- 验证：40 条指引/40 条要求用例断言全部 ID 可见、上下文 ≤ 32000；`test_guide_generation.py` **22 passed**（含新增 topic judge 用例）。真实收敛待 smoke18。

### P7：有界多轮质量修复（已实施）

- 问题：smoke17 仍有 9 个文本 critical；单轮 repair + 复审后未再修复。
- 处理：`repair_rounds=2`，每轮只修复新一轮 open critical，复审后仍有 critical 才进入下一轮；不降低 critical 标准。
- 验证：新增“首轮 critical→修复→复审通过”用例；`tests/test_guide_generation_pipeline.py` **10 passed**。真实效果待 smoke18。

### P5：覆盖缺口判定与补写（已实施）

- 问题：smoke17 报 78 个 `semantic_coverage` critical；需要区分“已有指引覆盖但审计未识别”与真实缺口。
- 处理：覆盖审计返回结构化 missing topics；先做主题级覆盖判定（严格 schema，绑定已有 GuideItem），仅对 `not_covered/uncertain` 保留 critical；真实缺口经严格证据绑定生成补充要求/锚点影响，进入 authoring→quality→coverage 复审，有界轮次。
- 出口：假缺口不进入 critical；真实缺口能进入候选并复审闭合；不得删除 critical 或放宽审计。
- 当前状态：**已实施并通过离线回归**。`CoverageResult.missing_topics` 结构化；`guide_topic_coverage` 只接受真实候选 GuideItem；未覆盖主题进入 `stage_supplement()`，有界 2 轮；复审计前 supersede 旧 coverage findings；authoring 的 impact 上下文携带 `impact_reason`，补写主题描述能传给作者模型；`guide_topic_coverage` 已注册到 ModelGateway。法规套件 **76 passed**（24 guide + 10 pipeline），全量回归运行中。smoke18 预算预登记为 1800 calls / $24 软上限（账本 2000 / $26），待验证。

### P8：独立复核模型资格（计划中）

- 当前所有角色为 `OpenCodeGo/deepseek-v4.1-flash`，`independent_model_review_status=independent_model_review_not_qualified`。
- 需在可用模型目录中选择与 author 不同的模型，配置 `FUNDLEX_GUIDE_GUIDE_REVIEWER_*`（或 roles 文件），记录身份哈希并完成真实复核；未合格前即使其他门禁通过也不能关闭资格。
- 当前状态：**FL-D382 已解决**。补上 FundLex 的 `x-opencode-session`/User-Agent 后 `glm-5.3-flash` 返回 200；真实 quality review schema 探测通过，`independent_model_review_status=qualified`，单次约 $0.003。smoke23 已配置 `FUNDLEX_GUIDE_GUIDE_REVIEWER_MODEL=glm-5.3-flash`，待完整验证。

### P10：uncertain 扫描批次逐要求裁决（已实施）

- 问题：任一 uncertain 批次使该合同所有无影响要求变成 latest uncertain（smoke17 115 个）。
- 处理：`resolve_uncertain_batches()` + `guide_batch_resolve` 严格 schema；仅全窗口 not_affected 才关闭批次；affected 必须 clause_ids + 可回查 quote；遗漏/不确定保持 open。
- 验证：三分支用例通过；`tests/test_guide_generation.py` **25 passed**。smoke18 在 P10 前启动已中止（$0.0238），smoke19 待验证。

### P9：smoke19/20 真实验证

- smoke18 在 P10 前启动已中止，不作为资格尝试。
- smoke19：run `3b4543d0ecda4feeaff169d30b894716`，latest uncertain **0**、unresolved **2**、critical_quality **1**、Residual **8/3/5**、费用 $0.641711；仍 `candidate_with_findings`。
- smoke20：run `85a131677d2c4992b4194acc4090509f`，latest uncertain 41（旧 model_error evidence）、unresolved 4、critical_quality 1、Residual 5/2/5、$0.688562；仍 `candidate_with_findings`。
- FL-D389/390：移除重试成功后的 stale model_error evidence；覆盖按批次窗口+resolver 逐要求结果计算；法规测试 28 passed。
- smoke21：run `37a22d0df6684cbbaf543ea158a7e985`，latest uncertain 101（窗口缺口）、unresolved 10、critical_quality 6、Residual 6/3/2、$0.80198；仍 `candidate_with_findings`。
- FL-D391/392：轮转要求窗口 + resolver 对 affected/uncertain 全批次逐要求裁决；施行/废止条款 out_of_contract_scope；法规测试 29 passed。
- smoke22：run `3ce81c396a8443728e84b9f2a121e76e`，撞账本上限，非资格证据。
- smoke23：run `9f7872b1fd1041d499c46c30b4123a7c`，独立 reviewer glm qualified、critical_quality 0，但 latest uncertain 58、Residual 10/4/1、glm 47 次截断；已修轮转游标/简洁输出/topic 等价判定。
- smoke24：run `520a39742a4c47af8c1c15da65490d96`，quality pass/independent qualified，但 latest uncertain 44、Residual circuit blocked；已登记 FL-D396。
- FL-D397 按合同 coverage tail + FL-D398 circuit 等待重试已实施；全量回归 **1848 passed / 0 failed**。
- smoke25：run `462f25deebf1452f87ca21fb7201047d`，path_b_max_calls=150、Residual 5 轮，待最终结果。

- 新目录/新账本，冻结 P5–P8 代码，核对 quality critical、coverage unresolved/latest uncertain、Residual 饱和、模型身份、费用。
- 只有质量、覆盖、Residual、独立身份全部通过，才可进入 Blind Benchmark。

## 验收口径

- 任何模型 schema 失败保留结构化错误并 fail closed。
- 质量、覆盖、Residual 任一未通过，运行状态保持 `complete_with_unresolved / candidate_with_findings`。
- 本计划不修改历史 smoke9–13 结果、不改写历史账本、不把离线测试冒称真实资格证据。
