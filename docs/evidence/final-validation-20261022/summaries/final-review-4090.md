# FundLex final review — runtime `4090a22` (read-only)

- **Reviewed head:** `4090a22462607852ca0862d64ddc2b1120bd3f03` (detached worktree `/home/opencode/fundlex-a5ed315`)
- **Evidence root:** `/home/opencode/fundlex/docs/evidence/final-validation-20261022/gate-closure-4090a22`
- **Baseline root:** `/home/opencode/fundlex/docs/evidence/final-validation-20261022/revalidation-ff4d7498`
- **Method:** local inspection of frozen reports, claim replay, DOCX text, ledgers and logs. No live model/HTTP calls, no code/test/git edits, no evidence mutation except this report.
- **Verdict:** **GATE HOLD — do not enter the 20-case run.**
- **Counts:** **BLOCKER 1 · HIGH 4 · MEDIUM 4 · LOW 2**

Paragraph labels below use the reports' 0-based indices (`pN` = paragraph index N); Word's visible numbering is +1.

## 1. Case results

| Case | Delivery | TRUE obligations | ARTIFACT_VERIFIED | ALREADY_SATISFIED | NOT_APPLICABLE | UNRESOLVED | Blocking | Finding |
|---|---|---|---:|---:|---:|---:|---:|---|
| D01 | `not_generated` | 24 | 0 | 0 | 10 | 24 | — | No 4090a22 artifact; D01 budget 0. **BLOCKER** |
| D02 | `complete` | 24 | 14 | 10 | 10 | 0 | 0 | Credible complete; plan/artifact consistent. |
| D11 | `incomplete` | 24 | 13 | 10 | 10 | 1 | 1 | Real missed duplicate G18 at `p1207`; correct fail-closed. **HIGH** |
| D16 | `incomplete` | 24 | 15 | 9 | 10 | 0 | 3 | All obligations PASS, but 2 false audit blocks + 1 stale target block. **HIGH** |

D02/D11/D16 counts are identical between record and replay. D01 has no record, replay or artifact in the 4090a22 bundle.

## 2. D02 — complete and internally consistent

- 24 TRUE obligations: 14 ARTIFACT_VERIFIED + 10 ALREADY_SATISFIED, 0 unresolved; `claim_replay.verified=true` (17 checked / 21 units); audit issues 0; errors 0.
- Plan: 17 edits; DOCX diff: exactly the same 17 paragraphs; `plan_artifact_mismatches=[]`; redline 17 insertions / 17 deletions, accepted revision == final and rejected revision == original.
- **G16:** append present at `p821` (body) and `p1287` (summary copy); audit completed both.
- **G17:** composite delete applied at `p822`+`p823` and `p1288`+`p1289`; audit completed all four target units.
- **G06:** authorised literal absent document-wide (0 matches); `ALREADY_SATISFIED` through the new 4090a22 `document_literal_absent` path. Spot checks confirm the literal is genuinely absent from original and final.
- G12/G13 joint edit at `p229` is exactly the guide-required text; audit explicitly says “未丢失要求内容”.
- G18 was applied to both copies (`p848` body, `p1257` summary), which is the correct duplicate-copy behaviour.
- The report's “G16 audit 2/4” denominator includes two `TARGET_SOURCE_MISMATCH` (not-applicable) targets; not a defect.

**Conclusion:** D02's `complete` claim survives independent plan/artifact and text checks.

## 3. D11 — real missing duplicate, correctly failed closed

- 24 TRUE obligations: 13 ARTIFACT_VERIFIED + 10 ALREADY_SATISFIED + 1 UNRESOLVED; `claim_replay.verified=false`; 14 edits, 14 changed paragraphs, 0 plan-artifact mismatches; redline 14/14 consistent.
- The unresolved item is `G18:B1:O1` at `p1207`: `CLAIM_OPERATION_NOT_PLANNED`, “operation effect is not proven at every verified site”.
- **The duplicate is real.** The contract contains the G18 sentence twice:
  - `p800` (body): edited to `由于本基金A类、D类基金份额和C类基金份额费用收取不同…`
  - `p1207` (summary copy): still `由于本基金 A 类基金份额和 D 类基金份额不收取销售服务费，而 C 类基金份额收取销售服务费…`
- The target ledger contains only the `p800` G18 target (`S03_S04_S07_S16_S17_S20_S26#1:T019`); there is no target for `p1207`. The audit completed G18 1/1 and the sweep only saw `p800`. Claim replay found the second occurrence and blocked delivery.
- D02 handled the equivalent duplicate correctly (`p848` + `p1257`); this is therefore an inconsistent duplicate-recall gap, not a false block.
- G16 (`p772` + `p1247`), G17 (`p773` + `p1248`) and G06 (literal absent document-wide) are correctly closed.

**Answer:** real missing duplicate target; the delivery block is **correct fail-closed**, not a false Review block. D11 is not a complete contract.

## 4. D16 — content correct, but two false audit findings and one stale target block

- 24 TRUE obligations: 15 ARTIFACT_VERIFIED + 9 ALREADY_SATISFIED, 0 unresolved; `claim_replay.verified=true` (18/23); 18 edits, 18 changed paragraphs, 0 plan-artifact mismatches; redline 18/18 consistent.
- Delivery is `incomplete` with `blocking_unresolved=3`: `T3001` target plus two G13 audit issues.
- **G16:** append at `p822` (body) and `p1306` (summary); **G17:** deletes at `p823`/`p824` and `p1307`/`p1308`; **G06:** literal absent document-wide. All content checks pass.
- **G12/G13 at `p221`/`p222`:** final `p221` is exactly the guide's G12:1 `new_text`:
  `赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用全额计入基金财产。`
  `p222` is blank, so the 7-day/1.5% sentence is gone.
- The audit's two issues are **false/unsupported**:
  1. “This new sentence … the guide does not state.” The guide's G12:1 `new_text` states exactly that sentence.
  2. “The replacement eliminated the pre-existing allocation rule, which G13 did not require deleting.” True that G13 did not require it, but **G12:1's `old_text` includes that allocation rule and its `new_text` replaces the whole clause without it**. The removal is G12-authorised; the audit attributed a G12 effect to G13's narrower delete scope.
- Cross-case proof: the identical joint edit is **accepted** in D02 (audit: “未丢失要求内容”) and D11 (audit: “剩余文字属于 G12 的授权改写”). D16's audit is the outlier.
- Root cause: D16's target rationales uniquely add a requirement not in the guide — “同时保留原有归入比例规则不应被一并删除” (`T015`) and “不得连带删除原有的赎回费归入基金财产比例规则” (`T016`). The audit appears to enforce that model-authored rationale.
- The audit re-ran 3 business rounds (`business_rounds_used=3`), spent ~311 s in audit recovery, and repeated the same two G13 issues in rounds 1–3 (round 0 saw the pre-replan state).

**Answer:** the D16 Review block is a **false/unsupported audit finding**, not a real content-loss finding. The DOCX complies with the certified guide.

## 5. D16 — `T3001` is also a false block

- `frozen/D16/targets.json` `T3001` (G12, `p219`, origin `T3_open_rule`, candidates `p219/p222/p223`) has `resolution=unresolved`, `status=not_planned`.
- Its audit record is `completed`: “p219 … is an authorized G09 edit, not a G12 obligation; … No G12 content is missing or contradicted at p219.”
- `p219` contains the G09 redemption-amount edit, not a G12 clause. No G12 old-text variant remains.
- Despite audit completion, the target is still counted in `blocking_unresolved`, so D16 would remain incomplete even after the G13 audit issue is fixed.

**Answer:** stale target-resolution projection; fix required independently of the audit fix.

## 6. D01 — no current-code live artifact

- 4090a22 `index.json` gives D01 **0** remaining HTTP attempts (`previous_calls=192`).
- No `artifacts/D01`, `replay/D01` or `frozen/D01` exists in `gate-closure-4090a22`; the runtime ledger root `/tmp/opencode/final-validation-4090a22` has only D02/D11/D16.
- The last D01 live run is in `gate-closure-d5703de/summaries/D01-record.json`: 31 calls, delivery `not_generated`, stop `MODEL_GLOBAL_CALL_BUDGET_EXCEEDED` at stage `sweep`, no DOCX artifact (only binding/report/edits).
- Therefore D01's current-code behaviour (including the claimed stable-identity/replan fix) is **unverified at 4090a22**; 4/4 exact-code delivery evidence is not established.

**BLOCKER.**

## 7. Record / replay verification

| Case | Record HTTP | Record logical | Replay HTTP | Replay cassettes | Semantic counts | Artifact text | DOCX bytes |
|---|---:|---:|---:|---:|---|---|---|
| D02 | 25 | 25 | 0 | 25 | equal | equal (`document.xml` identical) | differ only in ZIP timestamps |
| D11 | 27 | 27 | 0 | 27 | equal | equal | differ only in ZIP timestamps |
| D16 | 33 | 44 | 0 | 44 | equal | equal | differ only in ZIP timestamps |
| D01 | — | — | — | — | no artifact | — | — |

- Replay reports: `http_attempts=0`, `tokens=0`, `cost_usd=0`; 100% of events are `replayed=true`; no replay error.
- Record D16 has 11 in-run cassette replays (44 logical, 33 HTTP), i.e. repeated identical requests served from this run's own cassettes; not foreign-run data and not a live-HTTP violation, but the summary's `calls=33` vs report `logical_calls=44` should be labelled.
- Record/replay artifact hashes differ because DOCX ZIP entry timestamps differ; every ZIP part, including `word/document.xml` and `docProps/core.xml`, is byte-identical, and paragraph text is identical.

## 8. G16 / G17 / G06 closures

| Rule | D02 | D11 | D16 |
|---|---|---|---|
| G16 | append `p821`, `p1287` | append `p772`, `p1247` | append `p822`, `p1306` |
| G17 | delete `p822`+`p823`, `p1288`+`p1289` | delete `p773`, `p1248` | delete `p823`+`p824`, `p1307`+`p1308` |
| G06 | literal absent document-wide, 0 matches | same | same (but spurious survey targets remain) |

All three closures are content-correct. D16 has bookkeeping residue: G06 survey targets `Y005`/`Y006` (+ duplicates `Y033`/`Y034`) at `p431`/`p1169` remain `needs_edit` even though G06 is `ALREADY_SATISFIED`; they are non-blocking.

## 9. Findings

### BLOCKER

- **B1 — D01 has no exact-code artifact.** D01 budget is 0; last live run at d5703de stopped on `MODEL_GLOBAL_CALL_BUDGET_EXCEEDED`; no 4090a22 D01 artifact/replay/ledger. 4/4 exact-code gate evidence cannot be asserted.

### HIGH

- **H1 — D16 G13 audit false block (joint G12/G13 edit).** Final `p221` exactly matches guide G12:1 `new_text`; the 7-day clause is gone; the allocation-rule removal is G12-authorised. Audit claims “guide does not state” (false) and flags G13 for a G12 effect. D02/D11 accept the identical edit. All 24 obligations PASS and claim replay is true, yet delivery is incomplete. 3 business rounds / ~311 s spent; same issues repeated in rounds 1–3.
- **H2 — D11 G18 real duplicate missed at `p1207`.** Body `p800` edited; summary `p1207` unchanged; only one G18 target exists. Claim replay correctly fails closed, but the case is not deliverable. Audit/sweep missed the duplicate; D02 handled the equivalent duplicate correctly.
- **H3 — Evidence index/offline log not finalized for 4090a22.** `gate-closure-4090a22/index.json` has `record_results={}`, `replay_results` from head `682e68a`, stale totals (122 calls / $0.1146 vs current 85 / $0.08065), stale gate reason, and an offline log path `logs/pytest-682e68a.txt` that is absent from the bundle. The actual exact-code run (`/tmp/opencode/pytest-4090a22.log`) is **1072 passed, 6 skipped, 2 warnings in 200.89 s**, but it is not archived; the outer `index.json` still names 682e68a.
- **H4 — D16 `T3001` false blocking target.** Audit completed `T3001` as “no G12 content missing” but the target remains `unresolved`/`not_planned` and is counted in `blocking_unresolved=3`. D16 would stay incomplete even after H1.

### MEDIUM

- **M1 — D16 G06 survey targets left dirty.** `Y005`/`Y006`/`Y033`/`Y034` remain `needs_edit` while G06 is `ALREADY_SATISFIED` via document-wide absence; non-blocking ledger inconsistency.
- **M2 — D16 G16 duplicate targets mislocated.** `T019` at `p824` and `T017-D1` at `p1308` point to G17 “usage” sentences; the actual G16 copies are `p822`/`p1306` and are correct. G16 audit is 2/4 because of this binding.
- **M3 — Replay DOCX byte hashes differ from record.** D02 `7d348226…` vs `40168e69…`; D11 `86f134a9…` vs `f8526729…`; D16 `0eb39022…` vs `913e9c44…`. All ZIP parts and text are identical; only entry timestamps differ. The manifest binds only the record hash.
- **M4 — `calls` semantics differ between summary and report.** D16 summary `calls=33` vs report `logical_calls=44` (11 in-run cassette replays); D01 summary 31 vs logical 33. Not a live-HTTP violation, but budget/evidence metrics are ambiguous.

### LOW

- **L1 — Duplicate business notices.** The same `CONTRACT_POSSIBLY_ERRONEOUS` warning is emitted once per body/summary site (D02/D16 two identical entries); cosmetic.
- **L2 — 0-based paragraph labels.** Reports use `pN` as a 0-based index while Word numbering is 1-based (`p221` is Word paragraph 222); cite carefully when comparing audit text to the DOCX.

## 10. Gate recommendation

**HOLD — do not enter the 20-case run.**

Required before entry:

1. **D01:** authorise/resume budget and produce a 4090a22 record + artifact + replay, or obtain an explicit user waiver. Without this, 4/4 exact-code evidence is impossible.
2. **D16:** fix joint-edit audit attribution (G13 must check only its delete effect; a G12-authorised replacement must not be reported as G13 content loss) and do not enforce model-authored target rationales that contradict the guide; project audit completion into `T3001` resolution or discard the duplicate candidate. Re-run/replay D16 to `complete`.
3. **D11:** add deterministic duplicate-copy target generation/audit for G18 (edit `p1207` as well as `p800`), then re-run/replay to `complete`.
4. **Evidence:** finalise `gate-closure-4090a22/index.json` with 4090a22 `record_results`/`replay_results`, correct totals and gate reason, archive the exact-HEAD pytest log, and label/remove the stale 682e68a data from this bundle.

D11/D16 each consumed less than half of their allocated attempt budget in this attempt, so one re-run each is affordable. D01 has no remaining budget.

**Can enter 20-case now: NO.** D02 is complete; D11 is a real incomplete delivery; D16 is a false-blocked correct delivery; D01 has no current-code evidence.
