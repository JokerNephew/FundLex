"""Construct independent v2 semantic fixtures and freeze their expectations.

Fixtures are built locally before any real-model run. Expectations describe the
required business semantics (actual share classes, no A/C literals, refusal on
missing or hybrid fee evidence, body/summary consistency), never a fixed string
equality against the reference clause.

Run::

    .venv\\Scripts\\python.exe -X utf8 tools\\evaluation\\v2_fixtures.py --output <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from docx import Document


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base(document: Document) -> None:
    document.add_paragraph("广发示例混合型证券投资基金基金合同")
    document.add_heading("基金的基本情况", level=1)
    document.add_paragraph("基金的类别：混合型证券投资基金")


def _investment(document: Document) -> None:
    document.add_heading("基金的投资", level=1)
    document.add_paragraph("本基金投资于股票的比例为60%-95%，投资于债券的比例不低于基金资产的80%。")


def _save(document: Document, path: Path) -> str:
    document.save(path)
    return _sha(path)


def build_fx01(path: Path) -> dict:
    document = Document()
    _base(document)
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph(
        "基金份额类别设置：本基金将基金份额分为 H 类、J 类和 K 类三种不同的类别。"
        "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费；"
        "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费。")
    _investment(document)
    return {"fixture_id": "FX01", "purpose": "非A/C类别按实际类别生成直销豁免条款",
            "file": path.name, "sha256": _save(document, path), "delivery": "evaluation_modified",
            "actions": {"R02-A1": {"status": "applied", "edits": 1,
                                   "generated_checks": [
                                       {"kind": "contains_all", "values": ["H 类", "J 类", "K 类"]},
                                       {"kind": "not_contains", "values": ["A类", "A 类", "C类", "C 类"]},
                                       {"kind": "no_digits"},
                                   ]}},
            "expected_classes": {"subscription_group": ["H"], "service_group": ["J", "K"]}}


def build_fx02(path: Path) -> dict:
    document = Document()
    _base(document)
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph(
        "基金份额类别设置：本基金将基金份额分为 F 类、D 类和 E 类三种不同的类别。"
        "在投资者申购 F 类基金份额时收取申购费用，不计提销售服务费；"
        "在投资者申购 D 类基金份额时不收取申购费用，从本类别基金资产中计提销售服务费，"
        "年费率为 0.4%；在投资者申购 E 类基金份额时不收取申购费用，从本类别基金资产中计提销售服务费，"
        "年费率为 0.2%。")
    _investment(document)
    return {"fixture_id": "FX02", "purpose": "同组类别费率不同，新文不得携带费率数字",
            "file": path.name, "sha256": _save(document, path), "delivery": "evaluation_modified",
            "actions": {"R02-A1": {"status": "applied", "edits": 1,
                                   "generated_checks": [
                                       {"kind": "contains_all", "values": ["F 类", "D 类", "E 类"]},
                                       {"kind": "not_contains", "values": ["A类", "C类", "0.4", "0.2", "%"]},
                                       {"kind": "no_digits"},
                                   ]}},
            "expected_classes": {"subscription_group": ["F"], "service_group": ["D", "E"]}}


def build_fx03(path: Path) -> dict:
    document = Document()
    _base(document)
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph(
        "基金份额类别设置：本基金将基金份额分为 G 类、H 类两种不同的类别，"
        "不同类别基金份额分别设置代码并分别公布净值。")
    _investment(document)
    return {"fixture_id": "FX03", "purpose": "收费属性证据不足时必须拒绝写入",
            "file": path.name, "sha256": _save(document, path), "delivery": "incomplete",
            "actions": {"R01-A1": {"status": "not_matched", "edits": 0,
                                   "allowed_reasons": ["TARGET_SCOPE_UNRESOLVED"]},
                        "R02-A1": {"status": "failed", "edits": 0,
                                   "allowed_reasons": ["PROFILE_EVIDENCE_INCOMPLETE"]}}}


def build_fx04(path: Path) -> dict:
    document = Document()
    _base(document)
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph(
        "基金份额类别设置：本基金将基金份额分为 H 类、J 类和 K 类三种不同的类别。"
        "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费；"
        "在投资者申购 J 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费；"
        "在投资者申购 K 类基金份额时收取申购费用，并从本类别基金资产中计提销售服务费。")
    _investment(document)
    return {"fixture_id": "FX04", "purpose": "混合收费类别不得被强行归组，必须拒绝",
            "file": path.name, "sha256": _save(document, path), "delivery": "incomplete",
            "actions": {"R02-A1": {"status": "failed", "edits": 0,
                                   "allowed_reasons": ["V2_HYBRID_CLASS_FEE_UNSUPPORTED",
                                                       "PROFILE_EVIDENCE_INCOMPLETE",
                                                       "V2_CLASS_DEFINITION_CONFLICT"]}}}


def build_fx05(path: Path) -> dict:
    document = Document()
    _base(document)
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph(
        "基金份额类别设置：本基金将基金份额分为 H 类、J 类和 K 类三种不同的类别。"
        "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费；"
        "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费。")
    _investment(document)
    document.add_heading("基金合同内容摘要", level=1)
    document.add_heading("基金的基本情况", level=1)
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph(
        "基金份额类别设置：本基金将基金份额分为 H 类、J 类和 K 类三种不同的类别。"
        "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费；"
        "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费。")
    return {"fixture_id": "FX05", "purpose": "正文与摘要相同定义复用同一新文并保持一致",
            "file": path.name, "sha256": _save(document, path), "delivery": "evaluation_modified",
            "actions": {"R02-A1": {"status": "applied", "edits": 2,
                                   "generated_checks": [
                                       {"kind": "contains_all", "values": ["H 类", "J 类、K 类"]},
                                       {"kind": "not_contains", "values": ["A类", "C类"]},
                                       {"kind": "no_digits"},
                                   ],
                                   "body_summary_identical": True}}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    fixtures = [builder(root / f"FX0{index}.docx") for index, builder in
                enumerate([build_fx01, build_fx02, build_fx03, build_fx04, build_fx05], start=1)]
    manifest = {"schema": "fundlex-v2-fixtures-v1",
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "note": "构造夹具；期望按业务语义登记，运行前冻结；不代表真实合同准确率",
                "fixtures": fixtures}
    path = root / "expected.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(root), "fixtures": [item["fixture_id"] for item in fixtures],
                      "expected_sha256": _sha(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
