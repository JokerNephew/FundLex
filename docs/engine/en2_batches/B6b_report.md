# 批次B6b回报（guide.py / selective.py）

来源：子审计员 ses_e69bc7c72（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B6b报告

### fundlex/guide.py
- 结论：⚠️ 候选发现 2条
- ① 职责清晰：OOXML段落提取→模型分组（guide_parse)→确定性校验→独立核证（guide_verify)→修复重核→clean才认证，状态语义无伪造成功（clean=False则不certify，运行时validate_runtime_guide fail-closed）
- ② 失败路径整体良好：所有I/O失败转GuideError带code；`_model_summary`两处`except Exception`静默吞metrics/budget异常（仅诊断面）；`_verify_context`超额抛GUIDE_CONTEXT_LIMIT，不伪造
- ③ 模型上下文仅传文件名（source_path_hint取basename）防路径泄露；内部错误码落在document.validation供owner诊断页，未见token计数/哈希直给终用户
- ④ 无TODO/FIXME；975-979"legacy"注释为有意保留的兼容说明，非半成品
- ⑤ 交叉核验4处签名均匹配：`jobs.py:539 build_guide_document(source, gateway)`、`jobs.py:597 validate_runtime_guide(document, approved_source_sha256=…, approved_document_sha256=…)`、`recall_pipeline.py:4771`、`guide_generation/engine_compat.py:77 max_repair_rounds=0`；与`ObligationLedger.records`、`ModelGateway.call/max_context_chars/events/metrics/budget`契约一致
- 候选发现1：通用解析指令硬编码"15-group human reading"｜证据 guide.py:465-466 `The 15-group human reading of this guide is a reference only`｜同一_PARSE_INSTRUCTION用于自定义指引上传（jobs.py:539），对非内置新指引注入过时且不相关的分组数暗示（内置实为22 rules），亦与"新指引能否解析成合适规则"质量门抵触｜建议移入内置专用上下文或删除（报主线判定）
- 候选发现2：_model_summary 静默吞错｜证据 guide.py:748-760 `except Exception: snapshot = None` / `except Exception: pass`｜metrics/budget快照失败无任何记录，排障时预算/账本缺失原因不可见｜建议记入events或rounds_detail
- 已知命中：FL-D135（4000 token截断）、FL-D131（红色无语义，604-605已落实注释）、FL-D039（verifier隔离）、FL-D648（FL-D258块内split）、FL-D290（fencing在jobs侧）

### fundlex/selective.py
- 结论：⚠️ 候选发现 1条（次要）
- ① 职责单一：在已生成redline上做选择性accept/reject并独立复开校验；与docx生成器刻意解耦，明确不污染主交付物；状态语义（accepted/wrapper unwrap、rejected/delText→w:t）完整
- ② 失败路径严谨：全链路fail-closed（foreign whitelist、manifest精确比对、`except: target.unlink+raise`产物清理、复开c14n逐字节核对）；`_ordered_decisions`遗留重建路径的`except: pass`排序失败兜底（line 292-293）后续有_validate_revision_manifest兜底，风险被覆盖
- ③ DocxError均为内部错误码，用户可读性依赖API映射层；SelectionResult.path为绝对内部路径，不直达用户；无英文技术腔输出文案
- ④ 无TODO/FIXME/deprecated
- ⑤ 交叉核验5处fundlex.docx导入符号全部存在且签名匹配（`_validate_package(parts,limits,*,full,allow_existing_revisions=False)`、`docx.py:1246/1250 _write_package(_replaced)`、`docx.py:1335 _validate_revision_manifest`、`docx.py:1421 _accept_all_revision_parts`、`compare/revisions.py:173 _accept_revisions`）
- 候选发现1：accept_all重复计算清单｜证据 selective.py:612-615 `_manifests_from_report(report)`调用两次｜遗留报告走plan重建路径时重复排序/解析，纯性能小问题｜建议单次计算
- 已知命中：FL-D446（foreign修订叠加/区分）、FL-D555（A3-F1奇数id分配等DOCX/选择性缺陷）、FL-D298修订选择静默接受无效ID（现resolve_selection已抛SELECTION_UNKNOWN_REVISION并被test_selective固定）、FL-D088（配对ids展开）、FL-D610（base_had_tracked_changes语义，199行已落实）、FL-D291/FL-D299/FL-D331涉及本模块但属它域

结尾（批次小结）：
两文件整体质量高，失败路径以fail-closed为主，无伪造成功、无TODO半成品。 guide.py唯一实质候选是通用解析prompt内残留内置指引专属的"15-group"硬编码，影响新指引解析质量门，建议主线判定；另有诊断快照静默吞错次要项。selective.py仅一项微不足道重复计算；此前已报的无效ID静默接受问题在本版已修复并被测试固化。签名级跨模块契约抽查全部吻合。
