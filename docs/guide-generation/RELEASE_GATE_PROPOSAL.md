# 指引生成发布守门提案：部署形态 PILOT run 冒烟（原工单任务5成稿，2026-11-01）

> 状态：**提案，待主线裁定**。来源：AUDIT_REPORT.md §5 雏形 + 同日全覆盖审计新证据
> （FL-D906~925）与解析质量门成果（GUIDE_PARSE_QUALITY_GATE.md）。本文件是自含成稿，
> 可独立评审与实施。

## 1. 为什么要这道门

本条线的两次真实教训都证明：**只有通过真实发布形态（发布树路径 + systemd 单元固化
环境 + 沙箱 + 服务用户 + 真实模型）能暴露的缺陷，代码级测试一律不可见**。

- FL-D822：env 文件迁移了语料目录，但生产 unit 内联 Environment 覆盖未同步——worker
  每次运行按秒必败，单元测试全绿；FL-D820 同类沙箱拦截（ProtectHome 挡住 /home 语料）。
- FL-D829/913（同日审计）：后端把异常原文写进 error_code 入库，前端原样渲染服务器路径
  ——功能测试界面不点那个失败分支就永远看不见。
- FL-D907/925（同日审计 P1/P2）：corpus_segmenter 对「目录后直接以第X条起头」的合同
  整篇漏切——只有拿真实语料跑一遍才能量化影响面。

发布脚本 `tools/deploy/publish_workspace.sh`（fundlex-publish）今天只覆盖代码同步+重启。
本提案在它之后、宣布可用之前加**四层守门**，每层有明确断言、失败动作与留痕格式。

## 2. 四层守门

### 2.1 配置一致性断言（秒级，无模型，每次发布必跑）

1. 对全部生产单元 `systemctl show -p Environment` 的固化值，逐一比对
   `/etc/fundlex-recall.env` 中同名关键变量：`FUNDLEX_GUIDE_CORPUS_DIR`、`FUNDLEX_DATA_DIR`、
   `FUNDLEX_DATABASE_URL`、`FUNDLEX_MODEL_*`。内联覆盖要么不存在、要么与 env 文件逐字一致。
   **比对只哈希/比对布尔，不回显任何值**（FL-D901 教训：连接串曾因此进 journal）。
2. 以**服务用户身份**校验路径权限：`sudo -u fundlex test -r <corpus_dir>`、
   `test -w <data_dir>`；`systemd-analyze security` 复核沙箱没有引入新的路径阻断。
3. 发布树关键文件存在：`guides/builtin_guide_v1.json`、`uv.lock`；并断言
   `funds_word` **不存在于发布树**（防止硬编码回退路径复活，FL-D822 同族）。
4. `PARSER_VERSION`/`SCHEMA` 版本登记：若本发布含 guide/segmenter 解析器版本跃迁
   （如 guide-parse-2、contract-segmenter-2），守门输出必须列出**需要重解析/重切的
   存量对象清单**（含表指引版本、含 TOC 合同），未列入即失败——防止「发布成功但存量
   数据无声过期」（FL-D904/907 的交付形态）。

失败动作：阻断发布通告，输出不一致项清单（键名+布尔，不含值）。

### 2.2 PILOT run 冒烟（真实模型，小口径，每次发布必跑）

1. 上传一份固定 PILOT 法规（既有公开 PDF，如销售费用管理规定），`corpus_limit=1`，
   走**默认 API 入口**（不用开发者临时脚本）→ worker → 完成。
2. 验收断言（全部满足才算过）：
   - `status ∈ {complete, complete_with_unresolved}`；
   - `gg_steps` 全部 `completed`、无 `failed` 残留；
   - `payload.corpus_sync.eligible_files ≥ 1` 且 `corpus_dir` 为发布口径；
   - `error_code` **为空**；且抽样核对 steps/run 的 error 字段**不是裸异常原文**
     （正则拒绝 `errno|Traceback|/[a-z]+/[a-z]+` 形态——FL-D913/829 的直接断言）；
   - `payload.finalize` 的 `residual_check/engine_status` 与终态一致（FL-D918 断言：
     开了 engine 兼容的 run，证据包不得记录 `not_run`）。
3. 失败即阻断发布通告，附 gg_steps 诊断快照（脱敏）。

成本口径：一次 corpus_limit=1 常规 run 的真实模型调用量。守门**不设费用/次数门禁，
只设结果正确性门禁**（FL-D445）。

### 2.3 语料/指引切片冒烟（条件触发，解析器版本变更时必跑）

当发布涉及 corpus_segmenter / guide parser 版本跃迁：

1. 对语料目录按 **N=20 抽样**（含至少 2 份含目录、2 份含表格的合同——边扫边数，
   凑不齐就全量）跑离线切分，断言：
   - 每份合同条款数 > 0，且「只有表格条款」的合同数 = 0（FL-D907 断言）；
   - 无 heading 误判导致的超长缺失段（FL-D925 断言：抽样 diff 切分前后段落数）。
2. 对存量已解析指引版本，跑 `guide_parse_benchmark --guides v4 v2`
   通道不变量（可结构化拦下，不得静默异常），并核对新 `quality_checklist`
   五项全绿或如实标注 advisory。

输出逐份结果写入发布记录（哈希+计数，不写合同原文）。

### 2.4 负向冒烟（可选，测试/预发环境）

临时把语料指向不存在路径，断言 run 以稳定码 `CORPUS_DIR_MISSING` 失败（FL-D821 语义
在发布形态下成立），完成后恢复。证明错误通道本身健康。

## 3. 留痕与阻断语义

- 每次守门产出一条发布记录：发布 commit、发布时间、四层逐项结果（PASS/FAIL/SKIP）、
  断言证据（布尔与计数，脱敏）、PILOT run id。
- **任何一层 FAIL = 阻断宣布可用**；SKIP 只允许在条件未触发（无解析器变更/无预发环境），
  且必须写明条件判断依据。
- 记录位置建议：发布目录 `releases/YYYYMMDD-gate.json`，不进仓库（含内网路径）。

## 4. 实施建议（最小落地）

1. `tools/deploy/release_gate.py`（新，脚本化 2.1/2.2/2.3/2.4，退出码即门禁）；
2. `publish_workspace.sh` 末尾调用并阻断通告；
3. PILOT 法规与断言清单做成守门配置（不入代码常量）；
4. 首轮手工跑一遍四层，把实测时长写回本文件（PILOT 单 run 实测 1h15m @ limit=2，
   limit=1 预期更短——2026-10-31 真实 E2E 基线）。

## 5. 边界（如实声明）

- 守门是**采样+断言**，不是全量验证：它能拦住「部署形态级」事故（环境/权限/版本跃迁/
  通道性错误），拦不住单合同级的解析瑕疵——后者由评测防线（第二波扩样）承接。
- 2.1 的值比对永不输出值本身；违反即等同守门失败。
- 本提案不改变既有发布脚本的代码同步语义，只是其后置门禁。
