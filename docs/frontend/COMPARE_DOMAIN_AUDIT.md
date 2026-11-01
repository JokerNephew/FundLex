# CX 比对线全覆盖签认审计（2026-11-01）

> 依据 `docs/COVERAGE_MATRIX_20261101.md`（qa/full-audit-20261031 分支 commit 3cab25b，本树经 `git show 3cab25b:docs/COVERAGE_MATRIX_20261101.md` 核对）中标记「CX 比对线」的全部 19 项逐文件签认。规则：✅+发现编号 或「无发现」，不许抽样。发现登记于 `docs/DETAIL_APPEND_COMPARE_UX.md`（FL-D853~861）。

## 一、文件签认表（19/19）

### 后端 fundlex/compare/（16 项，全部逐行通读）

| # | 文件 | 行数 | 签认 | 发现编号 |
|---|------|------|------|----------|
| 1 | `__init__.py` | 22 | ✅ | 无发现 |
| 2 | `align.py` | 299 | ✅ | 无发现 |
| 3 | `api.py` | ~全 | ✅ | FL-D853（415 码坍缩，已修）、FL-D854（评估后不修复，见条目）、FL-D855（max_pairs 死参，已修） |
| 4 | `ingest.py` | 42 | ✅ | 无发现（except 路径均归一 COMPARE_INVALID_DOCX，语义正确） |
| 5 | `models.py` | 245 | ✅ | 无发现 |
| 6 | `normalize.py` | 55 | ✅ | 无发现 |
| 7 | `parser.py` | 400 | ✅ | 无发现（story 部件覆盖标记齐备） |
| 8 | `presentation.py` | 284 | ✅ | 无发现（全仓 compare 域唯一窄捕获 L24，语义正确） |
| 9 | `render.py` | 482 | ✅ | 无发现（HTML 全部 escape，diff id 锚定） |
| 10 | `revisions.py` | 255 | ✅ | 无发现（接受修订唯一 canonical 实现，副本操作不改原件） |
| 11 | `selection.py` | 393 | ✅ | 无发现（SelectionError 码面稳定，走 api_errors `exc.code` 安全） |
| 12 | `selection_writer.py` | 1610 | ✅ | 无发现（全文逐行；trailing delete chain 等边界均有注释与测试） |
| 13 | `service.py` | 27 | ✅ | 无发现 |
| 14 | `store.py` | 1097 | ✅ | 无发现（清单绑定/幂等/硬上限语义已查证） |
| 15 | `text_diff.py` | 208 | ✅ | FL-D860（死代码行，已删） |
| 16 | `worker.py` | 193 | ✅ | 无发现（失败归一 DocxError→COMPARE_PARSE_FAILED 等） |

### 前端（3 项，全部逐行通读）

| # | 文件 | 行数 | 签认 | 发现编号 |
|---|------|------|------|----------|
| 17 | `frontend/compare.html` | 1110 | ✅ | 无新增发现（aria/tablist/region/空态标记完备） |
| 18 | `frontend/compare.css` | 742 | ✅ | 无发现（主题变量一致、无死规则冲突；FL-D840/843/845/851 注释在案） |
| 19 | `frontend/compare.js` | 1228 | ✅ | FL-D856（上传错误码映射，已修）、FL-D857（INCOMPLETE 兜底，已修）、FL-D859①②（卡片反馈+超大预检，已修）、FL-D861（双监听冗余，评估后不修复） |

### 跨线协助项（非本线矩阵条目，改动保留并标注）

| 文件 | 矩阵归属 | 改动 | 发现编号 |
|------|----------|------|----------|
| `frontend/src/types/api.ts` | V2 线 | ComparePair 扩展 side.upload_status/error_code、pair.diagnostics | FL-D858 |
| `frontend/src/pages/Compare/shared.tsx` | V2 线 | COMPARE_UPLOAD_ERROR_LABELS/uploadErrorLabel/pairFailureLabel/COMPARE_MAX_UPLOAD_BYTES | FL-D858/859 |
| `frontend/src/pages/Compare/CompareTaskPage.tsx` | V2 线 | chip/空态可读文案 | FL-D858 |
| `frontend/src/pages/Compare/CompareNewPage.tsx` | V2 线 | 拒收回执带文件级原因+.doc/超大预检 | FL-D859③ |

V1 `view-compare` 页面域按矩阵属 FE 前端主线；本线仅就 compare.* 三件套签名，视图状态矩阵如下供主线引用。

## 二、V1 view-compare 四态 × 状态问题矩阵

### list（任务列表态）

| 状态 | 处理 | 结论 |
|------|------|------|
| 空列表 | `.empty` 引导文案 ✅ | 无发现 |
| 搜索/筛选/分页 | URL 参数驱动、防抖 300ms、20/页 ✅ | 无发现 |
| 加载失败 | `field-error` 内联 ✅ | 无发现 |
| 任务计数徽标 | taskMetrics 聚合（待处理/失败/覆盖不完整）✅ | 无发现 |

### new（新建任务态）

| 状态 | 处理 | 结论 |
|------|------|------|
| 选文件反馈 | **FL-D859① 已修**：卡片文件名/has-file/按钮同步更新 | 已修复 |
| .doc 文件 | 客户端预检+服务端 LEGACY_DOC_UNSUPPORTED 双保险 ✅ | 无发现（FL-D859③ 同步 V2） |
| 超大文件 | **FL-D859② 已修**：25MB 客户端预检（服务端仍为准） | 已修复 |
| 文件夹配对 | 相对路径配对+未配对提示 ✅ | 无发现 |
| 半组（缺 A 或 B） | createTask 拦截文案 ✅ | 无发现 |
| 上传被拒 | **FL-D853/856 已修**：精确文件级原因+诚实补救（密封前不可替换，须新建任务） | 已修复 |
| 断点续传 | uploadDraft 保留已传进度、重试按钮 ✅ | 无发现 |

### detail（任务详情/组切换态）

| 状态 | 处理 | 结论 |
|------|------|------|
| 轮询 | 仅 queued/running/uploading；隐藏页签暂停、回前台恢复 ✅ | 无发现 |
| 组失败原因 | **FL-D857 已修**：INCOMPLETE 消费文件级 error_code；diagnostics 分阶段文案 | 已修复 |
| 处理中/待上传组 | 空态区展示原因，不留旧组残影 ✅ | 无发现 |
| 任务读取失败（深链失效） | 清空前身份数据+「任务不可用」+返回列表 ✅ | 无发现 |
| 超上限建任务 | **FL-D855 已修**：422 COMPARE_TOO_MANY_PAIRS 接线 | 已修复 |

### viewer（结果查看态，word/classic 双视图）

| 状态 | 处理 | 结论 |
|------|------|------|
| 结果读取失败 | viewError 展示+组卡红态 ✅ | 无发现 |
| 覆盖不完整 | coverage chip+popover 警告清单 ✅ | 无发现 |
| 零差异 | 区分「已覆盖范围内无差异」/「无文字差异」空态 ✅ | 无发现 |
| view 完整性 | **FL-D854 评估后不修复**：fails-closed 门优先，每请求全量 sha256 | 已评估 |
| 选择/生成/下载 | epoch 冲突保留本地、幂等键、过期版本标注 ✅ | 无发现 |
| 联动滚动/虚拟化/分栏 | FL-D840/841 系列在案，perf 门禁绿 ✅ | 无发现 |

## 三、回归证据（本轮修复后全量）

| 套件 | 结果 |
|------|------|
| pytest test_compare_api + test_upload_validation + test_fl_d286_api_safety | 13 passed |
| pytest test_compare_algorithm/…/test_compare_render（10 件） | 91 passed |
| pytest test_compare_sdt/selection*/store/system_review/tracked_changes/worker/pilot | 89 passed, 6 skipped（FL-D854 撤回后 system_review 复绿） |
| frontend vitest | 24/24（compare.test.tsx 回执 mock 按真实服务端形状回显 client_id） |
| frontend tsc / eslint / build | 绿 |
| 浏览器 test_v1_frontend_remediation | 16/16 |
| 浏览器 test_frontend_v2 | 11/11（首传测试 mock multipart 提取 client_ids） |
| 浏览器 test_frontend_fixes + test_compare_scroll_perf | 16/16 |

## 四、发现汇总（FL-D853~861）

- 已修复并验证：FL-D853、FL-D855、FL-D856、FL-D857、FL-D858、FL-D859、FL-D860（7 项）
- 已评估-不修复：FL-D854（fails-closed 完整性门优先于缓存性能优化）、FL-D861（幂等冗余观察项）（2 项）
- 历史在案：FL-D840~852（见附录）
