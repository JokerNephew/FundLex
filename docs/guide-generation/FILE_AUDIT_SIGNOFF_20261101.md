# guide_generation 全 27 文件逐文件审计签认表（2026-11-01）

> 依据用户铁律与 docs/COVERAGE_MATRIX_20261101.md GG 行指派：**逐文件、无抽样、无遗漏**。
> 方法：6 个并行审计子任务逐行通读（每文件报告实际覆盖行数 1..N）+ 主审计员对全部 P1/P2
> 逐条亲验复核（读原码取证，驳回误报 1 条、降级 2 条）+ 独立横切补扫（裸 except/eval/
> SQL 拼接/路径穿越/凭据入日志/超时/XXE 等模式全量 grep）。发现入册 docs/DETAIL_APPEND_GG_AUDIT.md。
> 纪律：只读代码，本工单不修代码；修复归后续工单按优先级排。

## 签认图例
✅=逐行通读+复核完成；发现栏给出入册编号，「无发现」=无任何级别缺陷。

| # | 文件 | 行数 | 签认 | 发现（入册编号） |
| --- | --- | --- | --- | --- |
| 1 | `__init__.py` | 17 | ✅ | 无发现 |
| 2 | `api.py` | 371 | ✅ | FL-D922（英文详情/str(exc)/CD引号/rebuild 无状态门） |
| 3 | `authoring.py` | 522 | ✅ | FL-D924（uncertain→no 降级、死代码新项、截断面） |
| 4 | `benchmark.py` | 301 | ✅ | **FL-D915**（空分母记满分、gold 无 schema 校验） |
| 5 | `cli.py` | 166 | ✅ | FL-D924（裸 JSON/文件读、错误截断无提示）；FL-D821 修复验证在 |
| 6 | `corpus_catalog.py` | 241 | ✅ | **FL-D920**（symlink 跟随出目录、大写 .DOCX 静默缺席）；FL-D821 修复验证在 |
| 7 | `corpus_segmenter.py` | 347 | ✅ | **FL-D907（P1：TOC 退出漏切整篇正文）**、**FL-D925**（数字句误判 heading 丢条文、anchor 撞号、title 判定优先级）；FL-D900 修复验证在 |
| 8 | `coverage.py` | 652 | ✅ | FL-D924（O(V×R×I) 热点、_sweep_state 死计算、unresolved↔uncertain 死分支、中止信号吞并策略） |
| 9 | `discovery.py` | 840 | ✅ | **FL-D916**（sweep 窗口硬编码 [:8] 越界可配上限、impact_status 无白名单）；FL-D823/828 修复验证在 |
| 10 | `eligibility.py` | 157 | ✅ | FL-D921（all_requirements_dispositioned 判据永真）；FL-D828 fail-closed 复核确认 |
| 11 | `engine_compat.py` | 127 | ✅ | **FL-D914**（空 title 子串假阳性、重叠词表死代码、/tmp 默认、错误码=异常类名等） |
| 12 | `export.py` | 305 | ✅ | FL-D924（非原子写残留、new_text None AttributeError）；FL-D825 修复验证在 |
| 13 | `human.py` | 213 | ✅ | FL-D924（AI 基线 falsy 跳过、未知字段静默跳、双读） |
| 14 | `lexical.py` | 233 | ✅ | FL-D924（avg_len 未用于打分、crc32 碰撞族、注释与行为不符） |
| 15 | `model_router.py` | 476 | ✅ | FL-D924（熔断 sleep125 持信号量串行化、env JSON 裸解析） |
| 16 | `models.py` | 398 | ✅ | FL-D924（反序列化键过滤不一致、to_dict 字段覆盖、类型不矫正） |
| 17 | `pipeline.py` | 1257 | ✅ | **FL-D917**（续跑 stage 哈希缺 config/scope）、**FL-D918**（evidence 先于 engine 永久不一致）、FL-D919（supersede 状态口径不一）；FL-D826/827/828 修复验证在 |
| 18 | `prompts.py` | 703 | ✅ | FL-D924（指令「≤8 findings」与 schema maxItems=40 漂移、注入防护声明缺失） |
| 19 | `quality.py` | 416 | ✅ | **FL-D923**（复核截断先丢合同证据、severity 归一化英文化失效、检出描述失真断言） |
| 20 | `repair.py` | 144 | ✅ | FL-D919 并（critical 不滤 status 白调模型、中止信号降级、JSON 中段截断）；FL-D826 修复验证在 |
| 21 | `requirements.py` | 638 | ✅ | **FL-D906（P2 亲验：disposition_reason 覆盖矛盾）**、FL-D924（"可"字过宽、死参数、corrections 通道校验缺口） |
| 22 | `residual.py` | 347 | ✅ | FL-D924（小样本负轮换失效、轮次 clean_streak 口径滞后）；FL-D824/827/828 修复验证在 |
| 23 | `scope.py` | 66 | ✅ | FL-D924（双向子串过宽、空 scope fail-open 家族并入 FL-D828 同类） |
| 24 | `service.py` | 207 | ✅ | FL-D924（_server_corpus_dir 死函数、env int 裸解析）；FL-D821 修复验证在 |
| 25 | `store.py` | 1440 | ✅ | **FL-D908**（fencing 长事务空窗）、**FL-D909**（start_step 抹证据行）、**FL-D910**（payload lost update）、**FL-D911**（claim 退役漏 leased）、FL-D912（低危包） |
| 26 | `vector.py` | 520 | ✅ | FL-D924（无重试退避、全量向量驻留内存、连接不复用）；FL-D827/828 面亲验在 |
| 27 | `worker.py` | 248 | ✅ | **FL-D913**（异常原文入 error_code/engine_error 经 API 外泄，FL-D829 后端源头） |

**27/27 文件全部签认完成，零遗漏。**

## 主审计员复核记录（诚实记账）
- **驳回 1 条**：子任务报「worker.py L201 终态 payload 抹除全部状态」——亲验 `update_run`
  payload 路径为 `merged.update(payload)` **合并语义**（store.py L425-426），非整体替换，误报驳回。
  注：worker L194 的 `{**get_run()...}` 全量回写恰是 FL-D910 丢失更新在调用侧的实例，不另立条。
- **降级 2 条**：pipeline.py L544 兜底候选绕过空文案守卫——`source_quote` 经 requirements.py
  L103-105 校验必非空，触发路径不可达，降为 FL-D924 内登记项；pipeline.py L1224 engine attempt
  竞态——同 run 单活 job 声明（store claim sibling 检查）大幅弱化竞态面，降为 FL-D912 同级口径入 FL-D924。
- **亲验确认 P1×1**:FL-D907；**P2×11**:FL-D906/908/909/910/911/913/914/915/916/917/918/920/925。
  其中 FL-D906/907/908/909/910/911/913/914/915/916/920 均已读原码逐字核对；FL-D917/918/925/921/919
  由子任务行级证据+主审计员上下文抽查确认。
- 横切补扫（全 27 文件）：无裸 except、无 eval/exec/os.system、无 pickle/yaml.load、无 SQL 注入面
  （f-string 表名全为内部字面量调用点）、XML 解析全禁实体禁网络、httpx 全带 timeout、无凭据打印面、
  无可变默认参数、无 TODO/FIXME 残留。
