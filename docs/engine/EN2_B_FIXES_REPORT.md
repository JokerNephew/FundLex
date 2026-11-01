# EN2 · B 类 14 件裁决施工 完工报告（2026-11-01）

- 工作树：qa-audit-engine2（detached，施工区间 dfdd3ba → d1cf073，共 18 commit）
- 判词来源：总指挥「B 类 14 件逐件裁决（全部给出判词+施工令）」
- 配套：裁决表 docs/engine/EN2_B_RULINGS.md；A 类报告 docs/engine/EN2_A_FIXES_REPORT.md；双盲质检 docs/engine/en2_batches/QA_DOUBLEBLIND_B_FIXES.md

## 一、判词逐条断言表（自拍自检，引擎类 S2 口径）

| # | 判词 | 落地 | 证据 |
| --- | --- | --- | --- |
| B1 | FL-D921 结构完整性码永久留存+回归测试 | ✅ | `_purge_audited_failures`（claim_replay.py:1204-1236）+`_STRUCTURAL_INTEGRITY_CODES` 17 码（含质检并入的 CLAIM_VALIDATION_FAILED/UNKNOWN/CONFLICT）；回归 tests/test_fl_d921_audit_purge.py 5 例；commit ebbb317+b716bdf |
| B2 | FL-D922 最优先：解析为空抛 RoleConfigError 不回落 | ✅ | config.py `_resolve_key_env`（:130-142）接管 file/env 两路径+explicit_key 值非空；6 场景冒烟（异 host 落空报错/同 host 继承/显式 key/env 链路/replay）；定向 test_model_roles/settings 38 passed；commit 8a2d088 |
| B3 | FL-D923 canary 异常落 NEEDS_REVIEW+摘要入 issues_json | ✅ | guide_store.py:221-229 哨兵 canary（passed=False+error{type,note}）→ finish :750-752 天然落 NEEDS_REVIEW；冒烟 Exception→failed 报告；定向 guide_store/canary/quality_gate 25 passed；commit e012cbf |
| B4 | FL-D924a manifest 并入 rule_id/section + b 配对依 manifest+外来修订集成测试 | ✅ | docx.py:1566-1569 manifest 增键；html_view `_manifest_index` 返回权威配对对，`_pair_revisions` 防外来 id 借入+单侧内容保留；集成测试 tests/test_fl_d924_manifest_pairing.py 2 例（偶数外来ins/10号外来del 反奇偶形状）；定向 178 passed；commit 6afc165 |
| B5 | FL-D925 后端中文案+code附注；前端只按 code 映射；upload_guard 第一批 | ✅（后端侧闭合） | upload_guard 10 处 detail 中文化、error/error_code 键未动（冒烟验证 body）；orchestrator history detail 去原文（进日志）；guide_report zh 去内嵌原文/未归类码、code 落附注字段；测试锚 3 处随判词同步；commit c601e0b+55d9609。其余 reason 级（claim_replay/v2/v2_pipeline/pipeline report/reconciliation）属 code 附注维——delivery.business_reason 已中文映射，译层归 FL-D894 前端主线，已在质检档注明 |
| B6 | FL-D926 finally 写报告包 try/log | ✅ | pipeline.py:222-227；helper 直证 OSError 不外溢；test_pipeline 34 passed；commit 643b586 |
| B7 | FL-D927 两处 continue 记 rejected+reason | ✅ | semantic_contract context_load_failed/policy_or_rule_missing 落 rejected；冒烟+test_semantic_contract_v2 8 passed；commit c56f440 |
| B8 | FL-D930 等价测试先行；共享实现排后（recall.py 禁动） | ✅ | tests/test_fl_d930_predicate_parity.py 10 例（含全注册清单逐一比对）；首跑即抓到 canary None 崩溃漂移实锤，镜像补齐（不动 recall.py）；canary 套件 16 passed；commit eb4f4df |
| B9 | FL-D931 挪内置专用上下文+配 FL-D898 新形态指引实测 | ✅ | guide.py 献示句改负向约束+`_BUILTIN_GUIDE_COMPANION_NOTE` 仅经 companion_note 接线（jobs 不传、tools/build_builtin_guide 传）；GUIDE_PARSE_PROMPT_VERSION 升 v2（追踪诚实）；tests/test_fl_d931_companion_note.py 3 例（条款式新形态 3 组指引完整解析认证、prompt 无组数暗示）；guide 全线 70 passed；commit 904686b+0d6199c+b716bdf |
| B10 | FL-D932 展示层兼容映射不改历史账本 | ✅ | coverage.py plan-ledger satisfied→ALREADY_SATISFIED（与 state satisfied 同出口）；语义锚断言同步（test_generation_coverage.py）；交行门禁两态同属成功集无放行差（质检实证）；commit 16d4ae0+f6548d9 |
| B11 | FL-D933 一致性断言观测先行，改读取源排后 | ✅ | router.py:341-349 断言收窄到「路由停在注册默认 tier」的真实不变式（首轮过宽自纠 commit 4d6a320 留史）；test_generation_registry+escalation 绿；commit 006813b+4d6a320 |
| B12 | FL-D934 实现观测 telemetry（三态保留） | ✅ | trace_sink.record_event 通用观测通道+flags.observe_registry_shadow+recall 两行最小刀（shadow 保 legacy 结果、would_enable 落 JSONL，sink 关即 no-op）；冒烟两模式；commit da14cc1 |
| B13 | FL-D935(3/7) 删死形参+调用面同步（recall 仅签名一刀）+配测试证明 | ✅ | obligations.project 删 rules_by_id/artifact_text（recall_pipeline 2 点同步）、variants 删 rule（recall.py:7149 仅签名）；测试锚同签名同步（含质检抓回的 recovery_final_invariants:136）；定向 121 passed；commit dc0f64d+b716bdf |
| B14-1 | FL-D936(3) 锁表用完即清 | ✅ | ModelCassette.request_lock 引用计数 contextmanager，末位退出回收；并发共存锁不受影响；test_frozen_replay 绿；commit c1b3086 |
| B14-2 | FL-D936(8) 快照失败记 events/rounds_detail（技术观测维） | ✅ | _model_summary 新增 snapshot_errors（metrics/budget 各记 type 名），不进用户审计维；冒烟+test_guide 19 passed；commit bd9d820 |
| B15 | FL-D937 打包（1/4/5/6/8/11/12） | ✅ | RuleError taxonomy×11+锚同步（c63fc25）；v2 docstring 双轨（1804cd7）；QUALIFICATION_REVIEW_* 注册表（ffff96a，不入 PROMPT_VERSIONS 保已冻哈希）；user_agent 包元数据（2ec801c，五处收编）；FACT 前缀匹配（09c8d08）；EVAL 语义平面桥（1538aac，additive 不破旧键）；obligations 静态化（af3214d） |

## 二、全量回归证据（定版）

- 命令：`cd qa-audit-engine2 && PYTHONPATH=$PWD .venv/bin/python -m pytest tests -q -p no:cacheprovider`
- 定版结果（b716bdf 状态树）：**2678 passed / 143 skipped / 0 failed，13m54s**（/tmp/opencode/qa/en2_b_full_regression_final.txt）。
- 历史一跑（质检前状态树）：12 failed/2666 passed——12 红即质检抓到的 tests/test_recovery_final_invariants.py 漏同步，b716bdf 修复后定向复绿；如实留史，不以定版绿覆盖历史轨迹。
- 模型调用账本：本轮零真实模型调用（LLM_API_KEY unset；全部 ScriptedGateway/假网关/内存冒烟）。

## 三、纪律自检

- [x] 只在自己树施工（qa-base 未写）；recall.py 仅两处最小刀（签名同步一刀+shadow 遥测两行），冻结敏感区未动。
- [x] 增量 commit：18 个（判词号逐条落 message），无 30 分钟空窗；状态文件同步。
- [x] 新发现未自封编号；质检回流修复沿用被判词号（QA 疑点按「裁决复核」报告，不自作新号）。
- [x] 凭据不落盘（UA/config 路径只改来源，无任何密钥值变动）。
- [x] 全量回归一次（最终一轮）fc=0。
- [x] 双保险：A=本报告断言表（13+3 条目）；B=双盲质检（QA_DOUBLEBLIND_B_FIXES.md，⚠️ 有条件放行→闭环项全修）。

## 四、移交

- B 类 14 件：可批量验收（清单见上表）。
- 留存观察（非驳回级）：QUALIFICATION_REVIEW_* 注册未入 PROMPT_VERSIONS 映射属刻意保冻选项；FL-D925 剩余 reason 级译层由 FL-D894 前端主线覆盖；C 类 PROVIDERS 决策等用户。
