# 批次B1回报（claim_replay.py / joint.py / atomic.py）

来源：子审计员 ses_e69bdd6a（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B1报告

### fundlex/generation/claim_replay.py（2686行全读）
- 结论：⚠️ 候选发现 3 条
- ① 职责为产物级声明重放（段落完整性+义务/站点双重证明+残留扫描+分页），状态流转（FAIL→语义审计替换→ONE_OF补证→verified聚合）自洽，分页截断永不报 verified，无异常。
- ② fail-closed 为主：except 处多为「缺站点不能再证」方向；仅 818 行 `except Exception: pass`（已 noqa，只收窄容差集合，方向安全）。发现一处审计通过清障可能连带吞掉结构失败（候选1）。
- ③ 失败 reason 为英文技术句（如 "an edit is bound to a FALSE applicability operation"、"multiple targets … lack occurrence identity"），入 report failures 可能直出前端，联动 FL-D816/894 口径（候选3，报主线判定）。
- ④ 无 TODO/FIXME；「legacy」均为已写明语义的兼容路径（314/354/1153/1175 行），非死代码。
- ⑤ 抽查：`validate_edit`（validators.py:488）与全部 5 处调用签名一致；`evaluate_operation_effect`（effects.py:834）与 2216/2378 调用一致；`claim_components_for_rules`（components.py:124）与 joint.py:98 一致。轻微：模块 docstring 代码清单（9-10 行）远落后于实际 20+ 错误码。
- 候选发现1：语义审计PASS可连带清除同义务结构完整性失败｜evidence claim_replay.py:2343-2346 `failures[:] = [f … obligation_state[obligation].state != "PASS"]`｜此前逐 unit 记录的 CLAIM_OPERATION_SPAN_UNAUTHORIZED/OCCURRENCE_MISMATCH（带同 obligation_id，1733-1814 行入册）会随 obligation 被审计证明翻 PASS 而整体消失，verified 可转真｜建议清障仅限效果类失败码、保留结构完整性码；报主线判定
- 候选发现2：残留扫描裸访问 `record.applicability.status`｜evidence claim_replay.py:2575｜同文件 replay_claims 一律 getattr 链防御（1379 行），此处 applicability=None 即抛 AttributeError 中断整次残留扫描｜建议与 1379 行同口径防御
- 候选发现3：用户可见失败文案为英文技术腔｜evidence claim_replay.py:1389/1462/1568/1752 `reason` 英文句入 report.json failures｜属 FL-D816 文案人话化的引擎侧源头，若前端直出即外泄内部口径｜报主线判定（是否由前端翻译层统一覆盖）
- 已知命中：FL-D444、FL-D437、FL-D391、FL-D136、FL-D570、FL-D571/573/576/579、FL-D792、FL-D698、FL-D237、FL-D270（含码内注释 FL-D192/457/458/606/651/696 均为既有条目实现，未见恶化）

### fundlex/generation/joint.py（125行全读）
- 结论：✅ 无发现
- ① 重叠义务的模型合成入口，先固定文本/删除履行硬校验→`validate_edit`→独立 recall_verify 复核，任一环不过返回 None 由调用方回退冲突（recall.py:9185 回退 remaining），状态自洽。
- ② 无 except 吞错；全部拒绝路径显式 return None，调用方区分 None 与异常，无伪造成功通道。
- ③ 无用户可见字符串（JOINT_INSTRUCTION 为模型侧英文提示词，不入报告）。
- ④ 无 TODO；89 行 `__import__("re")` 为风格瑕疵（另有局部 import re），非缺陷。
- ⑤ 抽查：`claim_components_for_rules`/`validate_edit`/`VERIFY_SCHEMA` 三处跨模块调用签名均匹配；docstring「validator 复核后 review」与代码顺序一致。
- 已知命中：FL-D690/FL-D693（joint 合成触发问题在 recall.py 侧，非本文件）

### fundlex/generation/atomic.py（74行全读）
- 结论：✅ 无发现
- ① 原文坐标系上合成多个已独立校验的变换，区间越界/expected_old_text 不符/真实重叠即 return None，纯函数无状态。
- ② 拒绝路径全部显式 None，无异常分支；`_trim_orphan_tail` 有 FL-D489 回归覆盖（整段仅剩连接词的极端情形会保留原文，方向保守安全）。
- ③ 无用户可见字符串。
- ④ 无 TODO；无死代码。
- ⑤ 调用方（recall.py:8530/10168、recall_pipeline.py:2389）组件字段 start/end/replacement/expected_old_text 与本文件消费一致；overlap 判定逻辑经推演对同位双插、插入+替换同起点均正确拒绝。
- 已知命中：FL-D489（本文件修复实现处）

---
批次小结：claim_replay.py 结构成熟度极高，主流路径 fail-closed 无伪造通道；唯一值得主线裁决的是「语义审计PASS清障连带吞结构失败」（候选1，理论上可让 verified 转真）；另2条为健壮性/文案联动小项。joint.py、atomic.py 干净无发现。
