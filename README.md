# FundLex

FundLex 是 DOCX 基金合同处理的本地开发应用，包含 Fluent Office 工作台、持久批次队列、证据画像、通用规则、固定模板编辑器及报告交付。

**v2 已实现并完成受控真实修改评测（尚未发布）：** 用户允许 AI 生成局部合同条款，不再要求生成文字逐字等于固定模板。v2 按规则语义契约、当前合同证据、精确范围和内容验证执行，支持 6 个重点 action（R03-A3/R04-A1/R11-A1 精确删除、R10-A1 模型定位+生成+独立验证、R01-A1/R02-A1 按当前实际类别生成直销条款，移除旧 A/C 槽位限制）。固定字串约束与 22 个 action 自动写入关闭仍描述 v1 实现；v2 只在 `execution_mode=evaluation` 下运行，目录/正文/摘要保护、失败关闭、同计划双产物、预算限制继续适用。16 份开发回归集 16/16 应改目标正确、编辑精度 1.0，夹具 5/5，未见集注册运行 4/6 后修复并诊断 6/6；详见 [v2 实际修改与评测结果](docs/AI_EDITING_V2_RESULTS.md)。没有开启正式自动写入，也未取得发布批准。

**当前 v1 的 22 个业务 action 均未发布，自动写入关闭。** 当前应用可进行真实模型只读评测，展示资格、候选、失败原因和报告；诊断 DOCX 不会作为最终合同开放下载。固定模板修订与最终版生成已用独立 DOCX 夹具验证，包括 Microsoft Word 接受修订。缺少独立标注指标或离线发布批准的 action 不会因代码测试通过而开启。

## 本地启动

当前环境已有 `.venv`，Python 3.12；系统 `python`/`py` 启动器不可用时直接使用该虚拟环境。新环境使用 Python 3.11+ 和 uv，依赖由 `uv.lock` 锁定：

```powershell
uv sync --extra test
pwsh -NoProfile -File .\tools\local.ps1 -Mode api
```

在另一个终端启动 worker：

```powershell
pwsh -NoProfile -File .\tools\local.ps1 -Mode worker -Model deepseek-flash -RequestOptionsJson '{"thinking":{"type":"disabled"}}'
```

打开 [本地工作台](http://127.0.0.1:8000)。开发身份默认 `local-user`，所有 API 请求使用 `X-FundLex-User`；不同身份的批次/下载隔离。该身份适配只用于本地开发，不能作为生产认证。`FUNDLEX_AUTH_MODE` 设为非 dev 时，在生产身份提供方接入前返回 503。

默认状态/文件目录为规范用户目录 `~/AppData/Local/FundLex/runtime`（Windows），可用 `FUNDLEX_DATA_DIR` 配置。活动 SQLite、预算账本、worker 锁和产物应放在非同步的短路径。此次重现外部文件句柄拒绝写共享可引发 SQLite 只读错误；同步程序归因尚未直接证实；MSIX 的 `LOCALAPPDATA` 重定向长路径还会触发 Windows 路径长度错误。默认位置已避开这些运行问题。原有样本保持不动。

## 工作台的两种处理模式（2026-10-13）

任务工作台支持两种模式，导入页可选择：

- **只读诊断**（v1）：资格、候选与失败原因评估，不修改合同。
- **合同修订（评测）**（v2）：按 6 个已实现语义契约的动作自动定位、局部修改并独立验证，产出 `evaluation_final`（接受修订后）与 `evaluation_redline`（修订痕迹）评测文件；任务、结果与报告显示"已修改（评测）/无需修改（评测）/部分未修改"等状态。**评测产物不能作为正式合同**，正式 `final/redline` 不生成、前端不提供正式合同下载。

正式写入由规则包发布状态决定：未发布包一律评测模式；已发布包必须逐 action 携带评估报告、批准记录、预注册阈值与达标指标（代码强制校验，不能手改开关），此时 worker 自动进入正式交付模式并发布 `final/redline`。当前 v2 包为未发布状态。

真实任务链路复验入口：`tools/evaluation/task_revision_run.py`（任务 API→上传→默认 worker→评测修订→授权下载并核对 SHA）。前端改动检查：`node --check frontend/app.js`。

## 模型配置与预算

ModelGateway 读取通用变量 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`。`tools/local.ps1` 在 worker 进程缺变量时安全继承 Windows 用户级配置，仅检查存在性，不输出值或密钥。密钥不从仓库文件加载，不进入规则、日志或报告。

当前联调模型版本显示名是 DeepSeek-V4.1-Flash，官方 API 请求名称是 `deepseek-flash`，base URL `https://api.deepseek.com`。初始模型配置请求曾返回 HTTP 400；测试进程改用官方 API 名称后成功。上面的 `-Model` 只改变该 worker 子进程，未修改 Windows 用户级变量。[官方模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)。供应商/模型可替换，模块和业务规则不含供应商分支。

默认全局预算账本累计最多 16 次 HTTP 请求、USD 1 的配置价格估计、并发 1。`FUNDLEX_MODEL_MAX_REQUESTS`、`FUNDLEX_MODEL_MAX_COST_USD`、输入/输出单价、上下文和输出上限可配置；每次重试也预留预算，未知 token 用量保留保守预留值，账本不随重启清零。修改模型、价格或预算前应重新登记和验证。估计费用不是供应商账单。当前联调的低延迟请求选项通过 `FUNDLEX_MODEL_REQUEST_OPTIONS_JSON` 注入；不能覆盖输入、模型、输出长度或 schema 校验。

详见 [评测协议](docs/EVALUATION_PROTOCOL.md)、[部署参数](docs/DEPLOYMENT_PARAMETERS.md) 和 [实施计划](IMPLEMENTATION_PLAN.md)。不同合同全文不会拼成一次请求，模型不生成写入文字或 OOXML。

## 流程和支持边界

上传可编辑 DOCX → 最小资格证据 → 通用分类排除/失败关闭 → 完整结构预检 → 独立模型画像及代码核验 → 有范围的 action 候选 → 固定模板计划 → 修订版/最终版验证 → JSON/Markdown 报告。

- 只支持经验证的 Transitional DOCX 子集，普通正文/摘要和普通非合并表格；PDF、DOC、OCR 和历史转换不进入应用。
- 目录、域、超链接、内容控件、文本框、附录及其他部件不可编辑；嵌套/合并表格目标失败关闭。既有修订、保护、签名、损坏/异常包等按明确错误码拒绝。
- 名称、文件名、样本编号不决定资格。ETF、同业存单、货币及明确的其他排除类型都需要当前合同证据；不明确类别保留原文并失败。
- 所有新增文字引用规则包固定字串。类别槽位没有审定的具体模板变体时保持关闭，不用模型或程序拼合同文字。
- `complete/incomplete/not_generated` 与资格/action/candidate 分开记录；不完整或诊断文件不能作为最终合同。目录不自动刷新。
- 没有人工复核、审批或待办队列。离线规则发布批准属于规则包发布策略。

本地运行支持事务任务表、单 worker OS 锁、租约心跳/fencing、有界故障退避、暂停/恢复、输入/规则/引擎/schema 哈希核验及显式提交幂等。只读评测的同一任务支持模型阶段检查点：按源文件、规则、引擎/schema、提示和模型传输配置绑定，复用时重新校验 JSON 和原文引述；费用不重复计入本次尝试。结构、证据位置、编辑计划及产物均重新计算，损坏检查点重新调用模型。已发布自动写入链路禁用该缓存，仍完整执行；尚未完成生产多 worker 验收。

## 测试与资料

```powershell
pwsh -NoProfile -File .\tools\local.ps1 -Mode test
node --check .\frontend\app.js
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/corpus_audit.py
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/word_fixture.py
pwsh -NoProfile -File tools/evaluation/word_acceptance.ps1
```

真实模型场景、小批和受控批次的入口是 `tools/evaluation/real_scenarios.py`、`tools/evaluation/controlled_regression.py`；v2 定位/生成/验证评测入口是 `tools/evaluation/v2_fixtures.py`、`tools/evaluation/v2_pilot.py` 与 `tools/evaluation/v2_compare.py`（评分器读取实际修改的 DOCX）。先按协议设置全局账本、调用/费用上限再运行。用户已将本轮模型回归范围调整为230份，剩余284份取消；514份结构审计仍是独立验证。报告记录实际结果，不把替身测试或缺少真值的覆盖统计表述为准确率。

- [PRD v4.1](FundLex_PRD_v4.md)、[Agent 设计 v4.1](FundLex_Agent_设计方案_v4.md)、[技术详细设计 v1.1](FundLex_技术方案_详细设计_v1.md) 保留为原始产品/技术资料。
- `references/source/`、`references/evidence/` 是依据与离线评测材料；`funds_word/` 的 514 DOCX 是样本，不是运行时白名单。
- `funds/`、`archive/`、`tools/research/` 保留历史资料；未运行历史 PDF 转换。
- `frontend/` 是实际应用；`workbench/` 的 HTML 是标明虚构数据的历史视觉参考。
- [Word 与结构验收](docs/WORD_AND_STRUCTURE_VALIDATION.md)、[完整验证报告](docs/VALIDATION_REPORT.md) 和实施计划记录实际测试、提交及剩余发布条件。

生产 OIDC/身份网关、数据库与对象存储、服务器容量、模型固定版本、数据保留/地域和预算等上线参数仍待确定。当前本地配置不能视为生产验收。

## 本轮验收状态

完整测试135项通过；真实模型正常/既有修订失败/实际输出截断/检查点续跑及浏览器上传到报告下载通过。230份模型回归有149份资格符合、77份类型排除、4份资格证据失败关闭；不表示合同已修改或规则准确率达标。22个action仍自动写入关闭。规则编号冲突及语义对应详见[映射表](docs/RULE_ID_MAP.md)。

## 后续16份规则质量小批

独立AI盲核+真实模型小批发现业务定位缺口：R03/R04/R11的12处可编辑目标未定位，另有一处跨段目标不可写；费用明确字段41/68回答一致、27项未确认。最新完整测试137项通过属于代码验证，不能掩盖上述业务漏识别。详见[16份小批结果](docs/ACTION_PILOT_16_RESULTS.md)，规则自动写入继续关闭，缺口修复/复评尚待执行。

### 上述小批缺口的修复结果

资格字段/纯章节、子节别名、七日句宿主、类别费用归属已修复；16份缺陷回归的13份普通基金份额完全匹配、68项明确费用均核验、三重点动作12处可编辑目标精确定位。另1处跨段拒绝；并行源码变动导致1份版本保护失败，隔离实际补验正确排除，原记录保留。代码和冻结基线集成277测试通过。数量、外部批准、其他动作及R10精确边界仍未满足，所有自动写入关闭；见[修复复验报告](docs/ACTION_PILOT_FIX_RESULTS.md)。

## v2 实际修改评测状态（2026-10-13）

当前完整测试312项通过。v2 在隔离评测模式下完成真实模型定位/生成/独立验证与实际 DOCX 修改：16 份开发回归集 16/16 应改目标正确（R03-A3 5/5、R04-A1 4/4、R11-A1 3/3、R10-A1 4/4，含 P08 精确中段范围与已符合不改），编辑精度 1.0、误改 0、负例违规 0；独立构造夹具 5/5（含 H/J/K 实际类别、同组费率差异、证据不足与混合收费拒绝、正文摘要一致）；未见 8 份注册运行 4/6 后定位/识别缺口修复，修复后诊断 6/6 且资格 8/8。全部运行保留原始引擎与账本，共享账本 611/680 次、估计 USD 0.396947。22 个 action 正式写入仍全部关闭，6 个 v2 action 未取得发布批准；其余 16 个 action 不在 v2 支持范围。详见[v2 实际修改与评测结果](docs/AI_EDITING_V2_RESULTS.md)。
