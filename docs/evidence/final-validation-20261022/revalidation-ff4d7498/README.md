# ff4d7498 Exact-Code Validation

## Identity

- Runtime code HEAD: `ff4d7498b6c1aee72ba48686074d021fc7f84791`
- Evidence base HEAD: `387e334869fdb77954b8b97270e393c044105e3d` (docs/evidence archive commit; not a runtime revision)
- Evidence HEAD: `2bc40c1` (validation bundle commit; a docs-only packaging commit follows); the runtime tree is byte-identical to `ff4d7498` (`runtime_tree_sha256=7ad22dc0dfe38bf7d8431ee437e7c5f6575a4f3a8155164d24559028d14e27a2`)
- Baseline evidence, not overwritten: `docs/evidence/final-validation-20261022/` bound to `682e68a`
- Guide internal source SHA-256: `b77be53c3439d785a9ffad0f09d8d03ba74f7722397576b999ae6f5dd6eef895`
- Guide document SHA-256: `45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7`
- Guide JSON file SHA-256: `2dfe00e3506d8aea1363574103d9efb9c49d7c4ac28fdb2375c6b85481f6db17`
- Branch: `refactor/recovery-architecture`

## Offline regression

- `python -m pytest tests -q`: **1061 passed, 0 failed, 6 skipped, 2 warnings, 207.10s**
- `python -m compileall -q fundlex tests`: PASS
- `git diff --check`: PASS

Logs: `logs/pytest-ff4d749.txt`, `logs/compileall-ff4d749.log`, `logs/diff-check-ff4d749.log`.

## Live record (exact output of ff4d749)

| Case | Calls | Tokens | Cost USD | Wall s | Delivery | TRUE | ARTIFACT_VERIFIED | ALREADY_SATISFIED | UNRESOLVED | Claim |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|
| D01 | 32 | 129785 | 0.02354340 | 171.02 | incomplete | 24 | 11 | 7 | 6 | false |
| D02 | 35 | 202288 | 0.03701985 | 336.86 | incomplete | 24 | 11 | 8 | 5 | false |
| D11 | 29 | 120716 | 0.02172765 | 167.89 | incomplete | 24 | 13 | 8 | 3 | false |
| D16 | 34 | 185719 | 0.03513165 | 420.50 | incomplete | 24 | 11 | 7 | 6 | false |
| **Total** | **130** | **638508** | **0.11742255** | **1096.27** | **0/4 complete** | **96** | **46** | **30** | **20** | **0/4 PASS** |

`TRUE → NOT_APPLICABLE = 0` in every case. All four generated real `working_final.docx` and `working_redline.docx`. Plan conflicts remain in D01 (2) and D16 (2); D02 and D11 have 0 conflicts.

## Replay and artifact review

- Full zero-network replay: all four cases matched record semantics for facts, scope, targets, attribution, obligations, plan, claim replay, delivery, unresolved, recovery and audit recovery; **0 HTTP, 0 tokens, 0 cost**.
- `compare_frozen_replay`: **4/4 passed all 14 checks**, including identical artifact paragraph text (`summaries/full-replay-comparison.json`).
- D16 six-stage replay: facts/applicability/targets/obligations/plan/claim_replay all `same_head=true`, `model_calls=0`, no network. Base plan and revision 3 are recorded separately: `D16-stage-plan-base.json` (12 edits, 4 conflicts) and `D16-stage-plan-rev3.json` (14 edits, 2 conflicts).
- Actual DOCX review, all four: `plan_artifact_mismatches=[]`; redline accepted text == final and rejected text == original; final revision elements = 0; changed paragraphs 14/16/14/14.

## Old finding closure

| Finding | Old HEAD | New HEAD | Result |
|---|---|---|---|
| D01 overlap / no `working_final` | 682e68a | ff4d749 | **PARTIAL/OPEN** — artifact now exists and the old G08 overlap is gone, but G17 same-operation duplicates still conflict (`p760`, `p1223`) and old G17 text survives at `p759/p760/p1222/p1223`. |
| D02 absent placeholder heading as verified site | 682e68a | ff4d749 | **CLOSED** — heading `p1036` is rejected; G05:2 is proved at real class setup `p138`; G06 remains OPEN, not false `VERIFIED_ABSENT`. |
| D11 G02 A/D delimiter false missing | 682e68a | ff4d749 | **CLOSED** — G02/G04 are `ALREADY_SATISFIED` at `p91/p126`; guard checks A/D vs A/C and A/D vs A/C/D both FAIL. |
| D16 G05 wrong site `p427/p1165` | 682e68a | ff4d749 | **CLOSED** — G05 proof sites are `p133` only; `p427/p1165` are inert `survey_satisfied` rows, not evidence. |
| D16 Audit B-class contradiction | 682e68a | ff4d749 | **CLOSED in D16** — certified facts A/C, no B-class audit contradiction. A separate D01 G02 B-class false audit remains (new HIGH). |

## Safety

- False delivery `complete`: **0** (all four are truthfully incomplete).
- Obligation-level false completion: **1** — D11 G18 is `ARTIFACT_VERIFIED` from body `p800`, while summary copy `p1207` still contains the old A/D service-fee wording.
- Audit false completion: **1 group** — D02 target audits mark G12/G13 `completed`, while `p229` is unchanged and sweep/claim correctly report `pending`/`NOT_PLANNED`.
- Unauthorized paragraph edit: **0** (`plan_artifact_mismatches=[]`; all changed paragraphs are plan edits).
- Cross-site / duplicate-copy proof: **1** — D11 G18 summary `p1207`.
- Unsupported `VERIFIED_ABSENT`: **0** in these runs; heading/absent placeholders are rejected.
- Planned-but-not-artifact false PASS: **0** at Claim; but D02 audit false completion above remains a proof-model defect.
- False review block: **1** — D01 G02 audit demands the guide placeholder `B类` despite certified A/C/D facts.

## Remaining blockers / root causes

1. **G16 never sited (all four).** G15 deletes the payment clause, but no G16 append target/edit is produced (D01 `p758/p1221`, D02 `p821/p1287`, D11 `p772/p1247`, D16 `p822/p1306` blank). The required four-component mechanism is absent from every artifact.
2. **Same-operation duplicate/subset conflicts.** `ensure_delete_targets` measures composite coverage using `target.quote` only, so it recreates a residual target; `merge_edits` has no same-operation absorption rule. D01 G17 produces 0 edits; D16 G17 edits the summary copy but leaves body `p823/p824`; this also creates `DUPLICATE_SITE_UNEDITED` and false residual blocks.
3. **D02 G12/G13 joint compose regression.** Baseline plan had the validated `p229` joint edit; `replan_sites.bind_reference` drops it because one joint edit carries `G12:1+G13:0` while no single target carries both. Artifact `p229` is unchanged.
4. **D16 G12/G13 target geometry.** `Y007`/related targets span the whole paragraph or a split clause, creating an artificial `RECALL_EDIT_OVERLAP` at `p221`; the correct result is a joint edit, not a relaxed guard.
5. **G06 absent-literal proof missing (4/4).** The G06 sentence is absent document-wide, but there is no site-scoped/document-wide absence proof; all four remain OPEN.
6. **D01 split G01/G02.** G01 append is not sited at the split definition (`p91/p92`); G02's locator picks heading `p91` and the audit falsely demands `B类` even though the contract already has A/C/D.
7. **D11 G05:2 false block.** The same class-setup absence proof that closes D01/D02 is not applied at D11 `p129`.
8. **Evidence bookkeeping**: old index was stale; this revalidation `index.json` is regenerated. The old `682e68a` bundle remains untouched.

## Independent reviewers

- **Business** (`summaries/business-review-ff4d749.md`): **BLOCK**. All four artifacts are not deliverable; obligation-level false completion at D11 G18; D02 audit false completion; G16 missing; D01 G01/G17 and D16 G12/G13/G17 real gaps.
- **Architecture** (`summaries/architecture-review-ff4d749.md`): **HOLD**. No false delivery complete proven; 4 BLOCKER engine bugs (F1–F4), plus F5/F6 highs; 4/4 incomplete due engine defects, not model quality.
- **Recovery** (`summaries/recovery-review-ff4d749.md`): **4 BLOCKER / 5 HIGH / 8 MEDIUM**. No unsupported site proof and no false completion, but recovery cannot deliver G17 duplicates, G12/G13 split clauses, or G16 append; G06/G05:2 become permanent false blockers.
- **Test** (`summaries/test-review-ff4d749.md`): **CONDITIONAL PASS** on offline/replay/artifact evidence; TR-01 stale index and TR-02 stage-plan identity were identified and are corrected here.

## Gate

**DO_NOT_ENTER_20_CASE.**

Reason: 4/4 exact-code cases are incomplete, G16 is missing in every artifact, same-operation duplicate conflicts leave G17 text, D02 G12/G13 joint compose is a regression, D11 G18 has duplicate-copy false proof, D16 G12/G13 remains residual, and G06 is unprovable. This bundle is valid failure evidence and reproducible, not an acceptance pass. The old `682e68a` bundle was preserved.
