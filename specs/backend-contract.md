# 后端契约（2026-10-12）

## 模块

- `docx`: DOCX 包检查、位置映射、受限编辑和产物复核。输入只接受 Transitional DOCX；失败抛稳定代码，源文件不变。
- `rules`: 不可变版本化规则包、精确模板来源、资格/画像证据和 action 发布开关。所有首版业务 action 的 `auto_write=false`，直到预登记评测、批准及编辑器门槛实际完成。
- `model`: `ModelGateway` 只收有界合同片段和受限任务，返回结构化数据及模型、token、延迟、错误指标，不接收多份合同全文，不返回写入文本。
- `pipeline`: `process(input_path, output_dir, ruleset_version) -> report`。资格先于完整结构预检；排除与失败生成报告、不生成修改合同。eligible 且无可执行编辑时，经验证的空编辑计划可生成内容不变的修订/最终版，用于链路证明；报告必须明确零修改及 action 写入关闭。
- `store/jobs/api`: SQLite 与本地对象存储、单 worker、fencing token、幂等提交、按合同隔离；开发身份头 `X-FundLex-User`，缺失拒绝，生产身份未配置时拒绝。

## HTTP

- `POST /api/batches`: multipart `files[]`, `ruleset_version`, 可选 `Idempotency-Key`；返回批次 ID/status/total/documents。
- `GET /api/batches`: 当前身份的批次列表。
- `GET /api/batches/{id}`: 当前身份的批次状态、documents 及可用下载 URL。
- `GET /api/batches/{id}/documents/{document_id}/report`: JSON 事实源。
- `GET /api/batches/{id}/documents/{document_id}/download/{kind}`: `final`, `redline`, `report_json`, `report_md`；只有经验证且交付状态 complete 的合同公开两个 DOCX。
- `GET /api/batches/{id}/report`: Markdown 批次汇总。
- `/` 和 `/static` 同源提供 `frontend/`。

## 数据约束

逐合同报告分开保存资格、证据、画像、候选、action、编辑计划、产物断言和交付状态；`not_matched` 不等于 `not_applicable`。证据包含主文档 part、结构位置、段落区间、原文短引文和验证状态。所有内容哈希和版本记录在报告；密钥、完整 prompt 和完整合同不进日志。未知资格/证据/结构/模型错误失败关闭。`complete` 仅在所有需处理位置已核验、可用产物通过复核时使用。

## 验证

先独立 DOCX 夹具证明编辑器，再真实模型单份/极小批应用流程，再按调用/费用上限受控扩至 514 DOCX。规则未发布时只能验证空计划应用链路，固定模板的实际编辑通过独立结构夹具证明，不能称为业务 action 已发布。
