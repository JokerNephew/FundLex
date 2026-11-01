# 后端普查附录（DETAIL_APPEND_BACKEND）

> 主报告：`BACKEND_AUDIT_20261101.md`。本附录存可复算的原始证据与逐处定性，供复核与二次审计。

## A. AST 吞错 38 处逐处定性（来源 `/tmp/opencode/audit/swallows.txt`）

| # | 位置 | 模式 | 定性 |
| --- | --- | --- | --- |
| 1 | api.py:1033 | consume_oauth_state 取消授权路径 | OK：双消费保障显式，失败即已消费过 |
| 2 | api.py:1679 | 批量统计单份报告 NotFound | OK：边界统计（FL-D652 在册语义） |
| 3 | auth.py:458 | bootstrap_admin 用户已存在 → _recover | OK：恢复路径，竞态注释在码 |
| 4 | jobs.py:226/239 | unlink OSError / rmtree 返空 | OK：目录锁清理 best-effort+幂等故意 |
| 5 | jobs.py:260 | job_names 读失败 | OK：并发 reaper 间隙，环不完整是设计 |
| 6 | jobs.py:313 | gateway close | OK：清理不掩 job 结果（注释） |
| 7 | jobs.py:569 | review stamp advisory | OK：注释明示 advisory |
| 8 | store.py:885 | 孤儿对象 unlink OSError | OK：DB 权威注释在码 |
| 9 | upload_validation.py:95 | 部件 XML 解析失败跳过 | OK：该部件不参与判定，fail-closed 在别处 |
| 10 | retention.py:142/144/149 | StopIteration/OSError | OK：清理 best-effort |
| 11 | observability.py:182 | Langfuse gen.end | OK：外层 warning 已记 |
| 12 | trace_sink.py:154/167 | 本地磁盘满 etc | OK：兜底策略「带问题继续」注释在码 |
| 13 | proxy_headers.py:29 | 畸形 CIDR 跳过 | OK：注释「绝不扩信任集」 |
| 14 | integrations/store.py:292/501 | 清理 unlink OSError | OK：草稿清理 best-effort |
| 15 | feishu/oauth.py:127 | qrencode 不可用 → 无二维码 | OK：QR 是表现层非绑定前提（注释） |
| 16 | feishu/events.py:77 | tenant_token 尽力获取 | OK：失败不影响事件处理 |
| 17 | feishu/service.py:605/895 等 | update_card 失败 → 新发卡片 | OK：回退路径显式 |
| 18 | feishu/service.py:834 | discard_draft_files | **FL-D903**（方向对、零日志） |
| 19 | guide_store.py:221/233 | canary/block_report | **FL-D902**（方向对、零日志） |
| 20 | html_view.py:162/398/465 | 渲染容错/int 转换 | OK |
| 21 | onboarding.py:137 | int(payload.code) | OK：防御性解析 |
| 22 | user_model_connections.py:183/195/210 | GC 保守路径 | OK：「宁可留密文不误删」注释在码 |

## B. 安全模式专项核查记录

| 模式 | 命令口径 | 结果 |
| --- | --- | --- |
| SQL 拼接 | `grep -rnE 'execute\(f["\']'` 全库 | 7 处全部为：列名白名单（auth.py:213 column∈{'id','username'}）、DDL 迁移（store.py:567/573/580、guide_store:112/115）、占位符串 `(?,?,?)`（store.py:695/704/1188）——**无值拼接** |
| subprocess | 全库 | oauth.py:123 qrencode（参数数组、固定参数、无 shell）；stage_replay git（测试工具） |
| os.system/popen/eval/exec | AST 扫描 | **零命中** |
| 硬编码密钥 | `grep -rniE "(password|secret|token|api_key)=['\"]..."` 排除 env/test | **零命中** |
| 路径拼接回传 | FileResponse/StaticFiles 全部调用点 | 仅 guide_source（库 ID→系统路径，visible_guide 先鉴权）；下载走 read_artifact 读字节 |
| pickle/yaml.load 不定时炸弹 | 复扫 | api.py:770,775 系**自有命名类** DeserializationErrorMixin（非反序列化漏洞），guide_store.py:1025 候选复核为误报 |

## C. 前后端错误契约核对（FL-D901 定案链）

1. `api_errors.code_from_detail`：detail 仅当匹配 `^[A-Z0-9_]+$` 才作码，否则按状态码泛化（422→INVALID_REQUEST）。
2. `api.py:572 api_error_response`：`message=message_for(status)`（固定中文通用句）、`detail=code`。
3. 前端 `api()`（app.js:76）：`reasons[detail] || messages[status] || reason(detail) || 兜底`。
4. 前端 `reasons` 表无 `INVALID_REQUEST`/`MODEL_SETTINGS_INVALID` 条目 → 落 `messages[422]`=「请求或文件无法处理。」。
5. 对照：api.py:1269/1277/1279 作者意图文案「模型配置无法保存，请检查供应商、模型和访问密钥。」不可达。

## D. 澄清记录（初筛疑点后复核排除）

| 疑点 | 复核结论 |
| --- | --- |
| store.py:690-940 出现 39 行 `VALUES (?)` 单占位符 | 全是 INSERT OR IGNORE/UPDATE 状态写，条件全绑定——无问题 |
| check_publish_drift.sh「set +euo」 | 初筛误读，实为 `set -euo pipefail`，脚本只读且退出码语义清晰 |
| api.py 批量统计 N+1（每文档 get_report） | metrics 已按需加载+分页 200 上限，非热路径，不改 |
| api.py:1410 zip 校验前 `await upload.read(MAX+1)` | 有字节上限，内存不爆；total 超限标记 error_code 不中止——接收语义有意 |

## E. 五 worker systemd 硬化清单（全部模板核对）

- 共有：User=fundlex、EnvironmentFile=/etc/fundlex-recall.env、Restart=always、NoNewPrivileges/PrivateTmp/ProtectHome/ProtectSystem=strict、ReadWritePaths=/var/lib/fundlex、UMask=0077。
- 差异：recall-api uvicorn --workers 2（throttle 跨 worker 共享表已配套，R2-F01 在码）；feishu 晚启依赖（service_main 挂载 onboarding+runtime，生产核实 active）。
