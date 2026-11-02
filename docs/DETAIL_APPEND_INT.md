# DETAIL 增量登记附录：INT 整合收口线（不入主册，由总指挥统一并入）

## INT-001 多线「docs 增量与代码混缠同一提交」的摘收损耗（2026-11-01 登记）
- 问题与影响：EN1 的 docs(docs/DETAIL_APPEND_B4_B2.md 创建) 与代码（tests/tools）混在同一 commit（a587223），GG 的棒1 证据 commit（297bda9）与工具混缠，EVAL 的交接/治理档被本线提交触碰（c87bd00 碰集中册、55a3741/6b1237f 碰 ACTIVE_HANDOFF）。按 INT 章程「diff 出任何非 docs 文件→整批不并」「治理档永远不走 INT 通道」，这些登记内容无法经摘收通道入主线，只能整体等线代码裁定，存在登记滞留风险。
- 证据：INT-LOG #1 剔除 30532d1（modify/delete 依赖 a587223）、#3 剔除 c87bd00/55a3741/6b1237f。
- 处理建议（仅登记，决定权归总指挥）：①各线增量纪律追加「docs 登记单独成 commit，不与代码混缠；治理档/主线交接档只读」；②EN1 附录 docs/DETAIL_APPEND_B4_B2.md 全文（a587223 创建段+30532d1 A5 段）请总指挥在主册统一并入窗口一并取件。
- 状态：已登记，待总指挥裁定；不影响今日三批 docs 摘收独立性。

## INT-002 FE-C 树 node_modules 软链「移出后回潮」（2026-11-01 登记）
- 问题与影响：质检 P1 修复（162bc7d 移出误提交的 frontend/node_modules 软链）之后，5a96ccd（P3 文案修复）又将该符号链接重新 commit 入库（mode 120000，tree 核见 frontend/node_modules tracked @ 2821da8）。主线 HEAD 全树 0 个 node_modules 跟踪文件；若按现状摘 FE-C D989 链，tracked symlink 将进主线树（发布/对接/目录扫描面隐患）。
- 证据：qa-base 内 `git ls-tree 2821da8 frontend/node_modules` 返回 120000 blob；主线 `git ls-files | grep -c node_modules`=0。
- 处理方法：阻塞 FE-C 摘取；待该线在 HEAD 再移除一次（git rm --cached 语义）并验证后取件。ACCEPT-D989（T3 复拍）不涉及 git 树态，通过判定本身不受影响，但取件必须等树态清洁。
- 状态：已阻塞登记，报总指挥+FE-C；待修复。

## INT-003 N1 英文裸显族（候补派号登记，随 ACCEPT-FL-D988/992/993 §4 条件）
- 问题与影响：V2 Guides/index.tsx `qualificationStatusText`（:27）映射表仅 certified/frozen_builtin/not_run/failed 四键；后端 guide_store qualification_status 实写 `needs_review`，前端未映射值直接 `|| status` 英文裸显（监督实证截图含 `eligible` 同族裸显）。
- 证据：overseer-reports/ACCEPT-FL-D988-992-993.md §3-§4；证据图 docs/frontend/evidence/guides-20261102/d993-guide-detail.png。
- 处理口径（监督 §4 原话判定机关）：前端映射表对后端枚举**闭集完整覆盖**+未知值回退人话通用句（不回显原码）；一处补丁只补一个值会漏——需先由主线枚举后端 qualification_status 全集。
- 处置建议：派号后由前端域线按「全枚举映射审计」一次补修；属用户第六轮「技术内容怼给用户」族活样本。
- 状态：已登记候补派号（INT 不自封编号），实现侧 V2 已提报、监督独立确认成立。
