"""G12 must preserve a source clause's list number when replacing its body."""
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


def test_g12_keeps_the_numbered_list_prefix():
    inspection = inspect_docx(SOURCE, full=True)
    rule = next(item for item in GUIDE["groups"] if item["rule_id"] == "G12")
    target = Target("T", "G12", "p295", inspection.by_location("p295").text,
                    "needs_edit", "", start=0,
                    end=len(inspection.by_location("p295").text),
                    resolution="resolved", operations=("G12:1",))
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.start == 2  # after "5、"
    assert inspection.by_location("p295").text[:2] == "5、"
