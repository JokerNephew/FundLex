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


## 合并纠偏令（FL-D1105/1106，2026-11-03 起生效）

1. **禁整目录覆盖**：一律逐文件三方合并（交付树×产线实测字节×交付树三分基底），产线独有内容无条件保留。
2. **行前**：全量 sha 对缝表＋差异件逐件注明来源；无主差异=停手。
3. **行后**：对基底末期与当日主线上产功能点清单存在性断言冒烟（函数级存在性）。
4. **基底≠产线**：每次行前先实测产字节，不得以树基代产。
5. 交付物行表随 commit，不解释差异不发件。

## 二度纠偏（FL-D1107）
1. 行前实测产线五件 sha 对照当日 canonical；一不合=停手。
2. 对缝表单列五件实测 sha 与申领名单，不写「前端零变更」自欺口径。
3. 后端波包禁带 frontend/ 路径；前端入包向接班申领两侧来源+sha。
