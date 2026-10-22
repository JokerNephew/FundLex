# Architecture review — exact-code validation `ff4d7498b6c1aee72ba48686074d021fc7f84791`

- **Role:** independent architecture reviewer (read-only: no source/test/git/evidence edits, no live model/HTTP).
- **Runtime code:** `/home/opencode/fundlex-ff4d749` at `ff4d7498b6c1aee72ba48686074d021fc7f84791`.
- **Baseline code:** `682e68a5b3ef2a58feb77460af70afabdb314379`; baseline evidence root `/home/opencode/fundlex/docs/evidence/final-validation-20261022` (not overwritten).
- **Exact-HEAD evidence root:** `/home/opencode/fundlex/docs/evidence/final-validation-20261022/revalidation-ff4d7498`.
- **Method:** diff `682e68a..ff4d749`; exact-HEAD record reports `reports/D0*.json`; frozen stage replays `summaries/D16-stage-*.json`; record/replay comparison `summaries/full-replay-comparison.json`; frozen targets/plan/audit/artifacts. Local inspection/reproduction only; no model or network calls.

## 1. Bottom line

1. **No false complete is proven in these four cases.** All four exact-HEAD runs end `delivery: incomplete`, `artifact_claim_replay.verified: false`, with 3–6 open obligations. The record→replay comparison is exact (`full-replay-comparison.json`: all checks true, 0 HTTP attempts, identical artifact text). The blocked paragraphs are unchanged in the working DOCX, so the overlap guards fail closed. The working files are partial and the reports say `partial`; they must not be presented as final contracts.
2. **The gate must not enter the 20-case set yet.** The four cases still fail delivery on **nine distinct engine defects**, including a **regression** (D02 G12/G13 joint-compose edit is present at baseline but lost at `ff4d749`) and a **false audit negative** (D16 G01). Entering 20 cases now would replicate known engine bugs and measure them, not model quality.
3. The `ff4d749` absent-target tightening is directionally correct: no unsupported `VERIFIED_ABSENT` was found in these four cases. The remaining risks are latent (delete rules without a site guard; split-clause absence proofs), not realized here.

## 2. Exact-HEAD case snapshot

| Case | Mode | Calls | Cost USD | ARTIFACT_VERIFIED | ALREADY_SATISFIED | N/A | UNRESOLVED | Delivery | Unresolved items |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| D01 | record | 32 | 0.023543 | 11 | 7 | 10 | 6 | incomplete | 20 |
| D02 | record | 35 | 0.037020 | 11 | 8 | 10 | 5 | incomplete | 10 |
| D11 | record | 29 | 0.021728 | 13 | 8 | 10 | 3 | incomplete | 3 |
| D16 | record | 34 | 0.035132 | 11 | 7 | 10 | 6 | incomplete | 19 |

Sources: `summaries/D01-record.json` … `D16-record.json`; gate counts in `reports/D0*.json` (`delivery_gate`). The total is 130 calls / ≈$0.1174. `index.json` still says `current_record_total_calls: 122` / `$0.1146` and `record_results: {}`; it was written before the exact-HEAD records (see §9).

Per-case open obligations (from `reports/D0*.json`):

- **D01:** G01:0, G02:0, G02:1, G06:0, G16:0, G17:0.
- **D02:** G06:0, G12:0, G12:1, G13:0, G16:0.
- **D11:** G05:2, G06:0, G16:0.
- **D16:** G06:0, G12:0, G12:1, G13:0, G16:0, G17:0.

`G12:0` in D02/D16 is a ONE_OF history sibling of `G12:1`; it closes automatically when `G12:1` passes (as it does in D01 via the shared site, `reports/D01.json` `artifact_claim_replay.obligations["G12:B1:O1"]`). It is not an independent blocker.

## 3. Classification key

- **REAL_ENGINE_BUG** — deterministic engine logic produces a false conflict, loses a valid edit, cannot find a valid site, or books the wrong status.
- **EXPECTED_FAIL_CLOSED_TARGET / GENERATION** — the engine correctly refuses to write because the target/operation is not provable; the observed block is the intended safety behavior.
- **MODEL_FAILURE / RECOVERY_FAILURE** — the model supplied a wrong/out-of-scope target and recovery did not repair it; the engine correctly fails closed.
- **BUSINESS_AMBIGUITY** — two genuinely different business operations require a user/rule decision. None of the current blockers is of this class; the `G17` conflicts are the *same* operation, and `G12/G13` is a valid joint-compose case that was lost, not an unresolvable rule conflict.
- **EVIDENCE/BOOKKEEPING** — the evidence index/ledger is stale or internally inconsistent; not a runtime defect.

## 4. Blockers

### F1 — BLOCKER — D02 G12/G13 joint compose is present at baseline and lost by `replan_sites` (REAL_ENGINE_BUG, regression)

- **Observed:** baseline D02 plan contains the validated joint edit `T016+T017` at `p229` (`/home/opencode/fundlex/docs/evidence/final-validation-20261022/frozen/D02/plan.json`, 16 edits, `content_source: joint_compose`). At `ff4d749` the same frozen target/plan path has 16 edits but **no p229 edit**; `reports/D02.json` marks G12:1/G13:0 `UNRESOLVED` (`CLAIM_REPLAY_FAILED`) and the artifact `p229` is byte-identical to the source (`artifacts/D02/working_final.docx`). The plan ledger contains `UNBOUND:772a…` with `operation_keys: [G12:1, G13:0]`, `reason: RECALL_PLAN_REFERENCE_UNBOUND`, and `T016/T017` with `RECALL_PLAN_COMPONENT_DROPPED`.
- **Reproduced:** replaying frozen `stages/plan-1.json` (dirty `p1288,p1289,p228`; existing p229 joint) loses the joint edit in every replan (`replay_stage(..., 'plan', revision=1/2/3)`); a *fresh* replay of `stages/plan.json` does produce the p229 joint edit (17 edits, 1 conflict). So the loss is in `replan_sites`, not `plan_edits`/Joint Compose.
- **Root cause:** `replan_sites.bind_reference` treats one joint-compose edit as one unit and requires `keys <= set(target.operations)` on a *single* target (`fundlex/recall.py:4723-4735`). A joint edit has `G12:1+G13:0`, no single target carries both, so it returns `None`; the parent edit is dropped as atomic (`fundlex/recall.py:4843-4855`) and booked `UNBOUND` (`fundlex/recall.py:4805-4812`). The joint edit is self-contained (`expected_old_text`, span, replacement, validation PASS) and its paragraph is not dirty, so it should be retained.
- **Smallest generic fix:** in `replan_sites`, bind a multi-key/joint edit by its components (each operation+location) or, when `content_source == "joint_compose"` and its `expected_old_text` matches the current source span, retain it unchanged. Do not drop a validated joint edit because no single target owns both keys.
- **Why it blocks:** D02 would otherwise have a correct joint replacement for p229; G12/G13 are the two largest open obligations. This is a regression from baseline, so it must be fixed before any 20-case run.

### F2 — BLOCKER — G06 delete-of-absent sentence cannot be proven (4/4; REAL_ENGINE_BUG)

- **Observed:** G06:0 is `UNRESOLVED` / `CLAIM_OPERATION_UNPROVEN` with `verified site missing` in D01, D02, D11, D16 (`reports/D0*.json`; `summaries/D16-stage-claim_replay.json` failure `G06 G06:0 CLAIM_OPERATION_UNPROVEN`). The G06 sentence
  `除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。`
  is absent document-wide in all four sources (checked over every paragraph; 0 occurrences).
- **Root cause:** `replay_claims` now drops `state: absent` targets unless a real site is bound (`fundlex/generation/claim_replay.py:996-1045`), and `evaluate_operation_effect` returns `OPEN` when no site exists (`fundlex/generation/effects.py:334`). There is no document-wide absence proof for a delete. The old 682e68a behavior was too permissive (absent placeholders could count), but the replacement has no sound path for a genuinely absent literal.
- **Smallest generic fix:** in `evaluate_operation_effect` (or once per replay before the loop), for `spec.op == "delete"` with no verified site, if every reference (`old_text` plus alternatives) is absent from the **entire original document** (compact match, minimum length ≥ 8), return `PASS` / `VERIFIED_ABSENT` with `proof_kind: document_literal_absent` and the searched literal. This is stronger than a site/heading proof and cannot be spoofed by a placeholder. Do **not** generalize it to replace/append.
- **Why it blocks:** 4/4 cases; it is the only G06 issue. The correct business result is “already satisfied” (nothing to delete).

### F3 — BLOCKER — G16 append is never sited; G15 deletes the payment clause and nothing replaces it (4/4; REAL_ENGINE_BUG)

- **Observed:** G16:0 is `UNRESOLVED` / `verified site missing` in all four cases (`reports/D0*.json`; `summaries/D16-stage-claim_replay.json`); the plan contains no G16 edit in D01/D11/D16 and only an unbound/out-of-scope G16 target in D02. Meanwhile G15 deletes the service-fee payment clause:
  - D01 `p758`/`p1221`, D02 `p821`/`p1287`, D11 `p772`/`p1247`, D16 `p822`/`p1306` are `' '`/`''` in `artifacts/D0*/working_final.docx`.
  - The G16 new mechanism (daily accrual, direct-sales refund, monthly payment, >1-year refund) is absent from those paragraphs. The partial artifact therefore removes the old payment mechanism without installing the new one. The reports correctly say `partial`, but this is a substantive business gap and a strong reason not to treat the working file as final.
- **Root cause:** `target_site_ok("G16", …)` accepts any paragraph containing `销售服务费` plus one of `计提/每日计算/按月支付/支付日期` (`fundlex/recall.py:5220-5223`). In every case this matches 4 paragraphs in the fee section (fee list, rate clause, formula row, payment clause), so `append_applicability_targets` refuses to choose because it requires exactly one member (`fundlex/recall.py:2350`). The model's G16 targets are on the **usage** clause (`p760/p823/p773/p824`), fail the G16 site guard, and are marked `TARGET_SOURCE_MISMATCH`. The true G16 site is the **payment** clause that G15 deletes (`p758/p821/p772/p822`).
- **Proof the fix is minimal:** tightening the G16 guard to require `销售服务费` + (`每日计提` or `逐日累计`) + `按月支付` yields exactly one anchor in each case: D01 `p758`, D02 `p821`, D11 `p772`, D16 `p822` (checked against the frozen sources). The existing `duplicate_copy_targets` then clones the target to the byte-identical summary copy (`p1221/p1287/p1247/p1306`), and the existing G15-delete+G16-append merge (`merge_edits` `merged_delete_append`, `fundlex/recall.py:4243-4275`) installs the new mechanism where the old clause was removed.
- **Smallest generic fix:** tighten `target_site_ok` G16 to the payment-clause shape above. Do not add a new append architecture; the G15/G16 composition path already exists.
- **Why it blocks:** 4/4 cases; highest business impact (payment mechanism missing).

### F4 — BLOCKER — Same-operation duplicate targets create false `RECALL_EDIT_OVERLAP` conflicts (D01, D16; D02 duplicate-target false block; REAL_ENGINE_BUG)

- **Observed:**
  - D01: `Y006` (G17:0, composite `p759:0:52,p760:0:24`) vs `DEL001` (G17:0, `p760:0:24`) conflict at `p760`; `Y007` vs `DEL002` at `p1223` (`reports/D01.json`; `frozen/D01/plan.json` conflicts). Both sides are the **same operation** `G17:0`; `DEL001/DEL002` are engine-created `delete_residual_copy` targets for the second sentence already covered by the composite.
  - D16: `T019` (G17:0, `p823:0:52`) vs `Y010` (G17:0, composite `p823:0:52,p824:0:24`) conflict at `p823` (`reports/D16.json`; `summaries/D16-stage-plan.json`). `T019` is a single-paragraph alias of the composite's first part.
  - D02: `Y012` exists **twice** — one G18 `p223` satisfied target and one G15 `p821` needs_edit target. The G15 `Y012` duplicates `T019` at the same `p821` span and the same `G15:0`; the report lists `Y012` as `RECALL_TARGET_UNRESOLVED` even though G15 is `ARTIFACT_VERIFIED` at `p821/p1287`.
- **Root cause:**
  - `dedupe_operation_targets` groups by `(rule, location, operations)` and, when either target is composite, requires `item.composite == other.composite and item.quote == other.quote` (`fundlex/recall.py:1957-1958`). A composite and its first-paragraph single alias are therefore not deduped. The G17 composite/single pairs at different locations (`p759` vs `p760`) are not even in the same group.
  - `merge_edits` only absorbs a contained edit for declared ONE_OF alternatives (`fundlex/recall.py:4271-4287`); identical same-operation edits fall through to `RECALL_EDIT_OVERLAP` (`fundlex/recall.py:4288`).
  - `_survey_targets_from_hits` assigns `Y{counter:03d}` from `start_index=len(synthetic)` (`fundlex/recall_pipeline.py:676`, `:824`); a later survey round can reuse an existing `Y012`, producing the duplicate ID. The ledger/audit maps by `target_id`, so one target overwrites/mis-books the other.
- **Smallest generic fix:** (a) extend `dedupe_operation_targets` to compare a composite target part with a single target at the same part location, and to treat an absent/needs_edit alias of the same operation/span as one occurrence; prefer the composite/planned target. (b) As a safety net, in `merge_edits`, when two overlapping edits have the same `operation_keys` and identical/empty replacement at the same location, absorb the contained edit as covered instead of conflicting. (c) Allocate `Y` IDs from a global used-ID set (or a stable hash) and dedupe survey hits by `(rule, operation, location, span)`.
- **Why it blocks:** D01/D16 G17 are open solely because of these false conflicts; the user summary’s “同一段落的多项修改无法安全合并” is misleading for G17 (it is one delete, not two independent edits). D02’s `Y012` is a false unresolved item after G15 already passed.

## 5. Highs

### F5 — HIGH — D01 G01 split definition is skipped by the append pass (REAL_ENGINE_BUG)

- **Observed:** D01 `p91` is the split head `基金份额类别：本基金将基金份额分为 A 类、C 类和 D 类三种不同的`; `p92` is the continuation `类别。在投资者申购 A 类及 D 类基金份额时收取申购费用…`. D01 has **no G01 target** (`frozen/D01/targets.json`; obligation `G01:B1:O1 targets=[]`), no G01 edit (`frozen/D01/plan.json`), and the artifact `p92` is unchanged. G03 (the same policy in 基金的基本情况) succeeds at `p130`, so the policy exists only in the second section.
- **Root cause:** the `ff4d749` `append_site_ok` split-continuation branch correctly accepts `p92` (`fundlex/recall.py:5180-5208`), but it also accepts the head `p91` via the ordinary anchor test. `append_applicability_targets` requires exactly one member (`fundlex/recall.py:2350`), so two members (`p91`, `p92`) produce no hit. This is an incomplete fix, not a model issue: the append target is deterministic and the correct continuation is uniquely identifiable.
- **Smallest generic fix:** when a G01/G03 head paragraph ends without a sentence terminator and its direct successor is an accepted continuation, exclude the head from `members` (or emit the hit on the continuation only). The planner already appends after the last sentence, so no other change is needed.
- **Why it matters:** D01’s G01 is a primary obligation; without it D01 cannot deliver.

### F6 — HIGH — D01 G02 recovery locates the split head, then the audit compares the un-instantiated “B类” guide text (REAL_ENGINE_BUG + MODEL false negative)

- **Observed:** D01 G02 targets `T3001/T3002` are at `p91`, span `0..35`, quote `基金份额类别：… A 类、C 类和 D 类三种不同的` (`frozen/D01/targets.json`). Planning fails `RECALL_TARGET_OCCURRENCE_AMBIGUOUS`; `reports/D01.json` audits them `incomplete` with the literal reason “does not add B类” even though the product’s actual classes are A/C/D and the source already has `A 类及 D 类` (the correct subscription group). The real fee-group clause is `p92`.
- **Root cause:** the `class_definition` locator (`fundlex/v2.py:506-585`) finds the class letters in the `p91` sentence and returns that sentence as the target; it does not follow the split continuation `p92` where the fee-group wording lives. `_plan_target_inner`’s class-set-equivalence path (`fundlex/recall.py:3569-3590`) requires fee wording in the quote (`申购费/认购费/销售服务费`), which the `p91` heading lacks, so it cannot mark the target satisfied. The audit then reasons on the raw guide placeholder `A类、B类基金份额` rather than the instantiated `A类、D类`.
- **Smallest generic fix:** in `_locate_class_definition`, when the matched definition sentence ends without a terminator and the next paragraph is a `类别…` continuation containing fee wording, bind the target to the continuation (or to the union spanning both), mirroring `append_site_ok`. The class-set check will then see `A 类及 D 类` and mark G02/G04 `ALREADY_SATISFIED`, so the audit is not invoked. Separately, pass the instantiated group to the audit context; do not let the raw `B类` placeholder drive a false `incomplete`.
- **Why it matters:** D01 G02 is two obligations; the current result is a false negative on a contract that already complies.

### F7 — HIGH — D16 G12/G13 `p221` target is over-broad; the conflict is a correct fail-closed reaction to an engine target-construction bug (REAL_ENGINE_BUG; observed behavior EXPECTED_FAIL_CLOSED_TARGET)

- **Observed:** `Y007` is `G13:0` with `quote` = the **whole** `p221` paragraph and `composite: p221:0:101, p222:0:30` (`frozen/D16/targets.json`). The G13 old text is only the short-holding sentence starting at `其中，` (`p221:90..101` + `p222:0..30`, as the sweep itself records in `frozen/D16/sweep.json` `SW003`). `Y007` therefore overlaps `T014` (`G12:1`, `p221:0..101`) on the whole paragraph. The plan reports `RECALL_EDIT_OVERLAP`; the artifact leaves `p221` unchanged. The conflict guard is doing the right thing; the target geometry is wrong.
- **Root cause:** `survey_targets` fuzzy-matches the long G13 reference to the whole `p221` window (`fundlex/recall.py:2127-2290`); `_extend_to_clause_start` sees the match already at 0 and cannot trim it (`fundlex/recall.py:2447-2472`). `_clause_continuation_binding` then promotes the whole-paragraph target to a composite (`fundlex/recall_pipeline.py:957-995`), preserving `p221:0..101` instead of the operation’s `90..101` start. The joint-compose resolver only works on the conflicting `p221` span, not the composite’s `p222` part (`fundlex/recall.py:4393-4475`), so it cannot prove the full G12+G13 transformation.
- **Smallest generic fix:** bound a delete survey hit to the operation’s sentence(s) (use the `SW003`-style exact artifact span / the rule’s delete anchors), and when rebinding a split delete, keep the original mid-paragraph `start` and extend only the `end` into the follower. Do not relax the overlap guard; the guard’s fail-closed behavior is correct.
- **Why it matters:** D16 G12/G13 are two obligations; a correct joint replacement is already known in D02’s baseline. A whole-paragraph G13 delete without the G12 conflict would be an over-deletion; the current conflict prevents it, but the target must be fixed before 20 cases.

### F8 — HIGH — D16 G01 audit verdict is orphaned by the target quote change (REAL_ENGINE_BUG, regression)

- **Observed:** `frozen/D16/audit.json` contains a completed G01 verdict for `T001` with `evidence_verified: true` (“AFTER appends the required new clause …”). `reports/D16.json` still reports `AUDIT_VERDICT_MISSING` for the same `T001`, and `user_summary` says G01 “独立复核认为修改尚未完成”. The obligation is `ARTIFACT_VERIFIED`; the appended text is present at `p91` in `working_final.docx`. Baseline `T001` quote/span was `0..131`; at `ff4d749` it is `77..131` (the C-class sentence), while the audit result was stored under the old identity.
- **Root cause:** `_target_identity` hashes `start,end,compact(quote),composite,operations,occurrence` (`fundlex/recall_pipeline.py:547-561`). `_merge_audit_state` stores the verdict under that identity (`:1610-1626`); `_audit_issues` looks it up with the final target identity (`:1715-1728`). Narrowing the append target’s quote (without changing the paragraph or operation) changes the key, so a valid completed audit becomes “missing”.
- **Smallest generic fix:** key audit results by stable business identity — `rule_id`, paragraph location, source paragraph body hash, sorted operations, occurrence — not by the model’s target quote slice. Include the instantiated new-text hash for append/replace so a changed policy still re-opens the audit. This preserves the “content change re-opens” intent while ignoring pure target-geometry churn.
- **Why it matters:** it is a false negative on a completed obligation and it blocks D16 delivery; it is also a regression from the baseline target quote.

### F9 — HIGH — D02 `Y012` duplicate ID / redundant target blocks delivery after G15 passed (REAL_ENGINE_BUG, bookkeeping)

- **Observed:** `frozen/D02/targets.json` contains two targets with the same `target_id` `Y012`: G18 `p223` (`state: satisfied`) and G15 `p821` (`state: needs_edit`, same span/operation as `T019`). `reports/D02.json` lists `Y012` (G15, `p821`) as `RECALL_TARGET_UNRESOLVED`, while `G15:B1:O1` is `ARTIFACT_VERIFIED` and the artifact `p821`/`p1287` are deleted. The user-visible unresolved item is redundant.
- **Root cause:** the survey ID allocator can reuse `Y012` across rounds (`fundlex/recall_pipeline.py:676`, `:824`); `dedupe_operation_targets` skips `T019` because its state is `absent` (`:1920-1926`), so the needs_edit `Y012` alias is not suppressed. The ledger/audit keyed by `target_id` then conflates the two.
- **Smallest generic fix:** allocate survey IDs from a document-wide used set; include resolved `absent` targets in the same-operation/span dedupe and mark the redundant alias `covered` (or `satisfied`) instead of `unresolved`. This is the same duplicate-target class as F4 and can be fixed in the same pass.
- **Why it matters:** it is a false block in the closest-to-delivery case (D11 has 3 open; D02 has 5, one of which is this bookkeeping item).

### F10 — HIGH (latent) — Unsupported `VERIFIED_ABSENT` remains possible for delete rules without a site guard and for split-clause heads

- **Observed in these four:** no unsupported `VERIFIED_ABSENT` was found. D01/D02 G05:2 absence is at the real class-setup paragraph (`p135`/`p138`); D16 G05:2 is an actual edit at `p133`; G15/G17/G13 `VERIFIED_ABSENT` entries all have real edits; G06 is unproven (not falsely passed). The `ff4d749` fixes (drop `claimed_operations`, drop `attribution_error`, drop `absent` sites in `_verified_site_closure`) work for the exercised cases.
- **Latent risk:** `target_site_ok` returns `True` for any rule not in its explicit guards (`G13` and future delete rules; `fundlex/recall.py:5228-5229`). `evaluate_operation_effect` marks any delete with no residual at a “verified site” as `VERIFIED_ABSENT` (`fundlex/generation/effects.py:465`). A model target on a heading/summary paragraph that happens to pass the quote-in-body test can therefore prove a delete no-op at the wrong site. The D01 G05:2 proof is also site-scoped to `p135` even though the clause continues to `p136` (“公告。”); if the literal had been in the continuation, the proof would be unsupported.
- **Smallest generic fix:** for `VERIFIED_ABSENT`, require either (a) the exact literal was present in the *original* site and is absent in the artifact, or (b) the literal is absent document-wide (F2), or (c) a rule-specific site guard exists and the site is a complete business clause (follow the direct continuation when the paragraph is unfinished). Do not accept a bare heading/placeholder quote.
- **Why it matters:** the current four cases are safe, but a 20-case set with different layouts can turn this into a false complete.

## 6. Cross-cutting checklist (the requested focus)

| Concern | Finding |
|---|---|
| **False complete** | Not proven. All 4 cases `incomplete`; `claim_verified: false`; blocked paragraphs unchanged; audit/sweep `NOT_COMPLETED` for the unedited targets is correct. The false *negative* is D16 G01 (F8). Working DOCX is partial and marked partial; do not deliver as final. |
| **Cross-site proof** | Works where exercised: D16 G17 keeps `p823/p824` as required sites and fails although `p1307/p1308` were deleted; G15 requires both body/summary copies; G05:2 is site-guarded. Latent delete-without-guard risk (F10). |
| **Unsupported `VERIFIED_ABSENT` from heading/placeholder/unattributed** | The `ff4d749` filter closes the 682e68a hole for the 4 cases; D01/D02 G05:2 are real class-setup paragraphs. Residual latent risk: rules without site guards (G13) and split-clause heads (F10). |
| **Planned-but-not-artifact** | The final ledger reconciliation works: no ledger says `planned` for an edit absent from `records`; conflicting targets are `unresolved`. But D02’s validated joint edit is silently dropped in replan (F1) — a lost edit, not a false artifact claim. `plan_matches_actual: true` in the artifact reviews. |
| **Duplicate body/summary proof** | `DUPLICATE_SITE_UNEDITED` fires for D16 `p823` (`D16-stage-claim_replay.json`), and `_verified_site_closure` adds exact-body duplicates. The G16 summary copy is not yet a site because G16 has no target (F3); after the guard fix, `duplicate_copy_targets` handles it. |
| **Same-operation duplicate target/merge conflicts** | Proven false conflicts: D01 G17 composite vs `DEL001/DEL002`; D16 G17 `T019` vs `Y010`; D02 G15 `Y012`/`T019`. Fix in `dedupe_operation_targets` + `merge_edits` (F4/F9). |
| **Target renumbering/history** | Stable-key rebind is the right direction and fixes single-target replans, but it does not cover joint edits (F1), audit identity (F8), or duplicate IDs (F9). Concrete drift: D16 targets stage `T019 G16 p824 / T020 G17 p823` → final `T018 G16 / T019 G17`; D02 joint old `T017+T019` → current `T016/T017`. Do not use `target_id` as a business identity. |
| **G01/G03 split append** | D01 G01 fails because both the split head `p91` and continuation `p92` are members; G03 at `p130` succeeds. F5. |
| **G02/G04 occurrence/class-set** | Class-set equivalence works: D02/D11/D16 G02/G04 `ALREADY_SATISFIED` (actual `A、D` vs guide `A、B` after instantiation; `A 类及 D 类` vs `A类、D类`). D01 fails at the split heading (F6). The actual *replacement* path (source missing a group) is not exercised in these 4 cases — coverage gap for 20 cases. |
| **G05 bounded splice/site guard** | D16 `p133` G05:0 replace + G05:2 delete composed atomically and verified; D01/D02 G05:2 absent at the real class-setup site; D11 G05:2 is a model target error / fail-closed (F11 below). The guard is strong; the split-head absence edge is latent (F10). |
| **G16 duplicate sites** | 4/4 unresolved; the G16 site guard accepts 4 fee paragraphs and the append pass requires exactly one. Tightened guard yields one payment-clause anchor per case; `duplicate_copy_targets` then clones the summary copy (F3). |

## 7. Mediums / lows

### F11 — MEDIUM — D11 G05:2 is a model/recovery failure with an engine consistency gap (MODEL_FAILURE / RECOVERY_FAILURE; honest fail-closed)

- **Observed:** D11 `T006` (G05, `p129`, quote `调整前基金管理人需及时公告`, `claimed_operations: [G05:2]`, `operations: []`, `out_of_scope: true`, `reason: TARGET_SOURCE_MISMATCH`) does not produce a G05:2 site; `reports/D11.json` has `G05:B3:O1 UNRESOLVED` and recovery `REBUILD_PLAN` → `MARK_UNRESOLVED` (`detail: CLAIM_OPERATION_NOT_PLANNED:no_code_proven_site`). The literal `并报中国证监会备案` is absent at the class-setup paragraph `p129` (it occurs only in unrelated clauses `p726/p927/p1320`).
- **Root cause:** the model emitted `needs_edit` with the quote at the end of the clause, but the operation literal is not there. The engine has no site-scoped absence normalization for a delete target whose quote resolves and whose old text is absent at a real guarded site; it marks the target `TARGET_SOURCE_MISMATCH` and leaves the obligation open. D01/D02/D16 close the same situation because the model emitted `state: absent`.
- **Smallest generic fix:** when a delete target's quote resolves within its location, the rule’s site guard passes, and the operation’s exact old text is absent from that paragraph (including the direct continuation if unfinished), mark the target `absent`/`satisfied` for that operation. This is the same site-scoped proof used by D01/D02, applied consistently.
- **Classification:** the model target is wrong; the fail-closed result is honest. It is not a false complete. It is a delivery blocker only if the gate requires 4/4 model-perfect delivery; it is a model/recovery data point for 20 cases.

### F12 — MEDIUM — Evidence index/gate record is stale and inconsistent with the exact-HEAD runs (EVIDENCE/BOOKKEEPING)

- **Observed:** `revalidation-ff4d7498/index.json` has `validation_head: ff4d749…`, but `record_results: {}` and `replay_results.*.head: 682e68a…` (baseline). Its `gate_reason` still says “D01 artifact not generated due to stable-identity replan bug” and “Absent inventory placeholders accepted as proof sites”, both of which are no longer true at `ff4d749` (D01 has a working artifact; the absent filter is in place). `current_record_total_calls` is 122/$0.1146 while the four exact-HEAD records total 130/≈$0.1174. `gate: FAIL` is still the right *outcome* (4/4 incomplete), but the recorded reasons/figures are not exact-HEAD evidence.
- **Fix:** update the index with the four `record_results`, the exact-HEAD replay heads, the new totals, and a gate reason that cites the F1–F9 blockers. Keep the baseline and exact-HEAD evidence separate; do not overwrite the baseline root.
- **Why it matters:** any reviewer reading `index.json` alone would validate the wrong code/reasons.

### F13 — LOW/INFO — `ALREADY_SATISFIED` is used for ONE_OF sibling effects and class-set equivalence; supported but misleading

- **Observed:** D01 `G12:B1:O1` and D16 `G11:B1:O1` are `ALREADY_SATISFIED` with no own edit; the effect is present in the artifact because the sibling operation (`G12:1` / `G11:1`) wrote it, and the ONE_OF group shares the verified site (`fundlex/generation/claim_replay.py:1065-1095`). D02/D11/D16 G02/G04 `ALREADY_SATISFIED` are the instantiated class set (`A类、D类` vs `A 类及 D 类`; `fundlex/generation/effects.py:23-39`). These are supported, not false completes, but the label reads as “the source already complied” when the artifact effect came from a sibling edit.
- **Fix (reporting only):** use `EXPECTED_EFFECT_PRESENT_VIA_WORDING_GROUP` / `CLASS_GROUP_ALREADY_PRESENT` for these cases, or add a `provenance` field. No delivery impact.

### F14 — MEDIUM — Coverage gap: the four cases do not exercise the actual G02/G04 replacement path or a real G05 bounded split

- **Observed:** D01/D02/D11/D16 all already have the correct class group (`A`/`A,D`/`A,C`), so G02/G04 only exercise the “already correct” path. No case requires replacing a missing class group (`A` → `A,D`). G05:0 is a six-character literal replace; the only G05:2 delete with the literal present is D16 `p133` (single paragraph). The multi-paragraph G05 splice and the G02/G04 occurrence-index replacement are not live-validated.
- **Impact:** a 20-case set must include contracts with a missing/extra class group and a multi-paragraph class-setup clause; otherwise the “G02/G04 occurrence/class-set” and “G05 bounded splice” paths remain untested.

## 8. Gate decision

**Do not enter the 20-case set now. Gate stays closed.**

Rationale:

1. **4/4 exact-HEAD cases are still `incomplete`**; the common blockers are engine defects (F1–F4), not model/target ambiguity. A 20-case run would replicate them and waste budget.
2. **A regression is present:** D02’s validated G12+G13 joint edit existed at baseline and is lost by `replan_sites`. The exact-HEAD code is not monotonic over the baseline on this obligation.
3. **A false audit negative** (D16 G01) and a **duplicate-target false block** (D02 Y012) show the bookkeeping/evidence layer is not yet trustworthy for a larger batch.
4. The positive result is real: **no false complete**, zero HTTP in replay, identical artifact text, and the site/duplicate guards work. That is the right foundation; it is not a delivery pass.

**Conditions to enter 20 cases:**

- Fix F1–F4 (joint replan, G06 document-wide absence, G16 payment-clause guard, same-operation duplicate/dedupe) and F5/F6 (D01 split append/locator). F7/F8/F9 should be fixed before the batch if D02/D16 are in it; F8 is a regression and should be fixed regardless.
- Re-record the four cases on the new SHA (the fixes change planning/model calls; replay alone is not enough). Require **4/4 `delivery: complete`** or, if a case remains incomplete, every open item must be classified `MODEL_FAILURE`/`TARGET_AMBIGUITY` with no engine bug and no false complete.
- Update `index.json` to the new exact-HEAD record/replay values and a gate reason that cites the actual remaining blockers (F12).
- Pre-register the 20-case budget and seed set; include a contract with a missing class group and a multi-paragraph class-setup clause (F14). Current 4-case cost is ≈$0.117/130 calls; the index’s total limits (768 calls/$2.4) were not exhausted, but a 20-case run needs its own pre-registration.

If the project chooses to run 20 cases anyway, label it **diagnostic, not final**; do not publish delivery metrics as model quality until F1–F4 are fixed.

## 9. Smallest-fix order (suggested)

1. **F1** retain joint-compose edits in `replan_sites` (D02 G12/G13 regression).
2. **F3** tighten G16 site guard to the payment clause (4/4; restores the G15→G16 mechanism).
3. **F2** document-wide absent-literal proof for delete obligations (4/4 G06).
4. **F4/F9** same-operation duplicate dedupe + unique `Y` IDs (D01/D16 G17, D02 Y012).
5. **F5** exclude the split head from G01/G03 append members (D01 G01).
6. **F6** extend the class-definition locator over the split continuation + instantiate audit class groups (D01 G02).
7. **F7** trim survey delete hits to the operation sentence / joint compose across composite parts (D16 G12/G13).
8. **F8** stable audit identity (D16 G01).
9. **F10** harden `VERIFIED_ABSENT` for delete rules without a site guard and split heads.
10. **F11** site-scoped absent normalization for D11 G05:2 (model/recovery consistency).
11. **F12** update the evidence index; **F13/F14** reporting/coverage only.

## 10. Evidence map

- Exact-HEAD reports: `reports/D01.json`, `D02.json`, `D11.json`, `D16.json`; summaries `summaries/D0*-record.json`, `D0*-replay.json`, `full-replay-comparison.json`.
- Stage replays: `summaries/D16-stage-facts.json`, `-applicability.json`, `-targets.json`, `-obligations.json`, `-plan.json`, `-claim_replay.json`. `D16-stage-plan.value` equals `reports/D16.json.plan`; `D16-stage-claim_replay` has the same 9 failures and `verified: false` (only `recovery_state_hashes` differs).
- Frozen inputs/artifacts: `frozen/D0*/{original.docx,targets.json,plan.json,audit.json,report.json,sweep.json,working_final.docx}`; `artifacts/D0*/{report.json,report.md,working_final.docx,edits.json}`.
- D02 regression: baseline `/home/opencode/fundlex/docs/evidence/final-validation-20261022/frozen/D02/plan.json` (p229 joint present) vs exact-HEAD `frozen/D02/plan.json` (absent) and `replay_stage('.../frozen/D02','plan',revision=1/2/3)` (lost in replan; fresh `plan` has it).
- D16 audit regression: baseline `.../final-validation-20261022/frozen/D16/targets.json` `T001` `0..131` vs exact-HEAD `T001` `77..131`; `frozen/D16/audit.json` completed G01 verdict vs `reports/D16.json` `AUDIT_VERDICT_MISSING`.
- Code: `/home/opencode/fundlex-ff4d749/fundlex/recall.py` (4197–4300, 4514–4560, 4723–4812, 4843–4855, 5178–5229, 1909–1982, 2321–2366, 2127–2290, 2447–2472); `fundlex/generation/claim_replay.py` (996–1045, 1132–1220); `fundlex/generation/effects.py` (23–39, 127–230, 313–475); `fundlex/recall_pipeline.py` (547–561, 648–720, 957–995, 1610–1630, 1715–1728); `fundlex/v2.py` (506–585).
- Stale index: `index.json` (`record_results: {}`, `replay_results.*.head: 682e68a`, `gate_reason` baseline text).

*No source, test, git, or evidence data was modified by this review; only this report and its JSON companion were written.*
