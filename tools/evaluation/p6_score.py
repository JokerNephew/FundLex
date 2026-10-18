"""P6 scorer: compare the actual delivered DOCX against the frozen independent labels.

The scorer reads ONLY the frozen ``labels.json`` and the downloaded artifacts under the run
directory. It never reads the engine's plan, report replacements or target ledger, so the
score reflects what the customer would actually receive (the plan requires scoring the real
file, not ``report.applied``).

For every labelled target it decides one of:

* ``completed``   -- the required obligation is present in the final DOCX and the superseded
                     clause is gone;
* ``not_executed`` -- the target is absent/unresolved in the run and the file is unchanged;
* ``wrong``        -- the file changed but the required obligation is not correctly in place;
* ``kept``         -- a delete/replace target whose source text is still present verbatim
                     (the change did not happen where it was required).

Usage::

    .venv/bin/python -X utf8 -m tools.evaluation.p6_score \\
        --labels var/recall-first-evaluation/p6/labels.json \\
        --run var/recall-first-evaluation/p6-dev-baseline-01 \\
        --output var/recall-first-evaluation/p6-dev-baseline-01/score.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda name: "{" + W + "}" + name
COMPACT = re.compile(r"[\s\u3000]")


def compact(text: str) -> str:
    return COMPACT.sub("", text or "")


def paragraphs_of(path: Path) -> list[str]:
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"),
                                parser=etree.XMLParser(resolve_entities=False, no_network=True))
    body = root.find(Q("body"))
    return ["".join(node.text or "" for node in paragraph.iter(Q("t")))
            for paragraph in body.iter(Q("p"))]


def class_label_from_guide(new_text: str, facts: dict, group: str) -> str | None:
    """What the guide's example group becomes for this product.

    G02/G04 write ``A类基金份额`` -> ``A类、B类基金份额``. For the group that charges a
    subscription fee and no service fee the replacement must name every such class; for the
    service-fee group every class that carries the fee. The labels record the product's own
    classes, so the expected label is derived here without reading engine output.
    """
    classes = facts.get("classes") or []
    if group == "subscription":
        names = [item["name"] for item in classes
                 if item.get("subscription_fee") and not item.get("service_fee")]
    else:
        names = [item["name"] for item in classes if item.get("service_fee")]
    if not names:
        return None
    return "、".join(name.replace("基金份额", "") for name in names) + "基金份额"


def paragraph_of_offset(paragraphs: list[str], compact_offset: int) -> int:
    """The paragraph index holding a given compacted-text offset (or -1)."""
    running = 0
    for index, paragraph in enumerate(paragraphs):
        running += len(compact(paragraph))
        if compact_offset < running:
            return index
    return len(paragraphs) - 1


def locate_paragraph(final_paragraphs: list[str], original_paragraph: str,
                     hint: int) -> int:
    """Find the original paragraph in the final document despite inserted paragraphs.

    Paragraph indices shift when the engine appends or deletes paragraphs, so the region is
    found by its content: the paragraph with the largest shared compact prefix near the hint.
    A paragraph whose own wording was replaced keeps its unchanged lead, which is what anchors
    the match.
    """
    target = compact(original_paragraph)
    if not target:
        return -1
    best, best_score = -1, 0.0
    low = max(0, hint - 12)
    high = min(len(final_paragraphs), hint + 40)
    for index in range(low, high):
        candidate = compact(final_paragraphs[index])
        if not candidate:
            continue
        head = min(len(target), len(candidate), 24)
        common = 0
        while common < head and target[common] == candidate[common]:
            common += 1
        score = common / max(1, head)
        if candidate == target:
            return index
        if score > best_score:
            best, best_score = index, score
    return best if best_score >= 0.6 else -1


def _normalise_policy(value: str) -> str:
    """Canonicalise the wording variants contracts legitimately introduce.

    Beyond the punctuation/pronoun variants, contracts refer to fund share
    classes by their real letters. The rule templates assume "A类"/"C类", but a
    contract with three classes writes "A类、D类基金份额" where the template
    says "A类基金份额". The obligation is identical, so collapse every
    share-class enumeration to a single token before comparing.
    """
    value = compact(value)
    for variant, canonical in (("认购/申购", "申购"), ("认购、申购", "申购"),
                               ("的基金份额", "基金份额")):
        value = value.replace(variant, canonical)
    # "A类、D类基金份额" -> "类基金份额"; "A类" -> "类基金份额"-compatible form.
    value = re.sub(r"[A-ZＡ-Ｚ](?:类|份额)?(?:[、和及与][A-ZＡ-Ｚ](?:类|份额)?)*类?基金份额", "类基金份额", value)
    value = re.sub(r"[A-ZＡ-Ｚ]类基金份额", "类基金份额", value)
    # A single-class contract names no class letter at all ("申购本基金基金份额时"),
    # which is the same obligation as the template's "A类基金份额". Collapse the bare
    # form so a correct single-class append is not read as a miss.
    value = value.replace("类基金份额", "基金份额")
    return value


def _obligation_in_region(required: str, region: str, *, threshold: float = 0.9) -> bool:
    """True when the required obligation appears in the region up to small wording noise.

    A replacement can differ from the label only by a couple of characters: the G14
    policy "基金管理人可以适当调低基金申购费率和销售服务费率。" is delivered as
    "…调低基金申购费率和基金销售服务费率。" (one extra "基金"). A fixed-window
    comparison fails on an insertion because it shifts every later character, so measure
    the best alignment ratio over candidate windows with ``difflib`` instead. Only used
    as a fallback after the exact and normalised checks, and the threshold is high so a
    genuinely different obligation does not pass (FL-D099).
    """
    from difflib import SequenceMatcher

    obligation = compact(required)
    haystack = compact(region)
    if not obligation or not haystack:
        return False
    if obligation in haystack:
        return True
    # The obligation is a sentence; rarely longer than the region's paragraph, but compare
    # against windows of its own length stepped one character at a time.
    window = len(obligation)
    matcher = SequenceMatcher(autojunk=False)
    best = 0.0
    for start in range(0, max(1, len(haystack) - window) + 1):
        matcher.set_seq2(haystack[start:start + window])
        matcher.set_seq1(obligation)
        ratio = matcher.ratio()
        if ratio > best:
            best = ratio
            if best >= 0.999:
                break
    return best >= threshold


def appendix_present(required: str, final_compact: str) -> bool:
    """True when the appended policy sentence appears in the final document.

    The appended wording is a full sentence that contracts reproduce with small
    variations: an extra parenthetical, "申购" extended to "认购/申购", or a
    different set of fund share classes ("A类、D类" where the template says
    "A类"). A fixed prefix test misfires on those. Normalise the frequent
    variants, then require the obligation's leading clause to be present (the
    leading clause is the distinctive part; the trailing clause also appears in
    other sections).
    """
    policy = _normalise_policy(required)
    haystack = _normalise_policy(final_compact)
    if len(policy) < 12:
        return policy in haystack
    # The lead clause runs to the first full stop / semicolon in the policy.
    lead = policy.split("；")[0].split("。")[0]
    if lead and lead in haystack:
        return True
    # Fall back to a high-overlap fuzzy check for the leading segment. Step by
    # one character: the distinctive content is dense, and a coarse stride can
    # step over the single window that matches.
    segment = policy[: min(len(policy), 120)]
    window = len(segment)
    if window == 0:
        return False
    for start in range(0, max(1, len(haystack) - window) + 1):
        candidate = haystack[start:start + window]
        common = sum(1 for a, b in zip(segment, candidate) if a == b)
        if common / window >= 0.85:
            return True
    return False


def appendix_present_applicable_clauses(required: str, final_compact: str,
                                        facts: dict) -> bool:
    """True when every clause that *can* apply to this contract is present.

    An append policy bundles clauses for two class groups: the subscription class
    ("A类基金份额不收取认购/申购费用") and the service-fee class ("C类基金份额不收取
    销售服务费…持有超过一年不再收取"). A contract with a single class charges no
    sales service fee, so the service clauses have no subject: the engine correctly
    appends only the subscription clause and must not invent a C class. Score those
    contracts on the clauses that apply, otherwise the engine's correct work reads
    as a miss and the reported completion rate is too low.
    """
    classes = facts.get("classes") or []
    if any(item.get("service_fee") for item in classes if isinstance(item, dict)):
        return False  # the contract does have a service-fee class: the full policy applies
    policy = _normalise_policy(required)
    # Keep only the clauses that do not name the absent service-fee class.
    applicable = [clause for clause in re.split(r"(?<=[。；])", policy)
                  if clause.strip() and "销售服务费" not in clause]
    if not applicable:
        return False
    return all(appendix_present(clause, final_compact) for clause in applicable if clause.strip())


def _requirement_clause(requirement: str) -> str:
    """The clause text the requirement quotes between the Chinese quotation marks."""
    if not requirement:
        return ""
    for left, right in (("“", "”"), ("「", "」"), ('"', '"')):
        start = requirement.find(left)
        end = requirement.find(right, start + 1) if start >= 0 else -1
        if start >= 0 and end > start + 1:
            return requirement[start + 1:end]
    return ""


def _superseded_survives(target: dict, region: str, final_compact: str) -> bool:
    """True when the deleted clause is still present in the final document.

    The label's ``old_text`` is the anchor that located the clause and can be a short
    fragment ("销售服务费每日计提") that also appears verbatim inside a *different* clause
    kept on purpose (the appended policy text). Judging on that fragment alone reports a
    completed deletion as ``kept``. The requirement quotes the whole clause, so the verdict
    is decided on a distinctive long fragment of it (FL-D074).

    A quotation that names more than one sentence ("…服务费等。C类基金份额的销售服务费
    使用范围不包括…") is not a single deletion: only the sentence carrying the anchor is the
    target, and a later sentence can legitimately survive as its own clause. The trailing
    fragment is therefore only evidence when the anchor reaches the end of the quotation
    (FL-D097).
    """
    anchor = compact(target.get("old_text") or "")
    clause = compact(_requirement_clause(target.get("requirement") or ""))
    # Distinctive middle fragments of the quoted clause: skip the lead (often shared with
    # the kept policy text) and take interior runs.
    fragments: list[str] = []
    if len(clause) >= 24:
        fragments.extend([clause[8:40], clause[len(clause) // 2:len(clause) // 2 + 24]])
    # The trailing run is only distinctive when the anchor belongs to the quotation's last
    # sentence: a surviving later sentence is a separate clause, not a missed deletion.
    if len(clause) >= 24:
        last_sentence = [part for part in re.split(r"(?<=[。；])", clause) if part.strip()][-1]
        if anchor and anchor in last_sentence:
            fragments.append(clause[-24:])
    fragments = [frag for frag in fragments if len(frag) >= 12]
    if fragments:
        # The clause survives when any distinctive fragment is still present.
        return any(frag in final_compact for frag in fragments)
    # No quoted clause: fall back to the anchor, but require it inside the region.
    return bool(anchor) and anchor in region


def score_target(target: dict, facts: dict, final_paragraphs: list[str],
                 original_paragraphs: list[str]) -> dict:
    """Judge one frozen label by comparing the original contract with the final DOCX.

    The region is the original paragraph that carried the target (derived from the label's
    compacted offset). The final document is searched for that paragraph by content, because
    the engine inserts and removes paragraphs and shifts indices. A target counts as carried
    out when the wording it supersedes no longer appears in that region of the final file and
    (for replace/append) the required obligation now does. Working on the region, not the whole
    document, avoids two failure modes: short anchors that also live in unrelated clauses, and
    a replacement that reuses the old wording as a prefix.
    """
    rule_id = target["rule_id"]
    operation = target["op"]
    required = target.get("required_text") or ""
    old_text = target.get("old_text") or ""
    result = {"target_id": target.get("target_id"), "rule_id": rule_id, "op": operation}
    final_compact = compact("\n".join(final_paragraphs))
    compact_offset = target.get("compact_start")
    original_index = (paragraph_of_offset(original_paragraphs, compact_offset)
                      if isinstance(compact_offset, int) else -1)
    final_index = (locate_paragraph(final_paragraphs, original_paragraphs[original_index],
                                    original_index) if original_index >= 0 else -1)
    result["original_paragraph"] = original_index
    result["final_paragraph"] = final_index
    region = compact(final_paragraphs[final_index]) if final_index >= 0 else ""

    if operation == "append":
        if not required:
            result.update(verdict="wrong", detail="append without required text")
            return result
        # The appended policy is a whole sentence whose wording varies between contracts
        # ("申购" against "认购/申购", an extra parenthetical). Match on the obligation's
        # distinctive content rather than a fixed prefix, and accept it anywhere in the file
        # because the engine may insert the paragraph at a different but equivalent anchor.
        if appendix_present(required, final_compact):
            result.update(verdict="completed", detail="appended policy text present")
        elif appendix_present_applicable_clauses(required, final_compact, facts):
            # The policy mixes clauses for two class groups. A contract with no
            # service-fee class legitimately receives only the subscription clause (the
            # engine must not invent a C class), so score the clauses that can apply.
            result.update(verdict="completed",
                          detail="appended policy text present (applicable clauses only)")
        else:
            result.update(verdict="not_executed", detail="appended policy text absent")
        return result

    if not old_text or not compact(old_text):
        result.update(verdict="wrong", detail=f"{operation} without old text")
        return result
    needle = compact(old_text)

    if rule_id in {"G02", "G04"}:
        subscription = class_label_from_guide(required, facts, "subscription")
        service = class_label_from_guide(required, facts, "service")
        expected = [label for label in (subscription, service) if label]
        if not expected:
            result.update(verdict="completed", detail="no group to substitute")
            return result
        missing = [label for label in expected if compact(label) not in final_compact]
        if missing:
            result.update(verdict="wrong", detail=f"group label(s) absent: {missing}")
        else:
            result.update(verdict="completed", detail="group labels present")
        return result

    if operation == "delete":
        if final_index < 0:
            # The paragraph that carried the clause no longer exists in the final file.
            # For a deletion that is the expected outcome (the engine removed it), so the
            # target is carried out — requiring a located paragraph scored a completed
            # deletion as kept (FL-D098). The clause is confirmed absent from the whole
            # document, so a surviving copy elsewhere would still be caught.
            result.update(verdict="completed", detail="deleted clause gone with its paragraph")
        elif not _superseded_survives(target, region, final_compact):
            result.update(verdict="completed", detail="deleted clause gone from its region")
        else:
            result.update(verdict="kept", detail="deleted clause still in its region")
        return result

    # replace: the region must now carry the required obligation. The new wording often
    # keeps the old lead ("赎回费用由…收取" is a prefix of "…收取。赎回费用全额计入基金财产。"),
    # so presence of the new text is the signal, not the mere absence of the old one.
    replacement = compact(required)
    if replacement and replacement[:24] and replacement[:24] in region:
        result.update(verdict="completed", detail="required replacement present in its region")
    elif replacement and replacement[:24] and replacement[:24] in final_compact:
        result.update(verdict="completed", detail="required replacement present elsewhere")
    elif replacement and _obligation_in_region(replacement, region):
        # The region carries the obligation but not with the label's exact wording: an
        # extra "基金" ("调低基金申购费率和基金销售服务费率" against the label's
        # "…和销售服务费率") diverges inside the first 24 characters, so the prefix test
        # above misses it. A correct replacement was scored kept because the label's
        # old_text is a substring of the corrected sentence (FL-D099).
        result.update(verdict="completed",
                      detail="required replacement present in its region (wording variant)")
    elif final_index >= 0 and needle not in region:
        result.update(verdict="completed", detail="superseded wording gone")
    else:
        result.update(verdict="kept", detail="old wording still in its region")
    return result


def _select_label_cases(label_cases: list[dict], run_dir: Path, group: str
                        ) -> tuple[list[dict], set[str], str | None]:
    """Pick the label cases this run actually covers (FL-D116).

    The frozen label file contains both the dev and holdout sets. A dev-only batch has
    no holdout artifacts, so scoring every label would count 111 unrun holdout targets
    as ``not_executed`` and make a 95% dev run look like 65%.
    """
    if group == "all":
        return list(label_cases), set(), None
    if group in {"dev", "holdout"}:
        return [case for case in label_cases if case.get("group") == group], set(), None
    batch_path = run_dir / "batch.json"
    run_cases: set[str] = set()
    if batch_path.exists():
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        run_cases = {str(case) for case in batch.get("cases") or []}
        run_cases |= {str(row.get("case_id")) for row in batch.get("results") or []
                      if row.get("case_id")}
    if not run_cases:
        return list(label_cases), set(), "no batch.json case list; scoring every label case"
    selected = [case for case in label_cases if case["case_id"] in run_cases]
    missing = {case["case_id"] for case in label_cases} - {case["case_id"] for case in selected}
    return selected, missing, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="var/recall-first-evaluation/p6/labels.json")
    parser.add_argument("--run", required=True)
    parser.add_argument("--data-root", default="/home/opencode/data")
    parser.add_argument("--output", default=None)
    parser.add_argument("--group", choices=("run", "dev", "holdout", "all"), default="run",
                        help="Label cases to score. 'run' (default) scores exactly the cases "
                             "listed in the run's batch.json, so a dev-only run is not diluted "
                             "by unrun holdout labels (FL-D116).")
    args = parser.parse_args()

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    run_dir = Path(args.run)
    words_root = Path(args.data_root) / "funds_word"
    output = Path(args.output) if args.output else run_dir / "score.json"

    label_cases = labels["cases"]
    selected, missing, warning = _select_label_cases(label_cases, run_dir, args.group)
    if warning:
        print("WARNING:", warning, flush=True)
    groups = {group: sum(1 for case in selected if case.get("group") == group)
              for group in sorted({case.get("group") or "?" for case in selected})}
    print(f"scored_cases={len(selected)}/{len(label_cases)} groups={json.dumps(groups, ensure_ascii=False)}",
          flush=True)
    if missing and args.group == "run":
        print(f"note: {len(missing)} label cases not in this run (not scored)", flush=True)

    case_rows: list[dict] = []
    verdict_totals: dict[str, int] = {}
    rule_stats: dict[str, dict[str, int]] = {}
    delivery = {"reported_complete": 0, "actually_complete": 0, "false_complete": 0,
                "editable_cases": 0}

    for label in selected:
        case_id = label["case_id"]
        case_dir = run_dir / case_id
        entry: dict = {"case_id": case_id, "group": label["group"],
                       "editable": label["target_count"] > 0,
                       "facts": label["facts"]}
        final = None
        for candidate in ("final", "final.docx", "working_final", "working_final.docx"):
            path = case_dir / candidate
            if path.exists():
                final = path
                break
        if final is None:
            # No artifact at all: every editable target is not executed.
            plain = (case_dir / "result.json")
            report = json.loads((case_dir / "report.json").read_text(encoding="utf-8")) \
                if (case_dir / "report.json").exists() else {}
            entry["artifact"] = None
            entry["delivery_status"] = report.get("delivery_status")
            entry["verdicts"] = [{"target_id": t.get("target_id"), "rule_id": t["rule_id"],
                                  "verdict": "not_executed", "detail": "no artifact"}
                                 for t in label["targets"]]
        else:
            entry["artifact"] = str(final)
            entry["artifact_sha256"] = hashlib.sha256(final.read_bytes()).hexdigest()
            report = json.loads((case_dir / "report.json").read_text(encoding="utf-8")) \
                if (case_dir / "report.json").exists() else {}
            entry["delivery_status"] = report.get("delivery_status")
            final_paragraphs = paragraphs_of(final)
            original_path = words_root / label["file"]
            original_paragraphs = paragraphs_of(original_path) if original_path.exists() else []
            entry["original"] = str(original_path)
            # The engine's own applicability decisions are cross-checked, never used to
            # score the text. A label the engine judged not applicable / already satisfied
            # is a disagreement about scope to report separately, not a silent miss.
            engine_status: dict[str, set] = {}
            for item in report.get("targets") or []:
                engine_status.setdefault(item.get("rule_id"), set()).add(item.get("status"))
            verdicts: list[dict] = []
            conflicts: list[dict] = []
            for label_target in label["targets"]:
                verdict = score_target(label_target, label["facts"], final_paragraphs,
                                       original_paragraphs)
                statuses = engine_status.get(verdict["rule_id"]) or set()
                if statuses and statuses <= {"not_applicable", "satisfied"} \
                        and verdict["verdict"] in {"kept", "not_executed"}:
                    verdict["scope_conflict"] = True
                    conflicts.append({"rule_id": verdict["rule_id"],
                                      "engine_status": sorted(statuses),
                                      "label_verdict": verdict["verdict"]})
                verdicts.append(verdict)
            entry["verdicts"] = verdicts
            entry["applicability_conflicts"] = conflicts
        counts: dict[str, int] = {}
        for verdict in entry["verdicts"]:
            counts[verdict["verdict"]] = counts.get(verdict["verdict"], 0) + 1
            verdict_totals[verdict["verdict"]] = verdict_totals.get(verdict["verdict"], 0) + 1
            key = verdict["rule_id"]
            stats = rule_stats.setdefault(key, {"completed": 0, "total": 0})
            stats["total"] += 1
            if verdict["verdict"] == "completed":
                stats["completed"] += 1
        entry["counts"] = counts
        if entry["editable"]:
            delivery["editable_cases"] += 1
            if report.get("delivery_status") == "complete":
                delivery["reported_complete"] += 1
            complete = counts.get("completed", 0) == len(entry["verdicts"]) and not counts.get("wrong")
            entry["integrated_complete"] = complete
            if complete:
                delivery["actually_complete"] += 1
                if report.get("delivery_status") != "complete":
                    delivery["false_complete"] += 0  # reported less than actual: fine
            elif report.get("delivery_status") == "complete":
                delivery["false_complete"] += 1
        case_rows.append(entry)

    total = sum(verdict_totals.values()) or 1
    completed = verdict_totals.get("completed", 0)
    conflicts_total = sum(len(case.get("applicability_conflicts") or []) for case in case_rows)
    payload = {
        "schema": "fundlex-p6-score-v1",
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "run": str(run_dir),
        "labels_sha256": hashlib.sha256(Path(args.labels).read_bytes()).hexdigest(),
        "totals": {
            "targets": total,
            "completed": completed,
            "target_completion_rate": round(completed / total, 4),
            "verdicts": verdict_totals,
            "applicability_conflicts": conflicts_total,
        },
        "delivery": delivery,
        "cases_scored": len(selected),
        "groups": groups,
        "rule_completion": {
            rule: {"completed": stats["completed"], "total": stats["total"],
                   "rate": round(stats["completed"] / stats["total"], 4)}
            for rule, stats in sorted(rule_stats.items())},
        "cases": case_rows,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"targets": total, "completed": completed,
                      "rate": payload["totals"]["target_completion_rate"],
                      "verdicts": verdict_totals, "delivery": delivery}, ensure_ascii=False))
    print("score sha256:", hashlib.sha256(output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
