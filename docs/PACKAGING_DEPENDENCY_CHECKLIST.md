# 机械封装依赖清单（PACKAGING DEPENDENCY CHECKLIST）

每次发布 / 起波前逐条点名。唯一主线家 = `/tmp/opencode/qa-base`（FL-D1067 家法）；各线树完工后归并这里，波次从这里出。

## 前端基线法（FL-D1067/FL-D1073，2026-11-03 接班锤实）

- **qa-base/frontend 已封版 = commit `510f17c`**（生产 d32288a + 主线手修件全收：d1055 drag / d1065b / 生成 tab 处理 / 飞书序 / 七小件）。
- 自此**任何前端波以 qa-base 现 HEAD 为唯一起点**；集成树起波前先执行 `git checkout 510f17c（或接棒封版） -- frontend/` 归一并提交，禁止从各线树旧基线直接发 app.js。
- 发布前端零覆盖原则：生产字节与候选字节逐文件比对（app.css/app.js/compare.* /guide_generation.* /listbox.css 等全部点名），不得以「大体一致」放行。
- 禁止把 `*.bak-*` 等备份残留带进候选负载。

## guide_*/guides/ 域（FL-D1051/1052 衍生）

- 发布必须逐文件点名 `fundlex/guide_store.py`、`fundlex/builtin_cards.py`、`guides/`（builtin_guide_v1.json / builtin_cards_v2.json / builtin_guide_v1_source.docx）。
- 整文件下拉/覆盖前必须 diff：guide_store 是 CARD_SCHEMA_VERSION / BUILTIN_* 常量与 builtin 种子链的宿主，2026-11-03 生产 AttributeError 事故（旧版冲掉常量）即此类伤害；候选 tree 的 guide_store 必须与产验正本（md5 f54d1ffc…）一致或为其超集，并在发布说明里点名差异原因。

## 发布流（不变）

- 只走 REL + 接班 GO 三证：端到端证据 / 回滚+指纹 / 前端零覆盖。
- `bash tools/deploy/publish_workspace.sh --source <reviewed worktree> --commit <sha>`（先 `--dry-run`），发布前 `tools/deploy/check_publish_drift.sh` 必须 OK。
- 发布后核验：五服务 active+cwd verified、关键特性字节级 grep 在产、worker 日志清洁、队列消化、回滚凭据（revert 点+前端回基线+env 旋钮）写入集中问题文档。
