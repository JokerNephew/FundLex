"""T3 model locator: model proposes, code binds (plan §11)."""
from __future__ import annotations

from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.model import ModelResult
from fundlex.recall import Target
from fundlex.targeting import locate_unresolved_targets

from test_recall_core import CLASS_DEFINITION, build_contract


class Facts:
    def as_ledger(self):
        return {"classes": ["A", "C", "D"]}


class Gateway:
    def __init__(self, value):
        self.value = value
        self.calls = []
        self.max_context_chars = 60000

    def call(self, *, task_type, bounded_context, response_schema, instruction,
             prompt_version="v1"):
        self.calls.append(task_type)
        return ModelResult(self.value, "stub", 1, 1, 1, 2, None, 1, task_type=task_type)


def rule():
    return {"rule_id": "G02", "title": "class definition", "section_hint": "释义",
            "requirement": "replace class groups",
            "operations": [{"op": "replace", "old_text": "A类基金份额",
                            "new_text": "A类、D类基金份额",
                            "condition": {"kind": "none", "value": None}}]}


def unresolved_target():
    target = Target(target_id="T1", rule_id="G02", location="p3",
                    quote="不存在的旧句子", state="needs_edit", reason="inventory miss")
    target.resolution = "quote_not_found"
    return target


def test_model_locator_binds_only_a_verified_quote(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    target = unresolved_target()
    gateway = Gateway({"location": "p4", "quote": CLASS_DEFINITION,
                       "semantic_role": "class_definition", "reason": "definition clause"})
    records = locate_unresolved_targets([target], inspection, {"G02": rule()},
                                        Facts(), gateway)
    assert gateway.calls == ["recall_locate"]
    assert records[0]["status"] == "bound"
    assert target.location == "p4"
    assert target.resolution == "resolved"
    assert target.start is not None and target.end is not None
    assert "locator:class_definition" in target.reason


def test_model_locator_rejects_a_paraphrased_quote(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    target = unresolved_target()
    gateway = Gateway({"location": "p4", "quote": "本基金分为甲类和乙类",
                       "semantic_role": "class_definition", "reason": "guess"})
    records = locate_unresolved_targets([target], inspection, {"G02": rule()},
                                        Facts(), gateway)
    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "quote_not_found"
    assert target.resolution == "quote_not_found"


def test_model_locator_rejects_an_unknown_location(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    target = unresolved_target()
    gateway = Gateway({"location": "p999", "quote": CLASS_DEFINITION,
                       "semantic_role": "class_definition", "reason": "guess"})
    records = locate_unresolved_targets([target], inspection, {"G02": rule()},
                                        Facts(), gateway)
    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] in {"location_not_found",
                                           "location_outside_candidate_window"}


def test_model_locator_rejects_a_real_quote_from_outside_the_candidate_window(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    target = unresolved_target()
    target.location = "p10"
    gateway = Gateway({"location": "p0", "quote": "某某灵活配置混合型证券投资基金基金合同",
                       "semantic_role": "title", "reason": "guess"})
    records = locate_unresolved_targets([target], inspection, {"G02": rule()},
                                        Facts(), gateway)
    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "location_outside_candidate_window"
