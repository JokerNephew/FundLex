# FundLex 当前断点（ACTIVE_HANDOFF）

## V1 Compare selection 生产受控发布与真实验收（2026-10-26）

- 发布分支：`codex/v1-compare-selection-release`，HEAD `8b3c387`，已推送 `origin`。该分支相对 `origin/refactor/backend-engine-finalization` 的 `c46d6e8` 只增加 Compare selection 相关 14 个文件；未推送原开发分支的其他提交。
- 部署范围：只替换 `/opt/fundlex-recall-first` 的 `fundlex/compare/{__init__.py,api.py,store.py,selection.py,selection_writer.py}` 与 `frontend/compare.{html,js,css}` 共 8 个文件；未调用标准整仓发布器，未同步其他工作区改动。`selection.py` 和 `selection_writer.py` 为新增文件。
- 生产专有修复保留：`api.py` 继续使用 `raise_api_error` 并在上传结束后 `await upload.close()`；`compare.html` 保留设置入口和 OAuth 二维码 UI，同时加入选择面板。候选经生产虚拟环境导入、字节编译、`node --check` 和真实 `create_app()` schema 初始化检查后，才以同目录临时文件加 `mv` 原子替换。
- 备份：`/tmp/opencode/fundlex-compare-selection-production-backup-20261026-200031`，含部署前 6 个现有文件的副本、`production-before-sha256.txt` 和部署后 `production-after-sha256.txt`。部署后 8 个文件 SHA 与候选一致；关键值：`api.py f8b5ba27da5e810e000fc1315dcc3018201407351aa1fae459f9ebe9a8565fc1`、`store.py c8cf5f6ee6ecb7307c65f81b8faa898b52b31d859301af84452fb9d620f8712f`、`selection.py 4edb8fccc57538d8b5d25bcb6a823f53c848f9049f89084c675daf2f86cdbdc3`、`selection_writer.py 88b010ac0fc468d0e56c26a902bfe2949505a58622baf5f4187d00b640048f43`、`compare.html 5acc88e4e5b3cdc49b79108ce8d8e0dcce9735a774a87896e3bd018da686cc93`。
- 服务：2026-10-26 20:01:55/56 只重启 `fundlex-compare-worker.service` 与 `fundlex-recall-api.service`；两者均 `active/running`、`NRestarts=0`，API 监听 127.0.0.1:8010。重启后日志除刻意未认证路由探测的预期 401 外无 error/traceback。
- 线上入口：`GET /` 200 且包含 `compare-selection-generate`；`GET /static/compare.js` 200 且包含 11 处 `compare-selection`；未认证 `GET /api/compare/pairs/<id>/selection` 和 preview 均为 401；`/api/capabilities` 200。
- 真实生产 E2E 证据：`/tmp/opencode/compare-selection-prod-e2e/production/e2e-compare-sel-5m0jgfw1n7zg/result.json` 和同目录下载文件。临时账号 `e2e-compare-sel-5m0jgfw1n7zg` 通过真实注册登录 → V1 Compare → 上传公开合同 `广发科技动力股票型证券投资基金基金合同_20230708.docx` 及单处管理费率 `1.20%→1.00%` 的受控修订版 → seal → 生产 Compare Worker → 1 条 modify / coverage complete → 人工选择右侧 → 刷新后选择仍保留 → 生成 v1 → 下载四项产物。
- E2E 关键结果：任务 `f06b7dcb843240cfa85a944803b4a2e1`、pair `7072777f1c914cf4b97491168c817525`、`generate_http=200`、`generated_status=已生成 v1`。`selected_final` SHA `1bb79a3d2a0e3508fdeffebc8b4329ee02e1ed0186c7445f17c1c76ea51e59a0`、`selected_redline` SHA `5e76e71193fcf84504d1c3593d9a1d7804608e39949210173ae4dd506b71f672`，与报告 `outputs` 完全一致；报告 `checks` 7 项、`limitations=[]`。独立复核：最终版与左侧逐段仅第 763 段变化，采纳修订后的 redline 与最终版逐段一致，两个 DOCX ZIP 完整。
- 安全与布局：未认证下载 401，第二个临时账号下载 404；1440/768/390 三视口 `documentScrollWidth` 等于视口、无横向溢出；页面错误 0、静态/API 404 为 0。唯一 console error 是刻意未认证下载探测产生的 401，不是页面脚本错误。
- 清理：两个临时账号均已清理，主账号删除 1 user/1 session/1 compare task/1 pair/1 selection draft/4 selection artifacts 和 7 个对象；二次查询均返回 `username_present: false`。清理脚本已补 selection 表，详见 FL-D278。
- **限制（重要）**：普通真实合同多数含 header/footer/drawing 等未支持内容，writer 按设计 fail closed，不能生成最终版；本次 514 份公开合同中仅 1 份 coverage complete，生产成功路径使用的是该份合同。该限制登记为 FL-D279，状态为阻塞/待产品决策。整体项目结论继续 **NO-GO**，本次只证明 V1 Compare selection 在完整 coverage 合同上的受控发布和真实交付链路通过，不代表普通合同或完整项目已交付。
- 集中问题：新增 FL-D277（整树复制失败、白名单受控发布）、FL-D278（清理脚本缺少 selection 表）、FL-D279（真实合同 coverage 阻塞）。下一步：补参数化白名单发布器、把清理逻辑迁入仓库工具，并决定普通合同 header/footer 覆盖方案。

## FL-D276 生产真实验收结果（2026-10-26）

- D275 候选全量回归为 **1497 passed / 48 skipped / 2 warnings / 324.62s**；发布前备份为 `/tmp/opencode/fundlex-production-d275-backup-20261026/pre-publish-opt-fundlex-recall-first.tgz`，SHA-256 `85723301d210de32ee95463cbd503ebe4f1cd0bf43417b32fae2b6083a30cdd1`。发布后 API/Worker active，`/api/capabilities` HTTP 200，四个关键运行时文件部署哈希与工作区一致。
- 新真实 V1 普通路径证据 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-o9rfdisxoj2o/`：任务 `6200b8ad71974c10b613622809fa52f5` / 文档 `2adeaefc840b4df68e8be0d060cea16f` 为 `completed/succeeded/complete`，31/31 targets completed、unresolved=0、19 edits、`artifact_claim_replay.verified=true`。final/redline 与报告哈希一致；Review HTTP 200，19 条中拒绝 1 条，`selected_final`/`selected_redline` 均成功生成、下载和 DOCX 校验通过。
- 独立 Compare 任务 `191b14f48e264212abe98de5828bcd29` 已创建、完成、阅读器与 view API HTTP 200，1113 处差异；coverage 为 `incomplete`，警告为 header/footer/AlternateContent/drawing/pict 未支持，证据为同目录 `compare-view.json`。Compare 全文交付门禁失败。
- 临时账号 `e2e-v1-o9rfdisxoj2o` 已精确清理：1 user、1 session、1 task、1 batch、1 document、1 compare task、1 compare pair，关联对象 10 个；数据库复核用户名行数为 0。
- 当前结论：普通 V1 与 FL-D275 修复真实验收通过；整体生产结论继续 **NO-GO**，因为 Compare coverage incomplete，且 D01–D20 固定分母、G06 授权和其他项目级门禁尚未全部通过。

## FL-D275 G15 composite Replay 与 Review manifest 修复（2026-10-26）

- 真实生产报告 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-jeo9hsg813hd/report.json` 已在工作区修复后离线重放通过：19 个计划 edit、`verified=true`、0 个 Claim Replay failure。修复前的两个 G15 composite 首段失败对应 `p806`/`p1262`，尾段 `p807`/`p1263` 的 source-bound 尾随空白边界也已纳入校验。
- Review 的 `REVISION_TEXT_MISMATCH` 已用真实 `working_redline.docx` 重现；将 `validate_edit_plan()` 生成的父级 `expected_old_text`/`expected_old_hash` 写回 report plan 后，正式 selected artifact 生成器成功生成 `/tmp/opencode/selected-repro-after-d275.docx`。
- `fundlex/generation/claim_replay.py` 已增加仅针对 G15 composite 首段的相邻物理段、完整 payment head、source 重算 delay boundary 校验；`fundlex/recall.py` 仅在顺延句后没有可见文本时保留尾随格式空白；`fundlex/recall_pipeline.py` 持久化已验证 parent manifest 原文。新增 composite Replay 和尾随空白回归。
- 当前定向回归为 `97 passed`；`py_compile`、`node --check`、`git diff --check` 通过。完整回归正在执行，尚未计入本断点；本轮代码尚未发布。
- 本轮工作区仍 dirty，HEAD 为 `7cb25d4e27c0cc62408cf92587956fd4150d4d79`，未提交、未 push。下一步：完整回归通过后创建生产备份，发布 `recall.py`、`recall_pipeline.py`、`generation/claim_replay.py` 及相关当前候选，核对部署 hash 和服务状态。
- 发布后必须执行新的真实 V1 普通公开合同路径，完成 Claim Replay、working/final/redline、Review accept/reject、`selected_final`、`selected_redline`、报告/哈希/授权下载；随后独立完成 Compare、覆盖警告、报告下载、404/页面错误和 1440/768/390 三视口检查。任何 incomplete、selected artifact 缺口、D01–D20 或 G06 缺口继续保持 **NO-GO**。

## FL-D270–FL-D274 G15 生产归因修复与 V1 验收脚本修正（2026-10-26）

- 真实 V1 任务 `91ab2940c62844f7a5cd75ca021c7c54` / 文档 `2e8a8c9a2fd64c058d2bc6c4f2cd1401` 曾完成注册、登录、指引加载、任务创建、DOCX 上传、封存、持久 Worker 和 3 次真实模型调用，但因 G15 `p806` 支付头与 `p807` continuation/delay 跨段归因报 `operation_span_mismatch` 而失败；证据保留在 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-yarwc0ihqd68/`。
- `fundlex/recall.py` 已增加限定的 G15 跨段支付头归因：当前目标必须完整占据支付头段，下一段必须通过支付结构与顺延句校验；不放宽其他规则。新增回归覆盖生产 p806/p807 形态和 Claim Replay。G15 定向 `96 passed`，完整 `1493 passed / 48 skipped / 2 warnings`，`py_compile` 与 `git diff --check` 通过。
- `tools/evaluation/production_v1_e2e_20261026.py` 已将原生 `<option>` 等待改为 `state="attached"`，避免结果页因隐藏 option 可见性超时；`/tmp/opencode/cleanup_fundlex_e2e_user.py` 已按 MySQL schema 增加 Feishu Draft 文件、outbox 和安全对象根目录检查。
- 集中记录已新增 FL-D270–FL-D274。G15 修复已受控发布，备份与哈希证据在 `/tmp/opencode/fundlex-production-g15-20261026-022742/`，生产 API/Worker active，候选 `recall.py` 与部署文件 SHA 均为 `9c6fc3ae6705060d161c6bcf35be967c5c4e0132514b3962c42687ccace62b44`。`targeting.py` 的 NameError 修复也已发布，备份与哈希证据在 `/tmp/opencode/fundlex-production-nameerror-20261026-024021/`，API/Worker active。普通验收脚本已增加失败短路并在成功分支关闭详情弹窗，记录 FL-D274；第三次真实普通合同运行仍待终态。当前普通合同和 Compare 均未完成正式验收；后续必须完成报告、working/final/redline、Review、selected artifact、hash、授权下载、Compare reader/report 和三视口检查，再精确清理最新临时账号和全部关联对象。任何 incomplete 或 selected artifact 缺口都保持 NO-GO。
- 当前工作区仍 dirty，HEAD 为 `7cb25d4e27c0cc62408cf92587956fd4150d4d79`；本次未提交、未 push。生产发布前须记录新备份路径、部署 build 和服务状态；发布后所有结论以新真实证据为准。

## FL-D265–FL-D268 飞书接入专项测试与部署模板（2026-10-26）

- 本轮继续完成飞书私聊接入：修正 `feishu_drafts` INSERT 占位符错误；卡片 action 按事件 ID/payload hash 去重并返回实际提交结果；任务提交中途失败时 Draft 保留为 `COLLECTING`，使用原 idempotency key 恢复；解绑后的身份可复用 revoked 行；MySQL outbox 领取增加 `FOR UPDATE` 和 rowcount 检查。
- 新增 [`tests/test_feishu_integration.py`](../tests/test_feishu_integration.py)，覆盖一次性绑定码、解绑重绑、event payload conflict、重复附件、多个 DOCX、提交恢复、卡片重复 action、卡片发送失败后的 durable outbox、outbox fencing 和 chat/owner scope。专项结果：`PYTHONPATH=. .venv/bin/pytest -q tests/test_feishu_integration.py` = **8 passed**；`compileall` 和 `git diff --check` 通过。
- 新增 [`docs/FEISHU_INTEGRATION.md`](FEISHU_INTEGRATION.md) 和 [`tools/deploy/fundlex-feishu.service.template`](../tools/deploy/fundlex-feishu.service.template)，`.env.example` 只增加凭据变量名和公开 base URL 空值。凭据值未写入仓库、文档、测试或日志。
- 集中问题已登记 FL-D265–FL-D269。FL-D265–FL-D267 已在 SQLite/fake client 范围解决并验证；FL-D268 的 MySQL 8 实际并发锁行为、systemd 安装和真实飞书网络仍待验证。FL-D269 记录一次未复现的首次全量 G15 顺序失败。当前没有安装/启用 `fundlex-feishu.service`，没有发布生产，没有真实飞书任务或新增模型调用。
- 当前工作区继续 dirty，包含本轮 Feishu 文件以及既有 Compare/V1/引擎/文档修改；未提交、未 push。下一条动作：运行 Feishu API/入口回归和完整 pytest，若发现新细节先更新集中记录，再按真实 MySQL 条件执行 store 验证；之后才评估服务安装和真实飞书端到端验收。
- 本轮后续验证：Feishu 专项最终为 **8 passed**；API/入口/任务回归 **60 passed / 1 warning**；数据库回归 **2 passed / 6 skipped**（未配置 `FUNDLEX_MYSQL_TEST_URL`）；完整 `PYTHONPATH=. .venv/bin/pytest -q` 最终为 **1493 passed / 48 skipped / 2 warnings / 307.62s**；前端 typecheck、lint、Vitest **9 passed**、build、V1 `node --check` 和 diff check 通过。首次完整运行有一次未复现的 G15 顺序失败，已登记 FL-D269。
- 运维静态检查：模板复制为 `/tmp/opencode/fundlex-feishu.service` 后 `systemd-analyze verify` 通过；`fundlex.integrations.feishu.service_main` 可导入；`lark-oapi` 为 `1.7.5`。本机 shell 和 `/etc/fundlex-recall.env` 均未发现 `FUNDLEX_FEISHU_APP_ID`、`FUNDLEX_FEISHU_APP_SECRET` 或 `FUNDLEX_PUBLIC_BASE_URL` 的有效值，`/etc/systemd/system/fundlex-feishu.service` 不存在，故真实飞书网络 E2E、MySQL 实连和服务安装仍保持未完成。

## FL-D264 V1 默认工作台恢复与隔离测试发布（2026-10-26）

- 用户最新要求为恢复 V1；已将 `fundlex/api.py` 默认前端入口切回 `frontend/compare.html`，保留 Vite/React V2，并通过 `FUNDLEX_FRONTEND_VERSION=v2` 显式启用。V1 `/compare`、`/tasks`、`/tasks/new`、`/guides`、`/settings`、`/users` 深链映射到原 hash 页面；`frontend/compare.html` 标题恢复为合同修订工作台并移除独立 Compare 横幅。
- 为隔离测试路径增加 `FUNDLEX_FRONTEND_BASE_PATH`；测试服务 drop-in `/etc/systemd/system/fundlex-test-api.service.d/frontend-v1.conf` 当前设置 `FUNDLEX_FRONTEND_VERSION=v1`、`FUNDLEX_FRONTEND_BASE_PATH=/test`。V1 `frontend/app.js` 对 API fetch/XHR 使用该前缀，测试环境既有 `api.py` 的 `/test/static`、健康检查和运行隔离改动已保留。
- 本地验证：入口/Compare/修订 API `13 passed / 1 warning`；V1+V2 浏览器回归 `37 passed`；`git diff --check`、`node --check frontend/app.js` 通过。公网证据 `/tmp/opencode/fundlex-v1-public-smoke-20261026/browser-smoke.json`：测试域名 `/test/` 登录、任务总览、新建任务、指引配置、Compare 均通过；1440/768/390px 无横向溢出，静态/API 404 和页面错误为 0。登录前 Compare 的 401 为预期未认证请求。
- 已受控发布至 `/opt/fundlex-test` 并只重启 `fundlex-test-api`；测试 API、普通 Worker、Compare Worker 和生产 API/Worker 均 active。发布前备份为 `/tmp/opencode/fundlex-v1-restore-20261026/test-frontend-before.tgz`。未调用生产发布器、未修改 `/opt/fundlex-recall-first`、未创建合同任务或新增模型调用；临时 smoke 账号、会话和本地凭据文件已清理。
- 当前工作区仍 dirty：`fundlex/api.py`、`frontend/app.js`、`frontend/compare.html`、`tests/browser/test_workbench.py`、`tests/browser/test_frontend_v2.py`、`tests/test_frontend_entry.py`，以及既有 Compare/后端/文档修改。当前 HEAD：`7cb25d4e27c0cc62408cf92587956fd4150d4d79`。尚未 commit/push。
- 当前剩余动作：审核并提交本轮 V1 恢复文件；如需继续部署，先保留测试服务 drop-in 的 `/test` 前缀。普通合同真实 Worker/model/DOCX、D01–D20、G06、selected artifact 仍按 FL-D263、FL-D251 等记录保持未完成，不因 V1 页面验收改变状态。

## FL-D263 后端安全边界修复与当前验证断点（2026-10-25）

- 已实施后端通用修复：operation Registry 覆盖门移至 Guide enable 与 Worker binding；显式 custom operation 未登记时 fail-closed；Claim Replay 拒绝绑定 FALSE/UNKNOWN applicability 的 edit；普通 sibling 同文不再单独关闭 operation，显式 ONE_OF 历史替代保留；audit missed target 保留 operation/obligation/target 身份；Delivery Gate 接入传入 Obligation Ledger 的 open-record 检查。
- 新增回归：FALSE applicability edit、未登记 custom operation enable；Registry legacy identity 兼容边界已修正。错误码归类修复后，完整当前 dirty 工作区回归：`PYTHONPATH=. .venv/bin/pytest -q` = **1481 passed / 48 skipped / 2 warnings / 288.79s**；`.venv/bin/python -m compileall -q fundlex` 与 `git diff --check` 通过。最终验证时间：2026-10-25T18:48:54+08:00。
- 当前精确 Git HEAD 仍为 `4bad293302e77c859bf6036237142fb382dac6e0`，工作区 dirty。除既有 Compare/前端/文档修改外，本轮后端修改文件为 `fundlex/generation/claim_replay.py`、`fundlex/generation/effects.py`、`fundlex/generation/registry.py`、`fundlex/guide.py`、`fundlex/guide_store.py`、`fundlex/jobs.py`、`fundlex/recall_pipeline.py` 及两项测试文件；未部署生产引擎、未新增真实模型调用。
- 本轮后端文件 SHA-256：`guide.py` `52213bf99cc3e6c394c69519b8caf9d6926793169ffb61d790b05a1dfd239a6c`；`guide_store.py` `019fc5c022ecbaf5813dc8ca5ce7da89914c5dbe34ea52bdd46f2a3d922b915a`；`jobs.py` `22fb4e7f690634c28b342ade09423c82ee1838cac922f1cdb0eb45a627c2bcaa`；`claim_replay.py` `44377f84622bdeb481ea3b80bc780c76b37ec86647573cf658560006ac8c32aa`；`effects.py` `f3343b0a4575f5de0c6029c3d6de3d0dcbba57dba36a1cde0d6f2563a6c93946`；`registry.py` `4563c001408915f8dd4b226a8886a69da5f7b65b3cb75872b3af3e1eba2f9004`；`recall_pipeline.py` `38f6ab8f904282a805c0d88afec9f23a74b9643887b15b514ca45b03723f3927`。当前 dirty engine build：`63401714832f88277194e2005bc6a21b5365d30b56e49ee59d91c8f78b028edc`。
- 不能把本轮 dirty 回归计为最终发布证据。下一条依赖动作：审核 Compare dirty 修改边界并形成唯一 clean candidate；随后以最终 HEAD 重新冻结/生成 build 和 artifact hash，运行 Frozen Replay、真实 Worker/model、D01-D20 固定分母、holdout 及普通工作台最终 E2E。当前结论仍为 **NO-GO**：D01-D20 current gate 0/20、G06 业务授权未决、评测预算不足、selected artifact 仍无闭合证据。

## FL-D262 Compare 候选已发布到隔离测试环境（2026-10-25）

- 已将当前工作区候选发布到隔离测试目录 `/opt/fundlex-test`，覆盖 `fundlex/`、`frontend/`、`guides/`、`rules/`、`tools/`、`docs/`、`tests/` 和必要项目文件；未调用生产发布器，未写入 `/opt/fundlex-recall-first`，未修改生产配置或数据库。
- 发布前备份：`/tmp/opencode/fundlex-test-publish-20261025-150535/test-deployment-before.tgz`。发布证据和哈希文件位于同目录，包括 `after-sha256.txt`、`source-deployed-hash-check.txt`、`browser-smoke.json`、`before-sha256.txt` 和 `before-size.txt`。
- 已重启并核验 `fundlex-test-api.service`、`fundlex-test-worker.service`、`fundlex-test-compare-worker.service`，三项均为 `active`；测试 API 监听 `127.0.0.1:8110`。测试 API `/api/capabilities` 未登录返回 200；密码模式下 `/api/health` 与 `/api/auth/me` 未登录返回预期 401，不能把未认证健康接口 401 误判为服务故障。
 - 工作区与测试部署的 Compare Python 文件及当前入口静态资源 SHA-256 一致：`models.py` `13b36e48669eabd303ee2ef192f886692c81c5757f74fe120ace64be9be5370c`、`parser.py` `e49be4a2aa5d42777336752290db3cee74693927232d9159ce1666b1bd20429b`、`presentation.py` `3ced9d82bf6bfdd0e2e6597dc853aaa7a2b92341a9722749da9cb8d155f9c6fa`、`render.py` `f69d553587e08aedbc7d63f7e6982e2be354694e6aa4fbf96f37c32a9d1a9614`、`index.html` `131e6c718b3732b77431cb53b3ea6357a5657f1dafb8baac1d3a8ed53864f932`、JS `597d4cee45f13670e3f888d0ba2bdc609709b8870665b6704570f34dd48cf1d8`、CSS `3891a1846348a419486ffeb581476bad8c8c273f7b75eb21f3e7e896ae9c4cae`。
- 资源与页面验收通过：`/`、当前 HTML 引用的 JS/CSS 均 HTTP 200；真实测试账号登录后访问 `/compare`，390px 和 1440px 视口均无横向溢出，标题和“新建对比任务”入口可见，页面错误、控制台错误、静态 404、API 404 均为 0。证据：`/tmp/opencode/fundlex-test-publish-20261025-150535/browser-smoke.json`。
- 浏览器验收使用的临时 `compare-test-*` 账号及其会话已删除，数据库复核残留数为 0。未创建 Compare 任务，未新增模型调用。测试目录保留旧 Vite 哈希静态文件是增量同步的结果，首页只引用当前构建的 `index-GU2uu_zT.js` 和 `index-BSExzTi5.css`。
- 生产隔离复核通过：生产 API/Worker 仍 active，生产 8010 仍监听；生产 Compare renderer 文件时间和 PID 未因本次测试发布变化。本条只证明隔离测试环境发布与页面入口验收，不替代真实测试合同的 Worker/model/DOCX 交付验收。

## Frontend visual remediation checkpoint (2026-10-25, published and publicly verified)

## FL-D260 Compare reader implementation checkpoint (2026-10-26, local only)

- 已实施未发布：`frontend/src/pages/Compare/ComparePage.tsx` 将文档区与差异导航拆为桌面右侧独立 rail；rail 自身滚动，正文左右 pane 保持独立滚动。差异点击通过 `data-diff-id` 和目标相对 pane 坐标更新 `scrollTop`，不再使用 `scrollIntoView()`；移动端在目标仅存在另一侧时自动切换，双栏滚动加入锁避免递归联动。
- 已实施未发布：`frontend/src/styles/app.css` 调整 Compare 正文字号至 15px，增加中文合同字体、段落段后距、标题层级、列表、表格、页边距和 1440/768/390 布局；`fundlex/compare/presentation.py`、`fundlex/compare/parser.py`、`fundlex/compare/models.py`、`fundlex/compare/render.py` 现在解析并投影 DOCX 段落缩进/对齐/间距/页边距、编号、run 粗体/斜体/下划线/删除线/字号/颜色/字体/上下标，并保持差异坐标不变。当前能力仍是 Word-like 连续阅读投影，不代表完整 Word 分页还原。
- 验证：前端 `npm run typecheck`、`npm run lint`、`npm run test -- --run`（4 files / 9 passed）、`npm run build` 和 `git diff --check` 通过；`PYTHONPATH=. .venv/bin/pytest -q tests/test_compare*.py` 为 73 passed、5 skipped、1 个现有 Starlette/httpx deprecation warning；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/pytest -q tests/browser/test_frontend_v2.py` 为 8 passed，包含长文 pane 内定位、目标进入可视区、外层 `window.scrollY` 保持不变和移动端单侧差异自动切换夹具。
- 当前工作区：未提交文件为 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`、`docs/ACTIVE_HANDOFF.md`、`frontend/src/pages/Compare/ComparePage.tsx`、`frontend/src/styles/app.css`、`fundlex/compare/models.py`、`fundlex/compare/parser.py`、`fundlex/compare/presentation.py`、`fundlex/compare/render.py`、`tests/browser/test_frontend_v2.py` 和 `tests/test_compare_render.py`；生产静态资源仍为上一轮 `b78dc4a`/`4bad293` 发布版本，未发布本轮改动。
- 下一动作：保留本轮本地证据，继续补充真实 renderer 视觉截图和复杂表格/页眉页脚覆盖判断后，再进行受控发布决定；真实公网 Compare 新任务尚未创建，未新增模型调用。

- 本轮针对 FL-D252–FL-D256 的源码修复已提交为 `b78dc4a59e0b8be4c5c3c7b4979484e7a6a50a5a`，推送到 `origin/refactor/backend-engine-finalization`，并已完成前端静态资源受控发布。涉及文件：`frontend/src/components/layout/AppShell.tsx`、`frontend/src/pages/Compare/ComparePage.tsx`、`frontend/src/pages/DocumentDetail/DocumentDetailPage.tsx`、`frontend/src/pages/Guides/index.tsx`、`frontend/src/pages/Settings/index.tsx`、`frontend/src/styles/app.css` 和 `frontend/tests/components.test.tsx`；既有其他工作区改动未回退。
- 已实施：浅色顶栏消息/退出按钮可见性、统计卡相邻 margin 隔离、Compare 三种后端差异 class 解析、差异类型颜色、覆盖警告逐项列表和长标识断行、Compare 任务表移动端宽度隔离、帮助弹窗 Tab/Shift+Tab 焦点循环、Escape 关闭与焦点恢复、背景 `inert`、合同例外稳定短 ID/规则/位置/诊断来源/证据展示、设置能力值中文映射和指引上传中文文件控件。
- 候选构建已发布：`frontend/dist` 与 `/opt/fundlex-recall-first/frontend/dist` 的资产 SHA-256 一致：`index.html`=`8a1cb7f50066dca6450d4a77c080ca71a99caddaafb8818891993bf9cacca0c9`、`assets/index-DgSYi7V7.js`=`a64f599ba6e405767e680f829c37a9db4e2e567bcc9611846787f7945d580091`、`assets/index-CbzfypI-.css`=`4673c786f89d28f968725458e839088edf1d7026011964d0342f157339f22353`。生产备份为 `/tmp/opencode/fundlex-frontend-publish-20261025-121730/deployment-dist-before.tgz`，发布证据为 `/tmp/opencode/fundlex-frontend-publish-20261025-121730/deployment-evidence.json`。
- 验证已完成：`npm test -- --reporter=dot` 为 4 个文件/9 项通过；`npm run typecheck`、`npm run lint`（零 warning）、`npm run build`、`git diff --check` 通过；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` 为 8 项通过。浏览器回归覆盖真实 renderer 的 `modify/insert/delete` 形态、三类差异颜色、Compare 覆盖警告、帮助弹窗焦点循环和背景 inert。
- 三视口本地视觉证据在 `/tmp/opencode/fundlex-ui-fix-visual-20261025/`：`visual-data.json` 记录 1440、768、390px 的 document/body 宽度分别等于 viewport；覆盖警告在 390px 容器宽 320px、内容 `scrollWidth` 318px；差异 computed background 分别为修改 `rgb(255, 240, 182)`、新增 `rgb(217, 241, 223)`、删除 `rgb(247, 216, 216)`；帮助弹窗 Shift+Tab 到“知道了”、Tab 回到关闭按钮、Escape 后恢复“帮助中心”焦点。截图包括 `compare-{desktop,tablet,mobile}.png` 与 `help-{desktop,tablet,mobile}.png`。
- 公网验证已完成：`/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261025/result.json` 通过真实登录、消息、帮助、`/tasks`、`/tasks/new`、`/guides`、`/settings`，1440/768/390 三视口无横向溢出，页面错误、控制台错误、静态/API 404 均为 0。针对性证据 `/tmp/opencode/fundlex-public-frontend-fix-20261025/result.json` 确认白色顶栏按钮为品牌深色，设置能力值和指引上传中文控件生效，帮助 Shift+Tab/Tab、背景 inert、Escape 后焦点恢复均通过。当前公网账号没有 Compare 任务，因此没有为本轮新建任务或新增模型调用。
- 当前边界：D252 的指引可用版本长文件名尚未在公网已有数据上单独复核；D254 的事项是否应业务归并仍需产品/报告数据契约决定；屏幕阅读器合规和 Compare 超长差异清单性能建议尚未验收。普通合同 D01–D20、G15 和选择版产物问题继续按 FL-D240–FL-D243 阻断。
- 下一条可执行动作：保留本次发布备份和公网证据；如需验证 Compare 本轮类型颜色，使用既有生产 Compare 真实链路证据或在获得明确测试预算后创建新任务，不在本轮追加模型调用。

## Frontend V2 continuation checkpoint (2026-10-25, post-publish real acceptance)

- The current React V2 candidate was published as a frontend-only release at 2026-10-25 07:43 CST. Production backup: `/tmp/opencode/fundlex-frontend-publish-20261025-074321/deployment-dist-before.tgz`; byte evidence: `/tmp/opencode/fundlex-frontend-publish-20261025-074321/deployment-evidence.json`. Candidate and production SHA-256 match for `index.html` (`1a61614146d2c0d37e45e92876ab2d5f97b2641ace883a68b15118bd658c1518`), `assets/index-DYLFV7Bw.js` (`172d6479b38f5c5ae3c505df94a81922e52d0ce4847c84a0ea457d8749bbcacd`) and `assets/index-BdkF_0-u.css` (`15ce316f6e92f992cb8712da29093aab08cbf76cc811d23f986f18f00fcbe5ea`). API was restarted; Recall Worker PID stayed `3107909`, and API/Recall Worker/Compare Worker were active after publication.
- Real production React Compare acceptance completed through HTTPS login → DOCX upload → seal → persistent Compare Worker → result viewer → report download. Evidence: `/tmp/opencode/compare-production-react-v2-e2e-20261025/report.json` and the downloaded report in the same directory. The result contained 2,772 differences (451 modify / 1,238 insert / 1,083 delete), status `incomplete` with explicit unsupported header/footer/drawing coverage warnings, 390px left/right pane switching, next-difference navigation and a 3,189,696-byte report download whose SHA-256 is `0f39d4d3655d773722dccaade57d9518fd2ed8f609d6ebf632f7433e85643bbc`; page and console errors were zero.
- A real ordinary contract acceptance also completed against the published frontend and persistent production Worker/model. The current run is task `8e3767e727344ecbbebc76ee95ad2b20`, document `2acd8583cea340fca1da964914ab39aa`; task status is `completed`, job status `succeeded`, but delivery remains `incomplete` with 6 unresolved G15 verification items. It used 27 model HTTP attempts and estimated `$0.02525925`; `working_final` SHA is `d823a5c6a8a9d3eb4c85b66530513121b9525644429ec277f699a16b9a0b2e7d` and `working_redline` SHA is `3e7fb5f140fab1d1dfd4aed007bc98e90146f8e609abb5fbbd675e898b0b8e99`, both matching report hashes. The DOCX packages were valid and changed from the source; Review exposed 19 revisions and no page/API 404s. A follow-up task `add3f5e6d5f049eeb305c1e4a1ce81d9` / document `186228a5c3d645f188083f87f2095e26` also reached Review with 19 revisions, but its selection generation did not show `已生成选择版合同` within 60 seconds and produced no selected download. Selected-artifact availability remains unverified; evidence is `/tmp/opencode/fundlex-production-v2-e2e-selected-20261025/e2e-3lopn3fjl7yl/result.json`.

- React Compare parity review added previous/next pair navigation to `frontend/src/pages/Compare/ComparePage.tsx`; first/last pair buttons are disabled and switching resets the mobile reader to the original side. AppShell help-dialog close no longer performs duplicate focus restoration; the close handler remains the single restoration path.
- Browser evidence now includes the 390px Review flow and fixture-backed Compare result view. `FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q`: **8 passed**. The Compare case verifies two result pairs, diff markup, mobile side switching, pair navigation, viewport bounds, page errors and console errors.
- Serial frontend checks pass: `npm test -- --reporter=dot` (**4 files / 9 passed**), `npm run typecheck`, `npm run lint`, `npm run build`; Compare API/Auth/Worker focused tests **17 passed**; `git diff --check` passes. The first Compare browser attempt had an async rendering wait race and was corrected to wait for the visible pair-navigation button before the final 8-test run; recorded as FL-D248 and not treated as a product failure.
- The published frontend is now the current candidate. The isolated browser Compare result and focused tests remain regression evidence only; the real Compare Worker/DOCX evidence above is production acceptance evidence for this release. Ordinary D01–D20 and final ordinary-user delivery remain blocked under FL-D240–FL-D243.
- Next executable action: on a future authorized real run, capture the selection mutation HTTP status/error body and, after a successful response, poll and download `selected_final`; preserve the explicit G15 incomplete state and do not change the fixed D01–D20 gate.

## Production visual audit checkpoint (2026-10-25)

- Completed a screenshot-first audit of `https://fundlex.club` using Playwright Chromium with the temporary Chinese font configuration `/tmp/fundlex-ui-fontconfig/fonts.conf`. Captured 43 current production screenshots at 1440×900, 768×1024 and 390×844 covering login/register, tasks, new task, guides, settings, task/document detail, notifications/help, Review and Compare. Audit data and screenshots are under `/tmp/opencode/fundlex-visual-audit-20261025/`; existing E2E sessions were scoped for the run and revoked afterward; no model calls were made.
- Interaction evidence recorded 14 primary checks plus read-only follow-up DOM checks with zero page errors and zero console errors. Confirmed Review pending generation guard, bulk decision persistence after reload, mobile tabs/back navigation, Compare difference navigation, mobile side switching, empty upload validation and paired-pane scroll behavior. The help dialog closes on Escape and restores focus, but Shift+Tab moves focus outside the dialog; this is recorded as FL-D253.
- Visual findings are recorded as FL-D252–FL-D256: invisible topbar actions, mobile information density and statistics-card spacing (FL-D252), missing dialog focus trap (FL-D253), visually duplicated/unexplained exception rows with report-level source now verified (FL-D254), long unsupported-content identifiers in the 390px Compare warning (FL-D255), and Compare difference types losing their class and falling back to one yellow mark color because the frontend parser expects `compare-diff-*` while the real renderer emits `compare-diff modify/insert/delete` (FL-D256). These are audit findings only; no application code was changed or deployed in this audit.
- The audit uses the current published frontend and preserves the existing incomplete contract/Compare states. It does not establish accessibility compliance, fix the findings, or change the ordinary D01–D20 delivery gate.

## 当前源码候选快照断点（2026-10-25）

### 2026-10-25 G05/G16/G21 边界修复续接点

- 本轮在工作区继续完成三类 operation/site 生命周期修复：G05 absent coverage 仅按自身 operation 计入；G05:0 替换在旧文和新文均缺失时保持未证明，G05:2 仅在同一份额类别设置业务站点形成独立 absent proof；G16 duplicate-copy 先 clause-end rebinding，再按物理 clause 末端判断是否可复制；G21 适用 noop 的 satisfied target 从可审计/可编辑目标退出，同时保留 operation coverage，G22 同段 operation 独立继续。
- 新增回归覆盖实际 DOCX 形态：D19 p130 的 G05:0/G05:2、D20 p804-p806 与 p1259 的 G16 站点边界、G21/G22 同段审计生命周期。定向回归 **141 passed**；完整 `PYTHONPATH=/home/opencode/fundlex .venv/bin/pytest -q` 为 **1476 passed / 48 skipped / 2 warnings / 296.41s**。`compileall` 与 `git diff --check` 通过。
- 证据和问题登记：FL-D257、FL-D258、FL-D259 已追加到 [`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`](DETAIL_ISSUES_AND_RESOLUTIONS.md)。历史 D19/D20 report、DOCX、Replay、labels、gold、scorer 和评测账本均未改写。
- 本轮修复仍只存在于 dirty 工作区，未重新冻结、未发布、未重启生产服务、未新增真实模型请求；snapshot-20 build `06ef07cc...` 仍不包含本轮修复。D01-D20 当前固定分母 gate 仍为 0/20，G06 未授权语义和评测预算缺口仍按 FL-D240–FL-D243 阻断。
- 下一条：在预算与发布条件满足后，先以包含本轮修复的新候选受控冻结/发布，再真实复测受影响 D19/D20；逐 operation 核对 source site、实际 DOCX、Claim Replay、audit、报告、修订接受/拒绝等价和授权下载。不能把本轮零 HTTP/回归证据计为新的真实 Worker/model 交付。

- FL-D246 已修复并验证：`project_unresolved()` 对无 operation/site 身份的运行级 coverage 缺口保留原 `kind="coverage"`；有身份但无法绑定的证据仍转换为 `orphan_evidence` 并 fail closed。三项直接回归 **3 passed**，定向后端回归 **286 passed**，完整 `tests` 两次均通过：**1467 passed / 47 skipped / 2 warnings**，分别为 289.47s 和 284.79s。
- 当前精确候选已冻结于 `/tmp/opencode/operation-validation-20261024/snapshot-20`，build `06ef07cc443a61ebb50009d7e8ce8c0280d08d70d0190d350e8d92a02f78f75b`；178 个 `fundlex/` 与 `tests/` Python 源文件的启动 manifest 与测试后哈希一致。启动 manifest 为 `/tmp/opencode/operation-validation-20261024/current-candidate-full-test-start.json`，结果为 `/tmp/opencode/operation-validation-20261024/current-candidate-full-test-result.json`，上下文为 `/tmp/opencode/operation-validation-20261024/run_context-20.json`。
- snapshot-20 是**未发布候选**：工作区 `fundlex/api.py` SHA `c0459fd16573a2d2084be900156dc10ae8df65414eda298046f5935df04b0c98`、`fundlex/tasks.py` SHA `028e858c0706d15392c4eba5ec33dd3ade438fde00ecd44889d6105587bb546b`；生产目录对应 SHA 为 `8cdd1507fcccacf2b1ec596a4bfdf69daf623e35ea75bca2ba8c000c85416191`、`3e7162fdbcee2daa8bb0e45506f71d41f20990cc9350aae2ed6b1882b7de6063`。未部署、未重启服务、未新增模型调用。
- snapshot-20 冻结时共享 ledger 为 **1701 requests / `$1.64408310` / reserved 0**；当前仍有 299 requests / `$0.35591690`，但不足以按固定分母完成剩余开发集的估算需求。20 份开发集、holdout、正式发布和最终普通工作台 E2E 继续按 FL-D240–FL-D243 阻断。
- 当前下一条：若取得新增预算及发布授权，先对候选 API/tasks 做受控发布并核对生产字节，再按 snapshot-20 固定源码执行 D01–D20 真实登录→上传→seal→持久 Worker/model→DOCX→Review→授权下载和独立业务复核；未取得前不启动无法完成固定分母的真实批次。

## 当前 target-20 对账断点（2026-10-25）

- target-20 D06 已完成真实登录→上传→seal→持久 Worker/model→结果页→授权下载；snapshot-19 build `e2ac0f14429de4fdd71e631d10c18b27f1366c8337e797b4c834b5adf6611229`，82 targets 已处理，delivery 为 `incomplete`。机械下载核验 1/1 通过；final SHA `7503c5e61cf1602240b9c3843d5e7ebd7c9b29029d969b2e04485fcd97a5e7bd`，redline SHA `01de404f1fdc36c1a74e1a8fb0d3eb6b00613ffd4463b178e4f8e70bda2fedeb`。
- target-20 D06 的 corrected 独立业务复核 `/tmp/opencode/operation-validation-20261024/target-20-D06-independent-business-review-corrected.json` 已通过 25/25 断言，19/19 实际变化段通过。初始误报证据保留在 `/tmp/opencode/operation-validation-20261024/target-20-D06-independent-business-review.json`，对应 FL-D239；未修改真实 report、artifact 或历史失败文件。
- G02/G04 p98、p131、p231 的 operation/site coverage 均为 `ALREADY_SATISFIED`；G11 p228 为 `ALREADY_SATISFIED`、p229 为 `ARTIFACT_VERIFIED`。G12/G13、G15/G16/G17、G22 和 sweep findings 已由实际 DOCX、operation ledger 与 Claim Replay 逐项复核。G06 仍因 p280 的单向 Y 类转换语义变体保持 `CLAIM_OPERATION_UNPROVEN` / `semantic_delete_variant_present`，delivery gate `UNRESOLVED=1`、blocking_unresolved=2。
- 共享 ledger 当前为 **1701 requests / `$1.64408310` / reserved 0**，按状态 completed=1698、failed=2、abandoned=1，剩余 **299 requests / `$0.35591690`**。target-19 D04 的最近独立通过证据属于 snapshot-18，target-20 D06 属于 snapshot-19；其余开发集主要证据来自更早快照，尚未形成同一冻结版本的 20 合同 gate。按 FL-D240 保持 holdout、正式引擎发布和最终普通工作台 E2E 阻断；不得因目标计数 `unresolved=0` 或 mechanical pass 宣称交付完整。
- 当前下一条：在不新增预算授权前，不再启动无法完成固定分母的随机真实批次；先保存本断点和集中问题记录，若预算获授权则冻结新的、与 snapshot-19 一致的开发复测批次，按固定 20 合同分母继续真实运行并逐合同独立业务复核。
- 当前服务只读核验：`fundlex-recall-api.service` 与 `fundlex-recall-worker.service` 均为 active；生产 API 由 systemd 配置监听 `127.0.0.1:8010`，`GET /api/capabilities` 返回 200。当前 8013 由独立 `fundlex-test-api.service`（工作目录 `/opt/fundlex-test`）提供隔离测试服务响应，不能作为生产 API 证据；生产健康和真实验收仍以 8010/公网入口为准。该端口细节登记 FL-D243。
- D01-D20 固定分母对账已保存于 [`docs/evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md`](evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md) 和同目录 JSON；当前 snapshot-19 gate eligible 为 **0/20**。已有 snapshot-19 证据仅 D06，D04 独立通过是 snapshot-18；历史 snapshot-05 复核中 D02、D16、D17 通过，D18 失败，其余 15 份仍 pending。保留 D06 并补跑其余 19 份的历史消耗基线为约 602 requests / `$0.60031875`，相对当前余量缺口约 303 requests / `$0.24440185`，不含重试和 G06 修复调用；对应 FL-D241/FL-D242。

## 最新引擎验证断点（2026-10-25）

- FL-D237/FL-D238 已实施：G02/G04 完整收费组中的旧单类成员不再被 residual 门禁误判；p98 同段类别枚举 sweep 只有在同一段完整收费组 operation proof 通过时才可由 artifact proof 消解。新增回归与最终全量均已通过：**1459 passed / 47 skipped / 2 warnings / 291.27s**，`git diff --check` 通过。
- snapshot-19 已冻结于 `/tmp/opencode/operation-validation-20261024/snapshot-19`，build `e2ac0f14429de4fdd71e631d10c18b27f1366c8337e797b4c834b5adf6611229`，测试 manifest 为 `g02-g04-postpatch-full-test-start.json`，178 个 Python 源文件一致。已受控发布到 `/opt/fundlex-recall-first`，API/Worker active；工作区、snapshot-19 和部署目录的 `api.py`、`tasks.py`、`effects.py`、`recall_pipeline.py` 字节一致。

- FL-D231–FL-D234 修复后的最终源码回归已通过：**1458 passed / 47 skipped / 2 warnings / 288.47s**；`git diff --check` 通过。当前修复版 snapshot-18 已冻结于 `/tmp/opencode/operation-validation-20261024/snapshot-18`，build `e42254705a296954284d7fd3831543c38db1894ec1966bf3d7462cf85be3c39a`，上下文 `run_context-18.json`，源码 manifest 与最终回归启动 manifest 一致。
- snapshot-18 冻结时评测 ledger 为 1621 requests / `$1.54847790` / reserved 0；target-19 已完成 D04/D06 真实任务，使用独立 `data-19`，不复用 target-18。D04 complete，D06 incomplete；当前总账以本文件顶部 target-20 对账断点为准。
- snapshot-18 已通过受控发布同步到 `/opt/fundlex-recall-first`，API 与 Worker 均 active；工作区与部署目录 `fundlex/api.py`、`fundlex/tasks.py` SHA 一致，`/api/health` 返回 200。`/api/capabilities` 未认证请求返回 404，属于当前身份门禁行为；尚未以此接口结论替代登录验收。
- D04/D06 当前源码零模型真实原件重建已通过：`/tmp/opencode/operation-validation-20261024/offline-d231-d234-real-current/result.json`；D04 G12:1/G13:0 原子 component、D06 G11 p229 窄 continuation、Claim Replay、接受/拒绝修订等价均通过。该证据不替代 target-19 真实 Worker/model 交付。
- target-18 历史真实产物、报告和失败 Replay 保持不变；holdout、正式发布结论和最终普通工作台 E2E 仍受 20 份开发集完整业务门禁阻断。
- target-19 已完成：后台 shell `sh_16ead959c001MZSAUWU9cVPMyW` 使用 snapshot-18、独立 `data-19` 和共享 ledger，真实 D04/D06 登录→上传→seal→持久 Worker/model→结果页/Review→授权下载路径均已核验。D04 complete；D06 incomplete，报告和历史产物保持不变。
- target-20 已完成：使用 snapshot-19、独立 `data-20` 和共享 ledger，仅 D06；真实链路、机械核验、账本、Claim Replay/audit、p98 sweep、G02/G04/G06 逐站点实际差异及接受/拒绝修订/hash 均已核对。G06 单向 Y 类转换没有业务授权，继续保持未完成。

- 前端最终候选已完成受控公网发布并通过复验：只同步 `frontend/dist/index.html`、`index-BkJEWrna.js`、`index-ko73k-L5.css` 到 `/opt/fundlex-recall-first/frontend/dist`，只重启 `fundlex-recall-api.service`，Recall Worker 保持运行。工作区、部署目录和公网引用的 SHA-256 分别为 `6019229d8c9df8bd3e9e8b55fbfe4a4f8f0a46201fbc612088acbd4418c4b5c2`、`bc87d8701dc0bfaaaca00c121528942975253ac77a83c46a3b26fa03cf709ae3`、`a7f472e4b4dd426cb4cd2f8e91ca656a6d4528dd333930783274e08dcfc7167a`。备份为 `/tmp/opencode/fundlex-frontend-publish-20261024-180136-responsive-fix/deployment-dist-before.tgz`。
- 最终公网 smoke `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json` 已通过：真实登录、消息、帮助、`/tasks`、`/tasks/new`、`/guides`、`/settings`、1440/768/390 响应式、原地 1440→768 收缩、页面/控制台错误和静态/API 404 均通过或为0。该 smoke 只证明当前前端壳层与现有 API 可用，仍不能替代下面的真实合同模型交付验收。

- FL-D227全量已结束，结果为 **1 failed / 1451 passed / 46 skipped / 2 warnings / 288.10s**；源码manifest匹配，唯一失败是`tests/test_append_applicability.py`的FakeParagraph缺少真实段落结构字段。已补齐替身并登记FL-D228。
- FL-D228全量已启动，日志`/tmp/opencode/operation-validation-20261024/d228-full-pytest.log`，启动manifest`d228-full-test-start.json`，build为当前源码build。该运行启动后又完成G12边界收窄和新增回归，因此无论结果如何都必须按最终源码/测试manifest重跑完整回归。
- D228中间结果已结束：**1452 passed/46 skipped/2 warnings/284.20s**；启动manifest与当前源码不一致（启动后收窄G12边界并追加测试），不能冻结。最终manifest重跑已进入下一步。
- FL-D228增量定向回归通过：G12/Claim/append相关62 passed；真实D04 p198零模型流程`/tmp/opencode/operation-validation-20261024/offline-d228-g12-real/result.json`通过，G12固定政策写入、G13 7日/1.5%句保留、Claim与接受/拒绝修订等价均通过；D227 G03/G16真实D04零模型结果`offline-d227-real/result.json`通过。无HTTP。
- 当前源码仍未冻结、未运行新的真实任务。target-17历史产物保持不变；holdout、引擎发布和最终普通工作台E2E继续阻断。D228结束后下一步：记录结果→按最终manifest重跑全量→冻结新snapshot并核验API/tasks与生产字节一致→重新登记预算后真实复测D04/D06。
- 最终manifest重跑已通过：**1453 passed/46 skipped/2 warnings/280.23s**；177个Python源文件manifest与启动时一致，build `e4ae767880625a3cf090fd500283facd28caab2f696e96c35551ab74b65dc172`。已冻结`/tmp/opencode/operation-validation-20261024/snapshot-17`，上下文`run_context-17.json`；冻结时API/tasks与生产一致。
- target-18已预登记：D04/D06开发集真实普通工作台路径，预计80 HTTP/$0.08、最坏200/$0.24，账本起点1552/$1.47498705/reserved0，剩余448/$0.52501295。发布新快照后才启动；target-17不得复用，holdout/正式发布/最终普通工作台E2E继续阻断。
- 生产账本只读核对为26919 requests/`$21.81123075`（completed26874、failed32、abandoned13），与本轮隔离ledger不同；target-18沿既有评测协议使用`/tmp/opencode/operation-validation-20261024/ledger.sqlite`，不混算、不重置。
- FL-D229：首次target-18启动参数误传为`run dev target-18 D04 D06`，包装器在`p6_run`参数解析阶段退出，未创建任务、未登录、未上传、未调用Worker/model；shell `sh_16d542a77001GWC6jvid0LtxXr`，ledger仍1552/$1.47498705/reserved0，target-18目录不存在。下一步使用正确接口`dev target-18 D04 D06`重新启动。
- FL-D230：生产普通工作台验收脚本曾错误要求登录页品牌具有 heading 角色；React V2 登录页实际使用品牌 `<strong>`，该失败发生在注册前，不能作为产品或模型链路失败。已登记并从独立输出目录重新执行生产真实合同验收，等待新任务结果。

## 最新前端发布与公网验收（2026-10-24）

- **最新用户硬性要求**：允许在原版基础上做细节优化，但绝对不能丢失原版任何功能。React V2 后续必须先完成原版功能/入口/品牌资源/响应式基线矩阵，逐项证明等价可达；优化不得删除、隐藏、改成绕路入口或降低原版能力。矩阵未完成、任一硬性功能缺失或多视口不可用时，不得进入下一阶段或发布。

- 按用户“发布”要求完成 React V2 **前端静态文件受控发布**。标准整仓发布器未使用，避免将未完成的 recall-first 引擎、评测、测试和文档 dirty 改动同步到生产；仅更新 `/opt/fundlex-recall-first/frontend/dist/index.html` 和当前 Vite hashed assets，并只重启 `fundlex-recall-api.service`，Recall Worker 未重启。
- 最终备份：`/tmp/opencode/fundlex-frontend-publish-20261024-180136-responsive-fix/deployment-dist-before.tgz`。最终工作区、部署目录和公网入口引用一致：`index.html` SHA `6019229d8c9df8bd3e9e8b55fbfe4a4f8f0a46201fbc612088acbd4418c4b5c2`，`index-BkJEWrna.js` SHA `bc87d8701dc0bfaaaca00c121528942975253ac77a83c46a3b26fa03cf709ae3`，`index-ko73k-L5.css` SHA `a7f472e4b4dd426cb4cd2f8e91ca656a6d4528dd333930783274e08dcfc7167a`。
- 公网浏览器 smoke `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json` 已通过：真实登录、`/tasks`、`/tasks/new`、`/guides`、`/settings`、消息面板、帮助中心；1440px、768px、390px以及1440→768原地缩放均无页面横向溢出；`page_errors=[]`、`console_errors=[]`、静态 404 和 API 404 均为 0。公网入口和新 JS/CSS 均 HTTP 200，API 服务 active，Worker 保持 active。
- Smoke 首次发现移动端 V2 侧栏导航使页面宽度扩展至 664px；已通过窄屏纵向 shell 布局和侧栏横向滚动容器修复，重新执行 typecheck、lint、build、diff check 与公网 smoke 后通过。截图保留在 `/tmp/opencode/fundlex-public-v2-smoke-20261024/tasks-wide.png`、`new-task-mobile.png`。
- 本次仅证明前端页面与现有生产 API 的公网可用性；没有创建新的生产任务、没有新增模型调用，也不改变 recall-first 引擎发布门槛。Recall-first engine 仍受 dev-05 真实合同业务缺陷、开发集复测和 holdout 条件约束。

## 当前接续断点（2026-10-24，operation Registry/Router 当前版本）

- **正在运行，勿重复提交（2026-10-24）**：target-17 D04/D06已通过后台shell `sh_16d2e31ec001l5FWpDOa8gSz01`启动，冻结snapshot-16、独立data-17、共享ledger；等待完成通知，不轮询。日志`target-17-api.log`、`target-17-worker.log`及shell输出。下面“下一条启动”已执行，不得再跑。当前源码只在`fundlex/recall.py`和`tests/test_composite_slice_delivery.py`增加本轮G17窄parts修复，其他dirty属于既有工作；全量及冻结哈希相同。后续先`PYTHONPATH=/home/opencode/fundlex .venv/bin/python tools/evaluation/verify_downloaded_artifacts.py /tmp/opencode/operation-validation-20261024/target-17 --selection var/recall-first-evaluation/p6-current/selection.json`，再`replay_saved_case.py target-17 D04 d225planning`和D06同样（最后轮audit限制仍在），另建跨段G17业务复核与全部diff，独立账本增量对账。预算尚以run前1490/$1.40885745为基线，不把运行中值当最终。没有子agent；保留target-16旧失败和首次错误业务输出、冻结labels/scorer不改。上下文已分阶段持久保存；若压缩后先读本条、集中FL-D225/188、run_context-16再继续，勿重做真实调用或把离线通过当正式交付。总体20dev/holdout/发布/最终E2E尚未完成。
- **最新可执行动作**：G17规划修复完整回归1436 passed/46 skipped/2 warnings/278.05s，177源文件manifest匹配；已冻结snapshot-16/build `2858706c841ff88b1a75e394e1d4f225d0d6c8bcfa2ebfcb0b68252af7922889`、`run_context-16.json`，API/tasks与生产相同。另建target-17 D04/D06/data-17预算已登记：预计80 HTTP/$0.08、最坏200/$0.24，起点1490/$1.40885745/reserved0，总cap2000/$2不变。下一条启动命令`FUNDLEX_VALIDATION_SNAPSHOT=/tmp/opencode/operation-validation-20261024/snapshot-16 FUNDLEX_VALIDATION_DATA_DIR=/tmp/opencode/operation-validation-20261024/data-17 .venv/bin/python /tmp/opencode/fundlex-operation-validation.py dev target-17 D04 D06`；不要prepare/复用target-16。完成后机械下载核验、全计划Claim/audit、逐站点业务与全部diff；旧review_target16_g17.py已修正跨段及D06口径但输出固定target-16，更正版不会覆盖首次错误证据。D04 G12/G16、D06 G15及其他未决仍待独立处理；20dev完整独立分母/D07/单类别认证尚未完成。无holdout/发布、无子agent、未commit/push，工作区dirty保留。新快照不是整项目验收。
- **最新target-16终态，优先于下方历史**：D04/D06真实任务及下载结束，均incomplete（58/33、91/37 targets/unresolved），机械2/2；完整Claim false/8、false/9。G17宽survey composite被独立范围门禁拒绝，D04首副本DEL001窄删/余文保留但第二副本漏，D06两用途句漏删；排除句已合法删。已实施源operation窄parts恢复：D04/D06真实原件零模型规划各自Claim、余文保留、接受/拒绝修订等价通过，4/6 edits，证据`offline-d225-planning-real/result.json`；定向相关130 passed。下一步等待完整回归通知，核对源码manifest后冻结新snapshot，再登记预算并启动真实D04/D06复测；不放松Replay。临时业务脚本跨段漏检与D06旧排除口径已更正并保留首次输出；FL-D132/188确认ETF联接应正常修改。账本1490 requests/$1.40885745/reserved0，target-16增量67/$0.07048830（17/$0.01738935已对账为最终报告未保留的前轮请求），余510/$0.59114255，总cap2000/$2。无运行中的真实任务/子agent；未发布引擎/无holdout。分支feat/frontend-v2、HEAD fc8424aaae46e46d209ec7aa3834502136f692f8，所有已有dirty保留，无commit/push。
- **target-15 D03已完成真实交付**：真实登录→上传→seal→持久Worker/模型→结果页/授权下载完成，complete/35 targets/0 unresolved，34 HTTP/$0.02907375。机械核验1/1，final `66efdc0c6ceab948cd51a8745fc4236e275b7c7cb7a589cdadcd7afc401c8d2b`、redline `302c9805930dbc3460e51a0c2670ad989899fad85db516879ae09559e5a1dc91`，20 ins/20 del；Claim true/0 failures，audit replay 29/0/0，target-15实际diff 20/20 PASS。证据`target-15/D03/artifact-review.json`、`target-15/D03/target-15-business-diff-review.json`、`target-15-D03-d225-final-replay.json`。账本1423 HTTP/$1.33836915/reserved0，剩余577/$0.66163085。D03单合同已完成，20dev独立完整分母仍pending；下一步应登记新的D04/D06真实窄范围复测预算，验证G17 planner自动恢复独立用途句且保留D04费用支出/D06降费权限余文，再继续D07/D09/D13和完整dev审核。holdout、引擎发布、普通用户最终E2E仍被开发门槛阻断。
- **target-16 D04/D06 已登记并即将启动**：snapshot-15/data-16，预计80 HTTP/$0.06，最坏200/$0.24；预算余量足够。两份任务必须走真实登录、上传、seal、持久Worker/模型、结果页和授权下载，再逐文件核对G17窄范围、D04费用实际支出余文、D06下调/打折权限余文、报告/Claim/audit/修订/hash。run前账本1423/$1.33836915/reserved0；仍无holdout、无生产发布，D03单合同成功不能替代20dev门槛。
- **当前待通知与可直接执行动作**：唯一仍运行进程为D225最终完整tests后台`sh_16cfb1c5b0017gAN9i7cM35Ay7`，不是模型；20dev最终离线Replay已结束。最终target-14实际+旧audit重放`target-14-D03-d225-final-replay.json`为verified=true/0 failures、29 results/0 issues/0 artifact failures。启动manifest与源码再次核对相同，API/tasks字节仍等于生产，账本1389 HTTP/$1.30929540/reserved0，snapshot-15/data-15/target-15均不存在。等待通知后读`d225-final-full-pytest.log`保存结果、核对`d225-final-full-test-start.json`，通过才运行`.venv/bin/python /tmp/opencode/operation-validation-20261024/freeze_snapshot_15.py`；重验run_context-15.json文件manifest、预算及build，再`FUNDLEX_VALIDATION_SNAPSHOT=/tmp/opencode/operation-validation-20261024/snapshot-15 FUNDLEX_VALIDATION_DATA_DIR=/tmp/opencode/operation-validation-20261024/data-15 .venv/bin/python /tmp/opencode/fundlex-operation-validation.py dev target-15 D03`。勿调用prepare，不发布引擎、不跑holdout。结束后`review_target15.py`实际文件核验和`replay_saved_case.py target-15 D03 d225`（两者需PYTHONPATH=/home/opencode/fundlex）。review_target15.py仅同原件+同实际文本的target-14已审核段可复用结论，其余REVIEW_REQUIRED必须逐项读原件/指引；独立完整目标分母仍pending。branch feat/frontend-v2，HEAD fc8424aaae46e46d209ec7aa3834502136f692f8，所有并行dirty保留，尚未commit/push。无子agent。D03真实预算沿用40 HTTP/$0.04预估、100/$0.12最坏，余611/$0.69070460。下一阶段应完成D04/D06真实窄范围恢复、D07费用证书、D09/D13单类别认证和20dev独立分母/完整业务审核，达门槛才留出/发布/普通用户最终E2E。上下文已分阶段保存；不要因本轮工具通知把目标替换为单纯报告测试结果。
- **等待最终全量期间新增证据**：最终20dev只读重放已结束，D02/D11/D19合法G17措辞过拒消除；D04/D06独立余文损失、D18重复prefix保持失败。D04/D06原件窄切片DOCX重建`offline-d225-real-source-slices-verified/result.json`两份proof/余文保留/仅目标改变/接受拒绝修订等价全部通过，0 HTTP；仍非新真实任务。最终全量继续等待`sh_16cfb1c5b0017gAN9i7cM35Ay7`通知；源码未在测试期间修改，freeze/run按下一条。target-15后还要真实D04/D06验证规划召回能恢复窄边界，不以拒绝替代完整修改。临时重建脚本首次source绑定失败目录保留，已通过正式build_docx_edits修正。
- **D225最终增量全量运行中（优先于以下历史）**：首轮1428 passed/46 skipped/2 warnings/271.62s，manifest匹配，结果d225-full-test-result.json。随后已补有限措辞等价（佣金连接词/持有人简称/省略使用范围/分号），226项定向通过，反向语义和独立余文仍拒绝。最新全量后台`sh_16cfb1c5b0017gAN9i7cM35Ay7`，日志`d225-final-full-pytest.log`、manifest`d225-final-full-test-start.json`，build `4bbe0bd82928f338d4cdc87b786ca4dd39ced54aeea8bcdc2d9639c35709de00`；历史20dev只读重放后台`sh_16cfb1c5c001Pj0A1KHfwDu9XN`→`dev-05-d225-final-replay.{json,log}`。等待通知，勿轮询/改源码。通过后保存结果/核对manifest→freeze_snapshot_15.py（已绑定最终日志）→重验manifest/API/tasks/账本→真实target-15 D03（现snapshot-15/data-15/target-15均不存在），预计40 HTTP/$0.04、最坏100/$0.12，账本1389/$1.30929540、reserved0/cap2000/$2。实际下载后执行`PYTHONPATH=/home/opencode/fundlex .venv/bin/python /tmp/opencode/operation-validation-20261024/review_target15.py`（会机械校验并与target-14逐段相同原文/实际文本的已审核diff比对，未相同项保持REVIEW_REQUIRED），再全计划Claim与audit核验。此脚本及最终重放脚本在/tmp不参与引擎全量源码manifest。其余开发集独立完整分母、D07及单类别认证仍未完成，生产未发布本轮引擎/无holdout。
- **D225全量等待期间发现合法措辞过拒，暂停直接freeze**：20份dev-05只读Replay已结束（`dev-05-d225-replay.{json,log}`），D04独立费用支出句/D06独立降费权限句越界删除被阻断；D02佣金“，及”、D11/D19“持有人服务费”、D11省略“使用范围”需支持有限同义差异。等当前D225全量通知，保存当前结果/source manifest，再补合法差异与反例并重跑全量；不要立刻按下条freeze/run。target-14审核旧回答重放29 results/0 issues/0 artifact failures（`target-14-d225-audit-replay.json`）；0 HTTP。当前源码未在全量中修改。
- **FL-D225修复后全量运行中（优先于以下历史）**：G17单段/composite planner与Claim Replay均从原件及自身operation完整句独立核验删除范围，跨段parts/expected_old_text等不能自授权；合法G16/G17合并保留。新增伪造provenance/parts、反向语义与实际跨段DOCX反例，229项定向通过；target-14只读完整Replay true/0 failures，`target-14-d225-source-scope-replay.json`。当前全量后台`sh_16cf55000001QvBoY3mtjs1yoV`、日志`d225-full-pytest.log`、manifest`d225-full-test-start.json`、build `27721a2f381b3fbcfbac37236f1058d1a3bcc004d6a613bfb95ca7181468742c`。勿轮询/改源码；完成后保存统计/核对manifest→freeze_snapshot_15.py（已改绑定D225）→核验账本/API/tasks→另建真实D03 target-15→实际diff/修订/hash/audit。D224最终全量1420 passed/46 skipped/2 warnings/271.52s，源manifest匹配，结果`d224-final-full-test-result.json`，该全量不含D225。账本仍1389 HTTP/$1.30929540、reserved0、cap2000/$2；新真实D03预计40/$0.04、最坏100/$0.12，未发布引擎、无holdout、无子agent/真实Worker。其余20份开发集审核/收费认证未完成，branch/HEAD与并行dirty保持。
- **最新发现FL-D225，暂停原snapshot-15启动动作**：零HTTP探测G17整段删除+伪造expected_old_text/deleted_paragraph可吞掉独立无关句，Replay错误true。target-14无该余文，不应把对抗样例当作其实际错误。当前FL-D224最终全量继续等待通知、勿改源码；结束后需先补G17独立源授权（自身完整用途/排除句及合法跨段parts）和反例，再重新全量/manifest，不能按下面旧下一动作立刻freeze/run。集中记录已登记FL-D225未修复。
- **FL-D224最终全量重跑（优先于下一条）**：首轮完整回归1 failed/1417 passed/46 skipped，失败为合法自定义单句G15支付变体被过拒；新增单句source-bound支持与额外第二句/顺延不授权反例，相关233 passed。当前最终全量后台`sh_16cec1cb6001SVz0DMNrQuXjPC`、日志`d224-final-full-pytest.log`、启动manifest`d224-final-full-test-start.json`，build `9ed657267458d3fdd18a700a682576f7e5ec359e7535059799905648e01d6813`。不要轮询或修改源码；通过后运行`/tmp/opencode/operation-validation-20261024/freeze_snapshot_15.py`（强制源码哈希与该最终全量一致），重验manifest/账本→`FUNDLEX_VALIDATION_SNAPSHOT=.../snapshot-15 FUNDLEX_VALIDATION_DATA_DIR=.../data-15 .venv/bin/python /tmp/opencode/fundlex-operation-validation.py dev target-15 D03`另建真实复测。已预登记D03预计40 HTTP/$0.04、最坏100/$0.12，共享cap2000/$2。实际target-14全部20变化段复核已落`target-14-d224-business-diff-review.json`，为预测后开发审核；独立完整分母未完成。其余预算/无holdout/不发布约束不变。
- **FL-D224最新断点，优先于下列历史**：merged effect绕过FAIL unit已移除；G15 planner/Replay从operation独立重算删除范围；143项定向通过。audit接受BEFORE-only丢失引文，但经本地独立授权证明的合法G17删除仍可闭合，新增实际DOCX G16/G17合并与丢失核对句反例，124项相关通过。target-14只读完整Replay及既有audit重放均0 failures/issues，证据`target-14-d224-source-scope-replay.json`、`target-14-d224-audit-replay.json`；0新增HTTP，不代表新真实任务或独立业务审核。当前完整`tests`后台`sh_16ce5d301001xtf0RCLtCjneLJ`运行中，日志`d224-full-pytest.log`、启动manifest`d224-full-test-start.json`，build `d7dc3484d26e637a37d44cec07e492b5c94872845a928f677698fea022bc9683`；勿轮询或改源码混入该测试版本。通过后先核验源码哈希/预算，再冻结snapshot-15并另建真实D03及受影响G15样本。共享账本1389 HTTP/$1.30929540、reserved0、cap2000/$2；无真实Worker/子agent、无holdout、未发布引擎、所有并行dirty保留。branch/HEAD为feat/frontend-v2/fc8424a。FL-D208单类别、D07收费补证及全20份独立分母/实际DOCX审核仍待完成。
- **当前接续，优先于下列历史**：target-14已真实结束，snapshot-14 build `0f4fd6e2f3f701d1209900b4cc712470a108650f4694b6e0e2db37eb36d61117`，33 HTTP/$0.02573610、报告complete/34 targets/0 unresolved，机械1/1；共享账本1389 HTTP/$1.30929540，无reserved。接续重新读指引73/75–89段，纠正“p753/p1221必须保留使用范围句”误判：G17明确授权删除该句，G16可以与该独立删除合并，不能按错误审核恢复旧文。FL-D224登记审核误读及effect的planned_matches绕过FAIL unit缺口；下一动作是收紧merged effect证明并补实际DOCX正反例、完整target-14重放。当前无新真实批次/子agent、未发布引擎、无holdout，所有并行dirty保留；分支/HEAD仍feat/frontend-v2/fc8424a。此轮尚未改代码、尚未新增HTTP；不得把纠正审核等同全20份开发集通过。
- **最新snapshot-12/target-12（优先于下列历史）**：最终引擎全量 **1404 passed /44 skipped /2 warnings /286.21s**。冻结首次因唯一变化`tests/browser/test_frontend_v2.py`停在复制前；补验修正新增Compare测试漏点侧栏（FL-D219），显式Chromium **5 passed /10.90s**。`freeze12-supplement-evidence.json`记录精确差异及日志哈希，原1404全量证据保留，其余fundlex/tests文件集合及哈希未变。snapshot-12已冻结，build `d441ec1706668bcdcafb0fcf7cfef9798d5879bb3a22871c1f9e84963c1fb16b`，2418文件manifest重验、API/tasks与生产一致。真实`target-12` D03已启动，独立`data-12`，日志`target-12.log`，后台shell `sh_16ca07d6c001B2H2c12uth4Xap`；等待通知，勿轮询/重复提交。预算起点1267 HTTP/$1.19796015，无reserved，cap2000/$2/并发1、每合同192保持，预计33–40 HTTP/$0.03。完成后机械核验、p92 raw130插入/55号原文、p209无重复/p211编号、全部diff、G15/G16/G17及修订/report/hash核验。未发布引擎、无holdout、无子agent，保留全部并行dirty。
- **target-12 D03终态更新**：真实任务已完成但`incomplete`，42 targets/39 unresolved，52 HTTP/$0.05397930；共享ledger为1319 HTTP/$1.25193945、无reserved。下载机械核验1/1通过：final SHA `c593ea2a3b6cdefabed2ec8a031743abba0475ee61380c324286cb7fb592e7b3`、redline SHA `496b8ad8af0c75bde59d9c15b27dd3e8d2a744d683cf066bdd07287cca4e136b`，接受/拒绝修订、无残留修订和plan一致。实际业务复核相对target-11新增p92/p121/p209/p211/p752/p753/p925/p1221/p1318，target-11的G01 raw130/55号原文仍被验证；但新模型结果删除G16内容、回退G05语义、G22未完成，不能沿用旧审核通过。G16定向检查14/16，p751/p1219的完整政策计数失败。FL-D220已登记：D12 G09部分splice/Replay错误PASS；FL-D221已登记：D03收费引文认证部分仍UNKNOWN。局部G09/收费回归当前100 passed；源码已继续变更，snapshot-12不能作为修复后快照，未发布/无holdout。
- **FL-D220/221修复后回归**：`template.plan_g09_splice()`和G09 Replay现在要求净值与“扣除或加上相应的费用”两个完整效果，并支持`并扣除其他相应的费用`变体；`fee_evidence`支持“申购费用由投资人承担”和“的年费率计提”。定向156 passed；完整`tests`回归后台`sh_16caffd59001essR5lR6mEcfYO`，日志`post-d220-d221-full-pytest.log`，完成通知前勿重复运行。通过后需重新计算build/源码manifest、冻结新快照并另建真实D03；target-12仍是修复前真实证据。
- **FL-D222修复后回归**：同一G16费用条款若G16没有可执行计划，`guard_g17_deletes_against_g16()`会撤回G17删除并将其记为unresolved，避免删除应追加内容的源段；合法G16+G17合并与阻断反例受影响回归184 passed。完整`tests`回归后台`sh_16cba2c780012UvdfT6JwxpV8z`，日志`post-d222-full-pytest.log`，完成通知前勿重复运行。通过后重新冻结、再做真实D03；target-12仍保留为修复前证据。
- **target-13 D03终态**：snapshot-13真实Worker/模型、登录/上传/持久任务/授权下载已完成，`incomplete`，40 targets/52 unresolved，37 HTTP、$0.03161985；共享ledger现为1356 HTTP/$1.28355930，无reserved。下载机械核验1/1通过，final SHA `5810c37e6d3922ad0779682938782653637b068a0ed06dd4a324d28d49b1a06c`、redline SHA `214ea725352452d9df99b393e3d841066229f62f9970c32d735ed2d33083b3ea`。实际改变12段：G09 p210完整效果通过，G01/G03、G05、G06、G12/G13、G14、G15、G18实际修改与plan一致；收费A类引文仍省略原件p211“4、”，严格门禁保持UNKNOWN，G08/G11/G22未交付。FL-D222阻断真实生效：p752/p753、p1220/p1221的G17未单独删除，原文保留并标为`G17_BLOCKED_G16_UNPLANNED`/`CLAIM_OPERATION_NOT_PLANNED`，避免target-12错误半成品。target-13不是完整D03或开发集通过。
- **FL-D221来源驱动引文修复（当前未冻结）**：`facts_from_value()`新增窄范围source-bound修复，仅当模型引文以“本基金”开头、原件同一收费条款存在编号前缀、修复片段独立证明预期极性时补回原件完整引文；其他情况继续UNKNOWN/CONFLICT。新增编号收费条款DOCX回归，定向147 passed；受影响/完整回归待运行。target-13不能代表该修复，必须重新冻结并启动新真实批次。
- **最新动作已完成**：FL-D216完整回归 **1363 passed /44 skipped /2 warnings /261.77s**；snapshot-10 `target-10`真实D18 complete/0，33 HTTP/$0.02434395，机械1/1、定向14/14，仅p776/p1227相对target-08删除旧顺延句。final SHA `8ac72b7c83314f4b62230a2bfef4171f7a4f2d2d5def95c666472cb8fe34861b`，redline SHA `788c9f1fba9c0fa02446b08b1735d65518cc958f1330f7b17f92092b83633e7b`。FL-D216真实样本验证解决。共享账本1234 HTTP/$1.17396345，无reserved，剩余766/$0.82603655；未发布引擎、无holdout。下文“回归运行中/快照待冻结”为历史。
- **FL-D217真实复测进行中**：G08同句边界修复完整回归 **1370 passed /44 skipped /2 warnings /258.22s**（`g08-same-sentence-full-pytest.log`）。`snapshot-11`已冻结并重验manifest，build `92880a778ab4607b713cd26da56e8e061c9283e0d26021dfd121ad81298bdd5a`，API/tasks与生产一致，账本起点1234 HTTP/$1.17396345、无reserved，隔离`data-11`。真实`target-11` D03已启动（`target-11.log`、后台shell `sh_16c873a1a0012gDhh3Sv0vxp6J`）；结束后必须核对p209同义重复消失、p211“4、”保留、全部实际差异、报告/修订/授权下载哈希。未发布、无holdout。
- **target-11终态（覆盖上一条运行中）**：D03 complete/0，33 HTTP/$0.02399670，机械1/1、定向15/16。FL-D217 p209同义重复已真实修复，p211编号保持；新增FL-D218 p92 G01错误追加在同段下一“55、发起式基金”之后，不能判D03整合同通过。相对target-09仅p92/p209两处不同。累计1267 HTTP/$1.19796015、无reserved，余733/$0.80203985，不重复启动target-11。
- **FL-D218正在离线验证**：已实现`_definition_next_entry_start()`原件raw边界及Replay错误插入位置阻断；162项相关回归、compileall/diff check通过。真实旧target-11重放现G01 `CLAIM_OPERATION_SPAN_UNAUTHORIZED`，`offline-d03-merged-definition/`零模型重建仅在p92 raw130插入，下一定义原样、其他段落原样、接受/拒绝修订等价。完整回归后台`sh_16c8c95e6001anpIpG7qqz3rIh`，日志`merged-definition-audit-full-pytest.log`；等通知，勿轮询。该工作区同时含D07审核适用政策输入与audit_v3提示修复（UNKNOWN/CONFLICT不生成READY），尚未真实验证；D07收费事实认证仍未修复。
- **最新全量与事实入口（覆盖上一条）**：G01/audit版本已1396 passed/44 skipped/2 warnings/283.59s；随后`facts_from_value()`新增逐类申购/服务费quote极性核验与`fee_polarities`，缺失证据收费组UNKNOWN、反向证据CONFLICT，不改变原始布尔值。17项事实/恢复回归通过，当前完整回归后台`sh_16c91c85c001ZMbww6vst82T8Q`、日志`fee-evidence-current-full-pytest.log`，勿轮询/重启。20份旧回答原件重认证`fee-facts-current-recertification.json`确认D07/D10/D14/D16旧VERIFIED降UNKNOWN，这四份补证恢复尚未完成。待当前全量通过→`freeze_snapshot_12.py`→重验manifest/预算→真实target-12 D03→全部实际差异/G01/G08/编号/修订/hash审核。无真实批次运行，账本仍1267/$1.19796015，未发布/无holdout。
- **最终候选当前断点（优先于以上历史）**：收费入口初版1400 passed/44 skipped/2 warnings/270.15s；现支持每类独立`subscription_quote/service_quote`逐字证据（FACTS v5、恢复v2）、认申购缩写，157项相关回归通过；真实D10/D14/D16零模型补证可恢复VERIFIED（`fee-separate-positive-offline.json`），D07无服务费仍UNKNOWN。最终全量后台`sh_16c96ea870018j6h1FKOSs1igu`，日志`fee-separate-final-full-pytest.log`，启动源码哈希`fee-separate-final-test-start.json`/build `d441ec1706668bcdcafb0fcf7cfef9798d5879bb3a22871c1f9e84963c1fb16b`。**不要继续改源码混入测试版本**；等通知→读统计→运行freeze_snapshot_12.py（会强制源码哈希一致）→重验manifest/账本→target-12 D03真实复测。原target-11全部20处diff审核19通过、p92失败，证据`business-diff-review.json`。当前无真实Worker，账本1267/$1.19796015、剩733/$0.80203985。所有源码/前端/compare/外围dirty保留，未commit/push/发布，无子agent、无holdout；分支feat/frontend-v2，HEAD fc8424aaae46e46d209ec7aa3834502136f692f8。
- **最新真实终态，优先于下文历史**：target-08四份全部结束，140 HTTP/$0.12862980，机械4/4；D03 complete但编号丢失15/16（FL-D215），D05 complete且定向18/18，D07 incomplete/18 unresolved且修正辅助检查后33/33（不能替代业务完整审核），D18错误complete且12/14（FL-D216两处跨段顺延残留）。target-09 D03已完成，33 HTTP/$0.02420940，机械1/1、定向16/16，FL-D215该真实样本验证解决。D03相对target-08只变p209/p211，前者需细看语义差异，后者编号保留。target-09 final SHA `d04285613f9095a8b882daa92982d80a978fc5db04b1015252170595479ea226`。截至该轮账本1201 HTTP/$1.14961950，无reserved，剩余799/$0.85038050；无真实批次运行，不重复启动target-09。
- **FL-D216正在修复验证**：`recall.py`共用`_g15_delay_continuation()`，为已绑定G15支付head补紧邻完整顺延首句target；effect closure不依赖tail target也要求该site，Replay从原件独立重算授权与raw边界。新`tests/test_g15_cross_paragraph_delay.py`及相关82项通过；compileall/diff check通过。真实target-08 D18旧文件Replay现false，两tail FAIL；`offline-d18-cross-delay/`零模型局部重建只改p775/p1226 head及p776/p1227各0–33首句，G17用途/全部其他段落保留，修订等价通过。完整回归后台`sh_16c7b5248001q6uBCmnNuKAQuo`，日志`g15-cross-paragraph-full-pytest.log`，等完成通知，勿轮询/重复启动。待通过后冻结snapshot-10并另建target-10真实D18复测（脚本`freeze_snapshot_10.py`已备）。生产未发布、无子agent、所有前端/compare/其他dirty保留；branch/HEAD仍feat/frontend-v2/fc8424a。
- **后续未做**：D07收费facts引用管理费不能认证申购收费、audit适用组件口径仍待修；FL-D208单类别正面认证、FL-D209其余dev、全20份独立目标分母和完整实际文件审核待完成；达开发门槛才holdout、发布和最终普通工作台真实交付。不要把局部复测通过写成整项目完成。先完成FL-D216新真实任务闭环，再按这些缺口继续。
- **新发现FL-D217**：target-09 D03 p209比target-08多保留旧“本基金C类基金份额不收取申购费，”前缀，G08完整新政策再次声明C类免申购费，造成同义重复；编号FL-D215已解决不等于D03完整业务无缺陷。证据`target-09/D03/compared-to-target08.json`，待修G08源边界/重复，再新真实复测。snapshot-10已冻结（尚未启动真实），build `c3f8c6442b2b2880c82746e8b94e38e84127602da94053d5866d1b040f4638e8`，manifest `run_context-10.json`；先等当前完整回归通知，通过且manifest一致才启动target-10 D18。
- FL-D217定位证据：target-08 G08 p209 quote覆盖raw36–86（完整C类不收费＋A类费率同一句），target-09仅raw54–86（A类费率），二者均clean template，导致后一轮保留raw36–54旧C类前缀。应仅按自身完整政策覆盖的同句收费事实收敛边界，并让Replay检测相同来源政策重复，不盲吞相邻计算余文。尚未实施。

- **当前真实测试（覆盖下文旧下一动作）**：用户已再次授权真实测试、根据测试结果优化并继续真实复测；冻结`snapshot-08` build `a829181de8e965b8c6f64f7d37dcd2e1e7ff5134230a258a584ea2ee59c8652b`，manifest `run_context-08.json`。引擎与1343项完整回归工作区字节一致，API/tasks与生产一致，未发布。`target-08` dev D03/D05/D07/D18 已启动，隔离`data-08`、API8013、真实Worker/模型/授权下载；D03/D05已完成complete（D03 33 HTTP/$0.02439705，D05 费用报告$0.03210180），D07/D18仍运行，日志`/tmp/opencode/operation-validation-20261024/target-08.log`。预算起点1028 HTTP/$0.99678030，共享cap2000/$2/并发1；结果后立即做实际DOCX业务和机械复核，发现缺陷登记并优化，优化后继续新真实run，不能停在离线。D03已发现FL-D215编号吞掉，修复已通过55项定向回归，target-08保留修复前失败证据；无holdout、无子agent，生产前端发布与其他dirty改动保留。
- **FL-D215真实复测已冻结待启动**：修复版`snapshot-09` build `997329195f5699afd246bdb6ff5cca4fa28f5beaee440433e864e77c4f03d861`，manifest `run_context-09.json`，隔离`data-09`，仅真实复测D03；冻结时共享账本1137 HTTP/$1.108932，剩余863 HTTP/$0.891068。须等待`target-08` D07/D18终态后启动，避免两个隔离Worker争用共享并发；target-08旧D03失败证据保留。

- **最新终态（覆盖下文运行中历史信息）**：dev-05 D01–D20 已全部结束，不要重启或等待；D02/D16/D17报告complete，其余17份incomplete。真实634 HTTP / $0.63333525，共享ledger累计916 HTTP / $0.89509440，上限2000/$2不变。下载机械20/20通过，旧P6为214/236（90.68%，kept14/not_executed8），score SHA `5de8689c9d751c4b74e38f97ec2eeb1e7226599ee0128f052b2d9673d3f87afd`；旧口径存在已知限制，不能作为业务通过率。
- **最新修复与证据（覆盖下文历史）**：FL-D205已修完整引用标点定位和旧政策子句残留；dev-05实际产物0 HTTP离线重读，D17 G12 p207明确阻断，D02/D16状态保持。FL-D207跨段类别定义追加、FL-D210 composite切片外余文重复、FL-D211定义后净值公式追加及FL-D200异常计量修复已实施；相关82项Worker/管线/DOCX回归通过。完整离线回归 **1289 passed /44 skipped /2 warnings /242.46s**（`slice-formula-full-pytest.log`），该回归收集发生在新增FL-D200两项测试之前；FL-D200另外有上述组合验证。
- **2026-10-24最新工作区增量**：D07边界完整回归1308通过；后续G09 replay重算证明完整回归 **1317 passed /44 skipped /2 warnings /238.34s**（`g09-proof-full-pytest.log`）。真实target-07 D07原件/旧`working_final.docx`在`offline-d07-g09-proof-current/`重放：G09 PASS，整合同仍false。G15早先survey/parts试改已撤回；本次采用新的raw地址窄修复，仅补紧邻明确顺延句，D03真实原件p751/p1219均0–133删除，其他段落原样、Claim verified=true、接受/拒绝redline分别等于final/原件，证据`offline-d03-g15-raw-current/`。FL-D213把现有整段确定性删除移到compose预算检查之前，零模型/不扣compose名额；新测试`test_g15_payment_delay_boundary.py`及相关 **170 passed**。D05核对句授权仍OPEN，尚无新真实模型任务、未发布。
- **冻结候选为历史snapshot-07，不能代表当前工作区**：`/tmp/opencode/operation-validation-20261024/snapshot-07`，build `ac51034291840615ab22ee62c2453e2bc26cd456d51e0e9f550af4e3b2d001ad`，manifest `run_context-07.json`。它缺少最新G16/D07/G09/G15修复及新增测试；需重新显式冻结，保留当前API/tasks和其他并行外围，不复用旧快照冒充新构建。
- **target-07终态（覆盖上文预登记）**：四份已结束，禁止重复启动。D07 incomplete/40 unresolved，D11/D17/D18报告complete/0；112 HTTP/$0.10168590，累计1028 HTTP/$0.99678030，剩余972 HTTP/$1.00321970。机械4/4通过，D17旧比例句、D11公式末追加、D18顺延句局部复核符合预期；但D18在p775/p777及p1226/p1228重复完整G16且错误complete，FL-D192重新打开。证据`target-07/artifact-reviews.json`、`target-07-review-packets/`。
- 当前下一动作（2026-10-24更新）：D03/FL-D213旧全量为**1325 passed /44 skipped /2 warnings /240.20s**；随后D05 G15收窄/`bounded_delete`及G17 site closure已通过68项定向回归，D05实际重建`offline-d05-g17-site-closure/`四个G17 sites全部通过、两处核对句保留、修订等价通过。当前工作区最新完整回归为**1343 passed /44 skipped /2 warnings /245.29s**，日志`g17-closure-full-pytest.log`。FL-D214旧错误PASS已保留为失败证据，离线修复已验证，尚未真实Worker/模型复测。继续FL-D206授权审查、FL-D208单类别正面认证及FL-D209其余dev缺陷，再完成20份独立目标分母/实际DOCX业务审核。未达开发集门槛不跑holdout、不发布。无后台真实批次、无子agent，所有并行dirty内容保留；共享账本1028 HTTP/$0.99678030，总cap2000/$2，剩余972 HTTP/$1.00321970，本次全部离线。
- 目标：完成当前未提交 operation-level Registry/Router、Policy Components、canonical obligation、Claim Replay、coverage、Delivery Gate patch 的 build identity 冻结、真实合同评测、受控生产发布及当前版本工作台真实端到端交付验收。
- 用户/项目约束：不得整仓库 add/reset/覆盖并行前端、compare、evidence、运维改动；真实模型、实际 DOCX、报告和下载哈希必须核验；历史 FL-D175 证据不能证明当前版本；问题必须登记本文件与 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`；凭据只允许从受保护环境读取，不写入仓库、文档、日志或命令输出。
- 环境：hostname `iZf8zemhifedxdow1zefr0Z`，内网 `172.28.217.241`，工作区 `/home/opencode/fundlex`，Python `.venv/bin/python`。当前分支 `feat/frontend-v2`，HEAD `fc8424a`。系统 `python3` 为3.6，所有项目命令必须使用 `.venv/bin/python`。
- 工作区：引擎相关修改仍未提交；并行 dirty/untracked 文件同时存在。除此前引擎文件，本轮新增 `recall_prompts.py` audit v2、`tools/evaluation/{p6_run,verify_downloaded_artifacts}.py` 与相关测试。API/tasks/前端属于并行工作，保留其最新生产版本，不整仓库覆盖。
- 已完成：operation identity 已贯穿 Registry、Router、planner/replan/residual、targeting、obligation、coverage、Claim Replay、Delivery；UNKNOWN/CONFLICT、缺失显式 Registry、重复/缺失 occurrence 和兄弟 operation 借权均 fail-closed；G08/G11/G14/G16 policy component 规则已接入。定向回归 **142 passed / 1 warning**；完整离线回归 `.venv/bin/python -m pytest tests -q` **1249 passed / 43 skipped / 2 warnings / 235.11s**；`git diff --check` 通过。
- 当前版本评测冻结：`var/recall-first-evaluation/p6-current/selection.json` 为20 dev + 8 holdout，原件 manifest/hash 已校验；labels SHA `f120d38175c83cd1c973045d0414a69bacb9d837fc4bf24d40a8a762fe588841`。原标签347目标、26可改/2排除仅为旧标注器输出，存在ETF联接 D02/D06错排及单规则单目标限制（**FL-D188**，原误编号FL-D186与favicon冲突已消歧），不能作为完整业务真值。原gold/scorer不改；holdout新预测未读。
- 冻结快照：`/tmp/opencode/operation-validation-20261024/snapshot` build `41de9fcb36fe028457255cbb282ccc3e02ea3ef478f520dd6ef2b14e30fd3d97`，全量 **1216 passed / 65 skipped / 2 warnings /156.97s**。pilot-01 D01/D02 真实模型62次/$0.0646734，均 incomplete；下载机械检查2/2通过，旧scorer13/14目标通过（D02被旧标签错误排除，不能宣传92.86%为完整口径）。失败文件保留。
- 缺陷修复：FL-D189 G09 clean自动选template但只有splice实现，改为仅允许SPLICE，unsafe继续阻断；FL-D190 audit指令引用FACTS却未传账本，补完整facts.as_ledger、计入context cap并升级audit v2。新增routed planner→真实DOCX回归及audit调用上下文回归，相关 **106 passed /7.47s**。
- 当前新冻结：`snapshot-02` build `1a34319a91df99e389fbd403d419f09d21ae010db078244acd66bcaa48732cb9`，`run_context-02.json`记录源码hash/范围；继承原快照、只加上述两修复与最新生产API/tasks（保留React V2外围）。并行前端已发布生产，现build `dbfc3951b3e2ac46430a32086b1ade538950fb570bf93bce33f6c62f23cc84b2`，与snapshot-01仅API/tasks不同；本agent未发布新修复，后续先隔离评测，达发布条件才部署。
- 共享预算：`/tmp/opencode/operation-validation-20261024/ledger.sqlite`，本轮所有尝试共用，2000 HTTP/$2/并发1/每合同192调用上限；不得重置。harness只从受保护生产环境读模型配置到内存；隔离数据`data/`、API8013；结束自动终止隔离API/Worker。
- 最新结果：snapshot-02全量 **1221 passed /65 skipped /2 warnings /150.05s**；pilot-02 D01/D02均incomplete，61次/$0.06506505。G09及audit事实修复实际生效；机械核验2/2通过。D01 G02重复T3 target阻断Claim（FL-D191），实际DOCX G16在同一条款head/tail重复写入（FL-D192），G05误改权限条款（FL-D193）；D02业务站点补充40/40但G05权限句被audit误拒，不能称整合同通过。前两轮累计123次/$0.12973845。
- 新修复：`recall.py` 规划前精确对账satisfied aliases（显式不同occurrence保留）；`rebind_g16_clause_targets` 将同一费用条款head/tail绑定至统一尾位置再dedupe，正文摘要保持各一；G05在assign阶段所有状态及planner采用窄业务site guard，`generation/effects.py`同步允许直接“调整基金份额类别”。`recall_pipeline.py::_plan_and_generate` 调用重绑和最终dedupe。更新低层测试夹具补合法类别语境；原gold/scorer不改。相关174项通过，扩大组合后仅旧低层fixture需加类别语境，修复后最后组合104 passed/8.34s，diff check通过。
- 当前冻结改为 `snapshot-03`，build `515e0e08accf04172609422acf08f25120144e5fcd2da642e1c9199b9987ae12`，hash见`run_context-03.json`；继承snapshot-02仅新增上述FL-D191～193修复及测试。源站点审查脚本`/tmp/opencode/operation-validation-20261024/review_pilot_sites.py`是开发补充核验，不是独立gold；检查guide完整新文、费组、公式余文、旧机制删除、同条款G16次数和权限句保留。pilot-02 D01 36/40、D02 40/40，文件`pilot-02/supplemental-site-review.json`。
- snapshot-03完整测试已结束：**1226 passed /65 skipped /2 warnings /150.73s**。`replay_pilot_plan.py offline-plan-03`用pilot-02真实target、不调模型重建局部产物，D01/D02 G16 count均2（各正文摘要一次）；因其他生成/复用路径缺少模型与最终edit上下文，replay全量Claim未通过（D01有5类failure/7unresolved、D02有2类/4unresolved），只作局部重复修复证据，不可计正式交付或另一个真实样本。
- pilot-03 已完成：D01/D02 均 `completed`、`delivery_status=complete`、`unresolved=0`，真实模型 59 次、约 `$0.062185`；`verify_downloaded_artifacts.py` 机械核验 **2/2**，`review_pilot_sites.py` 实际 DOCX 逐站点检查 **D01 40/40、D02 40/40**。最终 SHA：D01 final `a682e23b6dada80dddd1ae0662a7a9a0277cdfc63bffe08ab6b565ab08ca94b3`、redline `fe5120b139ff86d1fb54d547f870940d8eb5c8291928cba43bb09603e0cb2b45`；D02 final `8f25c7470b8a99d3ebd6043452e96d33af00798e10c5326f72d05f848e4edd6e`、redline `cd292a7a2ab2f9ddfea16456866f156b1486ada480f6e733472da5aa3bf5d371`。FL-D191～193 已在这两个真实样本关闭；pilot-02 原失败证据保留。
- 仍未完成：受控发布；最终快照20份真实 dev 修改与实际 DOCX/report/hash 评分；按开发结果登记缺陷并局部复测；冻结后 holdout/blind 8份；生产域名真实登录→上传→持久任务→真实 Worker/模型→DOCX 修改→复核→结果页→final/redline/report 授权下载及哈希/修订核验；更新集中问题记录、最终交付说明和本断点。
- 运行状态：无子agent；旧 `dev-03` 在 D03 因 FL-D199 中止，D04–D20 未运行，其失败证据保留。`debug-d03` 已用保存 checkpoint 无网络稳定复现原 NameError，修复后越过该点；snapshot-05 冻结快照全量回归 **1234 passed /65 skipped /2 warnings /157.09s**。共享 ledger 仍须作为真实模型费用权威，失败报告中的 null 不能计为零成本。当前 `dev-05` 使用 snapshot-05、独立 `data-05` 和共享 ledger 正在运行，已完成 D01–D06：D01 `incomplete`/8 unresolved，D02 `complete`/0 unresolved，D03 `incomplete`/6 unresolved，D04 `incomplete`/16 unresolved，D05 `incomplete`/2 unresolved，D06 `incomplete`/30 unresolved；D07–D20 尚未完成。D01–D06 的下载 DOCX 机械核验均通过；D01 supplemental site review 为 **38/40**，失败为 G15 p758/p1221 变体残留。当前工作区已加入 FL-D204 的最小变体恢复修复及回归测试，但 dev-05 使用的是修复前 snapshot-05，不能把该批次结果当作修复后结论。
- 最新冻结与运行：`snapshot-04` build **`efc893de06f8476d4123a27cb1c467d4eb637c5f5cd297628d23590f27745edd`**，源码上下文已保存为 `run_context-04.json`（prepare 原始输出名为 `run_context.json`）。后台 **dev-04 完整 D01–D20**，shell `sh_16b94e96c0011udYlV17dBCfjC`；等待完成通知，不重复启动/轮询。启动后一次账本快照 **258 HTTP / $0.24256935**，总 cap 2000/$2不变。全量工作区离线验证 **1266 passed /44 skipped /2 warnings /242.79s**，快照 compileall通过。生产未发布。下一动作是完成通知后读取 `dev-04.log` 和 `dev-04/batch.json`，运行下载机械核验、旧scorer、实际DOCX逐合同业务复核；有已知缺陷不能凭complete状态直接进holdout。
- `snapshot-04/dev-04` 已判废并保留：其冻结脚本从 HEAD 取回旧 API/tasks，虽 D01 已完成，但 D02 尚未完成即停止；不作为单一版本评测。新冻结 `snapshot-05` 从 snapshot-03 显式继承并只覆盖 `fundlex/recall_pipeline.py`，build **`5b04e5ea2ed2aadddca51ddca4ed66c1d65f33461f435445f394b5e34cd953c2`**，`run_context-05.json` 已保存，API/tasks 与生产一致。后台 **dev-05 D01–D20** 使用独立 `data-05`、共享 ledger；启动前总账 **282 HTTP / $0.26175915**。dev-04 的 D01 产物保留，不并入 dev-05 分母。
- 接续补充：dev-05后台shell **`sh_16b98cf3b001YCPBttGsvCxaPI`**，父进程2645668、隔离API2645673、Worker2645674、runner2645684（仅作本轮识别，操作前重新核实）；D01已真实写入checkpoint，租约正常，尚无全批终态。最新一次总账快照 **316 HTTP / $0.30515715**；不要重置、重复提交或据此当作最终费用。等待完成通知后读取dev-05.log/batch.json再分析。
- snapshot-05自身完整离线测试已完成：**1234 passed /65 skipped /2 warnings /157.09秒**，日志`/tmp/opencode/operation-validation-20261024/snapshot-05-pytest.log`，与工作区1266项分开披露；完整冻结文件manifest无变化。无子agent、未改生产。
- 新增`tools/evaluation/build_revision_review_packet.py`（仅评测辅助，未写入冻结引擎），20 dev原件材料在`dev-source-review-05/`，pilot-03实际diff材料在`pilot-03-review-packets/`：D01 19段/D02 18段与机械复核地址及哈希完全对账，工具不赋业务分数，不读holdout产物。FL-D188保留未关闭，冻结labels SHA未变。已新建`docs/REAL_REVISION_EVALUATION_RESULTS.md`记录证据边界与后续动作。
- 只读`release-candidate-05.json`确认候选相对生产5文件不同：generation/effects.py、generation/registry.py、recall.py、recall_pipeline.py、recall_prompts.py；API/tasks相同。旧构建回退另登记FL-D203，本轮用显式继承修正，通用prepare未修。dev-05 运行期间新增 FL-D204 G15 变体恢复修复：Sweep 在唯一适用 delete/replace operation 且 finding 已 source-bind 时，能将原 `absent/not_applicable` target 转为 operation-specific synthetic `needs_edit` target；多 operation 继续 fail-closed。回归测试已通过。基于 snapshot-05 创建修复后候选 `snapshot-06`，build **`e53c8585514470019ff2b7890aed1f407573f9574d00abe8b23a72d8a1b0a568`**，`run_context-06.json` 已保存，唯一引擎源码 overlay 为 `fundlex/recall_pipeline.py`，API/tasks 与部署版本一致；snapshot-06 全量离线回归已完成 **1236 passed /65 skipped /2 warnings /148.62s**，日志为 `snapshot-06-pytest.log`，未发布、未调用真实模型。dev-05 仍继续使用修复前 snapshot-05。当前下一动作：dev-05完成后运行`verify_downloaded_artifacts.py`、旧p6_score、全dev实际DOCX阅读材料生成与逐站点业务复核；未达条件不跑holdout、不发布、不宣称最终交付。

## React V2 前端回归收口（2026-10-24，当前）

- 本轮按用户要求完成 React V2 控件与原版视觉体系对齐，登记 FL-D212：新增共享 `Select` 控件，统一输入/下拉/复选框/文件选择器/按钮组/筛选栏/拖放区/表格和 Review 决策状态；V2 顶栏改为原版浅色 64px，侧栏恢复 252px 分组图标导航，移动端保留横向导航；任务总览补齐按指引筛选，并恢复消息、帮助中心、修改密码入口和页脚信息。任务、批量上传、指引、设置、用户和 Review 路由/API 未改变，独立 Compare 入口保留。发布后的移动端侧栏溢出修复已追加验证，详见本文最新发布段。
- 当前验证：`PATH=/tmp/opencode/node-v20.18.0-linux-x64/bin:$PATH npm run typecheck`、`npm run lint`、`npm run build`、`git diff --check` 均通过；前端浏览器定向回归 **7 passed**；公网 smoke 已覆盖登录、关键路由、消息/帮助入口、1440px/768px/390px响应式宽度、1440→768原地缩放、页面错误、控制台错误和 404，证据见 `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json`。最终构建资源为 `frontend/dist/assets/index-BkJEWrna.js` 与 `frontend/dist/assets/index-ko73k-L5.css`，已完成前端-only 生产发布。

- 当前工作区仍为 branch `feat/frontend-v2`、HEAD `fc8424a`，同时保留前端、Compare、evidence、运维和 recall-first 引擎的并行未提交/未跟踪改动；不得整仓库 add/reset/覆盖。主机已核实为 `iZf8zemhifedxdow1zefr0Z`，内网 `172.28.217.241`，使用 `.venv/bin/python`。
- 本轮修复并登记 `FL-D182`、`FL-D183`、`FL-D184`：React smoke 将 API 404 与静态资源 404 分离；Guides 启用状态只允许后端支持的 `parsed`/`released`；任务列表、任务详情、指引列表/详情首次加载失败增加页面级重试。
- 新增浏览器覆盖：真实临时 FastAPI 任务入口创建任务、上传真实 DOCX，并打开 task-scoped 合同详情和 Review 深链，检查报告/修订错误态、请求路径和 page error。
- 当前验证：`PATH=/tmp/opencode/node-v20.18.0-linux-x64/bin:$PATH npm run typecheck` 通过；`npm run lint` 通过；`npm run build` 通过，最新 JS 为 `frontend/dist/assets/index-CmYK9MZP.js`，CSS 为 `frontend/dist/assets/index-BCmLwO6a.css`；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` → **3 passed**；`FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/test_tasks_api.py tests/browser/test_frontend_v2.py -q` → **30 passed / 1 warning**；`git diff --check` 通过。

### React V2 parity 候选更新（2026-10-24，未发布）

- 矩阵见 [`docs/FRONTEND_V2_PARITY_MATRIX.md`](FRONTEND_V2_PARITY_MATRIX.md)。本轮补齐并核验任务总览统计卡、上传清单搜索/状态筛选/分页/重复名称保护、替换/移除/清空，以及替换失败时旧文件不能继续提交的状态边界；集中记录新增前端问题 FL-D223。矩阵中的 Compare 独立入口问题沿用 FL-D219，已修正专项浏览器脚本默认页与业务页的导航断言。
- 当前前端候选构建资源：`frontend/dist/assets/index-B75utm89.css`、`frontend/dist/assets/index-jR7FF1CT.js`。`index.html`、CSS、JS SHA-256 分别为 `06e141e0edefd822bff92194e2f1c75115af292f8657029073f54fc461c25cc9`、`6e2be4855eafc59c43153cf2b1f58efa3c02b0a5452bc75b473d66f0e4d1664b`、`bc87d8701dc0bfaaaca00c121528942975253ac77a83c46a3b26fa03cf709ae3`。`npm run typecheck`、`npm run lint`、`npm run build`、`git diff --check` 通过。
- 当前本机浏览器证据：React V2 定向回归 **6 passed**，React/API 组合 **33 passed / 1 warning**；Compare 单测 **70 passed / 5 skipped / 1 warning**；`tools/evaluation/compare_e2e.py` 现访问 `/compare#compare`，独立 Compare **9/9 场景通过**，证据 `/tmp/opencode/compare-e2e-final.json`；1440/1180/1000/768/760/420/390 七视口均无 document/body 横向溢出。
- 本轮未发布候选，也没有新的生产模型调用。公网仍是此前已发布版本；任何后续发布都必须只同步前端静态候选并重新完成公网入口、深链、响应式和真实用户交付核验。
- 发布前公网复验发现 FL-D224：旧候选在同一浏览器从 1440px 原地调整到 768px 时 `document/body=976px`，已用 `.main-content { min-width: 0 }` 修复；本机浏览器专项 **7 passed**，最终候选已受控同步并完成公网复验，详见上方最新发布记录。
- React V2 已按用户“发布”指示完成前端-only 静态同步到 `/opt/fundlex-recall-first/frontend/dist` 并重启 API；本次没有重启 Recall Worker，Compare Worker 保持原状态。发布后公网 `/`、关键 V2 路由、新 hashed JS/CSS 均可用，具体资源哈希与浏览器证据见本文最新发布段。`FL-D185` 发布阻塞已解决，`FL-D186` favicon 404 已修复并验证。
- 发布后本地前端 typecheck、lint、Vite build、浏览器定向回归和公网 smoke 均通过；最新 smoke 已补充移动端页面宽度回归。此前的临时 API smoke 仍保留为开发证据，不能替代最终真实登录→当前指引→上传→seal→Worker/模型→DOCX 修改→Review→授权下载与哈希核验。
- 生产工作台的完整真实用户路径此前已有任务 `70e8148548ec4432a7d68457fd866fb1` 证据，但本次前端-only 发布没有重新创建任务或调用模型；当前版本仍需完成本轮生产真实合同的 Worker/model、DOCX、Review、报告、授权下载、修订和哈希核验，不能据此宣称完整项目交付完成。

## React V2 / Compare 入口说明（2026-10-24）

- 用户看到“恢复原版本”的原因已确认是访问 `/compare`：该路径按设计继续提供独立 Compare 页面，生产首页、`/tasks` 和 V2 hashed assets 未回滚。问题登记为 FL-D194。
- 已更新 React V2 导航为“合同对比（独立页）”；Compare 页面增加独立页面说明和返回 `/` 的“返回新版修订工作台”链接。Compare 业务链路保持不变。
- 本次前端静态变更已按文件发布并完成公网入口复验，新资源为 `index-BUWdg2p2.js` / `index-BCmLwO6a.css`，工作区、部署目录和公网 JS SHA 一致。最新生产任务 `70e8148548ec4432a7d68457fd866fb1` 已真实登录、当前指引快照、上传、seal、Worker/model、详情、Review、报告和授权下载完成：任务 `completed`，文档 `succeeded/incomplete`，32 targets 中31完成、1未解决；G09 p224 仍未执行。结果文件 `/tmp/opencode/fundlex-production-v2-e2e-20261024/e2e-12d1e3tfq98g/result.json` 确认 `page_errors=[]`、`console_errors=[]`、静态/API 404均为0；`working_final` SHA `c2becfdc024efc171b79ae2d409f25c8f079d65e40de67198ebbbbd0a4c1923e`、`working_redline` SHA `811425c8c14d87972098adbb7a179530e36ce958db0b0f9ec88b39b815ad8469`，报告 JSON/Markdown SHA 分别为 `a6d86a200eef81d82b55274047f5b4a79c19294b13a407c7e7a30064b172e16b` / `b86a864acd9d1d2665c7f5a4c8a47dfc863fc09b6d625fa303f27231b3db568f`。页面/路由误断言登记 FL-D195，自定义 fetch 漏带 Bearer 登记 FL-D196，详情/Review 文案登记 FL-D198；Review `<hr>` React #137 登记 FL-D201，工作文件哈希误报登记 FL-D202。引擎发布仍受 snapshot-05 dev 结果约束。

## Recall-first operation Registry/Router 收口断点（2026-10-24，当前优先）

- 当前工作区：branch `feat/frontend-v2`，HEAD `fc8424a`；工作区同时保留前端、compare、evidence、运维和其他并行未提交/未跟踪改动，禁止整仓库 add/reset/覆盖。当前主机已核实为生产/工作同机 `iZf8zemhifedxdow1zefr0Z`，内网 `172.28.217.241`；Python 使用 `.venv/bin/python`。
- 本轮继续收口 recall-first 的 operation-level Registry/Router、Policy Components、canonical obligation、Claim Replay、coverage 和 Delivery Gate。显式 guide `operation_id` 优先贯穿 planner、replan/residual、targeting、obligation、coverage 与 replay；部分标注、显式 operation 缺 Registry entry、UNKNOWN/CONFLICT fact 和未解析 occurrence 均 fail-closed。旧无显式 identity 的低层 fixture 只走 legacy 兼容路径。
- 已实施并登记集中问题 `FL-D178`、`FL-D179`、`FL-D180`：当前 operation policy 文案按自身组件验证；G08/G11 局部 fee group、G14 授权替换、G16 完整 Compose 语义分别处理；动态 operation 缺 concrete Registry 时 planner 返回 `RECALL_OPERATION_REGISTRY_MISSING`。
- 新增回归：`tests/test_generation_registry.py::test_routed_planner_fails_closed_for_missing_custom_operation_registry_entry`，直接穿过 `plan_target()` 验证缺失注册阻断；自定义 operation 不能借用 `RULE:index` 别名。
- 当前离线验证：Registry/recall core/Claim Replay 组合 **104 passed**；Registry/validators/coverage/obligations/delivery **89 passed**；Claim/targeting/pipeline **77 passed**；首次全量曾暴露并已修复 FL-D181，最终 `.venv/bin/python -m pytest tests -q` **1249 passed / 42 skipped / 2 warnings / 223.62s**；compileall 与 `git diff --check` 通过。真实合同重新评测、build identity 冻结、生产发布和当前版本工作台 E2E 尚未完成。
- 下一步：先运行完整 `.venv/bin/python -m pytest tests -q`，保存真实结果；再补 occurrence 0/1、重复 occurrence、canonical/legacy coverage fallback、replan/residual/delivery 的缺口；随后只整理引擎相关文件冻结版本，按 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` 重新执行真实合同开发集/历史失败样本/holdout-blind，并重新完成生产工作台真实上传、Worker/模型、DOCX、复核和下载哈希核验。旧 `FL-D175` 证据属于此前版本，不能替代本轮冻结版本验收。

## 合同比较阅读器联动滚动与视觉重构已发布（2026-10-24）

- 本轮完成 `frontend/index.html`、`frontend/compare.js`、`frontend/compare.css` 和 `tools/evaluation/compare_e2e.py`；集中问题记录新增并关闭 FL-D177。其他引擎、evidence、`tools/ops/` 等未提交改动仍保留，不能整仓库 add/reset。
- 已实施：双 pane 按可滚动高度比例联动，滚轮/连续事件使用 `requestAnimationFrame` 合并且有来源锁防递归；结果摘要、覆盖边界、方向提示、基准/修订标题、同步状态、差异导航和移动端结构重新分层；保留连线、筛选、键盘定位、pair 轮询和移动端切换。
- 验证：`.venv/bin/python -m pytest tests/test_compare_*.py -q` → **70 passed / 5 skipped / 1 warning**；本地 `/tmp/opencode/compare-e2e-ui-v5.json` → **9 场景全部通过**，正向/反向同步比例与 SVG 几何均通过；生产 `/tmp/opencode/compare-production-ui-e2e/report.json` → 真实注册/登录、上传公开合同、Compare Worker、结果查看、双向联动、移动切换、键盘定位、报告下载通过，page error 0，联动比例误差 `5.3e-6` / `2.6e-7`，报告 3189696 bytes。
- 发布：提交 `0f51d07` 已推送到 `origin/feat/contract-compare`，通过 `tools/deploy/publish_workspace.sh` 发布；`fundlex-recall-api`、`fundlex-recall-worker`、`fundlex-compare-worker` 均 active。生产截图 `/tmp/opencode/compare-production-ui-e2e/viewer.png`。
- 下一步：如继续调整 compare 视觉或滚动行为，必须重新运行 compare 专项、浏览器验收和生产真实用户路径；不要将当前截图中的 headless 环境中文字体缺失现象误判为合同文本内容问题，正式浏览器应按客户端字体渲染复核。

## 合同比较页面改版已发布（2026-10-24）

- 本轮依据产品、UI、前端三类只读评审修改 `frontend/index.html`、`frontend/compare.js`、`frontend/compare.css`，并扩展 `tools/evaluation/compare_e2e.py`。其他引擎、evidence、`tools/ops/` 等未提交改动仍保留，不能整仓库 add/reset。
- 已实施：原版→对比版方向语义、覆盖不完整人工复核提示、批量上传中断后继续上传、轮询保持选中 pair、差异类型筛选/章节显示、移动端单栏侧切换、正文差异标记键盘定位与焦点可达。
- 验证：compare 专项 **70 passed / 5 skipped**；本地浏览器验收 `/tmp/opencode/compare-e2e-ui-revision-v3.json` 为 **9 个场景全部通过**；生产浏览器验收 `/tmp/opencode/compare-production-ui-e2e/report.json` 通过，覆盖方向说明、incomplete warning、移动端单栏切换、修改筛选、键盘定位和报告下载，无 page error。
- 发布：UI 提交 `5d04271` 已推送并通过 `tools/deploy/publish_workspace.sh` 发布；三个服务均 active、重启计数 0。生产结果为 2772 处差异，报告下载 SHA-256 `d1607d77f3b0fe8487c8c1a8b4c2c287599e5283eb7d207b447ce0ca719716e3`。compare 不调用模型，费用 `$0`。
- 下一动作：后续 UI 或 Worker 改动必须重复生产浏览器回归；其他引擎、evidence、`tools/ops/` 等未提交改动仍保留，不能整仓库 add/reset。

## 引擎真实合同与工作台验收断点（2026-10-23 21:00，优先）

- 本轮完成 FL-D157~FL-D175：多通道召回、append/G16 锚点、复合目标 content-check、G06 语义探针、跨段事实引文、G17 尾句、G08 认购/申购 flip、G18 等价句、G20 FALSE 分支审计、delete+append 联合校验、重复 append 目标去重均已修复并有回归。
- **真实合同：6 份不同合同 delivery_status=complete、unresolved 0、final/redline 哈希与报告一致**（广发品质回报、核心优选 FOF、上海清算所债券、ESG 混合、央企股东回报 ETF 联接、央企创新驱动 ETF 联接）；港股通红利 ETF 正确 excluded。明细/哈希/费用见集中问题 FL-D175。
- **工作台真实路径（本地临时 API+Worker，非生产域名）**：登录 → 建任务 → 上传 → seal → 真实模型 30 calls/$0.02243 → complete → 下载 final/redline/report；final 哈希与报告一致，redline 19/19。脚本 `/tmp/opencode/engine-live-20261023/workbench_e2e.py`。
- 全量测试：**1203 passed / 40 skipped / 0 failed / 222.50s**；compileall/diff check 通过。
- 临时模型账本合计 **1129 calls / ≈$0.7999**，全部在 `/tmp/opencode/engine-live-*`，未用生产账本；未打印凭据。
- **生产发布已完成**：引擎提交 `11c3ae8` 已本地提交并通过 `publish_workspace.sh` 发布；部署 `recall.py`/`recall_pipeline.py`/`effects.py`/`claim_replay.py` 哈希与工作区一致，api/recall-worker/compare-worker 均 active。
- **生产域名 E2E 已通过**（https://fundlex.club，admin）：任务 `19a5c76e…`，上传广发品质回报 → Worker 真实模型 **30 calls / $0.02247 / 115s** → complete、unresolved 0；final SHA `e48e0f78…` 与报告一致，redline `aceb9289…` 与报告一致且 19/19；关键段落已核对。Chromium 登录/任务页/3 个下载入口正常，无 pageerror（仅登录前 401 探测）。
- **生产批量已通过（5 份不同合同 complete）**：广发品质回报 + FOF/上海清算所债券/ESG/央企创新驱动 ETF 联接；4 份批量任务均 unresolved 0、final/redline 哈希与报告一致、redline 17~19 处修订、G15/G17 旧条款 0 处、G16 新政策存在。明细见 FL-D175。生产 5 份合计 156 calls / ≈$0.1254。
- **未做**：生产验收任务未清理（无 DELETE 接口）；浏览器截图 `/tmp/opencode/engine-live-20261023/production-browser/task-page.png`；最终交付说明尚未汇总。
- 下一步：① 观察三服务与生产账本；② 清理/登记验收任务；③ 更新最终交付说明与 README；④ 如需回滚，使用 `11c3ae8` 前的部署快照（如有）。

## 合同比较已推送并部署（2026-10-23）

- Compare 发布提交为 `eba2b3a`，已推送到 `origin/feat/contract-compare`。工作区其他任务的未提交改动仍保留，未整仓库提交。
- 已执行 `tools/deploy/publish_workspace.sh`；API 与 Recall Worker active。随后安装、enable 并启动 `fundlex-compare-worker.service`，三项服务均 active，重启计数均为 0。
- 生产真实用户链路已通过：工作台注册/登录 → 合同对比 → 上传两份公开 DOCX → 封存 → 独立 Worker → 结果页 → 双栏导航 → 报告下载。结果为 2772 处差异，coverage 明确标记暂不支持的页眉/页脚/绘图结构；浏览器 page error 为 0。证据见 `/tmp/opencode/compare-production-e2e/` 和 `/tmp/opencode/compare-production-browser-e2e/`。
- 本轮 compare 模型调用 0、费用 `$0`；未修改 nginx 或生产数据库结构。后续若修改 compare 代码或 Worker 模板，需重新发布并重复生产链路验收。

## 核心引擎层审查与修复断点（2026-10-23 18:00，历史；最新见上）

- 用户问题：检查核心引擎层修改情况；前一个负责 agent 已失联。**本轮已完成审查、修复、回归与 1 份真实模型单例验证；未 commit、未部署、未跑 ≥5 份合同、未做工作台 E2E。**
- 现场：branch `feat/contract-compare`，HEAD `a36acd2`（与 `origin/refactor/recovery-architecture` 同 SHA）。引擎改动仍未提交：`fundlex/recall.py`、`recall_pipeline.py`、`generation/{coverage,effects,router,__init__}.py`、`recovery/{history,orchestrator,policies,types}.py` + 测试。compare/前端未提交工作保留，未整仓库 add。
- 全量回归：`.venv/bin/python -m pytest tests -q` → **1195 passed / 40 skipped / 0 failed / 230.16s**；compileall、`git diff --check` 通过。compare agent 同时登记 FL-D160~FL-D162（其 MySQL/worker 修复与 G16 site guard 兼容性），本段不覆盖。
- **已修复（集中问题记录 FL-D157~FL-D166）**：
  - FL-D157 G15 关键词配对跨条款：加入句末终止符/新主题/半句合并门禁，复合 parts 改 compact 偏移；100 份扫描 0 误配对（原 6）。
  - FL-D158 append 摘要误锚定变更触发句：新增 `_append_definition_anchor` 定义句门禁；30 份扫描 0 误锚点（原 16）。FL-D166 同时修复模型目标落在“基金份额类别设置”导致 G03 双插入。
  - FL-D159 G16 锚点在支付从句中间：`_g16_clause_end` 走到条款末段（p809/p1265），append site/归属/planning 使用同一 guard；30 份扫描 0 中间锚点（原 5）。
  - FL-D163 复合目标第二段被 content-check 静默丢弃：整段删除映射到 `len(span.text)`，`_composite_part_slice` 同步；G15 p807/p1263 不再残留。
  - FL-D164 out_of_scope 模型目标仍压制 survey：`known_operations_from_targets` 跳过无效目标。
  - FL-D165 删除与同段 append 合并时 Claim/Validator 误报：delete 在“联合计划精确匹配 + 旧文不存在”时判 PASS。
- **真实模型单例（`/tmp/opencode/engine-live-20261023/final1/`）**：广发品质回报，43 calls / $0.02638 / 约 150s，`delivery_status=incomplete`；G01 p106、G03 p138 各插入一次，G15 p806/p807/p1262/p1263 全部删除，G17 p808/p1264 删除，G16 p809/p1265 各插入一次；无重复政策文本。obligation：13 ARTIFACT_VERIFIED / 9 ALREADY_SATISFIED / 10 NOT_APPLICABLE / 2 UNRESOLVED。
- **剩余未完成（FL-D167）**：G08 p156 `RECALL_COMPOSE_FIXED_TEXT_MISSING` + `CLAIM_OPERATION_NOT_PLANNED`；G18 无 verified site。两者是 FL-D146 之前已有的生成/适用性问题，不是本轮 FL-D157/158 回归，但不能宣称合同完整。
- 预算：本轮真实模型合计 465 calls / ≈$0.2473（临时账本均在 `/tmp/opencode/engine-live-20261023/`，未用生产账本、未打印凭据）。无遗留 live 进程。
- **已本地提交 `f3791df`（未 push）**：20 个引擎/测试/文档文件；compare、前端、api.py 的未提交工作未纳入。生产仍是旧版本，未部署。
- 下一步：① 修 G08/G18 并重跑本单例；② ≥5 份真实合同；③ 工作台登录→上传→真实模型→DOCX→下载全链路；④ 发布与生产复核。当前生产仍是旧版本，未部署。

## 核心引擎层改动审查原始发现（2026-10-23 16:10，已由上一段修复）

- 原审查发现 FL-D157（G15 配对吞入 G17 p808）、FL-D158（G01/G03 摘要误锚定变更触发句）、FL-D159（G16 支付从句中间锚点）均已在 2026-10-23 晚修复并验证，详见集中问题记录与上一段。

## Codex SSH 稳定性修复断点（2026-10-23 15:00，优先）

- 用户问题：关闭 SSH 后 Codex 任务仍中断；历史对话频繁提示“open in another app”。OpenCode 侧正常。
- 已定位：① legacy `--no-daemon` TUI 把 turn 放在自身进程内，TUI 退出即 `op=Interrupt`；② 每个 TUI 都是独立 thread-store writer，旧 detached tmux 会话永久持有多个 thread lock；FL-D153 的“stale lock 删除”是误判，已更正。
- 已实施：官方完整包启用 managed app-server daemon（0.164.0），`~/.local/bin/codex` 指向 managed `current/bin/codex`（旧 0.162.1 保留为 `codex-standalone-0.162.1`）；daemon auto-update 关闭；`loginctl enable-linger opencode`；`codex-app-server.service` + 60s timer（`codex-daemon-ensure` 健康探测），cgroup 在 `user@1002.service`；`codex-persistent` 改为 daemon-first + tmux fallback，并新增 `resume` 锁路由、`ls/where/attach/close/gc`。
- 已验证：`where 01a16485…` 指向 pid 2152151 / `codex-d01396214ff5`；dry-run resume 正确 attach 而非新开；PTY 断线测试通过（0 模型调用）；TUI SIGKILL 后 daemon 仍写 rollout；`codex` 经 `.bashrc` 启动显示 `← for agents` 且不新建 legacy 会话；`codex doctor` 0 fail。
- 未完成/下一步：① 用户现有 4 个 legacy 会话仍在跑，未强杀；完成后退出，之后新会话走 daemon；② SIGHUP 实测已通过（TUI 收到 SIGHUP 后 daemon 内 sleep 120 仍于 121s 后完成并写出文件）；仍建议用户用真实任务复验；③ `01a16780…` 测试 thread 未删除；④ opencode.service 每 3s 重启 1768 次，已记 FL-D156，未修。
- 文件：`tools/ops/codex_persistent.sh`、`tools/ops/verify_codex_persistence.py`、`tools/ops/install_codex_persistence.py`、`~/.local/bin/codex-persistent`、`~/.local/bin/codex-daemon-ensure`、`~/.config/systemd/user/codex-app-server.{service,timer}`、`~/.codex/app-server-daemon/settings.json`。

## 合同双版本对比开发断点（2026-10-23，当前任务优先）

- 目标：独立确定性 compare pipeline、DOCX 文字高召回、前后端/持久任务/worker、20真实base 14dev6holdout mutation评测、独立review、浏览器验收。禁止生产部署；LLM调用0/费用0。
- 环境已核实：hostname iZf8zemhifedxdow1zefr0Z，instance i-f8zemhifedxdow1zefr0，同机172.28.217.241；Python必须 `.venv/bin/python`（系统python3.6不可用）。branch feat/contract-compare，HEAD a36acd2。当前compare代码全未提交；用户已有recall/generation/旧测试/运维和evidence改动不得覆盖/清理，禁止整仓库add。
- 已实现：fundlex/compare 全套 models/normalize/parser/align/text_diff/render/store/service/api/worker；frontend/compare.js/css + index nav/页面 + app.js 小adapter；api.py最小接入；设计文档；tests/test_compare_*；tools/evaluation/compare_fixture_builder/gold/evaluate/benchmark/e2e。
- Baseline全量：1103 passed/35 skipped/1 failed（test_append_applicability::test_g16_summary_business_anchor_is_considered_under_generic_heading），log `/tmp/fundlex-compare-evidence/baseline-pytest.log`。
- 最近compare suite：41 passed/4 skipped（MySQL opt-in），修gold structural zero后已通过corpus4。system reviewer隔离真实MySQL 8.0曾11pass，修finish/retry stale CAS与upload/seal锁，fixtures已改真DOCX。MySQL实例由reviewer管理，未碰生产。
- 实际发现修复：FL-D149/150/151 已记录；align长文本快速评分+cache；multi-block fuzzy不能吸收exact constituent；重复paragraph插入/删除真实漏覆盖已修；renderer已改offset准确virtual anchor、空docfallback、真正table结构、无silent overlap discard；parser新增递归nested/cell SDT（待reviewer回归），unknown可见结构应warning。frontend File refs保存且add/remove增量DOM；folder未配对显示、token隔离、创建后轮询、pane内滚动。
- Corpus `/tmp/fundlex-compare-corpus-v4`，20bases386mutation；初gold-v5 a8ba42...，v6修错误structural zero（B07 merge实际挪heading）hash58390e...。刚进一步修zero检查使用去空白可见字符流避免正常split被误取消expected_zero，需再冻结v7并最终跑全指标。不能修改gold迎合算法；原v5/v6保留。
- v6实际指标：dev272pairs，gold operations219/219，modify112/113，zero fixtures69；holdout114pairs，ops92/92，modify46/46，zero30；median0.620/0.653s，P95 0.897/0.942s，max2.096/2.759s。硬门 identity20/20，symmetry20/20，determinism20bases各5次20/20。注意集中FL-D152里分母刚写错（pair误作target，modify也写错），收尾必须更正为实际最终报告。
- 浏览器旧工具16/16通过 `/tmp/compare-e2e-review-final2.json`；仍需扩展到单组exact1modify、3组、20+diff、空侧、folder未配对、真实corpus页面上传worker。agent independent_frontend_review 正独占 tools/evaluation/compare_e2e.py 增补，root改frontend/render互不冲突。
- 活跃agents：algorithm_final_review 独立算法攻击/新增 tests/test_compare_review.py（已发现nested/cellSDT漏文本，root刚修parser）；independent_system_review 汇报MySQL/并发最终复查；independent_frontend_review 扩展E2E。无生产部署，无模型进程。
- 全量pytest正在 session16478，output `/tmp/fundlex-compare-evidence/final-pytest.log`，2026-10-23约13:5x启动，轮询工具write_stdin；最终当前代码若再修需合理重跑。
- 下一步：完成review发现修复和局部tests；v7 gold冻结+dev/holdout/hardgates，真实20pair benchmark（冷cache）含大小/blocks/peakmem；扩展browser；全量回归；集中问题登记/设计与最终证据报告；只commit compare相关文件，保留用户未提交代码。生产部署NOT PERFORMED。

## 合同比较最终收尾断点（2026-10-23 17:45，未提交/未部署）

- 当前分支 `feat/contract-compare`，HEAD `a36acd23d810aef2d8338e06698ed76c3e6b3c59`；工作区同时保留其他 agent 的引擎、旧测试、运维和 evidence 改动，禁止整仓库 add、reset 或覆盖。Compare 全套仍为未提交文件；本轮没有 commit、push、生产部署、服务重启、nginx/生产DB迁移或真实模型调用。
- 已完成实现：独立 `fundlex/compare` parser/normalize/align/text_diff/render/store/service/api/worker；工作台 `frontend/compare.js/css` 与导航接入；上传完整DOCX校验、对象/结果SHA、LONGTEXT、owner/idempotency、批量pair隔离、lease/fencing、严格span与renderer边界校验、bounded transient retry、固定错误码；worker systemd模板仅新增文档模板，未安装启用。
- 最新 compare 专项：`.venv/bin/python -m pytest tests/test_compare_*.py -q` → **70 passed / 5 skipped / 1 warning**；隔离MySQL8 port33155：`FUNDLEX_COMPARE_MYSQL_TEST_URL=... .venv/bin/python -m pytest tests/test_compare_system_review.py tests/test_compare_worker.py -q` → **28 passed / 1 warning**。Node `/tmp/opencode/node-v20.18.0-linux-x64/bin/node --check frontend/compare.js`、py_compile、compileall、git diff --check通过。
- 最新浏览器开发验收：`/tmp/opencode/compare-e2e-current.json` → **24/24 checks、9场景、全通过**；真实临时FastAPI+CompareWorker，单modify/0 diff/三组导航/25差异/insert-delete-modify/空侧anchor/folder手工补配/全失败/公开合同incomplete/XSS/身份隔离/SVG resize+独立滚动均覆盖；SVG三次误差均0px，无pageerror。截图 `/tmp/opencode/compare-e2e-current-shots/`。
- 冻结算法证据保持有效：compare算法及独立gold/evaluator源哈希与 `/tmp/opencode/compare-continuation/source-freeze-final.json` 一致；20 bases、386 mutation，dev 219/219 operations，holdout 92/92，identity20/20，symmetry60/60 directional，determinism20/20；dev modify112/113，holdout46/46。最终数字、gold与暴露holdout说明见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` 的 FL-D152 最终指标更正与 `/tmp/opencode/compare-continuation/FINAL_SUMMARY.md`。
- 独立算法复查：42种分段的1764对、1500组随机重排/修改攻击无零差异漏报、无双向不对称；已知限制是结构变化伴随局部修改时可能保守降级为整组delete+insert，已补FL-D152。系统复查发现的FL-D160过期清理覆盖终态、FL-D161重解析临时I/O已修并用临时MySQL验证。
- 本轮并行引擎兼容性修复：`fundlex/recall.py` 的 G16 site guard 对无 `location` 的简化测试替身返回 False；定向测试与完整回归均通过。最终 `.venv/bin/python -m pytest tests -q` → **1195 passed / 40 skipped / 2 warnings / 247.79s**，日志 `/tmp/opencode/compare-final-pytest-2.log`；FL-D162 已解决并更新集中记录。
- 最终收尾验证：启用隔离临时MySQL8（port33155）跑完整 compare → **75 passed / 1 warning / 14.31s**；本地 compare → **70 passed / 5 skipped / 1 warning**；最新浏览器 `/tmp/opencode/compare-e2e-final-current.json` → **24/24 checks、9场景、全通过**；Node/py_compile/compileall/diff-check通过。系统/worker关键并发回归额外重复5轮，每轮2 passed。
- 下一动作：只整理报告和供用户审阅的文件清单；当前默认不提交，保留所有未相关改动。最终回复必须明确 `Production deployment: NOT PERFORMED`、模型调用0/费用0，以及真实生产用户链路未执行。若后续用户要求提交，必须只选择compare相关文件，不能整仓库add。

## SSH 持久运行与权限配置（2026-10-23，FL-D147/FL-D148）

- 当前用户任务：解决关闭 SSH 后 Codex turn interrupted，并明确授权 Codex 完整本机权限；不涉及产品引擎修改或生产部署。分支 `refactor/recovery-architecture`，本轮读到 HEAD `a36acd23d810aef2d8338e06698ed76c3e6b3c59`；保留其他会话的引擎、测试和证据未提交修改。
- 已做：安装 tmux 2.7；安装 `~/.local/bin/codex-persistent`、`~/.config/fundlex/codex-tmux.conf` 与 `.bashrc` 的交互 `codex()` 函数；备份 `.bashrc`。用户 `~/.codex/config.toml` 设置 `approval_policy=never`、`default_permissions=:danger-full-access`，备份 `config.toml.bak-full-access-20261023-110532-742946`（600）。doctor 确认 Never/unrestricted；现有会话仍保留启动时权限，需要重开。
- 验证：`tools/ops/verify_codex_persistence.py` 真实 PTY 关闭后 worker 继续完成、重连接回相同进程，0 模型调用。Codex standalone 默认 app-server 启动失败（缺完整 package），加 `--no-daemon` 后真实客户端在 tmux 保持运行；同一聊天显示另一客户端写锁，未强抢。
- 收尾状态：`tools/ops/` 源码未提交；11:22 已同步最终 wrapper（含 `--no-daemon` 和显式 full-access flag），关闭 `client-diagnosis` 副本，最终 PTY 断线与同进程重连复验通过，syntax/compile/diff-check 通过。复现 `.venv/bin/python tools/ops/install_codex_persistence.py` 和 `.venv/bin/python tools/ops/verify_codex_persistence.py`，需宿主执行环境；当前旧沙箱已批准对应脚本前缀。新权限由新 invocation 验证，当前聊天仍受其原启动策略限制；用户应结束旧客户端后，新开 SSH、进入项目并运行 `codex resume --last`，之后同目录 `codex` 自动接回持久会话。
- 不改生产服务/SSH 守护配置，不打印/入库凭据；本轮无子 agent，无真实模型消费。新 shell 中同目录输入 `codex` 自动接入持久会话；旧聊天接续用 `codex resume <session-id>`，原客户端应先退出以释放锁。

## Codex 初始页与显式接回（2026-10-23，FL-D152）

- 用户反馈普通 `codex` 自动进入旧运行对话；原因是上一版 wrapper 固定 session + `new-session -A`。已改为普通 `codex` 每次新建 tmux session，`codex attach` 才按工作目录前缀接回最近旧 session，`codex resume --last` 继续官方历史聊天恢复。
- 已同步 `/home/opencode/.local/bin/codex-persistent`；旧活动 session `codex-d01396214ff5` 保留，未强制关闭。最终 PTY 持久测试通过：断线后完成、detached、attach 同一进程；syntax/compile/diff-check 通过。

## 目标合同闭环对话 stale lock（2026-10-23，FL-D153）

- 目标会话：`01a16485-b7ba-7090-99cc-51cb1c5fa0ab`，标题“优化 FundLex 合同修改闭环”。确认无对应运行进程，仅存在 10:26 的空 writer lock。
- 已将锁保留移至 `/tmp/fundlex-codex-stale-locks/01a16485-b7ba-7090-99cc-51cb1c5fa0ab.lock.20261023-134825`，释放原路径；当前两个活动 Codex 会话未停止。用户可重新切换该会话；若有其他客户端同时打开，需先关闭它。

## 当前前后端审查断点（2026-10-22，FL-D143）

- 最新用户要求：检查前后端交互与前端设计，暂不检查查找修改点及写 DOCX 引擎。当前不做真实模型调用或生产部署。
- 分支 refactor/recovery-architecture；收尾读到 HEAD `943830a33d41dccd7250bdcc36eae43da6d63c7a`（现场有其他会话推进证据提交，继续前重查）；本轮没有提交/推送，不覆盖他人引擎与证据内容。
- 本轮未提交文件：frontend/app.js/index.html/app.css、fundlex/api.py/tasks.py/guide_store.py、tests/test_tasks_api.py/test_guide_api.py、新增 tests/browser/test_workbench.py，以及本文和集中问题记录。详见 FL-D143。
- 已实施并隔离验证：未执行条款误标已修改；revision 字符串 ID 配对/checkbox/旧 review 响应；upload 草稿被旧请求污染；成功/异常去重统计、running/leased 筛选；单一支持模式、重复单位、总览轮询；failed 指引显式重试/去重；过期提示/身份展示残留。收尾增加排除/历史评测进度、含例外交付不可直接使用、业务问题摘要、无结果下载禁用、不可用指引说明、生成后恢复导航禁用状态。
- 验证：主改动后全量 `.venv/bin/python -m pytest -q` **1075 passed / 24 skipped / 2 warnings / 211.95s**；最后前端补充后相关 API/认证/指引/修订回归 **94 passed / 30.48s**，中文字体环境下 Chromium **29 passed / 38.03s**；Node syntax、compileall、diff-check PASS。前后端流程与报告/修订审查在 1440/768/390 无横向溢出、无 pageerror，中文截图人工复核。
- 复现浏览器：`FONTCONFIG_FILE=/tmp/fundlex-ui-fontconfig/fonts.conf FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_workbench.py -q --basetemp=/tmp/fundlex-ui-browser-zh-verified`；字体在 `/tmp/fundlex-ui-fonts/`，截图在 `/tmp/fundlex-ui-browser-zh-verified/`。这些仅是 UI fixture/临时 SQLite API 测试，不启动 Worker/真实模型。
- 预算/进程：本轮真实模型 0 calls/$0，不消耗前序引擎账本；无子 agent，无遗留测试服务。工作区修复已验证，生产未部署，查找目标和 DOCX 写入引擎未修改。保留他人 `docs/evidence/final-validation-20261022/` 的未跟踪材料。
- 下一步：如发布本轮改动，先核对并行引擎变更的冻结/发布状态，再按正常部署流程复核生产资源和真实登录路径。本轮不宣称项目最终真实合同验收完成。



## ff4d749 exact-code Gate 断点（2026-10-22，优先）

- **code_head=`ff4d7498b6c1aee72ba48686074d021fc7f84791`；evidence base=`387e334`（docs-only）。** 新证据根 `docs/evidence/final-validation-20261022/revalidation-ff4d7498/`；旧 682e68a bundle 未覆盖。
- 离线 1061 passed/0 failed/6 skipped/207.10s，compileall/diff-check PASS。四例 live record exact code：calls 32/35/29/34（合计130），cost $0.11742255；全部 incomplete，TRUE 24/例，TRUE→NOT_APPLICABLE=0；四例 working_final/redline 均生成，plan→artifact 0 mismatch；四例 replay 0 HTTP/0 tokens/0 cost 且 14/14 语义检查 PASS。D16 六 stage same_head=true、model_calls=0。
- 旧 finding：D02 absent、D11 G02、D16 G05、D16 Audit B 关闭；D01 overlap 仅 PARTIAL（artifact 已生成，但 G17 same-operation conflict 仍在）。
- **Gate=DO_NOT_ENTER_20_CASE**。剩余 root cause：G16 四例未 append；D01/D16 G17 duplicate/subset conflict；D02 G12/G13 joint edit 被 replan 丢失（回归）；D11 G18 summary p1207 false proof；D16 G12/G13 residual；G06 四例 absent literal 无 site proof；D01 G01/G02 split+B false audit；D11 G05:2 false block。
- 独立 Reviewer：Business BLOCK；Architecture 4 BLOCKER/6 HIGH；Recovery 4 BLOCKER/5 HIGH/8 MEDIUM；Test conditional（index/stage identity 已在证据修正）。本轮未改 runtime、未部署、未跑 20/514。
- 下一动作：按 `summaries/architecture-review-ff4d749.md`/`recovery-review-ff4d749.md` 的最小通用修复顺序修 G16/G17/G12-G13/G06/G01-G02；每项 regression；完整 pytest；新 code SHA 后重新四例 live+replay+四 Reviewer；不得用本 bundle 冒充验收通过。

## 接续断点（2026-10-22 07:00，前序 agent 断开后）

- **当前版本**：HEAD `682e68a5b3ef2a58feb77460af70afabdb314379`，分支 `refactor/recovery-architecture`，ahead 2（`22c15aa`、`682e68a`），未 push。工作区有未提交修复，涉及 `fundlex/recall.py`、`recall_pipeline.py`、`generation/claim_replay.py`、`generation/effects.py`、两个验证测试文件及未跟踪的 `docs/evidence/final-validation-20261022/`。
- **上一冻结证据**：exact-HEAD `682e68a` 全量 1024 passed/0 failed/6 skipped；四例 record 均完成但 Gate FAIL：D01 `not_generated`（EDIT_OVERLAP_OR_ADJACENT，无 DOCX），D02/D11/D16 `incomplete`，业务复核 5 项 BLOCKER/HIGH（absent 占位 proof、G02 分隔符、G05 会务条款误绑、Audit 无证据意见、D01 重叠）。D02/D11/D16 final/redline 与 FINAL_EDIT_SET 程序化零差异。
- **已实施未提交的最小修复**：
  1. Claim Replay 排除 `state=absent`、`attribution_error` 和 `claimed_operations` 作为 operation/site proof；避免无关 heading 产生 VERIFIED_ABSENT 或 falseblock。
  2. G02/G04 already-satisfied proof 按类别集合等价，接受 `A类及D类` 与 `A类、D类`；split 段落允许由含两类费用条款的报价证明 site，但仍拒绝 heading。
  3. G05 residual/effect proof 绑定份额类别设置/费率调整业务站，拒绝持有人会议费用豁免条款。
  4. `replan_sites` 改为按稳定 operation/site（而非会重编号的 target_id）保留/重绑；保留旧计划中合法的 p758 G15 duplicate delete，避免 duplicate-site 未编辑和 EDIT_OVERLAP。
- **离线验证（当前工作区，无模型调用）**：
  - D01 plan revision 2：18 edits / 0 conflicts；`build_docx_edits`→validate→generate 成功，G15 p758/p1221 均删除。Claim 仍剩 G01 p91、G02 p91/p92、G05:2、G06、G16；不是本轮 duplicate/overlap 误报。
  - D02 claim replay：12→4 failures；G02/G03/G04/G08/G09/G11/G12/G14/G22 已由 false failure 转 PASS；G05:2/G06/G16 继续 OPEN，G01 p93 真实 missing。
  - D11 claim replay：G02 delimiter false failure 消失；剩 G01 p91、G05:2、G06、G16。
  - D16 claim replay：G05 会务条款 false failure 消失；剩 G01、G06、G12/G13、G16、G17 真实 residual/缺失。
- **当前验证**：工作区全量离线 **1061 passed / 6 skipped / 2 warnings，219.40s**；修复已提交到本地分支，用户未要求 push，默认不 push。D01 split class-definition 的 G02 site 归属与 G01 append 已由 live 等价模拟关闭；G06/G16 仍缺有效 site/target；D16 G12/G13/G17 residual、BUS-FINAL-003 Audit 无证据意见仍待处理。之后新 SHA 重新四例 record/replay 与 ≥5 份真实合同验收。未部署、未跑 20/514，Gate 仍 FAIL。

## 新SHA四例record断点（2026-10-22，优先于以下）

- runtime冻结682e68a5b3ef2a58feb77460af70afabdb314379（ahead2，未push）。exact SHA完整1024passed/0failed/6skipped/200.45s；compileall/diff-check过。新证据docs/evidence/final-validation-20261022，原root20261021保留。
- D01新record35calls/$0.02569695/158.46s，not_generated EDIT_OVERLAP_OR_ADJACENT stage audit，无DOCX。Recovery agent零HTTP full replay复现，定位replan_sites单遍dirty_ids依赖target重新编号，旧G08 T007被保留+新T010 G08重复规划。diagnostics/D01-overlap-root-cause.md及capture/trace均保存。最小修复待D16当前record结束后实施，不重构writer。
- D02新record26calls/$0.02805225/127.21s，incomplete，24TRUE=7verified/5already/12unresolved。真实final/redline存在；programmatic source+finaledit→actual零差异，接受redline=final/拒绝=source。Business发现P0：state=absent占位heading p1036通过claimed_operations进入Claim verified site；导致falseblock以及G05:2/G06:0无关site VERIFIED_ABSENT。须排除absent/rejected/unattributed占位为proof，TRUE保持OPEN。Business reviewer继续只读，未修。
- D11新record25calls/$0.02588070/109.45s，incomplete，24TRUE=12verified/8already/4unresolved，artifact待business review。
- D16新record正在exec session23552，已22completed+1reserved（以实际状态为准），不要重启。完成前不改runtime，以保四例SHA一致。
- 活跃agents recovery_final_review只读诊断D01+absent入口；test_review只读stage/failclosed验证（D01sixstage缺Claim/obligation边界正确failclosed，D02全stage待结果）；business_final_review直接读新DOCX。Architecture上一轮CROSS001/002复审已0BLOCKER/HIGH，但新P0/P1尚未修，Gate FAIL。
- 预算原每case192/$0.60不变，已用累计：D01 164/$0.11800455余28calls；D02 76/$0.09072705余116；D11 79/$0.08133990余113；D16此前48/$0.06087105+当前未完。凭据仅进程内，ledger /tmp/opencode/final-validation-20261022，不改生产。
- 下一动作：D16完成→保存四例此SHA完整record/replay与business failure baseline→最小修复D01稳定op/site dirty closure与Claim absent proof gate+regression→新full freeze。不要旧cassette冒新record；D01剩余28不足一整轮平均calls，必须如实标预算限制，不增加预算。最新用户要求后续≥5完美合同+全前后端+性能，不能因此放松验证或伪称完成。

## 最新用户补充（2026-10-22）

- 当前最终验证任务完成后，用户要求继续组织多个agent自行推进后续修复/前后端逻辑检查，中途不自停/不询问，目标至少5份真实合同准确完整修改且单份耗时合理，为次日展示准备。不得放松原Gate、验证标准、预算/retry或伪称完美；先当前Gate再推进后续。
- 当前runtime编辑未冻结：Test agent正在修Architecture复现CROSS-001（compose任意replacement子串自授权负面review），Recovery agent正在修CROSS-002（Sweep已有target/no-plan被classify送TARGET）。Architecture只读反例交叉验证。完整1019pass/6skip是两条HIGH修复前，修后须完整实跑。

## 最终冻结准备（2026-10-22，优先于以下历史）

- 再次fetch/checkout/pull，HEAD22c15aa，remote4f3229d，ahead1；所有已有改动/证据保留。机器身份符合AGENTS规定。
- Architecture/Test/Recovery源码修复结束，正在完整重跑pytest；第一次1018passed/1failed/6skipped为末次编辑竞态，当前单项已通过；最终全量日志/tmp/fundlex-pytest-final.txt，exec session54854（查询实际状态）。compileall/diff-check通过。
- 未冻结/未push，未新live。接下来完整通过→commit runtime→新独立root四例record/replay，剩余预算继续扣：D01 63HTTP/$0.5076924，D02 142/$0.5373252，D11 138/$0.5445408，D16 144/$0.53912895。
- 当前Gate仍FAIL/PENDING，Business旧artifact问题已通用修复，但需最终新SHA artifact/四Reviewer验收；不得替换旧cassette。

## 最终证据收口接续（2026-10-22，优先于以下历史）

- 当前分支refactor/recovery-architecture；HEAD 22c15aa（未push）；fetch→checkout→pull已再次完成，remote仍4f3229d。本轮开始工作区已有ACTIVE_HANDOFF/runner修改和untracked全部evidence，已保留。
- 四例22c15aa live record均完成：D01 53/$0.04782，D02 47/$0.0496368，D11 51/$0.04332405，D16 43/$0.04055925；均incomplete、24 TRUE、TRUE→NOT_APPLICABLE=0。含旧4f3229d失败录制累计281HTTP/$0.27131265；每case192/$0.60总限额不增加。新录制前须继续扣除D01累计129、D02 50、D11 54、D16 48。
- 四例实际DOCX全部存在；programmatic source+FINAL EDIT SET→final零差异，final零修订；Business独立确认redline接受=final/拒绝=original均0差异。现有4例artifact可用作failure regression，不能证明后续新SHA。
- Business审查 `docs/evidence/final-validation-20261021/revalidation-22c15aa/summaries/business-review.md/json` 报BLOCKER1/HIGH3：delete residual虚假PASS与G16 duplicate只证一份、G11 explicit ONE_OF nested重复写、G22目标截尾留下“配。”、unsupported audit/sweep falseblock。细节FL-D142已更新。
- 主agent已修scope_map用set导致跨进程rule order变化/Inventory cassette miss，保Guide顺序。3个不同PYTHONHASHSEED context SHA一致已独立验证。新增tools/compare_frozen_replay.py比较facts/scope/targets/attribution/obligations/plan/replay/delivery/recovery和实际DOCX文本，检查0HTTP。
- 活跃agent：architecture_review负责effects.py/Claim跨段residual、原文duplicates独立siteproof，continuation regression先失败（joint绑定后单段语义再次False），现agent报告已修并在跑全组和四例Claim stage；test_review负责recall.py/recall_pipeline.py的G06 composite site guard、G17 sweep semantic、G11 ONE_OF绕过atomic先merge、G22 fuzzy同段句尾重绑定（最多12 chars且句界证据），新tests已82passed/1deselected（唯一失败属architecture正在修）；recovery_final_review独立审查真实history与源码，未交报告；business_review完成并idle，最终新SHA四例待复审。不要并行编辑同一agent所管源码/集中记录。
- 未完成：effects全组/四例旧artifact当前Claim离线重算；BR004其余G02/G04/G18错误facts意见/G05无备案证据仲裁；完整pytest（最终代码必须重跑）；冻结提交新SHA；以剩余额度新根目录四例record（不要旧cassette补位）→全replay0HTTP+semantic比较→D16六stage/revision selection→四Reviewer复审→Gate→证据提交push。不部署，不跑20/514，当前Gate FAIL。
- 运行中没有live任务；最新pytest运行已退出。系统Python3.6不可用，所有命令用.venv/bin/python。凭据只从sudo读取env到record进程内存，不输出/入库。现证据目录约40MB，安全模式扫描未见API key/Bearer；实际提交前再查。
- 当前运行代码未提交（git status为准），targeted回归仅局部，不可用992passed旧SHA当新证明。本环境无手动context压缩工具，已持久化本断点，接续优先读本段+FL-D142。

## 冻结版本与真实重录（2026-10-21，进行中）

- 运行代码已提交 `22c15aa4d8d736f2a2fc46a29bc3ed8611475f2f`，未push/未部署。该SHA完整实跑992 passed/0 failed/6 skipped/196.14s，compileall/diff-check通过；日志 `/tmp/fundlex-pytest-22c15aa.txt` 和 revalidation目录logs。
- 两处P0 occurrence、Audit同址sibling identity、record/error replay、class-set display、G05标点、incomplete append anchor、Audit dirty-site/no-progress已修，有新增regression；Architecture/Recovery复审代码范围BLOCKER0/HIGH0，业务实际artifact待验证。
- 新证据 `docs/evidence/final-validation-20261021/revalidation-22c15aa/`，index绑定SHA和剩余额度。旧四例保留原位。runner `tools/validate_frozen_case.py <case> record|replay --root <directory>`。当前外层exec session **68057** 顺序D16→D01→D02→D11 record（须用write_stdin轮询，不用functions.wait）；进程是否仍运行以ps为准。未增加模型并发/retry/总预算。
- 每case后续限额已扣首轮：D01 116 attempts/$0.5555124；D02 189/$0.586962；D11 189/$0.58786485；D16 187/$0.5796882。真实模型deepseek-v4.1-flash/上下文32000/output8000继承配置，凭据只内存。
- 增加evidence `review_artifacts.py` 可独立逐段对比source→final plan→DOCX并生成TRUE obligation证据表（无模型）；实际结果尚待。下一步：等待record、artifact复核、四例零网络full replay与D16六stage/revision selection、四Reviewer实际证据复审→Gate→提交push。不得旧bundle补齐或将无artifact填0安全错误。

## 最终验证接续（2026-10-21；优先于以下历史）

- 用户最新任务是最终验证、证据收口、最小修复、独立审查、Gate、提交 push；不是旧“只push”任务。起始 HEAD `4f3229d901bda33332a8abee3d909b7550f07ff0`，branch `refactor/recovery-architecture`，已fetch/checkout/pull，起始clean。
- 全量fresh离线 976 passed / 0 failed / 6 skipped / 199.41s；compileall通过。日志/四例真实证据 `docs/evidence/final-validation-20261021/`。
- 四例record首试均not_generated，无最终DOCX：D01 cassette conflict；D02/D11/D16 inventory output truncated。87 calls / $0.08997255；本轮总预登记768/$2.40、每case192/$0.60，后续扣除已用，不加预算。未部署、未改生产配置/账本、未跑20/514。
- FL-D142登记全部发现。主agent正在做bounded truncation split、cassette full-request复用/错误录制、无凭据replay、Stage参数/边界、occurrence dedupe、class-set label最小修复。源码未提交，`git status --short`为准；新tests fixture尚待通过；必须修后全量重跑。
- 三位独立Architecture/Recovery/Test reviewer已完成初审并发现BLOCKER/HIGH；Business Reviewer运行中，后续实际artifact需复审。没有运行中的record进程。
- 下一动作：完成小修/回归→提交代码冻结新SHA→以剩余预算独立录制四例（保留首试）→full/stage零网络replay→DOCX逐operation证据审查→四Reviewer复审→Gate→证据提交push。不能用历史artifact替代，不把缺验证当0缺陷。
- 无手动压缩工具；断点已持久化。所有凭据只在进程内读取，不打印/入库。


## 最新状态（2026-10-21，按用户要求仅提交和推送）

- 用户最新指示：“我只是让你继续推送而已，不用做别的”。本次停止其余开发、真实模型验收与部署，仅提交并推送当前 `refactor/recovery-architecture` 工作区。
- 推送前基线 HEAD `00312e3bae7047c4ca04762d8f2739bd130894ed`；fetch → checkout → pull 已再次完成，origin 未变化；工作区包含本轮最终收口改动。
- 本次审查补充：移除 Sweep 的旧 rule-level satisfied/first-required-text 关闭路径，统一由 operation/site artifact proof 仲裁；静默 re-sweep 不再单独关闭 finding；删除 Projection 未使用的旧 satisfaction helpers。针对性回归 **77 passed / 22.59s**，输出 `/tmp/fundlex-final-review-tests-2.txt`；`git diff --check` 通过。
- 历史完整离线回归 **977 passed / 6 skipped** 适用于上述审查补充之前；补充后未重新跑完整回归。中间误删 `_document_compact` 引发 NameError，已恢复并由 77 项回归验证；`_finding_evidence` 是本次有意移除的旧独立判断路径。
- 本次 live 调用/费用 0，未部署。真实合同 Frozen record 与真实工作台交付仍未完成，不能将推送或离线验证宣称业务验收完成。
- 源码、测试与集中问题记录随同一次提交；实际提交 SHA 以 `git log -1` 为准。


## 最新接续断点（2026-10-21，离线回归通过；最终收口尚未验收）

此段优先于下方历史断点；下方 883/59、90/4 等结果只保留历史，不代表当前工作区。

- 目标/约束：完成用户 1—40 项整链路收口；不降低 Validator/Claim/G02/G04、不忽略 residual、不加 retry/模型预算。用户末尾只写了 Stage Replay 标题，因此现有接口按冻结阶段输入实现，不杜撰额外规格。
- branch `refactor/recovery-architecture`；HEAD `00312e3bae7047c4ca04762d8f2739bd130894ed`。起始 fetch→checkout→pull 已完成且当时 clean；本轮继续时已重读 HEAD/status。全部工作区改动未提交、未推送、未部署，`git status --short` 为准。
- 最新完整离线测试：`.venv/bin/python -m pytest tests -q` → **977 passed / 6 skipped / 2 warnings / 199.30s**，输出 `/tmp/fundlex-final-offline-3.txt`。`compileall`、`git diff --check` 通过。第二轮曾 973 passed/1 failed（Worker 停机竞态），已修复并完整重测。针对性 dirty-site/Frozen 测试 33 passed，主链路 99 passed。
- 完成并验证：Guide Gate/显式历史 ONE_OF、TRUE completion invariant、Primary class-set completeness、排除双认证、Applicability 前置、site-scoped OperationEffectEvaluator/Claim/Projection、Audit 无证据意见仲裁、final ledger 重算、四层 Claim root-cause 路由、Final Sweep 至多两轮、相关站点签名复用与冻结回放。
- 本次新增实质修复：Audit missed-target 按 operation/site 去重；Sweep 不借其它 site 的 proof；delete residual site-first + 无关邻段反例；append 不再借用全文政策证明或邻段锚点，摘要独立发现；同段 deterministic edits 合为 atomic paragraph 并保留 component 账本；Claim 按 FINAL parent edits 重建实际产物；Joint Compose 同 rule 独立 operations 全部保留；Claim generation recovery 只重算 dirty sites，execution 复用原计划。见 FL-D140。
- 新文件：`fundlex/fact_evidence.py`、`qualification.py`、`frozen.py`、`stage_replay.py`、`generation/effects.py`、`generation/atomic.py`、`tools/replay_stage.py` 与两组新增测试。已迁移旧测试中的隐式 ONE_OF/无证据关闭/章节末尾 append/缺少 operation identity 等断言；未改独立评测 gold。
- Guide 运行门实测：source `b77be53c3439d785a9ffad0f09d8d03ba74f7722397576b999ae6f5dd6eef895`，document `45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7`，22 rules/34 operations。
- 模型/预算：本轮 live 请求 **0**、费用 **0**，无新生产任务、无子 agent、无运行中的本轮进程；未改 `/etc/fundlex-recall.env` 或生产账本，未跑 514。机器主机名/实例/内网均已核实，curl ifconfig.me 返回 IPv6 出口，不把内网当其它机器。
- **仍未完成**：最终变更审查（尤其认证裁定来源、真实 wording/duplicate 完整覆盖、Audit/Sweep 共用 evaluator 的剩余旧 helper）、真实合同 Frozen record/replay 验收、真实工作台登录→上传→Worker/模型→修改 DOCX→结果页→授权下载→实际文件/红线/报告哈希核验；没有真实 complete 验收，不能宣称总体完成。
- 下一条动作：先审阅当前 diff 与 `docs/RECOVERY_FINAL_AUDIT_20261021.md`/FL-D140；确认冻结回放目录与现有预算账本，在现有授权/预算内安排一次真实工作台验收并录制 cassette。失败时从冻结阶段回放定位修复，不重复 live 调试；若预算/服务阻塞，如实登记，勿增加预算或绕过发布门。
- 上下文：本环境没有可调用的手动压缩工具；已持久保存源码/测试/断点，下一上下文从本段继续，不重复审计或旧真实调用。


## 本轮实施补充断点（2026-10-21，未完成/未部署）

- HEAD 仍为 `00312e3bae7047c4ca04762d8f2739bd130894ed`；全部最终收口改动未提交，`git status --short` 可核对。无子 agent，live 调用 0/费用 0。
- 已完成针对性一批 146 passed；后续 pipeline 37 passed/2 failed 属旧 fixture（缺 operation metadata、故意漏 D 类），已迁移为认证 IR 与不完整集合阻塞测试。该结果不代表当前全部代码通过。
- 新增/接线：Guide certification、Primary class-set proof、exclusion 独立认证、Applicability 前置、site-scoped effects/Claim/Projection、final ledger components、模型 cassette 与 Stage Replay。
- 最新正在验证：消除 Claim 的文字/单 operation 归因 fallback；Audit 无引文意见用 operation proof 仲裁；audit site signature；Claim 四层 root-cause 路由；执行故障复用计划；Sweep 移至 Claim Recovery 之后，最多两轮；FINAL_EDIT 过滤后重新 reconcile。
- 当前测试：`/tmp/fundlex-proof-recovery-tests-2.txt`（运行状态需核实）；前一轮 90 passed/4 failed，包含已发现 Sweep 引用旧 reaudit_only 和旧断言，尚待再次核对。
- 未完成：site-first delete residual、Audit missed operation 去重、显式 Guide schema/业务批准边界核查、Frozen 完整 boundary serialization/阶段实际回放、dirty recovery/no-progress 全链路和完整回归，以及最终真实工作台交付。
- 下一动作：查看当前测试文件并修复；为四层 recovery/ledger same-operation 不同 site/Scope correction/回放零网络增加实质性回归。禁止把离线通过或历史真实 incomplete 当作最终交付。

## 最新任务（2026-10-21，最终收口，进行中）

- 用户最新指令：完成整条 Guide→Facts→Applicability→Target→Plan→Artifact→Audit/Claim/Sweep→Recovery→Delivery 收口；先完整审计后实施。详细审计/分批实施账本：`docs/RECOVERY_FINAL_AUDIT_20261021.md`。用户消息末尾为“40. 新增 Stage Replay”（未附具体阶段接口）；按冻结输入+确定性阶段 CLI 实施，不虚构额外要求。
- 起始同步已完成：`git fetch`→`git checkout refactor/recovery-architecture`→`git pull`；HEAD `00312e3bae7047c4ca04762d8f2739bd130894ed`，branch `refactor/recovery-architecture`，working tree clean。
- 硬约束：不降低 Validator/Claim、不中断 G02/G04 occurrence safety、不把 failure 降 warning、不忽略 residual、不减少规则、不增 retry/预算。不用反复 live E2E debug。后续最终端到端仍须真实路径验证，不宣称离线替代。
- 已做：全链路审计表已保存；未启动新 live 模型调用；未部署。上轮理解项目时测试 939 passed/6 skipped 属旧 HEAD，当前基线历史记录为 942 passed/6 skipped，不挪用为新改动验收。
- 发现：内置 Guide 10 findings 的历史裁定缺 finding_id/approved/双 SHA，内置 document_sha 与实际 payload 不一致；Primary Facts 没有完整 class_set；Projection 仍多处 TRUE→NOT_APPLICABLE；Claim append/replace 用 after_full 跨 site 借证据；Applicability resolve 晚于 Inventory。
- 运行环境：同台 Linux 云服务器，API `127.0.0.1:8010`，公网 `https://fundlex.club`；本次 health 返回 401，匿名不可用是认证行为，不是监听失败。FL-D139 待更正。
- 预算/账本：本轮 live 请求 0，费用 0；不改生产 `/etc/fundlex-recall.env` 或 `/var/lib/fundlex/`。不自行跑 514。
- 下一动作：实现 certified guide + 显式 group semantics + TRUE invariant；继而 facts set completeness、统一 operation/site effects 与 frozen replay。每批保存 tests/剩余项；上下文不可观测，保守分段接续，不虚构压缩完成。
- 进程/agent：本轮无子 agent；既有 D02e 后台若仍运行属于前序会话，不重启或重复花费。

> ## ⚠️ 机器身份（先读这一段，禁止凭内网地址判断机器）
>
> **当前工作机 = 云服务器**，即本仓库所在处：
>
> | 项 | 值 |
> | --- | --- |
> | 主机名 | `iZf8zemhifedxdow1zefr0Z` |
> | 公网出口 IP | `8.155.130.168` |
> | 内网网卡 IP | `172.28.217.241`（**同一台机器**，不是另一台开发机） |
> | 区域 / 实例 | `cn-heyuan` / `i-f8zemhifedxdow1zefr0` |
> | 工作区 | `/home/opencode/fundlex`（专用用户 `opencode`） |
> | 应用部署 | `/opt/fundlex-recall-first`（systemd `fundlex-recall-api`/`fundlex-recall-worker`，API `127.0.0.1:8010`） |
> | 公网 HTTPS 入口 | **`https://fundlex.club`**（`www.fundlex.club` 同；Let's Encrypt 证书，nginx/宝塔反代 `127.0.0.1:8010`，80→443 跳转） |
>
> **本文其余部分的“本机 / 笔记本”一律指已停用的 Windows 开发机，绝不是当前工作机。**
> 接续 agent 开工前先跑一次身份采集：`hostname`、`ip -4 addr`、`curl ifconfig.me`、
> `curl http://100.100.100.200/latest/meta-data/instance-id`，用事实确认自己所在的机器。
> （本机器块为 FL-D061 的处置结果，见集中问题记录。）

更新：2026-10-16（服务器开发主副本 `/home/opencode/fundlex`，接续 agent **第 12 轮**：A/B 遗留规则集退出运行时，能力接口收敛为 engine 契约，交付语义改由指引版本状态决定，FL-D093/FL-D094/FL-D095，生产端到端验收通过）。规则：50% 整理、60% 前完成压缩/交接；本文只记状态与下一动作，不写密码。

> **第 12 轮要点（A/B 下线）**：见 [`docs/LEGACY_RULESET_RETIREMENT.md`](LEGACY_RULESET_RETIREMENT.md)。
> 运行时仅服务指引绑定的 recall-first；`capabilities` 只返回 `engine` 对象；`/api/tasks` 只接受 `engine_id`（传 `ruleset_version` → 422 `RULESET_RETIRED`）；`/api/batches` 创建 → 410；遗留任务只读且标记 `legacy`。
> A/B 代码与规则文件**保留**（测试与离线评测直接导入管线），但不再被运行时引用。
> 相关提交：`5615609`（方案）→ `beee73e`（后端收敛）→ `2b32e40`（测试）→ `93196d9`/`012ba18`（前端与遗留标注）→ `67410b3`（收尾）。部署副本与仓库一致，服务 active。

> **编号更正（FL-D077，2026-10-15）**：集中问题记录曾有 5 组编号重号，已把后出现者改为新编号（保留首次出现的原编号）：
> `FL-D057→FL-D072`（sweep 误报 G02/G04）、`FL-D058→FL-D073`（无服务费结论）、`FL-D068→FL-D074`（评分器短锚误判）、
> `FL-D069→FL-D075`（G17 跨段删除）、`FL-D066→FL-D076`（Codex bwrap）。
> **注意**：本文下文第 5/6 轮的历史叙述写于更正之前，个别处仍写旧编号，含义以更正后为准；新增条目一律先查重再编号。

## 当前断点（2026-10-20，Recovery 架构改造，本地已验证/未发布）

- **分支**：`refactor/recovery-architecture`（基于 `a2905ac` + REITs/ETF feeder 提交 `374440a`）。本轮架构提交：`f98d95c` 模型角色、`69a6a24` Obligation IR、`3e257f0` Validator 硬门、`c6bbf1d` Recovery、`838c9a6` 管线接线；文档提交待补。
- **完成内容**：`docs/RECOVERY_ARCHITECTURE.md` 与集中问题 **FL-D133**。核心为 obligation-first ledger、Primary/Review 独立角色、tri-state applicability、focused fact recovery、T3 locator、Joint Compose、Validator hard gate、claim replay 边界证明、统一 Recovery/FailureClass、用户三态交付摘要。
- **测试**：全量 `pytest tests -q` → **872 passed / 6 skipped**。离线 validator shadow（round14-12）：19 例 / 222 段 / **0 hard FAIL**。
- **真实模型（临时账本 `/tmp/opencode/realcheck.sqlite`，未触碰生产账本）**：
  - **D01 曾出现 false_complete，已修复门禁**：早期一版报 `complete_with_notices`（27 calls），独立 Business Reviewer 复核最终 DOCX 发现 G17 第二句仍留在 p760、G15 正文/摘要处理不一致。新增 delete-only 逐句残留检测、重复条款副本一致性、G05/G06/G01/G03 目标锚点后，D01 被如实阻塞为 partial（96 calls / 约 $0.052；audit 另发现 G09 第二处措辞缺失、G01 追加位置错误、G11 变体残留）。
  - **D02**（ETF 联接基金）：`eligible/open_regular`；116 calls / $0.0615；G05 compose 固定文本缺失 → partial（诚实失败）。
  - **D03**：32 calls / $0.0222；G06 复合目标未解决 → partial。
  - **D11**：99 calls / $0.0658；旧版 false_complete 被新门改为 partial（G15 误绑托管费、G09 第二处措辞缺失）。
  - 临时账本合计约 **963 requests / $0.5792**；以上为 agent 真实调用，生产账本未动。
  - **结论**：新架构已能发现旧版 false_complete，但尚未取得“最新硬门下真实合同 complete”的验收样例。Final Architecture Reviewer 的 G05 satisfied-target 隐藏 delete、G11 ONE_OF 被新文误判残留两个 blocker 已在 `039519f` 修复并有回归测试。
- **独立审查**：Architecture Reviewer 提出 5 个 BLOCKER + 5 个 HIGH；已修复 scope 遗漏静默、plan not_applicable 覆盖 TRUE、Validator/Replay flag 开关、claim recovery 旧 audit/sweep、类别枚举前缀、单 completed 掩盖 siblings、infra stop 吞咽。保留限制见 `RECOVERY_ARCHITECTURE.md` §10：无目标规则 T3 默认关闭、audit context 分批未实现、514 全量未跑、G09/G15 业务残留、前端未展示新字段。
- **已发布（2026-10-20 20:37 CST，快照 commit `0fae88e`）**：`bash tools/deploy/publish_workspace.sh` 成功；`fundlex-recall-api` / `fundlex-recall-worker` active；`/opt/fundlex-recall-first` 与仓库 `obligations.py` / `recovery/orchestrator.py` / `models/roles.py` / `recall.py` / `recall_pipeline.py` / `frontend/app.js` sha256 一致；`/api/capabilities` 200。生产 env：`FUNDLEX_GENERATION_STRATEGY=registry`、`FUNDLEX_MODEL_MAX_OUTPUT_TOKENS=8000`。
- **真实工作台端到端（已通过）**：默认入口 `POST /api/tasks`（`engine_id=recall_first`）→ 上传 D01 → seal → 真实 Worker/模型 → `/revisions` 19 条全部映射、目录保留、14 页 → 拒绝第 1 条 + 接受其余 18 条 → 下载 `selected_final` **136125 bytes / sha256 `efd9f20c59fddb96224876782e9b73f5c0670201440947aeeac4e90f62faeb1f`**，残留修订 0，被拒条目恢复原文，接受条目保留替换；`accept-all` 19 条成功；`working_final`/`working_redline` 仍可下载。任务 `db67ed71…`、文档 `9a0810a9…`、批次 `b72d9b42…`；交付状态 `incomplete`（如实，不冒充 complete）。
- **子集回归（最终代码，用户授权只跑部分，不跑全量）**：
  - D01：partial；93 calls / $0.0516；claim replay 17/17 verified；残留问题集中在 G05/G01/G08 审计与 G06/G15/G17 查漏（具体见任务报告）。
  - D02（ETF 联接基金）：partial；56 calls / $0.0636；claim verified 17 段；TARGET 7 / GENERATION 1。
  - D11：partial；125 calls / $0.0906；claim 失败集中在重复正文/摘要副本（DUPLICATE_SITE_UNEDITED）与 G15/G17 残留。
  - D16：partial；61 calls / $0.0554；G06 复合目标、G14/G16/G18/G22 audit pending 等。
  - 对照 round14-12：D02 原先可能被排除，现正确进入处理；D11 旧版报 complete 但属 false_complete，现 blocked；D16 旧版 integrated complete，现因更严格 target/audit 门 partial（需人工复核是否为过度阻塞）。
- **下一动作**：① 用户自行跑全量 514（agent 不自行跑）；② 修 G05/G06/G15/G17 目标与审计残留、D16 过度阻塞复核；③ 用子集结果调优后再发布；④ 全量/留出验收与最终报告。
- **预算/账本**：生产账本 `/var/lib/fundlex/model_budget.sqlite` 本轮未读写；agent 使用临时账本 `/tmp/opencode/realcheck.sqlite`（约 $0.45）。

## 当前断点（2026-10-19，前端改造第一批，已本地验证并发布）

- **范围**：全局 Toast（修复 FL-D121 成功提示不可见）、面包屑、页脚 + 版本号（`capabilities.app_version`）与帮助弹窗、筛选 Chip、任务列表“合同份数/成功异常/进度”、任务详情统计条与异常行高亮、批量导入进度条/异常标红/替换/条件跳转、修订审查 A/R + Toast + 上一份/下一份、指引问题展开 + “重新解析（自动修复）”。
- **文件**：`frontend/index.html|app.js|app.css`、`fundlex/api.py`（仅 `app_version`）、`tests/test_tasks_api.py`；问题状态见 FL-D121 / FL-D126 / FL-D127 / FL-D128 / FL-D129。
- **验证**：全量 `pytest tests -q` → **752 passed / 6 skipped**；本地 dev 实例真实浏览器四组：`ui_smoke` 25/25、`ui_review` 20/20、`ui_guide` 10/10、`ui_redirect` 6/6，0 页面/控制台错误。
- **已发布（2026-10-19，commit `c2851a8` 快照）**：`bash tools/deploy/publish_workspace.sh` 成功，api/worker active；`frontend/index.html|app.js|app.css`、`fundlex/api.py` 与部署副本 sha256 一致；`https://fundlex.club/api/capabilities` 返回 `app_version=0.1.0`；首页资源版本已变化（`app.js?v=35788dcc…`）；生产匿名页真实 Chromium 检查 0 页面/控制台错误。发布快照同时包含并行 agent 的引擎提交 `839ffe0`（其自测全量通过；如该引擎变更需单独批次验证，由对应 agent 继续）。
- 下一动作：用户在真实登录环境复验第一批交互；第二批待拍板项（月度统计/消息持久化/全局搜索/重试/审计）见集中问题记录 FL-D122～FL-D125。

## 当前断点（2026-10-20，任务总览改版方案 B，本地验证；**未发布**）

- **需求**：侧栏「批量导入」→「新建任务」；右上角用户区**不改**（产品负责人更正）；批量总览头部卡片（BATCH OVERVIEW、本月累计处理/平均秒数、完成率进度、新建/刷新）；5 个指标卡（本月处理合同/完成率/待处理/平均时长/异常）；「我的任务」表格 + 指引名称/筛选 + 「查看」；不改配色/Logo/全局基础样式/不新增图表。
- **后端**：`GET /api/tasks/stats?month=YYYY-MM`（owner 范围，CST 月边界；处理数/完成率/待处理/进行中任务/异常/平均秒数/环比）；`documents.started_at|finished_at` 迁移与 claim/finish/terminal retry 写入；`GET /api/tasks?guide_version_id=...` 筛选。
- **前端**：`frontend/index.html|app.js|app.css` 总览重构；用户区未改；指引名称由 `/api/guides` + `guide_snapshot.version_id` 映射；数值接 stats 接口，加载中 `—`。
- **验证**：全量 `pytest tests -q` → **875 passed / 6 skipped**；本地 dev 真实浏览器 **23/23**（总览数字、5 卡片、指引筛选、Chip、刷新、0 控制台错误），截图 `/tmp/opencode/ui-batch2/overview.png`。
- **未发布**：工作区仍有另一 agent 未提交的 `fundlex/generation/template.py`、`fundlex/recall.py`、`tests/test_recall_core.py` 等引擎改动；现在执行 `publish_workspace.sh` 会把未协调改动一并带入生产，故本轮只提交本功能文件，待并行改动收敛后统一发布。
- **下一步**：并行引擎改动提交/发布后统一发布，并在生产真实登录页复验总览；如需要跨任务批量导出，另立后端接口。

## 当前断点（2026-10-18，模型供应商切换 + 外部模型复查核验）

- **供应商切换（按用户指示，先不切回）**：原 `OpenCodeGo` 周限额耗尽（429 `GoUsageLimitError`，retry-after ≈19.5h，见 FL-D111）。已改为 **DeepSeek 直连**：
  - `/etc/fundlex-recall.env`（备份 `/etc/fundlex-recall.env.bak-20261018-132608`）：`LLM_PROVIDER=deepseek`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`；API key 只在 env 文件，不写仓库/文档/聊天记录。
  - 请求选项保持 `{"thinking":{"type":"disabled"}}`（实测该端点接受且 `reasoning_tokens=0`）；`FUNDLEX_MODEL_MAX_REQUESTS` 20000→40000，`FUNDLEX_MODEL_MAX_COST_USD=50` 不变；单价按目录价输入 $0.15/M、输出 $0.60/M。
  - 2026-10-18 13:26 CST 重启 `fundlex-recall-api` / `fundlex-recall-worker`；`/api/capabilities` 200；独立账本探测（`/tmp/opencode/upstream_probe2.py`）`UPSTREAM OK: {"ok": true}`。
  - 账本（切换前）：`17462` requests / charged **$14.4908**（上限 40000 / $50）。**用户明确指示前不切回原供应商。**
- **外部模型复查核验（已完成，未改引擎）**：对另一模型对核心链路的分析逐条对照当前代码与真实批次，新增 4 条记录（FL-D112～FL-D115）：
  - **FL-D112（新，最高价值）**：recall 生成内容复核闭包返回 bool 且 `validate_edit_plan` **忽略返回值** → 所有 `_component_ok` 复核（composite/fragment/variant）实际未生效；同时 `_composite_part_slice` 用 `display_text` 解释 compact 偏移，一旦校验生效会误拒带空白锚点的 composite。两处需一起修，属交付校验语义变更，待裁定。
  - **FL-D113（新）**：sweep 的按窗口规则范围在“该窗口 section 无任何规则映射”时为空 → 整窗 findings 被丢弃；round11 实测 14/80 个窗口零规则（D02/D12/D16 等每案 1–2 个盲窗）；约 69% section 字符所在 section 未被规则映射（含部分摘要）。待裁定 + A/B。
  - **FL-D114（新）**：未核验 Facts 仍参与 `excluded_by_fund_type`（整份结束）与 `condition_matches` 分支；round11/12/13 有 3/4/6 个案例含未核验引文，多为省略号/跨段导致的验证假阴性，`FUND_TYPE_QUOTE_UNVERIFIED` 每轮 1 例但均为 `open_regular`（未排除）。待裁定。
  - **FL-D115（新）**：sweep finding 以“重扫未再报”判 `resolved`，无针对性产物证据；round11 resolved 18 / pending 15，round12 8 / 19，round13 8 / 16。待裁定。
  - **复查中被证伪/夸大的项**：`structure_index` 80 段上限在 514 份语料中**不可达**（groups 中位 26、p90 30、最大 34，0 份超 80）；`facts_context` 的 `break` 在 29500 字符预算下抽样 120 份 **0 份截断**；target identity/复合删除/无 ledger 默认 planned 三点**已在 FL-D110 记录待决**，非新问题。
- **本轮已实施（2026-10-18，commit `ebcd9de`，尚未发布）**：按 [`REVISION_PLAN_2026-10-18.md`](REVISION_PLAN_2026-10-18.md) 完成 FL-D112 / FL-D113 / FL-D114（引文核验部分）与 FL-D110 缺陷 2/3/4：
  - 内容校验真正接线（False → 拒绝；坏 edit 丢弃并记 `RECALL_EDIT_CONTENT_UNVERIFIED`，其余继续）；composite 坐标改用 `compact_offsets` 并按整段校验，follower 不再走旁路；fragment 记录并重放 `fragments` 轨迹；variant/span-delete/composite_replace 证据与生产者对齐；`content_check_factory` 查找键加入 span。
  - target 身份改为全文 span hash；复合删除逐 part 校验；缺 ledger → `unresolved/LEDGER_MISSING`。
  - sweep 新增 `blind_windows` 记录 + 空范围窗口回退 mandatory 规则。
  - `_verify_quote` 支持省略号分段与跨段边界（fund_type 排除策略未改）。
  - 测试：新增 9 项；全量 **680 passed / 6 skipped / 1 failed**（唯一失败为既有 references 缺失项）。
- **下一动作**：
  1. **`p6-dev-round14-03` 基线已完成**（DeepSeek 直连、旧引擎）：dev-only **218/236 = 0.9237**（kept 11 / not_executed 7），6 报 complete / 10 实际 complete / 1 false_complete；1019 calls / $0.7372。对照 round11 dev-only 225/236 = 0.9534（旧供应商）。**注意 FL-D116**：此前 218/347 = 0.6282 与 225/347 = 0.6484 是评分器把 111 个未运行留出目标计入分母导致的低估；`p6_score.py` 已改为默认只评本次批次实际运行的 case（`--group run`），并支持 `--group dev|holdout|all`。
  2. 修正版 `ebcd9de` 已于 2026-10-18 14:16 CST 发布（部署文件 sha 与仓库一致，服务 active）；**`p6-dev-round14-04` 已完成**：dev-only **220/236 = 0.9322**（kept 10 / not_executed 6），7 报 complete / 11 实际 complete / 1 false_complete；1008 calls / $0.7536。对照 14-03（同供应商、旧引擎）218/236 = 0.9237：**+2 目标，无回归**；`RECALL_EDIT_CONTENT_UNVERIFIED` 两轮均为 **0**（校验接线未造成拒绝），14-04 记录 **16 个 blind_windows**。
  3. 已修 FL-D117 的 delete 路径（satisfied replace 不再压制仍残留的 delete survey），单测通过；待发布后跑下一批验证。模型 target 的 operation 粒度覆盖仍待改造。
  3a. **2026-10-18 追加（commit `61e210c`，已发布）**：operation-aware 覆盖键 `(rule_id, operation_key, location)`（含模型 target 与 fuzzy delete）、D115 evidence-gated finding closure、unverified `fund_type` 不排除且禁止 complete、零规则 blind window 回退全规则；全量 `pytest tests -q` → 686 passed / 6 skipped / 1 failed（既有）。发布后跑 **round14-06** 对照 round14-04（220/236）。
  3b. **2026-10-18 更新**：round14-05（仅 FL-D117 精确补丁）dev-only **220/236 = 0.9322**（kept 10 / not_executed 6），reported complete 2 / actual 11 / false 1；1240 calls / $0.9053——目标率持平、complete 更保守、成本 +23%。`61e210c` 已发布（部署 sha 一致）。
  3c. **2026-10-19 更新（外部阻塞 + P0 修复）**：DeepSeek 直连账户 **HTTP 402 `Insufficient Balance`**（直连复现）；round14-06 在 D02 触发 `BATCH_ABORTED MODEL_CIRCUIT_OPEN`，**批次作废、不得评分**。旧供应商 OpenCodeGo 周额度**已恢复**（带 session 头探测 200）；按用户“等指示再切回”的约定**未自行切回**，等待“充值 DeepSeek / 允许切回 OpenCodeGo”的决定。外部复查指出的 4 处漏接已修（commit `9ae799a`）：`_collect_targets` 只做精确去重、unknown operation fail-open、`_delivery_complete(unresolved)` 纳入 `coverage_gaps`、D115 三边界（`location_gone`、`wrong_text` required、`unaddressed_requirement`）；全量 **689 passed / 6 skipped / 1 failed**（既有）。**尚未发布**；供应商恢复后发布并跑 round14-07 对照 14-04/14-05。
  3d. **2026-10-19 09:16 CST 已切回 OpenCode Go**（新 key 仅在 `/etc/fundlex-recall.env`，未入库/文档；env 备份 `…bak-20261019-091621`）；`9ae799a` 已发布（部署 sha 一致）、capabilities 200、独立账本探测 `UPSTREAM OK`；**round14-07 运行中**。
  3e. **2026-10-19 更新**：round14-07 在 D01 触发 `PROCESSING_FAILED`（`AttributeError`，`_survey_targets_from_hits` 对 unknown 覆盖 update None）——**批次作废**；已修并发布 `03fbbfa`（改用 `_add_operation_coverage` + 回归测试），全量 **690 passed / 6 skipped / 1 failed**（既有）；**round14-08 运行中**。
  3f. **2026-10-19 更新**：round14-08（FL-D118 缺陷 1–5，同供应商）dev-only **211/236 = 0.8941**（kept 20 / not_executed 5），`RECALL_EDIT_OVERLAP` **66**（round11 为 8）、plan conflicts 38、G17 完成 2/11、reported complete 1/actual 4/false 1；1305 calls / $0.9074 —— 判定收集层去重过宽（缺陷 6）。已修并发布 `d6cc8ce`（operation-aware + unknown fail-closed），全量 690 passed；**round14-09 运行中**。
  3g. **2026-10-19 更新**：round14-09（`d6cc8ce`）dev-only **221/236 = 0.9364**（kept 11 / not_executed 4），overlaps 回到 **8**、conflicts 5、findings 11 resolved（evidence=required_text_present）/16 pending/1 unresolved；891 calls / $0.7435。剩余差距集中在 D01/D19 的 G01/G03 append（被 `absent` inventory 目标经 unknown fail-closed 丢弃）——已修并发布 `46afe2f`（wildcard synthetic 仅在 needs_edit/satisfied 位置被抑制），全量 691 passed；**round14-10 运行中**。
  3h. **2026-10-19 用户指示停止批次**：`p6-dev-round14-10` 在 D11 后被终止（runner 已 kill；最多一个在途 case 会由 worker 收尾）。**该批次作废、不得评分**；当前无运行中的评测批次，等待后续指示。
  4. 对照重点：`RECALL_EDIT_CONTENT_UNVERIFIED` 数量、`blind_windows`/`SWEEP_RULE_OUT_OF_WINDOW`、working/incomplete 比例、kept 变化；供应商切换与修正合并，作为混杂因素注明。
  5. 结果稳定后再冻结版本 → 留出 H01–H08 → 评测报告 → 打包。
- **预算/账本**：真实运行前在批次说明预登记；账本 `/var/lib/fundlex/model_budget.sqlite`（切换前 requests=17462，charged=$14.4908；上限 40000 / $50）。
- **约束**：FL-D105 Q1–Q8、FL-D104 1–19 未裁定前不改规则适用性/评分语义；合同可入库/出境（公开资料），凭据不入库/不入文档。
- **2026-10-19 追加（文档侧，均未改引擎）**：产品负责人裁定 G08-1/G08-2 属"正常替换、按合同实际类别的收费性质实例化"（登记于 FL-D104 变更记录）；裁定 `compose` 两条硬约束（固定文本逐字、不新增数字）可推翻、改由"生成+独立复核"接管（登记于 FL-D106）；同日**八项业务裁定**并入生成方案（v3：G11-1 勘误、收费性质归类、G14 直接替换、G15 删除+疑似合同有误标记、同义等同、货币基金排除、class_count 按实际类别）并更新映射文档 `B_CLASS_PROCESSING_MAP_2026-10-19.md`；新增 **FL-D119**（G08 把"赎回费率"句误当"申购"参考命中：机制已离线复现）与 **FL-D120**（"确定性优先、模型补位"方案）及其实施计划 [`GENERATION_STRATEGY_PLAN_2026-10-19.md`](GENERATION_STRATEGY_PLAN_2026-10-19.md)（v4：八项裁定 + 二次工程评审已并入）。
- **2026-10-19 实施启动（v4 Phase 0–2 完成）**：按 [`GENERATION_STRATEGY_PLAN_2026-10-19.md`](GENERATION_STRATEGY_PLAN_2026-10-19.md)（v4，已批准/实施中）完成 **Phase 0–2**，进度与验收见 [`GENERATION_V4_PROGRESS.md`](GENERATION_V4_PROGRESS.md)：`53b6d0f` registry/router/coverage 只读视图/mix 工具（flag 默认 legacy）；`a6d7e60` V1/V2-A/V2-B 影子验证器 + **FL-D119 根因修复**（模糊命中加主题翻转守卫、satisfied 尾句通道收紧）+ G11 定位回归 + 离线回放工具（round14-09：155 段校验仅 1 FAIL，待复核；`D01/p227` fixture 被正确抓为硬失败）。全量 **722 passed / 6 skipped / 1 failed**（既有）。**下一动作：Phase 3（Facts 扩展 + 三态证据），随后 Phase 4 Tier1（G14/G09/G15/G17）。**
- **2026-10-19 继续实施（v4 Phase 3–8 代码完成 + 发布；批次被用户停止）**：按产品负责人指示连续实施：`f492701` Facts 三态；`24e39d6`/`9b0fdb0` Tier1（G14 收敛/重建、G15/G17 删除前置、G09 splice）；`287be26` Tier2（G08/G11 干净整句政策替换）；`1ecd93c` Tier3 V3 独立复核 + **Artifact Claim Replay 接线**（对已写入 DOCX 重放，失败阻塞 complete）；预登记与本地真实验证见 [`GENERATION_V4_PROGRESS.md`](GENERATION_V4_PROGRESS.md)（D01 claim replay 17/17 通过；D16 composed 归零）。全量 **750 passed / 6 skipped / 1 failed**（既有）。已 `publish_workspace.sh` 发布并在 `/etc/fundlex-recall.env` 增加 `FUNDLEX_GENERATION_STRATEGY=registry`（备份 `.bak-genv4`）后重启；**批次 `p6-dev-round14-11` 经用户指示停止、作废不得评分**（runner 与守候脚本已终止；D01 在飞任务自然结束后无运行批次）；env 开关**当前仍为 registry，未回滚**（回滚=还原 `.bak-genv4` 并重启）。
- **2026-10-19 外部复查 P0 批次实施（`66265f7` + `1dd68b4`，已发布）**：按第二份源材料复查实施：**P0-A** `condition_status` 三值 + `plan_target` 入口 fact gate/Router 决策记录；**P0-B（部分）** `class_label` 保合同原文称谓（修叠字）、`service_group` 严格定义、两费皆真→CONFLICT；**P0-C** G16 组件级 satisfied（不再因"每日计提"首句误判）、**G15 `business_notices`**（"原合同可能有误"，不影响交付）接线并去重；**P0-D** G08/G11 仅裁缺失服务组子句（registry）；**P1 部分** G06/G13/G17 关键词签名、G14 扩展句补项、coverage `operation_keys` + delivery gate 读投影、claim replay 已有；另修 V3 `recall_verify` 未在网关白名单（`MODEL_TASK_UNSUPPORTED`）。全量 **773 passed / 0 failed**（references 随语料入库后既有失败亦消失）。已发布；**`p6-dev-round14-12`（dev 20 例）运行中**，完成后自动评分与分析。残余：币种维度拆分、semantic site anchor、per-operation claim replay、CI、红色盲核。

## 当前断点（第 12 轮，2026-10-16，P6 开发集真实修改评测收敛到 0.8602）

- **本轮任务**：用户指示「做二和三」——(三) Langfuse 退化为**本地 JSONL trace 兜底**，(二) 用它帮助 P6 评测优化。
- **(三) 已完成**：`fundlex/trace_sink.py`（FL-D088）。纯标准库、无网络、`FUNDLEX_TRACE_JSONL` 未设即 no-op；一合同一 trace（确定 seed）、一次调用一 generation、一条评测 score；活动文档 id 走 thread-local，引擎深处模型调用自动归入正确 trace。接线于 `model.py:_trace_attempt` + `jobs.py:_document_trace`（与 Langfuse 并列，可同开）。生产落点 `/var/lib/fundlex/traces/model-calls.jsonl`（env 备份 `…env.bak-tracesink`）。真实 20 例验证：1085 行、单条 25KB 含合同原文、19/20 trace 匹配、0 错误。分析器 `tools/evaluation/p6_trace_report.py` 把 trace 与评分按 trace_id 关联，直接产出「按规则/按阶段」失败画像。单测 `tests/test_trace_sink.py`。
- **(二) 已完成 — 用 trace 定位并修掉 3 个真实缺陷**：
  - **FL-D089 评分器误判**（commit `64dab0c`）：`appendix_present()` 因份额类别枚举差异把**已正确追加**的政策句判 `not_executed`。改为折叠枚举 + 模糊兜底逐字符步进。0.7892 → 0.8161，无引擎改动。
  - **FL-D091 append 家族缺陷**（commits `fc08350`/`c6c00aa`/`8331233`/`b78c26e`）：三层叠加——①措辞变体致盘点判 `not_applicable`；②缺 class group 时 append 被整体判不适用；③hit 被既有 `absent`/未解析目标压制。新增 `append_applicability_targets()` 确定性兜底 + 收窄 class-substitution 门限 + `override_rules`。
  - **FL-D091 类别名渲染缺陷**（commit `d900fb2`）：终稿出现 `default类基金份额`、`A类份额类基金份额`。修正 `class_label()` 剥离份额变体并丢弃占位名。
  - **FL-D089 补充**（commit `48fe3ca`）：单类别合同只应追加适用分句，评分器不再索要不存在的 C 类分句。
- **当前指标（开发集 20 例 / 236 目标）**：**0.9322**（completed 220 / kept 15 / `not_executed` **1**），目标 0.95。唯一残留 `not_executed` 是 **D07/G16**——该合同 `基金费用与税收` 章节**确无销售服务费条款**，引擎判不适用属正确。整合完成 `actually_complete` 5→8，目标 0.9（`kept` 15 为主要来源）。
- **评分器又修两处误判（同源：把「引擎做对了」读成没做）**：
  - **FL-D097**（commit `c68434d`）：删除规则的引文**跨多句**时，`_superseded_survives()` 的末句片段属于**相邻的、引擎有意保留**的条款，命中它就把已完成的删除判 `kept`。改为仅当锚点落在引文末句才计末句片段。
  - **FL-D098**（commit `1b478b2`）：删除成功后**原段落在终稿消失**，`locate_paragraph()` 返回 `-1`，而 `delete` 分支要求定位成功，于是**正确删除被判 `kept`**。改为「条款在全文已不存在即达标」。
  - **FL-D099**（本轮）：`replace` 的「新义务是否出现」用 24 字前缀精确判定，一处措辞差异（多一个「基金」、或合同真实类别 `A类、D类`）即分叉；同时标签 `old_text` 恰是修正后句子的子串，于是**正确替换被判 `kept`**。新增 `_obligation_in_region()`（规范化＋`difflib` 滑窗，阈值 0.9）作第三顺位回退。
  - 三处合计：0.8602 → **0.9322**（`kept` 32 → 15，`not_executed` 恒为 1）。逐目标核对确认**仅预期目标翻转、无误放**，并以**引擎自身审计**为独立佐证（D12/G14 仍判 `kept`，引擎审计同判未执行）。
- **剩余 `kept` 15 = 真实引擎缺陷（非评分器问题）**：G17 删除 ×5、G18 替换 ×3、G08 ×2、G11 ×2、G05 ×2、G14 ×1（D12 `RECALL_EDIT_OVERLAP`）。引擎 ledger 显示多为 `not_applicable`（作用域判定与终稿残留矛盾）或 `planned` 但未落地。
- **预算**：round2–round7 累计约 **$3.7**（单批 ~$0.52–0.70）；协议预算 dev ≤2000 calls/≤$6。
- **运维教训（FL-D096）**：**批次运行期间禁止 `publish_workspace.sh`**。已在飞批次的任务 pin 了旧 `engine_build`，重发布后 worker 校验失败 → 整批 `ENGINE_SCHEMA_MISMATCH`。round7 首批已作废留证并重跑。
- **并行协作**：另一 agent 同期推进前端（FL-D092 缓存、FL-D093/094 A/B 遗留规则集下线、HTML 呈现 + 逐条审查）。共享文档编号曾两次冲突（我的条目被并入 FL-D091、FL-D096），**改共享文档前先看 mtime，只做追加**。
- **下一动作**：① 就「优化轮次已达 baseline+7，超协议 3 轮上限；应用账本 charged $9.06 / 协议 total $10」请产品负责人定夺是否继续；② 若继续，按 `append_applicability_targets` 成例为**删除类规则**加确定性适用性兜底（FL-D100①），并单独排查 G18「替换未落地」；③ 达标前**不得冻结、不得读留出 H01–H08**。
- **预算与轮次（须如实上报）**：`protocol.json` 明文 optimisation rounds ≤3、total ≤$10；实际 baseline+7 轮；账本 charged **$9.0593**。协议指定的 per-run 来源 `report.json`（model 段）在各 `p6-dev-*` 目录下**不存在**，per-run 花费当前不可核验（FL-D100②）。

## 当前断点（第 11 轮，2026-10-16，静态资源缓存失效修复，**已生产验证**）

- **本轮任务**：用户反馈「我这里看着还是没变」——区块顺序调整已发布但页面仍旧版。
- **根因（FL-D092）**：`index.html` 以**无版本号固定路径**引用 `/static/app.js`、`/static/app.css`，nginx 也不下发 `Cache-Control`，浏览器沿用旧缓存。HTTPS 实取字节 sha 与仓库/部署一致（`bc5ac9c7d044e90d`），证明**服务端早已是新代码**，问题在客户端缓存。
- **修复（commit `64b0302`）**：`fundlex/api.py`
  - `_asset_version("app.css","app.js")` 按资源内容 sha256 生成 16 位版本标识，**每次发布自动变化**。
  - 入口 `/` 改为读 `index.html` 文本并注入 `?v=<hash>`，下发 `Cache-Control: no-store, must-revalidate`。
  - 新增 HTTP 中间件：`/static/*` → `public, max-age=31536000, immutable`（URL 带哈希，安全长期缓存）；`/`、`/index.html` → `no-store`。
- **验证证据**：
  - `TestClient`：`/` 返回 `no-store` 且引用 `app.js?v=a751d9b7f43c2426`；`/static/app.js|app.css` 返回 `immutable`。
  - 生产（nginx/`127.0.0.1:8010`）：首页含 `?v=a751d9b7f43c2426` + `no-store`；带版本静态资源 `immutable`。
  - **真实浏览器（生产、真实登录）**：16 条修订、目录 24 条 + 24 链接、拒绝 1 + 接受 15 → 下载 `selected_final` 136235 字节、**残留修订 0**、**控制台错误 0**。
  - 回归 `611 passed / 6 skipped`（排除既有基线失败 `test_rules_catalogue.py`）。
  - 已 `bash tools/deploy/publish_workspace.sh` 发布，api/worker active。
- **易错点**：若再遇「页面没变」，按「响应头 → URL 版本号 → HTTPS 实取字节 sha」三步先判定是客户端还是服务端，勿直接改代码或重发。
- **下一动作**：无阻塞。用户如仍见旧版，请**硬刷新（Ctrl+Shift+R）**一次即可清掉历史缓存；此后发布自动带新版本号，不再需要手动清缓存。

## 当前断点（第 10 轮，2026-10-16，前端逐条审查修订 + HTML 呈现，**已完整端到端交付**）

- **本轮任务**：用户选定 **A 服务端 HTML 方案**，要求：用户在结果页看到合同的 Word 呈现、**逐条勾选接受/拒绝修订**（与 Word 一致，任意组合自由）、据此生成**独立最终版产物**、支持一键接受全部；并指出 A 页**目录丢失**，要求排查是否还有其他丢失；指定全链路改造 + 进度管控 + 版本管理 + **完整端到端交付**，中途不得停下。
- **目录丢失根因（FL-D087，已查明并修复）**：demo 转换器只遍历 `body` 顶层 `w:p`/`w:tbl`，**整份目录位于唯一 `w:sdt`（20806 字符）内被静默丢弃**。完整丢失清单：目录 sdt（24 超链接 + 23 PAGEREF + 24 bookmark + 24 个 TOC1 段）、75 个 fldChar / 29 个 instrText 域、超链接不输出 `<a href>`、`w:tab` 硬编码、`sectPr` 分页信息。原文档 1363 个 `w:p` vs A 页 1252 个 `doc-p`。
- **方案规格与进度台账**：`docs/HTML_PRESENTATION_PLAN.md`（P0–P6 全部 ✅）。
- **实施（5 个 commit，全部已 push 到本地分支，未 push 远程）**：
  - `da86401` P1 投影层 `fundlex/html_view.py`（新增，只读）：通用块级遍历（含 `w:sdt`/表格）、`w:hyperlink`→真实 `<a href>`（经 rels 解析，协议白名单）、域代码隐藏仅留缓存结果、`w:bookmarkStart`→锚点、`w:tab`/`w:br type=page`/`sectPr` 投影；修订锚点直接取 OOXML `w:id`（**零文本匹配**）。
  - `40c53da` P2 选择性写入 `fundlex/selective.py`（新增）：`accept` 提升 `w:ins` 并删除 `w:del`；`reject` 删除 `w:ins` 并把 `w:delText` 还原为 `w:t`；未托管修订 id 只报告不改写；产物独立重开校验无残留。
  - `b9ff52a` P3 新 kind `selected_final` + 端点 `GET /revisions`、`POST /decisions`、`POST /accept-all`；`store.save_selected_artifact`（用户产物存 `selected/`，与 worker 产物隔离；`finish()` 白名单**故意不含** `selected_final`）。
  - `e9e51ac` P4 前端审查面板（单滚动容器 + 点清单 `scrollIntoView` 定位，**不做双栏同步滚动**——已实测两侧高度差 22% 无解）。
  - `b938a21` P6 文档与问题登记。
- **验证证据（全部真实、可复现）**：
  - 单元/集成：新增 19 项测试（`tests/test_selective.py`、`tests/test_revision_api.py`）；全套 **596 passed**（唯一失败 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation` 经 `git stash` 对照确认为**既有基线失败**，与本次无关）。
  - P2 关键正确性：全部接受输出与引擎自身 `working_final` **逐段一致**（1363/1363，0 差异）；全部拒绝恢复每一条 `expected_old_text`；单条拒绝只影响其所在段落（p1191）；纯删除型拒绝恢复被删文本。
  - **真实云端端到端（默认工作台入口，非遗留 `/api/batches`，未改任何发布标志）**：`POST /api/auth/login` → `POST /api/tasks`（`engine_id=recall_first`）→ `/uploads` → `/seal` → 真实 Worker + 真实模型 → `/revisions` → `/decisions` → 下载 `selected_final`。输入为干净原件 D01（sha256 `2f2f7a36…`，0 条既有修订）。结果：17 条修订全部映射、`has_toc True`、14 页；拒绝第 1 条 + 接受其余 → 下载文件 **0 条残留修订**、被拒条目还原原文、被接受条目保留替换文本、**目录 sdt 完整保留**、1338 个顶层段落结构未变；一键接受全部成功；引擎原有产物仍可下载未被替换。**incomplete 交付情形同样通过**（16 条修订 / `working_*` 产物）。
  - **真实浏览器（生产端点 127.0.0.1:8010，真实密码登录）**：17/16 条修订、目录 24 条 + 24 链接、勾选联动、点清单精确定位、生成与下载成功、**0 控制台错误**。脚本 `/tmp/opencode/browser_prod.py`。
- **验证中修复的真实缺陷（FL-D088）**：① 存储产物保留原始上传名无 `.docx` 后缀，`_read_parts` 以上传防护拒读 → `/revisions`、`/decisions` 对真实任务一律 422（真实路径才会暴露）；已改为经临时 `.docx` 副本读取，包限制不减。② 前端 `pathDoc` 用 `doc.id`，实际字段是 `document_id` → 请求 `/documents/undefined/revisions` 404；已修正。
- **易错点（接续必读）**：
  - 端到端验证**必须**用默认入口 `POST /api/tasks` + `engine_id=recall_first`（FL-D089）。遗留 `/api/batches` 建的批次 `engine_id` 为空 → 走遗留 ruleset-only 路径 → 报告 `guide groups 0 / targets 0`，**会误判成"引擎找不到条款"**。
  - 任务 `id` 与上传回执的 `batch_id` **不是同一个值**；文档/报告/产物端点用 `batch_id`。
  - ruleset v1 处于 `unreleased`（`auto_write_enabled: false`）只关门 ruleset 路径；recall-first 引擎走绑定指引快照，**不受该门限制**，实测正常交付（FL-D090）。不得为"制造交付"手改发布标志。
  - 引擎在真实模型下**非确定**：同一份合同不同批次可能得 17 条（complete）或 16/17 条（incomplete，如 `RECALL_EDIT_OVERLAP`）。incomplete 时产物是 `working_final`/`working_redline`，`final`/`redline` 会 404，属**正确行为**。
- **部署状态**：`bash tools/deploy/publish_workspace.sh` 已执行；`/opt/fundlex-recall-first` 与仓库**逐文件 sha256 一致**（html_view/selective/api/store/app.js/app.css 全部 SAME）；`fundlex-recall-api`/`fundlex-recall-worker` 均 active，`/api/capabilities` 200。
- **下一动作**：功能已按用户要求完整端到端交付，无待办阻塞。可选后续：① 若要求修订审查的**确定性交付**，需先解决引擎 `RECALL_EDIT_OVERLAP`（属引擎既有议题，非本功能）；② 合并到主分支/推送远程需用户明确要求（本轮**未 push**）。

## 当前断点（第 9 轮，2026-10-15，前端合并「处理进度/合同结果」）

- **本轮任务**：用户提出前端「处理进度」与「合同结果」两页几乎一样，要求合并。用户**明确选定**方案：**一张表 + 全部列常显**（明确否决"视图切换"方案）。
- **合并依据（代码证据）**：两页消费**同一接口** `GET /api/tasks/{id}/documents`（`fundlex/api.py:720`），共用 `loadDocuments()`、任务选择器循环、`showDetail`、分页；差异仅列/筛选/页头按钮。→ 同一实体，非两个功能。
- **已实施**（仅 3 个前端文件，**无后端/数据库/引擎改动**，单 commit 可 revert）：
  - `frontend/index.html`：`#view-progress` + `#view-results` → 单个 `#view-task`；侧边栏两项 → 一项「任务详情」(`data-nav="task"`)，总览页英雄区两按钮 → 一个；固定 7 列表头常显（合同文件/上传状态/资格/交付完整性/处理状态/业务提示/操作）；工具栏 7 个筛选控件（`doc-search`/`doc-upload-filter`/`doc-qualification-filter`/`doc-completeness-filter`/`doc-status-filter`/`doc-reason-filter`/`doc-sort`）；两组统计 `#overall-counts`+`#result-counts` 常显；页头运行态+交付态按钮并列。顺带删掉无人引用的死标记 `release-notice`。
  - `frontend/app.js`：`state` 的 `progressPage/resultPage/progressSize/resultSize/progressDocs/resultDocs` → 单一 `docPage/docSize/taskDocs`；`VIEW_TITLES`/`go()` 支持 `task`；`renderTask`/`deliveryCounts`/`updateDeliveryNote`/`selectTask`/`loadDocuments`/`refresh`/`seal`/`exportResults`/`resetWorkspace`/`data-detail`/分页/`changed`/事件绑定全部改到 `doc-*`；`renderTask` 里失效的 `selected-task-ruleset` 已移除。
  - `frontend/app.css`：`#result-scope-note`→`#doc-scope-note`、`#result-rows`→`#doc-rows`（行置灰规则随合并变为常显）。
- **关键坑（勿再错改）**：分页名**必须**用 `name='doc'`。`pagination()` 按 `name` 推导 `state[`${name}Page`]`，而 `taskPage/taskSize` 已被**任务列表**占用，若沿用会把两处分页串在一起。`data-detail` 统一 `doc:i` 并统一读 `state.taskDocs`。
- **顺带修复**：原 `emptyRow(cols)` 列数与真实表头不符（progress 传 5 / results 传 7 / reset 传 6、5）→ 统一 7，空态 `colspan=7`，列错位消除。
- **真实浏览器验证（已做，非静态检查）**：装了 Playwright + Chromium（`dnf install atk gtk3 …` 补系统库）驱动**真实页面 + 真实 API**。脚本 `/tmp/opencode/browser_accept.py`、`/tmp/opencode/browser_accept2.py`。结果：**0 页面/控制台报错**；`#view-task` 唯一，旧两页已无；导航只剩一个「任务详情」；表头 7 列全部可见；数据行 7 单元格；`data-detail="doc:0"`；空态 `colspan=7`；筛选真实下发（`upload_status=pending`）；分页 `data-page='doc'`；`#overall-counts`/`#result-counts` 正常填充；刷新后一致。另：`app.js` 过 modern JS 引擎语法校验；HTML 结构闭合 0 错；118 个 JS 引用 id 全部存在。
- **测试**：572 passed / 6 skipped / 1 failed；该 1 失败经 `git stash` 对照确认是**既有环境问题**（缺 `references/source/…文案勘误版.docx`），**与本改动无关**。
- **已登记**：`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` **FL-D086**（两页重复 + `emptyRow` 列数缺陷，含验证证据）。
- **已发布到线上（已完成）**：`bash tools/deploy/publish_workspace.sh` → `api/worker` 均 active，`/api/capabilities` 200。公网 `https://fundlex.club` 已复核（真实 Chromium）：`#view-task` 唯一、旧两页不存在、导航只剩一个「任务详情」、0 报错。脚本 `/tmp/opencode/live_check.py`。
- **git**：commit `3f4d8cf`（前端合并）已推送 origin（`341be2b..3f4d8cf`）。注：FL-D086 文档条目被并行 agent 的 `341be2b` 一并提交，内容完整。
- **下一步**：① 前端合并已完成并上线，如需可让用户在线上点一遍确认交互手感；② 回到第 8 轮主线：修 **FL-D060**（无条件 append 漏加 G01/G03/G16）→ 开发集再跑 1—2 轮 → 冻结 → 留出 8 例 → `docs/REAL_REVISION_EVALUATION_RESULTS.md`。

## 当前断点（第 8 轮，2026-10-15，接续请从此处读）

- **本轮已完成的非批次工作（第 8 轮）**：① 修正集中问题记录的 5 组**编号冲突**（FL-D077），并同步修正 `tools/evaluation/p6_score.py` 与断点/计划文档的引用（后出现的重复项改为 FL-D072/073/074/075/076，保留首次出现编号之一义）；② **新增交付包工具 `tools/evaluation/p6_package.py`**（把 P6 运行目录打成业务读者可读的「结果总览.md + 最终版（接受修订后）/ + 逐份修改说明/<合同>/{修改说明.md,修改明细.json,（修改痕迹版）.docx}」，结构对齐参考包 `FundLex-合同修改结果-本次抽查-20261013`），已用它生成 **`var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/`**（20 份合同，81 文件）；③ 复核交付包时发现并修复**真实缺陷 FL-D079**（变体模糊匹配 span 停在句中，留下“…（如有）。配。”碎片）→ 新增 `fuzzy_span_clause()` 句边界吸附，`variant_replace/variant_delete/审计复核`三处统一；④ 新增测试 `tests/test_p6_package.py`（3 项）与 `test_fuzzy_span_clause_snaps_to_sentence_boundary`；⑤ 全量测试 **566 passed / 1 expected（references/）/ 6 skipped**。
- **P6 第 1 轮（第 3 次重跑）已完成**：`p6-dev-round1-01` 20/20、604 调用、$0.5533；评分 `.venv/bin/python -X utf8 -m tools.evaluation.p6_score --run var/recall-first-evaluation/p6-dev-round1-01 --output /tmp/opencode/p6-round1-final.json` → 全量 347 目标/184 完成/0.5303；**开发集口径 236 目标/184 完成/0.7797**（基线 0.754、第 2 次 0.792）；integrated_complete 0/20；applicability_conflicts 19。产物 `var/recall-first-evaluation/p6-dev-round1-01/`。
- **P6 关键文件（仓库外）**：`/home/opencode/data/funds_word/`、`/home/opencode/data/MANIFEST.sha256`；仓库内 `var/recall-first-evaluation/p6/`（selection/labels/protocol/freeze）。
- **账本（仓库外，勿入库）**：应用调用记 `/var/lib/fundlex/model_budget.sqlite`（root 只读，opencode 读不到；数字取自各 `report.json` 的 `model` 段）。基线 581 调用/$0.5624；第 2 次 677/$0.5738。**agent 自用 0 次**。
- **禁止**：把**密钥/凭据**入库。发布只能用 `bash tools/deploy/publish_workspace.sh`。（**更新**：用户已授权自行判断 git 提交/推送；**推送统一用 `bash tools/deploy/push_with_token.sh`**，token 存仓库外 `/home/opencode/.github_token`（600），不打印/不入库。**合同资料政策更新（用户 2026-10-15）**：合同为公开资料，**可入库、可出服务器**（含 Langfuse Cloud）；「不入库/不出服务器」的旧底线**仅对凭据仍然有效**。）
- **本轮已推送**：`e37aa21`（交付包工具 + FL-D079）、`99509fb`（push 助手）、`dcc715e`（FL-D080）；远端 `origin/codex/fundlex-recall-first` 与本地一致（HEAD `dcc715e`）。
- **交付包已含根目录 `结果清单.csv`（FL-D081，用户要求）**：`tools/evaluation/p6_package.py` 复刻工作台「导出结果清单」的格式（BOM+CRLF、列 `序号,文件名,资格,处理状态,交付完整性,业务提示,原始原因码`、末列仅短机器码）；`结果总览.md` 保持不变。重出包：`var/recall-first-evaluation/FundLex-合同修改结果-P6开发集-20261015/`（根目录 3 项 + 最终版 20 份 + 逐份说明 20 组）。
- **Langfuse 可观测性（FL-D081，已推送 `f5be16f`）**：接入 **Langfuse Cloud**（本机无 Docker/无 Postgres+ClickHouse+Redis+MinIO，自托管不可行）。代码：`fundlex/observability.py`（唯一收口，**无 key 纯 no-op**）、`fundlex/model.py` 的 `_trace_attempt`（每次调用一个 generation span）、`fundlex/jobs.py` 的 `_document_trace`（**一个合同一个 trace**，document_id 为确定性 seed）、`tools/evaluation/p6_langfuse_sync.py`（把 P6 verdict 作为 score 回写同一 trace）。开关：`FUNDLEX_LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST`（两个 key 都设才启用）+ `FUNDLEX_LANGFUSE_CAPTURE_TEXT`。已用本地 OTLP 桩验证真实发射（根 span 与 generation trace id 一致、带 usage/cost/version；score 带完整 metadata）；`tests/test_observability.py` 5 项通过；全量 **568 passed / 6 skipped**。详见 `docs/LANGFUSE_OBSERVABILITY.md`。**真实云端凭据已配置并验证**（FL-D083：`jp.cloud.langfuse.com`，`auth_check=True`，冒烟 trace `b1648f73…`）。
- **root 写权限（FL-D084，全部 agent 须知）**：用户已授予 `opencode` 本机 sudo `ALL`（`/etc/sudoers.d/fundlex-agent`）。`sudo -n` 可用；已用它备份并追加 `FUNDLEX_LANGFUSE_*` 到 `/etc/fundlex-recall.env`（备份 `…env.bak-langfuse`）。**边界**：仅 FundLex 部署/配置/服务/验证；凭据值不入库/文档/日志。**部署侧待办**：`/opt/fundlex-recall-first` 缺 `observability.py` 且 venv 未装 `langfuse` → 需 `sudo -n …/pip install langfuse` + `bash tools/deploy/publish_workspace.sh`（重启 api/worker）后生产 worker 才会发真实 trace。
- **合同资料政策更新（用户 2026-10-15）**：合同为公开资料，**可入库、可出服务器**；旧「不入库/不出服务器」约束**仅对凭据仍有效**（见 `AGENTS.md`）。
- **本地 JSONL trace 兜底（FL-D088，2026-10-16，已发布并验证）**：Langfuse 两区均丢 payload（FL-D085），用户指示退化到本地 JSONL。新增 `fundlex/trace_sink.py`（纯标准库；`FUNDLEX_TRACE_JSONL` 未设即 no-op；一个合同一 trace + 一次调用一 generation + 一条 score；活动文档 id 走 thread-local），接线于 `model.py`/`jobs.py`，配套分析器 `tools/evaluation/p6_trace_report.py`，单测 `tests/test_trace_sink.py`。生产落点 `/var/lib/fundlex/traces/model-calls.jsonl`（`/etc/fundlex-recall.env` 已加变量，备份 `.bak-tracesink`）。**真实 20 例已验证：1085 行、单条 25KB 含合同原文、19/20 trace 匹配、0 错误。**
- **评分器 append 误判已修（FL-D089，2026-10-16）**：`appendix_present()` 现折叠份额类别枚举（`A类、D类` ≡ `A类`）+ 模糊兜底逐字符步进。**开发集 0.7892 → 0.8161**（无引擎改动）。回归测试 `tests/test_p6_score_append.py`。
- **剩余主力缺陷（FL-D090，未修）**：开发集剩余 `not_executed` 11 例**全是 G01/G03/G16 append**（D07 真漏改——原件用「直销渠道」措辞致模型盘点判 `not_applicable`；D09/D13 属原件已含相近义务）。修法方向：`appendix` 规则增确定性适用性兜底 + 直销措辞归一化。
- **当前指标（2026-10-16，开发集 20 例 / 223 目标）**：**0.8161**，目标 0.95；整合完成 0/20，目标 0.9。`kept` 30 例（G17×8/G14×5/G11×4/G18×3/G15×3/G08×3/G13×2/G05×2）。
- **下一步（按序）**：① 修 FL-D090（append 适用性兜底）；② 开发集再跑 1 轮验证；③ 达标后冻结 → 跑留出 H01–H08；④ 出交付包 + `docs/REAL_REVISION_EVALUATION_RESULTS.md`；⑤ Langfuse 云端若报障有结论再回填 score 通道。
- **下一步（按序）**：①（可选）发布 FL-D079 修复后用 D01 等含 G22 变体的样本复跑，确认终稿无“……（如有）。配。”碎片；② 修 FL-D060（无条件 append 漏加 G01/G03/G16）后只在**开发集**再跑 1—2 轮（≤3 轮），直到 dev 达标（0.95 / 整合 0.9）并冻结；③ 冻结版跑 8 留出例（`--group holdout`）；④ 写 `docs/REAL_REVISION_EVALUATION_RESULTS.md`（用 `tools/evaluation/p6_package.py` 出交付包）；⑤ P7 浏览器端到端、断点续跑、双身份隔离、指引切换、MySQL 备份/恢复。

## 第 7 轮进度（服务器，2026-10-15）：用户 8 项 UX/修改问题 + P6 第 1 轮评分

任务计划文档：`docs/TASK_PLAN_UX_AND_APPEND_20261015.md`（该文档写于编号更正 FL-D077 之前，文中 FL-D068/069 指现在的前端互斥与 fragment 拼接两义，见本文顶部更正块）。

- **T2 引擎（问题 5，无标点拼接）已修复**：`_splice_fragment`（`fundlex/recall.py`，`fragment_replace` 路径）遗漏分隔符 → 已加 `append_separator`；`plan_composite_target` 同步加固。新增 2 回归测试。→ **FL-D068**
- **T1 后端并发核实（问题 1）**：后端本就支持多任务并行（`tasks.create` 无限制、`POST /api/tasks` 无守卫、worker 公平 claim）；互斥纯在**前端**。→ **FL-D069**
- **T3 前端 8 项 UX（问题 1–8）已实施**（`frontend/index.html|app.js|app.css`）：多任务并行、证据侧栏改「章节+改之前/改成了什么」、精简小字、结果页 ZIP 按钮置首、删顶部横幅+铃铛只收重要消息、总进度指标单行、导入 KPI 并入筛选栏。→ **FL-D071**。验证：`node --check` 通过、120 个 id 引用完整、`#2` 用真实报告核对 22 行可读无技术字段。**未做浏览器端点击验收。**
- **P6 第 1 轮评分（FL-D070）**：`p6-dev-round1-01` 20/20 完成，677 调用，$0.5738。**开发集 236 目标：基线 178（0.7542）→ 187（0.7924，+3.8pt）**；G15 +9、G05 +2、G17 −2；`applicability_conflicts` 29→13；**假完成仍 12**。评分产物 `/tmp/opencode/p6-round1-score.json`。**仍未达阈值（0.95/0.9）**。
- 测试：`.venv/bin/python -m pytest tests -q` → **561 passed / 1 expected（references/）/ 6 skipped**。
- **已提交并已推送（第 7 轮，11 个逻辑提交 `cc558ab..05fc90f`）**：工作树干净；`origin` 为私有仓库 `github.com/JokerNephew/FundLex`，分支 `codex/fundlex-recall-first`（新建 + upstream）。凭据为用户提供的 OAuth token（`gho_…`，经临时文件 + `GIT_ASKPASS` 使用，未入仓库/日志，用后即删；**用户应撤销该 token**）。仓库级代理 `http.proxy=http://127.0.0.1:9981`。详见 `docs/HANDOFF_ROUND7_UX_AND_GIT_20261015.md`。→ **FL-D078**（原 FL-D072，编号冲突后更正）。
- **未发布**：部署副本 `/opt/fundlex-recall-first` 仍为上一版。
- **预览服务（临时）**：`FUNDLEX_DATA_DIR=/tmp/opencode/fundlex-preview FUNDLEX_AUTH_MODE=dev .venv/bin/uvicorn fundlex.api:app --host 127.0.0.1 --port 8020`，供浏览器（经 SSH `-L 8020:127.0.0.1:8020` 转发）查看新代码；验证完应停掉。
- 下一动作：① 用户提供 GitHub 凭据后 `git push -u origin codex/fundlex-recall-first`（或新分支/PR）；② 浏览器端验收前端问题 1/2/4/6/7/8；③ 经确认后 `bash tools/deploy/publish_workspace.sh` 发布；④ 继续修 P6 开发集 `not_executed`（17，G01/G03/G16）+ `kept`（32，G17/G15/G14/G11/G08/G18）。

## 第 5 轮进度（服务器，2026-10-15）

- 基线复核：`uname` Linux x86_64；`.venv` Python 3.11.13；`/home/opencode/data/MANIFEST.sha256` 538/538 OK；`fundlex-recall-api`/`fundlex-recall-worker` active；`/api/capabilities` 200。
- 基线测试：`.venv/bin/python -m pytest tests -q` → **530 passed / 1 failed / 6 skipped**（唯一失败=`test_rules_catalogue`，references 未随迁移，预期）。
- 已修四类真实缺陷（**FL-D052**，见集中问题记录；代码在 `fundlex/recall.py`、`fundlex/recall_pipeline.py`）：
  1. survey 引文切片 compact→raw 偏移错误（`compact_offsets`；`survey_targets`/`plan_composite_target` 改用）；
  2. 跨段盘点目标未重绑定（`_rebind_unresolved_targets`，盘点后+每轮修复后执行，报告新增 `rebind` 段）；
  3. 同段多操作被首个命中短路（`plan_target` 累积 delete+replace，新增 `fragment_mixed`）；
  4. 查漏位置误报与“已满足”漏判（`_rule_mapped_locations`+`_sweep_batch(rule_locations=…)`→`SWEEP_LOCATION_OUT_OF_SCOPE`；`_rule_location_absent`→`SWEEP_LOCATION_NOT_RULE`；`satisfied_by_new_text` 同政策异语序等价；裸尾片段需上下文佐证 `bare_tail_keys`/`rule_context_anchors`）；并新增确定性审计确认 `_confirm_merged_append`（G03 p141、G16 p809 的 append+兄弟删除合并误判）。
- 新增单测 7 项；全量 **537 passed / 1 failed（预期）/ 6 skipped**。
- qr-local-12 12 项逐条结论：G05 p142=真实缺陷（已修）；G15 p806/p1262=跨段（已修）；G03 p141、G16 p809=审计误判（已加确定性确认）；G05 p760、G16 p227、G18 p139/p829/p1217、G22 p142=误报（已加过滤）；另修正 FL-D047 遗留判断：G05 真实目标只有 p142，p954/p1332 是“基金合同变更”条款非费用类别调整句。
- **已发布**：`tools/deploy/publish_workspace.sh` 成功（拷贝到 `/opt/fundlex-recall-first`、重启服务、capabilities 200）；部署代码已含全部 FL-D052 修复。
- **真实链路复验 quality-return-10**（应用链路：register→login→tasks→uploads→seal→轮询→下载；真实模型）：`task_status=completed`、`job_status=succeeded`、**64 调用 / $0.0461 / 230431 tokens / 358s / delivery=incomplete**；**targets 28 / completed 27 / unresolved 1**（对比 qr-local-12：30/14/12）；`rebind=[]`；`output_validation` 有 working_final/working_redline sha256。产物在 `var/cloud-runs/quality-return-10/`（report.json/working_final/working_redline/report_md）。
  - 已验证：G05 p142 同一目标同时 replace（调低销售服务费率）+ delete，`fragment_mixed` 生效；G03 p141 审计 completed；G16 p809 审计 completed（`_confirm_merged_append` 生效）；跨段 G15 p806/p1262 已解决；G18 p139/p829/p1217、G22 p142、G16 p227 误报消失（sweep dropped 记录 `SWEEP_LOCATION_OUT_OF_SCOPE`/`SWEEP_LOCATION_NOT_RULE`/`SWEEP_ALREADY_SATISFIED`）。
  - **残留 4 项未解决**（3 类原因）：① **G17 p808** `RECALL_COMPOSE_DELETE_NOT_SHRINKING`（审计 wrong）——规则 `old_text` 是 p808+p809 两句拼接，而 T018 目标只含 p808 一句，`_splice_fragment`/`variant_delete` 均无法匹配整段参考，落到 compose-delete 后被模型原样返回；② **G02 p106 sweep 误报**、③ **G04 p138 sweep 误报**——`class_substitution` 规则的 `new_text`（`A类、B类基金份额`）是指引示例，本产品只有 A/C 类，盘点已正确判 `satisfied`，但 sweep 模型把示例当真需求；④（第④项为 ①②③ 的审计/sweep 派生条目）。
- **第 5 轮第二轮修复（同属 FL-D052）**：
  1. `recall.class_substitution_noop`（新）：`class_substitution` 规则若各适用操作的实例化 `new_text` 与其 `old_text` 相等（产品实际类别已就是规则要的分组），则该规则无需修改；`recall_pipeline._rule_already_satisfied` 前置调用 → sweep finding 记 `SWEEP_ALREADY_SATISFIED`（修 ②③）。
  2. `recall.plan_target` 新增“删除整段目标”确定性分支：delete-only 规则、目标引文（compact）等于目标 span 且是规则 delete 参考文的子串时，整段 `replacement=""`（`variant_delete`），不再走 compose-delete（修 ①）。
  - 新增单测 3 项（core 2 + pipeline 1）；全量 **539 passed / 1 failed（预期）/ 6 skipped**。
- **未做**：quality-return-11 复验进行中、P6 评测。**本工作区未 commit、未 push**。
- 本轮模型调用：**0 次**（全部为离线单测与对既有 report.json 的离线核对）；应用账本 `/var/lib/fundlex/model_budget.sqlite` 的调用来自 quality-return-10/11 的应用任务，非 agent 自用（自用 0 次）。
- **第 5 轮第三轮修复（同属 FL-D052，已通过真实链路验证）**：quality-return-11 暴露两处新问题 →（a）G15 p806 因合同把支付条款拆成 p806+p807 两段、且指引措辞与合同不同，盘点把目标绑成单段 `…按月支付，`，删除无法覆盖续段 → 落 compose-delete 失败；（b）G16 p809 审计随之误判。修复：`_rebind_unresolved_targets` 新增 `extend_resolved`（仅跨段 composite 可替换已解析单段绑定）+ `_clause_continuation_binding`（整段覆盖 + 段末逗号 + 删除/替换规则 → 并入紧随一段）。新增单测 `test_rebind_extends_resolved_target_to_clause_continuation`。
- **quality-return-12 真实链路结果（已通过）**：`delivery_status=complete`、unresolved 0、targets 27/27、sweep_findings 0、**25 调用 / $0.0236 / 127s**；G15 重绑定 `p806:0:34+p807:0:88`。产物 `var/cloud-runs/quality-return-12/`；`final`/`redline` 哈希与报告一致（`862548a7…` / `2e586002…`），redline 含 16 `w:ins`+16 `w:del`；p806/p807/p808 删除、p809 保留+追加、p142 replace+delete 均在真实 DOCX 中核对通过。**FL-D052 全部收敛。**
- 全量测试：`.venv/bin/python -m pytest tests -q` → **540 passed / 1 failed（预期，references 未迁移）/ 6 skipped**。
- **待用户协助**：~~quality-return-10/11/12 的临时账号（`cloud-run-*`）与任务~~ **已于 2026-10-15 清理完毕（FL-D053 已解决）**：用户提供 3307 应用账号凭据，按 cloud_verify 顺序删除 3 账号及其任务/批次/文档/产物/会话；`admin` 与 `cloud-eval-*` 未动。
- **下一步**：P6 真实修改评测（28 份：20 开发 + 8 留出）。

## 第 6 轮（P6 真实修改评测，2026-10-15 续）

- **目标**：按 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` 执行 P6：28 份合同（20 开发 D01–D20 + 8 留出 H01–H08）走真实应用链路（`recall_first` 引擎、真实模型），对**实际 DOCX** 与**先冻结的独立标签**计分，据结果优化；留出集在冻结版之前只读一次。
- **样本选择**：`tools/evaluation/p6_select.py`（新）按分层确定式抽取（active/qdii/fof/likely_excluded/other 目标 16/3/4/3/2，stride 填充，dev/holdout 交错）；输出 `var/recall-first-evaluation/p6/selection.json`（`a7ed2519…`）。范围=514 份 `funds_word`，hash 引用 `/home/opencode/data/MANIFEST.sha256`。
- **独立标签**：`tools/evaluation/p6_label.py`（新，**盲于引擎输出**，只读指引 + 原件）。确定性推导事实（基金类别、份额类别与费用规则、浮动费）与逐规则义务；`old_text` 按合同实际措辞定位，删/替义务源句缺失记 `not_applicable`。规模：**347 目标 / 26 可改合同 / 2 排除**。修正过份额类别与费用事实推导（跨段、术语式定义、A/Y 按账户分类、否定式“不收取申购费/不从…中计提销售服务费”），旧/新 hash 均记录在 `freeze.json`（`label_corrections`）。
- **协议与冻结**：`protocol.json`（预算：dev ≤2000 调用 / ≤$6；holdout ≤900 / ≤$3；单任务 ≤$1；账本在仓库外）、`freeze.json`（三份 hash + 已知局限）。`labels.json` `230b5be4…`。
- **运行器/评分器**：`tools/evaluation/p6_run.py`（单账号、每合同一个 `POST /api/tasks`、下载 final/redline/report）、`tools/evaluation/p6_score.py`（重读实际 DOCX 计分；引擎判 `not_applicable/satisfied` 而标签仍要求改动的，单列 `applicability_conflicts`，不静默计为漏改）。
- **本轮修复的真实缺陷**（均记入集中问题文档）：
  - **FL-D054**：长合同 sweep 阶段 `MODEL_CONTEXT_LIMIT` 整单不产出 → `_sweep_chunk_chars` 扣减 `facts_text` 与固定开销。D01(1363 段) 复验不再触发。
  - **FL-D055**：审计把份额类别占位符展开误判为无依据新增 → `AUDIT_INSTRUCTION` 增补通用总则。
  - **FL-D056/FL-D058**：无销售服务费类别产品被误判 `RECALL_SLOT_UNRESOLVED` → `slot_group_missing`（服务组为空或费用同质）+ class_substitution 规则整体判不适用 + `Target.out_of_scope` 统一审计/未解决统计 + `unresolved_targets` 排除 `not_applicable`。D07 由 26 项降到 0，真实链路 `complete`。
  - **FL-D052 补充**：整段删除在合同措辞与指引不同、composer 报 `DELETE_NOT_SHRINKING` 时，整段 `replacement=""`（`whole_paragraph_delete`）。D01 真实链路 `complete`。
  - **FL-D072**（未完全解决）：sweep 偶发误报 G02/G04 分组替换未完成（残留旧标签句）。已加确定性过滤，偶发一次；规划侧正确。
- **测试**：`.venv/bin/python -m pytest tests -q` → **544 passed / 1 failed（预期，references 未迁移）/ 6 skipped**。新增单测 5 项（sweep 预算 2、服务费组不适用 1、整段删除 1、费用组反向 1）。
- **已发布**：`tools/deploy/publish_workspace.sh` 成功；部署 `fundlex/recall.py` `ef600a1e…` 与工作区一致（前次 `87407fe1…`/`2a0df932…`/`7136d6ad…` 为迭代中间态）。
- **基线批次已完成**：`p6-dev-baseline-01`（20 开发集，修复前部署 `ef600a1e…`，日志 `/tmp/opencode/p6-dev-baseline-01.log`）：**20/20 完成，581 调用，$0.5624**；报告内部 `delivery_complete=13`（D01/D04/D05/D08/D09/D10/D13/D14/D15/D16/D18/D19/D20），D02 `excluded`，D03/D06/D07/D11/D12/D17 `incomplete`。
- **基线评分（实际 DOCX vs 冻结标签）**：以**较正后**的 `/tmp/opencode/p6-baseline-full2.json`（`scored_at 08:26`）为准：**开发集口径（剔除未跑的 8 留出与 D02 excluded）236 标签目标 / completed 178 / 率 0.7542**；`kept 41`；**integrated-complete 0/18**；**13 份假完成**；**applicability_conflicts 29**。（较早的 `/tmp/opencode/p6-baseline-full.json` 给 168/0.712，已被 full2 取代。）全量口径 347 目标 / 178 / 0.513（含未跑的 8 留出）。**远低于阈值（目标 0.95 / 整合 0.9）**。
- **优化第 1 轮结果（`p6-dev-round1-01`，已完成并评分，见 FL-D070）**：20/20 完成，677 调用，**$0.5738**；**开发集 236 目标 / completed 187 / 率 0.7924（较基线 +9 目标，+3.8pt）**；规则层 **G15 +9（0/15→9/15）、G05 +2、G17 −2**；`kept 32`；`applicability_conflicts 13`；**假完成 12（actually_complete 1）**。评分产物 `/tmp/opencode/p6-round1-score.json`（sha256 `07fb0112…`）。**仍未达阈值**，不满足正式交付条件。
- **基线漏改归因**：`not_executed` 主要为 G01(5)+G03(5)+G16(3)（无条件 append 漏加，FL-D060）；`kept` 主要为 G15(7)+G17(4)（删除句变体漏删，FL-D059/FL-D062）。
- **本轮（发布前）修复并发布**：FL-D059（`_strip_class_lead` 短锚，G17 11/11）、FL-D052 整段删除兜底、FL-D062 通用结构化删除兜底（`_delete_keyword_bag`+`_keyword_bag_in_clause`，G15 28/28 精确 2 处、零误报）、FL-D054/D055/D056/D058。测试 **546 passed / 1 expected / 6 skipped**。
- **已发布**：`bash tools/deploy/publish_workspace.sh` → 部署 `fundlex/recall.py` `3bccf52788cb5bbc…` 与工作区一致；`fundlex-recall-api`/`worker` active，`/api/capabilities` 200。
- **进行中（第二轮=优化第 1 轮，第 3 次重跑）**：`p6-dev-round1-01`（20 开发集，最新构建 `fundlex/recall.py` `07b39288b87dfa14…`，日志 `/tmp/opencode/p6-dev-round1-01.log`，`--timeout 1800`）。前两次尝试见下。
- **第 2 次尝试结果（构建 `6340b6618745af32…`，已归档 `p6-dev-round1-01-prev`）**：20/20 完成，677 调用，$0.5738。评分（`/tmp/opencode/p6-round1b.json`）：开发集 **236 标签目标 / completed 187 / 率 0.792**（基线 0.712）；`applicability_conflicts` 38→13。**剩余主因**：G01/G03/G16 无条件 append 漏加（7/7/3）；G17 跨段删除次段残留（10）；G15 短锚误判（6，FL-D074 已修）。据此新增 FL-D074（评分器短锚误判）、FL-D075（G17 跨段删除）。
- **本轮新增修复（已发布，`07b39288b87dfa14…`）**：FL-D063（删除 span 延伸到引用所跨句数 + 句首回退避开公式行 + 词袋配对防误并 + `target_span_delete`）、FL-D064、FL-D062、FL-D065、FL-D067、FL-D074（评分器按引号内整条条款判删除）、FL-D075（G17 跨段删除合并）。全量 **562 passed / 1 expected / 6 skipped**。
- **本轮新增修复（已发布，`6340b6618745af32…`）**：FL-D063（删除 span 延伸到引用所跨句数 + 句首回退并避开公式行；G17 半删 / G15 空删修复）、FL-D064（survey 兜底补 `.with_parts()`）、FL-D062（G15 结构化删除兜底）、评测器 `appendix_present` 归一化（FL-D065 边界）、FL-D067（遗留 append 测试按当前 API 重写）。全量 **559 passed / 1 expected / 6 skipped**。
- **环境问题（FL-D066）**：中止批次遗留的模型账本 `reserved` 预留会阻塞后续任务（`MODEL_CONCURRENCY_LIMIT`，`concurrency=1`）；经重启 worker 缓解。**规程更新：不在任务在途中 kill 批次；中止后先重启服务。**
- **本轮新增修复（已发布）**：FL-D063（短锚点删除延伸到句末，修 G17 半删 / G15 空删）、FL-D064（survey 兜底命中补 `.with_parts()`，修 `IndexError`）、FL-D062（G15 通用结构化删除兜底）、评测器 `appendix_present` 归一化（FL-D065 边界：真漏加仍判 not_executed）。
- **环境问题（FL-D066）**：中止批次遗留的模型账本 `reserved` 预留会阻塞后续任务（`MODEL_CONCURRENCY_LIMIT`，`concurrency=1`）；经重启 worker 缓解。**规程更新：不在任务在途中 kill 批次。**
- **评分器**：`tools/evaluation/p6_score.py` 已实现并校准——按标签 `compact_start` 定位原段落，再按内容在最终文件中找回同一段落（段落索引会因增删而位移），在该**区域**内判断旧措辞是否消除/新义务是否到位。避免两类假信号：短锚点同时出现在无关条款；替换文本以旧措辞为前缀。
- **基线首轮已定位的漏改类别**（见集中问题文档）：
  - **FL-D059**：删规则合同措辞变体未进 survey → G15/G17 被判 not_applicable、应删条款保留（D01 两处×2）。**已实施修复**（`_strip_class_lead` 短锚点），独立验证命中。
  - **FL-D060**：无条件 append 规则在原文该条款缺失时被盘点判 not_applicable，导致漏加（D01 的 G01/G03）。**未解决**，待全量统计。
  - 评分器首轮还暴露出：D01 G05 在多处“费用调整”条款中只改了一处（标签冻结单点）、G18 替换未落实；D03 G08 引擎超规划到无源条款位置报 `RECALL_TARGET_UNRESOLVED`（非标签目标，属执行质量问题）。
- **本轮模型调用**：应用账本计 smoke-01..08 共 ≈ 600 调用 / ≈$0.5；开发集基线单独计费（见 `protocol.json` 预算）。**agent 自用 0 次**。
- **本工作区未 commit、未 push**。

## 0. 迁移决定与执行记录（2026-10-15，用户指令）

- **开发主副本迁移到云服务器**：`/home/opencode/fundlex`（专用用户 `opencode`，OpenCode v2.0.29 systemd 常驻，仅监听 127.0.0.1:49374）。
- 迁移内容：整个工作区（含 `.git`、`docs`、全部未提交改动）；排除 `var/`、`funds/`、`funds_word/`、`references/`、`.venv`、缓存与同步残留。
- **资料迁移（`/home/opencode/data`，与工作区分离）**：`funds_word/`（514 份合同）与 `references/`（24 份原件）已迁移，`chown -R opencode:opencode`、目录 750、文件 640；服务器生成 `MANIFEST.sha256`（每行 `sha256  相对路径  字节数`，注释行记录 538 文件 / 82361614 字节 / 生成时间 / 主机）；逐文件与本地比对 0 不一致（FL-D050）。**资料不进工作区、不进 git**；后续评测抽样引用该清单。`funds/`（历史 PDF）与 `.venv`、缓存不迁移。
- **执行记录（`tools/deploy/migrate_workspace.py` 等）**：
  - 打包 824 文件 / 283MB → 上传 → 解包覆盖 `/home/opencode/fundlex`（staging 校验 `layout-ok`）→ `chown -R opencode:opencode` → 保留可执行位；
  - 核对：远程文件数 824 = 本地包内文件数；11 个关键文件 sha256 全部一致（`fundlex/*.py`、`frontend/*`、`guides/builtin_guide_v1.json`、`docs/*.md`、`pyproject.toml` 等，见 `tools/deploy/migrate_verify.py`）；
  - git：远程 HEAD `3ed4e96146a04d3092de6c57138289bdffeca526`、分支 `codex/fundlex-recall-first`，与本机一致；工作区状态 55 项（本机 56 项，差一个未迁移的 `references/`）；
  - 服务器仓库设置 `core.autocrlf=input`、`core.quotepath=false`（修 CRLF 状态噪声与中文路径显示，FL-D049）；
  - 迁移后补传的文档/脚本哈希逐项一致（`tools/deploy/migrate_fixup.py` 复验）；
  - 服务器环境：`/usr/bin/python3.11 -m venv .venv` + `pip install -e '.[test]'`（pytest 9.1.1 / Python 3.11.13）；**基线测试 530 passed / 1 failed / 6 skipped**，唯一失败是 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`——该用例校验 `references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx` 的来源哈希，而 `references/` 按迁移约定不带去服务器（本机为标准 531 passed）。
  - 最终状态：源码文件 229（不含 `.git`/`.venv`/缓存）+ `.git` 对象 606 + `.venv` 4074；`git status` 55 项（11 个已跟踪修改 + 44 个未跟踪，与本机一致，仅缺未迁移的 `references/`）。
- 迁移后核对：74/74 关键文件哈希一致（`fundlex/*.py`、`frontend/*`、`guides/*.json`、`docs/*.md`、`tools/deploy/publish_workspace.sh`），远程 HEAD `3ed4e96…`。
- 迁移后：**服务器工作区是开发主副本；本机（笔记本）副本转为只读备份**。不要两边同时改同一份代码。
- 应用部署 `/opt/fundlex-recall-first` 不动；发布走 `/home/opencode/fundlex/tools/deploy/publish_workspace.sh`（内部调 root 的 `/usr/local/sbin/fundlex-publish`）。
- 不 push（未经用户要求）；不改应用部署，除非已按项目规定完成真实验证与问题登记。
- 模型账本：应用调用记 `/var/lib/fundlex/model_budget.sqlite`；常驻 agent 自身调用不记入该账本，用量单列跟踪。

## 目标与用户约束（摘要）

- 完成 FundLex 整个项目交付：前端、后端、召回优先修订引擎、指引配置、账号、持久任务、MySQL、云部署、真实用户端到端验收、20—30 份真实合同评测与优化闭环。
- 召回优先：模型负责业务判断/映射/盘点/联合修改/复核；代码负责结构地址/来源核对/执行/可靠性。不按关键词或旧文相等拒绝真实目标；已有命中仍查漏。
- 默认内置指引；自定义同结构 DOCX 指引仅在配置页上传/查看/启用/恢复默认；任务页只上传合同；任务绑定不可变指引版本。
- 每轮从原件重生成；复核发现问题自动补证/修复/仲裁，未解决才记未完成。
- 细节问题集中登记 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`；上下文 60% 前压缩或交接。
- 最终验收必须走真实用户端到端路径（工作台登录→上传真实合同→真实模型→DOCX 修改→复核→下载），见 AGENTS.md。

## 仓库状态（本机，迁移前）

- 分支：`codex/fundlex-recall-first`；HEAD：`3ed4e96`（仍未提交 commit；全部为工作区改动）。
- 已跟踪修改（5 个）：`IMPLEMENTATION_PLAN.md`、`README.md`、`docs/RECALL_FIRST_DESIGN.md`、`frontend/app.css|app.js|index.html`、`fundlex/api.py|jobs.py|model.py|store.py|tasks.py`。
- 未跟踪新增（节选，全部随迁移带上）：`AGENTS.md`、`fundlex/recall.py|recall_pipeline.py|recall_prompts.py|guide.py|guide_store.py`、`guides/builtin_guide_v1.json`、`tests/test_recall_*.py|test_guide*.py`、`tools/deploy/`、`tools/evaluation/recall_run.py|replay_checkpoints.py`、`docs/*.md`（含本文件、集中问题记录、实施计划、交接文档）。
- 明确不迁移：`var/`（产物与账本）、`funds_word/`（真实合同原件）、`references/`（指引原件）、`.venv/`、`__pycache__`、`.pytest_cache`。

## 已完成（有证据）

1. **内置指引**：22 组 / 34 操作，确定性校验干净，独立核验逐条处置（FL-D040）；哈希冻结。
2. **引擎核心 + 编排**：事实/映射/盘点/规划/写入/审计/修复/最终查漏/交付裁决；确定性优先；working_final/working_redline 门禁。
3. **第 4 轮新增确定性覆盖与跨段能力**（FL-D047）：`survey_targets` 在全部段落按规则参考旧文补扫（摘要第二处、变更章节残留）；`find_old_text_all` 边界/引导语约束；`plan_composite_target` 跨段删除/替换按段落精确执行；`satisfied_by_new_text` 已满足识别；`_absorb_sweep_findings` 重绑定（含跨段）；审计上下文覆盖 composite 段落；`recall_inventory_v2` / `recall_sweep_v2` 指令。
4. **FL-D048 修复**：条件不适用记 `not_applicable`（不再当未解决）；STOP_CODES 的 ModelError 直接暂停（`RecallPipelineStop`）；账本 reserve/finish 瞬时 readonly/locked 重试 3 次；`recall_run.py` 把 `--max-calls` 同时写入 `FUNDLEX_MODEL_MAX_REQUESTS`；`SOFT_STOP_CODES`（schema/quote/evidence 类）也按可恢复暂停处理。
5. **持久化/API/前端**：指引版本与配置、任务绑定快照、下载白名单、指引配置页、提交页只读显示当前指引。
6. **云端部署**（8.155.130.168）：`/opt/fundlex-recall-first`（8010，systemd `fundlex-recall-api`/`fundlex-recall-worker`，nginx 已切）；MySQL 127.0.0.1:3307/fundlex；公网 `http://8.155.130.168` 已实测 200。
7. **真实云端运行**：quality-return-01…09（产物在 `var/cloud-runs/`）；最新 09：69 调用 / $0.046 / 350s、delivery=incomplete、findings 8（其中 8 条经阅读为真实线索，FL-D047 已针对其治理）。
8. **全量测试**：`pytest tests -q` → **531 passed / 6 skipped**（MySQL 用例需 FUNDLEX_MYSQL_TEST_URL）。

## 本机真实运行证据（第 4 轮）

- `var/recall-runs/qr-local-01`：旧代码，48 calls / $0.029，`not_generated`；暴露 G07/G10 `RECALL_NO_APPLICABLE_OPERATION` 与账本 readonly 停止（催生 FL-D048）。
- `var/recall-runs/qr-local-11`：修复后，48 calls / $0.0284 / 198s，`not_generated`；survey 找到摘要 G22 p1357；sweep findings 0；仍有 G15 `RECALL_TARGET_UNRESOLVED`（跨段参考文与合同变体不匹配）与 G05 一处 `RECALL_COMPOSE_FIXED_TEXT_MISSING`。已针对这两类再改：非等价旧文先归一化再拆分（`_normalized_operation_text`）、`_operation_fingerprints` 逐级降级匹配、停止码细分。
- `var/recall-runs/qr-local-12`：上述再改后的运行完成（143 calls / $0.0748 / 512s，`incomplete`，targets 30 / edits 14 / rounds 5）。剩余未解决 12 项，下一条动作的输入：
  1. **G15 跨段目标未解析**（`RECALL_TARGET_UNRESOLVED`，p806；盘点引文与合同变体文不一致，sweep 本轮未报该规则，故 composite 重绑定没触发）→ 需要在“盘点/审计给出的目标本身引文未解析”时也走 `_operation_fingerprints` 降级匹配（不只是 sweep finding）；
  2. **G05 p760 假阳性**（survey 生成 `Y003`，plan 落 compose 后 `RECALL_COMPOSE_FIXED_TEXT_MISSING`，审计已判 wrong）→ 两处待查：① `_survey_targets_from_hits` 的引文切片疑似偏移一位（记录 quote 为“人并报中国证监会备”，实际应为“并报中国证监会备案”，导致 `_splice_fragment` 失配而走 compose）；② p760 是基金资产估值差错更正条款，与费用类别调整无关，需在 survey/规划入口按上下文过滤或交由审计裁决后不再进未解决。
  3. **审计未通过 4 项**：G03 p141（wrong）、G05 p142（incomplete）、G15 p806（incomplete）、G16 p809（wrong）→ 逐条读审计理由与产物片段核对（如属模型误判需按证据回驳，如属真实缺陷则修）；
  4. **sweep findings 5 条**：G16 p227、G18 p139/p829/p1217、G22 p142 —— G18 三条对应 FL-D047 里“已满足判定”的适用问题（p139 变体未被识别为已满足；p829/p1217 是摘要对应位置的追索），G22 p142 疑似位置错配（p142 是类别调整句，真实清算条款在 p978/p1357 已改），G16 p227 是摘要对应位置的追加缺失。
  以上均为“开发中真实缺陷”，不是评测或替身：修复后应在云端 quality-return-10 复验。

## 外部阻塞

- ~~**公网 HTTPS 未配置**（无域名）~~ **已于 2026-10-15 解决**：用户提供域名 `fundlex.club`，A 记录指向 `8.155.130.168`；已配 nginx + Let's Encrypt（acme.sh，自动续期），**`https://fundlex.club` 公网实测 200、证书有效、http 301 跳转 https**。详见集中问题记录 FL-D044。宝塔面板若重写站点 SSL 设置可能覆盖配置，旧版备份为 `fundlex.conf.pre-ssl-*`。
- **本机账本限制**（已登记 FL-D048）：本机 `var/` 目录被同工作区其他 agent 会话持续占用，SQLite 稳定 readonly；本机运行账本必须放项目目录之外（`%TEMP%` 或 `%LOCALAPPDATA%`）。迁移后本机仅作只读备份，此限制不再影响主开发。
- 评测额度：服务器账本 cap 20000 次 / $50（示例配置）。评测 28 份预计 $5—15，需用户确认额度或沿用服务器凭据。

## 模型账本与预算（预登记）

- 价格：input $0.15/M、output $0.60/M（OpenCodeGo deepseek-v4.1-flash）。
- 本轮（第 4 轮）已用：本机开发运行合计约 106 次调用 / ≈$0.06（qr-local-01 约 10 次、qr-local-11 48 次、qr-local-12 进行中；口径以各运行 report_json 的 `model` 段为准）。均在 P3—P5 预登记额度（≤1500 次 / ≤$8）内。
- 迁移后：开发验证默认走服务器应用链路，调用记 `/var/lib/fundlex/model_budget.sqlite`；常驻 agent 自身调用单列跟踪、不混入。
- 每次真实批量运行前写 `protocol.json`（样本/版本/预算/最坏调用上限），见实施计划 §5。

## 运行中的进程 / agent（迁移时）

- 本机：`qr-local-12` 开发运行（账本在 `%TEMP%\ledger-qr-local12.sqlite`）仍在执行；其产物在 `var/recall-runs/qr-local-12/`，不影响迁移（`var/` 不打包）。
- 本工作区另有其他 agent 会话在活动（`docs/RESIDENT_AGENT_SETUP.md` 等新文件非本轮所写）；迁移前已核对本文件与集中问题记录无冲突。
- 云端：`fundlex-recall-api`/`fundlex-recall-worker` 常驻（systemd）；`opencode.service` 常驻（127.0.0.1:49374）。

## 下一条可执行动作（服务器工作区，第 5 轮后）

1. ~~发布~~、~~quality-return-10/11/12 真实链路复验~~ 已完成；FL-D052 四类缺陷全部收敛，quality-return-12 `delivery_status=complete`、unresolved 0。
2. **P6 评测**：28 份（20 开发 + 8 留出），引用 `/home/opencode/data/MANIFEST.sha256` 冻结样本，写 `protocol.json`，独立标签冻结、评分读实际 DOCX；结果落 `docs/REAL_REVISION_EVALUATION_RESULTS.md`。预登记预算（≤相应调用/费用上限，ledger 放项目外）。
3. **FL-D053 清理**：请用户协助清理 quality-return-10/11/12 的临时账号与任务（无 DELETE 接口、DB 需 root 凭据）。
4. **P7**：浏览器端到端、服务重启续跑、双身份隔离、指引切换、MySQL 备份恢复演练。**正式入口 `https://fundlex.club` 已上线（FL-D044 已解决）**，P7 浏览器验收可直接走该 HTTPS 域名。

## 关键命令

- 服务器工作区测试：`cd /home/opencode/fundlex && .venv/bin/python -m pytest tests -q`（或只读用 `/opt/fundlex-recall-first/.venv/bin/python`）。
- 发布：`/home/opencode/fundlex/tools/deploy/publish_workspace.sh`。
- 云端真实运行：`python -X utf8 -m tools.deploy.cloud_task_run --contract "..." --output var/cloud-runs/<run> --timeout-min 30`。
- 资料目录（与工作区分离）：`/home/opencode/data/{funds_word,references}`；清单核对：
  `cd /home/opencode/data && awk '!/^###/ {print $1"  "$2}' MANIFEST.sha256 | sha256sum -c -`
- 本机（只读备份）真实运行：账本放 `%TEMP%`，命令见 `tools/evaluation/recall_run.py` 顶部说明；资料迁移脚本 `tools/deploy/migrate_data.py` / 工作区迁移脚本 `tools/deploy/migrate_workspace.py`。

## 本轮新增断点（2026-10-17，B 类全量排查 + 指引适配排查）

- **FL-D104**（已提交 `e780202`，未推送）：514 份全量 B 类（业务含义偏差）排查。报告 `/home/opencode/B_CLASS_REPORT_FINAL.md`，数据 `/tmp/opencode/b_gap_findings_clean.csv`（1638 行 / 509 份），分规则 CSV `/tmp/opencode/b_class_by_rule/*.csv`。**19 项口径待产品负责人裁决**，裁定前不得据以改动引擎/评分。
- **FL-D105**（已提交 `5fc3d70`，未推送）：合同语料 × 指引**结构性适配排查**（确定性、无模型）。报告 `/home/opencode/GUIDE_CORPUS_FIT_REPORT.md`，产物 `/tmp/opencode/{guide_fit_probe2,clause_material,verify_findings}.json`。核心：空格陷阱 386/514、真实类别超 A/C（E/F/Y/D/B/H）、删除型 old_text 大面积对不上（G15 1/514、G17 5/514）、已满足新机制 46/41 份、货币基金 8 份不兼容；**Q1–Q8 待裁决**。
- 两项均只登记"发现与待决"，未改动代码、未发布、未宣称达标。P6 开发集冻结/留出状态不受影响。

## FL-D106 代码改动断点（2026-10-17）

- **已发布并完成一轮真实批次验证**：发布哈希 `recall.py 1f898fe1…` / `recall_pipeline.py ccb2ff94…`，服务 13:59:47 重启；批次 `p6-dev-round9-01`（20/20 完成，$0.5561，无 abort）。
- **指标（同一评分器/标签集，347 目标）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；**round9 219/0.6311/kept9**。相对紧邻的 round8-03：completed **+8**、kept **−2**；相对 round7：kept **15→9**。明显改善：D04/D08/D17/D19 的 G17 删除型 kept→completed、D07 G16 not_executed→completed、D12 G14、D19 G08。
- **D09 崩溃为非本次引入**：82 次 sweep 中仅 1 次 `finish_reason=length`（输出 4000 上限截断）→ `MODEL_SCHEMA_INVALID`；sweep 工作量 84→79 反而下降。属既有输出截断脆弱点（FL-D107），待定处理。
- **未做**：未冻结版本、未跑留出 H01–H08、未写评测结果文档、未打包；未宣称达成 0.9。
- 详见集中问题记录 FL-D106、**FL-D107**。

## FL-D108 / FL-D109 断点（2026-10-17，sweep 输出截断 + 切窗与规则收敛）

- **当前生产状态（已发布并核对）**：`recall_pipeline.py db2ad9d1…` / `model.py 4d66f856…` 与仓库逐字节一致；服务于 **23:23:21** 重启，`/api/capabilities` 200。
- **FL-D108（已实施并生效）**：sweep 响应触到输出上限（`finish_reason=length`）时识别为 `MODEL_OUTPUT_TRUNCATED`，并**把该窗口按整段折半重扫**，而非重试同一超长请求；单段无法再拆则记诚实缺口。（根因实测：82 次 sweep 仅 1 次触顶，p50 输出仅 146 token，故不提高全局上限。）
- **FL-D109 第一步（已实施、已发布、已实测有效，为默认）**：sweep 规则**按窗口覆盖章节收敛**（含 mandatory 强制、不可达回退、空映射回退三道硬兜底），并对越界 finding 记 `SWEEP_RULE_OUT_OF_WINDOW`。round11：completed **225 / rate 0.6484**（round9 为 219 / 0.6311），`SWEEP_LOCATION_OUT_OF_SCOPE` **362→146**、`QUOTE_NOT_IN_WINDOW` 74→22；离线 requirements 文本量 **−87.7%**，每窗规则数 22 → mean 2.0–5.1。
- **FL-D109 第二步（已实施但默认关闭，opt-in）**：章节对齐切窗 + 未分配段落字符兜底，由 `FUNDLEX_SWEEP_SECTION_WINDOWS=1` 开启（当前未设置=关闭，部署已核对）。两次真实批次（round12 219 / round13 222）**无指标增益**且窗口数升至约 26（调用与成本上升），故不改默认。
- **指标台账（同评分器/同 347 标签）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；round9 219/0.6311/kept9；**round11 225/0.6484/kept11**；round12 219/0.6311/kept10；round13 222/0.6398/kept10。观测到显著运行间噪声（D09 跨轮 completed 7/7/0/7/4/4）。
- **全量测试**：`pytest tests` → **667 passed / 6 skipped / 1 failed**，唯一失败为既有无关项 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`（缺 `references/source/*.docx`）。
- **未做**：未冻结版本、未跑留出 H01–H08、未写 `docs/REAL_REVISION_EVALUATION_RESULTS.md`、未打包；未宣称达成 0.9。
- 待推送提交：`157aba6`、`e88b64e`（代码）与 `ef76bce`、`e85e08c`（文档），以及更早的 `3946bdf`、`84402c3`、`bd82207`、`24f4d6b`、`b4039a1`、`a36e64f`、`767cbd0`、`5fc3d70`、`d5aae21`、`e780202`。

## FL-D110 / FL-D111 断点（2026-10-18，全链路复查 + 上游周限额阻塞）【当前断点】

- **本段为最新断点，接续请从此处开始。**
- **产品负责人指示**：先推送代码（已完成）。其后仍需：等上游限额重置后重跑 round14 验证 FL-D110；再收尾冻结/留出/打包。
- **FL-D110（已提交、已发布、单测通过；真实批次待补）**：增量重扫（sweep 第二轮）原来与初次重扫**口径不同**——用 `_artifact_chunks` 而非同一入口，且**未传** `requirements_by_chunk`/`scope_by_chunk`（即绕过 FL-D109 的按窗口规则收敛）。实测约 **1/3 的 case** 触发增量重扫（round11 7/20、round12 4/20、round13 4/20），D12 单案最多 3 轮。已新增唯一入口 `_sweep_chunks()` 并让增量重扫重新执行 `_window_rule_scope()`。另记录 3 项待决机制缺陷（`_target_identity` 60 字截断致旧审计结论可存活；复合删除证据只查锚点段；无 ledger 条目默认 `planned`）。
- **FL-D111（已提交、已发布、单测通过）**：`observability.trace_document()` 把被追踪主体的异常一并吞掉并再次 `yield`，导致 contextlib 抛 `RuntimeError("generator didn't stop after throw()")`——引擎的**可恢复停止**（`RecallPipelineStop`）被降级为普通 `RuntimeError`，worker 判不出停止 → `PROCESSING_FAILED`、`attempt=1`、**永久失败**，"暂停/续跑"设计完全失效。已重写为"只吞追踪自身错误、主体异常原样传播、span 关闭只记日志"。生产证据：worker 日志 `langfuse trace failed …` + `RecallPipelineStop: MODEL_CIRCUIT_OPEN`；DB 中 round14 全部 `attempt=1, PROCESSING_FAILED`。同时 `tools/evaluation/p6_run.py` 增加 `ENVIRONMENT_BLOCKED_CODES` 与"零调用零目标"兜底中止，避免再出现"`completed 20/20` 实际全空跑"的假批次。
- **外部阻塞（当前最重要）**：上游模型服务返回 **HTTP 429 `GoUsageLimitError`（weekly 限额）**，`retry-after: 70343s`（≈**19.5 小时**，自 2026-10-18 12:25 观测起算）。**在此之前无法运行任何真实模型批次**。可用独立账本探测命令模式：读 worker 的 `/proc/<pid>/environ` 构造 `ModelGateway.from_env()`，并把 `FUNDLEX_MODEL_LEDGER` 指向临时文件（勿污染生产 circuit）。
- **round14/14-02 作废**：`p6-dev-round14-01`（19/20 空跑）、`p6-dev-round14-02`（20/20 空跑）**不得用于评分**；空跑发生在 `facts` 阶段之前，与 FL-D110 无关。
- **已推送状态（2026-10-18 12:xx 核对）**：`origin/codex/fundlex-recall-first == HEAD`，ahead=0/behind=0；推送用 `bash tools/deploy/push_with_token.sh`（token 来自 `/home/opencode/.github_token`，不打印）。
- **全量测试**：`pytest tests` → **671 passed / 6 skipped / 1 failed**（唯一失败为既有无关项 `test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation`，缺 `references/source/*.docx`）。
- **指标台账（同评分器/同 347 标签）**：round7 220/0.6340/kept15；round8-03 211/0.6081/kept11；round9 219/0.6311/kept9；**round11 225/0.6484/kept11（当前最好，FL-D109 第一步）**；round12 219/0.6311/kept10；round13 222/0.6398/kept10。round14/14-02 无效不计。
- **限额重置后的下一步（按序）**：(1) 直接重跑 `p6-dev-round14-03`（无需再发布，代码已发布）验证 FL-D110；(2) 与 round11/13 对比指标；(3) 若通过则继续冻结版本 → 跑留出 H01–H08 → 写 `docs/REAL_REVISION_EVALUATION_RESULTS.md` → `tools/evaluation/p6_package.py` 打包。
- **待决定/待决（未实施）**：FL-D110 记录的 3 项机制缺陷；FL-D105 Q1–Q8 与 FL-D104 1–19 仍待产品负责人裁定。
- **待推送提交**：无（已全部推送；此后新增提交需再次运行 `bash tools/deploy/push_with_token.sh`）。
- **安全提示**：2026-10-18 复查期间，读取服务环境时曾有一处命令未能完整脱敏，导致 `FUNDLEX_DATABASE_URL` 中的数据库口令出现在会话输出中。已停止再读该行；如需可评估轮换该口令。

## 当前断点（2026-10-21，Operation Execution Closure）

- **任务**：按用户方案完成 operation identity、final-plan ledger reconciliation、全 applicable obligation Claim Replay、G05 bounded splice、sweep/delete artifact proof、missing-operation recovery、dirty audit/并发/性能。
- **代码**：工作区已修改（未提交）：`fundlex/obligations.py`、`recall.py`、`targeting.py`、`recall_pipeline.py`、`generation/claim_replay.py`、`recovery/types.py`、`model.py`、`models/roles.py`；新增 `tests/test_operation_execution_closure.py`。
- **测试**：最近一次全量 `pytest tests -q` = 939 passed / 6 skipped；最后几处 target/duplicate/site 修复后需重跑。
- **真实子集（临时账本，均 incomplete）**：
  - D01f 37 targets / 18 edits / 133 calls / $0.0806；仅 G17 p760 残句。
  - D02b 35 / 17 / 109 / $0.0831；G16 missing + G17 p823 + G05 residual。
  - D11 29 / 16 / 104 / $0.0936；G05:2 + G16 + G22 audit。
  - D16 40 / 20 / 78 / $0.0476；p822/p1306 duplicate + G06 composite。
- **待完成**：D02c 后台结果；D01/D11/D16 用最后修复重跑；全量 pytest；5 类 Reviewer；文档/证据包；按逻辑 commit 提交推送。
- **明确未做**：未发布生产、未跑 514。

## 本轮实现断点（2026-10-21，未完成）

- 当前 HEAD 仍为 `00312e3bae7047c4ca04762d8f2739bd130894ed`，分支 `refactor/recovery-architecture`；未提交改动包含 Guide certification、Facts class-set、qualification review、site-scoped effects、frozen cassette/run/stage replay、Claim Replay 与 recovery 路由调整。
- 新增 `fundlex/fact_evidence.py`、`fundlex/qualification.py`、`fundlex/frozen.py`、`fundlex/stage_replay.py`、`tools/replay_stage.py`，并新增 `tests/test_recovery_final_invariants.py`。
- 内置 Guide runtime gate 实测通过：source SHA `b77be53c...`, guide SHA `45dd7746...`, 22 rules / 34 operations；未部署。
- 语法编译和 diff check 通过。旧全量测试在新硬不变量下为 883 passed / 59 failed / 6 skipped；失败混合旧测试预期（TRUE→NOT_APPLICABLE、隐式 ONE_OF、未认证 synthetic guide）和实际接线缺陷，不能作为最终验收。新增 invariant 测试尚未单独通过。
- 已修复：`CLAIM_PLANNED_EFFECT_MISSING` 路由至 generation；Audit evidence 按目标 site 验证；append fallback 要求 rule-specific site anchor；ModelGateway 支持 `FUNDLEX_MODEL_MODE=live|record|replay`；frozen run manifest 与 stage replay 均 fail closed。
- 待做：修复新增测试与事实解析边界；审查 all TRUE replay universe、delete residual site-first、scope correction、final sweep 次数与 no-progress hash；更新 Worker `GUIDE_NOT_CERTIFIED` 错误映射；运行针对性测试并记录结果；不进行 live E2E/部署。
