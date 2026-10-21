# Independent architecture cross review

Reviewed branch: `refactor/recovery-architecture`
Base HEAD: `22c15aa4d8d736f2a2fc46a29bc3ed8611475f2f` with uncommitted final-validation fixes.
Scope: other agent changes in `recall.py` and `recall_pipeline.py`; this is not independent approval of this reviewer's own effects/Claim Replay implementation. Zero live model calls.

## Findings at review time

BLOCKER: 0
HIGH: 0 (CROSS-001 and CROSS-002 fixed and independently reverified)

### CROSS-001 — generated replacement is accepted as its own semantic authorization

`_quote_is_expected_effect` previously accepted an exact quote anywhere in a final component replacement if that quote was not in BEFORE. The whole-AFTER-quote branch likewise accepted a superset of expected policy without proving its extra wording was authorized.

An operation-bound, site-bound final component proves where an insertion occurred. It does not establish that every inserted sentence agrees with Guide semantics. Claim Replay permits unexplained soft wording, so semantic Audit must remain able to reject an exact contradictory inserted sentence.

Offline reproduction used `_negative_review_fixture` from `tests/test_final_validation_regressions.py`, with the first edit set to `content_source="composed"` and replacement:

```text
新的业务规则已经生效。但本规则实际上不产生任何效力。
```

The Guide new text was only `新的业务规则已经生效。`. A review returned `verdict=wrong`, an exact artifact quote `但本规则实际上不产生任何效力。`, and a reason identifying the contradiction. `_run_audit` returned:

```json
{"evidence_verified":true,"artifact_proven":true,"review_status":"REVIEW_UNPROVEN","review_evidence_status":"EXPECTED_EFFECT_QUOTED_AS_ERROR"}
```

The failure was independent of old-text/variant priority: the contradictory sentence was novel, not an old-text residual. The fallback was removed. Full paragraph evidence is now accepted only after same-site component reconstruction, per-component operation identity, TRUE applicability, local PASS proof, and instantiated Guide/bounded replacement checks. Direct-quote and full-paragraph regressions now confirm `artifact_proven=false` for the contradiction.

### CROSS-002 — Sweep recovery routes an existing target back to target discovery (fixed)

`_sweep_recovery_contexts` found an attributed target at the finding's operation/site, but initially classified `CLAIM_OPERATION_NOT_PLANNED`/`CLAIM_OPERATION_UNPROVEN` directly as `TARGET`. It now reuses `_claim_failure_context` for the matching operation/site. Independent re-run returned `GENERATION`, root cause `TARGET_EXISTS_NO_PLAN`, preserving the operation/site/source span. Parameterized routing regressions pass.

## Areas checked without additional HIGH/BLOCKER findings

- Atomic paragraph planning defers overlapping explicit ONE_OF alternatives to the existing alternative merge. It does not infer alternatives from a shared rule ID.
- Fuzzy clause completion keeps the source paragraph and start identity, limits tail extension, requires a sentence terminator and one structural segment, and is replayed by the content check.
- Local proof projection retains operation/obligation identity and occurrence site IDs. It does not use another paragraph's evidence.
- Certified class-fact arbitration requires value and complete-set verification, verified fee/class groups, every current class quote, and a bounded literal grammar.
- G16 outside-scope routing can legitimately accept an old payment mechanism as an append anchor. This is a candidate-routing decision, not completion; requiring the source to already contain all new components would be incorrect. An initial concern about that path was withdrawn.

## Source binding

- `fundlex/recall.py`: current working-tree review (post-fix; see final commit binding)
- `fundlex/recall_pipeline.py`: current working-tree review (post-fix; see final commit binding)
