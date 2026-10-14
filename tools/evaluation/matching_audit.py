"""Score frozen matching labels against the actual downloaded DOCX, without calls.

Labels are independent AI reference annotations, not externally approved truth.
Unlabelled and uncertain edits are reported separately from confirmed mistakes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.evaluation.v2_compare import paragraph_map


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records(run: Path) -> dict[str, dict]:
    batches = sorted(run.glob("batch_*.json"))
    if batches:
        records = [item for path in batches for item in json.loads(path.read_text(encoding="utf-8"))]
    else:
        data = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        records = data.get("records", [])
    return {item["report"]["source_sha256"]: item for item in records}


def text_map(path: Path) -> dict[str, str]:
    entries = paragraph_map(path)
    return {entry["location"]: entry["text"] for entry in entries if entry["location"] is not None}


def overlaps(edit: dict, target: dict) -> bool:
    if edit["location"] != target["location"]:
        return False
    if edit["start"] == edit["end"]:
        return target["start"] <= edit["start"] <= target["end"]
    return edit["start"] < target["end"] and edit["end"] > target["start"]


def replay(source: dict[str, str], edits: list[dict]) -> dict[str, str]:
    """Replay coordinates from the unchanged source, rejecting invalid plans."""
    result = dict(source)
    groups: dict[str, list[dict]] = defaultdict(list)
    for edit in edits:
        groups[edit["location"]].append(edit)
    for location, group in groups.items():
        original = source[location]
        boundary = len(original) + 1
        text = original
        for edit in sorted(group, key=lambda item: (item["start"], item["end"]), reverse=True):
            start, end = edit["start"], edit["end"]
            if not 0 <= start <= end <= len(original) or end > boundary:
                raise ValueError("invalid or overlapping edit coordinates")
            if original[start:end] != edit.get("expected_old_text", ""):
                raise ValueError("edit source quote mismatch")
            text = text[:start] + str(edit["replacement"]) + text[end:]
            boundary = start
        result[location] = text
    return result


def evaluate(labels_path: Path, run: Path, rules_path: Path) -> dict:
    freeze = json.loads((labels_path.parent / "freeze.json").read_text(encoding="utf-8"))
    if digest(labels_path) != freeze.get("sha256", freeze.get("targets_sha256")):
        raise ValueError("reference labels changed after freezing")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    if labels.get("predictions_read") is not False:
        raise ValueError("labels must declare predictions_read=false")
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    by_id = {action["action_id"]: action for action in rules["actions"]}
    records = load_records(run)
    totals = Counter()
    by_action: dict[str, Counter] = defaultdict(Counter)
    cases = []
    for case in labels["cases"]:
        source_path = Path(case["source_path"])
        if digest(source_path) != case["source_sha256"]:
            raise ValueError("reference source changed")
        source = text_map(source_path)
        item = records.get(case["source_sha256"])
        out = {"case_id": case["case_id"], "targets": [], "unlabelled_edits": []}
        if not item:
            totals["missing_run_cases"] += 1
            cases.append(out)
            continue
        report = item["report"]
        out["qualification_status"] = report.get("qualification_status")
        if report.get("qualification_status") == "excluded_by_fund_type":
            totals["qualification_excluded_cases"] += 1
        edits = report.get("edit_plan", {}).get("edits", [])
        final_path = item.get("final_docx") or item.get("artifacts", {}).get("final")
        actual = text_map(Path(final_path)) if final_path else None
        expected = replay(source, edits)
        strict_ok = actual is not None and actual == expected
        # Whitespace (including line breaks inside a paragraph) is formatting, not
        # policy content; only non-whitespace differences count as artifact
        # mismatches. Strict differences are recorded separately.
        compact_ok = actual is not None and (
            {key: "".join(value.split()) for key, value in actual.items()}
            == {key: "".join(value.split()) for key, value in expected.items()})
        out["artifact_text_matches_plan"] = compact_ok
        out["artifact_text_matches_plan_strict"] = strict_ok
        if edits and not strict_ok:
            if compact_ok:
                totals["artifact_whitespace_differences"] += 1
            else:
                totals["artifact_mismatch_cases"] += 1
        artifact_ok = compact_ok
        matched = set()
        for action in case["actions"]:
            aid = action["action_id"]
            own = [(i, edit) for i, edit in enumerate(edits) if edit["action_id"] == aid]
            stats = by_action[aid]
            if action.get("status") == "not_applicable" and own:
                stats["confirmed_wrong_edits"] += len(own)
                matched.update(i for i, _ in own)
            for target in action.get("targets", []):
                if source[target["location"]][target["start"]:target["end"]] != target["quote"]:
                    raise ValueError("reference target quote does not match the source")
                hits = [(i, edit) for i, edit in own if overlaps(edit, target)]
                expectation = target["expectation"]
                outcome = "unscored"
                if expectation == "modify":
                    stats["expected_targets"] += 1
                    exact = [(i, edit) for i, edit in hits
                             if edit["start"] == target["start"] and edit["end"] == target["end"]]
                    if not hits:
                        outcome = "not_executed"
                    elif len(exact) != 1:
                        outcome = "wrong_range"
                    else:
                        i, edit = exact[0]
                        action_rule = by_id[aid]
                        mode = action_rule["generation"]["mode"]
                        replacement = str(edit["replacement"])
                        if mode == "delete":
                            correct = replacement == ""
                        elif mode == "template":
                            # Replay class slots independently from the stored verified profile.
                            template = action_rule["generation"]["template_text"]
                            groups = report.get("profile", {}).get("fee_groups", {})
                            for slot, group in action_rule["generation"].get("slots", {}).items():
                                names = groups.get(group, [])
                                if not names:
                                    template = ""
                                    break
                                template = template.replace(slot, "、".join(name + "类" for name in names) + "基金份额")
                            correct = bool(template) and "".join(replacement.split()) == "".join(template.split())
                        else:
                            correct = False  # Generated clauses require separately labelled semantics.
                        outcome = "edited_correct" if correct and artifact_ok else "wrong_content_or_artifact"
                    matched.update(i for i, _ in hits)
                    if outcome == "wrong_range":
                        # A narrower core may preserve legitimate neighbouring wording.
                        # Boundary disagreement needs semantic review, not a false assertion
                        # that it is already proven to be a business mistake.
                        stats["range_edits_needing_review"] += len(hits)
                    if outcome == "wrong_content_or_artifact":
                        stats["confirmed_wrong_edits"] += len(hits)
                    stats[outcome] += 1
                elif expectation == "already_satisfied":
                    outcome = "satisfied_violated" if hits else "satisfied_preserved"
                    stats[outcome] += 1
                    if hits:
                        stats["confirmed_wrong_edits"] += len(hits)
                    matched.update(i for i, _ in hits)
                else:
                    stats[expectation + "_targets"] += 1
                    if hits:
                        stats["uncertain_or_unsupported_edits"] += len(hits)
                        matched.update(i for i, _ in hits)
                out["targets"].append({"action_id": aid, "location": target["location"],
                                       "expectation": expectation, "outcome": outcome})
        for i, edit in enumerate(edits):
            if i not in matched:
                out["unlabelled_edits"].append({"action_id": edit["action_id"], "location": edit["location"],
                                               "start": edit["start"], "end": edit["end"]})
        totals["unlabelled_edits"] += len(out["unlabelled_edits"])
        cases.append(out)
    for stats in by_action.values():
        totals.update(stats)
    return {"schema": "matching-reference-comparison-1", "label_method": labels.get("kind"),
            "labels_sha256": digest(labels_path), "rules_sha256": digest(rules_path),
            "run": str(run.resolve()), "overall": dict(totals),
            "actions": {aid: dict(stats) for aid, stats in sorted(by_action.items())}, "cases": cases,
            "note": "Unlabelled/uncertain/range-disagreement edits are not counted as confirmed correct or wrong; they need independent semantic review. Qualification exclusions remain separately visible. AI labels are not external approval."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--rules", default="rules/rules_v2.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(Path(args.labels), Path(args.run), Path(args.rules))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["overall"], ensure_ascii=False))


if __name__ == "__main__":
    main()
