# FundLex 部署参数与本地运行边界

截至 2026-10-14，本文列出代码默认值和生产部署边界。4C8G 初始部署参数见 `DEPLOYMENT_GUIDE.md`（2 API / 1 worker / 模型并发 1）；该配置通过环境变量注入，不等于下表的开发默认值。默认值不构成吞吐或延迟承诺；action 写入仍由发布门槛决定。

## 本地存储、身份与 worker

| 配置或入口 | 当前默认 / 实际行为 |
| --- | --- |
| `FUNDLEX_DATA_DIR` | Windows 默认 `Path.home()/AppData/Local/FundLex/runtime`，典型为 `C:\Users\<用户>\AppData\Local\FundLex\runtime`。显式配置会覆盖默认；API 与 worker 必须指向同一目录。 |
| `FUNDLEX_MODEL_LEDGER` | 默认数据目录下 `model_budget.sqlite`；所有属于同一预算范围的 gateway 必须使用同一 ledger。 |
| `FUNDLEX_AUTH_MODE` | 默认 `dev`，使用 `X-FundLex-User`，仅适合可信本机开发；生产使用已实现的 `password` 本地账号和持久会话。其他模式返回 503；OIDC/SSO 尚未实现。 |
| worker 运行模式 | 本地目录 OS 文件锁限制同时只有一个执行中的 worker；SQLite 状态库启用 WAL。该机制没有完成多主机或生产并发验收。 |
| worker 租约 | `Worker(..., lease_seconds=900)` 默认 900 秒；构造参数须为正数。处理期间以约租约三分之一间隔心跳，当前 token 且租约未过期才可续租、重试和发布。不是环境变量配置。 |
| 合同尝试次数 | store 默认最多 3 次；退避基数 2 秒、指数增长并带 0.8–1.2 抖动，延迟上限 300 秒。可经 Python 参数调整，当前无对应环境变量。 |
| `FUNDLEX_MIN_FREE_BYTES` | 默认 268435456（256 MiB），领取任务前检查数据目录所在磁盘余量；低于阈值阻止继续领取。 |
| `FUNDLEX_MAX_RESULT_BYTES` | 默认 104857600（100 MiB），worker 对待发布合同/已有 Markdown 文件大小总和进行检查；不是整个临时目录或全量数据留存额度。 |

API 在每次读取批次、报告和下载时检查批次 owner。下载不是公开静态对象地址，且再次检查文件大小和 SHA-256，响应使用 `private, no-store`。目前没有生产 OIDC、限时签名下载 URL、静态加密或保留期限清理器。

合同任务状态和报告持久化，进程重启后可重新领取过期任务。每次领取递增 fencing token；旧 worker 不能覆盖新的尝试。产物在隔离目录生成，完整交付要求独立验证断言和 final/redline 实际 SHA-256 与报告一致，再发布不可变对象指针。

当前恢复重新执行合同的结构和证据定位；只读链路有**任务内模型阶段检查点**，成功判断按输入、规则、引擎/schema、提示和模型传输配置绑定，复用时重验JSON/原文引述。检查点损坏、输入/依赖变化导致重新调用。编辑计划和DOCX产物重新生成，已发布自动写入禁用该缓存。检查点含提取证据，按合同数据保护和留存；校验哈希用于本地完整性检测，不构成恶意本地用户可重写文件情况下的签名认证。源文件、规则哈希、引擎源码哈希和 schema 参与幂等或执行校验；引擎/规则变化会使旧排队任务失败关闭，需按新版本重新提交。历史损坏产物不会被静默复用。

## 上传与解析限制

API 限制在导入 `fundlex.api` 时读取；变更环境后须重启 API 进程。

| 环境变量 | 默认值 |
| --- | --- |
| `FUNDLEX_MAX_UPLOAD_BYTES` | 26214400（单文件 25 MiB） |
| `FUNDLEX_MAX_BATCH_DOCUMENTS` | 20 |
| `FUNDLEX_MAX_BATCH_BYTES` | 52428800（批次 50 MiB） |
| `FUNDLEX_MAX_UNCOMPRESSED_BYTES` | 209715200（ZIP 展开总量 200 MiB） |
| `FUNDLEX_MAX_PART_BYTES` | 33554432（单 ZIP 部件 32 MiB） |
| `FUNDLEX_MAX_COMPRESSION_RATIO` | 100 |

只接收 DOCX，拒绝重复 ZIP 成员、缺少必要包部件、加密成员以及超限内容。解析器另有 `ZipLimits` 构造参数：文件 64 MiB、展开 256 MiB、部件 64 MiB、压缩比 200、3000 个成员、XML 深度 128、节点 200 万。直接调用解析器不会自动继承 API 的更严格环境限制。

## 模型、请求和预算

`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 必须由运行进程配置；`LLM_PROVIDER` 为供应商元数据。密钥不写入仓库、报告或日志，也不回显。当前测试供应商与模型并不代表生产选型。

| 环境变量 | 默认值 / 范围 |
| --- | --- |
| `FUNDLEX_MODEL_CONTEXT_CHARS` | 12000，单请求局部上下文字符上限 |
| `FUNDLEX_MODEL_MAX_CALLS` | 默认 16；多对多定位及产物复核部署推荐 192，单 gateway 实例逻辑调用上限 |
| `FUNDLEX_MODEL_MAX_OUTPUT_TOKENS` | 1500，单请求输出上限 |
| `FUNDLEX_MODEL_TIMEOUT_S` | 45 秒；连接超时不超过 10 秒，读取与每次响应处理有界；重试会增加整个逻辑调用耗时。 |
| `FUNDLEX_MODEL_RETRIES` | 1，即每逻辑请求最多初次加一次可重试尝试 |
| `FUNDLEX_MODEL_MAX_REQUESTS` | 16，共享 ledger 的累计 HTTP 尝试额度；每次重试单独计数，不是按日自动重置。 |
| `FUNDLEX_MODEL_MAX_COST_USD` | 1，共享 ledger 的累计估计费用上限 |
| `FUNDLEX_MODEL_CONCURRENCY` | 1，共享 ledger 内同时有效的 reservation 上限；本地 single worker 是当前运行约束。 |
| `FUNDLEX_MODEL_INPUT_USD_PER_M` | 1，每百万输入 token 的估计美元单价 |
| `FUNDLEX_MODEL_OUTPUT_USD_PER_M` | 5，每百万输出 token 的估计美元单价 |
| `FUNDLEX_MODEL_REQUEST_OPTIONS_JSON` | `{}`；仅允许 `reasoning_effort`、`thinking`、`reasoning` 键，具体值须与供应商兼容。 |

每个 HTTP 尝试先预留最坏情况费用，有可信 usage 时据此调整；usage 缺失时保留预留费用。报告估计费用不是供应商账单，缓存价格、折扣、实际结算和地域币种须另行核对。不得通过删除 ledger 来掩盖已发生请求或释放预算。

暂时模型网络/重试耗尽可进入合同 `retry_wait`；连续两次合同尝试仍故障时暂停该批次。模型断路、共享请求额度/费用上限、实例调用上限或 `MODEL_LEDGER_UNAVAILABLE` 立即触发暂停（达到终态尝试上限的合同记录失败）。ledger 写入失败保留已获得的 usage 信息及已预留费用，失败关闭。`ModelBudget` 的断路默认最近 3 次服务失败、120 秒冷却，经构造参数配置，目前没有环境变量入口。

已实现 `POST /api/batches/{batch_id}/pause` 和 `/resume`。恢复前应确认服务、存储、预算配置和可用额度；恢复不会清零累计费用或合同尝试次数。当前暂停作用于发生故障的批次；其他批次仍受共享 ledger 门槛约束，并非独立实现的全部署调度熔断器。

## Windows 本地运行目录调查结论

在仓库所在桌面目录运行 SQLite 时曾间歇出现 `attempt to write a readonly database`。故障目录发现百度网盘上传侧车，时间与 WAL/SHM 创建相近，数据库本身只有 Archive 属性；尚未捕获实际故障时外部句柄的所属进程，不能把特定同步程序归因写成已证实结论。

隔离 Win32 实验已证明：外部只读 `CreateFileW` 句柄若仅开放 `FILE_SHARE_READ`、拒绝写共享，普通 SQLite 连接和 URI `mode=rw` 都可以打开成功，但随后写入返回 `SQLITE_READONLY`（code 8）。关闭外部句柄后写入恢复。因此仅改连接模式或无限重试不能解决外部文件共享冲突。非同步系统 TEMP 目录下的 30 次纯 callback 合同执行、预算 reserve/finish 与 60 次报告下载通过，未调用模型。

当前默认路径使用规范用户目录 `Path.home()/AppData/Local/FundLex/runtime`，避开仓库/同步目录，也避开 MSIX 对 `LOCALAPPDATA` 的长路径重定向。评测状态目录标识已缩至 32 位，解决此次深层产物路径的 Windows MAX_PATH / WinError 3 问题。显式覆盖目录时仍需选择非同步、足够短且可写的位置；应用尚未证明任意超长路径均可运行。运行库和 ledger 可留在本地目录，评测报告导出到仓库。

## 生产部署仍需确定

| 项目 | 待确定内容与当前缺口 |
| --- | --- |
| 身份与权限 | OIDC issuer/audience、可信反向代理边界、token 验证、用户/租户对象授权；当前 dev header 不具备生产身份保证。 |
| 数据库与队列 | 支持事务和多 worker 的关系数据库、迁移/备份恢复、部署级租约/锁、跨实例队列与预算适配；SQLite 本地验证不能作为生产并发验收。 |
| 对象存储 | 供应商/地域、不可变版本、完整性校验、访问控制、限时下载、加密与密钥轮换、失效对象清理。 |
| 容量与性能 | CPU/RAM/临时盘/磁盘低水位、峰值 RSS、P50/P95/尾延迟、吞吐、同时用户、最大合同复杂度和负载测试；3 分钟目标仍需按环境验证。 |
| 模型与预算 | 供应商/模型版本/地域、真实计价、总预算、每批额度、部署级并发/限流、错误阈值、恢复策略及账单对账。 |
| 数据留存 | 原件/产物/报告/模型元数据的期限、删除和备份保留、灾备恢复测试、供应商内容保留/日志条款。 |
| 发布与质量 | 每个 action 的证据/画像/候选精度、独立结构验证、Word 桌面兼容、版本变化后的受影响回归；仍须遵守业务发布门槛。 |
| 运维 | 服务启动/健康检查、指标告警、存储故障时可观测暂停、清理失败处理、日志脱敏、升级与回滚。 |

全量样本评测结果须以实际生成的协议、汇总和版本记录为准。本地可运行、测试通过或批次 completed 均不表示每份合同已成功修改，也不自动满足生产上线条件。

模型阶段检查点放在数据目录 `checkpoints/<document_id>`，不跨任务/身份复用；不存密钥。发布版规则链路始终重新执行真实模型，避免缓存替代新发布版本验收。worker遇到过期或旧租约仅丢弃该尝试，仍可继续领取任务，不允许旧尝试发布。
