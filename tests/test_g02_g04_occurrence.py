"""G02/G04 same-paragraph occurrence safety (external review 2026-10-20 P1).

Two identical class tokens in one paragraph must not be collapsed to the first match:
the target carries the occurrence index and the inventory quote that identifies it, and
claim replay rejects an edit that lands on a different occurrence.
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.generation.claim_replay import replay_claims
from fundlex.recall import resolve_occurrence

BEFORE = ("A类基金份额用于描述基金代码。对于收取申购费且不计提销售服务费的"
          "A类基金份额，基金管理人应当披露费率。")
SECOND_SENTENCE = ("对于收取申购费且不计提销售服务费的"
                   "A类基金份额，基金管理人应当披露费率。")
SECOND = BEFORE.index(SECOND_SENTENCE) + SECOND_SENTENCE.index("A类基金份额")
FIRST = BEFORE.index("A类基金份额")

RULE = {"rule_id": "G02", "class_substitution": True, "title": "份额类别",
        "operations": [
            {"op": "replace", "old_text": "A类基金份额",
             "new_text": "C类基金份额", "condition": {"kind": "none"}},
            {"op": "replace", "old_text": "C类基金份额",
             "new_text": "A类基金份额", "condition": {"kind": "none"}},
        ], "old_text_variants": []}


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{index}", text=text)
                           for index, text in enumerate(texts)]

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


def _after(change_at: int) -> str:
    return BEFORE[:change_at] + "C类基金份额" + BEFORE[change_at + len("A类基金份额"):]


TARGETS = {"T1": {"target_id": "T1", "operations": ["G02:0"],
                  "occurrence_index": 1, "occurrence_anchor": SECOND_SENTENCE}}


def _edit(start: int) -> dict:
    return {"rule_id": "G02", "target_id": "T1", "location": "p0",
            "start": start, "end": start + len("A类基金份额"),
            "replacement": "C类基金份额", "components": []}


def test_resolve_occurrence_uses_the_target_quote_context():
    span = SimpleNamespace(text=BEFORE)
    assert resolve_occurrence(span, "A类基金份额", anchor=SECOND_SENTENCE) == (
        SECOND, SECOND + len("A类基金份额"))


def test_resolve_occurrence_refuses_to_guess_without_context():
    span = SimpleNamespace(text=BEFORE)
    assert resolve_occurrence(span, "A类基金份额", anchor="A类基金份额") is None


def test_authorized_second_occurrence_changes_and_first_stays_untouched():
    result = replay_claims([_edit(SECOND)], Inspection([BEFORE]),
                           Inspection([_after(SECOND)]), rules_by_id={"G02": RULE},
                           targets_by_id=TARGETS)
    assert result["verified"] is True, result["failures"]
    # Only the authorized occurrence changed; the identical first token is intact.
    assert _after(SECOND).find("A类基金份额") == FIRST


def test_edit_on_the_other_occurrence_fails_claim_replay():
    # The artifact did change a class token, but the wrong occurrence of the paragraph.
    result = replay_claims([_edit(FIRST)], Inspection([BEFORE]),
                           Inspection([_after(FIRST)]), rules_by_id={"G02": RULE},
                           targets_by_id=TARGETS)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OCCURRENCE_MISMATCH" in codes


def test_paragraph_scoped_edit_cannot_prove_which_occurrence_changed():
    # A whole-paragraph span covers both tokens, so it cannot prove the authorized
    # occurrence was the one changed; claim replay must fail closed.
    result = replay_claims([_edit(0) | {"end": len(BEFORE)}], Inspection([BEFORE]),
                           Inspection([_after(FIRST)]), rules_by_id={"G02": RULE},
                           targets_by_id=TARGETS)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OCCURRENCE_MISMATCH" in codes


def test_authorized_occurrence_leaves_a_decoy_paragraph_untouched():
    decoy = "另一段完全无关的费率说明。"
    result = replay_claims([_edit(SECOND)], Inspection([BEFORE, decoy]),
                           Inspection([_after(SECOND), decoy]),
                           rules_by_id={"G02": RULE}, targets_by_id=TARGETS)
    assert result["verified"] is True, result["failures"]
    # The first identical token and the decoy paragraph are byte-identical.
    assert _after(SECOND)[:len("A类基金份额")] == "A类基金份额"
    assert result["failures"] == []


def test_occurrence_index_zero_is_verified_not_treated_as_missing():
    targets = {"T1": {"target_id": "T1", "operations": ["G02:0"],
                      "occurrence_index": 0, "occurrence_anchor": SECOND_SENTENCE}}
    result = replay_claims([_edit(FIRST)], Inspection([BEFORE]),
                           Inspection([_after(FIRST)]), rules_by_id={"G02": RULE},
                           targets_by_id=targets)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "CLAIM_OCCURRENCE_MISMATCH" in codes


def test_g02_site_guard_rejects_a_holder_rights_sentence():
    from fundlex.docx import ParagraphSpan, TextSegment
    from fundlex.recall import target_site_ok

    text = "本基金A类基金份额持有人享有表决权。"
    span = ParagraphSpan(location="p0", zone="body", section_path="", text=text,
                         segments=(TextSegment(0, len(text)),), fingerprint="fp")
    inspection = Inspection([text])
    assert target_site_ok("G02", span, inspection) is False


def test_resolve_occurrence_handles_real_docx_spaces_between_class_and_cjk():
    spaced = ("A 类基金份额用于描述基金代码。对于收取申购费且不计提销售服务费的"
              "A 类基金份额，基金管理人应当披露费率。")
    second = spaced.index("对于收取申购费")
    anchor = spaced[second:]
    span = SimpleNamespace(text=spaced)
    resolved = resolve_occurrence(span, "A类基金份额", anchor=anchor)
    assert resolved is not None
    assert resolved[0] > spaced.index("A 类基金份额")
    assert "A 类基金份额" in spaced[resolved[0]:resolved[1]]
