# 飞书多任务接入方案（2026-10-28）

## 目标与已确认口径

在现有“私聊 + 交互卡片”基础上，把飞书从单一合同修订入口扩展为任务中心：

1. **合同修订**：保留现有流程。
2. **合同对比（Compare）**：飞书收集左右两份 DOCX，创建 Compare 任务，状态卡 + `/compare` 深链。
3. **法规指引生成**：飞书接收法规 PDF/DOCX，创建 guide-generation run，状态卡 + `/guide-generation` 深链；审核、修改和发布仍在 Web。
4. **任务查询、结果回传**：飞书查看最近任务，发送最终版、修订版、报告；超限回退深链。
5. **只读诊断 / 评测**：
   - 用户已确认“跑完整流程”：诊断复用完整修订流程，但只回报告，不交付修改后的合同；
   - 评测模式产出评测文件（`evaluation_final` / `evaluation_redline`）和报告，明确标注不能作为正式合同；
   - 两者都在任务后端增加 `mode`，不是飞书层单独伪造。

用户已确认：**法规指引生成对所有已绑定用户开放**，不做管理员白名单。

## 交互原则

- 所有入口、步骤确认、状态、完成摘要和任务列表都使用飞书交互卡片。
- 附件仍是普通文件消息；结果文件作为文件消息回传，超过飞书限制时改为深链。
- 状态卡尽量原地 patch，避免刷屏；一个任务一张状态卡。
- 复杂的双栏差异阅读、逐条接受/拒绝、指引审核/发布保留在 Web。
- 一个飞书私聊同时只有一个活跃草稿；切换任务类型前必须完成或取消当前草稿。
- 所有卡片操作重新校验 `tenant_key + open_id + chat_id + owner`，不信任卡片里的任务 ID。

## 状态与数据模型

`feishu_drafts` 增加：

- `task_type`：`revision` / `compare` / `guide` / `diagnosis` / `evaluation`
- `step`：当前步骤（如 `left`、`right`、`confirm`、`waiting_file`）
- `metadata_json`：对比侧文件、显示名、指引 run id 等
- `target_id`：业务目标 ID（任务、Compare task、guide run）

`feishu_draft_files` 增加：

- `side`：`left` / `right`（Compare），其余为空
- `kind`：`contract` / `regulation`

`task_channels` 增加：

- `task_type`：用于 `sync_tasks` / `send_outbox` 分发
- `last_external_status`、`last_progress_json`：Compare / Guide 的通用状态缓存

`integration_outbox` 继续使用 `event_type=task_status`，`payload_json` 带 `task_type` 和目标 ID。

## 后端适配边界

- **修订**：`TaskApplicationService.create_task(..., mode="delivery")`。
- **Compare**：复用 `CompareStore.create/upload/seal` 和 compare worker；飞书只做输入收集与状态展示。
- **指引生成**：抽取 API 中的 run 创建逻辑为共享 helper，复用 `GuideGenerationStore.enqueue`；生产需要部署 `fundlex.guide_generation.cli worker` 独立服务。
- **诊断/评测**：`tasks` 增加 `mode`；worker 把 `execution_mode` 传给 `process_recall_first`；诊断在交付校验通过后只发布报告类产物；评测重命名/发布为 `evaluation_*` 产物。
- **结果回传**：`FeishuClient` 增加文件上传（`im/v1/files` + `im/v1/messages`），按 owner 校验后发送。

## 实施阶段

### Phase 1：任务中心 + 合同对比 + 查询/回传

- 菜单卡、任务类型路由、单活跃草稿约束。
- Compare 双文件草稿、确认卡、状态卡、`/compare?task=` 深链。
- 我的任务卡（最近 5–10 条），完成卡发送结果文件。
- 测试：菜单路由、Compare 草稿、重复事件、上传失败恢复、owner 隔离、文件回传。

### Phase 2：法规指引生成

- 共享 run 创建 helper；飞书 PDF/DOCX 接收与确认卡。
- run 状态卡、`/guide-generation?run=` 深链。
- 部署 guide-generation worker 模板；全部绑定用户可用。
- 测试：文件类型/大小、重复确认、run 失败、深链、权限。

### Phase 3：诊断 / 评测

- `tasks.mode` 与 API/worker 贯通。
- 诊断报告-only 产物；评测 `evaluation_*` 产物与状态标签。
- 飞书卡片、任务详情标签、下载按钮。
- 测试：诊断不暴露修改文件、评测不冒充正式合同、真实模型预算与 E2E。

## 验收边界

- 不以“卡片能点”代替真实任务完成；每个类型至少一条真实 Feishu 用户路径。
- Compare 必须核对差异数、coverage 和深链。
- 指引生成必须核对 run 完成、草案产物和 Web 审核入口；发布仍由用户确认。
- 诊断必须核对报告与实际修改文件未交付；评测必须核对 `evaluation_*` 与正式合同隔离。
- 现有修订交付仍有 `incomplete` 样本，扩展任务类型不改变项目级 NO-GO 结论。

## 当前状态（2026-10-28）

- 代码已实施：任务中心/Compare/指引生成/任务查询与回传/诊断与评测模式；完整 Python 回归 **1737 passed / 58 skipped**。
- 已受控发布生产；`fundlex-feishu`、API、两个 worker 和 `fundlex-guide-worker` 均 active。
- 真实 Feishu Compare E2E 通过（两份公开 DOCX、621 处差异、报告回传、浏览器深链）；指引 PDF 上传/确认/取消通过，未启动真实 model run；诊断/评测仅隔离测试。
- 生产修复：卡片 2.0 action 模块、guide worker 模块、并发迁移、`im:resource` 权限；新增文件收集卡（移除/替换、SHA 去重、错误提示；文件仍走消息，飞书卡片无文件上传组件）。网页与飞书均取消单批 20 个文件限制。任务名称表单卡已在 2026-10-28 产品/UX 复核后取消，改为文件优先、任务按创建时间命名（FL-D417/428）。
- 相关集中问题与验证结果登记在 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 的 FL-D400–FL-D404。
- 项目级结论仍为 **NO-GO**；本次扩展不改变现有合同修订交付质量问题。
