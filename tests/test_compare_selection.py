import pytest

from fundlex.compare import (
    SelectionError,
    assess_selection,
    binding_hash,
    decision_hash,
    diff_text,
    make_snapshot,
    normalize_decisions,
    require_generation_ready,
)
from fundlex.compare.models import DiffItem, TextSpan


def diff_result(left="旧文本", right="新文本"):
    return diff_text(left, right)


def test_initial_state_is_pending_and_generation_is_blocked():
    diffs = diff_result()
    state = assess_selection(diffs)
    assert state.pending_ids == ("D0001",)
    assert state.counts == {"pending": 1, "left": 0, "right": 0}
    assert not state.can_generate
    with pytest.raises(SelectionError, match="PENDING_SELECTIONS"):
        require_generation_ready(diffs)


def test_explicit_left_and_right_selection_has_deterministic_hashes():
    diffs = diff_result()
    left = assess_selection(diffs, {"D0001": "left"})
    right = assess_selection(diffs, [("D0001", "right")])
    assert left.can_generate and right.can_generate
    assert left.decision_map == {"D0001": "left"}
    assert right.decision_map == {"D0001": "right"}
    assert decision_hash({"D0001": "left", "D0002": "right"}) == decision_hash(
        [("D0002", "right"), ("D0001", "left")])
    assert binding_hash(result_sha256="r", left_source_sha256="l", right_source_sha256="q",
                        selection_epoch=1, decisions={"D0001": "left"}) != binding_hash(
        result_sha256="r", left_source_sha256="l", right_source_sha256="q",
        selection_epoch=2, decisions={"D0001": "left"})


@pytest.mark.parametrize("decision", [
    {"UNKNOWN": "left"},
    {"D0001": "maybe"},
])
def test_unknown_or_invalid_decisions_fail_closed(decision):
    with pytest.raises(SelectionError) as error:
        normalize_decisions(diff_result(), decision)
    assert error.value.code in {"UNKNOWN_DIFF_ID", "INVALID_DECISIONS"}


def test_duplicate_and_conflicting_decisions_are_rejected():
    diffs = diff_result()
    with pytest.raises(SelectionError, match="DUPLICATE_DECISION"):
        normalize_decisions(diffs, [("D0001", "left"), ("D0001", "left")])
    with pytest.raises(SelectionError, match="CONFLICTING_DECISION"):
        normalize_decisions(diffs, [("D0001", "left"), ("D0001", "right")])


def test_insert_and_delete_keep_the_empty_side_semantics():
    insert = diff_result("共同前文", "共同前文新增")
    delete = diff_result("共同前文新增", "共同前文")
    assert {item.type for item in insert} == {"insert"}
    assert {item.type for item in delete} == {"delete"}
    assert assess_selection(insert, {"D0001": "left"}).can_generate
    assert assess_selection(insert, {"D0001": "right"}).can_generate
    assert assess_selection(delete, {"D0001": "left"}).can_generate
    assert assess_selection(delete, {"D0001": "right"}).can_generate


def test_overlapping_result_is_reported_as_structural_blocker():
    first = DiffItem("D0001", "modify", TextSpan("b", 0, 3, "abc"),
                     TextSpan("r", 0, 3, "xyz"), left_spans=(TextSpan("b", 0, 3, "abc"),),
                     right_spans=(TextSpan("r", 0, 3, "xyz"),))
    second = DiffItem("D0002", "modify", TextSpan("b", 2, 5, "cde"),
                      TextSpan("r", 2, 5, "z12"), left_spans=(TextSpan("b", 2, 5, "cde"),),
                      right_spans=(TextSpan("r", 2, 5, "z12"),))
    state = assess_selection((first, second), {"D0001": "left", "D0002": "right"})
    assert not state.can_generate
    assert any(issue.code == "OVERLAPPING_DIFFS" for issue in state.issues)
    with pytest.raises(SelectionError, match="SELECTION_UNSUPPORTED"):
        require_generation_ready((first, second), {"D0001": "left", "D0002": "right"})


def test_cross_block_diff_is_one_decision_and_writer_eligible():
    item = DiffItem(
        "D0001", "modify",
        TextSpan("b1", 0, 1, "甲"), TextSpan("r1", 0, 1, "乙"),
        left_spans=(TextSpan("b1", 0, 1, "甲"), TextSpan("b2", 0, 1, "丙")),
        right_spans=(TextSpan("r1", 0, 1, "乙"), TextSpan("r2", 0, 1, "丁")),
    )
    state = assess_selection((item,), {"D0001": "right"})
    assert state.decision_map == {"D0001": "right"}
    issue = next(issue for issue in state.issues if issue.code == "MULTI_BLOCK_DIFF")
    assert issue.blocking is False
    # The writer owns the structural decision now; preview must not reject a
    # possible paragraph split/merge before it can inspect the DOCX.
    assert require_generation_ready((item,), {"D0001": "right"}).decision_map == {"D0001": "right"}


def test_snapshot_binds_sources_result_and_epoch():
    result = {
        "left": {"sha256": "left-hash"}, "right": {"sha256": "right-hash"},
        "diffs": [d.to_dict() for d in diff_result()],
    }
    snapshot = make_snapshot(result, {"D0001": "right"}, selection_epoch=4, result_sha256="result-hash")
    assert snapshot.selection_epoch == 4
    assert snapshot.result_sha256 == "result-hash"
    assert snapshot.left_source_sha256 == "left-hash"
    assert snapshot.right_source_sha256 == "right-hash"
    assert snapshot.decision_hash
    assert snapshot.binding_hash
