"""A broad recovery target must not duplicate per-operation targets."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.recall import Target, dedupe_operation_targets


class _Inspection:
    def by_location(self, location):
        return SimpleNamespace(text="本基金将基金份额分为A类、C类、E类三种不同的类别。")


def _target(target_id, operations, *, state="satisfied", start=0, end=30,
            quote="A类基金份额"):
    return Target(target_id, "G04", "p160", quote, state, "",
                  start=start, end=end, resolution="resolved",
                  operations=tuple(operations))


def test_broad_recovery_target_is_dropped_when_subsets_cover_it():
    first = _target("T1", ["G04:0"])
    second = _target("T2", ["G04:1"], quote="C类基金份额")
    broad = _target("R034", ["G04:0", "G04:1"], quote="本基金将基金份额分为", end=32)
    kept, removed = dedupe_operation_targets(
        [first, second, broad], {"G04": {"operations": []}}, _Inspection())
    assert broad.out_of_scope is True
    assert "SUPERSEDED_BY_OPERATION_SUBSET_TARGETS" in broad.reason
    assert {target.target_id for target in kept} >= {"T1", "T2"}
