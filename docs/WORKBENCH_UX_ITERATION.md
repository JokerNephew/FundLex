# 工作台 UX 迭代记录：业务结论汇总、导出与审计信息

日期：2026-10-13。分支 `frontend/workbench`（基于 `f6757e7`）。范围：正式前端 `frontend/` 的可用性优化；未改后端、规则、运行数据或其他并行工作线。

本轮实现来自产品评审结论中的 P0 全部与不依赖后端的 P1 子集；报告打包下载等需要后端配合的项目未实施，列于文末未完成项。

## 变更内容

| 变更 | 说明 | 文件 |
| --- | --- | --- |
| 结果页业务结论汇总 | 「合同结果」页头部由上传/处理计数改为资格三态（资格符合 / 已排除 / 资格失败 / 未判定）与交付三态（产物完整 / 结果不完整 / 未生成），消费服务端已有的 `qualification_counts` / `delivery_counts`；进度页保留队列与吞吐视角 | `frontend/app.js`、`frontend/index.html` |
| 总览交付卡修正 | 「交付不完整」卡片改为「产物完整」，并列出不完整与未生成数量，避免未生成结果被读成"没有问题" | `frontend/app.js` |
| 任务级规则版本 | 总览 hero、进度页、结果页任务标题处显示「规则版本 vN」chip，悬停可见任务绑定的规则包 SHA-256；任务列表行附规则版本 | `frontend/app.js`、`frontend/index.html`、`frontend/app.css` |
| 详情证据链补全 | 详情抽屉新增「目录状态」行（有目录域且未验证时提示在 Word 中更新；无目录域/未确认如实标注）；技术追溯区新增 `delivery_status`、`has_toc_field`、`toc_update_status`、`model`、`output_validation`、`artifacts` | `frontend/app.js` |
| 候选位置精度 | 候选证据行补充区域（正文/内容摘要）、字符区间、触发词预览与结构映射未通过标记 | `frontend/app.js` |
| 结果清单导出 | 结果页新增「导出结果清单 (CSV)」，按当前筛选与排序跨页汇总当前任务全部匹配合同（文件名/资格/处理状态/交付完整性/业务提示/原始原因码），UTF-8 BOM，导出提示明确"状态清单，不是合同交付" | `frontend/app.js`、`frontend/index.html` |
| 补传辅助 | 补传模式显示「待补传 N 份 · 已匹配 M 份」，新增「导出待补传清单 (CSV)」；导入阶段文案改为「01 本地文件初检」，避免浅检查被误读为内容级预检 | `frontend/app.js`、`frontend/index.html` |
| 完成通知 | 任务进入处理完成时弹出 toast；页面在后台时标签页标题显示「✓ <任务名> 处理结束」，回到前台恢复；启用了此前未被使用的 `#toast` 元素 | `frontend/app.js`、`frontend/app.css` |
| 品牌图标 | 补充 favicon 指向广发标志资源，消除浏览器对 `/favicon.ico` 的 404 控制台记录 | `frontend/index.html` |

边界保持：不伪造最终合同与批准；诊断/评测文件不进入正式交付；不新增人工复核、审批或待办；CSV 导出仅是状态清单。

## 验证结果

环境：仓库 `.venv` Python 3.12.14；`FUNDLEX_DATA_DIR` 指向临时目录；浏览器验收使用系统 Chrome 由 Playwright 驱动。

| 项目 | 实际结果 |
| --- | --- |
| `node --check frontend/app.js` | 退出码 0 |
| `git diff --check` | 退出码 0 |
| 完整测试 `python -m pytest -q -p no:cacheprovider` | **291 passed, 2 warnings, 28.97s** |
| 浏览器验收（`tools/evaluation/task_workbench_acceptance.py`，替身处理器、0 次模型调用） | **18/18 检查通过** |

浏览器验收逐项：导入文案与本地初检计数（8 可接收 / 0 异常）；真实上传→存储→worker→处理完成；结果页业务汇总数值与构造夹具一致（8 份：资格符合 4、已排除 2、资格失败 2、未判定 0；产物完整 0、结果不完整 2、未生成 6）；规则版本 chip 及 SHA-256 标题；详情目录状态行、候选位置行、技术追溯字段；结果清单 CSV（BOM + 表头 + 当前筛选 2 行）；补传模式文案、待补传清单 CSV（3 行）；任务完成 toast 实际触发；1440/1280/390 三档宽度在总览/进度/结果三视图均无页面级横向溢出；控制台 0 错误。

说明：浏览器验收使用明确标注的构造 DOCX 与替身处理器，只证明交互与真实 API/队列/存储链路，不是业务准确率、规则质量或真实模型验收；没有生成或开放最终合同。

环境备注：worktree 中首次运行完整测试时 `tests/test_rules_catalogue.py::test_source_provenance_and_reproducible_compilation` 因 `references/source/`（gitignore 未跟踪资料）缺失而失败 1 项；将本地来源资料复制进 worktree 后 291 项全部通过。这不是代码回归，来源资料不入库。

## 未完成项（如实记录）

1. 任务报告打包下载（ZIP，仅报告）需要服务端支持，本轮未实现；逐份报告下载维持现状。
2. 失败合同重试入口、生产 profile 隐藏「开发设置」、v2 评测产物（`evaluation_final`/`evaluation_redline`）独立下载区、详情深链等 P2 项目未开始。
3. 本记录只覆盖 `frontend/` 与本文档；未触碰主工作区并行进行的 v2 后端修改与未跟踪资料，未推送远端。
