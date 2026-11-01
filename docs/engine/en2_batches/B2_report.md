# 批次B2回报（effects.py / coverage.py / flags.py）

来源：子审计员 ses_e69bd3d45（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B2报告

### fundlex/generation/effects.py（1250 行，已逐行全读）
- 结论：⚠️ 候选发现 1 条
- ① 单操作效果证明器：site 级 OPEN/PASS/FAIL + artifact_status，worst-of 聚合、fail-closed，状态机清晰，无异常。
- ② 各 except 均收窄为类型/键错误并走 UNPROVEN 兜底；`instantiate_slots/policy_text` 的 `except (AttributeError,TypeError): pass`（:684,:1047）是定义好的"不实例化则按原文"回退，非静默吞错，无异常。
- ③ `reason` 位为英文 snake_case（"verified site missing":1037 等），但下游 `delivery.failure_reason/business_reason` 有 failure_code 中文映射+中文兜底，FL-D894 面受控，无异常。
- ④ 无 TODO/FIXME/XXX/HACK，无死代码（全部私有函数均有调用点）。
- ⑤ 抽查 ≥4 处跨模块签名均匹配：`claim_replay._expected_after/_occurrence_positions`、`recall.instantiate_policy_text(rule_id,op,facts)->(str,list)`、`recall._g15_delay_continuation(inspection,location,operation)`、`coverage.effect_proof_passed(proof,operation_id=,obligation_id=)`。
- 候选发现1：occurrence_index 转换无防护易崩而非 fail-closed｜证据 effects.py:804,1058,1063 `int(site.get("occurrence_index", -1))`，对照 coverage.py:249-252 与 claim_replay._occurrence_index(:540) 均有 try 防护｜坏回放 JSON（该字段显式 null/非数值）使整场效果评估抛 TypeError 中断，不是判 UNPROVEN｜建议补同款防护，机制面报主线判定。
- 已知命中：FL-D224（planned_matches 仅存于 own+FAIL 分支，与已修复记录一致）；FL-D263（开放中，根因位置现 :584-624/:687-693 仍与记录吻合，无新恶化）；FL-D395、FL-D585、FL-D651、FL-D863、FL-D310（均为已实现/变更记录）。

### fundlex/generation/coverage.py（469 行，已逐行全读）
- 结论：⚠️ 候选发现 1 条
- ① 只读投影器，五终态；canonical（obligations.records）为主路径，targets/audit 为 legacy 兜底，未识别状态一律 UNRESOLVED，无异常。
- ② UNKNOWN/CONFLICT/旧格式都降级为 UNRESOLVED；唯一 except（:250）收窄，无伪造成功，无异常。
- ③ basis 为英文技术串（"claim_replay:…"、"site_evidence_missing"），属内部台账字段，用户文案经 business_reason 中文化，无异常。
- ④ 无 TODO；"legacy" 注释均为有意兼容设计（`_legacy_replay_provenance` 写死 0.1.0 与 docstring 一致），无异常。
- ⑤ 抽查：`effect_proof_passed` kwargs 匹配；"records" 与 `obligations.ObligationLedger.as_dict`(:202) 匹配；`recall_pipeline:6439 build_coverage_view(report)` 匹配；plan ledger "satisfied" 语义与 recall.py:9393/9425/9505 比对发现下述错标。
- 候选发现1：legacy 投影把 plan "satisfied" 误记 NOT_APPLICABLE｜证据 coverage.py:440-444 `status in ("satisfied","not_applicable")`→NOT_APPLICABLE；recall.py:9505 需要修改但无编辑时 ledger=satisfied 而 target.state 仍 needs_edit｜旧报告中"引擎判已满足"被错标为不适用（两态均不阻断，无门禁绕过），覆盖计数语义失真｜建议 satisfied→ALREADY_SATISFIED，机制面报主线判定。
- 已知命中：无（FL-D390/FL-D386 所指为 `fundlex/guide_generation/coverage.py` 的 sweep/requirement 聚合，与本文件无关）。

### fundlex/generation/flags.py（20 行，已全读）
- 结论：⚠️ 候选发现 1 条
- ① 单函数读取环境变量并白名单化三模式，未知值回退安全默认，无异常。
- ② 无 except 路径；"未知值→registry" 是显式 fail-safe，无异常。
- ③ 不产出用户可见文本，无异常。
- ④ 无 TODO；`STRATEGY_MODES`/`strategy_mode` 已导出（`generation/__init__.py:13,81`）。
- ⑤ 消费面核查：全仓仅 `recall.py:6809` 一处比较；`recall_pipeline.py:32` 导入后从未使用（死导入，属他线文件）；`generation/template.py` 文档与 registry 默认开启一致。
- 候选发现1：registry_shadow 声明后无任何消费方｜证据 flags.py:7 docstring 承诺"routing/telemetry computed for observation only"，但全仓仅 `recall.py:6809 strategy_mode()=="registry"` 一处判定，shadow 值等同 legacy 行为｜文档承诺的 shadow 观测期未实现，半成品 flag｜建议报主线判定（见下）。
- 已知命中：FL-D558（"flags.py 注释与默认行为矛盾"清理项；候选1 为其相邻新证据，未在 FL-D558 中记录死模式事实）。

### 批次小结
- 3 文件均 fail-closed 设计、签名一致、无 TODO/半吞错；effects.py 相关历史高危项（FL-D224/585/651）与代码现状吻合，FL-D263 仍开放且无恶化。
- 新候选 3 条均为低危：effects.py occurrence_index 防护缺口、coverage.py legacy 终态错标、flags.py registry_shadow 死模式。
- coverage.py 的 FL-D390/FL-D386 经核实指向 guide_generation/coverage.py，已从本文件已知命中中剔除。
- 附带观察（他线文件，不作主报）：`recall_pipeline.py:32` 存在 strategy_mode 死导入，供管线线审计留意。
- 全部 3 条新候选均为机制面低危，建议主线程一判定是否入册。
