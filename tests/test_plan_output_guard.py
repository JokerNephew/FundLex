"""Plan-output completeness guard (FL-D657, mechanism C)."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.recall import plan_output_guard


def _target(target_id="T1", *, state="needs_edit", start=10, end=40,
            location="p5"):
    return SimpleNamespace(target_id=target_id, rule_id="G05", state=state,
                           location=location, start=start, end=end,
                           out_of_scope=False)


def _edit(target_id="T1", *, start=10, end=40, operation="G05:0",
          rule_id="G05", location="p5"):
    evidence = {"operation_keys": [operation], "obligation_ids": []}
    return {"rule_id": rule_id, "target_id": target_id, "location": location,
            "start": start, "end": end, "operation": operation,
            "replacement": "new", "evidence": evidence}


def _planned(edits):
    return {"edits": list(edits),
            "ledger": [{"target_id": edit["target_id"], "status": "planned",
                        "location": edit["location"],
                        "operation_keys": list(
                            (edit.get("evidence") or {}).get("operation_keys") or [])}
                       for edit in edits],
            "conflicts": []}


def test_clean_plan_passes_unchanged():
    planned = _planned([_edit()])
    issues = plan_output_guard(planned, [_target()])
    assert issues == []
    assert len(planned["edits"]) == 1
    assert planned["ledger"][0]["status"] == "planned"


def test_already_cited_closed_target_edit_is_rejected():
    planned = _planned([_edit()])
    issues = plan_output_guard(planned, [_target(state="satisfied")])
    assert [issue["code"] for issue in issues] == ["PLAN_CITED_CLOSED_TARGET"]
    assert planned["edits"] == []
    assert planned["ledger"][0]["status"] == "unresolved"
    assert planned["ledger"][0]["reason"] == "PLAN_CITED_CLOSED_TARGET"
    assert planned["plan_guard"][0]["kind"] == "plan_guard"


def test_not_applicable_target_is_also_closed():
    planned = _planned([_edit()])
    issues = plan_output_guard(planned, [_target(state="not_applicable")])
    assert [issue["code"] for issue in issues] == ["PLAN_CITED_CLOSED_TARGET"]


def test_span_outside_target_is_inconsistent():
    planned = _planned([_edit(start=200, end=240)])
    issues = plan_output_guard(planned, [_target()])
    assert [issue["code"] for issue in issues] == ["PLAN_SITE_INCONSISTENT"]
    assert planned["edits"] == []


def test_span_within_allowance_passes():
    planned = _planned([_edit(start=0, end=70)])
    planned_with_pad = _planned([_edit(start=0, end=70)])
    issues = plan_output_guard(planned_with_pad, [_target(start=10, end=40)])
    assert issues == []


def test_unbound_operation_is_rejected():
    edit = _edit()
    edit["operation"] = ""
    edit["evidence"] = {}
    planned = _planned([edit])
    issues = plan_output_guard(planned, [_target()])
    assert [issue["code"] for issue in issues] == ["PLAN_OPERATION_UNBOUND"]


def test_unknown_target_id_is_left_alone():
    """Composite/component edits bind other targets and stay outside the guard."""
    planned = _planned([_edit("X9")])
    issues = plan_output_guard(planned, [_target()])
    assert issues == []
    assert len(planned["edits"]) == 1


def test_second_guard_pass_is_idempotent():
    planned = _planned([_edit()])
    target = _target(state="satisfied")
    assert plan_output_guard(planned, [target])
    assert plan_output_guard(planned, [target]) == []
