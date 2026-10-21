# Independent Recovery Review

- HEAD reviewed: `22c15aa4d8d736f2a2fc46a29bc3ed8611475f2f` evidence bundle
- Working branch: `refactor/recovery-architecture`
- Scope: offline review of `reports/{D01,D02,D11,D16}.json`, frozen stage/model ledgers, and recovery implementation. No live model calls.

## Findings

### HIGH-001 — retry budget identity was reset by target re-numbering (fixed)

The recorded D01 recovery history shows the same business operation/site receiving a new discovery target id after inventory refresh:

```text
G01:0 @ p92: T005 → T001
G03:0 @ p135: T008 → T003
```

Both deterministic retries were recorded as `attempt=1`. `RecoveryHistory.count()` and `identical_attempt()` previously partitioned history by `target_id`, so a refreshed target could receive the same retry again. This violates dirty-operation/site recovery and can repeat work after discovery changes. The stable identity is `(rule_id, operation_id, site_id)` (falling back to obligation/site, then legacy target id only when no stable identity exists).

Fix: `fundlex/recovery/history.py` now centralizes `_same_subject()` and uses it for both budget counting and identical-attempt suppression. Regression: `test_retry_budget_survives_target_renumbering_for_same_operation_site`.

### HIGH-002 — Sweep repair restarted discovery for already-bound sites (fixed)

The prior repair loop sent every pending Sweep finding back through window inventory and full-plan regeneration. For a finding whose operation already had a verified target/site, this repeated target discovery and could rebind a different target while leaving the original operation unresolved. The new `_sweep_recovery_contexts()` route keeps the operation/site identity: bound sites go directly to generation or execution recovery, while only unbound sites use the target layer and bounded Inventory. Sweep recovery attempts are recorded in the unified recovery history.

Regression coverage is in `tests/test_sweep_recovery_routing.py` for bound generation, unbound target discovery, and execution classification. When a same-site target carries multiple operations and a Sweep quote cannot uniquely identify one operation, the route is `SWEEP_OPERATION_UNBOUND` and fails closed into Target recovery rather than dirtying every sibling operation.

### HIGH-003 / CROSS-002 — Sweep Claim failure with an existing target was routed back to Target discovery (fixed)

The Sweep route had an attributed target/site, but when Claim Replay reported `CLAIM_OPERATION_NOT_PLANNED` or `CLAIM_OPERATION_UNPROVEN`, it called the generic `classify()` helper. That classified the code as Target and could repeat locator/inventory work even though the operation already had a target. The route now reuses `_claim_failure_context()` with the existing target, plan edits, operation, site, and source span; this resolves the root cause as `TARGET_EXISTS_NO_PLAN` and routes to Generation. The parameterized regression covers both Claim codes.

### MEDIUM-001 — ZIP/container hash could report progress without semantic artifact change (fixed)

Final Sweep repair compared `DocumentInspection.source_sha256`. DOCX regeneration can change ZIP/container bytes (including timestamps) while paragraph text, locations, and structure remain unchanged. That could bypass the no-progress stop and trigger an unnecessary re-audit before the changed-window guard. It did not produce a second Sweep without changed semantic chunks in the reviewed bundles, but it weakened the progress detector.

Fix: `fundlex/recall_pipeline.py` adds `_artifact_text_signature()` over paragraph location/text/zone/part/section and package structure, and Final Sweep compares this semantic signature. Regression: `test_artifact_text_signature_ignores_container_source_hash`.

## Recovery evidence

- D01: `full_audit_count=1`, `incremental_audit_count=3`, `full_sweep_count=1`, `no_progress_stop_count=1`.
- D02: `full_audit_count=1`, `incremental_audit_count=1`, `full_sweep_count=2`, `no_progress_stop_count=2`.
- D11: `full_audit_count=1`, `incremental_audit_count=1`, `full_sweep_count=2`, `no_progress_stop_count=2`.
- D16: `full_audit_count=1`, `incremental_audit_count=1`, `full_sweep_count=2`, `no_progress_stop_count=2`.

The second Sweep occurred only in cases where the first Sweep produced pending findings and the artifact/window path changed. Cases with unchanged recovery state emitted `RECOVERY_NO_PROGRESS` and stopped. Execution-root failures are routed through existing plan reuse/dirty-site generation paths; the code does not call a locator for `CLAIM_PLANNED_EFFECT_MISSING`, and `CLAIM_EXECUTION_EFFECT_MISSING` is classified as execution.

## Severity

- BLOCKER: 0 recovery-routing findings.
- HIGH: 0 remaining after HIGH-001, HIGH-002, and HIGH-003 fixes; the pre-fix target-id budget reset, bound-Sweep rediscovery, and Claim-failure misroute were HIGH.
- MEDIUM: 0 remaining after MEDIUM-001 fix.
- LOW: none.

The four real artifacts remain business-incomplete for findings recorded by the independent business review. This recovery review does not reinterpret those business/effect-proof findings or claim the 20-case Gate passes.

## Validation

```text
.venv/bin/python -m pytest tests/test_sweep_recovery_routing.py tests/test_recovery.py tests/test_operation_execution_closure.py tests/test_recall_pipeline.py -q
75 passed in 19.77s
```
