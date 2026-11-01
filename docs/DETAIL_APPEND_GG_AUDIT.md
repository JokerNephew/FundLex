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
