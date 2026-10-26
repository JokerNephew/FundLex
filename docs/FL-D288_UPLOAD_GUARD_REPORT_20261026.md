# FL-D288 上传资源门禁实施与隔离测试报告

日期：2026-10-26  
范围：普通任务、Compare 和自定义指引的 multipart 上传入口。测试使用本地临时数据目录和受控小阈值；没有修改生产 Nginx、没有生产压力测试、没有新增模型调用。

## 实施

- `fundlex/upload_guard.py` 增加 ASGI 请求门禁：Content-Length 预检、无 Content-Length 时的早期累计字节预算、每 IP 和全局并发、每 IP 分钟窗口限流、单次接收超时、整体请求超时和最低接收速率。
- 同一模块替换 Starlette multipart parser 的引用，限制总 part 数、字段数、字段大小、part header 数量和 header 字节数；路由继续在解析后执行既有文件数门禁。解析器超限时由 Starlette 关闭已创建的临时文件。
- 普通任务、Compare 和指引路由在成功、业务错误、累计预算超限和验证异常后显式关闭 `UploadFile`，避免临时对象残留；原有 DOCX ZIP 成员、加密、重复成员、单 part、展开总量和压缩比检查保留。
- `tools/deploy/nginx-upload-limits.conf.template` 提供 `client_max_body_size`、请求/代理超时、`limit_req` 和 `limit_conn` 模板。部署时需将 zone 放到 `http{}`，location 放到 FundLex `server{}`，并和 EnvironmentFile 同步。

默认应用门禁：请求 52 MiB（指引 26 MiB）、单 IP 并发 2、全局并发 8、每 IP 12/min 加 burst 4、接收间隔 30s、整体 180s、最低速率 1024 B/s（前 5s grace）、20 文件、32 parts（安装时至少为文件上限加字段上限）、8 fields、每 part header 16 KiB/16 个。

## 受控验证

测试文件：`tests/test_upload_guard.py`。验证内容：

| 场景 | 结果 | 说明 |
|---|---|---|
| Content-Length 超出请求预算 | 通过 | 在进入表单解析和认证路由前返回 413，并返回 `UPLOAD_REQUEST_SIZE_LIMIT` |
| chunked/无 Content-Length 累计超限 | 通过 | ASGI receive 读到预算边界即停止；不等待后续 body |
| 缺失 boundary / 畸形 multipart | 通过 | 返回 400；应用不会创建任务上传对象 |
| multipart part/header/field 数量或大小超限 | 通过 | 解析阶段拒绝；未进入 DOCX 验证和对象写入 |
| 超过批次累计文件预算 | 通过 | 普通任务和 Compare 均在继续读取前返回 413；原有 ZIP 校验未关闭 |
| 慢上传、整体超时和低速流 | 通过 | 使用短测试阈值，返回 408；未执行 Worker |
| 并发/每 IP 限流 | 通过 | 使用阻塞 ASGI app 的两个受控请求，第二个返回 429，释放后可再次请求 |
| 超限后的临时对象清理 | 通过 | 解析器异常关闭已创建 spool 文件，路由 finally 关闭每个 `UploadFile` |

命令和结果：

```text
python -m pytest tests/test_upload_guard.py tests/test_tasks_api.py::test_manifest_segmented_upload_idempotency_and_refresh tests/test_compare_api.py::test_compare_api_roundtrip_and_xss -q
python -m compileall -q fundlex
```

实际结果：`tests/test_upload_guard.py` **9 passed**；`tests/test_tasks_api.py tests/test_compare_api.py tests/test_guide_api.py` **38 passed**（合计 47 passed，2 个既有依赖弃用 warning）。`compileall` 和 `git diff --check` 通过。该报告只描述受控资源门禁验收，不能作为生产容量或压力承诺。生产发布前应先在隔离测试服务应用模板，检查 Nginx `limit_req`/`limit_conn` 命中行为、systemd 环境变量和服务重启后的实际值。
