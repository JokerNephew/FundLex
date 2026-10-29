"""A single trailing delete must also clean its orphaned connector."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.recall import PlannedEdit, _atomic_paragraph_edits


class _Inspection:
    def __init__(self, text: str):
        self.text = text
        self.paragraphs = [SimpleNamespace(location="p0", text=text)]

    def by_location(self, location: str):
        assert location == "p0"
        return self.paragraphs[0]


def test_single_delete_routes_through_paragraph_compose():
    tail = "其中，本基金对持续持有期少于7日的投资者收取1.50%的赎回费。"
    head = "5、赎回费用由赎回基金份额的基金份额持有人承担。"
    text = head + tail
    start = len(head) + len("其中，")
    edit = PlannedEdit(
        target_id="T1", rule_id="G13", location="p0", start=start, end=len(text),
        replacement="", operation="replace", content_source="fragment_delete",
        evidence={"fragments": [{"op": "delete", "old_text": text[start:],
                                 "new_text": "", "mode": "full"}]},
        operation_keys=("G13:0",))
    result = _atomic_paragraph_edits([edit], _Inspection(text))
    assert len(result) == 1
    atomic = result[0]
    assert atomic.content_source == "atomic_paragraph"
    assert atomic.start == 0 and atomic.end == len(text)
    assert atomic.replacement == head
