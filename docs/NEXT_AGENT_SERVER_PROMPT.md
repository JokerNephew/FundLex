# FundLex 服务器接续开发 Prompt（2026-10-15 迁移后）

> 用法：把本文从“## 你是”以下整段粘贴给服务器工作区的 agent（或让它读本文件）。

## 你是

FundLex 项目在云服务器上的接续开发 agent。自 2026-10-15 起，**`/home/opencode/fundlex` 是开发主副本**（笔记本副本已转为只读备份），你在这里继续完成整个项目：前端、后端、召回优先修订引擎、指引配置、账号、持久任务、MySQL、云部署、真实用户端到端验收，以及 20—30 份真实合同评测与优化闭环。

本 prompt 里的“已核实”事实不需要你重新发现；先读文档、再按顺序执行。

## 第一步：先读这些（按顺序，不要跳）

1. `AGENTS.md` —— 项目级规定（集中登记细节问题、最终真实验收、上下文控制、预算与账本、凭据纪律）。注意：文件里的“Windows/PowerShell”约束适用于笔记本，服务器是 Linux/bash。
2. `docs/ACTIVE_HANDOFF.md` —— 断点：目标、已完成（有证据）、阻塞、预算、下一步（**必读**，含本轮全部细节）。
3. `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` —— FL-D001—FL-D050 集中问题记录；重点看 FL-D046/047/048/049/050。
4. `docs/FULL_PROJECT_IMPLEMENTATION_PLAN.md` —— 阶段计划（P0—P8）与预登记预算。
5. `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` —— 28 份评测的执行规格（P6 要用）。

## 当前基线（已核实，2026-10-15）

- 仓库：分支 `codex/fundlex-recall-first`，HEAD `3ed4e96`，**55 项未提交**（11 个已跟踪修改 + 44 个未跟踪新增，清单见 `git status`）。**不要 commit、不要 push**（未获用户要求）。
- 环境：工作区自带 `.venv`（Python 3.11.13 / pytest 9.1.1，已 `pip install -e '.[test]'`）。
- 测试基线：`.venv/bin/python -m pytest tests -q` → **530 passed / 1 failed / 6 skipped**。
  - 唯一失败 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation` 需要 `references/source/…指引_文案勘误版.docx`：该文件按约定放在 `/home/opencode/data/references/`（**不在工作区**）。这是预期差异，不是代码回归；**不要**把 references 复制进工作区，也不要改测试或仓库来“修”它。
- 资料（与工作区分离，不进 git）：`/home/opencode/data/funds_word/`（514 份合同）、`/home/opencode/data/references/`（24 份原件）、`/home/opencode/data/MANIFEST.sha256`（538 行：`sha256  相对路径  字节数` + 注释行记录总数/总字节/生成时间/主机）。
  - 核对：`cd /home/opencode/data && awk '!/^###/ {print $1"  "$2}' MANIFEST.sha256 | sha256sum -c -`
  - **本轮运行证据**（笔记本上运行、已复制到服务器）：`/home/opencode/data/evidence/qr-local-12/`——`report.json`（含 12 项未解决明细）、`report.md`、`working_final.docx`、`working_redline.docx`。
- 应用：`/opt/fundlex-recall-first`；systemd `fundlex-recall-api` / `fundlex-recall-worker`；nginx 80 → 127.0.0.1:8010；MySQL `127.0.0.1:3307/fundlex`；数据目录 `/var/lib/fundlex`；**应用账本** `/var/lib/fundlex/model_budget.sqlite`。
- 发布：**只允许** `tools/deploy/publish_workspace.sh`（内部 `sudo /usr/local/sbin/fundlex-publish`，把工作区发布到 `/opt/fundlex-recall-first` 并重启服务）。不要手改 `/etc/fundlex-recall.env`、systemd 单元或 nginx。
- 约束：不改应用部署配置；不在仓库放密钥/原件/样本；不打印密钥；你自己的模型调用不记入应用账本，**单列跟踪**（在断点文档记录用量）。

## 真实模型调用的两条合法路径

1. **应用链路（推荐，也符合“真实用户端到端”要求）**：发布后，用 `POST http://127.0.0.1:8010/api/auth/register` 注册一个测试账号 → 登录拿 token → `POST /api/tasks`（`engine_id: "recall_first"`）→ 上传合同 → `seal` → 轮询任务状态 → 下载 `working_final/working_redline` 与报告。worker（fundlex 用户，env 由 systemd 以 root 注入 `/etc/fundlex-recall.env`）会做真实模型调用并记入应用账本。示例可参考 `tools/deploy/cloud_task_run.py` 里的 `SERVER_RUNNER` 脚本（它在服务器上跑、临时账号自建自删）。
2. **直接跑引擎（开发调试）**：`tools/evaluation/recall_run.py`。需要 `LLM_PROVIDER/LLM_BASE_URL/LLM_MODEL/LLM_API_KEY` 环境变量。
   - 应用 env 文件是 root-only，你读不到；如需直接跑，用你自己的 provider 凭据（来自你的 OpenCode 配置，同端点 deekseek-v4.1-flash），**只经环境变量传入、不打印、不落盘**。
   - 账本必须放仓库之外（如 `/var/tmp/ledger-<run>.sqlite` 或 `~/runtime/`），不要放 `var/`（原因见 FL-D048）。
   - 若两条路径都不可用，把阻塞登记到集中问题记录并请用户提供，不要伪造运行。

## 立即要做的（按顺序，每步完成后更新断点文档）

### 1. 修两个真实缺陷（证据在 `data/evidence/qr-local-12/report.json`）

**(a) G15 跨段目标未解析（`RECALL_TARGET_UNRESOLVED`，p806）**
- 现状：盘点给出的 needs_edit 目标引文为合同真实文本“C 类基金份额的基金销售服务费每日计算，逐日累计至每月月末，按月支付，…”（跨段到 p807），但规划无法解析成可执行编辑。
- 相关代码：`fundlex/recall_pipeline.py` 的 `_absorb_sweep_findings`（其内部 `rebind()` 已能按 `_operation_fingerprints` 逐级降级匹配参考旧文并生成 composite 目标）——但该重绑定**只处理 sweep findings**，不处理“盘点/审计自己给出的未解析目标”。
- 任务：在盘点后（或规划前）对所有 `resolution != "resolved"` 的 needs_edit 目标，按规则参考旧文（含 `old_text_variants`）用 `_operation_fingerprints` + `recall.find_old_text_all`（支持“本段结尾 + 下段开头”拼接）做一次确定性 re-bind：命中则更新 target 的 `quote/start/end/composite/resolution` 并记 ledger（origin）；找不到则保留 unresolved 并登记原因。
- 期望：G15 在 p806+p807 与摘要 p1262+p1263 两处跨段删除按 `recall.plan_composite_target` 逐段精确执行（保留各段余文），content_check 通过。

**(b) G05 p760 假阳性 + survey 引文切片疑似偏移**
- 现状：survey 产出 `{"rule_id":"G05","operation":"survey","locations":["p760"],"quote":"人并报中国证监会备"}`——引文比真实文本“并报中国证监会备案”**偏移一位**；随后规划 `_splice_fragment` 失配 → 落 compose → `RECALL_COMPOSE_FIXED_TEXT_MISSING`；审计判 wrong，交付停在 incomplete。
- 相关代码：`fundlex/recall.py` 的 `survey_targets`（raw 切片 `index_map[first[1]]` / `index_map[first[2]-1]+1`）与 `find_old_text_all`（compact 偏移）之间的换算；`fundlex/recall_pipeline.py` 的 `_survey_targets_from_hits`。
- 任务：
  1. 复现并修切片换算（用 `display_text` 的 index_map 正确映射；补单测覆盖段首/段中/含全角空格/跨段四种命中）；
  2. p760 是“基金资产估值差错更正”条款，与费用类别调整语义无关：给出你的处理取舍（例如要求片段与规则语义相关后再建目标，或在交付裁决中把“审计否决的 survey 目标”记为已核验不适用而非未解决），补证据与单测。
- 同样检查：G22 p142（审计/查漏都曾指向“类别调整句”而非真实清算条款 p978/p1357）、G16 p227（摘要对应位置追加缺失）——这两条在 qr-local-12 的 findings 里。

### 2. 逐条核对 qr-local-12 的 12 项未解决（`report.json` 的 `unresolved`）

- target：G15 p806（上条 a）、G05 p760（上条 b）；
- audit：G03 p141（wrong）、G05 p142（incomplete）、G15 p806（incomplete）、G16 p809（wrong）、G05 p760（wrong）；
- sweep：G16 p227、G18 p139/p829/p1217、G22 p142。
- 规则：属模型误判 → 用产物原文回驳并加代码过滤；属真实缺陷 → 修；每条在集中问题记录里给出结论与证据。**不要**为了通过而放宽 fail-closed 门禁。

### 3. 修完后回归

- 补单测（`tests/test_recall_core.py`、`tests/test_recall_pipeline.py` 风格），跑全量 `.venv/bin/python -m pytest tests -q`（目标：除 `test_rules_catalogue` 外全绿）。
- 用 `tools/evaluation/recall_run.py` 重跑同一合同（广发品质回报 `_20230708.docx`）对比 12 项未解决是否收敛；账本放仓库外。

### 4. 发布 + 真实云端 quality-return-10（真实交付路径）

- `tools/deploy/publish_workspace.sh`；
- 走应用链路（见上“应用链路”）：注册测试账号 → 提交 广发品质回报 合同 → worker 真实模型 → 下载产物与报告；
- 核对：findings 数（期望 ≤2 且为真实线索）、摘要第二处是否修改（G22 p1357、G05 p954/p1332、G15/G16 摘要）、跨段删除一致性（p806+p807、p1262+p1263）、`not_applicable` 不计未解决、`delivery_status`（正常合同应能 `complete`）；
- 记录：应用账本调用数/费用（读 `/var/lib/fundlex/model_budget.sqlite` 的统计或报告 `model` 段）。

### 5. P6 评测（28 份：20 开发 + 8 留出）

- 从 `/home/opencode/data/funds_word/` 抽样，**引用 `MANIFEST.sha256` 冻结样本**（写入你的 manifest，记录文件 sha256）；
- 独立标签先冻结、评分读实际 DOCX（口径见 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` §4/§7）；
- 每次批量运行前写 `protocol.json`（样本/版本/预算/最坏调用上限）；
- 开发集基线 → 定位缺陷 → 修复 → 局部复测 → 全开发回归 → 冻结 → 留出验收；
- 结果落 `docs/REAL_REVISION_EVALUATION_RESULTS.md`，原始产物与账本单独归档并登记到 run_context。

### 6. P7 收尾

- 浏览器端到端（公网 `http://8.155.130.168` 已实测 200，也可 SSH 隧道 `ssh -L 8080:127.0.0.1:8010 root@8.155.130.168`）；
- 服务重启续跑、双身份隔离、指引切换（配置页上传/启用/恢复默认）、MySQL 备份恢复演练。

## 硬性规定（AGENTS.md 摘要，必须执行）

1. **细节问题集中登记**：任何发现（设计、实现、测试、评测、部署、用户反馈）都要写入 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`，用稳定编号、含证据、状态区分“建议/已确认/已实施/已验证”，未解决也要记；不能只留在聊天里。
2. **上下文控制**：50% 开始整理、60% 前完成压缩或交接；先保存源码与文档，把进度、断点、下一步写入 `docs/ACTIVE_HANDOFF.md`（含 branch/HEAD/未提交清单、已做/未做、验证证据、阻塞、账本与预算、运行中进程）。
3. **最终验收必须真实端到端**：工作台入口 → 真实合同上传 → 真实模型 → 实际 DOCX 修改 → 产物与修订复核 → 下载核对哈希；不能用评测/替身/脚本替代正式交付。
4. **预算**：真实运行前预登记（样本/版本/预算/最坏调用），账本不清零，触顶暂停并报告；应用账本与你自己的调用分开跟踪。
5. **凭据纪律**：密钥只经环境变量或 600 权限文件使用，不打印、不写入仓库/文档/日志。
6. **文件操作**：不要留下半写入文件；不要两边同时改同一份代码（本工作区是唯一开发主副本）。
7. **不做**：不 push；不手改应用配置；不改评测标签制造通过；不按样本特判。

## 常用命令（服务器）

```bash
cd /home/opencode/fundlex
.venv/bin/python -m pytest tests -q                       # 基线测试
.venv/bin/python -X utf8 -m tools.evaluation.recall_run \
  --input "/home/opencode/data/funds_word/广发品质回报混合型证券投资基金基金合同_20230708.docx" \
  --output var/recall-runs/qr-s12 --ledger /var/tmp/ledger-qr-s12.sqlite \
  --max-calls 200 --max-cost-usd 1.5 --business-rounds 5  # 开发运行（账本在仓库外）
tools/deploy/publish_workspace.sh                         # 发布到应用
systemctl is-active fundlex-recall-api fundlex-recall-worker
journalctl -u fundlex-recall-worker -n 80 --no-pager      # worker 日志
curl -s http://127.0.0.1:8010/api/capabilities            # 应用健康
```

## 交付报告要求

每完成一步，向用户报告：命令与关键输出、产物路径与 sha256、模型调用数与费用（应用账本/自用账本分开）、未解决事项与下一步；同时更新 `docs/ACTIVE_HANDOFF.md` 与集中问题记录。
