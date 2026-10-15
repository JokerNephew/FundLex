# Langfuse 可观测性与评测闭环（方案 A：Langfuse Cloud）

> 目标：把「模型中间结果」纳入监控，支撑用户要求的三件事（按优先级）：
> ① **评测回归可对比** ② **定位失败根因** ③ **成本与调用效率**。
> 状态：**代码已实施并本地验证；云接入待用户提供 API key**。

## 1. 结论与选型

| 方案 | 结论 |
| --- | --- |
| 自托管 Langfuse（本机） | **不可行**：本机无 Docker，无 Postgres/ClickHouse/Redis/MinIO；内存 7.4GB、磁盘 40GB，且为生产机。全栈需 6 个常驻服务，官方建议 16GB/100GB。 |
| **Langfuse Cloud（采用）** | 本机只装一个 pip 包（`langfuse==5.0.1` + OTel 依赖），零常驻服务、零资源压力。**用户已授权合同资料可出服务器**（见 `AGENTS.md` 合同资料政策）。 |

## 2. 架构：两个接入点，一个开关

```
worker: process_recall_first(...)        ← 一个合同 = 一个 trace
   └─ ModelGateway.call(...)             ← 每次模型调用 = 一个 generation span
        └─ fundlex/observability.py      ← 唯一收口；无 key 时纯 no-op
tools/evaluation/p6_langfuse_sync.py     ← 把评分 verdict 作为 score 回写到同一 trace
```

- **`fundlex/observability.py`（新增）**：所有 Langfuse 交互集中于此。**must never break a run**——任何导入/配置/网络异常都降级为"不追踪"并被吞掉。
- **`fundlex/model.py`**：`call()` 内新增 `_trace_attempt(...)`，每次尝试发一个 generation（复用已有 `event` 字段，不新造结构）。
- **`fundlex/jobs.py`**：新增 `_document_trace(job, store)`，以 **document_id 为确定性 trace seed** 打开根 span（重跑/重试落到同一 trace，不产生重复）。
- **`tools/evaluation/p6_langfuse_sync.py`（新增）**：把 `score.json` 的逐目标 verdict 作为 CATEGORICAL score 回写到对应 trace。

## 3. 环境变量（`.env.example` 已登记）

| 变量 | 说明 |
| --- | --- |
| `FUNDLEX_LANGFUSE_PUBLIC_KEY` / `FUNDLEX_LANGFUSE_SECRET_KEY` | **两个都设才启用**；缺任一则整体 no-op |
| `FUNDLEX_LANGFUSE_HOST` | 默认 `https://cloud.langfuse.com` |
| `FUNDLEX_LANGFUSE_CAPTURE_TEXT` | `1`（默认）发输入/输出原文；`0` 只发 sha256+长度 |

**凭据仍严禁入库**（`AGENTS.md`）：key 只从进程环境读，不写仓库/文档/日志。

## 4. 使用步骤

```bash
# 1) 配置 key（仅进程环境，不落库）
export FUNDLEX_LANGFUSE_PUBLIC_KEY=pk-lf-...
export FUNDLEX_LANGFUSE_SECRET_KEY=sk-lf-...

# 2) 跑一批（worker 侧自动产生 trace；runner 走 HTTP API 不受影响）
.venv/bin/python tools/evaluation/p6_run.py --run-id p6-dev-round2-01 --group dev

# 3) 评分（不变）
.venv/bin/python tools/evaluation/p6_score.py \
    --run var/recall-first-evaluation/p6-dev-round2-01

# 4) 把评分回写到 trace（过程↔结果对齐）
.venv/bin/python tools/evaluation/p6_langfuse_sync.py \
    --run var/recall-first-evaluation/p6-dev-round2-01

# 预览将发送什么（不调用 Langfuse）
.venv/bin/python tools/evaluation/p6_langfuse_sync.py --run <run> --dry-run
```

## 5. 三项需求如何被满足

| 需求 | Langfuse 里的看法 |
| --- | --- |
| ① 回归对比 | 按 `target_verdict` / `target_completion_rate` 分数过滤，比较两轮同名 score 的分布；tag 含 `recall-first`，`session_id=document_id` |
| ② 根因定位 | 打开某合同的 trace → 按 `task_type`（facts/scope/inventory/compose/audit/sweep）看每次调用的**输入、输出、prompt_version、失败码**；失败的 target_verdict score 就挂在同一 trace 上 |
| ③ 成本效率 | generation span 自带 `usage_details`（in/out/total）、`cost_details`、`latency_ms`，可聚合；`reused_checkpoint` 标出缓存命中 |

## 6. 本地验证（已做，无需 key）

用 `/tmp/opencode/otlp_stub.py`（本地 OTLP 收集桩）验证了真实发射：

- 收到 3 类请求：`/api/public/otel/v1/traces`（根 span + generation）、`/api/public/scores`。
- 根 span `recall-first:<file>` 与子 span `recall_facts` **trace id 一致**（分组正确）。
- generation 带 `input`/`output`/`model`/`usage_details`/`cost_details`/`langfuse.version=facts_v1`。
- score 带完整 `metadata`（`case_id`/`rule_id`/`target_id`）、`dataType=CATEGORICAL`。
- 单元测试 `tests/test_observability.py`：5 项全过（无 key 纯 no-op、双 key 才启用、脱敏哈希、真实 `call()` 发 span、trace seed 确定性）。
- 全量测试 **568 passed / 6 skipped**（无回归）。

## 7. 待办

1. **用户提供 Langfuse Cloud key**（public + secret），即可跑通真实云端链路。
2. key 到手后：跑一小批（如 2 例）验证真实 trace 入库 → 再跑整轮开发集。
3. 可选：把 `p6_run.py` 的批次 id 作为 Langfuse tag，便于按批次对比。
