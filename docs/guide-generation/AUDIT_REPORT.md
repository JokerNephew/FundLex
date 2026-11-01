# 指引生成功能「补完开发+充分测试」专项审计报告（qa-gg-audit）

- 日期：2026-11-01；基线：worktree qa-gg-audit @ 158475f（与生产发布树 /opt/fundlex-recall-first 同代码）。
- 触发：生产 run a552520cf648451c93ed82d954bdfe19 失败，用户明确「此功能此前并未完全开发和测试，要求全部检查一遍，充分完成开发和测试」。
- 范围：fundlex/guide_generation/ 全部 27 个模块 + 部署形态（systemd 单元×路径）+ 测试充分化 + 真实 E2E。

## 1. 生产失败取证（run a5525）

MySQL gg_runs/gg_steps 实测：INGEST/EXTRACT/VERIFY 完成后，BUILD_CORPUS_SNAPSHOT 以 `PermissionError` 失败，run error_code=`[Errno 13] Permission denied: '/home/opencode/data/funds_word'`。与主线 FL-D820 根因一致。本线补充两个机制面事实：

1. **失败语义当时不稳定/含混**：同样的「语料不可用」，权限拒绝以裸 OSError 冒泡、目录不存在则静默变空快照后在两阶段后以 CORPUS_EMPTY 失败——运维无法区分「配置缺失」与「语料为空」→ 已修（FL-D821）。
2. **主线修复未闭环**：worker unit 内联 `Environment=FUNDLEX_GUIDE_CORPUS_DIR=/home/opencode/data/funds_word` 覆盖 EnvironmentFile，worker 实际仍用旧路径 → 已修并验证（FL-D822）。

## 2. 交付物索引

| 交付 | 位置 |
| --- | --- |
| 功能逻辑清单（27 模块职责/状态机/失败路径/外部依赖） | docs/guide-generation/MODULE_INVENTORY.md |
| 问题入册（FL-D821~829） | docs/DETAIL_APPEND_GG_AUDIT.md（主线并册） |
| 代码修复 | corpus_catalog / pipeline / cli / discovery / export / repair |
| 新增测试 15 项 | tests/test_guide_generation_hardening.py |
| 本报告 | docs/guide-generation/AUDIT_REPORT.md |

## 3. 修复清单（发现即开发补完）

| 编号 | 摘要 | 处置 |
| --- | --- | --- |
| FL-D821 | 语料缺失/不可读显式 CORPUS_DIR_MISSING/UNREADABLE；CLI 空语料 exit 3、配置错 exit 2；CLI 默认绝对路径；SyncResult.eligible_files+ payload 记录截断 | 代码+9 测试 |
| FL-D822 | 生产 unit 内联 Environment 覆盖 env 文件（语料仍指 /home） | 已修生产+验证+备份 |
| FL-D823 | discovery 窗口填充死分支：相关需求 9+ 被轮换需求顶替 | 代码+1 测试 |
| FL-D824 | residual 整阶段死代码+3 配置字段黑洞（复启有无限循环风险） | 登记；复启/删除留产品决定 |
| FL-D825 | 证据 HTML 残余「新影响数」列恒空（键名错位） | 代码+1 测试 |
| FL-D826 | repair 单条失败完全不可见 | 代码+2 测试（major finding+落库） |
| FL-D827 | 低危杂项 11 项（死代码/未接线/静默回退等） | 登记 |
| FL-D828 | coverage/向量 fail-open 面 | 登记+阈值/徽章建议 |
| FL-D900 | 正文"……"省略句误判 TOC，后续条款静默丢失；PARSER_VERSION 升 v2；发布后需 force resync | 代码+2 测试 |
| FL-D901 | E2E 探针把 DB 连接串写入 journal | 已清除+复核干净；建议评估轮换 |
| FL-D829 | 失败 run 前端裸渲染 error_code、泄露服务器路径 | 登记（修复归前端线） |

## 4. 部署形态盲区排查结论（任务3）

- 8 个生产 fundlex 单元全部核对：仅 `fundlex-guide-generation-worker` 无 ProtectHome 且内联引用 /home（已修）；其余均 ProtectHome=true+ReadWritePaths=/var/lib/fundlex（test 线独立）。
- 发布树 `<repo>/funds_word` 不存在（实测）：FL-D821 后该情形失败为显式 `CORPUS_DIR_MISSING`（配置缺失），不再静默空语料。
- 代码内 `/home` 引用残留：仅 cli.py `~/.local/share/fundlex` 数据目录默认（CLI 运维路径，worker/API 均 env 注入 FUNDLEX_DATA_DIR=/var/lib/fundlex，不触）；可以接受，已登记。
- 依赖发布树必带文件：`guides/builtin_guide_v1.json`（scope 静默回退 6 章——已核对发布树存在该文件）、`uv.lock`（缺失时哈希记空）、git HEAD（缺失时回退 FUNDLEX_COMMIT_SHA）。
- 清理：两个 failed 遗留 transient unit（run-u399197/399217）已 reset-failed。

## 5. 发布守门补强建议（任务5）：部署形态 PILOT run 冒烟

**问题**：本次故障链「env 迁移但 unit 内联覆盖未同步」在代码级测试不可见——只有真实发布形态（发布树路径+unit 固化环境+沙箱+真实服务用户）能暴露。现有发布流程 `tools/deploy/publish_workspace.sh`（fundlex-publish）只覆盖代码同步+重启，无部署形态冒烟。

**方案（归属主线决定是否实施）**：发布后、宣布可用前，由发布脚本或独立守门脚本执行：

1. **配置一致性断言**（秒级，无模型）：
   - 对 5 个生产单元 `systemctl show -p Environment` 固化值与 `/etc/fundlex-recall.env` 比对关键路径变量（FUNDLEX_GUIDE_CORPUS_DIR、FUNDLEX_DATA_DIR、FUNDLEX_DATABASE_URL），内联覆盖要么不存在要么一致；
   - 以**服务用户身份**（`sudo -u fundlex test -r`）校验语料目录/数据目录可读可写；
   - 发布树关键文件存在：guides/builtin_guide_v1.json、uv.lock、funds_word **不存在**（防止回退路径意外复活）。
2. **PILOT run 冒烟**（真实模型，小口径）：上传一份 PILOT 法规（如既有销售费用 PDF），`corpus_limit=1`，走默认 API 入口→worker→完成。验收：status∈{complete, complete_with_unresolved}；gg_steps 全 completed；payload.corpus_sync.eligible_files≥1 且 corpus_dir 为新口径；error_code 为空。失败即阻断发布通告并附 gg_steps 诊断。
3. **负向冒烟**（可选，测试环境）：临时把测试环境语料指向不存在路径，断言 run 以 `CORPUS_DIR_MISSING` 失败且 error_code 稳定（验证 FL-D821 语义在发布形态下成立）。
4. 结果（run id、门禁值、哈希）写入发布记录。

成本：PILOT run 一次真实模型调用量≈corpus_limit=1 的常规 run，符合 FL-D445 政策；守门不设费用/次数门禁，只设结果正确性门禁。

## 6. 测试覆盖（任务4）

- 新增 15 项单测（tests/test_guide_generation_hardening.py）：FL-D821×9（缺失/空串/文件路径/不可读/空目录/截断 eligible/stage 传播/CLI 三退出码/默认绝对路径）、FL-D823×1（窗口相关需求全保留）、FL-D825×1（HTML 计数渲染）、FL-D826×2（repair 失败可见+落库）、FL-D900×2（正文省略号不误判 TOC、真目录行仍跳过）——**15/15 通过**。
- 既有 gg 套件 11 文件**回归 134/134 通过（76.5s）**，含 fake 模型端到端、fencing、API 全链路、门禁阻断。
- 测试口径：树内 venv（python 3.11.13）+ PYTHONPATH=$PWD，`import fundlex` 实测解析到本 worktree（FL-D593 陷阱复核）。
- 真实 E2E：见第 7 节。

## 7. 真实端到端验证（任务4）——已通过

**口径**：systemd-run ProtectHome=true（生产线沙箱口径）、真实模型（FL-D445，无预算门禁）、语料 `/var/lib/fundlex/corpus/funds_word`（新口径）、法规 `references/source/附件1：公开募集证券投资基金销售费用管理规定.pdf`（真实公开法规）、corpus_limit=2、sqlite 隔离数据目录与隔离账本（不触生产 MySQL/生产账本）；代码为经快照复制的本 worktree（含全部本线修复），venv editable finder 指向已改至 /tmp 复制树（FL-D593 口径复核）。

**结果**（run `06fc7cd96c83443c96e7804cc1df91a0`，2026-11-01，wall 1h15m29s，unit 退出码 0）：

- **15/15 stage 全部 completed**（INGEST→BUILD_EVIDENCE），无一步失败/重试。
- **终态 complete_with_unresolved，候选未获机器资格**——门禁按设计 fail-closed：open critical=15、unresolved impacts=26、requirement gap=1；`independent_model_review_qualified=false`（本环境只有单一真实模型，author==reviewer，独立性门禁正确拒绝）；`quality.run_status=fail`、`coverage.run_status=complete_with_unresolved`。其余 7 项 checks 全 true。**这证明资格链不会把有未决问题的候选包装成 complete**。
- **FL-D821 实证**：`corpus_sync={eligible_files:514, corpus_limit:2, parsed:2, errors:[]}`——新语料路径在 ProtectHome=true 下可读，截断账本字段按修复后形态落库。
- **FL-D900 实证**：BUILD_CORPUS_SNAPSHOT 以 contract-segmenter-2 解析，errors=0。
- 规模：requirements 60、impacts 645（definite 97 / possible 403）、sweep batches 60、guide_items 61、findings 218、模型调用 808 次（gg_model_calls 全量记账）。
- **产物与哈希**：guide/guide_ai docx（49,582B）、evidence_json（6.24MB）、evidence_html（493KB）四件 artifact 落库，**逐字节重哈希与登记值一致**。
- **账本（观测）**：隔离账本 812 次请求，charged $0.4542（reserved 估算 $4.646，观测口径不作门禁，符合 FL-D445）。
- 延迟分布实测：抽取/扫描/复核/覆盖全链 LRU 无中断；单 run 1h15m 于 corpus_limit=2，为发布守门 PILOT run 提供了真实时长基线（limit=1 预期更短）。

**负向冒烟（发布形态，FL-D821 语义实证）**：同沙箱口径下 `sync-corpus --corpus-dir /nonexistent/corpus` → **exit 2**（CORPUS_DIR_MISSING，stderr 明确提示）；`--corpus-dir /var/lib/fundlex/corpus/funds_word --limit 2` → **exit 0**。发布树形态下「默认回退不存在路径」的情形将显式失败为 CORPUS_DIR_MISSING，不再静默空语料。

**结论**：默认任务入口在真实模型+生产沙箱口径下可完整跑通并按门禁交付候选工作文件（含人工复核面），未依赖任何临时开关；本线修复点（截断账本、分段器 v2、修复 finding 形态）在实际产物中可见，配置错误路径在发布形态下显式失败。

## 8. 遗留与边界（如实声明）

- FL-D824 residual 复启/删除是产品决定，未擅自处理。
- FL-D827/828 低危与 fail-open 面仅登记，未改语义。
- FL-D829 前端错误显示修复归前端线。
- 本线代码改动**未发布**到 /opt/fundlex-recall-first（发布执行属主线，建议按第 5 节守门执行）。
- 隐私/凭据：本报告不含任何密钥值；数据库查询经环境变量管道，未打印凭据。
