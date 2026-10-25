# FundLex Frontend V2 审计日志

## Round 1 — 2026-10-25 — Baseline / architecture / review / test evidence

### Scope

Git baseline、`frontend/src`、legacy `frontend/app.js`/`compare.js`、FastAPI API、Compare API、browser tests、Compare E2E 和已有 parity/交接证据。

### Findings

1. 当前 HEAD 为 `f59c452`，分支原为 `refactor/backend-engine-finalization`；已创建 `feat/frontend-v2-final`。工作区有用户已有未跟踪 `docs/evidence/final-validation-20261022/`，保留。
2. React V2 已具备 Tasks/New Task/Task Detail/Document Detail/Review/Guides/Settings/Users、真实 API、上传恢复和 DocumentViewer allow-list，但 query 层仍是 `frontend/src/api/hooks.ts` 的自研 Map cache。
3. `@tanstack/react-query` 尚未安装；workspace Zustand store 当前无消费者。
4. mutation、upload、download 的 401 只变成错误，未统一清 auth/query/workspace 并回登录。
5. Review runtime 会阻止 pending 生成，但按钮未在 pending 时 disabled；决策草稿只存在内存；移动端目标定位不会自动切 pane。
6. `/compare` 当前由 React shell 原生链接进入 FastAPI 返回的 `frontend/compare.html`，不是 React route。
7. Task Detail ZIP 按 `status === completed` 才启用，较后端/原版的“有可下载结果即可”更严格。
8. React browser test 是真实临时 FastAPI + SQLite，但不启动普通 Worker/model；legacy test 大量 route/DB fixture；Compare E2E 使用真实 CompareWorker/算法但无模型和生产服务。
9. 当前交接明确真实普通业务 gate 仍阻断：snapshot-19 D01–D20 为 0/20；D06 有真实 Worker/model/artifact 证据但 delivery incomplete。

### Priority

1、4、5、7 为 P1/P0 业务正确性或安全回归风险；2、3、6 为架构收敛项；8、9 为证据边界和外部阻塞。

### Evidence

- `frontend/src/api/hooks.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/Review/ReviewPage.tsx`
- `frontend/src/pages/TaskDetail/index.tsx`, `frontend/src/components/layout/AppShell.tsx`
- `tests/browser/test_frontend_v2.py`, `tests/browser/test_workbench.py`, `tools/evaluation/compare_e2e.py`
- `docs/FRONTEND_V2_PARITY_MATRIX.md`, `docs/ACTIVE_HANDOFF.md`

### Fix

本轮先实现 Review pending UI、draft persistence、统一 401 事件和下载条件回归；随后迁移 TanStack Query、React Compare 和测试层。

### Retest

待实现后执行 typecheck/lint/build、前端单测/组件测、browser、Compare、人工视觉和 Full-Stack Test Environment。当前不标记已验证。

## Round 2+

后续每个阶段追加固定字段：Scope、Findings、Priority、Evidence、Fix、Retest，并保留历史结论。

## Round 2 — 2026-10-25 — First correctness batch

### Scope

API session expiry, Review draft and pending behavior, mobile pane focus, task aggregate phase, ZIP eligibility, and CSV filter parity.

### Findings

1. Shared `request` already converted HTTP 401 to `SessionExpiredError`, but upload XHR and the download/text/mutation callers had no common state-clearing event.
2. Review decisions were only held in component memory; the selected-artifact button remained enabled while revisions were pending.
3. Mobile Review focus callbacks did not control the visible pane, and task phase/ZIP availability were derived from current page data or task status.

### Priority

P0/P1 correctness and session-safety regression risks.

### Evidence

`frontend/src/api/client.ts`, `frontend/src/pages/Review/ReviewPage.tsx`, `frontend/src/components/document/SplitPane.tsx`, `frontend/src/pages/TaskDetail/index.tsx`, and `fundlex/tasks.py`.

### Fix

401 responses now emit `fundlex:session-expired`; auth, query cache, workspace state and login routing clear through the existing auth events. Review drafts are stored under user/task/document/revision-fingerprint keys, pending disables generation, and focus changes the mobile pane in both directions. Task summaries now include an aggregate phase and downloadable artifact count; CSV exports reuse the active tab/status filters.

### Retest

`frontend`: `npm run typecheck`, `npm run lint`, and `npm run build` passed. `tests/test_tasks_api.py`: 27 passed. Full browser and real Full-Stack Test Environment gates remain outstanding; this round does not change the blocked status of the real delivery gate.

## Round 3 — 2026-10-25 — TanStack Query migration

### Scope

React server-state cache, polling, query invalidation, and auth lifecycle cleanup.

### Findings

The custom Map/in-flight cache had no standard query identity or mutation invalidation semantics. It also made cache clearing a separate event-driven concern from the rest of the API state.

### Priority

P1 architecture and consistency risk.

### Evidence

`frontend/src/api/hooks.ts` previously owned the Map cache; `frontend/src/api/queryClient.ts`, `frontend/src/main.tsx`, and `frontend/package.json` now contain the TanStack Query 5 setup.

### Fix

All existing server-state hooks now use TanStack Query 5 with stable key factories, polling through `refetchInterval`, disabled automatic retries, and a shared QueryClient. Existing page-facing `data/loading/error/refreshing/refetch` contracts remain stable. Auth-cleared, auth-changed, and session-expired events clear the QueryClient. Prefix invalidation calls were mapped to structured keys.

### Retest

`npm run typecheck`, `npm run lint`, `npm run build`, `FUNDLEX_BROWSER_TESTS=1 pytest tests/browser/test_frontend_v2.py -q` (7 passed), and `pytest tests/test_tasks_api.py -q` (27 passed). Mutation-specific hook extraction and real Full-Stack Test Environment validation remained outstanding at this point in the historical log.

## Round 4 — 2026-10-25 — React Compare route and mutation integration

### Scope

React Compare migration, `/compare` deep-link serving, Compare capability preservation, and TanStack Query mutation adoption.

### Findings

1. The React shell still opened the legacy Compare HTML page, so Compare was outside the React route and shared session/query lifecycle.
2. Compare output HTML contains backend stable diff/block attributes; rendering it as unrestricted HTML would bypass the existing document security boundary.
3. Defining mutation wrappers without using them would leave upload, Review, guide, task control, and Compare invalidation semantics split across pages.

### Priority

P1 route parity, security boundary, and server-state consistency.

### Evidence

`frontend/compare.js`, `frontend/compare.html`, `fundlex/compare/api.py`, `fundlex/compare/render.py`, `frontend/src/pages/Compare/ComparePage.tsx`, `frontend/src/api/hooks.ts`, `fundlex/api.py`, and `tests/browser/test_frontend_v2.py`.

### Fix

Added the React `/compare` route and changed the FastAPI `/compare` entry to serve the React application for refresh/deep-link behavior. Migrated multi-pair upload, folder matching, resumable upload, sealing, polling, pair selection, coverage/error states, diff navigation/filtering, stable-ID navigation, synchronized panes, SVG connectors, mobile side switching, keyboard activation, and JSON report download. Compare markup is parsed through an inert tag/attribute allow-list. Added shared mutation wrappers and connected them to task uploads/seal/control, Review decisions, guide operations, and Compare operations.

### Retest

`npm run typecheck`, `npm run lint`, `npm run build` passed; `FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` passed (7); `.venv/bin/python -m pytest tests/test_compare_api.py tests/test_compare_auth.py tests/test_tasks_api.py tests/test_guide_api.py -q` passed (39); `git diff --check` passed. This evidence covers React/API and browser integration only. It does not establish real ordinary Worker/model/DOCX delivery or Full-Stack Test Environment acceptance.

## Round 5 — 2026-10-25 — Component, responsive, and accessibility regression layer

### Scope

Review pending and draft invalidation behavior, mobile SplitPane switching, Compare diff keyboard/sanitization behavior, help-dialog focus lifecycle, and reproducible frontend dependency installation.

### Findings

1. Existing shell coverage needed direct component evidence for the pending-first Review gate and revision-fingerprint draft boundary.
2. SplitPane mobile controls exposed a tablist container but its controls lacked explicit tab roles.
3. The help dialog had dialog semantics but no focus transfer, Escape close, or focus return lifecycle.
4. Running `npm ci` concurrently with tests/builds can temporarily remove dependency files and produce invalid missing-module failures.

### Priority

P0 Review safety, P1 responsive keyboard behavior and accessibility, and validation reproducibility.

### Evidence

`frontend/tests/review.test.tsx`, `frontend/tests/components.test.tsx`, `frontend/tests/client.test.ts`, `frontend/tests/documentViewer.test.tsx`, `frontend/src/pages/Review/ReviewPage.tsx`, `frontend/src/components/document/SplitPane.tsx`, `frontend/src/components/layout/AppShell.tsx`, `frontend/src/components/ui/Button.tsx`, and `frontend/package-lock.json`.

### Fix

Added 5 component regressions covering pending generation blocking, changed revision fingerprint draft invalidation, bidirectional pane switching, Compare diff keyboard activation with unsafe markup removal, and help-dialog Escape/focus return. Added `role="tab"` to SplitPane controls. Made Button ref-capable and implemented help-dialog focus transfer, Escape close, backdrop/close handling, and trigger focus return.

### Retest

After serial `npm ci --ignore-scripts --no-audit --no-fund`: Vitest **4 files / 9 passed**, `npm run typecheck`, `npm run lint`, `npm run build`, React browser **7 passed**, focused API **39 passed**, and `git diff --check` passed. This improves regression evidence but does not establish full accessibility, visual, responsive, real Compare-worker, or ordinary Worker/model/DOCX delivery acceptance. The concurrent-install transient failure is recorded as FL-D247.
