"""A paragraph that ends without the guide's final stop is still complete."""
from __future__ import annotations

from fundlex.recall import fuzzy_span_clause


OLD = ("赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
       "赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示。")
ACTUAL = OLD[:-1]  # source paragraph ends without the final stop


def test_unterminated_paragraph_keeps_the_whole_clause():
    start, end, _ratio = fuzzy_span_clause(ACTUAL, OLD)
    assert (start, end) == (0, len(ACTUAL))


def test_a_partial_tail_is_still_trimmed_to_the_last_sentence():
    text = "本基金赎回费用由基金份额持有人承担。赎回费用全额计入基金财产。剩余费用归基金财产"
    start, end, _ratio = fuzzy_span_clause(text, text + "。")
    assert (start, end) == (0, len(text))
