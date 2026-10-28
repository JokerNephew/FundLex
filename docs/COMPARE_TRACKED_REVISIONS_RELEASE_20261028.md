# Compare 修订版输入支持发布记录（2026-10-28）

## 范围

Compare 上传链路现在接受带 Word 修订痕迹的 DOCX：在私有副本上自动接受插入、删除、移动、表格行/单元格和属性变更标记，原始上传字节不被修改。原始与清理后哈希、大小和接受的修订数写入上传回执及 `compare_pair_files`。

不包含：交付引擎（Recall-first）的修订版输入策略；该引擎仍要求上传前接受/拒绝全部修订。Compare 与交付任务是两条独立链路。

## 代码

- 分支：`codex/compare-tracked-revisions`
- 基线：`f4bb2b7`（生产 Compare 后端基线；生产 `compare/store.py`、`docx.py` 与该基线一致）
- 提交：`feat(compare): accept existing Word revisions on upload`
- 新增：`fundlex/compare/revisions.py`、`fundlex/compare/ingest.py`
- 修改：`fundlex/compare/api.py`（上传校验）、`fundlex/compare/store.py`（审计字段与迁移）、`fundlex/docx.py`（允许清理阶段读取既有修订）
- 测试：`tests/test_compare_algorithm.py`、`tests/test_compare_api.py`

说明：生产 `fundlex/compare/api.py` 还包含 2026-10-28 的 Feishu/Compare 变更，因此生产发布采用同内容的最小回移补丁，而不是整体覆盖该文件。生产原有的 `fundlex/compare/ingest.py` 与提交版本哈希相同，未发生内容变化；`docx.py`、`compare/store.py` 按提交版本整文件替换，`revisions.py` 为新增。

## 生产发布

- 目标：`/opt/fundlex-recall-first`
- 重启：`fundlex-recall-api.service`、`fundlex-compare-worker.service`、`fundlex-feishu.service`
- 发布文件 SHA-256（见 `/tmp/opencode/fundlex-compare-revisions-20261028/deployed/sha256.txt`）：
  - `revisions.py` `995a4b37...`
  - `ingest.py` `25724d03...`
  - `docx.py` `fbe526d5...`
  - `compare/store.py` `6e67bcea...`
  - `compare/api.py` `a89b3b82...`
- 发布前代码备份与 SHA：`/tmp/opencode/fundlex-compare-revisions-20261028/code-before/`
- 发布前数据库备份：`/tmp/opencode/fundlex-compare-revisions-20261028/db-before.sql.gz`（MySQL `fundlex`，gzip 校验通过）
- 数据库迁移：启动时对 `compare_pair_files` 增加 `original_sha256`、`original_size`、`normalized_sha256`、`revisions_accepted`，仅新增可空字段/带默认值字段。

## 验证

- 生产目录服务：API 与 Compare Worker 均为 `active`，`/api/capabilities` 返回 200。
- 真实文件：`基金合同第一批_修订原件备份_20261027/广发ESG责任投资混合型证券投资基金基金合同.docx`，原始 138,515 字节，208 处 Word 修订。
- 生产 API → Compare Worker → 结果只读接口：
  - 上传回执 `accepted`，`revisions_accepted=208`；
  - 原始哈希 `bbe61101...`，清理后哈希 `80f72ef8...`，清理后 129,391 字节；
  - 任务处理完成（`incomplete` 仅因 header/footer coverage 警告，与既有契约一致）；
  - 结果 45 处差异（delete 24 / insert 12 / modify 9），view 左右 HTML 均返回；
  - 未授权访问返回 401/403；
  - 原始文件字节未改变。
- 证据：`/tmp/opencode/fundlex-compare-revisions-e2e-20261028/production-e2e.json`
- 定向回归（发布候选树，生产同源代码）：
  - 既有 Compare 套件 **48 passed**；
  - 新增修订相关测试 **35 passed**；
  - `py_compile`、`git diff --check` 通过。

## 未完成/后续

- 生产 V1 `frontend/compare.js` 仍是生产基线版本，上传成功但不会显示“已自动接受 N 处已有修订”的友好提示；回执字段已可用，后续前端发布时接入。
- 飞书 Compare 服务已引用同一 `ingest.prepare_compare_upload`，本次重启后加载 `revisions.py`，具备修订版输入能力；尚未做飞书端真实修订版上传 E2E。
- 集中问题记录 FL-D371 已在主工作区更新；本分支只保留发布记录。
