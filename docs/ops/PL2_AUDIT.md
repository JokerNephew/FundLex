# PL2 平台审计线 — 逐文件审计报告（tools/** 全量 + tests/** 全量）

> 全覆盖矩阵：`/tmp/opencode/qa/COVERAGE_MATRIX_20261101.md`（矩阵实际由调度方置于 /tmp/opencode/qa/，非 docs/；本线依矩阵 PL2 行+用户 prompt 口径执行）。
> 审计基线：本工作树 `qa-audit-platform` @ `158475f`（QA 冻结快照）。
> 审计日期：2026-11-01。审计线：PL2 平台审计线。编号段：FL-D940~FL-D959（逐条见 [DETAIL_APPEND_PL2](../DETAIL_APPEND_PL2.md)）。
> 纪律留痕：全程只读代码/只读生产实况（sudo -n 只读、只读 DB 探针、journalctl 探测、git 只读）；写入仅限本树的 `docs/ops/PL2_AUDIT.md`、`docs/DETAIL_APPEND_PL2.md` 与 `/tmp` 下断点/证据文件；pytest 基线运行禁用缓存（`-p no:cacheprovider`、TMPDIR=/tmp），不污染仓库树；未修改任何业务代码。

## 0. 范围与对账（口径差异如实记录）

- 矩阵 PL2 行共 **280**（矩阵行与磁盘文件逐一 comm 对账，非估算）：
  - 本树（@158475f）矩阵内实际存在并可审 **228**（tools 37 + tests 191）；
  - **52 件仅存在于更新分支 `qa-backend-audit-20261101`(d2a9bc5)**（该分支已合并 user-config/onboarding/qa 修复，git ls-tree 逐一核实 52/52 均在该分支），本线已将该分支的 fundlex/tools/tests/frontend/workbench/guides/rules/pyproject.toml 用 `git archive` 无损物化至 `/tmp/opencode/qa/pl2_ref_tree/`（14MB），52 件以其为参照树逐字审计（批次 E，见 §3.5）；
- 用户 prompt 口径「tools/** deploy/ops/maintenance 等全部」另含矩阵未指派的 **20 件**（5 单元模板、2 部署 conf、local.ps1、codex-tmux.conf、research 10 件 ps1+README），按"宁多勿漏"补充签认，列为 §2.2/§2.4 标注「矩阵外」的行——不影响其它线范围；
- 本树 tests/ 191 件按 /tmp/opencode/qa/pl2_tests_part_00~03 四批逐件通读（批次 A/B/C/D），子批次结论经主线复核高危项证据行号。

## 1. 方法与实况核对（结论引用处已验证）

1. **逐文件通读**：280 矩阵行 + 20 矩阵外补审无一抽样；大文件（如 tests/test_final_validation_regressions.py 2316 行、tests/test_qa_20261031_regressions.py 1562 行）分段读全。
2. **生产五单元一致性**：`systemctl is-active/is-enabled` 五单元（recall-api/recall-worker/compare-worker/guide-worker/feishu）全 active+enabled；`check_publish_drift.sh --units` 证实装在 /etc/systemd/system 的五单元与本树模板**逐字节一致**；模板 7 项沙箱（NoNewPrivileges/PrivateTmp/ProtectHome/ProtectSystem=strict/ReadWritePaths=/var/lib/fundlex/RestrictAddressFamilies/UMask=0077）与本树 verify_sandbox_templates.sh 断言全对应；发布器 `check_api` 固定 `127.0.0.1:8010` 与 recall-api 模板 uvicorn 端口一致。
3. **发布器双向漂移**：仓库版(1624251a…)与本机根侧(cac65e32…)**不一致且根侧更新**（含 fc5f7f2 FL-D801 留存清理、FL-D800 sys.path 钉版、be5484d FeishuAppOnboarding、check_api 重试）——本树 HEAD 早于这些修复分支，属等待合并回填的方向性差异（FL-D950，观察项，非本树缺陷）；已实测 `journalctl --since <ISO-TZ>` 本机 rc=1，复现 f6e33f3 修复动机。
4. **生产 DB 只读探针**（fundlex_ops，2026-11-01 16:15，仅 SELECT/SHOW）：users=118，cleanup 白名单前缀测试账号=43；其 compare/gg/integrations 相关行当前=0；`deploy-verify-%` 残留=0（FL-D941/946 的"当前无实际残留"证据）。
5. **覆盖空洞静态分析**：126 个 fundlex 模块中 95 个被 tests 精确 import；无直接测试的 31→28 项主要是经 fundlex.api 等聚合入口间接覆盖的模块，但 **fundlex.recovery.\*（4 模块 687 行）与 fundlex.integrations.feishu.service_main（五服务之一的入口）确无直接单元测试**（FL-D959）。
6. **pytest 全量基线**：本树全量后台运行（环境 /home/opencode/fundlex/.venv，禁用缓存/TMPDIR 隔离），结果见 §3.6。

## 2. tools/** 逐文件签认（57 件 + 矩阵外 21 件）

### 2.1 根级（5）

| 文件 | 签认 | 发现/注 |
| --- | --- | --- |
| tools/build_builtin_guide.py | ✅ | 注：未显式传 `--max-completion-tokens` 也用默认值覆盖 FUNDLEX_MODEL_MAX_OUTPUT_TOKENS（FL-D947 附属）；exit 0/1/2 语义与 docstring 一致 |
| tools/compare_frozen_replay.py | ✅ | 注：report.json 缺失时非结构化 traceback；summaries JSON 每次静默覆写（生成物口径，无伤） |
| tools/replay_stage.py | ✅ | 只读回放+错误码 2 结构化，方向正确 |
| tools/validate_frozen_case.py | ✅ | RECORD_EXISTS 防覆盖、HEAD/dirty 双冻结校验、凭据白名单落盘、回放禁网 monkeypatch 均到 |
| tools/local.ps1 | ✅ | Windows 退役机遗留（矩阵外补充）；无破坏面 |

### 2.2 deploy/（25）

| 文件 | 签认 | 发现/注 |
| --- | --- | --- |
| tools/deploy/check_publish_drift.sh | ✅ | 只读+exit 0/1/2 分明；当日实测可用 |
| tools/deploy/cleanup_test_accounts.sh | ⚠️ | **FL-D941**（删表不全/注释口径漂移/LIKE 前缀误伤面）；dry-run 默认+admin 排除方向正确 |
| tools/deploy/cloud_task_run.py | ✅ | cloud-run- 前缀在白名单内；注：cleanup 失败仅打印不非零（并入 FL-D946 口径）、/tmp 固定名可撞名（注级） |
| tools/deploy/cloud_verify.py | ⚠️ | **FL-D946**（白名单外前缀+cleanup 失败仍 0+隧道断言陈旧+seal 真实模型竞态+dir() 死代码） |
| tools/deploy/deploy_recall.py | ⚠️ | **FL-D940 高危**（就地覆写生产+无沙箱同名单元+无回滚；docs/tests 零引用，死而危险） |
| tools/deploy/diff_status.py | ⚠️ | **FL-D943**（硬编码 D:\ 死脚本，现机不可运行） |
| tools/deploy/fundlex-compare-worker.service.template | ✅ | 与 /etc 实物一致；exusExecStart=worker 与发布器 import_check 对应（矩阵外） |
| tools/deploy/fundlex-feishu.service.template | ✅ | 同上；service_main 导入校验对应（矩阵外） |
| tools/deploy/fundlex-guide-worker.service.template | ✅ | 同上（矩阵外） |
| tools/deploy/fundlex-publish.sh | ✅ | 事务化 rename/--dry-run/--commit 脏树拒发/flock/symlink 拒/三重哈希/隔离 import/systemd-run schema/init/双延迟健康检查+NRestarts 基线/journal 敏感日志不回显/recovery-failed 留现场——防护完备；注：`elif [ "$status" != 0 ]` 字符串比较（数字无差）；DIRS 含 docs/tests 进入生产树（口径自洽） |
| tools/deploy/fundlex-recall-api.service.template | ✅ | 与 /etc 一致；8010 与 check_api 一致（矩阵外） |
| tools/deploy/fundlex-recall-worker.service.template | ✅ | 与 /etc 一致（矩阵外） |
| tools/deploy/migrate_baseline.py | ✅ | Windows 迁移期只读核验脚（docs 零引用，一次性留档，注级） |
| tools/deploy/migrate_data.py | ✅ | 注：EXPECTED=514 陈旧（现 515，仅 NOTE 不失败，FL-D947） |
| tools/deploy/migrate_fixup.py | ✅ | 白名单上传+逐件 sha256 复核，失败即非零 |
| tools/deploy/migrate_verify.py | ✅ | 只读核验 |
| tools/deploy/migrate_verify_full.py | ✅ | 只读核验，批量分块防命令行溢出 |
| tools/deploy/migrate_workspace.py | ⚠️ | **FL-D944**（远端 rm -rf 无目标白名单/确认；失败残留 /var/tmp staging） |
| tools/deploy/migrate_workspace_diff.py | ⚠️ | **FL-D945**（自称 read-only 实则远端覆盖本地无备份） |
| tools/deploy/nginx-upload-limits.conf.template | ✅ | 与应用默认口径注释自洽（FL-D288 体系，矩阵外） |
| tools/deploy/production-deployment.conf | ✅ | 五服务/8010//var/lib/fundlex 与模板一致（矩阵外） |
| tools/deploy/publish_workspace.sh | ✅ | 仅包装 root 侧发布器、无隐式树、用法强制 |
| tools/deploy/push_with_token.sh | ✅ | token 不打印不入 argv、mktemp askpass+trap 清理；注：-u 直推当前分支无确认（注级） |
| tools/deploy/remote_workspace_check.py | ✅ | 只读远端核验+显式 venv 选择 |
| tools/deploy/setup_fundlex_ops.sh | ⚠️ | **FL-D942**（表级 DELETE 靠客户端自律；注释口径漂移并入 FL-D941） |
| tools/deploy/ssh_probe.py | ✅ | 凭据仅 env 读不打印；注：AutoAddPolicy 接受任意 host key（口令时代 recon 号径，注级） |
| tools/deploy/verify_sandbox_templates.sh | ✅ | mktemp 副本验 systemd-analyze+7 项 sandbox grep，不碰 /etc |

### 2.3 ops/（6）与 maintenance/（1）

| 文件 | 签认 | 发现/注 |
| --- | --- | --- |
| tools/ops/codex-tmux.conf | ✅ | destroy-unattached off 等与 verify 脚本断言一致（矩阵外） |
| tools/ops/codex_persistent.sh | ✅ | daemon 优先+tmux 兜底、close/gc 双 --force、专用 socket、dry-run——设计周密；注：grep codex TUI 文案绑定版本（注级） |
| tools/ops/configure_codex_full_access.py | ✅ | 冲突键拒绝+只许两键变更验证+备份 600+原子替换 |
| tools/ops/fundlex_backup.py | ✅ | 0700/600、defaults-extra-file 即用即删、symlink 拒、存在即失败、verify 明示不导库、未 quiesced 告警；注：tar 成员校验未拒 device node（自产归档口径，注级）；独立 AUTH DB 明示不受理（自陈边界） |
| tools/ops/install_codex_persistence.py | ✅ | 半成品块拒绝+逐项差异备份+原子替换+回滚 |
| tools/ops/verify_codex_persistence.py | ✅ | fake binary PTY 挂断验证，无模型调用+kill-server 清理 |
| tools/maintenance/prune_orphan_objects.py | ⚠️ | **FL-D948 高危（dry-run 默认缓解）**：referenced_keys 漏 compare_*/gg_* object_key 4 处 |

### 2.4 research/（7 件矩阵内 py + 11 ps1 + README 矩阵外）

tools/research/README.md 已明示"一次性研究脚本、非产品代码、本机路径假设、勿盲目批量运行 PowerShell"——以下签认以此为口径。

| 文件 | 签认 | 发现/注 |
| --- | --- | --- |
| tools/research/_batch_scan.py | ✅ | 只读扫描 funds/*.pdf（输入现不存在——一次性口径免于追责） |
| tools/research/_m0_scan.py | ✅ | 只读扫描+写 _m0_evidence.md/_variant_census.md 于仓根（README 自陈） |
| tools/research/_ooxml_census.py | ✅ | 只读扫描+写 _ooxml_census.md |
| tools/research/_ooxml_deep.py | ✅ | 只读扫描 |
| tools/research/_probe2.py | ✅ | 只读抽查 |
| tools/research/_probe_contracts.py | ✅ | 只读抽查 |
| tools/research/_variant_lib.py | ✅ | 只读变体枚举 |
| tools/research/README.md | ✅ | 免责口径声明有效、准确（矩阵外） |
| tools/research/_av.ps1 / _sec.ps1 / _wdiag.ps1 | ✅ | 只读环境侦察写日志（3 件，矩阵外） |
| tools/research/_cleanup.ps1 | ✅ | 仅删 ~$ 锁文件与自身 scratch（矩阵外） |
| tools/research/_convert.ps1 / _convert_pdf2word.ps1 / _test_one.ps1 / _test_three.ps1 / _t6.ps1 | ✅ | Word COM PDF→DOCX，skip 已存在目标不覆盖（5 件，矩阵外） |
| tools/research/_wtmpl.ps1 | ⚠️ | **FL-D949**：无条件 Kill 全部 WINWORD（README 免责已载，注级定级"低"） |

**tools/ 小结**：77 件（57 件磁盘全量，其中矩阵内 37 + 矩阵外 20）——67 ✅ / 10 ⚠️，登记 FL-D940~D950（11 条，含 2 高危、多条注级并入）。

## 3. tests/** 逐文件签认（191 本树 + 52 新分支版，含 2 件 tools/ 基准工具）

> 视角：失效引用（指向已删模块/文案/fixture）、覆盖空洞（静默 skip/无关键断言）、脆弱测试（时序/环境/CWD 依赖）、危险操作（毁表/写仓库/凭据）、陈旧（死代码/未使用导入）。
> A(50)/B(46)/C(48)/D(47+1)/E(51) 五批逐件通读；⚠️ 行证据均回验。

### 3.1 批次 A（tests/browser/* + test_ab 系 ~ test_de 系，50 件）

| 文件 | 签认 | 类别 |
| --- | --- | --- |
| tests/browser/__init__.py | ✅ | — |
| tests/browser/test_frontend_v2.py | ✅ | 前端文案/id 引用核验存在；≤350ms 固定 wait 可接受 |
| tests/browser/test_guide_generation.py | ✅ | guide_generation.js 控件/文案核验存在 |
| tests/browser/test_v1_frontend_remediation.py | ✅ | v1 元素引用存在；≤700ms wait 可接受 |
| tests/browser/test_workbench.py | ⚠️ | 脆弱：:429 三循环 wait_for_timeout(10500) 硬耦合 10s 后台轮询（FL-D951） |
| tests/guide_generation_fakes.py | ⚠️ | fake 漂移（FL-D953 高危，详见批 D 复核） |
| tests/test_absent_delete_coverage.py | ⚠️ | 脆弱：funds_word 语料布局硬编码（FL-D955） |
| tests/test_api_store.py | ⚠️ | 脆弱：:241 sleep(1.3) vs lease_seconds=1（FL-D956） |
| tests/test_append_applicability.py ~ test_audit_applicable_policy.py（4 件） | ✅ | 含 recall.py 私有符号核验存在 |
| tests/test_auth*.py（4 件：auth/auth_last_admin/auth_register/composite_bearer_boundary） | ✅ | — |
| tests/test_atomic_orphan_tail.py | ✅ | — |
| tests/test_backup_tools.py | ✅ | fundlex_backup.py 全覆盖 |
| tests/test_budget_preflight.py | ✅ | — |
| tests/test_build_labels_v2_20261028.py | ✅ | 工具与产出核验存在 |
| tests/test_claim_*.py（3 件） | ✅ | — |
| tests/test_class_*.py（4 件） | ✅ | — |
| tests/test_compare_algorithm*.py / test_compare_api.py / test_compare_auth.py / test_compare_batch.py（4 件） | ✅ | — |
| tests/test_compare_corpus.py | ⚠️ | 脆弱：语料布局硬编码（FL-D955） |
| tests/test_compare_merged_render.py / test_compare_remediation_boundaries.py / test_compare_render.py / test_compare_selection.py / test_compare_selection_writer.py / test_compare_store.py / test_compare_worker.py（7 件） | ✅ | — |
| tests/test_compare_selection_api.py | ⚠️ | 危险：MySQL DROP fixture 仅 env 门控（FL-D952） |
| tests/test_compare_system_review.py | ⚠️ | 危险：同 FL-D952 |
| tests/test_composite_bearer_boundary.py | ✅ | — |
| tests/test_composite_slice_delivery.py | ✅ | — |
| tests/test_condition_tri_state.py | ✅ | — |
| tests/test_db.py | ✅ | — |
| tests/test_db_mysql.py | ⚠️ | 危险：MySQL DROP fixture（FL-D952）；注：:241-243 `never-log-this` 假凭据无泄露 |
| tests/test_delete_applicability.py | ✅ | — |
| tests/test_delivery_e2e.py | ✅ | delivery_e2e allow_real_model 守卫匹配 |
| tests/test_delivery_summary.py | ✅ | — |
| tests/test_dependency_lock.py | ✅ | pyproject/uv.lock certifi 下限双向一致（防漂移正例） |

### 3.2 批次 B（test_deploy ~ test_ge 系，46 件）

| 文件 | 签认 | 类别 |
| --- | --- | --- |
| tests/test_deploy_publisher.py | ✅ | 发布器真实断言、写限 tmp |
| tests/test_development_gate_reconciliation.py | ✅ | — |
| tests/test_docx_overlay_contract.py | ⚠️ | 空洞：:286-303 skipif 静默+p159 硬编码（FL-D957/D958） |
| tests/test_docx.py / test_docx_structures.py | ✅ | — |
| tests/test_downloaded_artifact_verification.py | ✅ | — |
| tests/test_duplicate_copy_scope.py | ⚠️ | 脆弱：:10 CWD 相对路径未 __file__ 锚定（FL-D955，全仓孤例之一） |
| tests/test_effect_semantic_residual.py / test_evaluation_matching.py | ✅ | — |
| tests/test_facts_*.py（3 件）/ test_fee_*.py（3 件） | ✅ | — |
| tests/test_feishu_integration.py / test_feishu_oauth_api.py | ✅ | 卡片/绑定文案与 api.py/cards.py/service.py 逐一核对一致 |
| tests/test_ff4d749_gate_closure.py | ✅ | — |
| tests/test_final_validation_regressions.py | ✅ | 2316 行分段读全 |
| tests/test_fingerprint_engine_build.py | ✅ | — |
| tests/test_first_batch_label_20261028.py | ⚠️ | 空洞：:132-135 BH06 语料缺失即 pytest.skip（FL-D958） |
| tests/test_fl_d119_guards.py / test_fl_d286_api_safety.py | ✅ | — |
| tests/test_frontend_entry.py | ✅ | compare.html id 与路由核对一致 |
| tests/test_frozen_replay.py | ✅ | — |
| tests/test_fullwidth_heading_guard.py / test_fuzzy_clause_unterminated_paragraph.py | ✅ | — |
| tests/test_g02_g04_occurrence.py | ✅ | — |
| tests/test_g06_absent_coverage_delete.py | ⚠️ | 脆弱：:25 字节偏移 184-204 语料耦合（FL-D957） |
| tests/test_g08_partial_policy.py | ⚠️ | 脆弱：:10 sys.path.insert 污染（FL-D959）+:22 p292 硬编码（FL-D957） |
| tests/test_g08_same_sentence_exemption.py | ✅ | — |
| tests/test_g09_replay_proof.py | ✅ | — |
| tests/test_g11_class_prefix.py | ⚠️ | FL-D959 sys.path + FL-D957 p243 |
| tests/test_g11_split_target.py | ✅ | — |
| tests/test_g12_allocation_variant.py | ⚠️ | FL-D959 + FL-D957 p165 |
| tests/test_g12_list_prefix.py | ⚠️ | FL-D959 + FL-D957 p295 |
| tests/test_g12_semicolon_variant.py | ⚠️ | FL-D959 + FL-D957 p244 |
| tests/test_g14_fee_rate_variant.py | ⚠️ | FL-D957 p209 |
| tests/test_g15_business_notice.py / test_g15_cross_paragraph_delay.py / test_g15_payment_delay_boundary.py | ✅ | — |
| tests/test_g16_clause_duplicate_effect.py / test_g17_usage_site_closure.py | ✅ | — |
| tests/test_g22_variant_span.py | ⚠️ | FL-D959 sys.path + FL-D957 p955/0-39 |
| tests/test_generation_claim_replay.py / test_generation_coverage.py / test_generation_registry.py | ✅ | — |

### 3.3 批次 C（test_generation_router ~ test_remediation_engine_approval，48 件）

| 文件 | 签认 | 类别 |
| --- | --- | --- |
| tests/test_generation_router_escalation.py / test_generation_template.py / test_generation_tier1.py / test_generation_validators.py / test_generation_verify.py | ✅ | — |
| tests/test_guide_api.py / test_guide_generation_mysql_schema.py / test_guide_generation_transport_pause.py / test_guide_generation_vector.py / test_guide.py / test_guide_remediation_config.py / test_guide_remediation_eligibility.py / test_guide_remediation_worker_engine.py / test_guide_store.py | ✅ | worker_engine 的 Event.wait 有界 10-15s 为仓内良好范式 |
| tests/test_guide_generation.py | ⚠️ | 空洞+脆弱：:94-103 CWD 相对 PDF fixture+静默 skip（FL-D955）；:1337 线程+sleep(.03)（FL-D956）；:760-798 circuit_wait_s=0.01（FL-D956） |
| tests/test_guide_generation_pipeline.py | ✅ | — |
| tests/test_hard_fact_veto.py / test_inventory_*.py（2 件）/ test_joint_compose.py / test_merged_definition_append.py / test_missing_group_components.py | ✅ | — |
| tests/test_model.py / test_model_roles.py | ✅ | — |
| tests/test_multicomponent_satisfaction_guards.py / test_multiline_quote_verification.py | ✅ | — |
| tests/test_object_gc.py | ✅ | 注：未覆盖 compare/gg 引用免删反例（FL-D948 测试缺口佐证） |
| tests/test_obligations.py / test_observability.py / test_open_obligation_recovery.py | ✅ | — |
| tests/test_operation_execution_closure.py | ⚠️ | 脆弱：:528-577 真线程+sleep(.03) 并发断言（FL-D956） |
| tests/test_p6_*.py（6 件）/ test_pilot_compare.py | ✅ | — |
| tests/test_pipeline_failure_metering.py / test_pipeline.py | ✅ | — |
| tests/test_policy_clause_number_preservation.py / test_qualification_evidence.py | ✅ | — |
| tests/test_recall_core.py | ✅ | 1883 行读全；28+ 其它测试的 helper 源（跨测试 import 观察，FL-D959 末项） |
| tests/test_recall_integration.py | ✅ | — |
| tests/test_recall_pipeline.py | ⚠️ | 陈旧：:1390 函数内未使用 import ModelResult（FL-D959） |
| tests/test_recovery.py / test_recovery_final_invariants.py | ✅ | recovery 包 re-export 与 router 枚举核对一致 |
| tests/test_remediation_append_canonical.py | ✅ | — |
| tests/test_remediation_engine_approval_binding.py | ⚠️ | 陈旧：:17 未使用 import guide_fingerprint（FL-D959） |

### 3.4 批次 D（test_remediation_engine_approved ~ test_workspace_api + fakes，47 件）

| 文件 | 签认 | 类别 |
| --- | --- | --- |
| tests/test_remediation_engine_approved_delete_offsets.py / test_remediation_engine_delivery_classifier.py / test_remediation_engine_semantic_audit_site.py | ✅ | — |
| tests/test_remediation_engine_summary_scope.py | ⚠️ | 脆弱：:24 绝对机器路径 fixture /home/opencode/fundlex/… 换机即静默归零（FL-D955） |
| tests/test_remediation_engine_targeting_pagination.py / test_remediation_tasks_delivery.py / test_remediation_tasks_feishu.py | ✅ | feishu 文案与 service.py:1194 一致 |
| tests/test_replace_clause_closure.py / test_replay_pagination.py | ✅ | — |
| tests/test_replay_site_provenance.py | ⚠️ | 脆弱：:183 CWD 相对 open()（FL-D955） |
| tests/test_revision_api.py | ⚠️ | 空洞 高危：:20 gitignored var/ 门控，12 用例静默全 skip；:71 硬编码 revision_count==17（FL-D954） |
| tests/test_rule_recognition.py | ⚠️ | 脆弱：:100 CWD 相对 Path('rules/rules_v1.json')（FL-D955） |
| tests/test_rules_catalogue.py / test_rule_scope*.py（3 件）/ test_run_store_fencing.py 前段 | ✅ | — |
| tests/test_run_store_fencing.py | ⚠️ | 危险：:203-204 MySQL DROP 业务表（env 门控，FL-D952） |
| tests/test_runtime_budget_observation.py | ✅ | — |
| tests/test_selective.py | ⚠️ | 空洞 高危：:62-63 同 var/ 门控 ~15/18 用例静默 skip（FL-D954） |
| tests/test_semantic_contract_v2.py / test_semantic_evidence.py / test_single_delete_orphan_connector.py / test_split_definition_append.py / test_strategy_consistency.py / test_superset_target_dedupe.py / test_sweep_*.py（4 件） | ✅ | — |
| tests/test_targeting*.py（2 件）/ test_tasks_api.py（1007 行读全）/ test_trace_sink.py / test_tracked_changes_overlay.py | ✅ | — |
| tests/test_upload_guard.py | ⚠️ | 脆弱：:101-107 0.01s 超时 vs 0.05s 延迟时序（FL-D956） |
| tests/test_upload_validation.py / test_v2_actions16.py / test_v2_artifact_pipeline.py / test_v2_artifact_review.py / test_v2_engine.py（919 行）/ test_v2_evaluation.py / test_v2_matching.py / test_v2_release.py / test_v2_workbench.py / test_v3_delivery_review_gate.py / test_validator_hard_gate.py | ✅ | capabilities 契约与 api.py 一致 |
| tests/test_workspace_api.py | ✅ | frontend/workspace.js 11 个元素 id 全在 |
| tests/guide_generation_fakes.py（随批 D 复核） | ⚠️ | **FL-D953 高危**：预制响应缺 guide_batch_resolve/guide_repair/guide_topic_coverage 三任务类型→裸 {} 静默返回（discovery.py:622/repair.py:75/coverage.py:205 真实路径会调）；identity() 缺 6 字段（真实 model_router.py:324-351）。现状不炸靠各测试子类自行拦截+管线仅消费个别键——属隐性漂移风险而非现行红测 |

### 3.5 批次 E（d2a9bc5 新分支版 52 件，参照树 /tmp/opencode/qa/pl2_ref_tree/）

> 主复核说明：批 E 子批的两项「失效引用」经主线用 `git ls-tree d2a9bc5` 复核为**物化伪影**（references/ 与 funds_word/ 未进物化树，但分支树实际存在 `references/source/v4存量…勘误版.docx`、`references/fee-rule-v2/original/*`、`funds_word/基金合同第一批/广发弘利3个月…docx` 等 547+33 件），故 test_guide_parse_quality 等判 **✅（false positive 已排除）**；其余 ⚠️ 项证据行号主线逐一重验通过。新增证据全部并入既有家族编号（编号段无剩余槽位），不产生新编号。

| 文件 | 签认 | 类别 |
| --- | --- | --- |
| tests/browser/test_frontend_fixes.py / test_guide_history.py / test_tracked_upload.py | ✅ | — |
| tests/browser/test_guide_diff.py | ⚠️ | 危险：:51-63 `_ensure_v2_dist` 在测试内跑 `vite build` **写仓库 frontend/dist/**（mtime 新于产物即重建；依赖 node_modules 在场、600s 超时）（FL-D952-b） |
| tests/browser/test_compare_scroll_perf.py | ⚠️ | 危险：:40 默认 `OUT_DIR="var/qa-compare-scroll-perf"`（相对仓库），:337-339 测试把 JSON 结果**写仓库 var/**（可用 COMPARE_PERF_OUT 环境缓解）（FL-D952-c） |
| tests/test_compare_polling_gate.py | ⚠️ | 脆弱：:12 `Path("frontend/compare.js")` CWD 相对源码钉板（FL-D955） |
| tests/test_review_render_index.py | ⚠️ | 脆弱：:15 同型 `Path("frontend/app.js")` CWD 相对（FL-D955） |
| tests/test_fl_d692_scorer_classfold.py | ⚠️ | 脆弱（注级）：:22 `sys.path.insert(0, "tools/evaluation")` 相对插入（FL-D959） |
| tests/test_fl_d608_definition_group_chain.py | ⚠️ | 口径：同依赖 funds_word 语料（:26-27 ROOT 锚定✓）但**无 skipif/守卫**，语料缺失即硬 FileNotFoundError；与下两项的 skipif 静默跳过形成三方口径不一（FL-D958） |
| tests/test_docx_a3_regressions.py / test_compare_full_body_replacement.py | ⚠️ | 空洞（轻）：:330 / :490 funds_word 依赖均 skipif 静默跳过（FL-D958） |
| tests/test_qa_worker_20261031.py | ⚠️ | 脆弱：:337-339 sleep(0.05) 轮询（有 15s deadline 缓解）；:440-442 dead_pid 存在理论 PID 复用竞态；:427 写系统 /tmp（finally 兜底）（FL-D956） |
| tests/test_guide_parse_quality.py | ✅ | 批内初报"fixture 不在树"，主线复核为物化伪影，分支 git 树 fixture 实测存在（false positive 排除留痕） |
| tests/test_absent_variant_refutation.py / test_clause_residual_realization.py / test_compare_sdt_locations_and_trailing_delete.py / test_compare_tracked_changes.py / test_delivery_outcome.py / test_document_compact_cache.py / test_docx_single_read.py / test_docx_tracked_input.py / test_edit_summary.py / test_export_user_package.py | ✅（10） | — |
| tests/test_feishu_app_onboarding.py | ✅ | 与 onboarding/service 符号核对一致 |
| tests/test_fl_d573_fragment_bounds.py / test_fl_d585_excised_by_replace.py / test_fl_d587_g08_variant.py / test_fl_d588_g08_variant_authorization.py / test_fl_d690_residual_clause_repair.py / test_fl_d790_append_window.py / test_fl_d791_sentence_boundary_probe.py | ✅（7） | — |
| tests/test_guide_canary.py / test_guide_diff.py / test_guide_diff_api.py / test_guide_quality_gate.py / test_guide_smoke.py / test_guide_text_diff_api.py | ✅（6） | — |
| tests/test_loop6_repairs.py / test_model_settings.py / test_plan_output_guard.py / test_plan_rejected_replay_sites.py | ✅（4） | — |
| tests/test_qa_20261031_regressions.py | ✅ | 1562 行分段读全 |
| tests/test_reconciliation.py / test_recovery_conservatism.py / test_retention.py / test_revision_view_cache.py / test_store_query_budget.py / test_user_configuration.py / test_user_model_connections.py / test_variants.py | ✅（8） | — |
| tools/guide_parse_benchmark.py | ⚠️ | 门禁盲眼：--engine-smoke N 产出行只进 report，:183-191 `overall_ok` 只 AND 解析通道分，smoke 任务失败（如 task_create_4xx/not_certified）仍 exit 0——简称"引擎冒烟不计入门禁"（FL-D958 末项）；另 :102 依赖 references/fee-rule-v2/original（分支树实测存在✓） |
| tools/guide_quality_smoke.py | ✅ | — |

**批 E 小结**：52/52 读全；37 件符号级交叉验证全命中（含 `_plan_target_inner` kwargs、`merge_edits` 三元组、`replay_claims(rules_by_id=)` 等私有形状）；失效引用 0（两项初报经主线 git 树复核为物化伪影）。

### 3.6 pytest 全量基线（本树 @158475f）

- 命令：`TMPDIR=/tmp/opencode/qa/pytest-tmp /home/opencode/fundlex/.venv/bin/python -X utf8 -m pytest tests -q -p no:cacheprovider --tb=line`（共享 venv，禁缓存，临时目录隔离；运行后 `git status` 复核仓库树仅 2 个本线新增审计文档，无测试残留污染）。
- 结果：**2156 passed，1 failed，118 skipped，741.5s**。
- 唯一失败：`tests/test_deploy_publisher.py::test_real_entrypoint_imports_and_serial_migration_use_isolated_sqlite`——失败行为 `$DST/.venv/bin/python` 不存在（rc=127）。成因已定位：`fundlex-publish.sh:160/430` 的 import/migrate 步骤固定拼 `$DST/.venv/bin/python`，该测试以 DST=仓库根模拟，**隐性假设被测仓库含仓库级 .venv**；本审计工作树是无 .venv 的 worktree（`/home/opencode/fundlex/.venv` 是其自身 venv），故为**环境性失败而非代码缺陷**。隐依赖记入 FL-D955 末项（建议在测试头显式 skipif(ROOT/.venv 缺失) 以如实呈现）。
- 118 skipped 与 FL-D954/D955/D958 家族吻合（27 用例 var/ 门控 + PDF fixture 门控 + browser 套件 FUNDLEX_BROWSER_TESTS 门控 + MySQL 门控 + 语料 skipif 等）——基线未暴露新增意外 skip。
- 记录瑕疵留痕：运行 wrapper 采用 `pytest | tail > log; echo "exit=$?"`（无 pipefail），日志尾行 `exit=0` 记录的是 tail 的退出码而非 pytest 的；以上结论取自 pytest 自身的统计行与失败明细。

## 4. 发现汇总（FL-D940~D959）

| 编号 | 级别 | 主题 | 说明 |
| --- | --- | --- | --- |
| FL-D940 | 高 | tools/deploy/deploy_recall.py 旧部署器就地覆写生产+装回无沙箱同名单元 | 死而危险，建议退役/硬阻断 |
| FL-D941 | 中 | cleanup_test_accounts.sh 删表覆盖不全（漏 compare_*/gg_*/integrations）+前缀误伤面 | 生产当前无残留（已实证） |
| FL-D942 | 低 | setup_fundlex_ops.sh 表级 DELETE 靠客户端自律 | 约定式防护自知 |
| FL-D943 | 中低 | diff_status.py 硬编码 D:\ 死脚本 | 建议移入 research/ |
| FL-D944 | 中 | migrate_workspace.py 远端 rm -rf 无白名单/确认 | 退役机工具，触达面已降 |
| FL-D945 | 低 | migrate_workspace_diff.py 自称 read-only 实则覆盖本地 | 文档/行为矛盾 |
| FL-D946 | 中 | cloud_verify.py 白名单外前缀+cleanup 失败仍 0+隧道断言陈旧+seal 竞态 | 生产当前无残留（已实证） |
| FL-D947 | 低注 | migrate_data EXPECTED=514 陈旧；build_builtin_guide 默认覆盖 env | 注级 |
| FL-D948 | 高(缓解) | prune_orphan_objects referenced_keys 漏 compare_*/gg_* object_key | dry-run 默认缓解；--apply 可误删存活交付物 |
| FL-D949 | 低注 | research/_wtmpl.ps1 无确认 Kill WINWORD | README 免责已载 |
| FL-D950 | 中观察 | 根侧发布器领先本树 4 项加固（fc5f7f2/be5484d 未并入本树线） | 移交合并线回填，勿反向同步 |
| FL-D951 | 中 | browser/test_workbench.py:429 10500ms×3 硬等待耦合 10s 轮询 | 脆弱 |
| FL-D952 | 中 | 测试域危险写操作族：MySQL DROP fixture ×4 仅 env 门控无库名护栏；批 E 两项 browser 测试写仓库树（vite build→frontend/dist/、结果 JSON→var/） | 危险（gated/可环境缓解） |
| FL-D953 | 高 | guide_generation_fakes.py 与真实 ModelRouter 接口漂移 | 裸 {} 静默+identity 缺 6 字段 |
| FL-D954 | 高 | 27 用例依赖 gitignored var/ fixture 静默全 skip | CI/净克隆零覆盖 |
| FL-D955 | 中 | fixture 路径未 __file__ 锚定族（CWD 相对/绝对机器路径，8 文件+批 E 2 文件）+ test_deploy_publisher 隐依赖仓库级 .venv | 换 cwd/换机静默蒸发或环境性失败 |
| FL-D956 | 中 | 真实时钟/线程时序断言族（本树 5 文件+批 E qa_worker 1 件） | 慢 CI flake 面 |
| FL-D957 | 中 | 真实合同段落号/字节偏移硬编码族（9 处） | 语料版本耦合，扩波同步项 |
| FL-D958 | 中 | 实物证明蒸发型空洞族（docx_overlay/首批 BH06/批 E skipif 口径 d608 硬失败 vs a3/full_body 静默）+ 门禁盲眼（guide_parse_benchmark engine-smoke 不计 overall_ok） | 与 D954/D955 交叉引用 |
| FL-D959 | 低 | 测试卫生+模块覆盖空洞：recovery 四模块无直接单测、feishu.service_main 无直接测试、sys.path.insert×6（+批 E fl_d692 相对插入）、未使用导入×2、跨测试 import 观察 | 综合 |

## 5. 结论

- **覆盖**：矩阵 PL2 行 280/280 逐件签认（本树 228 直接审 + d2a9bc5 物化树 52 交叉审）+ 矩阵外补审 20 件 = 实际签认 300 件；批 E 两项"失效引用"初报经 git 树复核为物化伪影并已留痕排除。pytest 全量基线 2156 通过 / 1 失败（环境性：无 .venv 的 worktree，成因已定位至 fundlex-publish.sh:160 的 `$DST/.venv/bin/python` 固定拼法与测试的 DST=仓库根模拟）/ 118 跳过（与 FL-D954/D955/D958 家族吻合）。
- **tools/**：防御工事主线（发布器/备份/漂移校验/沙箱模板）质量高且与生产实况一致；风险集中在：两件仍具破坏力的退役工具（FL-D940/944）、对象 GC 引用漏网（FL-D948）、清理脚本覆盖口径（FL-D941）、根侧发布器方向性漂移（FL-D950）。
- **tests/**：280 件**失效引用 0 起**（全部 import/文案/id/fixture 交叉核验命中）；核心风险是"静默蒸发"型空洞（FL-D954 27 用例 + FL-D955/958 家族，CI 上呈绿色假覆盖）与 fakes 漂移（FL-D953）；时序脆弱与语料硬编码为系统性但低烈度的 flake 面；批 E 另析出测试写仓库树两件（并入 FL-D952）。
- 本线无 NO-GO 级（会丢用户数据/中断生产的现行缺陷）发现；FL-D940/948/953/954 为四个需要优先处置的项（具体排序：940→948→954→953）。
- 编号段 FL-D940~D959 全部用完；批 E 新证据应"并入既有家族"口径执行完毕（D952/D955/D956/D958/D959 备注行均含批 E 证据），未溢出编号段。
