# 细节问题与处理记录 · 附录 EN2（引擎审计2线，2026-11-01）

- 责任线：EN2 引擎审计2线（qa-audit-engine2 树 @ a96f118）
- 适用范围：覆盖矩阵 64 个 fundlex/*.py（generation/*、guide*、v2、docx、rules、obligations、delivery、frozen、html_view、checkpoints、application、models、observability、pipeline、proxy_headers、qualification、recall_prompts、reconciliation、recovery/*、regulatory/*、retention、selective、semantic_contract、stage_replay、trace_sink、upload_guard、upload_validation、user_model_connections、variants、workspace 等）
- 编号段：FL-D921~939（本册占用 FL-D921~937；FL-D938/939 预留未用，不归空号造假）
- 采证方式：子审计员逐行全读（11 批次回报原文收 docs/engine/en2_batches/），主审对全部高危与中危候选证据点亲自逐行复核（claim_replay:2343-2346、config.py:135-145/243-258、guide_store:208-222/740-752、html_view:376-441、docx.py:1554-1564/1542-1552、pipeline.py:210-222、reconciliation.py:216-244、effects.py:798-805、router.py:324-339、guide.py:460-467/744-762、upload_guard:244-320、coverage.py:434-447、v2_pipeline.py:262-285、variants.py:249-265、obligations.py:473-488、validators.py:50-577、semantic_contract.py:148-167、selective.py:604-615、roles.py:203-215、orchestrator.py:170-180、policies.py:80-90、frozen.py:45-64、ingestion.py:55-68、pdf_parser.py:70-78、trace_sink.py:190-200、guide_report.py:60-72、rules.py:99-131/720-730、template.py:426-434、canary:66-74↔recall.py:2732-2746、registry:100-150、types.py:50/148-150、user_agent 5 处、死代码调用点 grep 全仓验证等），证据行号均为 a96f118 实测。
- 去重：每文件已对集中文档 docs/DETAIL_ISSUES_AND_RESOLUTIONS.md 去重，已知命中在各批次档内标注，本册只收**新发现**。
- 处置纪律：本线不擅自改引擎；机制面问题一律“报主线判定”。

---

## FL-D921 claim_replay 语义审计 PASS 清障连带清除同义务结构完整性失败，verified 理论上可转真（严重，机制面）

- **发现日期**：2026-11-01（批次B1，主审复核属实）
- **问题与影响**：claim_replay.py:2341-2346 在审计证明到达后按「obligation 状态不是 PASS 的一律保留」重写 failures 清单：
  ```python
  failures[:] = [failure for failure in failures
                 if str((obligation_state.get(str(failure.get("obligation_id") or "")) or {}).get("state") or "") != "PASS"]
  ```
  此前逐 unit 记录的 CLAIM_OPERATION_SPAN_UNAUTHORIZED / OCCURRENCE_MISMATCH 等**结构完整性失败**（1733-1814 行入册处）与语义审计失败共用同一 obligation_id。义务被语义审计翻 PASS 时，同一键下的结构失败一并消失，verified 可转真——与「结构完整性永远不可被审计证明豁免」的 fail-closed 纪律相悖。
- **证据**：fundlex/generation/claim_replay.py:1720-1814（结构失败入册）、:2343-2346（清障无条件）。
- **处理方法（建议）**：清障仅限效果类失败码；CLAIM_OPERATION_SPAN_UNAUTHORIZED / OCCURRENCE_MISMATCH 等结构码永久留存。
- **状态**：新发现，报主线判定（机制面，涉及核验语义）。
- **下一步**：主线裁决后由引擎线修复并补回归测试。

## FL-D922 review 角色 api_key_env 未置值时静默继承 primary 凭据并绕过跨端点防护（严重，凭据安全）

- **发现日期**：2026-11-01（批次B10，主审复核属实）
- **问题与影响**：models/config.py `_merge_endpoint`（:135-138,145）：
  ```python
  api_key_env = str(entry.get("api_key_env") or "")
  if api_key_env:
      api_key = os.environ.get(api_key_env, "").strip()
  ...
  api_key=api_key or (base.api_key if base else "")
  ```
  配置写了 review 的 api_key_env 但环境变量未设置时，api_key 回落继承 primary 的密钥。而下行跨端点防护（:253-258）用 `review_entry.get("api_key_env")` 判定「用户显式配了密钥」=True，防护被绕过——primary 端点凭据被发往 review 配置指向的其他 host。
- **证据**：fundlex/models/config.py:135-145（回退继承）、:253-258（explicit_key 判空误判）。
- **处理方法（建议）**：api_key_env 解析为空时抛 RoleConfigError（与 :246-251“partially configured”同口径），不得回退继承。
- **状态**：新发现，报主线判定（凭据可能外发异端点，建议优先）。
- **验证**：静态复核成立；未做环境级重放（属修复验证范畴）。

## FL-D923 guide_store 金丝雀吞错 → 静默按 CERTIFIED 认证放行（严重，机質）

- **发现日期**：2026-11-01（批次B7，主审复核属实）
- **问题与影响**：_parse_enrichment 包裹金丝雀调用的 `except Exception: pass`（guide_store.py:210-222）吞掉 executability_report 自身崩溃，canary_report 保持 None。完成工序 :750-752：
  ```python
  qualification = (QUALIFICATION_NEEDS_REVIEW
                   if (canary is not None and not canary.get("passed"))
                   else QUALIFICATION_CERTIFIED)
  ```
  canary=None（崩溃路径）落入 CERTIFIED 而非 needs_review——认证门禁 fail-open（注释L32-43表明canary是认证维度而非纯咨询）。
- **证据**：fundlex/guide_store.py:210-222、:740-752。
- **处理方法（建议）**：canary 异常时 qualification 落 NEEDS_REVIEW（或显式 CANARY_ERROR 三态），并留异常摘要入 issues_json。
- **状态**：新发现，报主线判定（是否为有意设计须留痕）。

## FL-D924 html_view 修订清单两处与 docx 产出契约不一致（高，含用户可见回归）

- **发现日期**：2026-11-01（批次B8，主审复核属实）
- **a) manifest 分支丢 rule_id/section → 前端「规则 Gxx」标签静默消失**：
  - html_view.py:380-390：report.revision_manifest 存在即以 manifest 为修订索引来源。docx.py:1561-1564 写入 manifest 条目的键（edit_id/location/start/end/expected_old_text/replacement/template_id/del_id/ins_id）**不含 rule_id/section**；html_view._edit_info 对 manifest 条目吸不出来，_pair_revisions 拼出的清单 rule_id 恒为空串。对比一下 plan 重建分支（:391-403）用的 plan.edits 带 rule_id。
  - 影响：当前所有带 revision_manifest 的正式产物，用户审阅界面看不到「修改来自哪条规则」。
  - 证据：fundlex/html_view.py:380-390、fundlex/docx.py:1561-1564、html_view.py:432-434（`rule_id: info.get("rule_id","")`）。
  - 建议：docx manifest 写入时并入 rule_id/section，或投影时按 edit_id 回查 plan。
- **b) 修订奇偶配对假设与外来修订契约冲突**：
  - html_view.py:405-441 `_pair_revisions` 假定 del_id 奇数/ins_id=del_id+1；docx.py:1544-1547 注释明言「Foreign revision ids carry no parity guarantee」。allow_existing_revisions=True 的产物中，外来 ins/del 内容可能被错配或在清单丢失。
  - 建议：报主线判定——选择性审阅是否/何时覆盖 overlay 产物；若覆盖，配对逻辑须依赖 manifest.revision_ids 而非奇偶。
- **状态**：a) 新发现（组件间契约断裂，修法明确）；b) 报主线判定。

## FL-D925 FL-D894 联动：引擎侧用户可见技术串/内部码/原始异常外泄点清单（高，多证据合一册）

- **发现日期**：2026-11-01（多批次，主审逐点复核）——联动用户点名「页面中还有很多用户根本不需要看到的技术内容，比如规则哈希5335e401e840…」（USER_REQUIREMENTS_20261101_SESSION2.md:131 立 FL-D894，主线+V2线负责前端；本册为**后端/引擎侧泄露源**报告）。
- **证据清单（均用户可见路径，需翻译层确认覆盖度）**：
  1. claim_replay 失败 reason 英文技术句直进 report.failures（如 :1389/:1462/:1568/:1752 “an edit is bound to a FALSE applicability operation”）。
  2. v2.py `failure_reason`（:1521/:1526 英文 reason）→ v2_pipeline.py:280-281 exceptions 直出（V2_SCOPE_TEXT_MISMATCH 等机器码)。
  3. v2_pipeline 交付模式报告 markdown 含 record_sha256/plan_sha256/passed= 等内部字段（:60-69）。
  4. pipeline.py report.md 面向读报告者带 char 偏移、action_id、template_id、原始错误码（:32-41 节）。
  5. upload_guard 英文 message 直回用户的 HTTP 422/429/410（:251/:253 “too many uploads in progress”、:299-300 “RULESET_RETIRED”）；前端正则 grep 无对应 code 映射（app.js:477 回退 message）。
  6. guide_report._explain 把模型错误原文 inner / 未归类 code 拼进用户面中文案（:67 “模型服务调用失败（{inner}）”、:69 “未归类问题（{code}）”）。
  7. recovery/orchestrator.py:177 `detail = f"{type(exc).__name__}:{exc}"` 异常原文进 history summary → recall.py:9236 报告之回。
  8. reconciliation 升级行 reason 拼机器态串（RECONCILIATION_LAYER_MISMATCH:PASS）进用户面 holds（minor）。
- **影响**：后端源头不清，前端翻译层被追追打。属 FL-D894 后端侧专项子清单。
- **处理方法（建议）**：每条按「用户语 + code 附注（高级详情维度）」重构；upload_guard 属第一批施工对象（用户直见英文）。
- **状态**：新发现汇总，FL-D894 联动报告入；翻译覆盖面报主线判定。

## FL-D926 pipeline.py finally 块写报告失败可掩盖真实处理结果（中）

- **发现日期**：2026-11-01（批次B4，主审复核属实）
- **问题与影响**：process_document 的 try/finally（pipeline.py:216-222）：成功路径 `return report` 之前 finally 调 `_write_report_markdown`，磁盘写 OSError 将替换本应返回的 report 而向外抛异常——产物已交付却整体报失败。
- **证据**：fundlex/pipeline.py:216-222——finally 内无保护的 `_write_report_markdown(output_dir / "report.md", report)`。
- **处理方法（建议）**：finally 内的报告写包一层 try/log，或改为常规路径写。
- **状态**：新发现，建议修复批次顺手处理。

## FL-D927 semantic_contract 两处静默跳过与 fail-closed 纪律相悖（中）

- **发现日期**：2026-11-01（批次B4，主审复核属实）
- **问题与影响**：a) 构建模型上下文 `except Exception: continue`（:152-155），某 section 加载失败模型收不到该段而沉默无 rejected 记录，可能漏报目标；b) discover_for_rules 对 env 配置了但找不到的 rule_id `continue`（:363-366）无任何信号，语义发现静默无产出。
- **证据**：fundlex/semantic_contract.py:148-157、:358-367。
- **处理方法（建议）**：两处均记入 rejected 并附 reason（context_load_failed / policy_or_rule_missing）。
- **状态**：新发现（opt-in 特性，影响面受限），报主线判定。

## FL-D928 effects.py occurrence_index 裸 int() 转换缺防抑（中）

- **发现日期**：2026-11-01（批次B2，主审复核属实）
- **问题与影响**：:804/:1058/:1063 直接 `int(site.get("occurrence_index", -1))`；同工程 coverage.py:249-252 与 claim_replay._occurrence_index 都有 try 防护。回放缓存 JSON 该字段显式 null/非数值时整场效果评估抛 TypeError 中断，而非判 UNPROVEN。
- **证据**：fundlex/generation/effects.py:798-805 对比 coverage.py:249-252。
- **处理方法（建议）**：补同款防护判 UNPROVEN。
- **状态**：新发现，建议修复批次顺手处理。

## FL-D929 reconciliation MISS_REVIEW_PENDING 不可达死分支 + CLASS_TEXT 僵尸类（中）

- **发现日期**：2026-11-01（批次B7，主审复核属实）
- **问题与影响**：:221-228 `if proof_passed: ... return`；其后 :242 `if not proof_passed` 恒真，:244 `_finish("MISS_REVIEW_PENDING", ...)` 不可达（出口测试也未断言该类）。另 CLASS_TEXT 表中 MISS_COVERAGE_RESIDUAL（:89-94）无任何发射点且无预留注释（MISS_EDIT_LOST 有注释声明线协议预留），公开类表与实际发射不一致。
- **证据**：fundlex/reconciliation.py:216-244、:72-94。
- **处理方法（建议）**：删除不可达分支或补真发射路径；为 COVERAGE_RESIDUAL 补与 EDIT_LOST 同款预留注释或移除。
- **状态**：新发现，报主线判定（涉及公开分类表）。

## FL-D930 guide_canary 准入谓词双镜像漂移风险（中）

- **发现日期**：2026-11-01（批次B7，主审复核属实）
- **问题与影响**：guide_canary.py:70-72 `_declared_key` 手工镜像 recall.py:2735-2745 `_declared_operation_key`，两处谓词须恒等才能保住「准入=路由」承诺，任一側改版不编译报错，静默漂移将复发 FL-D648/FL-D660 族缺陷。
- **证据**：fundlex/guide_canary.py:70-72 docstring 明言 "Mirror ... (admission parity)"；fundlex/recall.py:2735-2745。
- **处理方法（建议）**：抽共享实现或加谓词等价性测试。
- **状态**：新发现，报主线判定。

## FL-D931 guide.py 通用解析指令残留“15-group”内置指引专属暗示（中，新指引质量门抵触）

- **发现日期**：2026-11-01（批次B6b，主审复核属实）
- **问题与影响**：_PARSE_INSTRUCTION（guide.py:465-466）写死 “The 15-group human reading of this guide is a reference only”。同一指令用于自定义新指引上传解析（jobs.py:539）——新指引往往非 15 组结构，对模型注入过时暗示，与用户“新指引能不能解析出合适规则”质量门（FL-D898 方向）抵触；内置指引实为 22 rules。
- **证据**：fundlex/guide.py:460-467。
- **处理方法（建议）**：移入内置专用上下文或删句。
- **状态**：新发现，报主线判定（属 FL-D898 质量门联动）。

## FL-D932 coverage.py legacy 投影把 plan “satisfied” 错标 NOT_APPLICABLE（低-中）

- **发现日期**：2026-11-01（批次B2，主审复核属实）
- **问题与影响**:legacy 投影 :440-444 `status in ("satisfied","not_applicable")` → NOT_APPLICABLE。recall.py:9505 要求修改但无编辑产出的场景 ledger=satisfied 而 target.state 为 needs_edit；老的报告中「引擎判已满足」被错标不适用（两态均不阻断，无门禁绕过），覆盖计数语义失真。
- **证据**：fundlex/generation/coverage.py:436-444 对比 recall.py:9505。
- **处理方法（建议）**：satisfied 走 ALREADY_SATISFIED（与 :437-439 同态）。
- **状态**：新发现，报主线判定（含旧报告语义兼容口径）。

## FL-D933 router.py 按 tier 重算 executor，无视 Registry 显式 spec.executor（低-中，机制面预留项）

- **发现日期**：2026-11-01（批次B4，主审复核属实）
- **问题与影响**：router.py:331-336 `executor = {DELETE:"delete",...}[tier]`；registry._op（:100,:124）允许显式 executor，将来注册遵 tier 推导以外的 executor 会被静默改写（当前全项对齐 tier 推导，无实际分歧）。
- **证据**：fundlex/generation/router.py:331-339、fundlex/generation/registry.py:100-134、types.py:50（OperationSpec.executor 字段）。
- **处理方法（建议）**：直接读 spec.executor 或加断言防放默改写。
- **状态**：新发现，报主线判定。

## FL-D934 flags.py registry_shadow 声明后无任何消费方（低，半成品 flag）

- **发现日期**：2026-11-01（批次B2，主审复核属实）
- **问题与影响**：docstring 承诺 shadow「routing/telemetry computed for observation only」，但生产全仓仅 recall.py:6809 判 `strategy_mode()=="registry"`；shadow 值走 legacy 分支，宣称的观测期未实现；仅测试引用。
- **证据**：fundlex/generation/flags.py:7-17、grep strategy_mode 全仓仅 1 生产消费 + 3 测试。
- **处理方法（建议）**：实现 shadow 观测或删三态第三态（属 FL-D558 相邻新证据）。
- **状态**：新发现，报主线判定。

## FL-D935 死代码合集（低，全仓 grep 无一调用点，逐项亲验）

- **发现日期**：2026-11-01（多批次，主审 grep/逐行复核）
- **清单**：
  1. validators.py:569-577 `_token_context`（全仓仅定义）。
  2. obligations.py:400-412 `_audit_verdicts` 死代码且与 coverage.py:119 `_iter_audit_verdicts`（活）重复双副本。
  3. obligations.py `project()` 形参 rules_by_id、artifact_text 仅签名出现（:474/:477），recall_pipeline.py:6433/6479 调用都传实参，函数体全不消费（scoped_rules/scope_gaps 有消费不误伤）。
  4. recovery/orchestrator.py:195-196 `failure_codes()` 孤儿 helper。
  5. frozen.py:57-59 `_path()` 内局部 `identity` 组装后未参与返回值。
  6. regulatory/ingestion.py:62-64 DOCX 标题合并后的死赋值（mutate 完即被 `document.blocks = document.blocks[consumed:]` 丢弃，且 for 首轮即 break）。
  7. variants.py:249 `authorized_variant_sentences(rule, ...)` 形参 rule 函数体未用，调用方 recall.py:7149 仍传（接口误导）。
- **处理方法（建议）**：删除或登记设计意图；3/7 涉及调用面，报主线判定。
- **状态**：新发现合集；建议清理批次统一处理。

## FL-D936 运行健壮性合集（低-中，逐项亲验）

- **发现日期**：2026-11-01（多批次，主审逐行复核）
- **清单**：
  1. recovery/policies.py:86 env `FUNDLEX_RECOVERY_*` 裸 `int(raw_value)`（与同文件 with_overrides:59-62 带 try 口径不一致）——运维配错抛无变量名的裸 ValueError。
  2. trace_sink.py:196-197 `_CAPTURE_TEXT` 模块级全局在 trace_document 内 `global` 改写，多线程 trace 打开有互相覆盖竞态窗口。
  3. frozen.py:47-63 `ModelCassette._locks` 类级字典按目录+digest 永久 setdefault 无清理，长跑 replay 进程内存缓增。
  4. models/roles.py:209-213 `metrics()` 就地改写 gateway 内部 event dict（`event["role"]=...` 改的是原 dict 引用），观测数据被读取方污染。
  5. regulatory/pdf_parser.py:73 `pymupdf.open` 无 close/try-finally，worker 长进程句柄与页面缓存累积泄漏。
  6. v2_pipeline.py:270-271 与 :282-285 同语义 review_blocked 反复（均执行同组 update，第一段冗余非不可达）。
  7. selective.py:612-615 `accept_all` 中 `_manifests_from_report(report)` 同一表达式调用两次（性能小项）。
  8. guide.py:746-761 `_model_summary` 两处 except Exception 吞 metrics/budget 快照失败，无 events 记录，排障时预算/账本缺失原因不可见。
  9. claim_replay.py:2575 残留扫描裸访问 `record.applicability.status`（同文件 :1379 一律 getattr 防御，此点未防御，applicability=None 时 AttributeError 中断整次扫描）。
  10. docx.py:478-481 `_max_revision_id_in_parts` `except DocxError: continue`、:1028-1030 `_max_revision_id` `except ValueError: continue` 防御性吞错（前置校验拦下，风险极低，观察级，建议注释说明依据）。
- **状态**：新发现合集；修复优先级建议 1/5/9 优先，其余随清理批次。

## FL-D937 治理一致性合集（低，逐项亲验）

- **发现日期**：2026-11-01（多批次，主审逐行复核）
- **清单**：
  1. rules.py:99-131 `validate_release_gate` 抛 12+ 裸英文 ValueError，与同模块 RuleError(code) taxonomy 不一致，上层不能按 code 归因。
  2. rules.py:725 `rs,re=right_positions[0],...` 局部变量遮蔽 stdlib re 模块（当前未用故无害，后续维护隐患）。
  3. rules_v2.py:190 注释引用不存在的常量 `TEMPLATE_VARIANT_UNNAPROVED`（实际 rules.py:655 `TEMPLATE_VARIANT_UNAPPROVED`）。
  4. v2.py:1 docstring “(evaluation only)” 与 v2_pipeline.py:305-327 正式交付分支（delivery_status=complete）矛盾。
  5. qualification.py:10-12,42 prompt 版本 `recall_qualification_review_v1` 与 SCHEMA 硬编码，未入 recall_prompts.PROMPT_VERSIONS 注册表治理。
  6. user_agent 硬编码 `fundlex/0.3.0` 共 5 处（models/config.py:54,159、model.py:153/186/244、user_model_connections.py:304）与 pyproject version=0.1.0 不一致。
  7. user_model_connections.py:20-35 PROVIDERS 内置模型清单（moonshot-v1-8k/32k/128k、glm-4-flash 等）可能过时（离线无法核供应商现行目录）；:38 类名 ConnectionError 遮蔽内建异常。
  8. validators.py:57 `FACT_BLOCKED_CODES` 含 `FACT_NOT_VERIFIED`，但 router.py:289 只把它作 fallback_reason 字符串前缀，永不产出 Finding.code，该分支恒不命中。
  9. components.py:2-3 docstring “**all** of its terms” 与 validators.py:478-480 `any(...)` “alternative wordings” 语义矛盾。
  10. template.py:431 `-120` 魔法收缩阈值无出处注释。
  11. artifact_review v3 产物 schema（actions/windows）与 tools/evaluation/development_gate_reconciliation.py:417-429 只比对的旧键 artifact_review_path 不同源（评测面引用断裂，EVAL 线接口）。
  12. obligations.py:378 `__import__("fundlex.applicability", ...)` 动态导入与文件头 :23 静态 import 同模块不一致。
- **状态**：新发现合集；多数为注释/命名/治理口径级，建议随顺手批次统一处理；1/4/8 建议报主线判定。

---

## 附：未编号定性结论（供主线参考，不占编号）

- FL-D938/FL-D939 保留未用——不制造空号。
- 交付完整性主场（delivery.py）与 docx/v2 主链路未发现「修改失败被报成功」新通道；B5 与用户投诉点（该修改但修改失败，FL-D897 立案）相关的直接引擎证据未在本次审计范围内复现，机制面大修归 recall-miss 线。
- canary/smoke/diff/reconciliation、trace_sink/retention/checkpoints、recovery/** 全部经 grep 确认为真实调度路径，非孤立脚本/死代码（与多个 historical「半成品」指控相反，本次定版为「接线完整」）。
- FL-D894 编号与集中文档的衔接：两批次回报均指出 DETAIL_ISSUES 文档对 FL-D894 无命中（当前最高 FL-D920 主文档内编号暂缺，最新立案表在 USER_REQUIREMENTS_20261101_SESSION2.md:131），建议主线在集中文档补登 FL-D894 本体，本册 FL-D925 作为其后端侧证据联动。
