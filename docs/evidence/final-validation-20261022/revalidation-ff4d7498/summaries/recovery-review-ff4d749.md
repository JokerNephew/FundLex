# Independent Recovery Review — exact HEAD ff4d749

- **Runtime code**: `ff4d7498b6c1aee72ba48686074d021fc7f84791` (`/home/opencode/fundlex-ff4d749`), branch `refactor/recovery-architecture`, tree `7ad22dc0…`
- **Evidence**: `docs/evidence/final-validation-20261022/revalidation-ff4d7498`
- **Cases**: D01, D02, D11, D16
- **Mode**: read-only. No source/test/git edits, no live model/HTTP calls. Only this summary pair was written.
- **Method**: static code read at HEAD + report/frozen-stage inspection + programmatic checks of every evidence site against the frozen original and the working DOCX.

## Verdict

**Recovery safety: PASS.** No obligation was closed without a site-bound proof, no absent/attributed/heading placeholder was accepted as a site, no `final.docx` was published while obligations remained open, and record/replay recovery state is byte-identical.

**Delivery: FAIL.** All four cases are incomplete: 20 open obligations and 52 unresolved entries. The gate is honest, but recovery itself is not: it loses deterministically deliverable edits (G17, G12/G13), never discovers a site for G16, and can never close an absent-literal delete (G06).

**Code change before the 20-case run: YES.** Four BLOCKER-level defects must be fixed first; otherwise every case will contain at least one false unresolved and at least one undelivered core obligation, and the 20-case metrics will measure planner gaps as contract difficulty.

| Severity | Count |
| --- | ---: |
| BLOCKER | 4 |
| HIGH | 5 |
| MEDIUM | 8 |
| **Total** | **17** |

## Record vs replay

| Check | Result |
| --- | --- |
| Recovery history equal | yes |
| Unresolved list equal | yes |
| Claim-replay `recovery_state_hashes` equal | yes (all 9 boundaries) |
| Audit-round `recovery_state_hashes` equal | yes |
| Artifact text equal | yes |
| Replay HTTP calls | 0 |
| D16 stage replay | all stages `same_head=true`, `replayed=true`, 0 calls (plan: 2 cassettes) |

All findings below are reproducible at ff4d749; none is a recording/replay artifact.

## Per-case recovery state

| Case | Delivery | Attempts | Open obligations | Unresolved entries | Claim-replay obligations attempted | Not attempted |
| --- | --- | ---: | ---: | ---: | --- | --- |
| D01 | incomplete | 14 | 6 (G01, G02:B1:O1, G02:B1:O2, G06, G16, G17) | 20 | G01 | G02×2, G06, G16, G17 |
| D02 | incomplete | 6 | 5 (G06, G12:B1:O1, G12:B1:O2, G13, G16) | 10 | G06 | G12×2, G13, G16 |
| D11 | incomplete | 2 | 3 (G05:2, G06, G16) | 3 | G05:2 | G06, G16 |
| D16 | incomplete | 21 | 6 (G06, G12:B1:O1, G12:B1:O2, G13, G16, G17) | 19 | G06 | G12×2, G13, G16, G17 |

## Findings

### BLOCKER

**RR-01 — Same-operation duplicate/subset targets become competing edits (D01, D16).**
D01 G17 has composite targets Y006/Y007 (p759+p760, p1222+p1223) *and* residual targets DEL001/DEL002 (p760/p1223), all `G17:0`. `ensure_delete_targets` computes coverage from `target.quote` (the first sentence) instead of the composite part spans, so it recreates the second sentence as a separate target. `merge_edits` only absorbs contained edits for declared ONE_OF siblings, never for the same operation, so both are reported as `RECALL_EDIT_OVERLAP`; the plan has **zero G17 edits**. D16 repeats at p823: inventory `T019` vs survey composite `Y010` (same operation, same span) conflict; only the summary copy `Y011` (p1307/p1308) is planned, so the body copy survives and the two copies diverge.
*Code*: `fundlex/recall.py:5265-5273, 5300-5306, 4271-4293`. Fix: cover composite parts by their own part spans; absorb identical/contained same-operation targets (keep the maximal composite, mark the subset covered); never send identical same-operation deletes to Joint Compose; keep the already planned site edit across a dirty-site replan.

**RR-02 — Over-extended target quotes create artificial cross-rule overlap and silent component drops (D02, D16).**
D16 p221: `G12:1 T014` span 0..101 (quote ends mid-G13 sentence, `其中，对持续持有期少于`) and `G13:0 Y007` composite `p221:0:101 + p222:0:30` are identical at p221. A correct G13 span starts at ~90, leaving the two edits adjacent. D16 made three Joint Compose calls overall; none produced an accepted edit at p221, and audit, sweep and claim all report the old text surviving. D02 p229 is the contained variant: `G12:1 T016` 0..147 and `G13:0 T017` 103..147; **no conflict is recorded**, both targets become `RECALL_PLAN_COMPONENT_DROPPED`, no edit exists at p229.
*Code*: `fundlex/recall.py:3591-3635, 4097-4133, 4547-4559, 4393-4479`. Fix: bind each operation's edit span to `resolve_occurrence(operation.old_text/alternatives)` inside the target location (target quote is a site/provenance anchor only). If a real overlap remains, record a conflict and one materially different Joint Compose; never emit `RECALL_PLAN_COMPONENT_DROPPED` without a reason.

**RR-03 — G16 append never receives a site (all four cases).**
`G16:B1:O1` is UNRESOLVED in every case; the required new text (`销售服务费每日计提。（1）直销机构…`) is absent from every working DOCX. Two independent gaps: `append_applicability_targets` requires **exactly one** qualifying member, but every contract repeats the sales-service-fee clause in body and summary (2 members) → no target; and `targets_for_open_rules('auto')` rejects appends because `strong` needs an `old_text` of ≥4 chars, which an append does not have. The model's wrong G16 targets (G17 residual sentence, p760/p1223 etc.) are correctly demoted `out_of_scope`, leaving nothing.
*Code*: `fundlex/recall.py:2344-2352`, `fundlex/targeting.py:640-647`. Fix: one append target per qualifying member (or per duplicate group, then clone); prefer the sibling delete site (G15/G17 payment clause) as the anchor; allow append ops that pass `append_site_ok` in auto discovery; regression with body+summary copies and with `每日计算` wording (D02).

**RR-04 — Absent-literal delete closure is hardcoded to G05 `备案`; G06 and D11 G05:2 can never close (all four).**
G06's literal is absent from all four originals and no semantic equivalent (“互相转换” / 不得+转换+份额类别) exists, yet G06 is UNRESOLVED in all four. D01/D02/D16 G05:2 pass `VERIFIED_ABSENT` at the real class-setup site (p135/p138/p133); D11 G05:2 is OPEN although p129 is the same clause and the filing literal is absent there — its target (`调整前基金管理人需及时公告`, operations `[]`) never got the operation key. `operation_site_bound` only allows a site-based absent proof for `G05` references all containing `备案`, and `_verified_site_closure` drops `state=absent` sites. Target discovery already treats an absent delete as closed (`operation_closed`), so the two layers disagree.
*Code*: `fundlex/generation/effects.py:206-213, 252-253, 333-336`, `claim_replay.py:1015-1020`, `targeting.py:601-602`. Fix: a first-class `document_absence_at_site` proof for any delete whose old_text/alternatives are absent from the whole original and whose site is a genuine rule site; keep rejecting headings/placeholders; reconcile with `operation_closed`; apply to G06/G05:2/G13/G15/G17.

### HIGH

**RR-05 — `DUPLICATE_SITE_UNEDITED` repair is unreachable (D16).** `replay_claims` emits the failure with only `location`; the repair branch requires `failure.get('locations')`, and the loop explicitly prefers non-duplicate failures. Result: D16 p823 body copy left unedited while p1307/p1308 summary copy is deleted. Code: `claim_replay.py:669-673`, `recall_pipeline.py:3373-3382, 3387-3389`.

**RR-06 — Claim-recovery is a global 2-attempt loop that stops on the first unrepairable obligation.** D01 attempts only G01, D02 only G06, D11 only G05:2, D16 only G06; respectively 5/4/2/5 open obligations never receive a claim-recovery attempt and get a generic “artifact recovery circuit breaker”. Code: `recall_pipeline.py:3373-3382, 3484-3538, 3617-3634`. Fix: per-obligation/site budget plus a separate global cap; continue to the next failure; record a terminal for each.

**RR-07 — Unresolved dedupe drops a distinct open obligation from the report and user summary (D01).** Dedupe key is `(kind, rule_id, location, code)`; G02:0 and G02:1 both have location `''` and code `CLAIM_OPERATION_UNPROVEN`, so G02:B1:O2 disappears from `unresolved` and `user_summary`, even though it is in `open_obligations`. The final safety net is `represented_rules` (rule ids), so it does not re-add it. Code: `recall_pipeline.py:3947-3961, 3990-3993`.

**RR-08 — Target ids are not unique and stale target entries are not reconciled with obligations (D01, D02, D16).** D02 has duplicate ids `Y011` (G18/G11) and `Y012` (G15/G18); `plan_by_target` is a dict keyed by target id, so the G15 `Y012` entry is lost and reported `RECALL_TARGET_UNRESOLVED` even though G15 is ARTIFACT_VERIFIED at p821/p1287. D01's `T3004` remains unresolved although G12:B1:O1 is ALREADY_SATISFIED at p229. Target ids are generated from independent counters (`f"Y{counter:03d}"` and `len(synthetic)+len(hits)+1`), with later rounds restarting at `len(synthetic)`. Code: `recall_pipeline.py:676, 817, 824, 523-526, 3924-3933`.

**RR-09 — Plan components can be dropped silently.** D02 p229 has no edit and no conflict; the only trace is `RECALL_PLAN_COMPONENT_DROPPED` on both targets. Downstream recovery sees `NOT_PLANNED`, re-plans the same dropped components, and stops on no-progress. Code: `recall.py:4547-4559`.

### MEDIUM

- **RR-10 — Recovery identity.** Audit contexts store `obligation_id=operation_id` (`G17:0`); the final D16 circuit-breaker entry is unattributed (`rule_id ''`, site p823) because the terminal is built from `replay.failures[0]` rather than the attempted context. (`recall_pipeline.py:1684-1690, 3617-3634`.)
- **RR-11 — History fidelity/budget key.** D02 executed a REBUILD but its history contains only `MARK_UNRESOLVED “unchanged”`; no-site decisions are constructed with an empty `budget_key`, bypassing policy accounting. (`recall_pipeline.py:3530-3538, 3561-3587`.)
- **RR-12 — False progress signals.** Audit “succeeded” means the issue key disappeared; D16 G17 p823 succeeded in round 1 and was wrong again in round 3 after a replan. D01 Joint Compose reused the same `context_sha256` four times (3 checkpoint reuses), so a failed request was replayed unchanged. (`recall_pipeline.py:3046-3056`; `recall.py:4393-4479`.)
- **RR-13 — Classification coherence.** One G17 obligation spans GENERATION (overlap) / TARGET (not planned) / EXECUTION (audit); sweep residuals carry a model-declared TARGET while claim residuals are GENERATION; `user_summary` says “clause not located” for a satisfied G12 p227 and for an occurrence-ambiguity rejection at G02 p91.
- **RR-14 — Report counts disagree.** D01 `blocking_unresolved=20` vs `open_obligations=6`; `operation_coverage.UNRESOLVED=26`; D16 `user_summary` repeats the same G12 p221/G17 p823 problem four times; `true_obligations=24` vs 34 ledger records (ONE_OF alternatives) is not explained.
- **RR-15 — Unattributed duplicate failure and audit-cap gap.** D16's `DUPLICATE_SITE_UNEDITED` has `rule_id ""`; D16 G01 `AUDIT_VERDICT_MISSING` is terminal at the global round cap although G01:B1:O1 is ARTIFACT_VERIFIED at p91. `VERIFICATION` is defensible, but the starvation is a recovery defect.
- **RR-16 — G02 split-paragraph occurrence.** D01 T3001/T3002 are bound to p91 yet rejected `RECALL_TARGET_OCCURRENCE_AMBIGUOUS` because the truncated quote (`…三种不同的`) does not contain `A类基金份额`; the audit reason cites `A类、B类` although the verified classes are A/C/D with subscription group A/D (no B).
- **RR-17 — Stale bundle index.** `index.json` still records `replay_results` at `682e68a`, `record_results {}` and baseline gate reasons (“D01 artifact not generated”), while this bundle's reports show D01 working artifacts. Regenerate before handoff.

## Focus items from the brief

### D01 G17 — composite vs `delete_residual_copy`

Confirmed. `Y006/Y007` composites cover `p759:0:52 + p760:0:24` and `p1222:0:52 + p1223:0:24`. `ensure_delete_targets` created `DEL001/DEL002` for the second sentence because the coverage map stores `target.quote` (first sentence) for each composite location. At p760/p1223 both targets are `G17:0` with identical `[0,24]` spans; `merge_edits` has no same-operation absorption, so both become `RECALL_EDIT_OVERLAP`. The plan has **0 G17 edits**; the artifact retains the full clause at all four sites. This is avoidable non-delivery, not a contract limitation.

### D16 G17 p823 — duplicate copy

Confirmed. `T019` (inventory, p823, 0..52) and `Y010` (survey composite `p823:0:52 + p824:0:24`) are the same operation with an identical span at p823 → conflict. `Y011` (`p1307:0:52 + p1308:0:24`) is planned and applied, so the summary copy is deleted while the body copy survives. `DUPLICATE_SITE_UNEDITED p823` is raised correctly, but the repair path is dead (RR-05): the failure has no `locations`, and the loop prefers G06. Audit round 1 had marked all four G17 sites complete; round 3 found p823 wrong again after a replan — the audit success was not artifact-grounded.

### D16 G12/G13 p221 — conflict

Confirmed. `G12:1 T014` 0..101 and `G13:0 Y007` `p221:0:101 + p222:0:30` overlap exactly at p221. The true G13 sentence starts at ~90; the survey part begins at 0, and T014's quote ends inside the G13 sentence. The spans are over-extended, not genuinely interleaved. D16 made three Joint Compose calls overall; none produced an accepted edit at p221, and no edit exists there; audit + sweep + claim all fail. D02 p229 is the contained variant and is dropped with no conflict at all (RR-02/RR-09).

### G06 / G16 recurring no-site

Confirmed and systematic. G06's literal is absent everywhere, so the correct terminal state is *already satisfied*; instead it is OPEN in all four cases because the only site-based absence proof is the G05 `备案` special case. G16's site demonstrably exists (the G15 payment clause with `销售服务费 … 每日计提/按月支付`), but the append pass refuses when the clause appears twice and auto discovery refuses appends. G16 is a true unmodified obligation in all four working artifacts.

### D02 G05:2 / G06 absent placeholder

- **G05:2 is fixed in D02**: `VERIFIED_ABSENT` at p138, a real class-setup paragraph, not a heading. D01 and D16 pass the same way. **D11 is the outlier**: p129 is the same class-setup clause and the literal is absent, but the target never got the operation key, so G05:2 stays OPEN. This is the same absence semantics producing different results by target shape (RR-04).
- **G06 is not fixed**: D02's absent target at p138 is rejected as a proof site and no document-wide absence proof exists. The same happens in D01/D11 (absent targets) and D16 (only misattributed survey targets).

## Answers to the audit questions

1. **Recovery actions/history** — bounded and policy-respecting (43 attempts, no over-limit group, no identical deterministic repeat, business rounds ≤3). Incomplete rather than unsafe: one claim failure per case starves the rest (RR-06), one executed REBUILD is unrecorded (RR-11), and audit identities are wrong (RR-10).
2. **Budget/retry identity** — the move to rule+site+operation/obligation (`history._same_subject`) is correct and target-id-independent. Remaining: manual decisions use an empty budget key; per-site budgets can multiply one operation across copies; Joint Compose bypasses the history and replays an identical context.
3. **Dirty-site routing** — a single `context.site_id` is too narrow for composite targets and duplicate copies: p823 needs p824, and p823 needs p1307/p1308. This contributes to dropping the body copy while keeping the summary copy.
4. **Duplicate-copy recovery** — G15 works (two verified sites per case, no divergence). G17 does not: same-operation conflict (RR-01) plus unreachable `DUPLICATE_SITE_UNEDITED` repair (RR-05).
5. **Open-target discovery** — G16 is never discovered (append pass single-member rule + auto `strong` gate); G06's absent target cannot become a site; absent/attributed placeholders are correctly rejected, so no unsupported proof.
6. **Unresolved classification** — every entry has a class, but they are stage-symptom labels; the same root cause spans three classes, sweep residuals are TARGET while claim residuals are GENERATION, and `user_summary` mislabels satisfied/ambiguous sites. G06/G16/G05:2's TARGET is defensible as “site not proven” but misdiagnoses “already absent” vs “site exists but not discovered”.

## No loss / no false proof

- **No true obligation silently lost at the gate.** All 24 true obligations per case are either site-verified or open and counted in `open_obligations`; no completion without evidence (0 of 91 evidence records lacked a site).
- **One silent loss in the human report.** D01 G02:B1:O2 is in `open_obligations` but absent from `unresolved` and `user_summary` (RR-07). D16's duplicate failure is unattributed (RR-15).
- **No unsupported site proof.** All 91 `ARTIFACT_VERIFIED`/`ALREADY_SATISFIED` evidence records were checked: every `before_quote` is an exact substring of the original paragraph at `site_id`; every non-empty `after_quote` is an exact substring of the final paragraph at that site. 0 violations. The HEAD rejection of absent/attributed placeholders is working.
- **No false completion.** All four cases are `incomplete`; only `working_final.docx`/`working_redline.docx` were published; `claim_verified=false`.

## 20-case recommendation

**Do not run the acceptance 20-case set yet.** Fix RR-01..RR-08 first (RR-09..RR-12 and RR-15/RR-17 before handoff), add regressions from the D01/D02/D11/D16 frozen targets, re-record all four cases at the new SHA, and confirm:

- G17: one composite delete per copy, no residual duplicate target, no `DUPLICATE_SITE_UNEDITED`.
- G12/G13: spans trimmed to the operation old_text, adjacent edits planned, no `RECALL_PLAN_COMPONENT_DROPPED`.
- G16: append target at the G15 payment clause, body and summary copies both edited.
- G06/G05:2: absent literal closes as `document_absence_at_site` in every contract shape.
- All open obligations appear in `unresolved`/`user_summary` and stale targets do not block.

A diagnostic 20-case run would not corrupt data (the gate is safe), but it would not be an acceptance run: with the current code every case will contain at least one false unresolved (G06) and at least one undelivered core obligation (G16), so the completion rate would not be attributable to contract difficulty.

## Evidence index

- Reports: `reports/{D01,D02,D11,D16}.json`
- Replays: `replay/{case}/report.json`
- Stage outputs: `summaries/D16-stage-*.json` (all stages replayed at the same head)
- Record/replay comparison: `summaries/full-replay-comparison.json` (all checks true, 0 HTTP)
- Frozen originals/guides: `frozen/{case}/original.docx`, `frozen/{case}/guide.json`
- Working artifacts: `artifacts/{case}/working_final.docx`, `working_redline.docx`
- Reproduction checks used here: evidence site binding (91 records, 0 violations), exact literal presence/absence in originals/finals (G06, G05:2, G16, G17), target-id uniqueness, and recovery-attempt/policy counts.
