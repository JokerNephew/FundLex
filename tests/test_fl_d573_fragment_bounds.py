# -*- coding: utf-8 -*-
"""FL-D573 planning-side fragment narrowing unit coverage (qa-feat-recall review
补强).  The mechanism landed inside ``ac697a4`` without dedicated tests; these
tripwires pin both directions (narrow when safe / refuse when ambiguous)."""
from __future__ import annotations

import importlib


def _module():
    return importlib.import_module("fundlex.recall")


CASE_TEXT = "释义条款中本条所称持有期限政策调整统一处理。"
FRAGMENT = "持有期限政策调整统一处理"


def _op(old_text: str) -> dict:
    return {"old_text": old_text}


def _call(text: str, start: int, end: int, old_text: str):
    return _module()._approved_fragment_bounds(text, start, end, _op(old_text))


def test_narrows_to_owned_fragment_with_unowned_prefix():
    """Unowned head + owned fragment + terminator: delete exactly the fragment,
    the surviving prefix keeps the sentence (FL-D573 tail-swallow guard)."""
    start = CASE_TEXT.index("本条所称")
    end = len(CASE_TEXT)
    bounds = _call(CASE_TEXT, start, end, FRAGMENT)
    assert bounds is not None
    narrowed = CASE_TEXT[bounds[0]:bounds[1]]
    assert narrowed == FRAGMENT
    assert CASE_TEXT[:bounds[0]].endswith("本条所称")


def test_fragment_occurring_twice_refuses_to_narrow():
    text = f"…{FRAGMENT}…甲，{FRAGMENT}…乙。"
    assert _call(text, 0, len(text), FRAGMENT) is None


def test_trailing_continuation_keeps_wider_approved_span():
    """A trailing continuation after the fragment is meaningful content: the
    function must NOT narrow (the wider, model-approved span stays and the
    claim-side residual proof is the backstop, per FL-D573 design)."""
    text = f"前缀内容，{FRAGMENT}，并列继续的实质内容。"
    assert _call(text, 0, len(text), FRAGMENT) is None


def test_no_unowned_prefix_refuses_to_narrow():
    text = f"{FRAGMENT}，经与基金托管人协商一致后提前公告。"
    assert _call(text, 0, len(text), FRAGMENT) is None


def test_absent_or_empty_old_text_refuses_to_narrow():
    assert _call(CASE_TEXT, 0, len(CASE_TEXT), "") is None
    assert _call(CASE_TEXT, 0, len(CASE_TEXT), "文档中不存在的句子") is None


def test_meaningful_fragment_only_counts_real_words():
    mod = _module()
    assert not mod._meaningful_fragment("，；。：、  ")
    assert mod._meaningful_fragment("收费")
