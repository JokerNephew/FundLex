from dataclasses import replace

import pytest

from fundlex.docx import ParagraphSpan, TextSegment
from fundlex.qualification_evidence import (
    QualificationEvidenceError, basic_spans, category_value, investment_spans,
)


def span(text, *, section="", zone="body", reasons=(), logical_zone=None):
    return ParagraphSpan("p" + str(len(text)), zone, section, text,
                         (TextSegment(0, len(text)),), "fixture",
                         reasons=reasons, logical_zone=logical_zone)


@pytest.mark.parametrize("heading,value", [
    ("第三部分 基金的基本情况", "(二) 基金的类别   混合型"),
    ("2.3 基金的基本情况", "基金的类别 股票型证券投资基金"),
    ("四、基金的基本情况", "基金的类型：债券型证券投资基金"),
])
def test_unseen_body_heading_and_literal_category(heading, value):
    paragraphs = (span(heading), span(value))
    quote, source, index = category_value(paragraphs)
    assert quote in source.text and index == 1
    assert quote.strip() in {"混合型", "股票型证券投资基金", "债券型证券投资基金"}


def test_adjacent_bare_value_preserves_spaces_and_coordinates():
    paragraphs = (span("第五章基金的基本情况"), span("基金的类别"),
                  span(""), span(" 债券型 证券投资基金 "))
    quote, source, index = category_value(paragraphs)
    assert quote == "债券型 证券投资基金"
    assert source is paragraphs[3] and index == 1


def test_category_conflict_is_rejected():
    paragraphs = (span("三、基金的基本情况"), span("基金的类别：混合型"),
                  span("基金的类型：货币市场基金"))
    with pytest.raises(QualificationEvidenceError) as error:
        category_value(paragraphs)
    assert error.value.code == "FUND_TYPE_EVIDENCE_CONFLICT"


@pytest.mark.parametrize("unsafe", [
    span("基金的类别：货币市场基金", zone="summary"),
    span("基金的类别：货币市场基金", zone="toc"),
    span("基金的类别：货币市场基金", reasons=("revision_content",)),
    span("基金的类别：货币市场基金", logical_zone="toc"),
    replace(span("基金的类别：货币市场基金"), segments=()),
])
def test_protected_category_never_provides_evidence(unsafe):
    assert category_value((span("三、基金的基本情况"), unsafe)) is None


def test_definitions_filename_and_other_product_categories_are_not_current():
    paragraphs = (span("广发某某同业存单基金基金合同"), span("二、释义"),
                  span("基金的类别：货币市场基金"),
                  span("三、基金的基本情况"), span("基金的类别"),
                  span("其他基金为债券型基金"), span("四、基金的投资"))
    assert category_value(paragraphs) is None


@pytest.mark.parametrize("heading", ["2.17 基金的投资", "十三、基金的投资", "第十二部分基金的投资"])
def test_unseen_investment_section_retains_current_mandate_only(heading):
    mandate = span("本基金投资于股票的比例不低于基金资产的70%。")
    other = span("另一基金投资于同业存单的比例不低于基金资产的80%。")
    paragraphs = (span(heading), span("投资范围"), mandate,
                  span("十四、基金的财产"), other)
    assert mandate in investment_spans(paragraphs)
    assert other not in investment_spans(paragraphs)


def test_directory_summary_and_mentions_do_not_establish_investment_scope():
    paragraphs = (span("十三、基金的投资……42"),
                  span("本基金投资于同业存单的比例不低于基金资产的80%。"),
                  span("详见十三、基金的投资"),
                  span("二十、基金合同摘要"), span("十三、基金的投资"),
                  span("本基金投资于股票的比例不低于基金资产的70%。"))
    assert investment_spans(paragraphs) == ()


def test_existing_trusted_section_path_is_supported():
    current = span("本基金投资于债券。", section="第十一部分基金的投资")
    summary = span("本基金投资于同业存单。", section="基金合同摘要 / 基金的投资")
    assert investment_spans((current, summary)) == (current,)


def test_category_value_cannot_cross_next_field_or_chapter():
    for next_field in ("基金的运作方式", "四、基金份额的发售"):
        paragraphs = (span("三、基金的基本情况"), span("基金的类别"),
                      span(next_field), span("混合型"))
        assert category_value(paragraphs) is None


def test_nested_plain_subheading_retains_scope_and_stale_path_cannot_extend_it():
    mandate = span("本基金投资于债券。", section="基金的投资")
    later = span("本基金投资于同业存单。", section="基金的投资")
    paragraphs = (span("十二、基金的投资"), span("一、投资目标"), mandate,
                  span("十三、基金的财产"), later)
    assert mandate in investment_spans(paragraphs)
    assert later not in investment_spans(paragraphs)


def test_protected_section_heading_does_not_open_body_scope():
    paragraphs = (span("十二、基金的投资", zone="revision"),
                  span("本基金投资于同业存单。"))
    assert investment_spans(paragraphs) == ()


def test_numbered_category_is_a_subsection_not_new_contract_chapter():
    paragraphs = (span("三、基金的基本情况"), span("二、基金的类别"), span("混合型"))
    assert category_value(paragraphs)[0] == "混合型"


def test_numbered_fund_investment_range_is_a_subsection():
    mandate = span("本基金投资于债券。")
    paragraphs = (span("三、基金的投资"), span("二、基金的投资范围"), mandate)
    assert mandate in investment_spans(paragraphs)


def test_unsupported_current_category_cannot_be_hidden_by_first_valid_value():
    paragraphs = (span("三、基金的基本情况"), span("基金的类别：混合型"),
                  span("基金的类型：未支持的专门基金"))
    with pytest.raises(QualificationEvidenceError, match="FUND_TYPE_EVIDENCE_AMBIGUOUS"):
        category_value(paragraphs)


def test_category_label_followed_by_explanation_is_not_a_type_value():
    paragraphs = (span("三、基金的基本情况"),
                  span("基金的类别：混合型基金是另一基金的类型"))
    assert category_value(paragraphs) is None


def test_unknown_explicit_main_chapter_ends_current_product_scope():
    paragraphs = (span("第十三部分基金的投资"), span("本基金投资于股票。"),
                  span("第十四部分另一产品说明"), span("本基金投资于同业存单。"))
    assert paragraphs[1] in investment_spans(paragraphs)
    assert paragraphs[3] not in investment_spans(paragraphs)


def test_unknown_same_level_numeric_section_ends_investment_scope():
    paragraphs = (span("4.6 基金的投资"), span("4.6.1 投资范围"),
                  span("本基金投资于股票。"), span("4.7 另一产品说明"),
                  span("本基金投资于同业存单。"))
    assert paragraphs[2] in investment_spans(paragraphs)
    assert paragraphs[4] not in investment_spans(paragraphs)


@pytest.mark.parametrize("value", [
    "股票型、指数型证券投资基金", "ETF联接基金", "股票型ETF联接基金", "联接基金",
    "交易型开放式指数证券投资基金联接基金", "基金中基金（FOF）", "货币市场基金",
    "同业存单指数证券投资基金", "中国证监会认可的其他基金或基金份额",
])
def test_existing_supported_category_families_remain_extractable(value):
    paragraphs = (span("三、基金的基本情况"), span("基金的类别：" + value))
    assert category_value(paragraphs)[0] == value


@pytest.mark.parametrize("text", [
    "二、基金的类别： 债券型 证券投资基金 三、基金的运作方式：契约型开放式",
    "（二）基金的类型：债券型 证券投资基金（四）基金的存续期限：不定期",
    "基金的类别：债券型 证券投资基金4.基金的投资目标：长期收益",
])
def test_inline_numbered_fields_keep_literal_category(text):
    paragraphs = (span("三、基金的基本情况"), span(text))
    quote, source, index = category_value(paragraphs)
    assert quote == "债券型 证券投资基金"
    assert quote in source.text and index == 1


def test_numbered_category_after_previous_field_value_and_inline_next_field():
    paragraphs = (span("三、基金的基本情况"),
                  span("某指数证券投资基金二、基金的类别"),
                  span("股票型、指数型证券投资基金三、基金的运作方式交易型开放式"))
    quote, source, index = category_value(paragraphs)
    assert quote == "股票型、指数型证券投资基金"
    assert source is paragraphs[2] and index == 1


@pytest.mark.parametrize("tail", [
    "基金的运作方式：开放式", "三、陌生叙述：另一基金是货币市场基金",
    "说明另一基金的运作方式是开放式",
])
def test_narrative_and_unknown_fields_do_not_hide_category_ambiguity(tail):
    paragraphs = (span("三、基金的基本情况"), span("基金的类别：混合型" + tail))
    assert category_value(paragraphs) is None


def test_inline_current_categories_must_not_hide_conflicts():
    paragraphs = (span("三、基金的基本情况"),
                  span("二、基金的类别：混合型三、基金的类型：货币市场基金"))
    with pytest.raises(QualificationEvidenceError, match="FUND_TYPE_EVIDENCE_CONFLICT"):
        category_value(paragraphs)


def test_duplicate_category_words_in_name_do_not_shift_value_evidence():
    paragraphs = (span("三、基金的基本情况"),
                  span("债券型证券投资基金二、基金的类别：债券型 证券投资基金"))
    assert category_value(paragraphs)[0] == "债券型 证券投资基金"


def test_bookmarked_pure_heading_uses_trusted_metadata_only():
    heading = replace(span("\ufff9三、基金的基本情况\ufff9", section="三、基金的基本情况"), segments=())
    paragraphs = (span("第一部分前言"), heading, span("基金的类别"), span("债券型基金"))
    assert category_value(paragraphs)[0] == "债券型基金"
    assert heading not in basic_spans(paragraphs)


@pytest.mark.parametrize("changes", [
    {"zone": "toc"}, {"logical_zone": "toc"}, {"reasons": ("field",)},
    {"section_path": "三、基金的基本情况其他叙述"},
])
def test_barrier_heading_must_not_bypass_scope_protection(changes):
    heading = replace(span("\ufff9三、基金的基本情况\ufff9", section="三、基金的基本情况"), segments=(), **changes)
    paragraphs = (span("第一部分前言"), heading, span("基金的类别"), span("债券型基金"))
    assert category_value(paragraphs) is None
