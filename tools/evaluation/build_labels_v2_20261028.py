#!/usr/bin/env python3
"""Build v2 labels by adjudicating the independent reviewer's v1 findings.

Reads only v1 labels, the frozen selection, the guide and the original contracts.
Never reads engine reports/artifacts. The adjudicator is a real model outside the
engine model family; every finding is either applied or explicitly moved to
`uncertain` with a reason (no silent deletion to make the labels pass).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/evaluation/first_batch_label_20261028.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("first_batch_label_tool_v2", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = load_tool()
FINDING_TYPES = ("missing_targets", "incorrect_targets", "fact_issues", "status_issues", "uncertain")


def build_findings(case: dict) -> list[dict]:
    findings: list[dict] = []
    counter = 0
    review = case.get("review") or {}
    for ftype in FINDING_TYPES:
        for index, item in enumerate((review.get("findings") or {}).get(ftype) or []):
            counter += 1
            findings.append({
                "finding_id": f"R{counter:03d}",
                "type": ftype,
                "index": index,
                "content": item,
            })
    return findings


def compact_labels_for_prompt(case: dict) -> dict:
    return {
        "fund": case.get("fund"),
        "targets": [
            {
                "target_id": t.get("target_id"), "rule_id": t.get("rule_id"), "op": t.get("op"),
                "scope": t.get("scope"), "paragraph_index": t.get("paragraph_index"),
                "old_text": t.get("old_text"), "required_text": t.get("required_text"),
                "anchor_quote": t.get("anchor_quote"), "source_quote": t.get("source_quote"),
                "provenance": t.get("provenance"),
            }
            for t in case.get("targets") or []
        ],
        "rule_coverage": [
            {"rule_id": c.get("rule_id"), "scope": c.get("scope"), "status": c.get("status"),
             "paragraph_index": c.get("paragraph_index"), "reason": c.get("reason")}
            for c in case.get("rule_coverage") or []
        ],
        "uncertain": case.get("uncertain") or [],
    }


def adjudication_prompt(doc, guide_text: str, case: dict, findings: list[dict]) -> str:
    return f"""
# 任务
你是独立标签复核的裁定人。下面是一份基金合同、指引规则、当前 v1 标签，以及独立复核人
提出的全部 findings。请逐条核对指引与合同原文，给出裁定：能确证的改正/补入，不能确证的
放入 uncertain（写明理由）。不得为了“通过”而删除或弱化已有目标；也不得把范围外内容塞进
标签。

裁定选项（每条 finding 必须给一个）：
- `accept_add`：missing_target 确证存在，给出完整 target（字段见下）。
- `accept_modify`：现有 target 确有错误，给出 target_id 与需要改正的字段。
- `accept_fact`：事实确有错误/需补强，给出 fact_correction（字段路径 + 新值 + 逐字证据）。
- `accept_status`：coverage 状态确有错误，给出 status_correction。
- `reject`：finding 错误、越界或已被现有站点覆盖；写明理由。
- `uncertain`：合同+指引不能唯一确定；写明理由与备选。

判断基线：
1. 指引只授权范围内的修改；范围外不新增、不去重、不润色。
2. G16 的“在原条款最后增加”在旧支付段(G15)和用途句(G17)会被删除时，锚在费率/公式段末尾
   是合理落点；不要仅因锚点不在旧支付段之后就判错（删除后最终顺序一致）。
3. replace/delete 的 old_text 可以是“最小必要片段”；只要它逐字来自原文并能实现该规则义务，
   不要求把整句/整段都塞进去。但若当前片段无法实现义务（例如 G12 只改比例句、未把“归入比例”
   旧义务替换掉），应按指引纠正。
4. G15 删除旧支付安排时，合同实际 5 日/自动划付/无需指令等变体仍属应删除对象（既有裁定）；
   不要求与指引示例逐字相同。
5. G14 变体（“适当调整”“基金”前缀等）按实际措辞的语义替换处理。
6. 份额类别事实：`share_classes` 的收费组按 A/C 等收费规则记录；QDII/币种子份额另列
   `currency_variants`，不要把币种子类别混入收费组，也不要因此改动 G02/G04 的收费组替换。
7. 摘要与正文是独立站点；摘要重复站点必须各有 target（如 p1296 附近摘要 G15/G16）。
8. 不确定时宁可 uncertain，不伪造 gold；但也不要把已确证的站点因复核意见就降级。

# 指引规则
{guide_text}

# 合同原文（pNNNN 为零基段号；[M]正文 [S]摘要）
{tool.contract_prompt(doc)}

# 当前 v1 标签
{json.dumps(compact_labels_for_prompt(case), ensure_ascii=False, indent=1)}

# 复核 findings（逐条裁定）
{json.dumps([{"finding_id": f["finding_id"], "type": f["type"], "content": f["content"]} for f in findings], ensure_ascii=False, indent=1)}

# 输出 JSON
{{
  "resolutions": [
    {{"finding_id": "R001", "decision": "accept_add|accept_modify|accept_fact|accept_status|reject|uncertain",
      "reason": "依据",
      "target": {{"rule_id": "G16", "op": "append|replace|delete", "scope": "main|summary",
                  "paragraph_index": 0, "old_text": "", "required_text": "",
                  "source_quote": "", "anchor_quote": null, "anchor_position": null,
                  "requirement": "", "class_scope": [], "guide_paragraphs": [], "rationale": ""}},   // accept_add
      "correction": {{"target_id": "T001", "paragraph_index": 0, "scope": "main",
                      "old_text": "", "required_text": "", "source_quote": "", "anchor_quote": null}}, // accept_modify
      "fact_correction": {{"field": "fund_type_evidence.paragraph_index", "value": 105, "evidence": "逐字证据"}}, // accept_fact；value 必填，字段路径用点号/下标
      "status_correction": {{"rule_id": "G08", "scope": "main", "status": "target|satisfied|not_applicable|unknown",
                            "paragraph_index": 0, "reason": ""}}                                     // accept_status
    }}
  ]
}}
只输出上述 JSON。
"""


def scorer_facts(fund: dict) -> dict:
    classes = []
    for item in fund.get("share_classes") or []:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        classes.append({
            "name": label if label.endswith("基金份额") else f"{label}类基金份额",
            "subscription_fee": bool(item.get("pays_purchase_fee")),
            "service_fee": bool(item.get("charges_sales_service_fee")),
        })
    return {
        "classes": classes,
        "class_count": fund.get("class_count"),
        "class_count_basis": "fee_group",
        "has_sales_service_fee": fund.get("has_sales_service_fee"),
        "floating_management_fee": fund.get("floating_management_fee"),
        "fund_type": fund.get("fund_type"),
        "currency_variants": fund.get("currency_variants") or [],
    }


def _normalise_target(raw: dict, doc, rule_map: dict) -> dict | None:
    normalised, errors = tool.normalize_targets([raw], doc, rule_map)
    if errors or not normalised:
        return None
    return normalised[0]


def _apply_target_correction(target: dict, correction: dict, doc, rule_map: dict) -> dict | None:
    merged = dict(target)
    for key in ("rule_id", "op", "scope", "paragraph_index", "old_text", "required_text",
                "source_quote", "anchor_quote", "anchor_position", "requirement",
                "class_scope", "guide_paragraphs", "rationale"):
        if key in correction and correction[key] is not None:
            merged[key] = correction[key]
    normalised = _normalise_target(merged, doc, rule_map)
    if normalised is None:
        return None
    normalised["target_id"] = target["target_id"]
    normalised["review_flags"] = list(target.get("review_flags") or []) + ["review_v2"]
    normalised["provenance"] = "review_adjudication"
    return normalised


def _set_path(obj, path: str, value) -> bool:
    parts = [part for part in path.split(".") if part]
    if not parts:
        return False
    cur = obj
    for part in parts[:-1]:
        match = None
        import re as _re
        m = _re.match(r"^(\w+)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(cur, dict) and isinstance(cur.get(key), list) and idx < len(cur[key]):
                cur = cur[key][idx]
                continue
            return False
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    last = parts[-1]
    m = __import__("re").match(r"^(\w+)\[(\d+)\]$", last)
    if m:
        key, idx = m.group(1), int(m.group(2))
        if isinstance(cur, dict) and isinstance(cur.get(key), list) and idx < len(cur[key]):
            cur[key][idx] = value
            return True
        return False
    if isinstance(cur, dict):
        cur[last] = value
        return True
    return False


def _apply_fact_correction(fund: dict, correction: dict, doc) -> bool:
    field = correction.get("field")
    value = correction.get("value")
    if not field or value is None:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        if field.endswith("paragraph_index") or field in {"class_count"}:
            if stripped.isdigit():
                value = int(stripped)
    if field in {"share_classes", "classes"} and isinstance(value, list):
        classes = []
        for item in value:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "").replace("类基金份额", "").strip()
            classes.append({
                "label": label,
                "pays_purchase_fee": item.get("pays_purchase_fee"),
                "charges_sales_service_fee": item.get("charges_sales_service_fee"),
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), dict) else None,
            })
        fund["share_classes"] = classes
        fund["class_count"] = len(classes) or fund.get("class_count")
        return True
    return _set_path(fund, field, value)


def apply_resolutions(case: dict, findings: list[dict], resolutions: dict, doc, rule_map: dict) -> tuple[dict, list[dict]]:
    by_id = {f["finding_id"]: f for f in findings}
    targets = list(case.get("targets") or [])
    coverage = list(case.get("rule_coverage") or [])
    uncertain = list(case.get("uncertain") or [])
    resolutions_out: list[dict] = []
    returned = set()
    for item in resolutions.get("resolutions") or []:
        fid = item.get("finding_id")
        if fid not in by_id:
            continue
        returned.add(fid)
        finding = by_id[fid]
        decision = item.get("decision")
        record = {
            "finding_id": fid,
            "type": finding["type"],
            "decision": decision,
            "reason": item.get("reason"),
            "applied": False,
        }
        if decision == "accept_add" and isinstance(item.get("target"), dict):
            new_target = _normalise_target(item["target"], doc, rule_map)
            if new_target is not None:
                # Avoid exact duplicate sites.
                duplicate = any(
                    t["rule_id"] == new_target["rule_id"] and t["scope"] == new_target["scope"]
                    and t["paragraph_index"] == new_target["paragraph_index"]
                    and tool.compact(t["old_text"]) == tool.compact(new_target["old_text"])
                    and t["op"] == new_target["op"]
                    for t in targets
                )
                if not duplicate:
                    new_target["provenance"] = "review_adjudication"
                    new_target["review_flags"] = ["review_v2"]
                    targets.append(new_target)
                record["applied"] = True
                record["target_rule"] = new_target["rule_id"]
            else:
                record["decision"] = "uncertain"
                record["reason"] = (record.get("reason") or "") + " | target failed validation"
        elif decision == "accept_modify" and isinstance(item.get("correction"), dict):
            correction = item["correction"]
            tid = correction.get("target_id")
            replaced = False
            for idx, target in enumerate(targets):
                if target.get("target_id") == tid:
                    new_target = _apply_target_correction(target, correction, doc, rule_map)
                    if new_target is not None:
                        targets[idx] = new_target
                        replaced = True
                        record["applied"] = True
                        record["target_id"] = tid
                    else:
                        record["decision"] = "uncertain"
                        record["reason"] = (record.get("reason") or "") + " | corrected target failed validation"
                    break
            if not replaced and record["decision"] != "uncertain":
                record["decision"] = "reject"
                record["reason"] = (record.get("reason") or "") + " | target_id not found"
        elif decision == "accept_fact" and isinstance(item.get("fact_correction"), dict):
            record["applied"] = _apply_fact_correction(case.setdefault("fund", {}), item["fact_correction"], doc)
            if not record["applied"]:
                record["decision"] = "uncertain"
                record["reason"] = (record.get("reason") or "") + " | fact correction lacks a mechanically applicable value; kept as uncertain"
        elif decision == "accept_status" and isinstance(item.get("status_correction"), dict):
            correction = item["status_correction"]
            found = False
            for cov in coverage:
                if cov.get("rule_id") == correction.get("rule_id") and cov.get("scope") == correction.get("scope"):
                    cov.update({
                        "status": tool._normalize_status(correction.get("status")),
                        "paragraph_index": correction.get("paragraph_index", cov.get("paragraph_index")),
                        "reason": correction.get("reason") or cov.get("reason"),
                    })
                    found = True
                    record["applied"] = True
                    break
            if not found:
                coverage.append({
                    "rule_id": correction.get("rule_id"),
                    "scope": correction.get("scope") or "main",
                    "status": tool._normalize_status(correction.get("status")),
                    "paragraph_index": correction.get("paragraph_index"),
                    "reason": correction.get("reason") or "review adjudication",
                    "evidence_quote": None,
                })
                record["applied"] = True
        elif decision == "uncertain":
            uncertain.append({
                "finding_id": fid,
                "type": finding["type"],
                "rule_id": (item.get("status_correction") or {}).get("rule_id")
                or (item.get("target") or {}).get("rule_id"),
                "scope": (item.get("status_correction") or {}).get("scope")
                or (item.get("target") or {}).get("scope"),
                "paragraph_index": (item.get("status_correction") or {}).get("paragraph_index")
                or (item.get("target") or {}).get("paragraph_index"),
                "issue": (finding.get("content") or {}).get("issue") if isinstance(finding.get("content"), dict) else str(finding.get("content"))[:200],
                "reason": item.get("reason"),
                "candidates": [(item.get("status_correction") or {}).get("status")]
                if item.get("status_correction") else [],
            })
        # reject: keep record only
        resolutions_out.append(record)
    # Findings the adjudicator did not return are explicitly uncertain, never dropped.
    for finding in findings:
        if finding["finding_id"] not in returned:
            content = finding.get("content") if isinstance(finding.get("content"), dict) else {}
            uncertain.append({
                "finding_id": finding["finding_id"],
                "type": finding["type"],
                "rule_id": content.get("rule_id"),
                "scope": content.get("scope"),
                "paragraph_index": content.get("paragraph_index"),
                "issue": content.get("issue") or str(finding.get("content"))[:200],
                "reason": "adjudication did not return a decision; moved to uncertain",
                "candidates": [],
            })
            resolutions_out.append({
                "finding_id": finding["finding_id"], "type": finding["type"],
                "decision": "uncertain", "reason": "not returned by adjudicator", "applied": False,
            })
    case["targets"] = targets
    case["rule_coverage"] = coverage
    case["uncertain"] = uncertain
    return case, resolutions_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--guide", default=str(ROOT / "references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx"))
    parser.add_argument("--rules", default=str(ROOT / "guides/builtin_guide_v1.json"))
    parser.add_argument("--provider-env", default="")
    parser.add_argument("--primary-model", default="gpt-6-luna")
    parser.add_argument("--primary-temperature", type=float, default=0.0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--usage-out", default="")
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()

    v1 = json.loads(Path(args.v1).read_text(encoding="utf-8"))
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    guide_paras, guide_sha = tool.load_guide(Path(args.guide))
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    rule_map = {g["rule_id"]: g for g in rules["groups"]}
    guide_text = tool.guide_prompt(rules, guide_paras)
    base_url, api_key, env_model = tool.load_provider_env(args.provider_env)
    client = tool.ModelClient(base_url, api_key)
    v1_cases = {c["case_id"]: c for c in v1["cases"]}
    wanted = {c.upper() for c in args.case} if args.case else None
    out_cases = []
    try:
        for case in selection["cases"]:
            cid = case["case_id"]
            if wanted and cid.upper() not in wanted:
                continue
            v1_case = json.loads(json.dumps(v1_cases[cid]))
            doc = tool.build_doc_model(ROOT / case["relative"])
            findings = build_findings(v1_case)
            if findings:
                try:
                    response, _ = client.chat_json(
                        model=args.primary_model,
                        system="你是基金合同独立标签的裁定人，只依据指引和合同原文，只输出 JSON。",
                        user=adjudication_prompt(doc, guide_text, v1_case, findings),
                        max_tokens=24000,
                        phase="v2_adjudicate",
                        case_id=cid,
                        retries=6,
                        temperature=args.primary_temperature,
                    )
                except RuntimeError as exc:
                    response = {"resolutions": []}
                    print(f"[v2] {cid} adjudication failed: {exc}", flush=True)
            else:
                response = {"resolutions": []}
            v1_case, resolutions = apply_resolutions(v1_case, findings, response, doc, rule_map)
            # Rebuild coverage target entries for any newly added target.
            for target in v1_case["targets"]:
                if not any(
                    c.get("rule_id") == target["rule_id"] and c.get("scope") == target["scope"]
                    for c in v1_case["rule_coverage"]
                ):
                    v1_case["rule_coverage"].append({
                        "rule_id": target["rule_id"], "scope": target["scope"], "status": "target",
                        "paragraph_index": target["paragraph_index"],
                        "reason": "target added by v2 review adjudication",
                        "evidence_quote": target.get("source_quote"),
                    })
                else:
                    for cov in v1_case["rule_coverage"]:
                        if cov.get("rule_id") == target["rule_id"] and cov.get("scope") == target["scope"]:
                            cov["status"] = "target"
            # Renumber targets.
            targets = v1_case["targets"]
            targets.sort(key=lambda t: (t["paragraph_index"], tool.RULE_IDS.index(t["rule_id"]), t["op"], t["compact_start"]))
            for idx, target in enumerate(targets, 1):
                target["target_id"] = f"T{idx:03d}"
            satisfied, not_applicable, unknown, _ = tool.derive_lists(v1_case["rule_coverage"], targets)
            v1_case["satisfied"] = satisfied
            v1_case["not_applicable"] = not_applicable
            v1_case["unknown"] = unknown
            v1_case["target_count"] = len(targets)
            v1_case["facts"] = scorer_facts(v1_case.get("fund") or {})
            v1_case["review_resolutions"] = resolutions
            v1_case["review_findings_total"] = len(findings)
            v1_case["review_findings_applied"] = sum(1 for r in resolutions if r.get("applied"))
            v1_case["review_findings_uncertain"] = sum(1 for r in resolutions if r.get("decision") == "uncertain")
            v1_case["review_findings_rejected"] = sum(1 for r in resolutions if r.get("decision") == "reject")
            out_cases.append(v1_case)
            print(f"[v2] {cid} findings={len(findings)} applied={v1_case['review_findings_applied']} "
                  f"uncertain={v1_case['review_findings_uncertain']} rejected={v1_case['review_findings_rejected']} "
                  f"targets={len(targets)}", flush=True)
    finally:
        client.close()
    usage = tool.usage_summary(client.usage)
    out = json.loads(json.dumps(v1))
    out["schema"] = "fundlex-independent-labels-v2"
    out["frozen_at"] = tool.now_iso()
    out["v1_labels_sha256"] = hashlib.sha256(Path(args.v1).read_bytes()).hexdigest()
    out["adjudication"] = {
        "model": args.primary_model,
        "engine_model_env": env_model,
        "prompt_version": "independent-label-review-adjudication-v1",
        "usage": usage,
        "independence": "adjudicator is outside the engine model family and read only guide/contracts/v1 labels",
    }
    if wanted:
        # partial run: merge into v1 cases
        out["cases"] = [v1_cases[c["case_id"]] if c["case_id"] not in {x["case_id"] for x in out_cases} else next(x for x in out_cases if x["case_id"] == c["case_id"]) for c in selection["cases"]]
    else:
        out["cases"] = out_cases
    out["review_summary"] = {
        "findings_total": sum(c.get("review_findings_total", 0) for c in out["cases"]),
        "applied": sum(c.get("review_findings_applied", 0) for c in out["cases"]),
        "uncertain": sum(c.get("review_findings_uncertain", 0) for c in out["cases"]),
        "rejected": sum(c.get("review_findings_rejected", 0) for c in out["cases"]),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    usage_path = Path(args.usage_out) if args.usage_out else Path(args.out).with_suffix(".usage.json")
    usage_path.write_text(json.dumps({"summary": usage, "events": client.usage}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[v2] wrote {args.out} sha256={hashlib.sha256(Path(args.out).read_bytes()).hexdigest()}", flush=True)
    print(f"[v2] review summary {json.dumps(out['review_summary'], ensure_ascii=False)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
