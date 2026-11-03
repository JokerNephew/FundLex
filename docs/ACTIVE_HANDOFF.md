# ACTIVE HANDOFF（2026-11-03 ~16:2x 断点）

## 主线状态
- **提速+体验波已上产**（d32288a，engine 指纹 2b0a2fbe…）：8000窗/节级/截断分层/单锚早停/病灶可见/retry 按钮/FE-E 四连单。五服务健康。
- **波后实测**（后端直连 /opt 构建，results/wave/）：富信FOF 359s/写7、道琼斯 597s/写7、恒阳 328s/写5、安颐 405s/写5（波前产线 42-48min 档）。抽检:安颐5/富信7/恒阳5 全合格；道琼斯发现 2 处缺陷（FL-D1075: p1243赘余、p1355类别错配）。

## 在飞事项（owner / 下一步）
1. **引擎审查层（FL-D1075 修复）**=line2(ses_e639c4ef0ffeCQvPmWIIB2VQrt)施工中：提案级模型审查(零领域词/veto带理由/自我修正≤2/放弃入例外清单/整份≥1写=完成含例外)。交付后**我独立验收**（用户亲令）：道琼斯5好放行2坏必杀、三份17处零误伤、恒裕/恒阳pick12签名∅。验收跑批器已备：/tmp/opencode/batch-run/run_one_cand.py + fix_and_run_cand.py（FUNDLEX_SRC 指候选树）。
2. **扩大回归（8份原始docx）**=子会话 ses_e5f9fe4b5ffe6YwNE0ec3TyeM9 后台跑，报告 results/regress1/REGRESS1_REPORT.md。
3. **.doc 异步转换（FL-D1074，用户裁决）**=line4(ses_e6393dc2fffeZVb0mp9USiyZV3)施工：上传即收即跳页，转换挪 Worker（预热/300s/重试/缓存）。
4. **ESG WRITER_SOURCE_MISMATCH（FL-D1076）**=line2 排队（审查层后接）：管线 sanitize 前置、全链单指纹。
5. **FL-D1077**：重启烧 attempt 致 4 份 EXHAUSTED——调度区分中断/真失败；4份管理员回队列待批（retry端点 attempt<3 救不了）。
6. **FL-D1071** 三模型对比：波后稳定 24h（明日下午）启动，同构建同卡包同判标。
7. **FL-D1069** 限流终态观测：24h 后复查复现率。

## 家法/闸（勿忘）
- 前端唯一起点=qa-base HEAD 510f17c（集成树已并 9fffccc）；PACKAGING_DEPENDENCY_CHECKLIST.md 在 qa-base/docs（复册版）。
- 发布只走 REL+接班GO三证；生产库操作只走 REL 流程；双模型池冻结等用户口令；真模型调用无预算闸。
- 接班 GO 会话 ses_e63e3258fffex4p6mYKYQlBkYH。

## 用户交代口吻
- 不要推算冒充实测；缺陷如实报；产线未修 def 不入 funds_word 波放行。
