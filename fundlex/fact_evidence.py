"""Deterministic verification of a class *set*, separate from its members."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence


def _normal(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def class_labels(value: str) -> set[str]:
    text = _normal(value)
    labels = set(re.findall(r"([A-Z])类", text))
    # A、C和E类 / A/C/E类 are common complete enumeration spellings.
    for match in re.finditer(r"([A-Z](?:[、,，/及和与或]+[A-Z])+)(?=类)", text):
        labels.update(re.findall(r"[A-Z]", match.group(1)))
    return labels


def verify_class_set(inspection: Any, classes: Sequence[Any], quote: str) -> dict[str, Any]:
    text = _normal(quote)
    result: dict[str, Any] = {"quote_verified": False, "set_complete_verified": False,
                              "parsed_classes": [], "reason": "CLASS_SET_QUOTE_UNVERIFIED"}
    if not text or re.search(r"…|\.{3}|⋯", text):
        return result
    from .recall import display_text
    paragraphs = [_normal(display_text(str(span.text))[0]) for span in inspection.paragraphs]
    matches = [paragraph for paragraph in paragraphs if text in paragraph]
    if not matches:
        return result
    result["quote_verified"] = True
    if not re.search(r"分为|分设|设置|设立|分成|仅有|一种|单一", text):
        result["reason"] = "CLASS_SET_ENUMERATION_UNPROVEN"
        return result
    labels = class_labels(text)
    current = [_normal(str(item.name)) for item in classes if item.current]
    expected = set(current)
    result["parsed_classes"] = sorted(labels)
    # A truncated literal prefix must not hide the tail of the same enumeration.
    for paragraph in matches:
        for sentence in re.split(r"[。；;！？]", paragraph):
            if text.rstrip("。；;！？") in sentence and class_labels(sentence) - labels:
                result["reason"] = "CLASS_SET_QUOTE_TRUNCATED"
                return result
    if not expected or len(current) != len(expected):
        result["reason"] = "CLASS_SET_EMPTY_OR_DUPLICATE"
        return result
    if all(re.fullmatch(r"[A-Z](?:类(?:(?:基金)?份额)?)?", name) for name in expected):
        expected = {name[0] for name in expected}
        complete = bool(labels) and labels == expected
    else:
        # Currency/descriptive classes require every full display name, and an
        # explicit count. Mere membership cannot establish set completeness.
        counts = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}
        count = re.search(r"([一二两三四五六\d]+)(?:种|个|类)(?:不同)?(?:的)?(?:份额)?类别", text)
        number = (int(count[1]) if count and count[1].isdigit()
                  else counts.get(count[1]) if count else None)
        complete = number == len(expected) and all(name in text for name in expected)
    result.update(set_complete_verified=complete,
                  reason="CLASS_SET_VERIFIED" if complete else "CLASS_SET_MISMATCH")
    return result
