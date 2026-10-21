# D01 stable dirty closure cross-review

Read-only review of the uncommitted `replan_sites()` fix based on HEAD `682e68a5b3ef2a58feb77460af70afabdb314379`. This is not final-SHA validation.

The fixed dirty-operation/site closure removes the duplicated G08 source span that previously caused `EDIT_OVERLAP_OR_ADJACENT`. However, the resulting frozen D01 `plan-2` still has eleven retained components whose discovery target IDs were reused for other operations/sites or removed during Inventory refresh. This remains **HIGH** until their references are rebound.

Examples:

| Retained component | Current target with the same ID | Actual current operation/site candidate |
|---|---|---|
| G05:0 T003 @ p135 | G03:0 T003 @ p130 | G05:0 T005 @ p135 |
| G08:0 T007 @ p226 | G05:2 T007 @ p135 | G08:0 T010 @ p226 |
| G14:3 T012 @ p231 | G10:0 T012 @ p228 | G14:3 T017 @ p231 |
| G15:0 Y005-D3 @ p758 | absent | G15:0 T018 @ p758 |

The accompanying JSON contains the full observed component/current-target mismatches and operation/site candidates. Composite targets are checked by all source parts: Y007's p1223 component remains correctly associated with Y007 anchored at p1222 because p1223 is an explicit part; it is not a stale-reference finding.

The downstream risk is concrete: `_plan_by_target()` and `_reconcile_final_plan_ledger()` still use target ID keys; Audit looks up the target's plan status/replacement by the current ID; Claim Replay also consults `targets_by_id` for occurrence identity. Correct executable geometry does not make those stale references safe.

Smallest general repair:

1. Match each retained component to current targets by the component's rule, operation identity, verified source site and source span, plus occurrence identity for narrow class substitution. A composite target must be matched through its explicit source parts. An exact direct span can be preferred over a broader composite only when both represent the same source effect; distinct occurrences must stay distinct.
2. Rewrite the component target ID and rederive the parent target reference from the current component references. Update retained ledger entries, covered-alternative references and operation edit IDs before final reconciliation. Preserve original source geometry/content unchanged.
3. For old frozen ledgers without stable fields, recover them only from the old plan's own components using `(old target ID, rule, operation keys)`. Do not use a newly reassigned current target ID to infer the old location.
4. If no source-bound current match exists, keep an explicit unresolved reference or replan that local site; never silently attach the old entry to a different business target. Multiple distinct source matches must fail closed. Duplicate aliases for the identical source operation/span can be canonicalized consistently.

Regression coverage must assert current target references and ledger coverage after an A/B ID swap, not just a non-overlapping executable edit list. It should include different-rule ID reuse, same operation at two separate sites/occurrences, a composite second paragraph, and old ledger inputs without location metadata.

No runtime source changes or live model calls were made during this review.
