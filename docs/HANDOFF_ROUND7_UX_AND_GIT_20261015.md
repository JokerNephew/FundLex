# 第 7 轮交接：用户 8 项 UX/修改问题 + P6 第 1 轮评分 + Git 版本管理（2026-10-15）

> 本文件是**第 7 轮**（用户 8 项反馈）的独立交接，供上下文压缩后接续。
> 与 `docs/ACTIVE_HANDOFF.md` 的「第 8 轮」并行存在（另一 agent 在跑 P6 优化，见下）。
> 编号以 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 的 FL-D077 更正块为准。

## 1. 用户需求（第 7 轮，8 项）

| # | 需求 | 归属 | 结果 |
| --- | --- | --- | --- |
| 1 | 有任务在跑时也要能新建任务、多任务并行 | 前端（后端本已支持） | 已实施 FL-D069 |
| 2 | 证据侧栏去掉「证据位置/技术追溯」，改为章节 + 改前/改后 | 前端 | 已实施 FL-D071 |
| 3 | 精简页面啰嗦小字 | 前端 | 已实施 FL-D071 |
| 4 | 结果页加「下载全部结果 ZIP」按钮 | 前端 | 已实施 FL-D071 |
| 5 | 段落结尾无标点时，追加文案与原文粘连 | 引擎 | 已修复 FL-D068 |
| 6 | 去掉顶部横幅；右上角铃铛只提醒重要消息 | 前端 | 已实施 FL-D071 |
| 7 | 任务总进度指标改成一行 | 前端 | 已实施 FL-D071 |
| 8 | 批量导入页 KPIs 移到复选框/筛选栏右侧 | 前端 | 已实施 FL-D071 |

另：用户后追加要求「git 的事情可自主判断，做好版本管理」→ 已完成本地提交并 push（FL-D078）。

## 2. 已完成与验证

### 2.1 引擎（问题 5）→ FL-D068
- 根因：`_splice_fragment`（`fundlex/recall.py`，`fragment_replace` 路径）把授权文案直接拼到未以标点结尾的前导文字上，产生 `…份额的通过直销机构…`。
- 修复：`_splice_fragment` 拼接 `new_text` 前后各调 `append_separator`；删除（`new_text` 为空）保持逐字拼接。`plan_composite_target` 同步加同样保护（防御性）。
- 回归测试：`test_fragment_replace_separates_authorized_text_from_unterminated_lead`、`test_composite_replace_separates_unpunctuated_clause`。
- 注意：append 分支（`plan_target`）与 composite 在更早已修复；`quality-return-12` 老报告缺标点是旧版本产物。

### 2.2 前端 8 项（问题 1、2、3、4、6、7、8）→ FL-D071
- 文件：`frontend/index.html`、`frontend/app.js`、`frontend/app.css`。
- 验证方式（**已做**）：
  - `node --check frontend/app.js` 通过（本机原无 node，下载便携版 v20.18.0 到 `/tmp/opencode/node-v20.18.0-linux-x64/`）。
  - 120 个 `$('id')` 引用在 HTML 中全部存在；CSS 花括号平衡（377/377）。
  - 问题 2 用真实 `var/cloud-runs/quality-return-12/report.json` 走 `changedClauses`/`clauseRow` 渲染：**22 行可读输出，无 `p142`/偏移/哈希/`content_source`/`mapping_safe`/`segment_ok`**。
- **未做**：浏览器端真实点击验收（本机无浏览器）。

### 2.3 P6 第 1 轮评分 → FL-D070
- 批次 `p6-dev-round1-01`（我这次跑的）：20/20 完成，677 调用，$0.5738。
- 开发集 236 目标：基线 178（0.7542，`/tmp/opencode/p6-baseline-full2.json`）→ **187（0.7924，+9/+3.8pt）**。
- 规则层：G15 +9、G05 +2、G17 −2；`applicability_conflicts` 29→13；假完成 13→12。
- 评分产物：`/tmp/opencode/p6-round1-score.json`（sha256 `07fb0112…`）。
- **未达阈值**（目标 0.95 / 整合 0.9）。
- ⚠️ 注意：**另有 agent（第 8 轮）在同一批次目录上跑了「第 3 次重跑」**（构建 `07b39288…`，见 `ACTIVE_HANDOFF.md` 第 8 轮）。以最新一次产物为准，必要时空批次目录重跑。

### 2.4 Git 版本管理 → FL-D078
- 本地 11 个逻辑提交（`cc558ab..05fc90f`），工作树干净，全量测试 **562 passed / 1 expected（references/ 未迁移）/ 6 skipped**。
- **已推送到远端**：`origin = https://github.com/JokerNephew/FundLex.git`（私有），分支 `codex/fundlex-recall-first`（新建并设 upstream）。
- 凭据（**已按用户要求持久保存，2026-10-15 晚**）：token 存于仓库外 `/home/opencode/.github_token`（权限 `600`）；推送用 `bash tools/deploy/push_with_token.sh`（默认读该文件，token 不打印、不入命令行/仓库/日志）。**文件中不含明文到其他任何位置**；如需撤销请删除该文件并轮换 GitHub token。
  - 早期一次用的是对话中出现的 OAuth token（`gho_…`，视为已暴露）——用户如已轮换，请把新 token 写入 `/home/opencode/.github_token` 即可，其余流程不变。
- 仓库级代理已配置：`http.proxy=http://127.0.0.1:9981`（mihomo）。
- **push 操作约定**：以后增量提交后直接 `bash tools/deploy/push_with_token.sh`（默认 `origin` / 当前分支）；并行 agent 有提交时先 `git pull --rebase`。
- 提交前安全扫描：无口令/密钥/私钥；样本与原件目录由 `.gitignore` 覆盖；3 个无引用散图（`frontend/assets/{640.png,t0183cba9196d3d9cc9.jpg,去白底 .png}`）已加入 `.gitignore` 不入库。

## 3. 未完成 / 待办（按优先级）

1. **前端浏览器端验收**（问题 1/2/4/6/7/8）：临时预览服务仍在后台跑：
   `FUNDLEX_DATA_DIR=/tmp/opencode/fundlex-preview FUNDLEX_AUTH_MODE=dev .venv/bin/uvicorn fundlex.api:app --host 127.0.0.1 --port 8020`
   经 `ssh -L 8020:127.0.0.1:8020 opencode@8.155.130.168` 后浏览器访问 `http://127.0.0.1:8020/`。**验收完应停掉该进程**。
2. **发布到生产**：`bash tools/deploy/publish_workspace.sh`（同步到 `/opt/fundlex-recall-first` 并重启 `fundlex-recall-api`/`fundlex-recall-worker`）。需用户确认。
3. **P6 继续优化**：开发集残留 `not_executed`（append 文案缺失，G01/G03/G16）与 `kept`（G17/G15/G14/G11/G08/G18）。
4. **安全**：提醒用户撤销对话中出现的 `gho_` token。

## 4. 硬约束与陷阱

- **机器身份**：当前工作机 = 云服务器（`/home/opencode/fundlex`），不是 Windows 开发机。开工先 `hostname`/`ip -4 addr`/`curl ifconfig.me` 确认。
- **多 agent 并行**：仓库内有另一 agent 在跑 P6（第 8 轮）。改 `docs/ACTIVE_HANDOFF.md`、`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 前先看 mtime，尽量小改、追加，避免冲突。
- **FL-D066**：不要 kill 在途 P6 批次；中止后残留模型账本 `reserved` 会阻塞后续（`MODEL_CONCURRENCY_LIMIT`），需重启 worker。
- **凭据**：只在内存/临时文件用，不写入仓库/文档/prompt/日志。
- **样本/原件**：`funds_word/`、`references/`、`var/` 因体积大仍由 `.gitignore` 覆盖（**非**安全要求）。**政策已更新（用户 2026-10-15）**：合同为公开资料，**可入库、可出服务器**（含 Langfuse Cloud）；只有**密钥/凭据**仍严禁入库、严禁写入文档/prompt/日志/第三方服务。

## 5. 关键文件

- 引擎：`fundlex/recall.py`（`_splice_fragment` ~1694、`append_separator` ~1759、`plan_target` ~1773、`plan_composite_target` ~1712）。
- 前端：`frontend/{index.html,app.js,app.css}`（`changedClauses`/`clauseRow` ~161/173、`notice`/`toast`/`flash` ~31/34/35）。
- 评测：`tools/evaluation/p6_{run,score,label,select}.py`。
- 记录：`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`（FL-D068/069/070/071/078 为本轮）、`docs/TASK_PLAN_UX_AND_APPEND_20261015.md`。
