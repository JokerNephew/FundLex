# EN2 · D4 移交件分级处置提案：FL-D900~906（2026-11-02）

- 对象：主线 `docs/backend/BACKEND_AUDIT_20261101.md` + `DETAIL_APPEND_BACKEND.md`（W3 移交，plaqa-backend-audit 基线 8b5467b）。证据点均在本树 a96f118+ 逐一 grep 实丝复核。分级口径沿用本线三阶：
  - **A 可安全直接修**（死代码/注释/日志/零行为变化的帮工件）；
  - **B 需主线裁决**（行为/语义变更，含跨线联动）；
  - **C 需用户裁决**（产品语义）。
- 范围澄清：FL-D905 在主文档为「正向结论非问题」占位行（L8674），同号在 GG 线又作前端施工项用过——**号段冲突报主线归并**，本批按 W3 报告实义（900~904、906）处置。

## A（可安全直接修，4 项）

| 编号 | 位置 | 修法一句 |
| --- | --- | --- |
| FL-D900 | fundlex/api.py:1413 `reasons` 字面量 | 删该 dict 定义——grep 全仓零引用（现行错 `exc.code` 路径），纯死代码 |
| FL-D902 | fundlex/guide_store.py canary/block_report 两 except: pass | 两个 except 分支各加 `log.warning("... error=%s", type(exc).__name__)`；崩溃语义已被 FL-D923 sentinel 覆盖，本条只剩可观测性缺口，日志只记类型名不入 users 面 |
| FL-D903a | fundlex/integrations/feishu/service.py:834 起 discard_draft_files ×3 | except: pass → log.warning 记类型名（草稿消息 ID） |
| FL-D903b | fundlex/integrations/store.py:449/606 add_draft_file/add_outbox `except: return False` | return False 前加 log.warning 记类型名与资源键（不带 payload） |

> O-05（service.py sync_tasks `except: continue` 无日志，W3 已并入 FL-D903 附记）可随 A 一起顺手改，不另起卡。

## B（需主线裁决，4 项）

| 编号 | 位置 | 修法一句 | 风险与为何上裁 |
| --- | --- | --- | --- |
| FL-D901 | api.py:1269/1277/1279 模型设置 422 | 按 FL-D925 裁定口径（后端产中文案+code附注维度，前端只按 code 映射）把该路由的中文指引从信封泛化里救出——把 detail 升格为机读 code+中文 message，前端无需改 | 行为（用户可见错误文案）+需与 FE 错误展示契约一致 |
| FL-D904 | api.py:1065 feishu_health `__import__` 单例假探活 | 换真活跃位：feishu runtime 导出进程级活跃注册（service_main/runtime 各注册一次），health 读注册位；上线前先给运维确认监控系统有否消费 `service_process_active` 的现有语义 | 运维契约变更，消费确认先行 |
| FL-D906a | feishu/events.py on_message 主派发 | service.handle_message_event 之前加「该 app 运行时活跃位」核对——不活跃即回到单机 ACK + log（runtime._seen 对 onboarding 面已门控，本条只补 service 面） | 行为（离线应用事件从静默通过变显式弃置） |
| FL-D906b | feishu/runtime.py:_close_socket `_disconnect` 私有调用 | 补兜底链：缺失 `_disconnect` 时按「强制结束 task + 标注 reconnect」下落，不把 socket 悬在原 reconnect loop | 私有 API 面变化，重度依赖 lark SDK 版本需 2B 测试 |

## C（需用户裁决，1 项）

| 编号 | 位置 | 修法一句 |
| --- | --- | --- |
| O-02（W3 观察项，建议申请正号） | onboarding 绑定码 | 要不要给 12 位绑定码加自 Try 限速（当前只仅靠 600s TTL+恒时比较+飞书消息送关卡），限速器会额外影响真实绑定的重试 UX——产品语义拍板 |

## 附言

- 全文未含 A/B/C 空档：FL-D905 依上文号段冲突处理（主文档为正向后占位、GG 有施工性 FL-D905，请主线分配新号给 GG 侧一项）。
- 序建议：A 批先行随下一波任何 PR；B 批按序 FL-D901→906a→906b→904（可行性递增委拖）；C 随用户下一轮。
- 若 A/B 批准走同一施工令，本线沿用判词号施工、每随—commit+定向测试，收口一遍全回归+双盲质检+完工报告断言表（与 B 类 14 件同款纪律）。
