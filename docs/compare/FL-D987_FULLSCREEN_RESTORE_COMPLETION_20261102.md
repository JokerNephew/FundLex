# FL-D987 比对查看器全屏回退——完工报告（重组装终版，2026-11-02）

> 用户原话：「为什么给我的修订审查还有合同比对改成那么小了，原来的全屏弹窗很好啊」。
> 分支 `qa-frontend-reassembly-v1-20261102`，基 `84eb34e`（V2 物理删除后主线基），HEAD `10e97a5`。
> 验收标准：S1（用户原话断言表+截图证据+同类清零）。V2(React) 已随 FL-D1010 物理删除，**本报告只配 V1 面**。
> 重启发稿：INT D987b 审查 overlay 全屏（59721b8）已在基内，无需重做；React 移植件（我树旧 a95c3c9/3698c4e）整机作废。

## 一、实锤（刀位再行实测核验）

| 目标 | 「弹窗化」的刀 | 结果 |
| --- | --- | --- |
| 修订审查（V1） | 8b1dc2f（10-31 R2-F01，overlay inset:0→top:64/left:252）| 主基 `59721b8` 已落我树 D987b（overlay inset:0 复原，刀位不重复施工 |
| 比对查看器（V1） | B 工单 FL-D843 Region 化（去 dialog/无 backdrop/无 Esc）| 重组装-1（1db23bd）回退：9f5b61d 出生全屏 dialog 骨架复位 |

## 二、复原动作（commit 链）

| commit | 内容 |
| --- | --- |
| `1db23bd` | V1 viewer：role=dialog+backdrop+×关闭+Esc+body lock+prev/next+counter；chip/selection-bar/单行修订项/preventScroll 保留（B 已验收真修复），chip 遮罩下组切换走 dialog 内按钮（出生版等价语义） |
| `c53e608` | 质检附条件闭环（stale 注释清/preventScroll 回归/Esc 断言 V1+V2 各 1；V2 段在 84eb34e 后已失宿主）+APPEND 登记三边界（2 存效+1 V2 作废注记） |
| `5310390` | stash 裁决 V1 三件：FL-D990（删红 banner+「已锁定」）、FL-D992（badge max-width+ellipsis）、FL-D994（删列表小字「仅合同修改任务…」）+ 测试锚同步 |
| `10e97a5` | 质检 F1 修复：test_v1_password_late_401 锚恢复 FE-B 的 `[data-nav="feishu"]`（整文件 checkout 误回退） |

## 三、用户原话断言表（S1）

| 断言 | 结果 | 证据（/tmp/opencode/qa/proof/d987/） |
| --- | --- | --- |
| 查看器 offset fixed + inset 全 0、bbox=全视口（1600×1000/640×900）| ✅ | `v1-viewer-{desktop,mobile}.png`、测试验收 V1 remediation/dialog role/body lock/backdrop/Esc |
| 留缝（弹窗化特征）全清 | ✅ | 像素核验四边 12px 带为正文白底，非遮罩灰带 |
| B 真修复保留能力筛选/组切/splitter/覆盖 chip/selection 等 | ✅ | 两点 remediation 组件断言全绿（16/16） |
| baseline 红自清 | ✅ | test_v1_password_late_401 修复后单跑绿（曾基线本体红，但恢复FE-B 正确锚才是本体；其它 2 条同名红在其它线/已销）|

## 四、质检记录（双盲，本轮三批）

1. ①审重组装-2（V2 于作为废时也记录）——附条件验收 4 项全闭环（注释/preventScroll/Esc 断言/APPEND 登记）。
2. ②审重组装 V1 面（本次）——F1（nav 锚自伤）驳回→修复 `10e97a5`，实示 1 用例绿。
3. ③「87 passed」口径更正：重组装后全套收集实测 87 件（test_frontend_v2 随 V2 删除六约14 用例减少）；单件 collect 内不再错引。

## 五、守门

- 全套浏览器 87 passed + 1 **本体红（test_v1_password_late_401，修复前）** → 修复后重跑单用例绿；**最终回归口 = 87/88 中清剩已认证主体物件**
- 无 build step（V1 静态直连）
- 边界问题（**非本刀**）：model_and_feishu（settings 独立页锚不跟）、guide_history Listbox 锚（FE-C/D 下拉框新宿主）——入 APPEND 待派号。

## 六、交接

- INT 可整链摘：`1db23bd`（V1 dialog）+`c53e608`（V1 闭环）+`5310390`（静态三件）+`10e97a5`（锚修复）。
- stash@{0}（冻结期悬置）尚在引用未动——FE-F/FE-G（D890/896）若需反面参照，我拿 diff 生提交（协调令）。
- 真实模型调用 0（route-mock 干跑）。
