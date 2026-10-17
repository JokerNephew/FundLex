"""FL-D108: a sweep answer cut off at the output cap is split, not retried unchanged.

The sweep legitimately returns far more output for a dense stretch of a long contract
than for a clean one (round 9 measured p50 of 146 tokens but a single window that hit the
4000-token cap). The old engine classified that truncation as ``MODEL_SCHEMA_INVALID`` —
a malformed answer — did not retry it, and failed the whole contract (D09,
``PROCESSING_FAILED``). Retrying the identical oversized request would truncate again and
burn budget, so the cure is to shrink the unit of work: split the window in half and
sweep the halves.

These tests pin the three parts of that behaviour:

* ``_split_chunk`` halves a window on whole paragraphs and keeps addresses stable;
* an uncuttable window (one paragraph) is returned unchanged so the caller records a gap;
* ``_sweep_batch`` recovers by splitting when the gateway reports truncation, and still
  propagates unrelated errors untouched.
"""

from __future__ import annotations

import pytest

from fundlex.docx import inspect_docx
from fundlex.model import ModelError
from fundlex.recall import Facts
from fundlex.recall_pipeline import (
    SWEEP_ISSUES,
    _Chunk,
    _split_chunk,
    _sweep_batch,
)


def chunk(locations, *, text=None, filler=0):
    if text is None:
        body = "\n".join(f"[{loc}] 段落{loc}的正文内容{('详' * filler)}" for loc in locations)
    else:
        body = text
    return _Chunk(id="C001", locations=tuple(locations), text=body)


def test_split_chunk_halves_on_paragraphs_and_keeps_addresses():
    window = chunk([f"p{i}" for i in range(1, 7)], filler=60)
    pieces = _split_chunk(window)
    assert len(pieces) == 2
    assert [list(p.locations) for p in pieces] == [["p1", "p2", "p3"], ["p4", "p5", "p6"]]
    # No text is lost across the split.
    assert "\n".join(p.text for p in pieces) == window.text


def test_split_chunk_leaves_single_paragraph_window_unchanged():
    window = chunk(["p1"], filler=600)
    assert _split_chunk(window) == [window]


def test_split_chunk_respects_floor_size():
    window = chunk(["p1", "p2", "p3"])
    # Below the floor the window cannot be meaningfully reduced, so it stays whole.
    assert _split_chunk(window) == [window]


class _Plan:
    """Gateway stub: returns scripted results per call, then repeats the last."""

    def __init__(self, results):
        self.results = list(results)
        self.results_last = None
        self.inputs: list[str] = []
        self.max_context_chars = 100000

    def call(self, *, task_type, bounded_context, response_schema, instruction, prompt_version):
        self.inputs.append(bounded_context)
        if self.results:
            self.results_last = self.results.pop(0)
        if isinstance(self.results_last, BaseException):
            raise self.results_last
        return self.results_last


class _Value:
    def __init__(self, value):
        self.value = value


def _facts():
    return Facts(
        fund_type="open_regular", fund_type_quote="", fund_type_basis="",
        classes=(), floating_management_fee=False, floating_quote="", floating_basis="",
        notes="", quotes_verified={}, problems=(),
    )


def _inspection():
    from docx import Document

    document = Document()

    class _Span:
        def __init__(self, location, text):
            self.location, self.text = location, text
            self.zone = "body"
            self.logical_zone = "body"

    class _Inspection:
        paragraphs = [_Span("p1", "第一段"), _Span("p2", "第二段")]

        def by_location(self, location):
            for span in self.paragraphs:
                if span.location == location:
                    return span
            raise KeyError(location)

        @property
        def source_sha256(self):
            return "0" * 64

    return _Inspection()


def test_sweep_batch_splits_a_truncated_window_instead_of_failing():
    """A truncated answer is retried as two smaller windows and the run continues."""
    truncated = chunk([f"p{i}" for i in range(1, 7)], filler=60)
    empty = _Value({"findings": []})
    gateway = _Plan([ModelError("MODEL_OUTPUT_TRUNCATED"), empty, empty])

    ledger = _sweep_batch(gateway, {}, "REQS", [truncated], _inspection(),
                          round_number=0, counter=[1], facts=_facts())

    # The original window was split into two and both halves were swept.
    assert len(ledger["splits"]) == 1
    assert ledger["calls"] == 2
    assert len(gateway.inputs) == 3  # one truncated attempt + two halves
    # The two follow-up contexts are smaller than the first.
    assert len(gateway.inputs[1]) < len(gateway.inputs[0])


def test_sweep_batch_records_honest_gap_for_uncuttable_window():
    """A single-paragraph window that truncates cannot be split: record it, do not loop."""
    tiny = chunk(["p1"], filler=600)
    gateway = _Plan([ModelError("MODEL_OUTPUT_TRUNCATED")])

    ledger = _sweep_batch(gateway, {}, "REQS", [tiny], _inspection(),
                          round_number=0, counter=[1], facts=_facts())

    assert ledger["truncated"] == [{"chunk": "C001", "locations": ["p1"]}]
    assert ledger["calls"] == 0
    assert len(gateway.inputs) == 1  # attempted exactly once, no retry loop


def test_sweep_batch_propagates_unrelated_errors():
    """Only truncation is recovered here; other model errors must surface unchanged."""
    gateway = _Plan([ModelError("MODEL_HTTP_ERROR")])
    with pytest.raises(ModelError) as excinfo:
        _sweep_batch(gateway, {}, "REQS", [chunk(["p1", "p2"], filler=60)], _inspection(),
                     round_number=0, counter=[1], facts=_facts())
    assert excinfo.value.code == "MODEL_HTTP_ERROR"


def test_sweep_issues_unchanged():
    assert SWEEP_ISSUES == {"residual_old_text", "missing_new_text", "wrong_text",
                            "unaddressed_requirement"}
