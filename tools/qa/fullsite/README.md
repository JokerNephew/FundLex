# tools/qa/fullsite — 全站走查走查基建（QA 走查线）

文书：`docs/qa/FULLSITE_CHECKLIST.md`（检查单/性能阈值表，编号与 manifest.json 一一对应）。

| 文件 | 作用 |
| --- | --- |
| `manifest.json` | 走查条目（FS-V1-xx/FS-V2-xx/FS-LC-xx），`mode=direct` 骨架期可直接打；`mode=staged` 需种子/编排（阶段二） |
| `perf_budget.json` | 性能预算（✅/⚠/❌ 阈值），与检查单 §2 镜像，冻结后二者同步改动 |
| `shots.py` | 执行器：截图 + P-TTFB/DCL/LOAD/READY/CLICK/LTASK 实测 + 预算判定 + 控制台 error 收集 |

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
2. 登录流程化：`v1_form_login()` 已给 V1 骨架，阶段二补 V2 登录与失败重试断言。
3. LC-01~08 链路编排脚本（起手顺序见检查单 §5）。
4. 三数相等自证校验（manifest 条目数 == 截图组数 == results 记录数）纳入 run 末尾硬断言。
