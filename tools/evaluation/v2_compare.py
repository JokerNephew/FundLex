"""Independent v2 scorer reading actual modified evaluation DOCX files.

Two modes:

- ``gold``: compare the 16-contract pilot run against the frozen independent
  AI blind review labels (never re-labelled to fit results).
- ``fixtures``: compare constructed semantic fixtures against expectations
  frozen before the real-model run.

The scorer never trusts report flags alone: paragraph text is recomputed from
the downloaded final DOCX and every executed edit is re-applied independently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda name: "{" + W + "}" + name

DELETE_ACTIONS = {"R03-A3", "R04-A1", "R11-A1"}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def paragraph_map(path: Path) -> list[dict]:
    """Paragraph text in document order, with runtime locations when available."""
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"),
                                parser=etree.XMLParser(resolve_entities=False, no_network=True))
    body = root.find(Q("body"))
    paragraphs = list(body.iter(Q("p")))
    direct = {id(p): f"p{i}" for i, p in enumerate(body.findall(Q("p")))}
    table_map = {}
    for ti, table in enumerate(body.findall(Q("tbl"))):
        for ri, row in enumerate(table.findall(Q("tr"))):
            for ci, cell in enumerate(row.findall(Q("tc"))):
                for pi, paragraph in enumerate(cell.findall(Q("p"))):
                    table_map[id(paragraph)] = f"tbl{ti}/r{ri}/c{ci}/p{pi}"
    result = []
    for paragraph in paragraphs:
        result.append({"text": "".join(t.text or "" for t in paragraph.iter(Q("t"))),
                       "location": direct.get(id(paragraph), table_map.get(id(paragraph)))})
    return result


def semantic_ok_redemption_ownership(replacement: str) -> bool:
    required = ["赎回费用由赎回基金份额的基金份额持有人承担", "在基金份额持有人赎回基金份额时收取", "全额计入基金财产"]
    forbidden = ["未归入基金财产", "登记费", "招募说明书", "比例"]
    conditions = ["超过一年", "少于", "不足", "持有期", "渠道", "直销"]
    return (all(value in replacement for value in required)
            and not any(value in replacement for value in forbidden)
            and not any(value in replacement for value in conditions)
            and not re.search(r"\d", replacement))


def load_run(run: Path) -> dict[str, dict]:
    records = {}
    for path in sorted(run.glob("batch_*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            records[item["report"]["source_sha256"]] = item
    return records


def final_map_of(item: dict) -> list[dict] | None:
    final = item.get("final_docx")
    if final and Path(final).is_file():
        return paragraph_map(Path(final))
    return None


def _entry(entries: list[dict], location: str) -> dict | None:
    return next((entry for entry in entries if entry["location"] == location), None)


def edited_segment(source_text: str, final_text: str, edit: dict) -> str | None:
    """Derive the actually written text from the final DOCX (length delta method)."""
    delta = len(final_text) - len(source_text)
    start, end = edit["start"], edit["end"]
    if edit.get("operation") == "insert":
        if start != end or delta < 0 or start + delta > len(final_text):
            return None
        return final_text[start:start + delta]
    new_length = (end - start) + delta
    if new_length < 0 or start + new_length > len(final_text):
        return None
    return final_text[start:start + new_length]


def gold_mode(root: Path, run: Path) -> dict:
    gold_path = root / "gold.json"
    raw = gold_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    frozen = json.loads((root / "gold.freeze.json").read_text(encoding="utf-8"))
    assert digest == frozen["sha256"], "gold label hash mismatch"
    gold = json.loads(raw)
    records = load_run(run)
    per_action = defaultdict(Counter)
    per_case = []
    qualification = Counter()
    for case in gold["cases"]:
        case_id = case["case_id"]
        source_path = root / "inputs" / f"{case_id}.docx"
        source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        item = records.get(source_hash)
        expected_qualification = case["qualification"]["status"]
        actual_qualification = (item or {}).get("report", {}).get("qualification_status")
        if expected_qualification in {"eligible", "excluded_by_fund_type"}:
            qualification["known"] += 1
            qualification["correct" if actual_qualification == expected_qualification else "wrong_or_abstained"] += 1
        qualification["actual_" + str(actual_qualification)] += 1
        case_out = {"case_id": case_id, "expected_qualification": expected_qualification,
                    "actual_qualification": actual_qualification,
                    "eligible": expected_qualification == "eligible",
                    "delivery_status": (item or {}).get("delivery_status"),
                    "actions": [], "artifact_text_match": None, "contract_correct": False}
        if item is None:
            case_out["missing_run"] = True
            per_case.append(case_out)
            continue
        report = item["report"]
        source = paragraph_map(source_path)
        final = final_map_of(item)
        edits = report.get("edit_plan", {}).get("edits", [])
        actions_by_id = {action["action_id"]: action for action in report.get("actions", [])}
        case_out["edits"] = len(edits)
        expected_texts = {entry["location"]: entry["text"] for entry in source if entry["location"]}
        if final is not None:
            by_location: dict[str, list[dict]] = defaultdict(list)
            for edit in edits:
                by_location[edit["location"]].append(edit)
            for location, items in by_location.items():
                if location not in expected_texts:
                    continue
                text = expected_texts[location]
                # Apply same-paragraph edits from the end so earlier offsets stay valid.
                for edit in sorted(items, key=lambda e: -e["start"]):
                    text = text[:edit["start"]] + str(edit["replacement"]) + text[edit["end"]:]
                expected_texts[location] = text
            mismatches = 0
            for entry in final:
                if entry["location"] and entry["location"] in expected_texts and entry["text"] != expected_texts[entry["location"]]:
                    mismatches += 1
            case_out["artifact_text_match"] = mismatches == 0
        for action in case["actions"]:
            aid = action["action_id"]
            engine_action = actions_by_id.get(aid, {})
            action_edits = [edit for edit in edits if edit.get("action_id") == aid]
            stats = per_action[aid]
            stats["reviewed_cases"] += 1
            stats["executed_edits"] += len(action_edits)
            stats["engine_status_" + str(engine_action.get("status", "absent"))] += 1
            if not action.get("targets"):
                if action_edits:
                    stats["edits_outside_reviewed_scope"] += len(action_edits)
                    case_out.setdefault("edits_outside_reviewed_scope", 0)
                    case_out["edits_outside_reviewed_scope"] += len(action_edits)
                continue
            item_out = {"action_id": aid, "gold_status": action["status"], "engine_status": engine_action.get("status"),
                        "engine_failure_reason": engine_action.get("failure_reason"),
                        "targets": [], "negative_violations": 0, "extra_edits": 0,
                        "satisfied_ok": 0, "satisfied_violated": 0}
            matched_edits: set[int] = set()
            for target in action.get("targets", []):
                label = target.get("label")
                paragraph_index = target.get("paragraph_index")
                entry = source[paragraph_index] if paragraph_index is not None and paragraph_index < len(source) else None
                if label == "target":
                    if entry is None or entry["location"] is None or target.get("edit_supported") is False:
                        stats["unsupported_or_unmapped_targets"] += 1
                        continue
                    stats["expected_targets"] += 1
                    runtime, src_text = entry["location"], entry["text"]
                    exact = [e for e in action_edits if e["location"] == runtime
                             and e["start"] == target["start"] and e["end"] == target["end"]]
                    whitespace = [e for e in action_edits if e["location"] == runtime
                                  and e["start"] == target["start"]
                                  and src_text[e["start"]:e["end"]].strip() == target["quote"].strip()]
                    overlapping = [e for e in action_edits if e["location"] == runtime
                                   and e["start"] < target["end"] and e["end"] > target["start"]]
                    outcome, detail = "not_executed", {}
                    if exact:
                        edit = exact[0]
                        matched_edits.add(id(edit))
                        final_entry = _entry(final or [], runtime)
                        final_text = final_entry["text"] if final_entry else None
                        expected_after = expected_texts.get(runtime)
                        if aid in DELETE_ACTIONS:
                            correct_content = final_text == expected_after and str(edit["replacement"]) == ""
                        elif aid == "R10-A1":
                            correct_content = (final_text == expected_after
                                               and semantic_ok_redemption_ownership(str(edit["replacement"])))
                        else:
                            correct_content = final_text == expected_after
                        passed = (edit.get("verification") or {}).get("passed") is True
                        if final_text is None:
                            outcome = "artifact_missing"
                        elif not correct_content:
                            outcome = "edited_wrong_content"
                        elif not passed:
                            outcome = "edited_unverified_record"
                        else:
                            outcome = "edited_correct"
                        detail = {"start": edit["start"], "end": edit["end"], "passed": passed,
                                  "replacement": str(edit["replacement"])[:120]}
                    elif whitespace:
                        matched_edits.add(id(whitespace[0]))
                        outcome = "edited_boundary_whitespace"
                        detail = {"start": whitespace[0]["start"], "end": whitespace[0]["end"]}
                    elif overlapping:
                        matched_edits.add(id(overlapping[0]))
                        outcome = "edited_range_mismatch"
                        detail = {"start": overlapping[0]["start"], "end": overlapping[0]["end"]}
                    stats[outcome] += 1
                    item_out["targets"].append({"paragraph_index": paragraph_index, "outcome": outcome,
                                                "range": [target["start"], target["end"]], **detail})
                elif label == "negative":
                    if entry is None or entry["location"] is None:
                        continue
                    runtime = entry["location"]
                    # Only this action's own edit in the negative region is a
                    # violation; other actions' unrelated edits are scored there.
                    overlapping = [e for e in action_edits if e["location"] == runtime
                                   and e["start"] < target["end"] and e["end"] > target["start"]]
                    if overlapping:
                        stats["negative_violations"] += 1
                        item_out["negative_violations"] += 1
                elif label == "satisfied":
                    if entry is None or entry["location"] is None:
                        continue
                    runtime = entry["location"]
                    edited = [e for e in action_edits if e["location"] == runtime
                              and e["start"] < target["end"] and e["end"] > target["start"]]
                    if edited:
                        stats["satisfied_violated"] += 1
                        item_out["satisfied_violated"] += 1
                    else:
                        stats["satisfied_ok"] += 1
                        item_out["satisfied_ok"] += 1
            extra = [edit for edit in action_edits if id(edit) not in matched_edits]
            stats["extra_edits"] += len(extra)
            item_out["extra_edits"] = len(extra)
            case_out["actions"].append(item_out)
        writable_targets = sum(stats["expected_targets"] for aid, stats in per_action.items()
                               if any(a["action_id"] == aid for a in case["actions"]))
        if expected_qualification == "eligible":
            all_targets_ok = all(item["outcome"] in {"edited_correct", "edited_boundary_whitespace"}
                                 for action in case_out["actions"] for item in action["targets"])
            no_violations = all(action["negative_violations"] == 0 and action["satisfied_violated"] == 0
                                and action["extra_edits"] == 0 for action in case_out["actions"])
            case_out["contract_correct"] = bool(case_out.get("artifact_text_match") and all_targets_ok and no_violations)
        per_case.append(case_out)
    action_summary = {}
    for aid, stats in per_action.items():
        executed = (stats.get("edited_correct", 0) + stats.get("edited_wrong_content", 0)
                    + stats.get("edited_unverified_record", 0) + stats.get("edited_boundary_whitespace", 0)
                    + stats.get("edited_range_mismatch", 0))
        action_summary[aid] = {
            **dict(stats),
            "edit_precision": ratio(stats.get("edited_correct", 0), executed),
            "target_completion": ratio(stats.get("edited_correct", 0), stats.get("expected_targets", 0)),
            "target_completion_with_whitespace": ratio(
                stats.get("edited_correct", 0) + stats.get("edited_boundary_whitespace", 0),
                stats.get("expected_targets", 0)),
        }
    expected_total = sum(stats.get("expected_targets", 0) for stats in per_action.values())
    correct_total = sum(stats.get("edited_correct", 0) for stats in per_action.values())
    eligible_cases = [case for case in per_case if case["eligible"]]
    summary = {
        "schema": "v2-gold-comparison-1",
        "gold_sha256": digest,
        "run": str(run),
        "scope": len(gold["cases"]),
        "label_method": "independent AI blind review; not externally approved business truth",
        "qualification": {**qualification, "agreement": ratio(qualification["correct"], qualification["known"])},
        "actions": action_summary,
        "overall": {
            "expected_targets": expected_total,
            "edited_correct": correct_total,
            "edit_precision": ratio(correct_total, sum(stats.get("executed_edits", 0) for stats in per_action.values())),
            "target_completion": ratio(correct_total, expected_total),
            "target_completion_with_whitespace": ratio(
                correct_total + sum(stats.get("edited_boundary_whitespace", 0) for stats in per_action.values()),
                expected_total),
            "negative_violations": sum(stats.get("negative_violations", 0) for stats in per_action.values()),
            "extra_edits": sum(stats.get("extra_edits", 0) for stats in per_action.values()),
            "edits_outside_reviewed_scope": sum(stats.get("edits_outside_reviewed_scope", 0)
                                                for stats in per_action.values()),
            "satisfied_ok": sum(stats.get("satisfied_ok", 0) for stats in per_action.values()),
            "satisfied_violated": sum(stats.get("satisfied_violated", 0) for stats in per_action.values()),
            "eligible_contracts": len(eligible_cases),
            "contracts_fully_correct": sum(1 for case in eligible_cases if case["contract_correct"]),
            "auto_completion_rate": ratio(sum(1 for case in eligible_cases if case["contract_correct"]),
                                          len(eligible_cases)),
        },
        "cases": per_case,
        "limitations": [
            "frozen 16-case diagnostic cohort; not population accuracy",
            "only annotated actions scored; edits outside annotated actions are reported separately",
            "no-target-found is not satisfied; unknown is not a true negative",
            "strict range scoring; whitespace-only boundary differences reported separately",
            "AI blind labels are not external business approval",
        ],
    }
    return summary


def fixture_segments(root: Path, fixture: dict, item: dict, action_id: str) -> list[str]:
    final = final_map_of(item)
    if final is None:
        return []
    source = paragraph_map(root / fixture["file"])
    segments = []
    for edit in item["report"].get("edit_plan", {}).get("edits", []):
        if edit.get("action_id") != action_id:
            continue
        source_entry = _entry(source, edit["location"])
        final_entry = _entry(final, edit["location"])
        if source_entry is None or final_entry is None:
            continue
        segment = edited_segment(source_entry["text"], final_entry["text"], edit)
        if segment is not None:
            segments.append(segment)
    return segments


def fixture_mode(root: Path, run: Path) -> dict:
    expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
    records = load_run(run)
    results = []
    for fixture in expected["fixtures"]:
        source_path = root / fixture["file"]
        source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        assert source_hash == fixture["sha256"], f"fixture {fixture['fixture_id']} changed after freeze"
        item = records.get(source_hash)
        out = {"fixture_id": fixture["fixture_id"], "purpose": fixture["purpose"],
               "delivery_status": (item or {}).get("delivery_status"), "actions": {}, "checks": [], "passed": True}
        if item is None:
            out["passed"] = False
            out["checks"].append({"check": "run_present", "ok": False})
            results.append(out)
            continue
        report = item["report"]
        actions = {action["action_id"]: action for action in report.get("actions", [])}
        for aid, expectation in fixture["actions"].items():
            action = actions.get(aid, {})
            actual_status = action.get("status")
            actual_reason = action.get("failure_reason")
            reasons = [target.get("reason") for target in action.get("targets", []) if target.get("reason")]
            status_ok = actual_status == expectation["status"]
            reason_ok = True
            if expectation.get("allowed_reasons"):
                reason_ok = actual_reason in expectation["allowed_reasons"] or any(
                    reason in expectation["allowed_reasons"] for reason in reasons)
            edits = [edit for edit in report.get("edit_plan", {}).get("edits", [])
                     if edit.get("action_id") == aid]
            edits_ok = len(edits) == expectation["edits"]
            out["actions"][aid] = {"expected_status": expectation["status"], "actual_status": actual_status,
                                   "actual_reason": actual_reason, "target_reasons": reasons,
                                   "expected_edits": expectation["edits"], "actual_edits": len(edits),
                                   "status_ok": status_ok, "reason_ok": reason_ok, "edits_ok": edits_ok}
            if not (status_ok and reason_ok and edits_ok):
                out["passed"] = False
            segments = fixture_segments(root, fixture, item, aid)
            for check in expectation.get("generated_checks", []):
                ok = fixture_check(check, segments)
                out["checks"].append({"action_id": aid, "kind": check["kind"], "ok": ok,
                                      "segments": [segment[:200] for segment in segments]})
                if not ok:
                    out["passed"] = False
            if expectation.get("body_summary_identical"):
                ok = len(edits) >= 2 and len(set(segments)) == 1
                out["checks"].append({"action_id": aid, "check": "body_summary_identical", "ok": ok})
                if not ok:
                    out["passed"] = False
        if fixture.get("delivery") and item["delivery_status"] != fixture["delivery"]:
            out["checks"].append({"check": "delivery_status", "expected": fixture["delivery"],
                                  "actual": item["delivery_status"], "ok": False})
            out["passed"] = False
        results.append(out)
    return {"schema": "v2-fixture-comparison-1", "fixture_count": len(results),
            "passed": sum(1 for item in results if item["passed"]), "fixtures": results}


def fixture_check(check: dict, segments: list[str]) -> bool:
    def compact(value: str) -> str:
        return re.sub(r"\s+", "", value)
    if check["kind"] == "contains_all":
        return bool(segments) and all(all(compact(value) in compact(segment) for value in check["values"])
                                      for segment in segments)
    if check["kind"] == "not_contains":
        return bool(segments) and all(not any(compact(value) in compact(segment) for value in check["values"])
                                      for segment in segments)
    if check["kind"] == "no_digits":
        return bool(segments) and all(not re.search(r"\d", segment) for segment in segments)
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["gold", "fixtures"], required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--name")
    args = parser.parse_args()
    root, run = Path(args.root).resolve(), Path(args.run).resolve()
    summary = gold_mode(root, run) if args.mode == "gold" else fixture_mode(root, run)
    name = args.name or ("v2_comparison.json" if args.mode == "gold" else "v2_fixture_comparison.json")
    target = run / name
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"cases", "fixtures"}},
                     ensure_ascii=False)[:4000])
    print("written", target)


if __name__ == "__main__":
    main()
