# FundLex 生产部署与验收清单（2026-10-29）

本清单用于本轮全面整改候选的受控发布。它不是部署完成声明；每一步都要保存时间、版本、SHA 和实际输出，失败则回滚。

## 1. 候选与前置

- [ ] 工作分支 `codex/comprehensive-remediation-20261028` 已审阅；`git diff --check` 通过，工作树仅允许已知未跟踪合同备份。
- [ ] 完整非浏览器回归（含隔离 MySQL）和浏览器回归通过；记录命令、版本、通过/跳过数。
- [ ] `fundlex`/`frontend`/`tests` 的污染文件、临时日志和 node_modules 不进入发布树；发布器会拒绝 symlink。
- [ ] 真实模型单合同 smoke 已完成，确认新端点、模型、输出上限和超时；失败证据保留。
- [ ] 生产 DB + 对象备份已生成并验证，备份目录 0700、文件 0600；记录 DB/对象 SHA。
- [ ] 记录当前五服务版本、engine build、service build、生产/候选文件差异和回滚目录。

## 2. 维护窗口

- [ ] 通知当前使用者（如适用）；确认没有正在运行的真实任务。
- [ ] 停止 `fundlex-recall-api`、`fundlex-recall-worker`、`fundlex-compare-worker`、`fundlex-guide-worker`、`fundlex-feishu`。
- [ ] 执行 `tools/ops/fundlex_backup.py create --quiesced`；核验备份文件可解压/可读取，不打印凭据。
- [ ] 备份并更新 `/etc/fundlex-recall.env`：新模型 endpoint/model/key 只在受保护文件注入；移除旧 provider header；保留真实余额/鉴权/资源边界，不设置 `FUNDLEX_MODEL_ENFORCE_LIMITS`。
- [ ] 备份 `/usr/local/sbin/fundlex-publish`，安装仓库审阅版；脚本 SHA 和执行权限记录。
- [ ] 用候选源运行发布器 `--dry-run`，核对五服务、迁移、engine/service hash、候选文件清单。
- [ ] 通过 `fundlex-publish --source <candidate> --commit <sha>` 执行；不得手工 `cp` 主工作区混版。
- [ ] 五个服务 active，API capabilities 200；检查启动日志无凭据、无 schema/模型配置错误。
- [ ] 生产 `/api/workspace/tasks` 200，首页任务列表可读取，owner 隔离。

## 3. 真实用户路径

- [ ] 通过正式 V1 浏览器身份注册/登录，打开当前指引。
- [ ] 上传首批真实合同，创建任务，观察 queued/running/completed。
- [ ] 真实 Worker 与模型完成；报告、Claim Replay、查漏状态一致；不存在 local cost/call 暂停。
- [ ] 打开结果页；下载 final/redline/report_json/report_md；未登录 401、跨用户 404。
- [ ] 重读实际 DOCX：接受全部=final、拒绝全部=source、final 无修订、计划与实际一致；独立业务复核正文/摘要/范围外余文。
- [ ] 验证 Review 选择/下载、Compare 多组选择和生成；不把 fixture 当真实。
- [ ] 如适用，验证真实飞书文件/卡片回传、法规生成和暂停恢复。

## 4. 验收结论

- 只有上述实际文件、独立业务复核、生产路径和权限检查全部通过，才可把项目状态改为 GO。
- 未完成/失败/不支持的结构写入集中问题记录，交付工作文件或明确原因；不能用接口 200、任务 completed 或测试通过冒充完整交付。
- 记录生产 URL、候选 commit/tree/build、guide/model、任务/文档/产物 SHA、耗时/调用/费用观测、回滚命令和剩余边界。
