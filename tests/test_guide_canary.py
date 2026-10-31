"""Executability canary: runtime-parity admission predicate (FL-D648)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fundlex.guide import bind_operation_identities
from fundlex.guide_canary import (CANARY_SCHEMA_VERSION, blocking_gaps,
                                  executability_report, review_dimensions)

FIXTURES = Path(__file__).parent / "fixtures" / "guides"
MERGED_REAL = "merged_g15_real_20261031.json"
MERGED_BLOCKING_KEYS = ["G03:1", "G03:2", "G06:1", "G07:1", "G07:2", "G08:1",
                        "G10:1", "G10:2", "G10:3", "G10:4", "G10:5", "G15:1"]


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def authoritative_document(rules: list[tuple[str, list[dict]]]) -> dict:
    """Synthetic parsed document through the real identity-binding step."""
    document = {"schema_version": "guide-rules-v1",
                "groups": [{"rule_id": rule_id, "title": f"规则{rule_id}",
                            "section_hint": "释义", "requirement": "要求",
                            "operations": operations, "source_paragraphs": [0]}
                           for rule_id, operations in rules]}
    bind_operation_identities(document)
    return document


def test_builtin_guide_passes_canary():
    """The frozen built-in guide must always satisfy its own contract."""
    from fundlex.guide_store import load_builtin_document
    report = executability_report(load_builtin_document())
    assert report["passed"] is True
    assert report["fatal"] == []
    assert report["executable_ratio"] == 1.0
    assert report["schema_version"] == CANARY_SCHEMA_VERSION
    assert blocking_gaps(load_builtin_document()) == []


def test_real_merged_version_is_caught_deterministically():
    """FL-D648 regression pin: the actual 15-rule re-parse that reached runtime
    with a -70% recall cliff is rejected at admission with the exact operation
    keys the runtime router failed closed on."""
    document = fixture(MERGED_REAL)
    report = executability_report(document)
    assert report["passed"] is False
    assert report["blocking_gaps"] == MERGED_BLOCKING_KEYS
    assert blocking_gaps(document) == MERGED_BLOCKING_KEYS
    assert {item["code"] for item in report["fatal"]} == {"GUIDE_CANARY_OP_UNREGISTERED"}
    assert 0 < report["executable_ratio"] < 1
    dimensions = review_dimensions(report)
    assert dimensions["fatal_codes"] == ["GUIDE_CANARY_OP_UNREGISTERED"]
    assert dimensions["blocking_gaps"] == MERGED_BLOCKING_KEYS


def test_dead_branch_condition_is_fatal():
    operations = [{"op": "replace", "old_text": "甲", "new_text": "乙",
                   "condition": {"kind": "compound", "value": [
                       {"kind": "class_count", "value": 1},
                       {"kind": "class_count", "value": "multiple"}]}}]
    # G01:0 is registered; with a contradictory compound condition the branch
    # can never apply under any fact assignment.
    document = authoritative_document([("G01", operations)])
    report = executability_report(document)
    assert report["passed"] is False
    dead = [item for item in report["fatal"] if item["code"] == "GUIDE_CANARY_DEAD_CONDITION"]
    assert dead and dead[0]["operation"] == "G01:0"


def test_partial_identity_is_fatal():
    document = {"schema_version": "guide-rules-v1",
                "groups": [{"rule_id": "G01", "title": "t", "section_hint": "释义",
                            "operations": [{"op": "append", "new_text": "x",
                                            "operation_id": "G01:0"},
                                           {"op": "append", "new_text": "y"}]}]}
    report = executability_report(document)
    assert report["passed"] is False
    assert any(item["code"] == "GUIDE_CANARY_PARTIAL_IDENTITY" for item in report["fatal"])
    assert blocking_gaps(document) == ["G01"]


def test_legacy_document_never_blocks():
    """Legacy fixtures (no operation_id) run the low-level runtime path and are
    at most advisory — admission parity with `_registry_execution_authoritative`."""
    document = {"schema_version": "guide-rules-v1",
                "groups": [{"rule_id": "G99", "title": "t", "section_hint": "释义",
                            "operations": [{"op": "append", "new_text": "x"}]}]}
    report = executability_report(document)
    assert report["passed"] is True
    assert blocking_gaps(document) == []
    assert any(item["code"] == "GUIDE_CANARY_LEGACY_RULE_UNREGISTERED"
               for item in report["advisory"])


def test_canary_is_deterministic():
    document = fixture(MERGED_REAL)
    first = executability_report(document)
    second = executability_report(json.loads(json.dumps(document)))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.parametrize("name", [MERGED_REAL])
def test_fixture_is_authentic_merged_artifact(name):
    """Guard the pin: the frozen fixture must stay the real 15-rule artifact."""
    document = fixture(name)
    assert len(document["groups"]) == 15
    assert document["groups"][0]["operations"][0]["operation_id_generated"] is True
