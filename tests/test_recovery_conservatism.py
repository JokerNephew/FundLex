"""Recovery conservatism (FL-D656, mechanism D).

A recovery channel must never manufacture a blocking target for an operation
whose business site is already proven satisfied — the B19 G04 R036/R037 shape,
where satisfied T005/T006 still got unplannable R-target twins that flipped
the Ledger open.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import fundlex.targeting as targeting
from fundlex.targeting import target_for_missing_operation


def _record(rule_id="G04", index=1, operation_id="G04:1"):
    spec = SimpleNamespace(rule_id=rule_id, operation_index=index,
                           operation_id=operation_id)
    return SimpleNamespace(spec=spec)


def _target(target_id, rule_id="G04", *, state, ops=("G04:1",), location="p160",
            out_of_scope=False):
    return SimpleNamespace(target_id=target_id, rule_id=rule_id, state=state,
                           location=location, operations=tuple(ops),
                           out_of_scope=out_of_scope)


def _inspection():
    span = SimpleNamespace(text="认购费和申购费按类别分别收取。", location="p160",
                           segments=())
    inspection = SimpleNamespace(paragraphs=[span])
    inspection.by_location = lambda location: span
    return inspection


def _rule():
    return {"rule_id": "G04", "title": "G04",
            "operations": [{"op": "replace", "old_text": "认购费和申购费", "new_text": "x"},
                           {"op": "replace", "old_text": "认购费和申购费", "new_text": "y"}]}


@pytest.fixture
def candidate_found(monkeypatch):
    """Force deterministic candidates so suppression is the only variable."""
    scan = {"pages": 1, "has_more": False, "candidates": ["p160"]}
    monkeypatch.setattr(targeting, "_scan_scope_pages",
                        lambda *args, **kwargs: (["p160"], scan))


def _create(targets, record=None):
    return target_for_missing_operation(
        record or _record(), targets, {"G04": _rule()},
        None, _inspection(), {"G04": ["S1"]}, [])


def test_needs_edit_twin_still_suppresses_recovery():
    assert _create([_target("T1", state="needs_edit")]) is None


def test_satisfied_target_suppresses_recovery_target(candidate_found):
    assert _create([_target("T6", state="satisfied")]) is None


def test_already_satisfied_state_also_suppresses(candidate_found):
    assert _create([_target("T6", state="already_satisfied")]) is None


def test_different_operation_satisfied_does_not_suppress(candidate_found):
    # B19 had T005 (G04:0 satisfied) and T006 (G04:1 satisfied): only the
    # matching operation's satisfaction may suppress recovery.
    created = _create([_target("T5", state="satisfied", ops=("G04:0",))])
    assert created is not None
    assert created.state == "needs_edit"


def test_out_of_scope_satisfied_does_not_suppress(candidate_found):
    created = _create([_target("T6", state="satisfied", out_of_scope=True)])
    assert created is not None
