# 多形态指引真实解析+真实直驱修订矩阵实证（2026-11-01）

> 棒1 收官证据：用户点名「这是你需要保证的」——**上传新指引 → 解析出能指导修订的规则 → 真实驱动修订**
> 的端到端成立性验证。全部真实模型调用（FL-D445 无预算门槛），逐调用入账隔离 sqlite
> （`/tmp/opencode/qa/guide-matrix-ledger.sqlite`）。
> 工具：`tools/guide_parse_shape_matrix.py`（树内，可复跑）；产物：
> `/tmp/opencode/qa/guide-matrix/`（构造指引 DOCX、报告 JSON、各驱动 store）。

## 1. 方法

7 个**刻意异构**的指引形态（真实业务措辞、非内置格式）构造为真实 DOCX，逐一走与生产线
**完全相同**的解析通道：`extract_guide_source` → 真实模型 parse → 确定性校验 → 独立核验 →
有界修复（max 2 轮），再经 FL-D898 质量门的确定性评分（可执行 canary、表达检查、
quality_checklist、code_map 完备性）。凡 certified 版本，走**真实直驱链路**：
`create_custom_version`（指引原文字节）→ `finish_guide_job` → `set_current_guide` →
TestClient POST `/api/tasks` + uploads → **真实 Worker 执行修订** → 产物级复核
（diff 实际 DOCX，不采信接口成功）。冻结合同：`references/fee-rule-v2/original/*.docx`。

| 形态 | 构造意图 | 模拟的用户指引形态 |
| --- | --- | --- |
| S1 standard_headings | 领域标题+红色新文案强调 | 内置指引同款双语新旧的典型公告式指引 |
| S2 table_carried_rules | 全部规则装在 DOCX 表格内（FL-D904 形态） | 监管对照表式指引 |
| S3 generic_numbering | 只有「第X条」编号、无领域标题、零强调 | 通用会议纪要式任务分解 |
| S4 errata_micro | 单点勘误（1.5%→1.2%） | 差错更正小指引 |
| S5 no_emphasis | 领域标题在、但全文零强调 | 纯文本粘贴转 DOCX |
| S6 empty | 空文档 | 上传错误文件 |
| S7 corrupt | 伪 DOCX 字节 | 上传损坏文件 |

## 2. 解析+质量门结果（最终轮，全真实模型）

| 形态 | 判定 | 规则数 | 校验 clean | canary | 表达检查 | checklist | 模型轮次/调用 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | **certified** | 1 | ✅ | ✅ | ✅ | pass | 1/2 |
| S2 | **certified** | 3 | ✅ | ✅ | ✅（2 条「不改未说明理由」warning） | pass | 3/8 |
| S3 | **certified** | 3 | ✅ | ✅ | ✅（2 条 warning） | pass | 1/10 |
| S4 | **certified** | 1 | ✅ | ✅ | ✅ | pass | 1/12 |
| S5 | **certified** | 1 | ✅ | ✅ | ✅ | pass | 1/14 |
| S6 | **GUIDE_SOURCE_EMPTY**（显式拒收，零模型，短路正确） | — |
| S7 | **GUIDE_SOURCE_UNREADABLE**（显式拒收，零模型，短路正确） | — |

- **code_map 完备性：三轮运行全部 missing=0**（任何新校验码均有中文解释）。
- 独立核验 findings=0、coverage_gaps=0（最终轮全形态）。
- S2/S3 的 2 条表达 warning（「不改」操作未说明理由）如实放行展示，不阻断——符合
  presentation 层「提示不属于阻断」的设计。

### 跨轮非确定性（如实记录）

全矩阵实跑三轮：第一轮 S2 被结构化门拦下（`clean=False, coverage_gaps=2`，修复轮未收敛），
其后两轮 S2 经修复轮收敛 certified。**同一形同时可拦可过**，证明结构化门真实生效
（非摆设）且修复轮能兜底模型漏段；拦下即用户可诊断（错误为结构化清单），无静默放行。

## 3. 真实直驱修订证据（TestClient+真实 Worker+真实模型）

| 形态 | 版本资格 | 任务终态 | 目标 | 交付态 | 产物复核 |
| --- | --- | --- | --- | --- | --- |
| S1 | certified | completed | **1/1 completed** | **complete** | ✅ 实际 diff 实证（下） |
| S5 | certified | completed | **1/1 completed** | **complete** | ✅ 实际 diff 实证（下） |
| S2 | certified | completed | 0 目标 | honest_hold | 见 §4-② |
| S3 | certified | completed | 0 目标 | honest_hold | 见 §4-① |
| S4 | certified | completed | 0 目标 | honest_hold | 见 §4-②（FL-D927） |

补跑：S2/S3/S4 × 另外 3 份冻结合同（QDII/FOF/弘利，共 9 驱）复用已解析文档零新增解析调用，
全部任务 completed、仍 0 目标（不同合同费率/定义措辞不同，规则无匹配属如实结果）。

### 产物级复核（S1/S5，两份独立解析、同语义新文案）

对 `final.docx` 与输入原件做 OOXML 全文 diff：`insert` 一处，精确位于「…称为C类基金份额。」
之后，插入文本与指引规定的**逐字一致**：

> 投资者通过直销机构（含基金管理人及其销售子公司）申购本基金A类基金份额时，不收取
> 认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。

交付物四件套齐全（final/redline/report_json/report_md），`delivery.state=complete`、
目标审计 `verdict=completed, evidence_verified=true`。**端到端成立**：
上传新指引 → 解析认证 → 普通 API 任务入口 → 真实修订出文。

## 4. 零目标如实分析（不藏失败分母）

- ① S3（泛化编号）：解析出 `append` 新文案正确，但规则标题只剩「第二条」，丢失 S1 的
  「释义-基金份额类别定义」章节信号 → A50 合同定位 0 目标（S1 同语义同合同 1/1）。
  **形态影响定位率**，属既有设计边界，如实记录；建议主线评估「section_hint 缺失时
  提示级检查」（已写入 FL-D927 条目）。
- ② S2/S4：`replace`/`delete` 操作 `old_text_variant=null`（空锚点），**引擎永不可达**，
  却过了全部门禁 certified → 4 份合同 target 恒 0。已入册 **FL-D927**（P2，canary/校验层
  应增「replace/delete可以没有锚点」检查）。这是本矩阵的重要产出：端到端链路反过来
  照出了质量门的真实空档。

工具侧教训（已修并留痕）：首轮 engine_drive store 根与 app 根不一致（我工具 bug，task 落在
另一库）；二轮暴露 **FL-D926**——冒烟类工具把合同字节当指引源上传，`source_sha256` 必不匹配，
worker 按设计 fail-closed（GUIDE_NOT_CERTIFIED）。两点均已修正并在本轮复验通过。

## 5. 账本与纪律

- 真实模型调用：解析三轮+驱动 14 次+补跑 9 驱，隔离账本 **78 请求 / 78 completed /
  $0.088655**（`/tmp/opencode/qa/guide-matrix-ledger.sqlite`）；FL-D445 无门禁，仅观测。
- env 白名单仅 LLM_*/FUNDLEX_MODEL_*（dev 鉴权，未加载生产鉴权变量——401 教训复用）；
  env 用 Python 逐行解析（systemd 语义），未打印任何值。
- 全程可复跑：`sudo -n .venv/bin/python /tmp/opencode/qa/run_matrix_env.py`。

## 6. 结论

1. **「上传新指引 → 解析出能指导修订的规则 → 真实驱动修订」端到端成立**（S1/S5 产物级
   diff 实证，非接口成功替代）。
2. 质量门真实生效：S2 一轮被拦一轮修复过（非确定性如实披露）；S6/S7 显式拒收；
   表达检查输出中文 warning 不越权阻断。
3. 矩阵反哺出真实缺陷并已入册（本线不收尾修复，交主线）：**FL-D926**（冒烟工具指引源
   用错字节，parsed 形态永不可直驱）、**FL-D927**（空锚点 replace/delete 可 certified
   但永不可达——质量门空档）。
4. 边界声明：构造指引代表 5 类真实形态但非全部；每形态修订实证合同数有限（S1/S5
   各 1 份完全实证、S2/S3/S4 各 4 份通过但无匹配）；扩大形态×合同覆盖属后续评测波次。
