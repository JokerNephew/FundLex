"""G22's distribution clause may omit one noun in the contract wording."""
import json
import sys
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import Target, plan_target

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g17_usage_site_closure import NoModel  # noqa: E402
from test_recall_core import _facts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发弘利3个月滚动持有债券型证券投资基金基金合同.docx"
GUIDE = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))


def test_g22_reference_offsets_expand_to_the_source_variant_clause():
    inspection = inspect_docx(SOURCE, full=True)
    rule = next(item for item in GUIDE["groups"] if item["rule_id"] == "G22")
    operation = rule["operations"][0]
    # The guide reference says 基金份额比例; the source p955 says 份额比例.
    target = Target("T", "G22", "p955", str(operation["old_text"]),
                    "needs_edit", "", start=0, end=39, resolution="resolved",
                    operations=("G22:0",))
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.start == 0 and edit.end == len(inspection.by_location("p955").text)
    assert edit.replacement.endswith(
        "，并加上返还基金份额持有人的销售服务费（如有）。")
    assert "份额比例进行分配。" not in edit.replacement
