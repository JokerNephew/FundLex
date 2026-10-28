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
    # A DOCX paragraph break is a source boundary, not whitespace that may be
    # skipped.  The model may quote one continuous clause split over adjacent
    # paragraphs, so search only contiguous paragraph windows.  This keeps a
    # cross-paragraph quote source-bound while rejecting a quote assembled from
    # unrelated sections (FL-D251).
    matches: list[str] = []
    for start in range(len(paragraphs)):
        joined = ""
        for end in range(start, len(paragraphs)):
            joined += paragraphs[end]
            if text in joined:
                matches.append(joined)
                break
            if len(joined) >= len(text):
                break
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
        if not complete and number is None and all(name in text for name in expected):
            # An exhaustive enumeration of every full display name is complete
            # even without an explicit "四种" count.  The truncation check above
            # already rejected a sentence that names an additional class.
            complete = True
        # Currency variants are sub-classes of the same fee group: a contract
        # that enumerates "A类、C类和E类三种" is complete for A类人民币、
        # A类美元现汇、C类、E类 (道琼斯).
        base = {name[0] for name in expected
                if re.fullmatch(r"[A-Z]类.*", name)}
        if (not complete and number is not None and base
                and labels == base and number == len(base)):
            complete = True
    result.update(set_complete_verified=complete,
                  reason="CLASS_SET_VERIFIED" if complete else "CLASS_SET_MISMATCH")
    return result
