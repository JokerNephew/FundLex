# FundLex 实施计划与验收记录

> 2026-10-12 从无提交的 `main` 和未跟踪资料开始。此文件记录执行状态；未验证的阶段保持未完成。用户已授权分阶段自主推进。`funds/` 的 PDF 不进入运行链路，`funds_word/` 的 514 份 DOCX 仅作评测与回归。

## 基线与资料口径

- 已阅读 `IMPLEMENTATION_BRIEF.md`、`README.md`、PRD v4.1、Agent 设计 v4.1、详细设计 v1.1；仓库未发现额外 `AGENTS.md`。当前对话的 Windows/PowerShell 约束适用。
- Git：`main` 无提交，远端 `origin` 已配置；所有原有资料未跟踪。仅显式暂存新应用代码、测试、配置与计划，不纳入样本、原件或密钥。
- 样本：`funds/` 514 PDF，`funds_word/` 514 DOCX；不执行历史转换脚本。
- 模型：4 个 `LLM_*` 变量在 Windows 用户级环境存在、进程级缺失。仅报告存在性，不输出值；实测前仅向测试子进程安全注入。
- 运行环境：系统 `python`/`py` 启动器不可用；已用 Codex bundled Python 创建忽略的 `.venv`。本地 profile 为 SQLite、文件存储和单 worker；生产身份、数据库、对象存储、容量及预算均未确定。
- `IMPLEMENTATION_BRIEF.md` 把“真实模型正常场景需验证 DOCX 产物”列为验收，同时 PRD/Agent/详细设计要求未通过 action 发布门槛不得自动写入。影响：首版业务 action 只能只读评测，不能把真实模型成功当作发布批准。编辑器产物需以独立夹具验收；如果无法满足“同一真实模型业务流程生成修改产物”，最终如实列出该差距，不能绕过门槛。

## 需求追踪

| 需求 | 实现位置 | 证据/验收 |
| --- | --- | --- |
| DOCX only、资格排除、证据失败关闭 | `fundlex/docx.py`, `fundlex/rules.py`, `fundlex/pipeline.py` | 独立结构夹具、真实 DOCX 小批、514 回归 |
| 规则版本、固定模板、发布门槛 | `rules/`, `fundlex/rules.py` | 静态校验、模板逐字比对、开关断言 |
| 结构范围与非目标保护 | `fundlex/docx.py` | 目录/域/超链接/文本框/表格夹具、非目标快照 |
| ModelGateway 有界真实调用 | `fundlex/model.py` | 真实应用单份及失败关闭场景、token/延迟/错误 |
| 唯一编辑计划、修订/最终版 | `fundlex/docx.py`, `fundlex/pipeline.py` | 独立 DOCX 夹具、接受修订等价与部件哈希 |
| 状态、隔离、幂等、续跑 | `fundlex/store.py`, `fundlex/jobs.py` | API/worker 集成测试与进程重启 |
| 报告、汇总、查询下载 | `fundlex/pipeline.py`, `fundlex/api.py` | JSON/Markdown schema、API E2E |
| Fluent Office 工作台 | `frontend/` | 浏览器/API 联调与响应式验证（主 agent） |
| 生产部署参数 | `README.md`, 配置说明 | 本地启动及上线前待定项（主 agent） |

## 阶段门槛

### 1. 审计与设计

- [x] 重新阅读资料、核对 Git/样本/运行环境；记录冲突及影响。
- [x] 冻结本地 API 契约与模块边界；建立需求追踪和阶段计划。
- [x] 检查 `.gitignore` 和初始配置，显式暂存并审阅提交。

### 2. 持久主流程

- [x] DOCX 上传、ZIP 基本拒绝、不可变输入对象、批次/逐合同状态及隔离执行（本地 profile）。
- [x] SQLite 持久化、任务租约/续跑、重复提交幂等和单 worker（本地 profile）。
- [x] 接口、开发身份适配、报告/下载权限；运行集成测试。生产 OIDC/限时下载链接未配置。

### 3. 结构与规则

- [x] 支持子集内的文本投影、位置映射、章节/区域识别、非目标屏障与输入预检；复杂结构失败关闭。
- [ ] 完整的可核验资格/画像、指引全量通用 action 与固定模板静态编译。当前 v1 仅 4 个试评 action；收费组画像和适用性未完成，不得发布写入。
- [x] 首版业务 action `auto_write=false`；无门槛或批准不得启用。
- [x] 独立夹具与 20 份样本资格抽查；保守误拒绝与覆盖率待 514 回归量化。

### 4. 模型与只读评测

- [x] 供应商中立 ModelGateway、结构化响应校验、单请求有界上下文/重试与指标。
- [ ] 进程/批次全局调用和费用上限及受控小批 runner；当前仅 gateway 实例级调用上限。
- [ ] 真实应用单份正常/失败关闭场景，记录模型、token、费用、延迟、限流、错误。
- [ ] 注册调用和费用上限后，受控分批 514 DOCX 只读回归。

### 5. 编辑器与产物

- [x] 编辑器子模块验证唯一计划、模板/范围/重叠校验；生产 pipeline 因规则门槛关闭，只生成非可执行零编辑计划。
- [x] 独立夹具验证同计划修订版/最终版、接受修订等价及非目标未改；真实 Word 桌面打开/接受修订未验。
- [x] 已覆盖跨 run、表格、目录、域、超链接、文本框、既有修订/重复 ZIP 的独立夹具；详细设计列出的其他极端结构仍待补齐。

### 6. API、前端与最终验证

- [ ] 报告/批次汇总、查询/下载、Fluent Office 前端真实 API 联调。
- [ ] 单元、集成、E2E、真实模型场景及受控 514 回归；逐项记录结果。
- [ ] README、上线前参数清单、本地启动；显式暂存审阅并按边界提交。

## 提交与验证日志

| 阶段 | 测试/检查 | 提交 | 备注 |
| --- | --- | --- | --- |
| 基线 | Git/样本/环境存在性检查、`.gitignore` 检查 | `549fc10` | 不复制或提交样本与密钥 |
| 本地后端原子阶段 | `& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider` → 22 passed、2 warnings；API→worker→pipeline 使用 DOCX 夹具和替身模型，不能算真实模型验收 | `e114adc` | 未执行 514 回归、真实模型、Word 桌面兼容 |

## 续跑记录

当前进行：阶段 3–6 的业务规则、真实模型及前端联调；阶段 1 和阶段 2 的本地 profile 已通过当前测试。提交 `549fc10` 与 `e114adc`；主 agent 同时新增 `frontend/` 和修改 `README.md`，请保持文件所有权。最近验证：`& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider` → 22 passed、2 warnings；其中 API→worker→pipeline 已用 DOCX 夹具和替身模型跑通。首 20 份 DOCX 资格抽查发现至少一份因目录域复杂结构被保守标为证据缺失，需量化覆盖。尚未完成：全量指引 action/画像、跨批次全局调用与费用预算、真实模型正常及失败关闭场景、514 DOCX 受控回归、Word 桌面端兼容、生产 OIDC/数据库/存储/限时下载。下一步：先用真实模型单份 DOCX 验证证据位置、零编辑计划、诊断 DOCX 与报告，修复问题；实测 token/费用/延迟后制定全局上限和小批 runner；再推进 514 回归及规则覆盖。额度恢复后从此处继续，不重做已通过单测；不要将 0-edit 评测 DOCX 当最终合同。
