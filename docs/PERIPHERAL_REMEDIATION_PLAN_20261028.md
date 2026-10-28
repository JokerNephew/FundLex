# 外围前后端整改分阶段计划（2026-10-28）

- 状态：**计划待确认，未继续开发**。
- 目标：在不动核心识别/召回/修改算法的前提下，收口外围交付门、指引版本、任务状态机、查询模型、账号安全和前后端一致性，并完成可复现的自动化与真实端到端验收。
- 基线：当前工作区分支 `codex/semantic-engine-remediation-20261028`（HEAD `f2e318e`）。GitHub 默认分支仍是 `codex/fundlex-recall-first`（`a2905ac`，2026-10-19）；当前分支领先 110 个提交且未推送。整改完成并验证后再合并/推送默认分支。
- 产品决定（已锁定）：
  1. 以当前工作区为修复基线，完成后合并/推送默认分支。
  2. `incomplete` 合同允许人工审查后生成选择版；不自动改变交付状态，仍按工作文件标注和打包。
  3. 指引“重新解析”采用 **方案 A：生成新版本 V2，`parent_version_id=V1`，V1 永不修改**。
  4. 只读诊断不再作为工作台产品入口；清理前端残留，后端 `mode=diagnosis` 暂留内部能力。
  5. 不关闭注册、不加登录限流；该风险由产品接受，本轮不修改。
  6. Langfuse 默认上传 prompt/completion 文本保持现状；当前合同均为公开资料且用户已授权出服务器。

## 0. 当前 WIP 与冻结要求

本轮在用户叫停前已产生 P0-3 的未完成 WIP，**不得当作已完成**：

- 改动文件：`fundlex/guide_store.py`、`fundlex/api.py`、`frontend/app.js`、`frontend/compare.html`、`tests/test_guide_store.py`、`tests/test_guide_api.py`。
- 已实现方向：`parent_version_id`、重新解析创建新版本、release 退回 attempt、清理只读诊断 UI、选择版工作文件下载标签。
- 已知失败：`tests/test_guide_api.py::test_guide_parse_endpoint_requeues_owner_versions_only` 仍有一条断言未更新，当前不是绿灯状态。
- WIP 补丁备份：`/tmp/opencode/fundlex-outer-remediation-wip-20261028.patch`（sha256 `90831114487dd5690e3d62e8a47f5cfa96ecb0b1751598303ccdaa2d885fd769`）。注意：该补丁是相对 HEAD 的 diff，包含这些文件上已有的其他未提交内容，使用前必须人工拆分。
- Phase 0 必须先决定：**在隔离 worktree 中继续完成这批 WIP，还是丢弃后从干净基线重做**。未决定前不继续修改代码、不提交、不发布。

## 1. 不可破坏的接口契约

### 1.1 交付状态机

```text
complete / complete_with_exceptions
    └── final + redline
        └── 人工审查 → selected_final（可作为最终版）

incomplete
    └── working_final + working_redline
        └── 允许人工审查
            └── selected_final 仍为工作文件
                ├── delivery_status 不自动改变
                ├── ZIP 归入“工作文件（未完成）”
                └── 下载名/UI 不得标成“最终版”
```

- `selected_final` 的生成不再被 `incomplete` 一律禁止；但“生成”不等于“交付完成”。
- 任何 API、ZIP、前端文案必须读取同一个 `delivery_status` 判定，不得各写一套。
- 评测/诊断文件继续与正式合同隔离。

### 1.2 指引版本状态机（方案 A）

```text
上传 V1 → 解析 V1 → 任务绑定 V1（id + hash）
                         │
用户重新解析 V1 ────────→ 创建 V2（parent_version_id=V1）
                         │
                         ├── V1 行、rules_json、rules_sha256 永不修改
                         ├── 已绑定 V1 的任务继续用 V1
                         └── 用户显式启用 V2 后，新任务才绑定 V2
```

- `enqueue_parse()` 不得再原地修改 `parsed/released` 版本；只允许未发布状态的首次尝试/重试。
- 重新解析必须写新行、复制源文件、创建新 parse job；重复点击同一源文件复用已存在的 queued/leased 新版本，不重复建行。
- 旧任务绑定哈希校验失败必须继续 fail closed，但正常重新解析不得再触发该失败。

### 1.3 引擎兼容版本

- `engine_build()` 只覆盖会改变合同处理结果的核心代码、规则和指引。
- 新增 `service_build()` 覆盖全部后端源码，用于审计/部署展示。
- 批次继续 pin `engine_build()`；修改 `api.py`、`auth.py`、`db.py`、`html_view.py`、前端或运维代码不得让排队任务 `ENGINE_SCHEMA_MISMATCH`。
- 修改核心引擎文件必须让 `engine_build()` 变化；测试必须同时覆盖“变”和“不变”。

### 1.4 查询与轮询

- 任务/合同列表的过滤、排序、分页下推到 SQL（`WHERE` / `ORDER BY` / `LIMIT` / `OFFSET`）。
- 列表接口禁止 per-document/per-task 查询；artifact、metrics、reason 聚合批量查询。
- 前端轮询改为按任务/游标增量读取；不再每 5 秒全量扫描所有任务和合同。

### 1.5 账号安全

- 保留注册开放和无限流（产品决定）。
- 只补“不能禁用最后一个 enabled admin”和 bootstrap 恢复规则；不改变登录/注册策略。

## 2. 多 Agent 分工

| 角色 | 职责 | 主要文件 | 依赖/冲突 |
|---|---|---|---|
| Captain/Integrator（主 agent） | 计划、接口冻结、合并、最终验收、集中问题记录 | 全仓、`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` | 所有 |
| Agent A：交付状态机 | P0-1 selected artifact、ZIP/下载标签、交付门测试 | `fundlex/api.py`（selection 段）、`fundlex/store.py`、`fundlex/edit_summary.py`、`tests/test_revision_api.py`、`tests/test_tasks_api.py` | 先于 C；与 B/D 争 `api.py` |
| Agent B：指引版本/任务状态机 | P0-3 新版本、parse job claim/release、迁移 | `fundlex/guide_store.py`、`fundlex/api.py`（guide 段）、`frontend/app.js` guide 段、`tests/test_guide_store.py`、`tests/test_guide_api.py` | 与 A/D 争 `api.py`；可与 A 并行但分段合并 |
| Agent C：引擎兼容版本/发布 | `engine_build`/`service_build` 拆分、发布顺序、回滚 | `fundlex/store.py`、`fundlex/jobs.py`、`tools/deploy/*`、`tests/test_fingerprint_engine_build.py` | 必须在 A 之后改 `store.py`；发布前完成 |
| Agent D：查询/轮询 | SQL 分页、N+1、通知游标 | `fundlex/tasks.py`、`fundlex/api.py`（list 段）、`frontend/src/api/hooks.ts`、`frontend/src/pages/*`、`frontend/app.js` | 在 A/B 后合并，避免 `api.py` 冲突 |
| Agent E：账号安全 | last-admin 保护、bootstrap 恢复 | `fundlex/api.py`（admin 段）、`fundlex/auth.py`、`tests/test_auth*.py` | 小补丁，最后合并 |
| Agent F：前端一致性 | 删除只读诊断残留、V1/V2 文案、指引版本展示、HTML 保真声明 | `frontend/app.js`、`frontend/compare.html`、`frontend/src/**`、`frontend/tests/**` | 与 B/D 争前端文件 |
| Agent G：QA/E2E | 回归矩阵、迁移/并发/浏览器/真实 E2E、证据包 | `tests/**`、`tests/browser/**`、`tools/evaluation/*` | 全程；最终验收 |

### 协作规则

1. **一个 worktree 一个 agent**，从集成分支创建，禁止在 `/home/opencode/fundlex` 主工作区直接并行改同一文件。
2. 集成分支建议：`codex/outer-remediation-20261028`，从当前 HEAD `f2e318e` 创建；当前主工作区的其他 dirty 文件不整树提交。
3. 每个 agent 只提交自己的文件和测试；提交前跑定向测试；不跑真实模型、不发布。
4. `fundlex/api.py` 按段分配：A（selection）、B（guide）、D（list）、E（admin）。同一时段最多两个 agent 改同一文件；合并顺序 A → B → C → D → E。
5. 每个 phase 结束由 Captain 合并、跑全量、登记集中问题记录；冲突由 Captain 解决，agent 不自行改写别人的段。
6. 任何数据库迁移必须同时覆盖 SQLite 和 MySQL，并在 Phase 4 用旧库快照演练。

## 3. 分阶段计划

### Phase 0：冻结与基线（0.5–1 天）

- 决定当前 P0-3 WIP 的去留；在隔离 worktree 中继续或重做。
- 创建集成分支和 5 个 worktree；记录每个 agent 的文件所有权。
- 跑一次基线：定向 guide/store/revision 测试 + 全量 `pytest`（记录已知失败，不修）。
- 把本轮确认的 P0/P1 问题登记到 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`，引用本计划。
- 冻结本计划第 1 节的接口契约。
- 退出条件：基线可重复、WIP 有归属、没有未登记的新问题、所有 agent 明确文件边界。

### Phase 1：P0 与部署前置（3–4 天）

**1A 交付状态机（Agent A）**

- `incomplete` 允许审查/生成 `selected_final`，但保持 `delivery_status=incomplete`。
- 下载名、详情页、ZIP 统一标为工作文件；`complete/complete_with_exceptions` 才进“最终版”。
- 修复 V1 点击下载仍叫“最终版（按人工选择）”的文案。
- 测试：incomplete accept-all 成功但归工作文件；complete accept-all 归最终版；ZIP 槽位；下载标签。

**1B 指引版本（Agent B）**

- 加 `parent_version_id` 迁移；重新解析创建新版本；旧行/hash 不变。
- `enqueue_parse` 拒绝原地修改 parsed/released。
- 前端重新解析后刷新版本列表，显示“基于 V…”。
- 测试：旧任务绑定旧版本仍可解析；新版本可启用；重复点击只产生一个 queued/leased 新版本；旧 hash 不变。

**1C 指引 parse job 状态机（Agent B）**

- release 退回 attempt，连续 release 不耗尽；旧 `queued + attempts=3` 清理为 failed/可重试。
- 测试：连续 3 次 release 后仍能 claim；lease 过期仍会耗尽；stale worker 不能写回。

**1D 引擎兼容版本（Agent C）**

- 拆分 `engine_build()`/`service_build()`；批次 pin 核心 digest；部署检查两者。
- 测试：改 `api.py`/`auth.py` 不变；改 `recall.py`/`generation/**`/规则/指引会变；旧队列任务在核心未变时继续。

**1E 只读诊断清理（Agent F）**

- 删除前端 `importMode`/`syncImportMode`/模式选择器残留；工作台只保留正式修订。
- 不删除后端 `mode=diagnosis` 内部能力（飞书/评测可能使用）。

**Phase 1 退出条件**：1A–1E 定向测试全绿；`engine_build` 拆分先于任何发布；不部署生产。

### Phase 2：P1 外围加固（2–3 天）

- **Agent E**：last-admin 保护；`bootstrap_admin` 在无 enabled admin 时的恢复策略；测试自禁用/唯一管理员。
- **Agent D**：任务/合同 SQL 分页、过滤、排序；移除 N+1；reason/artifact/metrics 批量查询；列表基准测试。
- **Agent D + F**：轮询改增量/游标；V1/V2 统一；避免 5 秒全量扫描。
- **Agent F**：HTML 预览文案改为“结构化修订预览”，删除“与 Word 一致/实际呈现”的过度承诺。
- **Agent C/F**：selected/attempt 对象 GC 或 retention 脚本；至少提供可运行的 orphan 检查。
- **Agent G**：CI 触发分支修正（默认分支 `codex/fundlex-recall-first` 纳入 push/PR；当前 workflow 只覆盖 main/master）。

**Phase 2 退出条件**：分页查询计划/基准通过；admin 锁定测试通过；浏览器 smoke 无回归；CI 在默认分支可触发。

### Phase 3：前端一致性与文档（1–2 天）

- V1/V2 对齐：交付状态、工作文件/最终版、选择版、含例外、评测/诊断标签。
- 指引版本列表、父版本、重新解析提示、启用流程。
- 工作台帮助文案与报告文案统一：报告/诊断/工作文件不作为最终合同。
- 更新 `docs/ACTIVE_HANDOFF.md`、集中问题记录、部署说明。
- 不新增真实模型调用。

### Phase 4：验证、发布与真实 E2E（1–2 天 + 真实运行）

- 全量 Python、前端 typecheck/lint/Vitest/build、Playwright V1/V2、MySQL、迁移、并发。
- 旧库快照演练：`parent_version_id` 迁移、旧 `queued attempts=3` 清理、旧 selected artifacts。
- 发布前：暂停/清空队列、备份数据库、确认 `engine_build`/`service_build`、部署单元与 nginx。
- 发布后：capabilities、排队任务兼容性、管理入口、下载/ZIP。
- 真实合同 E2E：登录 → 创建任务 → 上传 → Worker 实际处理 → 检查 DOCX 前后差异/修订痕迹 → 人工接受/拒绝 → 下载 selected/最终/报告 → 哈希一致。
- 真实模型调用前按项目规定预登记预算/账本；不使用替身模型冒充验收。
- 回滚：保留上一版部署目录、数据库备份、queue 恢复步骤；失败时不宣称完成。

## 4. 测试矩阵

| 层 | 内容 | 负责 |
|---|---|---|
| 单元 | guide_store 状态机、store selected、engine_build、auth last-admin | A/B/C/E |
| API | TestClient：incomplete/complete 选择、reparse 新版本、分页、admin | A/B/D/E |
| 迁移 | 旧 `guide_versions` 无 `parent_version_id`；MySQL/SQLite | B/G |
| 并发 | 双 reparse、重复 accept、stale lease、两次 release | B/G |
| 前端 | Vitest、V1/V2 Playwright、下载标签、工作文件/最终版 | F/G |
| 查询 | EXPLAIN/查询计数、N+1 断言、分页边界 | D/G |
| 发布 | 队列暂停/恢复、engine_build 不变/变、回滚 | C/G |
| 真实 E2E | 真实合同、真实 Worker、真实 DOCX 差异、哈希 | G/Captain |

## 5. 验收标准（摘要）

- `incomplete` 人工审查可生成选择版，但永远不会被自动标为 `complete` 或进入“最终版”ZIP。
- 重新解析后旧版本 id/hash 不变；旧任务继续可处理；新版本需显式启用。
- 连续 3 次可恢复 release 不会让 parse job 卡死；旧 stuck job 可恢复。
- 修改 `api.py`/`auth.py` 不改变 `engine_build()`；修改核心引擎文件会改变。
- 任务/合同分页由 SQL 完成，列表请求的查询次数不随合同数线性增长。
- 不能禁用最后一个 enabled admin。
- 前端不再出现“只读诊断”入口；所有“最终版/工作文件”文案与 `delivery_status` 一致。
- CI 在默认分支和 PR 上可运行；全量测试、浏览器、迁移、发布演练通过后，才进入真实 E2E。

## 6. 风险与待确认

1. `fundlex/api.py`/`store.py` 是热点文件，A/B/C/D/E 并行会产生冲突；必须按 A → B → C → D → E 合并。
2. 指引版本迁移涉及生产 MySQL；必须先备份并用旧库快照演练。
3. `engine_build` 拆分若 allowlist 漏掉核心模块，会让旧队列任务错误复用；需要“变/不变”双向测试。
4. P0-1 的“人工审查”是否包括“一键接受全部”仍需产品确认；当前计划按“允许生成、仍标工作文件”执行。
5. 真实 E2E 依赖模型预算和合同样本；预算未预登记前只做替身/回放测试，不冒充验收。
6. 注册开放、无限流、Langfuse 原文上传均为产品已接受风险；若后续处理非公开合同，必须重新评估。

## 7. 执行进度（2026-10-28）

当前集成分支：`codex/outer-remediation-20261028`（从当前工作区 HEAD 创建，未推送）。

- Phase 0：已在隔离 worktree 继续 P0-3 WIP；WIP 补丁保留在 `/tmp/opencode/fundlex-outer-remediation-wip-20261028.patch`。
- P0-3（方案 A）：已实现并提交 `3b4afee`。重新解析创建新版本，旧版本 id/hash 不变；旧任务快照测试通过；旧 parse job 会标记 `GUIDE_VERSION_SUPERSEDED`。
- 指引 parse job：release 退回 attempt；连续 release 不耗尽；旧 `queued + attempts=3` 会被清理。相关测试通过。
- P0-1：`selected_final` 人工生成保持允许；incomplete 的 ZIP/下载标签统一为工作文件；V1/V2 文案已对齐；回归测试通过。
- 引擎兼容版本：已实现并提交 `766c8fa`；`engine_build()` 只覆盖结果相关模块，`service_build()` 覆盖全部后端；部署脚本增加 `.fundlex-service-build` 校验（`5ecf23f`）。
- 最后一个管理员保护：已实现并提交 `a5abdfa`；API 返回 `LAST_ADMIN_REQUIRED`，V1/V2 前端有中文提示（`0179081`）。
- 前端一致性：V2 指引详情支持配置后的新版本跳转；重新解析按钮覆盖 `parsed/released`；轮询频率下调（`59cc317`）。
- 对象 GC：新增 `tools/maintenance/prune_orphan_objects.py`，默认 dry-run，测试 `tests/test_object_gc.py` 通过（`cb21d0d`）。
- HTML 保真文案：已改为“结构化修订预览”，不再声称等同 Word。
- CI：`ci.yml`/`delivery-e2e.yml` 的 push 分支加入默认分支和集成分支。
- 已修复测试：`tests/test_tasks_api.py` 的上传限制断言、`tests/test_recall_integration.py` 的 release attempt 期望、`tests/test_feishu_oauth_api.py` 的 PNG fixture、浏览器测试的旧模式选择器断言。
- 已验证：干净集成 worktree 最终全量 pytest **1782 passed / 85 skipped**（`/tmp/opencode/outer-full-pytest-final2.log`）；V1 浏览器在干净 worktree **34 passed**；V2 浏览器 **10 passed**；前端 typecheck/lint/Vitest/build 通过。
- Agent D 已合并（`2e5435c`）：任务/合同列表改为 SQL 过滤/排序/分页，批量读取 report/artifact；`assert_owned` 避免列表前构建完整 summary。新增 6 类分页/过滤/owner/查询次数测试。保留项：`reason_options` 仍需每请求解析该任务全部 report_json；`error_code` 精确过滤仍可能回退到 Python；legacy 分页仍是 O(legacy batches + page depth)；MySQL 未实跑。
- 为保持默认分支与当前工作区一致，已把工作区中已通过测试的 compare 选择版前后端补入（`f42180d`、`9809c73`）；干净 worktree 的 V1 浏览器 **34 passed**，V2 **10 passed**。这不是新增外围需求，而是避免默认分支保留半套 compare UI/后端。
- 仍在进行：最终全量 pytest（`/tmp/opencode/outer-full-pytest-final.log`）、迁移/发布演练；真实模型 E2E 需预算登记。

## 8. 下一步

1. 合并 Agent D 的分页提交，解决 `fundlex/tasks.py`/`fundlex/api.py` 冲突。
2. 在干净集成 worktree 跑全量 pytest、前端 typecheck/lint/Vitest/build、Playwright V1/V2。
3. 用旧库快照演练 `parent_version_id` 迁移和 `queued+attempts=3` 清理。
4. 发布演练：暂停/清空队列，确认 `engine_build`/`service_build`，再发布；不直接在生产跑真实模型批次。
5. 真实合同 E2E 需按项目规定预登记预算；未登记前不冒充完成。
