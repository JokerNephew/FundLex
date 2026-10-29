"""A trailing deletion must not leave an orphaned connector in the paragraph."""
from __future__ import annotations

from fundlex.generation.atomic import compose_paragraph


def _component(original: str, start: int, end: int, replacement: str) -> dict:
    return {"start": start, "end": end, "replacement": replacement,
            "expected_old_text": original[start:end]}


def test_deleting_a_trailing_where_clause_removes_orphan_connector():
    tail = "其中，本基金对持续持有期少于7日的投资者收取1.50%的赎回费。"
    head = "赎回费用由赎回基金份额的基金份额持有人承担。"
    original = head + tail
    start = len(head) + len("其中，")
    composed = compose_paragraph(original, [
        _component(original, start, len(original), ""),
    ])
    assert composed == head


def test_source_authored_trailing_punctuation_is_not_rewritten():
    original = "本基金赎回费率为0.5%，"
    composed = compose_paragraph(original, [
        _component(original, 0, len("本基金"), "该基金"),
    ])
    assert composed == "该基金赎回费率为0.5%，"
