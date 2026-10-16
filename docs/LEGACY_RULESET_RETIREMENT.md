# A/B 遗留规则集运行时下线改造方案（LEGACY_RULESET_RETIREMENT）

- 状态：**方案已确认，实施中**（产品负责人 2026-10-16 决定：A/B 运行时下线，发布门随 B 一起下线，交付语义改由指引版本状态决定）
- 关联问题：FL-D092（静态资源缓存，已修）、FL-D093（前端用 ruleset 标志判断全局可用性）、FL-D094（A 空壳载体会拖垮 recall-first 建任务）
- 关联文档：`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`、`docs/ACTIVE_HANDOFF.md`、`docs/HTML_PRESENTATION_PLAN.md`

---

## 1. 背景与现状（实测证据）

### 1.1 三套并存的「规则来源 + 门禁」

| # | 规则来源 | 存储 | 生产者 | 消费者 | 状态门 |
|---|---|---|---|---|---|
| **A** | `rules/rules_v1.json` | 仓库文件 | 离线 `compile_catalogue.py` | 遗留 `pipeline.py`（只读诊断） | `release_policy.status = unreleased` |
| **B** | `rules/rules_v2.json` | 仓库文件 | 离线 `compile_v2.py` + `rules/release_v2.py` 发布 | 遗留 `v2_pipeline.py` | `unreleased` → 强制 `evaluation` 模式 |
| **C** | 指引快照（内置 + 用户上传） | **数据库 `guide_versions`** | 上传 DOCX → 真实模型解析 | **recall-first** `recall_pipeline.py` | `uploaded → parsed → 启用` |

A 与 C 同源：`rules_v1.json.source_sha256` 与 `guides/builtin_guide_v1.json.source_sha256` 前缀均为 `b77be53c3439d785`（同一份「v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx」）。

### 1.2 生产环境实测（2026-10-16）

```
按引擎分布：
  engine_id='recall_first'   212 个任务   ← 全部实际工作
  engine_id=''                 1 个任务   ← 遗留孤例 efce8a8eacf7491a844d838970c2158f

按 ruleset_version：
  'v1'   212   （recall-first 任务的空壳载体字段，非实际生效规则）
  'v2'     1   （那唯一一个遗留任务）

batches：completed 215 / running 1
```

**212 : 1。** 唯一的遗留任务 `engine_id` 为空。

### 1.3 A/B 的调用者只剩测试与离线评测

全仓库调用点（排除 `.venv`）：

| 调用者 | A (`pipeline.process`) | B (`process_v2`) |
|---|---|---|
| 在线 API / Worker | **无** | **无** |
| 测试 | `test_pipeline.py`、`test_api_store.py` 等 | `test_v2_*.py`、`test_v3_delivery_review_gate.py` 等 |
| 离线评测工具 | `controlled_regression.py`、`real_scenarios.py`、`real_resume.py` | `v2_pilot.py` |

### 1.4 关键缺陷（本次改造的直接动因）

1. **在线入口到不了 A/B**：`api.py:764` 分流，非 `recall_first` 的 `engine_id` 一律 422；前端永远传 `engine_id='recall_first'`（`app.js:137`），且 capabilities 的 `engine_id` 写死（`api.py:572`）。UI 用户永远走 C。
2. **A 是空壳载体且有拖垮风险（FL-D094）**：`api.py:767` 建 recall-first 任务时 `carrier = load_ruleset("v1")`，仅为满足 `tasks.ruleset_version NOT NULL`。该字段对 recall-first **无任何作用**，但 A 加载失败会直接 503，**拖垮 C 的建任务**。
3. **前端混用两套判据（FL-D093）**：`importMode` 由 B 决定、提交按 C 走、「可直接使用」由 B 的 `auto_write_enabled` 决定 → 用户在使用完全健康的 C，却看到「不可认定」。
4. **发布门只对 B 有意义**，却被前端当全局可用性判据。

---

## 2. 设计目标

**终态：C（指引快照）是唯一规则来源；A/B 退出运行时，降级为开发期资产。**

1. 运行时只有一个规则来源（C），一条链路（recall-first）。
2. 能力接口只暴露「当前引擎的模式与可用性」，前端不再做跨引擎与运算。
3. 「发布门」概念随 B 下线；交付语义由**指引版本状态**决定。
4. A/B 的代码与规则文件保留（测试与历史回溯用），但**不参与运行时**。
5. 遗留任务可读、可回溯，但不与新任务混排、不产生误导性状态。

### 2.1 交付语义（用户 2026-10-16 确认：选项 A）

- **删除** ruleset 发布门与 `evaluation_*` 判据（`auto_write_enabled`、`revision_mode`、`revision_auto_write_enabled` 不再由前端消费）。
- **交付语义改由指引版本状态决定**：指引版本处于可启用状态（`parsed`/`released`）且任务绑定的 `guide_rules_sha256` 一致 → 该任务为正式交付路径。
- recall-first 的 `delivery_status = complete` / `complete_with_exceptions` 即视为可用。
- 「可直接使用」按**任务实际路径**判断，不含任何 ruleset 字段。

---

## 3. 全链路影响面分析

### 3.1 后端

| 位置 | 现状 | 改造 |
|---|---|---|
| `api.py:536-555` `capabilities` | 同时返回 A(`ruleset_version`/`actions_total`/`auto_write_*`)、B(`revision_*`)、C(`engine_id`/`guide`) | 收敛为 `engine` 对象：`{id, rule_source, guide, delivery_mode, auto_write_enabled}`；A/B 字段不再平铺 |
| `api.py:758-783` `create_task` | `engine`/`ruleset_version` 二选一；recall-first 走 `load_ruleset("v1")` 当 carrier | 仅保留 `engine_id`；删 `ruleset_version` 分支与 A carrier 依赖（**FL-D094 修复**） |
| `api.py:693` `parse_guide` 等 | 已只服务 C | 不动 |
| `api.py:1079-1100` 静态资源 | 已加内容哈希缓存（`64b0302`） | 不动 |
| `tasks.py:25,57-79` | 任务表 `ruleset_version NOT NULL`，随 carrier 写入 A 的版本 | recall-first 任务写入**空字符串/固定占位**，消除对 A 的加载依赖；保留列以兼容历史行 |
| `tasks.py:271-276` `batches` | 同样写 `ruleset_version` | 同上 |
| `jobs.py:62-76` `_default_processor` | `engine_id == recall_first` → C；否则 `ruleset_version == v2` → B；再否则 A | 只保留 C 分支；A/B 分支删除（或改为仅在显式 legacy 标志下可达，见 §3.4） |
| `store.py` 交付判定 | `_is_recall_report` 已按 `engine_id`/`schema_version` 分流 | 复核：确保无 A/B 分支泄漏到 recall-first 判定 |
| `pipeline.py` / `v2_pipeline.py` / `rules.py` / `rules_v2.py` | A/B 实现 | **保留**（测试与离线工具依赖），但不再被在线路径引用 |

### 3.2 前端（`frontend/app.js`）

| 位置 | 现状 | 改造 |
|---|---|---|
| `loadCapabilities` (117) | 读 `ruleset_version`、`revision_*`、`engine_id`/`guide` | 只读 `cap.engine.*` |
| `syncImportMode` (131) | 按 `engine_id==='recall_first'` 判断 + 回退到 B 文案 | 简化为按 `cap.engine.rule_source` / `guide` 状态 |
| `submissionPayload` (137) | `engine_id` 或 `ruleset_version` 二选一 | 只传 `engine_id` |
| `renderReport` (289) `usable` | 四条件含 `auto_write_enabled` | 改为：`交付门通过 && delivery ∈ {complete, complete_with_exceptions} && 产物存在` |
| `downloadSection` (302) | `final` 过滤依赖 `usable`；含 `evaluation_*` 项 | 保留 `usable` 过滤逻辑（语义已修正）；`evaluation_*` 项对非评测任务自然不出现 |
| 能力详情面板 (117) | 显示「只读诊断规则」+「合同修订规则 v2 · 评测模式」 | 改为显示当前引擎与指引版本信息 |

### 3.3 测试

- 依赖 A/B 的测试（`test_pipeline.py`、`test_v2_*.py`、`test_v3_delivery_review_gate.py`、`test_api_store.py` 等）**保持通过**：A/B 实现代码不删。
- 需要更新断言 API 形态的测试：`test_api_*`、`test_capabilities`、`test_revision_api.py`（若引用了被移除字段）。
- **新增测试**：
  - capabilities 不再含 A/B 平铺字段，含 `engine` 对象；
  - `/api/tasks` 只接受 `engine_id`，传 `ruleset_version` 的行为明确（拒绝或兼容）；
  - recall-first 建任务**不再加载 A**（可用 monkeypatch 让 `load_ruleset` 抛错，验证建任务仍成功 → FL-D094 回归）；
  - `usable` 判定不含 ruleset 字段（前端逻辑以接口返回驱动）。

### 3.4 遗留任务与回溯

- 保留那 1 个遗留任务的可读性（报告/产物仍可下载）。
- 前端对 `legacy` 任务明确标注，仅只读。
- **不删除** A/B 代码与规则文件 → 遗留任务回溯与离线评测仍可复现。

### 3.5 发布门下线（本次重点）

| 项 | 处置 |
|---|---|
| `rules/*.json` 的 `release_policy` | **保留文件字段**（A/B 代码仍在用），但**不再进入 capabilities / 前端判据** |
| `rules_v2.py:241` `V2_RELEASE_NOT_SEPARATE` 校验 | 保留（A/B 自洽性需要） |
| `revision_mode` / `revision_auto_write_enabled` | 从 capabilities 移除 |
| `v2_pipeline.py` 的 `evaluation` 分支 | 保留（B 的离线评测仍需要）；B 不再在线可达，故不影响用户 |
| 前端「不可认定」 | 改由任务实际交付路径判断，不再受 ruleset 标志影响 |

---

## 4. 任务分解与顺序（版本管理）

**基线**：分支 `codex/fundlex-recall-first`，起点 commit `21fb540`（本轮开始前工作树干净，仅未跟踪 `tools/evaluation/p6_trace_report.py` 属既有其他工作，勿动）。

| 阶段 | 内容 | 产出 commit | 验证 |
|---|---|---|---|
| **P0** | 方案文档 + 问题登记（FL-D093/FL-D094） | `docs: 登记 FL-D093/FL-D094 并新增 A/B 下线方案` | 文档评审自检 |
| **P1** | 后端能力接口收敛：`capabilities` 改为 `engine` 对象 | `refactor(api): capabilities 收敛为 engine 对象` | `test_capabilities` 更新 + 新增 |
| **P2** | 建任务路径收敛：删 `ruleset_version` 分支与 A carrier（FL-D094） | `refactor(api): /api/tasks 仅接受 engine_id，去除 A 载体依赖` | 新增 monkeypatch 回归测试 |
| **P3** | 处理器分流收敛：`jobs._default_processor` 只留 C | `refactor(jobs): 处理器只保留 recall-first 分支` | 全量测试 |
| **P4** | 任务/批次表字段与 recall-first 解耦 | `refactor(tasks): recall-first 任务不再写 A 版本` | 全量测试 + 迁移兼容 |
| **P5** | 前端改造：capabilities 消费、`usable` 语义、下载区、能力面板文案 | `refactor(frontend): 按引擎路径判断可用性` | 全量测试 + 真实浏览器 |
| **P6** | 遗留任务标注与只读回溯 | `feat(frontend): 遗留任务只读标注` | 真实浏览器 |
| **P7** | 文档收尾：更新 handoff / 台账 / 集中问题记录 | `docs: A/B 下线收尾与验证证据` | — |
| **P8** | 发布 + 真实端到端交付验收 | —（部署不改仓库） | 见 §6 |

**版本管理规则**：
- 每个阶段独立 commit，消息用中文、说明意图与影响面。
- 每阶段结束跑**全量测试**（排除既有基线失败 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`，缺参考文件，与本工作无关）。
- **未获用户明确要求不 push 远程**。
- 部署用 `bash tools/deploy/publish_workspace.sh`；部署后核对 `/opt/fundlex-recall-first` 与仓库逐文件 sha256 一致。

---

## 5. 风险与防护（不要改出 bug）

| 风险 | 防护 |
|---|---|
| 删除 A/B 在线分支后，历史任务无法回溯 | A/B 代码与规则文件**不删**；遗留任务只读保留 |
| 任务表 `ruleset_version NOT NULL` 导致空值时插入失败 | 写入固定占位（如 `""` 或 `legacy`）而非 NULL；保留列兼容历史行 |
| 前端 `usable` 语义变更误伤现有交付 | 新判据**只放宽不加严**：原有 `complete` 交付在新判据下仍为可用 |
| capabilities 收敛导致前端读不到字段而崩溃 | 分段改造：后端先加 `engine` 对象**同时保留旧字段**（过渡），前端切换后再删旧字段 |
| 离线评测工具/测试因 A/B 引用变化而失败 | A/B 实现冻结不删；仅改在线调用点 |
| 发布门字段被误删导致 A/B 测试失败 | `release_policy` 与校验逻辑保留，仅从 capabilities 移除暴露 |
| 「不可认定」误改后用户仍困惑 | 新语义需在 UI 明确标注判据来源（引擎交付路径，非 ruleset 标志） |

**核心原则：先加后删（expand–contract）。** 后端先同时提供新旧字段，前端切换完成、测试全绿后，再移除旧字段。

---

## 6. 验收标准（真实端到端）

1. 全量测试通过（除既有基线失败项）。
2. 生产部署后 `/api/capabilities` 返回 `engine` 对象且无 A/B 平铺字段。
3. **真实浏览器 + 真实登录**：建任务（默认入口 `engine_id=recall_first`）→ 上传真实合同 → 真实 Worker + 真实模型 → 报告与产物下载 → 逐条审查修订 → 生成 `selected_final`。
4. **FL-D094 回归**：验证 recall-first 建任务不再依赖 A（monkeypatch 层面 + 生产实测）。
5. 「可直接使用」在 recall-first 完整交付下**不再显示「不可认定」**；在确有例外/不完整时如实显示。
6. 遗留任务可读、可回溯、标注 legacy，不与新任务混排。
7. 部署副本与仓库 sha256 一致，服务 active，0 控制台错误。

---

## 7. 进度台账

| 阶段 | 状态 |
|---|---|
| P0 方案文档 + 问题登记 | ✅ |
| P1 能力接口收敛 | ⬜ |
| P2 建任务路径收敛 | ⬜ |
| P3 处理器分流收敛 | ⬜ |
| P4 任务表字段解耦 | ⬜ |
| P5 前端改造 | ⬜ |
| P6 遗留任务标注 | ⬜ |
| P7 文档收尾 | ⬜ |
| P8 发布与端到端验收 | ⬜ |
