"""Offline guard checks for the ff4d749 exact-code validation (no models)."""
from __future__ import annotations
import json
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from fundlex.generation.effects import _class_group_equivalent

cases = {
    "AD_vs_AD": ("A类、D类基金份额", "在投资者申购 A 类及 D 类基金份额时收取申购费用，不计提销售服务费；在投资者申购 C 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费"),
    "AD_vs_AC": ("A类、D类基金份额", "在投资者申购 A 类及 C 类基金份额时收取申购费用，不计提销售服务费"),
    "AD_vs_ACD": ("A类、D类基金份额", "在投资者申购 A 类、C 类及 D 类基金份额时收取申购费用，不计提销售服务费"),
}
result = {name: _class_group_equivalent(expected, quote) for name, (expected, quote) in cases.items()}
assert result == {"AD_vs_AD": True, "AD_vs_AC": False, "AD_vs_ACD": False}, result
print(json.dumps({"checks": result, "status": "PASS"}, ensure_ascii=False))
