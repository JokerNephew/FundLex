# 批次B7回报（guide_store/guide_report/guide_diff/guide_text_diff/guide_canary/guide_smoke/reconciliation）

来源：子审计员 ses_e69bbd007（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B7报告

### fundlex/guide_store.py
- 结论：⚠️ 候选发现 1条
- ① 版本状态机完整（uploaded/parsing/parsed/parse_failed/failed/released+认证三态），claim/release/finish 均带 fencing token 与 rowcount 校验（FL-D290 的修复形态）；canary/smoke 真实接入（finish→_parse_enrichment，jobs.py:567 worker 钩子）。
- ② ⚠️ 见候选发现1（canary 故障 fail-open 认证）；其余 fallback 文案均为中文人读。
- ③ `_version_dict` 输出 source/document/rules_sha256（L254-255）为 API 传输字段，前端隐藏已由 FL-D711 处理，属已知联动。
- ④ 全文无 TODO/FIXME；无悬挂死代码。
- ⑤ 抽查 3 处跨模块调用（`diff_guide_documents(before,after)`、`blocking_gaps(document)`、`extract_guide_source(path)`）签名均匹配。
- 候选发现1：canary 吞错导致认证 fail-open｜证据 guide_store.py:221 `except Exception: pass` +:750-752 canary=None→CERTIFIED｜可执行性金丝雀自身崩溃时版本被静默认证放行而非 needs_review，且启用门 `blocking_gaps` 不复验死条件/路由阻断维度｜建议：canary 异常时 qualification 不落 CERTIFIED（报主线判定，可能属有意"advisory by construction"设计，但 L32-43 注释表明 canary 是认证门禁非纯咨询）
- 已知命中：FL-D290（fencing，已实施）、FL-D183（ENABLEABLE 集合）、FL-D730（rule 人读字段）、FL-D894/711（哈希泄露主题，前端已治理）

### fundlex/guide_report.py
- 结论：⚠️ 候选发现 1条
- ① 纯确定性渲染模块，无状态，由 `_parse_enrichment` 真实调用。② code→中文解释映射完备且 fail-closed 有兜底，但兜底/模型分支把原始英文串直拼用户文案（见候选）。③ 块报告全中文化良好；`split` 理由拼接裸 rule_id（L152）在前端 pill 化背景下属可接受。④ 无 TODO。⑤ `segment_guide_blocks/_explain/block_report` 调用签名与 guide.py/guide_store.py 匹配。
- 候选发现1：用户面文案内嵌原始技术串｜证据 guide_report.py:67 `f"模型服务调用失败（{inner}）"` + L69 `未归类问题（{code}）`｜模型错误原文（限流/超时英文串）与未归类错误码直达用户块报告，违反 FL-D894/711 定下的"技术内容不出常规视图"口径｜建议：inner/code 仅在高级详情维度返回（报主线判定）
- 已知命中：FL-D894/711 主题关联（本条为新后端侧证据）

### fundlex/guide_diff.py
- 结论：✅ 无发现
- ① 纯确定性 diff 模块，经 `guide_store.diff_versions` 与 smoke 真实调用。② 无 except/兜底文案；同输入同输出（canonical dump sort_keys）。③ 输出含 source_sha256 meta 比较，属内部数据流，前端隐藏属 FL-D711 已治理。④ 无 TODO/死代码。⑤ `_flatten_rules` 处理 flat/nested 双形态与 guide_store._rule_entries 一致。

### fundlex/guide_text_diff.py
- 结论：✅ 无发现
- ① 收到 api.py:1193-1200 真实路由调用。② 三类守卫（422 缺参/不可读、404 跨 owner 不泄露、TextDiffUnavailable 内置源）齐全无静默吞错。③ 输出 filename/段落定位/前后文本均人读；diff_id 内部 UUID 属前端渲染键。④ 无 TODO。⑤ `compare_docx(...,left_filename=,right_filename=)`、`render_compare_document(...,side=)`、`render_merged_document(...,left_document=)` 三处签名实测匹配 compare 模块。已知命中：FL D660 系文档 L7646 记录。

### fundlex/guide_canary.py
- 结论：⚠️ 候选发现 1条
- ① 真实调用：finish 认证维（store L211）+ set_current_guide 启用门（L391），非孤立脚本。② 义务编译 except 限定五类异常并转结构化 fatal，无静默吞错；但对 store 侧吞错暴露 fail-open（见 store 候选）。③ fatal detail 全中文人读，无哈希/uuid。④ 无 TODO；"legacy" 为业务术语非死代码。⑤ 抽查 3 处：`route_operation(key,fact_status=,structure=None)`、`compile_obligations(document).records`、`evaluate(condition,facts).status` 签名全部匹配。
- 候选发现1：准入谓词双镜像漂移风险｜证据 guide_canary.py:70-72 手工复制 recall.py:2735-2745 `_declared_operation_key`（含 upper 语义简化版）｜两处谓词须恒等才能保住"准入=路由"承诺，任一侧改版不会编译失败，静默漂移即复发 FL-D648/660 族缺陷｜建议：抽取共享实现或加谓词等价性测试（报主线判定）
- 已知命中：FL-D648/FL-D660（谓词对齐与 canary 实施记录）
- 附注：`_CanaryFacts.fact_status` 为类级可变 dict（L48），当前只读无害，仅作观感备注不报。

### fundlex/guide_smoke.py
- 结论：✅ 无发现
- ① 真实调度：jobs.py:562-570 worker 解析成功后钩子 + tools/guide_quality_smoke.py CLI；非孤立。② jobs 钩子吞错有注释且仅 advisory 盖章不影响任务，属合理边界；`_baseline` except KeyError→None 语义明确。③ dimensions 全业务字段（规则数/规则 ID/段落号），无哈希直晒。④ 无 TODO。⑤ `review_version_footprint(store, job["owner"], job["guide_version_id"])` 调用签名匹配；review source 分槽纪律（不会覆盖 canary 盖章）与文档一致。
- 已知命中：FL-D659 系 footprint 冒烟实施记录（文档 L7276）

### fundlex/reconciliation.py
- 结论：⚠️ 候选发现 2条
- ① 确定性分类器在 ledger 投影后、交付门前真实注入（recall_pipeline.py:6504-6505），fail-closed 升级机制完整。② 无静默 except；replay 证据缺失均回落显式 MISS。③ 双语文本人读，无哈希；升级行 reason 拼机器态值（RECONCILIATION_LAYER_MISMATCH:PASS）属 minor。④ 见候选发现1/2（不可达分支与僵尸类）。⑤ `effect_proof_passed(proof,operation_id=,obligation_id=)` 签名实测匹配 generation/effects.py:428。
- 候选发现1：`MISS_REVIEW_PENDING` 分支不可达｜证据 reconciliation.py:242-244 行221已拦截 proof_passed，故行242 `not proof_passed` 恒真、行244永不执行｜声明的兜底类（含内置中英文案）实为死代码，出口测试也未覆盖该类（tests 无断言），公共类表与实际发射不一致｜建议：删除或补真发射路径
- 候选发现2：CLASS_TEXT 僵尸类｜证据 reconciliation.py:89-94 `MISS_COVERAGE_RESIDUAL`、:72-82 `MISS_EDIT_LOST` 无任何发射点（EDIT_LOST 有注释声明为线协议预留，COVERAGE_RESIDUAL 无说明且 FL-D653 文档列 9 类不含它）｜半成品公共分类，消费者若按 CLASS_TEXT 渲染将出现车库类无出处｜建议：为 COVERAGE_RESIDUAL 补与 EDIT_LOST 同款预留注释或移除（报主线判定）
- 已知命中：FL-D653/FL-D589/651 系（对账器实施记录）

结尾：批次小结
7 文件全部逐行读完（共1955行），canary/smoke/diff/reconciliation 均真实接入运行时而非孤立脚本，跨模块签名抽查全通过。新报 6 条候选：最值得注意的是两个条目——guide_store 的 canary 吞错→CERTIFIED fail-open 认证路径（可能与 FL-D648 防护语义冲突，需主线判定是否有意设计）与 reconciliation 的 `MISS_REVIEW_PENDING` 不可达死分支。哈希泄露主题（FL-D894）在本批后端仅见 API 传输字段，前端隐藏已由 FL-D711 治理，新见后端用户文案内嵌模型错误原文/code 一处（guide_report），建议纳入 711 后续根治范围。
