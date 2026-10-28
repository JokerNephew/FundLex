# Independent label schema — first batch (2026-10-28)

Schema id: `fundlex-independent-labels-v1`
Producer: `tools/evaluation/first_batch_label_20261028.py`
Output: `var/recall-first-evaluation/first-batch-20261028/labels-first-batch-20261028.json`
Tracked evidence copy: `docs/evidence/labels-first-batch-20261028.json`
Tracked selection copy: `docs/evidence/selection-first-batch-20261028.json`

The labels are produced by a real model outside the recall-engine model family and are
**independent of engine output**: the tool reads only the frozen selection, the guide
DOCX, the guide rule map (rule ids/templates), and the original contract DOCX. It does
not read engine reports, final/redline artifacts, engine prompts or historical P6 labels.
No filename or case-id special-casing exists in the tool; product facts and site
applicability are derived from each original contract and the guide.

## Reuse for later waves

The tool accepts an arbitrary frozen selection, output path, model pair and concurrency:

```
.venv/bin/python tools/evaluation/first_batch_label_20261028.py \
    --selection <frozen-selection.json> --out <labels.json> \
    --provider-env <protected-model-env> --all --concurrency 1
```

`--case ID` (repeatable) labels a subset. The output records the selection hash,
per-case source hash, guide hash and the model/independent-review usage summary, so a
later wave is versioned even when the sample grows toward the full `funds_word/` corpus.
Do not reuse an earlier engine prediction when labelling a later wave.

## Top level

| field | meaning |
| --- | --- |
| `schema` | `fundlex-independent-labels-v1` |
| `batch_id` | `--batch-id` or the selection stem |
| `frozen_at` | label freeze timestamp (UTC) |
| `selection_sha256` | SHA-256 of the frozen selection |
| `selection` | path, hash, counts, selection `frozen_at` |
| `guide` | guide DOCX hash, rule-map hash and paths |
| `labeler` | primary/review model ids, independence statement, prompt version, tool hash, engine model env value (name only), `selection_sha256`, `source_hashes`, usage summary |
| `excluded` | selection entries removed from the modification denominator (legacy `.doc` etc.) with reason |
| `protected_cases` | files whose protection metadata makes them `DOCUMENT_PROTECTED`; no write targets, denominator retained |
| `cases` | 28 case objects for the first batch |

## Case

| field | meaning |
| --- | --- |
| `case_id`, `group`, `file`, `relative`, `sha256`, `bytes`, `stratum` | frozen selection identity |
| `document` | paragraph count, source text hash, summary start, summary headings, protection metadata |
| `fund` | facts with paragraph quote evidence: `fund_type`, `eligible`, `share_classes` (label, purchase-fee / sales-service-fee polarity, evidence), `class_count`, `has_sales_service_fee`, `floating_management_fee` (+ basis), direct-sales policy, one-year rule, payment mechanism |
| `rule_coverage` | one entry per rule/scope (`target` / `satisfied` / `not_applicable` / `unknown`) with paragraph index, reason and evidence quote |
| `targets` | every real required site (see below) |
| `satisfied` | derived from `rule_coverage`; rule applies and required outcome already present with source evidence |
| `not_applicable` | derived; condition false or replacement old text absent with no new-obligation authorization |
| `unknown` | derived; evidence insufficient (never silently treated as not applicable) |
| `uncertain` | model/reviewer ambiguities with candidates |
| `protected` | present for `DOCUMENT_PROTECTED` cases |
| `label_quality` | deterministic validation issues after the bounded repair pass; empty means all checks passed |
| `review` | independent reviewer model, verdict, validated findings, adjudication decisions |
| `usage` | per-case call and token counts |

## Target

| field | meaning |
| --- | --- |
| `target_id` | stable id within the case, ordered by paragraph / rule / op |
| `rule_id`, `group` | G01–G22 |
| `op` | `replace` / `delete` / `append`, constrained per rule |
| `scope`, `site_scope` | `main` or `summary`; body and summary sites are separate targets |
| `paragraph_index` | python-docx zero-based paragraph index; for `append` it is the anchor paragraph |
| `location` | nearest part / subsection path |
| `old_text` | smallest contiguous span that must change (empty for append) |
| `required_text` | replacement / appended text (empty for delete) |
| `source_quote` | exact contract quote; anchor quote for append |
| `anchor_quote`, `anchor_position` | append anchor quote and `end_of_paragraph` |
| `requirement` | business requirement for this site |
| `class_scope` | real share-class labels involved |
| `guide_paragraphs` | guide source paragraph numbers |
| `compact_start`, `compact_end` | offsets into the paragraph with all whitespace removed |
| `old_text_sha256`, `paragraph_text_sha256` | integrity checks |
| `confidence` | `high` normally; `protected` for protected cases |
| `review_flags`, `provenance` | review/completion provenance (for example `guide_exact_completion` when a guide-exact G13 delete site was completed deterministically) |
| `related_target_ids` | main/summary or same-rule counterparts |

## First-batch merge and documented corrections

The first batch was produced in one full run plus three targeted re-runs of cases
that failed deterministic completeness checks (B01, B05, BH04, BH06, BH07, BH08,
B15, B16, B19). `tools/evaluation/finalize_first_batch_labels_20261028.py` merges
the latest run per case and applies only these documented, guide-based corrections:

| case | correction | basis |
| --- | --- | --- |
| B15 | drop G22 targets; G22 → `not_applicable` | contract has a sequential liquidation list, not the guide's "依据基金财产清算的分配方案…全部剩余资产" replacement clause |
| B15 | add G05 delete of `并报中国证监会备案` at p87 | guide-exact phrase in the class-setup clause |
| BH07 | G14 → `satisfied` (p240 already only `适当调低基金申购费率`), no target | no redemption/conversion/service-fee wording left to remove |
| BH08 | G08 → `unknown` with an `uncertain` record | purchase-fee sentence is a multi-class variant using A类人民币/A类美元/C类 wording; the adapted replacement has more than one defensible reading, so it is not counted as confirmed gold |
| BH06 | keep `DOCUMENT_PROTECTED`, no targets, denominator retained | `word/settings.xml` has `documentProtection` |

`labeler.merge_provenance` records each run file, its SHA-256 and its tool hash;
`labeler.tool_sha256_history` lists the labeler revisions used; and
`labeler.usage_observed_all_runs` aggregates observed calls/tokens across the full
run and all re-runs. The generator is generic for later waves; the merge/finalizer
script is batch-specific and must not be reused to inject later-wave labels.

## Validation built into the producer

* selection count and every source SHA-256 are checked before labelling;
* `old_text` / `source_quote` / evidence quotes must be literal contract substrings
  (whitespace differences are tolerated and the original span is kept);
* paragraph indices, scope (`main`/`summary`) and rule-specific section scope are checked;
* append anchors must be in the expected section and not on a paragraph deleted by G15/G17;
* `required_text` is checked against guide-required tokens for the main rules;
* deterministic completeness guards turn a model `not_applicable` into a repair request
  when the guide condition and real facts make a site mandatory;
* no-op replacements are dropped and their rule/scope becomes `satisfied`;
* G12 targets that swallowed the G13 7-day sentence are split with a guide-exact G13
  delete site;
* every case gets one independent review pass plus adjudication of validated missing
  targets; reviewer findings without exact source support are not accepted as gold.
