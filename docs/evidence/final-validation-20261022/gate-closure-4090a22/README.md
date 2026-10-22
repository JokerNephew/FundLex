# 4090a22 Gate Closure Evidence

## Identity

- Runtime code HEAD: `4090a22462607852ca0862d64ddc2b1120bd3f03`
- Evidence HEAD: pending packaging commit
- Runtime tree SHA-256: `b327ca18df639a7df0d29f559fb1624397d754b5f45565540138501ca51b5b72`
- Guide source SHA-256: `b77be53c3439d785a9ffad0f09d8d03ba74f7722397576b999ae6f5dd6eef895`
- Guide document SHA-256: `45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7`
- Baseline `ff4d749` and `d5703de` evidence is preserved; this root does not overwrite it.

## Offline

- pytest: **1072 passed / 0 failed / 6 skipped / 2 warnings / 200.89s**
- compileall: PASS
- git diff --check: PASS
- log: `logs/pytest-4090a22.txt`

## Live record

| Case | Delivery | Calls | Tokens | Cost USD | Wall s | TRUE | Artifact verified | Already satisfied | Open | Claim |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| D01 | not_generated | 0 (budget blocked) | 0 | 0 | 0 | 24 | 0 | 0 | 24 | false |
| D02 | **complete** | 25 | 156558 | 0.02817000 | 158.65 | 24 | 14 | 10 | 0 | true |
| D11 | incomplete | 27 | 120635 | 0.02160615 | 142.64 | 24 | 13 | 10 | 1 | false |
| D16 | incomplete | 33 | 167737 | 0.03087780 | 462.53 | 24 | 15 | 9 | 0 | true |

D01 had no remaining live budget: the preceding `d5703de` attempt consumed the last 31 calls and stopped at sweep with `MODEL_GLOBAL_CALL_BUDGET_EXCEEDED`; the log is copied as `logs/D01-budget-stop-d5703de.log`. It is not a 4090a22 artifact and is not counted as a pass.

## Finding closure

- **G16** — CLOSED in D02: body and summary payment sites received the four-component append; actual DOCX shows both. D11/D16 additionally have the correct G16 content, but their delivery is held by other findings.
- **G17 same-operation duplicate** — CLOSED in D02/D16: composite/subset deletion no longer conflicts; G17 body and summary copies are deleted.
- **G12/G13 joint/replan** — D02 joint edit retained and artifact changed p229; D16 joint replacement produced the exact G12 text at p221 and removed the G13 p222 sentence.
- **G06 absence proof** — CLOSED: document-wide literal absence is a bounded delete proof and projects to ALREADY_SATISFIED in D02/D11/D16.
- **D11 G18** — duplicate-copy false completion is CLOSED as a safety issue: p1207 is now a required site and blocks; the remaining gap is a real missing target (p1207 still old), not a false PASS.
- **D01 G01/G02 split** — code has continuation rebinding and G02 fact-aware handling; D02 verifies equivalent split handling. D01 itself has no 4090a22 live artifact due budget.
- **Recovery starvation** — D02/D16 progressed beyond G06/G12/G13 failures and reached claim PASS; no first-failure starvation observed in the completed runs.

## Remaining blockers

1. **D01 live budget exhausted** — no current-code live artifact or replay. This is an external budget blocker; do not increase silently.
2. **D11 G18 p1207** — summary copy still has the old A/D/C fee wording. Claim replay correctly blocks; a duplicate target/repair at p1207 is still needed.
3. **D16 audit false block** — all 24 obligations and claim replay pass; final p221 is the exact G12 replacement, yet the G13 audit and a stale `T3001` unresolved entry keep delivery incomplete. This is a proof/review bookkeeping defect, not artifact content loss.

## Safety

- false delivery complete: **0**
- unauthorized paragraph edit: **0** (artifact review plan/actual mismatches = 0)
- cross-site/duplicate proof: **1** D11 G18 (correctly blocked)
- unsupported `VERIFIED_ABSENT`: **0**
- planned-but-not-artifact false PASS: **0**
- false review block: **1** D16 G13/T3001 audit

## Replay

D02/D11/D16 full replays: **0 HTTP, 0 tokens, 0 cost**, all 14 comparison checks PASS including artifact text. D01 has no 4090a22 replay. D02 used `final.docx`; for the generic comparison tool a byte-identical `working_final.docx` alias was created.

## Reviewer

Independent final review: `summaries/final-review-4090.md` / `.json`.
Counts: **BLOCKER 1, HIGH 4, MEDIUM 4, LOW 2**.
D02 is complete and credible; D11 is a real duplicate gap; D16 is content-correct but falsely blocked; D01 is unverified due budget.

## Gate

**DO_NOT_ENTER_20_CASE**

D02 is complete. D01 has no current-code live artifact, D11 has a real p1207 duplicate gap, and D16's all-PASS artifact is held by an unsupported audit/T3001 block. Fix the two D11/D16 issues, obtain a D01 budget decision, rerun exact-code records/replays/reviews, then decide the Gate again.
