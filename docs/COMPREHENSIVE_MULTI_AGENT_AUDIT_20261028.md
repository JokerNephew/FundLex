# FundLex 多agent全方位检查报告

日期：2026-10-28。检查已完成，**整改未执行，整体结论 NO-GO**。本报告不等于代码修复、生产发布或28份正式质量验收。

## 1. 核心结论

1. **已在真实生产用户路径确认错误完整声明**：价值优选任务显示complete、查漏PASS，下载合同摘要p1258却仍保留旧销售服务费支付机制。正文已改、摘要未改，不能作为完整最终合同交付。此结论来自实际DOCX独立复核，不是模型自评或合成探针。
2. 发现多项P1：候选配置可外发服务器环境凭据、认证备份权限过宽、发布门禁与资格脱节、旧Worker覆盖新结果、语义批准可搬用、叠加修订Review断链、Compare错误作用域保存等。**未确认P0、未证明真实凭据泄露或外部攻击已发生**。
3. 自动测试大量通过不能替代业务完整性：Python **1945 passed / 13 skipped**、浏览器 **45 passed**、前端单测 **14 passed**；新增负例仍揭示当前测试盲区，P6评分器本身也有误放。
4. 用户明确从未限制付费模型调用。已清理21份现行政策/执行/接续/部署文档与示例说明；**账本只作观测，无费用/调用次数审批**。运行时代码仍有旧硬cap，已登记FL-D449，不能将修文档冒称代码已解除。

所有问题及处理建议已归并至 [集中问题记录](DETAIL_ISSUES_AND_RESOLUTIONS.md)：新增FL-D449–478（含政策修订、缺陷及待核运维观察），并补充已有FL-D188/305、277、284、288、303、312、338、374、384（第一批摘要副本）、434、437、441（引擎容量）、443、446、447等适用条目。历史编号重复时按“编号＋标题”定位。

## 2. 分工与版本边界

共8名子agent：政策文档、语义引擎/证明闭环、API/身份/数据库/队列、DOCX/Compare、前端、部署安全、法规生成/飞书、独立真实产物业务复核。主agent负责全量回归、正式生产浏览器任务、文件机械复核、反例复跑、去重入册与报告。

- 起点：`codex/outer-remediation-20261028` / `5cf7a4500b49bcb17cda6189348046d78537da0d`，含3个既有引擎dirty文件，全部纳入检查、未覆盖。
- 检查期间其他会话将原dirty提交为`c46f923`，随后HEAD到`28cac2f3e0259f23c9755b34045d64f7d1617c7f`；**本轮主agent及审查agent未提交、推送或部署**。源码SHA而非单一HEAD界定审查内容。
- 起点448份源码/配置文件SHA保存于证据目录`baseline.json`；政策说明变化不作为引擎版本改变。生产与工作区不相同，具体生产适用性分项说明。
- 本轮业务代码、生产配置、服务、既有合同、gold、manifest均未改；只修改用户要求的政策文档、集中记录及本报告。正式验证仅创建本轮自己的临时账号与任务，未改既有用户数据。
- 主机/网卡/实例metadata确认为本机生产云服务器；五个FundLex服务active，API回环监听。健康检查成功并不证明业务验收通过。

## 3. 真实生产合同：链路成立，业务未通过

| 项目 | 实际结果 |
|---|---|
| 入口 | `https://fundlex.club`，浏览器注册登录→当前指引→普通页面上传→Worker/model→结果详情→授权下载 |
| 输入 | `funds_word/基金合同第一批/广发价值优选混合型证券投资基金基金合同.docx` |
| 任务/文档 | `3860e8c301ab4343bb228d609cc968b2` / `ca8ef3e099344290b70aadd36abd7c57` |
| 引擎build | `1621a30b4f023efdaf86e58f808cf390f54430392587be7dc54043c385d8e57c` |
| 真实调用 | 27逻辑、28HTTP、149372tokens，约200.8秒、约USD0.03656805；一次429后恢复。费用仅观测。 |
| 实际产物 | 15个变化段、15处ins＋15处del，作者资金清算部；final无修订；final/redline及JSON/Markdown报告均下载成功，未登录下载401 |
| 机械复核 | 10项全通过：源/产物hash、文件对、接受全部=final、拒绝全部=source、段落位置、计划与实际文字一致 |
| 独立业务复核 | **未通过**：摘要p1258（全XML p1282）原样旧支付条款；正文p802已有新渠道/期限/返还机制，摘要缺直销返还、365天及超一年机制 |
| 错误声明 | 原报告`delivery_status=complete`、查漏PASS、open0；G15/G16默认排除摘要，既定站点闭合不等于业务目标覆盖 |

源SHA：`708bca5d2197d0688c59ebb7a0eaee1432b79162e2404a8545cd60d488fd67c7`；final：`d8f1dc99a7a138dc5b890e78bf5d17fe25c8f84797c6cacaab1e34e3a89709dc`；redline：`602b4487751da5d3099d34123c7e5ad9913feeeb90f0613832d3ad8a64825cea`。

独立agent先读原件/指引并保存盘点，再读实际产物，最后查看report归因；主agent再次读source/final确认旧句相同。**这是事后本份独立复核，不是运行前冻结gold，不将15个变化段折算为正式准确率**。旧报告和文件保留，不篡改complete字段掩盖事故。另p124/p128重复追加正确政策为P3质量观察，不构成范围外去重授权。

## 4. 风险与整改清单

下表全部仍未修复；只有FL-D449的文档部分已完成。P1/P2表示当前风险优先级，不宣称每项已发生生产事故。

| 优先级 | 编号 | 检查结论与验证范围 |
|---|---|---|
| P1 | FL-D384（摘要）、434/443 | **生产实证漏改＋错误complete**；另第一批景宁摘要候选被当前scope拒绝。范围外不改不能解释合法对应目标漏选。 |
| P1 | FL-D452 | 普通成员任意vector配置可指定环境凭据名及外发URL；虚构哨兵＋网络拦截实证。**当前生产无vector模块/消费链，仅候选风险，发布前须修**。 |
| P1 | FL-D463 | 含users/sessions等认证表的SQL备份0644、父目录0755，本机非sudo可读；未读取输出认证行值、未证明第三方窃取。 |
| P1 | FL-D464 | 两环境certifi2026.7.22命中emSign CA公告；OSV两来源确认，保守修复边界至少2026.10.19。未验证MITM。 |
| P1 | FL-D374/338 | 质量/覆盖/Residual未通过仍创建candidate_ready且HTTP可批准发布；覆盖新增critical与finalize缓存漏质量依赖。**候选发布不等于runtime已启用**。 |
| P1 | FL-D453 | 法规生成只在job结束检查token，run/阶段/产物已先被旧worker写入；隔离双worker交错实证。 |
| P1 | FL-D454 | 飞书请求文件自身hash通过即可发送，绕过网页的成对产物/报告门禁；损坏redline后final仍被fake sender发送。 |
| P1 | FL-D457 | 旧批准可搬到另一物理同文站点，实际planner生成删除；未证明HTTP能注入target。 |
| P1 | FL-D458 | 语义审计只把外层义务改PASS，site仍FAIL，合法同义已满足仍verified=false。 |
| P1 | FL-D459 | 批准删除混用段落绝对offset与已切片坐标，有前缀保留句即误退回compose。 |
| P1 | FL-D441（引擎） | 先截12候选再过滤scope；第13个合法候选虽在下一页，默认恢复不消费，持续饥饿。 |
| P1 | FL-D446 | 叠加成功的redline公开Review生成仍拒foreign ID；同段既有ins/del导致普通目标坐标错拒。合成及弘利临时副本实证。 |
| P1 | FL-D460 | Compare同段多处修改首处变长时，expected文本正序旧offset造成错误oracle，正常选择生成被拒。 |
| P1 | FL-D451/303/382/448 | 生产首页workspace接口404；三个发布器漂移、漏Guide Worker，源码/前端/依赖与生产分叉，禁止整树覆盖。 |
| P1 | FL-D466 | 飞书A解绑重绑B后，B能确认A旧草稿，任务/文件/channel owner不一致；隔离正常绑定流程复现。 |
| P1 | FL-D471 | Compare生成中换组，迟到响应污染selection，随后保存请求发往旧组；真实controller隔离浏览器实证。 |
| P1 | FL-D472 | 法规切任务迟到响应产生A标题＋B指引/下载；隔离浏览器实证，未证跨账号越权。 |
| P1 | FL-D312（V2） | React二次生成缺selection_epoch/manifest_hash，当前后端契约409；V1已有该修复，不重复误报。 |
| P1 | FL-D450 | P6实际DOCX反例：新义务缺失、首分句外缺项、删除句移远仍在、类别未知原样，评分器均completed；旧分数受影响范围未重算。 |
| P2 | FL-D437 | worker交付与摘要两套分类不一致，未知码/部分G14工程错可降级；只实证门禁级反例，另有生产摘要漏改事故，不混为同一复现。 |
| P2 | FL-D455/338 | 法规下载只查文件存在、不验登记hash；AI已发布对象仍可被条件性晚到finalize覆写。 |
| P2 | FL-D456 | incomplete evaluation丢模式，落库delivery并发布working文件；未证明变成正式complete文件。 |
| P2 | FL-D446 | 属性/其他story/段落标记修订入口放行后晚失败；不称已静默发布坏文件。 |
| P2 | FL-D447 | 末段删除两套接受器语义不同；纯拆/合/空段变化0diff且无覆盖提示，既有文字跨段能力不能证明纯结构已支持。 |
| P2 | FL-D461/462 | 合法非标准header URI漏警告；格式未比较不披露，同numId不同定义可静默绑定左编号。文本优先设计本身不是缺陷。 |
| P2 | FL-D288/284 | ASGI门禁及四服务沙箱已存在；残余为multipart入口遗漏、Nginx模板未生效、飞书沙箱/UMask较弱。 |
| P2 | FL-D465 | DB＋对象一致性恢复演练及定期保留证据不足；有hbrclient，未查云控制台，不能断言没有云备份。 |
| P2 | FL-D467/469 | 飞书失败同event永久去重；法规模型暂停retry_wait无法被正常领取且无owner恢复入口。 |
| P2 | FL-D468/470 | 引擎兼容性202不执行/配置True调用不存在方法；飞书全部交付只取前100份。 |
| P2 | FL-D473–477 | React旧401清新会话；法规页初始化中断、证据错误docx后缀、未决状态绿色、任务列表无键盘入口。 |
| 要求不符 | FL-D449 | 文档预算审批/停止规定已清理；model_budget/model/guide router/preflight等运行时硬cap仍待改，0不代表无限。 |

## 5. 验证结果、反证和局限

- 全量非浏览器Python：**1945 passed / 13 skipped / 3 warnings / 736.94秒**。13项skip包含未配置独立MySQL测试；没有把测试指向生产库。尝试无口令root MySQL被1045拒绝，未尝试猜密码或执行生产破坏性fixture。
- 浏览器既有套件：**45 passed / 169.67秒**；前端Vitest **14 passed / 5 files**；typecheck/lint/JS语法通过；新构建只写独立临时dist。既有浏览器读仓库dist，新增V2探针读新build，二者分别报告。
- API定向：74 passed/1 skipped；DOCX定向17 passed；集成10项新增缺陷反例连原专项42 passed；这些与全量重叠，**不相加虚增测试数**。“缺陷反例通过”表示复现成立，不是修复。
- 主agent复跑API、语义引擎探针及四项实际DOCX评分反例；重读生产下载文件机械检查、摘要业务反例。certifi公告另由主agent独立联网核对。
- npm锁文件官方advisory查询当日零命中，不等于所有依赖零风险；setuptools公告按Windows/不可信构建输入范围定性，不报Linux Web RCE。
- 当前普通身份隔离、强RunStore fencing、guide解析token、选择epoch、报告容错已有保护，未把历史已修漏洞照抄成现存问题。未确证额外XSS或P0。
- 未重跑完整20–30份冻结标签评测/新留出；旧P6标签仍有D06零目标等已知问题（FL-D188/305），不得把旧gold或本次小样本当现行完整质量证明。
- 未做Word/WPS保存往返、真实读屏/手机人工测试、MySQL并发压测、云备份控制台核验、全部飞书/法规真实模型生产E2E。未因费用限制排除这些；本轮范围是检查，不自动修改/部署全部业务。
- 代理慢传/大包/远程攻击未在生产执行；凭据外发反例只用虚构哨兵且拦截网络。站点面板8888主机监听/防火墙允许已见，云安全组及面板来源白名单未查，不能说已公网可达或可远程利用（FL-D478）；不动无关系统配置。

## 6. 建议整改顺序（待实施）

1. **安全与发布资格**：修候选transport/config信任边界、认证备份权限、TLS依赖、候选批准/发布资格与不可变对象。当前生产未部署的vector链不要先发布再补安全。
2. **唯一发布候选**：合入生产专有workspace/V1/Compare能力，核对五服务、schema、依赖锁和发布器；恢复首页接口，不从当前分叉树整树发布。
3. **业务完整性**：一般化正文/摘要对应scope及独立覆盖，绑定批准物理span/版本、统一语义站点证明与交付分类，修分页消费者和坐标系；优先复验本次真实错误complete。
4. **文档与多渠道一致性**：叠加Review/Compare oracle与接受器、统一下载hash/文件对门禁、evaluation权威模式、全链fencing。
5. **交互与恢复**：修跨任务回包、epoch、飞书重绑/事件/分页、模型恢复、兼容性任务、文件名/状态/键盘入口；解除旧运行时费用cap但保留资源和无进展保护。
6. **真实验收**：先修评分器与独立标签局限，冻结候选后按20–30份计划做实际修改/文件评分与完整回归，再复验正式工作台/飞书下载；故障与不完整用例如实交付工作稿，不靠降级或改gold过关。

## 7. 证据索引

详细原始证据根目录：`/tmp/opencode/comprehensive-audit-20261028/`。

- 子报告：`policy.md`、`engine.md`、`api.md`、`docx.md`、`frontend.md`、`ops.md`、`integrations.md`、`business-review.md`。
- 真实交付：`production-v2/{result,report,artifact-review,business-counterexample}.json`、下载final/redline/report及截图；`business-inventory.json`。
- 反例：`engine/probe.py`/`probe.json`、`api/repro.py`/`evidence.json`、`docx/*probe.py`/`*results.json`、`frontend-probes.py`/`.json`、`test_integrations_audit.py`/`integrations-junit.xml`、`scorer_probe.py`/`scorer-probe.json`及合成DOCX。
- 测试：`pytest.log`、`frontend-browser-tests.log`等；源码基线`baseline.json`及`frontend-source-hashes.json`。
- 核心证据摘要另保存在[`docs/evidence/comprehensive-audit-20261028.json`](evidence/comprehensive-audit-20261028.json)。集中问题文档保留具体影响、复现、修法与未修状态，不只留外链。

原始/tmp证据在本机保留，不授权清理；后续正式归档应排除凭据并验证hash。本轮已知后台agent/检查任务均完成，无本轮部署或服务重启。
