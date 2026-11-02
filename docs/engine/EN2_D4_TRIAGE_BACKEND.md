# EN2 · D4 移交件分级处置提案：FL-D900~906（2026-11-02 · 抹树事故重做）

- 对象：主线 `docs/backend/BACKEND_AUDIT_20261101.md` + `DETAIL_APPEND_BACKEND.md`（W3 移交，原 qa-backend-audit 基线 8b5467b）。证据点均在本树逐一 grep 实证复核。
- 分级口径沿用本线三阶：**A 可安全直接修**（死代码/注释/日志/零行为变化）/ **B 需主线裁决**（行为或语义变更、跨线联动）/ **C 需用户裁决**（产品语义）。
- 范围澄清：FL-D905 在主文档为「正向结论非问题」占位行（L8674），同号在 GG 线又作前端施工项使用——**号段冲突报主线归并**，本批按 W3 报告实义（900~904、906）处置。
- 重做说明：本文件替代丢失的 528a364，内容与证据点一致（已逐点复核现行树）。

## A（可安全直接修，4 项）

| 编号 | 位置 | 修法一句 |
| --- | --- | --- |
| FL-D900 | fundlex/api.py:1413 `reasons` 字面量 | 删该 dict 定义——grep 全仓零引用（现行走 `exc.code` 路径），纯死代码 |
| FL-D902 | fundlex/guide_store.py canary/block_report 两 except: pass | 两 except 分支各加 `log.warning("... error=%s", type(exc).__name__)`；崩溃语义已被 FL-D923 sentinel 覆盖，本条只剩可观测性缺口，日志只记类型名不入用户面 |
| FL-D903a | fundlex/integrations/feishu/service.py:834 起 discard_draft_files ×3 | except: pass → log.warning 记类型名与草稿消息 ID |
| FL-D903b | fundlex/integrations/store.py:449/606 add_draft_file/add_outbox `except: return False` | return False 前加 log.warning 记类型名与资源键（不带 payload） |

> O-05（service.py sync_tasks `except: continue` 无日志，W3 已并入 FL-D903 附记）可随 A 一起顺手改，不另起卡。

## B（需主线裁决，4 项）

| 编号 | 位置 | 修法一句 | 风险与为何上裁 |
| --- | --- | --- | --- |
| FL-D901 | api.py:1269/1277/1279 模型设置 422 | 按 FL-D925 已裁定口径（后端产中文案+code 附注、前端只按 code 映射）把该路由的中文指引从信封泛化里救出——detail 升格为机读 code+中文 message，前端无需改 | 行为（用户可见错误文案）+需与 FE 错误展示契约一致 |
| FL-D904 | api.py:1065 feishu_health `__import__` 单例假探活 | 换真活跃位：feishu runtime 导出进程级活跃注册（service_main/runtime 各注册一次），health 读注册位；上线前先给运维确认监控系统有否消费 `service_process_active` 的现有语义 | 运维契约变更，消费确认先行 |
| FL-D906a | feishu/events.py on_message 主派发 | service.handle_message_event 之前加「该 app 运行时活跃位」核对——不活跃即回单机 ACK + log（runtime._seen 对 onboarding 面已门控，本条只补 service 面） | 行为（离线应用事件从静默通过变显式弃置） |
| FL-D906b | feishu/runtime.py:_close_socket `_disconnect` 私有调用 | 补兜底链：缺失 `_disconnect` 时按「强制结束 task + 标注 reconnect」下落，不把 socket 悬在原 reconnect loop | 私有 API 面变化，重度依赖 lark SDK 版本，需清晰回归 |

## C（需用户裁决，1 项）

| 编号 | 位置 | 修法一句 |
| --- | --- | --- |
| O-02（W3 观察项，建议申请正号） | onboarding 绑定码 | 要不要给 12 位绑定码加独立尝试限速（当前仅依赖 600s TTL+恒时比较+飞书消息送达关卡），限速器会额外影响真实绑定重试 UX——产品语义拍板 |

## 附序建议

A 批先行随下一波任何 PR；B 批按序 FL-D901→906a→906b→904（可行性递减）；C 随用户下一轮。若批准施工，本线沿用判词号逐件 commit+定向测试，收口一号回归+双盲质检+完工报告断言表（与 B 类 14 件同款纪律）。
