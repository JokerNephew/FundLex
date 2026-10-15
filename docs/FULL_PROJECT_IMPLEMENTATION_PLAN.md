# FundLex 完整项目实施计划（召回优先新链路）

创建：2026-10-14。接续自 `docs/FULL_PROJECT_DEVELOPMENT_HANDOFF.md`（整合规格）与 `AGENTS.md`（项目规定）。
本文是**执行计划**：写待做/进行中/已完成/阻塞、代码位置与实际证据。不是完成声明，不复制整合文档作为勾选清单。
问题与处理方法持续登记在 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`；断点见 `docs/ACTIVE_HANDOFF.md`。

## 0. 起点核对（2026-10-14）

- 分支 `codex/fundlex-recall-first`；HEAD `3ed4e96`（`docs: replace the migration plan with the recall-first target design`）。
- 未提交：3 个已跟踪文件被修改（IMPLEMENTATION_PLAN.md、README.md、docs/RECALL_FIRST_DESIGN.md 各 +2 行），29 项未跟踪（AGENTS.md、本轮文档、references/、frontend/assets、workbench/style-templates、tools/research 等）。全部保留，不清理、不误提交。
- 环境：Windows 11 / PowerShell 7；Python `.venv\Scripts\python.exe`（3.12）；依赖见 pyproject.toml/uv.lock。
- 模型：User 环境变量 `LLM_PROVIDER=OpenCodeGo`、`LLM_MODEL=deepseek-v4.1-flash`、`LLM_BASE_URL`、`LLM_API_KEY` 均存在（不打印值）。价格经 models 工具核对：input $0.15/M、output $0.60/M、cache read $0.003/M。
- 账本：`%LOCALAPPDATA%\FundLex\runtime\model_budget.sqlite` 现有 10 次调用 / $0.0173（累计制，不重置）。历史 721 次 / $0.344 见 MODEL_USAGE_AUDIT.json。
- 旧 v2 包 `rules/rules_v2.json` 为 unreleased（auto_write_enabled=false，22 动作），当前只出评测产物。新链路不复用旧 22 动作门禁。

## 1. 目标与完成定义

按用户要求完成整个项目：前端、后端、修订引擎、指引配置、账号、持久任务、MySQL、云部署、真实用户端到端交付，以及 20—30 份真实合同评测与优化闭环。完成定义以整合文档 §16 为准：正常正式修改链路实际通过；单份合同未完成如实显示。

## 2. 架构决策（本计划的技术基线）

### 2.1 引擎标识与绑定

- 新引擎 `engine_id = "recall_first"`；服务端在任务创建时绑定**不可变指引快照**（GuideVersion id + rules_sha256 + 解析/prompt 版本）。
- 旧 v1/v2 任务只读保留；新任务入口只接受新 engine 契约；不静默回退旧引擎。
- Worker 按 engine_id 分派处理器；engine_build/schema_version 漂移继续 fail-closed。

### 2.2 新模块（fundlex/）

| 模块 | 职责 |
| --- | --- |
| `guide.py` | 指引 DOCX 解析（代码提取 + 模型分组）、独立来源核验、GuideRule schema、内置指引构建 |
| `guide_store.py` | 指引版本持久化（guide_versions、guide_config）、状态机（uploaded→parsing→parsed→validated→released/archived） |
| `recall.py` | 引擎核心：结构索引、事实画像、规则→业务子节映射、目标盘点、联合规划、文案组装 |
| `recall_pipeline.py` | 编排：原件重放写入、实际产物审计、自动修复与仲裁、最终分块全文查漏、交付裁决 |
| `recall_prompts.py` | 新任务类型的指令与 JSON schema（版本化） |
| `delivery.py` | DeliveryService：complete/incomplete/excluded/not_generated 统一裁决 |

### 2.3 复用与改造

- 直接复用：`docx.py`（inspect/validate/generate_artifacts 全部机械能力）、`model.py`（传输/预算/checkpoint）、`store.py`/`tasks.py`/`jobs.py`（队列/租约/幂等/对象）、`api.py`/`auth.py`（账号/会话）、`artifact_review.py` 的窗口化复核思路。
- 已知限制（登记 FL-D032）：`docx.py` 只支持段内单段编辑（run 级替换/插入，不可跨段、不可增删段落、不可改表格结构）。新引擎按“跨段语义拆为多个段内精确操作”实现；段级插入/删除如需，另行扩展并验证。
- 不复用：v2 的固定 22 动作定位/模板相等/整 action 回滚/评测模式门禁；`rules_v2.json` 不再作为新任务输入。

### 2.4 数据与状态

- 目标状态：pending / needs_edit / satisfied / not_applicable / modified_verified / unresolved / unsupported。
- 交付状态：complete / incomplete / excluded / not_generated；不完整交付 `working_final.docx` / `working_redline.docx`，不用 final 名称。
- 指引状态：uploaded / parsing / parsed / parse_failed / validated / released / archived。
- 任务绑定 workflow_epoch：事实更正/输入版本变化使 epoch 递增，迟到响应与旧 Worker 不能提交过期版本（复用 fencing_token + 新列）。

## 3. 阶段计划

### P0 盘点与基线（进行中）

- [x] 核对 branch/HEAD/dirty/环境/账本/价格。
- [x] 阅读 AGENTS、整合文档、问题记录、评测计划、原件阅读、设计审查、RECALL_FIRST_DESIGN。
- [x] 代码基线调查（docx/store/tasks/jobs/api/frontend/v2/rules/评测工具）。
- [x] 提取指引全文 107 段 6250 字符到 `var/design-reading-20261014/guide_paragraphs.txt`，人工通读并整理 15 个业务组（见 §4）。
- [x] 建立本计划、`docs/ACTIVE_HANDOFF.md`、新 FL-D 条目。
- [ ] 基线测试：`pytest` 全套通过性核对（记录既有失败，不隐藏）。
- [ ] 真实模型连通性探针（1 次最小调用，记账）。

### P1 契约与结构

- [ ] 新 report schema（schema_version=3、engine=recall_first）与状态枚举先冻结。
- [ ] `store.py`/`tasks.py` 迁移：engine_id、guide 绑定列、新产物种类（working_final/working_redline）、validate_delivery 新分支。
- [ ] `docx.py` 能力补充：拒绝全部修订等价校验（reject-all == source），保留现有 accept-all 校验。
- [ ] 结构专项：跨段、表格、不可编辑部件、目录/书眉、编号书签的读取缺口清单（对照 FL-D002/FL-D017）。

### P2 指引

- [ ] `guide.py` 解析器 + 独立核验 + 内置指引构建（真实模型调用，冻结为 `guides/builtin_guide_v1.json`）。
- [ ] `guide_store.py` + API（/api/guides、/api/settings/guide）。
- [ ] 配置页前端（上传/解析状态/查看/启用/恢复内置/历史版本）。
- [ ] 发布资格通道（qualification）设计实现，普通任务页不混入。

### P3 核心修订（真实修改能力）

- [ ] `recall.py`：事实画像（含资格排除独立配置）、规则→子节映射、分页目标盘点、联合修订单元。
- [ ] 文案组装：固定新文取自指引 + 槽位按实际类别实例化；语义生成附来源与事实并代码核验。
- [ ] 原件重放：validate_edit_plan + generate_artifacts（每轮从原件重建）。
- [ ] 阶段出口：至少 1 份真实合同（含应改目标）真实模型 → 实际 final/redline 文件 + 技术校验通过。

### P4 审计修复与查漏

- [ ] 实际产物独立审计（读 final.docx，不只读计划）+ 自动修复（≤3 轮业务修复）+ 仲裁。
- [ ] 最终分块全文轻量查漏（首轮不看目标清单，之后对账；非映射区域参与）。
- [ ] 故障与预算断点：paused + blocked_reason，保留待办/epoch/轮次/账本。

### P5 主链路集成与前端

- [ ] `jobs.py` 分派 recall_first；`api.py` 新契约（提交/进度/结果/详情/下载/指引配置）。
- [ ] 前端：登录/任务列表/提交/进度（真实阶段+暂停恢复）/结果/详情/指引配置/管理员，全部接真实 API。
- [ ] 发布前 qualification 浏览器验证真实修改 → 发布 → 普通入口正式复验。

### P6 真实评测与优化（20—30 份）

- [ ] 选 28 份（20 开发 + 8 留出），manifest + 独立标签先冻结（评分口径/阈值/预算见 §5）。
- [ ] 真实修改 + 实际文件评分（召回、正确完成、整合同完成、误改/漏改、耗时费用）。
- [ ] 按缺陷原因优化 → 局部复测 → 全开发回归 → 冻结 → 留出验收。
- [ ] 结果落 `docs/REAL_REVISION_EVALUATION_RESULTS.md` + `var/recall-first-evaluation/<run-id>/`。

### P7 云端交付

- [ ] 安全读取 FUNDLEX_SSH_*（只检查存在性），只读核实 OS/资源/服务/端口。
- [ ] 独立目录 `/opt/fundlex-recall-first` + 数据目录；专用运行用户；MySQL8 utf8mb4；systemd + 反代。
- [ ] 云端浏览器端到端（登录→提交→真实模型→下载 final/redline/报告→hash 核对）、重启续跑、隔离。
- [ ] 交付访问地址、启停/备份恢复说明、部署版本。

### P8 清理与收尾

- [ ] 清理被替代的旧运行链路（保留历史只读）；更新 README/部署/用户指南。
- [ ] 按功能提交（不含原件/样本/密钥）；不 push（未经要求）。

## 4. 指引业务组（本轮人工通读结论，供解析器设计）

来源：`references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx`，107 段。段落号为提取器 0 起序号。

| 组 | 段 | 业务域 | 操作 | 条件/要点 |
| --- | --- | --- | --- | --- |
| G1 | 0—8 | 释义-份额类别定义 | 追加新文 | 类别槽位分组替换（A类组/C类组）；实际类别以产品为准 |
| G2 | 10—16 | 基本情况-份额类别设置 | 追加新文 | 同 G1（不同位置） |
| G3 | 17—22 | 基本情况-类别调整句 | 条件替换+删除 | 有销售服务费类别→“调低赎回费率”改“调低销售服务费率”，否则删“、调低赎回费率”；删除“并报中国证监会备案” |
| G4 | 23—25 | 基本情况-类别转换 | 删除 | 删除“不同基金份额类别之间不得互相转换”句 |
| G5 | 26—34 | 申购份额计算 | 条件替换 | 单类别/多类别分支不同新文；类别槽位 |
| G6 | 35—40 | 赎回金额计算 | 条件替换 | 单类别不调整；多类别“扣除相应的费用”→“扣除或加上相应的费用”+“对应份额类别”→“该类基金份额” |
| G7 | 41—48 | 申购费用承担 | 条件替换 | 单类别替换；多类别条款1/条款2变体→固定新文；类别槽位 |
| G8 | 49—53 | 赎回费用归属 | 替换 | 描述1/描述2 → “赎回费用全额计入基金财产。” |
| G9 | 54—56 | 7日赎回费句 | 删除 | 删除“持续持有期少于7日……全额计入基金财产”句 |
| G10 | 57—66 | 促销费率调整句 | 条件替换 | 三种旧表述任一；单类别→“调低基金申购费率。”，多类别→“调低基金申购费率和销售服务费率。” |
| G11 | 67—84 | 费用与税收-销售服务费 | 删除+追加 | 有销售服务费类别；删除支付句；追加“销售服务费每日计提”+直销返还+其他销售机构支付/超一年返还 |
| G12 | 85—89 | 销售服务费用途条款 | 删除 | 两段用途/使用范围句 |
| G13 | 90—92 | 收益与分配 | 替换 | “A类…不收取销售服务费，而C类…收取销售服务费”→“…费用收取不同”；类别槽位 |
| G14 | 93—100 | 清算分配（浮动管理费） | 条件替换 | 浮动管理费产品；描述1/描述2 → 单类别/多类别两版新文（多类别含销售服务费） |
| G15 | 101—106 | 清算分配（非浮动） | 条件替换 | 非浮动；单类别不替换；有销售服务费（多类别）→ 追加“并加上返还基金份额持有人的销售服务费（如有）”版新文 |

注：G15 段 104/105 的“单类别不替换 / 如有销售服务费则替换”存在表述顺序歧义，登记 FL-D038，由独立核验与真实合同证据裁决，不自行杜撰。

## 5. 预算与账本（预登记）

- 价格（2026-10-14 核对）：input $0.15/M，output $0.60/M（OpenCodeGo deepseek-v4.1-flash）。账本费率环境变量按实际设置，不用默认 $1/$5 虚高费率。
- 共享账本：`%LOCALAPPDATA%\FundLex\runtime\model_budget.sqlite` 累计不清零；评测/开发运行使用独立账本文件并登记到 run_context；所有 agent 共享同一本轮 cap。
- 本轮预登记上限（在 §7 变更记录更新实际值）：
  - P2 指引解析与核验：≤300 次调用 / ≤$3。
  - P3—P5 引擎开发与集成（含真实小批）：≤1500 次调用 / ≤$8。
  - P6 评测：20 开发 ×（基线+优化≤3轮+修复）≈ 最坏 2500 次 / ≤$12；8 留出 ≤800 次 / ≤$4。
  - P7 云端端到端：≤500 次 / ≤$3。
  - 项目合计 cap：≤6000 次 / ≤$30（未使用部分不视为授权外扩；触发即暂停并报告）。
- 不重置账本、不无限重跑；每次真实批量运行前写 protocol.json（样本/版本/预算/最坏调用上限）。

## 6. 验证矩阵与验收（对齐整合文档 §12/§13）

- 功能：跨段/同段多项/重复引文/陌生类别/币种/已满足变体/正文摘要缺项/联合规则重叠/表格与不可编辑部件/编号书签。
- 可靠性：超时/限流/截断/JSON不合格/鉴权余额停止/预算停止/修复上限/断点复用/重复提交/租约过期/过期响应/指引切换竞态/双用户隔离/MySQL 迁移与重启续跑。
- 端到端：7 个脚本用例（默认内置指引、长合同、已满足或排除、不完整/故障、配置页切换、双身份与下载、服务重启）。
- 评测口径：见 EVALUATION_AND_OPTIMIZATION_PLAN.md §4 与 §7；主指标目标正确完成率与整合同完成率；错误完整声明零容忍。

## 7. 变更记录

- 2026-10-14：建立本计划；完成 P0 起点核对与代码基线调查；登记新问题 FL-D032—FL-D038；确认引擎/模块/预算基线。
- 2026-10-15：内置指引解析并冻结（FL-D039/FL-D040）；引擎核心/编排/持久化/API/前端完成（526 测试通过）；云端部署完成（/opt/fundlex-recall-first，MySQL 迁移、systemd、nginx、备份）；真实合同 7 次云端真实运行，产物与缺陷闭环见 FL-D041—FL-D046；发现本机 402（FL-D041）与公网阻断（FL-D044）。
- 2026-10-15（第 4 轮）：实现确定性覆盖补扫与跨段操作（FL-D047）：`survey_targets`/`find_old_text_all`/`_lead_nearby`/`satisfied_by_new_text`/`plan_composite_target`/`_run_survey`/`_absorb_sweep_findings` 重绑定；prompt 版本升到 `recall_inventory_v2`/`recall_sweep_v2`；修复“条件不适用被判未解决”和“账本/并发停止被吞成部分失败”（FL-D048）；测试 531 passed / 6 skipped；本机真实合同运行 `var/recall-runs/qr-local-01|11|12`。▸ **开发主副本迁移到云服务器 `/home/opencode/fundlex`**（含 .git 与全部未提交改动；排除 var/funds/funds_word/references/.venv/缓存），本机转只读备份；后续修复与验证在服务器工作区进行，发布走 `tools/deploy/publish_workspace.sh`。下一步：服务器基线测试 → 修 G15 未解析/composite 重绑定与 G05 p760 切片偏移 → 发布后云端 quality-return-10 复验 → P6 评测与浏览器端到端。
