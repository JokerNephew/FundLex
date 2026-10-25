"""Offline replay of one frozen pipeline stage.

Recomputes deterministic stages from frozen source and boundary inputs. Model-owned
stages are replayed through immutable cassettes; a miss never falls back to live.
"""
from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from .frozen import FrozenError, FrozenRun

STAGES = ("facts", "applicability", "targets", "obligations", "plan", "claim_replay")


def _facts(inspection: Any, value: dict) -> Any:
    from .recall import facts_from_value
    facts = facts_from_value(inspection, {
        **value, "fund_type": {"value": value.get("fund_type"),
                               "quote": value.get("fund_type_quote", ""),
                               "basis": value.get("fund_type_basis", "")},
        "floating_management_fee": {"value": value.get("is_floating_fee"),
                                    "quote": value.get("floating_quote", ""),
                                    "basis": value.get("floating_basis", "")},
        "direct_sales_exempt": {"classes": value.get("direct_sales_exempt_group") or [],
            "quote": (value.get("channel_evidence") or {}).get("direct_sales_exempt", "")},
        "other_sales_charged": {"classes": value.get("other_sales_charged_group") or [],
            "quote": (value.get("channel_evidence") or {}).get("other_sales_charged", "")},
    })
    for name, status in (value.get("fact_status") or {}).items():
        if status == "VERIFIED" and facts.status_of(name) != "VERIFIED":
            raise FrozenError("FROZEN_FACT_EVIDENCE_INVALID:" + name)
    return replace(facts, condition_overrides=dict(value.get("condition_overrides") or {}),
        fact_status={**facts.fact_status, **(value.get("fact_status") or {})},
        fund_type_certification=dict(value.get("fund_type_certification") or {}))


class _RecordedGateway:
    """Only recorded requests; credentials, HTTP clients and budgets are unnecessary."""
    max_context_chars = 10_000_000

    def __init__(self, directory: Path):
        self.directory = directory
        self.calls = 0

    def call(self, **kwargs: Any) -> Any:
        from types import SimpleNamespace
        from .frozen import ModelCassette
        matches = []
        for path in sorted((self.directory / kwargs["task_type"]).glob("*.json")):
            body = json.loads(path.read_text(encoding="utf-8"))["body"]
            request = body["request"]
            inner = request["request"]
            if (request["prompt_version"] == kwargs.get("prompt_version", "v1")
                    and inner["bounded_context"] == kwargs["bounded_context"]
                    and inner["instruction"] == kwargs["instruction"]
                    and inner["response_schema"] == kwargs["response_schema"]):
                matches.append(request)
        if len(matches) != 1:
            raise FrozenError("MODEL_REPLAY_MISS" if not matches else "MODEL_REPLAY_AMBIGUOUS")
        value, event = ModelCassette(self.directory).load(matches[0], kwargs["response_schema"])
        self.calls += 1
        if event.get("error_code"):
            from .model import ModelError
            raise ModelError(event["error_code"])
        return SimpleNamespace(value=value, model=event.get("actual_model"), attempts=0)


def replay_stage(run_dir: str | Path, stage: str, *, revision: int = 0) -> dict[str, Any]:
    if stage not in STAGES:
        raise FrozenError("FROZEN_STAGE_INVALID:" + str(stage))
    run = FrozenRun(Path(run_dir))
    run.verify()
    from .docx import inspect_docx
    from .guide import validate_runtime_guide
    from .recall import Target, assign_target_operations, build_docx_edits, plan_edits
    from .obligations import apply_facts, compile_obligations, project
    directory = Path(run_dir)
    boundary_path = directory / "stages" / (stage + (f"-{revision}" if revision else "") + ".json")
    inputs = {}
    if boundary_path.is_file():
        from .frozen import digest
        boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
        inputs = boundary["inputs"]
        if boundary.get("inputs_sha256") != digest(inputs) or boundary.get("stage") != stage:
            raise FrozenError("FROZEN_STAGE_INTEGRITY_MISMATCH")
    else:
        raise FrozenError("FROZEN_STAGE_INPUT_MISSING:" + str(boundary_path.name))
    def read(name: str) -> Any:
        if name in inputs:
            return inputs[name]
        path = directory / (name + ".json")
        if not path.is_file():
            raise FrozenError("FROZEN_STAGE_INPUT_MISSING:" + name)
        return json.loads(path.read_text(encoding="utf-8"))
    guide = read("guide")
    validate_runtime_guide(guide)
    original = inspect_docx(directory / "original.docx", full=True)
    facts = _facts(original, read("facts"))
    obligations = compile_obligations(guide)
    apply_facts(obligations, facts)
    rules = {rule["rule_id"]: rule for rule in guide["groups"]}
    gateway = _RecordedGateway(directory / "model_calls")
    gateway.max_context_chars = int(inputs.get("max_context_chars") or 10_000_000)
    if stage == "facts":
        value = facts.as_ledger()
    elif stage == "applicability":
        value = {item.obligation_id: item.applicability.as_dict() for item in obligations.records}
    elif stage == "obligations":
        project(obligations, read("report"), scope_gaps=set(inputs.get("scope_gaps") or []))
        value = obligations.as_dict()
    else:
        allowed = {item.name for item in fields(Target)}
        targets = [Target(**{key: value for key, value in item.items() if key in allowed})
                   for item in read("targets")]
        if stage == "targets":
            value = {"attribution": assign_target_operations(targets, rules, original, facts, obligations),
                     "targets": [target.as_dict() for target in targets]}
        elif stage == "plan":
            if inputs.get("existing_plan") is not None and inputs.get("dirty_locations"):
                from .recall import replan_sites
                value = replan_sites(inputs["existing_plan"], set(inputs["dirty_locations"]), rules,
                    targets, original, facts, gateway, obligations=obligations,
                    max_compose_calls=int(inputs.get("max_compose_calls", 6)))
            else:
                value = plan_edits(rules, targets, original, facts, gateway, obligations=obligations,
                                   max_compose_calls=int(inputs.get("max_compose_calls", 6)))
            # Keep frozen plan replay identical to the persisted production plan:
            # report generation projects the validated source slice back onto each
            # business edit for Review manifest reconstruction.
            projected = build_docx_edits(value.get("edits") or [], original)
            by_key = {
                (str(item.get("rule_id") or ""), str(item.get("target_id") or ""),
                 str(item.get("location") or ""), int(item.get("start") or 0),
                 int(item.get("end") or 0), str(item.get("replacement") or "")): item
                for item in projected
            }
            edits = []
            for item in value.get("edits") or []:
                item = dict(item)
                key = (str(item.get("rule_id") or ""), str(item.get("target_id") or ""),
                       str(item.get("location") or ""), int(item.get("start") or 0),
                       int(item.get("end") or 0), str(item.get("replacement") or ""))
                source = by_key.get(key)
                if source is not None:
                    item["expected_old_text"] = source.get("expected_old_text", "")
                    item["expected_old_hash"] = source.get("expected_old_hash", "")
                edits.append(item)
            value = {**value, "edits": edits}
        else:
            from .generation.claim_replay import replay_claims, check_delete_residuals
            from .generation.components import claim_components_for_rules
            artifact = (directory / inputs["artifact"] if inputs.get("artifact") else
                        next((directory / name for name in ("working_final.docx", "final.docx")
                              if (directory / name).is_file()), None))
            if artifact is None:
                raise FrozenError("FROZEN_ARTIFACT_MISSING")
            actual = inspect_docx(artifact, full=True)
            edits = read("plan").get("edits") or []
            value = replay_claims(edits, original, actual, rules_by_id=rules, facts=facts,
                                  components_by_rule=inputs["components_by_rule"],
                                  required_terms_by_rule=inputs["required_terms_by_rule"],
                                  target_rules=inputs["target_rules"],
                                  targets_by_id={target.target_id: target.as_dict() for target in targets},
                                  obligations=obligations)
            residuals = check_delete_residuals(rules, actual, edits=edits, original=original,
                targets=[target.as_dict() for target in targets], facts=facts, obligations=obligations)
            value["failures"].extend(residuals)
            value["verified"] = bool(value["verified"] and not residuals)
    import subprocess
    try:
        replay_head = subprocess.check_output(["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        replay_head = None
    binding_path = directory / "validation-config.json"
    binding = json.loads(binding_path.read_text()) if binding_path.is_file() else {}
    return {"stage": stage, "run_dir": str(Path(run_dir)), "value": value,
            "recorded_head": binding.get("head"), "replay_head": replay_head,
            "same_head": binding.get("head") == replay_head if binding else None,
            "model_calls": 0, "cassette_replays": gateway.calls, "replayed": True}
