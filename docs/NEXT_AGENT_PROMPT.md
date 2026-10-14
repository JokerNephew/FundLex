你是 FundLex 的接续开发 agent。工作目录 D:\Desktop\FundLex，Windows 11 + pwsh，分支 codex/fundlex-implementation，HEAD 0786f99。

用户已批准按多对多匹配与实际 DOCX 复核方案自主开发，并要求自己管理进度；生产服务器4C8G，并发参数由agent决定。上一agent因额度停止，要求你继续现有工作，不要重建项目或只停留在了解阶段。

开工先读 docs/HANDOFF_MATCHING_V3_20261014.md（最新完整断点）、IMPLEMENTATION_PLAN.md顶部、docs/SEMANTIC_MATCHING_V3_SPEC.md、docs/MATCHING_UPGRADE_EVALUATION_PROTOCOL.md。核对git dirty workspace，全部本轮WIP尚未commit；新文件也是开发成果，不要清理掉。旧子agents已中断，无需等待它们。

当前范围定位、变体定位、多目标盘点、临时产物实际语义复核、两轮回滚和0.3.0存储下载门禁已大部分实现，但C安全回归未最终冻结。当前rules/rules_v2.json是未发布评测草案False/22，旧published备份在var/matching-upgrade-20261014/baseline。新版本尚未全套验证、真实评测或重新发布，不得把基线357通过或实测零误改当新版本成果。

优先收尾：R15删除引文必须是完整业务句，防截半句/吞支付公式；R10已符合须独立语义核验；同章剩余子节盘点；相邻编辑冲突；后验完整证据与最终产物绑定。核实最新代码已修哪些，不重复做。最后确定性审计21/22正例、23/23反例，R13失败尚需重跑排查，不能修改期望或给默认成功模型答复。统一Python和rules JSON为LF，再build草案/隔离包，完整测试含MySQL及动作审计通过后冻结引擎。

共享预算账本不重置：仓库外LocalCache/Local/FundLex/action-pilot-20261013/pilot_budget.sqlite，实际1798 HTTP/USD1.2809772。本轮真实模型调用0；新累计上限已预登记7500 HTTP/USD6，输入0.3/M、输出1.2/M、并发1批大小1。任何额度用完即停，新加上限必须先登记。密钥/数据库密码只在环境，不回显、不写文件。

真实传输计划：deepseek-flash，thinking disabled，MAX_CALLS192、CONTEXT_CHARS20000、OUTPUT_TOKENS3000、TIMEOUT60、RETRIES1。4C8G初始2API/1worker/模型并发1；未做目标机容量验收。

先P05/P13两份诊断（私有matching-upgrade-20261014/spot-input已准备），随后最终5夹具+16回归+8历史泛化回归，跑旧gold和新冻结参考标签评分，保留所有失败记录。var/.../labels标签SHA73c42e92720f90fe1d9533d03e33d8471c5debf72d3e387a19f6bc0dca79888f，禁止改标签。新参考是独立AI、非业务专家真值；不能按结果改验收阈值。定位失败拒绝不改，误改必须0；漏改/不确定如实报告。

任何fundlex/*.py变更都要重跑审计和真实证据，再按新增--evidence-run（5+16+8当前run）重新发布规则包，随后全套测试+真实task_revision_run至少2份正式交付/授权下载SHA/例外复验。不能用只跑audit重新绑定指纹代替真实验收。

保护references/、funds_word/、原PRD/设计、workbench/、frontend/assets未提交图片；var不入库，不删除测试，不push。用户已授权开发与发布流程，不重复问开工许可。按功能分块commit前审阅staged diff。继续到功能、证据、发布和文档全部收尾；及时把进度写回IMPLEMENTATION_PLAN.md。
