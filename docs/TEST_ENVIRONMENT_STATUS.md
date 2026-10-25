# Test 环境状态

更新时间：2026-10-25。本文只记录已核对的 Test 部署状态，不把基础设施就绪写成完整合同交付。

## 当前运行状态

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 主机身份 | 已核对 | hostname `iZf8zemhifedxdow1zefr0Z`；实例 `i-f8zemhifedxdow1zefr0` |
| Test API | active，监听 `127.0.0.1:8110` | `fundlex-test-api.service`、`ss -ltnp` |
| Test 公网入口 | 通过，HTTPS 200 | `https://test.8-155-130-168.sslip.io`，独立 Nginx → 8110，Let's Encrypt 证书 |
| Test Recall Worker | active | `fundlex-test-worker.service`、Test heartbeat |
| Test Compare Worker | active | `fundlex-test-compare-worker.service`、Test heartbeat |
| Production | active，监听 `127.0.0.1:8010` | 仅只读核对，未被 Test 部署脚本操作 |
| Test capabilities | 通过，environment=`test` | `GET http://127.0.0.1:8110/api/capabilities` |
| Test password auth | 通过 | `/etc/fundlex-test-credentials`，凭据值未记录 |
| Test 注册 | disabled | capabilities/configuration |
| Test 数据隔离 | 通过 | `/var/lib/fundlex-test`、独立 `auth.sqlite3`、run DB、model ledger、trace、objects、heartbeats、deployments |
| Test health | `ok` | 模型配置已与 Production 对齐；Test 数据库、两个 Worker heartbeat 和模型组件均通过 |
| 本机工作台入口 | HTTP 200 | `http://127.0.0.1:8110/`；`/tasks/new` 使用 `/test/assets` 资源别名，JS/CSS HTTP 200 |
| 本机 Compare 浏览器例 | 通过 | `/tmp/opencode/fundlex-browser-evidence/local-e2e.json`；1 处正文差异、`覆盖完整`、无浏览器错误 |

最近部署 manifest 位于 `/var/lib/fundlex-test/deployments/20261025T174210Z.json`。其中记录 API `127.0.0.1:8110`、数据根目录 `/var/lib/fundlex-test`、Python 3.11.13、前端构建哈希和 `dirty=true`。部署源工作区仍有未提交的 Test 环境改动，因此该 manifest 是验证记录，不能作为发布版本身份。

## 已完成的真实路径

已先通过 Test password login、health、创建任务、上传公开 DOCX、seal、持久 Recall Worker 处理和失败报告读取；该前置 smoke 任务 `e260a3213fae471eac04d414a46d8d8c` 以 `MODEL_CONFIG_MISSING`/`not_generated` 结束，证据位于 `/tmp/opencode/fundlex-test-smoke-postdeploy-20261025.json`。

随后按用户要求同步 Production 模型配置并完成真实模型任务。任务 `cf68b45b5d6e4cb89bf4e19cf788ef4c`、文档 `eba63a9e1cc54c81ae81be04016df3d0` 的 smoke 证据位于 `/tmp/opencode/fundlex-test-smoke-production-model-final-20261025.json`。任务实际经过登录、上传、seal、持久 Worker、真实模型调用和报告/工作文件生成；health 为 `ok`，job 为 `succeeded`，qualification 为 `eligible`，delivery 为 `incomplete`，43 个 unresolved，artifact links 包含 `working_final`、`working_redline`、`report_json`、`report_md`。模型请求 trace 共 66 行，写入 `/var/lib/fundlex-test/traces/model-calls.jsonl`，账本为 Test 专属 `/var/lib/fundlex-test/model_budget.sqlite`。

Compare 的真实任务 `be56e24776cb45659c246b0ff6300c6a`、结果 `cb9bc6c97fb74456b332b3222c08cd86` 经过 Test Compare API、独立 Compare Worker、持久化和授权查看。结果 SHA-256 为 `409bdbae3813e5d3e9830efc17829259e273d0f9837587759793cc0ff22e40af`，状态为 `incomplete`，检测到一处 insertion，并报告 header、footer、drawing 的 `UNSUPPORTED_VISIBLE_CONTENT`。成员/admin 越权查看返回 404。另有本机支持正文内容的浏览器成功例：共 1 处差异、修改 1、新增 0、删除 0，覆盖完整且浏览器错误为 0。

既有真实模型任务的产物语义核对已保存于 `/tmp/opencode/fundlex-browser-evidence/artifact-provenance.json` 和 `/tmp/opencode/fundlex-browser-evidence/selection-semantics.json`：源 DOCX 无 OOXML 修订；`working_redline` 仅含 `FundLex` 生成的 ID 1/2；`working_final` 和接受全部后的 `selected_final` 无托管修订残留；拒绝 ID 1 的独立验证产物恢复源文本并无托管修订。源 SHA 为 `55c2c66a79fa96adbc13ea41f4632dce5cc41b28dbede9fd7e457fbbd7adaf56`，既有 working/selected 文件哈希以 `/tmp/opencode/fundlex-test-artifact-review-20261025/summary.json` 为准。

43 个 unresolved 已按规则、位置和 source/working-final 段落重新对账，机器可读结果为 `/tmp/opencode/fundlex-browser-evidence/unresolved-reconciliation.json`：G01 4、G02 4、G03 3、G04 4、G09 3、G11 5、G14 4、G15 8、G16 8；其中 16 项没有单一段落位置，涉及 operation/coverage/replay 门禁。该对账支持继续保持 `delivery_status=incomplete`，没有把工作文件升级为最终合同。

本机 React 工作台全新真实任务证据位于 `/tmp/opencode/fundlex-browser-evidence/local-react-e2e-checkpoint.json`、`local-react-e2e-checkpoint.jsonl` 和 `/tmp/opencode/fundlex-browser-evidence/local-react-api-poll.json`：全新登录、深层新任务页、真实 DOCX 上传、自动 seal、持久 Worker/真实模型和结果页均通过；API 最终为 task `completed`、document `succeeded`、`eligible`、`incomplete`，报告仍有 43 个 unresolved。

同一任务的 Review 与授权交付证据已完成：`/tmp/opencode/fundlex-browser-evidence/local-react-e2e-review-download.json` 记录详情页、Review 页、1 条修订、批量拒绝、选择版生成、返回详情页和浏览器错误为 0；`/tmp/opencode/fundlex-browser-evidence/authorized-downloads.json` 记录 6 个成员授权 artifact 全部 HTTP 200。报告 JSON SHA-256 为 `2813214e2826ebb9f196788e7db5fc46d483a6325ce272a6dbe4f0bc24baa555`，报告 Markdown 为 `0fe6195694f714fec0e4c603220e9a6cfa9adcc69bea2bf347d8533b5eb50004`，选择版合同与选择版修订痕迹均为 `68e4b5cbbbabb9fd064e2a39a21a2f80f68f5003a48cea5ddd946208d7dbdbbb`。DOCX 语义核验位于 `/tmp/opencode/fundlex-browser-evidence/fresh-artifact-semantics.json` 和 `fresh-selection-semantics.json`：拒绝唯一修订后选择版文本与源文本一致且无修订；working redline 仅含 `FundLex` ID 1/2。

## 阻塞与下一步

1. 按实际 working final/redline 和报告逐项核对 43 个 unresolved，确认每个问题的原文位置、实际差异和业务处置。
2. 实际 Test reset 仍需单独授权；已完成 dry-run，确认只清理 `/var/lib/fundlex-test` 的 Test 子项。实际清空后重新完成登录、上传、Worker、Review 和授权下载 smoke；此前长脚本超时证据由 FL-D254 保留。
3. 保持既有报告的 `delivery_status=incomplete`，直到每个交付 gate 独立关闭；完整交付前不得把 working 文件改称 final。
4. 在部署版本干净、真实路径和 Test reset 后路径均通过后，再作正式交付判断。

当前不能宣称 Test 已完成模型-backed 合同交付、完整 Compare 交付、holdout 评测或 Production 发布。
