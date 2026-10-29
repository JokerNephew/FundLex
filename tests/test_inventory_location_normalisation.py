"""Inventory locations copied in display brackets must still bind."""
from fundlex.recall import _normalise_physical_location


def test_bracketed_paragraph_and_table_locations_are_accepted():
    allowed = {"p87", "tbl0/r55/c1/p0"}
    assert _normalise_physical_location("[p87]", allowed) == "p87"
    assert _normalise_physical_location("[tbl0/r55/c1/p0]", allowed) == "tbl0/r55/c1/p0"
    assert _normalise_physical_location("【p87】", allowed) == "p87"


def test_location_in_prose_resolves_to_the_only_candidate():
    assert _normalise_physical_location(
        "第 [p87] 段（基金份额类别）", {"p87", "p83"}) == "p87"
    assert _normalise_physical_location("p999", {"p87"}) == "p999"
