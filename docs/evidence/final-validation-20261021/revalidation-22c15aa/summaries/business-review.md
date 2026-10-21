# Independent Business Review

- HEAD: `22c15aa4d8d736f2a2fc46a29bc3ed8611475f2f`
- Branch: `refactor/recovery-architecture`
- Guide document SHA: `45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7`
- Scope: direct Guide/source/final DOCX review plus independent redline XML comparison; no live model calls.

## Result

- Delivery-level false complete observed: **0** (all four reports are `incomplete`).
- Operation-level false passes observed: **yes** (P0; see BR-001 and case details).
- Unauthorized edits in reviewed changed sites: **none observed**; D02 p1371 is a generation error at an authorized site.
- Cross-site/duplicate-site proof defects: **yes**.
- Writer/serialization plan-to-artifact mismatch: **none observed**. Planned wrong effects: **yes** (D02 G11/G22); Claim blocks G11 but falsely passes malformed G22.
- Business gate: **FAIL**; do not enter 20-case acceptance.

## Mechanical artifact checks

All four cases have source/report SHA binding, preserved paragraph counts, accepted redline text exactly equal to `working_final.docx`, and rejected redline text exactly equal to `original.docx`; each has zero paragraph-level differences.

## D01

- Document SHA: `2f2f7a36000af8135feb625c0c7d6f9f3e8b291d1628f0879993d6987e2d278d`
- Final SHA: `ae8498744dc08d57ff8a18a32bdbd22e1948de81bdc8d0657f440d372beb33c0`
- Changed paragraphs: 12; model HTTP calls: 53; estimated cost: `$0.04782000`
- Delivery: `incomplete`; TRUE obligations: 24; TRUE→NOT_APPLICABLE: **0**
- Completion counts: `{"ARTIFACT_VERIFIED": 7, "ALREADY_SATISFIED": 6, "NOT_APPLICABLE": 10, "UNRESOLVED": 11}`
- Redline: accepted==final `True`, rejected==original `True`.

### Confirmed artifact findings
- G01 p91/p92 definition unchanged; required append absent
- G03 direct-sales policy absent at p130/basic-setting copy
- G05 p135 rate fixed but p434/p1100 unrelated fee-change sites remain and require scope distinction
- G13 p230 full 7-day/1.50% sentence remains
- G14 p231 still permits redemption-rate reduction
- G15 body p758 old payment mechanism remains while summary p1221 changed
- G16 body p758 new payment policy absent while summary p1221 contains it
- G17 body p759 usage sentence remains; body p760 deleted; summary p1222/p1223 deleted
- G22 summary p1299 remains unchanged while body p934 changed

### Proof findings
- G13:B1:O1 PASS/VERIFIED_ABSENT at p230 despite exact old charge sentence surviving
- G15:B1:O1 PASS/VERIFIED_ABSENT/ARTIFACT_VERIFIED despite unchanged body p758
- G16:B1:O1 PASS/EXPECTED_EFFECT_PRESENT based only on summary p1221 despite body p758 missing

### Unsupported review findings
- **HIGH:** Audit G02 p91 invents B class; certified actual set is A/C/D with A/D subscription and C service
- **HIGH:** Audit G04 p130 repeats wrong A/B/C/D grouping and conflicts with facts
- **HIGH:** Sweep G18 p782 is unrelated dividend clause; sweep G18 p785 rejects correct A/D/C instantiation
- **HIGH:** Sweep G22 p934 says wrong although exact required text is present

### Positive verified effects
- G05 p135 replacement and filing deletion are correct; G05 B3 verified absent
- G08/G09/G11/G12/G18/G22 body p934 effects are textually authorized where changed

## D02

- Document SHA: `c02ae5a04ffbb1a8c63a7408fb3c69fab4f54cd60ff44575f42031ab00e1289b`
- Final SHA: `77b6b3f56445e84da01cebe6e44da0df9b0ba4d0a2a0146927fa028aac7caf18`
- Changed paragraphs: 14; model HTTP calls: 47; estimated cost: `$0.04963680`
- Delivery: `incomplete`; TRUE obligations: 24; TRUE→NOT_APPLICABLE: **0**
- Completion counts: `{"ARTIFACT_VERIFIED": 10, "ALREADY_SATISFIED": 5, "NOT_APPLICABLE": 10, "UNRESOLVED": 9}`
- Redline: accepted==final `True`, rejected==original `True`.

### Confirmed artifact findings
- G01 p93 unchanged; G01 cannot borrow G03 p135
- G14 p232 unchanged and still includes redemption/conversion rates
- G16 summary p1287 blank while body p821 contains policy
- G17 body p822/p823 deleted but summary p1288/p1289 unchanged
- G05 filing operation at p138 is source-absent and is OPEN/UNPROVEN rather than proven already absent
- G06 prohibition is absent in source and remains fail-closed

### Proof findings
- G22:B1:O1 PASS/EXPECTED_EFFECT_PRESENT despite p1371 ending with orphan source suffix “配。”; effect proof checked prefix, not exact final site
- G16:B1:O1 PASS from body p821 despite duplicate summary p1287 missing
- G17 operation-level PASS evidence includes only body deletion while summary residuals remain (projection is separately unresolved)

### Generation findings
- **HIGH:** G11 p228 applies both historical ONE_OF operations to overlapping/nested spans (0:50 and 12:31), producing duplicated malformed text
- **HIGH:** G22 p1371 replacement span ends mid-source phrase and leaves “配。” after the fixed text

### Unsupported review findings

### Positive verified effects
- G03 p135, G05 rate p138, G12 p229, G13 p230, G15 p821, G22 p1001, G18 copies are textually authorized where changed

## D11

- Document SHA: `74920e09c398f086091ca2b522c5d3bb0ed574d8ccd8c6e00ecf416b508ba93a`
- Final SHA: `c2e4736a9a3fd0b4eef273788ae3228be2550f6f62c4409cdb929f5a4aeb589b`
- Changed paragraphs: 13; model HTTP calls: 51; estimated cost: `$0.04332405`
- Delivery: `incomplete`; TRUE obligations: 24; TRUE→NOT_APPLICABLE: **0**
- Completion counts: `{"ARTIFACT_VERIFIED": 11, "ALREADY_SATISFIED": 5, "NOT_APPLICABLE": 10, "UNRESOLVED": 8}`
- Redline: accepted==final `True`, rejected==original `True`.

### Confirmed artifact findings
- G01 p91 unchanged
- G05 p129 retains “调低赎回费率”; genuine missing effect
- G11 operation O1 is unresolved at p211; p209 O2 text is correct but same rule semantics require site review
- G16 new payment policy absent at all body/summary sites after G15 deletion
- G17 body and summary deletions are complete
- G18 body/summary A/D/C substitution is correct under certified facts
- G22 body/summary additions are correct

### Proof findings
- G16 remains OPEN (correct fail-closed), but no artifact contains required policy
- G17 PASS is valid for its known deletion sites; no cross-site success should be inferred for G16

### Unsupported review findings
- **HIGH:** Sweep G18 p800 insists literal A/C and rejects correct A/D/C instantiation
- **HIGH:** Sweep G05 p129 incorrectly treats “调整前基金管理人需及时公告” as evidence of备案 residual; actual备案 text absent
- **HIGH:** Sweep G05 p129 duplicate findings should distinguish p129 rate residual from filing deletion

### Positive verified effects
- G03/G08/G09+G11 atomic merge/G12+G13/G14/G15/G17/G18/G22 effects are textually correct at reviewed sites

## D16

- Document SHA: `8beacaba3446f7e7e6db1d8cdd3036f0eb086139d6e89a9d27e3552ec658e45d`
- Final SHA: `5fa95b8e067d79991a01e168d587716050a6c56976050b12086987f081c66e58`
- Changed paragraphs: 15; model HTTP calls: 43; estimated cost: `$0.04055925`
- Delivery: `incomplete`; TRUE obligations: 24; TRUE→NOT_APPLICABLE: **0**
- Completion counts: `{"ARTIFACT_VERIFIED": 10, "ALREADY_SATISFIED": 10, "NOT_APPLICABLE": 10, "UNRESOLVED": 4}`
- Redline: accepted==final `True`, rejected==original `True`.

### Confirmed artifact findings
- G01 p91 missing append; no cross-site borrowing from G03 p133
- G05 p133 rate replacement correct; unrelated p431/p1169 business-rule paragraphs unchanged and should not be deleted
- G15 old mechanism deleted at summary p1306 but body p822 unchanged
- G16 required four-component payment policy absent
- G17 usage/exclusion deletions complete at body/summary
- G18 body/summary A/C substitution correct
- G22 body/summary additions correct

### Proof findings
- G13:B1:O1 PASS/VERIFIED_ABSENT at p221 while p222 still contains exact continuation “7 日的投资者收取不低于 1.5%的赎回费，并全额计入基金财产。”; projection ALREADY_SATISFIED is false
- G15 is not complete because body p822 old payment mechanism remains despite p1306 deletion

### Unsupported review findings
- **HIGH:** Audit G06 p431/p1169 quotes unrelated business-rule adjustment text as the prohibited conversion sentence; source does not contain G06 prohibition
- **HIGH:** Sweep G05 p133 claims备案 residual although final exact quote has only announcement and no备案
- **HIGH:** Sweep G17 p822 attributes usage residual to payment paragraph; actual usage copies p823/p824 and p1307/p1308 are deleted

### Positive verified effects
- G03/G05 filing deletion/G11/G12/G14/G17/G18/G22 changed effects are textually correct at reviewed sites

## Root cause summary

- **BR-001 (BLOCKER / P0):** effect proof certifies a partial/stale site or prefix instead of all verified duplicate and component sites; exact residuals survive while PASS is emitted.
- **BR-002 (HIGH):** overlapping explicit ONE_OF alternatives can both be applied at one site, producing D02 p228 duplication.
- **BR-003 (HIGH):** replacement span integrity allows source suffix “配。” to survive after D02 p1371 G22 replacement while Claim passes.
- **BR-004 (HIGH):** audit/sweep semantic evidence is not consistently constrained by rule-specific semantics and certified facts, causing unsupported blockers.

These are evidence findings for the current HEAD; no source code or centralized issue log was modified by this review.

Review finding counts: **BLOCKER 1, HIGH 3**. Paragraph labels in this review are native `inspect_docx` locations (for example `p228`), not one-based physical Word paragraph order. The JSON includes source/final quotes and Claim/projection state for every disputed operation/site.
