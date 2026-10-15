"""Replay cached model checkpoints locally to debug a cloud run deterministically.

Downloads nothing; point it at a directory of checkpoint JSON files (as produced by
``fundlex.checkpoints``) and it rebuilds the plan for the same contract and guide.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.evaluation.replay_checkpoints `
      --checkpoints var/cloud-runs/<run>/checkpoints `
      --contract "funds_word/<contract>.docx" --guide guides/builtin_guide_v1.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]


class ReplayGateway:
    def __init__(self, checkpoints: dict[str, dict], *, max_context_chars: int = 32000,
                 allow_task_fallback: bool = True):
        self.checkpoints = checkpoints
        self.by_task: dict[str, list[dict]] = {}
        for path_key, value in checkpoints.items():
            task = str((value or {}).get("__task_type__") or "")
            self.by_task.setdefault(task, []).append(value)
        self.allow_task_fallback = allow_task_fallback
        self.max_context_chars = max_context_chars
        self.max_calls = 1000
        self.calls: list[str] = []
        self.fallbacks: list[str] = []

    def call(self, *, task_type, bounded_context, response_schema, instruction, prompt_version="v1"):
        digest = hashlib.sha256(bounded_context.encode()).hexdigest()
        self.calls.append(f"{task_type}:{digest[:10]}")
        if digest in self.checkpoints:
            return SimpleNamespace(value=self.checkpoints[digest])
        candidates = self.by_task.get(task_type) or []
        if self.allow_task_fallback and len(candidates) == 1:
            self.fallbacks.append(f"{task_type}:{digest[:10]}")
            return SimpleNamespace(value=candidates[0])
        raise AssertionError(f"missing checkpoint for {task_type} sha={digest[:12]} "
                             f"context_chars={len(bounded_context)}")


def load_checkpoints(directory: Path) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        body = envelope.get("body") or {}
        query = body.get("query") or {}
        digest = query.get("bounded_context_sha256")
        if digest:
            value = dict(body.get("value") or {})
            value["__task_type__"] = query.get("task_type")
            mapping[digest] = value
    return mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay checkpoints to rebuild a plan")
    parser.add_argument("--checkpoints", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--guide", default="guides/builtin_guide_v1.json")
    parser.add_argument("--dump-edits", default="")
    args = parser.parse_args(argv)

    from fundlex.docx import DocxError, generate_artifacts, inspect_docx, validate_edit_plan
    from fundlex.guide import load_guide_document
    from fundlex.recall import (build_docx_edits, content_check_factory, extract_facts,
                                inventory_window, plan_edits, plan_windows, rule_context,
                                scope_map, structure_index)
    from fundlex.recall_pipeline import MIN_WINDOW_CHARS

    guide = load_guide_document(REPO / args.guide if not Path(args.guide).is_absolute() else args.guide)
    rules = guide["groups"]
    rules_by_id = {rule["rule_id"]: rule for rule in rules}
    contract = Path(args.contract)
    if not contract.exists():
        contract = REPO / args.contract
    inspection = inspect_docx(contract, full=True)
    gateway = ReplayGateway(load_checkpoints(Path(args.checkpoints)))

    facts = extract_facts(inspection, gateway)
    print("facts:", facts.fund_type, "classes:", [(c.name, c.subscription_fee, c.service_fee) for c in facts.classes])
    sections = structure_index(inspection)
    mapping = scope_map(rules, sections, gateway)
    print("mapped rules:", sum(1 for ids in mapping.values() if ids), "/", len(mapping))
    targets = []
    facts_text = json.dumps(facts.as_ledger(), ensure_ascii=False, indent=1)
    rules_text = rule_context(rules, full=True)
    window_chars = max(MIN_WINDOW_CHARS,
                       gateway.max_context_chars - len(facts_text) - len(rules_text) - 2000)
    for window, rule_ids in plan_windows(sections, inspection, mapping, max_chars=window_chars):
        window_rules = [rules_by_id[rule_id] for rule_id in rule_ids]
        found, _ = inventory_window(window, window_rules, facts, gateway, inspection)
        targets.extend(found)
    planned = plan_edits(rules_by_id, targets, inspection, facts, gateway, max_compose_calls=12)
    print("targets:", len(targets), "| planned edits:", len(planned["edits"]), "| conflicts:", len(planned["conflicts"]))
    for conflict in planned["conflicts"]:
        print("  conflict:", conflict)
    for edit in planned["edits"]:
        print(f"  edit {edit['rule_id']} {edit['location']} [{edit['start']},{edit['end']}) "
              f"{edit['operation']} {edit['content_source']} -> {edit['replacement'][:60]!r}")
    edits = build_docx_edits(planned["edits"], inspection)
    try:
        plan = validate_edit_plan(contract, edits, {},
                                  content_check=content_check_factory(planned["edits"], inspection))
        print("validate: OK", len(plan.edits), "edits")
        out = Path(args.dump_edits or "var/replay-artifacts")
        out.mkdir(parents=True, exist_ok=True)
        artifacts = generate_artifacts(contract, plan, out / "redline.docx", out / "final.docx")
        print("artifacts:", artifacts.final_sha256[:12], artifacts.checks)
    except DocxError as error:
        print("validate FAILED:", error.code)
        for edit in edits:
            print(f"   raw edit {edit.get('edit_id')} {edit.get('location')} "
                  f"[{edit.get('start')},{edit.get('end')}) op={edit.get('operation')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
