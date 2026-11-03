"""FL-D1091（FL-D1084 体检缺陷①）：空差异文案走 COMPARE_COVERAGE_CHECKS 门。

门为 compile-time const=false（FL-D1045 用户口令压制展示层），真态分支保留
「已覆盖范围内」措辞仅作恢复用——双态各自钉死防再绕门；浏览器活态断言见
tests/browser/test_compare_scroll_perf.py::test_compare_empty_diff_copy_gated。
"""
from pathlib import Path

COMPARE_JS = Path(__file__).resolve().parents[1] / "frontend" / "compare.js"


def test_empty_diff_copy_gated_by_coverage_switch():
    src = COMPARE_JS.read_text(encoding="utf-8")
    # 双态原形：真态保留「已覆盖范围内」措辞，假态=统一「两份合同没有文字差异。」
    gated = "COMPARE_COVERAGE_CHECKS&&incomplete?'已覆盖范围内没有发现文字差异。':'两份合同没有文字差异。'"
    assert gated in src, "空差异文案必须走 COMPARE_COVERAGE_CHECKS 门（FL-D1091）"
    # 无第二个绕门出口
    assert src.count("已覆盖范围内没有发现文字差异") == 1
