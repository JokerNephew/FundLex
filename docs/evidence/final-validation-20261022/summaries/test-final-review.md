# Test Final Review

This read-only review is bound to branch `refactor/recovery-architecture` at HEAD `682e68a5b3ef2a58feb77460af70afabdb314379` and the exact-HEAD evidence root `docs/evidence/final-validation-20261022/`. No runtime source was changed by this review.

## Offline regression

The exact-HEAD log `logs/pytest-682e68a.txt` records:

- command: `.venv/bin/python -m pytest tests -q`
- result: **1024 passed, 0 failed, 6 skipped**, 2 warnings
- elapsed: 200.45 seconds
- `compileall` and `git diff --check`: PASS

The warnings are the existing Starlette/httpx deprecation and the intentional duplicate DOCX zip test warning. The six skips are conditional tests for unavailable optional integrations/fixtures; they are not failures.

## Frozen replay and cassette fail-closed

All replay checks below were run with `httpx.Client.send`, `httpx.AsyncClient.send`, and `ModelGateway.from_env` replaced by a function that raises. The recorded HEAD matched the replay HEAD and network attempts were zero.

- D02: `summaries/test-stage-replay-D02.json`. `facts`, `applicability`, `targets`, `obligations`, `plan`, and `claim_replay` all replayed successfully; plan revisions 1/2 and claim-replay revision 1 also replayed successfully. Each repeated replay had equal semantic output. A real recorded cassette hit used a `None` client and zero attempts; a deliberate absent request failed with `MODEL_REPLAY_MISS`, zero HTTP attempts; revision 99 failed with `FROZEN_STAGE_INPUT_MISSING`.
- D11: `summaries/test-stage-replay-D11-D16.json`. All six stages replayed successfully, repeated outputs were equal, `same_head=true`, and model calls were zero.
- D16: `summaries/test-stage-replay-D11-D16.json`. All six stages replayed successfully, repeated outputs were equal, `same_head=true`, and model calls were zero.
- D01: the earlier exact-HEAD stage evidence is `summaries/D01-replay.json` and the recorded stage probes. `facts`, `applicability`, `targets`, and plan revisions replayed with zero live model calls; `obligations` and `claim_replay` correctly failed closed because those stage boundaries were never recorded after the generation failure. No missing boundary was filled from another run.

The frozen manifests for D02, D11, and D16 verified successfully. These results establish replay mechanics and fail-closed behavior; they do not make a failed claim replay pass.

## Current-HEAD real case evidence

`review_artifacts.py` independently compared each source DOCX, final edit set, and actual `working_final.docx` without a model. It was run for D01, D02, D11, and D16.

| Case | Delivery | TRUE obligations | TRUE→NOT_APPLICABLE | Artifact review | Plan/artifact | Redline check |
|---|---|---:|---:|---|---|---|
| D01 | `not_generated` | 24 | 0 | UNVERIFIED (no artifact) | unavailable | unavailable |
| D02 | `incomplete` | 24 | 0 | PROGRAMMATIC_REVIEW | 0 mismatches | accepted=final, rejected=original |
| D11 | `incomplete` | 24 | 0 | PROGRAMMATIC_REVIEW | 0 mismatches | accepted=final, rejected=original |
| D16 | `incomplete` | 24 | 0 | PROGRAMMATIC_REVIEW | 0 mismatches | accepted=final, rejected=original |

The artifact review reported zero paragraph-level plan/artifact mismatches for D02, D11, and D16. It also verified the DOCX revision projections: accepted redline text equals the final DOCX and rejected redline text equals the original DOCX. This is serialization evidence, not evidence that every business operation passed.

### Operation/site proof observations

All four reports preserve 24 applicability-TRUE obligations and none projects a TRUE obligation to `NOT_APPLICABLE`. The per-operation rows are in `summaries/D01-artifact-review.json` (no artifact), `D02-artifact-review.json`, `D11-artifact-review.json`, and `D16-artifact-review.json`.

- D02 has deterministic PASS for the actual G02:1/G04:1 already-satisfied sites, G05:0, G05:2, G06:0, G12:1, G13:0, G15:0, G17:0, and G18:0. G02:0 and G04:0 have real p93/p135 already-satisfied evidence but the overall operation is blocked by an unrelated absent summary placeholder.
- D11 has PASS evidence for the recorded edits and already-satisfied sites, including G04:0/G04:1, G05:0, G06:0, G08/G09, G11/G12/G13/G14, G15, G17, G18, and G22. G01 and G02:0 remain proven missing; G05:2 and G16 remain unproven.
- D16 has PASS for G02, G03, G04, G08/G09, G11, G14, G15, G18, and G22, while G01, G05:0, G12:0, G13:0, G16, and G17 retain exact residual/missing/unproven evidence.

## P0 finding: absent placeholders are being treated as business sites

The current report evidence exposes a generic proof bug requiring the main agent's fix and regression coverage. In D02, the target for the absent summary window at `p1036` has `state=absent` and is only a heading placeholder, but it is included in operation sites. As a result:

- G05:2 receives `VERIFIED_ABSENT` from the unrelated p1036 heading in addition to its legitimate p138 deletion site; G06:0 receives `VERIFIED_ABSENT` solely from the unrelated p1036 heading despite having no verified business site.
- G02:0 and G04:0, which have valid already-satisfied proof at p93/p135, are turned into overall failures because the same absent placeholder is included as a required site.

This is a real P0 evidence/proof defect, not a model opinion. Absent, rejected, or unattributed placeholders must not enter the required site set used by `OperationEffectEvaluator`; TRUE operations must remain OPEN/UNRESOLVED until a valid operation-specific business site is proved.

Other case blockers remain real fail-closed evidence: D01 has no final artifact after `EDIT_OVERLAP_OR_ADJACENT`; D16 retains exact G05/G13/G17 old-text residuals; D11 has a missing G01/G02:0 effect and unproven G05:2/G16; D02 has unresolved operation/site failures despite a serialization-consistent artifact.

## Test-review gate

This review confirms exact-HEAD offline tests, replay isolation, cassette miss fail-closed behavior, revision selection, stage boundaries, and artifact serialization. It does **not** support entering the 20-case gate: D01 has no artifact, all four cases are incomplete, the absent-placeholder P0 remains, and independent business/recovery/architecture review and any required fix/re-record are still outstanding.

**Recommendation: DO_NOT_ENTER_20_CASE.**
