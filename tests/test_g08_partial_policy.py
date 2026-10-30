"""G08 may need to replace a class split that omits the direct-sales exemption."""
import json
import sys
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import Target, plan_target

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_class_group_and_g18_variants import _facts  # noqa: E402
from test_g17_usage_site_closure import NoModel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发道琼斯美国石油开发与生产指数证券投资基金（QDII-LOF）基金合同.docx"
GUIDE = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))


def test_g08_partial_class_split_is_replaced_with_the_full_policy():
    inspection = inspect_docx(SOURCE, full=True)
    rule = next(item for item in GUIDE["groups"] if item["rule_id"] == "G08")
    text = inspection.by_location("p292").text
    quote = ("本基金C类基金份额和E类基金份额不收取申购费，"
             "A类人民币基金份额和A类美元现汇基金份额的申购费率由基金管理人决定，"
             "并在招募说明书中列示。")
    start = text.find(quote)
    target = Target("T", "G08", "p292", quote, "needs_edit", "",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=("G08:0",))
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert "通过直销机构" in edit.replacement
    assert "通过直销机构以外的其他销售机构" in edit.replacement
