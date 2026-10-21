# Recovery 收口轮真实运行证据（2026-10-21）

本目录用于让后续 agent 复核本轮 `refactor/recovery-architecture` 的代码、测试与真实运行结果，避免仅凭聊天记录推断。

## 1. 代码基线

- 分支：`refactor/recovery-architecture`
- 证据对应代码 HEAD：`98d4237`（本轮 commit 见仓库 `git log`）
- 工作区：`/home/opencode/fundlex`
- 全量测试：`pytest tests -q` → **929 passed / 6 skipped / 0 failed**

## 2. 运行方式

- Runner：`run_subset_case.py`（本目录，读取 `/etc/fundlex-recall.env` 的变量名，不包含任何凭据值）
- 样例：D01/D02/D11/D16（开发集）
- 模式：`FUNDLEX_GENERATION_STRATEGY=registry`
- 模型：生产配置的 Primary/Review（账本记录 `configured_model` / `actual_model`）
- 预算：每例最多 200 calls / $0.6；`--business-rounds 3`
- 账本：每例独立临时 sqlite，不触碰生产账本
- 说明：D01 首次重跑遇到上游 HTTP 503（`MODEL_RETRY_EXHAUSTED`），重试后成功；失败尝试未计入最终结果。

## 3. 结果

| case | delivery | edits | calls | cost USD | claim replay | unresolved |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| D01 | incomplete | 16 | 79 | 0.0591 | verified | 10 |
| D02 | incomplete | 18 | 135 | 0.0889 | failed | 3 |
| D11 | incomplete | 15 | 149 | 0.0946 | failed | 7 |
| D16 | incomplete | 19 | 85 | 0.0483 | failed | 13 |

四例均 **不是 complete**。D16 旧版 complete 属 false complete（G15 旧支付机制、G06 转换限制仍在，正文/摘要副本不一致），新版 partial 是正确阻塞。

## 4. 文件索引

```text
index.json                  # 汇总
reports/<case>.json         # 完整 pipeline report（脱敏）
summaries/<case>.json       # claim replay / recovery / audit / unresolved 摘要
ledgers/<case>.csv          # 模型请求账本（task/status/token/cost/error，不含 headers/密钥）
artifacts/<case>-working_final.docx
artifacts/<case>-working_redline.docx
logs/<case>.log             # CLI 运行日志
run_subset_case.py          # 复现脚本（无凭据）
```

## 5. 未推送的原始数据（有意排除）

以下内容保留在服务器，不进入 Git：

- `/tmp/opencode/subset-final4-*` 原始运行目录（临时目录，内容已抽取到本目录）
- 原始 `ledger.sqlite`（二进制运行账本；CSV 已导出）
- 生产数据库/服务端 task report/Worker stdout/stderr（可能含其他任务、账号或运行环境信息）
- `/etc/fundlex-recall.env`、`~/.config/git/credentials` 等凭据文件

如确实需要生产 task report 或 worker 日志，应由 root 在服务器上按任务 ID 导出并脱敏后再提供，不要直接 `git add /var/lib/fundlex`。

## 6. 复核提示

- 先看 `summaries/<case>.json`：`claim_replay.failures`、`recovery.history`、`unresolved`。
- `reports/<case>.json` 包含 plan/targets/audit/sweep/recovery 全量记录，用于逐条核对目标、操作、obligation。
- DOCX 是实际写出的工作产物（非最终交付），用于核对真实修订/残留。
- 已知残余：G06 composite、G15/G17 旧支付/用途句、G13/G14 残留、正文/摘要重复副本与 target overlap、sweep 修复尚未接入 RecoveryOrchestrator、`AUDIT_NOT_COMPLETED` 无根因 route 时 terminal。
