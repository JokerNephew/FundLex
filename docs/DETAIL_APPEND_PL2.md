# 细节问题附录 — PL2 平台审计线（tools/** + tests/**）

> 2026-11-01 全覆盖 QA 审计，平台审计线（PL2）发现登记表。编号段 **FL-D940~D959**。
> 审计基线：工作树 qa-audit-platform @ `158475f`（QA 冻结快照）；矩阵 `/tmp/opencode/qa/COVERAGE_MATRIX_20261101.md`。
> 生产实况核对均以只读方式进行（sudo -n 读文件/只读 DB 探针/journalctl 探测），未做任何修改。
> 状态字段：未处理=仅登记，待主线决策；本线纪律为"发现即登记，不擅自大改"。

---

## FL-D940 旧部署器 deploy_recall.py 就地覆写生产且会装回无沙箱同名单元（高危）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：`tools/deploy/deploy_recall.py` 是现行"五单元+事务发布器（tools/deploy/publish_workspace.sh → /usr/local/sbin/fundlex-publish）"之前的部署器，仍具备完整破坏力：① 直接 `tar -xzf` 覆写 `/opt/fundlex-recall-first`（deploy_recall.py:214-215，无事务/清单/回滚）；② 向 `/etc/systemd/system/` 写入**与现行单元同名**的 `fundlex-recall-api.service`、`fundlex-recall-worker.service`（:228-229），其内嵌 `API_UNIT`/`WORKER_UNIT` 定义（:95-129）完全没有 NoNewPrivileges/ProtectSystem=strict/PrivateTmp 等现行模板（tools/deploy/fundlex-*.service.template）的沙箱项——运行即把带加固的单元烤回裸奔版；③ `ENV_OVERRIDES`（:84-93）会改写生产 `/etc/fundlex-recall.env` 并注入 `FUNDLEX_MODEL_MAX_COST_USD=50`/`MAX_REQUESTS=20000` 旧口径；④ `After=network.target` 与现行模板 `network-online.target` 不一致；⑤ 任何 `check=True` 中途失败（:80）直接 SystemExit，生产停在半更新状态，无回滚；⑥ sed 改 nginx vhost（:271）不携带 FL-D288 上传守卫。
- 证据：tools/deploy/deploy_recall.py:80/84-93/95-129/180-215/228-229/271/262-265；现行模板沙箱 7 项（tools/deploy/fundlex-recall-api.service.template:14-20）；发布器事务设计（tools/deploy/fundlex-publish.sh:16-30, 445-533）。grep 全仓库 docs/ 对该脚本引用为 0 次 → 已是死脚本。
- 处理方法（建议）：从仓库移除该脚本，或在文件头加 `sys.exit("superseded by fundlex-publish; refusing to run")` 式硬阻断；本次审计因"不擅自大改"纪律未改动。
- 状态：**未处理（建议退役/阻断）**。验证：未执行（只读）。

## FL-D941 cleanup_test_accounts.sh 关联数据删除不全 + 前缀通配误伤面（中）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/deploy/cleanup_test_accounts.sh 自称"只删除 …账号**及其关联数据**"，但 SQL（:46-63）只删 users/sessions/tasks/task_files/task_batches/batches/documents/artifacts 8 张表。生产同一套共享库中按 owner/user_id 建表的业务数据还包括：compare_tasks/compare_pairs/compare_pair_files/compare_artifacts/compare_selection_drafts/compare_selection_artifacts（fundlex/compare/store.py:52-94）、gg_runs/gg_candidate_guides/gg_artifacts 等全部 gg_*（fundlex/guide_generation/store.py:42-207）、external_identities/integration_binding_codes/integration_oauth_states/task_channels/feishu_drafts（fundlex/integrations/store.py:38-95）、guide_jobs（fundlex/guide_store.py:54）。被删用户的上述行会成为孤儿（这些表对 users 无外键约束，删除不会报错但衬底残留）。另：头部注释写前缀 `cloud-% / p6-% / cloud-eval-%`，代码实为 `cloud-run-% cloud-eval-% p6-%`（:25），注释/代码不一致；`LIKE 'p6-%'` 等通配会把任何注册名撞上前缀的**真实用户**一并删除（fundlex/auth.py:60 USERNAME_PATTERN 允许 `-`）。
- 证据：cleanup_test_accounts.sh:24-33/46-63；生产只读探针（2026-11-01 16:15）：users=118，白名单前缀账号=43，上述遗漏表中 whitelisted 用户相关行当前=0（**尚无实际残留，属潜在逻辑缺口**）；生产表清单含 compare_*/gg_*/external_identities/feishu_* 等（SHOW TABLES 实测）。
- 处理方法（建议）：把相关表补齐进删除事务（按 owner/user_id 级联），或者脚本更名/改注释明确"只清理 recall 修订域"；把 `p6-` 等前缀收窄（如 `p6-tmp-`）并在删除前列表二次确认。
- 状态：**未处理（建议）**。

## FL-D942 setup_fundlex_ops.sh：受限账号的表级 DELETE 依赖客户端自律（低）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/deploy/setup_fundlex_ops.sh 给 `fundlex_ops` 授予 `DELETE ON users` 等 8 张表级权限（:36-43），"只删测试前缀"完全依赖 cleanup_test_accounts.sh 的 WHERE 拼写——拿到凭据即可直接删任意用户。脚本注释（:33-35）已自陈"保护策略由调用侧 SQL 强制"，即明知为约定式防护。与 FL-D941 的注释口径（cloud-% vs cloud-run-%）存在同样漂移（:34）。
- 证据：setup_fundlex_ops.sh:33-43/6-7。
- 处理方法（建议）：接受约定式防护则应把权限收敛为存储过程（DEFINER 内附前缀检查）或视图代理；至少把注释口径与代码统一。
- 状态：**未处理（建议）**。

## FL-D943 diff_status.py 硬编码退役 Windows 路径，现机不可运行的死脚本（中-低）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/deploy/diff_status.py:6/9 写死 `D:\Desktop\FundLex`，Linux 现工作机上 import ssh_probe 即 ModuleNotFoundError，完全不可运行；docs/ 与 tests/ 零引用，属一次性诊断残留。
- 证据：tools/deploy/diff_status.py:1-30；`grep -rln diff_status docs tests` = 0。
- 处理方法（建议）：删除或移入 tools/research/（该目录 README 已声明一次性脚本口径）。
- 状态：**未处理（建议移置/删除）**。

## FL-D944 migrate_workspace.py 远端整目录 rm -rf 无目标白名单/确认（中）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/deploy/migrate_workspace.py:206 对 `--remote-dir` 任意值执行 `find {remote_dir} -mindepth 1 -maxdepth 1 -exec rm -rf {} +` 后整树回填；remote_dir 无白名单校验（默认 /home/opencode/fundlex），误传 `/home/opencode` 等路径即清空家目录。事前仅做打包正常性校验，未对目标值做 sanity 检查或交互确认；失败路径会残留 `/var/tmp/fundlex-migrate-*`（cleanup 只在成功末尾 :249 执行）。另 KEY_PATHS+文件计数属抽样核验（:38-48/223-246），目录层级错配可漏检。
- 证据：tools/deploy/migrate_workspace.py:137/199-217/249。
- 处理方法（建议）：remote_dir 白名单（== /home/opencode/fundlex 或显式 --i-know）+ dry-run 默认列清单确认；staging 失败也走 finally 清理。
- 状态：**未处理（建议）**。注：该机为已退役 Windows 迁移期工具，触达面随 Windows 退役而降低，故定级"中"而非"高"。

## FL-D945 migrate_workspace_diff.py 自称 read-only 实则回写并覆盖本地文件（低）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：docstring 声明 "Read-only"（tools/deploy/migrate_workspace_diff.py:3），但 :46-50 会把远端 `publish_workspace.sh` 字节写回本地仓库并**无备份覆盖**（"remote is authoritative"），与自述矛盾；`local_only` 计数仅报数量不列名（:57），排查面收窄。
- 处理方法（建议）：修 docstring（如实写"会用远端权威副本覆盖本地"）或默认只对比、加 --write 才落盘。
- 状态：**未处理（建议）**。

## FL-D946 cloud_verify.py：冒烟账号前缀在白名单外 + 清理失败仍返回 0 + 隧道断言陈旧 + 真实模型竞态（中）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/deploy/cloud_verify.py 服务器端脚本（SERVER_SCRIPT）① 临时账号前缀 `deploy-verify-`（:49）不在 cleanup_test_accounts.sh 白名单（cloud-run-/cloud-eval-/p6-）内，finally 清理失败（:132-133 仅标记 `cleanup: failed:<Type>`）时残留无回收机制；且该失败只写结果、主流程仍 `return 0`（:270/275）→ 告警静默；② seal 任务（:100）会驱动 recall worker 真实模型调用产生真实费用，清理删 DB 行与 worker 并发处理存在竞态，对象存储可能留孤儿文件（依赖 prune_orphan_objects 兜底）；③ 隧道检查断言陈旧：检查 `/` 响应含"指引配置"（:168）与 `/static/app.js` 含 `recall_first`（:178），现行前端为 React SPA（frontend/index.html 仅 root mount），本树 grep 两字面量在目标中均为 0 → 生产上恒 False，反而误报部署异常；④ :112-114 `if 'task_id' in dir():` 是无作用死代码；⑤ 上传固定文件名 /tmp/fundlex_cloud_verify.py（:252），并发运行互相覆盖。
- 证据：cloud_verify.py:49/100/112-114/132-133/168/178/252/270；cleanup_test_accounts.sh:25；生产探针 deploy-verify-% 用户当前=0（2026-11-01）。
- 处理方法（建议）：前缀改 cloud-run- 系；cleanup 失败即非零退出；隧道断言改为校验 /api/capabilities JSON 字段；清理前先 pause/abort 任务或等终态。
- 状态：**未处理（建议）**。

## FL-D947 migrate_data.py 期望计数陈旧（仅 NOTE 不失败）（低/注）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/deploy/migrate_data.py:29 `EXPECTED={"funds_word":514,"references":24}`；本树 funds_word 现为 515 份（references 24 ✓），差异只打印 NOTE 不影响结果（:79-81）。另 tools/build_builtin_guide.py:41：`--max-completion-tokens` 有默认值 8000，未显式传入也会覆盖环境变量 FUNDLEX_MODEL_MAX_OUTPUT_TOKENS。
- 处理方法（建议）：EXPECTED 改为下界断言或随扩波去掉硬编码；build_builtin_guide 只在显式传参时才写环境变量。
- 状态：**未处理（建议/注级）**。

## FL-D948 prune_orphan_objects.py referenced_keys 漏 compare/gg 的产物引用，--apply 可误删存活交付物（高危，默认 dry-run 缓解）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/maintenance/prune_orphan_objects.py:19-37 `referenced_keys()` 仅查询 `documents.input_key`、`artifacts.object_key` 与 guide_versions 派生键；但同一对象存储（RunStore.objects，fundlex/store.py:444）还被这些表引用：`compare_pair_files.object_key`（fundlex/compare/store.py:72）、`compare_artifacts.object_key`（:78）、`compare_selection_artifacts.object_key`（:94）、`gg_artifacts.object_key`（fundlex/guide_generation/store.py:207）。compare/指引生成任务的**存活**输入与产物若超过 --min-age-hours（默认 24h）就会被 scan 判为孤儿，`--apply` 时逐文件 unlink（:70-81）→ 交付物被删而 DB 行还在（用户端表现为"报告在、文件 404"）。缓解：默认 dry-run、需显式 --apply、24h 老化窗、symlink/越界防护齐全（:46-53/73-75）；tests/test_object_gc.py 只构造 documents/artifacts 场景，未覆盖"compare/gg 引用应免删"反例（测试缺口反向印证）。
- 证据：如上；gg 产物生命周期（guide_generation/store.py:1292-1297 put_artifact）；compare 产物（compare/store.py:1068）。
- 处理方法（建议）：referenced_keys 补齐 4 处 object_key 查询（数值列可空过滤）；test_object_gc.py 增加 compare/gg 引用免删用例；补查 feishu/whatever 新增 object_key 列的回归看板。
- 状态：**未处理（建议）**。验证：只读；未执行 --apply。

## FL-D949 tools/research/_wtmpl.ps1 无确认强杀全部 WINWORD 进程（低）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：tools/research/_wtmpl.ps1:4 `Get-Process WINWORD | ForEach { $_.Kill() }` 夺杀本机所有 Word 进程，未保存文档即丢，无任何确认。缓解：tools/research/README.md:5 已声明"一次性…不要盲目批量运行 PowerShell 脚本"；目标机（Windows 开发机）已退役。
- 处理方法（建议）：加 `-Confirm`/进程交互过滤或移入 README 特别强调；价值已随 Windows 退役趋零，可整体归档。
- 状态：**未处理（建议/注级）**。

## FL-D950 根侧发布器领先本审计树 4 项加固；合并后必须回填（中，观察项）

- 发现日期：2026-11-01（PL2 审计）
- 问题与影响：只读漂移核对（check_publish_drift.sh）显示 `/usr/local/sbin/fundlex-publish`(sha256 cac65e32…) 与本树 repo 版(1624251a…) 不一致。逐行 diff：根侧领先，包含 ① fc5f7f2 FL-D801 留存事务自动清理（保近 3 份，防磁盘 100%）；② FL-D800 migrate_schema sys.path 钉版（防 editable .pth 回落别的树）；③ FeishuAppOnboarding schema 初始化（be5484d 引入，本树 HEAD 无该模块/表）；④ check_api 冷启动 24×5s 重试。这些修复在 qa-backend-audit-20261101 等分支（fc5f7f2/be5484d 均不在本树 HEAD 祖先集）。风险在于方向性：发布流程书面规定"根侧须与仓库同步并在发布前漂移校验"（publish_workspace.sh:5-10）——若有人用本树/过期树副本执行同步，会把 4 项加固**反向烤掉**。另已实测 `journalctl --since '2026-10-29T09:00:00+08:00'` 本机 rc=1（f6e33f3 修复动机复现成立）。
- 证据：`sudo -n diff /usr/local/sbin/fundlex-publish tools/deploy/fundlex-publish.sh`（163-190/228-240/400-419 行块）；`git branch --all --contains fc5f7f2`；systemd 五单元与模板 drift=OK（装在 /etc 的 unit == 本树模板）。
- 处理方法（建议）：合并线把 fc5f7f2/be5484d 落主线后立即重跑 check_publish_drift，勿用旧树反向安装。
- 状态：**未处理（观察/移交合并线）**。

---

---

## FL-D951 browser/test_workbench.py 以 10.5s×3 固定等待硬耦合前端轮询时钟（中，脆弱）

- 发现日期：2026-11-01（批 A）
- 问题与影响：tests/browser/test_workbench.py:429 在三循环中 `page.wait_for_timeout(10500)`，:433 注释自述依赖"actual ten-second background poll"。单用例 ≥31.5s 墙钟，慢机/CI 抖动下易 flake；前端轮询间隔调整时静默失效。同文件 :418-421 已有 route 拦截设施，可改为事件等待。
- 状态：**未处理（建议改 route 驱动等待）**。

## FL-D952 测试域危险写操作族：MySQL DROP fixture 无库名护栏 + browser 测试写仓库树（中，危险 gated）

- 发现日期：2026-11-01（批 A/D/E）
- 问题与影响：
  - (a) 4 件 MySQL 集成 fixture 连接成功即 DROP 业务表：tests/test_db_mysql.py:38-42、test_compare_system_review.py:197-204、test_compare_selection_api.py:208-215、test_run_store_fencing.py:203-204。唯一防护是环境变量开关 + 专用 DSN；env 误指共享库即不可逆毁表。（test_db_mysql.py:241-243 的 `never-log-this` 为假凭据，无泄露，已单独核验。）
  - (b) 物化参照树 tests/browser/test_guide_diff.py:51-63 `_ensure_v2_dist` 在测试内执行 `vite build`（600s 超时），向**仓库 frontend/dist/** 写产物；依赖 node_modules 在场，且在 CI 并发/只读树下行径不可控。
  - (c) 同树 tests/browser/test_compare_scroll_perf.py:40 默认 `OUT_DIR="var/qa-compare-scroll-perf"`（仓库相对），:337-339 把性能 JSON 写仓库 var/（COMPARE_PERF_OUT 可缓解）。
- 处理方法（建议）：(a) fixture 强制校验库名含测试前缀（如 `fundlex_test_%`），不满足即 skip；(b)(c) 默认输出改 tmp_path/mktemp。
- 状态：**未处理（建议）**。

## FL-D953 guide_generation_fakes.py 与真实 ModelRouter 接口漂移（高，fake 漂移）

- 发现日期：2026-11-01（批 D，主线复核行号通过）
- 问题与影响：① tests/guide_generation_fakes.py:81 `_value()` 预制响应不含 `guide_batch_resolve`/`guide_repair`/`guide_topic_coverage` 三种真实任务类型（fundlex/guide_generation/discovery.py:622、repair.py:75、coverage.py:205 会调用），未命中时**静默返回裸 `{}`** 而非报错——假阳性放过或深层费解报错；② fake `identity()`（:35-45）每 role 仅 4 字段，真实 `identity()`（fundlex/model_router.py:324-351）另有 max_context_chars/max_output_tokens/temperature/request_options_sha256/shares_primary_endpoint/same_model_as_author 共 6 字段——报告快照类回归网稀疏。现测试仍绿仅因各用例子类自行拦截三条路径（test_guide_generation.py:361/867/1042、test_guide_generation_pipeline.py:144/188）且管线仅消费个别键；属隐性漂移风险非现行红测。
- 处理方法（建议）：fake 对未覆盖任务类型抛错；identity() 补齐 6 字段并与 model_router.ROLES 断言对齐。
- 状态：**未处理（建议）**。

## FL-D954 27 用例依赖 gitignored 的 var/ fixture，净克隆上静默全 skip（高，空洞）

- 发现日期：2026-11-01（批 D）
- 问题与影响：tests/test_revision_api.py:20 的 skipif 门控读 `var/recall-first-evaluation/p6-dev-round1-01/D01`；`.gitignore:9` 忽略整个 var/，干净克隆该目录不存在 → 全文件 12 用例 0 执行；tests/test_selective.py:62-63 同门控，约 15/18 用例 skip。合计约 **27 用例绿色假覆盖**；且 test_revision_api.py:71 硬编码 `revision_count == 17`，fixture 演进也无从发现漂移。pytest 基线 118 skipped 与此家族吻合（§3.6）。
- 处理方法（建议）：fixture 入仓（合同公开资料政策已授权入库）或改为可生成；skipif 换成显式 fail-fast 门，避免静默。
- 状态：**未处理（建议）**。

## FL-D955 fixture/源码路径未 `__file__` 锚定族（换 cwd/换机即蒸发或环境性失败）（中，脆弱）

- 发现日期：2026-11-01（批 A/C/D/E + pytest 基线）
- 问题与影响（同族多文件，逐一留证）：
  - tests/test_guide_generation.py:94-103：`Path("references/source/附件1…pdf")` CWD 相对 + 文件不在·即 `pytest.skip`——全仓唯一未锚定且接 skip 的 PDF 用例，非仓库根运行即静默零覆盖；
  - tests/test_duplicate_copy_scope.py:10：相对路径传入 inspect_docx（:16/:32），40+ 同类均 `ROOT = Path(__file__).resolve().parents[1]`，本文件孤例；
  - tests/test_rule_recognition.py:100：`Path('rules/rules_v1.json')`；tests/test_replay_site_provenance.py:183：`open("guides/builtin_guide_v1.json")`——均 CWD 相对；
  - tests/test_remediation_engine_summary_scope.py:24：硬编码绝对机器路径 `/home/opencode/fundlex/funds_word/基金合同第一批`（旧部署机专属），换机整体静默 skip；
  - tests/browser？（无）；tests/test_absent_delete_coverage.py、test_compare_corpus.py：funds_word 首批语料布局耦合（扩波同步项，与 FL-D957 相邻但属布局非段号）；
  - 批 E 参照树：tests/test_compare_polling_gate.py:12 `Path("frontend/compare.js")`、test_review_render_index.py:15 `Path("frontend/app.js")`——CWD 相对前端源码钉板；
  - **环境性隐依赖（基线实证）**：tests/test_deploy_publisher.py 以 DST=仓库根模拟 migrate_schema，间接固定使用 `<root>/.venv/bin/python`（fundlex-publish.sh:160）；无 .venv 的 worktree 上该用例 rc=127 失败（基线唯一失败即此）。建议用例头显式 skipif(ROOT/.venv 缺失)。
- 状态：**未处理（建议统一 `Path(__file__).resolve()` 锚定）**。

## FL-D956 真实时钟/线程时序断言族（中，脆弱 flake 面）

- 发现日期：2026-11-01（批 A/C/D/E）
- 问题与影响（同族多文件）：tests/test_api_store.py:241 `time.sleep(1.3)` 对 `lease_seconds=1` 续约断言（300ms 余量）；test_operation_execution_closure.py:528-577 与 test_guide_generation.py:1337 真线程 + sleep(0.03) 并发顺序断言；test_guide_generation.py:760-798 `circuit_wait_s=0.01` 真实时钟打熔断窗口；test_upload_guard.py:101-107 receive_timeout 0.01s vs delay 0.05s；批 E 参照树 test_qa_worker_20261031.py:337-339 sleep(0.05) 轮询（有 15s deadline 缓解）、:440-442 dead_pid 理论 PID 复用竞态、:427 写系统 /tmp（finally 兜底）。对照良好范式：test_guide_remediation_worker_engine.py 用有界 `threading.Event.wait(10..15)`。
- 状态：**未处理（建议改事件/注入时钟）**。

## FL-D957 真实合同段落号/字节偏移硬编码族（中，语料版本耦合）

- 发现日期：2026-11-01（批 B）
- 问题与影响：9 处断言与 `funds_word/基金合同第一批` 特定版本强绑定：test_g06:25(start=184,end=204)、g08_partial:22(p292)、g11_class:41(p243)、g12_allocation:24(p165)、g12_list:24(p295)、g12_semicolon:39(p244)、g14:32(p209)、g22:25-33(p955,start=0,end=39)、docx_overlay:287-303(p159)。现行对照真实 DOCX 均有效（风险而非现行错误）；语料扩波/重排时批量失效——属扩波工作必须携带的同步项。
- 状态：**未处理（扩波同步项）**。

## FL-D958 实物证明蒸发型空洞 + 门禁盲眼族（中）

- 发现日期：2026-11-01（批 B/D/E）
- 问题与影响：
  - tests/test_docx_overlay_contract.py:286-303：唯一以真实合同验证 overlay 插入位置的实物证明，语料缺失即 skipif 静默通过——CI 上语料丢失无感知；
  - tests/test_first_batch_label_20261028.py:132-135：BH06 用例语料缺失即 `pytest.skip`，同文件其余均为实断言；
  - 批 E 参照树口径不一致：同依赖 funds_word 语料，test_fl_d608_definition_group_chain.py **无任何守卫**（语料缺失硬 FileNotFoundError），而 test_docx_a3_regressions.py:330 / test_compare_full_body_replacement.py:490 用 skipif 静默跳过——三个文件三种行为，缺统一口径（硬失败其实比静默 skip 诚实，建议统一为显式 fail-fast 门）；
  - **门禁盲眼（tools/）**：guide_parse_benchmark.py:183-191，`--engine-smoke N` 产出仅进 report，`overall_ok` 只 AND 解析通道分——smoke 任务失败（task_create_4xx/not_certified 等 verdict）照样 exit 0。质量工具自身把引擎冒烟排除在门禁外；
  - 与 FL-D954（var/ 门控）、FL-D955（PDF CWD+skip）交叉引用。
- 状态：**未处理（建议统一显式门：缺失即 fail 或显式 xfail(strict=False) 带原因）**。

## FL-D959 测试卫生 + 模块覆盖空洞综合项（低）

- 发现日期：2026-11-01（批 B/C/D/E + 主线静态分析）
- 问题与影响：
  - **模块覆盖空洞**：126 个 fundlex 模块 95 被测试精确 import，28 个无直接测试多为聚合入口间接覆盖；其中确证直接单测缺席的两块：`fundlex.recovery.{history,orchestrator,policies,types}`（4 模块 687 行，仅经 recall_pipeline 间接覆盖）与 `fundlex.integrations.feishu.service_main`（五服务之一的进程入口，无任何直接测试）；
  - **sys.path 污染 6+1 处**：g08_partial:10、g11_class:10、g12_allocation:12、g12_list:10、g12_semicolon:12、g22:10（导入期插 tests 目录到全局 sys.path，受收集顺序影响）；批 E fl_d692:22 相对插入 `"tools/evaluation"`；
  - **未使用导入 2 处**：test_remediation_engine_approval_binding.py:17 `guide_fingerprint`、test_recall_pipeline.py:1390 函数内 `ModelResult`（死代码，误导读审）；
  - **跨测试 import 观察**：约 19 个文件以 test_recall_core.py（1883 行）/test_recall_pipeline.py 等为 helper 源（含 runpy.run_path 加载 test_docx_structures.py），单文件无法独立运行、helper 改动可级联；符号经逐一核验均存在，非失效引用，仅记录结构性脆性。
- 状态：**未处理（建议卫生批处理：conftest 规范化 sys.path、删死导入、recovery/feishu 入口补直接单测）**。

---

**登记完毕**：FL-D940~D959 共 20 条（高危 4：D940/D948/D953/D954；中 9：D941/D944/D946/D950/D951/D952/D955/D956/D957/D958 按主级别计；低/注级 6）。本线纪律为发现即登记、不擅自大改；所有证据行号可复核（本树 158475f 或物化树 d2a9bc5）。
