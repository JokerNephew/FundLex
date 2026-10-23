# 合同双版本对比验收报告

日期：2026-10-23

当前分支：`feat/contract-compare`；Compare 发布提交：`eba2b3a`，已推送到 `origin/feat/contract-compare`。工作区仍保留其他任务的未提交改动，不能使用整仓库 `git add` 或覆盖工作区。

## 交付内容

合同对比实现位于 `fundlex/compare/`，由 DOCX OOXML 解析、保留 offset 的文本差异、结构对齐、HTML/SVG 渲染、独立持久化、API 和 Worker 组成。它只比较正文、标题和普通表格文字，与 recall、revision、model、guide 和 delivery pipeline 分开。已有 Word 修订痕迹的输入会拒绝；暂不支持的可见结构会将结果标为 `coverage=incomplete` 并给出警告。

任务模型使用独立的 compare 表、对象存储、owner 隔离和 Idempotency-Key。上传会完整校验 DOCX 包，源文件和结果都绑定大小、SHA-256 与对象 key。Worker 使用 lease/fencing token、心跳、有限 transient retry、固定错误码和 pair 级失败隔离；MySQL 的过期租约清理不会覆盖并发 finish 或 heartbeat。独立服务模板在 [fundlex-compare-worker.service.template](../tools/deploy/fundlex-compare-worker.service.template)，已安装为生产 `fundlex-compare-worker.service`。

工作台入口使用 [compare.js](../frontend/compare.js) 和 [compare.css](../frontend/compare.css)：支持单组和批量 pair、独立双栏滚动、点击/上一处/下一处、虚拟锚点、文件夹相对路径配对、未配对文件手工补齐、失败状态和 coverage 提示。HTML 文本由后端转义，差异连线按浏览器实际几何位置重算。

## 验证结果

- 完整项目回归：`.venv/bin/python -m pytest tests -q` → **1195 passed / 40 skipped / 2 warnings / 247.79s**。日志：`/tmp/opencode/compare-final-pytest-2.log`。
- Compare 本地专项：`.venv/bin/python -m pytest tests/test_compare_*.py -q` → **70 passed / 5 skipped / 1 warning**。
- Compare 隔离 MySQL 8.0 专项：在临时实例 `127.0.0.1:33155` 和隔离测试库运行 → **75 passed / 1 warning / 14.31s**。覆盖长 JSON、并发 claim、stale finish/retry、upload/seal、过期清理与 heartbeat 竞态。生产数据库未连接。
- 关键并发用例额外重复 5 轮，每轮 **2 passed**。
- 语法与静态检查：Node `--check frontend/compare.js`、Python `py_compile`、`compileall`、`git diff --check` 均通过。
- 开发环境浏览器验收：临时 FastAPI + 实际 CompareWorker + Playwright，**9 个场景、24/24 checks passed**。证据：[compare-e2e-final-current.json](/tmp/opencode/compare-e2e-final-current.json)，截图目录 `/tmp/opencode/compare-e2e-final-current-shots/`。场景包括单处 modify、0 diff、三组批量、25 处差异、insert/delete/modify、空侧虚拟锚点、文件夹手工补配、全失败任务、真实公开合同、XSS 转义、身份隔离、导航和 resize/独立滚动。三次 SVG 端点误差均为 **0px**，无浏览器 page error。

## 真实合同算法评测

冻结语料位于 `/tmp/fundlex-compare-corpus-v4`：20 份公开合同、14 dev / 6 holdout、386 mutation pairs。独立 gold 直接读取 OOXML，不导入 compare 实现。证据和源冻结位于 `/tmp/opencode/compare-continuation/`。

- dev：272 pairs，219/219 gold operations，operation recall **1.0**；zero fixtures 69，identity false positives **0**；modify classification **112/113**。
- holdout：114 pairs，92/92 operations，operation recall **1.0**；zero fixtures 30，identity false positives **0**；modify classification **46/46**。
- Hard gates：identity **20/20**；symmetry **20/20 bases、60/60 directional checks**；determinism **20/20 bases**。
- 冷进程 benchmark：20 对，median **1.1745s**，P95 **1.6512s**，max **4.0687s**，peak RSS **51,728,384 bytes**。该 benchmark 未清空 OS page cache。
- gold payload SHA-256：`45651ace97a78ec4d1d6e28d8b492f6ec090da55b62156ffae58ee6ca5779e04`。
- gold 文件 SHA-256：`1a2afabe6bc09c182c107d9d608b5ea420dd08db57db855dbfe12ad914b63c3d`。
- manifest SHA-256：`731a29bf9dbd199ca978e476313e1d6fa9d67239725e917ee3c93f6ddbe10e60`。

算法独立复查对 42 种分段的 1764 对组合和 1500 组随机重排/修改攻击，发现 0 次字符流差异被归零、0 次双向不对称。已知分类限制是 split/merge 结构变化伴随局部文字修改时，部分结果会保守降级为整组 delete + insert；字符级召回保持，但 modify 粒度下降，已登记 FL-D152。B14–B19 holdout 曾在前一轮暴露，按透明回归 split 披露；B07 历史 zero 声明与实际可见字符流不一致，v7 已按独立字符流更正；12 个 `modify_percent` fallback 样本不冒称百分比语义样本。

## 状态和边界

FL-D149–FL-D153、FL-D160–FL-D162 的处理与验证已写入 [集中问题记录](DETAIL_ISSUES_AND_RESOLUTIONS.md)。FL-D152 的结构分类限制仍是已知范围，不阻塞字符级高召回硬门。

本轮 compare 不调用大模型，模型费用为 `$0`。生产发布通过既有 `tools/deploy/publish_workspace.sh` 完成，随后安装并启用 `fundlex-compare-worker.service`；API、Recall Worker 和 Compare Worker 均为 active，三项服务重启计数为 0。没有修改 nginx 或生产数据库结构。

## 生产用户链路验收

- 生产入口：`https://fundlex.club`，password 登录模式；通过工作台注册/登录实际账号后进入「合同对比」。
- 输入：两份已授权使用的公开 DOCX 合同，分别为消费品精选和品质回报合同；未调用修订模型。
- 实际路径：创建任务 → 上传左右文件 → 封存 → `fundlex-compare-worker.service` 领取并处理 → 结果页查看 → 双栏渲染 → 下一处差异导航 → 下载差异报告。
- 结果：生产 pair 状态为 `incomplete`，共 **2772** 处差异（修改 451、新增 1238、删除 1083）；页眉、页脚、AlternateContent、drawing、pict 等暂不支持可见结构被明确列入 coverage warning，没有伪装为完整覆盖。
- API 证据：`/tmp/opencode/compare-production-e2e/report.json`；浏览器证据：`/tmp/opencode/compare-production-browser-e2e/report.json`，报告下载文件 SHA-256 为 `076bd85be8cdebbad8798bad3b22f377dd1b21c9b3f1a0d1eb54d88ca42911ea`，浏览器 page error 为 0。
- 生产发布状态：**Production deployment: PERFORMED**。

## UI 改版发布回归（2026-10-24）

- UI 提交 `5d04271` 已推送并通过 `tools/deploy/publish_workspace.sh` 发布到 `/opt/fundlex-recall-first`；API、Recall Worker、Compare Worker 均 active，重启计数为 0。
- 生产浏览器路径：注册/登录 → 合同对比 → 上传两份公开 DOCX → 独立 Worker 处理 → 结果页 → 原版/对比版方向说明 → 覆盖 warning → 差异筛选 → 键盘定位 → 移动端侧栏切换 → 下载报告。
- 结果：2772 处差异（修改 451、新增 1238、删除 1083）；报告下载 3189696 bytes，SHA-256 为 `d1607d77f3b0fe8487c8c1a8b4c2c287599e5283eb7d207b447ce0ca719716e3`；page error 为 0。
- 证据：[生产 UI 回归报告](/tmp/opencode/compare-production-ui-e2e/report.json)，截图位于 `/tmp/opencode/compare-production-ui-e2e/viewer.png`。
- 本次 compare 不调用模型，模型费用为 `$0`。
