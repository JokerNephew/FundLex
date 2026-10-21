# D01 frozen diagnosis: duplicate incremental-plan component

- Reviewed SHA: `682e68a5b3ef2a58feb77460af70afabdb314379`.
- Case: D01; original SHA256: `2f2f7a36000af8135feb625c0c7d6f9f3e8b291d1628f0879993d6987e2d278d`.
- Guide document SHA256: `45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7`.
- Classification: `REAL_ENGINE_BUG / RECOVERY_FAILURE / GENERATION_FAILURE`, HIGH. The writer correctly rejects overlapping executable edits; no writer defect was demonstrated.
- No runtime source changes; no live calls; full replay reports `calls=0`, `tokens=0`, `cost_usd=0`. Both synchronous and asynchronous HTTP send paths are forbidden in the probe/replay process.

## Reproduction

```bash
.venv/bin/python docs/evidence/final-validation-20261022/diagnostics/D01-validate-plan-probe.py
```

The probe replaces only in-memory `validate_edit_plan` references and invokes the normal exact-HEAD replay runner. It retains the original exception behavior. Full workflow replay completed in 34.39 seconds and reproduced `delivery=not_generated`, `EDIT_OVERLAP_OR_ADJACENT`, stage `audit`, with 24 TRUE obligations and no final artifact. The frozen cassette was not modified.

The first four validator calls pass (14, 14, 17, and 17 incoming edits). The fifth call receives 16 edits and rejects exactly one conflicting pair:

| Field | Retained old component | Fresh component |
| --- | --- | --- |
| Rule / operation | G08 / G08:0 | G08 / G08:0 |
| Obligation | G08:B1:O1 | G08:B1:O1 |
| Site / range | p226 / [5, 50] | p226 / [5, 50] |
| Target suffix | T007 | T010 |
| Replacement | identical authorized G08 policy | identical authorized G08 policy |

Both target IDs have the prefix `S03_S04_S07_S16_S17_S20_S26#1:`. This conflict does not involve G17/Y007 at p1222/p1223.

Caller stack:

```text
process_recall_first  recall_pipeline.py:3207
_plan_and_generate    recall_pipeline.py:1116
validate_edit_plan    docx.py:686
```

## Generic root cause

`replan_sites()` (`fundlex/recall.py:4593`) treats inventory `target_id` as stable across inventory refreshes. In this recording the same ID was reassigned to different operations and sites. It also expands `dirty_ids` in the same single pass in which it retains old edits, then concatenates those retained edits with a new plan selected by the expanded IDs.

The third planning boundary (`frozen/D01/stages/plan-2.json`) has initial dirty locations p130, p228, p229, and p91. The failure follows directly from the frozen data:

1. Old G08 `T007 @ p226` is outside the initial dirty locations and is retained.
2. Old G12 `T010 @ p229` is at a dirty location, so `T010` is added to `dirty_ids`.
3. In the refreshed target list `T010` now identifies G08 `@ p226` (old G12 is now `T015`).
4. G08 `T010 @ p226` is therefore replanned despite its old component already being retained.
5. `retained_edits + fresh["edits"]` contains both identical G08 replacements, and the unchanged hard validator correctly rejects them.

The same target-ID reuse additionally invalidates unrelated retained components: old G05 `T003 @ p135` collides with current G03 `T003 @ p130`; old G14 `T012 @ p231` collides with current G10 `T012 @ p228`; old G18 `T015 @ p785` collides with current G12 `T015 @ p229`. These are distinct business operation/sites and must not share a dirty identity merely because Inventory reused a serial number.

The report still shows the previous successful 17-edit plan because `report["plan"]` is updated after `_plan_and_generate()` returns. The rejected 16-edit candidate is therefore visible only in the captured validator input and planning boundary. It is incorrect to infer the actual rejected candidate from the report's prior plan.

## Smallest general fix to consider after all four current-SHA records

Use source site/part closure and stable operation/site/occurrence identity to select old components for invalidation and current targets for replanning. A composite component requires all its source parts to be replanned together. Do not carry old inventory serial IDs into the refreshed target universe. Compute the dirty closure before deciding which old edits to retain, then reconcile ledger entries against the resulting final component set using the same stable identities. Keep the existing hard validator unchanged.

Required regressions: IDs reassigned across rules after discovery; same operation/site receiving a new ID; composite source-part closure; distinct same-paragraph occurrences; retained-plus-fresh executable geometry and final ledger consistency. No fix is implemented by this diagnostic task.

## Evidence

- `D01-validate-plan-capture.json`: all five incoming executable edit sets and full caller/exception stacks.
- `D01-replan-dirty-trace.json`: frozen-input single-pass retention decisions and the refreshed target identities.
- `D01-validate-plan-probe.py`: reproducible in-memory interception; runtime code remains unchanged.
- `../logs/D01-validator-probe-replay.log`: zero-call replay summary and reproduced error.
- `../summaries/D01-replay.json`: standard runner summary.

The failure is correctly fail-closed, but this is a genuine engine/recovery defect rather than an expected unresolved business case. No artifact safety metrics can be marked verified for this D01 attempt because it produced no final DOCX.
