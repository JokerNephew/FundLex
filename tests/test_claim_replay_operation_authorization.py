"""Operation/obligation-level claim-replay authorization (external review 2026-10-20 P0-1).

Paragraph-level union authorization lets operation B borrow operation A's delete or
add rights.  These tests pin the operation-level proof: every edit/component is
validated against the operations it actually executes, overlapping edits become an
explicit joint proof, and one satisfied sibling cannot close a failed obligation.
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.generation.claim_replay import replay_claims


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{index}", text=text)
                           for index, text in enumerate(texts)]

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


class Record:
    def __init__(self, operation_id, obligation_id, index):
        self.obligation_id = obligation_id
        operation = RULE["operations"][index] if operation_id.startswith("G99:") else {
            "op": "replace", "old_text": "旧说法甲。", "new_text": "新说法。"}
        self.spec = SimpleNamespace(rule_id=operation_id.split(":")[0], operation_id=operation_id,
                                    operation_index=index, one_of_group="", alternatives=(),
                                    op=operation["op"], old_text=operation.get("old_text", ""),
                                    new_text=operation.get("new_text", ""))
        self.applicability = SimpleNamespace(status="TRUE")


class Ledger:
    def __init__(self, records):
        self._records = records

    def record(self, key):
        return self._records.get(str(key))


RULE = {
    "rule_id": "G99",
    "operations": [
        {"op": "delete", "old_text": "旧句甲。", "new_text": ""},
        {"op": "append", "old_text": "", "new_text": "新增乙。"},
    ],
    "old_text_variants": [],
}

TARGETS = {
    "T0": {"target_id": "T0", "operations": ["G99:0"]},
    "T1": {"target_id": "T1", "operations": ["G99:1"]},
}


def _edit(target_id, start, end, replacement):
    return {"rule_id": "G99", "target_id": target_id, "location": "p0",
            "start": start, "end": end, "replacement": replacement,
            "components": []}


def _replay(edits, before, after, *, targets=TARGETS, ledger=None):
    return replay_claims(edits, Inspection([before]), Inspection([after]),
                         rules_by_id={"G99": RULE}, targets_by_id=targets,
                         obligations=ledger)


def test_legitimate_sibling_operations_both_pass():
    before = "旧句甲。保留句。"
    after = "保留句。新增乙。"
    result = _replay([_edit("T0", 0, 4, ""), _edit("T1", 8, 8, "新增乙。")],
                     before, after)
    assert result["verified"] is True, result["failures"]
    assert result["units_checked"] == 2
    assert {record["operation_id"] for record in result["operations"]} == {
        "G99:0", "G99:1"}


def test_sibling_cannot_lend_delete_permission():
    # Operation 1 (append-only) consumes the unrelated sentence "保留句。"; only the
    # sibling delete operation is authorized to remove text.  A paragraph-level union
    # authorization would explain this deletion and wrongly pass.
    before = "旧句甲。保留句。"
    tampered = "新增乙。"
    result = _replay([_edit("T0", 0, 4, ""), _edit("T1", 4, 8, "新增乙。")],
                     before, tampered)
    assert result["verified"] is False
    failures = {(failure["operation_id"], failure["code"])
                for failure in result["failures"] if failure.get("operation_id")}
    assert ("G99:1", "CLAIM_OPERATION_SPAN_UNAUTHORIZED") in failures


def test_sibling_cannot_lend_add_permission():
    # Operation 1's replacement carries operation 0's ``new_text`` (borrowed add
    # permission) instead of its own required wording.
    before = "保留句。"
    after = "新增甲。新增甲。"
    targets = {"T0": {"target_id": "T0", "operations": ["G99:0"]},
               "T1": {"target_id": "T1", "operations": ["G99:1"]}}
    rule = {"rule_id": "G99",
            "operations": [{"op": "append", "old_text": "", "new_text": "新增甲。"},
                           {"op": "append", "old_text": "", "new_text": "新增乙。"}],
            "old_text_variants": []}
    result = replay_claims(
        [_edit("T1", 0, 4, "新增甲。"), _edit("T0", 0, 0, "新增甲。")],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G99": rule}, targets_by_id=targets)
    assert result["verified"] is False
    failures = {(failure["operation_id"], failure["code"])
                for failure in result["failures"] if failure.get("operation_id")}
    assert ("G99:1", "CLAIM_OPERATION_EFFECT_MISSING") in failures


def test_missing_operation_attribution_fails_closed():
    # Operation identity must survive planning; text inference is not authorization.
    before = "旧句甲。保留句。"
    tampered = "新增乙。"
    result = _replay([_edit("", 0, 4, ""), _edit("", 4, 8, "新增乙。")],
                     before, tampered, targets={})
    assert result["verified"] is False
    failures = {(failure["operation_id"], failure["code"])
                for failure in result["failures"] if failure.get("operation_id")}
    assert ("G99:?", "CLAIM_OPERATION_UNATTRIBUTED") in failures


def test_claim_replay_uses_declared_operation_id_without_rule_index_alias():
    rule = {"rule_id": "G99", "operations": [
        {"operation_id": "G99:CUSTOM_DELETE", "op": "delete", "old_text": "旧句甲。", "new_text": ""},
        {"operation_id": "G99:CUSTOM_APPEND", "op": "append", "old_text": "", "new_text": "新增乙。"},
    ], "old_text_variants": []}
    targets = {"T0": {"target_id": "T0", "operations": ["G99:CUSTOM_DELETE"]},
               "T1": {"target_id": "T1", "operations": ["G99:CUSTOM_APPEND"]}}
    result = replay_claims(
        [{**_edit("T0", 0, 4, ""), "operation_keys": ["G99:0"]}],
        Inspection(["旧句甲。保留句。"]), Inspection(["保留句。"]),
        rules_by_id={"G99": rule}, targets_by_id=targets)
    assert result["verified"] is False
    assert any(item.get("code") in {"CLAIM_OPERATION_KEYS_INVALID",
                                     "CLAIM_OPERATION_NOT_AUTHORIZED",
                                     "CLAIM_OPERATION_UNATTRIBUTED"}
               for item in result["failures"])


def test_overlapping_operations_use_explicit_joint_verification():
    rule = {"rule_id": "G98",
            "operations": [{"op": "replace", "old_text": "甲乙丙",
                            "new_text": "甲乙丙A"},
                           {"op": "replace", "old_text": "丙丁戊",
                            "new_text": "丁戊B"}],
            "old_text_variants": []}
    before = "甲乙丙丁戊"
    after = "甲乙丙A丁戊B"
    targets = {"T0": {"target_id": "T0", "operations": ["G98:0"]},
               "T1": {"target_id": "T1", "operations": ["G98:1"]}}
    edits = [{"rule_id": "G98", "target_id": "T0", "location": "p0",
              "start": 0, "end": 3, "replacement": "甲乙丙A", "components": []},
             {"rule_id": "G98", "target_id": "T1", "location": "p0",
              "start": 2, "end": 5, "replacement": "丁戊B", "components": []}]
    result = replay_claims(edits, Inspection([before]), Inspection([after]),
                           rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is True, result["failures"]
    # Both obligations were proven in the joint pass; neither unit is silently dropped.
    assert len(result["operations"]) == 2
    assert all(record["verdict"] == "PASS" for record in result["operations"])


def test_one_satisfied_operation_cannot_close_failed_obligation_group():
    ledger = Ledger({
        "G99:0": Record("G99:0", "G99:B1:O1", 0),
        "G99:1": Record("G99:1", "G99:B1:O2", 1),
    })
    before = "旧句甲。保留句。"
    tampered = "新增乙。"
    result = _replay([_edit("T0", 0, 4, ""), _edit("T1", 4, 8, "")],
                     before, tampered, ledger=ledger)
    assert result["verified"] is False
    assert result["obligations"]["G99:B1:O1"]["state"] == "PASS"
    assert result["obligations"]["G99:B1:O2"]["state"] == "FAIL"


def test_unattributed_edit_never_gets_rule_wide_union():
    # Target has no operation keys and the edit carries neither the old nor the new
    # wording; it must fail closed instead of borrowing the delete operation.
    before = "旧句甲。保留句。"
    after = "旧句甲。"
    result = _replay([_edit("", 4, 8, "")], before, after, targets={})
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_UNATTRIBUTED" in codes


def test_invalid_target_operation_key_fails_closed():
    before = "旧句甲。保留句。"
    after = "保留句。"
    result = _replay([_edit("TX", 0, 4, "")], before, after,
                     targets={"TX": {"target_id": "TX", "operations": ["G99:99"]}})
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_KEYS_INVALID" in codes


def test_oversized_delete_cannot_swallow_a_sibling_sentence():
    # Operation 0 owns only "旧句甲。"; deleting the sibling sentence "保留句。" as well
    # must be rejected even though this is a delete operation.
    before = "旧句甲。保留句。"
    after = ""
    result = _replay([_edit("T0", 0, 8, "")], before, after)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_SPAN_UNAUTHORIZED" in codes


def test_replace_operation_cannot_borrow_delete_rights():
    rule = {"rule_id": "G98",
            "operations": [{"op": "delete", "old_text": "旧句甲。", "new_text": ""},
                           {"op": "replace", "old_text": "保留句。",
                            "new_text": "保留新句。"}],
            "old_text_variants": []}
    before = "旧句甲。保留句。"
    after = "保留新句。"
    targets = {"T1": {"target_id": "T1", "operations": ["G98:1"]}}
    result = replay_claims(
        [{"rule_id": "G98", "target_id": "T1", "location": "p0", "start": 0,
          "end": 8, "replacement": "保留新句。", "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_SPAN_UNAUTHORIZED" in codes


def test_concatenated_sibling_addition_is_rejected():
    rule = {"rule_id": "G99",
            "operations": [{"op": "append", "old_text": "", "new_text": "新增甲。"},
                           {"op": "append", "old_text": "", "new_text": "新增乙。"}],
            "old_text_variants": []}
    before = "保留句。"
    after = "保留句。新增甲。新增乙。"
    targets = {"T0": {"target_id": "T0", "operations": ["G99:0"]}}
    result = replay_claims(
        [{"rule_id": "G99", "target_id": "T0", "location": "p0", "start": 4,
          "end": 4, "replacement": "新增甲。新增乙。", "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G99": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_EFFECT_MISSING" in codes


def test_component_cannot_borrow_sibling_addition():
    rule = {"rule_id": "G99",
            "operations": [{"op": "append", "old_text": "", "new_text": "新增甲。"},
                           {"op": "append", "old_text": "", "new_text": "新增乙。"}],
            "old_text_variants": []}
    before = "保留句。"
    after = "保留句。新增甲。新增乙。"
    targets = {"T0": {"target_id": "T0", "operations": ["G99:0"]}}
    component = {"rule_id": "G99", "target_id": "T0", "location": "p0", "start": 4,
                 "end": 4, "replacement": "新增甲。新增乙。", "components": []}
    edit = {"rule_id": "G99", "target_id": "T0", "location": "p0", "start": 4,
            "end": 4, "replacement": "新增甲。新增乙。", "components": [component]}
    result = replay_claims([edit], Inspection([before]), Inspection([after]),
                           rules_by_id={"G99": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_EFFECT_MISSING" in codes


def test_missing_own_new_wording_is_rejected():
    rule = {"rule_id": "G97",
            "operations": [{"op": "replace", "old_text": "调低赎回费率",
                            "new_text": "调低销售服务费率"},
                           {"op": "delete", "old_text": "并报中国证监会备案", "new_text": ""}],
            "old_text_variants": []}
    before = "基金管理人可以调低赎回费率并报中国证监会备案。"
    after = "基金管理人可以调低其他费率。"
    targets = {"T0": {"target_id": "T0", "operations": ["G97:0"]}}
    result = replay_claims(
        [{"rule_id": "G97", "target_id": "T0", "location": "p0", "start": 0,
          "end": len(before), "replacement": after, "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G97": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_EFFECT_MISSING" in codes


def test_joint_result_missing_a_sibling_delete_effect_fails():
    rule = {"rule_id": "G98",
            "operations": [{"op": "delete", "old_text": "甲乙丙", "new_text": ""},
                           {"op": "replace", "old_text": "丙丁", "new_text": "丁B"}],
            "old_text_variants": []}
    before = "甲乙丙丁"
    after = "甲乙丙丁B"  # op1 applied, op0's deletion did not happen
    targets = {"T0": {"target_id": "T0", "operations": ["G98:0"]},
               "T1": {"target_id": "T1", "operations": ["G98:1"]}}
    edits = [{"rule_id": "G98", "target_id": "T0", "location": "p0", "start": 0,
              "end": 3, "replacement": "", "components": []},
             {"rule_id": "G98", "target_id": "T1", "location": "p0", "start": 2,
              "end": 4, "replacement": "丁B", "components": []}]
    result = replay_claims(edits, Inspection([before]), Inspection([after]),
                           rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_JOINT_OPERATION_EFFECT_MISSING" in codes


def test_joint_off_span_mutation_is_rejected():
    rule = {"rule_id": "G98",
            "operations": [{"op": "replace", "old_text": "甲乙丙",
                            "new_text": "甲乙丙A"},
                           {"op": "replace", "old_text": "丙丁", "new_text": "丁B"}],
            "old_text_variants": []}
    before = "开头。甲乙丙丁。结尾。"
    after = "开头。甲乙丙A丁B。改动的结尾。"  # suffix outside the union changed
    targets = {"T0": {"target_id": "T0", "operations": ["G98:0"]},
               "T1": {"target_id": "T1", "operations": ["G98:1"]}}
    edits = [{"rule_id": "G98", "target_id": "T0", "location": "p0", "start": 3,
              "end": 6, "replacement": "甲乙丙A", "components": []},
             {"rule_id": "G98", "target_id": "T1", "location": "p0", "start": 5,
              "end": 7, "replacement": "丁B", "components": []}]
    result = replay_claims(edits, Inspection([before]), Inspection([after]),
                           rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OUTSIDE_SPAN_CHANGED" in codes


def test_joint_unit_effect_failure_blocks_verified_even_without_overlap_union_failure():
    # An occurrence mismatch is a unit-level failure; the old overlap branch recorded it
    # as FAIL in the operation ledger but still returned verified=True.
    rule = {"rule_id": "G98",
            "operations": [{"op": "replace", "old_text": "甲乙", "new_text": "甲乙A"},
                           {"op": "replace", "old_text": "乙丙", "new_text": "乙丙B"}],
            "old_text_variants": []}
    before = "甲乙丙"
    after = "甲乙A丙B"
    targets = {"T0": {"target_id": "T0", "operations": ["G98:0"],
                      "occurrence_index": 5, "occurrence_anchor": "甲乙"},
               "T1": {"target_id": "T1", "operations": ["G98:1"]}}
    edits = [{"rule_id": "G98", "target_id": "T0", "location": "p0", "start": 0,
              "end": 2, "replacement": "甲乙A", "components": []},
             {"rule_id": "G98", "target_id": "T1", "location": "p0", "start": 1,
              "end": 3, "replacement": "乙丙B", "components": []}]
    result = replay_claims(edits, Inspection([before]), Inspection([after]),
                           rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OCCURRENCE_MISMATCH" in codes


def test_paragraph_scoped_multi_operation_edit_without_attribution_fails():
    before = "保留句。其他内容。"
    after = "完全不同的新文本。"
    result = replay_claims(
        [{"rule_id": "G99", "location": "p0", "replacement": after,
          "content_source": "guide_text", "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G99": RULE}, targets_by_id={})
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_UNATTRIBUTED" in codes


def test_non_joint_delete_must_actually_remove_the_old_sentence():
    rule = {"rule_id": "G96",
            "operations": [{"op": "delete", "old_text": "旧句甲。", "new_text": ""},
                           {"op": "append", "old_text": "", "new_text": "新增乙。"}],
            "old_text_variants": []}
    before = "旧句甲。保留句。"
    after = "旧句甲。保留句。新增乙。"
    targets = {"T0": {"target_id": "T0", "operations": ["G96:0"]}}
    result = replay_claims(
        [{"rule_id": "G96", "target_id": "T0", "location": "p0", "start": 8,
          "end": 8, "replacement": "新增乙。", "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G96": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_EFFECT_MISSING" in codes


def test_one_of_alternative_removal_is_authorized_by_its_own_ledger_record():
    ledger = Ledger({"G95:0": Record("G95:0", "G95:B1:O1", 0)})
    ledger._records["G95:0"].spec.one_of_group = "variant"
    ledger._records["G95:0"].spec.alternatives = ("旧说法乙。",)
    rule = {"rule_id": "G95",
            "operations": [{"op": "replace", "old_text": "旧说法甲。",
                            "new_text": "新说法。"},
                           {"op": "append", "old_text": "", "new_text": "其他新增。"}],
            "old_text_variants": []}
    before = "旧说法乙。"
    after = "新说法。"
    targets = {"T0": {"target_id": "T0", "operations": ["G95:0"]}}
    result = replay_claims(
        [{"rule_id": "G95", "target_id": "T0", "location": "p0", "start": 0,
          "end": len(before), "replacement": after, "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G95": rule}, targets_by_id=targets, obligations=ledger)
    assert result["verified"] is True, result["failures"]


def test_composed_rewording_is_not_rejected_by_exact_guide_wording():
    rule = {"rule_id": "G94",
            "operations": [{"op": "replace", "old_text": "赎回费率结构如下。",
                            "new_text": "赎回费率按持有期限分档。"},
                           {"op": "append", "old_text": "", "new_text": "其他补充。"}],
            "old_text_variants": []}
    before = "赎回费率结构如下。"
    after = "本基金赎回费率按份额持有时间分档设置。"
    targets = {"T0": {"target_id": "T0", "operations": ["G94:0"]}}
    result = replay_claims(
        [{"rule_id": "G94", "target_id": "T0", "location": "p0", "start": 0,
          "end": len(before), "replacement": after, "content_source": "composed",
          "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G94": rule}, targets_by_id=targets)
    assert result["verified"] is True, result["failures"]


def test_unknown_validator_is_not_a_claim_pass(monkeypatch):
    """Validator uncertainty must remain open at the artifact boundary."""
    from fundlex.generation import validators

    class Unknown:
        verdict = "UNKNOWN"
        findings = ()
        changes = ()

        def as_dict(self):
            return {"verdict": "UNKNOWN", "findings": [], "changes": []}

    monkeypatch.setattr(validators, "validate_edit", lambda *args, **kwargs: Unknown())
    result = _replay([_edit("T1", 8, 8, "新增乙。")],
                     "旧句甲。保留句。", "旧句甲。保留句。新增乙。")
    assert result["verified"] is False
    assert any(item["code"] == "CLAIM_VALIDATION_UNKNOWN"
               for item in result["failures"])


def test_duplicate_unidentified_sites_fail_closed():
    """Two same-operation targets at one location need occurrence identity."""
    targets = {
        "T0": {"target_id": "T0", "operations": ["G99:1"], "quote": "保留句。"},
        "T1": {"target_id": "T1", "operations": ["G99:1"], "quote": "保留句。"},
    }
    result = _replay(
        [{"rule_id": "G99", "target_id": "T0", "location": "p0",
          "start": 8, "end": 8, "replacement": "新增乙。", "components": []}],
        "旧句甲。保留句。", "旧句甲。保留句。新增乙。", targets=targets)
    assert result["verified"] is False
    assert any(item["code"] == "CLAIM_SITE_OCCURRENCE_UNRESOLVED"
               for item in result["failures"])


def test_duplicate_occurrence_identity_fails_closed():
    targets = {
        "T0": {"target_id": "T0", "operations": ["G99:1"],
               "occurrence_index": 0},
        "T1": {"target_id": "T1", "operations": ["G99:1"],
               "occurrence_index": 0},
    }
    result = _replay(
        [{"rule_id": "G99", "target_id": "T0", "location": "p0",
          "start": 8, "end": 8, "replacement": "新增乙。", "components": []}],
        "旧句甲。保留句。", "旧句甲。保留句。新增乙。", targets=targets)
    assert result["verified"] is False
    assert any(item["code"] == "CLAIM_SITE_OCCURRENCE_UNRESOLVED"
               for item in result["failures"])


def test_same_operation_at_distinct_locations_does_not_need_occurrence_identity():
    rule = {"rule_id": "G95", "operations": [
        {"op": "append", "old_text": "", "new_text": "新增乙。"},
    ], "old_text_variants": []}
    targets = {
        "T0": {"target_id": "T0", "location": "p0", "operations": ["G95:0"]},
        "T1": {"target_id": "T1", "location": "p1", "operations": ["G95:0"]},
    }
    edits = [
        {"rule_id": "G95", "target_id": "T0", "location": "p0",
         "start": 4, "end": 4, "replacement": "新增乙。", "components": []},
        {"rule_id": "G95", "target_id": "T1", "location": "p1",
         "start": 4, "end": 4, "replacement": "新增乙。", "components": []},
    ]
    result = replay_claims(
        edits, Inspection(["保留句。", "保留句。"]),
        Inspection(["保留句。新增乙。", "保留句。新增乙。"]),
        rules_by_id={"G95": rule}, targets_by_id=targets)
    assert result["verified"] is True, result["failures"]


def test_one_of_alternative_branch_can_close_when_sibling_was_applied():
    rule = {"rule_id": "G95", "operations": [
        {"op": "replace", "old_text": "旧说法甲。", "new_text": "新说法。"},
        {"op": "replace", "old_text": "旧说法乙。", "new_text": "新说法。"},
    ], "old_text_variants": []}
    first = Record("G95:0", "G95:B1:O1", 0)
    second = Record("G95:1", "G95:B1:O2", 1)
    first.spec.one_of_group = second.spec.one_of_group = "G95:history"
    ledger = Ledger({"G95:0": first, "G95:1": second})
    result = replay_claims(
        [{"rule_id": "G95", "target_id": "T0", "location": "p0",
          "start": 0, "end": len("旧说法甲。"), "replacement": "新说法。",
          "components": []}],
        Inspection(["旧说法甲。"]), Inspection(["新说法。"]),
        rules_by_id={"G95": rule},
        targets_by_id={"T0": {"target_id": "T0", "operations": ["G95:0"]}},
        obligations=ledger)
    assert result["verified"] is True, result["failures"]
    assert result["obligations"]["G95:B1:O2"]["state"] == "PASS"
    assert result["obligations"]["G95:B1:O2"]["artifact_status"] in {
        "ALREADY_SATISFIED", "NOT_REQUIRED"}


def test_inapplicable_operation_cannot_claim_an_artifact_edit():
    rule = {"rule_id": "G95", "operations": [
        {"op": "append", "old_text": "", "new_text": "新增乙。"},
    ], "old_text_variants": []}
    record = Record("G95:0", "G95:B1:O1", 0)
    record.spec.op = "append"
    record.spec.old_text = ""
    record.spec.new_text = "新增乙。"
    record.applicability = SimpleNamespace(status="FALSE")
    ledger = Ledger({"G95:0": record})
    result = replay_claims(
        [{"rule_id": "G95", "target_id": "T0", "location": "p0",
          "start": 4, "end": 4, "replacement": "新增乙。", "components": []}],
        Inspection(["保留句。"]), Inspection(["保留句。新增乙。"]),
        rules_by_id={"G95": rule},
        targets_by_id={"T0": {"target_id": "T0", "operations": ["G95:0"]}},
        obligations=ledger)
    assert result["verified"] is False
    assert any(item["code"] == "CLAIM_OPERATION_NOT_APPLICABLE"
               for item in result["failures"])


def test_protected_literal_tampering_does_not_pass_operation_claim():
    rule = {"rule_id": "G93", "operations": [
        {"op": "replace", "old_text": "按月支付0.40%销售服务费。",
         "new_text": "按月支付0.50%销售服务费。"}]}
    targets = {"T0": {"target_id": "T0", "operations": ["G93:0"]}}
    before = "按月支付0.40%销售服务费。"
    after = "按月支付0.60%销售服务费。"
    result = replay_claims(
        [{"rule_id": "G93", "target_id": "T0", "location": "p0",
          "start": 0, "end": len(before), "replacement": after, "components": []}],
        Inspection([before]), Inspection([after]), rules_by_id={"G93": rule},
        targets_by_id=targets)
    assert result["verified"] is False
    assert any(item["code"] == "CLAIM_VALIDATION_FAILED"
               for item in result["failures"])


def test_single_operation_replace_cannot_delete_a_sibling_sentence():
    rule = {"rule_id": "G93",
            "operations": [{"op": "replace", "old_text": "保留句。",
                            "new_text": "新句乙。"}],
            "old_text_variants": []}
    before = "旧句甲。保留句。"
    after = "新句乙。"
    targets = {"T0": {"target_id": "T0", "operations": ["G93:0"]}}
    result = replay_claims(
        [{"rule_id": "G93", "target_id": "T0", "location": "p0", "start": 0,
          "end": 8, "replacement": after, "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G93": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_SPAN_UNAUTHORIZED" in codes


def test_single_operation_delete_cannot_take_the_whole_paragraph():
    rule = {"rule_id": "G92",
            "operations": [{"op": "delete", "old_text": "旧句甲。", "new_text": ""}],
            "old_text_variants": []}
    before = "旧句甲。保留句。"
    targets = {"T0": {"target_id": "T0", "operations": ["G92:0"]}}
    result = replay_claims(
        [{"rule_id": "G92", "target_id": "T0", "location": "p0", "start": 0,
          "end": 8, "replacement": "", "components": []}],
        Inspection([before]), Inspection([""]),
        rules_by_id={"G92": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_SPAN_UNAUTHORIZED" in codes


def test_character_level_alignment_cannot_hide_a_sibling_sentence():
    rule = {"rule_id": "G98",
            "operations": [{"op": "delete", "old_text": "旧句甲。", "new_text": ""},
                           {"op": "replace", "old_text": "保留句。",
                            "new_text": "新句乙。"}],
            "old_text_variants": []}
    before = "旧句甲。保留句。"
    after = "新句乙。"
    targets = {"T1": {"target_id": "T1", "operations": ["G98:1"]}}
    result = replay_claims(
        [{"rule_id": "G98", "target_id": "T1", "location": "p0", "start": 0,
          "end": 8, "replacement": after, "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_SPAN_UNAUTHORIZED" in codes


def test_joint_result_cannot_insert_unexplained_text_inside_the_union():
    rule = {"rule_id": "G98",
            "operations": [{"op": "replace", "old_text": "甲乙丙",
                            "new_text": "甲乙丙A"},
                           {"op": "replace", "old_text": "丙丁戊",
                            "new_text": "丁戊B"}],
            "old_text_variants": []}
    before = "甲乙丙丁戊"
    after = "甲乙丙A额外丁戊B"
    targets = {"T0": {"target_id": "T0", "operations": ["G98:0"]},
               "T1": {"target_id": "T1", "operations": ["G98:1"]}}
    edits = [{"rule_id": "G98", "target_id": "T0", "location": "p0", "start": 0,
              "end": 3, "replacement": "甲乙丙A", "components": []},
             {"rule_id": "G98", "target_id": "T1", "location": "p0", "start": 2,
              "end": 5, "replacement": "丁戊B", "components": []}]
    result = replay_claims(edits, Inspection([before]), Inspection([after]),
                           rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_JOINT_UNEXPLAINED_TEXT" in codes


def test_joint_result_must_preserve_gaps_between_disjoint_spans():
    rule = {"rule_id": "G98",
            "operations": [{"op": "replace", "old_text": "甲乙丙",
                            "new_text": "甲乙丙A"},
                           {"op": "replace", "old_text": "丙丁", "new_text": "丁B"}],
            "old_text_variants": []}
    before = "甲乙丙丁戊己庚辛壬癸"
    after = "甲乙丙A丁B未申酉戌"
    targets = {"T0": {"target_id": "T0", "operations": ["G98:0"]},
               "T1": {"target_id": "T1", "operations": ["G98:1"]},
               "T2": {"target_id": "T2", "operations": ["G98:0"]}}
    edits = [{"rule_id": "G98", "target_id": "T0", "location": "p0", "start": 0,
              "end": 3, "replacement": "甲乙丙A", "components": []},
             {"rule_id": "G98", "target_id": "T1", "location": "p0", "start": 1,
              "end": 4, "replacement": "丁B", "components": []},
             {"rule_id": "G98", "target_id": "T2", "location": "p0", "start": 8,
              "end": 10, "replacement": "戌", "components": []}]
    result = replay_claims(edits, Inspection([before]), Inspection([after]),
                           rules_by_id={"G98": rule}, targets_by_id=targets)
    assert result["verified"] is False
    # The mutated gap is rejected; diff alignment may report it as a changed gap or
    # as unexplained text introduced inside the union.
    assert result["failures"]


def test_artifact_proof_rejects_an_unplanned_sibling_operation():
    class Spec(SimpleNamespace):
        pass

    class Record:
        def __init__(self, index, op, old_text, new_text):
            self.obligation_id = f"G96:B1:O{index + 1}"
            self.spec = SimpleNamespace(
                rule_id="G96", operation_id=f"G96:{index}", operation_index=index,
                op=op, old_text=old_text, new_text=new_text, one_of_group="",
                alternatives=())
            self.applicability = SimpleNamespace(status="TRUE")

    class Ledger:
        def __init__(self, records):
            self.records = records

        def record(self, key):
            for item in self.records:
                if item.spec.operation_id == str(key):
                    return item
            return None

    rule = {"rule_id": "G96",
            "operations": [{"op": "replace", "old_text": "旧说法。",
                            "new_text": "新说法。"},
                           {"op": "delete", "old_text": "备案句。", "new_text": ""}],
            "old_text_variants": []}
    ledger = Ledger([Record(0, "replace", "旧说法。", "新说法。"),
                     Record(1, "delete", "备案句。", "")])
    before = "旧说法。备案句。"
    after = "新说法。备案句。"
    result = replay_claims(
        [{"rule_id": "G96", "target_id": "T0", "location": "p0", "start": 0,
          "end": len("旧说法。"), "replacement": "新说法。", "components": []}],
        Inspection([before]), Inspection([after]),
        rules_by_id={"G96": rule}, targets_by_id={
            "T0": {"target_id": "T0", "operations": ["G96:0"]}},
        obligations=ledger)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OPERATION_UNPROVEN" in codes
