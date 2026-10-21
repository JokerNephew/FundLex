# D01 retained-reference edge recheck

Read-only review of the uncommitted `replan_sites()` retained-reference fix at HEAD `682e68a5b3ef2a58feb77460af70afabdb314379`. The runtime was not edited and no live model call was made.

Evidence: [`D01-reference-remap-edge-recheck.json`](../diagnostics/D01-reference-remap-edge-recheck.json), reproduced by [`recheck_retained_references.py`](../diagnostics/recheck_retained_references.py).

- Atomic edit with one missing component: **PASS**. The atomic edit is removed from executable records; exactly two unique `RECALL_PLAN_REFERENCE_UNBOUND` ledger rows remain, one per operation.
- Existing conflict with `Old` remapped to current `New`: **PASS**. Ledger and conflict target both use `New`.
- Cross-rule ID reuse (`Old` now belongs to `G88 @ p1`, original conflict was `G99:0 @ p0`): **PASS**. The remapper keeps the original G99 site and does not borrow the reused G88 target.
- Missing legitimate site with only the reused cross-rule ID available: **PASS**. Ledger remains unresolved and the conflict is retained with `reference_status=RECALL_PLAN_REFERENCE_UNBOUND` and an `UNBOUND:` target.
- The replan implementation uses positional `(edit_index, component_index)` caching; no `id(unit)` lookup remains.
- Network attempts: 0.

These checks cover reference identity and fail-closed behavior. They do not certify a final commit or live contract result.
