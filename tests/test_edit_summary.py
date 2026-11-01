"""edit_summary 导出行构造单测（用户视角结果清单/逐份修改说明 的单一事实源）。"""
from __future__ import annotations

from fundlex.edit_summary import (CLIP_LIMIT_AFTER, CLIP_LIMIT_BEFORE,
                                  DETAIL_CLIP_NOTE, EDIT_DETAIL_HEADER,
                                  OUTCOME_LABELS, RESULT_LIST_HEADER,
                                  clip_detail, edit_detail_rows, exception_note,
                                  guide_ref, outcome_label, result_list_row)

GUIDE = {"groups": [
    {"rule_id": "G12", "title": "赎回费归属改为全额计入基金财产：", "requirement": "r"},
    {"rule_id": "G13", "title": "删除 7 日短期持有赎回费旧句：", "requirement": "r"},
]}


def edit(**overrides):
    base = {"rule_id": "G12", "location": "p42", "operation": "replace",
            "components": [{"expected_old_text": "旧文"}], "replacement": "新文"}
    return base | overrides


def report(edits, **overrides):
    return {"guide": GUIDE, "plan": {"edits": edits}, **overrides}


def test_headers_are_reader_facing():
    assert RESULT_LIST_HEADER == ["序号", "合同文件", "处理结果", "修改处数", "修改内容摘要", "备注"]
    assert EDIT_DETAIL_HEADER == ["序号", "修改类型", "位置", "修改前", "修改后", "对应指引"]


def test_edit_detail_rows_one_row_per_edit():
    rows = edit_detail_rows(report([edit(), edit(rule_id="G15", location="p9",
                                                 operation="insert", replacement="新增条款")]))
    assert rows[0] == ["1", "替换", "p42", "旧文", "新文", "G12：赎回费归属改为全额计入基金财产"]
    assert rows[1][1] == "新增" and rows[1][3] == "（保留原文，在其后追加新条款）"
    assert rows[1][5] == "G15：删除销售服务费支付旧条款"  # RULE_SHORT 短标签


def test_edit_detail_rows_composite_rule_and_delete():
    rows = edit_detail_rows(report([edit(rule_id="G12+G13", replacement="")]))
    assert rows[0][1] == "删除"  # replace with empty replacement is a delete
    assert rows[0][4] == "（删除该句）"
    assert rows[0][5] == "G12＋G13：赎回费归属改为全额计入基金财产＋删除 7 日短期持有赎回费旧句"


def test_edit_detail_rows_clips_and_points_to_redline():
    long_text = "文" * 300
    rows = edit_detail_rows(report([edit(components=[{"expected_old_text": long_text}],
                                         replacement=long_text)]))
    before, after = rows[0][3], rows[0][4]
    assert before.endswith("…" + DETAIL_CLIP_NOTE) and len(before) < 300
    assert after.endswith("…" + DETAIL_CLIP_NOTE)
    assert CLIP_LIMIT_BEFORE <= 160 and CLIP_LIMIT_AFTER <= 200


def test_clip_detail_short_text_passes_through():
    assert clip_detail("短句", 160) == "短句"
    assert clip_detail("  多空格\n换行  ", 160) == "多空格 换行"


def test_guide_ref_without_rule():
    assert guide_ref(GUIDE, "") == "—"
    assert guide_ref(GUIDE, "G99") in {"G99：G99", "G99"}


def test_result_list_row_readable_and_notes():
    row = result_list_row(3, "甲合同.docx", report([edit()]),
                          {"delivery_status": "complete"})
    assert row == ["3", "甲合同.docx", "已修改并复核通过", "1", "赎回费归属改为全额计入基金财产", ""]
    row = result_list_row(1, "乙合同.docx", report([], delivery_status="incomplete",
                                                   unresolved=[{"rule_id": "G15"}]),
                          {"delivery_status": "incomplete"})
    assert row[5] == "1 项条款按安全规则保持原文，详见修改说明"
    row = result_list_row(2, "丙合同.docx", {}, {"delivery_status": "", "job_status": ""})
    assert row[2] == "处理进行中" and row[5] == ""


def test_exception_note_failure_and_exclusion():
    assert exception_note({}, {"job_status": "failed"}).startswith("处理未完成")
    assert exception_note({}, {"delivery_status": "excluded_by_fund_type"}) == "该类型合同不在本流程处理范围"
    assert exception_note(report([edit()]), {"delivery_status": "complete"}) == ""


def test_unknown_enums_fall_back_to_readable_text():
    """FL-D720：未知 delivery/operation 枚举不得把英文原值透传给用户。"""
    from fundlex.edit_summary import delivery_text, operation_text
    assert delivery_text({"delivery_status": "incomplete_v9"}) == "状态待确认"
    assert delivery_text({}, {}) == "处理进行中"  # 空值仍是「处理进行中」
    assert operation_text({"operation": "overwrite_paragraph"}) == "其他修改"
    assert operation_text({"operation": ""}) == "—"
    row = result_list_row(1, "合同.docx", {"delivery_status": "legacy_state",
                                           "plan": {"edits": [{"operation": "legacy_op"}]}},
                          {"delivery_status": "legacy_state"})
    assert row[2] == "状态待确认" and "legacy" not in ",".join(row)
    detail = edit_detail_rows({"plan": {"edits": [{"operation": "legacy_op",
                                                   "rule_id": "G12"}]}})
    assert detail[0][1] == "其他修改" and "legacy_op" not in ",".join(detail[0])


def test_outcome_labels_cover_the_five_buckets():
    assert OUTCOME_LABELS == ["已修改", "部分修改", "无需修改", "类型排除", "失败"]
    cases = [
        (report([edit()]), {"delivery_status": "complete"}, "已修改"),
        (report([]), {"delivery_status": "complete"}, "无需修改"),
        (report([edit()]), {"delivery_status": "incomplete"}, "部分修改"),
        ({}, {"delivery_status": "not_generated", "eligibility": "excluded_by_fund_type"}, "类型排除"),
        ({}, {"delivery_status": "excluded"}, "类型排除"),
        ({}, {"job_status": "failed", "delivery_status": "not_generated"}, "失败"),
        ({}, {"job_status": "running", "delivery_status": ""}, "处理进行中"),
        ({}, {"job_status": "", "delivery_status": ""}, "处理进行中"),
        ({}, {"upload_status": "pending", "delivery_status": "not_generated"}, "处理进行中"),
        ({}, {"upload_status": "rejected", "delivery_status": ""}, "未接收"),
    ]
    for rep, doc, expected in cases:
        assert outcome_label(rep, doc) == expected, (rep, doc, expected)
