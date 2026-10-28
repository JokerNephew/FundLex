# operation-validation-20261024 快照压缩归档记录（2026-10-28）

## 授权

用户 2026-10-28 明确同意方案：保留 1 份完整 snapshot，其余 snapshot 只保留差异补丁，然后删除整树拷贝。原保留清单 `deletion_authorized=false` 由本次用户授权覆盖，仅限本记录列出的范围。

## 保留

| 内容 | 说明 |
|---|---|
| `snapshot-20/` | 完整参考树（含 `MANIFEST.sha256`，514 份合同 + 24 份 references 的哈希） |
| `data*/`、`target*/`、`dev*/` 等 | 各次验证的运行数据、复现输入输出、评审包（未改动） |
| `ledger.sqlite` | 调用/费用权威账本（未改动） |
| 顶层 pytest 日志/结果 JSON | 历史测试记录（未改动） |
| `patches/<name>.patch` | 其余 21 个快照相对 `snapshot-20` 的差异补丁 |
| `patches/<name>.tree.sha256` | 每个快照删除前的完整文件哈希清单 |

## 删除

21 个整树拷贝：`snapshot`、`snapshot-02` … `snapshot-19`、`debug-snapshot-03`、`replay-snapshot-03`。

删除前逐一确认：

- `patches/<name>.patch` 非空；
- `patches/<name>.tree.sha256` 非空；
- `patch -p1 --dry-run -d snapshot-20 < patches/<name>.patch` 成功。

## 校验

- 所有快照的 `funds_word/`、`docs/`、`references/` 与 `snapshot-20` **完全一致（0 差异）**，因此补丁不包含这三个目录；
- `snapshot-03`：完整重建后与原件 `diff -qr` 为 **0**（排除 `__pycache__`）；
- `snapshot-19`：删除后重建，完整文件哈希与 `patches/snapshot-19.tree.sha256` **完全一致**。

## 重建方法

```bash
cp -a snapshot-20 /tmp/reconstruct
cd /tmp/reconstruct
patch -p1 < /path/to/patches/snapshot-19.patch
```

## 结果

| | 之前 | 之后 |
|---|---|---|
| 目录大小 | 5.6GB | 830MB |
| 根分区可用 | 1.5GB | 6.2GB |

## 说明

补丁只覆盖代码/测试/工具/配置等差异；合同语料和证据目录由 `snapshot-20` 唯一保留。若未来需要某个历史快照，按上面的重建方法还原即可，哈希清单可用于逐文件核验。
