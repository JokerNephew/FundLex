# tools/qa/fullsite — 全站走查走查基建（QA 走查线）v1.1

文书：`docs/qa/FULLSITE_CHECKLIST.md`（检查单/性能阈值表，编号与 manifest.json 一一对应）。

| 文件 | 作用 |
| --- | --- |
| `manifest.json` | 走查条目（FS-V1-xx/FS-V2-xx/FS-LC-xx，103 条），`mode=direct` 骨架期可直接打；`mode=staged` 需种子/编排（阶段二）；`ready_any`=行级优先容器回落；`expect_redirects`=307 断言 |
| `perf_budget.json` | 性能预算（✅/⚠/❌ 阈值），与检查单 §2 镜像，冻结后二者同步改动 |
| `shots.py` | 执行器：截图 + P-TTFB/DCL/LOAD/READY/CLICK/LTASK 实测（verdict 按中位数重算）+ 登录墙/ready 超时显式失败 + 307 断言 + 控制台 error 收集 |

## 鉴权与种子（全部走环境变量，绝不落盘）

- `FUNDLEX_QA_TOKEN`（优先；同源 localStorage 注入，不发请求头）或 `FUNDLEX_QA_USER`+`FUNDLEX_QA_PASSWORD`（V1 表单登录引导）。
- 要求登录态却拿不到 → 整 run 中止 exit 3（防未登录失真）；未登录态条目专用 `--no-auth`。
- 种子：`FUNDLEX_SEED_{TASK,DOC,CMP,PAIR,RUN,GUIDE}_ID` 替换 url_template 占位符；缺失 → 该条 ⛔skipped 并计入覆盖。

## 用法

```bash
# 生产 V1 冒烟（未登录态会落到登录弹层，属预期；用于验证基建本身）
.venv/bin/python tools/qa/fullsite/shots.py --base-url https://fundlex.club \
    --site v1 --samples 1 --no-mobile

# 带鉴权（凭据只走环境变量，不落盘）
export FUNDLEX_QA_TOKEN=...   # 或 FUNDLEX_QA_USER / FUNDLEX_QA_PASSWORD
.venv/bin/python tools/qa/fullsite/shots.py --base-url https://fundlex.club --site v1

# 本地 V2
.venv/bin/python tools/qa/fullsite/shots.py --base-url http://127.0.0.1:5173 --site v2

# 只跑指定条目
.venv/bin/python tools/qa/fullsite/shots.py --only FS-V1-01 FS-V1-64
```

输出：`/tmp/opencode/qa/fullsite/<run-id>/{shots/*.png, results.json, PERF.csv, console-errors.json}`。

## 阶段二待补（骨架明确留白）

1. staged 条目编排：种子数据（task/doc/cmp/gg/guide/admin）、断网/慢网注入、confirm dialog 捕获、未登录上下文。
2. V2 表单登录引导（V1 已实现于 `auth_bootstrap()`）与失败重试断言。
3. LC-01~08 链路编排脚本（起手顺序见检查单 §5）。
4. V2 Suspense fallback 截图：route 延迟注入稳定捕获窗口。
5. LCP/INP 采集链验证后并入冻结表。
6. 截图状态后缀（`<编号>-<状态>-<视口>.png`）在 staged 编排落地时启用。
