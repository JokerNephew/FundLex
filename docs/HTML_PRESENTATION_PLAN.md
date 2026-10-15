# A 方案（服务端 HTML 呈现 + 逐条接受/拒绝修订）全链路改造方案

日期：2026-10-16。状态：**进行中**。本文件是方案规格与进度台账，随实施更新。

用户决定：采用 **A 服务端 HTML 方案**（不再用 docx-preview、不再用第三方编辑器）。
目标：用户在结果页看到合同的 HTML 呈现，**逐条勾选接受/拒绝修订**（与在 Word 中操作一致，任意组合自由），据此生成**独立的最终版产物**，并支持一键接受全部。原引擎产出的 `final`/`redline` 保持不变、可追溯。

## 1. 已验证的事实基础

| 事实 | 证据 |
| --- | --- |
| 修订 id 规则：第 n 条 edit → `del_id=2n-1`、`ins_id=2n`（按 `(location, -start)` 排序） | `fundlex/docx.py:983-989` |
| 每条 edit 的 manifest 字段：`edit_id/location/start/end/expected_old_text/replacement/template_id/del_id/ins_id` | `docx.py:986-989` |
| 全接受逻辑已存在：`_accept_our_revisions` 把 `ins` 内容提升、`del` 整块删除 | `docx.py:808-835` |
| 纯删除型修订只有 `w:del` 无 `w:ins`（D01 中 #2/#10/#12/#13） | demo `revisions.json` |
| 交付状态：`incomplete` → 产物 `working_final`/`working_redline`；`complete` → `final`/`redline` | `store.py:433-448` |
| 产物 kind 有**三处白名单**必须同步 | `store.finish`(530)、`store.get_artifact`(432)、`api.download`(916) |
| 前端为单文件 99KB `frontend/app.js` + `index.html` + `app.css` | 实测 |
| HTML 转换当前丢失目录/超链接/域/分页 | 问题 FL-D087 |

## 2. 丢失清单（FL-D087）与修复要求

当前 demo 转换器只处理 `body` 顶层 `w:p`/`w:tbl`，丢弃 `w:sdt`（目录所在）、`w:hyperlink` 链接目标、`w:fldChar`/`w:instrText` 域、`w:bookmarkStart` 锚点、`w:br` 分页与 `sectPr` 分页。

修复要求见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md` FL-D087「处理方法」1-6 条。

## 3. 改造范围（全链路）

### 3.1 后端 · 投影层（新文件 `fundlex/html_view.py`）

职责：把 DOCX 投影为带修订锚点的 HTML + 修订清单。**完全独立于现有 `docx.py` 的写入逻辑**，只读。

- 输入：DOCX 路径 + 可选 report（提供 `edit_id`/`rule_id`/`location` 业务映射）。
- 输出：`{"html": str, "revisions": [...], "meta": {...}}`。
- 要求：
  - 通用块级遍历：`w:p`/`w:tbl`/`w:sdt`/`w:sdtContent` 递归，未知容器继续下沉，不静默丢弃。
  - 修订锚点：`w:ins`→`<ins data-rev="{ins_id}">`、`w:del`→`<del data-rev="{del_id}">`；`data-rev` 直接取 OOXML `w:id`，与 manifest 一致，**零文本匹配**。
  - 超链接：`w:hyperlink` 的 `r:id` 经 `document.xml.rels` 解析为真实 URL 输出 `<a href>`；锚点型输出 `#bookmark`。
  - 域：`w:fldChar`/`w:instrText` 不显示域代码；保留缓存结果文本（`w:t`）。
  - 书签：`w:bookmarkStart`→`<a id>`。
  - 分页：`w:br w:type="page"` 与 `w:sectPr` 输出分页边界标记，便于前端分段。
  - 安全：HTML 转义、属性转义；链接协议白名单（http/https/mailto，其余降级为纯文本）。
  - 修订清单：由 `del_id=2n-1`/`ins_id=2n` 配对，右侧清单用；纯删除型 `after` 为空。

### 3.2 后端 · 选择性写入（扩展 `fundlex/docx.py`）

新增公共入口（不改动既有函数行为）：

```
generate_selected_artifacts(source, plan, target_path, decisions, *, author, limits)
```

- `decisions`: `{del_id/ins_id → "accept"|"reject"}`，或 `edit_id` 集合。未给出的默认按 `accept`（与"一键全接受"等价）。
- 实现：先按 `generate_artifacts` 同样的方式生成 redline（保持 del/ins 结构），再**逐条**应用：
  - `accept` 一条：提升该 `w:ins` 内容、删除该 `w:del` 块（单条执行 `_accept_our_revisions` 的子集）。
  - `reject` 一条：**移除 `w:ins` 与 `w:del` 包装并把 `w:del` 内的 `delText` 还原为 `w:t`**，令文本回到原文；同时移除 `w:ins` 引入的文本。
- 独立复验：重新打开产物，确认「被接受条目 = 新文本、被拒绝条目 = 原文本」，并确认非目标段落/结构未变。

**关键正确性要求**：拒绝时 `w:del` 内的 `delText` 必须还原为普通 `w:t`（否则 Word 会显示为删除内容），`w:ins` 必须整块移除（丢弃新文本），二者不可混。

### 3.3 后端 · 产物 kind 与新端点

新 kind：`selected_final`（用户选择后的最终版 DOCX）。三处白名单同步：
- `store.finish` 的 `allowed_kinds`
- `store.get_artifact`
- `api.download` 的 `docx_kinds`

新端点（`fundlex/api.py`）：
| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/batches/{b}/documents/{d}/revisions` | 返回 HTML 视图 + 修订清单 + 业务映射 |
| POST | `/api/batches/{b}/documents/{d}/decisions` | 提交逐条决策，生成 `selected_final` |
| POST | `/api/batches/{b}/documents/{d}/accept-all` | 一键接受全部，生成 `selected_final` |

- 所有端点走现有鉴权（`Depends(_user)`）。
- 生成后用 `store` 的既有校验路径登记产物，记录决策到 report 或独立表（**决策必须可追溯**）。
- 校验：kind、哈希、交付状态一致性沿用 `validate_delivery` 逻辑。

### 3.4 前端 · 详情面板改造

- 结果页每份合同新增「查看修订 / 选择接受」入口。
- 面板结构：左侧 HTML 合同视图（唯一滚动容器），右侧修订清单（每条含规则、前后文、勾选）。
- 交互：勾选 ↔ 正文 `data-rev` 高亮联动；点清单条目 `scrollIntoView` 精确定位（**不做双栏同步滚动**——已实测两侧高度差 22%，无解）。
- 操作：一键接受全部、生成最终版、下载 `selected_final`。

## 4. 进度台账

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 根因定位（目录丢失）与丢失清单 | ✅ 已完成（FL-D087） |
| P1 | 投影层 `html_view.py`（含目录/链接/域/锚点/分页） | ✅ 已完成，已验证 |
| P2 | 选择性写入入口（`selective.py`） | ✅ 已完成，已验证 |
| P3 | 新 kind + API 端点 | ✅ 已完成，已验证 |
| P4 | 前端交互面板 | ✅ 已完成，真实浏览器已验证 |
| P5 | 单元/集成验证 | ✅ 已完成（19 项新测试；全套 596 通过） |
| P6 | 真实云端端到端交付验证 | ⬜ 进行中 |

### 已完成阶段的验证证据

- **P1**：真实 D01 `working_redline` 投影出 24 条目录 + 24 个链接；17 条修订全部映射到规则 id；纯删除型集合 `{2,10,12,13}` 与既有 demo 一致。
- **P2**：全部接受输出与引擎自身 `working_final` **逐段一致**；全部拒绝恢复每一条 `expected_old_text`；单条拒绝只影响其所在段落（p1191）；纯删除型拒绝能恢复被删文本。
- **P3**：真实 API 路径（含产物无 `.docx` 后缀的真实情况）通过；拒绝 `{1,7}` 后下载文件为合法 DOCX、0 条残留修订、被拒条目还原原文、被接受条目保留替换文本。
- **P4**：真实 Chromium 驱动真实 API：17 条修订/17 个勾选、目录 24 条 24 链接、勾选联动、点清单精确定位、生成与下载成功、下载文件内容正确、**0 控制台错误**。

### 实施中修复的真实缺陷

1. **产物无 `.docx` 后缀**：存储产物保留原始上传名，而 `_read_parts` 以 `.docx` 后缀作为上传防护拒绝读取；`html_view` 与 `selective` 改为经临时 `.docx` 副本读取，包限制仍全部生效。
2. **前端 `pathDoc` 用错字段**：文档行暴露 `document_id` 而非 `id`，导致请求 `/documents/undefined/revisions` 返回 404。
3. **删除文本未被采集**：`w:delText` 不在 `w:t` 中，导致修订清单 `before` 全为空。

## 5. 版本与回退

- 分支：`codex/fundlex-recall-first`；每阶段独立 commit，可单次 revert。
- 不动原引擎产物逻辑，新能力全部为新增，回退不影响既有交付。
