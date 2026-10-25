# FundLex Frontend V2 进度

日期：2026-10-25
分支：`feat/frontend-v2-final`

状态只能为：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`DONE`、`VERIFIED`。

| Workstream | Status | Evidence / next action |
|---|---|---|
| Baseline and scope isolation | IN_PROGRESS | HEAD `f59c452`; current branch `refactor/backend-engine-finalization`; dirty engine/docs/evidence preserved |
| Frontend parity audit | IN_PROGRESS | React route map and current Compare capability matrix migrated; full independent acceptance remains open |
| P0 Review safety | IN_PROGRESS | Button now disabled while pending; runtime gate retained; draft persistence keyed by revision payload |
| 401/auth lifecycle | IN_PROGRESS | Query, mutation, upload and download 401 now emit one session-expired event; auth/query/workspace clear follows |
| Server state migration | IN_PROGRESS | TanStack Query 5 provider, typed keys, polling, QueryClient invalidation, shared mutation wrappers, and 9 Vitest/RTL/axe tests are implemented; real environment remains open |
| Tasks and filters | IN_PROGRESS | Task summary now exposes aggregate phase/downloadable count; CSV uses the same tab/status filters; API/browser regression passes |
| New Task upload/recovery | IN_PROGRESS | Multi-file/chunk/recovery remains in React and upload/seal now use mutation wrappers; real Worker delivery remains open |
| Task/Document detail | IN_PROGRESS | ZIP gate follows task downloadable artifact count; incomplete/unresolved visibility retained; real artifact verification remains open |
| Review workspace | IN_PROGRESS | pending-first, revision-keyed drafts, mutation submission, and bidirectional mobile pane focus implemented; 390px browser flow now passes, real selected artifact remains open |
| Compare React migration | IN_PROGRESS | `/compare` is a React Router page; multi-pair/folder pairing, recovery, polling, pair/diff navigation, safe rendering, connectors, mobile panes, and report download migrated; fixture browser parity passes, real worker evidence remains |
| Guides/Settings/Users | IN_PROGRESS | Existing routes/API; guide mutations now use shared wrappers; password/accessibility evidence remains |
| Design system/CSS | IN_PROGRESS | Shared tokens/UI remain; Compare styles added; duplicate global definitions and broader visual audit remain |
| Responsive/accessibility | IN_PROGRESS | Component axe/regression checks plus 390px Review/Compare browser checks and help focus evidence pass; broader independent visual/axe audit remains open |
| Frontend automated tests | IN_PROGRESS | Vitest/RTL/axe 4 files / 9 tests pass; `typecheck`, `lint`, `build`, 8 React browser tests, and 17 Compare API/Worker/Auth regressions pass |
| Test environment integration | BLOCKED | Requirements doc to create; full-stack real gate currently unavailable/0 of 20 |
| Independent acceptance | BLOCKED | React/API gates pass; real Full-Stack Test Environment remains 0/20 in current snapshot and cannot be replaced by browser/fixture evidence |

## 2026-10-25 implementation evidence

- React Compare was added at `frontend/src/pages/Compare/ComparePage.tsx`, registered at `/compare`, and linked through `AppShell`; FastAPI `/compare` now serves the React entry for deep-link refresh.
- Compare uses `/api/compare/*` through the shared client, preserving paired uploads, folder matching, resumable uploads, sealing, task polling, pair selection, result coverage warnings, diff type filtering, stable diff IDs, keyboard focus, scroll synchronization, SVG connectors, mobile side switching, and JSON report download. Server-rendered HTML is parsed through an inert allow-list.
- Shared mutation wrappers in `frontend/src/api/hooks.ts` now cover task upload/seal/control, Review decisions, guide enable/upload/parse, and Compare create/upload/seal. Success handlers invalidate related TanStack Query keys; 401 handling remains centralized in `frontend/src/api/client.ts`.
- Component and accessibility coverage includes Review pending/generation gating and revision-fingerprint draft invalidation, bidirectional SplitPane mobile switching, Compare diff keyboard activation and safe markup filtering, help-dialog Escape/focus return, API 401 event handling, DocumentViewer allow-list rendering, and jsdom axe smoke checks. `frontend/tests/` contains 4 files / 9 passing tests.
- The help dialog now moves focus to its close control, closes on Escape or backdrop/close actions, and returns focus to its trigger. SplitPane mobile controls expose `role="tab"`; the Button primitive forwards refs for focus management.
- Verification after serial `npm ci --ignore-scripts --no-audit --no-fund`: `npm test -- --reporter=dot` (4 files / 9 passed); `npm run typecheck`; `npm run lint`; `npm run build`; `FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q` (**8 passed**, including 390px Review and fixture-backed Compare result navigation); `.venv/bin/python -m pytest tests/test_compare_api.py tests/test_compare_auth.py tests/test_compare_worker.py -q` (**17 passed**); `git diff --check` passed. A concurrent install and test run produced transient missing `node_modules` files; it is invalid evidence and recorded as FL-D247. React Compare now includes previous/next pair navigation; this parity gap and its verification boundary are recorded as FL-D248.
