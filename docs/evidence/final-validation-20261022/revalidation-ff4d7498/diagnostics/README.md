# Diagnostics

- `guards_check.py` / `../logs/guards-check.log`: offline G02 class-set guard checks. A/D vs A/D = PASS; A/D vs A/C = FAIL; A/D vs A/C/D = FAIL.
- D16 stage replay: base plan and revision 3 are stored separately in `../summaries/D16-stage-plan-base.json` and `../summaries/D16-stage-plan-rev3.json`; all six stages have `same_head=true` and `model_calls=0`.
- Root-cause evidence is in `../summaries/business-review-ff4d749.md`, `architecture-review-ff4d749.md`, `recovery-review-ff4d749.md`, and the per-case `reports/` / `artifacts/` directories.
- The baseline `682e68a` diagnostics and artifacts remain under `docs/evidence/final-validation-20261022/`; do not overwrite them.
