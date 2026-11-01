# EVAL 轨集中问题附册（按新纪律：先请赐号后登记，禁止自封编号）

本册承接 qa-feat-recall 在 A2/A3/B3 施工中的新发现。每项：**请主线赐号**后回填编号；历史不删、变更只追加。

## 【请赐号·高危】自定义指引操作注册链路断路：解析再好也无法启用（2026-11-01，qa-feat-recall，A3 基线实证）

- **发现日期**：2026-11-01（A3 基线三路真实 parse 全量读数时；QC 双盲复核后修订口径 2026-11-01）。
- **问题与影响**：`fundlex/generation/registry.py::register_guide_operations`（受控发布方为扩展指引供 OperationSpec 的注册入口）**生产链路零调用**：fundlex/ 与 tools/ 无任何生产调用点（QC 复核：`tests/test_generation_registry.py:124` 有一例既有祖先件 090cc5c 的单测 caller，非生产链路，不影响结论）。后果链（生产实证，非推演）：任意用户上传指引的解析产物，只要声明的 operation id 超出内置指引的 34 键注册表（`register_guide_operations` 设计文档自述「Guide text never creates execution policy by itself」），`guide_canary.blocking_gaps` 必报 `GUIDE_CANARY_OP_UNREGISTERED` → `set_current_guide` 必抛 `GUIDE_OPERATION_REGISTRY_MISSING` → **自定义指引永远不可启用**。
- **三路实证**（真实模型基线 parse，2026-11-01 账本段 var/parse-eval/ledger-parse.sqlite，16 次调用 $0.3513）：
  | 指引 | rules | clean | canary 可执行比 | fatal |
  | --- | --- | --- | --- | --- |
  | V2（修改指引） | 15 组 | **true（校验全过）** | 0.636 | OP_UNREGISTERED ×12 |
  | v4 | 15 组 | false | 0.625 | OP_UNREGISTERED ×14 |
  | v4 勘误版 | 15 组 | false | 0.576 | OP_UNREGISTERED ×14 |
  对照铁证：同一份 V2 的 A3 G 层评分 **规则召回 100%/分支召回 100%/结构正确 100%/true_extra=0**（17/17 规则含指令式分解全部覆盖）——解析质量与可启用性完全脱钩，断路点就在注册链路。
- **机制定位**：blocking ops 的共同形态=解析把指引拆得比内置指引更细（如 G03:1 条件删除、G06:1 多类替换、G10:1~5 六条件变体、G15:1 compound 条件）——这些是**正确**的解析（G 金实证），但注册表键空间=内置指引 operation_id 全集，解析新键无任何供 spec 的通道。
- **处理方法（建议，归主线/GG/引擎）**：①把 `register_guide_operations` 接入指引认证管线——qualified 版本的操作键从解析 document 派生 OperationSpec（执行谓词按 op 类型模板化注册），并留「未经模板可注册的 op 形态」清单给引擎线；②或裁决「uploaded-guide 走 legacy 态」（canary 现为 advisory-only）为过渡口径，但须明示 engine 端 legacy 路径的真实执行覆盖度；③金丝雀测试补「custom-guide 解析产物注册回流」反例（mutation：注册链路断时启用必败）。
- **与已有条目关系**：与 FL-D648（门滑非可执行解析）同族不同层——FL-D648 是门把坏的放进来，本件是门把好的挡在外面（注册无对面）。**这是 B3 冷启动协议的头号实证**：用户原则「不能指望修规则来活」之下，当前连满分解析都活不了。
- **当前状态**：open，高危；请赐号。A3 直接可用率基线如实记 0（gate 口径）并归因本件，不修 gate 前不跑 score-o 引擎评测。
- **验证结果**：上述三路 run 原件 var/parse-eval/runs/*-baseline-20261101.json；注册表 34 键现场打印（G03/G06/G10/G15 均仅 :0）；caller 零命中 grep 双遍。
- **变更记录**：2026-11-01 新增（随 A3 基线报告 v1 上报）→ 2026-11-01 QC 双盲复核驳回字面口径后修正：tests/ 存在单测 caller（090cc5c 既有祖先件），结论措辞由「tests/ 均无 caller」收束为「生产链路零调用」；DETAIL_APPEND 原文措辞失实如实自承。

## 已知待办（不占号）

- `.doc` 抽取设施缺位（14/33 种子边界）+ 保护文档只读通道（1/33）+ OPC_URI 异常（1/33）——A2 片1 已如实边界留分母，请主线裁决设施方案。
- 看门狗 pgrep 自匹配族（r2/r3 运维教训）——修复方案成型（模式外置+python 锚定+阴检），待下一跑批实证。
