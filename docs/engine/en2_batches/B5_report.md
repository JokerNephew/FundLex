# 批次B5回报（v2.py / docx.py）

来源：子审计员 ses_e69bc7c7e（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B5报告

### fundlex/v2.py（1558行，已全读）
- 结论：⚠️ 候选发现 2条
- ① 定位→生成/选择→服务端核验记录→编辑冻结的 fail-closed 状态机清晰，`plan_v2` 与 `v2_pipeline.py:258/105/134` 调用契约匹配（edits+records+content_check），无异常
- ② 失败路径良好：per-target `V2Error` 落 reason、`ModelError` 上抛、`V2_BODY_SUMMARY_CONFLICT`/`V2_ACTION_PARTIAL_REVERTED`/范围冲突均整组 fail-closed；无静默吞错、无失败报成功；无异常
- ③ `failure_reason`/target `reason` 为英文错误码并直接进 report/exceptions（v2_pipeline.py:281），用户可读性依赖前端翻译层——联动 FL-D894，报主线判定；本文件无内部哈希/token直接面向用户
- ④ 无 TODO/FIXME/deprecated；仅 v2.py:1334 与 1343 `action = ruleset.by_id(...)` 重复调用（冗余无害）
- ⑤ 已抽查≥3处跨模块契约并全部匹配：`build_content_check` 抛 `DocxError` 契约↔`docx.py:908`（FL-D112已修）；edit 字段集↔`validate_edit_plan` 校验项；`_recognized_literals` 只回传文内子串故 v2.py:464 `find` 恒命中；`locate["min_chars"]` 由 `rules_v2.py:178-181` 模式强制，v2.py:658 无默认值处安全
- 候选发现1：模块 docstring 与现网职责矛盾｜证据 v2.py:1 `"(evaluation only)"` 对比 v2_pipeline.py:310-327 正式交付分支 delivery_status=complete｜影响：误导审计/接续判断引擎定位｜建议：更正为评测+正式交付双轨描述
- 候选发现2：英文错误码直进 exceptions｜证据 v2.py:1521/1526 `failure_reason=...reason`; v2_pipeline.py:281 `exceptions=[{... "reason"...}]`｜影响：报告端用户见 V2_SCOPE_TEXT_MISMATCH 等技术码｜建议：报主线判定（FL-D894 翻译层覆盖面）
- 已知命中：FL-D112（content_check 返回值，已修）；FL-D568（书签伙伴，已修）；FL-D610/611/612 关联面

### fundlex/docx.py（1776行，已全读）
- 结论：⚠️ 候选发现 2条
- ① 职责单一：OPC 包校验、投影（含 overlay 接受视图）、run 级修订写入与产物独立复核（重开包双向比对）；修订 id 奇 del/偶 ins 步进 2（docx.py:1548-1557）与 selective.py:247/html_view.py:370 的重建假设一致，无异常
- ② 失败路径扎实：全程 typed `DocxError`；`generate_artifacts`/`_generate_identical_artifacts` 异常即 unlink 双产物再上抛；`PLAN_DRIFT`/`FINAL_TEXT_MISMATCH`/`NON_TARGET_CHANGED` 等多重重开校验，无"修改失败报成功"通道
- ③ 错误输出均为内部 code 由上层映射，无技术腔直达用户；作者名默认「资金清算部」已有 FL-D611 登记；`generate_noop_evaluation_artifacts` docstring 明示非正式交付，无异常
- ④ 无 TODO/FIXME/legacy；`generate_noop_evaluation_artifacts` 有 pipeline.py:179/v2_pipeline.py:300 真实调用，非死代码；仅 v2 风格瑕疵：docx.py:32 `Q = lambda`（E731）、docx.py:955 函数内 `import json`，无碍运行
- ⑤ 抽查契约全部匹配：`_edit_region` 同时服务 validate（书签配对）与 `_apply_one`，两侧 overlay 参数同源传递；`normalize_tracked_base`↔`compare/revisions.py:173` `_accept_revisions` 返回 int 计数吻合；manifest 字段↔`_validate_revision_manifest`/`html_view` 消费面吻合；FL-D448 旧坐标混用点现已由 `_accepted_offsets`（1375-1391）+统一 overlay 投影（1065）显式映射，未见复现证据但未经我实测
- 候选发现1：`_max_revision_id_in_parts` 静默跳过解析失败部件｜证据 docx.py:478-481 `except DocxError: continue`｜影响：理论上漏计外方修订 id 最大值（前置 `_validate_package` 已拦住，属防御性吞错，风险极低）｜建议：改为上抛或注释说明依据
- 候选发现2：`_max_revision_id` 对非数字修订 id 静默按 0 处理｜证据 docx.py:1028-1030 `except ValueError: continue`｜影响：畸形 id 不计入 max 可能与生成 id 冲突（`REVISION_ID_UNEXPECTED` 会兜底拦下）｜建议：观察级，报主线判定是否收紧
- 已知命中：FL-D032（段内单段编辑限制）；FL-D448（叠加修订坐标，旧证据点 838/1177 已重构）；FL-D568（已修）；FL-D611（作者名）；FL-D612（死导入观察项）

批次小结：两大文件均为 fail-closed 设计，未发现静默吞错、失败报成功或用户可见技术腔直出。v2.py 两处候选均为低风险（陈旧 docstring、错误码翻译归属）；docx.py 两处为防御性吞错的观察级项。跨模块契约（content_check、edit 字段、修订 id 奇偶、compare 复用函数返回值）抽查全部吻合。已知问题集中于 FL-D032/448/112/568/611/612，无新恶化证据。
