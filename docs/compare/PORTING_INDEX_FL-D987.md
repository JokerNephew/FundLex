# FL-D987 比对链路全屏骨架回退——region 版真修复移植索引

> 用途：FE 回退施工（region 版 → 全屏大画布，FL-D987）的修复保全地图。覆盖 region 版上修的 **10 件真修复**（FL-D980/996/997/853~859），逐件给出：问题 / 修复 commit / 现行代码位置 / 移植要点与风险。
> 行号基线：`qa/full-audit-20261031 @ 7fad716`（漂移后以函数名检索）。
> 回退目标：**全屏 modal 骨架**（B 重设计 18ba761 之前的形态：`#compare-viewer` `role="dialog" aria-modal="true"` + `#compare-viewer-backdrop` + 「上一组/下一组/× 关闭」头行 + 组列表）。pre-B 对照基线 = `18ba761^`。
> 修复 commit：`b257e46`（FL-D853~860 批次）、`915002f`（FL-D980/996/997 dogfood 批次）。

---

## 全局移植铁律（先于逐件读）

| # | 铁律 | 依据 |
|---|------|------|
| G1 | **回退操作面只限 `frontend/` + 前端测试**；`fundlex/compare/api.py` 等后端不参与回退，853/854/855 自动保全。若骨架用「git checkout 旧版整域」手法，必须把 `fundlex/` 排除在回退路径之外 | 853~855 是纯后端修复 |
| G2 | **V2 骨架方案先定再动**：`shared.tsx / CompareNewPage.tsx / CompareTaskPage.tsx` 均为 B 时代新建（18ba761 三路由拆分，FL-D846）。858、859 的 V2 面、980 的 V2 面宿主在这三个文件里。保留三路由→零搬运；回单页 ComparePage.tsx→按逐件「V2 风险」节携带 | FL-D992/V2 线仍在施工 |
| G3 | 逐件守门测试回退完工必须全绿（见文末「守门矩阵」）；**FL-D854 是唯一「禁止反向优化」的契约**，不是代码搬运项 | fails-closed 门 |
| G4 | FL-D843~852 的 B 版结构件（region 化/chip/rail 选择条/单行修订项/三路由）**不在本索引 10 件内**——其中部分是被回退的结构本身；若骨架需要其中零结构副作用子件（FL-D850 preventScroll、FL-D852 notice），请从 18ba761 按需摘取，超本索引口径 | 范围纪律 |

---

## 后端三件（骨架零搬运，守卫型）

### 01 · FL-D853 上传 415 拒收错误码坍缩
- **问题**：`validate_upload` 415 靠匹配英文文案区分 legacy .doc，加密/格式等原因一律坍缩成 `COMPARE_INVALID_DOCX`，真实原因（解除密码）丢给用户的是错码。
- **修复 commit**：`b257e46`
- **位置**：`fundlex/compare/api.py:23` `_upload_rejection_code()`（失败路径重跑共享校验器取 `.code`）；`:204` 上传路由接线。前端消费：V1 `compare.js:121`、V2 `CompareNewPage.tsx:50`（回执 error_code → uploadErrorLabel）。
- **移植要点与风险**：纯后端，骨架零搬运。唯一风险=回退手法误带 `fundlex/`（见 G1）。守门：`tests/test_compare_api.py`（含 documentProtection 用例）、`test_fl_d286_api_safety.py`、`test_upload_validation.py`。

### 02 · FL-D854 view 端点 fails-closed 契约（评估后撤回优化）
- **问题**：view 每请求对两份输入全量 sha256；曾试图缓存命中免哈希。
- **修复 commit**：`b257e46`（撤回优化，保留 `_view_cache_get` 无行为重构）。
- **位置**：`fundlex/compare/api.py:102` `_view_cache_get`/`:115` 命中后仍全量校验（注释在案）。
- **移植要点与风险**：**不是搬运物，是行为契约**。回退/重写期间严禁给 view 命中降级为 size 门——`tests/test_compare_system_review.py::test_view_fails_closed_when_source_or_result_object_changes` 锁定同长度篡改必须 409。骨架抄旧代码若带回旧缓存形态即破约。风险：中（抄旧码是回退的标准手法，最容易顺手套现）。

### 03 · FL-D855 `register_compare_routes(max_pairs)` 死参数接线
- **问题**：路由注册参数 `max_pairs` 从未生效，仅 store 硬编码 1000 兜底。
- **修复 commit**：`b257e46`
- **位置**：`fundlex/compare/api.py:159` create 路由显式 `422 COMPARE_TOO_MANY_PAIRS`（store 硬编码作二道防线）。
- **移植要点与风险**：纯后端，同 01，零搬运。守门：compare API 套件。

---

## V1 前端六件（全屏骨架的搬运主战场）

### 04 · FL-D856 V1 上传拒收错误码无用户可读映射
- **问题**：V1 上传失败直露 `error_code`/裸状态；补救话术不实（MANIFEST 绑定 name+size，组内不可换文件）。
- **修复 commit**：`b257e46`
- **位置**：`frontend/compare.js:21-30` `uploadErrorLabel`（8 码表：LEGACY/ENCRYPTED/UNSUPPORTED/INVALID/UPLOAD_REJECTED/MANIFEST_ENTRY_NOT_FOUND/MANIFEST_FILE_MISMATCH/UPLOAD_IDENTITY_CONFLICT，补救统一「请新建对比任务上传」）；消费点 `:121`（新建页密封前逐组回执组装）。
- **移植要点与风险**：**pre-B 基线无此函数**——若骨架从 pre-B 重建 compare.js 必须整体携带表+消费点。它是 853 成果的用户出口、05（FL-D857 `pairErrorLabel`）的内部依赖（`:102` 引用）：漏携带则 853 在前端坍缩回裸码。风险：高（纯新增逻辑，非旧码演进，最容易在回退中蒸发）。

### 05 · FL-D857 密封不完整组（COMPARE_PAIR_INCOMPLETE）错误兜底误导
- **问题**：组失败落通用「处理失败，请稍后重试」，真实原因在随负载下发的文件级 `error_code`，重试无用。
- **修复 commit**：`b257e46`
- **位置**：`frontend/compare.js:91-108` `pairErrorLabel()`（优先消费文件级码按侧列「合同A/B：原因」；diagnostics 分支诚实文案）。消费点 `:110`（chip 行 `.compare-pair-error`）、`:1152`（viewer 空态 `setViewerEmpty`）。
- **移植要点与风险**：函数纯「数据→字符串」，零 DOM 依赖，直接搬运。**消费点才是结构敏感位**——region 版的落点是 chip 行+region 空态；全屏骨架对应位是 pre-B 组列表行与 dialog 内失败渲染，骨架须保留「组失败=用户在该组落点看到组级原因」的显示位置并接 `pairErrorLabel(p)`。残留依赖：06（996 话术）与 04（uploadErrorLabel）同函数集成。风险：中高（消费位重建时易接旧兜底串）。守门：`tests/browser/test_v1_frontend_remediation.py`（L1039 diagnostics 断言、失败组用例）。

### 06 · FL-D996 失败组话术补救路径重复（改号自 983/981）
- **问题**：pairErrorLabel 尾句「请新建对比任务重新上传」与 8 码表内补救语一句话两遍。
- **修复 commit**：`915002f`（V1 compare.js）+ V2 同修。
- **位置**：`frontend/compare.js:99-107`（尾句「该组已判失败，须新建任务补救。」）；V2 `shared.tsx:82-94` `pairFailureLabel` 同语义尾句。
- **移植要点与风险**：无独立搬运单元——05（857）整体携带即自动带上；V2 面随 07（858）落位。风险：低，但若骨架从 **857 修复之前**的更早基线重拼 pairErrorLabel，丢的正是这段尾句——届时文案复读立刻复发。守门：remediation 失败组用例目检文案。

### 07 · FL-D858 V2 错误码直露（跨线协助；属 V2 域文件）
- **问题**：V2 chip/空态直露原始 error_code；类型层缺 `upload_status/error_code/diagnostics`。
- **修复 commit**：`b257e46`
- **位置**：`frontend/src/types/api.ts`（ComparePair 扩展）；`shared.tsx:45-58`（`COMPARE_UPLOAD_ERROR_LABELS`/`uploadErrorLabel`）、`:82-94`（`pairFailureLabel`）；`CompareTaskPage.tsx:186`（chip）、`:190/192`（空态/失败组）。
- **移植要点与风险**：**全在 G2 悬顶之下**。保留 V2 三路由→零搬运；V2 回单页→须把两 label 函数+8 码表带进旧 ComparePage.tsx 并补 types/api.ts 字段。矩阵归属标 V2 线，FE 开工前请先与 V2 线确认骨架归属。风险：中。守门：`frontend/tests/compare.test.tsx`（失败/上传用例）。

### 08 · FL-D859 选择文件反馈缺失+双端无 25MB 预检+V2 回执不带原因
- **问题**：选文件后卡片无文件名/has-file/「更换文件」反馈；双端无超大预检（服务端拒后同清单不可换文件只能新建任务）；V2 回执只说「第 N 对还没上传完」。
- **修复 commit**：`b257e46`
- **位置**：
  - V1 `compare.js:20` `MAX_UPLOAD_BYTES`；`:53` 卡片渲染（has-file/更换文案）；`:135` 提交前预检；`:1213-1228` change 监听同步卡片 DOM（**含 FL-D861 观察项在案**：通用监听与组内监听双处幂等，骨架合并事件层时维持至多两处、勿引申三处）。
  - V2 `shared.tsx:43` `COMPARE_MAX_UPLOAD_BYTES` + `PairInput/fileName` 帮手；`CompareNewPage.tsx:76` oversize 预检、`:44-50` 回执按 client_id 匹配文件位并带原因。
- **移植要点与风险**：P2 新建流程 B 重设计未动结构，V1 大体近零搬运；但卡片反馈段（`:1213-1228`）与预检（`:135`）是 B 后新增——pre-B 基线无此逻辑，必须携带。联动风险：`frontend/tests/compare.test.tsx` 与 `tests/browser/test_frontend_v2.py` 的 multipart mock 已按 client_id 回显真实形状适配，骨架改上传链路时两测试会红——**红了就是回执匹配被拆回旧形状的信号**，不许反向改测试迁就。风险：中高（测试与实现的联动绳子多）。

### 09 · FL-D980 覆盖不完整警告直露机读 token
- **问题**：parser coverage warnings（`UNSUPPORTED_VISIBLE_CONTENT:*`）直出给用户，看不懂哪部分没比对到。
- **修复 commit**：`915002f`
- **位置**：V1 `compare.js:36-50` `coverageWarningLabel()`（story 页眉/页脚/脚注/尾注/批注 + marker 图形/文本框等 + table-wrapper 组合句式）；消费 `:1123` 覆盖 chip popover 的 warning `<li>`。V2 `shared.tsx:60-80` 同函数；`CompareTaskPage.tsx:190` popover。
- **移植要点与风险**：函数纯零 DOM，直接搬运。**消费位骨架天然同构**：pre-B `compare.html:555-557` 已有 `compare-coverage-chip/summary/list` 同 id 结构，V1 接线按 id，零结构改动。契约边界：后端 warnings 协议码原样保留（tests/test_compare_remediation_boundaries.py 等锁定），可读化只做展示层，骨架别把映射沉到后端或删改协议字符串。风险：低。守门：`tests/browser/test_v1_frontend_remediation.py`（断言「页眉」）。

### 10 · FL-D997 选择产物下载按钮直露裸 kind + 文件名缺扩展名（改号自 984/982）
- **问题**：后端产物 kind 恒为 `final`/`redline`，旧 `selected_*` 键名从不命中→按钮直露「final · v1」；下载文件名模板漏 `.docx`。
- **修复 commit**：`915002f`
- **位置**：`frontend/compare.js:571-579` `renderSelectionDownloads()` 内 labels 表（final/redline 中文 + 旧键防御）+ `isDocx` 判断（final/redline 也补 `.docx`）。
- **移植要点与风险**：消费位 `#compare-selection-downloads`——pre-B `compare.html:710` 已有同 id，按 id 接线骨架零结构改动；唯一要携带的是 labels 表与 isDocx 模板两行。**注意 V2 无选择下载栏**（V2 未实现，既知形态差，骨架不因此补造）。风险：低，但骨架重排选择条 DOM 时若换掉这个 id，栏整体消失——id 保真即安全。

---

## 守门矩阵（FE 回退完工必跑；全绿=10 件不丢）

| 修复 | 守门测试 | 断言面 |
|------|----------|--------|
| 853 | `tests/test_compare_api.py`、`test_fl_d286_api_safety.py`、`test_upload_validation.py` | COMPARE_ENCRYPTED/UNSUPPORTED_FORMAT/LEGACY 精确码 |
| 854 | `tests/test_compare_system_review.py::test_view_fails_closed_when_source_or_result_object_changes` | 同长度篡改 409 |
| 855 | compare API 套件 | TOO_MANY_PAIRS 422 |
| 856/996 | `tests/browser/test_v1_frontend_remediation.py`（上传拒收/失败组用例） | 8 码中文+尾句一次 |
| 857/996 | 同上（diagnostics L1039 断言） | 组级原因按侧列出 |
| 858/859-V2 | `frontend/tests/compare.test.tsx`、`tests/browser/test_frontend_v2.py` | client_id 回显真实形状、V2 中文码 |
| 859-V1 | remediation 卡片反馈用例 | has-file/更换文件/25MB 预检 |
| 980 | remediation 覆盖 chip 用例（「页眉」断言） | 中文警告 |
| 997 | remediation 下载行用例 + 目检 | 中文标签+`.docx` 文件名 |

## FE 回退完工走查锚点（复用本线 dogfood 流程）

走查脚本 `/tmp/opencode/qa/compare_dogfood.py` + 复拍 `/tmp/opencode/qa/compare_dogfood_dl.py`（真实 app+worker+浏览器+python-docx 种子，14 状态截图）可直接换用骨架前端复跑，基线截图在 `/tmp/opencode/qa/compare-dogfood-20261101/` 做对照。验收逐状态：P1 空态/列表、P2 新建+选卡反馈、P3 连带四件（覆盖中文警告/失败组话术/下载行中文/选择条），与全屏 modal 新开壳（Esc/backdrop/关闭按钮）目检。

—— compare-ux 线 2026-11-01（制图人：修复实施者本人；FE 施工回扣问题走本线附录追加）
