# 直通重构六线协调看板（2026-11-02；持续更新，非交付验收）

## 当前责任与底线

- 本会话 `ses_e724374bfffeSA7sLpyEtWH7Uh` 负责六线接口协调、问题统一入册和真实验收判定；原旧解析/引擎十线及 FL-D1020/旧波次保持冻结，不恢复、不用旧产物冒充新验收。各线若无法直接跨会话发消息，先在自己的 worktree 写交接并将路径与 commit 发至本会话；所有问题集中记录由本会话统一合并。
- 其他领域接班会话 `ses_e63e3258fffex4p6mYKYQlBkYH` 已确认冻结边界：本轮 FL-DT-01～05 已由其 `f823692` 权威映射为 FL-D1028～1032；下一可用编号为 FL-D1033，后续派号仍由接班统一管理。生产部署只经 REL 唯一发布官 `ses_e648914e4ffeoIO6UsKqu04go2` 和明确发布令。第 6 线只能在隔离树集成/验收并提出发布候选，不能自己 sudo 发布。旧 INT 冻结合并槽不擅取。
- 第 5 线 `frontend/` 与接班侧仍活跃 FE/CX/V2 的 V1 前端线路可能同文件重叠（FL-D1032，跨域共管）；两侧均保留各自 commit，集成逐区块审查，禁止直接覆盖/重置共享树。集中问题文档如有两边修改，不在脏工作树执行 `git pull --rebase`；保留双方条目后在独立分支逐项整合。
- 接班会话已向 FE/CX/FE-E/FE-F/FE-G/FE-H/V2 七条前端线下隔离令；其核对 `/home/opencode/fundlex` 当前 tracked 改动仅集中问题文档的旧留一笔、无双方前端新混写。**当前未见前端冲突；未来合并点仍须双边 commit 逐区块审查并交 REL 发布。**
- 已通过 OpenCode V2 会话列表和 `git worktree list --porcelain` 核查六个对话在运行。会话收到工单≠代码完成。各线独立 worktree；`/home/opencode/fundlex` 共享主线有他人未提交文档和未跟踪公开样本，任何线不得直接写入/清理。
- 本看板来自 `/tmp/opencode/qa-base` 的 `qa/full-audit-20261031` 工作树。其未跟踪 `docs/DIRECT_THROUGH_REFACTOR_ASSESSMENT_20261102.md` 是本轮评估，保留。集中问题文件修改只在本工作树进行，后续合并时核对共享主线的独立改动。

| 线 | 会话 ID | 工作树/当前事实 | 核心交接 |
| --- | --- | --- | --- |
| 1 指引卡 | `ses_e639e3431ffe6zLWyGAzw7hMvw` | `.../guide-cards-direct-20261102`；`101efa4` 已冻结初版契约，解析代码仍有未提交工作 | `docs/DIRECT_THROUGH_CONTRACT_20261102.md`、`fundlex/guide_cards.py`；待确认模糊定位规则不误删及真实 V2 解析 |
| 2 定位/改写 | `ses_e639c4ef0ffeCQvPmWIIB2VQrt` | 已核实会话位置移至 `.../direct-edit-line2`；本轮尚无该线新提交证据 | 已发第 1/3 线契约位置；等提案接口和真实合同证据 |
| 3 DOCX 写回 | `ses_e639a6244ffeyIDbgHRRh0Hp4e` | `.../direct-writer-line3-20261102`；接口草稿未提交 | `docs/DIRECT_WRITE_LINE3_CONTRACT_20261102.md`；待收紧摘要授权、生成记录绑定及原修订拒绝能力 |
| 4 后端接线 | `ses_e6393dc2fffeZVb0mp9USiyZV3` | 已核实会话位置移动至 `.../direct-backend-line4`；尚无该线新提交证据 | 待 `direct_edit_v1` 后端报告/下载契约；旧 `builtin-v1` 不得伪装新卡或静默 fallback |
| 5 V1/公开报告 | `ses_e6391ae3cffeeUamXKOpDrA5y3` | `.../direct-line5-v1-workbench-20261102`；暂无该线新提交证据 | 已发第 1/3 线契约路径；待真实已写回计数贯穿 ZIP/CSV/飞书/报告及截图 |
| 6 集成/删旧/验收 | `ses_e638f9454ffeEnYk7tKYVMbzna` | 已核实会话位置移至 `.../direct-integration-line6`；本轮尚无该线新提交证据 | 待五线 commit、依赖迁移/物理删除清单、真实工作台验收 |

上表 `.../` 统一前缀 `/home/opencode/.local/share/opencode/worktree/29a9a9/`；会话位置不等于实际写入路径，后续以逐线 `git status`、commit 和运行证据复核。

## 本轮接口核查（静态，未验证实现）

- 第 1 线契约初版 `guide_card_v1` 卡片 ID `card_id`、包字段 `cards`、解析入口 `build_guide_card_document`；初版文档 `docs/DIRECT_THROUGH_CONTRACT_20261102.md:89` 和实现 `fundlex/guide_cards.py:313-317` 要求 replace/delete 必带引句，可能漏掉只有指定章节+语义事项的规则卡，已直接要求该线核对并补测试（FL-D1028，原 FL-DT-01）。
- 第 3 线草案 `direct_edit_proposal_v1`/`direct_write_scope_v1`/`direct_edit_write_v1`，写回接口 `write_direct_edits`，改动计数来自重开产物。草案 `summary_sections` 缺省可放行整个摘要（FL-D1029，原 FL-DT-02）；字段自算 SHA 不构成可信生成来源绑定（FL-D1030，原 FL-DT-03）；属性变更类原修订 reject 不支持（FL-D1031，原 FL-DT-04）。已向第 3 线派纠正与证据要求，第 2/4/6 线同步作为接口/验收风险。此处是**草案风险**，不得当成已发布行为。
- 第 4 线应将新卡、提案、写回结果整合成版本化 `direct_edit_v1` 用户与内部报告，必须保持身份/配对/hash 闸门。第 5 线只据真实 manifest 显示修改数；第 6 线五线交付前不提前集成。

## 下一动作及门禁

1. 第 1—6 线会话位置均已核实为各自独立工作树；继续核对各线实际写入路径、commit 和共享主线是否有其他领域未提交工作，不视为功能验收。
2. 收齐第 1/2/3/4/5 线契约与 commit；优先裁定摘要逐处授权、来源绑定、双层修订、旧内置默认指引；所有问题及时更新 FL-D1022。
3. 第 6 线在独立工作树逐线合入，检索并物理删除替代旧业务；对受影响单测/数据库迁移/登录与授权回归。
4. 最终仍需真实登录工作台、上传指引、提交确有改动目标的真实合同、真实 Worker/模型、重开 DOCX 差异/双层痕、结果页与本人授权下载；未完成不宣称交付。模型费用不设本地审批上限，保留技术资源与有限重试。
