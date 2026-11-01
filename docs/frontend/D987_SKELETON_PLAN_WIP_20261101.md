# FL-D987 比对工作台全屏骨架恢复——施工计划与移植核对表（WIP，开工令·全线等件）

> 产出声明：本文件是增量 commit 纪律下的 WIP 占位+施工锚，随施工进度更新。
> 基线：出生 `9f5b61d`（全屏 dialog）+ 滚动丝滑 `5cdde51`；弹窗化刀 `18ba761`（5cdde51 之后 1h43m）。

## 一、骨架取法（开工令指定动作已完成）

`git diff 9f5b61d~1 5cdde51 -- frontend/src` 全库 24 文件（两 commit 跨 2 天，非纯比对）。
骨粗锁位改为按「弹窗化刀的落点」反推：`git diff 5cdde51 18ba761` 落定文件：

| 骨粗文件 | 弹窗化相关内容（18ba761 diff 实锤） | 骨架恢复动作 |
| --- | --- | --- |
| frontend/compare.css | 删 `.compare-viewer[role="dialog"]` 全屏规则族 + `body.compare-fullscreen-open` 滚动锁 + `.compare-viewer-close`；增 P3 region 规则 | 恢复 dialog 规则族（按 5cdde51 原文 + 后续 fx token 化合并） |
| frontend/compare.html | viewer `role="dialog"` → 页面内嵌；删 backdrop/关闭钮 | 恢复 dialog 结构（含 aria-modal/Esc/backdrop/关闭钮） |
| frontend/compare.js | openViewer 全屏 → setViewerDetail region 打开；滚动锁移除 | 恢复全屏打开+滚动锁/Esc；保留 chip 组切换与真修复 |
| frontend/src/pages/Compare/* + App.tsx | V2 拆三路由后查看器以页面 body 呈现（非全屏 dialog） | V2 查看器恢复全屏 dialog（modal over 页） |
| frontend/src/styles/app.css | 同 V2 | 同上 |

## 二、保留件（18ba761 非弹窗化真修复，骨架上必须留住）

- FL-D844 选择条并入修订 rail 底部（`.compare-selection-bar`，替代旧 selection-panel）
- FL-D845 修订项单行网格（height 128→44、`compare-diff-preview` 单行 ellipsis）
- chip 合同组切换条（role=tablist）——但组切换在 dialog 全屏内继续工作
- 删 direction-note（摘要行前缀「合同A → 合同B」承担）
- `setViewerEmpty/compare-viewer-empty`（失败/处理中组空态）
- FL-D840/841/842 滚动丝滑（5cdde51 自带，不碰）
- 弹窗化之后落库的真修复：98109db（比对列表行令牌）、64b7c5d（D880~895 对 compare 的部分）、6ee9eaa（矩阵件）、556e069（D896 对 ComparePage 的行改）

## 三、移植核对表（等 CX《PORTING_INDEX_FL-D987.md》对照替换）

> 本表是自建草案；CX 索引到后逐件用索引落点核验替换，不许凭表自证。

| # | FL | 类别判定（待索引核验） | 落点 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | FL-D980 | 未知→待索引 | 待索引 | ⏳ |
| 2 | FL-D996 | 未知→待索引 | 待索引 | ⏳ |
| 3 | FL-D997 | 未知→待索引 | 待索引 | ⏳ |
| 4 | FL-D853 | 未知→待索引 | 待索引 | ⏳ |
| … | FL-D854~859 | 未知→待索引 | 待索引 | ⏳ |

## 四、施工切片与 commit 计划

1. 片 1：V1 CSS+HTML+JS dialog 全屏恢复（含 Esc/backdrop/滚动锁/关闭钮），回归 V1 比对用例 → commit
2. 片 2：V2 查看器全屏 dialog（src/pages/Compare 查看器部分，不拆三路有页面本体）→ commit
3. 片 3：CX 索引对照 10 件逐件点名+补漏+全套回归+证据 → commit
4. 完工报告（用户原话断言表✅/❌+截图+质检子 agent 记录）
