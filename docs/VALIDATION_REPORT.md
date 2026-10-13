# FundLex 本地开发与验证最终报告

日期：2026-10-13。工作目录：`D:\Desktop\FundLex`。本报告按用户最新决定以 **230份** 真实模型回归为本轮范围，剩余284份取消；514份结构审计单独报告。没有部署、发布、推送、生产数据修改或PDF转换。

## 结论与边界

本地DOCX上传、持久队列、实际ModelGateway、资格与画像证据、通用action、唯一计划、固定模板编辑器、报告/下载、续跑/幂等及Fluent Office工作台已实现并完成下表验证。

**22个业务action全部未发布，自动写入关闭。** 已完成的真实模型正常场景生成经过校验的空计划和源字节一致的诊断DOCX，API仅开放报告下载；不能称真实业务合同修改已发布或可直接使用。实际非空编辑、修订/最终等价由独立DOCX夹具和Word验收证明。独立业务标注、充分正反例/变体覆盖、具体类别模板变体及离线发布批准仍缺，不能捏造指标或批准。没有产品内人工复核、审批或待办队列。

## 验收矩阵

| 范围 | 实现/证据 | 实际结果与限制 |
| --- | --- | --- |
| 1 审计与追踪 | IMPLEMENTATION_PLAN、忽略规则、样本/环境/Git核对 | 指定资料已阅读；514 PDF/514 DOCX分开；原件保护 |
| 2 批次与状态 | api/store/jobs；事务、租约心跳、fencing、隔离、重试、暂停/恢复 | API/worker集成通过；过期尝试不能发布且worker继续运行；本地单worker |
| 3 解析/通用规则 | docx/rules、17来源组22action、来源段落/哈希、JSON schema | 测试通过；按当前正文证据判断资格；类型/位置/画像不确定失败关闭，质量准确率未计算 |
| 4 计划与DOCX | 固定模板、原文/位置/源哈希、屏障/重叠/字符边界；同计划双产物 | 独立夹具及Word COM通过；业务发布链路仍关闭 |
| 5 报告/交付/续跑 | JSON/Markdown、批次汇总、owner授权及下载完整性；模型检查点 | 真实API报告/下载及损坏/旧版本拒绝通过；结构/位置/计划/产物重新生成 |
| 6 正式前端 | frontend、GF原标志、橙红强调、Office布局、真实API | 浏览器上传→真实worker/model→结果→JSON/MD/批次MD下载；1440桌面、390手机无页面横向溢出 |
| 7 配置/文档 | local.ps1、env示例、uv.lock、README、DEPLOYMENT_PARAMETERS | 文档启动脚本API及测试模式运行成功；生产身份/容量/数据库/存储等待定 |
| 8 验证 | 单元/集成、独立结构/Word、真实三场景/续跑/UI、小批和230回归 | 135项测试通过；各实际结果下列；不把替身当真实验收 |

## 实际命令与结果

全部PowerShell，Python使用仓库`.venv`。模型环境只向测试进程安全继承用户级变量，未打印/提交密钥。

```powershell
& .\tools\local.ps1 -Mode test
node --check .\frontend\app.js
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/corpus_audit.py
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/corpus_audit.py --metadata-only
.\.venv\Scripts\python.exe -X utf8 tools/evaluation/word_fixture.py
pwsh -NoProfile -File tools/evaluation/word_acceptance.ps1
```

- 最后完整测试：**135 passed、2 warnings，17.43秒**。之后仅移除rules.py末尾空行，`git diff --check`通过，并重新执行真实三场景。警告为Starlette/httpx弃用提示及故意重复ZIP测试夹具；没有测试失败。
- `node --check`通过。
- 514份结构审计：0解析错误、源哈希不变、只读区域越界可写节点0；445.16秒。TOC元数据修正后另验全部12份误报静态目录及2份真TOC，全部正确；未声称重跑完整审计。
- Word16.0 build16.0.14334隐藏打开：5个edit/10个OOXML修订节点（Word可见9条）；接受后0条，正文及全部7种可用story与最终版逐字一致；8个非目标段落和其他部件不变。没有人工页面布局视觉验收；目录未刷新。
- 编译器重现来源哈希和22action包，已包含在测试中。编号冲突具体影响及R09/R10→当前R11/R12/R13映射见RULE_ID_MAP。

真实命令入口（执行前必须按EVALUATION_PROTOCOL设置账本、调用/费用上限、模型及通用请求选项；不能无界调用）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.evaluation.real_scenarios --scenario normal --output <独立运行目录>
.\.venv\Scripts\python.exe -X utf8 -m tools.evaluation.real_scenarios --scenario structure_failure --output <独立运行目录>
.\.venv\Scripts\python.exe -X utf8 -m tools.evaluation.real_scenarios --scenario truncated --output <独立运行目录>
.\.venv\Scripts\python.exe -X utf8 -m tools.evaluation.real_resume --output <独立运行目录>
.\.venv\Scripts\python.exe -X utf8 -m tools.evaluation.controlled_regression --input var/evaluation/smoke_inputs --output <独立运行目录> --batch-size 4 --expected-count 8
.\.venv\Scripts\python.exe -X utf8 -m tools.evaluation.controlled_regression --output <独立运行目录> --batch-size 10 --expected-count 514
```

最后一条在用户调整范围时暂停，仅完成的23批计入230份；不能把该命令写成514份完成。浏览器E2E使用Playwright和真实localhost8765 API，worker实际执行`python -m fundlex.jobs --once`。标准启动另在localhost8000验明：带开发身份的health/batches、HTML、JS均200；无身份health401。

## 真实模型与资源

配置API alias/实际响应模型均为`deepseek-flash`，官方映射DeepSeek-V4.1-Flash；响应未提供不可变模型快照，不把alias当固定版本承诺。请求选项`thinking.type=disabled`由供应商中立配置注入。初始用户模型值曾HTTP400，仅测试进程用官方API alias覆盖，未修改用户级变量。[官方模型价格](https://api-docs.deepseek.com/quick_start/pricing/)；预算保守采用峰时输入0.3/百万、输出1.2/百万USD，不计优惠，以下估计均非账单。

| 最终三场景 | 实际HTTP | token | USD估计 | 模型延迟ms | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| normal | 2 | 1067 | 0.0004443 | 1999 | 资格符合，零编辑诊断 |
| structure_failure | 1 | 400 | 0.0001380 | 1094 | EXISTING_REVISION_UNSUPPORTED |
| truncated | 1 | 381 | 0.0001152 | 610 | MODEL_SCHEMA_INVALID |

- 正常：证据位置/原文核验、固定包加载、空计划校验、同源字节诊断DOCX和实际API报告下载通过。空计划不能替代已发布action的真实非空修改验收。
- 既有修订：实际模型确认资格后结构拒绝，无合同产物下载。
- 截断：将真实模型输出上限设为1，实际finish_reason=length/JSON不完整被schema拒绝，未用替身。
- 续跑：首次真实2次请求（1070token）后注入存储异常；同任务重试复用2项检查点，新增HTTP0、token0、费用0；结构/证据位置/计划/字节一致性重新核验，实际API下载通过。只读缓存按源、规则、引擎/schema、提示、模型传输配置绑定；已发布自动写入禁用缓存。
- 最终浏览器批次：2份独立DOCX、3次真实HTTP、1473token；正常不完整/结构失败清楚呈现，最终下载不开放；其他开发身份404。正常页面控制台0错误/警告；故意访问其他身份对象产生预期404网络记录。
- 8份最终小批：3符合、3排除、2证据不明确失败；10次HTTP、9636token、USD0.0040104，费用组1/3核验、上下文截断0。不是独立准确率评测。

## 用户确认的230份回归

- 原514样本范围缩减为已完成230份，剩余284份取消；第24批部分记录不纳入完成统计。
- **149 eligible、77 excluded_by_fund_type、4 failed**。资格失败为FUND_TYPE_EVIDENCE_MISSING 2份、FUND_TYPE_INVESTMENT_EVIDENCE_MISSING 2份。单份失败未阻断已完成批次。
- 实际425次HTTP、输入329493、输出59847、总389340token；USD0.1706643。限流0；模型层记录5次错误，与资格4份失败属于不同层次。
- 端到端单合同p50=4250ms、p95=5719ms，超过3分钟0份；不是生产负载性能验收。
- 149份画像中费用组8份完整核验、截断0。剩余字段不可靠时未知，依赖动作失败关闭。不能声称费用画像质量达标。
- 149份经校验空计划和诊断产物（源字节相同），全部230份修改数0；交付228 not_generated、2 incomplete，没有complete最终合同。候选区域body464；本次样本回归未证明摘要目标覆盖，摘要编辑由独立夹具验证。
- 源清单514份哈希在收尾重查仍未改变；这不表示剩余284份做了模型回归。
- 回归引擎`e17891baee83fc2fa9c9a9878e21865f33de54b599e83587528c16aa76f219ec`；随后新增恢复功能并定向实测，当前引擎`55753716cfededb918baefdf6ce7fd1626aeef8a838f9dc9a4230038700949be`。格式收尾前的续跑/UI引擎f0f355cd，功能相同，区别为末尾空行；最终三场景已在当前指纹重跑。没有把230份旧指纹报告伪装为新指纹结果。
- 基线130份因费用上下文截断/模型类型unknown覆盖问题主动暂停，记录保留；修复后新目录运行。累计预算始终4096请求/USD5/并发1，未清零旧账本。

历史用量总账按保留ledger的唯一reservation ID去重：721项预留，718项有元数据、3项元数据缺失并保留保守费用；已知854233token，总配置费用估计USD0.3439271，限流0。包含失败实验、重复小批及旧基线；预留不一定等于已发送HTTP，早期尚无ledger时的全部尝试不可完整重建。详见MODEL_USAGE_AUDIT，不能把这些总数混成230份的用量。

## 尚未满足的发布条件和外部参数

- 逐action/依赖画像的独立标注、precision/accuracy≥0.99、recall≥0.95、越界0、模板精确率1及登记的正反例/独立/正文/摘要/结构数量未证明达标。
- 没有真实离线评测批准/发布记录；类别槽位具体文字变体未确认。全部自动写入保持关闭，未引入逐合同审批。
- 真实已发布action的非空修改验收及人工页面视觉验收尚未完成；不能将独立编辑器或空计划测试冒充。
- OIDC/身份网关、生产数据库/队列、对象存储/签名下载、服务器容量、多worker负载、预算和模型快照、留存/灾备等待定。当前dev header仅可信本机，非dev模式503，不能声称生产验收通过。
- 任务内模型阶段可复用；整个计算阶段没有通用DAG快照恢复。旧版本排队任务失败关闭需新版本重交；产物损坏下载拒绝，无自动重建已发布对象功能。上述边界已明确记入README和部署清单。

## 本地启动与关键文件

```powershell
uv sync --extra test
pwsh -NoProfile -File .\tools\local.ps1 -Mode api
# 另一个终端；四个LLM变量需在进程或Windows用户级存在：
pwsh -NoProfile -File .\tools\local.ps1 -Mode worker -Model deepseek-flash -RequestOptionsJson '{"thinking":{"type":"disabled"}}'
```

访问http://127.0.0.1:8000。默认数据为规范用户`AppData/Local/FundLex/runtime`，API与worker同目录；活动库/账本放在非同步短路径。共享预算累计默认16次/USD1，达到上限暂停，增加前须重新登记，不能删账本掩盖用量。测试进程原始数据在`C:\Users\asus\AppData\Local\FundLex`及忽略的`var/evaluation`，逐合同报告/诊断保留、不入Git。

核心：fundlex/docx.py、rules.py、model.py、model_budget.py、checkpoints.py、pipeline.py、store.py、jobs.py、api.py；rules/rules_v1.json及compile_catalogue.py；frontend/；tools/local.ps1及tools/evaluation/。

## Git与未提交资料

分支`codex/fundlex-implementation`。已审核显式暂存，无git add . / -A、无密钥/合同/法规原件/运行数据库、无改写历史或推送。

| 提交 | 内容 |
| --- | --- |
| 549fc10 | 基线审计及阶段计划 |
| e114adc | 初始安全评测后端与API |
| f662712 | 后端阶段进度 |
| 1e9ed7f | 独立DOCX结构及Word修订验证 |
| e6c29c8 | 全量固定规则、真实模型边界/预算和检查点 |
| 90a82bc | 持久状态、租约/隔离/恢复、经验证交付 |
| de55bf1 | Fluent Office真实API工作台和指定视觉参考 |

本报告、配置与评测汇总将在文档收尾提交；提交号随后记录在IMPLEMENTATION_PLAN。原始PRD/Agent/技术设计、简报、references里原有材料、tools/research及未选历史视觉样板保持未跟踪，合同/法规原件和运行产物忽略；没有整体提交目录。
