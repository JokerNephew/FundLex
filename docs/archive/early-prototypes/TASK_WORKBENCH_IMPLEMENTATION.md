# 正式任务工作台实施计划与契约

日期 2026-10-13。用户已确认 HTML 原型并授权正式开发。沿用任务级工作区、固定导航与 Fluent Office 视觉。只接收 DOCX；22 个业务动作自动写入仍关闭；不增加人工复核、审批或待办。

## 实施基线

当前 `codex/fundlex-implementation`，原型提交 `5a8684b`。工作区另有规则、证据识别、评测及 IMPLEMENTATION_PLAN.md 的并行修改；本任务不修改或提交这些文件。正式前端复用既有静态 HTML/CSS/JavaScript，执行层复用 RunStore 和 worker。验收启动独立临时运行目录，不操作现有合同或运行数据库。

## 任务层契约

业务单位是持久任务，技术批次对用户透明。现有批次端点保持兼容。任务创建先登记不可变文件清单；浏览器按服务端配置的数量/体积限制串行分段上传，逐文件接收回执与幂等防止网络重试重复创建合同。服务端将接收合同原子关联到任务后交给既有 worker。上传阶段与合同处理阶段分开统计；接收失败、尚未上传、排队、处理中、处理结束与交付完整性分别呈现。

已实现的正式端点：

- `GET /api/capabilities`：开发环境与上传限制、实际规则版本及自动写入状态；数量/分段大小仅供前端上传编排。
- `POST /api/tasks`：JSON `{name, ruleset_version, files:[{client_id,name,size}]}`，支持 `Idempotency-Key`，返回任务 ID 和摘要。
- `GET /api/tasks`：身份限定的任务查询，支持任务名搜索、状态、排序和分页；历史独立批次以历史任务形式查询，不改写原数据。
- `GET /api/tasks/{task_id}`：任务摘要，包含期望总数、已上传、待上传、接收失败、排队、处理中、已处理、失败关闭、资格和交付统计，以及上传/执行状态。
- `POST /api/tasks/{task_id}/uploads`：multipart `files` 与 JSON 编码的 `client_ids`，保持单请求实际配置限制；返回逐文件接收回执，同一清单项重试不重复创建合同。
- `POST /api/tasks/{task_id}/seal`：结束本次上传尝试；未上传清单仍保留，可补传；不得静默缩小任务规模。
- `POST /api/tasks/{task_id}/pause|resume`：整个任务的事务控制；正在执行的合同可安全结束，停止后续领取；新接收文件继承任务暂停状态。
- `GET /api/tasks/{task_id}/documents`：任务范围内服务端文件名搜索、资格、执行状态、交付完整性、原始原因码、排序、分页；返回 `items,total,page,page_size`。逐合同 `report_url` 和 `downloads` 继续使用已授权的真实批次端点。
- `GET /api/tasks/{task_id}/report`：根据任务全部文件生成真实 Markdown 汇总，保留未接收/未上传条目。

每个端点验证 owner；其他身份统一返回不存在，不暴露文件名、统计、报告或下载地址。开发身份变化时前端立即清空旧数据、终止请求，并丢弃迟到响应。生产身份未配置仍失败关闭，不能把开发设置包装为生产登录。

## 前端工作流

任务总览 → 批量导入与预检查 → 整任务上传/处理 → 全部合同结果 → 证据抽屉/真实报告下载。文件可多选、拖入、文件夹选择和追加；紧凑清单搜索/异常筛选/分页/移除/清空。技术拆批不出现在业务界面。中断后任务清单和已接收条目持久保存，补传需用户重新选择本地文件，明确浏览器不能跨重载保留文件权限。

结果列表使用任务范围的真实服务端筛选与分页。资格符合、处理结束、交付完整及最终合同可用独立表达；只显示真实 API 开放的合同下载，诊断文件绝不伪装成最终合同。失败中文解释和原始错误码分别在业务提示与追溯详情呈现。固定侧栏和独立工作区滚动，桌面全宽，笔记本与手机无页面级横向溢出，弹层具备焦点管理。

## 实施与验收

- [x] 持久任务与清单、分段接收幂等、任务查询、控制和汇总；完成规格与代码审查。
- [x] 正式前端任务工作区、导入、上传、中断补传、查询、证据、下载与开发设置；完成规格与代码审查，浏览器交互验收另列。
- [x] API 测试：多段/失败隔离/重复请求/并发接收/身份隔离/暂停继承/分页筛选/历史兼容；完成语义补充后独立复跑任务与既有批次共 35 项通过。
- [x] 独立运行目录浏览器：240 份构造 DOCX 经真实上传、存储与 worker，业务处理器为明确夹具；已覆盖刷新、四类结果、报告与任务汇总下载、任务范围搜索、长内容、暂停补传和身份隔离。详见 `TASK_WORKBENCH_VALIDATION.md`。
- [ ] 笔记本和手机视口、页面溢出及固定侧栏滚动的最终浏览器检查：用户要求停止追加检查，本轮未完成该项验收；响应式实现已经落地。
- [x] 本轮无需真实模型调用，实际调用数为 0；未重跑 230/514 份业务回归。
- [x] 更新验证证据和已有截图；只显式暂存本任务文件并本地提交，不部署、不推送。

## 已确定的响应结构

任务摘要返回 `id,name,legacy,ruleset_version,ruleset_sha256,status,upload_status,created_at,updated_at,total,uploaded,pending_upload,rejected,queued,processing,completed,failed,qualification_counts,delivery_counts,summary_url,pause_reason`。`completed` 是处理终态总数，包含成功结束与失败关闭；`failed` 为其中的失败数。任务状态为 `uploading/queued/running/paused/completed`，上传状态为 `pending/partial/complete/sealed_incomplete`。任务总数始终以初始清单为准。全部清单均已接收并进入终态时优先显示完成；暂停时最后一份在执行合同安全结束后不要求再次继续以确认完成。仍有未接收清单时保持暂停，补传仍继承暂停。

任务与合同查询均返回 `{items,total,page,page_size}`。任务查询参数是 `q,status,sort,page,page_size`。合同查询参数是 `q,eligibility,job_status,delivery_status,error_code,upload_status,sort,page,page_size`，查询范围为整个当前任务。排序值为 `newest/oldest/name/name_desc`，合同另支持 `exceptions/status` 的异常优先和处理状态排序；合同默认按初始清单顺序。分页限制和文件接收分段规则属于内部实施细节。

合同条目为 `batch_id,document_id,client_id,name,size,job_status,upload_status,eligibility,delivery_status,error_code,report_url,downloads,source_sha256,reason_codes`。未接收条目的合同 ID、技术批次 ID、报告链接及源文件哈希为空，处理状态为 `not_started`。上传状态为 `pending/rejected/accepted`。`reason_codes` 保留文件错误及实际规则动作/候选失败原因；原因筛选匹配该集合，原始 `error_code` 不改写。合同查询另返回整个任务的 `reason_options:[{code,count}]`，防止按当前页生成原因选项。

接收回执为 `{receipts:[{client_id,status,document_id,batch_id,error_code}],task}`，回执状态为 `accepted/already_accepted/rejected`。相同清单项重试核对源文件 SHA-256、大小和名称；冲突不替换原已接收合同。开发能力接口返回 `auth_mode,ruleset_version,ruleset_sha256,actions_total,auto_write_enabled,auto_write_count,action_labels,upload_limits,task_api`，其中开关由实际规则包读取，`action_labels` 是实际动作 ID 到规则业务描述的映射，不含模板全文。

历史独立技术批次以 `legacy-{batch_id}` 映射为 `legacy:true` 的历史任务，保留原报告与下载，不迁移或改写历史合同。历史任务允许暂停/继续以保留既有处理工作流，不允许追加上传或重新结束上传清单。尚未执行完的历史合同仍受既有引擎/规则哈希校验约束；新版本不能自动复用旧引擎绑定继续写入。

## 后端审查与验证记录

2026-10-13 完成两阶段审查。规格检查覆盖清单总数持久保留、逐文件拒绝隔离、同一清单项源文件身份核验、任务与执行批次原子关联、暂停继承、预算故障整任务暂停、真实原因查询、历史流程与 owner 隔离。代码检查额外修复了已提交接收数据后的孤儿文件清理异常误删输入风险，并用故障注入测试确认新旧已发表输入均保留。摘要避免读取每份合同产物；查询结果只在报告存在时提供报告入口。

母代理在独立临时目录复跑 `tests/test_tasks_api.py tests/test_api_store.py`，实际输出 `33 passed, 1 warning in 5.45s`。临时根为 `C:\Users\asus\AppData\Local\Temp\fundlex-mother-review-f1cb38c826c1425a9098ce7b3609c0f6`，测试进程在导入 API 模块前将 `FUNDLEX_DATA_DIR` 指向其中 `module-default` 子目录。提示为既有 Starlette/httpx 弃用警告；报告类别属于明确夹具，未调用模型、未重跑样本回归或修改现有运行数据。

缓存隔离门槛补充后，所有 `/api/*` 成功与错误响应统一带 `Cache-Control: private, no-store`，静态资源保持独立行为。新增 401、owner 404、能力、合同列表、未知 API 404 及静态资源响应检查。母代理最终独立复跑实际输出 `34 passed, 1 warning in 5.30s`，临时根为 `C:\Users\asus\AppData\Local\Temp\fundlex-mother-cache-review-d306349577414cb0ab8683707d3350c8`。后端修改改变引擎哈希，浏览器验收服务应重启并重新创建隔离夹具。

完成状态语义补充后新增“暂停时最后执行中的合同结束”测试，并保留未接收清单暂停继承测试。母代理最终独立复跑输出 `35 passed, 1 warning in 5.52s`，临时根为 `C:\Users\asus\AppData\Local\Temp\fundlex-mother-final-review-c762db817dae4d67b65ed1e1ee76e925`。全部测试为独立数据目录；业务标签按真实规则描述提供，不能以测试状态推断规则已发布。

## 前端审查记录

已用真实 API 替换原型数据与交互。规格检查覆盖整任务信息架构、固定侧栏、上传预检查与补传、任务级状态、服务端范围搜索及四维筛选分页、真实下载与开发设置。代码检查修正了终态统计重复累加失败数的问题：终态与百分比使用 `completed`，已处理数量使用 `completed - failed`；上传 XHR 的字节进度与服务端接收回执分别呈现，传输达到 100% 不等于文件已接收。

上传时锁定任务切换，迟到接收回执只更新同一任务。身份变化终止 fetch/XHR、清空可见与隐藏的旧文件名、状态、原因选项统计、文件权限和报告，JSON/下载 Blob 读取后再次校验身份版本。详情抽屉使用焦点管理与背景 `inert`；拖放容器使用分组语义和真实文件选择按钮，避免嵌套按钮角色。最终合同入口同时核对实际自动写入能力、资格、交付完整性与真实下载地址。母代理执行 `node --check frontend/app.js` 与相关 `git diff --check`，均退出码 0。此记录是实现与静态审查，真实浏览器操作证据由主代理另行记录。
