# Independent test/evidence review — code HEAD `ff4d7498`

- **Role:** independent TEST REVIEWER (read-only; no source/test/git edits, no live model or HTTP).
- **Runtime code:** `/home/opencode/fundlex-ff4d749` @ `ff4d7498b6c1aee72ba48686074d021fc7f84791` (clean worktree).
- **Evidence root:** `docs/evidence/final-validation-20261022/revalidation-ff4d7498`.
- **Branch:** `refactor/recovery-architecture`. Code is identical to the main repo at `387e334` (`git diff ff4d749 387e334 -- fundlex tests` is empty; `387e334` is docs-only).
- **Overall:** **CONDITIONAL PASS** — the listed test areas and artifacts validate at `ff4d749`, but the evidence bundle is not yet self-consistent/complete. Two evidence blockers are open (stale `index.json`, D16 plan-stage mislabel).

## Area results

| Area | Result | Evidence |
|---|---|---|
| Offline pytest counts | **PASS** | `logs/pytest-ff4d749.txt:26` → `1061 passed, 6 skipped, 2 warnings in 207.10s`; 0 failed/error lines. HEAD collects **1067** tests = 1061 + 6 skipped. |
| compileall / diff-check | **PASS independent, PARTIAL as evidence** | `git diff --check` exit 0; in-memory compile of 135 `fundlex/`+`tests/` `.py` files OK. **No persisted ff4d749 compileall/diff-check log**, and `index.json` still cites the old 1024-test/682e68a run. |
| Full record→replay counts | **PASS** | All four summaries carry `head=ff4d749…`, `runtime_tree_sha256=7ad22dc0…`; record/replay completion counts are identical per case. Record HTTP 32/35/29/34; replay HTTP **0/0/0/0** (logical calls 39/35/29/45). |
| `compare_frozen_replay` | **PASS** | Re-ran `compare()` offline: D01/D02/D11/D16 `passed=true`, all 14 checks true, `http_attempts=0` each. Matches `summaries/full-replay-comparison.json` and log. |
| D16 six-stage replay | **PASS (same_head/no-network); FAIL (stage identity)** | All six `D16-stage-*.json`: `same_head=true`, `model_calls=0`, `replayed=true`; six-stage rerun with `httpx.Client.send` / `AsyncClient.send` / socket connect forced to raise succeeded. **However `D16-stage-plan.json` is plan revision 3, not the base `plan` boundary.** |
| Artifact review (all four) | **PASS** | `plan_artifact_mismatches=[]` for D01/D02/D11/D16. Redline: `accepted_matches_final=true`, `rejected_matches_original=true`. Independent re-projection from the actual redline DOCX confirmed accepted==final and rejected==original for all four (1363/1430/1405/1452 paragraphs). Independently applying the plan edits to each original also produced the final text with 0 mismatches (14/16/14/14 edits). Artifact and document SHA-256 fields match the files. |
| G02 negative cases | **PASS behavior; MISSING tests** | Direct offline replay at HEAD: expected `A类、D类` vs source `A类及D类` → PASS/`ALREADY_SATISFIED`; vs `A类及C类` → FAIL/`MISSING_EFFECT`; vs `A类、C类和D类` → FAIL/`MISSING_EFFECT`. No committed regression test asserts the two negative cases. |
| G05 heading vs real class setup | **PASS** | `operation_site_bound` (G05:2): generic heading false, summary heading false, meeting-exemption clause false, real class-setup clause true, already-absent real setup true. Tests `test_absent_inventory_placeholder_never_becomes_verified_operation_site` (12 params) and `test_absent_delete_target_at_real_class_setup_proves_verified_absent` pass. |
| G06/G16/G17 site guards | **PASS behavior; G16 test gap** | G06: real conversion clause true, generic business-rule clause false (`test_g06_site_guard_rejects_generic_business_rule_clause`, `test_g06_generic_business_adjustment_clause_is_not_a_delete_site`). G17: usage clause true, payment-only clause false (`test_sweep_drops_g17_payment_clause_as_wrong_business_site`). G16: accrual/payment paragraph true, heading/generic/payment-only false — behavior correct but no direct regression test of `target_site_ok("G16")`. |
| Duplicate semantic guard | **PASS** | `test_delete_scan_keeps_duplicate_sites_and_rejects_unrelated_filing` keeps both real class-setup copies but excludes the unrelated `信息披露计划并报中国证监会备案` paragraph. `test_operation_proof_requires_each_exact_source_duplicate` still requires every genuine duplicate site. |

## Targeted test runs (offline)

- `pytest tests/test_final_validation_regressions.py tests/test_recovery_final_invariants.py tests/test_g02_g04_occurrence.py tests/test_frozen_replay.py tests/test_missing_group_components.py tests/test_claim_replay_boundary.py -q` → **132 passed**.
- 34 selected G02/G05/G06/G16/G17/duplicate-guard tests → **34 passed**.

## Findings / blockers

### TR-01 (BLOCKER, HIGH) — `index.json` is stale and contradicts the summaries
`revalidation-ff4d7498/index.json` (mtime 07:53, before the runs) still records `offline.passed=1024`, `log=logs/pytest-682e68a.txt` (file absent), `replay_results` bound to `682e68a`, D01 `not_generated`, and `gate=FAIL` for old reasons. Current summaries are `ff4d749`, 1061 tests, D01 has an artifact. The authoritative index cannot be used to certify this bundle until regenerated.

### TR-02 (HIGH, evidence traceability) — D16 plan stage summary is revision 3, not base plan
`summaries/D16-stage-plan.json` (`stage="plan"`, no revision field) contains **14 edits / 40 ledger / 2 conflicts / cassette_replays=2**. Replaying the base `stages/plan.json` (input `existing_plan=null`, `dirty_locations=[]`) at HEAD deterministically gives **12 edits / 42 ledger / 4 conflicts / cassette_replays=3**. The saved value is byte-for-byte `replay_stage(..., "plan", revision=3)` (digest equal). It represents the final recovered plan, but it is mislabeled and omits the revision; the base plan boundary is not actually covered by the saved stage evidence. Recommend recording `revision: 3` (or renaming to `plan-3`) and recording the base/other revisions explicitly.

### TR-03 (MEDIUM) — no persisted ff4d749 compileall/diff-check evidence
The only compileall/diff-check claim in the bundle is in the stale `index.json` and refers to the 682e68a run. Independent checks passed (`git diff --check`; 135 files compile), but the primary evidence should persist the command and result for `ff4d749`.

### TR-04 (MEDIUM) — missing committed G02 negative regressions
The delimiter-equivalence behavior is correct, but tests only cover acceptance (`A/D`, `A类及D类`, display-name variants) and the `A/C/E` partial-class-set rejection. Add cases asserting `A/D` expected vs `A/C` and vs `A/C/D` fail closed; otherwise a future change could accept a wrong class set without a failing test.

### TR-05 (LOW) — no direct G16 site-guard regression test
`target_site_ok("G16")` was verified directly (real accrual paragraph accepted; heading, generic fee text, payment-only text rejected), but no committed test names the G16 guard. G06/G17 have explicit negative tests.

### TR-06 (LOW) — pytest log lacks SHA/command provenance
`logs/pytest-ff4d749.txt` contains only pytest output (no `git rev-parse`, command header, or environment binding). Counts and timing are consistent with ff4d749 (1067 collected; +37 cases vs the 682e68a suite), and code is identical in the main repo, but the log itself is not cryptographically bound to the SHA.

## Test-review gate

The offline suite, record/replay equivalence, zero-HTTP replay, D16 stage replay (same-head/no-network), artifact/redline projections, and the named G02/G05/G06/G16/G17/duplicate guards are **PASS at `ff4d749`**. This does **not** make the overall validation gate PASS: all four cases remain `incomplete` (unresolved 20/10/3/19; 24 TRUE obligations each), and the evidence bundle still has TR-01/TR-02 open. Recommendation: **fix evidence metadata (TR-01..TR-03) and add the missing negative tests before certifying the bundle**; business completeness remains a separate gate.
