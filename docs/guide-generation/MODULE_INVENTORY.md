# 指引生成（guide generation）功能逻辑清单

> 编制：qa-gg-audit 专项线，2026-11-01。基线 commit 158475f（生产发布树 /opt/fundlex-recall-first 同代码）。
> 生产部署事实：API `fundlex-recall-api`（uvicorn×2，ProtectHome=true）；执行 `fundlex-guide-generation-worker`（`python -m fundlex.guide_generation.worker`，无 ProtectHome，EnvironmentFile=/etc/fundlex-recall.env）；DB 为 MySQL（FUNDLEX_DATABASE_URL, 127.0.0.1:3307/fundlex，gg_* 表）；数据根 FUNDLEX_DATA_DIR=/var/lib/fundlex；语料新口径 /var/lib/fundlex/corpus/funds_word（514 份公开合同 docx）。

## 总体链路（状态机）

```
上传法规(docx/pdf) ──POST /api/guide-generation/runs──> gg_runs(status=queued) + gg_jobs
worker claim(lease+fencing) ──> GuidePipeline.run() 逐 stage(输入哈希缓存可断点续跑):
  INGEST_REGULATION → EXTRACT_REQUIREMENTS → VERIFY_REQUIREMENTS → BUILD_CORPUS_SNAPSHOT
  → DISCOVERY_REQUIREMENT_RETRIEVAL(A路径检索) → DISCOVERY_CONTRACT_SWEEP(B/C路径扫描, marker)
  → ADJUDICATE_IMPACTS(marker) → BUILD_LOCAL_GUIDE_CANDIDATES(authoring)
  → MERGE_AND_GENERALIZE(marker) → GUIDE_QUALITY_REVIEW → GUIDE_REPAIR
  → SEMANTIC_COVERAGE → SUPPLEMENT_COVERAGE → FINALIZE_GUIDE → BUILD_EVIDENCE
  → (可选) run_engine_compatibility
终态: complete(门禁全绿) | complete_with_unresolved | failed | paused(人工resume) | retry_wait(瞬时故障,有界退避)
```
- 每 stage 包 `_stage()`：step 行(start/finish)+成功后 `router.raise_if_blocked()` 兜底基础设施故障。
- 候选不可变：FINALIZE 遇 published/approved/human_draft 版本记 late_rejected 证据拒绝覆盖（FL-D338 防护）。
- 模型调用全部走 model_router，记账 gg_model_calls；成本/次数仅观测（FL-D445），完成与否由质量/覆盖门禁决定。

## 逐模块清单

### api.py（365 行）— HTTP 路由
- 职责：runs CRUD/下载/候选 approve/publish/人工编辑 PATCH/engine 触发/resume/rebuild-evidence/corpus 概况。
- 失败路径：owner 越权→404；REGULATION_* / CONFIG_* 稳定错误码→4xx；ArtifactIntegrityError→409。
- 外部依赖：FastAPI、auth 依赖注入、GuideGenerationStore。
- 注意：approve/publish 接受 run.status∈{complete, complete_with_unresolved, completed}。

### service.py（207 行）— Web/外部渠道共用的建单服务
- 职责：`sanitize_public_config`（FL-D452 严格白名单，corpus_dir 仅接受别名 funds_word 且永不当路径用）、`_config` 注入服务端默认（corpus_limit 默认 FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT=1；corpus_dir 取 FUNDLEX_GUIDE_CORPUS_DIR，缺省回退 `<repo>/funds_word`）、`create_run`、`verified_artifact`（下载前重哈希校验）。
- 缺口/风险：回退路径在发布树不存在（见 FL-D821）；`_server_corpus_dir()` 仅测试引用，生产代码未直接调用（低）。

### worker.py（222 行）— 持久 worker
- 职责：gg_jobs 租约+fencing _claim/heartbeat；engine-only 分支；失败分类：ModelError 瞬时码(6 个)→retry_wait 指数退避(上限 FUNDLEX_GUIDE_TRANSIENT_ATTEMPTS=5)，非瞬时→paused 待 resume；其他异常→failed；Conflict(租约失效)→静默放弃。
- 外部依赖：GuideModelRouter.from_env、RunStore。

### pipeline.py（1245 行）— 可断点编排（上文状态机）
- 职责：stage 实现、payload 汇总、finalize 候选版本落库+DOCX 导出+证据包；`_finalize_cache_valid` 以 gate_sha256 复核缓存。
- 外部依赖：全部下游模块；git rev-parse（commit_sha）；uv.lock 哈希。
- 关键事实：`stage_residual` 已定义但**不在 STAGES/run() 中**（死阶段，residual_check="disabled"，见 FL-D824）；corpus_dir 回退 `<repo>/funds_word`（FL-D821）。

### corpus_catalog.py（181 行）— 语料发现/版本化/快照
- 职责：`scan_corpus_directory`（非递归 glob *.docx，排除 ~$ 与模板/说明类）、`parse_contract_filename`（保守，无日期则不猜 mtime）、`sync_corpus`（哈希去重复用、分段、版本链 resolved/unresolved、不可变 CorpusSnapshot）。
- 失败路径：单文件读/解析失败→errors 列表+parse_failed 版本（可区分）；**目录不存在/不可读→静默空列表**（FL-D821 修复点）。

### corpus_segmenter.py（343 行）— DOCX 保守分段
- 职责：zipfile→document.xml→lxml(禁实体)→RawBlock→标题层级→ClauseUnit(≤1400 字符切片)+上下文；尺寸上限 80MB/64MB；结构化 ContractParseError（NOT_DOCX/FILE_LIMIT/DOCX_INVALID/PART_MISSING/PART_LIMIT/XML_INVALID/EMPTY）。
- 已知限制：不读嵌套表格/textbox/页眉页脚/脚注（静默丢失）；TOC 启发式可能误吞正文段（审计 #7，med-high，登记）。

### vector.py（520 行）— 可选稠密检索派生物
- 职责：HttpEmbeddingProvider(FUNDLEX_EMBEDDING_*)；SQLiteVectorIndex(manifest 原子激活/rollback)/QdrantVectorIndex；DenseRetriever；`build_dense_retriever`（默认 vector_enabled=False）。
- 失败路径：构建/重建失败→payload.vector_index=unavailable+回退词法（静默降级但 payload 留痕）；查询异常在 discovery 层被吞成 note。
- 风险：rebuild 先短路后判空（#10 med）；SQLite 全表扫性能瓶颈（#11 med）。

### lexical.py（233 行）— 内存 BM25-ish 二字元检索
- 职责：tokenize→crc32 倒排+df→deterministic_query/query_from_intents→LexicalIndex.search(top_k/per_contract 配额)。
- 不会抛错；空语料与无命中同义返回 []（设计上由 CORPUS_EMPTY 兜前）。

### eligibility.py（157 行）— 纯门禁（fail-closed）
- 职责：11 项 checks（质量 run_status∈{pass,pass_with_findings}、无未豁免 open critical、覆盖=pass、要求全处置、独立复核身份合格等）→qualified+gate_sha256。
- 已知豁免：guide_reviewer 且 evidence_verified=False 的 critical 不阻塞（FL-D377 明示政策）；residual_check 已禁用（schema v2）；RUN_COMPLETE_STATUSES 为 dead constant（低，登记）。

### discovery.py（838 行）— A/B/C 三路径高召回发现+仲裁
- 职责：A=需求意图检索(词法+向量)过滤 impact；B=按章节约束批次合同扫描(ThreadPool4,失败整批重试一次→MODEL_RETRY_EXHAUSTED)；C=not_affected 合同用另一模型复扫(身份不合格则跳过)；uncertain/affected 批次逐需求 resolve；词法专属 impact 批量仲裁。
- 失败路径：模型/解析异常多处裸 except→uncertain/notes（fail-closed 方向，但与代码缺陷不可区分，登记）。
- **已确认逻辑缺陷**：_sweep_requirements 窗口填充死分支（related[8:] 永不入选，被轮换无关需求顶替）→ FL-D823 修复。

### coverage.py（652 行）— 三级覆盖+独立 LLM 审计
- 职责：requirement/impact/contract×requirement 看板→applicability 逐条问模型→16/40 批量独立审计覆写→topic 判定→run_status=pass|complete_with_unresolved。
- 失败路径：applicability/审计模型失败→major finding 不阻塞 pass（gap 窗口见 FL-D828 登记）；topic 判定失败→unresolved(critical,阻塞)。
- 已知：第一遍 counts 计算为 dead work（低，登记）。

### authoring.py（522 行）— 本地候选→族→指引条目
- 职责：4 impacts/批起草(22k 字符)→解析失败/遗漏 impact 的 fallback 族(uncertain 无文案,不丢 impact)→模型合并族(异常→确定性族)→families_to_guide_items；直销守卫注入；pipeline 补 definite impact 保守 regulation_verbatim 候选。
- 失败路径闭环良好（impact 不会消失）。

### requirements.py（638 行）— 要求原子化+独立挑战
- 职责：1500 字符/批抽取→硬校验(quote 必含/id 绑定)→覆盖检查补漏→独立 challenger 复核修正→处置兜底；任何路径不静默丢条文；空结果 ValueError(NO_REQUIREMENTS_EXTRACTED)。
- 失败路径：批次失败→critical finding 继续（eligibility 兜底）。

### quality.py（416 行）— 独立质量门
- 职责：确定性修复(_auto_fix_item)→确定性 findings→4 并发 reviewer 复核→run_status。
- 失败路径：reviewer 调用异常→review_execution critical（fail-closed）；未验证 evidence 的 reviewer critical 不计入阻塞（FL-D377 政策内 fail-open 面）。

### repair.py（132 行）— 一轮有界修复
- 职责：对 open critical 条目调 guide_repair→version+1,quality_status=not_run→_auto_fix+直销守卫重打；pipeline 侧 superseded 旧 finding 并对修复项重跑 quality（闭环成立）。
- **缺陷**：单条模型失败静默原样返回（不计 calls/不写 finding）→ FL-D826 修复。

### export.py（302 行）— DOCX 导出+证据包
- 职责：export_guide_docx(python-docx+sha256)；build_evidence_package；render_evidence_html。
- **缺陷**：HTML 读 `new_impact_count` 而持久化键为 `new_impacts` → 该列恒空 → FL-D825 修复。

### human.py（213 行）— 人工修订闭环（完整，非半成品）
- 职责：update_guide_item(事务内白名单清洗/逐字段 change/版本+重导出/生成 human_draft 候选不继承机器资格)；rebuild_evidence。
- 已知：事务内文件 IO 回滚留孤儿文件（低，登记）。

### model_router.py（476 行）— 角色路由+记账
- 职责：6 角色→gateway；from_env(FUNDLEX_GUIDE_<ROLE>_* 或 roles JSON)；identity()；每次调用写 ModelCallRecord gg_model_calls；`_block`+`raise_if_blocked`（基础设施故障上抛→worker pause/retry）。
- 缺口：非 ModelError 异常不记账不阻断（窄缝，登记）；熔断固定 sleep125 重试一次（低，政策笔记）。

### residual.py（347 行）— 残余影响挖掘（**当前死阶段**）
- 职责：sweep 批次选样→按批调 guide_residual_sweep→校验绑定→pattern 去重→新 impacts/conflict findings→clean 轮次饱和判定。
- **FL-D824**：pipeline.stage_residual 定义但 run() 不调用；finalize 明示 residual_check="disabled"。

### scope.py（66 行）— 指引章节范围
- 职责：guides/builtin_guide_v1.json→section_hint 集合；子串匹配判范围。JSON 缺失→静默回退 6 章默认（低，登记；发布树必须含该 JSON）。

### engine_compat.py（127 行）— 引擎兼容性独立报告
- 职责：解析候选 DOCX→逐条 classify expressible/ENGINE_CAPABILITY_GAP/GUIDE_COVERAGE_GAP；可选样本合同试跑；不改写指引、不进质量门。
- 已知：requirements 参数未使用；直销类恒 ENGINE_CAPABILITY_GAP 偏置（med，登记）。

### store.py（1370 行）— gg_* 持久层
- 职责：schema(gg_runs/gg_steps/gg_jobs/fencing/合同版本/条款/快照/需求/影响/候选/版本/findings/覆盖/applicability/residual/模型调用/artifact/人机版本)；claim+heartbeat+fencing 事务；candidate_transaction。
- 与 models.py 字段已核对一致（专用列+payload_json）。

### models.py / prompts.py / __init__.py
- models：数据类+canonical_json/sha256/stable_id/compact_for_match/quote_in_text。已知潜伏缺陷：PolicyRequirement to/from_dict payload 覆盖陈旧值（med-latent，当前无触发路径，登记）。
- prompts：15 任务版本常量+严格 JSON Schema(additionalProperties:false)；ENGINE_SCHEMA/ENGINE_INSTRUCTION 死代码（低，登记）。
- __init__：纯 re-export。

### benchmark.py / cli.py — 评测与命令行
- benchmark：gold 对比 recall/覆盖/FP/fidelity/3-gram Jaccard；结果写 gold 目录 results/。
- cli：sync-corpus/create-run/run/worker/benchmark。**缺陷**：corpus_dir 默认相对 'funds_word'（发布树 CWD 下错）、sync-corpus 空目录仍 return 0 → 并入 FL-D821 修复。

## 外部依赖汇总
| 依赖 | 消费方 | 生产口径 |
| --- | --- | --- |
| FUNDLEX_GUIDE_CORPUS_DIR | service/pipeline/worker/cli | env 文件 + unit 必须一致指向 /var/lib/fundlex/corpus/funds_word（FL-D822 修复 unit 内联覆盖） |
| FUNDLEX_DATABASE_URL (MySQL) / FUNDLEX_DATA_DIR | store | mysql@127.0.0.1:3307/fundlex；/var/lib/fundlex（ReadWritePaths 内） |
| LLM_* 与 FUNDLEX_GUIDE_<ROLE>_* | model_router | 真实模型，无预算门禁（FL-D445） |
| FUNDLEX_EMBEDDING_* / Qdrant | vector | 可选，默认关 |
| guides/builtin_guide_v1.json | scope | 发布树必须包含 |
| git/uv.lock | pipeline 证据 | 发布树 .git 可能缺失→回退 FUNDLEX_COMMIT_SHA |

## 指引版本 diff（「我的指引→版本对比」；运行时指引体系，非 guide_generation 候选）

> 专项补充（2026-11-01，应总指挥追加要求，供 FL-D891 判定后端缺口）。**版本差提醒**：该功能模块不在 worktree 基线 158475f 中（`git ls-tree` 无 guide_diff/guide_text_diff），为生产树 `/opt/fundlex-recall-first` 随后新增的代码；本节结论基于生产树源码逐行核对，与基线其余模块同行管理。

### diff 在哪算（接口/数据）
- **规则级 diff**：`GET /api/guides/{version_id}/diff?against={base_id}`（api.py:1175）→ `guide_store.diff_versions`（guide_store.py:817）→ `fundlex/guide_diff.py:diff_guide_documents`（guide-diff-v1）。输入是两侧版本的**已解析规则文档**（`guide_document()`：guide_versions.rules_json，内置版读冻结 `guides/builtin_guide_v1.json`）。**同步请求内计算，确定性、零模型调用、无缓存、无异步任务**。
- **原文 diff**：`GET /api/guides/{version_id}/text-diff?against={base_id}`（api.py:1186）→ `fundlex/guide_text_diff.py`（guide-text-diff-v1）。输入是两侧版本的**上传源 DOCX 字节**（`guide_source_path()` → 数据根下源文件），直接复用合同比对算法链 `compare.text_diff.compare_docx` + `render_compare_document/render_merged_document`，输出 left/right/merged 三段 HTML + 差异行 + coverage 摘要。同样**同步、确定性、零模型**。
- 前端（生产 app.js:1236-1280）：「版本对比」卡两个 tab（rules/text）+ 合并稿/并排切换，请求失败时统一兜底。

### 「差异暂未算出来，请稍后重试」属于哪种？——**报错兜底文案，不是未实现、也不是异步未就绪**
文案出自生产 app.js:1280 的 catch 兜底（`detail==='BUILTIN_SOURCE_UNAVAILABLE'` 时另显"内置指引无法原文比对"）。两个 diff 端点均请求内同步算出，**不存在"暂未算出来、稍后就绪"的异步形态**；该文案的实际触发路径：
1. **404 GUIDE_DIFF_UNAVAILABLE**（统一报错码，三种来源不区分）：① 任一版本不存在/不属当前 owner；② 规则 diff 时任一版本**尚未解析出规则**（rules_json 空→`guide_document` KeyError，即"解析中/解析失败"状态被折叠成"暂未算出来"）；③ 原文 diff 时 `TextDiffUnavailable(GUIDE_SOURCE_UNAVAILABLE)`（源文件丢失/非 docx，非内置情形）。
2. **404 BUILTIN_SOURCE_UNAVAILABLE**：原文 diff 任一侧为内置指引（无上传原文），前端有专属文案，**不落到该兜底**。
3. **422 INVALID_REQUEST**（against 缺失；前端恒带值，理论路径）。
4. **网络/其他异常**：落到兜底 + errorNotice。
结论：用户看到该文案时几乎总是 404 类「不可用/未就绪」语义，但后端**已能区分**各成因（错误码已在 API 层稳定），只是前端未按码细分，且"稍后重试"对「版本未解析出规则」有效、对「源缺失/built-in」无效。规则 tab 前端**不预检**版本 status（不像「规则开关」页过滤 GUIDE_RULES_READY），因此解析中版本必然触发兜底。

### 规则级 diff 支持度与缺口
- 已实现：rule_id 键控的增/删/改+字段级变更（白名单 6 字段：title/requirement/operations/old_text_variants/slot_tokens/class_substitution/references）；groups 结构增删与顺序变化；meta 四字段（parser/schema_version/source_sha256/prompt_versions）；validation 摘要计数两边对照；summary 含 identical 判定；owner 可见性逐侧 404（不泄露存在性）。
- 缺口：① **字段白名单外变化不可见**——rule 中 `section_hint` 等字段 变化不产生 changed 记录（前端 guideDiffFieldLabel 已备 section_hint 映射，说明展示面预留、算法未覆盖）；② rule_id 重编即删+增（无移动/改名识别）；③ 不过滤版本状态，未解析版本→404 兜底而非「该版本还在解析中」；④ 无缓存（大规则集重复比较每次重算，成本低可接受）。

### 原文 diff 支持度与缺口
- 已实现：两个自定义版 DOCX 的全文确定性 diff（modify/insert/delete + 覆盖率），合并稿/并排 HTML 与合同比对页同款渲染；内置指引显式拒绝为 BUILTIN_SOURCE_UNAVAILABLE；源损坏归 422 GUIDE_TEXT_DIFF_UNREADABLE。
- 缺口：① 自定义版本源文件缺失/非 docx→GUIDE_SOURCE_UNAVAILABLE 前端无专属文案（落兜底）；② 源文件可用性依赖数据根文件留存（未见生命周期/清理保护约定）；③ 不支持"内置 JSON 规则反渲染为文本"比对形态（设计上拒绝，属明示边界）。

**后端缺口总判定（供 FL-D891）**：diff 计算能力**完整存在且确定性**；后端真正缺口只有「404 的三种成因共用一个 GUIDE_DIFF_UNAVAILABLE 兜底码/文案」与「规则 diff 字段白名单不含 section_hint」。前端只需要按已有错误码细分文案（含 status=parsing 的专属提示），**不需要后端新增异步 diff 计算**。


- 完成判定 fail-closed：complete 需 11 项 checks 全绿；其余 complete_with_unresolved。
- 基础设施故障：router 阻断→阶段失败→worker retry_wait/paused，不会错误 complete。
- 主要 fail-open 面（政策内/已登记）：reviewer 未验证 evidence 的 critical 豁免（FL-D377）、coverage applicability/审计模型失败仅 major（FL-D828）、向量静默降级（payload 留痕）、scope 默认章回退（静默）。
