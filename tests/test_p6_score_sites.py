"""P6 scorer FL-D450 counterexamples on actual DOCX files.

The old scorer could report ``completed`` when the obsolete string disappeared but
the replacement obligation was never written, when only the first append clause was
present, when a deleted clause was moved elsewhere, or when class facts were
unknown.  It also matched append text anywhere in the file, which hides a summary
site that was never changed while the body was.  These tests read real
``python-docx`` packages through the production ``paragraphs_of`` reader.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document

from tools.evaluation import p6_score
from tools.evaluation.p6_score import paragraphs_of, score_target


def _document(path: Path, paragraphs: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(path)
    return path


def _score(tmp_path: Path, target: dict, source: list[str], final: list[str],
           facts: dict | None = None) -> dict:
    source_path = _document(tmp_path / "source.docx", source)
    final_path = _document(tmp_path / "final.docx", final)
    return score_target(target, facts or {}, paragraphs_of(final_path),
                        paragraphs_of(source_path))


FACTS_WITH_SERVICE_FEE = {
    "classes": [
        {"name": "A类基金份额", "subscription_fee": True, "service_fee": False},
        {"name": "C类基金份额", "subscription_fee": False, "service_fee": True},
    ],
    "has_service_fee": True,
}


def test_replace_requires_the_new_obligation_not_only_old_text_removal(tmp_path):
    target = {"target_id": "t", "rule_id": "G14", "op": "replace",
              "old_text": "本基金可以调低赎回费率",
              "required_text": "基金管理人可以适当调低基金申购费率和销售服务费率。",
              "compact_start": 0}
    verdict = _score(tmp_path, target,
                     ["费用管理条款：本基金可以调低赎回费率。"],
                     ["费用管理条款：本基金可以不采取任何费用优惠。"])
    assert verdict["verdict"] != "completed"
    assert verdict["verdict"] == "wrong"


def test_append_requires_every_applicable_clause_not_only_the_first(tmp_path):
    target = {"target_id": "t", "rule_id": "G16", "op": "append",
              "required_text": ("销售服务费每日计提，按月支付；"
                                "持有超过一年的基金份额不再收取销售服务费。")}
    verdict = _score(tmp_path, target, ["原支付条款。"],
                     ["销售服务费每日计提，按月支付。"], FACTS_WITH_SERVICE_FEE)
    assert verdict["verdict"] != "completed"
    assert verdict["verdict"] == "not_executed"


def test_delete_anchor_moved_outside_search_window_is_not_completed(tmp_path):
    clause = "销售服务费可用于支付销售机构佣金。"
    target = {"target_id": "t", "rule_id": "G17", "op": "delete",
              "old_text": "销售服务费可用于支付销售机构佣金。", "compact_start": 0}
    final = ["保留其他无关条款。"] * 45 + [clause]
    verdict = _score(tmp_path, target, [clause], final)
    assert verdict["verdict"] != "completed"
    assert verdict["verdict"] == "kept"


def test_unknown_class_facts_cannot_prove_no_group_was_needed(tmp_path):
    target = {"target_id": "t", "rule_id": "G02", "op": "replace",
              "old_text": "A类基金份额", "required_text": "A类、B类基金份额",
              "compact_start": 0}
    for index, facts in enumerate(({"classes": []}, {}, {"classes": None})):
        directory = tmp_path / f"unknown-{index}"
        directory.mkdir()
        verdict = _score(directory, target, ["A类基金份额。"], ["A类基金份额。"], facts)
        assert verdict["verdict"] not in {"completed", "kept"}
        assert verdict["verdict"] == "unknown"


def test_correct_replace_is_completed(tmp_path):
    target = {"target_id": "t", "rule_id": "G14", "op": "replace",
              "old_text": "可以适当调低基金申购费率和基金赎回费率",
              "required_text": "基金管理人可以适当调低基金申购费率和销售服务费率。",
              "compact_start": 0,
              "requirement": ("将“基金管理人可以适当调低基金申购费率和赎回费率。”变更为"
                              "“基金管理人可以适当调低基金申购费率和销售服务费率。”")}
    final = ["在基金促销活动期间，基金管理人可以适当调低基金申购费率和基金销售服务费率。"]
    verdict = _score(tmp_path, target, ["在基金促销活动期间，基金管理人可以适当调低基金申购费率和赎回费率。"],
                     final)
    assert verdict["verdict"] == "completed"


def test_correct_full_append_with_contract_wording_variants_is_completed(tmp_path):
    target = {"target_id": "t", "rule_id": "G03", "op": "append",
              "required_text": ("投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类基金份额时，"
                                "不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。"
                                "对于投资者通过直销机构之外的其他销售机构申购的C类基金份额且持续持有期限超过一年的，"
                                "不再继续收取销售服务费。")}
    final = ["基金份额类别定义。" + "投资者通过直销机构（含基金管理人及其销售子公司，下同）认购/申购本基金A类基金份额时，"
             "不收取认购/申购费用；通过直销机构认购/申购的C类基金份额，不收取销售服务费。"
             "对于投资者通过直销机构之外的其他销售机构认购/申购的C类基金份额且持续持有期限超过一年"
             "（即365天，下同）的，不再继续收取销售服务费。"]
    verdict = _score(tmp_path, target, ["基金份额类别定义。"], final, FACTS_WITH_SERVICE_FEE)
    assert verdict["verdict"] == "completed"


def test_correct_single_class_append_is_not_false_rejected(tmp_path):
    facts = {"classes": [{"name": "基金份额", "subscription_fee": True, "service_fee": False}],
             "has_service_fee": False}
    target = {"target_id": "t", "rule_id": "G01", "op": "append",
              "required_text": ("投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类基金份额时，"
                                "不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。")}
    final = ["释义。" + "投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金基金份额时，"
             "不收取认购/申购费用。"]
    verdict = _score(tmp_path, target, ["释义。"], final, facts)
    assert verdict["verdict"] == "completed"


def test_correct_delete_with_paragraph_removed_is_completed(tmp_path):
    clause = "C类基金份额的销售服务费主要用于支付销售机构佣金。"
    target = {"target_id": "t", "rule_id": "G17", "op": "delete",
              "old_text": "销售服务费主要用于支付销售机构佣金",
              "requirement": f"删除原条款“{clause}”。", "compact_start": 0}
    verdict = _score(tmp_path, target, [clause],
                     ["基金管理人应当在每年结束之日起三个月内编制年度报告。"])
    assert verdict["verdict"] == "completed"


def test_declared_body_site_completes_but_unchanged_summary_site_does_not(tmp_path):
    required = ("销售服务费每日计提，按月支付；持有超过一年的基金份额不再收取销售服务费。")
    # FL-D790: the append window now reaches six paragraphs backwards, matching
    # real body/summary distances; keep the fixture sites at a realistic gap so
    # the body append stays outside the summary site's window (was 4 apart).
    source = ["正文：基金份额类别定义。", "间隔一。", "间隔二。", "间隔三。",
              "间隔四。", "间隔五。", "间隔六。", "间隔七。",
              "摘要：基金份额类别定义。", "结尾。"]
    final = [source[0] + "销售服务费每日计提，按月支付；持有超过一年的基金份额不再收取销售服务费。"
             ] + source[1:]
    body_target = {"target_id": "body", "rule_id": "G16", "op": "append",
                   "required_text": required, "paragraph_index": 0, "site_scope": "body"}
    summary_target = {"target_id": "summary", "rule_id": "G16", "op": "append",
                      "required_text": required, "paragraph_index": 8,
                      "site_scope": "summary"}
    body = _score(tmp_path / "body", body_target, source, final, FACTS_WITH_SERVICE_FEE)
    summary = _score(tmp_path / "summary", summary_target, source, final,
                     FACTS_WITH_SERVICE_FEE)
    assert body["verdict"] == "completed" and body["site_scoped"] is True
    assert summary["verdict"] != "completed"
    assert summary["site_scoped"] is True


def test_declared_body_replace_does_not_prove_the_summary_site(tmp_path):
    source = ["本基金可以调低赎回费率。", "间隔一。", "间隔二。", "间隔三。",
              "本基金可以调低赎回费率。"]
    final = ["基金管理人可以适当调低基金申购费率和销售服务费率。", "间隔一。", "间隔二。",
             "间隔三。", "本基金可以调低赎回费率。"]
    target = {"target_id": "body", "rule_id": "G14", "op": "replace",
              "old_text": "本基金可以调低赎回费率",
              "required_text": "基金管理人可以适当调低基金申购费率和销售服务费率。",
              "paragraph_index": 0, "site_scope": "body"}
    summary = {"target_id": "summary", "rule_id": "G14", "op": "replace",
               "old_text": "本基金可以调低赎回费率",
               "required_text": "基金管理人可以适当调低基金申购费率和销售服务费率。",
               "paragraph_index": 4, "site_scope": "summary"}
    body = _score(tmp_path / "body", target, source, final)
    summary_verdict = _score(tmp_path / "summary", summary, source, final)
    assert body["verdict"] == "completed"
    assert summary_verdict["verdict"] != "completed"
    # The summary still carries the superseded wording at its own site.
    assert summary_verdict["verdict"] == "kept"


def test_legacy_labels_report_document_wide_limitation(tmp_path, monkeypatch, capsys):
    data_root = tmp_path / "data"
    words = data_root / "funds_word"
    words.mkdir(parents=True)
    _document(words / "源.docx", ["原条款。"])
    run = tmp_path / "run"
    case = run / "D01"
    case.mkdir(parents=True)
    _document(case / "final.docx", ["原条款。", "销售服务费每日计提，按月支付。"])
    (run / "batch.json").write_text(json.dumps({"cases": ["D01"]}), encoding="utf-8")
    labels = {"cases": [{
        "case_id": "D01", "group": "dev", "file": "源.docx", "target_count": 1,
        "facts": {"classes": [{"name": "A类基金份额", "subscription_fee": True,
                               "service_fee": False},
                              {"name": "C类基金份额", "subscription_fee": False,
                               "service_fee": True}]},
        "targets": [{"target_id": "D01:G16", "rule_id": "G16", "op": "append",
                     "required_text": "销售服务费每日计提，按月支付。"}],
    }]}
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "score.json"
    monkeypatch.setattr(sys, "argv", [
        "p6_score", "--labels", str(labels_path), "--run", str(run),
        "--data-root", str(data_root), "--output", str(output), "--group", "dev",
    ])
    assert p6_score.main() == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["scoring"]["site_scoped_targets"] == 0
    assert payload["scoring"]["legacy_document_wide_targets"] == 1
    assert payload["limitations"]
    assert "document-wide" in payload["limitations"][0]
