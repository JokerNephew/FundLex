# 细节问题与处理记录 · 附录（qa-gg-audit 指引生成补完开发+充分测试专项线）

> **测试验证总账（2026-11-01，worktree qa-gg-audit，树内 venv python 3.11.13，PYTHONPATH=$PWD 锁树内代码）**：
> - 新增 `tests/test_guide_generation_hardening.py` **15 项全部通过**，覆盖 FL-D821×9、FL-D823×1、FL-D825×1、FL-D826×2、FL-D900×2。
> - 既有 gg 套件回归（test_guide_generation/pipeline/api/vector/guide/store/remediation_config/eligibility/worker_engine/transport_pause/mysql_schema，11 文件）**134 项全部通过**（76.5s，1 个 starlette deprecation warning）。
> - 全部修改文件 py_compile 通过；`import fundlex` 解析路径实测指向本 worktree（FL-D593 口径）。
> - **真实 E2E 已完成（2026-11-01）**：run 06fc7cd96c83443c96e7804cc1df91a0，真实模型、systemd-run ProtectHome=true、语料 /var/lib/fundlex/corpus/funds_word、隔离 sqlite/账本；15/15 stage completed，终态 complete_with_unresolved（门禁 fail-closed 合格），808 次调用全量记账，4 件 artifact 哈希一致；负向冒烟 exit 2/0 符合 FL-D821 语义。详见 AUDIT_REPORT 第 7 节；本线代码改动未发布（发布执行与守门属主线）。

> 本附录为 qa-gg-audit 专项线（worktree `/home/opencode/.local/share/opencode/worktree/29a9a9/qa-gg-audit`，基线 158475f）在工作期间的登记草稿，编号段 FL-D820~829。合并时由主线统一并入 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`，不重建编号、不删除历史结论。
> 格式与集中记录一致：发现日期 / 问题与影响 / 证据 / 处理方法 / 状态与验证 / 下一步 / 变更记录。
> FL-D820（worker 语料路径沙箱根因与迁移）归主线登记，本附录不重复；本线编号自 FL-D821 起。

## FL-D821 语料目录缺失/不可读失败语义含混，CLI 空语料仍报成功（2026-11-01）

- 发现日期：2026-11-01，qa-gg-audit 逐模块审计 corpus_catalog/pipeline/cli/service 时发现。
- 问题与影响：`scan_corpus_directory` 对不存在/不可读目录静默返回 `[]`（`is_dir()` 为 False 直接返回），缺失、无权限、真空目录三种情况统一汇入空快照；pipeline 只能在其后抛 `CORPUS_EMPTY`，运维无法区分「配置缺失」（部署形态问题）与「语料真的为空」。发布树 `/opt/fundlex-recall-first/funds_word` 不存在，一旦 `FUNDLEX_GUIDE_CORPUS_DIR` 未设置/被覆盖，回退路径即落入此含混失败。CLI `sync-corpus` 对空快照仍 `return 0`；`create-run` 的 corpus_dir 默认是相对路径 `funds_word`（随 CWD 漂移，旁路 `PipelineConfig` 的仓库根绝对回退）。
- 证据：`fundlex/guide_generation/corpus_catalog.py` 原 67-76 行；`cli.py` 原 27-31/45/112 行；生产 run a552520cf648451c93ed82d954bdfe19 实际 error_code=`[Errno 13] Permission denied: '/home/opencode/data/funds_word'`（MySQL gg_runs/gg_steps，BUILD_CORPUS_SNAPSHOT 阶段），证明不可读目录的失败以裸 OSError 形式冒泡、随 Python 版本与权限形态不稳定。
- 处理方法：新增 `CorpusConfigError`（稳定 code），`sync_corpus` 前 `_validated_corpus_root` 用 `os.listdir` 精确区分 `CORPUS_DIR_MISSING`（不存在/非目录/未配置）与 `CORPUS_DIR_UNREADABLE`（无权限）；glob 扫描异常同归为 UNREADABLE；`SyncResult.eligible_files` 记录 limit 截断前 eligible 文件数并写入 run payload `corpus_sync`（含 corpus_limit）。CLI：sync-corpus 配置错误 stderr+exit 2，空快照 stderr 警告+exit 3；CLI 全部 corpus 默认改为「env 或仓库根绝对路径」，删除相对 `funds_word` 默认。
- 状态与验证：**代码已实施（本 worktree），新增单测 9 项（tests/test_guide_generation_hardening.py FL-D821 段）：缺失/空串/文件路径→MISSING、chmod 0→UNREADABLE、空目录空快照不报错、limit 截断 eligible_files=2、pipeline stage 传播、CLI 2/3/0 退出码、默认绝对路径**。pytest 已验证（见总账）；发布形态负向冒烟已验证（systemd-run ProtectHome=true：不存在目录 exit 2=CORPUS_DIR_MISSING、合法目录 exit 0）；真实 E2E 中 corpus_sync 落库形态实证（eligible_files=514/limit=2/errors=0）。尚未发布到生产树（发布归属主线守门，见报告建议）。
- 下一步：主线合并后按发布守门（PILOT run 冒烟）发布并验证生产 run 的 error_code 变为稳定分类码。
- 变更记录：2026-11-01 新增。

## FL-D822 生产 guide-generation worker unit 内联 Environment 覆盖环境文件，语料路径修复未生效（2026-11-01）

- 发现日期：2026-11-01，本线「服务单元×路径引用交叉核对」时发现。
- 问题与影响：主线 FL-D820 已将 `/etc/fundlex-recall.env` 的 `FUNDLEX_GUIDE_CORPUS_DIR` 迁到 `/var/lib/fundlex/corpus/funds_word`，但 `/etc/systemd/system/fundlex-guide-generation-worker.service` 第 13 行留有内联 `Environment=FUNDLEX_GUIDE_CORPUS_DIR=/home/opencode/data/funds_word`——systemd 中同名变量**内联 Environment 优先于 EnvironmentFile**，worker 实际仍用旧 /home 路径，修复未闭环；仅靠 /home ACL 事后放行才未复发。另发现两个主线 systemd-run 复现遗留的 failed transient unit（run-u399197、run-u399217）未清理。
- 证据：`systemctl cat fundlex-guide-generation-worker`；`systemctl show -p Environment` 实测值；`stat / home/opencode/data` ACL `user:fundlex:--x`（仅穿越，脆弱）。
- 处理方法：备份 unit（`.bak-fl-d822-20261101`）后将内联值改为 `/var/lib/fundlex/corpus/funds_word`，`daemon-reload`+restart，`systemctl show -p Environment` 复核为 `/var/lib/fundlex/corpus/funds_word`；`reset-failed` 清理两个遗留 unit。其余 8 个 fundlex 单元交叉核对均 ProtectHome=true+ReadWritePaths=/var/lib/fundlex（test 线独立目录），无其他 /home 引用。
- 状态与验证：**已修复并验证（2026-11-01）**：service active，固化环境指向新语料路径。遗留建议（未实施，归属主线/运维）：给该 unit 补与其他单元一致的沙箱（ProtectHome=true+ReadWritePaths），需先全量回归 worker 所需写路径；为免再发「unit 内联覆盖环境文件」类错误，建议发布守门加「unit 内联关键路径变量 vs 环境文件一致性」检查。
- 下一步：随 FL-D821 发布后做一次默认入口真实 run，验证 worker 全程不再触碰 /home。
- 变更记录：2026-11-01 新增并当日修复验证。

## FL-D823 discovery 合同扫描窗口填充死分支：相关需求第 9 名以后永远被轮换需求顶替（2026-11-01）

- 发现日期：2026-11-01，逐模块审计 discovery.py 合同扫描窗口构建逻辑时发现。
- 问题与影响：`path_b_contract_sweep` 组窗口时先取批次相关需求前 8，再应把剩余相关需求（第 9 名起）补进窗口空位，最后才用轮换无关需求兜底「每合同每需求都被扫到」。但补位循环条件写成 `item.requirement_id not in related_ids`，而 `related_ids` 已含全部 related——恒 False，**相关需求第 9~12 永不入窗口**，空位全被轮换需求填充：该批次最相关的需求反而没被扫，且 batch 证据 `requirement_ids` 与真实扫描意图不符（影响覆盖判定的语义准确性）。
- 证据：`fundlex/guide_generation/discovery.py` 原 479-495 行；审计推演+测试复现（12 个全部相关需求、窗口 12：修复前仅前 8 出现在扫描上下文）。
- 处理方法：调整顺序——先直接追加 `related[8:]` 至窗口上限，再以轮换需求补剩余空位；去重判据改为对窗口现成员判重。
- 状态与验证：**代码已实施，新增单测 `test_sweep_window_keeps_related_tail_before_rotating`（12/12 相关需求全出现在扫描上下文）**。pytest 已验证（见下）。该修复改变扫描批次组成，属召回方向修正；对生产既有 run 无回填义务（run 快照不可变）。
- 下一步：纳入完整回归与真实 E2E 观察 sweep batch 证据 requirement_ids。
- 变更记录：2026-11-01 新增。

## FL-D824 residual（残余挖掘）整阶段为死代码，三个配置字段是参数黑洞（2026-11-01）

- 发现日期：2026-11-01，审计 pipeline/run() 与 residual.py 接线关系时发现。
- 问题与影响：`GuidePipeline.stage_residual` 已定义但既不在 `STAGES` 也不被 `run()` 调用，全库无其他调用方；`residual.py`（347 行）及 `max_residual_rounds`/`required_clean_rounds`/`residual_max_calls_per_round` 三个 PipelineConfig 字段（还暴露在 Web 公开配置白名单）因此完全不生效，CLI `--no-residual` 同理踏空。finalize 明示 `residual_check="disabled"`，说明当前为有意停用，但代码形态是「半成品悬挂」而非「显式移除」，易误导读配置的人。另确认 residual 若复启存在持续性基础设施失败下的无限循环风险（无退出保护，每轮向 gg_residual/findings 追加记录）。
- 证据：`grep -rn stage_residual` 仅定义点与 import；`pipeline.py:824-907` vs `run():1074-1151`；`finalize_payload["residual_check"]="disabled"`（pipeline.py:970）。
- 处理方法：本线按「显式化现状、不擅自复启」处理：在 MODULE_INVENTORY 与本条目登记死阶段事实与风险；不改公开配置白名单（避免 API 破坏）；复启与否是产品决定（涉及预算与运行时长形态），需解：复启则先修无限循环保护（bounded rounds 默认+持续失败熔断）；不复启则建议下个允许破坏的版本删除死代码与配置字段。
- 状态与验证：**已登记，代码未改（有意）**。验证：`grep` 无调用方证据如上。
- 下一步：由产品/主线决定复启或移除；本线报告已列两种路径的检查单。
- 变更记录：2026-11-01 新增。

## FL-D825 证据 HTML 残余轮次「新影响数」列恒空（键名错位）（2026-11-01）

- 发现日期：2026-11-01，审计 export.py 与 pipeline 持久化键一致性时发现。
- 问题与影响：`render_evidence_html` 残余轮次表读 `new_impact_count`，而 pipeline/store 持久化键为 `new_impacts`——报告该列恒为空，证据报告与 payload 数据不一致。
- 证据：`export.py:243` vs `pipeline.py:870`（`"new_impacts": len(new_impacts)`）。
- 处理方法：HTML 改读 `new_impacts`，保留旧键回退以兼容历史 artifact payload。
- 状态与验证：**代码已实施，新增单测 `test_evidence_html_renders_persisted_new_impacts_count`**。pytest 已验证（见下）。
- 下一步：无（随本线合并回归）。
- 变更记录：2026-11-01 新增。

## FL-D826 repair 单条模型失败完全不可见（不计调用、不留记录、证据链缺账）（2026-11-01）

- 发现日期：2026-11-01，审计 repair.py 聚合逻辑时发现。
- 问题与影响：`repair_items` 单条修复模型异常时原样返回且错误串被丢弃：不计 calls、不写 finding；整轮零修复时 pipeline 只留 `"repair_model_returned_nothing"` 备注，连 fixes（含失败信息）也不落库。运维无法区分「模型全部修复失败」与「无需修复」；与证据链完整性（gg_model_calls 虽由 router 记账，但 finding 维度断点）不符。
- 证据：`repair.py` 原 74-79/115-130 行；`pipeline.py` stage_repair 原 `if not repaired: ... break` 分支不持久化 fixes。
- 处理方法：repair 失败显式记 `major/open/guide_repair` finding（含错误码，不阻断完成——修复为 best-effort，原 critical 仍在，门禁语义不变）；pipeline 在零修复分支也持久化 fixes 并在 rounds 记 failures 数。
- 状态与验证：**代码已实施，新增单测 2 项：repair_items 失败 finding 可见、stage_repair 零修复时失败 finding 落库**。pytest 已验证（见下）。
- 下一步：真实 E2E 观察 repair 轮次记录形态。
- 变更记录：2026-11-01 新增。

## FL-D827 低危杂项登记：死代码/未接线旋钮/静默回退（本线不改代码）（2026-11-01）

- 发现日期：2026-11-01，逐模块审计汇总（两个审计子任务交叉核对）。
- 问题与影响（按严重度归档的低危项，均不改变现行行为，登记备查；修复价值低或需随破坏窗口）：
  1. eligibility.py `RUN_COMPLETE_STATUSES` 定义后零引用（dead constant）。
  2. corpus_catalog.py `_VERSION_SUFFIX` 定义未用（真实逻辑在 parse_contract_filename 内联 regex）。
  3. prompts.py `ENGINE_SCHEMA/ENGINE_INSTRUCTION` 与 model_router `guide_engine_map` 映射半接线死代码；engine_compat `requirements` 参数未用。
  4. vector.py rebuild 先短路后判空的顺序瑕疵（实际触发窗口极小）；SQLite 检索全表扫性能瓶颈（语料×需求规模下 O(R·N·dim) Python 循环，扩展性注意）；Qdrant 旧 collection 无 GC；rollback 不校验目标 manifest 完整性。
  5. coverage.py 第一遍 counts 计算为 dead work（后被全量重算覆盖）；`_sweep_state` 返回值未用。
  6. scope.py 内建指引 JSON 缺失时静默回退 6 章默认（发布树必须含 `guides/builtin_guide_v1.json`，已核对发布树文件存在）。
  7. service.py `_config` 对 `FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT` 非整数 env 直接 ValueError 冒泡（启动即败，fast-fail 可接受，部署注意）。
  8. models.py PolicyRequirement to/from_dict 的 payload 覆盖陈旧字段潜伏缺陷（当前管线无「加载后修改再写」路径，未触发）。
  9. engine_compat 直销守卫相关条目恒分类 ENGINE_CAPABILITY_GAP 的系统性偏置（不影响指引内容，仅独立报告口径）。
  10. discovery/authoring/quality/residual 多处裸 `except Exception` 静默降级（方向 fail-closed/保守，但使代码缺陷与真实模型故障不可区分，观测面建议）。
  11. human.py candidate_transaction 内文件 IO，DB 回滚留孤儿文件（低）。
- 处理方法：登记不修复（保持最小变更）；如需排序，建议优先 8（数据一致性）与 4 的性能项（随语料扩到全量 514 份时成瓶颈）。
- 状态与验证：**已登记，未改代码**。
- 下一步：主线按需立项；8 建议在引入任何「编辑后重存 requirement」路径前先修。
- 变更记录：2026-11-01 新增。

## FL-D828 coverage/向量链路 fail-open 面登记（政策一致性建议，本线不改代码）（2026-11-01）

- 发现日期：2026-11-01，审计 coverage.py 与 vector.py 失败语义时发现。
- 问题与影响：两处「模型/派生病失败不阻塞 pass」的面：① coverage 的 semantic applicability 调用失败→`ambiguous` 仅 major finding，独立审计调用失败→major finding，`run_status` 只看 critical/latest_uncertain/unresolved_impact，因此「模型质量性失败（非基础设施失败，不触发 router 阻断）」下覆盖仍可 pass，与「覆盖审计必须显式关闭每个问题」的门卫语义有缝隙；② 向量检索为可选增强路径，构建/重建/查询失败静默降级词法（payload 留 `vector_index.status=unavailable`），合理但对「以为用了向量召回」的运维不可见。
- 证据：`coverage.py:455-466/472-477/564-605/643-648`；`pipeline.py:171-178/383-390`；`discovery.py:268-271`。
- 处理方法：不改语义（属产品门禁松紧决定）。建议：对同一 run 内 applicability/audit 模型失败次数设阈值（如 ≥3 或占比 >1/3）升级为 critical；向量降级在 run summary/前端展示为显式警告徽章（归前端线展示面一起处理）。以上是建议，未实施。
- 状态与验证：**已登记为建议，未实施、未验证**。
- 下一步：由主线/产品决定门禁松紧；若采纳阈值方案，本线可按同一容错口径补开发。
- 变更记录：2026-11-01 新增。

## FL-D900 【编号段溢出，并册时请主线确认】正文省略号误判为目录行，后续条款被静默跳过（2026-11-01）

- 发现日期：2026-11-01，深查审计子任务报告的 TOC 状态机高危候选（原审计 #7）时确认。
- 问题与影响：分段器 `_is_toc` 命中 `_TOC_LINE=(?:…{2,}|\.{4,}|·{4,})\s*\d*\s*$`——**页码是可选的**，任何 <140 字符且以「……」/点线收尾的正文段（中文合同极常见的列举省略，如“包括国债、央行票据……”）都会把解析器置为 in_toc，**其后直到下一个「第N部分/第N章」标题的所有段落被静默跳过**，条款丢失无任何 warning/统计。语料 514 份均在风险面内。
- 证据：`fundlex/guide_generation/corpus_segmenter.py` 原 37/158-162/233-244 行；新增回归测试构造“正文省略号陷阱”合同复现（修复前 `披露投资组合的具体情况` 条款整段丢失）。
- 处理方法：页码改为必选（`\d*`→`\d+`），真实目录行（点线+页码）照旧跳过；正文省略句不再触发 TOC 状态。PARSER_VERSION 升 `contract-segmenter-2`；pipeline BUILD_CORPUS_SNAPSHOT 的输入哈希改用实际常量（原为硬编码 "contract-segmenter-1" 副本）。
- **连带部署动作（重要）**：`version_id` 只含 identity+日期+内容哈希、**不含 parser 版本**，存量 514 份已解析合同在下次 sync 会按原样复用（reuse），新分段逻辑不会自动生效。发布后须执行一次 `sync-corpus --force`（或等效运维步骤）重建条款分段，并核对 parse_failed 计数。此步骤写入发布守门。
- 状态与验证：**代码已实施，新增单测 2 项（正文省略号条款保留、真目录行仍跳过）**。pytest 已验证（见下）。未做 514 份全量重分段前后 diff 评测（发布守门覆盖）。
- 下一步：主线发布后按守门做 force resync+抽 diff；编号段（FL-D820~829）在本条溢出为 FL-D900，并册时由主线确认是否保留该编号。
- 变更记录：2026-11-01 新增。

## FL-D829 run a5525 失败的前端展示问题（登记，修复归前端线）（2026-11-01）

- 发现日期：2026-11-01，按工单核查 run a552520cf648451c93ed82d954bdfe19 失败时前端展示。
- 问题与影响：该 run status=failed、error_code=`[Errno 13] Permission denied: '/home/opencode/data/funds_word'`。前端 runProblem/阶段列表直接渲染 `error_code` 原文：① 向最终用户泄露服务器绝对路径与 Python 裸错误；② 无任何可操作指引（应显示稳定错误分类码+「语料目录配置问题，请联系管理员」类文案）；③ step 级 `PermissionError`（类型名）同样裸显。FL-D821 修复后后端将产稳定分类码（CORPUS_DIR_MISSING/CORPUS_DIR_UNREADABLE/CORPUS_EMPTY），前端应映射为友好文案而非渲染原文。
- 证据：MySQL gg_runs/gg_steps 记录（见 FL-D821 证据）；`frontend/guide_generation.js` line 71/273/326（`stage()` 映射表、`runProblem(run.error_code)`、`step.error_code` 直接 esc 渲染）。
- 处理方法：本线仅登记（工单明确修复归前端线）。建议：错误码白名单映射（已知码→中文可操作文案），未知码显示通用文案+trace 编号，不渲染原始异常串；路径类信息不进浏览器。
- 状态与验证：**已登记，未修复（归属前端线）**。
- 下一步：前端线实现错误码映射；与 FL-D821 后端稳定码一并验收。
- 变更记录：2026-11-01 新增。

## FL-D902 【编号段溢出，并册时请主线确认】指引版本对比「差异暂未算出来」兜底文案与后端实际语义不符；三成因共码、字段白名单漏 section_hint（2026-11-01）

- 发现日期：2026-11-01，应总指挥追加要求盘点「我的指引→版本对比」后端能力时逐行核对生产树（该功能代码不在本 worktree 基线 158475f，为生产树后续新增，见 MODULE_INVENTORY 专节版本差提醒）。
- 问题与影响：①前端「差异暂未算出来，请稍后重试」（生产 app.js:1280）是**一切请求失败的统一兜底**，而两个 diff 端点（GET /api/guides/{id}/diff 与 /text-diff）均为请求内**同步、确定性、零模型**计算，不存在异步未就绪形态；"稍后重试"对「版本未解析出规则」（404 GUIDE_DIFF_UNAVAILABLE 来自 rules_json 空）恰好有效，但对「源文件缺失 GUIDE_SOURCE_UNAVAILABLE」「built-in 参与原文比对」无意义。②404 三种成因（版本不可见/未解析/源缺失）共用 GUIDE_DIFF_UNAVAILABLE，前端无法区分。③规则级 diff 的字段白名单（guide_diff.py RULE_FIELDS 6 字段）不含 `section_hint`，该字段变化的版本对比显示「无变化」；前端 guideDiffFieldLabel 已备 section_hint 映射，展示面预留但算法未覆盖。④原文 diff 的 GUIDE_SOURCE_UNAVAILABLE（非内置源缺失）前端无专属文案，落兜底。
- 证据：/opt/fundlex-recall-first/fundlex/api.py:1175-1203；guide_diff.py:16-17（RULE_FIELDS）；guide_text_diff.py:26-45；guide_store.py:817-828（diff_versions）与 338-355（guide_document 空 rules_json→KeyError）；生产 app.js:1236-1280（兜底与 tab 对版本 status 无预检，对照 「规则开关」页有 GUIDE_RULES_READY 过滤）。
- 处理方法：盘点结论已写入 docs/guide-generation/MODULE_INVENTORY.md「指引版本 diff」专节（含触发路径分解与缺口总判定）。后端代码本线**不改**（该功能属运行时指引体系、且生产树领先基线，修复归 FL-D891 前后端一并判定）；后端最小改动建议：404 载荷区分 UNPARSED/SOURCE_MISSING/VERSION_NOT_FOUND（或复用 detail 字段），guide_diff RULE_FIELDS 增补 section_hint；前端按码细分文案并对 status=parsing 版本预检。
- 状态与验证：**已登记+盘点结论落盘，代码未改（归属 FL-D891 施工判定）**。验证为源码逐行核对，未发真实 HTTP 请求复现（避免触碰生产会话态）。
- 下一步：主线将本节结论并入 FL-D891 判定；并册时确认编号。
- 变更记录：2026-11-01 新增。

## FL-D901 【编号段溢出，并册时请主线确认】E2E 探针将数据库连接串回显进 systemd journal（已清除，建议评估轮换）（2026-11-01）

- 发现日期：2026-11-01，本线搭建真实 E2E 时。
- 问题与影响：为诊断 systemd-run 环境注入行为，本线临时单元打印了 `repr(os.environ['FUNDLEX_DATABASE_URL'])`，该值含 MySQL 凭据，被写入 systemd journal（system 与 user-1002 两处持久化日志，root-only）。同样值也进入本次会话工具输出日志（无法自擦除，与 FL-D547 同类）。
- 证据：journal `strings` 命中复核记录（值本身不在本条登记）。
- 处理方法：当日完成清除——`journalctl --rotate`+删除两条含泄露的归档 journal+停 journald 删除含泄露的 active user-1002.journal（该机 opencode 用户级 journal 历史损失，影响仅限日志审计面），复扫全部 journal 文件 `ALL-CLEAN`；探针单元为 transient 已自动回收。后续 E2E 改为生成 root-only `/etc/fundlex-gg-e2e.env`（由 env 文件管道改写，永不回显），不再打印任何环境值。生产数据库凭据值未变化；是否轮换由用户/管理员评估（本线不擅自变更生产凭据）。
- 状态与验证：**泄露通道已关闭并复核干净；凭据未轮换（待所有者决定）；防范规则已写入本线操作（不再将环境变量值输出到任何日志/工具结果）**。
- 下一步：建议主线/管理员评估轮换该 MySQL 凭据（与 FL-D547 记录的旧凭据回显事件并案评估）；发布守门脚本增加「输出过滤器：禁止回显含 KEY/SECRET/PASSWORD/URL 凭据段的环境变量值」检查。
- 变更记录：2026-11-01 新增。

## FL-D903 新指引解析质量保障体系：可检验质量门标准+多形态测试矩阵+表达质量检查层（FL-D898 工单落地）（2026-11-01）

- 发现日期：2026-11-01，总指挥扩展工单（用户亲定「新指引能不能很好解析成合适的规则，是你需要保证的」）。
- 问题与影响：解析通道此前只回答「能不能跑」（确定性校验/独立核验/可执行性金丝雀），从未回答「解析出的规则对用户是不是好规则」：①「解析得好」无可检验标准；②多形态指引（无强调格式/通用编号/表格承载/修订痕迹）无解析测试矩阵；③诊断 detail 是英文技术串直怼用户（FL-D883 的同源病灶），findings 的 kind 枚举码直接渲染。
- 证据：frontend/app.js:1333+（errors/warnings 的 detail 英文技术串直渲染、findings 的 kind 枚举码直渲染）；guide.py 旧 _issue detail 全英文（如 `operations[0].condition class_count requires value 1`）。
- 处理方法（本线已实施）：①质量门检查清单落档 docs/GUIDE_PARSE_QUALITY_GATE.md（标准 S1-S9+诊断红线+矩阵 M1-M12，每条标注检验位置与状态）。②guide.py：PARSER_VERSION 升 guide-parse-2；validate_parsed_guide 全部 detail 中文化（操作位置「第 N 个操作」、字段中文名、条件中文名），技术串保留在 `detail_tech` 并由 _render_repair_context 专用（模型 repair 上下文不吃中文变更）。③新模块 fundlex/guide_quality.py：presentation_report（S1-S5：人话标题、要求≥8 字、占位符检出、章节定位域提醒、内部标识符红线 INTERNAL_TOKENS）与 check_parse_quality（版本级 5 项 advisory 清单：structure/verification/executability/presentation/code_map）。④guide_store.py：verification findings 持久化时附 `kind_zh`；_parse_enrichment 输出 `quality_checklist`。⑤guide_report.py CODE_EXPLANATIONS 补全（section_hint 空/段落顺序/覆盖缺口/legacy 未注册/文档无效），未归类即矩阵测试失败。⑥tests/test_guide_parse_quality_matrix.py 16 测（M1-M11 零模型构造 DOCX 多形态+M12 基准工具可用性）；test_guide.py 断言适配中文契约+detail_tech 双断言。
- 状态与验证：**代码已实施+确定性测试全绿+真实模型实证完成**。确定性：matrix 16 + guide 系 123 passed + guide API 16 passed（venv 补装 cryptography 后恢复可收集——并线带来的环境缺口，非代码问题）。真实模型（FL-D445，账本 /tmp/opencode/qa/guide-parse-bench-fl-d898.sqlite，报告同目录 .json）：`tools/guide_parse_benchmark --guides v4 v2 --engine-smoke 2` overall_ok=True——v4 15 规则/0 覆盖缺口/0 findings 但校验层 12×GROUP_INVALID 拦下（预期允许 certify_or_structured_block）；v2 按预期结构化拦下（1×SLOT_NOT_IN_TEXT+4 findings）；引擎冒烟 2 行 task_create_401（CLI 无会话态，如实限制，非通道失败）。追加 v4 探针（同账本）实证 S5 落地：真实输出 detail=「该规则第 2 个操作的『择一关系』标记与『择一分组』填写不一致」「槽位词『C类基金份额』没有出现在任何新条款文本中」，detail_tech 保留 `operations[1].one_of_group does not match group_kind` 技术串；独立核验抓到 wrong_condition（把「有多个份额类别时适用」误写成 has_service_fee=true）由核验层正确拦下。**真实跑暴露并已直补两项**：诊断文案错别字（「择一招牌」→「择一关系」）；模型反复违反 group_kind/one_of_group 一致性（单轮 12 错、修复不收敛）→解析指令明示一致性契约，GUIDE_PARSE_PROMPT_VERSION 升 guide_parse_v2（d4ed3a8）。presentation 检查定位 advisory，不改 certified/enable 闸语义（升级与否留主线决定）。
- 下一步：发布时需对既有含表指引版本重解析（PARSER_VERSION v2 段落索引变化，同类 resync 注意事项已写明）；FL-D905 前端协同落地；prompt v2 对 one_of_group 失效率的改善待下次基准实跑观察（不阻塞本工单）。
- 变更记录：2026-11-01 新增；2026-11-01 回填真实模型基准+探针证据与两项直补。

## FL-D904 指引解析表格盲区：body 内 w:tbl 内容全部静默丢失（已修复，guide-parse-2）（2026-11-01）

- 发现日期：2026-11-01，FL-D898 施工通读 extract_guide_source 时发现。
- 问题与影响：extract_guide_source 旧实现只迭代 body 直属 w:p，**表格（w:tbl）内的指引内容全部静默丢失**——规则写在表格里的指引：混合文档表现为规则静默缺失（且因 source_paragraphs 无索引可指，覆盖校验也不报），纯表格指引被误报 GUIDE_SOURCE_EMPTY「没读到文本」。属于 S7「结构无丢失」的实质缺口。
- 证据：旧 guide.py extract_guide_source 循环 `if element.tag != Q("p"): continue`；矩阵测试 M6（test_m6_table_content_is_extracted_and_parseable）修复前后对比。
- 处理方法：_collect 递归收集 body 直属段落+表格内全部段落（保持文档流顺序）；PARSER_VERSION 升 guide-parse-2（含表文档段落索引变化，既有版本需重解析才受益）。
- 状态与验证：**已修复并验证**（M6 测表格段可引用、逐字校验通过、零覆盖缺口；M7 测表格内修订删除痕不混入）。
- 下一步：发布说明注明含表指引需重新解析；评估存量版本是否触发 resync（与 FL-D900 守门同类）。
- 变更记录：2026-11-01 新增。

## FL-D905 【协同项，施工归前端线】指引问题区块 findings 渲染改用 kind_zh；detail_tech 不得进浏览器（2026-11-01）

- 发现日期：2026-11-01，FL-D883 根治施工时定位前端渲染面。
- 问题与影响：frontend/app.js:1338「独立核验发现」区块把 finding 的 kind 机器枚举码（wrong_text/missing_group/ambiguous_branch 等内部变量名）当 code 直渲染给用户。后端已在 issues 载荷附带 `kind_zh`（FL-D903，中文名映射 FINDING_KIND_LABELS）；validation issues 现同时带 `detail`（中文）与 `detail_tech`（技术串，供模型 repair context）——前端若改读 detail_tech 属于回退，需防呆。
- 证据：frontend/app.js:1338（`guideIssueDetails(finding&&finding.kind?finding.kind:'FINDING',...)`）；guide_store._quality_failure_issues 的 kind_zh 产出。
- 处理方法：本线仅登记（前端文件域归前端线）。建议一行切换：`finding.kind_zh || finding.kind`；GUIDE_ISSUE_HINTS 无需新增（kind 枚举不再进入渲染路径后可保留兜底）。
- 状态与验证：**已登记，未修复（归属前端线）**；后端侧 kind_zh 已就绪并在 guide 系测试覆盖。
- 下一步：前端线切换渲染字段并回归指引问题区块；并册时确认编号。
- 变更记录：2026-11-01 新增。

## FL-D906 requirements disposition_reason 被 walrus 无条件覆盖：确定性理由死赋值，兜底文案与实际处置矛盾（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01，27 文件全覆盖审计（子任务初报+主审计员读 requirements.py L90-162 亲验确认）。
- 问题与影响：`_validate_requirement` L147-150 `if disposition_reason := str(item.get("disposition_reason") or "").strip(): pass else: disposition_reason = "模型对处置给出 uncertain…"`——无论模型是否给理由，L136/140/143/146 四条确定性改写分支刚写入的理由都被覆盖：①模型给了理由→模型理由胜出（与确定性改写的 disposition 不一致）；②模型没给→兜底文案固定写「uncertain」，而实际 disposition 可能是 no_contract_change/out_of_contract_scope/modify_contract。理由与处置事实矛盾，误导人工复核与下游 reason 展示。
- 证据：requirements.py L136-150（L90-117 确认 disposition_reason 此前无初始化）。
- 处理方法：本工单只读登记。修复方向：确定性理由优先（非空即留）→模型理由次之→按实际 disposition 生成兜底文案。
- 状态与验证：**已登记，未修复**（本工单纪律只读）。正确性已主审计员亲验。
- 下一步：修复工单纳入；补单测钉住三分支理由一致性。
- 变更记录：2026-11-01 新增。

## FL-D907 【P1】corpus_segmenter TOC 退出只认「第X部分/第X章」：正文以「第X条」起头的合同整篇正文静默漏切（FL-D900 同族未闭合变体）（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01，全覆盖审计（子任务初报+主审计员读 corpus_segmenter.py L24-68/L190-271 亲验确认）。
- 问题与影响：FL-D900 修复了 TOC 进入侧（点线+页码才入 TOC 态），但退出侧 corpus_segmenter.py L244-248 只在 `level==1 and (_PART.match or _CHAPTER.match)` 时复位 in_toc；标题正则族根本没有「第X条」模式。真实目录之后正文若以第X条直接起头（无部分/章层级的基金合同常见形态），in_toc 永不复位，后续全部正文段落被 `continue` 静默跳过；表格在 in_toc 检查之前收集（L221-231），产出「只有表格条款」且 `if not raw` 不触发、无任何报错。
- 证据：corpus_segmenter.py L34-41（标题/TOC 模式集）、L244-248（退出谓词）、L221-231（表格先行）、L270-271（raw 保护）。
- 处理方法：本工单只读登记。修复方向：TOC 态下遇到任何非 TOC 形态的正文级标题（含第X条/一、/1.等）或连续 N 段非 TOC 文本即复位；PARSER_VERSION 升号并对受影响合同重切（同 FL-D900 守门节奏）。
- 状态与验证：**已登记，未修复；影响面待量化**（需扫 514 份语料识别含目录且无部分/章层级的合同数）。
- 下一步：修复+语料扫描量化+重切守门；与 FL-D900 并案评估是否同源补丁窗口。
- 变更记录：2026-11-01 新增。

## FL-D908 store fencing 长事务空窗：candidate_transaction 活跃连接跳过 _assert_fence，与 docstring「every write checked」矛盾（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 store.py L248-277 亲验确认）。
- 问题与影响：`_connect` L255-258 在 `_transaction_db` 活跃时直接 `yield active` 返回，不执行 L263-264 的 `_assert_fence`；而 fencing docstring（L268-273）声称每次写都在库上检查。candidate_transaction 长事务内（pipeline.py:941、human.py:38 调用）租约中途过期/被 reclaim 后，旧 worker 仍可在该事务内继续写候选版本，stale write 防护出现空窗。
- 证据：store.py L253-265。
- 处理方法：登记。修复方向：fencing 绑定后每次写前断言（含事务内复用连接），或事务提交前强制断言+失败回滚。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入（与 fencing 单测同批做「租约中途失效」用例）。
- 变更记录：2026-11-01 新增。

## FL-D909 store start_step 显式 attempt 用 INSERT OR REPLACE 抹掉既有证据行（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 store.py L845-870 亲验确认）。
- 问题与影响：`start_step` 显式传入 attempt 时 L856-860 `INSERT OR REPLACE INTO gg_steps` 无条件清空该行 finished_at（置 NULL）、output_hash、error_code、payload——重跑同一 attempt 会抹掉此前已完成/失败 attempt 的证据行，破坏 gg_steps 可审计证据链；仅 attempt=None 路径（MAX+1）安全。另 L863-870 finish_step 与 update_impact/update_guide_item/update_requirement 的 UPDATE 均不查 rowcount，目标行不存在时静默空写（低危，并入本条登记）。
- 证据：store.py L847-861、L863-870、L694-702、L1104-1110、L1158-1164。
- 处理方法：登记。修复方向：start_step 显式 attempt 撞已完成行时拒绝或另起 attempt；四处 UPDATE 加 rowcount 校验抛 NotFound。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入；补「重跑证据不丢」回归测试。
- 变更记录：2026-11-01 新增。

## FL-D910 store update_run/update_candidate payload 读-改-写无 BEGIN IMMEDIATE，并发丢失更新（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 store.py L414-434 亲验确认）。
- 问题与影响：`update_run` payload 路径 L421-428 读当前 payload_json→merge→写回，全程无 BEGIN IMMEDIATE（对比 enqueue L896/resume_run L1024 均有）；SQLite WAL 下两个并发 payload 更新各自读到同一基线，后提交者整包覆盖，payload 字段丢失更新（lost update）。update_candidate L479-487 同构。调用侧实例：worker.py L194 `{**get_run()...}` 全量回写会把并发新增键用陈旧副本覆盖。
- 证据：store.py L419-433、L479-487；worker.py L192-198。
- 处理方法：登记。修复方向：payload 合并放进 BEGIN IMMEDIATE 事务，或改 JSON_MERGE 服务端原子合并。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入。
- 变更记录：2026-11-01 新增。

## FL-D911 store claim 退役谓词漏 'leased'：历史竞态残留的第二 job 可再被 claim，同 run 双活 epoch（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 store.py L960-992 亲验确认）。
- 问题与影响：claim 成功后退役同 run 重复 job 的 UPDATE（L984-986）`status IN ('queued','retry_wait')` 漏掉 'leased' 态；历史竞态留下的第二个 lease 已过期 job 不会被退役，其 claim 谓词 `status='leased' AND lease_until<now`（L976）仍通过，之后可被再次 claim——同一 run 出现两个活 epoch 并发处理。fence 能挡 stale 写，但浪费真实模型调用且重复副作用。
- 证据：store.py L966-986。
- 处理方法：登记。修复方向：退役谓词纳入 `'leased'`（lease 过期语义下安全）。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入；补双活 epoch 回归用例。
- 变更记录：2026-11-01 新增。

## FL-D912 store 低危包：死旋钮/死表/反序列化防御不一致/注解契约失真（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+抽查确认）。
- 问题与影响：①L37 SCHEMA_VERSION="guide-generation-1" 定义后全仓库无引用（schema 演进无登记点）；②L221-223 gg_corpus_state 表建出后无任何读写（死表）；③L429-433 update_run 对 allowed 之外字段静默丢弃；④L838/844/1102/1126/1156 多处 `Model(**_loads(...))` 直接展开，合法 JSON 但键不符即 TypeError 打挂整表读取，与同文件 from_dict 键过滤风格不一；⑤L1344-1353 record_model_call 注 `-> None` 实返 call_id。
- 证据：store.py 对应行号。
- 处理方法：登记（与 FL-D827 低危登记同类，列新条目因属新一轮全覆盖审计的增量面）。
- 状态与验证：**已登记，未修复**。
- 下一步：并入下一轮低危清扫工单。
- 变更记录：2026-11-01 新增。

## FL-D913 worker 异常原文入 error_code/engine_error 并经 API 外泄——FL-D829 前端暴露的后端源头（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报；与 FL-D829 run a5525 实证互证）。
- 问题与影响：worker.py L136/L186 `code = getattr(exc, "code", None) or str(exc)[:160] or type(exc).__name__`——未知异常以异常原文填充 error_code 入库，经 api.py `_public_run` 的 error_code 字段回前端（FL-D829 run a5525 的 `[Errno 13] Permission denied: '/home/opencode/data/funds_word'` 正是此路径产出）；engine 分支 L194-198 另把 `str(exc)[:500]` 写入 payload.engine_error。异常原文可含服务器路径/SQL/供应商报文，error_code 也不再是稳定枚举。
- 证据：worker.py L136、L186-199；api.py public 字段；FL-D829 的 MySQL 实证记录。
- 处理方法：登记。修复方向：未知异常统一映射 UNKNOWN_WORKER_ERROR（类名入 detail 字段，原文仅入服务端日志）；engine_error 同规则；api/public 输出白名单。
- 状态与验证：**已登记，未修复**；与 FL-D829（前端渲染登记，修归前端线）构成前后端同一缺陷链，后端源头在本条。
- 下一步：与 FL-D821 稳定码族并案修复；前端 FL-D829 联动验收。
- 变更记录：2026-11-01 新增。

## FL-D914 engine_compat 空 title 子串恒真：缺 title 解析组与任意条目「匹配」，capability gap 假阳性（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 engine_compat.py L33-45 亲验确认）。
- 问题与影响：L37 `if item.title and (item.title[:30] in title or title[:30] in item.title)`——guard 只验 item.title，未验解析组 title；解析组 title 为空时 `""[:30] in item.title` 恒真，该组与所有条目匹配，本应「无对应规则」的 ENGINE_CAPABILITY_GAP 被翻成 expressible，兼容性报告假阳性（对照 L39/L41 均双端非空守卫）。附带 P3：①L19-25 supported 与 unsupported_markers 词表重叠（直销/销售机构/持有期限/持续持有），unsupported 先判使 supported 四项成死代码；②L56-63 首个坏组即整体判 gap，结果依赖 matched 顺序；③L93 默认 output_dir=/tmp（共享可预测目录不清理）；④L109-111 错误码=异常类名（违反 FL-D821 稳定码原则，str(exc)[:500] 可带内部路径）；⑤L97 `router.gateways["primary"]` 硬编码键名，缺该键配置即永久 engine_error 而非显式配置错误。
- 证据：engine_compat.py 对应行号。
- 处理方法：登记。修复方向：title 分支加 `title and` 守卫；错误码稳定化；output_dir 默认受控目录。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入；补空 title 组回归用例。
- 变更记录：2026-11-01 新增。

## FL-D915 benchmark 空分母记满分：「没测」被记成「全对」（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 benchmark.py L92-152 亲验确认）。
- 问题与影响：L98-99 `critical_requirement_recall = … if critical_requirements else 1.0`——gold 缺 critical 项时 recall 直接 100%；同形 L148-150 known_clause_pattern_recall、L169-171 condition_results。对照 pattern_results 内部 L148 用的是 `else None`（N/A 语义）——同一文件两种口径。空分母出现在 gold 缺项或语料无该 pattern 时，headline 指标失真。附带 P3：L122-132 无 impact 链路时任一 expected_action_term 命中即记 covered（无最少命中门槛）；L44/L87-91 gold JSON 无 schema 校验，缺键裸 KeyError。
- 证据：benchmark.py 对应行号。
- 处理方法：登记。修复方向：空分母输出 N/A/None 并单列分母；弱命中加门槛；gold 校验给稳定错误码。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入；评测口径改动需同步冻结标签纪律（EVALUATION_AND_OPTIMIZATION_PLAN）。
- 变更记录：2026-11-01 新增。

## FL-D916 discovery sweep 窗口硬编码 [:8]，可配 max_requirements 调小即越界（FL-D823 修复引入的邻边缺口）（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 discovery.py L470-500 亲验确认）。
- 问题与影响：L479 `window = related[:8]` 硬编码 8；FL-D823 的补齐循环 `for item in related[8:]` 只在 `len(window) < max_requirements` 时追加。当配置把 path_b_max_requirements 调小到 <8 时，窗口恒为 8 超出自身上限，`_validate_sweep`（L390）按 max_requirement_ids 拒绝全部 finding，该批永远 model_error→重试→uncertain——配置小幅调低即静默亏覆盖。附带 P3：L552 模型返回的 impact_status 无白名单校验直接入 ImpactCandidate（脏串流进状态机被默默降权）；L715/731 changed 字典收集后未用；L283 source_sha256 为空串时跳过哈希校验属 FL-D828 同族 fail-open 分支（建议并入其登记）。
- 证据：discovery.py L479-499、L390、L552。
- 处理方法：登记。修复方向：`window = related[:min(8, max_requirements)]`；impact_status 白名单非法值归档到默认态并记 finding。
- 状态与验证：**已登记，未修复**；FL-D823 主修复验证在。
- 下一步：修复工单纳入；补 max_requirements<8 配置用例。
- 变更记录：2026-11-01 新增。

## FL-D917 pipeline 断点续跑 stage 哈希缺口：authoring/coverage 缓存不含 config/guide_scope/requirements（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读完哈希上下文确认）。
- 问题与影响：L1119-1122 BUILD_LOCAL_GUIDE_CANDIDATES 的 stage 输入哈希只含 impacts id+identity；L1135-1138 SEMANTIC_COVERAGE 哈希漏 sweep evidence/requirements/config.semantic_applicability/guide_scope（对比 discovery/finalize 均含 config.to_dict()）。中途改 guide_scope_sections 或 semantic_applicability 配置后重跑，会静默复用过期 authoring/coverage 结果，破坏断点续跑的「输入变=缓存失效」正确性。附带 P3：L1093 INGEST_REGULATION 哈希硬编码 "regulation-1" 字面量，解析器升级不失效缓存。
- 证据：pipeline.py L1117-1123、L1135-1138、L1093。
- 处理方法：登记。修复方向：两个 stage 哈希纳入 config 相关字段与 requirements 内容哈希；INGEST 用 PARSER 常量。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入；补「改配置重跑必失效缓存」回归。
- 变更记录：2026-11-01 新增。

## FL-D918 pipeline BUILD_EVIDENCE 排在 engine_compatibility 之前：开引擎兼容的 run 证据包永久记 engine "not_run"（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读完 L1154-1160/1219-1226 确认）。
- 问题与影响：run() 内 BUILD_EVIDENCE stage 先于 `if self.config.run_engine_compatibility: self.run_engine_compatibility()` 执行，且 BUILD_EVIDENCE 的 stage 哈希不含 engine 结果；stage_evidence L1047 硬编码 `{"status": "not_run", …}` 读库。开了 engine 兼容的 run，最终 evidence 包永久记录 engine "not_run" 且不含 engine 模型调用/结果——证据包与 run 终态不一致，可审计性受损。
- 证据：pipeline.py L1154-1160、L1219-1226、L1047。
- 处理方法：登记。修复方向：engine 兼容挪到 BUILD_EVIDENCE 之前并纳入其输入哈希；或 evidence 阶段重读 engine 终态。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入。
- 变更记录：2026-11-01 新增。

## FL-D919 repair/supersede 状态口径不一致与 repair target 不滤 status（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 pipeline.py L683-690 与 repair.py 上下文确认）。
- 问题与影响：①pipeline.py L687 supersede 过滤用 `finding.get("status") == "open"`，而全文件其余 critical/open 判定均用 `{"open","",None}`（L663/L636/L725）——status 为空串/None 的 finding 永不 supersede，既阻塞 repair 收敛又被 _refresh_quality_summary 继续计为 critical。②repair.py L65 by_item 收集 critical finding 时不滤 status，全部 critical 已 resolved 的条目仍被选为 repair target 白调一次模型并被无条件改写字段+升 version（无依据重写）。③同 run 两个 quality summary 口径不一（pipeline L638 major 统计不滤 status）。
- 证据：pipeline.py L636-690；repair.py L38、L65。
- 处理方法：登记。修复方向：统一 status 归一化谓词（一处定义全引用）；repair target 只取活跃 critical。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入。
- 变更记录：2026-11-01 新增。

## FL-D920 corpus_catalog 目录扫描双缺口：符号链接跟随出语料目录 + 大写 .DOCX 静默缺席（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 corpus_catalog.py L86-96 亲验确认）。
- 问题与影响：①scan_corpus_directory 只验目录本身，目录内指向目录外的符号链接会被 read_bytes 跟随并解析入库——可写语料目录者能让系统读取/入库目录外 docx/PDF（风险取决于语料目录写权限边界）；②`root.glob("*.docx")` 顶层且大小写敏感，Linux 下 `XXX.DOCX` 被静默排除且不计入 errors，eligible_files 口径不含它，无任何痕迹。
- 证据：corpus_catalog.py L86-96。
- 处理方法：登记。修复方向：resolve 后校验前缀在语料根内（拒绝逃逸 symlink 并记 error）；后缀匹配大小写不敏感或把大写命中记入 errors。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入。
- 变更记录：2026-11-01 新增。

## FL-D921 eligibility all_requirements_dispositioned 判据永真（死检查/语义待定）（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 eligibility.py L80-90 与 models.py L177-185 亲验确认）。
- 问题与影响：L85 `unhandled = sum(1 for item in requirements if not item.disposition)`——PolicyRequirement dataclass 默认 "uncertain" 且 __post_init__ 把空/非法 disposition 兜底为 "uncertain"，故 `not item.disposition` 对任何 PolicyRequirement 永 False，该闸门位恒通过（死检查）。「uncertain 算不算已处置」是业务语义问题：若不算，当前闸门把所有停留 uncertain 的 run 判格为合格；若算，该检查应删除或改名。另 L147 missing_topics 元素假设 dict（裸字符串列表会 AttributeError，数据漂移时 500 而非 fail-closed 输出）。
- 证据：eligibility.py L38-52、L85、L147；models.py L177-185。
- 处理方法：登记；语义取向上报主线裁定（uncertain 是否=已处置），按裁定改判据或删检查。
- 状态与验证：**已登记，未修复（含业务待定项）**。
- 下一步：主线裁定语义后修复。
- 变更记录：2026-11-01 新增。

## FL-D922 api.py 错误详情三形态：英文句子 detail、str(exc) 原文回吐、Content-Disposition 无转义（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（主审计员横切补扫+子任务复核）。
- 问题与影响：①L106/228/268/283/294/352 HTTPException detail 用英文句子（"guide generation run not found" 等），与同文件稳定码风格（UPPER_SNAKE）混用，前端若直渲 detail 即复现 FL-D829 类展示问题；②L200/214/230/232/350 `raise HTTPException(409, str(exc))` 异常原文回吐，当前抛点多是受控文案但无收口保证（store 层新增带路径异常时原样外泄）；③L296-299 未知 kind 回退文件名未经引号转义直接拼 Content-Disposition 带引号串（文件名含 `"` 时响应头拼坏）；④L368-371 rebuild-evidence 不校验 run 状态（对照 approve 有 RUN_NOT_COMPLETE 门），运行中的 run 可并发触发证据重建。
- 证据：api.py 对应行号。
- 处理方法：登记。修复方向：错误详情改稳定码白名单；str(exc) 仅在受控文案集内放行；文件名转义；rebuild 加状态门。
- 状态与验证：**已登记，未修复**；16 路由鉴权与 owner 隔离逐路由核对通过（无鉴权缺口）。
- 下一步：与 FL-D913/FL-D829 同批修复。
- 变更记录：2026-11-01 新增。

## FL-D923 quality.py 三处质量门表达/截断缺陷（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+抽查确认）。
- 问题与影响：①L216-217 复核上下文尾部 `text[:limit]` 硬截断，`[REAL_CONTRACT_EVIDENCE]` 恰为最后拼装段——超限最先丢合同证据，复核模型在无合同证据下判 fidelity，且截断无任何标记；②L285-294 `_normalise_reviewer_severity` 用英文关键词匹配模型自由文本 description（text_error_markers 全英文且定义后未用）——中文 critical 描述永不命中降级规则，归一化对中文输出名存实亡；③L161-165 「必须/应当+关联方」检查只验 new_text 同现、不验来源是否支持，描述却断言「来源未支持」——来源实际支持时产生事实性失真的 major finding。
- 证据：quality.py L161-165、L216-217、L285-294。
- 处理方法：登记。修复方向：截断重排关键段+加截断标记；severity 归一化改结构化输入；检出描述改为条件陈述。
- 状态与验证：**已登记，未修复**。
- 下一步：修复工单纳入。
- 变更记录：2026-11-01 新增。

## FL-D924 本轮全覆盖审计低危杂项包（各文件剩余 P3，按文件列全账）（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01。
- 问题与影响（按文件，行号见签认表与审计报告）：
  - prompts.py：指令「≤8 findings」与 schema maxItems=40 漂移（L445-446/L406）；全指令语料注入防护声明缺失（[Bxxxx] 仅声明地址性）；
  - authoring.py：模型 related_but_different+uncertain 被无条件改写 no（L265-266）；_candidate_signature 死函数+死 hasattr 分支（L332-334）；merged 死赋值（L368）；死导入×4；_impact_context 字符截断静默丢尾部 impact（L205-210）；
  - vector.py：embedding/Qdrant 请求无退避重试（L107-119/364-377）；rebuild 全量向量驻留内存（L244-247/398-401）；模块级 httpx 无连接复用；
  - model_router.py：熔断重试 time.sleep(125) 持有 _call_gate 信号量，任一角色熔断即全局串行化一整冷却窗（L367/421-422）；env REQUEST_OPTIONS_JSON 裸 json.loads 无稳定错误码（L133-136）；
  - lexical.py：avg_len 计算后未用于打分（L120）；token crc32 碰撞合并发帖表（L109）；注释称 section hints 不打分与实际相反（L83/L204-205）；
  - models.py：RegulationBlock(**item) 无键过滤（L142）；PolicyRequirement.to_dict 字段被同名 payload 键覆盖（L189-197）；from_dict 不做类型矫正（L202）；
  - human.py：AI 基线取「第一个 truthy guide_items」版本误取人工 draft（L55-58）；未知字段静默跳过（L63-65）；同批字节双读（L109-111）；
  - service.py：_server_corpus_dir 死函数（L56-58）；FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT 裸 int()（L118-119）；
  - cli.py：read_bytes/json.loads 无包裹（L56/61）；errors[:20] 截断无溢出提示（L43）；
  - export.py：DOCX 非原子写残留半成品（L71-74）；item.new_text 假非 None（L57-58）；
  - residual.py：not_affected 小集合下负样本轮换失效（L117-119）；
  - scope.py：双向子串匹配过宽（L56）；空 scope 静默 fail-open（L50-52，FL-D828 家族）；
  - requirements.py：「可」单字过宽误判 permission（L262）；_EXPLICIT_CONDITION 吞整句（L176）；死参数 ordinal/existing_ids/run_id/prompt_versions（L98/L350-351）；corrections 通道标量字段无类型归一、requirement/subject/object 可被模型整段改写不重走校验（L568-579）；
  - discovery.py：by_clause_id 循环内重复重建（L272）；旋转填充每轮重建 id set（L496）；docstring 与行为不符（"uncertain" vs 也处理 "affected"，L591/603）；
  - coverage.py：_requirement_in_scope 内层全表扫 impacts（L384，O(V×R×I) 热点）；_sweep_state 死计算（L371）；unresolved↔uncertain 死分支（L528）；审计返回行全表扫 rows（L502/511）；覆盖层中止信号被 except Exception 吞并按 finding 继续（L465/566-605，与 discovery 策略不一）；
  - pipeline.py：major 统计不滤 status 两 summary 口径不一（L638）；注释与 scope 过滤行为不符（L551-552）；candidate_transaction 内文件导出回滚留孤儿目录（L941-968）；_engine_html 英文技术串（L1252-1256）；跨模块导私有函数（L768）；rounds=0 被静默抬 1（L659/779）；clean_streak 记的是判定前旧值（L886）；L544 兜底候选绕过空文案守卫（触发路径经 requirements 校验不可达，降级登记）；L1224 engine attempt len+1 竞态（同 run 单活 job 弱化，降级登记）；
  - engine_compat.py：四项异报告 P3 已并入 FL-D914；
  - store.py：低危包见 FL-D912。
- 证据：docs/guide-generation/FILE_AUDIT_SIGNOFF_20261101.md 签认表+六批审计报告行号。
- 处理方法：统一登记，修复按主题分批；其中 fail-open 家族（scope L50-52、discovery L283）建议并入 FL-D828 的同一补丁窗口。
- 状态与验证：**已登记，未修复**。
- 下一步：低危清扫工单逐主题消化。
- 变更记录：2026-11-01 新增。

## FL-D925 corpus_segmenter 三处条款定位缺陷：数字起头句误判 heading 丢条文、anchor ordinal 撞号失真、title 判定优先级（2026-11-01，全覆盖审计）

- 发现日期：2026-11-01（子任务初报+主审计员读 corpus_segmenter.py L190-271 复核确认）。
- 问题与影响：①_NUM_ITEM(`^\d+[、．.]`)/_DOTTED(`^\d+(?:\.\d+)+`) 无「编号后须为短标题、无句读收尾」约束（对照 L156-158 对 bold heading 有 _SENTENCE_END 排除）——以十进制数起头且 ≤80 字的正文句子（费用率、比例列举段）被判 level-3 heading，而 heading 永不入 clauses，该句条文文本静默丢失且污染 section_stack 归属；②L228-229/L265-266 p 与 tbl 共用同一 ordinal 生成 xml_path，且空段/TOC 行被跳过不占号——ordinal 既非真实 OOXML 子节点序号，anchor 指向与 document.xml 实际位置不符，证据链追溯定位错误段落；③L250 运算符优先级使 title 判定实为 `endswith("基金合同") or ("基金合同" in text and len<=80)`，200 字内以基金合同结尾的长段可误判为 title（仅元数据，低危）。
- 证据：corpus_segmenter.py L148-158、L228-229、L235-240、L250、L265-266、L304-305。
- 处理方法：登记。修复方向：编号 heading 加句读排除与短标题约束；xml_path 改用真实 OOXML 子序号（含跳过元素）；title 判定加括号明确优先级。
- 状态与验证：**已登记，未修复**。
- 下一步：与 FL-D907 同一 segmenter 修复窗口处理；修后 PARSER_VERSION 升号+受影响合同重切。
- 变更记录：2026-11-01 新增。

## FL-D926 直驱冒烟工具把合同字节作为「指引源」上传：source_sha256 必不匹配，parsed 形态 engine drive 必败（2026-11-01，棒1 实战验证发现）

- 发现日期：2026-11-01，棒1 多形态矩阵 engine drive 子项实证（worker 终态 error_code=GUIDE_NOT_CERTIFIED，failures=['source_sha256_mismatch']）。
- 问题与影响：tools/guide_parse_benchmark.py::engine_smoke（约 L120-122）`create_custom_version(store,"qa",contract.name,contract.read_bytes())`——把**合同 DOCX 字节**当指引源上传；而版本 source_sha256 由上传字节哈希得出，_bound_guide_document→validate_runtime_guide 会核对文档内嵌 source_sha256（指南源 SHA）与版本记录值，二者必不同。因此「parsed（已解析自定义指引）形态直驱修订」在该工具下**永远无法真实通过**，此前该类 smoke 的交付证据实际只覆盖了 builtin 形态；生产上传路径本身无恙（指引源=用户上传指引文件）。
- 证据：tools/guide_parse_benchmark.py:120-122；实证复现 /tmp/opencode/qa/guide-matrix drive 库 guide_versions.source_sha256 与 rules_json 内嵌 source_sha256 不一致；对照 fundlex/guide.py:971 validate_runtime_guide 与 jobs.py:573 _bound_guide_document。
- 处理方法（已实施）：本线矩阵工具 tools/guide_parse_shape_matrix.py 已修正为传**指引文件字节**（engine_drive(document, guide_path, ...)，并在 docstring 写明原因）；benchmark 工具同款调用建议主线同步修正（本线只读不改正）。
- 状态与验证：**本线工具已修复并复跑验证**；benchmark 侧修复属后续主线工单（登记，未修复）。
- 下一步：主线修正 benchmark engine_smoke 的同源调用，并以驱动成功为证据闭环。
- 变更记录：2026-11-01 新增。

## FL-D927 replace/delete 操作 old_text_variant 为空仍可过门 certified：规则永不可达的解析质量空档（2026-11-01，棒1 矩阵实证）

- 发现日期：2026-11-01，棒1 七形态真实模型矩阵×引擎直驱实证。
- 问题与影响：S4 勘误微指引解析产出 `replace` 操作 old_text_variant=null、new_text="1.2%"；S2 表形态产出 `delete` 操作 old_text_variant=null。无锚点旧文的 replace/delete 在引擎侧**永不可达**（无处定位），但该版本仍能过全部认证门（validation clean + canary passed + checklist pass）并 enable，实际驱动总目标数恒 0——「解析通过却永远不改任何合同」的质量空档。canary 现有检查（OP_UNREGISTERED/ROUTE_BLOCKED/DEAD_CONDITION/COMPILE）覆盖注册路由与条件恒假，未覆盖「操作缺必要锚点参数」这一执行死端。
- 证据：三跑驱动库 rules_json（S4 e8eb2bf9…G01 replace old_text_variant=null；S2 3067354e…G01 delete 同）；驱动 4 合同 total=0；对照 guide_canary.py L150-187 检查集无 op 参数完备性项。
- 处理方法（建议，本线只读不动代码）：canary/guide_parse 确定性校验增加「replace/delete 须具非空 old_text_variant 或 anchor」的 fatal/advisory 项；并考虑 section_hint 缺失（泛化编号形态 S3）时 append 定位率下降的提示级检查。另注意同一语义在标准标题形态（S1）可命中而泛化编号形态（S3 G02）在 A50 合同 0 目标——形态影响定位率，属既有设计边界如实记录。
- 状态与验证：**已登记，未修复（本线不改正）**；结论由真实模型链路产物直接实证。
- 下一步：主线裁定检查级别（fatal 或 advisory）后在 canary/校验层实施，回归复跑本矩阵。
- 变更记录：2026-11-01 新增。

## FL-GGAPPLY-01【占位，号段申请中】指引提取层不读 OOXML 脚注：脚注承载规则的记忆性丢失（形态库 FF-1）（2026-11-01，总攻压测）

- 占位说明：按总攻纪律③先向主线申请号段（主线已用至 FL-D997，申请 FL-D998~，见状态文件）；批复后替换占位号，条目内容不变。
- 发现日期：2026-11-01，A6 形态压测 T5_footnote_rules（真实 OOXML footnotes.xml 承载修订执行口径，正文仅「见脚注①」）。
- 问题与影响：`extract_guide_source` 只读 word/document.xml 的正文段与表（guide-parse-2），脚注文字对解析全链不可见——该形态下解析中空转：模型如实保守地 noop+notes 标记「引用悬空」，验证器中文诊断为「脚注①的具体内容未包含在指南文本中」，三轮修复无法收敛，版本终态 failed（fail-closed，方向正确；属提取层机制缺口）。
- 证据：一轮实测版本 issues（verification.findings[kind=missing_reference, kind_zh=引用未解析]，区块报告 blocks_total=1）。
- 处理方法（已实施，机制修复非单件特判）：提取层泛化读取 word/footnotes.xml——跳过 separator/continuation，按序号输出「脚注<n>：」标记段（正文索引不变，正文纯净文件的提取集合与 parse-2 完全一致，mutation 反例钉住）； malformed footnotes.xml 容错不炸；PARSER_VERSION 升 guide-parse-3。
- 状态与验证：**已修复并复验通过（本树 commit e36548e）：相关 4 文件套件（test_guide.py 24 含 5 项脚注新测／test_guide_canary.py 10／test_guide_parse_quality.py 9／test_guide_smoke.py 3）合计 46 passed；parse-3 全量压测复验已通过（T5 failed→certified，见形态库/登记册）。**
- 下一步（均已闭环）：T5 复验 failed→certified 已回填形态库与失败族登记册（0b6a31a/6bbd2a5）；剩余仅主线核拨正式编号。
- 变更记录：2026-11-01 新增；2026-11-01 状态推进为复验通过（盲审 NOTES-2 修正口径）。

## FL-GGAPPLY-02【占位，号段申请中】模型失败诊断把「内容不是指引」误诊为「服务暂不可用」（A7 空档）（2026-11-01，总攻压测）

- 占位说明：同 FL-GGAPPLY-01。
- 发现日期：2026-11-01，A6 压测 N3_garbage_semantic（菜谱/天气/纪要内容的合法 DOCX）。
- 问题与影响：模型对非指引内容反复输出非法 schema，终码 GUIDE_MODEL_FAILED:MODEL_SCHEMA_INVALID；`guide_report._explain` 对 GUIDE_MODEL_FAILED:* 一律诊断为「模型服务调用失败…多为服务暂不可用或限流，稍后重试解析」——对非指引文件是**事实性误诊**（重试永无效），用户被引向无谓重试。
- 证据：N3 版本 parse_report entries.reason_zh/remedy_zh 原文。
- 处理方法（已实施，通用机制非单件特判）：说明文案改为双修因表述「模型未能解析该内容（码）→请确认上传文件确为修订指引（非指引内容无法解析出修订规则）；若确认是指引仍失败，多为服务暂不可用或限流…」——真暂态与真垃圾两种情形都不说谎。
- 状态与验证：**已修复并复验通过（e36548e + d584602 文案钉测）；同套件 46 passed（基数同 FL-GGAPPLY-01）；N3 诊断原文已在压测版本 issues 实测为新双修因文案。**
- 下一步（已闭环）：N3 复验 diagnosis 原文=新文案（6bbd2a5/报告抽查）；剩余仅主线核拨正式编号。
- 变更记录：2026-11-01 新增；2026-11-01 状态推进为复验通过（盲审 NOTES-2 修正口径）。

## FL-GGAPPLY-03【占位，号段申请中】admission 与执行双层对 generated 区位操作身份判定不一（FF-T7 缝隙，canary 守住）（2026-11-01，总攻压测深层取证）

- 占位说明：同 FL-GGAPPLY-01（申请号段 FL-D998~）。
- 发现日期：2026-11-01，A6 压测 T7_conditional「附条件适用」形态深层取证。
- 问题与影响：对 bind 生成的 positional operation_id（如 T7 第二分支落到 `G01:1`，内置注册表无此键），三层判定不一：①`jobs._bound_guide_document` 的 admission 谓词 `generation.registry.operation_registry_coverage_gaps` **跳过** `operation_id_generated=True 且规则名在 STRATEGY_REGISTRY` 的操作→gaps=[](放行）；②运行时 `_registry_execution_authoritative`（recall.py）只看 operation_id 存在性，把这类规则当 authoritative→routed 执行对 `G01:1` 抛 `RECALL_OPERATION_REGISTRY_MISSING`（fail-closed 于执行中）；③启用门 `guide_canary.blocking_gaps` 同样判 fatal OP_UNREGISTERED→版本 needs_review 不可启用。也就是说：canary 的「严」是与执行一致的、保护性的；admission 谓词的「宽」才是缝隙——若无启用门，该版本会在修订执行中失败。我（本线）一度误向「canary 向 admission 看齐」修复，深挖后已整体回退并改钉测试（7d131f4），如实留史。
- 证据：registry.py L295-318（generated 跳过条款）；recall.py L2694-2710（_registry_execution_authoritative 全面无视 generated 标记）；压测 T7 两轮 canary OP_UNREGISTERED=G01:1；对照 MERGED 夹具注释「runtime router failed closed on」与该夹具经 admission gaps=[] 的实测。
- 处理方法（建议，需主线裁定，本线不改运行时语义）：二选一——a) registry.py admission 去掉 generated 跳过条款（与执行/enable 统一 fail-closed）；b) 运行时把 generated id 规则降级为 legacy 执行（语义放松，需证明兼容路径正确执行条件分支）。在裁定前，canary 保持现状（needs_review 拦截）。
- 状态与验证：**已登记（未修，待主线裁定）**；本树已钉执行一致性测试（tests/test_guide_canary.py 三例：generated 越区位仍 fatal、出版方 id 未注册仍 fatal、未知规则名仍 fatal）+test_guide.py 24，合计 34 passed。
- 下一步：主线裁定 a/b；裁定后统一三层谓词并复跑 T7 压测。
- 变更记录：2026-11-01 新增（含本人修复方向误走的诚实回退记录）。
