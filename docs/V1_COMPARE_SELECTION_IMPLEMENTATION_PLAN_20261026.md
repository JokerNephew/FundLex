# V1 Compare 左右选择与选择版生成实施方案

日期：2026-10-26
负责人：当前主 agent
范围：V1 原生工作台、V1 Compare API/Worker、V1 浏览器回归
关联：FL-D328、FL-D329、FL-D330、FL-D331；设计基线见 [`V1_COMPARE_SELECTION_DESIGN_20261026.md`](V1_COMPARE_SELECTION_DESIGN_20261026.md)

本文是持续执行的实施账本。每个阶段都记录目标、代码范围、验证门槛、提交边界和回滚点。阶段状态只能在实际证据具备后更新；单元测试、fixture 或隔离 API 通过不等于真实用户交付通过。

## 0. 固定约束

- 只修改 V1 原生 Compare 和为其提供服务的 `fundlex/compare` 代码；React V2 不纳入本功能实现范围。
- 左右语义固定为“原版（左）→ 对比版（右）”。每处差异初始为 `pending`，用户明确选择 `left` 或 `right` 后才可生成完整选择版。
- 原始左/右 DOCX、比较结果 JSON 和已生成版本均不可被选择操作覆盖。每次生成必须绑定源文件哈希、结果哈希和选择 epoch。
- 生成必须基于实际 DOCX OOXML，重新打开并核对产物；不能用 HTML 拼接、文本替换脚本、模型自评或接口 200 代替产物验证。
- 选择版与修订痕迹版、选择报告分别记录；不把人工选择版冒称为规则引擎正式合同交付。
- 不调用真实模型。Compare 本身是确定性比较和人工选择功能；真实用户端到端仍需走工作台登录、上传、Compare Worker、选择、生成和授权下载。
- 不覆盖当前工作区已有 dirty 修改；提交时只暂存本功能实际新增或修改的文件和明确属于本轮的文档片段。

## 1. 当前基线与版本策略

### 当前快照

- 分支：`refactor/backend-engine-finalization`
- HEAD：`18093fa`
- 工作区：dirty，包含既有引擎、OAuth、V1/V2 前端、测试和集中记录修改。
- 当前项目结论：NO-GO；Compare 复杂结构和完整真实用户交付尚未闭合。
- 生产、真实模型和正式部署：本功能实施期间保持不动。

### 功能分支与提交规则

1. 创建功能分支 `codex/v1-compare-selection`，保留现有 dirty 文件。
2. 每个阶段完成后先运行该阶段门禁，再创建一个小提交；提交只包含该阶段文件。
3. 计划文档、设计文档和集中问题记录属于文档提交；若集中记录包含其他历史 dirty 内容，使用局部 patch 暂存，不能 `git add -A`。
4. 每个提交前记录：`git status --short`、`git diff --check`、相关测试命令和结果摘要。
5. 出现失败时保留失败证据和问题编号，不重置工作区。回滚使用反向提交或恢复到上一个功能提交，不使用 `git reset --hard`。
6. 阶段完成后在本文“阶段状态”和 `docs/ACTIVE_HANDOFF.md` 更新断点；压缩或交接后先读这两个文件再继续。

### 提交序列（预期）

| 提交 | 内容 | 状态 |
| --- | --- | --- |
| `docs(compare): add selection implementation plan` | 本方案和设计交接 | 进行中 |
| `feat(compare): add selection contract` | 选择状态、校验、哈希和纯逻辑 | 待开始 |
| `feat(compare): generate selected docx` | OOXML 选择版/修订痕迹版生成与验证 | 待开始 |
| `feat(compare): persist selection drafts` | 草稿、epoch、产物和下载 API | 待开始 |
| `feat(v1): add compare selection reader` | V1 阅读器选择控件、保存、生成、下载 | 待开始 |
| `test(compare): close selection delivery gates` | API、DOCX、浏览器和真实路径验证材料 | 待开始 |

## 2. 阶段一：选择数据契约与可执行能力分析

目标：把“采用左侧/采用右侧”从 UI 文案变成稳定、可校验、可哈希的服务端对象，并先识别哪些差异可安全写入。

### 代码范围

- 新增 `fundlex/compare/selection.py`：选择状态、差异选择单元、规范化、选择摘要、manifest/decision hash。
- 必要时扩展 `fundlex/compare/models.py` 的类型投影，但不改变既有 Compare 结果 schema 的兼容字段。
- 新增纯逻辑测试：修改/新增/删除、pending、全部左/右、未知 ID、重复 ID、结果哈希绑定、重叠/联合选择。
- 更新 FL-D331 和本文状态。

### 设计门槛

- `pending` 不等同于 `right`，生成能力明确拒绝未选择。
- 选择集合只能引用服务端结果中的 diff ID；客户端不能提交任意文本作为 replacement。
- 差异选择以稳定 diff ID 和当前 result hash 绑定；结果变化必须失效旧选择。
- 单个差异跨多个 span 时作为一个选择单元；重叠或结构依赖项要么形成联合单元，要么列为不可生成。
- 选择摘要必须能解释新增/删除的空侧语义。

### 验收门槛

- 纯逻辑测试通过。
- 选择 hash 对排序、重复和未知项有确定性行为。
- `git diff --check`、Python 编译通过。
- 未改变已有 Compare API/Worker 行为。

### 回滚点

只回滚阶段一新增模块和测试；既有 Compare 结果 schema 不需迁移。

## 3. 阶段二：实际 DOCX 选择版生成器

目标：从真实左右 DOCX 和已验证 Compare result 生成选择版，并独立核对实际文本、结构和包完整性。

### 实现顺序

1. 建立 OOXML 文档地址映射：正文段落和普通表格单元格使用稳定 location，校验 parser 的 source hash、block text 和 span。
2. 在左侧文档副本上建立安全编辑计划：段内替换先覆盖单 block；跨 block、空侧整段、结构变化先进入明确阻塞清单。
3. 实现 `left/right` 选择写入，保留原有 run 属性，正确处理前缀、后缀、空格、换行、表格单元格和从右侧插入文本的基本场景。
4. 输出选择版和选择修订痕迹版；选择修订痕迹版只表达实际与左侧基底不同的选择，不复制未选择或被拒绝的差异。
5. 重新打开产物，验证 DOCX package、非 document 部件、目标文本、非目标文本、段落/表格结构和选择报告哈希。

### 首期支持范围

- 支持：单段内 modify、单段内 insert/delete、普通表格单元格内单段差异、多个不重叠差异。
- 阻塞并解释：跨段差异、整段结构插入/删除、合并单元格、嵌套表格、header/footer/drawing/field/content control 等未建立安全编辑地址的结构。
- 覆盖状态为 incomplete 时，不自动拒绝所有结果，但任何落在未覆盖或不可写结构的选择必须阻止生成并列出位置；不能把不完整结果命名为完整最终合同。

### 验收门槛

- 使用真实 `python-docx` 生成的 DOCX 和 XML 夹具覆盖修改、新增、删除、表格、相邻差异及混合选择。
- 生成文件能被 `python-docx` 和项目 DOCX reader 重新打开。
- 选择左侧的目标与左侧投影一致，选择右侧的目标与右侧投影一致；未改变位置保留左侧。
- 篡改源文件、result JSON、span、选择 hash 或输出路径时 fail closed。
- 生成错误不留下半成品或错误下载记录。

### 回滚点

在选择 API 接入前，只删除新的 compare selection writer 和定向测试；不改旧 renderer、parser 或 Worker 结果。

## 4. 阶段三：持久化、并发版本和下载 API

目标：让刷新、重开、多标签和生成后的版本都有可追溯状态。

### 数据模型建议

- `compare_selection_drafts`：`pair_id`、`selection_epoch`、`result_sha256`、left/right source hash、canonical decisions JSON、decision hash、状态、时间。
- `compare_selection_artifacts`：pair、generation version、kind、object key、sha256、size、selection epoch、decision hash、源/result hash、报告对象。
- 迁移必须兼容 SQLite 与 MySQL；初始化/迁移不在请求热路径中创建竞争 schema，避免复现 FL-D308 类问题。

### API 建议

- `GET /api/compare/pairs/{pair_id}/selection`：返回 diff 选择清单、草稿、epoch、摘要、生成能力和已有版本。
- `PUT /api/compare/pairs/{pair_id}/selection`：携带 expected epoch、result/source hash 和完整或增量选择，原子保存。
- `POST /api/compare/pairs/{pair_id}/selection/preview`：绑定当前快照，返回可执行计划和阻塞，不发布文件。
- `POST /api/compare/pairs/{pair_id}/selection/generate`：只接受当前草稿版本，生成并原子记录文件和报告。
- `GET /api/compare/pairs/{pair_id}/selection-artifacts/{version}/{kind}`：鉴权后下载。

### 安全门槛

- 所有 pair、draft、artifact 查询和下载都校验 owner。
- epoch、result hash、左右源 hash 任一不匹配均返回稳定冲突错误。
- 生成请求重复提交必须幂等或返回同一 generation version，不能产生悬挂重复文件。
- 当前草稿变更后旧 artifact 标记为 stale；旧文件仍可追溯，但不能显示为当前版本。

### 验收门槛

- API 定向测试覆盖正常保存、刷新恢复、未知 diff、过期 epoch、结果篡改、跨用户、重复生成和下载哈希。
- SQLite 通过后，如环境可用，再运行真实 MySQL 8 迁移/并发测试；未配置时明确保持 skipped，不冒称通过。
- 既有 Compare 上传、seal、Worker、view API 回归不受影响。

### 回滚点

迁移和 API 可通过反向迁移/关闭新路由回退；已生成对象不删除，保留审计对象。生产发布前必须有数据库备份和 schema 版本证据。

## 5. 阶段四：V1 阅读器交互

目标：在右侧差异 rail 中完成选择、草稿保存、进度展示、预览和生成下载。

### 页面改造

- `frontend/compare.html`：建立任务列表、创建态、结果态、阅读态边界；阅读器增加选择进度、左右选择控件、待选择导航、预览/生成/下载区域。
- `frontend/compare.js`：维护 `selectionEpoch`、decision map、保存 token、生成 token、当前 generation version；重开恢复，不信任过期响应。
- `frontend/compare.css`：右侧独立滚动 rail；768px 以下抽屉/单栏降级；控件复用 V1 `.btn`、`.toolbar`、`.card`、Review 清单样式。

### 交互门槛

- 页面明确显示“未选择不能生成”；不会以默认右侧替代用户决定。
- 全部左右操作显示作用范围和影响数量；筛选不改变未显示项。
- 选择保存失败时保留本地草稿、提示重试，不清空用户决定。
- 生成成功后显示版本、选择计数、文件哈希和下载按钮；选择变更后旧版本标记过期。
- 键盘可操作 radio/button，焦点、ARIA、移动端抽屉关闭和目标侧切换可验证。

### 验收门槛

- V1 浏览器夹具覆盖修改/新增/删除三类选择、全选、pending 阻断、刷新恢复、冲突和下载。
- 390px、768px、1440px 无横向溢出；右 rail/抽屉独立滚动，外层页面不被差异定位带走。
- `node --check frontend/compare.js` 和既有 V1 浏览器回归通过。

### 回滚点

前端可通过隐藏新选择区域、保留只读 view 入口回退；不删除后端已生成 artifact。

## 6. 阶段五：全链路验证与候选冻结

目标：确认实际用户路径和交付文件，不把隔离测试当正式完成。

### 验证层次

1. 静态：diff check、Node check、Python compile、类型/构建检查。
2. 纯逻辑：selection、OOXML writer、报告和 hash 测试。
3. API/Worker：真实 DOCX 上传 → seal → Compare Worker → view → selection save → generate → download。
4. 浏览器：登录工作台、进入 V1 Compare、查看差异、逐条左右选择、刷新恢复、生成并下载。
5. 产物复核：独立读取下载 DOCX，核对前后文本、差异选择、段落/表格结构、修订痕迹、报告和文件哈希。
6. 环境：若执行测试环境发布，记录备份、部署哈希、服务状态和回滚路径；生产发布需另有明确发布授权与完整门禁。

### 必须保留的证据

- 测试命令和完整结果；
- 任务/pair/generation version（使用脱敏 ID）；
- 源文件、result、选择报告和下载文件 SHA-256；
- 浏览器视口、页面/控制台错误、关键请求状态；
- 未支持结构、覆盖不完整和失败任务的明确说明。

### 完成判定

只有真实用户路径完成且实际 DOCX、选择报告、修订痕迹和下载哈希一致，才能把 Compare 选择版功能标为已交付。只通过单测、API、fixture、页面按钮或生成调用不能标为完成。任何服务/预算/环境阻塞写入集中问题记录和 ACTIVE_HANDOFF，状态保持未完成。

## 7. 持续进度账本

| 阶段 | 状态 | 最近证据 | 下一动作 |
| --- | --- | --- | --- |
| 0 基线/分支/方案 | 进行中 | 本文已创建；工作区 dirty 快照已核对 | 创建功能分支，提交计划文档 |
| 1 选择契约 | 未开始 | — | 新增 selection 纯逻辑和测试 |
| 2 DOCX 生成器 | 未开始 | — | 在契约稳定后实现 OOXML writer |
| 3 持久化/API | 未开始 | — | 增加迁移、草稿、artifact 和下载路由 |
| 4 V1 阅读器 | 未开始 | — | 接入右侧选择 rail 和生成状态 |
| 5 全链路/候选 | 未开始 | — | 分层回归、真实用户路径、候选冻结 |

最后更新：2026-10-26，方案创建阶段。下一条可执行动作是创建功能分支并提交本方案，再开始阶段一。
