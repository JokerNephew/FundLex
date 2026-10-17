"""Offline measurement of sweep window/rule scoping (FL-D109).

No model calls: this only exercises the deterministic chunking and rule-assignment code
so the effect of scoping rules per window can be measured before any batch spend.

For each contract it reports:

* how many windows the character chunker produces;
* how many guide rules each window currently carries (the "全部规则灌每窗" status quo);
* how many rules each window *needs* under section scoping, and which rules would become
  unreachable (a rule whose mapped sections no window touches) — the coverage hole that a
  naive scoping would open and that the hard fallback must close.

Usage::

    .venv/bin/python -m tools.evaluation.sweep_scope_probe --limit 12
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fundlex.docx import inspect_docx
from fundlex.guide import load_guide_document
from fundlex.recall import structure_index
from fundlex.recall_pipeline import (
    _artifact_chunks,
    _guide_rules,
    _rule_mapped_locations,
    _sweep_chunk_chars,
    _sweep_requirements,
)


class _Budget:
    """Stand-in gateway: only max_context_chars is used by the chunker."""

    def __init__(self, chars: int = 12000):
        self.max_context_chars = chars


def probe(path: Path, rules, *, chars: int = 12000) -> dict:
    inspection = inspect_docx(str(path), full=True)
    sections = structure_index(inspection)
    budget = _Budget(chars)

    # The real mapping is model-produced; for measurement, approximate it by binding each
    # rule to the sections that contain its section_hint title, falling back to the whole
    # document. This is only a probe of chunk/rule cardinality, never a correctness claim.
    mapping = {rule["rule_id"]: [] for rule in rules}
    titles = [(s.id, str(s.title or "")) for s in sections]
    for rule in rules:
        hint = str(rule.get("section_hint") or "")
        for section_id, title in titles:
            if hint and hint in title:
                mapping[rule["rule_id"]].append(section_id)
        if not mapping[rule["rule_id"]]:
            mapping[rule["rule_id"]] = [section_id for section_id, _ in titles]

    requirements = _sweep_requirements(rules)
    chunk_chars = _sweep_chunk_chars(budget, requirements, "")
    chunks = _artifact_chunks(inspection, max_chars=chunk_chars)

    rule_locations = {rule_id: _rule_mapped_locations(rule_id, mapping, sections)
                      for rule_id in mapping}
    location_to_section = {}
    for section in sections:
        for location in section.locations:
            location_to_section[location] = section.id

    per_window = []
    covered_rules: set[str] = set()
    for chunk in chunks:
        window_sections = {location_to_section[loc] for loc in chunk.locations
                           if loc in location_to_section}
        needed = [rule_id for rule_id, ids in mapping.items()
                  if set(ids) & window_sections]
        covered_rules.update(needed)
        per_window.append({"window": chunk.id, "locations": len(chunk.locations),
                           "sections": sorted(window_sections),
                           "rules_needed": len(needed), "rules_all": len(rules)})
    unreachable = sorted(set(mapping) - covered_rules)
    return {
        "contract": path.name,
        "paragraphs": len(inspection.paragraphs),
        "sections": len(sections),
        "windows": len(chunks),
        "rules_total": len(rules),
        "requirements_chars_all": len(requirements),
        "requirements_chars_scoped_mean": round(
            sum(max(1, len(_sweep_requirements([r for r in rules
                                                if r["rule_id"] in _needed_ids(chunk, location_to_section, mapping)])))
                for chunk in chunks) / max(1, len(chunks))),
        "status_quo_requirements_chars": len(requirements) * len(chunks),
        "rules_needing_rule_unreachable": unreachable,
        "per_window": per_window,
    }


def _needed_ids(chunk, location_to_section, mapping):
    window_sections = {location_to_section[loc] for loc in chunk.locations
                       if loc in location_to_section}
    return {rule_id for rule_id, ids in mapping.items() if set(ids) & window_sections}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="/home/opencode/data/funds_word")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--chars", type=int, default=12000)
    parser.add_argument("--output", default="/tmp/opencode/sweep_scope_probe.json")
    args = parser.parse_args()

    guide = load_guide_document("guides/builtin_guide_v1.json")
    rules = _guide_rules(guide)
    files = sorted(Path(args.data_root).glob("*.docx"))[:args.limit]
    results = []
    for path in files:
        try:
            results.append(probe(path, rules, chars=args.chars))
        except Exception as exc:  # noqa: BLE001 - a probe must not die on one bad file
            results.append({"contract": path.name, "error": f"{type(exc).__name__}: {exc}"})
    Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=1))

    total_st = sum(r.get("status_quo_requirements_chars", 0) for r in results)
    total_scoped = sum((r.get("requirements_chars_scoped_mean") or 0) * r.get("windows", 0)
                       for r in results)
    print(f"contracts: {len(results)}")
    print(f"status-quo requirements chars (sum over windows): {total_st}")
    print(f"section-scoped requirements chars (sum over windows): {total_scoped}")
    if total_st:
        print(f"reduction: {100 * (1 - total_scoped / total_st):.1f}%")
    holes = {r["contract"]: r["rules_needing_rule_unreachable"]
             for r in results if r.get("rules_needing_rule_unreachable")}
    print(f"contracts with unreachable rules under naive scoping: {len(holes)}")
    for name, ids in list(holes.items())[:5]:
        print(f"  {name[:40]} -> {ids}")
    print(f"written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
