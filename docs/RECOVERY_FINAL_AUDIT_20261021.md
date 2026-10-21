# Recovery 最终收口审计与实施账本

## 起始事实

2026-10-21：按要求顺序执行 `git fetch`、`git checkout refactor/recovery-architecture`、`git pull`，均成功。

- HEAD：`00312e3bae7047c4ca04762d8f2739bd130894ed`。
- branch：`refactor/recovery-architecture`。
- working tree：clean，与 origin 同步。
- 本轮费用策略：先离线审计、录制回放与回归；不增加调用预算、retry 上限，不启动新的 live E2E 调试，不发布生产，不跑 514。
- 此表描述改动前代码；实施/验证另记，不能把审计建议冒称完成。

## 全链路审计

O=operation 粒度；S=site 粒度；D=确定性；M=模型判断。混合链路标注具体分工。

| 层/职责 | 输入 → 输出 | O/S | D/M | 已核实风险 |
| --- | --- | --- | --- | --- |
| Guide/Rule IR：来源解析及编译 | DOCX/JSON → rules/obligations | O；无合同 S | M 解析，D 校验/编译 | 缺 runtime certification；旧 findings 裁定无双 SHA；内置 document_sha 未重算；ONE_OF 由文字隐式推导 |
| Facts：画像/收费关系 | source → Facts | 无 O；quotes 有来源 | M 提取，D 引文 | Primary 没有 class_set_quote，真实 A/C/E 可漏 E；值真实不等于集合完整 |
| Applicability：是否有义务 | conditions/Facts/local evidence → TRUE/FALSE/UNKNOWN | O；局部 S | D 分支，M 仲裁 | resolve 在 Inventory 之后；required_facts 未统一前置；model override 可绕事实完整性 |
| Qualification：整份排除 | fund type/evidence → eligible/excluded | 文档 | M + D 引文 | Primary 单次排除，无独立认证 |
| Scope：搜索路由 | rules/structure → sections | rule 级 | M | 空映射仍被 projection 当 NOT_APPLICABLE；不得回答 WHETHER |
| Inventory：目标盘点 | window/Facts/rules → targets | 可携带 O/S | M + D bind | 不唯一 attribution；UNKNOWN 后变 TRUE 目标遗漏 |
| Deterministic Survey：补召回 | references/source → hits | O/S | D，变体可 M | satisfied 的 rule/global 证明需与统一 evaluator 收口 |
| Open Operation Discovery | TRUE ledger/covered ops → candidates | O/S | D→bounded M | 已 operation-first；append fallback/语义 site 需进一步核对 |
| Target Attribution | target/span/operation → identities | O/S | D | 已 fail closed；跨 transformation 身份还需消除 object identity |
| Planner | attributed target → candidate edits | O/S | D/T3 M | operation effects 没有统一输出；G08/G11/G14 copied dict index 路径需审 |
| Overlap/Merge/Joint Compose | candidate edits → merged edits | components O/S | D + M | same-site atomic transform 不完整；component span 可能交叉归属 |
| Final Edit Set/Ledger | executable filtering → edits/ledger | O/S | D | 已 reconcile；需加强 operation effect 对应、掉落不静默 |
| DOCX Writer | source/plan → DOCX pair | edit/span S | D | 保留 source binding、validate、re-open、FINAL_TEXT_MISMATCH；无证据不重构 |
| Actual Artifact | re-open DOCX → inspection | paragraph S | D | source offset 不能直接 slice final offset |
| Hard Validator | authorized text/span → PASS/FAIL | O/S | D | 不放松；merged component 必须只消费自己的授权 |
| Audit | before/actual/rule/ledger → verdict/evidence | target/rule；S evidence | M + D quote | wrong + evidence_unverified 仍进入 issue/recovery；需 focused re-audit 和 proof 仲裁 |
| Claim Replay | all TRUE obligations/actual → proof | O；S 部分 | D | append/replace 用 after_full；无 site delete 可全局缺失冒称满足；component spans 串用 |
| Sweep | full artifact → candidates | rule/location | M + D | scope 外 candidate 可能被丢；finding 分类/proof 与 Claim 不统一；轮数调度需约束 |
| Recovery | failures → root cause/action | O/S 字段已存在 | D 路由 + M 修复 | PLANNED_EFFECT_MISSING 错走 target/execution；hash 少 facts/applicability/scope；重复无意义工作 |
| Obligation Projection | run state/proof → completion | O；S 借用报告 | D | TRUE 多处能被置 NOT_APPLICABLE；rule/sibling shortcuts 可借证据 |
| Delivery Gate | ledger/hard validation/replay/sweep → delivery | 全文 + O | D | 依赖上游证明质量；必须检查每个 TRUE 自身及全部 site，unsupported review 不能取代 proof |
| ModelGateway/Performance | requests/budget/cache → result/metrics | task/context | D 传输 | 无冻结 cassette；普通 checkpoints 不能独立阶段回放；保留 bounded concurrency/locks |

## 实施批次与验收

1. Guide certification、显式 group semantics、TRUE invariant。
2. Facts 完整集合、依赖门、exclusion 双认证、Applicability 顺序。
3. OperationRef、atomic/site effect evaluator、Claim/Projection/Sweep/Audit 共用证据。
4. root-cause recovery、dirty site/signatures/no-progress、最多两次 Final Sweep。
5. Frozen Run record/replay、Stage Replay、离线缺陷矩阵与完整回归。

最终仍需按 AGENTS 走真实工作台交付验收；离线通过不等于真实合同 complete。已有 D01/D02/D11/D16 的 incomplete 原因保留，不重写历史分母。

## 当前发现

- 内置 Guide `validation.clean=true`，却仍有 10 个独立 findings；旧 residual_review 没有稳定 finding_id、approved 和双 SHA。
- 内置 `document_sha256=3932d4ca…`，现有规范 hash（去掉自引用字段）为 `8db9b5b7…`，不一致。必须验真实 payload，不能信字段。
- Primary Facts 仅验证逐类别 quote；完整集合验证只在 focused recovery，需上移。
- runtime API 实际为 `127.0.0.1:8010`；health 返回 401，证明监听/认证在工作。此前 8000 端口问题属于错误默认入口推断，已更正 FL-D139。

## 当前实施结果（2026-10-21，尚未真实交付）

完整离线回归 977 passed / 6 skipped；compileall 与 diff-check 通过。新增 atomic paragraph planning、dirty-site replan、site-first residual、operation/site Audit 去重、append duplicate 独立覆盖与零网络 Frozen Stage Replay，具体证据见 FL-D140 和 ACTIVE_HANDOFF 最新段。

本轮 live 调用/费用 0，未部署。仍需审查认证裁定来源与剩余 rule-level satisfaction helpers，并完成一次真实工作台录制、实际产物与授权下载验收。不能依据离线测试宣称真实合同 complete 或本轮最终收口完成。

离线阶段命令：`.venv/bin/python tools/replay_stage.py <frozen-run-dir> <facts|applicability|targets|obligations|plan|claim_replay> [--revision N]`。record 使用 `FUNDLEX_MODEL_MODE=record` 与每份合同独立 `FUNDLEX_FROZEN_RUN_DIR`；replay 缺少相同 request cassette 时直接失败，不回落 live。
