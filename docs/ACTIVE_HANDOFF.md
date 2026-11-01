# ACTIVE_HANDOFF（2026-11-02 00:1x，压缩前存档——读我继续干活）

## 目标与铁规
用户=产品负责人，全程生产挑刺。铁规：①不简化用户要求（FL-D920）②改完截图自检+子agent质检双保险（缺=驳回）③完工30min内验收或驳回（SLA）④真实模型无预算（FL-D445）⑤发现集中登记（FL派号走主线）⑥端到端交付前不擅自停。分工：裁决/派号/GO=我；界面验收(S1)=监督线；合并/验证=INT线（唯一可写主线树副官，章程dispatch-draft-INT.md）；监督抽审INT。当前在 qa/full-audit-20261031 分支，主线树=/tmp/opencode/qa-base。

## 盘面状态
- **第二波 100 份在跑+初读出刺**：holdout25 初读 50.4%、wrong=0、**fc=2 七波首破（FL-D1002 双形态：gate旁路W2H04/audit盲区W2H12）**——EN1 已接根因令；dev75 续跑中；总判定待全量读数+主线裁定，未 pass 未 fail。
- 引擎修复在主线：FL-D981/869（r3=92.8%）、EN2 B类14件（完工待INT收，其中 recall.py 最小刀需我 ACK）、FL-D1001 sealed（待INT收）。
- 前端战区：FL-D991 下拉框✅并入+已验收；FL-D989 飞书独立页✅并入+已验收；**FE 全屏回退（FL-D987）施工中（00:07 有动静）**；FE-B 的 F2 施工中；FE-C 的 990/994/992 停滞被二催；QA 校枪已交；CX 992-Compare 待出。
- A 轨：GG 形态学已并入；A6 实战压测被三问（欠账惯犯）；EVAL 黄金集 A2/A3 基线已交（直接可用率 gate=0 归因 FL-D1001，修复后 17 对补测）；W3 第三波标注器方案已交。
- 监督：ACCEPT 三件（989/991/QA-P1）；SLA 曾双破已催。

## 会话映射（尾部ID）
FE=l8yCbACU FE-B=tljVou FE-C=97M5v5L CX=OhgIvj8 V2=81FirpsQ GG=XMWmAw4 EN1=LzndoPec EN2=Kdvq1x EVAL=CBU8V6tg PL1=ivRkf1jH(只读待命) PL2=czGpu W2=kvvQwuiB W3=TuPbxp8Vf QA=YzywIt15 监督=O4MKd INT=zEYTMn

## 待办（按序）
1. EN1 的 FL-D1002 双形态根因报告 → 修复 → 全量回归 → 影响第二波总判定
2. INT 收 EN2 B类+FL-D1001（recall.py diff 需我 ACK）；监督验收 FE 全屏回退件
3. dev75 完 → 第二波总判定（fc=2 前提下裁定，可能=修复后重跑）→ 如实报用户
4. FE-C 二催观察期；PL1 D4 主线自行接手做（FL-D900~906 分级表，欠）
5. 前端战区全收→发布#5（含 r3+新引擎修复）→QA 阶段二全站扫荡（103格）→真实端到端→GO/NO-GO 汇报→touch /tmp/fundlex-watchdog.stop
6. 待用户拍板：FL-D937⑦ 模型下拉清单是否按供应商现目录更新（小问题，下次对话捎带问）

## 红线
- 第二波任何判定不许隐去 fc=2；gold 不许改。
- 上下文窗口已调 1024k；压缩纪律50%整理。磁盘现 4.7G 健康。sudo -n 可用（部署用）。
- FL 派号下一个可用：FL-D1003 起。
