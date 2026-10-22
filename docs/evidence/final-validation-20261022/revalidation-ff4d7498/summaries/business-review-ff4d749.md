# Independent Business Review — exact code `ff4d749` (D01 / D02 / D11 / D16)

- **Reviewer:** independent business reviewer (read-only; no source, test, git, evidence or live-model changes)
- **Runtime code:** `ff4d7498b6c1aee72ba48686074d021fc7f84791`, branch `refactor/recovery-architecture`
- **Evidence root:** `docs/evidence/final-validation-20261022/revalidation-ff4d7498`
- **Baseline (read only, not overwritten):** `docs/evidence/final-validation-20261022` (bound to `682e68a`)
- **Certified guide:** `guides/builtin_guide_v1.json` — 22 rules / 34 operations, document SHA-256 `45dd7746…f92c8d7`, source SHA-256 `b77be53c…6eef895`
- **Case inputs/outputs reviewed:** `frozen/Dxx/original.docx`, `artifacts/Dxx/working_final.docx`, `artifacts/Dxx/edits.json`, `reports/Dxx.json` (plan / targets / obligations / artifact_claim_replay / audit / sweep), `ledgers/Dxx.csv`
- **Method:** python-docx body-paragraph extraction (text only); every planned span reconstructed from the plan and compared to the actual paragraph; every changed paragraph checked against the plan; residual old text searched across all paragraphs; hashes, replay and ledger checked. No claim of `PASS` or `delivery=incomplete` was accepted without artifact evidence.
- **Convention:** `pN` is the **0-based body paragraph index used by the engine/report** (so Word's 1-based paragraph number is generally `pN+1`). Quotes are exact except marked ellipses.

---

## 1. Bottom line

1. **The four reports’ `delivery=incomplete` is substantively truthful.** Every case has at least one real, unfixed business gap — above all **G16 is absent in all four working_final.docx**. There is therefore **no case-level false “complete”**.
2. **But the artifacts are not safe to deliver.** All four delete the old sales-service-fee payment clause (`G15`) and **never add the required four-component replacement policy (`G16`)**. D02/D11 additionally delete the sales-service-fee purpose/scope sentences. The fee section is gutted or internally inconsistent. Example: D02 `p821–p823` are blank and `p1287–p1289` are blank; D11 `p772–p773` and `p1247–p1248` are blank; no replacement text exists in any case.
3. **One real obligation-level false complete exists: D11 G18.** The body copy at `p800` is changed, but the summary copy at **`p1207` still contains the old “A类基金份额和D类基金份额不收取销售服务费，而C类基金份额收取销售服务费” wording**, while `G18:B1:O1` is recorded `ARTIFACT_VERIFIED` with sole site `p800`. The report’s `delivery_gate` has only 3 open obligations (G05:2, G06, G16); if those were fixed/waived, D11 would pass the gate with the summary copy still wrong.
4. **One real audit false-complete exists: D02 G12/G13.** `p229` is textually identical to the original — the full old proportional-allocation + 7-day/1.5% sentence remains — yet the target audit says `completed` and the report says “审计完成 1/1” / “未决问题 0”. The sweep and claim replay correctly say `pending` / `NOT_PLANNED`. The audit is not reading the artifact.
5. **Several incompletes are false blocks, not real defects.** G06 is absent from all four originals, but is `UNRESOLVED` in all four. D01 G02 is already satisfied by `p92` (“A 类及 D 类基金份额 … C 类基金份额”), but is blocked by a truncated `p91` target and an audit that demands a non-existent **B类**. D11 G05:2 is absent from the class-setting clause, but is `UNRESOLVED` while the same absence in D01/D02 is `ALREADY_SATISFIED`.
6. **Old finding closure:** `BR-D01-001` is **partially closed** (working_final now exists and is hash-bound; the false “overlap” still drops G17); `BR-D02-001/004`, `BR-D11-002`, `BR-D16-003`, `BR-D16-006` are **CLOSED** for the specific old defect. The B-class audit defect is **closed in D16 but has migrated to D01**.

**Gate recommendation: BLOCK / FAIL — do not deliver any of the four `working_final.docx` files.** The existing `index.json` gate `FAIL` is substantively correct, but its published reasons are stale (see §8).

---

## 2. Rule-level matrix — required vs actual

Legend: ✅ done and textually correct at the business site; ⚠️ done but placement/duplication concern; ❌ missing/real residual; ⊘ already satisfied (no edit required); N/A condition false; **bold** = finding.

| Rule | Required business effect | D01 | D02 | D11 | D16 |
|---|---|---|---|---|---|
| G01 | Append direct-sales / C-fee policy after the **释义** class definition | **❌ missing at p92** | ✅ p93 | ✅ p91 | ✅ p91 |
| G02 | Replace A/C labels with the actual fee groups (A/D and C where applicable) | **⊘ already satisfied at p92, but falsely OPEN** | ⊘ p93 | ⊘ p91 | ⊘ p91 |
| G03 | Append the same policy after the **基金的基本情况** class-setting clause | ✅ p130 | ✅ p138 | ⚠️ p126 (mid-paragraph) | ✅ p133 |
| G04 | Replace A/C labels in 基金的基本情况 | ⊘ p130 | ⊘ p135 | ⊘ p126 | ⊘ p129 |
| G05:0 | `调低赎回费率` → `调低销售服务费率` | ✅ p135 | ✅ p138 | ✅ p129 | ✅ p133 |
| G05:2 | Delete `并报中国证监会备案` | ⊘ absent | ⊘ absent | **⊘ absent but falsely OPEN** | ✅ removed p133 |
| G06 | Delete `除非…不得互相转换` clause | **⊘ absent but falsely OPEN** | **⊘ absent but falsely OPEN** | **⊘ absent but falsely OPEN** | **⊘ absent but falsely OPEN** |
| G07 | Single-class purchase-fee wording | N/A | N/A | N/A | N/A |
| G08 | Multi-class purchase-fee wording | ✅ p226 | ✅ p226 | ✅ p208 | ✅ p217 |
| G09 | `扣除相应的费用` → `扣除或加上相应的费用` | ✅ p227 | ✅ p227 | ✅ p209 | ✅ p219 |
| G10 | Single-class subscription-fee wording | N/A | N/A | N/A | N/A |
| G11 | Multi-class subscription-fee wording | ✅ p228 | ✅ p228 | ✅ p209 | ✅ p220 |
| G12 | Replace redemption-fee clause with `赎回费用全额计入基金财产。` | ✅ p229 | **❌ p229 unchanged** | ✅ p210 | **❌ p221 unchanged** |
| G13 | Delete the 7-day / 1.50% redemption-fee sentence | ✅ p230 | **❌ p229 unchanged** | ✅ p210 | **❌ p221–p222 unchanged** |
| G14 | Multi-class `赎回费率` → `销售服务费率` | ✅ p231 | ✅ p232 | ✅ p213 | ✅ p224 |
| G15 | Delete old sales-service-fee payment clause | ✅ p758 + p1221 (non-exact variant) | ✅ p821 + p1287 (non-exact variant) | ✅ p772 + p1247 (non-exact variant) | ✅ p822 + p1306 (non-exact variant) |
| G16 | Append the four-component sales-service-fee policy | **❌ absent** | **❌ absent** | **❌ absent** | **❌ absent** |
| G17 | Delete sales-service-fee purpose/scope sentences | **❌ p759/p760 + p1222/p1223 unchanged** | ✅ p822/p823 + p1288/p1289 | ✅ p773 + p1248 | **⚠️ summary p1307/p1308 deleted; body p823/p824 unchanged** |
| G18 | `…费用收取不同` wording | ✅ p785 + p1191 | ✅ p848 + p1257 | **⚠️ body p800 done; summary p1207 unchanged but marked complete** | ✅ p845 + p1261 |
| G19/G20/G21 | Floating-fee branches | N/A | N/A | N/A | N/A |
| G22 | Add sales-service-fee return to liquidation distribution | ✅ p934 + p1299 | ✅ p1001 + p1371 | ✅ p951 + p1344 | ✅ p1000 + p1399 |

**What should change, in business terms:** G01 (D01), G12/G13 (D02, D16), G16 (all), G17 (D01, D16 body), G18 summary (D11). Everything else is either already correct, already satisfied, or condition-false.

---

## 3. Case-by-case evidence

### 3.1 D01 — artifact exists now; G01/G16/G17 missing; G02/G06 falsely blocked

**Artifact integrity (positive):** `artifacts/D01/working_final.docx` exists, SHA-256 `80a87bd8ab44d36f08e399c864ce677c82887fd83505142126c283b0673bc6a9`, exactly the report’s `output_validation.final_sha256`; binding is `ff4d749`, mode `record`. `replay/D01/working_final.docx` also exists and its extracted text is identical to the record artifact. The old `BR-D01-001` “no working_final” is factually closed. The `index.json` line claiming D01 `not_generated` / `EDIT_OVERLAP_OR_ADJACENT` is **stale** (see §8).

**Actual changed paragraphs (14, all plan-exact):**

| Paragraph | Rule / op | Effect |
|---|---|---|
| p130 | G03:0 insert | Appended the direct-sales / C-fee clause after the 基金的基本情况 class definition. Correct site and text: “投资者通过直销机构…申购本基金A类、D类基金份额时，不收取认购/申购费用…” |
| p135 | G05:0 | `调低赎回费率` → `调低销售服务费率`. Correct. |
| p226 | G08:0 | Multi-class purchase-fee wording. Correct. |
| p227 | G09:0 | `扣除相应的费用` → `扣除或加上相应的费用`. Correct. |
| p228 | G11:0 | Multi-class subscription-fee wording. Correct. |
| p229 | G12:1 | Replaced with “赎回费用由…收取。赎回费用全额计入基金财产。” Correct. |
| p230 | G13:0 | Deleted “本基金对持续持有期少于 7 日的投资者收取 1.50%的赎回费，并将上述赎回费全额计入基金财产。” Correct. |
| p231 | G14:3 | `…调低基金申购费率和销售服务费率。` Correct. |
| p758 | G15:0 | Old daily-accrual/payment clause blanked. |
| p785, p1191 | G18:0 | Both body and summary copies changed to “由于本基金A类、D类基金份额和C类基金份额费用收取不同…”. Correct. |
| p934, p1299 | G22:0 | Both copies add “并加上返还基金份额持有人的销售服务费（如有）。” Correct. |
| p1221 | G15:0 | Summary copy of the payment clause blanked. |

**Missed / residual (with exact text):**

- **G01 missing at p92 (true gap).** The 释义 definition is split across `p91` (“…分为 A 类、C 类和 D 类三种不同的”) and `p92` (“类别。在投资者申购 A 类及 D 类基金份额时收取申购费用，不计提销售服务费；…计提销售服务费”). No direct-sales/C-fee clause was appended after `p92`. The final contains the clause only once, at `p130` (G03 site); `reports/D01.json` has no G01 target. This is a real missing edit in 释义.
- **G16 missing (true gap, blocker).** `p758` is blank, `p759/p760` still contain the old purpose/scope sentences, and no “销售服务费每日计提。（1）直销机构…” policy exists anywhere in the final. The section now says how the fee is calculated (`p754–p757`) but not how it is paid/returned.
- **G17 missing at p759, p760, p1222, p1223 (true gap).** Exact survivors:
  - `p759`: “销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。”
  - `p760`: “销售服务费使用范围不包括基金募集期间的上述费用。”
  - `p1222` / `p1223`: the same two sentences in the summary copy.
  The plan dropped these four targets with `plan_reason=RECALL_EDIT_OVERLAP` (“同一段落的多项修改无法安全合并”). The G15 delete is `p758 0–135`; the G17 deletes are `p759 0–52` and `p760 0–24` — **adjacent, not overlapping**. No character span is shared. This is a false overlap classification (see BR-FF-005).
- **G02 falsely OPEN (already satisfied).** `p92` already says “在投资者申购 A 类及 D 类基金份额时收取申购费用…在投资者申购 C 类基金份额时不收取申购费用”. That is exactly the required A/D + C grouping for D01’s certified A/C/D facts. The target `T3001/T3002` is the truncated `p91` quote ending at “三种不同的”, so it cannot see `p92`. The claim replay therefore has “verified site missing”, and the audit demands a **B类** that does not exist (see below).
- **G06 falsely OPEN (absent).** The certified G06 old text (“除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。”) does not occur in D01 — a whitespace-normalized search for “不同基金份额类别之间不得互相转换” returns zero hits. There is nothing to delete; `UNRESOLVED / CLAIM_REPLAY_FAILED` is a false block, not a true fail-closed.

**Audit false block (B-class):** `audit.issues[4]` says:
> “G02:0 requires replacing 'A类基金份额' with all classes that charge subscription/purchase fees and no sales service fee, i.e. 'A类、B类基金份额'. The AFTER text still lists only 'A 类、C 类和 D 类' and does not add B类…”
>
> `affected_fact`: “基金份额类别分组（A类、B类为收取认购申购费且不计提销售服务费的类别）”

D01’s certified facts are **A类、C类、D类** (`reports/D01.json facts.classes`), with `subscription_group=[A,D]` and `service_group=[C]`; `guide.groups[G02].class_substitution=true`. The instantiated groups are **A类、D类** and **C类** only. The companion `G02:1` audit likewise demands “C类、D类基金份额”, which would wrongly put D类 into the service-fee group. The obligation records still carry the uninstantiated templates (`A类、B类基金份额` / `C类、D类基金份额`), and the audit read them literally. This is the **same defect as old BR-D16-006**, now reproduced in D01.

**Verdict for D01:** `incomplete` is correct, but the real gaps are **G01, G16, G17**; **G02 and G06 are false blocks**; **G17’s stated overlap reason is false**. The artifact is not deliverable.

---

### 3.2 D02 — G12/G13 real miss + audit false completion; G16 missing; G06 false block

**Artifact integrity:** `artifacts/D02/working_final.docx` SHA-256 `4ad99c97…907140`, matches report; binding `ff4d749` record; replay text identical.

**Actual changed paragraphs (16, all plan-exact):** `p93` G01; `p138` G03+G05:0; `p226` G08; `p227` G09; `p228` G11; `p232` G14:5; `p821` G15; `p822/p823` G17; `p848` G18; `p1001` G22; `p1257` G18; `p1287` G15; `p1288/p1289` G17; `p1371` G22. All applied texts are authorized and correct at their sites. The G01 append at `p93` and the G03+G05 append/replace at `p138` are correct: D02’s facts are A/C, and the inserted clause says “A类基金份额”.

**Missed / residual:**

- **G12 and G13 unchanged at p229 (true gap; blocker).** The final `p229` is textually identical to the original paragraph:
  > “赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用归入基金财产的比例依照相关法律法规设定，具体见招募说明书的规定，未归入基金财产的部分用于支付登记费和其他必要的手续费。其中，对持续持有期少于 7 日的投资者收取不低于 1.5%的赎回费，并全额计入基金财产。”
  This is exactly `G12:1` old_text (with the 1.5% form) plus the G13 sentence. The plan dropped both targets with `RECALL_PLAN_COMPONENT_DROPPED` because the G12 span `0–147` and G13 span `103–147` overlap. A single G12:1 replacement would have removed both; D11 shows the same overlap was successfully merged at `p210`. D02 did not merge. This is a generation/merge defect, not an impossible edit.
- **G16 missing (true gap, blocker).** `p821–p823` are blank (old payment clause + purpose/scope), `p1287–p1289` are blank (summary copies), and no G16 policy exists. The sales-service-fee section now ends with blank paragraphs before “上述‘一、基金费用的种类’…”. This is a net content loss.
- **G06 falsely OPEN (absent).** Same as D01: no “不同基金份额类别之间不得互相转换” anywhere. Target `T010` is `state=absent`, `resolution=quote_not_found`, yet the obligation is `target=FOUND`, `validation=FAIL`, `UNRESOLVED`. The target status and obligation status contradict each other.

**Audit false completion (blocker):** `targets[T016/T017]` both say `audit.verdict="completed"`, `evidence_verified=true`:
> G12: “AFTER 将原赎回费用条款替换为要求的表述，删除了按比例归入基金财产及 7 日/1.5% 的表述，并写明赎回费用全额计入基金财产…”
> G13: “AFTER 删除了关于持续持有期少于7日投资者收取不低于1.5%赎回费并全额计入基金财产的表述；该句已不存在…”
Both statements are false: `p229` still contains the entire old sentence. `sweep.findings` SW002/SW003 correctly say `pending` / `RESIDUAL_CONFIRMED`, and the claim replay says `CLAIM_OPERATION_NOT_PLANNED`. The report’s “审计完成 1/1” and “未决问题 0” are therefore misleading.

**Old finding BR-D02-001/004 (p1036 placeholder):** **CLOSED.** `p1036` appears only inside scope/window `locations` lists; it is not a target location and not a claim site. G05:2’s absent proof is now at `p138` (the real class-setting clause), and G06 is no longer `PASS VERIFIED_ABSENT` — it is `OPEN`. The old false PASS is gone. The remaining G06 false OPEN is a new, different defect.

**Verdict for D02:** `incomplete` is correct; real gaps **G12/G13, G16**; **G06 false block**; **audit falsely marks G12/G13 completed**. Not deliverable.

---

### 3.3 D11 — hidden G18 summary false complete; G16 missing; G05:2/G06 false blocks

**Artifact integrity:** `artifacts/D11/working_final.docx` SHA-256 `74400197…42b23b`, matches report; binding `ff4d749` record; replay text identical.

**Actual changed paragraphs (14, all plan-exact):** `p91` G01; `p126` G03; `p129` G05:0; `p208` G08; `p209` G09+G11; `p210` G12+G13; `p213` G14; `p772` G15; `p773` G17; `p800` G18; `p951` G22; `p1247` G15; `p1248` G17; `p1344` G22. The G12+G13 merge at `p210` is the positive control: it correctly replaced the whole clause with “赎回费用全额计入基金财产。” and removed the 7-day sentence.

**Hidden false complete — G18 summary p1207 (blocker):**

- Body `p800` final: “由于本基金A类、D类基金份额和C类基金份额费用收取不同，各基金份额类别对应的可分配收益将有所不同。”
- Summary `p1207` final: **unchanged original** — “由于本基金 A 类基金份额和 D 类基金份额不收取销售服务费，而 C 类基金份额收取销售服务费，各基金份额类别对应的可分配收益将有所不同。本基金同一类别的每一基金份额享有同等分配权； 5、法律法规或监管机关另有规定的，从其规定。”
- `artifact_claim_replay.obligations["G18:B1:O1"]` = `PASS / EXPECTED_EFFECT_PRESENT`, `sites=["p800"]`; `G18` obligation = `ARTIFACT_VERIFIED`; `audit` says completed for `p800`; `sweep.findings` is empty. `user_summary.issues` lists only G05:2, G06 and G16. Nothing in the report tells the user that `p1207` is still old.
- Root cause is visible in scope mapping: `scope_mapping.coverage[G18].sections = ["S17"]` only; the summary section **S25** (`p986–p1317`) is omitted. `windows[0].sections` is `["S03","S04","S07","S16","S17","S20","S26"]` — S25 is absent. D02, by contrast, maps G18 to `["S17","S25"]` and both copies are changed. This is a real duplicate-copy coverage gap, not a subjective judgment.
- Regression signal: the baseline `682e68a` **plan** explicitly listed `G18 p800` **and** `G18 p1207`; its artifact has `p1207` correctly changed (“由于本基金A类、D类基金份额和C类基金份额费用收取不同…”). The `ff4d749` plan lists only `G18 p800`; the artifact has reverted `p1207` to the old text while still marking G18 complete. This is a plan-coverage regression, not just a sweep miss.

**G16 missing (true gap, blocker):** `p772` (body payment clause) and `p773` (body purpose/scope) are blank; `p1247` and `p1248` (summary copies) are blank; no G16 policy exists. The entire sales-service-fee payment/usage text is gone with no replacement.

**G05:2 falsely OPEN (absent):** D11’s class-setting clause `p129` ends “…调整前基金管理人需及时公告。” — no “并报中国证监会备案”. A normalized search finds 备案 only at unrelated `p726`, `p927`, `p1320`. The deletion is already satisfied, but `G05:B3:O1` has `targets=[]`, `target=MISSING`, `UNRESOLVED`. D01/D02 prove the same absence as `ALREADY_SATISFIED` at `p135`/`p138`; D11 is inconsistent.

**G06 falsely OPEN:** absent (zero “互相转换” hits); `T007` is `state=absent` but the obligation is `UNRESOLVED`.

**G03 placement (medium):** `p126` final inserts the new clause **between** “本基金 A 类、C 类和 D 类基金份额分别设置基金代码。” and “各类基金份额将分别计算基金份额净值。”. The target quote over-extends through the “设置基金代码” sentence, so the append lands mid-paragraph rather than after the 份额类别设置 clause. Text is authorized; placement is poor.

**Old finding BR-D11-002 (G02 A/D delimiter):** **CLOSED.** Both G02 operations are `ALREADY_SATISFIED` at `p91`, with the reason “原文已按实际分组表述，无需替换”; `p91` says “A 类及 D 类基金份额” and “C 类基金份额”. No false missing remains.

**Verdict for D11:** `incomplete` is correct, but the report understates the real residual set: **G16 is a true gap**, **G18 summary p1207 is a hidden false complete**, and **G05:2/G06 are false blocks**. The `delivery_gate` has only 3 open obligations; fixing/waiving those would flip the gate to pass with `p1207` still wrong. **BLOCK.**

---

### 3.4 D16 — G12/G13 and G17 body residual; G16 missing; G05/B-class old findings closed

**Artifact integrity:** `artifacts/D16/working_final.docx` SHA-256 `bbd5a437…4ff102`, matches report; binding `ff4d749` record; replay text identical.

**Actual changed paragraphs (14, all plan-exact):** `p91` G01; `p133` G03+G05:0+G05:2; `p217` G08; `p219` G09; `p220` G11; `p224` G14; `p822` G15; `p845` G18; `p1000` G22; `p1261` G18; `p1306` G15; `p1307/p1308` G17; `p1399` G22. The G05 splice at `p133` is correct: “调低赎回费率” → “调低销售服务费率”, and “并报中国证监会备案” is removed. G03’s append at `p133` is textually correct. G18 both copies (`p845`, `p1261`), G22 both copies (`p1000`, `p1399`), and G15 both copies (`p822`, `p1306`) are handled.

**G12/G13 residual (true fail-closed):** `p221`–`p222` are unchanged:
> `p221`: “赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用应根据法律法规规定的比例归入基金财产，未计入基金财产的部分用于支付登记费和其他必要的手续费。其中，对持续持有期少于”
> `p222`: “7 日的投资者收取不低于 1.5%的赎回费，并全额计入基金财产。”

This is a third historical variant (not G12:0/G12:1 and not G13:0). The plan dropped G12/G13 with `RECALL_EDIT_OVERLAP`; the locator bound G13 to `p222` but the attribution said `operation_span_mismatch`; the audit correctly says `wrong`; the sweep correctly says `pending`. This is a genuine unapplied edit, but it is **true fail-closed**, not a false complete. The business requirement is clear: replace the first sentence with “赎回费用全额计入基金财产。” and delete the 7-day sentence. A cross-paragraph merge is needed.

**G17 partial (true fail-closed, but inconsistent artifact):**

- Summary `p1307`: “销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。” → blanked.
- Summary `p1308`: “销售服务费使用范围不包括基金募集期间的上述费用。” → blanked.
- Body `p823`: the same purpose sentence → **unchanged**.
- Body `p824`: the same scope sentence → **unchanged**.

The claim replay explicitly catches `DUPLICATE_SITE_UNEDITED` at `p823` and `RESIDUAL_OLD_TEXT` at `p823`/`p824`; `G17:B1:O1` is `FAIL / RESIDUAL_OLD_TEXT` with sites `p1307, p1308, p823, p824`. The audit is split: `Y011 p1307` says completed (true), `T019 p823` says wrong (true). This is a true fail-closed, but the artifact now has a **body/summary contradiction** — worse than a consistently untouched draft. Not deliverable.

**G16 missing (true gap, blocker):** `p822` and `p1306` are blank; `p823/p824` retain the old purpose/scope; `p1307/p1308` are blank; no G16 policy exists. The body and summary fee sections no longer agree.

**G06 falsely OPEN (absent):** zero “互相转换” hits; `G06:B1:O1` has no target and `UNRESOLVED`. Same systemic false block.

**Old finding BR-D16-003 (G05 wrong site p427/p1165):** **CLOSED** for the business claim. `G05:B1:O1` claim sites are `["p133"]` only; `p133` is correctly spliced. `p427` and `p1165` are only `survey_satisfied` rows (`state=satisfied`, `resolution=unresolved`, `status=not_planned`) citing “调低销售服务费率”; they are **not** in the verified site set and did not drive completion. Residual hygiene issue: those inert false-positive rows should still be removed, but they are no longer a false block.

**Old finding BR-D16-006 (audit B-class vs A/C):** **CLOSED in D16.** `audit.issues` contains no G02/G04 B-class conclusion. The target reasons now say “实际份额类别为A类、C类…无需替换为B类等额外类别”, and G02/G04 are `ALREADY_SATISFIED` at `p91`/`p129`. The 21 “B类” strings remaining in `reports/D16.json` are guide templates/window reasons, not audit conclusions. **However, the same defect is now live in D01** (see §3.1 and BR-FF-008).

**Verdict for D16:** `incomplete` is correct; real gaps **G12/G13, G16, G17 body**; **G06 false block**; **G17 partial body/summary inconsistency**. Not deliverable.

---

## 4. Old-finding closure table

Status vocabulary: **CLOSED** = the specific old defect is gone with concrete evidence; **PARTIAL** = part closed, part still live; **OPEN** = still live; **CONFIRMED** = the old finding remains true (including expected fail-closed).

| Old ID | Old claim | New status | Evidence / reason |
|---|---|---|---|
| **BR-D01-001** | No `working_final.docx`; `EDIT_OVERLAP_OR_ADJACENT` stopped audit | **PARTIAL — no-artifact CLOSED; overlap OPEN** | `artifacts/D01/working_final.docx` exists, SHA-256 `80a87bd8…`, matches `reports/D01.json output_validation.final_sha256`; `replay/D01/working_final.docx` exists with identical text; replay `errors=[]`, `delivery=incomplete`. The overlap is not gone: G17 targets `p759/p760/p1222/p1223` were dropped with `plan_reason=RECALL_EDIT_OVERLAP`. G15 is `p758 0–135`; G17 is `p759 0–52`/`p760 0–24` — adjacent, not overlapping. Residual text remains at all four sites. The stale `index.json` still says D01 `not_generated` with `EDIT_OVERLAP_OR_ADJACENT`; that is contradicted by the per-case replay. |
| **BR-D02-001** | Placeholder absent targets at `p1036` (summary heading) used as verified sites; G05:2/G06:0 PASS VERIFIED_ABSENT | **CLOSED** | `p1036` is not a target location or claim site in `reports/D02.json`; it occurs only in scope/window `locations`. G05:2’s absent proof is at `p138` (the real class-setting clause) with identical before/after quotes; G06 is `OPEN`, not `PASS VERIFIED_ABSENT`. |
| **BR-D02-004** | G05:2/G06:0 cannot be ALREADY_SATISFIED from unrelated p1036; source has no G05 filing phrase / no G06 prohibition | **CLOSED** | Source class clause `p138` has no “并报中国证监会备案” (unrelated occurrences only at `p766/p767`); no “互相转换” anywhere. G05:2 is `ALREADY_SATISFIED` from `p138`, which is the correct clause. G06 is no longer called satisfied. |
| **BR-D11-002** | G02:0 already satisfied by A/D wording at p91 but claim reports FAIL | **CLOSED** | `G02:B1:O1` and `G02:B1:O2` are `ALREADY_SATISFIED`, claim `PASS`, site `p91`; `p91` says “A 类及 D 类基金份额” and “C 类基金份额”. |
| **BR-D11-001** | G06:0 PASS VERIFIED_ABSENT at unrelated p129 heading | **CLOSED as false PASS; new false OPEN** | G06 is no longer `PASS`; it is `UNRESOLVED` with no sites. The old false PASS is gone. The new behavior is a false block (BR-FF-009), not a false complete. |
| **BR-D16-003** | G05 claim treats p427/p1165 meeting-exemption lists as class-setting sites; real splice p133 correct | **CLOSED** | `G05:B1:O1` claim sites = `["p133"]`; `p133` is correctly spliced. `p427`/`p1165` are only inert `survey_satisfied` rows (`status=not_planned`), not verified sites. |
| **BR-D16-006** | Audit G02/G04 reports missing B class while Facts are A/C | **CLOSED in D16; defect migrated to D01** | D16 `audit.issues` has no G02/G04 B-class conclusion; target reasons explicitly say “无需替换为B类”. But D01 `audit.issues[4]` now demands B类 while D01 facts are A/C/D — same defect class, new case (BR-FF-008). |
| BR-D16-001 | G12/G13 overlapping same-site edits failed at p221–p222; exact old text remains; claim RESIDUAL_OLD_TEXT | **OPEN / CONFIRMED** | `p221`–`p222` unchanged; audit `wrong`; sweep `pending`; claim `FAIL / RESIDUAL_OLD_TEXT`. True fail-closed. |
| BR-D16-002 | G17 usage text remains at p823/p824 and p1307/p1308 | **PARTIAL / OPEN** | Summary `p1307/p1308` now blank; body `p823/p824` still old. Claim `DUPLICATE_SITE_UNEDITED` at p823. True fail-closed, but the artifact is now body/summary inconsistent. |
| BR-D16-004 | G01 append missing at p91; G16 has no verified site and is OPEN | **PARTIAL** | G01 is now applied at `p91` (claim `PASS`, `EXPECTED_EFFECT_PRESENT`). G16 is still missing in all four. |
| BR-D16-005 | G03/G08/G09/G11/G14/G15/G18/G22 effects authorized and correct; G05:2 at p133 valid; G06 correctly OPEN | **CLOSED for applied edits; G06 classification changed** | The listed edits are textually correct in the artifact. G05:2 at p133 is present-before/absent-after. G06 is no longer “correctly OPEN”; it is a false OPEN because the text is absent. |
| BR-D02-002 | G16 four-component payment policy absent; OPEN is correct fail-closed | **CONFIRMED / OPEN** | No G16 policy in D02 `p821–p823` or `p1287–p1289`; true business gap. |
| BR-D02-003 | G01 p93 append genuinely missing; G14 alternatives are one business ONE_OF | **CLOSED for G01; G14 note valid** | G01 is now applied at `p93`; G14 final policy is correct at `p232`. The G14 ALREADY alternatives are still double-counted (BR-FF-011). |
| BR-D02-005 | G05/G08/G09/G11/G12/G13/G14/G15/G17/G18/G22 changed text authorized and correct; no unauthorized edit | **PARTIAL** | The applied edits are correct, but G12/G13 are **no longer applied** at `p229` (BR-FF-003). The “no unauthorized edit” part remains true at paragraph level. |
| BR-D11-003 | G05:2 OPEN/UNPROVEN appropriate fail-closed; G16 OPEN | **PARTIAL** | G16 is still a true OPEN. G05:2 is absent from the business clause and should be `ALREADY_SATISFIED`, not `UNPROVEN` (BR-FF-009). |
| BR-D11-004 | G03/G05/G08/G09/G11/G12/G13/G14/G15/G17/G18/G22 actual changes authorized; no plan-artifact mismatch | **PARTIAL** | Applied changes are correct, but G18 summary `p1207` is missed (BR-FF-002) and G03 is inserted mid-paragraph at `p126` (BR-FF-010). |

---

## 5. True vs false incompletes

### True fail-closed (real business gap, correctly blocked)

| Case | Rule | Real residual | Evidence |
|---|---|---|---|
| D01 | G01 | 释义 `p92` lacks the direct-sales/C-fee clause | final contains the clause only at `p130`; no G01 target |
| D01 | G16 | No four-component sales-service-fee policy | `p758` blank; `p759/p760` old purpose/scope; no G16 text |
| D01 | G17 | `p759/p760` and `p1222/p1223` still contain the purpose/scope sentences | exact quotes; claim `RESIDUAL_CONFIRMED` |
| D02 | G12/G13 | `p229` unchanged: proportional allocation + 7-day/1.5% sentence | exact quote; claim `NOT_PLANNED`; sweep `pending` |
| D02 | G16 | No policy; `p821–p823` and `p1287–p1289` blank | final text |
| D11 | G16 | No policy; `p772–p773` and `p1247–p1248` blank | final text |
| D16 | G12/G13 | `p221–p222` unchanged | exact quote; claim `RESIDUAL_OLD_TEXT` |
| D16 | G16 | No policy; `p822`/`p1306` blank; body purpose/scope still old | final text |
| D16 | G17 | Body `p823/p824` still old while summary `p1307/p1308` blank | claim `DUPLICATE_SITE_UNEDITED` |

**All four case-level `incomplete` verdicts are justified by at least G16 alone.** There is no case-level false incomplete.

### False block / unsupported incompleteness (no real business defect)

| Case | Rule | Why it is false | Evidence |
|---|---|---|---|
| D01 | G02 | `p92` already says “A 类及 D 类基金份额 … C 类基金份额”; the target is truncated at `p91`; the audit demands a non-existent B类 | `p91` quote ends “三种不同的”; `p92` grouping; facts A/C/D |
| D01 | G06 | The prohibited-conversion clause is absent; nothing to delete | zero “互相转换” hits; `G06` unresolved with no site |
| D02 | G06 | Same absence | zero hits; target `state=absent` but obligation `target=FOUND/FAIL` |
| D11 | G05:2 | `p129` has no “并报中国证监会备案”; unrelated 备案 at p726/p927/p1320 | normalized search; D01/D02 same absence is `ALREADY_SATISFIED` |
| D11 | G06 | Same absence | zero hits; `UNRESOLVED` |
| D16 | G06 | Same absence | zero hits; `UNRESOLVED` |

These false blocks are not harmless: they keep the gate red even after the real edits are fixed, and they distort the user’s “what is missing” report.

### False complete (claimed complete but artifact is not)

| Case | Where | What is claimed | What is actually in the DOCX |
|---|---|---|---|
| **D11** | G18 summary `p1207` | `G18:B1:O1` `ARTIFACT_VERIFIED`, claim `PASS`, site `p800`; audit completed for `p800`; sweep empty; user_summary lists only G05:2/G06/G16 | `p1207` still “由于本基金 A 类基金份额和 D 类基金份额不收取销售服务费，而 C 类基金份额收取销售服务费…” |
| **D02** | G12/G13 audit | target audit `completed`, `evidence_verified=true`; report “审计完成 1/1”, “未决问题 0” | `p229` unchanged full old sentence; claim `NOT_PLANNED`; sweep `pending` |

The D02 false complete is at audit level (the obligations remain `UNRESOLVED`, so the ledger still blocks). The D11 false complete is at **obligation level**, which is more dangerous because it is invisible to the delivery gate.

---

## 6. Authorization, plan-to-artifact and “beyond authorization”

**Plan-to-artifact is exact (positive).** For every case, reconstructing the final paragraph from the original plus the plan’s `(start,end,replacement)` spans gives an exact text match, and **no changed paragraph is outside the plan**:

| Case | Plan edits | Changed paragraphs | Reconstructed mismatches | Unplanned changed paragraphs |
|---|---|---|---|---|
| D01 | 14 | 14 | 0 | none |
| D02 | 16 | 16 | 0 | none |
| D11 | 14 | 14 | 0 | none |
| D16 | 14 | 14 | 0 | none |

Therefore: **no planned-but-not-artifact drift; no paragraph-level unauthorized edit.** The misses are pre-plan (no target / target not planned / plan component dropped), not execution drift.

**Authorization-scope notes (not paragraph drift):**

1. **G15 deletes non-exact old_text variants.** The certified G15 old_text is the 10-working-day instruction clause (“C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金托管人发送…10个工作日内…支付给登记机构…”). The deleted paragraphs are contract-specific variants:
   - D01 `p758`: “基金销售服务费每日计提…次月前 5 个工作日内…划出，由基金管理人代收…”
   - D02 `p821`: “基金销售服务费每日计算…自动在月初 5 个工作日内…资金支付…无需再出具资金划拨指令…”
   - D11 `p772`: “C类基金份额的销售服务费每日计提…次月初五个工作日内…注册登记机构代收…”
   - D16 `p822`: “基金销售服务费每日计提…次月前 5 个工作日内…自动支付/扣划…”
   These are semantically the same “old payment clause” and the business notice flags the 5-vs-10-day discrepancy, so the deletion is defensible as G15’s intent. But it is **not literally the certified old_text**, and because G16 is missing it is a net content loss. Treat as “authorized in intent, unsafe in effect”, not as a clean literal G15.
2. **G18 class expansion to A/D/C** in D01/D11 is beyond the literal G18 new_text (“A类基金份额和C类基金份额费用收取不同”). It is necessary to preserve the real D类 and is consistent with the facts; I do not classify it as unauthorized. The literal A/C-only text would be wrong for a three-class fund.
3. **D11 G03 insertion at `p126`** is authorized text but placed after “分别设置基金代码” rather than after the 份额类别设置 clause. This is a placement quality issue, not an unauthorized edit.
4. **D16 G17 summary-only deletion** is a targeted edit but leaves the body copy old. It is a partial application, not an unauthorized paragraph.

**Unsupported `VERIFIED_ABSENT`:** none found at the current sites. The old D02 `p1036` issue is fixed; D01/D02 G05:2 and D16 G05:2 are supported by the correct clause; D01/D11 G13 and D02/D11 G17 are supported by real prior text. The problem is the opposite: **absent text is sometimes not accepted as satisfied** (G06, D11 G05:2).

---

## 7. Cross-cutting defects

### BR-FF-001 (BLOCKER) — G16 missing in all four; G15 deletions leave the fee section gutted
- D01: `p758` blank, `p1221` blank; `p759/p760` and `p1222/p1223` old purpose/scope; no G16.
- D02: `p821–p823` blank, `p1287–p1289` blank; no G16.
- D11: `p772–p773` blank, `p1247–p1248` blank; no G16.
- D16: `p822` blank, `p1306` blank; `p823/p824` old purpose/scope; `p1307/p1308` blank; no G16.
- Business effect: the contract no longer states the sales-service-fee payment/return policy; in D02/D11 the purpose/scope is also gone. This is a real content loss, not merely an unproven claim. The reports correctly keep G16 `UNRESOLVED`, but the artifacts should not be delivered.
- Root cause: the G16 append target is always the G17 “scope” sentence and is rejected with `TARGET_SOURCE_MISMATCH`; no G16 target is planned in any case.

### BR-FF-002 (BLOCKER) — D11 G18 summary `p1207` false complete
- `p800` new, `p1207` old; `G18:B1:O1` `ARTIFACT_VERIFIED` with sole site `p800`.
- Scope map G18 `["S17"]` omits S25; window sections omit S25; sweep findings empty.
- Baseline `682e68a` had `p1207` changed; `ff4d749` regressed it. If the 3 open D11 obligations were fixed/waived, the gate would pass with `p1207` still old.

### BR-FF-003 (BLOCKER) — D02 G12/G13 real miss + audit false completion
- `p229` unchanged; exact old sentence remains.
- Target audit `completed`, `evidence_verified=true`; report “审计完成 1/1”, “未决问题 0”; sweep `pending`; claim `NOT_PLANNED`.
- D11 shows the same overlap can be merged; D02’s `RECALL_PLAN_COMPONENT_DROPPED` is a generation defect, and the audit’s “completed” is a verification defect.

### BR-FF-004 (HIGH) — D01 G01 missing at 释义 `p92`
- Real missing append. The final contains the clause only at the G03 site `p130`; the 释义 definition is split across `p91/p92` and has no target. True fail-closed.

### BR-FF-005 (HIGH) — D01 G17 dropped by false `RECALL_EDIT_OVERLAP`
- G15 `p758 0–135`; G17 `p759 0–52`, `p760 0–24`, plus `p1222/p1223`. These are adjacent/disjoint, not overlapping. The plan dropped all four targets; the artifact has `p758/p1221` blank and all four G17 sentences intact. The old BR-D01-001 overlap defect is therefore still live in substance.

### BR-FF-006 (HIGH) — D16 G17 partial body/summary edit
- Summary `p1307/p1308` blank; body `p823/p824` old. Claim correctly flags `DUPLICATE_SITE_UNEDITED`; obligation is `FAIL / RESIDUAL_OLD_TEXT`. True fail-closed, but the body and summary now contradict each other. Do not deliver.

### BR-FF-007 (HIGH) — D16 G12/G13 real residual
- `p221–p222` unchanged; third historical variant; `RECALL_EDIT_OVERLAP` + `operation_span_mismatch`; audit `wrong`; sweep `pending`. True fail-closed.

### BR-FF-008 (HIGH) — D01 G02 false block + B-class audit contradicts certified facts
- `p92` already satisfies the A/D + C grouping; target is truncated at `p91`; `audit.issues[4]` demands `A类、B类` while facts are A/C/D; obligation `new_text` is the uninstantiated template. This is the old BR-D16-006 defect migrated to D01. It also puts a factually wrong “affected_fact” in the user-facing unresolved list.

### BR-FF-009 (HIGH) — G06 false OPEN in all four; D11 G05:2 false OPEN
- G06 text is absent in all four (zero “互相转换” hits); yet all four have `G06:B1:O1 = UNRESOLVED / CLAIM_REPLAY_FAILED` with no site. D11 G05:2 is absent at `p129` but `target=MISSING/UNRESOLVED`, while D01/D02 treat the same absence as `ALREADY_SATISFIED`. These false blocks prevent a legitimate pass and distort the unresolved list.

### BR-FF-010 (MEDIUM) — D11 G03 mid-paragraph insertion
- `p126` inserts the new clause between “分别设置基金代码。” and “各类基金份额将分别计算基金份额净值。”. The target quote over-extends through the code sentence. Authorized text, poor placement; it interrupts the code/NAV explanation.

### BR-FF-011 (MEDIUM) — ONE_OF alternatives counted as ALREADY_SATISFIED (completion inflation)
- D01: G11:B1:O2 (alt of O1), G12:B1:O1 (alt of O2), G14:B2:O2/O3 (alts of O1) are counted `ALREADY_SATISFIED` while their sibling was applied. They are one business obligation per ONE_OF group, not separate completions.
- Similar in D02 (G11:O2, G14:O1/O2), D11 (G11:O1, G12:O2, G14:O2/O3), D16 (G11:O1, G14:O2/O3).
- Effect: `completion_counts` and “true_obligations=24” overstate business completion. It does not by itself claim delivery complete, but it makes the gate metrics look better than the business truth.

### BR-FF-012 (HIGH, evidence integrity) — `index.json` is stale/contradictory
- `index.json replay_results.D01` says `head=682e68a`, `delivery=not_generated`, `errors=[EDIT_OVERLAP_OR_ADJACENT]`; `summaries/D01-replay.json` and `replay/D01/report.json` say `head=ff4d749`, `delivery=incomplete`, `errors=[]`, and `replay/D01/working_final.docx` exists. `record_results` is `{}` despite record summaries. The gate reason “D01 artifact not generated due to stable-identity replan bug” is false for this evidence root. The gate `FAIL` may still be right, but its published reasons must be replaced.

### BR-FF-013 (MEDIUM) — rule-level report classifications mislead
- D16 report.md shows G13 “应改 0 / 不适用 1” and G17 “应改 0 / 不适用 1”, while both are mandatory and the artifact has residual text; the unresolved list does include them, so the report contradicts itself.
- D02 report.md says “未决问题 0” and G12/G13 “审计完成 1/1” while the sweep says pending and the claim says not planned.
- D11 report.md says G18 “审计完成 1/1” and “未决问题 0” while `p1207` is old.
- D01 report.md says G01/G02 “no_target_found” while G02 has targets and audit issues; G17 “no_target_found” while there are four G17 targets.

### BR-FF-014 (LOW/MEDIUM, authorization note) — G15 non-exact old_text
- See §6.1. The deletion is semantically aligned with G15 but not literally the certified old_text. Combined with missing G16, it is unsafe. This is a scope/authorization note, not a paragraph-level unauthorized edit.

### BR-FF-015 (MEDIUM, latent) — class-substitution is not applied to obligation `new_text`
- All four reports’ `G02:B1:O1/O2` obligations still say `A类、B类基金份额` / `C类、D类基金份额`. D01’s audit read this literally and demanded B类. D02/D11/D16 escaped only because their G02 was already satisfied and not audited. Any future G02 audit on a multi-class fund can reproduce the false block.

### BR-FF-016 (LOW) — D16 G01 audit verdict missing
- `AUDIT_VERDICT_MISSING` for G01 at `p91`, although the artifact has the G01 append and the claim replay `PASS`. Audit coverage gap, not a business defect.

---

## 8. Gate recommendation

**Recommendation: BLOCK / FAIL — do not deliver D01, D02, D11 or D16 `working_final.docx`.**

Why BLOCK, despite the truthful `delivery=incomplete`:

1. **Real content loss in all four.** G16 is a mandatory business requirement and is absent in every artifact; G15 deletions removed the old payment clause. D02/D11 also removed the purpose/scope. These are not “unproven” claims; the final documents are missing required contract text.
2. **D11 has a hidden false complete.** G18 summary `p1207` is old but marked `ARTIFACT_VERIFIED`. The delivery gate has only 3 open D11 obligations (G05:2, G06, G16); fixing/waiving those would flip D11 to pass with the summary still wrong. This is the single most dangerous verification defect in the set.
3. **D02 audit falsely marks G12/G13 complete.** The artifact is unchanged; the audit says completed. The claim/sweep still block, but the audit cannot be trusted as evidence.
4. **D16’s G17 is only half-applied** (summary deleted, body retained), leaving a body/summary contradiction. Even though it is fail-closed, the artifact is not a coherent draft.
5. **D01’s G01 and G17 are real gaps**, and the G17 drop is caused by a false overlap classification, not by a real span conflict.
6. **False blocks (G06 all, D01 G02, D11 G05:2) will keep the gate red after the real edits are fixed.** A clean pass requires fixing the proof model, not just the documents.

**The existing `index.json gate=FAIL` is substantively correct, but its reasons are stale.** Replace:
- “D01 artifact not generated due to stable-identity replan bug” → **false** at this root; D01 artifact exists and replay is deterministic.
- “Absent inventory placeholders accepted as proof sites” → **fixed** for D02 (`p1036` no longer a target/site).
- Keep: G16 missing; D11 G18 summary false complete; D02 G12/G13 audit false complete; D16 G17 partial; D01 G01/G17; false blocks.

**Minimum clearing conditions for the next revalidation:**
1. Implement G16 in all four (body and summary copies), with the four components (daily accrual; direct-sales return on redemption/termination; other-agency monthly payment; >1-year return).
2. D02: merge G12+G13 at `p229` (use the D11 `p210` combined-edit pattern) and verify the artifact, not the plan.
3. D16: merge G12+G13 across `p221–p222`; delete G17 in **both** body `p823/p824` and summary `p1307/p1308`.
4. D01: append G01 at 释义 `p92`; delete G17 at `p759/p760` and `p1222/p1223`; remove the false `RECALL_EDIT_OVERLAP`.
5. D11: add G18 summary `p1207`; map G18 to S25; remove the false G05:2/G06 blocks.
6. Fix the class-substitution audit path (D01 G02) and the absence proof path (G06; D11 G05:2).
7. Refresh `index.json` from the per-case ff4d749 record/replay summaries; do not carry 682e68a replay results into this root.

---

## 9. Positive checks (what is genuinely good)

- **Hash bindings are correct.** All four `working_final.docx` SHA-256 values equal the report `output_validation.final_sha256`; all four `original.docx` SHA-256 values equal `source_sha256`; guide document SHA-256 matches the certified guide.
- **Replay is deterministic and text-identical.** `replay/Dxx/working_final.docx` text equals `artifacts/Dxx/working_final.docx` for all four; the replay reports have `calls=0`, `errors=[]`, and the same plan.
- **Plan-to-artifact is exact.** 14/14, 16/16, 14/14, 14/14 changed paragraphs; no unplanned changed paragraph; no reconstructed mismatch.
- **Most applied edits are textually correct** at their real sites: G05:0, G08, G09, G11, G14, G22 in all four; G12/G13 in D01/D11; G01/G03 in D02/D11/D16; G05:2 in D16; G18 in D01/D02/D16.
- **D02 `p1036` placeholder issue is fixed**; G05:2/G06 are scoped to the real clause `p138`.
- **D11 G02 A/D delimiter issue is fixed** (ALREADY_SATISFIED at `p91`).
- **D16 G05 real site is fixed** (`p133`; claim sites `p133` only; p427/p1165 inert).
- **D16 B-class audit issue is fixed** (no G02/G04 B-class conclusion; target reasons say “无需替换为B类”).
- **Model-call ledgers are clean:** D01 32, D02 35, D11 29, D16 34 calls; all HTTP 200 / completed; total charged cost ≈ $0.1174; no error codes. Replay uses 0 calls. This is consistent with the index budget and `production_budget_modified=false`.

---

## 10. Evidence map (for reproduction)

- `reports/D01.json`: `plan.edits` (14), `targets[T3001/T3002]` (truncated p91), `audit.issues[4]` (B-class), `unresolved[10]`, `artifact_claim_replay.failures` (G01/G02/G06/G16/G17), `obligations.records[G18]`.
- `reports/D02.json`: `plan.edits` (16; no G12/G13), `targets[T016/T017]` (audit completed), `sweep.findings` SW002/SW003 (pending), `artifact_claim_replay.obligations` G12/G13 (OPEN/FAIL), `targets[T009/T010]` (G05:2/G06 at p138).
- `reports/D11.json`: `targets[T019]` (G18 p800 completed), `artifact_claim_replay.obligations["G18:B1:O1"].sites=["p800"]`, `scope_mapping.coverage[G18].sections=["S17"]`, `windows[0].sections` (no S25), `sweep.findings=[]`.
- `reports/D16.json`: `targets[T014]` (G12 wrong), `targets[T019]` (G17 p823 wrong), `artifact_claim_replay.obligations["G17:B1:O1"].sites=["p1307","p1308","p823","p824"]`, `failures` (`DUPLICATE_SITE_UNEDITED` p823), `target_locator` (G13 p222 bound but attribution mismatch).
- `artifacts/Dxx/working_final.docx`: p130/p135/p226–p231/p758/p785/p934/p1191/p1221/p1299 (D01); p93/p138/p226–p228/p232/p821–p823/p848/p1001/p1257/p1287–p1289/p1371 (D02); p91/p126/p129/p208–p213/p772–p773/p800/p951/p1247–p1248/p1344 (D11); p91/p133/p217/p219–p220/p224/p822/p845/p1000/p1261/p1306–p1308/p1399 (D16).
- `ledgers/Dxx.csv`: 32/35/29/34 rows, all `completed`, HTTP 200, no `error_code`.
- `summaries/D01-replay.json` / `replay/D01/report.json`: `delivery=incomplete`, `errors=[]`; contradicts the stale `index.json`.

---

**Final recommendation: BLOCK. The four `delivery=incomplete` claims are truthful, but the artifacts are unsafe, D11 contains a hidden obligation-level false complete, D02 contains an audit false complete, and several unresolved items are false blocks rather than real defects. Fix the real gaps and the proof model before any delivery or gate pass.**
