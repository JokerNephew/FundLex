# 规则组选择「可见即所得」规格（2026-11-01，项 3 / FL-D730，前端主线+后端）

> 用户痛点：规则选择了只有编号+章节，根本不知道每条规则要求改什么。必须让用户在勾选之前就**看到这条规则的人读内容**（要求/将执行的修改），并能点开看详情；已选/未选视觉一目了然。

## 一、数据与后端（前端主线实施）

`GET /api/guides/{version_id}/rule-settings` 的 `rules[]` 现在只有 `rule_id/title/section_hint/enabled`。**向后兼容地增字段**（不改既有 key 语义）：

```jsonc
{
  "rule_id": "G01",
  "title": "释义-基金份额类别定义：",
  "section_hint": "释义",
  "enabled": true,
  "requirement": "在释义的基金份额类别定义原条款后增加新条款，明确…（完整人读要求）",
  "operations": [                      // 化简后的操作摘要（人读），最多 4 条
    { "label": "新增 3 处", "detail": "投资者通过直销机构…（前 80 字）" }
  ]
}
```

- `requirement` 取指引文档 `rules[].requirement` 全值（已是中文人读文本）；无该字段时给 `title` 兜底，不给英文。
- `operations` 摘要由后端从 `rules[].operations` 生成：按 op 类型聚合（append=新增 / replace=修改 / delete=删除 / move=移动 / other=调整），detail 取第一条 op 的 `new_text`/`old_text` 80 字截断；全空时 `operations: []`。
- 若文档结构改变导致字段缺失，必须退回安全值（requirement=titie，operations=[]），不 500。
- V1 的 `renderGuidePanel`、`rules_overview` 数据源改为读同一接口的 `rules[]`（前端 join），不再依赖 `rules_overview[].operations` 的聚合。
- 回归：`tests/test_guides*`、`tests/browser/test_guide_*` 全绿；`GUIDE_RULES_ALL_DISABLED`/`GUIDE_RULE_UNKNOWN` 契约不变。

## 二、页面交互（V1/V2 同构，规则列表页）

当前视图（两岸一致）：
```
[卡片] 规则组
  头部：<h3>规则组 + 「共 N 条 · 已启用 X / N」+ 操作 [全选|全不选|保存启停]
  说明一句：关闭的规则不会在之后新建的任务中执行，并会在报告里列为“用户关闭的规则”。
  主体（按 group 分组渲染，组头 = section_hint；同组规则按 rule_id 序）：
    [行] ☑ | 🔵规则 G01·<title> | <章节 tag> | [已启用 pill]
         > 展开人读详情（<details>/<summary 样式=项目统一 advanced-details）
           - requirement 全文（13px 正文）
           - operations 摘要列表（label pill + detail 一行 80 字…）
           - （无 requirement 时显示 title 全文 + 「详细修改见条规条款」）
  关闭的行（disabled）：
    - 底色 `--warning-soft` 1px 边 + `已关闭` pill（warning 系）；
    - 标题带删除线；requirement/详情仍可展开预览（不做 disabled）；
    - checkbox 映射 enabled=false。
  页脚：保存按钮 disabled 时 title 提示「至少保留一条启用规则」（后端 GUIDE_RULES_ALL_DISABLED 前置校验）。
```

- 勾选框 aria-label 维持「启用规则 {rule_id}」保浏览器锚点；Visually 该 checkbox 居中且点击区不小于 44×44。
- 「规则 G01」pill + 章节 tag 与当前 V2 `.ui-tag` 同系；人读详情使用与本仓 advanced-details 同款 summary/虚线分隔。
- 展开详情**不阻塞批量操作**：行内 checkbox/按钮在任何展开态都可达。
- 空态：指引未解析/无规则组 →「指引解析完成后才能配置规则组」；有规则但无 requirement → 落 title 兜底（不出现英文或空行）。

## 三、V1/V2 分工（实施各自域；前端主线验收一致性）

- **后端（前端主线）**：扩 `fundlex/guide_store.py::rule_settings` 与 API 文档（含退化兜底）；python 侧补单元测试覆盖 requirement/operations 聚合与空值兜底；不动路由与鉴权。
- **V2 worker（81FirpsQ）**：Guides 规则组页按 §二重构（分组、人读详情、已选/未选视觉、操作排）；新增 `useGuideRules`（或复用 hooks）读增强后的 `rules[]`；保留保存逻辑与 422 处理；`<details>` 也要遵守 `.advanced-details` 样式。
- **V1 worker（ivRkf1jH）**：`renderGuidePanel` 删除 `rules_overview` 依赖，同样渲染 §二结构；与 V2 同文案/同徽标/同展开交互；保留 `data-guide-rule-save` 等 data-action 与 `#gg-*` 锚点。

## 四、验收（前端主线执行）

1. 用户视角走查：上传一版自定义指引 → 进规则组 → 不看报告能说出每条要求改什么、所属章节、已启用与否；切换勾选即见徽标/底色变化；保存后回来仍为当前值。
2. Playwright 截图两版同态：展开至少一条详情、关闭至少一条，徽标/pill/详情样式对比一致。
3. 真实 API 走查：`curl /api/guides/{id}/rule-settings` 返回 requirement+operations 字段且值与内置/自定义指引一致；无 requirement 字段的旧指引不 500、落 title 兜底。
4. 浏览器锚点：`aria-label="启用规则 G01"`、`保存启停` 按钮、`GUIDE_RULES_ALL_DISABLED` 提示、既有手册测试全绿。
5. 需求档案登记：新增 FL-D730 记录接口扩展 + FL-D731/732 关联。
EOF
