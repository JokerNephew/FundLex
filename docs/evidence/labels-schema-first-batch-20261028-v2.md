# Independent label schema v2 — review-adjudicated first batch (2026-10-29)

Schema id: `fundlex-independent-labels-v2`
Producer: `tools/evaluation/build_labels_v2_20261028.py` (adjudication over v1)
Base v1: `docs/evidence/labels-first-batch-20261028.json` (unchanged)
Output: `var/recall-first-evaluation/first-batch-20261028/labels-first-batch-20261028-v2.json`
Tracked copy: `docs/evidence/labels-first-batch-20261028-v2.json`

v2 keeps every v1 field and adds the following. It never reads engine reports,
final/redline artifacts, engine prompts or historical P6 labels.

## Adjudication

Every entry in `cases[].review.findings` (v1 independent-review output) is given
a stable `R###` id and a resolution in `cases[].review_resolutions`:

| field | meaning |
| --- | --- |
| `finding_id` | `R001`… in v1 finding order |
| `type` | `missing_targets` / `incorrect_targets` / `fact_issues` / `status_issues` / `uncertain` |
| `decision` | `accept_add` / `accept_modify` / `accept_fact` / `accept_status` / `reject` / `uncertain` |
| `reason` | adjudicator basis from the guide and the original contract |
| `applied` | true when the label file was actually changed |

Rules:
* `accept_add` produces a new validated target; `accept_modify` replaces a target's
  fields; `accept_fact` updates the detailed `fund` mapping (dotted path + value);
  `accept_status` updates `rule_coverage`.
* Findings the adjudicator did not return, and accepted-but-not-mechanically-applicable
  fact corrections, are moved to `cases[].uncertain` with a reason. They are never
  silently dropped.
* A finding is not a licence to delete a target; nothing is removed to make scoring pass.

Per-case counters: `review_findings_total`, `review_findings_applied`,
`review_findings_uncertain`, `review_findings_rejected`; batch summary in
`review_summary`. The adjudicator model, prompt version, engine model name (value not
printed) and token usage are in `adjudication`.

## Scorer compatibility

`cases[].target_count` is the number of confirmed targets (used by `p6_score.py` for
`editable`).

`cases[].facts` is the scorer-compatible mapping while the detailed evidence remains in
`cases[].fund`:

```json
{
  "classes": [{"name": "A类基金份额", "subscription_fee": true, "service_fee": false}],
  "class_count": 2,
  "class_count_basis": "fee_group",
  "has_sales_service_fee": true,
  "floating_management_fee": false,
  "fund_type": "混合型",
  "currency_variants": []
}
```

`classes` are the fee groups used by G02/G04 substitution; QDII/LOF currency sub-classes
are recorded separately in `currency_variants` so they are not mixed into fee groups.
The detailed `fund` object (share classes with paragraph/quote evidence, payment
mechanism, eligibility, etc.) is retained unchanged for audit.

## First v2 run result (2026-10-29)

346 v1 review findings were adjudicated: **44 applied** (13 target modifications, 16 fact
corrections, 13 status corrections, 2 other modifications), **51 kept as unresolved
`uncertain`** with reasons, and **251 rejected** with recorded reasons (reviewer opinion
out of guide scope, already covered by an existing site, or a stricter-text preference
that the guide does not require). There were no `accept_add` decisions: deterministic
audit plus v1 already covered every real body/summary site, including the duplicated
summary G15/G16 site near p1296, and the reviewer's proposed additions did not survive
adjudication. v2 targets remain 501; `review_summary.unresolved_review_findings` is 51.
Unresolved findings are visible per case in `uncertain`; they are not silently dropped
and not presented as gold. v2 is still an independent-label draft, not an engine pass.

## Scope retained

28 cases (20 dev / 8 holdout), frozen selection hash, per-case source hash, `excluded`
legacy `.doc` list and the `DOCUMENT_PROTECTED` BH06 boundary (no targets, denominator
retained) are unchanged from v1. Later waves must pass their own frozen selection and
output paths; do not reuse engine predictions from earlier waves.
