# 新指引解析质量门——可检验标准与检查清单（FL-D898）

> 2026-11-01，qa-gg-audit 线（工单原文：用户「用户上传新的指引文件，能不能很好的解析成
> 合适的规则，这是你需要保证的」）。本文定义「解析得好」的**可检验标准**，每条标注：
> 检查实施位置（确定性代码/测试/基准工具）、当前状态（已具备/本次补强/未实施）。
> 与《指引上传质量通道》(GUIDE_UPLOAD_QUALITY_CHANNEL.md) 互补：该文描述链路与门禁，
> 本文描述**判定"好规则"的内容标准**。

## S 级标准（用户视角，全部可机器检验）

| 编号 | 标准（人话） | 检验方式与位置 | 状态 |
| --- | --- | --- | --- |
| S1 | 每条规则有**人话标题**：源自指引自己的组标题，非编号、非占位、非内部标识符 | `guide_quality.presentation_report`（新增）；矩阵测试 S-M9 | 本次补强 |
| S2 | 每条规则的**要求表述是可读自然语言**：≥8 字、非占位符、不含内部变量名（`class_count`/`wrong_text`/`operations[`/`rule_id` 等） | 同上 | 本次补强 |
| S3 | **操作指令可执行且具体**：append/replace/delete 的目标文本逐字取自指引（既有校验）；文本不是占位符（「待补」「TODO」「____」）；noop 必须能解释（notes/references 非空为建议级） | 逐字与非空：`validate_parsed_guide`（既有）；占位符：`guide_quality`（新增） | 既有+本次补强 |
| S4 | **章节定位可用**：`section_hint` 非空且属已知业务域集合（域外为提醒级，不误杀新写法） | 非空：`validate_parsed_guide` warning（既有）；域集合：`guide_quality`（新增） | 既有+本次补强 |
| S5 | **无内部变量名外泄到用户可见字段**：title/requirement/notes/诊断 detail/finding 展示位不得出现内部标识符（FL-D883 根治） | 诊断 detail 中文化改造（guide.py，本次）；`guide_quality.INTERNAL_TOKENS` 单测断言（新增） | 本次补强 |
| S6 | **可执行**：权威操作键可注册路由、分支条件可满足、义务编译条数一致（运行时同谓词金丝雀） | `guide_canary.executability_report`（既有，启用闸） | 已具备 |
| S7 | **结构无丢失**：指引每个内容段落都被某条规则引用（coverage_gaps=0）；表格/嵌套内容不得静默丢失 | 覆盖校验（既有）；**表格提取修复**（guide.py，本次，原盲区） | 既有+本次补强 |
| S8 | **能驱动修订**：解析产物走真实引擎路径完成修订交付（与 feat-recall 解析驱动证据对接） | `tools/guide_parse_benchmark --engine-smoke N`（既有工具）；本次实跑留证 | 既有工具+本次实跑 |
| S9 | **失败路径显式**：空文档/坏文件/超上下文/模型失败各有稳定错误码+中文解释+修正建议，绝不静默 | `GuideError` 稳定码 + `guide_report.CODE_EXPLANATIONS` 全映射（既有）；矩阵测试 S-M4~S-M8（新增） | 既有+本次验证 |

## 诊断输出红线（S5 细化，FL-D883 根治契约）

- 用户可见 `detail`：中文自然句，含「第几条规则/第几个操作」位置与可读字段名（「新条款文本」而非 `new_text`，「份额类别数量条件」而非 `class_count`）。
- 面向模型/排障的技术串迁移到 `detail_tech`（repair context 继续用它），用户界面不渲染。
- 独立核验 finding 的 `kind` 是机器枚举；持久化到 issues 时附 `kind_zh`（中文名），前端切换渲染（前端线一行切换，见 FL-D905）。
- `guide_report.CODE_EXPLANATIONS` 必须覆盖全部出口码，未命中即单测失败（映射完备性断言）。

## 质量门检查清单（版本级，每次解析后给出）

`guide_quality.check_parse_quality(source, document)` 汇总一版解析的检查单结果
（advisory，不改动既有启用闸语义），并由 `guide_store._parse_enrichment` 写入
`issues_detail.quality_checklist`，API 直读。检查单项：

1. `structure`：确定性校验 errors=0 & coverage_gaps=0（门禁既有）
2. `verification`：独立核验 findings 全处置、invalid=0（门禁既有）
3. `executability`：金丝雀 passed（门禁既有）
4. `presentation`：S1+S2+S3占位符+S4 检查结果与问题清单（本次新增）
5. `code_map`：出现的全部问题码都有中文解释映射（本次新增）

## 测试矩阵（多形态，断言「能解析成合适规则」而非仅不报错）

`tests/test_guide_parse_quality_matrix.py`（零模型，构造 DOCX）：

| 用例 | 形态 | 断言 |
| --- | --- | --- |
| M1 | 域标题+粗体标准形态（内置 v4 风格，含单一/多份额类别分支） | 全链 clean+canary pass+**certified**+操作逐字 |
| M2 | 无强调格式、域标题纯文本 | 可解析；块报告 segmentation=single-block 不判错 |
| M3 | 无域标题、仅通用编号（第X条/一、） | generic 切块成立；不报「未识别结构」 |
| M4 | 空正文 | `GUIDE_SOURCE_EMPTY` 显式码 |
| M5 | 非 DOCX/损坏 | `GUIDE_SOURCE_UNREADABLE` 显式码 |
| M6 | **规则写在表格内**（原盲区） | 表格段落进入 source，可被规则引用（修复后；修复前=静默丢失） |
| M7 | 含修订痕迹（删除线/已拒修订） | 删除文本不进入 source |
| M8 | 超模型上下文 | `GUIDE_CONTEXT_LIMIT` 显式码 |
| M9 | 模型把内部标识符写进 title/requirement | presentation 检出（S5 红线） |
| M10 | 诊断 detail 输出 | 中文可读+无内部变量名；`detail_tech` 保留技术串 |
| M11 | 出口码→中文解释映射 | 全量覆盖（含金丝雀码与模型失败前缀） |
| M12 | 真实 v4/V2 双文档通道不变量 | 见下「真实模型基准」 |

真实模型基准（FL-D445 政策，手动执行、仅记账）：
`tools/guide_parse_benchmark --guides v4 v2 --engine-smoke 2`——通道不变量
（v4 认证可执行或结构化拦下、V2 必结构化拦下）+引擎冒烟双版本对比。

## 边界（如实声明）

- section_hint 域外值为**提醒级**：不卡门禁（指引可能写新业务域，`scope.py` 只认已知域，
  运行时找不到章节按既有回退处理）。
- 页眉/页脚/文本框内容仍不解析（既有边界，指引正文应在正文流）。
- presentation 检查为 advisory：不改变 certified/enable 闸语义；候选是否升级为门禁由主线定。
