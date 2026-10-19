"""Offline shadow replay for the V1/V2 validators (plan v4 §23-A).

Runs the validators over existing batch artifacts — no model calls — and writes
per-edit findings plus run-level statistics. This is the Phase-2 observation
step: the validators must flag the FL-D119 mis-target (round14-08 / D01 / p227)
while ordinary edits pass.

Method: for every edit in ``edit_plan.edits`` take the source paragraph
(``funds_word/<file>``, index from the ``p<n>`` location) and the artifact
paragraph (``working_final``) at the same index, derive an authorization from
the guide rule's operations (``old_text`` → removal patterns, ``new_text`` →
must-add phrases) and validate. Paragraph alignment is positional and therefore
crude when a run adds/removes paragraphs; findings carry the raw texts so a
human can confirm.

Usage:
  .venv/bin/python -X utf8 -m tools.evaluation.validator_shadow \
      var/recall-first-evaluation/p6-dev-round14-08 --case D01 \
      [--sources /home/opencode/data/funds_word] [--output /tmp/shadow.json]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from docx import Document

from fundlex import recall as R
from fundlex.generation.validators import Authorization, run_validation

_REPO = Path(__file__).resolve().parents[2]
_GUIDE_PATH = _REPO / "guides" / "builtin_guide_v1.json"
_EQUIVALENCES = (("每日计算", "每日计提"), ("逐日累计", "每日计提"),
                 ("按日计提", "每日计提"))


def _load_guide() -> dict[str, dict]:
    guide = json.loads(_GUIDE_PATH.read_text(encoding="utf-8"))
    return {group["rule_id"]: group for group in guide.get("groups") or []}


def _paragraph_texts(path: Path) -> list[str]:
    return [paragraph.text for paragraph in Document(str(path)).paragraphs]


def _authorization(rule_ids: list[str], guide: dict[str, dict],
                   edit: dict | None = None) -> Authorization:
    must_add: list[str] = []
    remove_patterns: list[str] = []
    removals_authorized = False
    for rule_id in rule_ids:
        rule = guide.get(rule_id)
        if not rule:
            continue
        carried = [op for op in (rule.get("operations") or []) if op.get("op") != "noop"]
        if carried and all(op.get("op") == "delete" for op in carried):
            # Delete-only rules (G06/G13/G15/G17): locating is the hard part,
            # deleting is the authorized action itself (plan §7.3).
            removals_authorized = True
        for operation in rule.get("operations") or []:
            if operation.get("op") in {"replace", "append"}:
                for part in re.split(r"(?<=[。；])", str(operation.get("new_text") or "")):
                    part = part.strip()
                    if len(R._compact(part)) >= 6:
                        must_add.append(part)
            if operation.get("op") in {"replace", "delete"}:
                old_text = str(operation.get("old_text") or "").strip()
                if old_text:
                    remove_patterns.append(old_text)
        for variant in rule.get("old_text_variants") or []:
            remove_patterns.append(str(variant))

    allow_whole_span_delete = False
    if edit:
        content_source = str(edit.get("content_source") or "")
        evidence = edit.get("evidence") or {}
        deletion_edit = "delete" in content_source
        if deletion_edit:
            removals_authorized = True
            # Delete-type edits authorize removing what they bound; the rule itself
            # is a deletion, so the engine's own evidence is the authorization.
            for key in ("matched_old_text", "deleted_quote", "deleted_paragraph",
                        "deleted_fragment"):
                value = str(evidence.get(key) or "")
                if value:
                    remove_patterns.append(value)
            for fragment in evidence.get("fragments") or []:
                value = str(fragment.get("old_text") or "")
                if value:
                    remove_patterns.append(value)
            allow_whole_span_delete = not str(edit.get("replacement") or "")
        fixed = str(evidence.get("fixed_text") or "")
        if fixed:
            must_add.append(fixed)

    return Authorization(must_add=tuple(must_add), remove_patterns=tuple(remove_patterns),
                         equivalences=_EQUIVALENCES,
                         allow_whole_span_delete=allow_whole_span_delete,
                         removals_authorized=removals_authorized)


def _edit_rule_ids(edit: dict) -> list[str]:
    """All rule ids an edit carries — merged edits list their components separately."""
    rule_ids = [part.strip() for part in str(edit.get("rule_id") or "").split("+")]
    for component in edit.get("components") or []:
        if isinstance(component, dict):
            rule_ids.extend(part.strip()
                            for part in str(component.get("rule_id") or "").split("+"))
    return sorted({rule_id for rule_id in rule_ids if rule_id})


def _case_report(case_dir: Path, source_dir: Path, guide: dict[str, dict]) -> dict | None:
    report_path = case_dir / "report.json"
    artifact_path = case_dir / "working_final"
    result_path = case_dir / "result.json"
    if not (report_path.exists() and artifact_path.exists()):
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    file_name = str(result.get("file") or "")
    source_path = source_dir / file_name
    if not source_path.exists():
        return {"case": case_dir.name, "file": file_name, "skipped": "source_missing"}

    before_paragraphs = _paragraph_texts(source_path)
    after_paragraphs = _paragraph_texts(artifact_path)
    findings: list[dict] = []
    verdicts = Counter()

    # Several edits may touch one paragraph (e.g. a G05 fragment replace plus a G03
    # append). Offline we cannot reconstruct the intermediate state, so validate the
    # paragraph once with the union of all its edits' authorizations.
    edits_by_location: dict[str, list[dict]] = {}
    for edit in (report.get("edit_plan") or {}).get("edits") or []:
        location = str(edit.get("location") or "")
        edits_by_location.setdefault(location, []).append(edit)

    for location, edits in edits_by_location.items():
        match = re.fullmatch(r"p(\d+)", location)
        if not match:
            continue
        index = int(match.group(1))
        if index >= len(before_paragraphs) or index >= len(after_paragraphs):
            continue
        before, after = before_paragraphs[index], after_paragraphs[index]
        if before == after:
            continue

        rule_ids: list[str] = []
        components: list[dict] = []
        sources: list[str] = []
        evidence_merged: dict = {}
        all_empty = True
        for edit in edits:
            rule_ids.extend(_edit_rule_ids(edit))
            components.extend(component for component in (edit.get("components") or [])
                              if isinstance(component, dict))
            sources.append(str(edit.get("content_source") or ""))
            if str(edit.get("replacement") or ""):
                all_empty = False
            evidence = edit.get("evidence") or {}
            for key in ("matched_old_text", "deleted_quote", "deleted_paragraph",
                        "deleted_fragment", "fixed_text"):
                value = str(evidence.get(key) or "")
                if value:
                    evidence_merged[key] = (evidence_merged.get(key, "") + " || " + value).strip(" |")
            fragments = evidence.get("fragments")
            if fragments:
                evidence_merged.setdefault("fragments", []).extend(fragments)

        merged_edit = {
            "rule_id": "+".join(sorted(set(rule_ids))),
            "components": [{"rule_id": component.get("rule_id")} for component in components],
            "content_source": " ".join(sources),
            "replacement": "" if all_empty else "x",
            "evidence": evidence_merged,
        }
        auth = _authorization(_edit_rule_ids(merged_edit), guide, merged_edit)
        validation = run_validation(before, after, auth=auth)
        verdicts[validation.verdict] += 1
        if validation.verdict == "FAIL" or validation.soft_changes:
            findings.append({
                "rule_id": merged_edit["rule_id"],
                "location": location,
                "verdict": validation.verdict,
                "findings": [{"code": finding.code, "detail": finding.detail}
                             for finding in validation.findings],
                "hard": [{"before": record.before, "after": record.after,
                          "reason": record.reason}
                         for record in validation.changes
                         if record.explanation == "UNEXPLAINED_HARD"],
                "soft_count": len(validation.soft_changes),
                "before": R._clip(before, 160),
                "after": R._clip(after, 160),
            })
    return {"case": case_dir.name, "file": file_name, "edits_checked": sum(verdicts.values()),
            "verdicts": dict(verdicts), "failures": findings}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--sources", type=Path,
                        default=Path("/home/opencode/data/funds_word"))
    parser.add_argument("--case", action="append", default=None,
                        help="only these case dirs (e.g. D01); default: all")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.run.is_dir():
        print(f"not a directory: {args.run}", file=sys.stderr)
        return 2
    guide = _load_guide()
    wanted = set(args.case or [])
    reports: list[dict] = []
    for case_dir in sorted(path for path in args.run.iterdir() if path.is_dir()):
        if wanted and case_dir.name not in wanted:
            continue
        case_report = _case_report(case_dir, args.sources, guide)
        if case_report is not None:
            reports.append(case_report)

    total_checked = sum(item.get("edits_checked", 0) for item in reports)
    total_fail = sum(item.get("verdicts", {}).get("FAIL", 0) for item in reports)
    total_soft = sum(sum(1 for f in item.get("failures", [])) for item in reports)
    print(f"cases: {len(reports)}  edits_checked: {total_checked}  "
          f"FAIL: {total_fail}  flagged(soft or fail): {total_soft}")
    for item in reports:
        if item.get("skipped"):
            print(f"  {item['case']}: skipped ({item['skipped']})")
            continue
        verdicts = item.get("verdicts") or {}
        print(f"  {item['case']}: edits={item.get('edits_checked', 0)} "
              f"verdicts={verdicts} failures={len(item.get('failures') or [])}")
    if args.output:
        args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=1),
                               encoding="utf-8")
        print(f"written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
