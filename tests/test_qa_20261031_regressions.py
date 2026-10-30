"""Regression tests for the 2026-10-31 full-project QA sweep.

Covers: A7-01 (G16 unbound rule), A7-02 (frozen paging input for residual
delete targets), A7-03 (NFKC expansion index drift), A8-F1 (engine build
module list) and A8-F2 (orphan evidence must block delivery).
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.delivery import requires_blocker
from fundlex.docx import TextSegment
from fundlex.recall import (Facts, Target, assign_target_operations,
                            ensure_delete_targets, find_normalized)
from fundlex import store as store_module


class Inspection:
    def __init__(self, texts):
        self.paragraphs = tuple(
            SimpleNamespace(location=f"p{i}", text=text, zone="body",
                            logical_zone="body", section_path="",
                            segments=(TextSegment(0, len(text)),),
                            fingerprint=f"p{i}")
            for i, text in enumerate(texts))
        self.source_sha256 = "source"

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _facts() -> Facts:
    return Facts("普通开放式基金", "", "", (), False, "", "", "", {}, ())


# --- A7-01 -----------------------------------------------------------------

def test_g16_satisfied_out_of_scope_first_target_no_unbound_rule():
    """A satisfied+out_of_scope G16 first target must not raise NameError."""
    target = Target("T001", "G16", "p10", "直销机构 其他销售机构", "satisfied",
                    "survey", start=0, end=10, operations=("G16:0",),
                    resolution="resolved", segment_ok=True)
    target.out_of_scope = True
    rules = {"G16": {"rule_id": "G16",
                     "operations": [{"op": "replace", "old_text": "x",
                                     "new_text": "直销机构 其他销售机构"}]}}
    errors = assign_target_operations([target], rules, Inspection(["x"]), _facts())
    assert isinstance(errors, list)


# --- A7-02 -----------------------------------------------------------------

def test_ensure_delete_targets_frozen_paging_input_covers_all_pages():
    sentence = "本基金对持续持有期少于7日的投资者收取不低于1.5%的短期赎回费。"
    texts = [sentence + f"（副本{i}）" for i in range(60)]
    inspection = Inspection(texts)
    rule = {"rule_id": "G13",
            "operations": [{"op": "delete", "old_text": sentence}]}
    base_targets: list[Target] = []
    created: list[Target] = []
    cursor = 0
    # Mirror the pipeline caller contract: the paging input is a frozen
    # snapshot; newly created clones are collected separately (A7-02 fix).
    paging_base = list(base_targets)
    for _ in range(10):
        info: dict = {}
        page = ensure_delete_targets(paging_base, {"G13": rule}, inspection,
                                     limit=20, cursor=cursor, page_info=info)
        created.extend(page)
        base_targets.extend(page)
        if not info.get("has_more"):
            break
        cursor = int(info["next_cursor"])
    locations = {item.location for item in created}
    assert len(locations) == 60, (len(locations), sorted(locations)[:5])


# --- A7-03 -----------------------------------------------------------------

def test_find_normalized_nfkc_length_expansion_offsets():
    # "㏄" folds to two NFKC characters; offsets must still map exactly to the
    # original span (pre-fix this raised IndexError or mislocated the span).
    haystack = "面积为5㏄的容器，见附件。"
    needle = "5㏄的容器"
    located = find_normalized(haystack, needle)
    assert located is not None
    start, end = located
    assert haystack[start:end] == needle


# --- A8-F1 -----------------------------------------------------------------

def test_engine_build_modules_include_semantic_contract():
    assert "fundlex/semantic_contract.py" in store_module._ENGINE_BUILD_MODULES


# --- A8-F2 -----------------------------------------------------------------

def test_orphan_evidence_requires_blocker():
    item = {"kind": "orphan_evidence", "code": "LEDGER_EVIDENCE_UNBOUND",
            "rule_id": "G05", "location": "p12"}
    assert requires_blocker(item) is True
