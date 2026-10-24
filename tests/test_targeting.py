"""T3 model locator: model proposes, code binds (plan §11)."""
from __future__ import annotations

from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.model import ModelResult
from fundlex.recall import Target
from fundlex.recall import duplicate_copy_targets
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


def test_duplicate_copy_preserves_the_authorized_occurrence(tmp_path: Path):
    """An indexed second occurrence stays second in an identical section copy."""
    from types import SimpleNamespace

    old = "A类基金份额"
    first = "本段先说明代码。" + old
    second = "随后再次说明费率。" + old
    text = first + second
    span = lambda location: SimpleNamespace(
        location=location, text=text,
        segments=(SimpleNamespace(start=0, end=len(text)),))
    inspection = SimpleNamespace(
        paragraphs=[span("p0"), span("p1")],
        by_location=lambda location: next(
            span for span in inspection.paragraphs if span.location == location),
    )
    target = Target(
        target_id="T1", rule_id="G02", location="p0", quote=second,
        state="needs_edit", reason="indexed occurrence", start=text.index(old, len(first)),
        end=text.index(old, len(first)) + len(old), resolution="resolved",
        operations=("G02:0",), occurrence_index=1, occurrence_anchor=second)
    rule = {"rule_id": "G02", "class_substitution": True, "operations": [
        {"op": "replace", "old_text": old, "new_text": "C类基金份额"}
    ]}

    clones = duplicate_copy_targets([target], {"G02": rule}, inspection)

    assert len(clones) == 1
    clone = clones[0]
    assert clone.location == "p1"
    assert clone.occurrence_index == 1
    assert clone.occurrence_anchor == second
    assert clone.start == text.index(old, len(first))
    assert clone.end == clone.start + len(old)
