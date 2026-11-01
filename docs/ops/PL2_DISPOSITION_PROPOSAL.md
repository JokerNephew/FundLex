# PL2 平台审计线 — 发现分级处置提案（2026-11-01）

> 状态：**提案，待主线裁定**。来源：PL2 全覆盖审计 [PL2_AUDIT](docs/ops/PL2_AUDIT.md)（300 件逐件签认）与发现登记册 [DETAIL_APPEND_PL2](../DETAIL_APPEND_PL2.md)（FL-D940~D959）。本文件自含，可独立评审与实施。发布守门一节（§2）与已并入主线的 GG 提案 `docs/guide-generation/RELEASE_GATE_PROPOSAL.md`（d2f570c）同构：每层含断言、失败动作、留痕格式，费用只设结果正确性门禁不设次数门禁（FL-D445）。

## 1. 分级口径

| 级 | 定义 | 处置时限 |
| --- | --- | --- |
| **P0 阻断级** | 现行就可能在误用/净克隆/合并中造成生产破坏或绿色假覆盖；不处置即构成发布守门漏洞 | 下一发布前 |
| **P1 近期** | 系统性口径错误/方向性风险，触达面已在收窄或需组合条件 | 本波合并线收口时 |
| **P2 卫生批** | 局部、低烈度、已有免责/缓解；批量清理一次性完成 | 随机会批（同 PR 打包） |

**分级结果**：P0 ×4（D940/D948/D954/D953）／P1 ×7（D941/D944/D946/D950/D951/D952/D955）／P2 ×9（D942/D943/D945/D947/D949/D956/D957/D958/D959）。

## 2. 发布守门相关高危项（单独详述）

> PL2 域与「发布守门」直接相关的项：旧部署器、对象 GC、发布器方向性漂移、发布后冒烟校验、清理口径。GG 提案提出发布后四层守门（配置一致性断言/PILOT run 冒烟/切片冒烟/负向冒烟）；以下 5 项是守门**地基缺陷**——地基不补，守门断言会在坏地基上运行。建议按本节处置后再谈守门层叠加。

### 2.1 FL-D940（P0）：旧部署器 publish path 地雷，发布守门第一前提是消灭它

- **事实**：tools/deploy/deploy_recall.py 仍具完整破坏力：tar 覆写 /opt（:214-215，无事务/无回滚）、写**与现行单元同名**的无沙箱 unit（:95-129 内联定义 vs 现行模板 7 项沙箱全无）、ENV_OVERRIDES 注旧成本闸门（:84-93）、中途失败留半成品（:80）、sed 改 nginx 不带 FL-D288 上传守卫（:271）。docs/tests 全仓零引用 = 死而危险。
- **处置（二选一，公务员推荐 b）**：
  a. **删除文件** + 一次 commit message 留痕「superseded by fundlex-publish (62a3eff)」；
  b. 文件头 15 行内硬阻断：`sys.exit("deploy_recall.py is superseded by tools/deploy/publish_workspace.sh (fundlex-publish); refusing to run. See FL-D940.")`——保留历史可查但物理不可运行。
- **守门断言（叠加到现有守门层 2.1，秒级）**：发布记录附 `test -f tools/deploy/deploy_recall.py` 的布尔 +（若存在）grep 出阻断行——旧部署器在候选树中要么不存在、要么含阻断语句，否则**阻断发布**。
- **验证**：阻断后 `.venv/bin/python -m tools.deploy.deploy_recall --skip-pack` 即 rc≠0 且不回显凭据。

### 2.2 FL-D948（P0）：对象 GC 引据不全，保住所有发布/交付证据的可恢复性

- **事实**：tools/maintenance/prune_orphan_objects.py:19-37 referenced_keys 漏 4 处 object_key 表（compare_pair_files:72 / compare_artifacts:78 / compare_selection_artifacts:94 / gg_artifacts:207）。发布留存与交付证据共住 RunStore.objects；`--apply` 可在 24h 老化后误删存活交付物（DB 行在、文件 404）。
- **处置**：
  1. referenced_keys 补齐 4 查询（空值过滤 + `UNION` 单表扫描）；
  2. tests/test_object_gc.py 增 4 用例：compare/gg 引用的对象在 `--apply` 下**必须存活**；
  3. dry-run 报告加「referenced_keys 命中表计数」字段，便于人工复核覆盖面。
- **守门断言（运维门禁，非每发布必跑）**：`--apply` 运行前一律先 dry-run 落盘报告并比对「orphan 数 vs 上周期基线」——突增必查；脚本增加 `--require-dry-run` 强制选项（apply 模式必须先有本次 dry-run 报告哈希）。
- **验证**：修补后在隔离副本库构造 compare/gg 引用对象，--apply 后 `sha256sum` 比对存活。

### 2.3 FL-D950（P1）：发布器方向性漂移——守门必须防「旧树反向烤掉根侧加固」

- **事实**：根侧 /usr/local/sbin/fundlex-publish 领先本审计树 4 项加固（fc5f7f2 FL-D801 留存清理、FL-D800 sys.path 钉版、be5484d FeishuAppOnboarding、check_api 24×5s 重试）；本树 158475f 早于这些分支。publish_workspace.sh:5-10 的同步纪律只说了「保持同步」未说「方向」。
- **处置**：
  1. 合并线把 fc5f7f2/be5484d 落主线后重跑 `check_publish_drift.sh`（必修路径）；
  2. publish_workspace.sh 头注释补方向条款：**只允许「仓库被评审版本 → 根侧」方向安装，禁止旧树副本覆盖根侧**；check_publish_drift.sh 发现「根侧含仓库没有的修复标记」时输出方向警示（不阻断，但要求 --ack 参数）。
- **守门断言（守门层 2.1 同列）**：每个发布记录附 drift 检查结果与根侧↔仓库 sha256 两个值（值是脚本哈希非凭据，可留痕）。

### 2.4 FL-D946（P1）：发布后冒烟校验（cloud_verify）自身失修，守门要用就得修

- **事实**：tools/deploy/cloud_verify.py 是现行发布后冒烟入口；① 临时账号前缀 `deploy-verify-` 在清理白名单外（生产当前 0 残留已实证）；② cleanup 失败仍 return 0（告警静默）；③ 隧道断言查「指引配置」/app.js 含 `recall_first`，React SPA 化后恒 False——**守门断言会误报**；④ seal 触发真实模型调用与清理竞态。
- **处置**：前缀归 `cloud-run-`；cleanup 失败即非零退出；隧道断言改验 `/api/capabilities` JSON 字段（engine.id/auth_mode）；seal 前 pause 或等终态再清；删 :112-114 死代码；/tmp 固定文件名加 pid。
- **守门接管**：修好后把 cloud_verify 的服务器端段纳入 GG 守门层 2.2 后的「端到端补充」（PILOT run 主守门，cloud_verify 收尾验下载链路）。

### 2.5 FL-D941/D942（P1/P2）：清理域口径——发布留存边界的数据面

- **事实**：cleanup_test_accounts.sh 只删 8 表，漏 compare_*/gg_*/integrations/guide_jobs（生产实测当前 0 残留，潜在逻辑缺口）；前缀注释漂移；`p6-%` LIKE 有真实用户误伤面；ops 账号表级 DELETE 靠客户端自律。
- **处置**：补 owner/user_id 级联删除清单（对照 information_schema 自动生成差集断言防再漏）；前缀收窄（`p6-tmp-`）+ 删除前列表 + admin 保留；注释与代码统一；中期评估把 DELETE 收进存储过程。
- **守门断言（运维侧）**：cleanup 后自动跑「白名单用户关联行=0」校验 SQL，非零即报告。

## 3. 非守门域分级处置一览

### 3.1 P0（除 §2.1/2.2 外的两项测试域高危）

| 编号 | 处置 | 验证 |
| --- | --- | --- |
| FL-D954 27 用例 gitignored var/ 静默全 skip | fixture 入仓（合同公开资料政策已授权入库，funds_word 先例）或生成式 fixture；将 skipif 改显式 fail-fast 门（`pytest.fail("fixture missing", pytrace=False)` 或 module-level `pytestmark` 说明） | 干净克隆跑 pytest 该两文件 collect>0 且 skip=0 |
| FL-D953 fakes 接口漂移 | fake 对未覆盖任务类型抛异常；identity() 补 6 字段并与 model_router.ROLES 加等价断言 | 新增负用例：fake 收到 guide_repair 任务必须 raise |

### 3.2 P1（测试域家族性修复）

| 编号 | 处置要点 |
| --- | --- |
| FL-D952 危险写操作族 | MySQL fixture 强校验库名测试前缀；browser 两测试默认输出改 tmp_path/COMPARE_PERF_OUT 必需 |
| FL-D955 路径未锚定族 | 全部换 `Path(__file__).resolve()` 锚定；test_deploy_publisher 头部显式 skipif(ROOT/.venv 缺失)（基线唯一失败即此环境隐依赖） |
| FL-D951 10.5s×3 固定等待 | 复用同文件 :418-421 route 设施改事件等待 |
| FL-D944/946/941 | 见 §2.4/2.5（涉及发布域，并 P1 处理） |

### 3.3 P2 卫生批（单 PR 打包）

- 死脚本移置：diff_status.py（D943）、research/ 全部（D949 _wtmpl 先加确认）移入 tools/research/ 统一一次性口径；
- 文档/行为对齐：migrate_workspace_diff.py 改 docstring 或加 --write（D945）；migrate_data EXPECTED 改下界断言（D947）；build_builtin_guide 仅显式传参时覆 env（D947 附属）；setup_fundlex_ops 注释统一（D942）；
- 测试卫生：sys.path.insert×7 改用 conftest，未使用导入×2 删除，跨测试 import 19 文件逐步抽 helper 到 conftest（D959）；recovery 四模块与 feishu.service_main 补直接单测；
- 语料同步项：D957 九处段号/字节偏移纳入扩波任务清单（扩波时批量 regenerate），D956 时序族随卫生批改注入时钟/事件。

## 4. 实施排序与依赖

1. **第一序**：D940 阻断（§2.1，分钟级）+ D948 修引据+补测试（§2.2，半天级）——两者都是「留着就有误伤窗口」；
2. **并行**：D954/D953（§3.1，测试域，互不阻塞）；
3. **随合并线**：D950 方向条款 + drift 方向警示（§2.3）→ D946 修 cloud_verify 后纳入守门（§2.4）→ D941/942 清理域（§2.5）；
4. **随卫生批**：全部 P2（§3.3）；
5. **收尾**：所有 P0/P1 落地后，在发布脚本侧实装 §2 守门断言（3 项布尔/哈希断言，零模型成本），与 GG 守门四层合并为单一守门清单。

不留存量：每项处置 commit 引用本提案编号；处置完成即在 DETAIL_APPEND_PL2.md 原条目追加「状态：已修复 @commit」而不是删条目（集中记录规定）。

## 5. 留痕格式（沿用 GG 同构）

每条守门断言记录：检查项、布尔/计数（不回显值）、证据哈希、判定 PASS/FAIL/SKIP、处置人、commit。例外项必须带 FL-D 编号与豁免理由。发布记录与留存事务并列存放 /var/lib/fundlex/ 外审计可见位置。
