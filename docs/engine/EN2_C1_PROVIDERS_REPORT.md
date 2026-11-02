# EN2 · C 类 1 件完工报告：PROVIDERS 清单按供应商现行目录更新 + 灰置（2026-11-02）

- 裁定来源：用户拍板「C 类 FL-D937(7) 要——按供应商现行目录更新」。
- 施工区间：commit d5d4b72（主干）+ fc6cd78（质检回流）
- 范围：provider 下拉（修改/复核两模型配置卡，V2 React 与 V1 静态前端同款）

## 一、用户原话逐条断言表

| # | 用户/裁定原话 | 断言 | 证据 |
| --- | --- | --- | --- |
| 1 | 「按供应商现行目录更新」 | ✅ 7 家全部按 2026-11-02 官方目录刷新 | 后端 `fundlex/user_model_connections.py.PROVIDERS`；逐供来源见第②节 |
| 2 | 「用只读方式取现行目录…凭据只引环境变量不落盘不打印」 | ✅ 零凭据零落盘 | 核验走各家公开官方模型页（webfetch/websearch 只读，无 key）；全程 LLM_API_KEY unset 未触发；无任何凭据写入仓库/prompt/日志 |
| 3 | 「custom 通道保留兜底」 | ✅ 保留 | PROVIDERS["custom"] 存在未动 |
| 4 | 「下拉展示取『现行在售+我方验证可用』交集，不可用条目如实灰置不藏」 | ✅ 交集+灰置 | 在售=官方目录现行；我方验证=后端 save/test_connection 路径不拒（umc 套件 33 passed）+V2/V1 两端 datalist 只放在售项；deprecated_models 灰字 <del> 展示带官方停用日期+建议，不藏 |
| 5 | 「截图自检」 | ✅ 实拍 ×2 | /tmp/opencode/qa/screenshots/mi-edit-{primary,review}.png（Vite preview+Playwright 构陷 API，零凭据零外发；灰置 del 文本清晰可见） |
| 6 | 「子agent质检」 | ✅ 已过且回流闭环 | 双盲质检：总判 ✅ 带 2 处文案瑕疵（DeepSeek 继任名 outdated、glm-4.5 措辞），fc6cd78 闭坏 |
| 7 | 「vitest」 | ✅ | frontend tests：modelSettings.test.tsx 新增 3 例（灰置展示/datalist 排除/无下线不显示条）；全量 27/27 Duration 24s |

## 二、只读核验来源（2026-11-02，官方页为准）

- moonshot：platform.kimi.com/docs/models——moonshot-v1 全系 2026-08-31 官方下线（实锤）；kimi-k3.1-pro（旗舰）/highspeed/kimi-k3 在openname。
- deepseek：api-docs.deepseek.com/quick_start/pricing——当前模型名 deepseek-v4-pro / deepseek-flash（V4.1-Flash-1017 由 flash 接任）；deepseek-chat/reasoner 官方通告 2026-07-24 停use。
- 阿里云百炼：help.aliyun.com model-studio——qwen-max/qwen-plus/qwen-flash 滚动别名在支持清单（qwen-turbo 未核到现行车站条，灰置带对冲措辞）。
- 智谱：docs.bigmodel.cn model-overview——glm-5.3（旗舰）/glm-5.3-flash/glm-4.7 在list；glm-4-flash 改快照 glm-4-flash-250414；glm-4.5 旧代。
- OpenAI：OpenAI 官方退役公告（2026-02-13）——gpt-4o/gpt-4.1/gpt-4.1-mini 快照 2027-01-14 退役计划；gpt-5.5/gpt-5.2/gpt-5-mini 在 API 目录。
- 硅基流动：api-docs.siliconflow.cn release notes——DeepSeek-V4.1-Flash（2026-10-17 高速版上线）、Qwen/Qwen3-235B-A22B-Instruct-2507 为现行 ID；DeepSeek-V3 灰置标注。

## 三、契约影响
- 后端/settings/model 出参新增 `deprecated_models` 键（纯新增，旧消费面不破防）。
- save/prepare/validate_snapshot 路径不做模型名白名单——已保存的下线模型名仍可保存不被拒，灰置仅做展示引导（与本裁定不藏语义匹配）。
- V2 `frontend/src/pages/Settings/ModelSettings.tsx` + `types/api.ts` + `styles/app.css`；V1 `frontend/app.js` + `app.css`（同款渲染、`esc()` 转义从无信任注入）。CSS 类命名私有。

## 四、验证证据链
- 后端：pytest tests/test_model_settings.py tests/test_user_configuration.py tests/test_user_model_connections.py = 49 passed；umc 单独套件 33 passed。
- V2 前端：vitest 全量 27/27（含新增 3 例）；npm run build 绿（9.56s，含 typecheck）。
- 截图 ×2 实拍（本报告附路径）。
- 出口：git 仅新增/修改业务文件，package.json/lock 未动（依赖增扰 0）。

## 五、如实边界
- 「我方验证可用」=代码路径连通性（test_connection 由用户自测），无法代替真实凭据调用；本机零凭据，未做真实模型连通性实测——这是按裁定政策的名录刷新而非可用性认证。
- qwen-turbo 与 glm-4.5 两杠已无硬停用证据，note 均已用对冲/建议措辞如实标注（质检⚠️ 项，已闭环措辞）。
